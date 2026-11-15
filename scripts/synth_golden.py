#!/usr/bin/env python3
"""The golden record of what the standard corpora hash to, and the check against it.

PART R1 makes the three hand-written plants declarative. The whole value of that refactor rests
on one claim: that it changed the *description* of a plant and not a single number the plant
produces. A claim like that is worth exactly as much as the thing that would catch it being
false, so the digests are captured here *before* the refactor and compared after it.

What is recorded, per corpus in ``configs/synth/``:

* every generated file's SHA-256, its size and its record count — the telemetry, the topology and
  the capture, which between them are the whole payload a detector would ever see;
* the manifest's own SHA-256, which covers the plant's full declaration, the benign events and
  the run spec, so a signal that quietly changed its noise model or a coupling that quietly lost
  a driver fails this check even though every published number stayed the same.

The payload itself is still not committed (ADR 0073's rule, and ``.gitignore`` enforces it). Each
corpus is generated into a temporary directory, digested, and thrown away. What is committed is
``tests/synth/golden/corpus_digests.json``, which is small, and the script that produced it, so
the capture is auditable rather than asserted.

**A mismatch is a result, not a thing to fix by recapturing.** If a change makes these digests
move, either the change is wrong or the reason it is right has to be written down first. Rerunning
with ``--write`` to make a red check go green destroys the only evidence that the refactor was
behaviour-preserving. See PART R1: "If byte-identical is impossible for a justified reason, stop
and report instead of changing the golden values."

Usage::

    python scripts/synth_golden.py            # check the corpora against the committed record
    python scripts/synth_golden.py --write    # capture it (first time, or a declared change)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Final

REPO_ROOT: Final = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from phos.synth.catalogue import DatasetConfig, load_configs  # noqa: E402
from phos.synth.generate import MANIFEST_FILE, generate_dataset  # noqa: E402
from phos.synth.manifest import digest_of  # noqa: E402

__all__ = [
    "CONFIG_DIR",
    "GOLDEN_PATH",
    "SCHEMA_VERSION",
    "capture",
    "compare",
    "load_golden",
    "main",
]

logger = logging.getLogger("phos.synth.golden")

CONFIG_DIR: Final = REPO_ROOT / "configs" / "synth"
GOLDEN_PATH: Final = REPO_ROOT / "tests" / "synth" / "golden" / "corpus_digests.json"
SCHEMA_VERSION: Final = 1
"""Bumped when the shape of the golden record changes, not when a digest does."""

CorpusRecord = dict[str, object]
GoldenRecord = dict[str, object]


def capture_one(config: DatasetConfig) -> CorpusRecord:
    """Generate one corpus into a temporary directory and return its digests.

    Args:
        config: The standard dataset to produce.

    Returns:
        What this corpus hashes to: the run that made it, its size, and a digest per file.
    """
    with tempfile.TemporaryDirectory(prefix="phos-golden-") as scratch:
        directory, manifest = generate_dataset(config, Path(scratch))
        manifest_sha256, _ = digest_of(directory / MANIFEST_FILE)
        return {
            "plant_id": config.plant_id,
            "seed": config.seed,
            "traffic_seed": config.traffic_seed,
            "samples": manifest.samples,
            "events": len(manifest.events),
            "manifest_sha256": manifest_sha256,
            "files": {
                file.filename: {
                    "kind": file.kind,
                    "records": file.records,
                    "sha256": file.sha256,
                    "size_bytes": file.size_bytes,
                }
                for file in manifest.files
            },
        }


def capture(configs: Sequence[DatasetConfig]) -> GoldenRecord:
    """Generate every standard corpus and return the whole golden record.

    Args:
        configs: The standard datasets, in catalogue order.

    Returns:
        The record, ready to be written or compared. Corpora are keyed by name and the mapping is
        written sorted, so the file does not reorder itself between captures.
    """
    corpora: dict[str, CorpusRecord] = {}
    for config in configs:
        logger.info("capturing %s", config.name)
        corpora[config.name] = capture_one(config)
    return {"schema_version": SCHEMA_VERSION, "corpora": corpora}


def load_golden(path: Path = GOLDEN_PATH) -> GoldenRecord:
    """Read the committed golden record.

    Args:
        path: The record to read.

    Returns:
        The parsed record.

    Raises:
        FileNotFoundError: If no record has been captured. The message says how to capture one,
            because an absent golden is a missing safeguard rather than a missing file.
        ValueError: If the record carries a schema version this code does not read.
    """
    if not path.exists():
        raise FileNotFoundError(
            f"no golden record at {path}; capture one with "
            "`python scripts/synth_golden.py --write` before changing the generator"
        )
    record: GoldenRecord = json.loads(path.read_text(encoding="utf-8"))
    version = record.get("schema_version")
    if version != SCHEMA_VERSION:
        raise ValueError(
            f"{path} carries schema_version {version!r}; this code reads {SCHEMA_VERSION}"
        )
    return record


def write_golden(record: GoldenRecord, path: Path = GOLDEN_PATH) -> None:
    """Write the golden record, sorted and newline-terminated so re-capture is a clean diff."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    logger.info("wrote %s", path)


def compare(fresh: GoldenRecord, golden: GoldenRecord) -> list[str]:
    """Return one line per difference between a fresh capture and the committed record.

    Every difference is named specifically — which corpus, which file, which field, and both
    values — because "the golden test failed" is not enough to tell a refactor that moved a
    digest from a config that was edited on purpose.

    Args:
        fresh: Digests just captured.
        golden: Digests read from the committed record.

    Returns:
        The differences, in a stable order. Empty when the two agree.
    """
    differences: list[str] = []
    fresh_corpora = _corpora(fresh)
    golden_corpora = _corpora(golden)

    for name in sorted(set(golden_corpora) - set(fresh_corpora)):
        differences.append(f"{name}: in the golden record but no config produces it now")
    for name in sorted(set(fresh_corpora) - set(golden_corpora)):
        differences.append(f"{name}: generated now but absent from the golden record")

    for name in sorted(set(fresh_corpora) & set(golden_corpora)):
        differences.extend(_compare_corpus(name, fresh_corpora[name], golden_corpora[name]))
    return differences


def _corpora(record: GoldenRecord) -> dict[str, CorpusRecord]:
    """Return the corpus mapping from a record, typed for the comparison."""
    corpora = record.get("corpora", {})
    if not isinstance(corpora, dict):
        raise ValueError("golden record's 'corpora' is not a mapping")
    return dict(corpora)


def _compare_corpus(name: str, fresh: CorpusRecord, golden: CorpusRecord) -> list[str]:
    """Return the differences for one corpus."""
    differences: list[str] = []
    for field in ("plant_id", "seed", "traffic_seed", "samples", "events", "manifest_sha256"):
        if fresh.get(field) != golden.get(field):
            differences.append(
                f"{name}: {field} is {fresh.get(field)!r}, golden says {golden.get(field)!r}"
            )

    fresh_files = _files(fresh)
    golden_files = _files(golden)
    for filename in sorted(set(golden_files) - set(fresh_files)):
        differences.append(f"{name}: {filename} is no longer written")
    for filename in sorted(set(fresh_files) - set(golden_files)):
        differences.append(f"{name}: {filename} is written now and was not before")
    for filename in sorted(set(fresh_files) & set(golden_files)):
        for field in ("kind", "records", "sha256", "size_bytes"):
            now = fresh_files[filename].get(field)
            before = golden_files[filename].get(field)
            if now != before:
                differences.append(f"{name}: {filename} {field} is {now!r}, golden says {before!r}")
    return differences


def _files(corpus: CorpusRecord) -> dict[str, dict[str, object]]:
    """Return a corpus record's per-file mapping, typed for the comparison."""
    files = corpus.get("files", {})
    if not isinstance(files, dict):
        raise ValueError("corpus record's 'files' is not a mapping")
    return dict(files)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns a process exit code."""
    parser = argparse.ArgumentParser(
        description="Capture or check the golden digests of the standard synthetic corpora."
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="capture the record and overwrite it; only for a first capture or a declared change",
    )
    arguments = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    configs = load_configs(CONFIG_DIR)
    fresh = capture(configs)

    if arguments.write:
        write_golden(fresh)
        return 0

    try:
        golden = load_golden()
    except (FileNotFoundError, ValueError) as error:
        logger.error("%s", error)
        return 2

    differences = compare(fresh, golden)
    if differences:
        logger.error("%d difference(s) from the golden record:", len(differences))
        for line in differences:
            logger.error("  %s", line)
        logger.error(
            "Do not rerun with --write to clear this. A moved digest is a changed corpus; "
            "say why it changed, or the change is wrong."
        )
        return 1
    logger.info("%d corpora match the golden record", len(_corpora(golden)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

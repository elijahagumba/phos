#!/usr/bin/env python3
"""Acquire the public corpora described in ``data/registry.json``.

This script is the only thing in PHOS that reaches the network, and it is deliberately not part
of the ``phos`` package: the core is pure and offline (Constitution §3.8). It downloads a
registered dataset into ``data/<name>/``, records what it got, converts it into a form the
existing :class:`phos.eval.LabelledCsvAdapter` can read without modification, and writes the
per-dataset manifest.

Three properties matter more than convenience here:

* **Idempotence.** A file already present at its registered size is not re-downloaded, so
  re-running the script is free and safe.
* **Nothing it downloads is committable.** ``.gitignore`` excludes every payload under
  ``data/<name>/`` while keeping ``manifest.json`` tracked. The script never touches git.
* **Preparation is explicit, not inferred.** Timestamp formats, label values and dropped columns
  come from the registry, which recorded them after someone read the actual file. Nothing is
  guessed at load time, because a wrong guess silently invalidates every metric computed
  downstream.

Usage::

    python scripts/fetch_datasets.py --list
    python scripts/fetch_datasets.py --all
    python scripts/fetch_datasets.py batadal hai
    python scripts/fetch_datasets.py --all --yes      # skip the size confirmation
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import tarfile
import urllib.error
import urllib.request
import zipfile
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Final

import pandas
from pydantic import BaseModel, ConfigDict, Field

REPO_ROOT: Final = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from phos.eval.batch_distillation import (  # noqa: E402
    RECIPE_STEP_FEATURE,
    UNSCORED_LABEL,
    JoinSpec,
    PrepareError,
    PrepareResult,
    prepare_corpus,
)
from phos.eval.data4cyber import Data4CyberPrepareSpec  # noqa: E402

if TYPE_CHECKING:
    from phos.eval.data4cyber import PrepareResult as Data4CyberPrepareResult

DATA_DIR: Final = REPO_ROOT / "data"
REGISTRY_PATH: Final = DATA_DIR / "registry.json"

#: Datasets whose licence was not positively established are never downloaded. The registry
#: records why for each one; this is the enforcement point.
FETCHABLE_STATUSES: Final = frozenset({"integrated", "fetched", "labels-only"})

_USER_AGENT: Final = "phos-dataset-fetcher/1.0 (research; +https://github.com/icsdataset/hai)"
_DOWNLOAD_CHUNK: Final = 1 << 20

logger = logging.getLogger("phos.fetch")


class FetchError(RuntimeError):
    """Raised when a dataset cannot be acquired or prepared as the registry describes it."""


class LicenseInfo(BaseModel):
    """The licence under which a corpus is redistributed.

    Attributes:
        spdx: SPDX identifier where one applies, otherwise ``None``.
        name: Human-readable licence name.
        url: Canonical licence text.
        status: ``explicit`` when a licence is stated at the source, ``unclear`` when only a
            citation request was found, ``form-required`` when access is gated, ``unverified``
            when nobody has checked yet.
        evidence: Where the statement was read. This is what makes the claim auditable.
        permits_research_use: Tri-state; ``None`` means undetermined, never "probably".
    """

    model_config = ConfigDict(frozen=True)

    spdx: str | None = None
    name: str
    url: str | None = None
    status: str
    evidence: str
    permits_research_use: bool | None = None


class RemoteFile(BaseModel):
    """One downloadable file belonging to a dataset.

    Attributes:
        url: Direct download URL. No forms, no tokens, no scraping.
        filename: Name to store it under, inside the dataset directory.
        size_bytes: Expected size, used both for the confirmation prompt and to decide whether an
            existing file is complete.
        role: ``train``, ``test``, ``labels`` or ``events``.
        note: Anything worth knowing about the file's contents.
        sha256: Upstream checksum, when the publisher provides one. Verified after download and
            after finding an already-present file, because a size match is a weak claim about a
            multi-gigabyte transfer and the publisher went to the trouble of telling us the strong
            one.
        md5: Upstream MD5, when that is what the publisher publishes (Zenodo records). Same
            purpose as ``sha256``; recorded separately because the two are not interchangeable.
        extract: Whether this file is an archive to unpack in place. Extraction is skipped when
            the target directory already exists, so re-running the script stays free.
        extract_to: Directory the archive unpacks into, relative to the dataset directory. Used
            only to decide whether extraction has already happened.
    """

    model_config = ConfigDict(frozen=True)

    url: str
    filename: str
    size_bytes: int = Field(ge=0)
    role: str = "data"
    note: str = ""
    sha256: str | None = None
    md5: str | None = None
    extract: bool = False
    extract_to: str = ""


class PrepareStep(BaseModel):
    """How to turn one downloaded file into a CSV the shipped adapter can read.

    Every field exists because some real corpus needed it. Nothing here is speculative.

    Attributes:
        source_file: Downloaded filename to read. ``.gz`` is decompressed transparently.
        output_file: Prepared CSV to write, beside the source.
        timestamp_column: Column holding the row timestamp, after any name stripping.
        timestamp_format: ``strptime`` format, pinned so parsing never depends on inference.
        label_column: Column holding ground truth, after any name stripping.
        attack_values: The exact cell values that mean "attack". Everything else becomes normal,
            which is what makes an "unlabelled" sentinel such as BATADAL's ``-999`` safe.
        drop_columns: Columns to discard, typically because they leak the label.
        strip_column_names: Strip surrounding whitespace from every column name.
        row_stride: Keep every Nth row. ``1`` keeps the corpus at full resolution. This exists
            for one concrete reason: the ontology represents every cell as a `Observation`
            model, so HAI's 216001 rows x 79 signals at 1 Hz is 17 million objects, which is not
            tractable in memory. Any stride above 1 is recorded in the manifest's ``source_note``
            and therefore in every report the corpus produces, so a number is never quietly
            computed on a thinned corpus.
    """

    model_config = ConfigDict(frozen=True)

    source_file: str
    output_file: str
    timestamp_column: str
    timestamp_format: str
    label_column: str
    attack_values: list[str]
    drop_columns: list[str] = Field(default_factory=list)
    strip_column_names: bool = True
    row_stride: int = Field(default=1, ge=1)


class DatasetEntry(BaseModel):
    """A single registered corpus.

    Attributes:
        name: Directory name under ``data/`` and the key used on the command line.
        title: Full name of the corpus.
        domain: ``ATLAS`` (industrial/OT) or ``SENTIEL`` (enterprise/cloud).
        homepage: Where the corpus is published.
        status: Acquisition state; only :data:`FETCHABLE_STATUSES` are ever downloaded.
        status_note: Why the corpus is in that state.
        license: Its licence, with the evidence for it.
        citation: How to cite it.
        files: Files this script may download.
        prepare: Role-keyed preparation steps, or ``None`` when the corpus is not a single-file
            labelled CSV. A multi-file join (batch-distillation) uses ``join`` instead.
        join: How to join a multi-file experiment corpus into prepared CSVs, or ``None``.
        grid_prepare: Data4Cyber Track A (S0 fit / S1 score). Not a command-corpus path.
        release: The specific release fetched, e.g. ``"r3.1"``. Present for corpora published as
            several independently-labelled releases, where "which one" is part of the result.
        payload_license: A second, conflicting licence shipped *inside* the payload, when there is
            one. Recorded as its own field rather than folded into `license` because a corpus whose
            catalogue record and whose own bundled terms disagree is a fact a reader must be able
            to see, not a discrepancy for whoever wrote the registry to quietly resolve.
        caveats: Statements that must travel with every number computed from this corpus.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    name: str
    title: str
    domain: str
    homepage: str
    status: str
    status_note: str = ""
    license: LicenseInfo
    citation: str = ""
    files: list[RemoteFile] = Field(default_factory=list)
    prepare: dict[str, PrepareStep] | None = None
    join: JoinSpec | None = None
    grid_prepare: Data4CyberPrepareSpec | None = None
    release: str | None = None
    payload_license: LicenseInfo | None = None
    caveats: list[str] = Field(default_factory=list)

    @property
    def fetchable(self) -> bool:
        """Return whether this corpus is cleared for download."""
        return self.status in FETCHABLE_STATUSES

    def total_bytes(self) -> int:
        """Return the summed registered size of every file this corpus would download."""
        return sum(file.size_bytes for file in self.files)


class Registry(BaseModel):
    """The committed catalogue of corpora.

    Attributes:
        schema_version: Incremented if the shape below ever changes.
        verified_on: When the licences and label semantics were last checked against source.
        size_confirm_threshold_bytes: Downloads totalling more than this need explicit consent.
        datasets: Every registered corpus, fetchable or not.
    """

    model_config = ConfigDict(frozen=True)

    schema_version: int
    verified_on: str = ""
    size_confirm_threshold_bytes: int = 300 * 1024 * 1024
    datasets: list[DatasetEntry]

    def by_name(self, name: str) -> DatasetEntry:
        """Return the entry called ``name``.

        Raises:
            FetchError: If no such dataset is registered, naming the ones that are.
        """
        for dataset in self.datasets:
            if dataset.name == name:
                return dataset
        known = ", ".join(sorted(entry.name for entry in self.datasets))
        raise FetchError(f"unknown dataset {name!r}; the registry has: {known}")


def load_registry(path: Path = REGISTRY_PATH) -> Registry:
    """Read and validate the dataset registry.

    Raises:
        FetchError: If the registry is missing.
    """
    if not path.is_file():
        raise FetchError(f"registry not found at {path}")
    return Registry.model_validate_json(path.read_text(encoding="utf-8"))


def human_bytes(count: int) -> str:
    """Render a byte count in the largest unit that keeps it readable."""
    size = float(count)
    for unit in ("B", "KB", "MB", "GB"):
        if abs(size) < 1024.0 or unit == "GB":
            return f"{size:,.1f} {unit}" if unit != "B" else f"{int(size):,} B"
        size /= 1024.0
    raise AssertionError("unreachable")


def sha256_of(path: Path) -> str:
    """Return the SHA-256 of a file, read in chunks so a multi-gigabyte file still works."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_DOWNLOAD_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, destination: Path) -> None:
    """Download ``url`` to ``destination`` atomically.

    The file is written to a ``.partial`` sibling and renamed only on success, so an interrupted
    run can never leave a truncated file that the next run would mistake for complete.

    Raises:
        FetchError: If the transfer fails.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".partial")
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            with partial.open("wb") as handle:
                while chunk := response.read(_DOWNLOAD_CHUNK):
                    handle.write(chunk)
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        partial.unlink(missing_ok=True)
        raise FetchError(f"failed to download {url}: {error}") from error
    partial.replace(destination)


def md5_of(path: Path) -> str:
    """Return the MD5 of a file. Used only to check a publisher's published digest."""
    digest = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as handle:
        while chunk := handle.read(_DOWNLOAD_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def locate_file(remote: RemoteFile, dataset_dir: Path) -> Path:
    """Return where ``remote`` lives, preferring the dataset root then ``raw/``.

    The batch-distillation intake stored its zips under ``raw/``; BATADAL and HAI store theirs
    at the dataset root. Looking in both keeps a re-run from downloading a file we already have.
    """
    for folder in (dataset_dir, dataset_dir / "raw"):
        candidate = folder / remote.filename
        if candidate.is_file():
            return candidate
    return dataset_dir / remote.filename


def fetch_file(remote: RemoteFile, dataset_dir: Path, *, force: bool = False) -> Path:
    """Ensure ``remote`` is present locally, downloading it only if it is not.

    A file is considered already present when it exists and its size matches the registry. A
    size mismatch is treated as a truncated download and re-fetched rather than trusted.
    """
    destination = locate_file(remote, dataset_dir)
    if destination.is_file() and not force:
        actual = destination.stat().st_size
        if remote.size_bytes == 0 or actual == remote.size_bytes:
            logger.info("  present  %-34s %14s", remote.filename, human_bytes(actual))
            verify_checksum(remote, destination)
            return destination
        logger.warning(
            "  re-fetch %-34s size %s != registered %s",
            remote.filename,
            human_bytes(actual),
            human_bytes(remote.size_bytes),
        )
        destination = dataset_dir / remote.filename
    else:
        destination = dataset_dir / remote.filename
    logger.info("  GET      %-34s %14s", remote.filename, human_bytes(remote.size_bytes))
    download(remote.url, destination)
    size = destination.stat().st_size
    logger.info(
        "  stored   %-34s %14s  sha256=%s",
        remote.filename,
        human_bytes(size),
        sha256_of(destination)[:16],
    )
    verify_checksum(remote, destination)
    return destination


def verify_checksum(remote: RemoteFile, destination: Path) -> None:
    """Check a downloaded file against its registered checksum, if one is registered.

    A size match is a weak claim about a multi-gigabyte transfer; when the publisher ships a
    checksum, not checking it is a choice to know less than we were told. SHA-256 is preferred
    when both exist; MD5 is what Zenodo publishes and is checked as the publisher's digest, not
    as a cryptographic claim.

    Raises:
        FetchError: On mismatch. The file is left in place so it can be inspected rather than
            silently re-downloaded into the same corrupt state.
    """
    if remote.sha256 is not None:
        actual = sha256_of(destination)
        if actual != remote.sha256:
            raise FetchError(
                f"{destination.name}: sha256 {actual} does not match the registered "
                f"{remote.sha256}. The file is corrupt or is not the file the registry describes; "
                "it has been left in place for inspection."
            )
        logger.info("  verified %-34s sha256 matches upstream", remote.filename)
    if remote.md5 is not None:
        actual_md5 = md5_of(destination)
        if actual_md5 != remote.md5:
            raise FetchError(
                f"{destination.name}: md5 {actual_md5} does not match the registered "
                f"{remote.md5}. The file is corrupt or is not the file the registry describes; "
                "it has been left in place for inspection."
            )
        logger.info("  verified %-34s md5 matches upstream", remote.filename)


def extract_archive(remote: RemoteFile, dataset_dir: Path, archive: Path | None = None) -> None:
    """Unpack a registered archive in place, skipping the work if it is already unpacked.

    Tar extraction uses ``filter="data"``, which refuses absolute paths, parent-directory escapes,
    links out of the tree, and device nodes. Zip members are checked for the same escapes before
    extraction. A published research corpus is not hostile input, but it is input, and unpacking
    it into the repository is exactly where that assumption would cost something if it were ever
    wrong.

    Raises:
        FetchError: If the archive cannot be read or a member is refused.
    """
    if not remote.extract:
        return
    marker = remote.extract_to or Path(remote.filename).name.split(".")[0]
    if _already_extracted(dataset_dir, marker):
        logger.info("  present  %-34s already extracted", marker)
        return
    source = archive if archive is not None else locate_file(remote, dataset_dir)
    logger.info("  extract  %-34s -> %s", remote.filename, marker)
    try:
        if source.suffix.lower() == ".zip":
            _extract_zip(source, dataset_dir)
        else:
            with tarfile.open(source, "r:*") as handle:
                handle.extractall(dataset_dir, filter="data")
    except (OSError, tarfile.TarError, zipfile.BadZipFile) as error:
        raise FetchError(f"failed to extract {source}: {error}") from error


def _already_extracted(dataset_dir: Path, marker: str) -> bool:
    """Return whether ``marker`` already exists as an extracted directory under ``dataset_dir``."""
    if not marker:
        return False
    direct = dataset_dir / marker
    if direct.exists():
        return True
    return any(path.is_dir() for path in dataset_dir.rglob(marker))


def _extract_zip(archive: Path, dataset_dir: Path) -> None:
    """Extract ``archive`` into ``dataset_dir``, refusing path-escape members."""
    destination = dataset_dir.resolve()
    with zipfile.ZipFile(archive) as handle:
        for info in handle.infolist():
            name = info.filename.replace("\\", "/")
            if name.startswith("/") or ".." in Path(name).parts:
                raise FetchError(f"refusing zip member {info.filename!r} from {archive.name}")
            target = (destination / name).resolve()
            if target != destination and not str(target).startswith(str(destination) + "/"):
                raise FetchError(f"refusing zip member {info.filename!r} from {archive.name}")
        handle.extractall(destination)


def prepare_csv(step: PrepareStep, dataset_dir: Path) -> tuple[Path, list[str]]:
    """Convert one downloaded file into a CSV the shipped adapter reads correctly.

    Preparation exists so that :class:`phos.eval.LabelledCsvAdapter` needs no changes to read
    real corpora. It does exactly four things, each forced by a real defect found in a real file:

    1. Strips whitespace from column names, because BATADAL's test file names its columns
       ``" L_T1"`` while its training file names them ``"L_T1"``. A model fitted on one and
       scored on the other would match no baselines and report a silent zero recall.
    2. Parses the timestamp with a pinned format, because BATADAL's ``%d/%m/%y`` dates are parsed
       inconsistently by inference — some rows day-first, some month-first — which scrambles the
       ordering the whole harness depends on. Output is ISO-8601 UTC.
    3. Reduces the label to ``1``/``0`` by exact membership of ``attack_values``, because the
       shipped default treats any non-zero value as an attack and BATADAL uses ``-999`` to mean
       *unlabelled* across 95% of its test rows.
    4. Drops leaking and non-numeric columns, because HAI ships ``attack_P1..P3`` — numeric
       copies of the answer that the adapter's auto-detection would otherwise feed in as signals.

    Returns:
        The prepared CSV path and the value columns written to it.

    Raises:
        FetchError: If the source file is missing, a configured column is absent, or no numeric
            value columns survive.
    """
    source = dataset_dir / step.source_file
    if not source.is_file():
        raise FetchError(f"cannot prepare {step.output_file}: {source} is missing")

    frame = pandas.read_csv(source)
    if step.strip_column_names:
        frame.columns = pandas.Index([str(column).strip() for column in frame.columns])

    present = [str(column) for column in frame.columns]
    for required in (step.timestamp_column, step.label_column):
        if required not in present:
            raise FetchError(
                f"{source.name}: column {required!r} not found; the file has: {', '.join(present)}"
            )

    timestamps = pandas.to_datetime(
        frame[step.timestamp_column], format=step.timestamp_format, utc=True
    )

    raw_labels = frame[step.label_column].astype(str).str.strip()
    labels = raw_labels.isin(step.attack_values).astype(int)

    excluded = {step.timestamp_column, step.label_column, *step.drop_columns}
    candidates = [column for column in present if column not in excluded]
    numeric = frame[candidates].apply(pandas.to_numeric, errors="coerce")
    value_columns = [column for column in candidates if not bool(numeric[column].isna().all())]
    if not value_columns:
        raise FetchError(f"{source.name}: no numeric value columns survived preparation")
    dropped = sorted(set(candidates) - set(value_columns))
    if dropped:
        logger.info("  dropped non-numeric columns: %s", ", ".join(dropped))

    prepared = pandas.DataFrame({"timestamp": timestamps.dt.strftime("%Y-%m-%dT%H:%M:%S%z")})
    prepared["label"] = labels
    for column in value_columns:
        prepared[column] = numeric[column]
    prepared = prepared.sort_values("timestamp", kind="stable")

    if step.row_stride > 1:
        before = int(prepared["label"].sum())
        windows_before = _count_label_runs(prepared["label"].tolist())
        prepared = prepared.iloc[:: step.row_stride]
        windows_after = _count_label_runs(prepared["label"].tolist())
        if windows_after < windows_before:
            raise FetchError(
                f"{source.name}: row_stride={step.row_stride} destroyed "
                f"{windows_before - windows_after} of {windows_before} attack windows; "
                "ground truth would be silently lost"
            )
        logger.info(
            "  strided  every %dth row: %d attack rows -> %d, %d attack windows preserved",
            step.row_stride,
            before,
            int(prepared["label"].sum()),
            windows_after,
        )

    output = dataset_dir / step.output_file
    prepared.to_csv(output, index=False)
    logger.info(
        "  prepared %-34s %6d rows x %3d signals, %d attack rows",
        step.output_file,
        len(prepared),
        len(value_columns),
        int(prepared["label"].sum()),
    )
    return output, value_columns


def _count_label_runs(labels: Sequence[object]) -> int:
    """Return the number of maximal runs of ``1`` in ``labels``.

    Used to prove that thinning a corpus with ``row_stride`` did not erase an attack window
    outright, which would remove ground truth without removing the attack.
    """
    runs = 0
    previous = 0
    for value in labels:
        current = int(value)  # type: ignore[call-overload]
        if current == 1 and previous != 1:
            runs += 1
        previous = current
    return runs


def build_manifest(
    entry: DatasetEntry,
    dataset_dir: Path,
    *,
    join_result: PrepareResult | None = None,
    grid_result: Data4CyberPrepareResult | None = None,
) -> Path | None:
    """Write ``data/<name>/manifest.json`` describing the prepared corpora.

    The top level is exactly the :class:`phos.eval.LabelledCsvAdapter` field set for the corpus
    that gets *scored*, so it validates directly with no translation layer. Provenance and the
    training corpus hang off extra keys, which the adapter ignores.

    Returns:
        The manifest path, or ``None`` when the corpus has no preparation steps.
    """
    if grid_result is not None and entry.grid_prepare is not None:
        return _write_grid_manifest(entry, dataset_dir, grid_result)
    if join_result is not None and entry.join is not None:
        return _write_join_manifest(entry, dataset_dir, join_result)
    if not entry.prepare:
        return None

    def adapter_config(role: str, step: PrepareStep) -> dict[str, object]:
        note = f"{entry.title} [{role}] — prepared from {step.source_file}"
        if step.row_stride > 1:
            note += f", downsampled to every {step.row_stride}th row"
        if step.drop_columns:
            note += f", dropped {', '.join(step.drop_columns)}"
        return {
            "name": f"{entry.name}-{role}",
            "path": f"{entry.name}/{step.output_file}",
            "timestamp_column": "timestamp",
            "label_column": "label",
            "value_columns": None,
            "source_note": note,
            "domain": entry.domain,
        }

    steps = entry.prepare
    scored_role = "test" if "test" in steps else next(iter(steps))
    manifest: dict[str, object] = dict(adapter_config(scored_role, steps[scored_role]))
    if "train" in steps and scored_role != "train":
        manifest["train"] = adapter_config("train", steps["train"])
    manifest["provenance"] = {
        "dataset": entry.name,
        "title": entry.title,
        "homepage": entry.homepage,
        "license": entry.license.model_dump(),
        "citation": entry.citation,
        "files": [
            {
                "filename": file.filename,
                "url": file.url,
                "size_bytes": (dataset_dir / file.filename).stat().st_size
                if (dataset_dir / file.filename).is_file()
                else file.size_bytes,
                "sha256": sha256_of(dataset_dir / file.filename)
                if (dataset_dir / file.filename).is_file()
                else None,
            }
            for file in entry.files
        ],
        "note": "Generated by scripts/fetch_datasets.py. The data this describes is git-ignored.",
    }

    path = dataset_dir / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    logger.info("  manifest %s", path.relative_to(REPO_ROOT))
    return path


def _write_join_manifest(
    entry: DatasetEntry,
    dataset_dir: Path,
    result: PrepareResult,
) -> Path:
    """Write a labelled-CSV manifest for a joined multi-experiment corpus.

    Every adapter block declares ``unscored_label_values``: without it the adapter would read the
    ``-1`` sentinel for blind and recovery phases as an attack (ADR 0082).
    """
    spec = entry.join
    if spec is None:
        raise FetchError(f"{entry.name}: join result produced without a join spec")

    def adapter_config(role: str, output_file: str) -> dict[str, object]:
        return {
            "name": f"{entry.name}-{role}",
            "path": f"{entry.name}/{output_file}",
            "timestamp_column": "timestamp",
            "label_column": "label",
            "unscored_label_values": [str(UNSCORED_LABEL)],
            "value_columns": None,
            "source_note": f"{result.source_note} [{role}]",
            "domain": entry.domain,
        }

    manifest: dict[str, object] = dict(adapter_config("test", spec.test_output_file))
    manifest["train"] = adapter_config("train", spec.train_output_file)
    manifest["contaminated_train"] = adapter_config(
        "contaminated-train", spec.contaminated_output_file
    )
    manifest["join"] = spec.model_dump()
    manifest["counts"] = {
        "n_clean_train": result.n_clean_train,
        "n_contaminated_train": result.n_contaminated_train,
        "n_test": result.n_test,
        "n_train_rows": result.n_train_rows,
        "n_test_rows": result.n_test_rows,
        "n_test_windows": result.n_test_windows,
        "n_test_positive_rows": result.n_test_positive_rows,
        "n_test_unscored_windows": result.n_test_unscored_windows,
        "n_test_unscored_rows": result.n_test_unscored_rows,
        "n_signals": len(result.signal_columns),
        "n_train_recipe_step_rows": result.n_train_recipe_step_rows,
        "n_test_recipe_step_rows": result.n_test_recipe_step_rows,
    }
    if result.recipe_step_names:
        manifest["phase_feature"] = RECIPE_STEP_FEATURE
        manifest["recipe_step_names"] = list(result.recipe_step_names)
    if entry.caveats:
        manifest["caveats"] = list(entry.caveats)
    manifest["provenance"] = {
        "dataset": entry.name,
        "title": entry.title,
        "homepage": entry.homepage,
        "license": entry.license.model_dump(),
        "citation": entry.citation,
        "files": [
            {
                "filename": file.filename,
                "url": file.url,
                "size_bytes": locate_file(file, dataset_dir).stat().st_size
                if locate_file(file, dataset_dir).is_file()
                else file.size_bytes,
                "md5": file.md5,
                "sha256": file.sha256,
            }
            for file in entry.files
        ],
        "note": "Generated by scripts/fetch_datasets.py. The data this describes is git-ignored.",
    }
    path = dataset_dir / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    logger.info("  manifest %s", path.relative_to(REPO_ROOT))
    return path


def _write_grid_manifest(
    entry: DatasetEntry,
    dataset_dir: Path,
    result: Data4CyberPrepareResult,
) -> Path:
    """Write a labelled-CSV manifest for Data4Cyber Track A (not a command corpus)."""
    spec = entry.grid_prepare
    if spec is None:
        raise FetchError(f"{entry.name}: grid result produced without a grid_prepare spec")

    def adapter_config(role: str, output_file: str) -> dict[str, object]:
        return {
            "name": f"{entry.name}-{role}",
            "path": f"{entry.name}/{output_file}",
            "timestamp_column": "timestamp",
            "label_column": "label",
            "value_columns": None,
            "source_note": f"{result.source_note} [{role}]",
            "domain": entry.domain,
        }

    manifest: dict[str, object] = dict(adapter_config("test", spec.test_output_file))
    manifest["train"] = adapter_config("train", spec.train_output_file)
    manifest["format"] = "csv"
    manifest["grid_prepare"] = spec.model_dump()
    manifest["counts"] = {
        "n_train_rows": result.n_train_rows,
        "n_test_rows": result.n_test_rows,
        "n_test_attack_rows": result.n_test_attack_rows,
        "n_reconnaissance_rows": result.n_reconnaissance_rows,
        "n_test_windows": result.n_test_windows,
        "n_signals": result.n_signals,
    }
    if entry.caveats:
        manifest["caveats"] = list(entry.caveats)
    manifest["provenance"] = {
        "dataset": entry.name,
        "title": entry.title,
        "homepage": entry.homepage,
        "license": entry.license.model_dump(),
        "citation": entry.citation,
        "files": [
            {
                "filename": file.filename,
                "url": file.url,
                "size_bytes": locate_file(file, dataset_dir).stat().st_size
                if locate_file(file, dataset_dir).is_file()
                else file.size_bytes,
                "md5": file.md5,
                "sha256": file.sha256,
            }
            for file in entry.files
        ],
        "note": (
            "Generated by scripts/fetch_datasets.py. Track A process telemetry. "
            "The data this describes is git-ignored. format=csv, never pcap."
        ),
    }
    path = dataset_dir / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    logger.info("  manifest %s", path.relative_to(REPO_ROOT))
    return path


SENTIEL_MANIFEST_NAME: Final = "sentiel-manifest.json"

"""Filename of the manifest for a multi-file event corpus.

Deliberately **not** ``manifest.json``. That name is claimed by the labelled-CSV manifests, which
``tests/eval/test_real_dataset.py`` discovers by globbing ``data/*/manifest.json`` and validates
against :class:`phos.eval.LabelledCsvAdapter`'s field set. A CERT release is not a labelled CSV and
has no ``path`` to give that adapter, so writing one under the shared name would break a PART 2 test
from the outside. A distinct name keeps PART 2 untouched, which is what PART 6-D requires.
"""


def build_release_manifest(entry: DatasetEntry, dataset_dir: Path) -> Path | None:
    """Write ``data/<name>/sentiel-manifest.json`` for a multi-file event corpus.

    This is the committed record of what was downloaded: the exact release, its size and verified
    checksum, both licences, the attribution string, and the caveats that must travel with every
    number the corpus produces. The payload it describes is git-ignored; this file is not.

    Returns:
        The manifest path, or ``None`` when the entry names no release.
    """
    if entry.release is None:
        return None

    extracted = [file for file in entry.files if file.extract]
    manifest: dict[str, object] = {
        "name": f"{entry.name}-{entry.release}",
        "domain": entry.domain,
        "release": entry.release,
        "release_dir": next(
            (
                f"{entry.name}/{file.extract_to}"
                for file in extracted
                if file.role == "events" and file.extract_to
            ),
            None,
        ),
        "answers_dir": next(
            (
                f"{entry.name}/{file.extract_to}"
                for file in extracted
                if file.role == "labels" and file.extract_to
            ),
            None,
        ),
        "attribution": entry.citation,
        "caveats": list(entry.caveats),
        "provenance": {
            "dataset": entry.name,
            "title": entry.title,
            "homepage": entry.homepage,
            "license": entry.license.model_dump(),
            "payload_license": (
                entry.payload_license.model_dump() if entry.payload_license else None
            ),
            "citation": entry.citation,
            "files": [
                {
                    "filename": file.filename,
                    "url": file.url,
                    "role": file.role,
                    "size_bytes": (dataset_dir / file.filename).stat().st_size
                    if (dataset_dir / file.filename).is_file()
                    else file.size_bytes,
                    "sha256": file.sha256,
                    "sha256_verified": file.sha256 is not None
                    and (dataset_dir / file.filename).is_file(),
                }
                for file in entry.files
            ],
            "note": (
                "Generated by scripts/fetch_datasets.py. The release this describes is "
                "git-ignored and is never committed."
            ),
        },
    }
    path = dataset_dir / SENTIEL_MANIFEST_NAME
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    logger.info("  manifest %s", path.relative_to(REPO_ROOT))
    return path


def acquire(entry: DatasetEntry, *, force: bool = False) -> None:
    """Download, prepare and describe one corpus.

    Raises:
        FetchError: If the corpus is not cleared for download.
    """
    if not entry.fetchable:
        raise FetchError(
            f"{entry.name} is not fetchable (status={entry.status!r}). {entry.status_note}"
        )
    logger.info("%s — %s", entry.name, entry.title)
    logger.info("  licence  %s (%s)", entry.license.name, entry.license.status)
    dataset_dir = DATA_DIR / entry.name
    dataset_dir.mkdir(parents=True, exist_ok=True)
    if entry.payload_license is not None:
        logger.warning(
            "  NOTE     the payload ships its own terms (%s), which differ from the catalogue "
            "record above; both are recorded in the manifest",
            entry.payload_license.name,
        )
    for remote in entry.files:
        stored = fetch_file(remote, dataset_dir, force=force)
        extract_archive(remote, dataset_dir, archive=stored)
    join_result: PrepareResult | None = None
    grid_result: Data4CyberPrepareResult | None = None
    if entry.grid_prepare is not None:
        import phos.eval.data4cyber as data4cyber_prep

        try:
            grid_result = data4cyber_prep.prepare_corpus(dataset_dir, entry.grid_prepare)
        except data4cyber_prep.PrepareError as error:
            raise FetchError(str(error)) from error
    elif entry.join is not None:
        try:
            join_result = prepare_corpus(dataset_dir, entry.join)
        except PrepareError as error:
            raise FetchError(str(error)) from error
    elif entry.prepare:
        for step in entry.prepare.values():
            prepare_csv(step, dataset_dir)
    build_manifest(entry, dataset_dir, join_result=join_result, grid_result=grid_result)

    build_release_manifest(entry, dataset_dir)


def confirm_size(entries: Sequence[DatasetEntry], threshold: int, *, assume_yes: bool) -> bool:
    """Print the download size and, above ``threshold``, require explicit consent.

    Returns:
        Whether to proceed.
    """
    total = sum(entry.total_bytes() for entry in entries)
    logger.info("Planned download: %s across %d dataset(s)", human_bytes(total), len(entries))
    for entry in entries:
        logger.info("  %-24s %12s  %s", entry.name, human_bytes(entry.total_bytes()), entry.status)
    if total <= threshold or assume_yes:
        return True
    if not sys.stdin.isatty():
        logger.error(
            "Refusing to download %s unattended (threshold %s). Re-run with --yes to consent.",
            human_bytes(total),
            human_bytes(threshold),
        )
        return False
    answer = input(f"This exceeds {human_bytes(threshold)}. Proceed? [y/N] ").strip().lower()
    return answer in {"y", "yes"}


def describe(registry: Registry) -> None:
    """Print every registered corpus with its licence and acquisition state."""
    for entry in registry.datasets:
        marker = "fetch" if entry.fetchable else "skip "
        logger.info(
            "[%s] %-24s %-8s %-18s %s",
            marker,
            entry.name,
            entry.domain,
            entry.license.spdx or entry.license.status,
            human_bytes(entry.total_bytes()) if entry.files else "-",
        )
        if not entry.fetchable:
            logger.info("         %s", entry.status_note.split(".")[0] + ".")


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns a process exit code."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("names", nargs="*", help="dataset names to fetch")
    parser.add_argument("--all", action="store_true", help="fetch every fetchable dataset")
    parser.add_argument("--list", action="store_true", help="show the registry and exit")
    parser.add_argument("--force", action="store_true", help="re-download even if present")
    parser.add_argument("--yes", action="store_true", help="consent to large downloads")
    arguments = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    try:
        registry = load_registry()
        if arguments.list or (not arguments.names and not arguments.all):
            describe(registry)
            return 0
        selected = (
            [entry for entry in registry.datasets if entry.fetchable]
            if arguments.all
            else [registry.by_name(name) for name in arguments.names]
        )
        blocked = [entry for entry in selected if not entry.fetchable]
        if blocked:
            for entry in blocked:
                logger.error("%s: %s", entry.name, entry.status_note)
            return 2
        if not confirm_size(
            selected, registry.size_confirm_threshold_bytes, assume_yes=arguments.yes
        ):
            logger.info("Aborted; nothing downloaded.")
            return 1
        for entry in selected:
            acquire(entry, force=arguments.force)
    except FetchError as error:
        logger.error("%s", error)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Score a `GaussianBaseline` against every integrated real corpus and log the results.

This is the script that turns a downloaded dataset into a number on the record. It exists so the
numbers in `PROGRESS.md` can be re-created rather than trusted (Constitution §3.7): every run it
performs is appended to ``eval_runs/log.jsonl`` stamped with the git commit and seed.

Two protocols are run per corpus, because they answer different questions:

* **designed** — fit on the corpus's own attack-free training file, score on its labelled test
  file. This is how the corpus authors intend it to be used and is the honest headline number.
* **prefix** — ignore the training file, and use `phos.reasoning.prefix_split` (which delegates
  to `phos.models.train_test_split` and also stops at unscored time) to carve an attack-free
  prefix out of the labelled file alone. This is the protocol PART 3 used on
  synthetic data, so it keeps the new numbers comparable with the old ones.

Neither protocol lets a model score data it was fitted on.

Usage::

    python scripts/evaluate_corpora.py
    python scripts/evaluate_corpora.py batadal
    python scripts/evaluate_corpora.py --no-log     # print the table, write nothing
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final

REPO_ROOT: Final = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from phos.eval import (  # noqa: E402
    EvalConfig,
    EvaluationReport,
    LabelledCsvAdapter,
    append_to_experiment_log,
    evaluate,
)
from phos.models import (  # noqa: E402
    GaussianBaseline,
    ModelDetector,
    SplitPolicy,
)
from phos.reasoning import prefix_split  # noqa: E402

DATA_DIR: Final = REPO_ROOT / "data"

#: Matches the threshold PART 3 used for `model:gaussian` on synthetic data, so the real numbers
#: land in the same column as the synthetic ones rather than in a new one.
ALERT_THRESHOLD: Final = 3.0
SEED: Final = 11

logger = logging.getLogger("phos.evaluate")


def _adapter(config: dict[str, Any]) -> LabelledCsvAdapter:
    """Build an adapter from a manifest block, resolving its path against ``data/``."""
    fields = {
        key: value
        for key, value in config.items()
        if key in LabelledCsvAdapter.model_fields and key != "path"
    }
    return LabelledCsvAdapter.model_validate({**fields, "path": str(DATA_DIR / config["path"])})


def discover(names: Sequence[str]) -> list[tuple[str, dict[str, Any]]]:
    """Return ``(dataset_name, manifest)`` for every integrated corpus present on disk.

    A manifest whose CSV is absent is skipped rather than failing, because manifests are
    committed and the data they describe is not — a fresh clone legitimately has one without the
    other.
    """
    found: list[tuple[str, dict[str, Any]]] = []
    for manifest_path in sorted(DATA_DIR.glob("*/manifest.json")):
        name = manifest_path.parent.name
        if names and name not in names:
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not (DATA_DIR / manifest["path"]).is_file():
            logger.warning("%s: manifest present but %s is not", name, manifest["path"])
            continue
        found.append((name, manifest))
    return found


def run_designed(name: str, manifest: dict[str, Any]) -> EvaluationReport | None:
    """Fit on the corpus's own attack-free training file and score its labelled test file."""
    if "train" not in manifest:
        logger.info("%s: no training corpus in the manifest, skipping designed split", name)
        return None
    train_config = manifest["train"]
    if not (DATA_DIR / train_config["path"]).is_file():
        logger.warning("%s: training file %s absent", name, train_config["path"])
        return None

    train = _adapter(train_config).load()
    test = _adapter(manifest).load()
    if train.attack_intervals:
        raise RuntimeError(
            f"{name}: the training corpus carries {len(train.attack_intervals)} attack "
            "interval(s); it must be attack-free or the model learns the attack as normal"
        )
    if train.unscored_intervals:
        raise RuntimeError(
            f"{name}: the training corpus carries {len(train.unscored_intervals)} unscored "
            "interval(s); unscored time is not verified normal and must not be fitted on"
        )
    logger.info(
        "%s designed: fit on %d obs (%s), score %d obs (%s), %d attack windows",
        name,
        len(train.observations),
        train.name,
        len(test.observations),
        test.name,
        len(test.attack_intervals),
    )
    fitted = GaussianBaseline().fit(train.observations)
    report = evaluate(
        ModelDetector(fitted=fitted),
        test,
        EvalConfig(alert_threshold=ALERT_THRESHOLD, seed=SEED),
    )
    return report.model_copy(update={"dataset_name": f"{test.name}[designed]"})


def run_prefix(name: str, manifest: dict[str, Any]) -> EvaluationReport | None:
    """Carve an attack-free prefix out of the labelled corpus and score the remainder."""
    corpus = _adapter(manifest).load()
    train, test = prefix_split(corpus, SplitPolicy(train_fraction=0.5, seed=SEED))
    if not train.observations or not test.attack_intervals:
        logger.warning("%s: prefix split left nothing usable, skipping", name)
        return None
    logger.info(
        "%s prefix:   fit on %d obs, score %d obs, %d attack windows",
        name,
        len(train.observations),
        len(test.observations),
        len(test.attack_intervals),
    )
    fitted = GaussianBaseline().fit(train.observations)
    report = evaluate(
        ModelDetector(fitted=fitted),
        test,
        EvalConfig(alert_threshold=ALERT_THRESHOLD, seed=SEED),
    )
    return report.model_copy(update={"dataset_name": f"{corpus.name}[prefix]"})


def render(reports: Sequence[EvaluationReport]) -> str:
    """Render the reports as a markdown table, in the shape PROGRESS.md uses."""
    header = (
        "| Corpus | Protocol | Recall | FPs | FP/normal-hr | Precision | Latency | ECE | Brier |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"
    )
    rows = []
    for report in reports:
        corpus, _, protocol = report.dataset_name.partition("[")
        latency = f"{report.latency.median_seconds:.0f} s" if report.latency.count else "n/a"
        rows.append(
            f"| `{corpus}` | {protocol.rstrip(']')} | {report.window_recall:.2f} "
            f"| {report.false_positives} | {report.false_positive_rate:.2f} "
            f"| {report.precision:.3f} | {latency} "
            f"| {report.expected_calibration_error:.3f} | {report.brier_score:.3f} |"
        )
    return "\n".join([header, *rows])


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns a process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("names", nargs="*", help="dataset names; default is every one found")
    parser.add_argument("--no-log", action="store_true", help="do not append to the experiment log")
    parser.add_argument(
        "--protocol",
        choices=("designed", "prefix", "all"),
        default="all",
        help="which split protocol(s) to run; default is both",
    )
    arguments = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    corpora = discover(arguments.names)
    if not corpora:
        logger.error("no integrated corpus found; run scripts/fetch_datasets.py --all first")
        return 2

    protocols = {
        "designed": (run_designed,),
        "prefix": (run_prefix,),
        "all": (run_designed, run_prefix),
    }[arguments.protocol]

    reports: list[EvaluationReport] = []
    for name, manifest in corpora:
        for protocol in protocols:
            report = protocol(name, manifest)
            if report is None:
                continue
            reports.append(report)
            if not arguments.no_log:
                append_to_experiment_log(report)

    print("\n" + render(reports))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Measure what calibration is worth on every integrated real corpus, and log the answer.

This is the reproducible proof behind PART 4A's headline claim. For each corpus it performs the
three-way split, fits a `GaussianBaseline` on the training slice, fits **both** calibrators on the
calibration slice, and then scores the test slice three times — once with the uncalibrated
`ModelDetector` PART 3 shipped, and once with each `CalibratedModelDetector`. Every report is
appended to ``eval_runs/log.jsonl`` stamped with the git commit and seed (Constitution §3.7).

The alert threshold and seed match ``scripts/evaluate_corpora.py`` so the numbers land in the same
column as PART 3's rather than in a new one.

Two things this script is careful not to hide:

* **Both calibrators are reported, including when one loses.** Platt makes BATADAL's calibration
  error *worse* than doing nothing. Reporting only the winner would turn a measurement into an
  advertisement.
* **The Brier score is printed beside the calibration error.** A calibrator can be perfectly
  calibrated and useless — answering the base rate to everything is honest and uninformative — and
  the Brier score is what shows the difference. On HAI that is not a hypothetical.

A corpus whose attacks do not reach every slice raises `DegenerateSplitError`; that is reported and
skipped rather than worked around, because the alternative is a number that means nothing. HAI needs
its own fractions for exactly this reason — see `SPLIT_POLICIES`.

Usage::

    python scripts/calibrate_corpora.py
    python scripts/calibrate_corpora.py batadal
    python scripts/calibrate_corpora.py --no-log                        # print, write nothing
    python scripts/calibrate_corpora.py hai --train-fraction 0.04 --calib-fraction 0.3
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
    Dataset,
    EvalConfig,
    EvaluationReport,
    LabelledCsvAdapter,
    append_to_experiment_log,
    evaluate,
)
from phos.models import GaussianBaseline, ModelDetector  # noqa: E402
from phos.reasoning import (  # noqa: E402
    CalibratedModelDetector,
    CalibrationSplitPolicy,
    DegenerateSplitError,
    IsotonicCalibrator,
    PlattCalibrator,
    scores_and_labels_from,
    train_calib_test_split,
)

DATA_DIR: Final = REPO_ROOT / "data"

#: Matches `scripts/evaluate_corpora.py` so calibrated and uncalibrated runs are comparable.
ALERT_THRESHOLD: Final = 3.0
SEED: Final = 11

DEFAULT_POLICY: Final = CalibrationSplitPolicy(train_fraction=0.4, calib_fraction=0.3)

#: Per-corpus overrides where the default fractions cannot yield three viable slices.
#:
#: HAI's attacks all fall in the first half of its test file — the last one ends at 51% of the
#: timeline — so a 0.4/0.3 split leaves a test slice with no attacks in it at all, and a calibrator
#: that answered 0.0 to everything would post a perfect calibration error on it. Training is
#: capped at 4% because HAI's *first* attack arrives at 4.9%, and the attack-free prefix stops
#: there regardless of what is asked for.
SPLIT_POLICIES: Final[dict[str, CalibrationSplitPolicy]] = {
    "hai": CalibrationSplitPolicy(train_fraction=0.04, calib_fraction=0.30),
}

logger = logging.getLogger("phos.calibrate")


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

    A manifest whose CSV is absent is skipped rather than failing: manifests are committed and the
    data they describe is not, so a fresh clone legitimately has one without the other.
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


def calibrate(name: str, corpus: Dataset, policy: CalibrationSplitPolicy) -> list[EvaluationReport]:
    """Split, fit, and score one corpus three ways.

    Args:
        name: The corpus's directory name, used only for logging.
        corpus: The labelled corpus.
        policy: The split fractions to use for it.

    Returns:
        The uncalibrated report first, then one per calibrator that could be fitted. Empty if the
        corpus cannot yield three viable slices.
    """
    try:
        train, calib, test = train_calib_test_split(corpus, policy)
    except DegenerateSplitError as error:
        logger.warning("%s: %s", name, error)
        return []

    logger.info(
        "%s: train=%d obs, calib=%d obs (%d windows), test=%d obs (%d windows)",
        name,
        len(train.observations),
        len(calib.observations),
        len(calib.attack_intervals),
        len(test.observations),
        len(test.attack_intervals),
    )

    fitted = GaussianBaseline().fit(train.observations)
    config = EvalConfig(alert_threshold=ALERT_THRESHOLD, seed=SEED)
    reports = [evaluate(ModelDetector(fitted=fitted), test, config)]

    scores, labels = scores_and_labels_from(fitted, calib)
    for calibrator in (IsotonicCalibrator(seed=SEED), PlattCalibrator(seed=SEED)):
        try:
            fitted_calibrator = calibrator.fit(scores, labels)
        except ValueError as error:
            logger.warning("%s: could not fit a calibrator on the calib slice: %s", name, error)
            continue
        detector = CalibratedModelDetector(fitted=fitted, calibrator=fitted_calibrator)
        reports.append(evaluate(detector, test, config))

    return reports


def render(reports: Sequence[EvaluationReport]) -> str:
    """Render a before/after table, grouped by corpus, in the shape PROGRESS.md uses."""
    header = (
        "| Corpus | Detector | ECE | Brier | Recall | FP/normal-hr | Alerts |\n"
        "| --- | --- | --- | --- | --- | --- | --- |"
    )
    rows = []
    for report in reports:
        rows.append(
            f"| `{report.dataset_name}` | `{report.detector_name}` "
            f"| {report.expected_calibration_error:.4f} | {report.brier_score:.4f} "
            f"| {report.window_recall:.2f} | {report.false_positive_rate:.2f} "
            f"| {report.n_alerts} |"
        )
    return "\n".join([header, *rows])


def summarise(reports: Sequence[EvaluationReport]) -> str:
    """State the headline verdict per corpus: did calibration beat doing nothing?"""
    by_corpus: dict[str, list[EvaluationReport]] = {}
    for report in reports:
        by_corpus.setdefault(report.dataset_name, []).append(report)

    lines: list[str] = []
    for corpus, group in by_corpus.items():
        baseline = next((r for r in group if "+" not in r.detector_name), None)
        if baseline is None:
            continue
        base_ece = baseline.expected_calibration_error
        for report in group:
            if report is baseline:
                continue
            calibrator = report.detector_name.rsplit("+", 1)[-1]
            delta = base_ece - report.expected_calibration_error
            verdict = "BEATS" if delta > 0 else "LOSES TO"
            lines.append(
                f"{corpus}: {calibrator} {verdict} uncalibrated — "
                f"ECE {base_ece:.4f} -> {report.expected_calibration_error:.4f} "
                f"({delta:+.4f})"
            )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns a process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("names", nargs="*", help="dataset names; default is every one found")
    parser.add_argument("--no-log", action="store_true", help="do not append to the experiment log")
    parser.add_argument(
        "--train-fraction", type=float, default=None, help="override the training fraction"
    )
    parser.add_argument(
        "--calib-fraction", type=float, default=None, help="override the calibration fraction"
    )
    arguments = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    corpora = discover(arguments.names)
    if not corpora:
        logger.error("no integrated corpus found; run scripts/fetch_datasets.py --all first")
        return 2

    override: CalibrationSplitPolicy | None = None
    if arguments.train_fraction is not None or arguments.calib_fraction is not None:
        base = DEFAULT_POLICY
        override = CalibrationSplitPolicy(
            train_fraction=arguments.train_fraction or base.train_fraction,
            calib_fraction=arguments.calib_fraction or base.calib_fraction,
        )

    reports: list[EvaluationReport] = []
    for name, manifest in corpora:
        policy = override or SPLIT_POLICIES.get(name, DEFAULT_POLICY)
        corpus = _adapter(manifest).load()
        for report in calibrate(name, corpus, policy):
            reports.append(report)
            if not arguments.no_log:
                append_to_experiment_log(report)

    if not reports:
        logger.error("no corpus yielded a usable three-way split")
        return 1

    print("\n" + render(reports))
    print("\n" + summarise(reports))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

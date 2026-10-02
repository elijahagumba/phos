#!/usr/bin/env python3
"""Measure ADR 0083's normal-score calibrator on HAI and batch-distillation.

Fits the behavioural model on the corpus's attack-free training file (holding out a normal
calibration suffix), fits `NormalScoreCalibrator` on that suffix alone, and scores the labelled
test under a **new** experiment name. Frozen isotonic / three-way rows are gates only — never
overwritten.

HAI uses the same three-way **test slice** the frozen vertical uses, so alert counts are comparable
to the ADR 0075 diagnostic (0.48 h → 5,123; 60 h → 97). Batch-distillation uses designed protocol
under ADR 0082 scoring beside the sandbox ``noboom-atlas-v1`` baseline.

Default is ``--no-log``. Append to ``eval_runs/log.jsonl`` only with ``--log`` when authorised.

Usage::

    uv run python scripts/evaluate_normal_score_calibrator.py
    uv run python scripts/evaluate_normal_score_calibrator.py --no-write
    uv run python scripts/evaluate_normal_score_calibrator.py --log   # authorised append only
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from pydantic import BaseModel, ConfigDict

REPO_ROOT: Final = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Reuse the vertical script's measurement helpers without re-deriving them.
from scripts.evaluate_atlas_vertical import (  # noqa: E402
    PrecomputedDetector,
    detections_from,
    magnitudes_of,
    split_evidence,
    windows_covered,
)

from phos.atlas import (  # noqa: E402
    ATLAS_VERTICAL_CAVEATS,
    AtlasEngine,
    MahalanobisModel,
    annotate_with_caveats,
    load_topology,
)
from phos.eval import (  # noqa: E402
    EvalConfig,
    EvaluationReport,
    LabelledCsvAdapter,
    append_to_experiment_log,
    evaluate,
)
from phos.models import ModelDetector  # noqa: E402
from phos.reasoning import (  # noqa: E402
    NORMAL_SCORE_WEIGHT_CAVEAT,
    CalibratedModelDetector,
    CalibrationSplitPolicy,
    NormalScoreCalibrator,
    attack_free_fit_calib_split,
    normal_scores_from,
    train_calib_test_split,
)

DATA_DIR: Final = REPO_ROOT / "data"
OUT_DIR: Final = REPO_ROOT / "eval_runs" / "sandbox" / "adr0083-normal-score"
ALERT_THRESHOLD: Final = 3.0
SEED: Final = 11
CALIB_FRACTION: Final = 0.1
HAI_THREE_WAY: Final = CalibrationSplitPolicy(train_fraction=0.04, calib_fraction=0.30)
GATE_TOLERANCE: Final = 1e-4
FROZEN_HAI_UNGATED: Final = 646.5797816132441
FROZEN_HAI_GROUPED: Final = 53.25818950334625
FROZEN_HAI_EVENTS: Final = 424
FROZEN_HAI_RECALL: Final = 1.0
# Quoted stamps (README / ADR tables); used only in prose, not for the gate.
QUOTED_HAI_UNGATED: Final = 646.58
QUOTED_HAI_GROUPED: Final = 53.26
NOBOOM_V1_RECALL: Final = 0.532
NOBOOM_V1_FP_RATE: Final = 18.61
NOBOOM_V1_PRECISION: Final = 0.709

logger = logging.getLogger("phos.adr0083")


class GateError(RuntimeError):
    """Frozen HAI rows drifted; abort before publishing a new number."""


def _adapter(config: Mapping[str, Any]) -> LabelledCsvAdapter:
    fields = {
        key: value
        for key, value in config.items()
        if key in LabelledCsvAdapter.model_fields and key != "path"
    }
    return LabelledCsvAdapter.model_validate({**fields, "path": str(DATA_DIR / config["path"])})


def _load_manifest(name: str) -> dict[str, Any]:
    path = DATA_DIR / name / "manifest.json"
    loaded: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise TypeError(f"{path} must be a JSON object, got {type(loaded).__name__}")
    return {str(key): value for key, value in loaded.items()}


def _named(report: EvaluationReport, label: str) -> EvaluationReport:
    return report.model_copy(update={"dataset_name": label})


def _with_caveats(report: EvaluationReport) -> EvaluationReport:
    annotated = annotate_with_caveats(report)
    if NORMAL_SCORE_WEIGHT_CAVEAT in annotated.source_note:
        return annotated
    note = " | ".join(part for part in (annotated.source_note, NORMAL_SCORE_WEIGHT_CAVEAT) if part)
    return annotated.model_copy(update={"source_note": note})


def gate_hai_frozen() -> tuple[EvaluationReport, EvaluationReport]:
    """Reproduce the frozen isotonic vertical before any new number is produced."""
    from scripts.evaluate_atlas_vertical import run_corpus

    manifest = _load_manifest("hai")
    result = run_corpus("hai", manifest)
    if result is None:
        raise GateError("hai three-way vertical returned nothing; cannot gate")
    before, after = result.reports[1], result.reports[2]
    drifts: list[str] = []
    if abs(before.false_positive_rate - FROZEN_HAI_UNGATED) > GATE_TOLERANCE:
        drifts.append(
            f"ungated FP/hr {before.false_positive_rate} drifted from {FROZEN_HAI_UNGATED}"
        )
    if abs(after.false_positive_rate - FROZEN_HAI_GROUPED) > GATE_TOLERANCE:
        drifts.append(
            f"grouped FP/hr {after.false_positive_rate} drifted from {FROZEN_HAI_GROUPED}"
        )
    if result.n_events != FROZEN_HAI_EVENTS:
        drifts.append(f"subsystem events {result.n_events} drifted from {FROZEN_HAI_EVENTS}")
    if abs(after.window_recall - FROZEN_HAI_RECALL) > GATE_TOLERANCE:
        drifts.append(f"grouped recall {after.window_recall} drifted from {FROZEN_HAI_RECALL}")
    if drifts:
        raise GateError("; ".join(drifts))
    logger.info(
        "gate passed: hai isotonic vertical ungated=%.2f grouped=%.2f events=%d recall=%.2f",
        before.false_positive_rate,
        after.false_positive_rate,
        result.n_events,
        after.window_recall,
    )
    return before, after


def run_hai_normal_score() -> list[EvaluationReport]:
    """Fit on declared-normal history; calibrate without labelled positives; score vertical test."""
    manifest = _load_manifest("hai")
    if "train" not in manifest:
        raise RuntimeError("hai manifest has no attack-free train block")
    declared = _adapter(manifest["train"]).load()
    fit, calib = attack_free_fit_calib_split(declared, calib_fraction=CALIB_FRACTION)
    fitted = MahalanobisModel().fit(fit.observations)
    calibrator = NormalScoreCalibrator(seed=SEED).fit(normal_scores_from(fitted, calib))

    labelled = _adapter(manifest).load()
    _, _, test = train_calib_test_split(labelled, HAI_THREE_WAY)

    topology = load_topology(
        DATA_DIR / "hai" / "topology.toml",
        {observation.feature for observation in labelled.observations},
        corpus="hai",
    )
    engine = AtlasEngine(fitted=fitted, calibrator=calibrator, subsystem_map=topology)
    narratives = engine.run(test)
    logger.info("hai normal-score vertical: %d narrative(s)", len(narratives))

    per_signal, events = split_evidence(engine)
    magnitude, signals = magnitudes_of(engine, per_signal, events)
    members = {item.id: item for item in per_signal}
    config = EvalConfig(alert_threshold=0.0, seed=SEED)

    reports = [
        _with_caveats(
            _named(
                evaluate(
                    ModelDetector(fitted=fitted),
                    test,
                    EvalConfig(alert_threshold=ALERT_THRESHOLD, seed=SEED),
                ),
                "hai[designed-normal-score][5A context]",
            )
        ),
        _with_caveats(
            _named(
                evaluate(
                    PrecomputedDetector(
                        name=f"{engine.name}/per-signal-evidence",
                        detections=detections_from(per_signal, magnitude, signals),
                    ),
                    test,
                    config,
                ),
                "hai[designed-normal-score][before]",
            )
        ),
        _with_caveats(
            _named(
                evaluate(
                    PrecomputedDetector(
                        name=f"{engine.name}/subsystem-events",
                        detections=detections_from(events, magnitude, signals),
                    ),
                    test,
                    config,
                ),
                "hai[designed-normal-score][after]",
            )
        ),
    ]
    logger.info(
        "hai windows covered: before=%d after=%d of %d; fit_obs=%d calib_obs=%d",
        len(windows_covered(per_signal, members, test.attack_intervals)),
        len(windows_covered(events, members, test.attack_intervals)),
        len(test.attack_intervals),
        len(fit.observations),
        len(calib.observations),
    )
    return reports


def run_distillation_normal_score() -> list[EvaluationReport]:
    """Designed train with normal-score weights; ADR 0082 test scoring; no topology / no vertical.

    Detection uses the **full** dual-clean train (same fit the designed baseline uses). The
    normal-score CDF is fitted on a held-out suffix scored by a model that never saw that suffix,
    then applied to the full-fit model. Alert counts therefore stay comparable to designed; any FP
    rise would be a real regression rather than an artefact of carving 10% off the fit.
    """
    manifest = _load_manifest("batch-distillation")
    if "train" not in manifest:
        raise RuntimeError("batch-distillation manifest has no attack-free train block")
    train = _adapter(manifest["train"]).load()
    test = _adapter(manifest).load()
    fit_prefix, calib = attack_free_fit_calib_split(train, calib_fraction=CALIB_FRACTION)
    partial = MahalanobisModel().fit(fit_prefix.observations)
    calibrator = NormalScoreCalibrator(seed=SEED).fit(normal_scores_from(partial, calib))
    full_fit = MahalanobisModel().fit(train.observations)
    config = EvalConfig(alert_threshold=ALERT_THRESHOLD, seed=SEED)

    reports = [
        _with_caveats(
            _named(
                evaluate(ModelDetector(fitted=full_fit), test, config),
                "batch-distillation[designed][adr0083-baseline]",
            )
        ),
        _with_caveats(
            _named(
                evaluate(
                    CalibratedModelDetector(fitted=full_fit, calibrator=calibrator),
                    test,
                    config,
                ),
                "batch-distillation[designed-normal-score]",
            )
        ),
    ]
    return reports


class CorpusSummary(BaseModel):
    """One corpus's measured rows for the sandbox report."""

    model_config = ConfigDict(frozen=True)

    corpus: str
    reports: tuple[EvaluationReport, ...]


def render(summaries: Sequence[CorpusSummary]) -> str:
    """Render every measured report as a markdown table."""
    header = (
        "| Dataset | Detector | Alerts | Recall | FPs | FP/normal-hr | Precision | ECE |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- |"
    )
    rows = [
        f"| `{report.dataset_name}` | `{report.detector_name}` | {report.n_alerts:,} "
        f"| {report.window_recall:.3f} | {report.false_positives:,} "
        f"| {report.false_positive_rate:.2f} | {report.precision:.4f} "
        f"| {report.expected_calibration_error:.4f} |"
        for summary in summaries
        for report in summary.reports
    ]
    return "\n".join([header, *rows])


def verdict_text(hai: Sequence[EvaluationReport], distillation: Sequence[EvaluationReport]) -> str:
    """Honest dual-corpus reading against ADR 0083 success."""
    grouped = next(r for r in hai if r.dataset_name.endswith("[after]"))
    baseline = distillation[0]
    candidate = distillation[1]
    lines = [
        "## Verdict (ADR 0083)",
        "",
        (
            f"- HAI gate: frozen ungated {QUOTED_HAI_UNGATED} / grouped "
            f"{QUOTED_HAI_GROUPED} reproduced."
        ),
        f"- HAI new path (`{grouped.dataset_name}`): "
        f"{grouped.n_alerts} alerts, recall {grouped.window_recall:.3f}, "
        f"FP/hr {grouped.false_positive_rate:.2f}. "
        f"Compare to frozen grouped {QUOTED_HAI_GROUPED} (short isotonic fit) "
        "and diagnostic 97 alerts at 60 h.",
        (
            f"- Batch-distillation baseline (full designed train): "
            f"recall {baseline.window_recall:.3f}, "
            f"FP/hr {baseline.false_positive_rate:.2f}, "
            f"precision {baseline.precision:.4f} "
            f"(sandbox noboom-atlas-v1 was "
            f"{NOBOOM_V1_RECALL}/{NOBOOM_V1_FP_RATE}/{NOBOOM_V1_PRECISION})."
        ),
        (
            "- Batch-distillation normal-score "
            "(full designed fit + normal-CDF from held-out suffix): "
            f"recall {candidate.window_recall:.3f}, "
            f"FP/hr {candidate.false_positive_rate:.2f}, "
            f"precision {candidate.precision:.4f}. "
            "Alert set must match baseline when the behavioural fit is identical; "
            "divergence means the calibrator leaked into scoring (a defect)."
        ),
        f"- Weights caveat: {NORMAL_SCORE_WEIGHT_CAVEAT}",
        "",
    ]
    hai_quieter = grouped.false_positive_rate < FROZEN_HAI_GROUPED - GATE_TOLERANCE
    hai_recall_ok = grouped.window_recall >= FROZEN_HAI_RECALL - 1e-9
    dist_both = (
        candidate.window_recall > baseline.window_recall + 1e-9
        and candidate.false_positive_rate < baseline.false_positive_rate - 1e-9
    )
    dist_parity = (
        abs(candidate.window_recall - baseline.window_recall) < 1e-9
        and abs(candidate.false_positive_rate - baseline.false_positive_rate) < 1e-9
    )
    if hai_quieter and hai_recall_ok and dist_both:
        lines.append(
            "**Dual-corpus success:** HAI quieter at full recall, and distillation improved both "
            "recall and FP/hr versus its designed baseline."
        )
    elif hai_quieter and hai_recall_ok and dist_parity:
        lines.append(
            "**Incomplete dual win:** HAI improved (longer attack-free fit unlocked by the "
            "normal-score calibrator) at unchanged recall. Batch-distillation detection "
            "metrics are **unchanged** versus designed — expected, because designed already "
            "fits the full attack-free train; the calibrator only adds evidence weights. "
            "ADR 0083 asked for improvement on both corpora; detection parity on "
            "distillation is not that improvement. Recipe-step coverage mismatch remains "
            "the residual FP driver."
        )
    elif hai_quieter and hai_recall_ok and not dist_both:
        lines.append(
            "**Incomplete dual win:** HAI improved at unchanged recall; batch-distillation did "
            "**not** improve both recall and FP/hr versus designed. The calibrator removes the "
            "labelled-positive blocker; it does not invent recipe-step coverage the dual-clean "
            "train never had."
        )
    else:
        lines.append(
            "**Measured negative or incomplete:** see the table. Do not publish a quieter public "
            "row from a partial win."
        )
    lines.extend(["", "Read with:", *(f"- {c}" for c in ATLAS_VERTICAL_CAVEATS)])
    return "\n".join(lines)


def write_report(path: Path, body: str) -> None:
    """Write the sandbox markdown report, creating the parent directory if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    logger.info("wrote %s", path)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns a process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--log",
        action="store_true",
        help="append NEW-named reports to eval_runs/log.jsonl (off by default)",
    )
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="print only; do not write the sandbox markdown report",
    )
    parser.add_argument("--skip-gate", action="store_true", help="development only")
    arguments = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if not arguments.skip_gate:
        gate_hai_frozen()

    hai_reports = run_hai_normal_score()
    dist_reports = run_distillation_normal_score()
    summaries = (
        CorpusSummary(corpus="hai", reports=tuple(hai_reports)),
        CorpusSummary(corpus="batch-distillation", reports=tuple(dist_reports)),
    )

    table = render(summaries)
    verdict = verdict_text(hai_reports, dist_reports)
    body = "\n".join(
        [
            "# ADR 0083 — normal-score calibrator measurement",
            "",
            "New experiment names only. Frozen 646.58 / 53.26 / 18.72 untouched.",
            f"Seed {SEED}, threshold {ALERT_THRESHOLD}, calib_fraction={CALIB_FRACTION}.",
            "",
            table,
            "",
            verdict,
            "",
        ]
    )
    print(body)

    if not arguments.no_write:
        write_report(OUT_DIR / "measurement.md", body)
        payload = {
            "seed": SEED,
            "alert_threshold": ALERT_THRESHOLD,
            "calib_fraction": CALIB_FRACTION,
            "reports": [r.model_dump(mode="json") for s in summaries for r in s.reports],
        }
        (OUT_DIR / "measurement.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    if arguments.log:
        for summary in summaries:
            for report in summary.reports:
                append_to_experiment_log(report)
        n_rows = sum(len(s.reports) for s in summaries)
        logger.info("appended %d new-named rows to the experiment log", n_rows)
    else:
        logger.info("not appending to log.jsonl (pass --log when authorised)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

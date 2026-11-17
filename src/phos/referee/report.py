"""Render an exam's score as a plain-language report: markdown and JSON, worst plants first.

PART S6. "Failures are listed before successes" is not a stylistic choice: the worst plants are
the first table a reader sees, before any headline number, because a reader scanning only the top
of a report should land on what went wrong rather than on a flattering mean.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final

from phos.eval import EvaluationReport
from phos.referee.exam import Exam
from phos.referee.scoring import DiscriminationHonesty, ExamScore, PlantScore, Summary
from phos.synth.events import EventKind

__all__ = [
    "load_raw_scores",
    "render_json",
    "render_markdown",
    "write_raw_scores",
    "write_report",
]

_WORST_PLANTS_SHOWN: Final = 10


def _summary_document(summary: Summary | None) -> dict[str, float | str] | None:
    """Return a `Summary` as a plain dict, or ``None`` unchanged."""
    if summary is None:
        return None
    return {
        "mean": summary.mean,
        "stddev": summary.stddev,
        "p5": summary.p5,
        "p50": summary.p50,
        "p95": summary.p95,
        "worst_plant_id": summary.worst_plant_id,
        "worst_value": summary.worst_value,
        "ci_low": summary.ci_low,
        "ci_high": summary.ci_high,
    }


def _discrimination_document(discrimination: DiscriminationHonesty | None) -> dict[str, Any] | None:
    """Return a `DiscriminationHonesty` as a plain dict, or ``None`` for a non-Atlas detector."""
    if discrimination is None:
        return None
    return {
        "discrimination_by_kind": {
            kind.value: value for kind, value in discrimination.discrimination_by_kind.items()
        },
        "insufficient_evidence_count": discrimination.insufficient_evidence_count,
        "insufficient_evidence_honest_count": discrimination.insufficient_evidence_honest_count,
        "honesty_rate": discrimination.honesty_rate,
    }


def _plant_document(plant: PlantScore) -> dict[str, Any]:
    """Return one plant's full score, nothing summarized away."""
    return {
        "plant_id": plant.plant_id,
        "family": plant.family,
        "false_positive_rate": plant.report.false_positive_rate,
        "window_recall": plant.report.window_recall,
        "recall_sample": plant.report.recall_sample,
        "expected_calibration_error": plant.report.expected_calibration_error,
        "brier_score": plant.report.brier_score,
        "latency": plant.report.latency.model_dump(mode="json"),
        "recall_by_technique": dict(plant.recall_by_technique),
        "recall_by_fault_type": dict(plant.recall_by_fault_type),
        "stealthy_recall": plant.stealthy_recall,
        "physical_effect_missed": plant.physical_effect_missed,
        "discrimination_honesty": _discrimination_document(plant.discrimination_honesty),
    }


def render_json(exam: Exam, score: ExamScore) -> str:
    """Return the full report as pretty, sorted-key JSON."""
    document = {
        "exam_id": exam.exam_id,
        "scorer_version": exam.scorer_version,
        "code_version": exam.code_version,
        "label": "SIMULATED",
        "detector_name": score.detector_name,
        "n_plants": score.n_plants,
        "false_positive_rate": _summary_document(score.false_positive_rate),
        "window_recall": _summary_document(score.window_recall),
        "expected_calibration_error": _summary_document(score.expected_calibration_error),
        "stealthy_recall": _summary_document(score.stealthy_recall),
        "total_physical_effect_missed": score.total_physical_effect_missed,
        "plants": [_plant_document(plant) for plant in score.plants],
    }
    return json.dumps(document, indent=2, sort_keys=True) + "\n"


def _summary_markdown(label: str, summary: Summary) -> str:
    """Return one headline metric as a bullet carrying its mean, its CI and its spread."""
    return (
        f"- **{label}** — mean {summary.mean:.4f} "
        f"(95% bootstrap CI {summary.ci_low:.4f}-{summary.ci_high:.4f}), "
        f"stddev {summary.stddev:.4f}, p5/p50/p95 "
        f"{summary.p5:.4f}/{summary.p50:.4f}/{summary.p95:.4f}, "
        f"worst plant `{summary.worst_plant_id}` ({summary.worst_value:.4f})"
    )


def render_markdown(exam: Exam, score: ExamScore) -> str:
    """Return the report as plain-language markdown, worst plants before the headline numbers."""
    lines: list[str] = [
        f"# Referee exam `{exam.exam_id[:12]}` — {score.detector_name}",
        "",
        "**SIMULATED.** Every plant in this exam is `phos.synth`'s model of an industrial "
        "process, not a real one. See Limitations below before quoting any number here.",
        "",
        f"- Plants scored: {score.n_plants}",
        f"- Scorer version: `{exam.scorer_version}`",
        f"- Code version: `{exam.code_version or 'unknown'}`",
        "",
        "## Worst plants first",
        "",
        "| plant | family | window recall | FP/hour | physical-effect missed |",
        "|---|---|---|---|---|",
    ]
    worst = sorted(score.plants, key=lambda plant: plant.report.window_recall)[:_WORST_PLANTS_SHOWN]
    for plant in worst:
        lines.append(
            f"| {plant.plant_id} | {plant.family} | {plant.report.window_recall:.3f} | "
            f"{plant.report.false_positive_rate:.4f} | {plant.physical_effect_missed} |"
        )

    lines += ["", "## Headline metrics", ""]
    lines.append(_summary_markdown("False alarms per normal hour", score.false_positive_rate))
    lines.append(_summary_markdown("Window recall", score.window_recall))
    lines.append(_summary_markdown("Expected calibration error", score.expected_calibration_error))
    if score.stealthy_recall is not None:
        lines.append(_summary_markdown("Stealthy-attack recall", score.stealthy_recall))
    lines += [
        "",
        f"**Physical-effect attacks and faults missed, summed across the exam: "
        f"{score.total_physical_effect_missed}.**",
        "",
        "## Limitations",
        "",
        "This exam is simulated: every plant is a model, written from public descriptions of how "
        "such processes behave, not a capture of a real one. A result here is evidence about how "
        "this detector behaves on PHOS's own models, not a field detection rate "
        "(`docs/rules/data-tiers.md`). Fault-versus-attack discrimination and uncertainty honesty "
        "are reported only for a detector that narrates competing hypotheses; a `null` for either "
        "means the detector does not, not that it scored zero.",
    ]
    return "\n".join(lines) + "\n"


def _plant_score_to_json(plant: PlantScore) -> dict[str, Any]:
    """Return one `PlantScore`, in full, as JSON.

    The raw unit `run` persists and `report` loads.
    """
    return {
        "plant_id": plant.plant_id,
        "family": plant.family,
        "report": plant.report.model_dump(mode="json"),
        "recall_by_technique": dict(plant.recall_by_technique),
        "recall_by_fault_type": dict(plant.recall_by_fault_type),
        "stealthy_recall": plant.stealthy_recall,
        "physical_effect_missed": plant.physical_effect_missed,
        "discrimination_honesty": _discrimination_document(plant.discrimination_honesty),
    }


def _plant_score_from_json(data: dict[str, Any]) -> PlantScore:
    """Return the `PlantScore` `_plant_score_to_json` wrote, reconstructed."""
    raw_discrimination = data["discrimination_honesty"]
    discrimination = None
    if raw_discrimination is not None:
        discrimination = DiscriminationHonesty(
            discrimination_by_kind={
                EventKind(key): value
                for key, value in raw_discrimination["discrimination_by_kind"].items()
            },
            insufficient_evidence_count=raw_discrimination["insufficient_evidence_count"],
            insufficient_evidence_honest_count=raw_discrimination[
                "insufficient_evidence_honest_count"
            ],
        )
    return PlantScore(
        plant_id=data["plant_id"],
        family=data["family"],
        report=EvaluationReport.model_validate(data["report"]),
        recall_by_technique=dict(data["recall_by_technique"]),
        recall_by_fault_type=dict(data["recall_by_fault_type"]),
        stealthy_recall=data["stealthy_recall"],
        physical_effect_missed=data["physical_effect_missed"],
        discrimination_honesty=discrimination,
    )


def write_raw_scores(detector_name: str, plants: list[PlantScore], path: Path) -> Path:
    """Persist every plant's unaggregated score, so `report` can re-render without rescoring."""
    path.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "detector_name": detector_name,
        "plants": [_plant_score_to_json(plant) for plant in plants],
    }
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def load_raw_scores(path: Path) -> tuple[str, list[PlantScore]]:
    """Return ``(detector_name, plants)`` as `write_raw_scores` wrote them."""
    document = json.loads(path.read_text(encoding="utf-8"))
    plants = [_plant_score_from_json(item) for item in document["plants"]]
    return document["detector_name"], plants


def write_report(exam: Exam, score: ExamScore, directory: Path) -> tuple[Path, Path]:
    """Write both the markdown and the JSON report into ``directory`` and return their paths."""
    directory.mkdir(parents=True, exist_ok=True)
    markdown_path = directory / f"{exam.exam_id}.md"
    json_path = directory / f"{exam.exam_id}.json"
    markdown_path.write_text(render_markdown(exam, score), encoding="utf-8")
    json_path.write_text(render_json(exam, score), encoding="utf-8")
    return markdown_path, json_path

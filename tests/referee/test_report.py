"""`phos.referee.report`: worst plants before headline numbers, and a raw-score round trip."""

from __future__ import annotations

import json
from pathlib import Path

from phos.eval import EvaluationReport, LatencySummary
from phos.ontology import Domain
from phos.referee.exam import Exam, ExamEntry
from phos.referee.report import (
    load_raw_scores,
    render_json,
    render_markdown,
    write_raw_scores,
    write_report,
)
from phos.referee.scoring import DiscriminationHonesty, PlantScore, aggregate
from phos.referee.seeds import SeedPool
from phos.synth.events import EventKind


def _report(window_recall: float, false_positive_rate: float) -> EvaluationReport:
    return EvaluationReport(
        detector_name="stub",
        dataset_name="stub",
        domain=Domain.ATLAS,
        seed=1,
        source_note="",
        alert_threshold=0.0,
        match_tolerance_seconds=0.0,
        calibration_bins=1,
        n_observations=1,
        n_detections=0,
        n_alerts=0,
        n_attack_intervals=0,
        n_unscored_intervals=0,
        n_unscored_alerts=0,
        normal_hours=1.0,
        window_recall=window_recall,
        false_positives=0,
        false_positive_rate=false_positive_rate,
        precision=1.0,
        recall_sample=0.5,
        f1=0.5,
        latency=LatencySummary(count=0),
        operating_points=[],
        expected_calibration_error=0.1,
        brier_score=0.1,
        reliability=[],
    )


def _plant(
    plant_id: str, window_recall: float, fp_rate: float, with_discrimination: bool = False
) -> PlantScore:
    discrimination = None
    if with_discrimination:
        discrimination = DiscriminationHonesty(
            discrimination_by_kind={
                EventKind.ATTACK: 1.0,
                EventKind.FAULT: None,
                EventKind.MAINTENANCE: None,
            },
            insufficient_evidence_count=2,
            insufficient_evidence_honest_count=1,
        )
    return PlantScore(
        plant_id=plant_id,
        family="level_flow",
        report=_report(window_recall, fp_rate),
        recall_by_technique={"sensor_replay": window_recall},
        recall_by_fault_type={},
        stealthy_recall=None,
        physical_effect_missed=0,
        discrimination_honesty=discrimination,
    )


def _exam() -> Exam:
    entry = ExamEntry(family="level_flow", seed=1, hours=4.0, event_seed=1, pool=SeedPool.DEV)
    return Exam.build([entry], "s6.0", "abc123")


def test_markdown_lists_worst_plants_before_headline_metrics() -> None:
    plants = [_plant("good", 1.0, 0.0), _plant("bad", 0.0, 5.0)]
    score = aggregate("stub", plants)
    markdown = render_markdown(_exam(), score)

    worst_index = markdown.index("## Worst plants first")
    headline_index = markdown.index("## Headline metrics")
    bad_index = markdown.index("bad")
    assert worst_index < headline_index
    assert bad_index < headline_index


def test_markdown_states_the_label_is_simulated() -> None:
    score = aggregate("stub", [_plant("p1", 1.0, 0.0)])
    assert "SIMULATED" in render_markdown(_exam(), score)


def test_json_report_round_trips_through_json_loads() -> None:
    score = aggregate("stub", [_plant("p1", 1.0, 0.0, with_discrimination=True)])
    document = json.loads(render_json(_exam(), score))
    assert document["n_plants"] == 1
    assert document["plants"][0]["plant_id"] == "p1"
    assert document["plants"][0]["discrimination_honesty"]["insufficient_evidence_count"] == 2
    assert (
        document["plants"][0]["discrimination_honesty"]["discrimination_by_kind"]["attack"] == 1.0
    )


def test_write_report_writes_both_files(tmp_path: Path) -> None:
    score = aggregate("stub", [_plant("p1", 1.0, 0.0)])
    markdown_path, json_path = write_report(_exam(), score, tmp_path / "out")
    assert markdown_path.exists()
    assert json_path.exists()
    assert markdown_path.suffix == ".md"
    assert json_path.suffix == ".json"


def test_raw_scores_round_trip_including_discrimination_honesty(tmp_path: Path) -> None:
    plants = [_plant("p1", 1.0, 0.0, with_discrimination=True), _plant("p2", 0.0, 1.0)]
    path = write_raw_scores("stub-detector", plants, tmp_path / "scores.json")

    detector_name, restored = load_raw_scores(path)

    assert detector_name == "stub-detector"
    assert len(restored) == 2
    assert restored[0].plant_id == "p1"
    assert restored[0].discrimination_honesty is not None
    assert restored[0].discrimination_honesty.discrimination_by_kind[EventKind.ATTACK] == 1.0
    assert restored[1].discrimination_honesty is None
    assert restored[0].report.window_recall == 1.0

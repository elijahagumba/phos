"""`phos.referee.scoring`: per-plant metrics on toy cases with known answers, then aggregation."""

from __future__ import annotations

import pytest

from phos.atlas import MahalanobisModel, load_topology
from phos.eval import Dataset, Detection, EvaluationReport, LatencySummary
from phos.models.base import SplitPolicy, train_test_split
from phos.ontology import Domain
from phos.reasoning import FittedPlattCalibrator
from phos.referee.corpus import event_records, load_plant_dataset
from phos.referee.detectors import AtlasDetector
from phos.referee.scoring import (
    ExamScore,
    PlantScore,
    ScoringError,
    _bootstrap_ci_mean,
    aggregate,
    score_plant,
    summarize,
)
from phos.synth.events import EventKind
from phos.synth.outputs import TOPOLOGY_FILE, GeneratedPlant

# ------------------------------------------------------------------------------------------------
# summarize / bootstrap, on known inputs
# ------------------------------------------------------------------------------------------------


def test_summarize_mean_and_percentiles_on_a_known_set() -> None:
    values = {"a": 0.0, "b": 50.0, "c": 100.0}
    summary = summarize(values, higher_is_better=True)
    assert summary.mean == pytest.approx(50.0)
    assert summary.p50 == pytest.approx(50.0)
    assert summary.worst_plant_id == "a"  # lowest, since higher is better


def test_summarize_worst_plant_flips_with_higher_is_better() -> None:
    values = {"a": 0.0, "b": 1.0}
    assert summarize(values, higher_is_better=True).worst_plant_id == "a"
    assert summarize(values, higher_is_better=False).worst_plant_id == "b"


def test_summarize_stddev_is_zero_for_one_plant() -> None:
    summary = summarize({"only": 42.0}, higher_is_better=True)
    assert summary.stddev == 0.0
    assert summary.ci_low == summary.ci_high == 42.0


def test_summarize_refuses_an_empty_mapping() -> None:
    with pytest.raises(ScoringError):
        summarize({}, higher_is_better=True)


def test_summarize_is_order_independent() -> None:
    forward = summarize({"a": 1.0, "b": 2.0, "c": 3.0}, higher_is_better=True)
    backward = summarize({"c": 3.0, "b": 2.0, "a": 1.0}, higher_is_better=True)
    assert forward.mean == backward.mean
    assert forward.stddev == backward.stddev
    assert forward.p50 == backward.p50


def test_bootstrap_ci_contains_the_sample_mean_for_a_constant_series() -> None:
    low, high = _bootstrap_ci_mean([5.0, 5.0, 5.0, 5.0], seed=1, resamples=200)
    assert low == pytest.approx(5.0)
    assert high == pytest.approx(5.0)


def test_bootstrap_ci_is_reproducible_for_a_fixed_seed() -> None:
    values = [1.0, 2.0, 3.0, 10.0, 20.0]
    first = _bootstrap_ci_mean(values, seed=20261116, resamples=500)
    second = _bootstrap_ci_mean(values, seed=20261116, resamples=500)
    assert first == second


# ------------------------------------------------------------------------------------------------
# aggregate, on hand-built PlantScores
# ------------------------------------------------------------------------------------------------


def _report(*, window_recall: float, false_positive_rate: float) -> EvaluationReport:
    """Return a minimal, otherwise-neutral `EvaluationReport` for an aggregation test."""
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


def _plant_score(
    plant_id: str, *, window_recall: float, fp_rate: float, missed: int = 0
) -> PlantScore:
    return PlantScore(
        plant_id=plant_id,
        family="level_flow",
        report=_report(window_recall=window_recall, false_positive_rate=fp_rate),
        recall_by_technique={},
        recall_by_fault_type={},
        stealthy_recall=None,
        physical_effect_missed=missed,
        discrimination_honesty=None,
    )


def test_aggregate_refuses_an_empty_exam() -> None:
    with pytest.raises(ScoringError):
        aggregate("stub", [])


def test_aggregate_sums_physical_effect_missed() -> None:
    plants = [
        _plant_score("p1", window_recall=1.0, fp_rate=0.0, missed=2),
        _plant_score("p2", window_recall=0.0, fp_rate=1.0, missed=1),
    ]
    score = aggregate("stub", plants)
    assert score.total_physical_effect_missed == 3
    assert score.n_plants == 2


def test_aggregate_worst_plant_for_recall_is_the_lowest() -> None:
    plants = [
        _plant_score("good", window_recall=1.0, fp_rate=0.0),
        _plant_score("bad", window_recall=0.0, fp_rate=0.0),
    ]
    score = aggregate("stub", plants)
    assert score.window_recall.worst_plant_id == "bad"
    assert score.false_positive_rate.worst_plant_id in ("good", "bad")  # both are 0.0, tie


def test_aggregate_is_deterministic_regardless_of_plant_order() -> None:
    plants = [
        _plant_score("p1", window_recall=0.8, fp_rate=0.2),
        _plant_score("p2", window_recall=0.6, fp_rate=0.4),
        _plant_score("p3", window_recall=1.0, fp_rate=0.0),
    ]
    forward = aggregate("stub", plants)
    backward = aggregate("stub", list(reversed(plants)))
    assert forward.window_recall.mean == backward.window_recall.mean
    assert forward.window_recall.stddev == backward.window_recall.stddev
    assert forward.false_positive_rate.mean == backward.false_positive_rate.mean


def test_stealthy_recall_is_none_when_no_plant_had_a_stealthy_attack() -> None:
    plants = [_plant_score("p1", window_recall=1.0, fp_rate=0.0)]
    assert aggregate("stub", plants).stealthy_recall is None


# ------------------------------------------------------------------------------------------------
# score_plant, against a real small generated plant, with hand-built known detectors
# ------------------------------------------------------------------------------------------------


class _NeverAlerts:
    name = "never-alerts"

    def run(self, dataset: Dataset) -> list[Detection]:
        del dataset
        return []


class _AlwaysAlerts:
    name = "always-alerts"

    def run(self, dataset: Dataset) -> list[Detection]:
        return [
            Detection(timestamp=observation.timestamp, score=1.0, confidence=1.0)
            for observation in dataset.observations
        ]


class _OracleDetector:
    """Alerts exactly once inside every event window this plant actually has."""

    name = "oracle"

    def __init__(self, plant: GeneratedPlant) -> None:
        self._plant = plant

    def run(self, dataset: Dataset) -> list[Detection]:
        del dataset
        return [
            Detection(timestamp=record.started_at, score=1.0, confidence=1.0)
            for record in event_records(self._plant)
            if record.kind in (EventKind.ATTACK, EventKind.FAULT)
        ]


def test_never_alerts_detector_has_zero_recall_and_zero_false_positives(
    small_exam_plant: GeneratedPlant,
) -> None:
    score = score_plant(_NeverAlerts(), small_exam_plant)
    assert score.report.window_recall == 0.0
    assert score.report.false_positive_rate == 0.0
    assert score.physical_effect_missed >= 0


def test_always_alerts_detector_has_perfect_recall(small_exam_plant: GeneratedPlant) -> None:
    score = score_plant(_AlwaysAlerts(), small_exam_plant)
    assert score.report.window_recall == 1.0


def test_oracle_detector_catches_every_detection_target(small_exam_plant: GeneratedPlant) -> None:
    score = score_plant(_OracleDetector(small_exam_plant), small_exam_plant)
    assert score.report.window_recall == 1.0
    assert score.physical_effect_missed == 0


def test_recall_by_technique_and_fault_type_are_populated(small_exam_plant: GeneratedPlant) -> None:
    score = score_plant(_OracleDetector(small_exam_plant), small_exam_plant)
    assert score.recall_by_technique or score.recall_by_fault_type


def test_non_atlas_detector_has_no_discrimination_honesty(small_exam_plant: GeneratedPlant) -> None:
    score = score_plant(_NeverAlerts(), small_exam_plant)
    assert score.discrimination_honesty is None


def test_score_plant_result_can_be_aggregated(small_exam_plant: GeneratedPlant) -> None:
    score = score_plant(_OracleDetector(small_exam_plant), small_exam_plant)
    exam_score = aggregate("oracle", [score])
    assert isinstance(exam_score, ExamScore)
    assert exam_score.window_recall.mean == 1.0


# ------------------------------------------------------------------------------------------------
# score_plant with a real AtlasDetector: the discrimination and honesty path
# ------------------------------------------------------------------------------------------------


def _atlas_detector_for(plant: GeneratedPlant) -> AtlasDetector:
    """Fit a real, minimal Atlas vertical on this plant's own attack-free training prefix."""
    dataset = load_plant_dataset(plant)
    train, _test = train_test_split(dataset, SplitPolicy())
    fitted = MahalanobisModel().fit(train.observations)
    calibrator = FittedPlattCalibrator(coefficient=0.05, intercept=0.0)
    topology = load_topology(
        plant.directory / TOPOLOGY_FILE,
        {observation.feature for observation in dataset.observations},
        corpus=plant.manifest.plant_id,
    )
    return AtlasDetector(fitted=fitted, calibrator=calibrator, subsystem_map=topology)


def test_atlas_detector_produces_discrimination_and_honesty(
    small_exam_plant: GeneratedPlant,
) -> None:
    score = score_plant(_atlas_detector_for(small_exam_plant), small_exam_plant)

    assert score.discrimination_honesty is not None
    # Whatever the numbers are, they must be in-range and self-consistent.
    for rate in score.discrimination_honesty.discrimination_by_kind.values():
        assert rate is None or 0.0 <= rate <= 1.0
    honesty = score.discrimination_honesty.honesty_rate
    assert honesty is None or 0.0 <= honesty <= 1.0
    assert score.discrimination_honesty.insufficient_evidence_honest_count <= (
        score.discrimination_honesty.insufficient_evidence_count
    )

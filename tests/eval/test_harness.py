"""Tests for the evaluation harness — the end-to-end proof that the ruler works."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from phos.eval.datasets import Dataset, SyntheticAnomaly, SyntheticICSAdapter
from phos.eval.detectors import Detection, ThresholdDetector
from phos.eval.harness import EvalConfig, evaluate, sweep_thresholds
from phos.ontology import Domain, Observation

T0 = datetime(2026, 7, 28, 9, 0, tzinfo=UTC)

# A 240-point periodic signal with a single 20-sample anomaly of magnitude 50 injected at
# indices 100..119. The offset is far outside the noise, so a z-score threshold of 2.0
# separates the anomaly from normal operation cleanly and ground truth is known exactly.
ANOMALY = SyntheticAnomaly(
    start_index=100, end_index=119, magnitude=50.0, attack_type="setpoint_tamper"
)


@pytest.fixture
def synthetic() -> Dataset:
    return SyntheticICSAdapter(
        n_points=240, anomaly_intervals=(ANOMALY,), seed=11, noise_stddev=1.0
    ).load()


# --------------------------------------------------------------------------------------------
# EvalConfig
# --------------------------------------------------------------------------------------------


def test_eval_config_has_usable_defaults() -> None:
    config = EvalConfig()
    assert config.alert_threshold == 0.0
    assert config.match_tolerance == timedelta(0)
    assert config.calibration_bins == 10


def test_eval_config_rejects_a_negative_tolerance() -> None:
    with pytest.raises(ValidationError):
        EvalConfig(match_tolerance=timedelta(seconds=-1))


def test_eval_config_rejects_a_non_positive_bin_count() -> None:
    with pytest.raises(ValidationError):
        EvalConfig(calibration_bins=0)


def test_eval_config_is_frozen() -> None:
    with pytest.raises(ValidationError):
        EvalConfig().seed = 9  # type: ignore[misc]


# --------------------------------------------------------------------------------------------
# sweep_thresholds
# --------------------------------------------------------------------------------------------


def test_sweep_thresholds_is_empty_without_detections() -> None:
    assert sweep_thresholds([]) == []


def test_sweep_thresholds_are_ascending_and_span_the_scores() -> None:
    detections = [
        Detection(timestamp=T0 + timedelta(seconds=i), score=float(i), confidence=0.5)
        for i in range(100)
    ]
    thresholds = sweep_thresholds(detections)
    assert thresholds == sorted(thresholds)
    assert thresholds[0] == 0.0
    assert thresholds[-1] == 99.0


def test_sweep_thresholds_collapses_a_single_valued_score_distribution() -> None:
    detections = [
        Detection(timestamp=T0 + timedelta(seconds=i), score=4.0, confidence=0.5) for i in range(10)
    ]
    assert sweep_thresholds(detections) == [4.0]


# --------------------------------------------------------------------------------------------
# evaluate — synthetic end-to-end against known ground truth
# --------------------------------------------------------------------------------------------


def test_evaluate_recovers_the_injected_anomaly(synthetic: Dataset) -> None:
    report = evaluate(ThresholdDetector(), synthetic, EvalConfig(alert_threshold=2.0))

    assert report.window_recall == 1.0
    assert report.false_positives == 0
    assert report.false_positive_rate == 0.0
    assert report.precision == 1.0
    assert report.latency.count == 1


def test_evaluate_records_what_it_scored(synthetic: Dataset) -> None:
    report = evaluate(ThresholdDetector(), synthetic, EvalConfig(alert_threshold=2.0))

    assert report.detector_name == "threshold-detector"
    assert report.dataset_name == "synthetic-ics"
    assert report.domain is Domain.ATLAS
    assert report.n_observations == 240
    assert report.n_detections == 240
    assert report.n_attack_intervals == 1
    assert 0 < report.n_alerts < report.n_detections
    assert report.source_note == synthetic.source_note


def test_evaluate_echoes_the_config_so_the_numbers_can_be_reproduced(
    synthetic: Dataset,
) -> None:
    config = EvalConfig(
        alert_threshold=2.5, match_tolerance=timedelta(seconds=45), calibration_bins=4, seed=99
    )
    report = evaluate(ThresholdDetector(), synthetic, config)

    assert report.alert_threshold == 2.5
    assert report.match_tolerance_seconds == 45.0
    assert report.calibration_bins == 4
    assert report.seed == 99
    assert len(report.reliability) == 4


def test_evaluate_measures_a_badly_tuned_detector_as_bad(synthetic: Dataset) -> None:
    # Alerting on everything catches the attack but drowns the operator: the harness has to
    # show that as a large false-positive rate, not as a perfect recall score.
    report = evaluate(ThresholdDetector(), synthetic, EvalConfig(alert_threshold=0.0))

    assert report.window_recall == 1.0
    assert report.false_positives > 0
    assert report.false_positive_rate > 0.0
    assert report.precision < 0.5


def test_evaluate_normal_hours_is_the_false_positive_denominator(synthetic: Dataset) -> None:
    report = evaluate(ThresholdDetector(), synthetic, EvalConfig(alert_threshold=0.0))
    expected = synthetic.normal_duration().total_seconds() / 3600
    assert report.normal_hours == pytest.approx(expected)
    assert report.false_positive_rate == pytest.approx(report.false_positives / expected)


def test_evaluate_produces_a_monotone_operating_point_curve(synthetic: Dataset) -> None:
    report = evaluate(ThresholdDetector(), synthetic, EvalConfig())
    recalls = [point.recall for point in report.operating_points]
    fp_rates = [point.fp_rate for point in report.operating_points]

    assert len(report.operating_points) > 1
    assert recalls == sorted(recalls, reverse=True)
    assert fp_rates == sorted(fp_rates, reverse=True)


def test_evaluate_reports_calibration(synthetic: Dataset) -> None:
    report = evaluate(ThresholdDetector(), synthetic, EvalConfig(alert_threshold=2.0))
    assert 0.0 <= report.expected_calibration_error <= 1.0
    assert report.brier_score >= 0.0
    assert sum(row.count for row in report.reliability) == report.n_alerts


def test_evaluate_is_deterministic(synthetic: Dataset) -> None:
    config = EvalConfig(alert_threshold=2.0, seed=42)
    first = evaluate(ThresholdDetector(), synthetic, config)
    second = evaluate(ThresholdDetector(), synthetic, config)

    # created_at is wall-clock provenance, and is the only field allowed to differ.
    assert first.model_dump(exclude={"created_at"}) == second.model_dump(exclude={"created_at"})


def test_evaluate_is_deterministic_across_freshly_loaded_datasets() -> None:
    config = EvalConfig(alert_threshold=2.0, seed=42)
    adapter = SyntheticICSAdapter(n_points=120, anomaly_intervals=(ANOMALY,), seed=5)
    first = evaluate(ThresholdDetector(), adapter.load(), config)
    second = evaluate(ThresholdDetector(), adapter.load(), config)

    assert first.model_dump(exclude={"created_at"}) == second.model_dump(exclude={"created_at"})


def test_evaluate_handles_a_corpus_with_no_attacks() -> None:
    clean = SyntheticICSAdapter(n_points=60, seed=3).load()
    report = evaluate(ThresholdDetector(), clean, EvalConfig(alert_threshold=2.0))

    assert report.n_attack_intervals == 0
    assert report.window_recall == 0.0
    assert report.recall_sample == 0.0
    assert report.false_positives == report.n_alerts


def test_evaluate_handles_an_empty_corpus() -> None:
    empty = Dataset(
        name="empty",
        domain=Domain.ATLAS,
        observations=[],
        attack_intervals=[],
        source_note="",
    )
    report = evaluate(ThresholdDetector(), empty, EvalConfig())

    assert report.n_observations == 0
    assert report.n_alerts == 0
    assert report.window_recall == 0.0
    assert report.false_positive_rate == 0.0
    assert report.operating_points == []
    assert report.latency.count == 0


def test_evaluate_applies_tolerance_consistently() -> None:
    # One alert, 10 s before the labelled window opens. With 30 s of tolerance it must count as
    # a hit AND stop being a false positive — never both.
    observations = [
        Observation(
            id=f"obs_{second:012d}",
            entity_ids=["ent_000000000001"],
            feature="flow_rate",
            value=1.0,
            timestamp=T0 + timedelta(seconds=second),
            domain=Domain.ATLAS,
        )
        for second in range(0, 3601, 60)
    ]
    dataset = Dataset.model_validate(
        {
            "name": "tolerance",
            "domain": Domain.ATLAS,
            "observations": observations,
            "attack_intervals": [
                {
                    "start": T0 + timedelta(seconds=600),
                    "end": T0 + timedelta(seconds=900),
                    "label": "attack",
                    "attack_type": None,
                }
            ],
            "source_note": "",
        }
    )

    class SingleAlertDetector:
        """Fires once, 10 s before the labelled window opens."""

        name = "single-alert"

        def run(self, dataset: Dataset) -> list[Detection]:
            return [Detection(timestamp=T0 + timedelta(seconds=590), score=10.0, confidence=0.9)]

    strict = evaluate(SingleAlertDetector(), dataset, EvalConfig())
    assert strict.window_recall == 0.0
    assert strict.false_positives == 1

    forgiving = evaluate(
        SingleAlertDetector(), dataset, EvalConfig(match_tolerance=timedelta(seconds=30))
    )
    assert forgiving.window_recall == 1.0
    assert forgiving.false_positives == 0

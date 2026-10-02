"""Tests for the model/harness adapter — and the first real detection numbers in PHOS.

The headline tests at the bottom are the point of PART 3: a behavioural model is split off
attack-free training data, fitted, and then scored by the PART 2 harness it has never met, on data
it has never seen.
"""

import math
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from phos.eval import (
    Dataset,
    Detection,
    Detector,
    EvalConfig,
    SyntheticAnomaly,
    SyntheticICSAdapter,
    evaluate,
)
from phos.models.base import FittedModel, SplitPolicy, train_test_split
from phos.models.detector import ModelDetector, uncalibrated_confidence
from phos.models.ewma import EwmaBaseline
from phos.models.gaussian import GaussianBaseline
from phos.models.iqr import IqrBaseline
from phos.ontology import Deviation, Domain, ExpectedRange, Observation

T0 = datetime(2026, 7, 28, 9, 0, tzinfo=UTC)
ENTITY = "ent_00000000000a"
FEATURE = "flow_rate"

TRAINING_VALUES = [8.0, 12.0] * 4  # mean 10, stddev 2 — see test_gaussian.py


def observation(index: int, value: float) -> Observation:
    return Observation(
        id=f"obs_{index:012d}",
        entity_ids=[ENTITY],
        feature=FEATURE,
        value=value,
        timestamp=T0 + timedelta(minutes=index),
        domain=Domain.ATLAS,
    )


def series(values: list[float], *, start: int = 0) -> list[Observation]:
    return [observation(start + index, value) for index, value in enumerate(values)]


def dataset(observations: list[Observation]) -> Dataset:
    return Dataset(
        name="fixture",
        domain=Domain.ATLAS,
        observations=observations,
        attack_intervals=[],
        source_note="fixture",
    )


@pytest.fixture
def fitted_gaussian() -> FittedModel:
    return GaussianBaseline().fit(series(TRAINING_VALUES))


# --------------------------------------------------------------------------------------------
# uncalibrated_confidence
# --------------------------------------------------------------------------------------------


def test_confidence_is_the_documented_squash() -> None:
    assert uncalibrated_confidence(3.0, 3.0) == pytest.approx(1.0 - math.exp(-1.0))


def test_confidence_is_zero_for_no_departure() -> None:
    assert uncalibrated_confidence(0.0, 3.0) == 0.0


def test_confidence_is_monotone_in_the_magnitude() -> None:
    values = [uncalibrated_confidence(magnitude, 3.0) for magnitude in (0.0, 1.0, 5.0, 50.0)]
    assert values == sorted(values)


def test_confidence_stays_bounded_even_for_a_clamped_magnitude() -> None:
    assert 0.0 <= uncalibrated_confidence(1e6, 3.0) <= 1.0


def test_a_larger_scale_is_more_conservative() -> None:
    assert uncalibrated_confidence(3.0, 10.0) < uncalibrated_confidence(3.0, 3.0)


# --------------------------------------------------------------------------------------------
# ModelDetector
# --------------------------------------------------------------------------------------------


def test_it_satisfies_the_harness_detector_protocol(fitted_gaussian: FittedModel) -> None:
    assert isinstance(ModelDetector(fitted=fitted_gaussian), Detector)


def test_its_name_identifies_the_model_behind_it(fitted_gaussian: FittedModel) -> None:
    assert ModelDetector(fitted=fitted_gaussian).name == "model:gaussian"


def test_it_keeps_the_concrete_fitted_model_it_was_given(fitted_gaussian: FittedModel) -> None:
    detector = ModelDetector(fitted=fitted_gaussian)
    assert detector.fitted is fitted_gaussian


def test_the_detection_score_is_the_deviation_magnitude(fitted_gaussian: FittedModel) -> None:
    detections = ModelDetector(fitted=fitted_gaussian).run(dataset(series([16.0], start=100)))

    assert len(detections) == 1
    assert detections[0].score == pytest.approx(3.0)


def test_the_detection_confidence_is_the_uncalibrated_squash(
    fitted_gaussian: FittedModel,
) -> None:
    detections = ModelDetector(fitted=fitted_gaussian, score_scale=3.0).run(
        dataset(series([16.0], start=100))
    )

    # Not a calibrated probability, and asserted here as exactly the documented formula so that
    # PART 4 replacing it is a visible, deliberate change rather than a silent one.
    assert detections[0].confidence == pytest.approx(uncalibrated_confidence(3.0, 3.0))


def test_the_detection_carries_the_observations_identity(fitted_gaussian: FittedModel) -> None:
    scored = series([16.0], start=100)
    detections = ModelDetector(fitted=fitted_gaussian).run(dataset(scored))

    assert detections[0].timestamp == scored[0].timestamp
    assert detections[0].entity_ids == [ENTITY]
    assert detections[0].feature == FEATURE


def test_it_emits_nothing_for_entirely_normal_data(fitted_gaussian: FittedModel) -> None:
    assert ModelDetector(fitted=fitted_gaussian).run(dataset(series([10.0] * 5, start=100))) == []


def test_detections_round_trip_through_json(fitted_gaussian: FittedModel) -> None:
    detection = ModelDetector(fitted=fitted_gaussian).run(dataset(series([16.0], start=100)))[0]

    assert Detection.model_validate_json(detection.model_dump_json()) == detection


@pytest.mark.parametrize("scale", [0.0, -1.0])
def test_score_scale_must_be_positive(fitted_gaussian: FittedModel, scale: float) -> None:
    with pytest.raises(ValidationError):
        ModelDetector(fitted=fitted_gaussian, score_scale=scale)


class StrayDeviationModel(FittedModel):
    """A broken model that reports a deviation for an observation nobody gave it."""

    def score(self, observations: Sequence[Observation]) -> list[Deviation]:
        return [
            Deviation(
                observation_id="obs_notinthisdataset",
                expected=ExpectedRange(
                    feature=FEATURE,
                    entity_id=ENTITY,
                    low=0.0,
                    high=1.0,
                    mean=0.5,
                    stddev=0.1,
                    learned_from_window=(T0, T0),
                ),
                magnitude=1.0,
                timestamp=T0,
            )
        ]


def test_an_untraceable_deviation_is_an_error_not_a_dropped_row() -> None:
    broken = ModelDetector(
        fitted=StrayDeviationModel(name="broken", expected_ranges={}, feature_ranges={}, emit_k=0.0)
    )

    with pytest.raises(ValueError, match="cannot be traced back"):
        broken.run(dataset(series([10.0] * 3)))


# --------------------------------------------------------------------------------------------
# HEADLINE — a real behavioural model, scored on the real ruler
# --------------------------------------------------------------------------------------------

# 480 samples 30 s apart: four hours of a periodic "process" signal. A 40-sample offset of +25 is
# injected from index 360, well after the halfway mark, so the attack-free training prefix is a
# clean two hours and the model is scored only on the two hours it has never seen.
ANOMALY = SyntheticAnomaly(
    start_index=360, end_index=399, magnitude=25.0, attack_type="setpoint_tamper"
)


@pytest.fixture
def split_corpus() -> tuple[Dataset, Dataset]:
    corpus = SyntheticICSAdapter(
        n_points=480, anomaly_intervals=(ANOMALY,), seed=11, noise_stddev=1.0
    ).load()
    return train_test_split(corpus, SplitPolicy(train_fraction=0.5))


def test_the_split_gives_clean_training_and_a_labelled_test_half(
    split_corpus: tuple[Dataset, Dataset],
) -> None:
    train, test = split_corpus

    assert len(train.observations) == 240
    assert train.attack_intervals == []
    assert len(test.observations) == 240
    assert len(test.attack_intervals) == 1


def test_gaussian_baseline_scored_end_to_end_on_the_harness(
    split_corpus: tuple[Dataset, Dataset],
) -> None:
    train, test = split_corpus
    fitted = GaussianBaseline().fit(train.observations)

    report = evaluate(ModelDetector(fitted=fitted), test, EvalConfig(alert_threshold=3.0, seed=7))

    assert report.detector_name == "model:gaussian"
    assert report.dataset_name == "synthetic-ics-test"
    assert report.window_recall == 1.0
    assert report.false_positives == 0
    assert report.false_positive_rate == 0.0
    assert report.precision == 1.0
    assert report.latency.count == 1
    assert report.latency.min_seconds == 0.0
    # A dense candidate set beneath the alert threshold is what makes the sweep meaningful.
    assert report.n_detections > report.n_alerts > 0
    assert len(report.operating_points) > 1


def test_ewma_baseline_scored_end_to_end_on_the_harness(
    split_corpus: tuple[Dataset, Dataset],
) -> None:
    train, test = split_corpus
    fitted = EwmaBaseline().fit(train.observations)

    report = evaluate(ModelDetector(fitted=fitted), test, EvalConfig(alert_threshold=3.0, seed=7))

    assert report.window_recall == 1.0
    assert math.isfinite(report.false_positive_rate)
    assert report.false_positive_rate < 5.0


def test_iqr_baseline_scored_end_to_end_on_the_harness(
    split_corpus: tuple[Dataset, Dataset],
) -> None:
    train, test = split_corpus
    fitted = IqrBaseline().fit(train.observations)

    # An IQR magnitude is an overshoot in interquartile ranges, not a z-score, so its operating
    # point lives on a different scale. That the scales differ is exactly why the harness sweeps
    # each detector's own scores rather than comparing raw ones across detectors.
    report = evaluate(ModelDetector(fitted=fitted), test, EvalConfig(alert_threshold=1.0, seed=7))

    assert report.window_recall == 1.0
    assert math.isfinite(report.false_positive_rate)
    assert report.false_positive_rate < 5.0


def test_the_harness_measures_calibration_without_anything_having_fitted_it(
    split_corpus: tuple[Dataset, Dataset],
) -> None:
    train, test = split_corpus
    fitted = GaussianBaseline().fit(train.observations)

    report = evaluate(ModelDetector(fitted=fitted), test, EvalConfig(alert_threshold=3.0, seed=7))

    # Calibration is measured here, never fitted (PART 4 fits it). The number must exist so the
    # improvement PART 4 makes is provable against this baseline.
    assert 0.0 <= report.expected_calibration_error <= 1.0
    assert report.brier_score >= 0.0
    assert sum(row.count for row in report.reliability) == report.n_alerts


def test_the_end_to_end_run_is_deterministic(split_corpus: tuple[Dataset, Dataset]) -> None:
    train, test = split_corpus
    config = EvalConfig(alert_threshold=3.0, seed=42)

    first = evaluate(ModelDetector(fitted=GaussianBaseline().fit(train.observations)), test, config)
    second = evaluate(
        ModelDetector(fitted=GaussianBaseline().fit(train.observations)), test, config
    )

    assert first.model_dump(exclude={"created_at"}) == second.model_dump(exclude={"created_at"})


def test_a_model_fitted_on_nothing_scores_nothing_rather_than_alerting(
    split_corpus: tuple[Dataset, Dataset],
) -> None:
    _, test = split_corpus
    fitted = GaussianBaseline().fit([])

    report = evaluate(ModelDetector(fitted=fitted), test, EvalConfig(seed=7))

    # No baseline means no claim. Emitting alerts here would be asserting past the evidence.
    assert report.n_detections == 0
    assert report.false_positives == 0

"""Tests for the calibrated detector — the path on which Constitution §3.3 is finally satisfied.

The important structural property is that only the *confidence* changes. `score` stays the raw
anomaly magnitude, so every threshold the harness sweeps still means what it meant in PART 3 and
the two detectors can be compared on the same alert set.
"""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import numpy
import pytest
from numpy.typing import NDArray

from phos.eval import Dataset, Detector, EvalConfig, LabelledInterval, evaluate
from phos.models import FittedModel, GaussianBaseline, ModelDetector
from phos.ontology import Deviation, Domain, ExpectedRange, Observation
from phos.reasoning.calibration import FittedIsotonicCalibrator, FittedPlattCalibrator
from phos.reasoning.detector import CalibratedModelDetector

T0 = datetime(2026, 7, 29, 0, 0, tzinfo=UTC)
ENTITY = "ent_00000000000a"
FEATURE = "flow_rate"

#: sigmoid(0.5·score - 2): about 0.12 at score 0, about 0.62 at score 5.
PLATT = FittedPlattCalibrator(coefficient=0.5, intercept=-2.0)


def observations(values: list[float], *, start: int = 0) -> list[Observation]:
    return [
        Observation(
            id=f"obs_{start + index:012d}",
            entity_ids=[ENTITY],
            feature=FEATURE,
            value=value,
            timestamp=T0 + timedelta(minutes=start + index),
            domain=Domain.ATLAS,
        )
        for index, value in enumerate(values)
    ]


def fitted_model() -> FittedModel:
    """A Gaussian fitted on a mean-12, stddev-2 training window."""
    return GaussianBaseline(min_samples=4).fit(observations([10.0, 14.0] * 8))


def scoring_dataset() -> Dataset:
    scoring = observations([12.0, 20.0, 12.0, 30.0], start=100)
    return Dataset(
        name="fixture",
        domain=Domain.ATLAS,
        observations=scoring,
        attack_intervals=[
            LabelledInterval(start=scoring[3].timestamp, end=scoring[3].timestamp, label="attack")
        ],
        source_note="fixture",
    )


def detector() -> CalibratedModelDetector:
    return CalibratedModelDetector(fitted=fitted_model(), calibrator=PLATT)


# ------------------------------------------------------------------------------------------------
# Shape and contract
# ------------------------------------------------------------------------------------------------


def test_satisfies_the_harness_detector_protocol() -> None:
    assert isinstance(detector(), Detector)


def test_name_records_both_the_model_and_the_calibrator() -> None:
    """The experiment log has to tell a calibrated run from an uncalibrated one at a glance."""
    assert detector().name == "model:gaussian+platt"


def test_score_remains_the_raw_magnitude() -> None:
    """Only confidence is calibrated. The threshold sweep still operates on the raw score.

    If calibration replaced the score, every `alert_threshold` in the experiment log would silently
    change meaning between PART 3's runs and this one, and the before/after comparison would be
    between two different alert sets rather than two readings of the same one.
    """
    dataset = scoring_dataset()
    calibrated = detector().run(dataset)
    uncalibrated = ModelDetector(fitted=fitted_model()).run(dataset)

    assert [d.score for d in calibrated] == [d.score for d in uncalibrated]
    assert [d.timestamp for d in calibrated] == [d.timestamp for d in uncalibrated]


def test_confidence_is_the_calibrated_probability() -> None:
    dataset = scoring_dataset()

    detections = detector().run(dataset)

    scores = numpy.asarray([d.score for d in detections], dtype=float)
    assert numpy.allclose([d.confidence for d in detections], PLATT.calibrate(scores))


def test_confidence_differs_from_the_uncalibrated_path() -> None:
    """A regression guard: if these ever agreed, calibration would be doing nothing."""
    dataset = scoring_dataset()

    calibrated = detector().run(dataset)
    uncalibrated = ModelDetector(fitted=fitted_model()).run(dataset)

    assert [d.confidence for d in calibrated] != [d.confidence for d in uncalibrated]


def test_is_deterministic() -> None:
    dataset = scoring_dataset()

    assert detector().run(dataset) == detector().run(dataset)


# ------------------------------------------------------------------------------------------------
# Through the harness
# ------------------------------------------------------------------------------------------------


def test_runs_through_the_harness_and_reports_the_calibrated_confidences() -> None:
    dataset = scoring_dataset()
    subject = detector()

    report = evaluate(subject, dataset, EvalConfig(alert_threshold=1.0, seed=11))

    assert report.detector_name == "model:gaussian+platt"
    assert report.dataset_name == dataset.name
    assert report.n_alerts > 0
    assert sum(row.count for row in report.reliability) == report.n_alerts
    assert 0.0 <= report.expected_calibration_error <= 1.0
    # The reliability table bins the calibrated confidences, so its populated bins must be the ones
    # the calibrator actually produced.
    alerts = [d for d in subject.run(dataset) if d.score >= 1.0]
    populated = {min(int(d.confidence * 10), 9) for d in alerts}
    assert {index for index, row in enumerate(report.reliability) if row.count} == populated


def test_harness_report_is_deterministic_under_seed() -> None:
    dataset = scoring_dataset()
    config = EvalConfig(alert_threshold=1.0, seed=11)

    first = evaluate(detector(), dataset, config)
    second = evaluate(detector(), dataset, config)

    assert first.model_dump(exclude={"created_at"}) == second.model_dump(exclude={"created_at"})


def test_works_with_an_isotonic_calibrator_too() -> None:
    isotonic = FittedIsotonicCalibrator(
        score_thresholds=(0.0, 5.0, 10.0), probability_thresholds=(0.0, 0.4, 0.9)
    )
    subject = CalibratedModelDetector(fitted=fitted_model(), calibrator=isotonic)

    detections = subject.run(scoring_dataset())

    assert subject.name == "model:gaussian+isotonic"
    assert all(0.0 <= d.confidence <= 1.0 for d in detections)


# ------------------------------------------------------------------------------------------------
# Refusals
# ------------------------------------------------------------------------------------------------


class RogueCalibrator:
    """Satisfies the protocol structurally but returns numbers that are not probabilities."""

    name = "rogue"

    def calibrate(self, scores: NDArray[numpy.float64]) -> NDArray[numpy.float64]:
        return numpy.full(numpy.asarray(scores).shape, 1.5)


def test_refuses_a_calibrator_that_returns_values_outside_zero_one() -> None:
    """A structural protocol cannot enforce a numeric range, so the detector checks it.

    `FittedCalibrator` is a `Protocol`: anything with the right method satisfies it, including
    something that returns 1.5. Letting that through would put a non-probability on the
    user-facing confidence path, which is exactly what §3.3 is about.
    """
    subject = CalibratedModelDetector(fitted=fitted_model(), calibrator=RogueCalibrator())

    with pytest.raises(ValueError, match=r"outside \[0, 1\]"):
        subject.run(scoring_dataset())


class OrphanEmittingModel(FittedModel):
    """A fitted model that emits a deviation for an observation nobody has ever seen."""

    def score(self, observations: Sequence[Observation]) -> list[Deviation]:
        return [
            Deviation(
                observation_id="obs_ffffffffffff",
                expected=ExpectedRange(
                    feature=FEATURE,
                    entity_id=ENTITY,
                    low=0.0,
                    high=1.0,
                    mean=0.5,
                    stddev=0.1,
                    learned_from_window=(T0, T0),
                ),
                magnitude=9.0,
                timestamp=T0,
            )
        ]


def test_refuses_a_deviation_it_cannot_trace_to_an_observation() -> None:
    """Same refusal as `ModelDetector`, for the same constitutional reason (§3.2).

    A detection whose measurement cannot be produced is unexplainable by construction, so it is
    raised rather than quietly dropped.
    """
    rogue = OrphanEmittingModel(name="orphan", expected_ranges={}, feature_ranges={}, emit_k=1.0)
    subject = CalibratedModelDetector(fitted=rogue, calibrator=PLATT)

    with pytest.raises(ValueError, match="unknown observation"):
        subject.run(scoring_dataset())


def test_emits_nothing_when_the_model_emits_nothing() -> None:
    quiet = Dataset(
        name="quiet",
        domain=Domain.ATLAS,
        observations=observations([12.0, 12.0, 12.0], start=200),
    )

    assert detector().run(quiet) == []


class WrongLengthCalibrator:
    """Satisfies the protocol but returns the wrong number of probabilities."""

    name = "wrong-length"

    def calibrate(self, scores: NDArray[numpy.float64]) -> NDArray[numpy.float64]:
        return numpy.asarray([0.5])


def test_refuses_a_calibrator_that_returns_the_wrong_number_of_probabilities() -> None:
    """Pairing detections with probabilities positionally only works if the counts match.

    A protocol cannot express "returns one probability per score", so a calibrator that returns
    fewer would otherwise have its output silently zipped against the wrong detections — assigning
    real confidences to the wrong measurements, which is a traceability failure that no downstream
    check could detect.
    """
    subject = CalibratedModelDetector(fitted=fitted_model(), calibrator=WrongLengthCalibrator())

    with pytest.raises(ValueError, match="probabilities"):
        subject.run(scoring_dataset())

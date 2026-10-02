"""Tests for the calibration layer.

The headline property is measured with the PART 2 metric rather than a private one: a calibrator
is only worth anything if `phos.eval.expected_calibration_error` — the number the harness already
reports — says so. `_ece_of` below is the small bridge that lets a pure ``(confidence, label)``
vector be scored by a metric whose signature speaks detections and datasets.
"""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import numpy
import pytest
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict

from phos.eval import Dataset, Detection, LabelledInterval, expected_calibration_error
from phos.models import FittedModel, GaussianBaseline
from phos.ontology import Deviation, Domain, ExpectedRange, Observation
from phos.reasoning.calibration import (
    FittedCalibrator,
    FittedPlattCalibrator,
    IsotonicCalibrator,
    PlattCalibrator,
    calibrated_probabilities,
    scores_and_labels_from,
)

T0 = datetime(2026, 7, 29, 12, 0, tzinfo=UTC)
ENTITY = "ent_00000000000a"
FEATURE = "flow_rate"

CALIBRATORS = [IsotonicCalibrator(), PlattCalibrator()]
CALIBRATOR_IDS = ["isotonic", "platt"]


def staircase(
    levels: int = 10, per_level: int = 100
) -> tuple[NDArray[numpy.float64], NDArray[numpy.float64]]:
    """Return ``(scores, labels)`` whose attack rate is exactly ``level / levels`` per level.

    Deterministic by construction rather than sampled: level ``i`` holds ``per_level`` points of
    score ``i``, of which exactly ``i * per_level / levels`` are attacks. So the true probability
    at score ``i`` is exactly ``i / levels``, with no sampling noise for a calibrator to be
    forgiven for. A calibrator that cannot recover an exact staircase cannot recover anything.
    """
    scores: list[float] = []
    labels: list[float] = []
    for level in range(levels):
        positives = round(per_level * level / levels)
        scores.extend([float(level)] * per_level)
        labels.extend([1.0] * positives + [0.0] * (per_level - positives))
    return numpy.asarray(scores, dtype=float), numpy.asarray(labels, dtype=float)


def _ece_of(
    confidences: NDArray[numpy.float64], labels: NDArray[numpy.float64], bins: int = 10
) -> float:
    """Score confidences against labels using the PART 2 metric, not a private reimplementation."""
    stamps = [T0 + timedelta(minutes=index) for index in range(len(labels))]
    dataset = Dataset(
        name="calibration-fixture",
        domain=Domain.ATLAS,
        observations=[
            Observation(
                id=f"obs_{index:012d}",
                entity_ids=[ENTITY],
                feature=FEATURE,
                value=0.0,
                timestamp=stamp,
                domain=Domain.ATLAS,
            )
            for index, stamp in enumerate(stamps)
        ],
        attack_intervals=[
            LabelledInterval(start=stamp, end=stamp, label="attack")
            for stamp, label in zip(stamps, labels, strict=True)
            if label == 1.0
        ],
    )
    detections = [
        Detection(timestamp=stamp, score=1.0, confidence=float(confidence))
        for stamp, confidence in zip(stamps, confidences, strict=True)
    ]
    return expected_calibration_error(detections, dataset, bins)


# ------------------------------------------------------------------------------------------------
# The metric bridge itself
# ------------------------------------------------------------------------------------------------


def test_true_probabilities_score_a_near_zero_calibration_error() -> None:
    """Sanity-check the bridge: perfect confidences must score ~0 on the PART 2 metric.

    Without this, a later assertion that a calibrator achieves a low ECE would not distinguish a
    good calibrator from a broken measurement.
    """
    scores, labels = staircase()
    truth = scores / 10.0

    assert _ece_of(truth, labels) == pytest.approx(0.0, abs=1e-12)


# ------------------------------------------------------------------------------------------------
# Both calibrators
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("calibrator", CALIBRATORS, ids=CALIBRATOR_IDS)
def test_calibrated_values_are_probabilities(
    calibrator: IsotonicCalibrator | PlattCalibrator,
) -> None:
    scores, labels = staircase()

    calibrated = calibrator.fit(scores, labels).calibrate(scores)

    assert calibrated.shape == scores.shape
    assert numpy.all(calibrated >= 0.0)
    assert numpy.all(calibrated <= 1.0)


@pytest.mark.parametrize("calibrator", CALIBRATORS, ids=CALIBRATOR_IDS)
def test_calibration_is_monotonic_non_decreasing(
    calibrator: IsotonicCalibrator | PlattCalibrator,
) -> None:
    """A higher anomaly score may never map to a lower probability.

    Both calibrators promise this — Platt because a logistic with a non-negative coefficient is
    monotone, isotonic because monotonicity is the constraint it is fitted under. It matters
    because the harness thresholds on the raw score: if calibration could invert the ordering, a
    higher operating point could admit less confident alerts.
    """
    scores, labels = staircase()
    fitted = calibrator.fit(scores, labels)

    probe = numpy.linspace(-5.0, 15.0, 500)
    calibrated = fitted.calibrate(probe)

    assert numpy.all(numpy.diff(calibrated) >= -1e-12)


@pytest.mark.parametrize("calibrator", CALIBRATORS, ids=CALIBRATOR_IDS)
def test_calibration_is_deterministic(calibrator: IsotonicCalibrator | PlattCalibrator) -> None:
    """Same inputs, same calibrator — Constitution §3.7 for the calibration layer."""
    scores, labels = staircase()

    assert calibrator.fit(scores, labels) == calibrator.fit(scores, labels)


@pytest.mark.parametrize("calibrator", CALIBRATORS, ids=CALIBRATOR_IDS)
def test_fitted_calibrator_round_trips_as_json(
    calibrator: IsotonicCalibrator | PlattCalibrator,
) -> None:
    """A fitted calibrator is stored parameters, not a pickled estimator.

    This is what lets a calibrated confidence be reproduced from the record rather than by
    re-running a fit, and it is why the fitted types hold plain floats.
    """
    scores, labels = staircase()
    fitted = calibrator.fit(scores, labels)

    restored = type(fitted).model_validate_json(fitted.model_dump_json())
    assert restored == fitted
    assert numpy.allclose(restored.calibrate(scores), fitted.calibrate(scores))


@pytest.mark.parametrize("calibrator", CALIBRATORS, ids=CALIBRATOR_IDS)
def test_fitted_calibrators_satisfy_the_protocol(
    calibrator: IsotonicCalibrator | PlattCalibrator,
) -> None:
    scores, labels = staircase()

    assert isinstance(calibrator.fit(scores, labels), FittedCalibrator)


# ------------------------------------------------------------------------------------------------
# Isotonic specifically
# ------------------------------------------------------------------------------------------------


def test_isotonic_recovers_an_exact_staircase() -> None:
    """The headline correctness property: an exactly-calibratable input is exactly calibrated."""
    scores, labels = staircase()

    calibrated = IsotonicCalibrator().fit(scores, labels).calibrate(scores)

    assert numpy.allclose(calibrated, scores / 10.0)
    assert _ece_of(calibrated, labels) == pytest.approx(0.0, abs=1e-12)


def test_isotonic_matches_sklearns_own_prediction() -> None:
    """Lock the reimplementation to the library it claims to reproduce.

    `FittedIsotonicCalibrator` stores the fitted thresholds and interpolates them with
    ``numpy.interp`` rather than holding a live estimator, so that it stays a frozen, serialisable
    value. That is only legitimate while it agrees with sklearn exactly, including outside the
    fitted range where ``out_of_bounds="clip"`` applies — hence the probe extends well past both
    ends of the training scores.
    """
    from sklearn.isotonic import IsotonicRegression

    scores, labels = staircase()
    reference = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0).fit(scores, labels)
    probe = numpy.linspace(-20.0, 40.0, 1000)

    ours = IsotonicCalibrator().fit(scores, labels).calibrate(probe)

    assert numpy.allclose(ours, reference.predict(probe), atol=1e-12)


def test_isotonic_clips_outside_the_fitted_range() -> None:
    scores, labels = staircase()
    fitted = IsotonicCalibrator().fit(scores, labels)

    below = fitted.calibrate(numpy.asarray([-1000.0]))
    above = fitted.calibrate(numpy.asarray([1000.0]))

    assert below[0] == pytest.approx(fitted.calibrate(numpy.asarray([0.0]))[0])
    assert above[0] == pytest.approx(fitted.calibrate(numpy.asarray([9.0]))[0])


# ------------------------------------------------------------------------------------------------
# Platt specifically
# ------------------------------------------------------------------------------------------------


def test_platt_is_a_logistic_of_the_score() -> None:
    """Platt is two numbers and a sigmoid; check it really is that function."""
    scores, labels = staircase()
    fitted = PlattCalibrator().fit(scores, labels)

    probe = numpy.linspace(-5.0, 15.0, 200)
    expected = 1.0 / (1.0 + numpy.exp(-(fitted.coefficient * probe + fitted.intercept)))

    assert numpy.allclose(fitted.calibrate(probe), expected)


# ------------------------------------------------------------------------------------------------
# Refusals — a degenerate calibrator is worse than no calibrator
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("calibrator", CALIBRATORS, ids=CALIBRATOR_IDS)
def test_fit_refuses_single_class_labels(calibrator: IsotonicCalibrator | PlattCalibrator) -> None:
    """Both refuse, and isotonic is the reason this test exists.

    A logistic regression raises on its own when shown one class. Isotonic does not — it happily
    returns a calibrator that answers the same constant to everything, which is a *perfectly
    calibrated and entirely useless* function that would sail through an ECE check. Refusing here
    is what stops a split with no attacks in it from producing a number that looks like a win.
    """
    scores = numpy.linspace(0.0, 10.0, 50)

    with pytest.raises(ValueError, match="both classes"):
        calibrator.fit(scores, numpy.zeros(50))

    with pytest.raises(ValueError, match="both classes"):
        calibrator.fit(scores, numpy.ones(50))


@pytest.mark.parametrize("calibrator", CALIBRATORS, ids=CALIBRATOR_IDS)
def test_fit_refuses_empty_input(calibrator: IsotonicCalibrator | PlattCalibrator) -> None:
    with pytest.raises(ValueError, match="no scores"):
        calibrator.fit(numpy.asarray([]), numpy.asarray([]))


@pytest.mark.parametrize("calibrator", CALIBRATORS, ids=CALIBRATOR_IDS)
def test_fit_refuses_mismatched_lengths(calibrator: IsotonicCalibrator | PlattCalibrator) -> None:
    with pytest.raises(ValueError, match="same length"):
        calibrator.fit(numpy.asarray([1.0, 2.0, 3.0]), numpy.asarray([0.0, 1.0]))


@pytest.mark.parametrize("calibrator", CALIBRATORS, ids=CALIBRATOR_IDS)
def test_fit_refuses_non_binary_labels(calibrator: IsotonicCalibrator | PlattCalibrator) -> None:
    with pytest.raises(ValueError, match="0 or 1"):
        calibrator.fit(numpy.asarray([1.0, 2.0, 3.0]), numpy.asarray([0.0, 1.0, 0.5]))


@pytest.mark.parametrize("calibrator", CALIBRATORS, ids=CALIBRATOR_IDS)
def test_fit_refuses_non_finite_scores(calibrator: IsotonicCalibrator | PlattCalibrator) -> None:
    with pytest.raises(ValueError, match="finite"):
        calibrator.fit(numpy.asarray([1.0, numpy.inf, 3.0]), numpy.asarray([0.0, 1.0, 0.0]))


# ------------------------------------------------------------------------------------------------
# scores_and_labels_from
# ------------------------------------------------------------------------------------------------


def observations(values: list[float]) -> list[Observation]:
    return [
        Observation(
            id=f"obs_{index:012d}",
            entity_ids=[ENTITY],
            feature=FEATURE,
            value=value,
            timestamp=T0 + timedelta(minutes=index),
            domain=Domain.ATLAS,
        )
        for index, value in enumerate(values)
    ]


def test_scores_and_labels_come_from_the_model_and_the_ground_truth() -> None:
    """One row per candidate: its magnitude, and whether ground truth calls that instant attack."""
    training = observations([10.0, 14.0] * 8)  # mean 12, stddev 2
    fitted = GaussianBaseline(min_samples=4).fit(training)

    scoring = observations([12.0, 30.0, 12.0, 30.0])
    dataset = Dataset(
        name="fixture",
        domain=Domain.ATLAS,
        observations=scoring,
        attack_intervals=[
            LabelledInterval(start=scoring[1].timestamp, end=scoring[1].timestamp, label="attack")
        ],
    )

    scores, labels = scores_and_labels_from(fitted, dataset)

    assert len(scores) == len(labels)
    assert set(numpy.unique(labels)) <= {0.0, 1.0}
    assert labels.sum() == 1.0, "exactly one candidate falls inside the labelled window"
    # The two value-30 observations are 9 stddevs out; the value-12 ones sit on the mean and never
    # reach emit_k, so they are not candidates at all.
    assert numpy.all(scores > 3.0)


def test_scores_and_labels_are_empty_when_the_model_emits_nothing() -> None:
    fitted = GaussianBaseline(min_samples=4).fit(observations([10.0, 14.0] * 8))
    quiet = observations([12.0, 12.0, 12.0])
    dataset = Dataset(name="fixture", domain=Domain.ATLAS, observations=quiet)

    scores, labels = scores_and_labels_from(fitted, dataset)

    assert scores.size == 0
    assert labels.size == 0


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


def test_scores_and_labels_refuse_a_deviation_they_cannot_label() -> None:
    """A label that cannot be traced back to a measurement is refused, not guessed.

    `ModelDetector` and `CalibratedModelDetector` refuse the same thing for the same reason
    (Constitution §3.2). Here the stakes are slightly different: an unlabellable candidate would
    silently become a *training row* for the calibrator, so the damage would be baked into the
    mapping rather than showing up in one detection.
    """
    rogue = OrphanEmittingModel(name="orphan", expected_ranges={}, feature_ranges={}, emit_k=1.0)
    dataset = Dataset(name="fixture", domain=Domain.ATLAS, observations=observations([12.0]))

    with pytest.raises(ValueError, match="unknown observation"):
        scores_and_labels_from(rogue, dataset)


# ------------------------------------------------------------------------------------------------
# The shared range guard
# ------------------------------------------------------------------------------------------------
#
# `FittedCalibrator` is a structural Protocol: it guarantees a `calibrate` method exists, not that
# the method returns probabilities. Three call sites needed the same guard, so it lives here once.


class _RogueCalibrator(BaseModel):
    """A calibrator that satisfies the protocol and returns something that is not a probability."""

    model_config = ConfigDict(frozen=True)

    name: str = "rogue"
    output: tuple[float, ...]

    def calibrate(
        self, scores: numpy.typing.NDArray[numpy.float64]
    ) -> numpy.typing.NDArray[numpy.float64]:
        returned: numpy.typing.NDArray[numpy.float64] = numpy.asarray(self.output, dtype=float)
        return returned


def test_calibrated_probabilities_returns_one_probability_per_score() -> None:
    fitted = FittedPlattCalibrator(coefficient=1.0, intercept=0.0)

    probabilities = calibrated_probabilities(fitted, [0.0, 1.0, 2.0])

    assert len(probabilities) == 3
    assert all(0.0 <= probability <= 1.0 for probability in probabilities)
    assert probabilities == sorted(probabilities)


def test_calibrated_probabilities_of_nothing_is_nothing() -> None:
    """An empty batch must not reach the calibrator at all: sklearn-fitted maps refuse one."""
    fitted = FittedPlattCalibrator(coefficient=1.0, intercept=0.0)

    assert calibrated_probabilities(fitted, []) == []


def test_calibrated_probabilities_refuses_the_wrong_number_of_values() -> None:
    with pytest.raises(ValueError, match="returned"):
        calibrated_probabilities(_RogueCalibrator(output=(0.5,)), [1.0, 2.0])


@pytest.mark.parametrize("value", [-0.5, 1.5])
def test_calibrated_probabilities_refuses_a_value_that_is_not_a_probability(value: float) -> None:
    with pytest.raises(ValueError, match=r"outside \[0, 1\]"):
        calibrated_probabilities(_RogueCalibrator(output=(0.5, value)), [1.0, 2.0])


def test_calibrated_probabilities_absorbs_floating_point_slack_without_masking_a_fault() -> None:
    """A probability a float-step outside the interval is clipped; a real excursion still raises."""
    slack = calibrated_probabilities(_RogueCalibrator(output=(1.0 + 1e-12,)), [1.0])

    assert slack == [1.0]


def test_candidates_in_unscored_time_are_neither_positive_nor_negative_examples() -> None:
    training = observations([10.0, 14.0] * 8)  # mean 12, stddev 2
    fitted = GaussianBaseline(min_samples=4).fit(training)

    scoring = observations([30.0, 30.0, 30.0])
    dataset = Dataset(
        name="fixture",
        domain=Domain.ATLAS,
        observations=scoring,
        attack_intervals=[
            LabelledInterval(start=scoring[0].timestamp, end=scoring[0].timestamp, label="attack")
        ],
        unscored_intervals=[
            LabelledInterval(start=scoring[1].timestamp, end=scoring[1].timestamp, label="unscored")
        ],
    )

    scores, labels = scores_and_labels_from(fitted, dataset)

    # Three candidates; the unscored one is dropped, leaving one positive and one negative.
    assert len(scores) == 2
    assert labels.tolist() == [1.0, 0.0]

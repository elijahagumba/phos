"""Tests for the one-class normal-score calibrator (ADR 0083).

Fits on attack-free scores alone. The map is the empirical CDF of those scores — a monotone
extremity weight under the normal distribution, **not** P(attack | score). Constitution §3.3 forbids
claiming the latter without labelled positives; ADR 0083 authorises the former with that honesty.
"""

from datetime import UTC, datetime, timedelta

import numpy
import pytest

from phos.eval import Dataset, LabelledInterval
from phos.models import GaussianBaseline
from phos.ontology import Domain, Observation
from phos.reasoning.calibration import (
    FittedCalibrator,
    FittedNormalScoreCalibrator,
    NormalScoreCalibrator,
    calibrated_probabilities,
    normal_scores_from,
)
from phos.reasoning.splits import DegenerateSplitError, attack_free_fit_calib_split

T0 = datetime(2026, 7, 29, 12, 0, tzinfo=UTC)
ENTITY = "ent_00000000000a"
FEATURE = "flow_rate"


def _normal_scores(n: int = 200, seed: int = 11) -> numpy.ndarray:
    """Deterministic draw of non-negative magnitudes resembling band-width units."""
    rng = numpy.random.default_rng(seed)
    return numpy.abs(rng.normal(loc=1.0, scale=0.5, size=n))


def test_normal_score_fit_needs_no_labels() -> None:
    scores = _normal_scores()
    fitted = NormalScoreCalibrator(seed=11).fit(scores)
    assert isinstance(fitted, FittedCalibrator)
    assert fitted.name == "normal-score-cdf"
    assert fitted.weights_are_attack_probabilities is False


def test_normal_score_values_are_probabilities() -> None:
    fitted = NormalScoreCalibrator().fit(_normal_scores())
    probe = numpy.linspace(0.0, 5.0, 50)
    calibrated = fitted.calibrate(probe)
    assert calibrated.shape == probe.shape
    assert numpy.all(calibrated >= 0.0)
    assert numpy.all(calibrated <= 1.0)


def test_normal_score_is_monotonic_non_decreasing() -> None:
    fitted = NormalScoreCalibrator().fit(_normal_scores())
    probe = numpy.linspace(-1.0, 10.0, 500)
    calibrated = fitted.calibrate(probe)
    assert numpy.all(numpy.diff(calibrated) >= -1e-12)


def test_normal_score_is_deterministic_and_json_round_trips() -> None:
    scores = _normal_scores()
    a = NormalScoreCalibrator(seed=11).fit(scores)
    b = NormalScoreCalibrator(seed=11).fit(scores)
    assert a == b
    restored = FittedNormalScoreCalibrator.model_validate_json(a.model_dump_json())
    assert restored == a
    assert numpy.allclose(restored.calibrate(scores), a.calibrate(scores))


def test_empirical_cdf_matches_hand_computation() -> None:
    """Lock the definition: weight(m) = #{normal ≤ m} / n."""
    scores = numpy.asarray([1.0, 2.0, 2.0, 4.0], dtype=float)
    fitted = NormalScoreCalibrator().fit(scores)
    probe = numpy.asarray([0.5, 1.0, 2.0, 3.0, 4.0, 10.0], dtype=float)
    expected = numpy.asarray([0.0, 0.25, 0.75, 0.75, 1.0, 1.0], dtype=float)
    assert numpy.allclose(fitted.calibrate(probe), expected)


def test_fit_refuses_empty_or_non_finite() -> None:
    with pytest.raises(ValueError, match="no scores"):
        NormalScoreCalibrator().fit(numpy.asarray([], dtype=float))
    with pytest.raises(ValueError, match="finite"):
        NormalScoreCalibrator().fit(numpy.asarray([1.0, numpy.nan], dtype=float))


def test_calibrated_probabilities_accepts_normal_score_calibrator() -> None:
    fitted = NormalScoreCalibrator().fit(_normal_scores())
    weights = calibrated_probabilities(fitted, [0.1, 1.0, 5.0])
    assert len(weights) == 3
    assert all(0.0 <= w <= 1.0 for w in weights)


def test_attack_free_fit_calib_split_is_time_ordered_and_disjoint() -> None:
    stamps = [T0 + timedelta(minutes=i) for i in range(100)]
    observations = [
        Observation(
            id=f"obs_{i:012d}",
            entity_ids=[ENTITY],
            feature=FEATURE,
            value=float(i),
            timestamp=stamp,
            domain=Domain.ATLAS,
        )
        for i, stamp in enumerate(stamps)
    ]
    dataset = Dataset(
        name="attack-free-fixture",
        domain=Domain.ATLAS,
        observations=observations,
        attack_intervals=[],
    )
    fit, calib = attack_free_fit_calib_split(dataset, calib_fraction=0.2)
    assert len(fit.observations) == 80
    assert len(calib.observations) == 20
    assert fit.observations[-1].timestamp < calib.observations[0].timestamp
    assert {o.id for o in fit.observations}.isdisjoint({o.id for o in calib.observations})
    assert not fit.attack_intervals and not calib.attack_intervals


def test_attack_free_fit_calib_split_refuses_attacks() -> None:
    observations = [
        Observation(
            id="obs_000000000001",
            entity_ids=[ENTITY],
            feature=FEATURE,
            value=1.0,
            timestamp=T0,
            domain=Domain.ATLAS,
        ),
        Observation(
            id="obs_000000000002",
            entity_ids=[ENTITY],
            feature=FEATURE,
            value=2.0,
            timestamp=T0 + timedelta(minutes=1),
            domain=Domain.ATLAS,
        ),
    ]
    dataset = Dataset(
        name="poisoned",
        domain=Domain.ATLAS,
        observations=observations,
        attack_intervals=[LabelledInterval(start=T0, end=T0, label="attack")],
    )
    with pytest.raises(DegenerateSplitError, match="attack-free"):
        attack_free_fit_calib_split(dataset, calib_fraction=0.5)


def test_normal_scores_from_ignores_labels() -> None:
    """Signal for the one-class fit comes from magnitudes alone on an attack-free slice."""
    stamps = [T0 + timedelta(minutes=i) for i in range(40)]
    observations = [
        Observation(
            id=f"obs_{i:012d}",
            entity_ids=[ENTITY],
            feature=FEATURE,
            value=10.0 if i < 20 else 100.0,
            timestamp=stamp,
            domain=Domain.ATLAS,
        )
        for i, stamp in enumerate(stamps)
    ]
    train = Dataset(
        name="train",
        domain=Domain.ATLAS,
        observations=observations[:20],
        attack_intervals=[],
    )
    calib = Dataset(
        name="calib",
        domain=Domain.ATLAS,
        observations=observations[20:],
        attack_intervals=[],
    )
    fitted = GaussianBaseline().fit(train.observations)
    scores = normal_scores_from(fitted, calib)
    assert scores.size > 0
    assert numpy.all(numpy.isfinite(scores))

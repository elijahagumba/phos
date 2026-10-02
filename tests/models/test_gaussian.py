"""Tests for the Gaussian baseline: does a z-score mean what it says it means."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from phos.models.base import MAX_MAGNITUDE
from phos.models.gaussian import GaussianBaseline, GaussianFittedModel
from phos.ontology import Deviation, Domain, Observation

T0 = datetime(2026, 7, 28, 9, 0, tzinfo=UTC)
ENTITY = "ent_00000000000a"
FEATURE = "flow_rate"

# Alternating 8 and 12: mean exactly 10, population stddev exactly 2. Eight points, which is the
# default min_samples, so every number below is checkable by hand.
#   mean = (8+12)*4 / 8 = 10
#   variance = mean((8-10)^2, (12-10)^2, ...) = mean(4, 4, ...) = 4  ->  stddev = 2
TRAINING_VALUES = [8.0, 12.0, 8.0, 12.0, 8.0, 12.0, 8.0, 12.0]


def observation(index: int, value: float, feature: str = FEATURE) -> Observation:
    return Observation(
        id=f"obs_{index:012d}",
        entity_ids=[ENTITY],
        feature=feature,
        value=value,
        timestamp=T0 + timedelta(minutes=index),
        domain=Domain.ATLAS,
    )


def training(values: list[float] | None = None) -> list[Observation]:
    return [observation(index, value) for index, value in enumerate(values or TRAINING_VALUES)]


# --------------------------------------------------------------------------------------------
# What it learns
# --------------------------------------------------------------------------------------------


def test_it_learns_the_mean_and_standard_deviation() -> None:
    fitted = GaussianBaseline().fit(training())
    learned = fitted.expected_ranges[(ENTITY, FEATURE)]

    assert learned.mean == 10.0
    assert learned.stddev == 2.0


def test_the_band_is_the_mean_plus_or_minus_band_k_sigma() -> None:
    fitted = GaussianBaseline().fit(training())
    learned = fitted.expected_ranges[(ENTITY, FEATURE)]

    # 10 +/- 3 * 2
    assert learned.low == 4.0
    assert learned.high == 16.0


def test_band_k_widens_the_reported_band() -> None:
    fitted = GaussianBaseline(band_k=1.0).fit(training())
    learned = fitted.expected_ranges[(ENTITY, FEATURE)]

    assert (learned.low, learned.high) == (8.0, 12.0)


def test_the_learned_range_names_its_entity_and_feature() -> None:
    fitted = GaussianBaseline().fit(training())
    learned = fitted.expected_ranges[(ENTITY, FEATURE)]

    assert learned.entity_id == ENTITY
    assert learned.feature == FEATURE


def test_fit_produces_a_gaussian_fitted_model() -> None:
    assert isinstance(GaussianBaseline().fit(training()), GaussianFittedModel)


# --------------------------------------------------------------------------------------------
# How it scores
# --------------------------------------------------------------------------------------------


def test_a_value_at_three_sigma_scores_three_and_is_emitted() -> None:
    fitted = GaussianBaseline().fit(training())
    # mean 10 + 3 * stddev 2 = 16
    deviations = fitted.score([observation(100, 16.0)])

    assert len(deviations) == 1
    assert deviations[0].magnitude == pytest.approx(3.0)


def test_a_value_at_the_mean_emits_nothing() -> None:
    fitted = GaussianBaseline().fit(training())

    assert fitted.score([observation(100, 10.0)]) == []


def test_magnitude_is_unsigned_so_both_directions_score_alike() -> None:
    fitted = GaussianBaseline().fit(training())
    above = fitted.score([observation(100, 16.0)])[0]
    below = fitted.score([observation(101, 4.0)])[0]

    assert above.magnitude == pytest.approx(below.magnitude)


def test_scoring_is_order_independent() -> None:
    fitted = GaussianBaseline().fit(training())
    scored = [observation(100, 16.0), observation(101, 20.0), observation(102, 4.0)]

    forwards = {item.observation_id: item.magnitude for item in fitted.score(scored)}
    backwards = {
        item.observation_id: item.magnitude for item in fitted.score(list(reversed(scored)))
    }

    assert forwards == backwards


def test_each_deviation_carries_the_range_that_judged_it() -> None:
    fitted = GaussianBaseline().fit(training())
    judged = fitted.score([observation(100, 20.0)])[0]

    # Traceability: the conclusion is reconstructable from what is stored on it.
    assert judged.expected.mean == 10.0
    assert judged.expected.stddev == 2.0
    assert judged.magnitude == pytest.approx(abs(20.0 - 10.0) / 2.0)


# --------------------------------------------------------------------------------------------
# The constant-feature edge, and serialisation
# --------------------------------------------------------------------------------------------


def test_a_perfectly_constant_feature_makes_any_departure_maximal() -> None:
    fitted = GaussianBaseline().fit(training([5.0] * 8))
    judged = fitted.score([observation(100, 5.001)])[0]

    # zscore returns infinity here; the model clamps so the magnitude stays finite and storable.
    assert judged.magnitude == MAX_MAGNITUDE


def test_a_constant_feature_still_emits_nothing_at_its_own_value() -> None:
    fitted = GaussianBaseline().fit(training([5.0] * 8))

    assert fitted.score([observation(100, 5.0)]) == []


def test_a_clamped_deviation_still_round_trips_through_json() -> None:
    fitted = GaussianBaseline().fit(training([5.0] * 8))
    judged = fitted.score([observation(100, 99.0)])[0]

    assert Deviation.model_validate_json(judged.model_dump_json()) == judged


def test_an_ordinary_deviation_round_trips_through_json() -> None:
    fitted = GaussianBaseline().fit(training())
    judged = fitted.score([observation(100, 20.0)])[0]

    assert Deviation.model_validate_json(judged.model_dump_json()) == judged


# --------------------------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------------------------


def test_the_model_is_frozen() -> None:
    with pytest.raises(ValidationError):
        GaussianBaseline().band_k = 5.0  # type: ignore[misc]


def test_the_default_name_identifies_the_model() -> None:
    assert GaussianBaseline().name == "gaussian"
    assert GaussianBaseline().fit(training()).name == "gaussian"

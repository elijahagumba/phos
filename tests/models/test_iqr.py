"""Tests for the IQR baseline, including the robustness it buys over the Gaussian one."""

from datetime import UTC, datetime, timedelta

import pytest

from phos.models.base import MAX_MAGNITUDE
from phos.models.gaussian import GaussianBaseline
from phos.models.iqr import IqrBaseline, IqrFittedModel
from phos.ontology import Deviation, Domain, Observation

T0 = datetime(2026, 7, 28, 9, 0, tzinfo=UTC)
ENTITY = "ent_00000000000a"
FEATURE = "flow_rate"

# Nine evenly spaced values. numpy's linear interpolation puts Q1 at index 2 and Q3 at index 6:
#   Q1 = 3, Q3 = 7, IQR = 4
#   fence at k=1.5: [3 - 6, 7 + 6] = [-3, 13]
CLEAN_VALUES = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0]

# Twelve well-behaved readings around 10, plus two absurd ones. This is what a real capture
# window looks like when something hiccupped during collection.
CONTAMINATED_VALUES = [9.0, 10.0, 11.0] * 4 + [1000.0, 1000.0]


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


# --------------------------------------------------------------------------------------------
# What it learns
# --------------------------------------------------------------------------------------------


def test_it_learns_tukeys_fence() -> None:
    fitted = IqrBaseline().fit(series(CLEAN_VALUES))
    learned = fitted.expected_ranges[(ENTITY, FEATURE)]

    assert (learned.low, learned.high) == (-3.0, 13.0)


def test_band_k_scales_the_fence() -> None:
    fitted = IqrBaseline(band_k=0.0).fit(series(CLEAN_VALUES))
    learned = fitted.expected_ranges[(ENTITY, FEATURE)]

    # With no multiplier the fence collapses onto the quartiles themselves.
    assert (learned.low, learned.high) == (3.0, 7.0)


def test_it_still_records_the_mean_and_stddev_for_other_consumers() -> None:
    fitted = IqrBaseline().fit(series(CLEAN_VALUES))
    learned = fitted.expected_ranges[(ENTITY, FEATURE)]

    # ExpectedRange is one shared type; these fields are populated even though the fence
    # neither uses nor depends on them.
    assert learned.mean == 5.0
    assert learned.stddev == pytest.approx(2.581988897)


def test_fit_produces_an_iqr_fitted_model() -> None:
    assert isinstance(IqrBaseline().fit(series(CLEAN_VALUES)), IqrFittedModel)


# --------------------------------------------------------------------------------------------
# How it scores
# --------------------------------------------------------------------------------------------


def test_a_value_inside_the_fence_scores_zero_and_emits_nothing() -> None:
    fitted = IqrBaseline().fit(series(CLEAN_VALUES))

    assert fitted.score([observation(100, 12.0)]) == []


def test_a_value_beyond_the_fence_scores_its_overshoot_in_iqrs() -> None:
    fitted = IqrBaseline().fit(series(CLEAN_VALUES))
    # fence high 13, IQR 4, so 17 overshoots by 4 -> exactly one IQR.
    judged = fitted.score([observation(100, 17.0)])[0]

    assert judged.magnitude == pytest.approx(1.0)


def test_the_lower_fence_scores_symmetrically() -> None:
    fitted = IqrBaseline().fit(series(CLEAN_VALUES))
    # fence low -3, so -7 overshoots by 4 -> one IQR.
    judged = fitted.score([observation(100, -7.0)])[0]

    assert judged.magnitude == pytest.approx(1.0)


def test_a_value_exactly_on_the_fence_is_still_normal() -> None:
    fitted = IqrBaseline().fit(series(CLEAN_VALUES))

    # ExpectedRange bounds are inclusive, so the fence itself is inside normal.
    assert fitted.score([observation(100, 13.0)]) == []


def test_scoring_is_order_independent() -> None:
    fitted = IqrBaseline().fit(series(CLEAN_VALUES))
    scored = [observation(100, 17.0), observation(101, 25.0), observation(102, -7.0)]

    forwards = {item.observation_id: item.magnitude for item in fitted.score(scored)}
    backwards = {
        item.observation_id: item.magnitude for item in fitted.score(list(reversed(scored)))
    }

    assert forwards == backwards


def test_deviations_round_trip_through_json() -> None:
    fitted = IqrBaseline().fit(series(CLEAN_VALUES))
    judged = fitted.score([observation(100, 40.0)])[0]

    assert Deviation.model_validate_json(judged.model_dump_json()) == judged


# --------------------------------------------------------------------------------------------
# Robustness — the reason this model exists alongside the Gaussian one
# --------------------------------------------------------------------------------------------


def test_the_fence_barely_moves_when_training_data_is_contaminated() -> None:
    clean = IqrBaseline().fit(series([9.0, 10.0, 11.0] * 4))
    contaminated = IqrBaseline().fit(series(CONTAMINATED_VALUES))

    clean_range = clean.expected_ranges[(ENTITY, FEATURE)]
    dirty_range = contaminated.expected_ranges[(ENTITY, FEATURE)]

    assert dirty_range.high - dirty_range.low < 2.0 * (clean_range.high - clean_range.low)


def test_the_iqr_band_is_dramatically_tighter_than_the_gaussian_one_on_dirty_data() -> None:
    observations = series(CONTAMINATED_VALUES)
    gaussian = GaussianBaseline().fit(observations).expected_ranges[(ENTITY, FEATURE)]
    iqr = IqrBaseline().fit(observations).expected_ranges[(ENTITY, FEATURE)]

    gaussian_width = gaussian.high - gaussian.low
    iqr_width = iqr.high - iqr.low

    # Two readings of 1000 drag the Gaussian mean to ~151 and its stddev to ~346, so its
    # three-sigma band spans roughly 2000 units. The quartiles hardly notice: the fence spans
    # about 7. That difference is the whole argument for keeping both models.
    assert iqr_width < gaussian_width / 50.0


def test_a_real_departure_survives_contaminated_training_only_under_the_iqr_model() -> None:
    observations = series(CONTAMINATED_VALUES)
    departure = [observation(100, 20.0)]

    assert IqrBaseline().fit(observations).score(departure)
    # The Gaussian band swallowed it whole: 20 is well under one contaminated sigma from a mean
    # that no longer describes anything real.
    assert GaussianBaseline().fit(observations).score(departure) == []


# --------------------------------------------------------------------------------------------
# The constant-feature edge
# --------------------------------------------------------------------------------------------


def test_a_perfectly_constant_feature_makes_any_departure_maximal() -> None:
    fitted = IqrBaseline().fit(series([5.0] * 9))
    judged = fitted.score([observation(100, 5.001)])[0]

    # Quartiles all coincide, so the fence has zero width and admits no departure at all.
    assert judged.magnitude == MAX_MAGNITUDE


def test_a_constant_feature_still_emits_nothing_at_its_own_value() -> None:
    fitted = IqrBaseline().fit(series([5.0] * 9))

    assert fitted.score([observation(100, 5.0)]) == []


# --------------------------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------------------------


def test_the_default_fence_multiplier_is_tukeys() -> None:
    assert IqrBaseline().band_k == 1.5


def test_the_default_name_identifies_the_model() -> None:
    assert IqrBaseline().name == "iqr"

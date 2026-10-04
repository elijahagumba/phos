"""Tests for the empirical command baseline: the band is the observed distribution.

A Gaussian three-sigma band can exclude a value that occurs often enough to be ordinary, because
the mean and the standard deviation do not know the value is a pile. These tests pin the
replacement: the same nominal tail, read off the sample with ``inverted_cdf``, magnitude zero
inside that band, a z-score outside it, and the maximum magnitude when the fit has no spread.
The tail is the Gaussian claim. It is not fitted to a false-alarm count.
"""

import math
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from phos.models.base import MAX_MAGNITUDE
from phos.models.empirical import (
    EmpiricalBaseline,
    EmpiricalFittedModel,
    one_sided_gaussian_tail,
)
from phos.models.gaussian import GaussianBaseline
from phos.models.iqr import IqrBaseline
from phos.ontology import Deviation, Domain, Observation

T0 = datetime(2026, 7, 28, 9, 0, tzinfo=UTC)
ENTITY = "ent_00000000000a"
FEATURE = "command_interval_mean_ms"

# Alternating 8 and 12: mean exactly 10, population stddev exactly 2. Eight points is the
# default min_samples. With only eight points a 0.135% tail cannot resolve inside the sample,
# so the empirical band is the sample itself: 8 to 12.
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


def test_the_tail_is_the_gaussian_three_sigma_claim() -> None:
    # Φ-bar(3), inherited from band_k=3. Conventionally written 0.00135. Not searched.
    claimed = 0.5 * math.erfc(3.0 / math.sqrt(2.0))
    assert one_sided_gaussian_tail(3.0) == pytest.approx(claimed)
    assert one_sided_gaussian_tail(3.0) == pytest.approx(0.00135, abs=1e-5)
    assert EmpiricalBaseline().band_k == 3.0


def test_a_wider_nominal_band_uses_a_thinner_tail() -> None:
    # Values 0, 1, ..., 999. Hand-checked against numpy inverted_cdf at each tail:
    #   band_k=3 → low 1, high 998
    #   band_k=1 → low 158, high 841
    values = [float(index) for index in range(1000)]
    wide = EmpiricalBaseline().fit(training(values)).expected_ranges[(ENTITY, FEATURE)]
    narrow = EmpiricalBaseline(band_k=1.0).fit(training(values)).expected_ranges[(ENTITY, FEATURE)]

    assert (wide.low, wide.high) == (1.0, 998.0)
    assert (narrow.low, narrow.high) == (158.0, 841.0)


def test_a_discrete_pile_stays_inside_the_band() -> None:
    # 1,000 windows at 10 s and 10 at 15 s. The pile is about 1% of the sample, more than the
    # 0.135% tail, so inverted_cdf lands on 15. mean + 3 standard deviations does not.
    values = [10.0] * 1000 + [15.0] * 10
    learned = EmpiricalBaseline().fit(training(values)).expected_ranges[(ENTITY, FEATURE)]

    assert learned.low == 10.0
    assert learned.high == 15.0
    assert learned.mean == pytest.approx(10.04950495049505)
    assert learned.contains(15.0)


def test_the_same_pile_is_outside_the_gaussian_band() -> None:
    values = [10.0] * 1000 + [15.0] * 10
    observations = training(values)
    empirical = EmpiricalBaseline().fit(observations)
    gaussian = GaussianBaseline().fit(observations)

    assert empirical.score([observation(2000, 15.0)]) == []
    gaussian_hit = gaussian.score([observation(2000, 15.0)])
    assert len(gaussian_hit) == 1
    assert gaussian_hit[0].magnitude > 3.0


def test_iqr_collapses_on_a_near_constant_count_and_this_model_does_not() -> None:
    # Nearly always exactly 6, with a few 5s. Tukey's quartiles are both 6, so the fence has
    # no width and a 5 that occurred in the fit is maximally anomalous. Do not use IQR here.
    values = [5.0] * 10 + [6.0] * 1000
    observations = training(values)
    empirical = EmpiricalBaseline().fit(observations)
    iqr = IqrBaseline().fit(observations)
    learned = iqr.expected_ranges[(ENTITY, FEATURE)]

    assert learned.low == learned.high == 6.0
    assert iqr.score([observation(2000, 5.0)])[0].magnitude == MAX_MAGNITUDE
    assert empirical.score([observation(2000, 5.0)]) == []


def test_fit_produces_an_empirical_fitted_model() -> None:
    assert isinstance(EmpiricalBaseline().fit(training()), EmpiricalFittedModel)


def test_the_default_name_identifies_the_model() -> None:
    assert EmpiricalBaseline().name == "empirical"
    assert EmpiricalBaseline().fit(training()).name == "empirical"


def test_a_value_outside_the_band_scores_its_absolute_z() -> None:
    fitted = EmpiricalBaseline().fit(training())
    # Band is [8, 12]. 16 is (16 - 10) / 2 = 3 standard deviations out.
    deviations = fitted.score([observation(100, 16.0)])

    assert len(deviations) == 1
    assert deviations[0].magnitude == pytest.approx(3.0)


def test_a_value_inside_the_band_emits_nothing_even_at_one_sigma() -> None:
    fitted = EmpiricalBaseline().fit(training())
    # 8 is inside [8, 12]. The Gaussian z-score is 1, which the Gaussian model would emit.
    assert fitted.score([observation(100, 8.0)]) == []
    assert GaussianBaseline().fit(training()).score([observation(100, 8.0)])[0].magnitude == (
        pytest.approx(1.0)
    )


def test_magnitude_is_unsigned_so_both_directions_score_alike() -> None:
    fitted = EmpiricalBaseline().fit(training())
    above = fitted.score([observation(100, 16.0)])[0]
    below = fitted.score([observation(101, 4.0)])[0]

    assert above.magnitude == pytest.approx(below.magnitude)


def test_scoring_is_order_independent() -> None:
    fitted = EmpiricalBaseline().fit(training())
    scored = [observation(100, 16.0), observation(101, 20.0), observation(102, 4.0)]

    forwards = {item.observation_id: item.magnitude for item in fitted.score(scored)}
    backwards = {
        item.observation_id: item.magnitude for item in fitted.score(list(reversed(scored)))
    }

    assert forwards == backwards


def test_each_deviation_carries_the_range_that_judged_it() -> None:
    fitted = EmpiricalBaseline().fit(training())
    judged = fitted.score([observation(100, 20.0)])[0]

    assert judged.expected.mean == 10.0
    assert judged.expected.stddev == 2.0
    assert judged.expected.low == 8.0
    assert judged.expected.high == 12.0
    assert judged.magnitude == pytest.approx(abs(20.0 - 10.0) / 2.0)


def test_a_perfectly_constant_feature_makes_any_departure_maximal() -> None:
    fitted = EmpiricalBaseline().fit(training([5.0] * 8))
    judged = fitted.score([observation(100, 5.001)])[0]

    assert judged.magnitude == MAX_MAGNITUDE


def test_a_constant_feature_still_emits_nothing_at_its_own_value() -> None:
    fitted = EmpiricalBaseline().fit(training([5.0] * 8))

    assert fitted.score([observation(100, 5.0)]) == []


def test_a_clamped_deviation_still_round_trips_through_json() -> None:
    fitted = EmpiricalBaseline().fit(training([5.0] * 8))
    judged = fitted.score([observation(100, 99.0)])[0]

    assert Deviation.model_validate_json(judged.model_dump_json()) == judged


def test_an_unseen_feature_scores_nothing() -> None:
    fitted = EmpiricalBaseline().fit(training())

    assert fitted.score([observation(100, 99.0, feature="never_seen")]) == []


def test_the_model_is_frozen() -> None:
    with pytest.raises(ValidationError):
        EmpiricalBaseline().band_k = 1.0  # type: ignore[misc]

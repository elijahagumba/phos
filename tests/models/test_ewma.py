"""Tests for the EWMA baseline: a moving idea of normal, and the order-dependence that implies."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from phos.models.ewma import EwmaBaseline, EwmaFittedModel, ewma_update
from phos.ontology import Deviation, Domain, Observation

T0 = datetime(2026, 7, 28, 9, 0, tzinfo=UTC)
ENTITY = "ent_00000000000a"
OTHER_ENTITY = "ent_00000000000b"
FEATURE = "flow_rate"


def observation(
    index: int, value: float, *, entity: str = ENTITY, feature: str = FEATURE
) -> Observation:
    return Observation(
        id=f"obs_{entity[-1]}{index:011d}",
        entity_ids=[entity],
        feature=feature,
        value=value,
        timestamp=T0 + timedelta(minutes=index),
        domain=Domain.ATLAS,
    )


def series(values: list[float], *, start: int = 0, entity: str = ENTITY) -> list[Observation]:
    return [observation(start + index, value, entity=entity) for index, value in enumerate(values)]


# A stationary signal with just enough jitter that the exponentially weighted variance is
# non-zero, so magnitudes stay finite and the "few deviations" claim is about the model rather
# than about a degenerate fixture.
STATIONARY = [10.0, 10.4] * 20


# --------------------------------------------------------------------------------------------
# The recursion itself
# --------------------------------------------------------------------------------------------


def test_ewma_update_matches_the_hand_computed_step() -> None:
    # residual = 20 - 10 = 10
    # ema      = 10 + 0.5 * 10                 = 15
    # variance = (1 - 0.5) * (0 + 0.5 * 10^2)  = 25
    assert ewma_update(10.0, 0.0, 20.0, 0.5) == (15.0, 25.0)


def test_ewma_update_leaves_a_perfectly_predicted_value_alone() -> None:
    assert ewma_update(10.0, 0.0, 10.0, 0.3) == (10.0, 0.0)


def test_ewma_variance_is_never_negative() -> None:
    ema, variance = 10.0, 4.0
    for value in [12.0, 3.0, 40.0, -8.0, 10.0]:
        ema, variance = ewma_update(ema, variance, value, 0.3)
        assert variance >= 0.0


# --------------------------------------------------------------------------------------------
# What it learns
# --------------------------------------------------------------------------------------------


def test_fitting_ends_in_the_hand_computed_state() -> None:
    # alpha 0.5, seeded at the first value:
    #   start            ema = 10, var = 0
    #   value 10         residual 0  -> ema = 10, var = 0.5 * (0 + 0.5 * 0)  = 0
    #   value 14         residual 4  -> ema = 12, var = 0.5 * (0 + 0.5 * 16) = 4
    fitted = EwmaBaseline(alpha=0.5, min_samples=3).fit(series([10.0, 10.0, 14.0]))
    learned = fitted.expected_ranges[(ENTITY, FEATURE)]

    assert learned.mean == 12.0
    assert learned.stddev == 2.0
    # 12 +/- 3 * 2
    assert (learned.low, learned.high) == (6.0, 18.0)


def test_fit_produces_an_ewma_fitted_model_carrying_its_hyperparameters() -> None:
    fitted = EwmaBaseline(alpha=0.4, band_k=2.0).fit(series(STATIONARY))

    assert isinstance(fitted, EwmaFittedModel)
    assert fitted.alpha == 0.4
    assert fitted.band_k == 2.0


def test_fitting_is_order_independent_because_it_sorts_by_timestamp() -> None:
    observations = series([10.0, 10.0, 14.0])
    forwards = EwmaBaseline(alpha=0.5, min_samples=3).fit(observations)
    shuffled = EwmaBaseline(alpha=0.5, min_samples=3).fit([observations[i] for i in (2, 0, 1)])

    key = (ENTITY, FEATURE)
    assert forwards.expected_ranges[key].mean == shuffled.expected_ranges[key].mean


# --------------------------------------------------------------------------------------------
# How it scores
# --------------------------------------------------------------------------------------------


def test_the_first_scored_value_is_judged_against_the_fitted_state() -> None:
    fitted = EwmaBaseline(alpha=0.5, min_samples=3).fit(series([10.0, 10.0, 14.0]))
    # Fitted state is ema 12, stddev 2, so 18 sits exactly three of them out.
    judged = fitted.score([observation(100, 18.0)])[0]

    assert judged.magnitude == pytest.approx(3.0)
    assert judged.expected.mean == 12.0


def test_a_stationary_signal_produces_no_deviations() -> None:
    model = EwmaBaseline(emit_k=3.0)
    fitted = model.fit(series(STATIONARY))

    assert fitted.score(series(STATIONARY, start=100)) == []


def test_a_step_change_is_flagged() -> None:
    model = EwmaBaseline(emit_k=3.0)
    fitted = model.fit(series(STATIONARY))
    stepped = series([*STATIONARY[:10], *([50.0] * 10)], start=100)

    deviations = fitted.score(stepped)

    assert deviations
    # The step is what got flagged, not the quiet run that preceded it.
    assert all(deviation.timestamp >= T0 + timedelta(minutes=110) for deviation in deviations)


def test_the_baseline_follows_the_step_so_the_surprise_decays() -> None:
    fitted = EwmaBaseline(emit_k=0.0).fit(series(STATIONARY))
    deviations = fitted.score(series([50.0] * 6, start=100))

    # An EWMA absorbs a sustained shift; that is the documented trade for tracking drift.
    assert deviations[0].magnitude > deviations[-1].magnitude


def test_scoring_is_order_dependent() -> None:
    fitted = EwmaBaseline(emit_k=0.0).fit(series(STATIONARY))
    scored = series([10.0, 50.0, 10.0, 50.0, 10.0, 50.0], start=100)

    ordered = {item.observation_id: item.magnitude for item in fitted.score(scored)}
    shuffled = {
        item.observation_id: item.magnitude for item in fitted.score(list(reversed(scored)))
    }

    # Same observations, different sequence, genuinely different answers. A static model would
    # give identical maps here; this one must not.
    assert ordered != shuffled


def test_the_expected_range_moves_as_it_scores() -> None:
    fitted = EwmaBaseline(emit_k=0.0).fit(series(STATIONARY))
    deviations = fitted.score(series([50.0, 50.0], start=100))

    assert deviations[0].expected.mean != deviations[1].expected.mean


def test_the_expected_window_extends_as_observations_are_absorbed() -> None:
    fitted = EwmaBaseline(emit_k=0.0).fit(series(STATIONARY))
    first, second = fitted.score(series([50.0, 50.0], start=100))

    # The second range truthfully reports having seen one more observation than the first.
    assert second.expected.learned_from_window[1] > first.expected.learned_from_window[1]


def test_out_of_order_scoring_never_inverts_the_learned_window() -> None:
    fitted = EwmaBaseline(emit_k=0.0).fit(series(STATIONARY))
    backwards = list(reversed(series([50.0] * 5, start=100)))

    for deviation in fitted.score(backwards):
        start, end = deviation.expected.learned_from_window
        assert start <= end


def test_each_key_evolves_independently() -> None:
    fitted = EwmaBaseline(emit_k=0.0).fit(series(STATIONARY))
    interleaved = [
        observation(100, 50.0, entity=ENTITY),
        observation(101, 10.0, entity=OTHER_ENTITY),
        observation(102, 50.0, entity=ENTITY),
    ]

    scored = fitted.score(interleaved)
    # The second entity falls back to the feature baseline and is unaffected by the first
    # entity's excursion, which would be impossible if they shared live state.
    assert scored[1].expected.mean == pytest.approx(scored[0].expected.mean, abs=0.5)
    assert scored[2].expected.mean > scored[0].expected.mean


def test_an_unseen_feature_emits_nothing() -> None:
    fitted = EwmaBaseline(emit_k=0.0).fit(series(STATIONARY))

    assert fitted.score([observation(100, 999.0, feature="spindle_speed")]) == []


def test_an_unseen_entity_is_seeded_from_the_feature_baseline() -> None:
    fitted = EwmaBaseline(emit_k=3.0).fit(series(STATIONARY))

    deviations = fitted.score([observation(100, 500.0, entity=OTHER_ENTITY)])

    assert len(deviations) == 1
    # Once seeded it tracks this entity alone, so the range is attributed to it.
    assert deviations[0].expected.entity_id == OTHER_ENTITY


def test_deviations_round_trip_through_json() -> None:
    fitted = EwmaBaseline(emit_k=0.0).fit(series(STATIONARY))
    judged = fitted.score([observation(100, 50.0)])[0]

    assert Deviation.model_validate_json(judged.model_dump_json()) == judged


# --------------------------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("alpha", [0.0, -0.1, 1.1])
def test_alpha_must_lie_in_zero_to_one(alpha: float) -> None:
    with pytest.raises(ValidationError):
        EwmaBaseline(alpha=alpha)


def test_alpha_of_one_is_allowed_and_forgets_everything_but_the_last_value() -> None:
    fitted = EwmaBaseline(alpha=1.0, min_samples=3).fit(series([10.0, 10.0, 14.0]))

    assert fitted.expected_ranges[(ENTITY, FEATURE)].mean == 14.0


def test_the_default_name_identifies_the_model() -> None:
    assert EwmaBaseline().name == "ewma"

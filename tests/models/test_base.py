"""Tests for the shared model machinery: keying, fallback, min_samples and honest splits."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from phos.eval.datasets import Dataset, LabelledInterval
from phos.models.base import (
    FEATURE_LEVEL_ENTITY_ID,
    MAX_MAGNITUDE,
    SplitPolicy,
    clamp_magnitude,
    model_key,
    train_test_split,
)
from phos.models.gaussian import GaussianBaseline
from phos.ontology import Domain, Observation

T0 = datetime(2026, 7, 28, 9, 0, tzinfo=UTC)

ENTITY_A = "ent_00000000000a"
ENTITY_B = "ent_00000000000b"


def observation(
    index: int,
    value: float,
    *,
    entity: str = ENTITY_A,
    feature: str = "flow_rate",
    minutes: int | None = None,
) -> Observation:
    offset = index if minutes is None else minutes
    return Observation(
        id=f"obs_{entity[-1]}{feature[:3]}{index:08d}",
        entity_ids=[entity],
        feature=feature,
        value=value,
        timestamp=T0 + timedelta(minutes=offset),
        domain=Domain.ATLAS,
    )


def series(
    values: list[float], *, entity: str = ENTITY_A, feature: str = "flow_rate", start: int = 0
) -> list[Observation]:
    return [
        observation(start + index, value, entity=entity, feature=feature, minutes=start + index)
        for index, value in enumerate(values)
    ]


# The Gaussian fixture below has hand-computed statistics: alternating 8 and 12 gives a mean of
# exactly 10 and a population standard deviation of exactly 2, so every derived number in these
# tests can be checked by eye.
FLAT_VALUES = [8.0, 12.0, 8.0, 12.0, 8.0, 12.0, 8.0, 12.0]


# --------------------------------------------------------------------------------------------
# model_key
# --------------------------------------------------------------------------------------------


def test_model_key_pairs_entity_and_feature() -> None:
    assert model_key(observation(0, 1.0)) == (ENTITY_A, "flow_rate")


def test_model_key_attributes_a_relationship_to_its_first_entity() -> None:
    relationship = Observation(
        id="obs_000000000001",
        entity_ids=[ENTITY_A, ENTITY_B],
        feature="bytes_between",
        value=1.0,
        timestamp=T0,
        domain=Domain.SENTIEL,
    )
    assert model_key(relationship) == (ENTITY_A, "bytes_between")


# --------------------------------------------------------------------------------------------
# clamp_magnitude
# --------------------------------------------------------------------------------------------


def test_clamp_magnitude_takes_the_absolute_value() -> None:
    assert clamp_magnitude(-2.5) == 2.5


def test_clamp_magnitude_passes_ordinary_scores_through() -> None:
    assert clamp_magnitude(3.0) == 3.0


def test_clamp_magnitude_bounds_infinity() -> None:
    # ExpectedRange.zscore returns infinity for any departure from a constant feature. An
    # infinite magnitude would serialise to JSON null and fail to round-trip.
    assert clamp_magnitude(float("inf")) == MAX_MAGNITUDE
    assert clamp_magnitude(float("-inf")) == MAX_MAGNITUDE


# --------------------------------------------------------------------------------------------
# SplitPolicy
# --------------------------------------------------------------------------------------------


def test_split_policy_defaults_to_half() -> None:
    assert SplitPolicy().train_fraction == 0.5


@pytest.mark.parametrize("fraction", [0.0, -0.1, 1.1])
def test_split_policy_rejects_a_fraction_outside_zero_to_one(fraction: float) -> None:
    with pytest.raises(ValidationError):
        SplitPolicy(train_fraction=fraction)


def test_split_policy_is_frozen() -> None:
    with pytest.raises(ValidationError):
        SplitPolicy().train_fraction = 0.9  # type: ignore[misc]


# --------------------------------------------------------------------------------------------
# train_test_split — the honesty of every number that follows
# --------------------------------------------------------------------------------------------


def labelled(observations: list[Observation], intervals: list[LabelledInterval]) -> Dataset:
    return Dataset(
        name="corpus",
        domain=Domain.ATLAS,
        observations=observations,
        attack_intervals=intervals,
        source_note="fixture",
    )


def test_split_puts_the_first_half_in_training_when_attacks_are_late() -> None:
    observations = series([float(index) for index in range(100)])
    attack = LabelledInterval(
        start=T0 + timedelta(minutes=80), end=T0 + timedelta(minutes=90), label="attack"
    )
    train, test = train_test_split(
        labelled(observations, [attack]), SplitPolicy(train_fraction=0.5)
    )

    # 100 samples one minute apart span 99 minutes; half of that is minute 49.5, so the last
    # training sample is minute 49.
    assert len(train.observations) == 50
    assert len(test.observations) == 50
    assert train.observations[-1].timestamp == T0 + timedelta(minutes=49)


def test_split_never_places_an_attack_in_the_training_set() -> None:
    observations = series([float(index) for index in range(100)])
    # An attack at minute 20 sits well inside the half the fraction alone would have taken.
    attack = LabelledInterval(
        start=T0 + timedelta(minutes=20), end=T0 + timedelta(minutes=30), label="attack"
    )
    train, _ = train_test_split(labelled(observations, [attack]), SplitPolicy(train_fraction=0.5))

    assert train.attack_intervals == []
    assert all(not attack.contains(item.timestamp) for item in train.observations)
    assert train.observations[-1].timestamp < attack.start
    assert len(train.observations) == 20


def test_split_excludes_an_observation_stamped_exactly_at_an_attack_start() -> None:
    observations = series([float(index) for index in range(40)])
    attack = LabelledInterval(
        start=T0 + timedelta(minutes=10), end=T0 + timedelta(minutes=12), label="attack"
    )
    train, _ = train_test_split(labelled(observations, [attack]), SplitPolicy(train_fraction=1.0))

    # Labelled intervals are inclusive at both ends, so minute 10 is inside the attack.
    assert len(train.observations) == 10
    assert train.observations[-1].timestamp == T0 + timedelta(minutes=9)


def test_split_gives_the_test_set_the_attacks() -> None:
    observations = series([float(index) for index in range(100)])
    attack = LabelledInterval(
        start=T0 + timedelta(minutes=80), end=T0 + timedelta(minutes=90), label="attack"
    )
    _, test = train_test_split(labelled(observations, [attack]), SplitPolicy(train_fraction=0.5))

    assert test.attack_intervals == [attack]


def test_split_drops_intervals_that_miss_the_test_window() -> None:
    observations = series([float(index) for index in range(100)])
    # A label from before the capture even opened. It intersects neither half.
    stale = LabelledInterval(
        start=T0 - timedelta(minutes=10), end=T0 - timedelta(minutes=5), label="attack"
    )
    live = LabelledInterval(
        start=T0 + timedelta(minutes=70), end=T0 + timedelta(minutes=75), label="attack"
    )
    train, test = train_test_split(
        labelled(observations, [stale, live]), SplitPolicy(train_fraction=0.5)
    )

    assert test.attack_intervals == [live]
    # And the consequence worth being explicit about: because the earliest label precedes the
    # first observation, the attack-free prefix rule leaves no training data at all.
    assert train.observations == []


def test_split_can_leave_the_test_half_empty() -> None:
    observations = series([float(index) for index in range(20)])
    train, test = train_test_split(labelled(observations, []), SplitPolicy(train_fraction=1.0))

    assert len(train.observations) == 20
    assert test.observations == []
    assert test.attack_intervals == []


def test_split_yields_no_training_data_when_the_corpus_opens_under_attack() -> None:
    observations = series([float(index) for index in range(20)])
    attack = LabelledInterval(start=T0, end=T0 + timedelta(minutes=5), label="attack")
    train, test = train_test_split(
        labelled(observations, [attack]), SplitPolicy(train_fraction=0.5)
    )

    # A fact about the corpus, reported rather than worked around.
    assert train.observations == []
    assert len(test.observations) == 20


def test_split_handles_a_corpus_with_no_attacks() -> None:
    observations = series([float(index) for index in range(100)])
    train, test = train_test_split(labelled(observations, []), SplitPolicy(train_fraction=0.5))

    assert len(train.observations) == 50
    assert len(test.observations) == 50
    assert test.attack_intervals == []


def test_split_handles_an_empty_corpus() -> None:
    train, test = train_test_split(labelled([], []), SplitPolicy(train_fraction=0.5))

    assert train.observations == []
    assert test.observations == []
    assert test.attack_intervals == []


def test_split_records_itself_in_the_names_and_provenance() -> None:
    train, test = train_test_split(
        labelled(series([float(index) for index in range(20)]), []), SplitPolicy(train_fraction=0.5)
    )

    assert train.name == "corpus-train"
    assert test.name == "corpus-test"
    assert "train_fraction=0.5" in train.source_note
    assert "fixture" in train.source_note


def test_split_is_deterministic() -> None:
    dataset = labelled(
        series([float(index) for index in range(100)]),
        [
            LabelledInterval(
                start=T0 + timedelta(minutes=80), end=T0 + timedelta(minutes=90), label="attack"
            )
        ],
    )
    first = train_test_split(dataset, SplitPolicy(train_fraction=0.5))
    second = train_test_split(dataset, SplitPolicy(train_fraction=0.5))

    assert first[0].model_dump() == second[0].model_dump()
    assert first[1].model_dump() == second[1].model_dump()


def test_split_halves_partition_the_corpus() -> None:
    observations = series([float(index) for index in range(63)])
    train, test = train_test_split(labelled(observations, []), SplitPolicy(train_fraction=0.5))

    assert [item.id for item in train.observations] + [item.id for item in test.observations] == [
        item.id for item in observations
    ]


# --------------------------------------------------------------------------------------------
# Fit / score separation
# --------------------------------------------------------------------------------------------


def test_an_unfitted_model_cannot_score() -> None:
    # The guarantee is structural, not a runtime check: there is no score to call.
    model = GaussianBaseline()
    assert not hasattr(model, "score")


def test_fit_returns_something_that_can_score() -> None:
    fitted = GaussianBaseline().fit(series(FLAT_VALUES))

    assert fitted.expected_ranges[(ENTITY_A, "flow_rate")].mean == 10.0
    assert callable(fitted.score)


def test_fit_carries_the_model_name_and_emit_threshold_onto_the_fitted_model() -> None:
    fitted = GaussianBaseline(emit_k=2.0).fit(series(FLAT_VALUES))

    assert fitted.name == "gaussian"
    assert fitted.emit_k == 2.0


def test_fit_on_nothing_learns_nothing_and_scores_nothing() -> None:
    fitted = GaussianBaseline().fit([])

    assert fitted.expected_ranges == {}
    assert fitted.feature_ranges == {}
    assert fitted.score(series(FLAT_VALUES)) == []


# --------------------------------------------------------------------------------------------
# Keying, min_samples and the fallback ladder
# --------------------------------------------------------------------------------------------


def test_a_key_below_min_samples_forms_no_baseline() -> None:
    # Seven points, one short of the default of eight.
    fitted = GaussianBaseline().fit(series(FLAT_VALUES[:7]))

    assert fitted.expected_ranges == {}
    assert fitted.feature_ranges == {}


def test_min_samples_is_configurable() -> None:
    fitted = GaussianBaseline(min_samples=4).fit(series(FLAT_VALUES[:4]))

    assert (ENTITY_A, "flow_rate") in fitted.expected_ranges


def test_a_feature_level_baseline_aggregates_across_entities() -> None:
    observations = series(FLAT_VALUES, entity=ENTITY_A) + series(
        FLAT_VALUES, entity=ENTITY_B, start=100
    )
    fitted = GaussianBaseline().fit(observations)

    assert set(fitted.expected_ranges) == {(ENTITY_A, "flow_rate"), (ENTITY_B, "flow_rate")}
    assert fitted.feature_ranges["flow_rate"].mean == 10.0
    assert fitted.feature_ranges["flow_rate"].entity_id == FEATURE_LEVEL_ENTITY_ID


def test_an_unseen_entity_falls_back_to_the_feature_level_baseline() -> None:
    fitted = GaussianBaseline().fit(series(FLAT_VALUES, entity=ENTITY_A))
    # ENTITY_B was never trained on, but flow_rate was. A value at +5 sigma must still be caught.
    deviations = fitted.score([observation(0, 20.0, entity=ENTITY_B)])

    assert len(deviations) == 1
    assert deviations[0].magnitude == pytest.approx(5.0)
    # The stored evidence says which baseline judged it: the cross-entity one.
    assert deviations[0].expected.entity_id == FEATURE_LEVEL_ENTITY_ID


def test_an_entirely_unseen_feature_emits_nothing() -> None:
    fitted = GaussianBaseline().fit(series(FLAT_VALUES, feature="flow_rate"))
    # Unknown is not the same as anomalous. Emitting here would manufacture evidence.
    assert fitted.score([observation(0, 999.0, feature="spindle_speed")]) == []


def test_an_exact_key_is_preferred_over_the_feature_level_fallback() -> None:
    quiet = series(FLAT_VALUES, entity=ENTITY_A)
    loud = series([100.0, 140.0] * 4, entity=ENTITY_B, start=100)
    fitted = GaussianBaseline().fit(quiet + loud)

    judged = fitted.score([observation(0, 20.0, entity=ENTITY_A)])[0]

    assert judged.expected.entity_id == ENTITY_A
    assert judged.expected.mean == 10.0


def test_a_key_below_min_samples_still_falls_back_to_its_feature() -> None:
    plenty = series(FLAT_VALUES, entity=ENTITY_A)
    # Two points for ENTITY_B: too few for its own baseline, but they feed the feature level.
    scarce = series([9.0, 11.0], entity=ENTITY_B, start=100)
    fitted = GaussianBaseline().fit(plenty + scarce)

    assert (ENTITY_B, "flow_rate") not in fitted.expected_ranges
    judged = fitted.score([observation(0, 30.0, entity=ENTITY_B)])[0]
    assert judged.expected.entity_id == FEATURE_LEVEL_ENTITY_ID


# --------------------------------------------------------------------------------------------
# Learned window and ordering
# --------------------------------------------------------------------------------------------


def test_the_learned_window_spans_the_training_group() -> None:
    fitted = GaussianBaseline().fit(series(FLAT_VALUES))
    window = fitted.expected_ranges[(ENTITY_A, "flow_rate")].learned_from_window

    assert window == (T0, T0 + timedelta(minutes=7))


def test_fitting_is_order_independent() -> None:
    observations = series(FLAT_VALUES)
    forwards = GaussianBaseline().fit(observations)
    backwards = GaussianBaseline().fit(list(reversed(observations)))

    key = (ENTITY_A, "flow_rate")
    assert forwards.expected_ranges[key].model_dump() == backwards.expected_ranges[key].model_dump()


# --------------------------------------------------------------------------------------------
# Emission
# --------------------------------------------------------------------------------------------


def test_emit_k_of_zero_emits_a_candidate_for_every_scored_observation() -> None:
    fitted = GaussianBaseline(emit_k=0.0).fit(series(FLAT_VALUES))
    scored = series([10.0, 10.0, 10.0])

    assert len(fitted.score(scored)) == 3


def test_a_higher_emit_k_emits_strictly_fewer_candidates() -> None:
    training = series(FLAT_VALUES)
    scored = series([10.0, 12.0, 16.0, 22.0])

    dense = GaussianBaseline(emit_k=0.5).fit(training).score(scored)
    sparse = GaussianBaseline(emit_k=3.0).fit(training).score(scored)

    assert len(dense) > len(sparse)
    assert all(deviation.magnitude >= 3.0 for deviation in sparse)


def test_deviations_are_stamped_with_the_observation_time_not_the_wall_clock() -> None:
    fitted = GaussianBaseline().fit(series(FLAT_VALUES))
    scored = observation(0, 30.0, minutes=500)

    assert fitted.score([scored])[0].timestamp == scored.timestamp


def test_deviations_carry_the_observation_they_judged() -> None:
    fitted = GaussianBaseline().fit(series(FLAT_VALUES))
    scored = observation(0, 30.0)

    assert fitted.score([scored])[0].observation_id == scored.id

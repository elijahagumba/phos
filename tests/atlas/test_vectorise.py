"""Tests for vectorising: does a pile of scalars become the right matrix, and does it ever lie.

The second question matters more than the first. Assembling a matrix from per-``(entity, feature)``
scalars means deciding what to do when a signal has no reading at some timestamp, and the tempting
answer — put a zero there — fabricates a measurement that was never taken. Everything the joint
model later concludes would rest on it. So the missing-data policy gets more tests here than the
happy path does.
"""

from datetime import UTC, datetime, timedelta

import numpy
import pytest
from pydantic import ValidationError

from phos.atlas.vectorise import (
    NO_OBSERVATION,
    SignalSpace,
    VectorisePolicy,
    vectorise,
)
from phos.ontology import Domain, Observation

T0 = datetime(2026, 7, 31, 6, 0, tzinfo=UTC)
PUMP = "ent_00000000pump"
TANK = "ent_00000000tank"
FLOW = "flow_rate"
LEVEL = "tank_level"

PUMP_FLOW = (PUMP, FLOW)
TANK_LEVEL = (TANK, LEVEL)


def observation(
    row: int,
    entity: str,
    feature: str,
    value: float,
    *,
    identifier: str | None = None,
) -> Observation:
    return Observation(
        id=identifier or f"obs_r{row:04d}{entity[-4:]}{feature[:2]}",
        entity_ids=[entity],
        feature=feature,
        value=value,
        timestamp=T0 + timedelta(minutes=row),
        domain=Domain.ATLAS,
    )


def two_signal_rows(rows: int) -> list[Observation]:
    """Both signals present at every one of ``rows`` timestamps."""
    out: list[Observation] = []
    for row in range(rows):
        out.append(observation(row, PUMP, FLOW, 10.0 + row))
        out.append(observation(row, TANK, LEVEL, 100.0 - row))
    return out


# --------------------------------------------------------------------------------------------
# SignalSpace
# --------------------------------------------------------------------------------------------


def test_the_space_is_learned_from_the_observations() -> None:
    space = SignalSpace.from_observations(two_signal_rows(3))

    assert space.signals == (PUMP_FLOW, TANK_LEVEL)
    assert space.size == 2


def test_the_space_is_ordered_deterministically_whatever_the_input_order() -> None:
    forwards = SignalSpace.from_observations(two_signal_rows(3))
    backwards = SignalSpace.from_observations(list(reversed(two_signal_rows(3))))

    assert forwards.signals == backwards.signals


def test_a_signal_seen_many_times_appears_in_the_space_once() -> None:
    space = SignalSpace.from_observations(two_signal_rows(50))

    assert space.size == 2


def test_a_space_learned_from_nothing_is_empty() -> None:
    assert SignalSpace.from_observations([]).size == 0


def test_index_of_locates_a_signal_and_refuses_to_guess_at_an_unknown_one() -> None:
    space = SignalSpace.from_observations(two_signal_rows(3))

    assert space.index_of(PUMP_FLOW) == 0
    assert space.index_of(TANK_LEVEL) == 1
    assert space.index_of((PUMP, "pressure")) is None


def test_select_narrows_the_space_to_the_given_columns_in_order() -> None:
    space = SignalSpace.from_observations(two_signal_rows(3))

    assert space.select([1]).signals == (TANK_LEVEL,)
    assert space.select([]).signals == ()


def test_select_refuses_a_column_the_space_does_not_have() -> None:
    space = SignalSpace.from_observations(two_signal_rows(3))

    with pytest.raises(ValueError, match="column 7"):
        space.select([7])


def test_a_space_may_not_hold_the_same_signal_twice() -> None:
    with pytest.raises(ValidationError, match="appears more than once"):
        SignalSpace(signals=(PUMP_FLOW, PUMP_FLOW))


# --------------------------------------------------------------------------------------------
# Assembling the matrix
# --------------------------------------------------------------------------------------------


def test_observations_assemble_into_a_time_by_signal_matrix() -> None:
    observations = two_signal_rows(3)
    space = SignalSpace.from_observations(observations)

    series = vectorise(observations, space)

    assert series.matrix.shape == (3, 2)
    assert series.timestamps == (T0, T0 + timedelta(minutes=1), T0 + timedelta(minutes=2))
    numpy.testing.assert_array_equal(
        series.matrix,
        numpy.array([[10.0, 100.0], [11.0, 99.0], [12.0, 98.0]]),
    )


def test_a_shuffled_input_assembles_into_the_same_matrix() -> None:
    observations = two_signal_rows(4)
    space = SignalSpace.from_observations(observations)
    shuffled = [observations[index] for index in (5, 0, 7, 2, 1, 6, 3, 4)]

    numpy.testing.assert_array_equal(
        vectorise(shuffled, space).matrix, vectorise(observations, space).matrix
    )


def test_each_cell_records_which_observation_it_came_from() -> None:
    observations = two_signal_rows(3)
    space = SignalSpace.from_observations(observations)

    series = vectorise(observations, space)

    # Row 1, the pump's flow column: the observation whose value is 11.0.
    source = series.source_index[1, 0]
    assert source != NO_OBSERVATION
    assert observations[source].value == 11.0
    assert observations[source].entity_ids == [PUMP]
    assert observations[source].feature == FLOW


def test_a_signal_outside_the_space_is_ignored_rather_than_appended() -> None:
    observations = two_signal_rows(3)
    space = SignalSpace.from_observations(observations)
    intruder = [*observations, observation(1, PUMP, "pressure", 42.0)]

    series = vectorise(intruder, space)

    assert series.matrix.shape == (3, 2)
    assert 42.0 not in series.matrix


def test_vectorising_nothing_yields_an_empty_series_rather_than_an_error() -> None:
    space = SignalSpace.from_observations(two_signal_rows(3))

    series = vectorise([], space)

    assert series.matrix.shape == (0, 2)
    assert series.timestamps == ()
    assert series.n_rows == 0


def test_the_last_reading_wins_when_one_signal_is_measured_twice_at_one_instant() -> None:
    observations = [
        *two_signal_rows(1),
        observation(0, PUMP, FLOW, 999.0, identifier="obs_duplicate0"),
    ]
    space = SignalSpace.from_observations(observations)

    series = vectorise(observations, space)

    assert series.matrix[0, 0] == 999.0


# --------------------------------------------------------------------------------------------
# The missing-signal policy — the part that must never fabricate a reading
# --------------------------------------------------------------------------------------------


def test_a_gap_is_forward_filled_from_the_previous_row_not_from_zero() -> None:
    # Drop the tank's reading at row 1 only.
    observations = [
        o
        for o in two_signal_rows(3)
        if not (o.feature == LEVEL and o.timestamp == T0 + timedelta(minutes=1))
    ]
    space = SignalSpace(signals=(PUMP_FLOW, TANK_LEVEL))

    series = vectorise(observations, space, VectorisePolicy(forward_fill_rows=1))

    assert series.n_rows == 3
    # Row 1's tank level carries row 0's reading of 100.0. It is emphatically not 0.0.
    assert series.matrix[1, 1] == 100.0


def test_a_forward_filled_cell_is_not_credited_to_an_observation() -> None:
    observations = [
        o
        for o in two_signal_rows(3)
        if not (o.feature == LEVEL and o.timestamp == T0 + timedelta(minutes=1))
    ]
    space = SignalSpace(signals=(PUMP_FLOW, TANK_LEVEL))

    series = vectorise(observations, space, VectorisePolicy(forward_fill_rows=1))

    assert series.source_index[1, 1] == NO_OBSERVATION
    assert series.source_index[1, 0] != NO_OBSERVATION


def test_a_gap_wider_than_the_fill_limit_drops_the_timestamp() -> None:
    gapped = [
        o
        for o in two_signal_rows(4)
        if not (
            o.feature == LEVEL
            and o.timestamp in {T0 + timedelta(minutes=1), T0 + timedelta(minutes=2)}
        )
    ]
    space = SignalSpace(signals=(PUMP_FLOW, TANK_LEVEL))

    series = vectorise(gapped, space, VectorisePolicy(forward_fill_rows=1))

    # Row 1 is filled from row 0; row 2 is a bridge too far and is dropped whole.
    assert series.timestamps == (T0, T0 + timedelta(minutes=1), T0 + timedelta(minutes=3))
    assert series.dropped_timestamps == 1


def test_a_gap_with_no_earlier_reading_to_carry_drops_the_timestamp() -> None:
    late_starter = [o for o in two_signal_rows(3) if not (o.feature == LEVEL and o.timestamp == T0)]
    space = SignalSpace(signals=(PUMP_FLOW, TANK_LEVEL))

    series = vectorise(late_starter, space, VectorisePolicy(forward_fill_rows=1))

    assert series.timestamps == (T0 + timedelta(minutes=1), T0 + timedelta(minutes=2))
    assert series.dropped_timestamps == 1


def test_forward_fill_can_be_switched_off_entirely() -> None:
    gapped = [
        o
        for o in two_signal_rows(3)
        if not (o.feature == LEVEL and o.timestamp == T0 + timedelta(minutes=1))
    ]
    space = SignalSpace(signals=(PUMP_FLOW, TANK_LEVEL))

    series = vectorise(gapped, space, VectorisePolicy(forward_fill_rows=0))

    assert series.timestamps == (T0, T0 + timedelta(minutes=2))
    assert series.dropped_timestamps == 1


def test_a_gap_never_becomes_a_zero_however_wide_it_is() -> None:
    """The whole reason this module is isolated: a fabricated 0.0 is a fabricated measurement."""
    sparse = [
        o
        for o in two_signal_rows(6)
        if not (o.feature == LEVEL and o.timestamp > T0 + timedelta(minutes=1))
    ]
    space = SignalSpace(signals=(PUMP_FLOW, TANK_LEVEL))

    for fill in (0, 1, 3, 10):
        series = vectorise(sparse, space, VectorisePolicy(forward_fill_rows=fill))
        levels = series.matrix[:, 1]
        assert not numpy.any(levels == 0.0)
        # Every surviving level is one that was genuinely measured.
        assert set(levels.tolist()) <= {100.0, 99.0}


def test_a_negative_fill_limit_is_refused() -> None:
    with pytest.raises(ValidationError):
        VectorisePolicy(forward_fill_rows=-1)


def test_dropping_every_timestamp_yields_an_empty_matrix_of_the_right_width() -> None:
    space = SignalSpace(signals=(PUMP_FLOW, TANK_LEVEL))
    only_one_signal = [observation(row, PUMP, FLOW, 1.0) for row in range(4)]

    series = vectorise(only_one_signal, space, VectorisePolicy(forward_fill_rows=0))

    assert series.matrix.shape == (0, 2)
    assert series.dropped_timestamps == 4

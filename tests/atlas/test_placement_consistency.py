"""ADR 0398: the earliest threshold crossing places the alert, whatever saturates beside it."""

from __future__ import annotations

import numpy

from phos.atlas.consistency import (
    ONSET_FRACTION,
    ONSET_LEVEL,
    THRESHOLD,
    ConsistencyEvent,
    events,
)
from phos.atlas.placement_consistency import (
    RESULT_NAME,
    detect_with_placement,
    earliest_crossing_events,
)

# ----------------------------------------------------------------- the rule, by hand


def test_the_earliest_crossing_is_the_first_sample_the_group_can_point_at() -> None:
    """A lone weak episode places its alert where it first clears the threshold."""
    scores = numpy.zeros((400, 2), dtype=numpy.float32)
    scores[120:180, 0] = 1.5
    found = earliest_crossing_events(scores)
    assert len(found) == 1
    assert found[0].onset == 120
    assert found[0].column == 0
    assert found[0].score == 1.5


def test_a_saturated_member_no_longer_moves_a_weak_episode_later() -> None:
    """The ADR 0286 defect: the frozen rule skips the weak member and alerts at the strong one.

    Both members are in one group. The frozen rule takes the strong member as ``best``, pins
    ``level`` at its floor, and skips the weak member whose peak is below it. The new rule places
    the alert at the weak member's own crossing, which is earlier.
    """
    scores = numpy.zeros((400, 2), dtype=numpy.float32)
    scores[0:40, 1] = 1.5
    scores[20:200, 0] = 20.0

    frozen = events(scores)
    placed = earliest_crossing_events(scores)

    assert len(frozen) == 1
    assert len(placed) == 1
    assert frozen[0].onset > 0
    assert placed[0].onset == 0
    assert placed[0].column == 1
    assert placed[0].onset < frozen[0].onset


def test_the_group_score_is_still_its_strongest_peak() -> None:
    """Placement moves; strength does not. The budget ranks on this number."""
    scores = numpy.zeros((400, 2), dtype=numpy.float32)
    scores[0:40, 1] = 1.5
    scores[20:200, 0] = 20.0
    placed = earliest_crossing_events(scores)
    assert placed[0].score == 20.0
    assert placed[0].peak_column == 0


def test_the_rule_agrees_with_the_frozen_one_when_no_weak_member_is_skipped() -> None:
    """A group whose members all reach the level places the same alert either way."""
    scores = numpy.zeros((400, 1), dtype=numpy.float32)
    scores[100:200, 0] = 3.0
    frozen = events(scores)
    placed = earliest_crossing_events(scores)
    assert len(frozen) == len(placed) == 1
    assert placed[0].onset == frozen[0].onset == 100
    assert placed[0].column == frozen[0].column == 0


def test_a_member_that_only_clears_the_threshold_can_place_the_alert() -> None:
    """The bar an episode cleared to exist is the bar that lets it place the alert."""
    scores = numpy.zeros((400, 2), dtype=numpy.float32)
    scores[10:30, 1] = 1.05
    scores[100:300, 0] = 19.0
    placed = earliest_crossing_events(scores)
    assert len(placed) == 1
    assert placed[0].onset == 10
    assert placed[0].column == 1


def test_the_rule_is_stable_over_the_sample_rows_it_places() -> None:
    """A crossing is a real sample of the placed column, not an index into another column."""
    scores = numpy.zeros((400, 2), dtype=numpy.float32)
    scores[57:80, 1] = 1.4
    scores[60:300, 0] = 15.0
    placed = earliest_crossing_events(scores)
    assert placed[0].onset == 57
    assert float(scores[placed[0].onset, placed[0].column]) >= THRESHOLD


def test_two_members_crossing_at_the_same_row_keep_the_earlier_start_then_lower_column() -> None:
    """Ties are resolved deterministically, so the rule is reproducible."""
    scores = numpy.zeros((400, 2), dtype=numpy.float32)
    scores[50:90, 1] = 1.5
    scores[50:90, 0] = 1.5
    placed = earliest_crossing_events(scores)
    assert len(placed) == 1
    assert placed[0].onset == 50
    assert placed[0].column == 0


def test_an_empty_matrix_gives_no_events() -> None:
    """A quiet file draws nothing, and the rule does not invent a crossing."""
    assert earliest_crossing_events(numpy.zeros((50, 3), dtype=numpy.float32)) == []


def test_every_member_of_the_group_is_reported() -> None:
    """The members travel, so a caller can still read what the group was made of."""
    scores = numpy.zeros((400, 2), dtype=numpy.float32)
    scores[0:40, 1] = 1.5
    scores[20:200, 0] = 20.0
    placed = earliest_crossing_events(scores)
    assert len(placed[0].members) == 2
    assert {member[4] for member in placed[0].members} == {0, 1}


def test_the_events_are_returned_in_onset_order_like_the_frozen_ones() -> None:
    """Two separated departures give two events, ordered by where their alerts go."""
    scores = numpy.zeros((4000, 1), dtype=numpy.float32)
    scores[100:200, 0] = 4.0
    scores[3000:3100, 0] = 4.0
    placed = earliest_crossing_events(scores)
    assert [event.onset for event in placed] == [100, 3000]


# ----------------------------------------------------------------- the frozen engine is unmoved


def test_the_rule_returns_the_frozen_event_type() -> None:
    """`budget_alerts` takes these unchanged, so the type is the frozen one."""
    scores = numpy.zeros((400, 1), dtype=numpy.float32)
    scores[10:40, 0] = 2.5
    placed = earliest_crossing_events(scores)
    assert all(isinstance(event, ConsistencyEvent) for event in placed)


def test_the_onset_level_constants_are_read_not_restated() -> None:
    """The rule points at a threshold crossing; it never computes a level from the peak."""
    scores = numpy.zeros((400, 2), dtype=numpy.float32)
    scores[0:40, 1] = 1.5
    scores[20:200, 0] = 20.0
    placed = earliest_crossing_events(scores)
    assert placed[0].score != placed[0].onset
    assert max(ONSET_LEVEL, ONSET_FRACTION * placed[0].score) > THRESHOLD
    assert placed[0].onset == 0


def test_the_result_name_is_the_one_the_declaration_named() -> None:
    """A score carries its own name, as every detector in the programme does."""
    assert RESULT_NAME == "atlas-placement-consistency"


def test_scoring_a_file_with_the_rule_never_touches_the_frozen_alert_list() -> None:
    """One fit, two placements. The frozen engine's own alerts are bit-for-bit what they were."""
    from phos.atlas.consistency import TrainFile, budget_alerts, feature_scores, fit

    rows = 3000
    t = numpy.arange(rows, dtype=numpy.float64)
    train = numpy.column_stack(
        [
            numpy.sin(t / 31.0) + 0.01 * numpy.cos(t / 7.0),
            numpy.sin(t / 17.0 + 1.0) + 0.01 * numpy.cos(t / 5.0),
            numpy.sin(t / 53.0 + 2.0) + 0.01 * numpy.cos(t / 11.0),
        ]
    )
    model = fit([TrainFile(values=train, attack=numpy.zeros(rows, dtype=bool))])

    hostile = train.copy()
    hostile[1500:1700, 0] += 8.0
    before = events(feature_scores(model, hostile), windows=model.windows)
    detect_with_placement(model, hostile, t, windows=model.windows)
    after = events(feature_scores(model, hostile), windows=model.windows)

    assert [event.onset for event in before] == [event.onset for event in after]
    assert [event.column for event in before] == [event.column for event in after]
    assert [event.score for event in before] == [event.score for event in after]
    _ = budget_alerts(before, t, windows=model.windows)


def test_the_budget_still_caps_the_alerts_it_returns() -> None:
    """The rule is placement only; `budget_alerts` still holds the eight-a-shift ceiling."""
    from phos.atlas.consistency import ALERTS_PER_SHIFT, TrainFile, fit

    rows = 6000
    t = numpy.arange(rows, dtype=numpy.float64)
    train = numpy.column_stack([numpy.sin(t / 41.0), numpy.sin(t / 23.0 + 1.0)])
    model = fit([TrainFile(values=train, attack=numpy.zeros(rows, dtype=bool))])

    hostile = train.copy()
    for start in range(0, rows, 200):
        hostile[max(0, start - 1) : start + 1, 0] += 12.0
        hostile[max(0, start - 1) : start + 1, 1] += 12.0
    rows_out, _columns, _scores = detect_with_placement(model, hostile, t, windows=model.windows)
    assert len(rows_out) <= ALERTS_PER_SHIFT


# ----------------------------------------------------------------- refusal paths


def test_a_placement_with_no_members_is_refused() -> None:
    """A group is never empty from the rule's own grouping, but a direct call can pass one."""
    import pytest

    from phos.atlas.placement_consistency import _crossing

    with pytest.raises(ValueError, match="at least one member"):
        _crossing(numpy.zeros((10, 2), dtype=numpy.float32), (), THRESHOLD)


def test_a_matrix_that_does_not_match_the_time_axis_is_refused() -> None:
    """Scored rows and timestamps must agree, or the alert rows index the wrong samples."""
    import pytest

    from phos.atlas.consistency import TrainFile, fit

    rows = 400
    t = numpy.arange(rows, dtype=numpy.float64)
    train = numpy.column_stack([numpy.sin(t / 13.0), numpy.sin(t / 29.0)])
    model = fit([TrainFile(values=train, attack=numpy.zeros(rows, dtype=bool))])
    with pytest.raises(ValueError, match="scored rows but"):
        detect_with_placement(model, train, t[:-1], windows=model.windows)

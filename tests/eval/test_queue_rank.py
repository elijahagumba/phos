"""The A3 queue rank, on a hand-built shift."""

from datetime import UTC, datetime, timedelta

import pytest

from phos.eval.budget import OPERATOR_SHIFT
from phos.eval.queue_rank import AttackSpan, QueueAlert, rank_attacks, top_slots

_ORIGIN = datetime(2020, 1, 1, tzinfo=UTC)


def test_top_slots_round_up_and_a_queue_of_one_is_the_top_slot() -> None:
    assert top_slots(0) == 0
    assert top_slots(1) == 1
    assert top_slots(10) == 1
    assert top_slots(11) == 2
    for length in range(0, 101):
        assert top_slots(length) == (length + 9) // 10


def test_a_lone_true_alert_passes_and_a_lone_false_alert_fails() -> None:
    attack = _attack(hours=1, duration=1)
    true = rank_attacks((_alert(1, score=3.0),), (attack,), origin=_ORIGIN)
    false = rank_attacks((_alert(4, score=9.0),), (attack,), origin=_ORIGIN)
    assert true[0].passed is True
    assert true[0].rank == 1
    assert true[0].queue_length == 1
    assert true[0].top_slots == 1
    assert false[0].passed is False
    assert false[0].rank is None


def test_rank_nine_of_one_hundred_passes_and_rank_eleven_fails() -> None:
    passed = rank_attacks(_queue(true_at=9), (_attack(hours=0, duration=1),), origin=_ORIGIN)
    assert passed[0].rank == 9
    assert passed[0].queue_length == 100
    assert passed[0].top_slots == 10
    assert passed[0].passed is True
    failed = rank_attacks(_queue(true_at=11), (_attack(hours=0, duration=1),), origin=_ORIGIN)
    assert failed[0].rank == 11
    assert failed[0].passed is False


def test_ties_break_toward_the_earlier_timestamp_then_the_earlier_input() -> None:
    same_time = _ORIGIN + timedelta(hours=1)
    alerts = (
        QueueAlert(same_time, 5.0, 1),
        QueueAlert(same_time, 5.0, 0),
        QueueAlert(same_time - timedelta(minutes=1), 5.0, 2),
    )
    earlier = same_time - timedelta(minutes=1)
    attack = AttackSpan("file#0", earlier, earlier)
    ranked = rank_attacks(alerts, (attack,), origin=_ORIGIN)
    assert ranked[0].rank == 1
    later = AttackSpan("file#1", same_time, same_time)
    both = rank_attacks(alerts, (later,), origin=_ORIGIN)
    assert both[0].rank == 2


def test_an_alert_in_the_next_shift_does_not_count() -> None:
    attack = _attack(hours=7, duration=2)
    only_next = _alert(8.5, score=100.0)
    missed = rank_attacks((only_next,), (attack,), origin=_ORIGIN)
    assert missed[0].shift_index == 0
    assert missed[0].passed is False
    assert missed[0].rank is None
    in_shift = _alert(7.5, score=1.0)
    caught = rank_attacks((in_shift, only_next), (attack,), origin=_ORIGIN)
    assert caught[0].passed is True
    assert caught[0].queue_length == 1


def test_an_empty_shift_fails() -> None:
    attack = _attack(hours=1, duration=1)
    ranked = rank_attacks((), (attack,), origin=_ORIGIN)
    assert ranked[0].passed is False
    assert ranked[0].queue_length == 0
    assert ranked[0].top_slots == 0


def test_a_negative_queue_length_is_rejected() -> None:
    with pytest.raises(ValueError, match="negative"):
        top_slots(-1)


def test_the_shift_is_the_frozen_eight_hours() -> None:
    assert OPERATOR_SHIFT == timedelta(hours=8)


def _queue(true_at: int) -> tuple[QueueAlert, ...]:
    """100 alerts in one shift. Only position ``true_at`` (1-based) falls inside hour 0."""
    alerts: list[QueueAlert] = []
    for position in range(1, 101):
        inside = position == true_at
        alerts.append(_alert(0.5 if inside else 3, score=200 - position, order=position))
    return tuple(alerts)


def _alert(hours: float, *, score: float, order: int = 0) -> QueueAlert:
    return QueueAlert(_ORIGIN + timedelta(hours=hours), score, order)


def _attack(hours: float, duration: float) -> AttackSpan:
    start = _ORIGIN + timedelta(hours=hours)
    return AttackSpan("file#0", start, start + timedelta(hours=duration))

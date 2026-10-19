"""Where an attack's first true alert sits in its shift's full queue.

The queue is every alert in the shift, before any budget cut. Ties break the way
``recall_within_budget`` breaks them: higher score, then earlier timestamp, then
earlier input order. The top of a queue is ``ceil(10%)`` of its length, so a queue
of one alert has one passing slot. An attack with no alert in its own shift fails.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from phos.eval.budget import OPERATOR_SHIFT

__all__ = [
    "AttackRank",
    "AttackSpan",
    "QueueAlert",
    "rank_attacks",
    "top_slots",
]


@dataclass(frozen=True)
class QueueAlert:
    """One alert in the order the detector emitted it, before a budget cut.

    Attributes:
        timestamp: When the alert is shown.
        score: The detector's own score. Higher ranks earlier.
        input_order: Position in the detector's output. Earlier ranks earlier on a tie.
    """

    timestamp: datetime
    score: float
    input_order: int


@dataclass(frozen=True)
class AttackSpan:
    """One attack window on a single file's clock.

    Attributes:
        attack_id: Stable id, ``file#index`` in the callers that use the G1 windows.
        start: First timestamp of the attack, inclusive.
        end: Last timestamp of the attack, inclusive.
    """

    attack_id: str
    start: datetime
    end: datetime


@dataclass(frozen=True)
class AttackRank:
    """The rank of an attack's first true alert in its shift.

    Attributes:
        attack_id: The attack this row describes.
        passed: True when that rank is inside the top 10% of the shift's queue.
        rank: 1-based rank of the first true alert. ``None`` when the shift has none.
        queue_length: How many alerts are in the shift, before the budget cut.
        top_slots: How many leading ranks count as the top 10%.
        shift_index: The shift that contains the attack's start.
    """

    attack_id: str
    passed: bool
    rank: int | None
    queue_length: int
    top_slots: int
    shift_index: int


def top_slots(queue_length: int) -> int:
    """Return ``ceil(queue_length / 10)``.

    A queue of 1 has 1 slot. A queue of 10 has 1. A queue of 11 has 2. An empty
    queue has 0.

    Raises:
        ValueError: If ``queue_length`` is negative.
    """
    if queue_length < 0:
        raise ValueError(f"a queue length is never negative, got {queue_length}")
    return (queue_length + 9) // 10


def rank_attacks(
    alerts: Sequence[QueueAlert],
    attacks: Sequence[AttackSpan],
    *,
    origin: datetime,
    shift: timedelta = OPERATOR_SHIFT,
) -> tuple[AttackRank, ...]:
    """Rank each attack's first true alert in the shift that contains its start.

    Alerts are placed in half-open shifts ``[origin + k * shift, origin + (k + 1) * shift)``.
    An alert exactly on a boundary belongs to the later shift. Within a shift the
    queue is ordered by higher score, then earlier timestamp, then earlier
    ``input_order``. A true alert has its timestamp inside the attack, inclusive.
    The first true alert is the earliest of those in that ordered queue. The attack
    passes when its rank is at most :func:`top_slots` of that queue. Alerts in
    another shift do not count, including one that falls inside an attack which
    started in the previous shift.

    Args:
        alerts: The full queue, before a budget cut. One entry per detector alert.
        attacks: Attack windows on the same clock as ``alerts``.
        origin: The shift clock's zero. Callers pass the file's first timestamp.
        shift: Length of one shift. The frozen operator shift is eight hours.

    Returns:
        One rank per attack, in the order ``attacks`` was given.

    Raises:
        ValueError: If ``shift`` is not a positive duration.
    """
    if shift <= timedelta(0):
        raise ValueError(f"a shift must be a positive duration, got {shift}")
    queues = _queues(alerts, origin, shift)
    ranks: list[AttackRank] = []
    for attack in attacks:
        index = _shift_index(attack.start, origin, shift)
        queue = queues.get(index, ())
        slots = top_slots(len(queue))
        rank = _first_true(queue, attack)
        ranks.append(
            AttackRank(
                attack_id=attack.attack_id,
                passed=rank is not None and rank <= slots,
                rank=rank,
                queue_length=len(queue),
                top_slots=slots,
                shift_index=index,
            )
        )
    return tuple(ranks)


def _queues(
    alerts: Sequence[QueueAlert], origin: datetime, shift: timedelta
) -> dict[int, tuple[QueueAlert, ...]]:
    grouped: dict[int, list[QueueAlert]] = {}
    for alert in alerts:
        grouped.setdefault(_shift_index(alert.timestamp, origin, shift), []).append(alert)
    return {
        index: tuple(
            sorted(group, key=lambda alert: (-alert.score, alert.timestamp, alert.input_order))
        )
        for index, group in grouped.items()
    }


def _first_true(queue: Sequence[QueueAlert], attack: AttackSpan) -> int | None:
    for position, alert in enumerate(queue, start=1):
        if attack.start <= alert.timestamp <= attack.end:
            return position
    return None


def _shift_index(stamp: datetime, origin: datetime, shift: timedelta) -> int:
    return (stamp - origin) // shift

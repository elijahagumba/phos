"""Forty-eight tickets a day (ADR 0202).

A ticket is one person-day. This module does not read CERT, does not fit a model,
and does not change `AggregationPolicy` or the exclusive-host count. Hypothesis
confidence is not computed here.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime

from phos.sentiel.bet001 import BUDGET, DayScore, rank_days
from phos.sentiel.exclusive_return import alerting

__all__ = [
    "alerts_per_day",
    "draw_and_people",
    "draw_size",
    "expected_distinct_insiders",
    "s3_met",
    "surfaced_user_ids",
]


def _calendar_day(when: datetime) -> date:
    """Return the UTC calendar day of a window timestamp."""
    if when.tzinfo is None:
        return when.date()
    return when.astimezone(UTC).date()


def alerts_per_day(days: Sequence[DayScore], budget: int = BUDGET) -> tuple[DayScore, ...]:
    """Raise each calendar day's alerts: positive scores only, at most ``budget``.

    Each day is ranked by ``(-score, user_id, timestamp)`` via `rank_days`, then
    cut by `alerting`. Days are returned in calendar order. The malicious flag
    is not part of the rank.

    Args:
        days: Person-days, in any order.
        budget: The most alerts one calendar day may raise.

    Returns:
        The alerts actually raised.

    Raises:
        ValueError: If ``budget`` is not positive.
    """
    if budget < 1:
        raise ValueError(f"budget must be positive, got {budget}")
    grouped: dict[date, list[DayScore]] = {}
    for item in days:
        grouped.setdefault(_calendar_day(item.day), []).append(item)
    raised: list[DayScore] = []
    for day in sorted(grouped):
        raised.extend(alerting(rank_days(grouped[day]), budget))
    return tuple(raised)


def surfaced_user_ids(alerts: Sequence[DayScore]) -> tuple[str, ...]:
    """Return the distinct labelled users who have a malicious day among ``alerts``.

    A benign day of a labelled user does not count. The order is sorted, so the
    headline count does not depend on rank order.
    """
    return tuple(sorted({item.user_id for item in alerts if item.malicious}))


def draw_size(n_person_days: int, budget: int = BUDGET) -> int:
    """Return how many person-days a label-free draw takes on a day with ``n_person_days``.

    Raises:
        ValueError: If the counts are impossible.
    """
    if n_person_days < 0:
        raise ValueError(f"n_person_days must be >= 0, got {n_person_days}")
    if budget < 1:
        raise ValueError(f"budget must be positive, got {budget}")
    return min(budget, n_person_days)


def draw_and_people(
    days: Sequence[DayScore], budget: int = BUDGET
) -> tuple[dict[date, int], dict[date, int]]:
    """Return ``(n_draw, n_people)`` per calendar day, ignoring score and labels.

    ``n_people`` is the number of distinct user ids present that day. ``n_draw``
    is `draw_size` of the person-day rows. The score and the malicious flag are
    not read.

    Raises:
        ValueError: If ``budget`` is not positive.
    """
    if budget < 1:
        raise ValueError(f"budget must be positive, got {budget}")
    rows: dict[date, int] = {}
    people: dict[date, set[str]] = {}
    for item in days:
        day = _calendar_day(item.day)
        rows[day] = rows.get(day, 0) + 1
        people.setdefault(day, set()).add(item.user_id)
    n_draw = {day: draw_size(count, budget) for day, count in rows.items()}
    n_people = {day: len(users) for day, users in people.items()}
    return n_draw, n_people


def expected_distinct_insiders(
    malicious_days: Mapping[str, Sequence[date]],
    n_draw: Mapping[date, int],
    n_people: Mapping[date, int],
) -> float:
    """Return the expected number of distinct labelled insiders under a uniform draw.

    For each insider the term is ``1 - product over that insider's malicious days
    of (1 - n_draw/n_people)``. An insider with no malicious days contributes 0.
    The draw sizes are inputs; this function does not look at a score.

    Raises:
        ValueError: If a malicious day has no draw, ``n_people`` is below 1, or
            ``n_draw`` exceeds ``n_people``. The ratio is not clamped.
    """
    total = 0.0
    for user_id, days in malicious_days.items():
        if not days:
            continue
        miss = 1.0
        for day in days:
            if day not in n_draw or day not in n_people:
                raise ValueError(f"{user_id} has a malicious day {day} with no draw")
            people = n_people[day]
            draw = n_draw[day]
            if people < 1:
                raise ValueError(f"{day} has no people")
            if draw < 0 or draw > people:
                raise ValueError(f"{day}: n_draw {draw} exceeds n_people {people}")
            miss *= 1.0 - (draw / people)
        total += 1.0 - miss
    return total


def s3_met(challenger_insiders: int, frozen_insiders: int) -> bool:
    """Return whether the challenger surfaced more distinct insiders than frozen 6B.

    Equality is not a pass.

    Raises:
        ValueError: If either count is negative.
    """
    if challenger_insiders < 0 or frozen_insiders < 0:
        raise ValueError(
            f"insider counts must be >= 0, got {challenger_insiders} and {frozen_insiders}"
        )
    return challenger_insiders > frozen_insiders

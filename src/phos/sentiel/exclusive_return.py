"""A return to a web host nobody else has used (ADR 0195).

The score of a person-day is a count of hosts. It is not a confidence, and it
is not a term inside the frozen 6B sum. ``AggregationPolicy`` is not imported
here.

A host counts when this user requested it on a strictly earlier day and every
earlier request of that host was by this same user. The first request scores
nothing. Another user's request on the same day neither adds a point nor
removes one: the day is judged from the state at its start.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime
from typing import NamedTuple, Protocol

__all__ = [
    "SCORER_NAME",
    "HostDay",
    "alerting",
    "exclusive_return_scores",
    "single_user_host_owners",
]


class Scored(Protocol):
    """Anything ranked with a numeric score."""

    @property
    def score(self) -> float:
        """The ranked score."""
        ...


SCORER_NAME: str = "exclusive-host-return"
"""Challenger name. Not the frozen 6B detector name."""


class HostDay(NamedTuple):
    """One user's web hosts on one calendar day.

    Attributes:
        user_id: The corpus user id.
        day: Midnight UTC of the window.
        hosts: Distinct hosts requested that day. Duplicates count once.
    """

    user_id: str
    day: datetime
    hosts: tuple[str, ...]


def exclusive_return_scores(days: Sequence[HostDay]) -> tuple[int, ...]:
    """Return one exclusive-return count per day, in input order.

    Args:
        days: Person-days in non-decreasing day order. Every row that shares a
            day is judged against the same prior state, whatever order those
            rows are in.

    Returns:
        The count for each input row. A day with no qualifying host is 0.

    Raises:
        ValueError: If a later row names an earlier day. The state would then
            include the future.
    """
    scores = [0] * len(days)
    seen: dict[str, set[str]] = defaultdict(set)
    owners: dict[str, set[str]] = defaultdict(set)
    index = 0
    previous: datetime | None = None
    while index < len(days):
        day = days[index].day
        if previous is not None and day < previous:
            raise ValueError(f"days must be non-decreasing; {day} follows {previous}")
        end = index + 1
        while end < len(days) and days[end].day == day:
            end += 1
        for offset in range(index, end):
            item = days[offset]
            already = seen[item.user_id]
            count = 0
            for host in dict.fromkeys(host for host in item.hosts if host):
                prior = owners.get(host)
                if host in already and prior is not None and prior <= {item.user_id}:
                    count += 1
            scores[offset] = count
        for offset in range(index, end):
            item = days[offset]
            for host in dict.fromkeys(host for host in item.hosts if host):
                owners[host].add(item.user_id)
                seen[item.user_id].add(host)
        previous = day
        index = end
    return tuple(scores)


def alerting[T: Scored](ranked: Sequence[T], budget: int) -> tuple[T, ...]:
    """Return the alerts actually raised: positive scores only, at most ``budget`` (ADR 0196).

    A day that scores 0 is not an alert, even when ties would otherwise let it fill the budget.

    Args:
        ranked: Days already in rank order.
        budget: The most alerts that may be raised.
    """
    return tuple(item for item in ranked if item.score > 0)[:budget]


def single_user_host_owners(days: Sequence[HostDay]) -> dict[str, int]:
    """Count, per user, the hosts that no other user requested anywhere in the release.

    The realism check of ADR 0196: in real browsing, many people use a site no colleague
    uses. A release where almost no innocent user has one suggests the signal reads how the
    dataset was generated rather than how people behave.

    Returns:
        Each user with at least one single-user host, mapped to how many such hosts they have.
    """
    owners: dict[str, set[str]] = defaultdict(set)
    for item in days:
        for host in item.hosts:
            if host:
                owners[host].add(item.user_id)
    counts: dict[str, int] = defaultdict(int)
    for host_owners in owners.values():
        if len(host_owners) == 1:
            counts[next(iter(host_owners))] += 1
    return dict(counts)

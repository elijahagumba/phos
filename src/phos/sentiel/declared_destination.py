"""How many declared destinations were new for this user (ADR 0270).

The score of a person-day is ``declared_new_destination_count`` from
`IdentityFeaturiser`. It is a count. It is not a confidence, it is not a term
inside the frozen 6B sum, and it is not `exclusive-host-return`.

``AggregationPolicy`` is not imported here. The 34 features are not read.
``HistoryPolicy`` stays at its defaults: eight prior windows before a new-name
count may speak, and a name is forgotten after thirty. A day the history cannot
support scores 0. Another user's mail does not change this user's count.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Iterator, Sequence
from datetime import datetime
from typing import NamedTuple

from phos.ontology import Observation
from phos.sentiel.events import EnterpriseEvent
from phos.sentiel.identity_score import events_from_trace
from phos.sentiel.named_counterparties import (
    MATCHED_IDENTITIES,
    DeclaredIdentities,
    IdentityFeaturiser,
)
from phos.sentiel.traces import EntityDayTrace

__all__ = [
    "SCORER_NAME",
    "DestinationDay",
    "score_declared_new_destinations",
    "single_user_destination_owners",
    "users_with_new_destination",
]

SCORER_NAME: str = "declared-new-destination"
"""Challenger name. Not the frozen 6B detector name, and not exclusive-host-return."""

_COUNT: str = "declared_destination_count"
_NEW: str = "declared_new_destination_count"


class DestinationDay(NamedTuple):
    """One person-day's declared destinations and how many were new for that user.

    Attributes:
        user_id: The corpus user id.
        day: Midnight UTC of the window.
        new_destinations: Declared addresses in this window that the user's own
            history did not already hold. Zero when that history is too short.
        destinations: The declared addresses in this window, sorted. Addresses
            outside the register are not listed.
    """

    user_id: str
    day: datetime
    new_destinations: int
    destinations: tuple[str, ...]


def score_declared_new_destinations(
    traces: Sequence[EntityDayTrace],
    register: DeclaredIdentities,
) -> tuple[DestinationDay, ...]:
    """Return one new-destination count per trace, in input order.

    The count is the score a later ranker uses. This function does not rank,
    does not read a label, and does not drop a zero.

    Args:
        traces: Person-days in non-decreasing day order.
        register: Declared names. Destinations are the only kind this score reads.
            Hosts and machines in the register match nothing here, because the
            events rebuilt from a trace's recipients are mail.

    Returns:
        One row per input trace.

    Raises:
        ValueError: If the traces are not time-ordered, a person-day is repeated,
            or the featuriser does not emit every input trace.
    """
    featuriser = IdentityFeaturiser(identities=register)
    found = _collect(featuriser.stream(_events(traces)))
    rows: list[DestinationDay] = []
    for trace in traces:
        key = (trace.user_id, trace.day)
        row = found.pop(key, None)
        if row is None:
            raise ValueError(f"no destination score for {trace.user_id} at {trace.day}")
        rows.append(row)
    if found:
        raise ValueError(f"the featuriser emitted {len(found)} person-days the traces omit")
    return tuple(rows)


def users_with_new_destination(days: Sequence[DestinationDay]) -> frozenset[str]:
    """Return users with at least one day whose new-destination count is positive.

    A zero, including a day the history cannot yet support, does not count.
    """
    return frozenset(day.user_id for day in days if day.new_destinations > 0)


def single_user_destination_owners(days: Sequence[DestinationDay]) -> dict[str, int]:
    """Count, per user, the declared destinations no other user mailed.

    This is not the score. It is the exclusivity reading, so a result can say
    whether a directory address was one person's alone. The new-destination
    count does not use it.

    Returns:
        Each user with at least one such destination, mapped to how many.
    """
    owners: dict[str, set[str]] = defaultdict(set)
    for day in days:
        for name in day.destinations:
            if name:
                owners[name].add(day.user_id)
    counts: dict[str, int] = defaultdict(int)
    for who in owners.values():
        if len(who) == 1:
            counts[next(iter(who))] += 1
    return dict(counts)


def _events(traces: Sequence[EntityDayTrace]) -> Iterator[EnterpriseEvent]:
    """Yield the recipients on each trace, in trace order."""
    for trace in traces:
        yield from events_from_trace(trace)


def _names(joined: str) -> tuple[str, ...]:
    """Split a matched-identity list. An empty list stays empty."""
    return tuple(part for part in joined.split(";") if part)


def _collect(
    observations: Iterable[Observation],
) -> dict[tuple[str, datetime], DestinationDay]:
    """Pair each window's destination count with its new-destination count."""
    found: dict[tuple[str, datetime], DestinationDay] = {}
    pending: dict[tuple[str, datetime], tuple[str, ...]] = {}
    for observation in observations:
        feature = observation.feature
        if feature not in (_COUNT, _NEW):
            continue
        context = observation.context
        user_id = context["user_id"]
        if not isinstance(user_id, str) or not user_id:
            raise ValueError("a destination observation has no user id")
        when = observation.timestamp
        if not isinstance(when, datetime):
            raise ValueError("a destination observation has no timestamp")
        key = (user_id, when)
        if feature == _COUNT:
            pending[key] = _names(context.get(MATCHED_IDENTITIES, ""))
            continue
        names = pending.pop(key, None)
        if names is None:
            raise ValueError(
                f"new-destination count for {user_id} at {when} has no destination list"
            )
        if key in found:
            raise ValueError(f"duplicate person-day {user_id} at {when}")
        value = observation.value
        if isinstance(value, bool) or not isinstance(value, int | float) or value != int(value):
            raise ValueError(f"new-destination count must be a whole number, got {value!r}")
        if value < 0:
            raise ValueError(f"new-destination count must be >= 0, got {value}")
        found[key] = DestinationDay(user_id, when, int(value), names)
    if pending:
        raise ValueError(f"{len(pending)} destination lists had no new-destination count")
    return found

"""Counting one event once: collapsing a unit's per-signal evidence into a subsystem event.

5A attributes a joint anomaly to the specific signal that broke the plant's learned structure,
which is the right unit for *explaining* it. It is the wrong unit for *counting* it. When a pump
falters, every instrument on that pump departs at the same instant and Atlas produces one piece of
`Evidence` for each, so an operator is handed ten things to investigate when there was one thing.

5B wrote down the fact that fixes it — which signals share a physical unit — as a declared
partition. This module is where that fact is finally spent: evidence sharing a ``(subsystem, time
window)`` becomes one **subsystem event**, and the operator's queue shrinks by the size of the
instrumentation rather than by any change in what was detected.

**This is a counting change and nothing else, and the code is arranged so that stays checkable.**
No evidence is discarded, filtered or re-scored on the way through: every input lands in exactly
one event, and the event keeps the ids of all of them. `group_evidence` is a pure function of its
arguments — no store, no clock, no model — so the same evidence and the same map always collapse
the same way.

**Membership comes only from `SubsystemMap`.** Never from name similarity, never from co-movement.
The signal a piece of evidence concerns is recovered by walking its own traceability link back to
the `Deviation` that raised it and reading the signal off the `ExpectedRange` there, which is why
`group_evidence` needs a deviation lookup: `Evidence` records the entities a fact concerns, and in
a CSV-sourced corpus every signal is attributed to one entity, so the entity cannot say which
signal departed. Walking the link is also exactly the route an operator would take.

**Buckets are anchored to a fixed epoch, not to the batch.** Two runs over overlapping slices of
one corpus must agree about which window a measurement fell in, so the grid is absolute. The cost
is the ordinary tumbling-window one: two departures a second apart land in different events if they
straddle a boundary.

**A subsystem event's ``entity_ids`` are the signals that departed, not the entities behind them.**
That is what makes breadth — how much of a unit moved — a property of one fact, which is what
`phos.atlas.templates` matches on. It has one consequence worth knowing rather than discovering:
`ReasoningEngine` tests co-occurrence by intersecting ``entity_ids``, and because membership is a
partition, two subsystem events never share a signal. So events are never joined into one story by
co-occurrence; they are joined only when the same hypothesis rests on both.

**Traceability survives the collapse** (Constitution §3.2). A subsystem event's ``source_id``
carries the ids of every piece of evidence it was built from, behind a marker so it can never be
mistaken for a single `Deviation` id; from each member the existing ontology already leads to its
deviation and on to the measurement. `member_evidence_ids` is that path's front door — an event an
operator cannot expand back into signals would be a summary, not a finding.
"""

import logging
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Final

from phos.atlas.topology import Subsystem, SubsystemMap
from phos.ontology import (
    Deviation,
    DeviationId,
    Domain,
    Evidence,
    EvidenceId,
    EvidenceKind,
)

__all__ = [
    "SUBSYSTEM_EVENT_MARKER",
    "group_evidence",
    "is_subsystem_event",
    "member_evidence_ids",
]

logger = logging.getLogger(__name__)

SUBSYSTEM_EVENT_MARKER: Final = "subsystem-event:"
"""Prefix that marks an `Evidence.source_id` as naming members rather than one `Deviation`.

Explicit rather than inferred from the id prefixes, so "is this a collapsed event?" is a question
about a declared marker instead of a question about how identifiers happen to be spelled.
"""

_MEMBER_SEPARATOR: Final = ","
"""Separates member ids inside a subsystem event's ``source_id``. Absent from every minted id."""

_WINDOW_EPOCH: Final = datetime(1970, 1, 1, tzinfo=UTC)
"""The instant the tumbling window grid is anchored to. Any fixed instant would do; this one is
conventional and makes a bucket boundary readable in a log."""

_GroupKey = tuple[Domain, str, datetime]
"""How a subsystem event is identified while it is being assembled.

`(domain, subsystem_id, window start)`. Domain is in the key rather than checked, because a
`SubsystemMap` describes one corpus and putting two engines' evidence in one event would be
cross-engine correlation, which is PART 7's business and not something to do by accident.
"""


def group_evidence(
    evidence: Sequence[Evidence],
    subsystem_map: SubsystemMap,
    window: timedelta,
    deviations: Mapping[DeviationId, Deviation],
) -> list[Evidence]:
    """Collapse per-signal evidence into one event per physical unit per time window.

    Args:
        evidence: The per-signal evidence to collapse, in any order. Not modified.
        subsystem_map: The declared partition. The **only** source of membership.
        window: Width of the tumbling time window. Buckets are anchored to a fixed epoch, so
            which window a piece of evidence falls in does not depend on what else is in the batch.
        deviations: Lookup from deviation id to `Deviation`, covering every piece of evidence's
            ``source_id``. Needed to recover which signal each fact concerns; see this module's
            docstring for why the evidence cannot say so itself.

    Returns:
        One representative `Evidence` of kind `DEVIATION` per ``(domain, subsystem, window)`` that
        had any evidence in it, ordered by timestamp then subsystem then domain. Each names its
        subsystem in ``summary``, lists the distinct member signals in ``entity_ids``, carries the
        strongest member's calibrated ``weight``, is stamped at its earliest member's instant, and
        holds every member's id in ``source_id`` — read it back with `member_evidence_ids`.

    Raises:
        ValueError: If ``window`` is not a positive duration, or if a piece of evidence names a
            ``source_id`` ``deviations`` does not hold, which leaves its signal — and therefore its
            subsystem — unknowable.
        TopologyError: If a signal is outside the corpus the map was built against. It should not
            happen after 5B, whose construction refuses a partial map; the guard is here because
            guessing the unit would corrupt every count taken from it, invisibly.

    Note:
        Pure and deterministic. The same arguments always produce the same events, in the same
        order, with the same summaries.
    """
    if window <= timedelta(0):
        raise ValueError(
            f"window must be a positive duration, got {window}: a zero or negative window would "
            "put every piece of evidence in its own event and collapse nothing"
        )

    grouped: dict[_GroupKey, list[tuple[str, Evidence]]] = {}
    units: dict[str, Subsystem] = {}
    for fact in evidence:
        signal = _signal_of(fact, deviations)
        subsystem = subsystem_map.subsystem_for(signal)
        units[subsystem.subsystem_id] = subsystem
        key: _GroupKey = (
            fact.domain,
            subsystem.subsystem_id,
            _window_start(fact.timestamp, window),
        )
        grouped.setdefault(key, []).append((signal, fact))

    events = [
        _event(units[subsystem_id], members)
        for (_, subsystem_id, _), members in sorted(
            grouped.items(), key=lambda item: (item[0][2], item[0][1], item[0][0].value)
        )
    ]
    logger.info(
        "grouped %d piece(s) of evidence into %d subsystem event(s) over a %s window",
        len(evidence),
        len(events),
        window,
    )
    return events


def is_subsystem_event(evidence: Evidence) -> bool:
    """Return whether this evidence is a collapsed subsystem event rather than a per-signal fact."""
    return evidence.source_id.startswith(SUBSYSTEM_EVENT_MARKER)


def member_evidence_ids(event: Evidence) -> tuple[EvidenceId, ...]:
    """Return the ids of the per-signal evidence ``event`` was collapsed from.

    The first step of the drill-down path. Each member's own ``source_id`` names the `Deviation`
    behind it, and that deviation names the `Observation` — so from here the ontology already
    reaches the measurement.

    Args:
        event: A subsystem event produced by `group_evidence`.

    Returns:
        The member ids, in the order the event recorded them: earliest first, ties broken by signal.

    Raises:
        ValueError: If ``event`` is not a subsystem event. A per-signal `Evidence` has no members,
            and returning its own ``source_id`` — a deviation id — would silently hand the caller
            the wrong kind of identifier.
    """
    if not is_subsystem_event(event):
        raise ValueError(
            f"evidence {event.id!r} is not a subsystem event: its source_id {event.source_id!r} "
            "names the deviation it came from, not a set of members"
        )
    return tuple(event.source_id[len(SUBSYSTEM_EVENT_MARKER) :].split(_MEMBER_SEPARATOR))


def _signal_of(fact: Evidence, deviations: Mapping[DeviationId, Deviation]) -> str:
    """Return the signal ``fact`` concerns, by walking its traceability link to its deviation.

    Raises:
        ValueError: If the deviation is not in the lookup.
    """
    deviation = deviations.get(fact.source_id)
    if deviation is None:
        raise ValueError(
            f"evidence {fact.id!r} names source {fact.source_id!r}, which cannot be resolved to a "
            "deviation, so the signal it concerns — and therefore its subsystem — is unknowable"
        )
    return deviation.expected.feature


def _window_start(timestamp: datetime, window: timedelta) -> datetime:
    """Return the start of the tumbling window ``timestamp`` falls in, on the absolute grid."""
    return _WINDOW_EPOCH + ((timestamp - _WINDOW_EPOCH) // window) * window


def _event(subsystem: Subsystem, members: Sequence[tuple[str, Evidence]]) -> Evidence:
    """Assemble one subsystem event from the ``(signal, evidence)`` pairs that share its key."""
    ordered = sorted(members, key=lambda member: (member[1].timestamp, member[0]))
    signals = sorted({signal for signal, _ in members})
    strongest = min(members, key=lambda member: (-member[1].weight, member[0]))

    return Evidence(
        kind=EvidenceKind.DEVIATION,
        source_id=SUBSYSTEM_EVENT_MARKER + _MEMBER_SEPARATOR.join(fact.id for _, fact in ordered),
        entity_ids=signals,
        timestamp=ordered[0][1].timestamp,
        domain=ordered[0][1].domain,
        weight=strongest[1].weight,
        summary=(
            f"{subsystem.subsystem_id} ({subsystem.label}): {len(signals)} of "
            f"{len(subsystem.signals)} signal(s) departed from the plant's learned structure "
            f"together; strongest {strongest[0]}"
        ),
    )

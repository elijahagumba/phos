"""Collapse repeated alerts of one labelled incident so the shift can hold more of them.

`group_evidence` is not edited and is not called. Membership is the incident id the caller
already supplied. Two ids never become one incident because they happened to be close.
Alerts of one id join when the gap is within the frozen event window and the chain spans
at most the frozen event span. The representative is the earliest alert, so the page is
not later than the first member. Its score is the strongest member, so the incident can
still compete for a slot.

The page keeps at most `ALERTS_PER_SHIFT` representatives. This is a counting change on a
fixture. It is not a detection claim.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

from phos.atlas.consistency import ALERTS_PER_SHIFT
from phos.atlas.consistency_windows import EVENT_SPAN, EVENT_WINDOW

__all__ = [
    "IncidentAlert",
    "PackedIncident",
    "incidents_inside_budget",
    "pack_incidents",
]

logger = logging.getLogger(__name__)

_GAP: Final = timedelta(seconds=EVENT_WINDOW)
_SPAN: Final = timedelta(seconds=EVENT_SPAN)


@dataclass(frozen=True)
class IncidentAlert:
    """One already-labelled alert.

    Attributes:
        incident_id: The incident the caller says this alert belongs to.
        at: When it fires. Timezone-aware.
        score: Rank against other alerts. Higher is kept first when unpacked.
        key: Stable name of this alert.
    """

    incident_id: str
    at: datetime
    score: float
    key: str


@dataclass(frozen=True)
class PackedIncident:
    """One chain of a single incident id.

    Attributes:
        incident_id: The shared id. Never a merge of two ids.
        at: The earliest member.
        score: The strongest member.
        key: The earliest member's key.
        member_keys: Every member, earliest first.
    """

    incident_id: str
    at: datetime
    score: float
    key: str
    member_keys: tuple[str, ...]


def pack_incidents(alerts: Sequence[IncidentAlert]) -> tuple[PackedIncident, ...]:
    """Return one representative per chain.

    Args:
        alerts: Labelled alerts. An empty sequence stays empty.

    Returns:
        Chains ordered by time, then incident id.

    Raises:
        ValueError: If a time is naive.
    """
    for alert in alerts:
        _require_aware(alert.at)
    grouped: dict[str, list[IncidentAlert]] = {}
    for alert in alerts:
        grouped.setdefault(alert.incident_id, []).append(alert)
    packed: list[PackedIncident] = []
    for incident_id in sorted(grouped):
        rows = sorted(grouped[incident_id], key=lambda item: (item.at, item.key))
        chain: list[IncidentAlert] = []
        for alert in rows:
            if chain and not _joins(chain, alert):
                packed.append(_close(incident_id, chain))
                chain = []
            chain.append(alert)
        if chain:
            packed.append(_close(incident_id, chain))
    packed.sort(key=lambda item: (item.at, item.incident_id, item.key))
    logger.info("packed %s alerts into %s incidents", len(alerts), len(packed))
    return tuple(packed)


def incidents_inside_budget(alerts: Sequence[IncidentAlert], *, packed: bool) -> tuple[str, ...]:
    """Return the incident ids that receive a slot inside the shift budget.

    Unpacked, each alert competes on its own score and the first
    ``ALERTS_PER_SHIFT`` win. Packed, each chain competes once, on its strongest
    member, and the earliest member is the time that is shown.

    Args:
        alerts: The labelled alerts of one comparison.
        packed: Whether to collapse chains before the budget.

    Returns:
        Incident ids that won a slot, highest score first. At most one copy of an id
        when packed. Unpacked may list an id once even if several of its alerts won.
    """
    if packed:
        rows = pack_incidents(alerts)
        ranked = sorted(rows, key=lambda item: (-item.score, item.at, item.incident_id))
        return tuple(item.incident_id for item in ranked[:ALERTS_PER_SHIFT])
    ranked_alerts = sorted(alerts, key=lambda item: (-item.score, item.at, item.key))
    chosen = ranked_alerts[:ALERTS_PER_SHIFT]
    seen: list[str] = []
    for alert in chosen:
        if alert.incident_id not in seen:
            seen.append(alert.incident_id)
    return tuple(seen)


def _joins(chain: Sequence[IncidentAlert], alert: IncidentAlert) -> bool:
    """Return whether ``alert`` is close enough to stay in this chain."""
    gap = alert.at - chain[-1].at
    span = alert.at - chain[0].at
    return gap <= _GAP and span <= _SPAN


def _close(incident_id: str, chain: Sequence[IncidentAlert]) -> PackedIncident:
    """Build the representative. Earliest time, strongest score."""
    earliest = min(chain, key=lambda item: (item.at, item.key))
    strongest = max(item.score for item in chain)
    return PackedIncident(
        incident_id=incident_id,
        at=earliest.at,
        score=strongest,
        key=earliest.key,
        member_keys=tuple(item.key for item in chain),
    )


def _require_aware(moment: datetime) -> None:
    """Raise when ``moment`` has no timezone."""
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("incident time must be timezone-aware")

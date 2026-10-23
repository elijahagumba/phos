"""One shift page that keeps an unbooked transfer and then the process hits.

An unbooked program transfer stays, with ``Go and look.`` and both stories tied.
It is not removed to make room for a joint move, a walk, or a handoff. A booked
transfer takes no slot. A handoff whose booking names both tags takes no slot.
The page holds at most eight. The frozen allocator is not called, and it is not
edited.

This is a fixture. It is not a detection claim.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

from phos.atlas.consistency import ALERTS_PER_SHIFT, SHIFT_SECONDS
from phos.atlas.handoff_booking import HandoffNotice, TagBooking, handoff_notices
from phos.atlas.joint_setpoint import SetpointStep, joint_moves
from phos.atlas.program_transfer import GO_AND_LOOK, NEXT_OBSERVATION, TransferReport
from phos.atlas.subfloor_walk import subfloor_walks

__all__ = [
    "BriefSlot",
    "shift_brief",
]

logger = logging.getLogger(__name__)

_TRANSFER: Final = "transfer"
_JOINT: Final = "joint"
_WALK: Final = "walk"
_HANDOFF: Final = "handoff"


@dataclass(frozen=True)
class BriefSlot:
    """One place on the shift brief.

    Attributes:
        at: When this slot fires.
        kind: ``transfer``, ``joint``, ``walk``, or ``handoff``.
        name: The act, the tags, or the walked tag.
        instruction: ``Go and look.`` on an unbooked transfer or an open handoff.
        next_observation: The booking that would withdraw that alert, or ``None``.
        lead: Always ``None``.
    """

    at: datetime
    kind: str
    name: str
    instruction: str | None
    next_observation: str | None
    lead: None = None


def shift_brief(
    steps: Sequence[SetpointStep],
    transfers: Sequence[tuple[TransferReport, datetime]] = (),
    bookings: Sequence[TagBooking] = (),
) -> tuple[BriefSlot, ...]:
    """Keep unbooked transfers, then the earliest process hits, at most eight.

    Args:
        steps: Setpoint writes the caller supplied.
        transfers: Each report with the time it happened. A report whose alert is
            false is omitted.
        bookings: Bookings that can withdraw a handoff. They do not withdraw a
            transfer. An empty sequence stays empty.

    Returns:
        At most ``ALERTS_PER_SHIFT`` slots. Unbooked transfers first, earliest act
        name after that. Process hits fill the room that is left, earliest first.

    Raises:
        ValueError: If a time is naive, or the supplied times span a second shift.
    """
    _one_shift([step.at for step in steps] + [at for _report, at in transfers])
    kept = [(report, at) for report, at in transfers if report.alert]
    kept.sort(key=lambda item: (item[1], item[0].act.value))
    kept = kept[:ALERTS_PER_SHIFT]
    room = ALERTS_PER_SHIFT - len(kept)
    process = _process(steps, bookings)[:room]
    slots = [_transfer_slot(report, at) for report, at in kept]
    slots.extend(process)
    if len(slots) > ALERTS_PER_SHIFT:
        raise RuntimeError("shift brief exceeded eight")
    logger.info("shift brief transfers=%s process=%s", len(kept), len(process))
    return tuple(slots)


def _process(steps: Sequence[SetpointStep], bookings: Sequence[TagBooking]) -> list[BriefSlot]:
    """Joint moves, walks, and handoffs that are still open, earliest first."""
    slots: list[BriefSlot] = []
    for move in joint_moves(steps):
        slots.append(
            BriefSlot(
                at=move.at,
                kind=_JOINT,
                name=",".join(move.tags),
                instruction=None,
                next_observation=None,
            )
        )
    for walk in subfloor_walks(steps):
        slots.append(
            BriefSlot(
                at=walk.at,
                kind=_WALK,
                name=walk.tag,
                instruction=None,
                next_observation=None,
            )
        )
    for notice in handoff_notices(steps, bookings):
        if notice.alert:
            slots.append(_handoff_slot(notice))
    slots.sort(key=lambda slot: (slot.at, slot.kind, slot.name))
    return slots


def _transfer_slot(report: TransferReport, at: datetime) -> BriefSlot:
    """An unbooked transfer. The instruction and the next observation stay."""
    return BriefSlot(
        at=at,
        kind=_TRANSFER,
        name=report.act.value,
        instruction=GO_AND_LOOK,
        next_observation=NEXT_OBSERVATION,
        lead=None,
    )


def _handoff_slot(notice: HandoffNotice) -> BriefSlot:
    """An open handoff. The booking sentence is the next observation."""
    return BriefSlot(
        at=notice.at,
        kind=_HANDOFF,
        name=",".join(notice.tags),
        instruction=notice.instruction,
        next_observation=notice.next_observation,
        lead=None,
    )


def _one_shift(moments: Sequence[datetime]) -> None:
    """Raise when the times are naive or cover more than one shift."""
    for moment in moments:
        if moment.tzinfo is None or moment.utcoffset() is None:
            raise ValueError("shift time must be timezone-aware")
    if len(moments) < 2:
        return
    span = max(moments) - min(moments)
    if span >= timedelta(seconds=SHIFT_SECONDS):
        raise ValueError("shift_brief takes one shift")

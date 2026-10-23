"""The same in-band value, written on a second tag after the joint window.

`joint_moves` joins two tags only while the gap is within the frozen event window.
A later write of that same value, on a different tag, is invisible there, and it is
not a 720-step walk. This module reports that pair. The time shown is the earlier
write. The score is the count of tags. It is not a confidence.

The gap has to be longer than the frozen window and shorter than one shift. Neither
length is retuned. A value outside 6.5-7.5 is not this class. There is no path from
a Modbus function code to a step. This is a fixture. It is not a detection claim,
and it does not edit the frozen detector.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

from phos.atlas.consistency import SHIFT_SECONDS
from phos.atlas.consistency_windows import EVENT_WINDOW
from phos.atlas.joint_setpoint import SETPOINT_BAND, SetpointStep

__all__ = [
    "BandHandoff",
    "band_handoffs",
]

logger = logging.getLogger(__name__)

_AFTER_WINDOW: Final = timedelta(seconds=EVENT_WINDOW)
_INSIDE_SHIFT: Final = timedelta(seconds=SHIFT_SECONDS)


@dataclass(frozen=True)
class BandHandoff:
    """One value that moved from one tag to another after the joint window.

    Attributes:
        at: The earlier write.
        tags: The two tags, sorted.
        value: The shared in-band value.
        score: How many tags moved. A count, not a confidence.
    """

    at: datetime
    tags: tuple[str, str]
    value: float
    score: float


def band_handoffs(steps: Sequence[SetpointStep]) -> tuple[BandHandoff, ...]:
    """Return one handoff per pair the joint window cannot see.

    Args:
        steps: Setpoint writes the caller supplied. Empty stays empty.

    Returns:
        Handoffs, earliest first. A pair inside the joint window is omitted.
        The same tag twice is omitted. A gap of one full shift is omitted.

    Raises:
        ValueError: If an in-band time is naive.
    """
    inside = [step for step in steps if _in_band(step)]
    for step in inside:
        _require_aware(step.at)
    inside.sort(key=lambda step: (step.at, step.tag))
    used: set[int] = set()
    found: list[BandHandoff] = []
    for sender_index, sender in enumerate(inside):
        if sender_index in used:
            continue
        receiver_index = _receiver(inside, used, sender_index, sender)
        if receiver_index is None:
            continue
        receiver = inside[receiver_index]
        used.add(sender_index)
        used.add(receiver_index)
        found.append(_pair(sender, receiver))
    found.sort(key=lambda handoff: (handoff.at, handoff.tags))
    logger.info("band handoffs %s from %s in-band steps", len(found), len(inside))
    return tuple(found)


def _receiver(
    inside: Sequence[SetpointStep],
    used: set[int],
    sender_index: int,
    sender: SetpointStep,
) -> int | None:
    """Return the earliest later step that continues ``sender``'s value."""
    for index in range(sender_index + 1, len(inside)):
        if index in used:
            continue
        candidate = inside[index]
        gap = candidate.at - sender.at
        if gap >= _INSIDE_SHIFT:
            return None
        if _continues(sender, candidate, gap):
            return index
    return None


def _continues(sender: SetpointStep, candidate: SetpointStep, gap: timedelta) -> bool:
    """Return whether ``candidate`` is the later tag of a handoff."""
    return gap > _AFTER_WINDOW and candidate.tag != sender.tag and candidate.value == sender.value


def _pair(sender: SetpointStep, receiver: SetpointStep) -> BandHandoff:
    """One handoff timed at the earlier write."""
    tags = tuple(sorted((sender.tag, receiver.tag)))
    return BandHandoff(at=sender.at, tags=(tags[0], tags[1]), value=sender.value, score=2.0)


def _in_band(step: SetpointStep) -> bool:
    """Return whether the value sits in the ordinary setpoint band."""
    low, high = SETPOINT_BAND
    return low <= step.value <= high


def _require_aware(moment: datetime) -> None:
    """Raise when ``moment`` has no timezone."""
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("setpoint time must be timezone-aware")

"""Several setpoints move together inside the ordinary band.

One setpoint written inside 6.5-7.5 is the ordinary operator write. It raises nothing
here. Two or more different tags inside that band, chained on the frozen event window,
are one joint move. The time shown is the earliest step, so the alert is not later than
the first write. A value outside the band is not this class.

There is no path from a Modbus function code to a step. This is a fixture. It is not a
detection claim, and it does not edit the frozen detector.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

from phos.atlas.consistency_windows import EVENT_SPAN, EVENT_WINDOW

__all__ = [
    "SETPOINT_BAND",
    "JointMove",
    "SetpointStep",
    "joint_moves",
]

logger = logging.getLogger(__name__)

SETPOINT_BAND: Final = (6.5, 7.5)
"""The band a benign setpoint already uses. Not a second band, and not a threshold."""

_GAP: Final = timedelta(seconds=EVENT_WINDOW)
_SPAN: Final = timedelta(seconds=EVENT_SPAN)


@dataclass(frozen=True)
class SetpointStep:
    """One supplied setpoint write.

    Attributes:
        tag: The setpoint the caller names.
        at: When it was written. Timezone-aware.
        value: The written value.
    """

    tag: str
    at: datetime
    value: float


@dataclass(frozen=True)
class JointMove:
    """One chain in which at least two tags moved inside the band.

    Attributes:
        at: The earliest step.
        tags: The distinct tags, sorted.
        score: How many tags moved. A count, not a confidence.
    """

    at: datetime
    tags: tuple[str, ...]
    score: float


def joint_moves(steps: Sequence[SetpointStep]) -> tuple[JointMove, ...]:
    """Return one alert per chain of two or more in-band tags.

    Args:
        steps: Setpoint writes the caller supplied. Empty stays empty.

    Returns:
        Joint moves, earliest first. A chain of one tag is omitted.

    Raises:
        ValueError: If a time is naive.
    """
    inside = [step for step in steps if _in_band(step)]
    for step in inside:
        _require_aware(step.at)
    inside.sort(key=lambda step: (step.at, step.tag))
    found: list[JointMove] = []
    chain: list[SetpointStep] = []
    for step in inside:
        if chain and not _joins(chain, step):
            _emit(chain, found)
            chain = []
        chain.append(step)
    _emit(chain, found)
    logger.info("joint moves %s from %s in-band steps", len(found), len(inside))
    return tuple(found)


def _in_band(step: SetpointStep) -> bool:
    """Return whether the value sits in the ordinary setpoint band."""
    low, high = SETPOINT_BAND
    return low <= step.value <= high


def _joins(chain: Sequence[SetpointStep], step: SetpointStep) -> bool:
    """Return whether ``step`` is close enough to stay in this chain."""
    return step.at - chain[-1].at <= _GAP and step.at - chain[0].at <= _SPAN


def _emit(chain: Sequence[SetpointStep], found: list[JointMove]) -> None:
    """Append a move when the chain names two tags."""
    if not chain:
        return
    tags = tuple(sorted({step.tag for step in chain}))
    if len(tags) < 2:
        return
    earliest = min(step.at for step in chain)
    found.append(JointMove(at=earliest, tags=tags, score=float(len(tags))))


def _require_aware(moment: datetime) -> None:
    """Raise when ``moment`` has no timezone."""
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("setpoint time must be timezone-aware")

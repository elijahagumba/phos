"""One tag walked across the ordinary band in 720 steps.

`joint_moves` stays silent on one tag, so this class is invisible there. A walk is 720
in-band steps of one tag whose consecutive gap is at most one second. The alert is the
first step, so it is not later than the walk. 719 steps are not a walk. The frozen event
span is 600 seconds, and a 720-step walk is longer than that, so this module does not
reuse that span and does not retune it.

This is a fixture. It is not a detection claim, and it does not edit the frozen detector.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

from phos.atlas.joint_setpoint import SETPOINT_BAND, SetpointStep

__all__ = [
    "WALK_STEPS",
    "TagWalk",
    "subfloor_walks",
]

logger = logging.getLogger(__name__)

WALK_STEPS: Final = 720
"""The harness floor. Fewer steps are not this class."""

_STEP_GAP: Final = timedelta(seconds=1)


@dataclass(frozen=True)
class TagWalk:
    """One tag that crossed the band in at least `WALK_STEPS` close steps.

    Attributes:
        tag: The setpoint that was walked.
        at: The first step. Not the last.
        steps: How many steps joined. At least `WALK_STEPS`.
        score: The step count. A count, not a confidence.
    """

    tag: str
    at: datetime
    steps: int
    score: float


def subfloor_walks(steps: Sequence[SetpointStep]) -> tuple[TagWalk, ...]:
    """Return one walk per tag that takes at least `WALK_STEPS` close in-band steps.

    Args:
        steps: Setpoint writes the caller supplied. Empty stays empty.

    Returns:
        Walks, earliest first. A short chain is omitted.

    Raises:
        ValueError: If an in-band time is naive.
    """
    inside = [step for step in steps if _in_band(step)]
    for step in inside:
        _require_aware(step.at)
    grouped: dict[str, list[SetpointStep]] = {}
    for step in inside:
        grouped.setdefault(step.tag, []).append(step)
    found: list[TagWalk] = []
    for tag in sorted(grouped):
        rows = sorted(grouped[tag], key=lambda step: step.at)
        chain: list[SetpointStep] = []
        for step in rows:
            if chain and step.at - chain[-1].at > _STEP_GAP:
                _emit(tag, chain, found)
                chain = []
            chain.append(step)
        _emit(tag, chain, found)
    found.sort(key=lambda walk: (walk.at, walk.tag))
    logger.info("subfloor walks %s", len(found))
    return tuple(found)


def _in_band(step: SetpointStep) -> bool:
    """Return whether the value sits in the ordinary setpoint band."""
    low, high = SETPOINT_BAND
    return low <= step.value <= high


def _emit(tag: str, chain: Sequence[SetpointStep], found: list[TagWalk]) -> None:
    """Append a walk when the chain is long enough."""
    if len(chain) < WALK_STEPS:
        return
    found.append(TagWalk(tag=tag, at=chain[0].at, steps=len(chain), score=float(len(chain))))


def _require_aware(moment: datetime) -> None:
    """Raise when ``moment`` has no timezone."""
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("setpoint time must be timezone-aware")

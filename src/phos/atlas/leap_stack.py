"""Joint moves and tag walks on one page of eight.

Each checker stays silent on the other's class. The stack reports both, and keeps at
most eight, earliest first. A lone in-band write is still nothing. This does not call
the frozen allocator and does not edit it.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from phos.atlas.consistency import ALERTS_PER_SHIFT
from phos.atlas.joint_setpoint import JointMove, SetpointStep, joint_moves
from phos.atlas.subfloor_walk import TagWalk, subfloor_walks

__all__ = [
    "StackHit",
    "stack_page",
]

logger = logging.getLogger(__name__)

_JOINT: Final = "joint"
_WALK: Final = "walk"


@dataclass(frozen=True)
class StackHit:
    """One slot on the combined page.

    Attributes:
        kind: ``joint`` or ``walk``.
        at: The earliest write of that move or walk.
        name: The tags, or the walked tag.
        score: A count of tags or of steps. Not a confidence.
    """

    kind: str
    at: datetime
    name: str
    score: float


def stack_page(steps: Sequence[SetpointStep]) -> tuple[StackHit, ...]:
    """Return at most eight joint moves and walks.

    Args:
        steps: Setpoint writes the caller supplied.

    Returns:
        The earliest hits, at most `ALERTS_PER_SHIFT`. A one-tag short write is absent.
    """
    hits = [_from_joint(move) for move in joint_moves(steps)]
    hits.extend(_from_walk(walk) for walk in subfloor_walks(steps))
    hits.sort(key=lambda hit: (hit.at, hit.kind, hit.name))
    kept = tuple(hits[:ALERTS_PER_SHIFT])
    logger.info("stack page %s of %s", len(kept), len(hits))
    return kept


def _from_joint(move: JointMove) -> StackHit:
    """One joint move as a page slot."""
    return StackHit(kind=_JOINT, at=move.at, name=",".join(move.tags), score=move.score)


def _from_walk(walk: TagWalk) -> StackHit:
    """One tag walk as a page slot."""
    return StackHit(kind=_WALK, at=walk.at, name=walk.tag, score=walk.score)

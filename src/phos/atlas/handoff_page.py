"""Joint moves, tag walks, and band handoffs on one page of eight.

The stack is silent on a handoff. This page reports all three, earliest first, and
keeps at most eight. It does not edit the stack or either checker, and it does not
call the frozen allocator.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from phos.atlas.band_handoff import band_handoffs
from phos.atlas.consistency import ALERTS_PER_SHIFT
from phos.atlas.joint_setpoint import SetpointStep, joint_moves
from phos.atlas.subfloor_walk import subfloor_walks

__all__ = [
    "PageHit",
    "handoff_page",
]

logger = logging.getLogger(__name__)

_JOINT: Final = "joint"
_WALK: Final = "walk"
_HANDOFF: Final = "handoff"


@dataclass(frozen=True)
class PageHit:
    """One slot on the page that includes handoffs.

    Attributes:
        kind: ``joint``, ``walk``, or ``handoff``.
        at: The earliest write of that move, walk, or handoff.
        name: The tags, or the walked tag.
        score: A count of tags or of steps. Not a confidence.
    """

    kind: str
    at: datetime
    name: str
    score: float


def handoff_page(steps: Sequence[SetpointStep]) -> tuple[PageHit, ...]:
    """Return at most eight joint moves, walks, and handoffs.

    Args:
        steps: Setpoint writes the caller supplied.

    Returns:
        The earliest hits, at most `ALERTS_PER_SHIFT`. A one-tag short write is absent.
    """
    hits: list[PageHit] = []
    for move in joint_moves(steps):
        hits.append(PageHit(_JOINT, move.at, ",".join(move.tags), move.score))
    for walk in subfloor_walks(steps):
        hits.append(PageHit(_WALK, walk.at, walk.tag, walk.score))
    for handoff in band_handoffs(steps):
        hits.append(PageHit(_HANDOFF, handoff.at, ",".join(handoff.tags), handoff.score))
    hits.sort(key=lambda hit: (hit.at, hit.kind, hit.name))
    kept = tuple(hits[:ALERTS_PER_SHIFT])
    logger.info("handoff page %s of %s", len(kept), len(hits))
    return kept

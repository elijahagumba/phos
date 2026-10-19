"""How many facts separate a lead from the next explanation.

A fact separates them when it supports one and contradicts the other. The count is not a
probability. Calibration, if any, is applied by the caller on held-aside development leads.
"""

from __future__ import annotations

from collections.abc import Sequence

__all__ = ["separation_count"]


def separation_count(
    lead_supporting: Sequence[str],
    lead_contradictory: Sequence[str],
    rival_supporting: Sequence[str],
    rival_contradictory: Sequence[str],
) -> int:
    """Return how many facts support one explanation and contradict the other.

    A fact that supports both, or contradicts both, does not separate them. A fact
    counted in either direction is counted once.
    """
    separating = (set(lead_supporting) & set(rival_contradictory)) | (
        set(rival_supporting) & set(lead_contradictory)
    )
    return len(separating)

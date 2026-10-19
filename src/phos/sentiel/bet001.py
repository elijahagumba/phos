"""Rank Bet 001's three declared scores. This module does not read CERT.

ADR 0093 fixed the formulas. ADR 0148 fixes the ranking that the one labelled
run uses: higher score first, then user id, then timestamp. That order is not
chosen to prefer either insider. A day is in the top 48 when it is one of the
first 48 after that sort. Ties at the cut do not widen the budget.

Nothing here changes `AggregationPolicy` or the frozen 6B detector name.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "BUDGET",
    "DayScore",
    "chance_malicious_days",
    "insiders_in_budget",
    "rank_days",
    "top_budget",
]


BUDGET: int = 48


class DayScore(BaseModel):
    """One person-day and one candidate's score.

    Attributes:
        user_id: The corpus user id.
        day: The window timestamp, UTC.
        score: The candidate's score. Not a confidence.
        malicious: Whether a label covers this user on this day. The ranker
            does not read this field.
    """

    model_config = ConfigDict(frozen=True)

    user_id: str = Field(min_length=1)
    day: datetime
    score: float
    malicious: bool = False


def rank_days(days: Sequence[DayScore]) -> tuple[DayScore, ...]:
    """Return ``days`` ordered by ``(-score, user_id, day)``.

    The malicious flag is not part of the key.
    """
    return tuple(sorted(days, key=lambda item: (-item.score, item.user_id, item.day)))


def top_budget(days: Sequence[DayScore], budget: int = BUDGET) -> tuple[DayScore, ...]:
    """Return the first ``budget`` days in `rank_days` order.

    Raises:
        ValueError: If ``budget`` is not positive.
    """
    if budget < 1:
        raise ValueError(f"budget must be positive, got {budget}")
    return rank_days(days)[:budget]


def insiders_in_budget(days: Sequence[DayScore], budget: int = BUDGET) -> frozenset[str]:
    """Return user ids that have a malicious day inside the budget.

    A user is present only when one of their own malicious days was ranked in.
    A benign day of that user does not count.
    """
    return frozenset(item.user_id for item in top_budget(days, budget) if item.malicious)


def chance_malicious_days(n_days: int, n_malicious: int, budget: int = BUDGET) -> float:
    """Return how many malicious days a random budget would hold, in expectation.

    Raises:
        ValueError: If the counts are impossible.
    """
    if n_days < 1:
        raise ValueError(f"n_days must be positive, got {n_days}")
    if not 0 <= n_malicious <= n_days:
        raise ValueError(f"n_malicious {n_malicious} is outside 0..{n_days}")
    if not 1 <= budget <= n_days:
        raise ValueError(f"budget {budget} is outside 1..{n_days}")
    return budget * n_malicious / n_days

"""Depth counting on the six starter counts (ADR 0190).

A day scores as the larger of breadth (the 6B squash over count z-scores) and
depth (the largest z-score divided by the same scale, with no cap). The frozen
``AggregationPolicy`` is not imported and not edited.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable, Sequence

from pydantic import BaseModel, ConfigDict

from phos.sentiel.day_facts import COUNT_FIELDS, DayFacts

__all__ = ["COUNT_SCALE", "MIN_HISTORY", "CountDepth", "breadth_and_depth"]

COUNT_SCALE: float = 3.0
MIN_HISTORY: int = 8


class CountDepth(BaseModel):
    """Per-user mean and sample standard deviation of the six counts.

    Attributes:
        means: ``user_id -> field -> mean`` on the attack-free prefix.
        stdevs: ``user_id -> field -> sample standard deviation``.
        history: How many training days each user contributed.
    """

    model_config = ConfigDict(frozen=True)

    means: dict[str, dict[str, float]]
    stdevs: dict[str, dict[str, float]]
    history: dict[str, int]

    @classmethod
    def fit(cls, train: Sequence[DayFacts]) -> CountDepth:
        """Fit one baseline per user from the attack-free prefix."""
        values: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        for day in train:
            for field in COUNT_FIELDS:
                values[day.user_id][field].append(float(day.count(field)))
        means: dict[str, dict[str, float]] = {}
        stdevs: dict[str, dict[str, float]] = {}
        history: dict[str, int] = {}
        for user, fields in values.items():
            n = len(fields[COUNT_FIELDS[0]])
            history[user] = n
            means[user] = {}
            stdevs[user] = {}
            for field in COUNT_FIELDS:
                series = fields[field]
                mean = sum(series) / n
                means[user][field] = mean
                if n < 2:
                    stdevs[user][field] = 0.0
                    continue
                variance = sum((item - mean) ** 2 for item in series) / (n - 1)
                stdevs[user][field] = math.sqrt(variance)
        return cls(means=means, stdevs=stdevs, history=history)

    def magnitudes(self, day: DayFacts) -> tuple[float, ...]:
        """Return absolute z-scores, or an empty tuple when history is too short."""
        if self.history.get(day.user_id, 0) < MIN_HISTORY:
            return ()
        user_means = self.means[day.user_id]
        user_stdevs = self.stdevs[day.user_id]
        out: list[float] = []
        for field in COUNT_FIELDS:
            spread = user_stdevs[field]
            if spread <= 0.0:
                spread = 1.0
            out.append(abs(float(day.count(field)) - user_means[field]) / spread)
        return tuple(out)

    def score(self, day: DayFacts) -> float:
        """Return ``max(breadth, depth)`` for ``day``."""
        return breadth_and_depth(self.magnitudes(day))[2]


def breadth_and_depth(
    magnitudes: Iterable[float], scale: float = COUNT_SCALE
) -> tuple[float, float, float]:
    """Return ``(breadth, depth, max of the two)`` from already-computed magnitudes.

    Raises:
        ValueError: If ``scale`` is not positive.
    """
    if scale <= 0.0:
        raise ValueError(f"scale must be positive, got {scale}")
    values = [float(item) for item in magnitudes if item > 0.0]
    if not values:
        return (0.0, 0.0, 0.0)
    breadth = sum(1.0 - math.exp(-item / scale) for item in values)
    depth = max(values) / scale
    return (breadth, depth, max(breadth, depth))

"""Four checks on the frozen candidate, declared before they run.

ADR 0105. Nothing here scores a corpus. The command that does is
``scripts/measure_candidate_checks.py``, and it refuses a second start.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

import numpy
from numpy.random import Generator
from numpy.typing import NDArray

CHANCE_SEED = 20261010
CHANCE_DRAWS = 500
ALERTS_PER_SHIFT = 8
SHIFT_SECONDS = 8 * 3600
DRIVER_SHARE_ABOVE = 0.20
CANDIDATE_CAUGHT: Mapping[str, tuple[int, int]] = {
    "hai-22.04": (53, 58),
    "hai-23.05": (36, 52),
}
MINMAX_EVENTS_RELATIVE = "experiments/2026-10-04-sandbox/controls/minmax_events/candidate.py"
NO_LOOP_RELATIVE = "experiments/2026-10-04-sandbox/controls/no_loop/candidate.py"
MINMAX_EVENTS_SHA256 = "c9ff81dead9ff0154b83c276772d93149fad4e0b5f6b815fdd824c35321b5a0d"
NO_LOOP_SHA256 = "91d462d78d210fea8aac6f432f1019ffee6b4ce948e6895dc4cab6f5d516bd91"
CHECKS_JSON_NAME = "g1-candidate-checks.json"
HAI_DETAILS_PIN = "2a814ceb"
QUANTILE_METHOD: Literal["linear"] = "linear"


@dataclass(frozen=True)
class ChanceSummary:
    """One edition's random-alert draws. Caught counts, not a rate."""

    draws: int
    mean_caught: float
    percentile_95: float
    max_caught: int


@dataclass(frozen=True)
class DriverChoice:
    """The kept alert that stands for one caught attack."""

    row: int
    feature: str
    score: float


def summarise_chance(caught: NDArray[numpy.int64]) -> ChanceSummary:
    """Mean, linear 95th percentile, and max of one draw per entry."""
    if caught.ndim != 1 or caught.size == 0:
        raise ValueError("chance draws must be a non-empty vector")
    counts = numpy.asarray(caught, dtype=numpy.int64)
    floated = counts.astype(numpy.float64)
    return ChanceSummary(
        draws=int(counts.size),
        mean_caught=float(floated.mean()),
        percentile_95=float(numpy.quantile(floated, 0.95, method=QUANTILE_METHOD)),
        max_caught=int(counts.max()),
    )


def shift_ids(time: NDArray[numpy.float64]) -> NDArray[numpy.int64]:
    """8-hour shift index from the first timestamp, matching the candidate."""
    if time.ndim != 1 or time.size == 0:
        raise ValueError("time must be a non-empty vector")
    return numpy.asarray((time - time[0]) // SHIFT_SECONDS, dtype=numpy.int64)


def draw_rows(
    row_indexes: NDArray[numpy.int64],
    shifts: NDArray[numpy.int64],
    rng: Generator,
    per_shift: int = ALERTS_PER_SHIFT,
) -> NDArray[numpy.int64]:
    """Eight distinct rows per shift. A shorter shift contributes all of its rows."""
    if row_indexes.shape != shifts.shape:
        raise ValueError("each row needs one shift")
    if per_shift < 1:
        raise ValueError("per_shift must be positive")
    chosen: list[NDArray[numpy.int64]] = []
    for shift in numpy.unique(shifts):
        pool = row_indexes[shifts == shift]
        take = min(per_shift, int(pool.size))
        chosen.append(rng.choice(pool, size=take, replace=False).astype(numpy.int64))
    if not chosen:
        return numpy.empty(0, dtype=numpy.int64)
    return numpy.concatenate(chosen)


def larger_component(range_score: float, loop_score: float) -> str:
    """Which of the two ``_raw_scores`` inputs is larger. Equal is a tie."""
    if range_score > loop_score:
        return "range"
    if loop_score > range_score:
        return "loop"
    return "tie"


def choose_driver(alerts: Sequence[tuple[int, str, float]]) -> DriverChoice:
    """Greatest event score, then the earliest row, then the feature name."""
    if not alerts:
        raise ValueError("a caught attack needs a kept alert")
    row, feature, score = min(alerts, key=lambda alert: (-alert[2], alert[0], alert[1]))
    return DriverChoice(row=row, feature=feature, score=score)


def flagged_features(counts: Mapping[str, int], caught: int) -> tuple[str, ...]:
    """Features whose share of caught attacks is strictly above 20 percent."""
    if caught < 1:
        return ()
    return tuple(
        sorted(feature for feature, count in counts.items() if count / caught > DRIVER_SHARE_ABOVE)
    )


def same_alert_list(left: Sequence[tuple[int, str]], right: Sequence[tuple[int, str]]) -> bool:
    """True when the two point-adjusted lists carry the same row and feature."""
    return sorted(left) == sorted(right)

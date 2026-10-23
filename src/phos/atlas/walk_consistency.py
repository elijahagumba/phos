"""The valve the pinned PLC1 line would write, one sample at a time.

ADR 0301 specifies this column and does not build it. ADR 0313 is the gate: the
champions missed one slow walk, so the column may exist. It is not a running sum.
Samples inside the band are zero, because the quoted logic does not move the valve
there. The frozen detector is not edited.

The constants are copied from ICSSim `src/PLC1.py` at `bcfd184`. Above
`tank_level_max` that line writes 0. Below `tank_level_min` it writes the constant
1. A min branch that did not write a constant would be a refusal, and this module
would not exist.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

import numpy
from numpy.typing import NDArray

from phos.atlas.consistency import (
    CALIBRATION_RANK,
    ONSET_LEVEL,
    THRESHOLD,
    ConsistencyModel,
    _all_episodes,
    feature_scores,
)

__all__ = [
    "LEVEL_MAX",
    "LEVEL_MIN",
    "LEVEL_VALUE",
    "RESULT_NAME",
    "VALVE_ABOVE_MAX",
    "VALVE_BELOW_MIN",
    "VALVE_STATUS",
    "WalkModel",
    "augmented_scores",
    "count_later",
    "fit_walk",
    "raw_walk_column",
    "walk_divisor",
]

logger = logging.getLogger(__name__)

RESULT_NAME: Final = "atlas-walk-consistency"
"""The result name of this column. Not a champion until a kept score says so."""

LEVEL_VALUE: Final = "tank_level_value"
LEVEL_MIN: Final = "tank_level_min"
LEVEL_MAX: Final = "tank_level_max"
VALVE_STATUS: Final = "tank_input_valve_status"

VALVE_ABOVE_MAX: Final = 0.0
"""What PLC1 writes when the level is strictly above `tank_level_max`."""

VALVE_BELOW_MIN: Final = 1.0
"""What PLC1 writes when the level is strictly below `tank_level_min`. A constant."""

_Float64 = NDArray[numpy.float64]
_Float32 = NDArray[numpy.float32]


@dataclass(frozen=True)
class WalkModel:
    """The frozen model plus this column's calibration.

    Attributes:
        base: The per-signal model. Not edited.
        divisor: The third-largest raw peak on the training runs, or 1.0.
        level: Column of `tank_level_value`.
        level_min: Column of `tank_level_min`.
        level_max: Column of `tank_level_max`.
        valve: Column of `tank_input_valve_status`.
    """

    base: ConsistencyModel
    divisor: float
    level: int
    level_min: int
    level_max: int
    valve: int


def raw_walk_column(
    level: _Float64,
    level_min: _Float64,
    level_max: _Float64,
    valve: _Float64,
) -> _Float32:
    """Return the uncalibrated per-sample error against the pinned valve.

    Args:
        level: `tank_level_value` at each sample.
        level_min: `tank_level_min` at each sample.
        level_max: `tank_level_max` at each sample.
        valve: `tank_input_valve_status` at each sample.

    Returns:
        Absolute error times `ONSET_LEVEL` outside the band, and 0 inside it.
        One value per sample. A correct valve is 0. The next sample does not
        inherit this one.

    Raises:
        ValueError: If the arrays differ in length, or a sample is both above
            the max and below the min.
    """
    if not (level.shape == level_min.shape == level_max.shape == valve.shape):
        raise ValueError("walk columns must be the same length")
    above = level > level_max
    below = level < level_min
    if bool(numpy.any(above & below)):
        raise ValueError("level is above max and below min in the same sample")
    error = numpy.zeros(level.shape, dtype=numpy.float64)
    error[above] = numpy.abs(VALVE_ABOVE_MAX - valve[above])
    error[below] = numpy.abs(VALVE_BELOW_MIN - valve[below])
    return (error * ONSET_LEVEL).astype(numpy.float32)


def walk_divisor(peaks: Sequence[float]) -> float:
    """Return the third-largest peak, and at least 1.0.

    Args:
        peaks: Episode peaks of the uncalibrated column on attack-free runs.

    Returns:
        1.0 when fewer than `CALIBRATION_RANK` peaks exist. Otherwise the
        rank-th largest, floored at 1.0. The same rule `fit_commands` uses.
    """
    if len(peaks) < CALIBRATION_RANK:
        return 1.0
    return max(1.0, float(sorted(peaks)[-CALIBRATION_RANK]))


def _index(keys: Sequence[str], name: str) -> int:
    try:
        return keys.index(name)
    except ValueError as exc:
        raise ValueError(f"walk column requires {name}") from exc


def _peaks(model: WalkModel, values: _Float64) -> list[float]:
    raw = raw_walk_column(
        values[:, model.level],
        values[:, model.level_min],
        values[:, model.level_max],
        values[:, model.valve],
    )
    series = raw.reshape(-1, 1)
    return [
        peak
        for _start, _end, peak, _at, _column in _all_episodes(
            series, THRESHOLD, model.base.windows.feature_gap
        )
    ]


def fit_walk(
    model: ConsistencyModel,
    training: Sequence[_Float64],
    keys: Sequence[str],
) -> WalkModel:
    """Learn the walk-column divisor from attack-free runs.

    Args:
        model: The fitted per-signal model. Its bytes are not changed.
        training: One value matrix per attack-free run, columns in `keys` order.
        keys: Signal names, in that same order.

    Returns:
        The walk model. The divisor is 1.0 when training has too few peaks.
    """
    partial = WalkModel(
        base=model,
        divisor=1.0,
        level=_index(keys, LEVEL_VALUE),
        level_min=_index(keys, LEVEL_MIN),
        level_max=_index(keys, LEVEL_MAX),
        valve=_index(keys, VALVE_STATUS),
    )
    peaks: list[float] = []
    for values in training:
        peaks.extend(_peaks(partial, values))
    divisor = walk_divisor(peaks)
    logger.info("walk column divisor %.4f from %s peaks", divisor, len(peaks))
    return WalkModel(
        base=model,
        divisor=divisor,
        level=partial.level,
        level_min=partial.level_min,
        level_max=partial.level_max,
        valve=partial.valve,
    )


def augmented_scores(model: WalkModel, values: _Float64) -> _Float32:
    """Return the per-signal scores with the calibrated walk column appended.

    The result has one more column than `feature_scores` and goes through the
    unchanged `events` and `budget_alerts`. Dividing by the divisor is the only
    change to the raw column.
    """
    raw = raw_walk_column(
        values[:, model.level],
        values[:, model.level_min],
        values[:, model.level_max],
        values[:, model.valve],
    )
    column = (raw / numpy.float32(model.divisor)).reshape(-1, 1)
    plain = feature_scores(model.base, values)
    return numpy.concatenate([plain, column], axis=1).astype(numpy.float32)


def count_later(
    windows: Sequence[tuple[float, float]],
    champion: Sequence[float],
    candidate: Sequence[float],
) -> int:
    """Count windows both catch where the candidate's earliest alert is later.

    Args:
        windows: Inclusive event windows, `(start, end)`.
        champion: Budgeted alert times of the champion.
        candidate: Budgeted alert times of this column's detector.

    Returns:
        How many windows fail the "not later" bar. A window only one of them
        catches is not counted.
    """

    def earliest(times: Sequence[float], start: float, end: float) -> float | None:
        inside = [at for at in times if start <= at <= end]
        if not inside:
            return None
        return min(inside)

    later = 0
    for start, end in windows:
        old = earliest(champion, start, end)
        new = earliest(candidate, start, end)
        if old is not None and new is not None and new > old:
            later += 1
    return later

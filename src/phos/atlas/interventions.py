"""Grade B of the plant model: links seen to propagate from a logged change (ADR 0130, ADR 0132).

Watching normal data cannot tell, inside a closed loop, which signal moves which. A logged change
can: when someone writes a new value to point *T* (an operator's setpoint, a mode, a work order's
action), whatever responds afterwards was moved by that write, not the other way round. So each
logged change is a small experiment, and a link *T* -> *S* is **intervened** when *S* responds to
the changes on *T*, again and again, and never moves first.

**A response** is a shift in *S*'s mean: its mean over the horizon after the change against its
mean over the horizon before. It counts when the shift is beyond what that signal's own shift
reaches at ordinary moments of the same training data (the `NULL_QUANTILE` of shifts measured at
every `NULL_STRIDE_SECONDS`, away from any change). **Moving first** is the same test one horizon
earlier: a signal already shifting before the change cannot be credited to it.

**A link** needs at least `MIN_CHANGES` changes on *T*, a response to at least `AGREEMENT` of
them, and no change at which *S* moved first. These constants are ADR 0132's, set before any
score. A logged change is not a randomised experiment: an operator changes things for reasons,
and a coincident disturbance can pass for a response. The agreement rule and "never first" are
the guard, not a proof.

Nothing here reads a label, a truth record or a declared coupling.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

import numpy
from numpy.typing import NDArray

from phos.atlas.plant_map_model import samples_for

__all__ = [
    "AGREEMENT",
    "HORIZON_SECONDS",
    "MIN_CHANGES",
    "NULL_QUANTILE",
    "NULL_STRIDE_SECONDS",
    "IntervenedLink",
    "Intervention",
    "intervened_links",
]

#: How long after a change a response may take, and how long a mean is taken over.
HORIZON_SECONDS: Final = 120
#: A shift counts when it exceeds this quantile of the signal's ordinary shifts.
NULL_QUANTILE: Final = 0.99
#: Ordinary shifts are measured every this many seconds.
NULL_STRIDE_SECONDS: Final = 30
#: A link needs at least this many changes on its driver.
MIN_CHANGES: Final = 3
#: And a response to at least this share of them.
AGREEMENT: Final = 2 / 3

_Float = NDArray[numpy.float64]


@dataclass(frozen=True)
class Intervention:
    """A logged change: a new value written to ``point`` at ``row`` of training file ``file``."""

    file: int
    row: int
    point: str


@dataclass(frozen=True)
class IntervenedLink:
    """``driver`` -> ``driven``: it responded to ``responses`` of ``changes`` logged changes."""

    driver: str
    driven: str
    changes: int
    responses: int
    moved_first: int


def _shift(column: _Float, row: int, horizon: int) -> float:
    """``|mean(after) - mean(before)|`` around ``row``; NaN where either window is cut off."""
    if row - horizon < 0 or row + horizon > column.size:
        return math.nan
    return float(abs(column[row : row + horizon].mean() - column[row - horizon : row].mean()))


def _thresholds(
    files: Sequence[_Float], changes: Sequence[Intervention], horizon: int, stride: int
) -> _Float:
    """Each signal's `NULL_QUANTILE` shift at ordinary moments, two horizons from any change."""
    columns = files[0].shape[1]
    shifts: list[list[float]] = [[] for _ in range(columns)]
    for index, values in enumerate(files):
        near = numpy.zeros(values.shape[0], dtype=bool)
        for change in changes:
            if change.file == index:
                near[max(0, change.row - 2 * horizon) : change.row + 2 * horizon] = True
        for row in range(2 * horizon, values.shape[0] - horizon, stride):
            if near[row]:
                continue
            for j in range(columns):
                shifts[j].append(_shift(values[:, j], row, horizon))
    out = numpy.full(columns, numpy.inf)
    for j, found in enumerate(shifts):
        finite = [s for s in found if math.isfinite(s)]
        if finite:
            out[j] = float(numpy.quantile(finite, NULL_QUANTILE))
    return out


def intervened_links(
    files: Sequence[_Float],
    names: Sequence[str],
    changes: Sequence[Intervention],
    period_seconds: float,
) -> tuple[IntervenedLink, ...]:
    """Every grade-B link the logged changes support, in (driver, driven) order.

    Args:
        files: Attack-free files, rows by signals, one sample every ``period_seconds``.
        names: One name per column.
        changes: The logged changes in those files.
        period_seconds: Seconds between samples; the horizon and stride convert by ADR 0112.
    """
    horizon = samples_for(HORIZON_SECONDS, period_seconds)
    stride = samples_for(NULL_STRIDE_SECONDS, period_seconds)
    threshold = _thresholds(files, changes, horizon, stride)
    by_point: dict[str, list[Intervention]] = {}
    for change in changes:
        by_point.setdefault(change.point, []).append(change)
    links: list[IntervenedLink] = []
    for point in sorted(by_point):
        events = by_point[point]
        if len(events) < MIN_CHANGES:
            continue
        for j, name in enumerate(names):
            if name == point or not math.isfinite(threshold[j]):
                continue
            responses = first = 0
            for change in events:
                column = files[change.file][:, j]
                before = _shift(column, change.row - horizon, horizon)
                after = _shift(column, change.row, horizon)
                if math.isfinite(before) and before > threshold[j]:
                    first += 1
                elif math.isfinite(after) and after > threshold[j]:
                    responses += 1
            if first == 0 and responses >= AGREEMENT * len(events):
                links.append(IntervenedLink(point, name, len(events), responses, first))
    return tuple(links)

"""Judge the signals together, not one at a time. Lane 2 of the stronger-engine programme.

`phos.atlas.consistency` scores every signal on its own and opens an episode only where *that*
signal crosses `THRESHOLD`. Two consequences follow by construction, before any measurement:

- An attack spread thinly across many signals, none of them individually over the threshold, opens
  no episode anywhere and is invisible.
- A signal that is hypersensitive on one plant supplies a large share of the catches, because
  nothing else is competing for the same evidence. On HAI 22.04 one tag, `P1_PCV01D`, drives 11 of
  the frozen detector's 53 catches (ADR 0106).

This module adds one extra column to the score matrix and changes nothing else. The column is a
**breadth** statistic: how many signals' worth of departure is present at this sample, counting no
single signal more than once.

    breadth_raw[i] = sum over j of min(score[i, j], THRESHOLD)

The cap is the whole point. A signal already at or past alerting level contributes exactly one unit
and no more, so depth in one instrument cannot drive the column — only breadth across instruments
can. The column is then calibrated by the rule `phos.atlas.consistency.fit` already uses per signal:
divide by the third-largest episode peak the statistic reaches on attack-free training, floored at
1.0, so `THRESHOLD` means on this column what it means on every other.

The augmented matrix goes through the unchanged `events` and `budget_alerts`, so the breadth column
competes with the per-signal columns for the same shift budget rather than being added on top of it.
An alert attributed to the breadth column is reported as such: its meaning is "many signals are
mildly inconsistent at once", not "this instrument is wrong".

**Nothing here edits the frozen detector.** `atlas-v1-consistency` is on the frozen list in
`docs/rules/data-tiers.md`. This is a separate detector under a separate name, measured beside it
(ADR 0273). Result name for anything this module scores: ``atlas-breadth-consistency``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy
from numpy.typing import NDArray

from phos.atlas.consistency import (
    CALIBRATION_RANK,
    THRESHOLD,
    ConsistencyModel,
    _all_episodes,
    feature_scores,
)

__all__ = [
    "BREADTH_COLUMN",
    "BreadthModel",
    "augmented_scores",
    "breadth_raw",
    "calibrate_breadth",
]

_Float32 = NDArray[numpy.float32]
_Float64 = NDArray[numpy.float64]

#: The name the extra column carries wherever columns are named.
BREADTH_COLUMN: Final = "__breadth__"


@dataclass(frozen=True)
class BreadthModel:
    """A fitted `ConsistencyModel` plus the divisor for the breadth column.

    Attributes:
        base: The per-signal model, unchanged. Never edited by this module.
        divisor: The breadth column's calibration, floored at 1.0, from attack-free training.
    """

    base: ConsistencyModel
    divisor: float


def breadth_raw(scores: _Float32) -> _Float32:
    """Return the uncalibrated breadth statistic, one value per row.

    Each signal contributes ``min(score, THRESHOLD)``, so a single signal can add at most one unit
    however far past the threshold it goes. The sum therefore counts how many signals are at or
    near alerting level, which is breadth rather than depth.

    Args:
        scores: Rows by signals, as `phos.atlas.consistency.feature_scores` returns them.

    Returns:
        One value per row, same row count as ``scores``.
    """
    capped = numpy.minimum(scores, numpy.float32(THRESHOLD))
    total: _Float32 = capped.sum(axis=1, dtype=numpy.float32)
    return total


def calibrate_breadth(model: ConsistencyModel, benign: _Float64, feature_gap: int) -> float:
    """Return the breadth divisor from attack-free training, by the engine's own rule.

    The rule is `phos.atlas.consistency.fit`'s: take the episode peaks the statistic reaches above
    ``THRESHOLD``, and use the ``CALIBRATION_RANK``-th largest, floored at 1.0. Fewer peaks than
    that rank means the statistic is quiet on training and needs no scaling.

    Args:
        model: The fitted per-signal model.
        benign: Attack-free training rows by signals, the same matrix `fit` was given.
        feature_gap: ``model.windows.feature_gap``, so episodes are cut the same way.

    Returns:
        The divisor, at least 1.0.
    """
    raw = breadth_raw(feature_scores(model, benign)).reshape(-1, 1)
    peaks = [peak for _s, _e, peak, _at, _j in _all_episodes(raw, THRESHOLD, feature_gap)]
    if len(peaks) < CALIBRATION_RANK:
        return 1.0
    return max(1.0, float(sorted(peaks)[-CALIBRATION_RANK]))


def augmented_scores(model: BreadthModel, values: _Float64) -> _Float32:
    """Return the per-signal scores with the calibrated breadth column appended.

    The returned matrix has one more column than ``values``. Everything downstream —
    `phos.atlas.consistency.events`, `budget_alerts` — takes it unchanged, so the breadth column
    competes for the same shift budget as the signals rather than being added on top of it.

    Args:
        model: The breadth model, carrying the per-signal model and the breadth divisor.
        values: Rows by signals.

    Returns:
        Rows by signals plus one. The last column is the breadth column.
    """
    scores = feature_scores(model.base, values)
    column = (breadth_raw(scores) / numpy.float32(model.divisor)).astype(numpy.float32)
    return numpy.concatenate([scores, column.reshape(-1, 1)], axis=1).astype(numpy.float32)

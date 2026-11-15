"""Is a commanded setpoint being held, or walked?

Q-0001 asks whether the walk column's 1-of-9 miss is an artefact of thresholding a per-sample score
under a saturated calibration, or a property of the class that no per-sample comparison can see.
This module supplies the statistic that separates those: not "how far is this reading from what was
expected", but "how many samples in a row has this value been *moving*".

**Why a run, and why this tag.** A setpoint write is a discrete act: the register takes a new value
once and then holds. A slow walk is the same register moving at every sample for the length of the
walk. Per-sample, both are ordinary — an in-band value is an in-band value, which is exactly the
observation ADR 0315 records ("a full valve error is `ONSET_LEVEL` before that division"). In time,
they are not alike at all: the write's run is 1 and the walk's run is its whole length. The
statistic is order-dependent by construction, so a permutation of the same values changes it.

The tag is `tank_level_max` specifically, not every signal. `tank_level_value` ramps continuously as
the tank fills, so a run statistic applied to it fires on normal operation. The discriminator is not
"the value moved"; it is "a **commanded** setpoint moved continuously", which no legitimate write
does. That makes this a plant-map claim as much as a statistical one: it needs to know which tags
are written by an operator rather than driven by physics.

**What this is not.** It is not a detector and not a champion. Nothing here calibrates a
probability, sets a weight, or picks a rank. The threshold is learned — the longest run that
attack-free training produced — and it is floored at zero rather than at a constant, because a
training set whose setpoint never moved has told us nothing permissive.

The composition is deliberate: `sequential_scores` returns one column, and the caller passes it
through the frozen `events` and `budget_alerts` unchanged. That keeps the alert machinery the same
as the column it is compared with, so a difference between the two is the statistic and not the
budget.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

import numpy
from numpy.typing import NDArray

__all__ = [
    "RESULT_NAME",
    "SLID_TAG",
    "SequentialModel",
    "change_run",
    "fit_sequential",
    "sequential_scores",
]

logger = logging.getLogger(__name__)

RESULT_NAME: Final = "atlas-sequential-consistency"
"""The result name this column records under. A name, not a promotion."""

SLID_TAG: Final = "tank_level_max"
"""The commanded setpoint the run is measured on. A tag a write moves, not the physics."""

_Float32 = NDArray[numpy.float32]
_Float64 = NDArray[numpy.float64]


@dataclass(frozen=True)
class SequentialModel:
    """The learned run threshold and where the tag sits.

    Attributes:
        column: Index of `SLID_TAG` in the corpus's column order.
        longest_run: The longest consecutive-change run in attack-free training. Zero when the
            setpoint never moved, which makes every run an event.
    """

    column: int
    longest_run: int


def change_run(series: _Float64) -> _Float32:
    """Return, per sample, how many samples in a row the value has been changing.

    A sample whose value equals the previous one resets the count to zero. The first sample has no
    predecessor and is zero.

    Args:
        series: One signal, ascending in time.

    Returns:
        One float per sample. A held value is 0; a single write is 1 on the sample it lands and 0
        after it; a value that moves every sample counts 1, 2, 3, ...

    Raises:
        ValueError: If ``series`` is not one-dimensional.

    Note:
        Equality is exact. On a corpus whose telemetry is rounded to a fixed number of decimals, a
        true change smaller than that resolution is not distinguishable from a hold, and is counted
        as one. That is a property of the recorded data, not a tolerance chosen here.
    """
    if series.ndim != 1:
        raise ValueError(f"change_run takes a one-dimensional series, got shape {series.shape}")
    run = numpy.zeros(series.shape[0], dtype=numpy.float64)
    count = 0
    for index in range(1, series.shape[0]):
        if series[index] != series[index - 1]:
            count += 1
        else:
            count = 0
        run[index] = count
    return run.astype(numpy.float32)


def _column(keys: Sequence[str], tag: str) -> int:
    """Return the index of ``tag``, naming it when it is absent."""
    try:
        return list(keys).index(tag)
    except ValueError as exc:
        raise ValueError(f"the sequential column requires {tag}") from exc


def fit_sequential(keys: Sequence[str], training: Sequence[_Float64]) -> SequentialModel:
    """Learn the longest run that attack-free operation produced.

    Args:
        keys: The corpus's signal names, in the column order of ``training``.
        training: One value matrix per attack-free run.

    Returns:
        The model. ``longest_run`` is the largest run over every training sample.

    Raises:
        ValueError: If there is no training run, or ``keys`` has no `SLID_TAG`.
    """
    if not training:
        raise ValueError("a sequential fit needs at least one training run")
    column = _column(keys, SLID_TAG)
    longest = 0
    for values in training:
        observed = float(change_run(values[:, column]).max(initial=0.0))
        longest = max(longest, int(observed))
    logger.info("sequential column longest attack-free run %s samples", longest)
    return SequentialModel(column=column, longest_run=longest)


def sequential_scores(model: SequentialModel, values: _Float64) -> _Float32:
    """Return the run column for one scored file, shaped as `events` expects.

    Args:
        model: The learned run threshold and column.
        values: Rows by signals, in the order the model was fitted on.

    Returns:
        Rows by one signal. Nothing is calibrated and no constant is applied: the column is the
        run length itself, and `events` reads it against the learned threshold.
    """
    return change_run(values[:, model.column]).reshape(-1, 1)

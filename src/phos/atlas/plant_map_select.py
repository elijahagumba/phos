"""Forward selection of lagged terms on time-blocked cross-validated error (ADR 0123 §2).

Everything here works from Gram matrices, one per fold: the training rows are split into
contiguous blocks in time, and a fold's model is solved from every other block's Gram. The error
of a term set is exact out-of-block squared error, computed from the held-out block's Gram, so
selection never needs the rows again. Candidates are scored in one batched solve per fold.

The columns of a Gram are laid out by `Layout`: every candidate term ``(driver, lag)``, then each
target's level, then each target's one-sample increment, then a column of ones.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy
from numpy.typing import NDArray

__all__ = ["Layout", "Selection", "accumulate", "cv_sse", "fold_coefficients", "select_terms"]

_Float = NDArray[numpy.float64]
_Int = NDArray[numpy.int64]


@dataclass(frozen=True)
class Layout:
    """Where each quantity sits among a Gram's columns.

    Attributes:
        drivers: Signal column of each candidate term.
        lags: Lag in samples of each candidate term.
        targets: Signal columns that may be targets, in order.
    """

    drivers: _Int
    lags: _Int
    targets: _Int

    @property
    def n_terms(self) -> int:
        """Candidate terms."""
        return int(self.drivers.size)

    def level_column(self, target: int) -> int:
        """The Gram column holding a target's level."""
        return self.n_terms + int(numpy.flatnonzero(self.targets == target)[0])

    def increment_column(self, target: int) -> int:
        """The Gram column holding a target's one-sample increment."""
        return self.n_terms + self.targets.size + int(numpy.flatnonzero(self.targets == target)[0])

    @property
    def ones(self) -> int:
        """The Gram column of ones."""
        return self.n_terms + 2 * int(self.targets.size)

    @property
    def width(self) -> int:
        """Columns in a Gram."""
        return self.ones + 1


def accumulate(
    grams: _Float, z: _Float, rows: _Int, folds: _Int, layout: Layout, chunk: int = 20_000
) -> None:
    """Add one file's rows to the per-fold Grams, in place.

    Args:
        grams: ``(folds, width, width)``, added to.
        z: The file's standardised values, rows by signals.
        rows: Rows entering the fit; each needs every lag and one previous sample.
        folds: Each row's fold.
        layout: The column layout.
        chunk: Rows built at a time, to bound memory.
    """
    for start in range(0, rows.size, chunk):
        part = rows[start : start + chunk]
        fold_of = folds[start : start + chunk]
        matrix = numpy.empty((part.size, layout.width))
        matrix[:, : layout.n_terms] = z[part[:, None] - layout.lags[None, :], layout.drivers]
        level = z[part][:, layout.targets]
        matrix[:, layout.n_terms : layout.n_terms + layout.targets.size] = level
        previous = z[part - 1][:, layout.targets]
        matrix[:, layout.n_terms + layout.targets.size : layout.ones] = level - previous
        matrix[:, layout.ones] = 1.0
        for fold in numpy.unique(fold_of):
            block = matrix[fold_of == fold]
            grams[fold] += block.T @ block


def _solve_sse(
    grams: _Float, total: _Float, columns: _Int, extra: _Int, y: int, ridge: float
) -> _Float:
    """Out-of-block SSE of ``columns`` plus each one of ``extra``, summed over folds.

    Returns one SSE per entry of ``extra``; with ``extra`` empty, one SSE for ``columns`` alone.
    """
    n_extra = max(int(extra.size), 1)
    sets = (
        numpy.repeat(columns[None, :], n_extra, axis=0)
        if extra.size == 0
        else numpy.hstack([numpy.repeat(columns[None, :], n_extra, axis=0), extra[:, None]])
    )
    size = sets.shape[1]
    sse = numpy.zeros(n_extra)
    eye = ridge * numpy.eye(size)
    rows_index = sets[:, :, None]
    cols_index = sets[:, None, :]
    for fold in range(grams.shape[0]):
        held = grams[fold]
        train = total - held
        a = train[rows_index, cols_index] + eye
        b = train[sets, y]
        beta = numpy.linalg.solve(a, b[..., None])[..., 0]
        cross = held[sets, y]
        quad = numpy.einsum("ni,nij,nj->n", beta, held[rows_index, cols_index], beta)
        sse += held[y, y] - 2.0 * numpy.einsum("ni,ni->n", beta, cross) + quad
    return sse


def cv_sse(grams: _Float, terms: Sequence[int], y: int, ones: int, ridge: float) -> float:
    """Out-of-block squared error of one term set (plus the intercept), summed over folds."""
    total = grams.sum(axis=0)
    columns = numpy.asarray([*terms, ones], dtype=numpy.int64)
    return float(_solve_sse(grams, total, columns, numpy.empty(0, numpy.int64), y, ridge)[0])


def fold_coefficients(
    gram: _Float, terms: Sequence[int], y: int, ones: int, ridge: float
) -> _Float:
    """Ridge coefficients of ``terms`` then the intercept, solved from one Gram."""
    columns = numpy.asarray([*terms, ones], dtype=numpy.int64)
    a = gram[numpy.ix_(columns, columns)] + ridge * numpy.eye(columns.size)
    solved: _Float = numpy.linalg.solve(a, gram[columns, y])
    return solved


@dataclass(frozen=True)
class Selection:
    """The terms chosen for one target in one form, and their cross-validated error."""

    terms: tuple[int, ...]
    sse: float
    baseline_sse: float


def select_terms(
    grams: _Float,
    layout: Layout,
    y: int,
    allowed: NDArray[numpy.bool_],
    max_drivers: int,
    max_lags_per_driver: int,
    min_gain: float,
    ridge: float,
) -> Selection:
    """Forward stepwise selection of candidate terms for one Gram column ``y``.

    Each step adds the allowed term that most lowers out-of-block error; it stops when the best
    reduction is under ``min_gain`` of the current error, or no allowed term remains under the
    caps. Ties go to the lowest candidate index, which is signal order then lag order.
    """
    total = grams.sum(axis=0)
    chosen: list[int] = []
    ones = layout.ones
    current = cv_sse(grams, [], y, ones, ridge)
    baseline = current
    while True:
        drivers = layout.drivers[chosen] if chosen else numpy.empty(0, numpy.int64)
        names, counts = numpy.unique(drivers, return_counts=True)
        full = names[counts >= max_lags_per_driver]
        mask = allowed.copy()
        mask[chosen] = False
        mask &= ~numpy.isin(layout.drivers, full)
        if names.size >= max_drivers:
            mask &= numpy.isin(layout.drivers, names)
        candidates = numpy.flatnonzero(mask)
        if candidates.size == 0:
            break
        base = numpy.asarray([*chosen, ones], dtype=numpy.int64)
        sse = _solve_sse(grams, total, base, candidates, y, ridge)
        best = int(numpy.argmin(sse))
        if current - sse[best] < min_gain * current:
            break
        chosen.append(int(candidates[best]))
        current = float(sse[best])
    return Selection(terms=tuple(chosen), sse=current, baseline_sse=baseline)

"""Let the prediction bend. Lane 4 of the stronger-engine programme (ADR 0273).

`phos.atlas.consistency` asks the right question — predict each signal from every **other** signal,
now and at four lags — and answers it with one ridge regression per signal. The question is kept
here exactly. Only the answer changes.

A linear answer has two costs the brief names. During ordinary non-linear operation — a valve
saturating, a controller sitting in its deadband, a plant moving between phases — a straight line
cannot follow the relationship, so it leaves a *structured* error that is not an attack, and that
error is paid for in false alarms. And an attacker who moves a reading inside the region a straight
line cannot represent is invisible, because the line was never predicting that region correctly in
the first place.

**The bend is a hinge basis, and it is still a linear model.** Each standardised input ``x`` is
expanded to

    [x, max(0, x - t_1), ..., max(0, x - t_k)]

for knots ``t`` taken from the attack-free training distribution of that signal. A weighted sum of
hinges is a piecewise-linear function of ``x``: give the later hinges negative weight and the
response flattens, which is **saturation**; give a middle stretch zero slope and it is a
**deadband**; change slope at a knot and it is a **phase change**. Nothing else about the engine
moves. The model is still linear *in its parameters*, so it is still one ridge solve per signal from
one shared Gram matrix, still excludes the target's own history, and still returns an absolute
residual in units of a training quantile. "Same inputs, same outputs, same interpretation" is
literal here, not a claim.

**Inputs are clamped to the training range before expansion.** Outside what training showed, the
predictor holds its edge value instead of extrapolating a slope off to infinity — the saturation the
brief asks for, and it keeps a wild reading from producing a wild *prediction* and so hiding itself.
A reading outside its own training range is already the range score's business, and that component
is untouched.

**With zero knots this module is the frozen detector.** The basis collapses to ``[x]``, the Gram is
the frozen Gram, and the scores come back identical. A test pins exactly that, so the bend is the
only difference between this detector and the one it is measured against.

**Nothing here edits the frozen detector.** `atlas-v1-consistency` is on the frozen list in
`docs/rules/data-tiers.md`; its detrending, its range score, its episode and event grouping and its
budget are imported and reused unchanged. This is a separate detector under a separate name,
measured beside it (ADR 0273). Result name: ``atlas-bending-consistency``.

Unlike lanes 1 to 3 this lane appends **no** column: it returns the same one score per signal that
the frozen engine does. So ADR 0286's constraint on appended columns does not apply to it, and that
record's paragraph saying lane 4 appends columns is wrong — see this module's ADR.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

import numpy
from numpy.typing import NDArray

from phos.atlas.consistency import (
    CALIBRATION_RANK,
    RESID_QUANTILE,
    RIDGE,
    THRESHOLD,
    TrainFile,
    _all_episodes,
    _detrend,
    _lagged,
    _range_scores,
    _standardise,
)
from phos.atlas.consistency_windows import FROZEN_WINDOWS, Windows

__all__ = [
    "KNOT_QUANTILES",
    "RESULT_NAME",
    "BendingModel",
    "bending_scores",
    "fit_bending",
    "hinge_basis",
    "knots_from",
]

_Float64 = NDArray[numpy.float64]
_Float32 = NDArray[numpy.float32]
_Int = NDArray[numpy.int64]

#: The result name every score from this detector carries.
RESULT_NAME: Final = "atlas-bending-consistency"

#: Where the hinges go, as quantiles of each signal's attack-free training values.
#:
#: The quartiles: a minimal bend with resolution following the data rather than the axis. This is
#: the module's one free quantity, and it is read from attack-free training only — never from a
#: label, an attack window or a result. An empty tuple reproduces the frozen detector exactly.
KNOT_QUANTILES: Final = (0.25, 0.5, 0.75)

#: Rows per chunk when scoring, matching the frozen detector's own chunking.
_CHUNK: Final = 50_000


@dataclass(frozen=True)
class BendingModel:
    """Everything learned from attack-free training. Arrays are indexed by signal column.

    Mirrors `phos.atlas.consistency.ConsistencyModel` field for field, with ``knots`` added and
    ``weights`` widened to the hinge basis.

    Attributes:
        mean: Per signal, the attack-free mean used to standardise.
        spread: Per signal, the attack-free standard deviation, with zeros replaced by one.
        live: Indices of signals that vary in training; only these are predicted or predict.
        low: Per signal, the attack-free minimum. Used by the untouched range score.
        high: Per signal, the attack-free maximum.
        knots: ``(live, n_knots)`` hinge positions in standardised units, per live signal.
        weights: ``(width + 1, live)`` ridge solution over the hinge basis plus an intercept.
        scale: Per signal, the residual quantile the loop error is measured in.
        divisor: Per signal, the third-largest attack-free episode peak, floored at 1.0.
        windows: The windows the model was fitted with.
    """

    mean: _Float64
    spread: _Float64
    live: _Int
    low: _Float64
    high: _Float64
    knots: _Float64
    weights: _Float64
    scale: _Float64
    divisor: _Float64
    windows: Windows = FROZEN_WINDOWS


def knots_from(
    train: Sequence[TrainFile],
    mean: _Float64,
    spread: _Float64,
    live: _Int,
    quantiles: Sequence[float] = KNOT_QUANTILES,
) -> _Float64:
    """Return hinge positions per live signal, in standardised units.

    One knot set per signal, shared across lags: the same signal at a different lag has the same
    marginal distribution, so a second set would add parameters without adding shape.

    Args:
        train: Attack-free training files. Attack rows are excluded.
        mean: Per-signal mean from `phos.atlas.consistency._standardise`.
        spread: Per-signal spread from the same.
        live: Indices of the signals that vary.
        quantiles: Where to place the hinges, as quantiles in ``[0, 1]``.

    Returns:
        ``(live.size, len(quantiles))``, ascending along each row.

    Raises:
        ValueError: If a quantile is outside ``[0, 1]``.
    """
    for q in quantiles:
        if not 0.0 <= q <= 1.0:
            raise ValueError(f"a quantile must be in [0, 1], got {q!r}")
    if not quantiles:
        return numpy.zeros((live.size, 0), dtype=numpy.float64)
    stacked = numpy.vstack([f.values[~f.attack] for f in train])
    standardised = (stacked - mean) / spread
    found: _Float64 = numpy.quantile(standardised[:, live], list(quantiles), axis=0).T
    return numpy.ascontiguousarray(found, dtype=numpy.float64)


def hinge_basis(columns: _Float64, knots: _Float64, low: _Float64, high: _Float64) -> _Float64:
    """Expand each column to ``[x, max(0, x - t_1), ..., max(0, x - t_k)]``, x clamped first.

    Args:
        columns: ``(rows, p)`` standardised inputs.
        knots: ``(p, n_knots)`` hinge positions for those same columns.
        low: ``(p,)`` lower clamp per column, in standardised units.
        high: ``(p,)`` upper clamp per column.

    Returns:
        ``(rows, p * (1 + n_knots))``, grouped by input column: column ``i``'s linear term and then
        its hinges, before column ``i + 1``.

    Raises:
        ValueError: If ``knots``, ``low`` or ``high`` do not describe ``columns``.
    """
    rows, p = columns.shape
    if knots.shape[0] != p:
        raise ValueError(f"knots describe {knots.shape[0]} columns, not {p}")
    if low.shape[0] != p or high.shape[0] != p:
        raise ValueError(f"clamps describe {low.shape[0]}/{high.shape[0]} columns, not {p}")
    clamped = numpy.clip(columns, low, high)
    n_knots = knots.shape[1]
    out = numpy.empty((rows, p * (1 + n_knots)), dtype=numpy.float64)
    out[:, 0 :: 1 + n_knots] = clamped
    for k in range(n_knots):
        out[:, k + 1 :: 1 + n_knots] = numpy.maximum(clamped - knots[:, k], 0.0)
    return out


def _tiled(values: _Float64, n_lags: int) -> _Float64:
    """Repeat a per-live-signal vector across lags, matching `_lagged`'s column order."""
    return numpy.tile(values, n_lags)


def _standardised_clamps(
    mean: _Float64, spread: _Float64, low: _Float64, high: _Float64, live: _Int
) -> tuple[_Float64, _Float64]:
    """The training range per live signal, in the standardised units the basis clamps in.

    `_standardise` returns ``low``/``high`` in the signals' own units and over every signal, while
    `hinge_basis` clamps standardised columns and is given one entry per *live* signal. Converting
    in one place is deliberate: fitting and scoring must clamp identically, and when they did not,
    the zero-knot faithfulness test caught it.
    """
    return ((low - mean) / spread)[live], ((high - mean) / spread)[live]


def _design(
    z: _Float64,
    rows: _Int,
    live: _Int,
    lags: tuple[int, ...],
    knots: _Float64,
    low: _Float64,
    high: _Float64,
) -> _Float64:
    """The hinge design matrix for the given rows, without the intercept."""
    lagged = _lagged(z, rows, live, lags)
    n_lags = len(lags)
    return hinge_basis(
        lagged,
        numpy.tile(knots, (n_lags, 1)),
        _tiled(low, n_lags),
        _tiled(high, n_lags),
    )


def _own_columns(position: int, n_live: int, n_lags: int, n_knots: int) -> list[int]:
    """Every basis column derived from the target signal, at any lag."""
    per = 1 + n_knots
    return [
        (lag_index * n_live + position) * per + offset
        for lag_index in range(n_lags)
        for offset in range(per)
    ]


def _solve(
    train: Sequence[TrainFile],
    mean: _Float64,
    spread: _Float64,
    live: _Int,
    knots: _Float64,
    low: _Float64,
    high: _Float64,
    windows: Windows,
) -> _Float64:
    """Accumulate one Gram matrix over training and ridge-solve each signal from the others."""
    lags = windows.lags
    n_live = live.size
    n_knots = knots.shape[1]
    width = n_live * len(lags) * (1 + n_knots)
    gram = numpy.zeros((width + 1, width + 1))
    for f in train:
        z = (f.values - mean) / spread
        rows = numpy.arange(max(lags), z.shape[0], windows.fit_step)
        rows = rows[~f.attack[rows]]
        if rows.size == 0:
            continue
        x = numpy.hstack(
            [_design(z, rows, live, lags, knots, low, high), numpy.ones((rows.size, 1))]
        )
        gram += x.T @ x
    weights = numpy.zeros((width + 1, n_live))
    for position in range(n_live):
        own = _own_columns(position, n_live, len(lags), n_knots)
        keep = numpy.setdiff1d(numpy.arange(width + 1), own)
        a = gram[numpy.ix_(keep, keep)] + RIDGE * numpy.eye(keep.size)
        weights[keep, position] = numpy.linalg.solve(a, gram[keep, position])
    return weights


def _residual(
    values: _Float64,
    mean: _Float64,
    spread: _Float64,
    live: _Int,
    knots: _Float64,
    low: _Float64,
    high: _Float64,
    weights: _Float64,
    lags: tuple[int, ...],
) -> _Float32:
    """The absolute standardised prediction error per live signal, chunked as the frozen one is."""
    z = (values - mean) / spread
    n = z.shape[0]
    out = numpy.zeros((n, live.size), dtype=numpy.float32)
    for a in range(max(lags), n, _CHUNK):
        rows = numpy.arange(a, min(n, a + _CHUNK))
        design = _design(z, rows, live, lags, knots, low, high)
        prediction = design @ weights[:-1] + weights[-1]
        out[rows] = numpy.abs(z[rows][:, live] - prediction)
    return out


def _components(model: BendingModel, values: _Float64) -> tuple[_Float32, _Float32]:
    """The detrended loop and range scores, the frozen engine's own two, with the bent loop."""
    z_low, z_high = _standardised_clamps(
        model.mean, model.spread, model.low, model.high, model.live
    )
    loop = numpy.zeros(values.shape, dtype=numpy.float32)
    loop[:, model.live] = (
        _residual(
            values,
            model.mean,
            model.spread,
            model.live,
            model.knots,
            z_low,
            z_high,
            model.weights,
            model.windows.lags,
        )
        / model.scale[model.live]
    )
    return (
        _detrend(loop, model.windows),
        _detrend(_range_scores(values, model.low, model.high), model.windows),
    )


def fit_bending(
    train: Sequence[TrainFile],
    windows: Windows = FROZEN_WINDOWS,
    *,
    quantiles: Sequence[float] = KNOT_QUANTILES,
) -> BendingModel:
    """Learn the bent loop model, the ranges and the per-signal calibration from training.

    Every step is the frozen detector's own, with the hinge basis in place of the raw inputs: the
    same standardisation, the same residual quantile, the same third-largest-episode-peak
    calibration with attack rows excluded.

    Args:
        train: Training files sharing one signal order. Attack rows are left out.
        windows: The windows to fit with; `windows_for_period` for another sample period.
        quantiles: Hinge placement. ``()`` reproduces the frozen detector exactly.

    Returns:
        The fitted model.

    Raises:
        ValueError: If there is no training file.
    """
    if not train:
        raise ValueError("a bending fit needs at least one training file")
    mean, spread, live, low, high = _standardise(train)
    z_low, z_high = _standardised_clamps(mean, spread, low, high, live)
    knots = knots_from(train, mean, spread, live, quantiles)
    weights = _solve(train, mean, spread, live, knots, z_low, z_high, windows)

    residuals = numpy.vstack(
        [
            _residual(f.values, mean, spread, live, knots, z_low, z_high, weights, windows.lags)
            for f in train
        ]
    )
    scale = numpy.ones(mean.shape[0])
    scale[live] = numpy.maximum(numpy.quantile(residuals, RESID_QUANTILE, axis=0), 1e-6)

    n_signals = train[0].values.shape[1]
    partial = BendingModel(
        mean=mean,
        spread=spread,
        live=live,
        low=low,
        high=high,
        knots=knots,
        weights=weights,
        scale=scale,
        divisor=numpy.ones(n_signals),
        windows=windows,
    )
    peaks: list[list[float]] = [[] for _ in range(n_signals)]
    for f in train:
        loop, rng = _components(partial, f.values)
        raw = numpy.maximum(loop, rng)
        raw[f.attack] = 0.0
        for _s, _e, peak, _at, j in _all_episodes(raw, THRESHOLD, windows.feature_gap):
            peaks[j].append(peak)
    divisor = numpy.ones(n_signals)
    for j in range(n_signals):
        if len(peaks[j]) >= CALIBRATION_RANK:
            divisor[j] = max(1.0, sorted(peaks[j])[-CALIBRATION_RANK])

    return BendingModel(
        mean=mean,
        spread=spread,
        live=live,
        low=low,
        high=high,
        knots=knots,
        weights=weights,
        scale=scale,
        divisor=divisor,
        windows=windows,
    )


def bending_scores(model: BendingModel, values: _Float64) -> _Float32:
    """Return each signal's calibrated departure score at every row.

    Same shape and same meaning as `phos.atlas.consistency.feature_scores`: one score per signal
    per row, the element-wise maximum of the detrended loop and range scores over the per-signal
    divisor. This lane appends no column, so the result goes straight into the unchanged
    `phos.atlas.consistency.events` and `budget_alerts`.
    """
    loop, rng = _components(model, values)
    scores: _Float32 = (numpy.maximum(loop, rng) / model.divisor).astype(numpy.float32)
    return scores

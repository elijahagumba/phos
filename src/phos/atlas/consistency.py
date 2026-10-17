"""Is this reading consistent with the rest of the plant? Atlas's consistency detector.

This is the detector that won on the clean HAI editions, ported into the engine. It began as the
sandbox candidate in ``experiments/2026-10-04-sandbox/candidate.py`` (ADR 0096), frozen on
4 October 2026 and scored once on HAI 22.04 and 23.05 (ADR 0103, ADR 0104): 53 of 58 and 36 of 52
attacks within 8 alerts per 8-hour shift, against grouped MinMax's 10 and 6. The controls in
ADR 0106 put most of that margin on the loop score below, not on grouping.

**The port changes no arithmetic.** Every constant is the frozen file's, and the operations run in
the same order on the same dtypes, so the alert list is identical; a lab test runs both on one
input and compares them element for element. Only the scored configuration is carried over: the
frozen file's ablation switches (``USE_LOOP``, ``USE_DETREND``) and its unused calibration modes
are gone, because no result was scored with them off.

**Two scores per signal, at every sample.**

- *Loop*: each signal is predicted from every **other** signal now and 5, 15, 30 and 60 samples
  ago, one ridge regression per signal solved from one shared Gram matrix. The absolute error,
  divided by its 99.99th percentile on attack-free training, says how far the reading departs
  from what the rest of the plant implies. This is the question Atlas is built around, and
  `feature_components` returns it separately so the reasoning layer can cite it.
- *Range*: how far the reading sits outside its training range, in units of half that range (the
  MinMax rule's margin), times ten.

Both are detrended against their own median over the previous hour, so a slow drift stops
alerting without hiding a new departure, and each signal is divided by the third-largest episode
peak that attack-free training produced, so a signal that moves a lot in normal operation is
trusted less.

**Events, then the budget.** A stretch where a signal stays high is an episode; episodes whose
onsets chain within 300 samples (spanning at most 600) form one event, scored by its strongest
member. The alert goes at the first sample where a member reaches a strong level, so a weak drift
that starts just before a real departure does not pull the alert out of it. In each 8-hour shift
the strongest events get one alert each; spare slots get a second alert at the peak of the top
events, at a much lower score.

**Windows are counted in samples.** On HAI a sample is one second. ADR 0112 declares the one
rule for any other sample period (roadmap §2.0, A6): each frozen window is read as that many
seconds and `windows_for_period` converts it to samples. At one second it returns
`FROZEN_WINDOWS`, so HAI's arithmetic is unchanged.

Result name for anything this detector scores: ``atlas-v1-consistency``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

import numpy
from numpy.typing import NDArray

from phos.atlas.consistency_windows import (
    DETREND_STEP,
    DETREND_WINDOW,
    EVENT_SPAN,
    EVENT_WINDOW,
    FEATURE_GAP,
    FIT_STEP,
    FROZEN_WINDOWS,
    LAGS,
    SECOND_ALERT_MIN_SEPARATION,
    Windows,
    windows_for_period,
)

__all__ = [
    "ALERTS_PER_SHIFT",
    "CALIBRATION_RANK",
    "DETREND_STEP",
    "DETREND_WINDOW",
    "EVENT_SPAN",
    "EVENT_WINDOW",
    "FEATURE_GAP",
    "FIT_STEP",
    "FROZEN_WINDOWS",
    "LAGS",
    "ONSET_FRACTION",
    "ONSET_LEVEL",
    "RANGE_WEIGHT",
    "RESID_QUANTILE",
    "RESULT_NAME",
    "RIDGE",
    "SECOND_ALERT_MIN_SEPARATION",
    "SHIFT_SECONDS",
    "THRESHOLD",
    "ConsistencyEvent",
    "ConsistencyModel",
    "ScoredFile",
    "TrainFile",
    "Windows",
    "budget_alerts",
    "detect",
    "events",
    "feature_components",
    "feature_scores",
    "fit",
    "loop_expectation",
    "windows_for_period",
]

_Float64 = NDArray[numpy.float64]
_Float32 = NDArray[numpy.float32]
_Bool = NDArray[numpy.bool_]
_Int = NDArray[numpy.int64]

#: The result name every score from this detector carries.
RESULT_NAME: Final = "atlas-v1-consistency"

#: An operator shift, in seconds of the file's own clock.
SHIFT_SECONDS: Final = 8 * 3600
#: Alerts an operator can read per shift.
ALERTS_PER_SHIFT: Final = 8

#: Ridge penalty on the standardised regression.
RIDGE: Final = 1.0
#: Training residual quantile that a loop error is measured in.
RESID_QUANTILE: Final = 0.9999
#: Weight on the range score, so a range overshoot of half the range scores ten.
RANGE_WEIGHT: Final = 10.0
#: A score above this opens an episode.
THRESHOLD: Final = 1.0
#: The alert goes where a member first reaches this share of the event's peak ...
ONSET_FRACTION: Final = 0.1
#: ... and at least this score.
ONSET_LEVEL: Final = 2.0
#: A signal is divided by the k-th largest training episode peak.
CALIBRATION_RANK: Final = 3


@dataclass(frozen=True)
class TrainFile:
    """One training file: values (rows by signals) and its attack flags.

    Attack flags are used only to leave attack rows out of fits and calibration.
    """

    values: _Float64
    attack: _Bool


@dataclass(frozen=True)
class ScoredFile:
    """One file to score: unix seconds and values. It carries no labels."""

    time: _Float64
    values: _Float64


@dataclass(frozen=True)
class ConsistencyModel:
    """Everything learned from attack-free training. Arrays are indexed by signal column."""

    mean: _Float64
    spread: _Float64
    live: _Int
    low: _Float64
    high: _Float64
    weights: _Float64
    scale: _Float64
    divisor: _Float64
    windows: Windows = FROZEN_WINDOWS


@dataclass(frozen=True)
class ConsistencyEvent:
    """One event: where its alert goes, how strong it is, and its member episodes.

    A member episode is ``(start, end, peak, peak_row, column)``.
    """

    onset: int
    column: int
    score: float
    peak_at: int
    peak_column: int
    members: tuple[tuple[int, int, float, int, int], ...]


# ---------------------------------------------------------------------------- loop model


def _standardise(
    files: Sequence[TrainFile],
) -> tuple[_Float64, _Float64, _Int, _Float64, _Float64]:
    matrix = numpy.vstack([f.values[~f.attack] for f in files])
    mean = matrix.mean(axis=0)
    spread = matrix.std(axis=0)
    live = numpy.flatnonzero(spread > 0)
    return (
        mean,
        numpy.where(spread > 0, spread, 1.0),
        live,
        matrix.min(axis=0),
        matrix.max(axis=0),
    )


def _lagged(z: _Float64, rows: _Int, live: _Int, lags: tuple[int, ...]) -> _Float64:
    return numpy.hstack([z[rows - lag][:, live] for lag in lags])


def _fit_loop(
    files: Sequence[TrainFile], mean: _Float64, spread: _Float64, live: _Int, windows: Windows
) -> _Float64:
    lags = windows.lags
    n_live = live.size
    width = n_live * len(lags)
    gram = numpy.zeros((width + 1, width + 1))
    for f in files:
        z = (f.values - mean) / spread
        rows = numpy.arange(max(lags), z.shape[0], windows.fit_step)
        rows = rows[~f.attack[rows]]
        x = numpy.hstack([_lagged(z, rows, live, lags), numpy.ones((rows.size, 1))])
        gram += x.T @ x
    weights = numpy.zeros((width + 1, n_live))
    for k in range(n_live):
        own = [lag_index * n_live + k for lag_index in range(len(lags))]
        keep = numpy.setdiff1d(numpy.arange(width + 1), own)
        a = gram[numpy.ix_(keep, keep)] + RIDGE * numpy.eye(keep.size)
        weights[keep, k] = numpy.linalg.solve(a, gram[keep, k])
    return weights


def _loop_residual(
    values: _Float64,
    mean: _Float64,
    spread: _Float64,
    live: _Int,
    weights: _Float64,
    lags: tuple[int, ...] = LAGS,
) -> _Float32:
    z = (values - mean) / spread
    n = z.shape[0]
    out = numpy.zeros((n, live.size), dtype=numpy.float32)
    for a in range(max(lags), n, 50_000):
        rows = numpy.arange(a, min(n, a + 50_000))
        prediction = _lagged(z, rows, live, lags) @ weights[:-1] + weights[-1]
        out[rows] = numpy.abs(z[rows][:, live] - prediction)
    return out


# ---------------------------------------------------------------------------- range and detrend


def _range_scores(values: _Float64, low: _Float64, high: _Float64) -> _Float32:
    margin = (high - low) / 2.0
    over = numpy.maximum(numpy.maximum(values - high, low - values), 0.0)
    scale = numpy.where(margin > 0, margin, numpy.maximum(numpy.abs(high), 1.0))
    return (RANGE_WEIGHT * over / scale).astype(numpy.float32)


def _detrend_base(scores: _Float32, windows: Windows = FROZEN_WINDOWS) -> _Float32:
    """Each score's median over the previous hour, sampled every minute. What `_detrend` removes."""
    step = windows.detrend_step
    sampled = scores[::step]
    k = windows.detrend_window // step
    base = numpy.zeros_like(scores)
    for i in range(1, sampled.shape[0]):
        base[i * step : (i + 1) * step] = numpy.median(sampled[max(0, i - k) : i], axis=0)
    return base


def _detrend(scores: _Float32, windows: Windows = FROZEN_WINDOWS) -> _Float32:
    n = scores.shape[0]
    detrended: _Float32 = numpy.maximum(scores - _detrend_base(scores, windows)[:n], 0.0)
    return detrended


# ---------------------------------------------------------------------------- episodes and events


def _runs(mask: _Bool) -> tuple[_Int, _Int]:
    if not mask.any():
        return numpy.empty(0, int), numpy.empty(0, int)
    d = numpy.diff(numpy.concatenate(([0], mask.astype(numpy.int8), [0])))
    return numpy.flatnonzero(d == 1), numpy.flatnonzero(d == -1) - 1


def _episodes(
    column: _Float32 | _Float64, threshold: float, gap: int
) -> list[tuple[int, int, float, int]]:
    starts, ends = _runs(column > threshold)
    if starts.size == 0:
        return []
    keep = numpy.concatenate(([True], starts[1:] - ends[:-1] > gap))
    start_index = starts[keep]
    end_index = numpy.concatenate((ends[:-1][keep[1:]], [ends[-1]]))
    out: list[tuple[int, int, float, int]] = []
    for s, e in zip(start_index.tolist(), end_index.tolist(), strict=True):
        segment = column[s : e + 1]
        at = int(segment.argmax())
        out.append((s, e, float(segment[at]), s + at))
    return out


def _all_episodes(
    scores: _Float32 | _Float64, threshold: float, gap: int = FEATURE_GAP
) -> list[tuple[int, int, float, int, int]]:
    found: list[tuple[int, int, float, int, int]] = []
    for j in range(scores.shape[1]):
        for s, e, peak, at in _episodes(scores[:, j], threshold, gap):
            found.append((s, e, peak, at, j))
    found.sort()
    return found


def events(
    scores: _Float32, threshold: float = THRESHOLD, windows: Windows = FROZEN_WINDOWS
) -> list[ConsistencyEvent]:
    """Group per-signal episodes into events and place each event's alert.

    Args:
        scores: Rows by signals, as `feature_scores` returns them.
        threshold: A score above this opens an episode.
        windows: The model's windows (`ConsistencyModel.windows`). HAI's by default.

    Returns:
        Events in onset order of their first member.
    """
    groups: list[list[tuple[int, int, float, int, int]]] = []
    current: list[tuple[int, int, float, int, int]] = []
    last = 0
    for episode in _all_episodes(scores, threshold, windows.feature_gap):
        if current and (
            episode[0] - last > windows.event_window
            or episode[0] - current[0][0] > windows.event_span
        ):
            groups.append(current)
            current = []
        current.append(episode)
        last = episode[0]
    if current:
        groups.append(current)
    found: list[ConsistencyEvent] = []
    for group in groups:
        best = max(group, key=lambda episode: episode[2])
        level = min(best[2], max(ONSET_LEVEL, ONSET_FRACTION * best[2]))
        onset, column = best[3], best[4]
        for s, e, peak, _at, j in group:
            if peak < level or s >= onset:
                continue
            hit = numpy.flatnonzero(scores[s : min(e, onset) + 1, j] >= level)
            if hit.size and s + hit[0] < onset:
                onset, column = s + int(hit[0]), j
        found.append(
            ConsistencyEvent(
                onset=int(onset),
                column=int(column),
                score=best[2],
                peak_at=best[3],
                peak_column=best[4],
                members=tuple(group),
            )
        )
    return found


def budget_alerts(
    found: Sequence[ConsistencyEvent], time: _Float64, windows: Windows = FROZEN_WINDOWS
) -> tuple[list[int], list[int], list[float]]:
    """Keep the strongest events per 8-hour shift, one alert each, plus spare second alerts.

    Args:
        found: Events from `events`.
        time: Unix seconds for each row of the scored file.
        windows: The model's windows. Only the second-alert separation is read.

    Returns:
        ``(rows, columns, scores)``, one entry per alert, in the order they were chosen.
    """
    rows: list[int] = []
    columns: list[int] = []
    scores: list[float] = []
    origin = time[0]
    by_shift: dict[int, list[ConsistencyEvent]] = {}
    for event in found:
        by_shift.setdefault(int((time[event.onset] - origin) // SHIFT_SECONDS), []).append(event)
    for shift in sorted(by_shift):
        chosen = sorted(by_shift[shift], key=lambda event: -event.score)[:ALERTS_PER_SHIFT]
        for event in chosen:
            rows.append(event.onset)
            columns.append(event.column)
            scores.append(event.score)
        spare = ALERTS_PER_SHIFT - len(chosen)
        for event in chosen:
            if spare <= 0:
                break
            same = int((time[event.peak_at] - origin) // SHIFT_SECONDS) == shift
            if same and abs(event.peak_at - event.onset) >= windows.second_alert_min_separation:
                rows.append(event.peak_at)
                columns.append(event.peak_column)
                scores.append(event.score * 1e-3)
                spare -= 1
    return rows, columns, scores


# ---------------------------------------------------------------------------- fitting and scoring


def _components(
    values: _Float64,
    mean: _Float64,
    spread: _Float64,
    live: _Int,
    low: _Float64,
    high: _Float64,
    weights: _Float64,
    scale: _Float64,
    windows: Windows,
) -> tuple[_Float32, _Float32]:
    loop = numpy.zeros(values.shape, dtype=numpy.float32)
    loop[:, live] = _loop_residual(values, mean, spread, live, weights, windows.lags) / scale[live]
    return _detrend(loop, windows), _detrend(_range_scores(values, low, high), windows)


def fit(train: Sequence[TrainFile], windows: Windows = FROZEN_WINDOWS) -> ConsistencyModel:
    """Learn the loop model, the ranges and the per-signal calibration from training.

    Args:
        train: Training files sharing one signal order. Attack rows are left out.
        windows: HAI's frozen windows by default; `windows_for_period` for another sample
            period (ADR 0112). The model keeps them, so scoring uses the windows it was fit with.

    Returns:
        The fitted model.

    Raises:
        ValueError: If there is no training file.
    """
    if not train:
        raise ValueError("a consistency fit needs at least one training file")
    mean, spread, live, low, high = _standardise(train)
    weights = _fit_loop(train, mean, spread, live, windows)
    residuals = numpy.vstack(
        [_loop_residual(f.values, mean, spread, live, weights, windows.lags) for f in train]
    )
    scale = numpy.ones(mean.shape[0])
    scale[live] = numpy.maximum(numpy.quantile(residuals, RESID_QUANTILE, axis=0), 1e-6)
    n_signals = train[0].values.shape[1]
    peaks: list[list[float]] = [[] for _ in range(n_signals)]
    for f in train:
        loop, rng = _components(f.values, mean, spread, live, low, high, weights, scale, windows)
        raw = numpy.maximum(loop, rng)
        raw[f.attack] = 0.0
        for _s, _e, peak, _at, j in _all_episodes(raw, THRESHOLD, windows.feature_gap):
            peaks[j].append(peak)
    divisor = numpy.ones(n_signals)
    for j in range(n_signals):
        if len(peaks[j]) >= CALIBRATION_RANK:
            divisor[j] = max(1.0, sorted(peaks[j])[-CALIBRATION_RANK])
    return ConsistencyModel(
        mean=mean,
        spread=spread,
        live=live,
        low=low,
        high=high,
        weights=weights,
        scale=scale,
        divisor=divisor,
        windows=windows,
    )


def feature_components(model: ConsistencyModel, values: _Float64) -> tuple[_Float32, _Float32]:
    """Return the calibrated loop and range scores separately, rows by signals.

    Their element-wise maximum is `feature_scores`. The loop part is the consistency evidence:
    how far each reading departs from what the rest of the plant implies.
    """
    loop, rng = _components(
        values,
        model.mean,
        model.spread,
        model.live,
        model.low,
        model.high,
        model.weights,
        model.scale,
        model.windows,
    )
    return (
        (loop / model.divisor).astype(numpy.float32),
        (rng / model.divisor).astype(numpy.float32),
    )


def feature_scores(model: ConsistencyModel, values: _Float64) -> _Float32:
    """Return each signal's calibrated departure score at every row."""
    loop, rng = _components(
        values,
        model.mean,
        model.spread,
        model.live,
        model.low,
        model.high,
        model.weights,
        model.scale,
        model.windows,
    )
    scores: _Float32 = (numpy.maximum(loop, rng) / model.divisor).astype(numpy.float32)
    return scores


def loop_expectation(model: ConsistencyModel, values: _Float64) -> tuple[_Float64, _Float64]:
    """Return what the rest of the plant implies each reading should be, and how far it may stray.

    The first array is the loop regression's prediction in the signal's own units: the value the
    other signals, now and over the last minute, imply. When a reading is falsified this is the
    reconstruction of the real value. The second is the half-width of the band around it inside
    which the calibrated loop score stays at or below `THRESHOLD`, including the hour's detrending
    baseline, so a reading outside ``predicted ± half_width`` is exactly one whose loop score
    exceeds the threshold (up to float32 rounding in the scores themselves).

    Both are ``NaN`` where no prediction exists: a signal with no spread in training, and the
    first ``max(lags)`` rows of the file. This adds nothing to, and changes nothing in,
    `feature_scores` or the alert list.
    """
    predicted = numpy.full(values.shape, numpy.nan)
    half_width = numpy.full(values.shape, numpy.nan)
    live = model.live
    lags = model.windows.lags
    n = values.shape[0]
    if live.size == 0 or n <= max(lags):
        return predicted, half_width
    z = (values - model.mean) / model.spread
    raw = numpy.zeros(values.shape, dtype=numpy.float32)
    raw[:, live] = (
        _loop_residual(values, model.mean, model.spread, live, model.weights, lags)
        / (model.scale[live])
    )
    base = _detrend_base(raw, model.windows)
    for a in range(max(lags), n, 50_000):
        rows = numpy.arange(a, min(n, a + 50_000))
        prediction = _lagged(z, rows, live, lags) @ model.weights[:-1] + model.weights[-1]
        predicted[numpy.ix_(rows, live)] = prediction * model.spread[live] + model.mean[live]
        half_width[numpy.ix_(rows, live)] = (
            model.spread[live]
            * model.scale[live]
            * (base[rows][:, live] + model.divisor[live] * THRESHOLD)
        )
    return predicted, half_width


def detect(
    train: Sequence[TrainFile],
    test: Sequence[ScoredFile],
    windows: Windows = FROZEN_WINDOWS,
) -> list[tuple[list[int], list[int], list[float]]]:
    """Fit once and return each test file's budgeted alerts as ``(rows, columns, scores)``.

    This is the frozen candidate's ``run``: one fit, then events and the budget per file. With
    the default windows it is the frozen file's arithmetic exactly.
    """
    model = fit(train, windows)
    return [
        budget_alerts(
            events(feature_scores(model, f.values), windows=model.windows), f.time, model.windows
        )
        for f in test
    ]

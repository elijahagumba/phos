"""Accumulate over time, not only at the peak. Lane 3 of the stronger-engine programme (ADR 0273).

`phos.atlas.consistency` opens an episode only where a signal's score crosses `THRESHOLD` at some
single sample. Two properties of that rule make a slow departure hard to see, and both are
structural rather than a matter of tuning:

* **The test is on the peak.** A reading that is mildly wrong for an hour never exceeds the
  threshold at any one sample, so it opens no episode, however long it goes on.
* **The detrender actively removes a ramp.** Every score is detrended against its own median over
  the previous `detrend_window` samples, which the frozen docstring describes as letting "a slow
  drift stop alerting". For a reading drifting steadily away from truth, the trailing median
  follows it, and what is left is a small persistent offset rather than a growing one.

So the shape this module is for is a score that sits a little above its own normal for a long time.
`liar_freeze` — a reading held while the plant moves away underneath it — is exactly that shape, and
on `phos-icssim-dev2` the frozen engine, lane 1 and lane 2 all catch it **1 of 10**
(`eval_runs/build/lane-e/dev2-with-creep-many.md`).

**The statistic.** One accumulator per signal, over that signal's own frozen score:

    A[i, j] = max(0, RETENTION * A[i - 1, j] + score[i, j] - slack[j])

Three parts, each with a reason that is not an attack:

* ``slack[j]`` is what ordinary operation is allowed for free: the `SLACK_QUANTILE` quantile of that
  signal's score on attack-free training. Below it nothing accumulates, so a quiet plant stays at
  zero and the total only grows while a signal runs persistently above its own normal. This is the
  "implausible for attack-free operation" clause of the bar, read from training and not from labels.
* ``RETENTION`` makes the tally leaky, so it is bounded and forgets. Its memory is the engine's own
  `detrend_window`: the accumulator remembers for exactly as long as the detrender's baseline looks
  back. A bounded tally also re-arms after an episode ends, so a second attack later in the same run
  gets its own episode instead of being swallowed by one unbounded run of high score.
* The clamp at zero is Page's: credit is not carried for being quieter than normal.

Each column is then divided by the third-largest episode peak it reaches on attack-free training,
the rule `phos.atlas.consistency.fit` already applies per signal, so `THRESHOLD` means on these
columns what it means on every other.

**One column per signal, not one for the plant.** The accumulator keeps the instrument it belongs
to, so an alert it wins still names a signal and the explanation layer can cite it. Collapsing
signals is lane 2's idea (`phos.atlas.breadth_consistency`) and is kept separate from this one.

The augmented matrix goes through the unchanged `events` and `budget_alerts`, so the accumulator
columns compete with the per-signal columns for the same eight alerts a shift rather than being
added on top of them. That is the whole test: on a saturated budget an accumulator column earns a
slot only by outscoring a column that already had one.

**Nothing here edits the frozen detector.** `atlas-v1-consistency` is on the frozen list in
`docs/rules/data-tiers.md` and is consumed, never changed. This is a separate detector under a
separate name, measured beside it (ADR 0273). Result name: ``atlas-drift-consistency``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

import numpy
from numpy.typing import NDArray

from phos.atlas.consistency import (
    CALIBRATION_RANK,
    ONSET_FRACTION,
    ONSET_LEVEL,
    THRESHOLD,
    ConsistencyModel,
    _all_episodes,
    feature_scores,
)

__all__ = [
    "CONTRIBUTION_CAP",
    "RESULT_NAME",
    "SLACK_QUANTILE",
    "DriftModel",
    "accumulate",
    "augmented_scores",
    "calibrate_drift",
    "fit_drift",
    "retention_for",
]

_Float32 = NDArray[numpy.float32]
_Float64 = NDArray[numpy.float64]

#: The result name every score from this detector carries.
RESULT_NAME: Final = "atlas-drift-consistency"

#: The share of attack-free score a signal is allowed for free, per signal.
#:
#: The accumulator grows only on what exceeds this. A high quantile means ordinary operation,
#: including its occasional excursions, contributes nothing, so the tally measures persistent
#: excess rather than noise. Read from attack-free training only.
SLACK_QUANTILE: Final = 0.99

#: The most a calibrated accumulator column may read: ``ONSET_LEVEL / ONSET_FRACTION``.
#:
#: This is not a sensitivity knob — it is what keeps the column from moving the frozen engine's
#: alert placement. `phos.atlas.consistency.events` puts an event's alert at the earliest member
#: episode reaching ``level = max(ONSET_LEVEL, ONSET_FRACTION * best_peak)``, and skips any member
#: whose own peak is below that. A tally is a sum over time, so its peak runs to the hundreds while
#: a per-sample score sits near one; an uncapped column therefore becomes every group's ``best``,
#: drives ``level`` into the tens, disqualifies the early per-signal episode that *would* have
#: placed the alert, and moves the alert to the accumulator's own later crossing. Measured on
#: `phos-icssim-dev2`: the paired median delay went from 1 s to 8 s that way, failing the half of
#: the bar that exists to catch exactly this.
#:
#: ``ONSET_LEVEL / ONSET_FRACTION`` is the largest cap for which ``max(ONSET_LEVEL,
#: ONSET_FRACTION * peak)`` is still ``ONSET_LEVEL``. So the cap leaves ``level`` at the floor the
#: frozen engine uses when nothing is extreme, every per-signal episode reaching ``ONSET_LEVEL``
#: keeps its right to place the alert, and ordering over ``(THRESHOLD, CONTRIBUTION_CAP]`` is
#: preserved for the budget's ranking. Lane 2 caps a per-signal contribution for the same reason:
#: so that one thing cannot dominate (`phos.atlas.breadth_consistency`).
CONTRIBUTION_CAP: Final = ONSET_LEVEL / ONSET_FRACTION


@dataclass(frozen=True)
class DriftModel:
    """A fitted `ConsistencyModel` plus what the accumulator learned from attack-free training.

    Attributes:
        base: The per-signal model, unchanged. Never edited by this module.
        slack: Per signal, the score an ordinary sample is allowed before anything accumulates.
        divisors: Per signal, the accumulator column's calibration, each floored at 1.0.
        retention: The leak factor, in (0, 1]. One would make the tally unbounded.
        cap: The most a calibrated column may read. See `CONTRIBUTION_CAP`.
    """

    base: ConsistencyModel
    slack: _Float64
    divisors: _Float64
    retention: float
    cap: float = CONTRIBUTION_CAP


def retention_for(detrend_window: int) -> float:
    """Return the leak factor whose memory is ``detrend_window`` samples.

    A leaky accumulator with factor ``r`` has a memory of about ``1 / (1 - r)`` samples, so a
    window of ``w`` gives ``r = 1 - 1 / w``. A window of one sample gives zero retention, which is
    the frozen engine's own per-sample test and the right degenerate case.

    `fit_drift` always passes `Windows.detrend_window`, so the accumulator remembers for exactly as
    long as the detrender's trailing median looks back. That is deliberate: the detrending is what
    removes a slow drift in the first place, and tying this module's one time constant to a window
    the engine already declares keeps it away from the length of any particular attack.

    Args:
        detrend_window: `phos.atlas.consistency_windows.Windows.detrend_window`, in samples.

    Returns:
        The factor, in ``[0, 1)``.

    Raises:
        ValueError: If the window is not a positive number of samples.
    """
    if detrend_window < 1:
        raise ValueError(f"a detrend window must be at least one sample, got {detrend_window!r}")
    return 1.0 - 1.0 / float(detrend_window)


def accumulate(scores: _Float32, slack: _Float64, retention: float) -> _Float32:
    """Return the per-signal accumulator, one value per row per signal.

    ``A[i] = max(0, retention * A[i - 1] + score[i] - slack)``, clamped at zero at every step, with
    ``A`` before the first row taken as zero.

    Args:
        scores: Rows by signals, as `phos.atlas.consistency.feature_scores` returns them.
        slack: One allowance per signal.
        retention: The leak factor, in ``[0, 1]``.

    Returns:
        Rows by signals, the same shape as ``scores``.

    Raises:
        ValueError: If ``slack`` does not have one entry per signal, or retention is out of range.
    """
    if slack.shape[0] != scores.shape[1]:
        raise ValueError(f"slack has {slack.shape[0]} entries for {scores.shape[1]} signals")
    if not 0.0 <= retention <= 1.0:
        raise ValueError(f"retention must be in [0, 1], got {retention!r}")
    excess = scores.astype(numpy.float64) - slack
    out = numpy.zeros(scores.shape, dtype=numpy.float64)
    carried = numpy.zeros(scores.shape[1], dtype=numpy.float64)
    for row in range(scores.shape[0]):
        carried = numpy.maximum(retention * carried + excess[row], 0.0)
        out[row] = carried
    return out.astype(numpy.float32)


def _slack_from(scores: Sequence[_Float32], quantile: float) -> _Float64:
    """Per signal, the ``quantile`` quantile of the attack-free score."""
    stacked = numpy.vstack([numpy.asarray(item, dtype=numpy.float64) for item in scores])
    found: _Float64 = numpy.quantile(stacked, quantile, axis=0)
    return found


def calibrate_drift(accumulated: Sequence[_Float32], n_signals: int, feature_gap: int) -> _Float64:
    """Return one divisor per accumulator column, by the engine's own calibration rule.

    The rule is `phos.atlas.consistency.fit`'s: collect the episode peaks the column reaches above
    ``THRESHOLD`` on attack-free training and take the ``CALIBRATION_RANK``-th largest, floored at
    1.0. A column with fewer peaks than that rank is quiet on training and needs no scaling.

    Args:
        accumulated: One accumulator matrix per attack-free run, rows by signals.
        n_signals: How many signals each matrix has.
        feature_gap: ``model.windows.feature_gap``, so episodes are cut the same way.

    Returns:
        One divisor per signal, each at least 1.0.
    """
    peaks: list[list[float]] = [[] for _ in range(n_signals)]
    for matrix in accumulated:
        for _s, _e, peak, _at, column in _all_episodes(matrix, THRESHOLD, feature_gap):
            peaks[column].append(peak)
    divisors = numpy.ones(n_signals, dtype=numpy.float64)
    for column in range(n_signals):
        if len(peaks[column]) >= CALIBRATION_RANK:
            divisors[column] = max(1.0, sorted(peaks[column])[-CALIBRATION_RANK])
    return divisors


def fit_drift(
    model: ConsistencyModel,
    training: Sequence[_Float64],
    *,
    slack_quantile: float = SLACK_QUANTILE,
    cap: float = CONTRIBUTION_CAP,
) -> DriftModel:
    """Learn the accumulator's slack and calibration from attack-free runs.

    Both come from training alone: the slack is a quantile of the attack-free score per signal, and
    the divisor is the third-largest attack-free episode peak of the accumulator itself. No label
    and no attack window is read.

    Args:
        model: The fitted per-signal model, consumed and never edited.
        training: One attack-free telemetry matrix per run, rows by signals, sharing a column order.
        slack_quantile: The quantile of attack-free score allowed for free, per signal.
        cap: The most a calibrated accumulator column may read.

    Returns:
        The drift model.

    Raises:
        ValueError: If there is no training run, or the quantile is not in ``[0, 1]``.
    """
    if not training:
        raise ValueError("a drift fit needs at least one attack-free run")
    if not 0.0 <= slack_quantile <= 1.0:
        raise ValueError(f"a quantile must be in [0, 1], got {slack_quantile!r}")
    scored = [feature_scores(model, values) for values in training]
    slack = _slack_from(scored, slack_quantile)
    retention = retention_for(model.windows.detrend_window)
    accumulated = [accumulate(item, slack, retention) for item in scored]
    divisors = calibrate_drift(accumulated, scored[0].shape[1], model.windows.feature_gap)
    return DriftModel(base=model, slack=slack, divisors=divisors, retention=retention, cap=cap)


def augmented_scores(model: DriftModel, values: _Float64) -> _Float32:
    """Return the per-signal scores with one calibrated accumulator column appended per signal.

    The result has twice as many columns as ``values``: the frozen engine's own scores first, in
    their original order, then the accumulator for each signal in the same order. Everything
    downstream — `phos.atlas.consistency.events`, `budget_alerts` — takes it unchanged, so the
    accumulator columns compete for the same shift budget as the signals.

    Each accumulator column is clipped at `CONTRIBUTION_CAP`, which leaves the frozen engine's
    alert placement exactly where it would have been. See that constant for why.

    Args:
        model: The drift model, carrying the per-signal model, the slack and the divisors.
        values: Rows by signals.

    Returns:
        Rows by twice the signals. Column ``n_signals + j`` is signal ``j``'s accumulator.
    """
    scores = feature_scores(model.base, values)
    tally = accumulate(scores, model.slack, model.retention) / model.divisors
    capped = numpy.minimum(tally, model.cap)
    return numpy.concatenate([scores, capped.astype(numpy.float32)], axis=1).astype(numpy.float32)

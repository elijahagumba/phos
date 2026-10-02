"""The measurements a taxonomy's screens and prose rest on, so no figure in a report is transcribed.

`phos.eval.taxonomy` decides what category an alert belongs to. It is a pure function of a corpus
screen and a set of declared-normal references, and it deliberately knows nothing about how either
was measured. This module is where they are measured.

**Why it is separate, and why it is not in the script.** A screen that says "no instrument became
noisier" is only worth reading if the comparison behind it can be re-run. A number typed into a
report by whoever wrote it is a claim; a number a function returned is evidence. Every figure the
HAI taxonomy quotes — the alert-rate pair that carries the whole finding, the noise-scale ratios
behind the refuted sensor-noise screen, the trend correlation behind the not-separable ageing
screen, the duty-cycle period that explains where the fit-length cliff falls — comes from a function
here, and the script that writes the report has no arithmetic of its own.

**Everything here is a diagnostic instrument, and none of it is a detector.** `fit_length_sweep`
refits a model many times, which in any other context would be a threshold search wearing a
disguise. It is not one: the threshold never moves, the signal space is held fixed, the seed is
fixed, every point on the curve is reported rather than the best one selected, and nothing it
produces is logged or proposed as an operating point. It exists to answer *how much of this alert
load is attributable to the length of the fit set*, which is a question about attribution and has
an answer whether or not anybody ever acts on it.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from itertools import pairwise
from typing import Final

import numpy
import pandas
from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "AlertRatePair",
    "CyclePeriod",
    "FitLengthPoint",
    "NoiseScaleRatio",
    "TrendStrength",
    "cycle_periods",
    "noise_scale_ratios",
    "sweep_transition",
    "trend_strengths",
]

logger = logging.getLogger(__name__)

_SECONDS_PER_HOUR: Final = 3600.0


class NoiseScaleRatio(BaseModel):
    """How one signal's sample-to-sample jitter compares between two stretches.

    The discriminator for sensor noise. An instrument that became noisier shows a larger lag-1
    absolute difference than it does in declared-normal data; one whose jitter is unchanged did not
    become noisier, whatever else changed. Both a median and a 99th percentile are carried because a
    median alone misses a channel that started spiking occasionally.

    Attributes:
        signal: The signal compared.
        median_ratio: Median lag-1 absolute difference under review over the same in the reference.
        p99_ratio: The same at the 99th percentile.
    """

    model_config = ConfigDict(frozen=True)

    signal: str
    median_ratio: float = Field(ge=0.0)
    p99_ratio: float = Field(ge=0.0)

    @property
    def noisier(self) -> bool:
        """Whether either statistic says the instrument became materially noisier.

        Materially is 1.5x, declared here rather than chosen per corpus. It is a screen, not an
        operating point: a signal within 1.5x on both statistics has not changed character, and one
        beyond it is worth looking at by hand rather than being auto-assigned.
        """
        return max(self.median_ratio, self.p99_ratio) > 1.5


class TrendStrength(BaseModel):
    """How monotone one signal is over a stretch, and over the reference for comparison.

    The discriminator for equipment ageing, and on a short corpus it is the measurement that
    *refuses* rather than assigns: a trend present over the slice and also present over a much
    longer declared-normal stretch is a duty-cycle phase, not a degradation.

    Attributes:
        signal: The signal measured.
        rho_under_review: Spearman rank correlation of value against time over the slice.
        rho_reference: The same over the declared-normal reference.
        envelope_shift: How far the slice's 5th-95th percentile band sits from the reference's,
            as a fraction of the reference band's width. A degradation moves the envelope; a phase
            of a cycle does not.
    """

    model_config = ConfigDict(frozen=True)

    signal: str
    rho_under_review: float = Field(ge=-1.0, le=1.0)
    rho_reference: float = Field(ge=-1.0, le=1.0)
    envelope_shift: float = Field(ge=0.0)

    @property
    def drifting(self) -> bool:
        """Whether the slice shows a monotone tendency the declared-normal reference does not.

        Two conditions, because either alone is satisfied by ordinary behaviour. The tendency has to
        be real — 0.3 of rank correlation, declared here — and it has to be materially stronger than
        the same signal manages over a reference many times longer, since a signal that drifts just
        as much across sixty hours of declared-normal operation is not drifting, it is cycling.
        """
        return abs(self.rho_under_review) >= 0.3 and abs(self.rho_under_review) > 2.0 * abs(
            self.rho_reference
        )

    @property
    def separable_from_cycle_phase(self) -> bool:
        """Whether a drift here could be told apart from a phase of a cycle on this evidence.

        Both halves are required. Without a drift there is nothing to attribute, however the
        envelope sits — a signal with no monotone tendency is not ageing. And a drift inside an
        unmoved envelope is what the middle of a slow cycle looks like: the readings march one way
        while the range they march inside is the range declared-normal operation already shows, and
        no length of argument separates the two on a corpus spanning days.

        The envelope comparison is a fraction of the reference band's own width, so it is scale-free
        by construction. That makes it fire readily on a very narrow signal, which is why the drift
        condition is the one that has to hold first.
        """
        return self.drifting and self.envelope_shift > 0.1


class CyclePeriod(BaseModel):
    """The dominant period in one signal, read off its autocorrelation.

    Explains where a fit-length cliff falls. A fit set shorter than one period contains one phase of
    the cycle and learns that phase's structure as the plant's.

    Attributes:
        signal: The signal measured.
        first_zero_crossing_hours: Lag at which autocorrelation first goes negative.
        first_peak_hours: Lag of the first autocorrelation maximum after that crossing — the period.
    """

    model_config = ConfigDict(frozen=True)

    signal: str
    first_zero_crossing_hours: float = Field(ge=0.0)
    first_peak_hours: float = Field(ge=0.0)


class AlertRatePair(BaseModel):
    """What share of moments a model alerts on, declared-normal against the slice under review.

    The single pair of numbers the whole modelling-error finding rests on. If they agree, the alert
    load on the slice is the model's out-of-sample behaviour on ordinary operation and not a
    response to anything the slice contains.

    Attributes:
        reference_pct: Share of declared-normal moments with any departure outside the band.
        under_review_pct: The same over the normal-labelled moments of the slice under review.
        reference_hours: How much declared-normal data the first figure rests on.
    """

    model_config = ConfigDict(frozen=True)

    reference_pct: float = Field(ge=0.0, le=100.0)
    under_review_pct: float = Field(ge=0.0, le=100.0)
    reference_hours: float = Field(gt=0.0)

    @property
    def indistinguishable(self) -> bool:
        """Whether the two rates agree closely enough to call the slice's load ordinary.

        Two percentage points, declared here. Wider than any plausible sampling wobble on tens of
        thousands of moments and far narrower than the gap a real phenomenon would open.
        """
        return abs(self.reference_pct - self.under_review_pct) <= 2.0


class FitLengthPoint(BaseModel):
    """One point on a fit-length curve: how loud a model is when fitted on this much normal data.

    Attributes:
        timestamps: How many moments the fit used.
        hours: The same in hours.
        alerts: Per-signal alerts the fitted model raised on the slice under review.
        moments_pct: Share of the slice's moments with any departure.
        windows_caught: Attack windows the model's alerts overlapped.
        n_windows: Attack windows available to catch.
    """

    model_config = ConfigDict(frozen=True)

    timestamps: int = Field(gt=0)
    hours: float = Field(gt=0.0)
    alerts: int = Field(ge=0)
    moments_pct: float = Field(ge=0.0, le=100.0)
    windows_caught: int = Field(ge=0)
    n_windows: int = Field(ge=0)


def noise_scale_ratios(
    under_review: pandas.DataFrame, reference: pandas.DataFrame, signals: Sequence[str]
) -> dict[str, NoiseScaleRatio]:
    """Compare each signal's lag-1 jitter between a slice and a declared-normal reference.

    Args:
        under_review: Raw rows of the slice, in timestamp order.
        reference: Raw rows of the declared-normal reference, in timestamp order.
        signals: Signals to compare.

    Returns:
        One ratio per signal.

    Raises:
        KeyError: If a requested signal is absent from either frame, which would otherwise produce a
            ratio of nothing against nothing.
    """
    ratios: dict[str, NoiseScaleRatio] = {}
    for signal in signals:
        slice_jitter = numpy.abs(numpy.diff(under_review[signal].to_numpy(dtype=float)))
        reference_jitter = numpy.abs(numpy.diff(reference[signal].to_numpy(dtype=float)))
        ratios[signal] = NoiseScaleRatio(
            signal=signal,
            median_ratio=_ratio(numpy.median(slice_jitter), numpy.median(reference_jitter)),
            p99_ratio=_ratio(
                numpy.percentile(slice_jitter, 99), numpy.percentile(reference_jitter, 99)
            ),
        )
    return ratios


def trend_strengths(
    under_review: pandas.DataFrame, reference: pandas.DataFrame, signals: Sequence[str]
) -> dict[str, TrendStrength]:
    """Measure how monotone each signal is over a slice, and whether its envelope moved.

    Args:
        under_review: Raw rows of the slice, in timestamp order.
        reference: Raw rows of the declared-normal reference, in timestamp order.
        signals: Signals to measure.

    Returns:
        One trend strength per signal.
    """
    strengths: dict[str, TrendStrength] = {}
    for signal in signals:
        values = under_review[signal].to_numpy(dtype=float)
        baseline = reference[signal].to_numpy(dtype=float)
        low, high = numpy.percentile(baseline, [5, 95])
        slice_low, slice_high = numpy.percentile(values, [5, 95])
        width = float(high - low)
        shift = (abs(slice_low - low) + abs(slice_high - high)) / width if width else 0.0
        strengths[signal] = TrendStrength(
            signal=signal,
            rho_under_review=_spearman(values),
            rho_reference=_spearman(baseline),
            envelope_shift=float(shift),
        )
    return strengths


def cycle_periods(
    reference: pandas.DataFrame, signals: Sequence[str], *, sample_seconds: float
) -> dict[str, CyclePeriod]:
    """Read the dominant period of each signal off its autocorrelation on declared-normal data.

    The reference is used rather than the slice because a period has to be measured over many cycles
    and the slice is, by construction, short.

    Args:
        reference: Raw rows of the declared-normal reference, in timestamp order.
        signals: Signals to measure.
        sample_seconds: Seconds between consecutive rows.

    Returns:
        One period per signal. A signal with no negative autocorrelation anywhere — a monotone drift
        or a constant — reports zero for both lags rather than a fabricated period.

    Raises:
        ValueError: If ``sample_seconds`` is not positive, which would make every lag meaningless.
    """
    if sample_seconds <= 0.0:
        raise ValueError(f"sample_seconds must be positive, got {sample_seconds}")
    periods: dict[str, CyclePeriod] = {}
    for signal in signals:
        values = reference[signal].to_numpy(dtype=float)
        centred = values - values.mean()
        if not centred.any():
            periods[signal] = CyclePeriod(
                signal=signal, first_zero_crossing_hours=0.0, first_peak_hours=0.0
            )
            continue
        correlation = numpy.correlate(centred, centred, mode="full")[len(centred) - 1 :]
        correlation = correlation / correlation[0]
        negative = numpy.flatnonzero(correlation < 0.0)
        if negative.size == 0:
            periods[signal] = CyclePeriod(
                signal=signal, first_zero_crossing_hours=0.0, first_peak_hours=0.0
            )
            continue
        crossing = int(negative[0])
        peak = int(numpy.argmax(correlation[crossing:]) + crossing)
        periods[signal] = CyclePeriod(
            signal=signal,
            first_zero_crossing_hours=crossing * sample_seconds / _SECONDS_PER_HOUR,
            first_peak_hours=peak * sample_seconds / _SECONDS_PER_HOUR,
        )
    return periods


def sweep_transition(
    curve: Sequence[FitLengthPoint], *, factor: float = 5.0
) -> tuple[FitLengthPoint, FitLengthPoint] | None:
    """Return the pair of adjacent curve points a step change in alert load falls between.

    A fit-length curve that improves gradually and one that falls off a cliff mean different things:
    the first says more data always helps a little, the second says the fit was missing something
    structural and then had it. Naming the bracketing pair reports which, without picking a point on
    the curve as an operating point.

    Args:
        curve: Points in ascending fit length.
        factor: How large a drop in per-signal alerts counts as a step. Five, declared here.

    Returns:
        The ``(before, after)`` pair the step falls between, or ``None`` when the curve has no step.

    Raises:
        ValueError: If ``curve`` is not in ascending fit length, which would report a step where the
            data had merely been shuffled.
    """
    lengths = [point.timestamps for point in curve]
    if lengths != sorted(lengths):
        raise ValueError("curve must be in ascending fit length")
    for before, after in pairwise(curve):
        if after.alerts * factor < before.alerts:
            return before, after
    return None


def summarise_ratios(ratios: Mapping[str, NoiseScaleRatio]) -> str:
    """State a set of noise-scale ratios as a range, for a screen's basis line."""
    medians = [ratio.median_ratio for ratio in ratios.values()]
    p99s = [ratio.p99_ratio for ratio in ratios.values()]
    return (
        f"median ratios {min(medians):.2f}-{max(medians):.2f}, "
        f"99th-percentile ratios {min(p99s):.2f}-{max(p99s):.2f}"
    )


def _ratio(numerator: float, denominator: float) -> float:
    """Return a ratio, treating zero-over-zero as unchanged rather than as undefined."""
    if denominator == 0.0:
        return 1.0 if numerator == 0.0 else float("inf")
    return float(numerator / denominator)


def _spearman(values: numpy.ndarray) -> float:
    """Return the Spearman rank correlation of a series against its own position in time."""
    if len(values) < 2 or not numpy.ptp(values):
        return 0.0
    ranks = pandas.Series(values).rank().to_numpy(dtype=float)
    positions = numpy.arange(len(values), dtype=float)
    return float(numpy.corrcoef(positions, ranks)[0, 1])

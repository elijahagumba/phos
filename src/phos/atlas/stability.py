"""Plant health, expressed as numbers a process engineer would recognise.

Atlas's dashboards (PARTs 9-10) will report whether the plant is *stable* — not whether a
particular reading is odd, but whether the process as a whole still looks like itself. This module
builds the two such metrics that process telemetry can actually support, and refuses to build the
two it cannot.

- **Baseline similarity** — what proportion of a window's readings sat where the rest of the plant
  implied they should. It is deliberately a count rather than a squashed score: a count has no free
  parameter to tune, and "eleven readings in four hundred fell outside their band" is a sentence
  whose provenance an operator can walk back to individual measurements (Constitution §3.2).
- **Process-cycle deviation** — industrial processes repeat. `learn_process_cycle` finds the period
  a signal actually ran at during normal operation, and `process_cycle_deviation` measures how far
  a later window departs from that rhythm. A plant doing the right thing at the wrong time is a
  real fault mode, and it is invisible to any metric that ignores phase.

**Communication-timing and protocol-state stability used to be stubs here, and PART P3 retired
them.** Both were genuine Atlas metrics that raised `NotImplementedError` naming the one thing they
needed: per-packet observations, which PHOS had no adapter to produce. P2 produced them — and made
the honest answer *retirement rather than implementation*, because the packet adapter expresses both
signals better than a function returning one float ever could:

- **Communication timing** is `phos.atlas.packet.COMMAND_INTERVAL_MEAN_MS` and
  `COMMAND_INTERVAL_CV`, per device per window. A device's polling rhythm and how rigid it is.
- **Protocol state** is the per-function-code counts (`function_count_feature`) together with the
  command graph's `UNEXPECTED_COMMAND_FUNCTION` — literally "a function code never seen from that
  master", which is the example the retired stub's own docstring gave.

The difference is not presentational. Each of those is an ordinary `Observation`, so it is
baselined by PART 3's models, judged against a learned `ExpectedRange`, promoted through 4A's
evidence boundary, weighted by a fitted calibrator and measured by the PART 2 harness. A bare float
returned from this module would have had none of that: no baseline, no band, no calibration, no
provenance, and no way for Constitution §3.5 to say whether it was worth anything. Keeping the stubs
would have meant building a second, weaker path to a signal the adapter already carries properly.

What is *not* retired is the question those stubs stood for. "Is this plant's communication still
steady?" is answered by baselining the timing features; "is this conversation still following its
normal state machine?" by the function-count features and the graph. Both now go through
`phos.atlas.command_evidence`.
"""

import logging
from collections.abc import Sequence
from datetime import datetime, timedelta
from itertools import pairwise

import numpy
from pydantic import BaseModel, ConfigDict, Field

from phos.atlas.multivariate import MultivariateFittedModel
from phos.atlas.vectorise import NO_OBSERVATION
from phos.models import clamp_magnitude, model_key
from phos.ontology import EntityId, Observation, UtcDatetime

__all__ = [
    "ProcessCycle",
    "baseline_similarity",
    "dominant_period",
    "learn_process_cycle",
    "process_cycle_deviation",
]

logger = logging.getLogger(__name__)

MIN_CYCLE_STRENGTH = 0.3
"""Autocorrelation a candidate period must reach before a signal is called cyclic.

Below this the "period" is whatever noise happened to peak, and reporting a phase against it would
manufacture a rhythm the plant does not have.
"""


# ------------------------------------------------------------------------------------------------
# Baseline similarity
# ------------------------------------------------------------------------------------------------


def baseline_similarity(
    fitted: MultivariateFittedModel, observations: Sequence[Observation]
) -> float | None:
    """Return the share of a window's readings that stayed inside their expected band.

    Args:
        fitted: A fitted joint model. The window is judged against what *it* learned normal to be.
        observations: The window to assess. Readings of signals the model does not span are
            ignored, exactly as they are when scoring.

    Returns:
        A proportion in ``[0, 1]`` — 1.0 when every reading sat where the rest of the plant implied
        it should. ``None`` when the window contains no reading this model can speak about, either
        because it is empty, because it holds only signals outside the model's `SignalSpace`, or
        because the model learned nothing. A dashboard must show *no data* for that case, never
        perfect health.

    Note:
        The test is the same inclusive one `phos.reasoning.boundary.is_out_of_band` applies, so
        this number and the deviations the same model emits are two readings of one computation
        and cannot disagree. Carried-forward cells are excluded: a stale value is not a fresh
        reading, and counting it would let a quiet sensor inflate the plant's apparent health.
    """
    series, _, departure = fitted.departures(observations)
    if series.n_rows == 0:
        return None

    # Every surviving row was created because some signal was measured at that instant, so the
    # count below is never zero once there is a row at all.
    fresh = series.source_index != NO_OBSERVATION
    measured = int(numpy.count_nonzero(fresh))
    within = int(numpy.count_nonzero(fresh & (departure <= fitted.band_k)))
    logger.debug(
        "baseline similarity for %s: %d of %d readings within band", fitted.name, within, measured
    )
    return within / measured


# ------------------------------------------------------------------------------------------------
# Process cycle
# ------------------------------------------------------------------------------------------------


class ProcessCycle(BaseModel):
    """The rhythm one signal ran at during normal operation, and what each phase looked like.

    Phase is derived from the *timestamp* rather than from position in a list, so a window
    measured later can be compared against the cycle without having to start on a cycle boundary.
    That is what makes "the plant is doing the right thing at the wrong time" expressible.

    Attributes:
        entity_id: The entity whose signal this describes.
        feature: The signal.
        period: Length of one cycle, in samples.
        sample_interval: The spacing between consecutive samples during training, used with
            ``epoch`` to place a later reading in the cycle.
        epoch: The first training timestamp — phase zero.
        phase_mean: The learned mean value at each phase, ``period`` entries long.
        phase_stddev: The learned spread at each phase. Zero where a phase repeated exactly.
        strength: Autocorrelation at ``period``, in ``[-1, 1]``. How cyclic the signal really is,
            reported so a weak rhythm can be discounted rather than silently trusted.
        learned_from_window: ``(first, last)`` timestamps the cycle was learned from.

    Invariants:
        ``period >= 2``; ``phase_mean`` and ``phase_stddev`` are both ``period`` long.
    """

    model_config = ConfigDict(frozen=True)

    entity_id: EntityId
    feature: str
    period: int = Field(ge=2)
    sample_interval: timedelta
    epoch: UtcDatetime
    phase_mean: tuple[float, ...]
    phase_stddev: tuple[float, ...]
    strength: float = Field(ge=-1.0, le=1.0)
    learned_from_window: tuple[UtcDatetime, UtcDatetime]

    def phase_of(self, timestamp: datetime) -> int:
        """Return which phase of the cycle ``timestamp`` falls in."""
        elapsed = (timestamp - self.epoch) / self.sample_interval
        return round(elapsed) % self.period


def dominant_period(
    values: Sequence[float],
    *,
    max_period: int | None = None,
    min_strength: float = MIN_CYCLE_STRENGTH,
) -> int | None:
    """Return the period a series repeats at, in samples, or ``None`` if it does not repeat.

    See `_dominant_rhythm`, which does the work and also reports how strong the rhythm is.

    Args:
        values: The series, in time order.
        max_period: Longest period to consider.
        min_strength: Autocorrelation the best candidate must reach to count as a cycle.

    Returns:
        The period in samples, or ``None``.
    """
    rhythm = _dominant_rhythm(values, max_period=max_period, min_strength=min_strength)
    return None if rhythm is None else rhythm[0]


def _dominant_rhythm(
    values: Sequence[float],
    *,
    max_period: int | None = None,
    min_strength: float = MIN_CYCLE_STRENGTH,
) -> tuple[int, float] | None:
    """Return ``(period, strength)`` for a repeating series, or ``None`` if it does not repeat.

    Autocorrelation rather than an FFT: the answer wanted is a lag in samples, which is what an
    autocorrelation peak *is*, and reading it off a periodogram would mean interpolating between
    frequency bins for a number the correlation gives directly.

    The search starts only after the autocorrelation first goes negative. Without that, any
    smoothly drifting signal returns a period of one — consecutive samples of anything continuous
    are correlated, and that correlation is not a rhythm.

    Args:
        values: The series, in time order.
        max_period: Longest period to consider. Defaults to half the series, since a period longer
            than that is observed fewer than twice and cannot be told from a trend.
        min_strength: Autocorrelation the best candidate must reach to count as a cycle.

    Returns:
        The period in samples paired with its autocorrelation, or ``None`` for a series that is
        constant, too short, aperiodic, or whose only rhythm is longer than ``max_period``.
    """
    series = numpy.asarray(values, dtype=numpy.float64)
    limit = max_period if max_period is not None else len(series) // 2
    if len(series) < 4 or limit < 2:
        return None

    centred = series - numpy.mean(series)
    energy = float(numpy.dot(centred, centred))
    if energy == 0.0:
        return None

    limit = min(limit, len(series) - 2)
    correlation = numpy.asarray(
        [float(numpy.dot(centred[:-lag], centred[lag:])) / energy for lag in range(1, limit + 1)],
        dtype=numpy.float64,
    )

    negative = numpy.flatnonzero(correlation < 0.0)
    if negative.size == 0:
        return None
    searchable = correlation[negative[0] :]
    best = int(numpy.argmax(searchable))
    strength = float(searchable[best])
    if strength < min_strength:
        return None
    return int(negative[0]) + best + 1, strength


def learn_process_cycle(
    observations: Sequence[Observation],
    *,
    max_period: int | None = None,
    min_strength: float = MIN_CYCLE_STRENGTH,
) -> ProcessCycle | None:
    """Learn the rhythm of one signal from a stretch of normal operation.

    Args:
        observations: Readings of a **single** ``(entity, feature)`` signal, from an attack-free
            window. Sorted here, so input order does not matter.
        max_period: Passed to `dominant_period`.
        min_strength: Passed to `dominant_period`.

    Returns:
        The learned cycle, or ``None`` when the signal has no rhythm to learn. ``None`` is the
        honest answer for a signal that simply does not repeat, and callers must handle it rather
        than receive a period that is really just noise.

    Raises:
        ValueError: If there are no observations, or if they span more than one signal. Averaging
            two signals' phases would produce a cycle belonging to neither.
    """
    if not observations:
        raise ValueError("cannot learn a process cycle from no observations")
    signals = {model_key(observation) for observation in observations}
    if len(signals) > 1:
        raise ValueError(
            f"a process cycle describes one signal, but these observations span {len(signals)}: "
            + ", ".join(sorted(f"{entity}/{feature}" for entity, feature in signals))
        )

    ordered = sorted(observations, key=lambda observation: observation.timestamp)
    values = [observation.value for observation in ordered]
    rhythm = _dominant_rhythm(values, max_period=max_period, min_strength=min_strength)
    if rhythm is None:
        logger.debug("no dominant period in %d samples of %s", len(values), ordered[0].feature)
        return None
    period, strength = rhythm

    interval = _sample_interval(ordered)
    if interval is None:
        logger.debug(
            "%s has a rhythm of %d samples but no time between them; a phase cannot be placed",
            ordered[0].feature,
            period,
        )
        return None

    entity_id, feature = next(iter(signals))
    series = numpy.asarray(values, dtype=numpy.float64)
    phases = numpy.arange(len(series)) % period
    means = numpy.asarray([float(numpy.mean(series[phases == p])) for p in range(period)])
    stddevs = numpy.asarray([float(numpy.std(series[phases == p])) for p in range(period)])

    return ProcessCycle(
        entity_id=entity_id,
        feature=feature,
        period=period,
        sample_interval=interval,
        epoch=ordered[0].timestamp,
        phase_mean=tuple(float(value) for value in means),
        phase_stddev=tuple(float(value) for value in stddevs),
        strength=strength,
        learned_from_window=(ordered[0].timestamp, ordered[-1].timestamp),
    )


def process_cycle_deviation(cycle: ProcessCycle, observations: Sequence[Observation]) -> float:
    """Return how far a window departs from a learned cycle, in learned spreads.

    Each reading is placed in the cycle by its timestamp and compared against what that phase
    normally holds. A window running the same process at the same time as always scores near zero;
    one running at the wrong level, or the right level at the wrong moment, does not.

    Args:
        cycle: The learned rhythm.
        observations: The window to assess, all of the cycle's own signal.

    Returns:
        The mean absolute departure across the window, in phase standard deviations. Never
        negative; zero only for a window that matched every phase exactly.

    Raises:
        ValueError: If there are no observations, or if any of them belongs to a different signal
            than the one the cycle describes.
    """
    if not observations:
        raise ValueError("cannot measure cycle deviation over no observations")
    expected_signal = (cycle.entity_id, cycle.feature)
    for observation in observations:
        if model_key(observation) != expected_signal:
            entity_id, feature = model_key(observation)
            raise ValueError(
                f"this cycle describes {cycle.entity_id}/{cycle.feature}, but was given a "
                f"reading of {entity_id}/{feature}"
            )

    departures = []
    for observation in observations:
        phase = cycle.phase_of(observation.timestamp)
        spread = cycle.phase_stddev[phase]
        gap = observation.value - cycle.phase_mean[phase]
        departures.append(_phase_departure(gap, spread))
    return float(numpy.mean(departures))


def _phase_departure(gap: float, spread: float) -> float:
    """Return one reading's departure from its phase, in phase standard deviations.

    Mirrors `ExpectedRange.zscore` followed by `phos.models.clamp_magnitude`, including its answer
    for a phase that repeated exactly: any departure from a perfectly constant phase is infinitely
    surprising, and no departure at all is not surprising in the least. A cleanly periodic signal
    has many such phases, so this is the ordinary case rather than an edge one.
    """
    if spread > 0.0:
        return clamp_magnitude(gap / spread)
    return 0.0 if gap == 0.0 else clamp_magnitude(numpy.inf)


def _sample_interval(ordered: Sequence[Observation]) -> timedelta | None:
    """Return the typical spacing between consecutive readings, or ``None`` if there is none.

    The median rather than the mean, so one long gap in an otherwise regular capture does not
    stretch every phase calculation that follows it.
    """
    gaps = [
        (later.timestamp - earlier.timestamp).total_seconds()
        for earlier, later in pairwise(ordered)
    ]
    positive = [gap for gap in gaps if gap > 0.0]
    if not positive:
        return None
    return timedelta(seconds=float(numpy.median(positive)))

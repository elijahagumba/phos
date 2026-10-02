#!/usr/bin/env python3
"""The whole Sentiel vertical over a whole CERT release, and the detection number it publishes.

PART 6C built `phos.sentiel.SentielEngine` — score, promote through the evidence boundary, group
into behaviour events, reason per entity, narrate — and then recorded, in its own words, that it
"publishes no detection number, and PART 6B's stand unsuperseded", because the engine was exercised
on a hand-built fixture and a 400,000-row CERT slice and nowhere else. This script closes exactly
that gap and nothing wider. It builds no detection logic: it wires PART 6·D's intake, PART 6A's
enrichment, PART 6B's peer features and aggregated scoring, PART 4A's calibrator, and PART 6C's
engine into one pass over one release, and writes the result to the shared experiment log.

**What an engine alert is, and why it is not the same alert PART 6B counted.** A window enters the
alert set when it clears the budget on PART 6B's own aggregate score *and* at least one of its
features actually left its expected range — that is, when the engine has something it may build a
hypothesis on. The score ranking inside the budget is 6B's, unchanged; the vertical's contribution
is the second filter, which is 4A's evidence boundary used as a detector rather than only as a gate
into reasoning. A window can score highly on thirty-four contributions that all sit between
``emit_k`` (1.0) and ``band_k`` (3.0) and produce no evidence at all, so the two alert sets are
genuinely different and the difference is measurable.

**No number here reads the calibrator.** The ranking is the score and the filter is
`phos.reasoning.is_out_of_band`; neither consults a calibrated weight, and
``tests/sentiel/test_engine_runner.py`` asserts the alert set is byte-identical under two very
different calibrators. That is what keeps this script clear of Constitution §3.3: the hypothesis
confidences the engine produces are uncalibrated and are never surfaced, ranked into, or summed
into anything reported. The explanation census below counts *which* explanation led each story and
reports no confidence at all.

**The calibration slice costs one of the corpus's two insiders, and the arithmetic is forced.** A
calibrator must be fitted on a held-out slice carrying both classes
(`phos.reasoning.calibration`), r3.1's only labelled positives are two incidents, and the training
prefix is attack-free by construction. Two insiders in the test slice therefore leaves zero
positives for calibration: there is no configuration with a leak-free calibrator *and* PART 6B's
two-insider test half. This script takes the leak-free side — calibration runs from the first
labelled incident to the start of the second, and the test slice is everything from the second
incident onward — and pays for it in a window recall that can only be 0 or 1. Because that test
slice is **not** PART 6B's, a PART 6B-shaped control is measured on *this* slice in *this* run, and
that control is the only exact comparison the run contains. See ADR 0025.

**Memory.** ADR 0023 records that per-entity reasoning holds hypotheses proportional to the
population and that "a corpus-scale runner should stream by entity rather than hold all of them".
At 34 features r3.1's test half is about 7 million `Observation` objects, which no ordinary machine
will hold, so the corpus is read **once**: the attack-free prefix is fitted and dropped, the
calibration slice is reduced to ``(score, label)`` floats as it streams, and the test half is
scored and discarded except for one representative observation per entity-window and the full
observation set of the ``--max-explained`` highest-scoring windows — the only ones an operating
point on 6B's budget curve would ever ask the engine to explain.

Usage::

    python scripts/fetch_datasets.py cert-insider-threat --yes   # ~4.25 GB, once
    python scripts/evaluate_sentiel_engine.py                    # the PART 6C engine number
    python scripts/evaluate_sentiel_engine.py --max-events 3000000 --no-log   # a bounded probe

If ``phos`` is not importable, the repository's ``src`` is not on the path: prefix the command with
``PYTHONPATH=src``. ``pytest`` adds it from ``pyproject.toml`` and a bare interpreter does not.
"""

from __future__ import annotations

import argparse
import heapq
import itertools
import json
import logging
import resource
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping, Sequence
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Final, NamedTuple

import numpy
from pydantic import BaseModel, ConfigDict, Field

from phos.eval import (
    Dataset,
    Detection,
    EvalConfig,
    EvaluationReport,
    append_to_experiment_log,
    current_git_commit,
)
from phos.models import GaussianBaseline
from phos.models.base import StaticRangeFittedModel
from phos.ontology import Domain, EntityId, Narrative, Observation
from phos.reasoning import FittedCalibrator, IsotonicCalibrator, ReasoningConfig
from phos.sentiel import (
    DEFAULT_GROUP_ATTRIBUTE,
    AggregationPolicy,
    CertReader,
    CertRelease,
    EntityLabelledInterval,
    FeatureSet,
    Featuriser,
    PeerGroups,
    PeerPolicy,
    PrecomputedDetector,
    ScoredWindow,
    ScoringSummary,
    SentielConfig,
    SentielEngine,
    WindowScorer,
    annotate_with_caveats,
    base_rate,
    evaluate_entity_aware,
    is_behaviour_event,
    peer_source_note,
    precision_policy,
    read_insiders,
    static_range_model,
    user_id_of,
)

REPO_ROOT: Final = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR: Final = REPO_ROOT / "data"
MANIFEST_NAME: Final = "sentiel-manifest.json"

_LOG_EVERY: Final = 500_000
_CALIBRATION_BATCH: Final = 100_000
_BYTES_PER_GB: Final = 1024.0**3

logger = logging.getLogger("phos.sentiel.engine_runner")


class EngineRunError(RuntimeError):
    """Raised when the corpus or its labels are not in a state this script can measure."""


# ------------------------------------------------------------------------------------------------
# What must travel with any number this runner produces
# ------------------------------------------------------------------------------------------------

CALIBRATION_SPENDS_AN_INSIDER_CAVEAT: Final = (
    "THE TEST SLICE HERE IS NOT PART 6B's, AND THE REASON IS ARITHMETIC RATHER THAN PREFERENCE. "
    "phos.reasoning.calibration refuses a single-class fit, so a calibrator needs a held-out slice "
    "carrying both classes; the training prefix is attack-free by construction; and CERT r3.1 "
    "labels exactly TWO malicious users. Two insiders in the test slice therefore leaves ZERO "
    "labelled positives anywhere a calibrator could be fitted without reading the test half. There "
    "is no configuration of this corpus with both a leak-free calibrator and PART 6B's "
    "two-insider test half. This run spends the EARLIER incident on calibration and measures on "
    "the LATER one, so (a) window recall on this slice can take only the values 0 and 1 — coarser "
    "than PART 6B's 0/0.5/1 and emphatically not a rate, and (b) precisions here are NOT "
    "like-for-like with the logged PART 6B rows, which were measured over a longer slice with a "
    "different base rate. The only exact comparison in this run is against the PART 6B-shaped "
    "control scored on THIS slice, from THIS corpus read and THIS fitted model."
)

ENGINE_ALERT_UNIT_CAVEAT: Final = (
    "THE ENGINE'S ALERT UNIT, STATED SO IT IS NOT ASSUMED. An engine alert is an entity-window "
    "that (i) falls inside the alert budget on PART 6B's aggregate window score and (ii) produced "
    "at least one BEHAVIOUR EVENT — at least one feature whose value actually left its expected "
    "range under phos.reasoning.is_out_of_band. The ranking inside the budget is PART 6B's score, "
    "unchanged and re-derived from the same fitted model; the vertical's whole contribution to "
    "the DETECTION number is the second filter. A window can score highly on contributions that "
    "all sit between emit_k and band_k and yield no evidence at all, which is why the two alert "
    "sets differ. NEITHER STEP READS THE CALIBRATOR, so no reported number depends on the "
    "uncalibrated hypothesis confidences Constitution §3.3 forbids surfacing; a test asserts the "
    "alert set is identical under two different calibrators."
)

PER_DAY_BUDGET_CAVEAT: Final = (
    "ALERTS PER DAY IS A MEAN, AND IT IS DERIVED RATHER THAN ASSERTED. The alert unit is one "
    "entity-window and a window is one day (PART 6·D), so the alerts-per-day figure is the alert "
    "count divided by the number of DISTINCT one-day windows the test slice covers — a count read "
    "off the corpus, reported beside every figure that uses it. It says nothing about how the "
    "alerts are distributed: they are not uniform across days, so the BUSIEST SINGLE DAY is "
    "reported next to the mean and is the number an analyst would actually face. A SOC budget "
    "expressed per day is converted to a total alert budget by the same division, and both the "
    "day count and the resulting totals are printed so the arithmetic can be checked."
)

EXPLAINED_CEILING_CAVEAT: Final = (
    "THE ENGINE IS RUN ON AN OPERATING POINT, NOT ON THE WHOLE CORPUS, AND THE CEILING IS "
    "REPORTED. Explaining every entity-window in a corpus explains nothing (phos.sentiel."
    "SentielConfig.alert_threshold says so), and holding 7 million observations to do it is not "
    "possible on an ordinary machine, so only the --max-explained highest-scoring windows keep "
    "their observations and reach the engine. Every alert budget evaluated here is at or below "
    "that ceiling; a budget above it would be reported as unreachable rather than silently "
    "truncated. The SCORING pass, and therefore the PART 6B control and the base rate, still cover "
    "every entity-window in the test slice."
)

ENGINE_RUNNER_CAVEATS: Final[tuple[str, ...]] = (
    CALIBRATION_SPENDS_AN_INSIDER_CAVEAT,
    ENGINE_ALERT_UNIT_CAVEAT,
    PER_DAY_BUDGET_CAVEAT,
    EXPLAINED_CEILING_CAVEAT,
)
"""Everything this runner adds to `phos.sentiel.SENTIEL_VERTICAL_CAVEATS`.

Attached to the logged report rather than kept in a document, because a document is not what a
reader of ``eval_runs/log.jsonl`` has in front of them.
"""


def partial_corpus_caveat(events_read: int, bounded: bool) -> str:
    """Return the caveat naming how much of the corpus a bounded read actually covered.

    Args:
        events_read: Activity events the reader consumed.
        bounded: Whether ``--max-events`` stopped the read before the corpus ended.

    Returns:
        A sentence stating the read was complete, or one naming the event count it stopped at.
        Never silence: a number measured on part of a corpus must say so beside itself.
    """
    if not bounded:
        return (
            f"CORPUS COVERAGE: the read was NOT bounded — every activity event in the release was "
            f"consumed ({events_read:,} events)."
        )
    return (
        f"PARTIAL CORPUS: --max-events stopped the read after {events_read:,} activity events, so "
        "every number here rests on a time-ordered PREFIX of the release rather than on the whole "
        "of it. The prefix is a prefix in TIME, so it is not a sample of the corpus: later months "
        "are absent entirely, and any insider whose incident falls in them cannot be found or "
        "missed. This is a probe, not a measurement."
    )


# ------------------------------------------------------------------------------------------------
# The split, derived from the corpus's own ground truth
# ------------------------------------------------------------------------------------------------


class SlicePlan(BaseModel):
    """Where the three slices of the corpus begin and end, and which insider paid for which.

    Attributes:
        train_end: First instant of the earliest labelled incident. The training prefix is
            everything strictly before it, which is exactly `phos.models.train_test_split`'s
            attack-free prefix and exactly the prefix PART 6B fitted on.
        calib_end: First instant of the earliest incident belonging to a *different* user. The
            calibration slice runs from ``train_end`` up to it, so it holds the first user's whole
            incident and none of the second's.
        calibration_labels: The incidents spent on calibration.
        test_labels: The incidents left to measure on.

    Invariants:
        ``train_end < calib_end``; both label lists are non-empty and name disjoint users.
    """

    model_config = ConfigDict(frozen=True)

    train_end: datetime
    calib_end: datetime
    calibration_labels: tuple[EntityLabelledInterval, ...] = Field(min_length=1)
    test_labels: tuple[EntityLabelledInterval, ...] = Field(min_length=1)

    def note(self) -> str:
        """Return the one line a report carries so the split is never inferred from the numbers."""
        return (
            f"SPLIT (derived from the corpus's own ground truth, not from a fraction): train = "
            f"everything before {self.train_end.isoformat()}, the first labelled incident, which "
            f"is PART 6B's attack-free prefix unchanged. Calibration = "
            f"{self.train_end.isoformat()} to {self.calib_end.isoformat()}, holding "
            + ", ".join(
                f"{label.user_id}/scenario-{label.scenario}" for label in self.calibration_labels
            )
            + f". Test = {self.calib_end.isoformat()} onward, holding "
            + ", ".join(f"{label.user_id}/scenario-{label.scenario}" for label in self.test_labels)
            + "."
        )


def plan_slices(labels: Sequence[EntityLabelledInterval]) -> SlicePlan:
    """Divide the corpus timeline using the labels alone, spending the earliest insider on fitting.

    The two boundaries are read off ground truth rather than chosen: the training prefix ends at
    the first labelled incident, because a model that learns an attack as normal cannot be
    surprised by it later, and the calibration slice ends where the *next user's* incident begins,
    because that is the latest cut that keeps the calibration slice's positives out of the test
    slice and the test slice's positives out of the calibrator. Nothing here is a tunable.

    Args:
        labels: Every entity-scoped label for the release, in any order.

    Returns:
        The plan, with each incident assigned to exactly one of the two labelled slices.

    Raises:
        EngineRunError: If the corpus labels fewer than two distinct users, in which case no cut
            leaves both a two-class calibration slice and a labelled test slice, and the run would
            report a recall with no denominator or a calibrator with one class.
    """
    ordered = sorted(labels, key=lambda label: (label.start, label.user_id))
    first_user = ordered[0].user_id
    later = [label for label in ordered if label.user_id != first_user]
    if not later:
        raise EngineRunError(
            f"the release labels only one malicious user ({first_user}), so no cut of the "
            "timeline leaves both a calibration slice with two classes and a test slice with a "
            "labelled positive. A calibrator fitted on one class is a constant "
            "(phos.reasoning.calibration), and a recall measured against no positive is vacuous, "
            "so this is refused rather than reported"
        )
    calib_end = later[0].start
    return SlicePlan(
        train_end=ordered[0].start,
        calib_end=calib_end,
        calibration_labels=tuple(label for label in ordered if label.start < calib_end),
        test_labels=tuple(label for label in ordered if label.start >= calib_end),
    )


# ------------------------------------------------------------------------------------------------
# What an analyst's day actually looks like
# ------------------------------------------------------------------------------------------------


class DailyLoad(BaseModel):
    """How an alert total spreads over the days the test slice covers.

    Attributes:
        days: Distinct one-day windows in the test slice. The denominator, counted off the corpus.
        alerts: Alerts in the set being described.
        mean_per_day: ``alerts / days``.
        busiest_day_alerts: Alerts on the single worst day.
        busiest_day: That day, so the claim can be checked against the corpus.
    """

    model_config = ConfigDict(frozen=True)

    days: int = Field(ge=1)
    alerts: int = Field(ge=0)
    mean_per_day: float = Field(ge=0.0)
    busiest_day_alerts: int = Field(ge=0)
    busiest_day: str | None = None

    def note(self) -> str:
        """Return the one line that puts an alert total into the unit a SOC budget is written in."""
        return (
            f"DAILY LOAD: {self.alerts:,} alerts over {self.days:,} distinct one-day windows = "
            f"{self.mean_per_day:.2f} alerts/day on average; the busiest single day carried "
            f"{self.busiest_day_alerts:,}"
            + (f" (on {self.busiest_day})" if self.busiest_day else "")
            + "."
        )


def daily_load(alerts: Sequence[Detection], days: int) -> DailyLoad:
    """Return how ``alerts`` spread over the ``days`` the test slice covers.

    Args:
        alerts: The alert set. Each carries the entity-window's timestamp, and a window is a day.
        days: Distinct one-day windows in the test slice, counted from the corpus.

    Returns:
        The mean and the worst day. The mean is what a budget is written in; the worst day is what
        an analyst experiences, and reporting only the first would be the flattering half.

    Raises:
        ValueError: If ``days`` is not positive, which would make the mean undefined rather than
            large.
    """
    if days <= 0:
        raise ValueError(f"a daily load needs at least one day to divide by, got {days}")
    per_day = Counter(alert.timestamp.date() for alert in alerts)
    busiest: tuple[date, int] | None = None
    for day, count in sorted(per_day.items()):
        if busiest is None or count > busiest[1]:
            busiest = (day, count)
    return DailyLoad(
        days=days,
        alerts=len(alerts),
        mean_per_day=len(alerts) / days,
        busiest_day_alerts=busiest[1] if busiest else 0,
        busiest_day=busiest[0].isoformat() if busiest else None,
    )


def soc_budgets(days: int, rates: Sequence[float]) -> dict[float, int]:
    """Return the total alert budget each per-day SOC rate corresponds to on this test slice.

    The conversion the programme target needs, done as division rather than asserted: a budget of
    ``r`` alerts a day over a slice covering ``days`` days is ``round(r * days)`` alerts in total.

    Args:
        days: Distinct one-day windows in the test slice.
        rates: Alerts per day a SOC is assumed able to work.

    Returns:
        ``rate -> total alerts``, dropping any rate that rounds to nothing.
    """
    return {rate: round(rate * days) for rate in rates if round(rate * days) > 0}


# ------------------------------------------------------------------------------------------------
# Holding only the windows an operating point would ever ask about
# ------------------------------------------------------------------------------------------------


class RetainedWindows:
    """The highest-scoring entity-windows, with the observations behind them, bounded in memory.

    `WindowScorer` drops a window's observations once it has scored them and PART 6C may not
    change it, so this keeps a parallel index and then throws away all but the best ``capacity``
    windows. Mutable run state, created inside the call that uses it and never shared.

    The bound is what makes a corpus-scale run possible at all: 34 features over r3.1's test half
    is about 7 million `Observation` objects, and an operating point on PART 6B's budget curve
    never asks about more than a few thousand windows.
    """

    __slots__ = ("_capacity", "_heap", "_observations")

    def __init__(self, capacity: int) -> None:
        """Create an empty retainer.

        Args:
            capacity: How many windows to keep. Must be positive.

        Raises:
            ValueError: If ``capacity`` is not positive, which would retain nothing and leave the
                engine with an empty corpus while every other number looked normal.
        """
        if capacity <= 0:
            raise ValueError(f"a retainer must keep at least one window, got {capacity}")
        self._capacity = capacity
        self._heap: list[tuple[float, datetime, EntityId]] = []
        self._observations: dict[tuple[EntityId, datetime], list[Observation]] = {}

    def offer(self, window: ScoredWindow, observations: Sequence[Observation]) -> None:
        """Keep this window if it is among the best seen, dropping the weakest if it is not.

        Args:
            window: The scored entity-window.
            observations: Every observation the window was scored from.

        Note:
            Ties are broken by ``(timestamp, entity_id)``, which is unique per window, so the
            retained set is a function of the corpus rather than of arrival order.
        """
        entry = (window.score, window.timestamp, window.entity_id)
        key = (window.entity_id, window.timestamp)
        if len(self._heap) < self._capacity:
            heapq.heappush(self._heap, entry)
            self._observations[key] = list(observations)
            return
        if entry <= self._heap[0]:
            return
        _, evicted_time, evicted_entity = heapq.heapreplace(self._heap, entry)
        del self._observations[(evicted_entity, evicted_time)]
        self._observations[key] = list(observations)

    def threshold(self) -> float:
        """Return the weakest retained score — the operating point retention itself imposes."""
        return self._heap[0][0] if self._heap else 0.0

    def observations(self) -> list[Observation]:
        """Return every retained observation, time-ordered, ready to be a `Dataset`."""
        return sorted(
            itertools.chain.from_iterable(self._observations.values()),
            key=lambda observation: (observation.timestamp, observation.entity_ids[0]),
        )

    def __len__(self) -> int:
        """Return how many windows are retained."""
        return len(self._heap)


# ------------------------------------------------------------------------------------------------
# One pass over the release
# ------------------------------------------------------------------------------------------------


class CorpusPass(NamedTuple):
    """Everything one read of a release yields, with the corpus itself already discarded."""

    fitted: StaticRangeFittedModel
    calibrator: FittedCalibrator
    detections: list[Detection]
    windows: list[Observation]
    retained: RetainedWindows
    scoring: ScoringSummary
    events_read: int
    n_train: int
    n_calibration_points: int
    n_calibration_positives: int
    test_days: int


def calibration_signal(
    fitted: StaticRangeFittedModel,
    observations: Sequence[Observation],
    labels: Sequence[EntityLabelledInterval],
) -> tuple[list[float], list[float]]:
    """Return one ``(magnitude, label)`` pair per candidate deviation, labelled per **entity**.

    `phos.reasoning.scores_and_labels_from` does this job for Atlas and labels by time alone, which
    for an organisation is the error `phos.sentiel.labels` exists to prevent: it would call every
    one of a thousand colleagues' observations malicious for as long as one insider was active.
    This is that function with the entity restored, and nothing else changed — candidates rather
    than out-of-band deviations, because the calibrator's job is to map the score distribution the
    harness actually sweeps.

    Args:
        fitted: The model fitted on the training prefix.
        observations: A batch of calibration-slice observations.
        labels: Entity-scoped ground truth for the calibration slice.

    Returns:
        ``(magnitudes, labels)`` as parallel lists, one row per candidate deviation.

    Raises:
        ValueError: If the model returns a deviation for an observation this batch does not hold,
            which would be a label that cannot be traced to a measurement (Constitution §3.2).
    """
    by_id = {observation.id: observation for observation in observations}
    magnitudes: list[float] = []
    outcomes: list[float] = []
    for deviation in fitted.score(observations):
        observation = by_id.get(deviation.observation_id)
        if observation is None:
            raise ValueError(
                f"{fitted.name} produced a deviation for unknown observation "
                f"{deviation.observation_id!r}, which cannot be labelled from this batch"
            )
        user_id = user_id_of(observation.entity_ids[0])
        magnitudes.append(deviation.magnitude)
        outcomes.append(
            float(any(label.contains(user_id, observation.timestamp) for label in labels))
        )
    return magnitudes, outcomes


def read_corpus(
    stream: Iterator[Observation],
    plan: SlicePlan,
    policy: AggregationPolicy,
    min_samples: int,
    capacity: int,
    seed: int,
    events_read: Iterable[int],
) -> CorpusPass:
    """Fit, calibrate and score in a single time-ordered pass, never holding the corpus.

    The three slices are contiguous and in time order, so one pass can do all three jobs: the
    prefix is accumulated and fitted and then dropped; the calibration slice is reduced to
    ``(magnitude, label)`` floats in batches as it arrives; and the test slice is scored window by
    window, keeping one representative observation per window for the evaluation's `Dataset` and
    the full observation set of only the best ``capacity`` windows.

    Args:
        stream: The featurised observation stream, in non-decreasing timestamp order.
        plan: Where the slices begin and end.
        policy: How per-feature contributions combine into a window score.
        min_samples: Fewest training points a baseline needs.
        capacity: How many top-scoring windows keep their observations.
        seed: Recorded on the calibrator.
        events_read: A one-element mutable view of how many activity events the reader consumed,
            read after the stream is exhausted. Passed rather than counted here because the count
            belongs to the reader underneath the featuriser.

    Returns:
        The finished pass.

    Raises:
        EngineRunError: If any of the three slices is empty, or the calibration slice carries only
            one class. Each is a corpus that cannot support an honest measurement, and each is
            refused rather than reported.
    """
    training: list[Observation] = []
    pending: Observation | None = None
    for observation in stream:
        if observation.timestamp >= plan.train_end:
            pending = observation
            break
        training.append(observation)
    if not training:
        raise EngineRunError(
            f"the training prefix is empty: the earliest labelled incident is at "
            f"{plan.train_end.isoformat()}, at or before the corpus's first observation, so there "
            "is no attack-free history to learn normal from"
        )
    n_train = len(training)
    fitted = static_range_model(GaussianBaseline(min_samples=min_samples).fit(training))
    logger.info(
        "fitted %s on %d training observations up to %s; dropping them before the rest of the pass",
        fitted.name,
        n_train,
        training[-1].timestamp.date(),
    )
    training.clear()

    remainder = stream if pending is None else itertools.chain([pending], stream)
    magnitudes, outcomes, remainder = _calibration_pairs(fitted, remainder, plan)
    if not magnitudes:
        raise EngineRunError(
            f"the calibration slice {plan.train_end.isoformat()} to {plan.calib_end.isoformat()} "
            "produced no candidate deviation, so there is nothing to fit a calibrator on"
        )
    positives = int(sum(outcomes))
    try:
        calibrator = IsotonicCalibrator(seed=seed).fit(
            numpy.asarray(magnitudes, dtype=float), numpy.asarray(outcomes, dtype=float)
        )
    except ValueError as error:
        raise EngineRunError(
            f"the calibration slice cannot fit a calibrator: {error}. It holds "
            f"{len(magnitudes)} candidate deviation(s), {positives} of them inside a labelled "
            "insider's window"
        ) from error

    detections, windows, retained, scoring = _score_test_slice(fitted, remainder, policy, capacity)
    if not windows:
        raise EngineRunError(
            f"the test slice from {plan.calib_end.isoformat()} onward is empty, so there is "
            "nothing to measure on"
        )
    days = len({observation.timestamp.date() for observation in windows})
    return CorpusPass(
        fitted=fitted,
        calibrator=calibrator,
        detections=detections,
        windows=windows,
        retained=retained,
        scoring=scoring,
        events_read=next(iter(events_read)),
        n_train=n_train,
        n_calibration_points=len(magnitudes),
        n_calibration_positives=positives,
        test_days=days,
    )


def _calibration_pairs(
    fitted: StaticRangeFittedModel, stream: Iterator[Observation], plan: SlicePlan
) -> tuple[list[float], list[float], Iterator[Observation]]:
    """Reduce the calibration slice to ``(magnitude, label)`` floats and hand the rest back."""
    magnitudes: list[float] = []
    outcomes: list[float] = []
    batch: list[Observation] = []
    pending: Observation | None = None

    def drain() -> None:
        scores, labels = calibration_signal(fitted, batch, plan.calibration_labels)
        magnitudes.extend(scores)
        outcomes.extend(labels)
        batch.clear()

    for observation in stream:
        if observation.timestamp >= plan.calib_end:
            pending = observation
            break
        batch.append(observation)
        if len(batch) >= _CALIBRATION_BATCH:
            drain()
    drain()
    logger.info(
        "calibration slice: %d candidate deviations, %d inside a labelled insider's window",
        len(magnitudes),
        int(sum(outcomes)),
    )
    return magnitudes, outcomes, stream if pending is None else itertools.chain([pending], stream)


def _score_test_slice(
    fitted: StaticRangeFittedModel,
    stream: Iterator[Observation],
    policy: AggregationPolicy,
    capacity: int,
) -> tuple[list[Detection], list[Observation], RetainedWindows, ScoringSummary]:
    """Score the test slice as it streams, keeping one row per window and the best windows whole."""
    scorer = WindowScorer(fitted, policy)
    retained = RetainedWindows(capacity)
    buffers: dict[tuple[EntityId, datetime], list[Observation]] = {}
    detections: list[Detection] = []
    windows: list[Observation] = []
    read = 0

    def drain(scored: Sequence[ScoredWindow]) -> None:
        for window in scored:
            sources = buffers.pop((window.entity_id, window.timestamp), [])
            detections.append(window.as_detection(policy.score_scale))
            windows.append(sources[0])
            retained.offer(window, sources)

    for observation in stream:
        read += 1
        if read % _LOG_EVERY == 0:
            logger.info(
                "test slice: %d observations scored into %d entity-windows (retaining %d)",
                read,
                len(windows),
                len(retained),
            )
        drain(scorer.push(observation))
        buffers.setdefault((observation.entity_ids[0], observation.timestamp), []).append(
            observation
        )
    drain(scorer.close())
    logger.info(
        "test slice: %d observations scored into %d entity-windows; %d retained whole above "
        "score %.4f",
        read,
        len(windows),
        len(retained),
        retained.threshold(),
    )
    return detections, windows, retained, scorer.summary()


# ------------------------------------------------------------------------------------------------
# The engine's alert set, and what it explained
# ------------------------------------------------------------------------------------------------


def engine_alerts(engine: SentielEngine, score_scale: float) -> list[Detection]:
    """Return one alert per explained entity-window that produced at least one behaviour event.

    The alert is built by `phos.sentiel.ScoredWindow.as_detection`, exactly as PART 6B's alerts
    are, so precision, calibration error and every other metric are computed on the same footing
    and the only difference between the two alert sets is *which windows are in them*.

    Args:
        engine: An engine that has just run. Read through its store and its explained windows.
        score_scale: The aggregation policy's scale, reused for the confidence squash.

    Returns:
        Detections ordered by timestamp then entity, one per surviving entity-window.

    Raises:
        ValueError: If a behaviour event names a window the engine did not report explaining,
            which would be an alert with no score to rank it by.
    """
    explained = {
        (window.entity_id, window.timestamp): window for window in engine.explained_windows()
    }
    keys = {
        (evidence.entity_ids[0], evidence.timestamp)
        for evidence in engine.store.evidence(Domain.SENTIEL)
        if is_behaviour_event(evidence)
    }
    alerts: list[Detection] = []
    for key in sorted(keys, key=lambda item: (item[1], item[0])):
        window = explained.get(key)
        if window is None:
            raise ValueError(
                f"a behaviour event names entity-window {key!r}, which this engine did not report "
                "explaining, so the alert built from it would have no score to rank it by"
            )
        alerts.append(window.as_detection(score_scale))
    return alerts


def explanation_census(
    engine: SentielEngine,
    narratives: Sequence[Narrative],
    labels: Sequence[EntityLabelledInterval],
) -> str:
    """Return how often each explanation led a story, and what led the labelled insider's.

    Counts of leading template ids and **no confidence at all**. The confidences behind the
    ordering are uncalibrated (`phos.sentiel.UNCALIBRATED_HYPOTHESIS_CONFIDENCE_CAVEAT`) and may
    not be surfaced under Constitution §3.3; which explanation came out in front is an ordering
    rather than a probability, and is the most that may honestly be said.

    Args:
        engine: The engine that produced the stories, read for its hypotheses.
        narratives: The stories, in the order the engine returned them.
        labels: Entity-scoped ground truth for the test slice.

    Returns:
        A single line, appended to every logged report.
    """
    malicious = {label.user_id for label in labels}
    overall: Counter[str] = Counter()
    for_insiders: Counter[str] = Counter()
    for narrative in narratives:
        leading = _leading_template(engine, narrative)
        if leading is None:  # pragma: no cover - a narrative always cites its explanations
            continue
        overall[leading] += 1
        if _users_of(engine, narrative) & malicious:
            for_insiders[leading] += 1
    return (
        f"LEADING EXPLANATIONS ACROSS {len(narratives):,} STORIES (an ORDERING, never a "
        "probability — the confidences behind it are uncalibrated and are not reported): "
        + (", ".join(f"{name} {count:,}" for name, count in sorted(overall.items())) or "none")
        + ". For the labelled insider(s): "
        + (", ".join(f"{name} {count:,}" for name, count in sorted(for_insiders.items())) or "none")
        + "."
    )


def _leading_template(engine: SentielEngine, narrative: Narrative) -> str | None:
    """Return the template id of a story's leading explanation, or ``None`` if it cites none."""
    for hypothesis_id in narrative.hypothesis_ids:
        hypothesis = engine.store.get_hypothesis(hypothesis_id)
        if hypothesis is not None:
            return hypothesis.template_id
    return None  # pragma: no cover - the engine stores every hypothesis it cites


def _users_of(engine: SentielEngine, narrative: Narrative) -> set[str]:
    """Return the users a story's evidence is about."""
    users: set[str] = set()
    for evidence_id in narrative.evidence_ids:
        evidence = engine.store.get_evidence(evidence_id)
        if evidence is not None:
            users |= {user_id_of(entity_id) for entity_id in evidence.entity_ids}
    return users


# ------------------------------------------------------------------------------------------------
# Comparison
# ------------------------------------------------------------------------------------------------


class ReferenceRun(BaseModel):
    """A previously logged PART 6B row, kept so this run's number is never reported alone.

    Attributes:
        label: Which subset and budget it describes.
        commit: The commit the number came from.
        dataset_name: The corpus and split it was measured on.
        n_alerts: The alert budget it was measured at.
        precision: Fraction of its alerts that named the right user in the right window.
        window_recall: Fraction of labelled malicious windows it caught. Not quotable at two
            insiders, and carried only because omitting it would invite a reader to assume it.
    """

    model_config = ConfigDict(frozen=True)

    label: str
    commit: str
    dataset_name: str
    n_alerts: int = Field(ge=1)
    precision: float = Field(ge=0.0, le=1.0)
    window_recall: float = Field(ge=0.0, le=1.0)


BASELINE_6B: Final[tuple[ReferenceRun, ...]] = (
    ReferenceRun(
        label="6B peer set (34 features)",
        commit="b71c40f",
        dataset_name="cert-r3.1-user-day-peer-test",
        n_alerts=48,
        precision=0.104167,
        window_recall=0.5,
    ),
    ReferenceRun(
        label="6B enriched control (26 features)",
        commit="b71c40f",
        dataset_name="cert-r3.1-user-day-peer-test",
        n_alerts=48,
        precision=0.083333,
        window_recall=0.5,
    ),
    ReferenceRun(
        label="6B peer set (34 features)",
        commit="b71c40f",
        dataset_name="cert-r3.1-user-day-peer-test",
        n_alerts=1_668,
        precision=0.004796,
        window_recall=1.0,
    ),
)
"""PART 6B's standing numbers, transcribed from ``eval_runs/log.jsonl`` at commit ``b71c40f``.

Context rather than a like-for-like comparison, and the difference matters: 6B measured over
210,814 entity-windows containing 53 malicious ones from two insiders, and this run measures over
a shorter slice with one insider, because `CALIBRATION_SPENDS_AN_INSIDER_CAVEAT`. The exact
comparison in every run is the PART 6B-shaped control scored on the same slice in the same pass.
"""


def side_by_side(
    engine_report: EvaluationReport,
    control_report: EvaluationReport,
    counts: Mapping[str, int],
    load: DailyLoad,
) -> str:
    """Return the comparison stamped onto every logged report.

    A number on its own invites the reader to supply their own baseline, so this refuses to let one
    travel alone: the PART 6B-shaped control from the same corpus read, this run's engine, both
    read against the alert-on-everything floor, and PART 6B's logged rows as distant context with
    their different denominator stated.

    Args:
        engine_report: The vertical's report at one budget.
        control_report: The PART 6B-shaped report at the same budget, from the same run.
        counts: `phos.sentiel.base_rate`'s malicious and benign user-window counts for this slice.
        load: How the engine's alerts spread over the days of the slice.

    Returns:
        A single string.
    """
    total = counts["malicious_user_windows"] + counts["benign_user_windows"]
    trivial = counts["malicious_user_windows"] / total if total else 0.0
    engine_multiple = engine_report.precision / trivial if trivial > 0.0 else 0.0
    control_multiple = control_report.precision / trivial if trivial > 0.0 else 0.0
    return (
        f"LIKE-FOR-LIKE, ONE CORPUS READ, ONE FITTED MODEL, ONE SLICE. (1) PART 6B-SHAPED CONTROL "
        f"(one alert per entity-window, ranked by the aggregate score, no evidence boundary): "
        f"{control_report.n_alerts:,} alerts, precision {control_report.precision:.6f} = "
        f"{control_multiple:.2f}x the alert-on-everything floor, window recall "
        f"{control_report.window_recall:.1f}. (2) THIS RUN, the PART 6C vertical (the same ranking "
        f"filtered to windows that produced a behaviour event): {engine_report.n_alerts:,} alerts, "
        f"precision {engine_report.precision:.6f} = {engine_multiple:.2f}x that floor, window "
        f"recall {engine_report.window_recall:.1f}. Floor: "
        f"{counts['malicious_user_windows']} malicious of {total:,} entity-windows. {load.note()} "
        "DISTANT CONTEXT, NOT LIKE-FOR-LIKE — PART 6B's logged rows on its own longer, "
        "two-insider slice: "
        + "; ".join(
            f"{reference.label} at {reference.n_alerts:,} alerts, precision "
            f"{reference.precision:.6f}, recall {reference.window_recall:.1f} (commit "
            f"{reference.commit})"
            for reference in BASELINE_6B
        )
        + "."
    )


# ------------------------------------------------------------------------------------------------
# The run
# ------------------------------------------------------------------------------------------------


class OpenedCorpus(NamedTuple):
    """Everything a run needs to read one release once."""

    stream: Iterator[Observation]
    events_read: list[int]
    labels: list[EntityLabelledInterval]
    featuriser: Featuriser
    peer_groups: PeerGroups
    dataset_name: str
    provenance: str


def load_manifest(data_dir: Path) -> dict[str, object]:
    """Read the committed CERT manifest written by ``scripts/fetch_datasets.py``.

    Args:
        data_dir: Where datasets were fetched to.

    Returns:
        The manifest as a mapping.

    Raises:
        EngineRunError: If it is absent, with the command that creates it.
    """
    path = data_dir / "cert-insider-threat" / MANIFEST_NAME
    if not path.is_file():
        raise EngineRunError(
            f"{path} not found. Fetch the corpus first:\n"
            "    python scripts/fetch_datasets.py cert-insider-threat --yes\n"
            "(~4.25 GB compressed, ~13 GB unpacked; it is git-ignored and never committed.)"
        )
    manifest: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
    return manifest


def build_corpus(
    data_dir: Path,
    manifest: Mapping[str, object],
    peer_policy: PeerPolicy,
    max_events: int | None,
) -> OpenedCorpus:
    """Open the release and return the single stream this run reads.

    Args:
        data_dir: Where the corpus was fetched to.
        manifest: The committed CERT manifest.
        peer_policy: Which declared attribute makes a peer group, and how small a group may be.
        max_events: Stop the reader after this many activity events, or ``None`` for all of them.

    Returns:
        The opened corpus, its stream not yet consumed.

    Raises:
        EngineRunError: If the directory carries no email addresses to define "external" from, if
            it carries no value for the grouping attribute, or if the release names no insider.
    """
    release_dir = data_dir / str(manifest["release_dir"])
    answers_dir = data_dir / str(manifest["answers_dir"])
    release_name = str(manifest["release"])

    reader = CertReader.for_release(CertRelease.discover(release_dir))
    catalogue = reader.catalogue()
    org_domain = catalogue.dominant_email_domain()
    if not org_domain:
        raise EngineRunError(
            f"the LDAP directory under {release_dir} carries no email addresses, so 'external "
            "email' cannot be defined from the corpus rather than guessed at"
        )
    labels = read_insiders(answers_dir, release_name)
    try:
        groups = PeerGroups.from_catalogue(catalogue, peer_policy)
    except ValueError as error:
        raise EngineRunError(str(error)) from error
    logger.info(
        "directory: %d users as of %s; organisation mail domain %s; %s",
        len(catalogue.entities),
        catalogue.directory_as_of.date(),
        org_domain,
        groups.summary(),
    )

    featuriser = Featuriser(
        org_domains=frozenset({org_domain}),
        feature_set=FeatureSet.PEER,
        peer_groups=groups,
    )
    counter = [0]

    def counted() -> Iterator[Observation]:
        events = (
            reader.events() if max_events is None else itertools.islice(reader.events(), max_events)
        )
        yield from featuriser.stream(_counting(events, counter))

    return OpenedCorpus(
        stream=counted(),
        events_read=counter,
        labels=labels,
        featuriser=featuriser,
        peer_groups=groups,
        dataset_name=f"cert-{release_name}-user-day-peer-engine",
        provenance=(
            f"CERT Insider Threat {release_name} (CMU/SEI, doi:10.1184/R1/12841247.v1) | "
            f"{len(catalogue.entities)} directory users"
        ),
    )


def _counting[T](items: Iterable[T], counter: list[int]) -> Iterator[T]:
    """Yield ``items`` unchanged, recording how many passed through."""
    for item in items:
        counter[0] += 1
        yield item


def thresholds_for_budgets(
    detections: Sequence[Detection], budgets: Sequence[int]
) -> dict[int, float]:
    """Return the score threshold that yields about each target alert count.

    An operating point chosen by **budget** rather than by threshold, because an analyst's
    constraint is the number of alerts they can work. No label is consulted: this reads the score
    distribution and nothing else, which is what keeps it a choice of operating point rather than
    a fit to the answer. Copied in shape from ``scripts/evaluate_sentiel_baseline.py``, which
    chose PART 6B's operating points the same way.

    Args:
        detections: Every detection the control produced.
        budgets: Target alert counts.

    Returns:
        ``budget -> threshold``, ascending by budget. A budget larger than the detection count is
        dropped, and ties mean the realised count can exceed the target.
    """
    ranked = sorted((detection.score for detection in detections), reverse=True)
    return {budget: ranked[budget - 1] for budget in sorted(budgets) if 0 < budget <= len(ranked)}


class RunResult(NamedTuple):
    """What one complete run produced."""

    reports: list[EvaluationReport]
    pass_: CorpusPass
    summary: str
    narratives: int
    counts: Mapping[str, int]
    budgets: dict[int, float]
    unreachable: list[int]


def run(
    corpus: OpenedCorpus,
    plan: SlicePlan,
    config: EvalConfig,
    policy: AggregationPolicy,
    min_samples: int,
    capacity: int,
    budgets: Sequence[int],
    soc_rates: Sequence[float],
    max_events: int | None,
) -> RunResult:
    """Read the release once, run the vertical on the operating point, and score both alert sets.

    Args:
        corpus: The opened release.
        plan: The label-derived three-way split.
        config: PART 2's evaluation config, unchanged.
        policy: How per-feature contributions combine into a window score.
        min_samples: Fewest training points a baseline needs.
        capacity: How many top-scoring windows the engine may explain.
        budgets: Fixed alert budgets, so rows line up with PART 6B's.
        soc_rates: Alerts-per-day rates to convert into budgets from the slice's own day count.
        max_events: How the reader was bounded, carried onto the report's caveats.

    Returns:
        The finished run.

    Raises:
        EngineRunError: If the corpus cannot support an honest measurement — see `read_corpus` —
            or if no labelled insider falls in the test slice.
    """
    read = read_corpus(
        corpus.stream,
        plan,
        policy,
        min_samples,
        capacity,
        config.seed,
        corpus.events_read,
    )
    in_test = [
        label
        for label in plan.test_labels
        if label.start <= read.windows[-1].timestamp and label.end >= read.windows[0].timestamp
    ]
    if not in_test:
        raise EngineRunError(
            "no labelled insider falls in the test slice, so recall would be vacuous. The slice "
            f"runs {read.windows[0].timestamp.isoformat()} to "
            f"{read.windows[-1].timestamp.isoformat()}; --max-events may have stopped the read "
            "before the corpus reached the labelled incident"
        )

    test = Dataset(
        name=f"{corpus.dataset_name}-test",
        domain=Domain.SENTIEL,
        observations=read.windows,
        attack_intervals=[],  # Sentiel truth is entity-scoped; it travels in `in_test`.
        source_note="",
    )
    counts = base_rate(test, in_test)
    total = counts["malicious_user_windows"] + counts["benign_user_windows"]

    engine = SentielEngine(
        read.fitted,
        read.calibrator,
        config=SentielConfig(
            scoring=policy,
            reasoning=ReasoningConfig(correlation_window=timedelta(days=7), seed=config.seed),
            alert_threshold=read.retained.threshold(),
        ),
    )
    narratives = engine.run(
        Dataset(
            name=f"{corpus.dataset_name}-explained",
            domain=Domain.SENTIEL,
            observations=read.retained.observations(),
            source_note="",
        )
    )
    alerts = engine_alerts(engine, policy.score_scale)
    logger.info(
        "%s explained %d retained window(s) into %d alert(s) and %d narrative(s)",
        engine.name,
        len(read.retained),
        len(alerts),
        len(narratives),
    )

    wanted = sorted({*budgets, *soc_budgets(read.test_days, soc_rates).values()})
    reachable = thresholds_for_budgets(read.detections, [b for b in wanted if b <= capacity])
    unreachable = [budget for budget in wanted if budget not in reachable]
    note = _source_note(corpus, plan, read, engine, counts, total, max_events)
    test = test.model_copy(update={"source_note": note})

    commit = current_git_commit(REPO_ROOT)
    control = PrecomputedDetector(
        name=f"aggregate:gaussian:6B-shaped control on this slice{policy.log_suffix}",
        detections=read.detections,
    )
    explained = PrecomputedDetector(name=engine.name, detections=alerts)
    census = explanation_census(engine, narratives, in_test)

    reports: list[EvaluationReport] = []
    for budget, threshold in reachable.items():
        at = config.model_copy(update={"alert_threshold": threshold})
        control_report = evaluate_entity_aware(control, test, in_test, at)
        engine_report = evaluate_entity_aware(explained, test, in_test, at)
        load = daily_load([alert for alert in alerts if alert.score >= threshold], read.test_days)
        comparison = side_by_side(engine_report, control_report, counts, load)
        for report in (control_report, engine_report):
            reports.append(
                annotate_with_caveats(
                    report.model_copy(
                        update={
                            "git_commit": commit,
                            "source_note": (
                                f"{report.source_note} | BUDGET {budget:,} | {comparison} | "
                                f"{census}"
                            ),
                        }
                    )
                )
            )
    return RunResult(
        reports=reports,
        pass_=read,
        summary=engine.summary().note(),
        narratives=len(narratives),
        counts=counts,
        budgets=reachable,
        unreachable=unreachable,
    )


def _source_note(
    corpus: OpenedCorpus,
    plan: SlicePlan,
    read: CorpusPass,
    engine: SentielEngine,
    counts: Mapping[str, int],
    total: int,
    max_events: int | None,
) -> str:
    """Compose the provenance every report in this run carries."""
    return " | ".join(
        [
            peer_source_note(
                f"{corpus.provenance} | {total:,} test entity-windows x "
                f"{len(corpus.featuriser.feature_names)} emitted features "
                f"({corpus.featuriser.feature_set.value}), one-day windows | n_observations on "
                f"this report counts ENTITY-WINDOWS, not feature observations, because the alert "
                f"unit is a window | {read.scoring.note()} | {engine.summary().note()}",
                f"base rate {counts['malicious_user_windows']} malicious of {total} entity-windows",
                corpus.peer_groups.summary(),
            ),
            plan.note(),
            f"CALIBRATION: isotonic, fitted on {read.n_calibration_points:,} candidate deviations "
            f"of which {read.n_calibration_positives:,} fall inside a labelled insider's window, "
            f"all from the held-out calibration slice; the model was fitted on {read.n_train:,} "
            "attack-free training observations",
            partial_corpus_caveat(read.events_read, max_events is not None),
            *ENGINE_RUNNER_CAVEATS,
        ]
    )


def report_lines(result: RunResult, budget: int, report: EvaluationReport) -> list[str]:
    """Render the honest summary printed for one report."""
    comparison = report.source_note.rpartition("LIKE-FOR-LIKE")[2]
    return [
        "",
        "=" * 98,
        f"SENTIEL ENGINE — {report.detector_name}",
        f"  budget                 {budget:,} alerts (threshold {report.alert_threshold:.4f})",
        "=" * 98,
        f"  commit                 {report.git_commit or '(unknown)'}",
        f"  seed                   {report.seed}",
        f"  entity-windows (test)  {report.n_observations:,}",
        f"  alerts                 {report.n_alerts:,}",
        "",
        f"  window recall          {report.window_recall:.4f}   (NOT QUOTABLE — one insider on "
        "this slice, so this can only be 0 or 1)",
        f"  precision              {report.precision:.6f}",
        f"  false positives        {report.false_positives:,}",
        f"  FP per normal USER-hr  {report.false_positive_rate:.6f}",
        f"  sample recall          {report.recall_sample:.4f}",
        f"  F1                     {report.f1:.6f}",
        f"  ECE                    {report.expected_calibration_error:.4f}",
        f"  Brier                  {report.brier_score:.4f}",
        "  median latency         "
        + (
            f"{report.latency.median_seconds / 3600.0:.1f} h"
            if report.latency.median_seconds is not None
            else "(nothing caught)"
        ),
        "",
        f"  LIKE-FOR-LIKE{comparison}",
        "=" * 98,
    ]


def closing_lines(result: RunResult, soc_rates: Sequence[float]) -> list[str]:
    """Render what the run rests on: coverage, the day arithmetic, and every caveat."""
    read = result.pass_
    budgets = soc_budgets(read.test_days, soc_rates)
    return [
        "",
        "=" * 98,
        "WHAT THIS RUN RESTS ON",
        "=" * 98,
        f"  activity events read   {read.events_read:,}",
        f"  training observations  {read.n_train:,}",
        f"  calibration points     {read.n_calibration_points:,} "
        f"({read.n_calibration_positives:,} malicious)",
        f"  test entity-windows    "
        f"{result.counts['malicious_user_windows'] + result.counts['benign_user_windows']:,} "
        f"({result.counts['malicious_user_windows']} malicious)",
        f"  distinct test days     {read.test_days:,}",
        f"  windows explained      {len(read.retained):,} (score >= "
        f"{read.retained.threshold():.4f})",
        f"  narratives             {result.narratives:,}",
        "",
        "  THE PER-DAY CONVERSION, DONE AS ARITHMETIC:",
        *[
            f"    {rate:g} alerts/day x {read.test_days:,} days = {alerts:,} alerts in total"
            for rate, alerts in budgets.items()
        ],
        *(
            [
                "    budgets that could not be evaluated (above --max-explained or above the "
                "alert count): " + ", ".join(f"{budget:,}" for budget in result.unreachable)
            ]
            if result.unreachable
            else []
        ),
        "",
        f"  {result.summary}",
        f"  {read.scoring.note()}",
        "",
        "  CAVEATS (stamped into source_note on every logged report, so they cannot be read apart",
        "  from the numbers above):",
        *[f"    - {caveat}" for caveat in ENGINE_RUNNER_CAVEATS],
        f"  peak memory            {_peak_memory_gb():.2f} GB",
        "=" * 98,
    ]


def _peak_memory_gb() -> float:
    """Return this process's peak resident set size in GB, for the record."""
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # macOS reports bytes; Linux reports kilobytes. Anything under a megabyte cannot be a real
    # peak for this script, so the small number is the kilobyte one.
    return (usage if usage > 1_000_000 else usage * 1024) / _BYTES_PER_GB


def build_parser() -> argparse.ArgumentParser:
    """Return the command line, so a test can read the defaults rather than restate them."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--min-samples", type=int, default=8)
    parser.add_argument("--alert-threshold", type=float, default=3.0)
    parser.add_argument(
        "--alert-budgets",
        type=int,
        nargs="*",
        default=[48, 200, 723, 1_668],
        help=(
            "fixed alert budgets to evaluate at. The defaults are PART 6B's, so the rows line up "
            "with the standing numbers in eval_runs/log.jsonl"
        ),
    )
    parser.add_argument(
        "--soc-alerts-per-day",
        type=float,
        nargs="*",
        default=[30.0, 50.0],
        help=(
            "alerts a day a SOC is assumed able to work. Converted to total alert budgets by the "
            "number of distinct one-day windows the test slice covers, and the arithmetic is "
            "printed rather than asserted"
        ),
    )
    parser.add_argument(
        "--max-explained",
        type=int,
        default=12_000,
        help=(
            "how many top-scoring entity-windows keep their observations and reach the engine. "
            "Explaining every window in a corpus explains nothing and will not fit in memory; "
            "this is the ceiling on the operating point, and it is reported"
        ),
    )
    parser.add_argument(
        "--max-events",
        type=int,
        default=None,
        help=(
            "stop the reader after this many activity events. A probe, not a measurement: the "
            "result rests on a time-ordered prefix of the release and every report says so"
        ),
    )
    parser.add_argument("--group-attribute", default=DEFAULT_GROUP_ATTRIBUTE)
    parser.add_argument("--min-group-size", type=int, default=PeerPolicy().min_group_size)
    parser.add_argument("--score-scale", type=float, default=AggregationPolicy().score_scale)
    parser.add_argument(
        "--precision-policy",
        action="store_true",
        help=(
            "apply the opt-in aggregation that discounts volume, off-hours, self-relative-only "
            "departures, and single-family windows. Default AggregationPolicy is unchanged so the "
            "PART 6B/6C rows stay reproducible. The control detector name gains :precision"
        ),
    )
    parser.add_argument(
        "--no-log", action="store_true", help="compute but do not append to the experiment log"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns a process exit code."""
    arguments = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    config = EvalConfig(
        alert_threshold=arguments.alert_threshold,
        match_tolerance=timedelta(0),
        seed=arguments.seed,
    )
    policy = (
        precision_policy().model_copy(update={"score_scale": arguments.score_scale})
        if arguments.precision_policy
        else AggregationPolicy(score_scale=arguments.score_scale)
    )
    try:
        corpus = build_corpus(
            arguments.data_dir,
            load_manifest(arguments.data_dir),
            PeerPolicy(
                group_attribute=arguments.group_attribute,
                min_group_size=arguments.min_group_size,
            ),
            arguments.max_events,
        )
        plan = plan_slices(corpus.labels)
        logger.info("%s", plan.note())
        result = run(
            corpus=corpus,
            plan=plan,
            config=config,
            policy=policy,
            min_samples=arguments.min_samples,
            capacity=arguments.max_explained,
            budgets=arguments.alert_budgets,
            soc_rates=arguments.soc_alerts_per_day,
            max_events=arguments.max_events,
        )
    except EngineRunError as error:
        logger.error("%s", error)
        return 2

    budgets = list(result.budgets)
    for index, report in enumerate(result.reports):
        for line in report_lines(result, budgets[index // 2], report):
            print(line)
        if not arguments.no_log:
            append_to_experiment_log(report)
    for line in closing_lines(result, arguments.soc_alerts_per_day):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

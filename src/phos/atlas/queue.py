"""What an operator is actually handed: the subsystem-event queue, ranked and cut to a budget.

`phos.atlas.grouping` collapses per-signal evidence into one event per physical unit, and it is
scrupulous about being a counting change and nothing else — no evidence is discarded, filtered or
re-scored on the way through. That leaves the queue in *time* order. On HAI it leaves 424 events
covering 7.89 normal hours, of which 4 are true. An operator reading them front to back reads 424
things to find 4, and no false-positive rate describes that experience: 53.26 FP/normal-hour and
"your shift contains 424 items" are the same fact told to two different people.

This module asks the question the rate cannot: **if the queue is ranked and cut to a budget an
operator could actually work, what survives?** It is the Atlas twin of Session S4's
`phos.sentiel.cert_curve`, which already asks exactly this of CERT and reports recall against a
ticket budget rather than a rate.

**Ranking is a separate stage from grouping, and the separation is the point.** Grouping's promise
that it re-scores nothing is worth keeping, so nothing here is imported by it. A queue is built
*from* finished events by a caller that already walked their traceability links, and this module
never sees a model, a store or a corpus.

**Three ranking keys, because the honest answer may be that none of them rank.** Atlas already
carries two numbers per event and can derive a third:

* ``magnitude`` — the largest raw joint distance among the event's members. Continuous, in the
  units 5A reported, and uncalibrated.
* ``weight`` — the strongest member's calibrated probability. The calibrator that produces it fits
  four knots spanning ``[0.000, 0.034]``, because only 140 of 4,249 candidates fall in attack
  windows, so this key is expected to tie heavily. Measuring that is the point of offering it.
* ``breadth`` — how many of the unit's signals departed together. An integer, and on a coarse map
  a small one, so it ties by construction.

A key that ties across the cut has not ranked the queue; the tiebreak has. `BudgetOutcome` reports
that directly rather than leaving it to be inferred from a suspiciously round number.

**The cut can be arbitrary, and an arbitrary cut is refused rather than reported.** When the alert
at the budget boundary and the alert just past it share a score, which of them made the queue was
decided by the deterministic tiebreak — timestamp, then id — and not by the ranking signal. The
resulting precision is then a property of the sort, not of Atlas. `BudgetOutcome.cut_is_arbitrary`
says so, and `QueueCurve.honest_points` drops those points instead of quoting them.

**Truth is overlap-aware, exactly as `scripts/evaluate_atlas_vertical.py` already counts it.** A
subsystem event stands for the span from its earliest member to its latest and is stamped at the
earliest, so an event that began in normal time and continued into an attack has plainly caught
that attack. Counting only its stamp would report a miss that did not happen. `windows_overlapped`
is that rule as a pure function; the vertical script keeps its own copy untouched so the frozen
`hai[after]` row reproduces byte-identically.

**What a number from here is not.** It is not a control-room budget, it is not a claim that Atlas
is deployable, and it does not replace the logged 53.26 FP/normal-hour or 646.58 ungated rows.
Detector names minted here carry `QUEUE_DETECTOR_PREFIX` so a queue row can never be mistaken for
the vertical's. Recall at a budget is measured on one corpus's declared topology, and HAI's map
could not be partitioned below process level, so the events being ranked are coarse.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from phos.eval.datasets import LabelledInterval

__all__ = [
    "ARBITRARY_CUT_CAVEAT",
    "QUEUE_CAVEATS",
    "QUEUE_DETECTOR_PREFIX",
    "RANKING_KEYS",
    "BudgetOutcome",
    "QueueCurve",
    "QueuedAlert",
    "RankingKey",
    "outcome_at_budget",
    "queue_curve",
    "queue_detector_name",
    "rank_queue",
    "render_queue_markdown",
    "windows_overlapped",
]

logger = logging.getLogger(__name__)

RankingKey = Literal["magnitude", "weight", "breadth"]
"""Which number a queue is ranked by. Declared, never inferred from what scores best."""

RANKING_KEYS: Final[tuple[RankingKey, ...]] = ("magnitude", "weight", "breadth")
"""Every key this module will rank by, in the order a report should present them."""

QUEUE_DETECTOR_PREFIX: Final = "atlas-queue:"
"""Prefix on every detector name minted here.

The vertical's `atlas-vertical:` rows are frozen public names (646.58 ungated, 53.26 grouped). A
ranked queue is a different measurement of the same alert set and must never land under one of
them, so the prefix is explicit rather than a convention.
"""

ARBITRARY_CUT_CAVEAT: Final = (
    "The budget cut fell inside a block of alerts sharing one score, so which alerts made the "
    "queue was decided by the deterministic tiebreak and not by the ranking signal. Precision "
    "here is a property of the sort order, not of Atlas."
)

QUEUE_CAVEATS: Final[tuple[str, ...]] = (
    "Recall at an alert budget is not a control-room budget and not a deployment claim.",
    "This re-counts the alert set the vertical already logged. It does not replace 646.58 "
    "ungated or 53.26 grouped FP/normal-hour, and no threshold was searched.",
    "HAI's declared topology could not be partitioned below process level, so the subsystem "
    "events being ranked are coarse; a finer map would change the queue without changing "
    "the detector.",
    "Calibrated weights top out at 0.034 across four isotonic knots, because only 140 of 4,249 "
    "calibration candidates fall in attack windows. A weight-ranked queue is expected to tie.",
)


def queue_detector_name(ranking: RankingKey) -> str:
    """Return the log name for a queue ranked by ``ranking``."""
    return f"{QUEUE_DETECTOR_PREFIX}{ranking}"


class QueuedAlert(BaseModel):
    """One subsystem event as it appears in an operator's queue.

    Attributes:
        evidence_id: The subsystem event's id. Ties are broken on it, so it must be unique.
        timestamp: The event's stamp — its earliest member's instant.
        magnitude: Largest raw joint distance among the event's members.
        weight: The strongest member's calibrated probability.
        breadth: How many distinct signals of the unit departed together.
        covers_windows: Indices of the attack windows this event overlaps, from
            `windows_overlapped`. Empty means the event is a false positive.
    """

    model_config = ConfigDict(frozen=True)

    evidence_id: str = Field(min_length=1)
    timestamp: datetime
    magnitude: float
    weight: float = Field(ge=0.0, le=1.0)
    breadth: int = Field(ge=1)
    covers_windows: tuple[int, ...] = ()

    @property
    def is_true_positive(self) -> bool:
        """Whether this alert overlaps at least one labelled attack window."""
        return bool(self.covers_windows)

    def rank_score(self, ranking: RankingKey) -> float:
        """Return the number this alert is ranked by under ``ranking``."""
        if ranking == "magnitude":
            return self.magnitude
        if ranking == "weight":
            return self.weight
        return float(self.breadth)


class BudgetOutcome(BaseModel):
    """What an operator working the top ``budget`` alerts would have got.

    Attributes:
        budget: Alerts the operator is assumed to work. Positive.
        ranking: Which key produced the order.
        n_queued: Alerts actually taken — ``min(budget, len(queue))``.
        n_available: Alerts in the full queue before the cut.
        true_positives: Taken alerts that overlap an attack window.
        precision: ``true_positives / budget``, matching `phos.eval.metrics.precision_at_budget` —
            the denominator is the operator's budget, not what happened to be available, because a
            queue shorter than the budget did not earn credit for the alerts it did not raise.
        window_recall: Attack windows covered by the taken alerts, over all windows.
        n_windows: Attack windows in the corpus.
        n_true_available: True positives in the whole queue, before the cut. The denominator of
            the random baseline below.
        cut_score: The score of the last alert taken, or ``None`` when the queue was shorter than
            the budget and nothing was cut.
        tie_span_at_cut: How many alerts in the whole queue share ``cut_score``.
        cut_is_arbitrary: Whether the cut fell inside a tie block, making membership of the queue
            a property of the tiebreak rather than of the ranking.
    """

    model_config = ConfigDict(frozen=True)

    budget: int = Field(ge=1)
    ranking: RankingKey
    n_queued: int = Field(ge=0)
    n_available: int = Field(ge=0)
    true_positives: int = Field(ge=0)
    precision: float = Field(ge=0.0, le=1.0)
    window_recall: float = Field(ge=0.0, le=1.0)
    n_windows: int = Field(ge=0)
    n_true_available: int = Field(ge=0)
    cut_score: float | None = None
    tie_span_at_cut: int = Field(ge=0)
    cut_is_arbitrary: bool = False

    @model_validator(mode="after")
    def _arbitrary_cut_needs_a_tie(self) -> BudgetOutcome:
        """An arbitrary cut is exactly a tie spanning the boundary; the two cannot disagree."""
        if self.cut_is_arbitrary and self.tie_span_at_cut < 2:
            raise ValueError(
                f"cut_is_arbitrary is set but tie_span_at_cut is {self.tie_span_at_cut}: a cut is "
                "arbitrary only when more than one alert shares the cut score"
            )
        return self

    @property
    def expected_true_positives(self) -> float:
        """True positives a *random* sample of ``budget`` alerts from this queue would expect.

        The bar a ranking has to clear. A key that sorts truth downwards scores below it, which is
        a stronger statement than "the precision is low" — it says the severity signal is pointing
        the wrong way, and no threshold on it will help.
        """
        if not self.n_available:
            return 0.0
        return min(self.budget, self.n_available) * self.n_true_available / self.n_available

    @property
    def beats_random(self) -> bool:
        """Whether this cut found more truth than drawing the same number of alerts at random."""
        return self.true_positives > self.expected_true_positives

    @property
    def caveat(self) -> str | None:
        """Return the caveat this outcome must be read with, or ``None`` if the cut was clean."""
        return ARBITRARY_CUT_CAVEAT if self.cut_is_arbitrary else None


class QueueCurve(BaseModel):
    """Recall and precision across a sweep of operator budgets, for one ranking key.

    Attributes:
        ranking: The key the queue was ranked by.
        detector_name: Log name for this curve, always prefixed `QUEUE_DETECTOR_PREFIX`.
        points: One outcome per budget, in ascending budget order.
        n_available: Alerts in the full queue.
        n_windows: Attack windows in the corpus.
        distinct_scores: How many different values ``ranking`` took across the queue. One means
            the key did not order anything at all.
        true_positive_ranks: Zero-indexed positions of the true alerts in the ranked queue. This
            is the finding a curve of precisions can only imply: if these sit in the back half,
            the key is sorting truth away from the operator.
    """

    model_config = ConfigDict(frozen=True)

    ranking: RankingKey
    detector_name: str
    points: tuple[BudgetOutcome, ...]
    n_available: int = Field(ge=0)
    n_windows: int = Field(ge=0)
    distinct_scores: int = Field(ge=0)
    true_positive_ranks: tuple[int, ...] = ()

    @property
    def n_true_positives(self) -> int:
        """How many alerts in the whole queue overlap an attack window."""
        return len(self.true_positive_ranks)

    @property
    def sorts_truth_downwards(self) -> bool:
        """Whether the median true alert sits in the back half of the queue.

        The compact statement of an anti-ranking. A key that satisfies this has not merely failed
        to help; it has actively buried the incidents under the noise.
        """
        if not self.true_positive_ranks or not self.n_available:
            return False
        middle = self.true_positive_ranks[len(self.true_positive_ranks) // 2]
        return middle >= self.n_available / 2

    @property
    def ranks_at_all(self) -> bool:
        """Whether the key took more than one value. A constant key has ordered nothing."""
        return self.distinct_scores > 1

    @property
    def honest_points(self) -> tuple[BudgetOutcome, ...]:
        """Return only the points whose cut was decided by the ranking rather than the tiebreak."""
        return tuple(point for point in self.points if not point.cut_is_arbitrary)


def windows_overlapped(
    stamps: Sequence[datetime],
    intervals: Sequence[LabelledInterval],
    tolerance: timedelta = timedelta(0),
) -> tuple[int, ...]:
    """Return the indices of the attack windows any of ``stamps`` falls in.

    A subsystem event is stamped at its earliest member but stands for all of them, so truth is
    tested against every member's instant. An event that began in normal time and continued into
    an attack has caught it.

    Args:
        stamps: Every member instant the event stands for. A per-signal fact passes one.
        intervals: Ground-truth attack windows.
        tolerance: Slack applied to each window's bounds, consistently with `phos.eval.metrics`.

    Returns:
        Ascending window indices, without repeats. Empty when the event overlaps nothing.
    """
    covered = {
        index
        for index, interval in enumerate(intervals)
        for stamp in stamps
        if interval.start - tolerance <= stamp <= interval.end + tolerance
    }
    return tuple(sorted(covered))


def rank_queue(alerts: Sequence[QueuedAlert], ranking: RankingKey) -> tuple[QueuedAlert, ...]:
    """Order a queue so the most severe alert is read first.

    Args:
        alerts: The subsystem events to rank, in any order. Not modified.
        ranking: Which declared key to rank by.

    Returns:
        The alerts, highest score first. Ties break on timestamp then ``evidence_id``, so the
        order is total and reproducible — and so a tie that decides the cut can be detected
        rather than being hidden by an unstable sort.

    Raises:
        ValueError: If two alerts share an ``evidence_id``, which would make the tiebreak
            ambiguous and the queue unreproducible.
    """
    ids = [alert.evidence_id for alert in alerts]
    if len(set(ids)) != len(ids):
        raise ValueError(
            "queue contains duplicate evidence ids, so the tiebreak is ambiguous and the same "
            "alerts could rank two ways"
        )

    def order(alert: QueuedAlert) -> tuple[float, datetime, str]:
        return (-alert.rank_score(ranking), alert.timestamp, alert.evidence_id)

    return tuple(sorted(alerts, key=order))


def outcome_at_budget(
    ranked: Sequence[QueuedAlert],
    budget: int,
    ranking: RankingKey,
    n_windows: int,
) -> BudgetOutcome:
    """Score the top ``budget`` alerts of an already-ranked queue.

    Args:
        ranked: The queue, as returned by `rank_queue`. Assumed ordered; not re-sorted, because
            re-sorting here would silently accept a queue ranked by a different key.
        budget: How many alerts the operator works. Must be positive — a budget of zero is not
            an operating point, it is switching the system off.
        ranking: The key ``ranked`` was ordered by, recorded on the outcome.
        n_windows: Attack windows in the corpus. Zero returns recall ``0.0`` rather than a
            vacuous ``1.0``, matching `phos.eval.metrics.window_recall`.

    Returns:
        The outcome, including whether the cut was decided by the ranking or by the tiebreak.

    Raises:
        ValueError: If ``budget`` is not positive.
    """
    if budget < 1:
        raise ValueError(f"budget must be a positive operator volume, got {budget}")

    taken = list(ranked)[:budget]
    covered = {index for alert in taken for index in alert.covers_windows}
    true_positives = sum(1 for alert in taken if alert.is_true_positive)

    cut_score: float | None = None
    tie_span = 0
    arbitrary = False
    if taken:
        cut_score = taken[-1].rank_score(ranking)
        tie_span = sum(1 for alert in ranked if alert.rank_score(ranking) == cut_score)
        arbitrary = len(ranked) > len(taken) and ranked[len(taken)].rank_score(ranking) == cut_score

    return BudgetOutcome(
        budget=budget,
        ranking=ranking,
        n_queued=len(taken),
        n_available=len(ranked),
        true_positives=true_positives,
        precision=true_positives / float(budget),
        window_recall=(len(covered) / n_windows) if n_windows else 0.0,
        n_windows=n_windows,
        n_true_available=sum(1 for alert in ranked if alert.is_true_positive),
        cut_score=cut_score,
        tie_span_at_cut=tie_span,
        cut_is_arbitrary=arbitrary,
    )


def queue_curve(
    alerts: Sequence[QueuedAlert],
    budgets: Sequence[int],
    ranking: RankingKey,
    n_windows: int,
) -> QueueCurve:
    """Rank a queue once and score it at every budget, as one curve.

    Args:
        alerts: The subsystem events, in any order.
        budgets: Operator volumes to score. Deduplicated and sorted ascending, so a curve is
            presented the way it is read.
        ranking: Which declared key to rank by.
        n_windows: Attack windows in the corpus.

    Returns:
        The curve, carrying enough structure to tell "this key ranks" from "this key ties".

    Raises:
        ValueError: If ``budgets`` is empty, or any budget is not positive.
    """
    if not budgets:
        raise ValueError("a curve needs at least one budget")

    ranked = rank_queue(alerts, ranking)
    points = tuple(
        outcome_at_budget(ranked, budget, ranking, n_windows) for budget in sorted(set(budgets))
    )
    distinct = len({alert.rank_score(ranking) for alert in ranked})
    true_ranks = tuple(index for index, alert in enumerate(ranked) if alert.is_true_positive)
    logger.info(
        "%s: %d alert(s), %d distinct score(s), %d budget(s) scored",
        queue_detector_name(ranking),
        len(ranked),
        distinct,
        len(points),
    )
    return QueueCurve(
        ranking=ranking,
        detector_name=queue_detector_name(ranking),
        points=points,
        n_available=len(ranked),
        n_windows=n_windows,
        distinct_scores=distinct,
        true_positive_ranks=true_ranks,
    )


def _verdict(curve: QueueCurve) -> str:
    """State, in one line, whether this key ordered the queue or merely tied it."""
    if not curve.ranks_at_all:
        return "**did not rank** — every alert shares one score, so the order is the tiebreak's."
    if curve.sorts_truth_downwards:
        return (
            "**ranked the wrong way** — the median true alert sits in the back half of the "
            "queue, so this key buries incidents under the noise rather than surfacing them."
        )
    honest = len(curve.honest_points)
    if honest == 0:
        return (
            "**did not rank at any budget scored** — every cut fell inside a tie block, so the "
            "queue's membership was decided by timestamp order."
        )
    if honest < len(curve.points):
        return (
            f"ranked at {honest} of {len(curve.points)} budgets; the rest cut inside a tie block "
            "and are struck."
        )
    return f"ranked cleanly at all {honest} budgets scored."


def render_queue_markdown(
    curves: Sequence[QueueCurve],
    *,
    corpus: str,
    seed: int,
    git_commit: str | None = None,
) -> str:
    """Render the queue curves as a standalone report.

    Args:
        curves: One curve per ranking key, in the order they should be presented.
        corpus: Which corpus the queue came from.
        seed: The run's seed, so the report reproduces.
        git_commit: Commit that produced it, when known.

    Returns:
        Markdown. Every table is followed by the caveats it must be read with, because a table
        that travels without them is the thing this repository exists not to produce.

    Raises:
        ValueError: If ``curves`` is empty.
    """
    if not curves:
        raise ValueError("a queue report needs at least one curve")

    available = curves[0].n_available
    windows = curves[0].n_windows
    lines = [
        f"# Atlas operator queue on {corpus} — recall at an alert budget",
        "",
        "**Not a new detector and not a control-room budget.** This re-counts the alert set the",
        "Atlas vertical already logged, ranked instead of in time order. The frozen public rows",
        "are untouched: 646.58 FP/normal-hour ungated and 53.26 grouped. No threshold was",
        "searched and no model was refitted.",
        "",
        f"- Queue: **{available:,}** subsystem events over **{windows}** labelled attack window(s)",
        f"- Seed: `{seed}`",
        f"- Commit: `{git_commit or 'unknown'}`",
        f"- Detector names: `{QUEUE_DETECTOR_PREFIX}<key>` — never a vertical name",
        "",
    ]

    for curve in curves:
        lines.extend(
            [
                f"## Ranked by `{curve.ranking}`",
                "",
                f"`{curve.detector_name}` — {curve.distinct_scores:,} distinct score(s). "
                f"This key {_verdict(curve)}",
                "",
                "| Budget | Queued | TP | Random would find | Beats random | "
                "Precision@budget | Window recall | Cut score | Tie span | Cut decided by |",
                "| ---: | ---: | ---: | ---: | :---: | ---: | ---: | ---: | ---: | --- |",
            ]
        )
        for point in curve.points:
            cut = "—" if point.cut_score is None else f"{point.cut_score:.4f}"
            decided = "**tiebreak (struck)**" if point.cut_is_arbitrary else "ranking"
            lines.append(
                f"| {point.budget:,} | {point.n_queued:,} | {point.true_positives} "
                f"| {point.expected_true_positives:.2f} "
                f"| {'yes' if point.beats_random else '**no**'} "
                f"| {point.precision:.4f} | {point.window_recall:.2f} | {cut} "
                f"| {point.tie_span_at_cut:,} | {decided} |"
            )
        if curve.true_positive_ranks:
            positions = ", ".join(
                f"{rank} ({100 * rank / curve.n_available:.0f}%)"
                for rank in curve.true_positive_ranks
            )
            lines.extend(
                [
                    "",
                    f"The {curve.n_true_positives} true alert(s) sit at rank {positions} of "
                    f"{curve.n_available:,}. An operator reads from rank 0.",
                ]
            )
        lines.append("")

    lines.extend(["## Read every number above with these", ""])
    lines.extend(f"- {caveat}" for caveat in QUEUE_CAVEATS)
    lines.append(f"- {ARBITRARY_CUT_CAVEAT}")
    lines.append("")
    return "\n".join(lines)

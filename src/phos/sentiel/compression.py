"""What an analyst actually reads: entity-days against episodes, at one budget, counted honestly.

`phos.atlas.queue` asked this of a plant — *if the queue is ranked and cut to a budget an operator
could work, what survives?* — and answered it by re-counting an alert set that already existed,
under detector names that could never be mistaken for a published row. This is the Sentiel twin of
that question, with one difference that is the whole point: Atlas re-counted the same alerts in a
different order, and this re-counts them in a different **unit**.

**The comparison.** At a budget of N items:

* *baseline* — the top N entity-days by PART 6B's aggregate score. Exactly what 6B hands an
  operator today, and at N=48 exactly the frozen row: 5 true entity-days, one insider of two.
* *episodes* — the top N episodes by the same score lifted to the episode unit.

**Three numbers, because one of them would be a lie on its own.**

* ``items`` — what the analyst opens. The thing a budget is a budget *of*.
* ``entity_days`` — what those items contain. An episode of nineteen days is one item and nineteen
  days of reading, and a compression ratio that quoted only the first would be a conjuring trick.
  `EPISODE_UNIT_CAVEAT` travels on every report for this reason.
* ``malicious_days_covered`` — how much of the labelled activity the analyst would actually see.
  This is the number the whole exercise is about, and it is the one a per-day queue at a realistic
  budget cannot move: 53 malicious entity-days competing for 48 slots against 210,000 benign ones.

**Truth is entity-scoped and uses the ontology's own rule.** A day counts as malicious when
`phos.sentiel.EntityLabelledInterval.contains` says the labelled user was malicious at that
window's start — the same test `phos.sentiel.evaluation` applies, so a covered day here and a true
positive there mean the same thing. An episode is a true positive when **any** of its member days
is malicious. Gap days inside an episode are not members and are never counted as covered:
claiming a day nothing fired on would inflate every recall built from episodes.

**A tie at the cut is reported, not smoothed.** When the episode at the boundary and the one just
past it share a rank score, which of them made the queue was decided by the deterministic tiebreak
and not by the ranking — so the resulting precision is a property of the sort. `cut_is_arbitrary`
says so, exactly as `phos.atlas.queue.BudgetOutcome` does.

Nothing here is imported from Atlas. ADR 0023 refused Sentiel importing from Atlas — it would
couple two engines through a place neither owns — so the shared vocabulary is deliberately
re-expressed rather than reached for, and a later PART free to touch both should promote it once.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import datetime
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from phos.sentiel.episodes import EPISODE_UNIT_CAVEAT, Episode, EpisodeRanking
from phos.sentiel.labels import EntityLabelledInterval

__all__ = [
    "COMPRESSION_CAVEATS",
    "EPISODE_DETECTOR_PREFIX",
    "BudgetComparison",
    "EpisodeAlert",
    "QueuedDay",
    "build_episode_queue",
    "compare_at_budget",
    "episode_detector_name",
    "rank_episodes",
]

logger = logging.getLogger(__name__)

EPISODE_DETECTOR_PREFIX: Final = "sentiel-episode:"
"""Prefix on every detector name minted here.

PART 6B's ``aggregate:gaussian:peer set (34 features)`` is a frozen public name carrying precision
0.104 at 48 alerts. An episode queue is a different measurement in a different unit and must never
land under it, so the prefix is explicit rather than a convention.
"""

COMPRESSION_CAVEATS: Final[tuple[str, ...]] = (
    EPISODE_UNIT_CAVEAT,
    "Two labelled insiders means insider coverage takes only the values 0, 0.5 and 1.0. It is not "
    "a rate and must not be read as one. The malicious ENTITY-DAY count (53) is the finer "
    "denominator and is the one to read.",
    "This re-counts PART 6B's own scores in a different unit. No model was refitted, no threshold "
    "was searched against a label, and the frozen 48-alert row is reproduced as a gate before any "
    "number here is computed. It does not supersede that row.",
    "CERT is SYNTHETIC. Simulated insiders may be more persistent, and therefore more episodic, "
    "than real ones; a compression ratio measured here is not a claim about an enterprise.",
)


def episode_detector_name(ranking: EpisodeRanking) -> str:
    """Return the log name for an episode queue ranked by ``ranking``."""
    return f"{EPISODE_DETECTOR_PREFIX}{ranking}"


class QueuedDay(BaseModel):
    """One entity-day in the per-day baseline queue.

    Attributes:
        user_id: The actor.
        day: The window start.
        score: PART 6B's aggregate score.
        malicious: Whether ground truth calls this entity-day malicious.
    """

    model_config = ConfigDict(frozen=True)

    user_id: str
    day: datetime
    score: float = Field(ge=0.0)
    malicious: bool = False


class EpisodeAlert(BaseModel):
    """One episode as it appears in an analyst's queue, with what it covers.

    Attributes:
        user_id: The actor.
        start: First member day.
        end: Last member day.
        n_days: Member days — the reading cost of this one item.
        n_carried_days: Member days that would never have reached the budget alone.
        peak: Largest single-day score.
        total: Every member day's score summed.
        breadth: Most behaviour families departing together on any one member day.
        trajectory: Which way the episode is going.
        malicious_days: Member days ground truth calls malicious.
        insider: The labelled user this episode is about, or ``None``.
    """

    model_config = ConfigDict(frozen=True)

    user_id: str
    start: datetime
    end: datetime
    n_days: int = Field(ge=1)
    n_carried_days: int = Field(ge=0)
    peak: float = Field(ge=0.0)
    total: float = Field(ge=0.0)
    breadth: int = Field(ge=0)
    trajectory: str = "single"
    malicious_days: tuple[datetime, ...] = ()
    insider: str | None = None

    @property
    def is_true_positive(self) -> bool:
        """Whether any member day of this episode is labelled malicious."""
        return bool(self.malicious_days)

    def rank_score(self, ranking: EpisodeRanking) -> float:
        """Return the number this alert is ranked by."""
        if ranking == "peak":
            return self.peak
        if ranking == "total":
            return self.total
        if ranking == "days":
            return float(self.n_days)
        return float(self.breadth)


def _malicious_days_of(
    episode: Episode, user_id: str, labels: Sequence[EntityLabelledInterval]
) -> tuple[tuple[datetime, ...], str | None]:
    """Return the episode's malicious member days and the insider they belong to."""
    covered = tuple(
        day.day for day in episode.days if any(label.contains(user_id, day.day) for label in labels)
    )
    insider = next((label.user_id for label in labels if label.user_id == user_id), None)
    return covered, (insider if covered else None)


def build_episode_queue(
    episodes: Sequence[Episode], labels: Sequence[EntityLabelledInterval]
) -> list[EpisodeAlert]:
    """Turn assembled episodes into queue items carrying what each one covers.

    Args:
        episodes: The episodes, in any order.
        labels: Entity-scoped ground truth.

    Returns:
        One alert per episode, in the input order.
    """
    alerts: list[EpisodeAlert] = []
    for episode in episodes:
        user_id = episode.entity_id.removeprefix("ent_")
        malicious, insider = _malicious_days_of(episode, user_id, labels)
        alerts.append(
            EpisodeAlert(
                user_id=user_id,
                start=episode.start,
                end=episode.end,
                n_days=episode.n_days,
                n_carried_days=episode.n_carried_days,
                peak=episode.peak,
                total=episode.total,
                breadth=episode.breadth,
                trajectory=episode.trajectory,
                malicious_days=malicious,
                insider=insider,
            )
        )
    return alerts


def rank_episodes(
    alerts: Sequence[EpisodeAlert], ranking: EpisodeRanking
) -> tuple[EpisodeAlert, ...]:
    """Order an episode queue so the most severe episode is read first.

    Ties break on start, then user, then end, so the order is total and reproducible — and so a
    tie that decides the cut can be detected rather than hidden by an unstable sort.
    """

    def order(alert: EpisodeAlert) -> tuple[float, datetime, str, datetime]:
        return (-alert.rank_score(ranking), alert.start, alert.user_id, alert.end)

    return tuple(sorted(alerts, key=order))


class BudgetComparison(BaseModel):
    """What a per-day queue and an episode queue each buy an analyst at one budget.

    Attributes:
        budget: Items the analyst is assumed to read.
        ranking: Which key ordered the episode queue.
        n_malicious_days: Malicious entity-days in the test half. The denominator that matters.
        n_insiders: Labelled insiders in the test half.
        n_scored_days: Entity-days scored in the test half.
        n_episodes_available: Episodes assembled from them.
        n_episode_days_available: Entity-days those episodes contain in total.
        baseline_true_items: Of the top ``budget`` entity-days, how many are malicious.
        baseline_malicious_days: Malicious entity-days those items cover. Identical to
            ``baseline_true_items`` by construction — a day covers itself — and stated so the two
            queues are compared on the same quantity rather than on two different ones.
        baseline_insiders: Distinct labelled insiders those items name.
        episode_true_items: Of the top ``budget`` episodes, how many contain a malicious day.
        episode_entity_days: Entity-days those episodes contain — the real reading cost.
        episode_malicious_days: Malicious entity-days those episodes cover.
        episode_insiders: Distinct labelled insiders those episodes name.
        episode_carried_days: Days inside those episodes that could not have reached the budget
            alone.
        cut_score: Rank score of the last episode taken.
        tie_span_at_cut: How many episodes in the whole queue share it.
        cut_is_arbitrary: Whether the cut fell inside a tie block.
    """

    model_config = ConfigDict(frozen=True)

    budget: int = Field(ge=1)
    ranking: EpisodeRanking = "peak"
    n_malicious_days: int = Field(ge=0)
    n_insiders: int = Field(ge=0)
    n_scored_days: int = Field(ge=0)
    n_episodes_available: int = Field(ge=0)
    n_episode_days_available: int = Field(default=0, ge=0)
    baseline_true_items: int = Field(ge=0)
    baseline_malicious_days: int = Field(ge=0)
    baseline_insiders: int = Field(ge=0)
    episode_true_items: int = Field(ge=0)
    episode_entity_days: int = Field(ge=0)
    episode_malicious_days: int = Field(ge=0)
    episode_insiders: int = Field(ge=0)
    episode_carried_days: int = Field(ge=0)
    cut_score: float | None = None
    tie_span_at_cut: int = Field(default=0, ge=0)
    cut_is_arbitrary: bool = False

    @property
    def compression_ratio(self) -> float:
        """Entity-days **inside episodes** per episode. One means no compression at all.

        Deliberately *not* ``n_scored_days / n_episodes``: dividing the whole corpus by the
        episode count would produce a huge number that describes the anchor threshold rather than
        any grouping the rule did. What an analyst actually experiences is how many entity-days
        one item replaces, which is this.
        """
        if not self.n_episodes_available:
            return 0.0
        return self.n_episode_days_available / self.n_episodes_available

    @property
    def baseline_expected_by_chance(self) -> float:
        """Malicious entity-days a random sample of ``budget`` entity-days would expect.

        The bar any ranking has to clear, on `phos.atlas.queue.BudgetOutcome`'s pattern. A key
        scoring below it has not merely failed to help; it is pointing the wrong way.
        """
        if not self.n_scored_days:
            return 0.0
        return min(self.budget, self.n_scored_days) * self.n_malicious_days / self.n_scored_days

    @property
    def baseline_coverage(self) -> float:
        """Share of malicious entity-days the per-day queue shows at this budget."""
        if not self.n_malicious_days:
            return 0.0
        return self.baseline_malicious_days / self.n_malicious_days

    @property
    def episode_coverage(self) -> float:
        """Share of malicious entity-days the episode queue shows at this budget."""
        if not self.n_malicious_days:
            return 0.0
        return self.episode_malicious_days / self.n_malicious_days

    @property
    def coverage_multiple(self) -> float:
        """How many times more malicious activity the episode queue shows.

        Zero when the baseline showed none, which would make the ratio undefined rather than
        infinite.

        Warning:
            **Not publishable on its own.** A ratio of two small integer counts carries no
            interval, and ADR 0072 published this one as "1.8x the malicious activity in
            front of an analyst" before any null existed for it. U2 ran that null: the 9
            observed malicious entity-days sit at the top edge of a permuted 95% interval of
            [5, 9] with ``P(permuted >= 9) = 0.055`` (ADR 0076, register R18). The count
            stands; the ratio was withdrawn, and `verdict` no longer prints one.
        """
        if not self.baseline_malicious_days:
            return 0.0
        return self.episode_malicious_days / self.baseline_malicious_days

    @property
    def days_read_per_item(self) -> float:
        """Average entity-days inside one taken episode. The honest cost of the bigger unit."""
        taken = min(self.budget, self.n_episodes_available)
        return (self.episode_entity_days / taken) if taken else 0.0

    def verdict(self) -> str:
        """State in one line what this budget actually bought, including when it bought nothing."""
        if self.episode_malicious_days > self.baseline_malicious_days:
            return (
                f"At {self.budget} items the episode queue shows "
                f"{self.episode_malicious_days} of {self.n_malicious_days} malicious entity-days "
                f"against the per-day queue's {self.baseline_malicious_days}, and names "
                f"{self.episode_insiders} of {self.n_insiders} insider(s) against "
                f"{self.baseline_insiders}. It costs {self.days_read_per_item:.1f} entity-days "
                f"per item read. Whether the difference in coverage is separable from chance "
                f"needs a null beside it, which this comparison does not carry: on CERT r3.1 it "
                f"is not (ADR 0076, register R18)."
            )
        if self.episode_malicious_days == self.baseline_malicious_days:
            return (
                f"At {self.budget} items the episode queue shows exactly as much malicious "
                f"activity as the per-day queue ({self.episode_malicious_days} of "
                f"{self.n_malicious_days} entity-days). Compression changed the unit and not the "
                "coverage."
            )
        return (
            f"At {self.budget} items the episode queue shows LESS malicious activity than the "
            f"per-day queue ({self.episode_malicious_days} against "
            f"{self.baseline_malicious_days} of {self.n_malicious_days} entity-days). Grouping "
            "cost coverage at this budget."
        )


def compare_at_budget(
    days: Sequence[QueuedDay],
    alerts: Sequence[EpisodeAlert],
    budget: int,
    n_malicious_days: int,
    n_insiders: int,
    ranking: EpisodeRanking = "peak",
) -> BudgetComparison:
    """Score both queues at one budget.

    Args:
        days: Every scored entity-day in the test half, carrying its truth.
        alerts: Every episode assembled from them, carrying what it covers.
        budget: Items the analyst reads. Positive.
        n_malicious_days: Malicious entity-days in the test half.
        n_insiders: Labelled insiders in the test half.
        ranking: Which key orders the episode queue.

    Returns:
        The comparison.

    Raises:
        ValueError: If ``budget`` is not positive — a budget of zero is not an operating point,
            it is switching the system off.
    """
    if budget < 1:
        raise ValueError(f"budget must be a positive analyst volume, got {budget}")

    ranked_days = sorted(days, key=lambda item: (-item.score, item.day, item.user_id))[:budget]
    baseline_true = sum(1 for item in ranked_days if item.malicious)
    baseline_insiders = len({item.user_id for item in ranked_days if item.malicious})

    ranked = rank_episodes(alerts, ranking)
    taken = list(ranked[:budget])
    covered_days = {day for alert in taken for day in alert.malicious_days}
    episode_insiders = {alert.insider for alert in taken if alert.insider is not None}

    cut_score: float | None = None
    tie_span = 0
    arbitrary = False
    if taken:
        cut_score = taken[-1].rank_score(ranking)
        tie_span = sum(1 for alert in ranked if alert.rank_score(ranking) == cut_score)
        arbitrary = len(ranked) > len(taken) and ranked[len(taken)].rank_score(ranking) == cut_score

    comparison = BudgetComparison(
        budget=budget,
        ranking=ranking,
        n_malicious_days=n_malicious_days,
        n_insiders=n_insiders,
        n_scored_days=len(days),
        n_episodes_available=len(alerts),
        n_episode_days_available=sum(alert.n_days for alert in alerts),
        baseline_true_items=baseline_true,
        baseline_malicious_days=baseline_true,
        baseline_insiders=baseline_insiders,
        episode_true_items=sum(1 for alert in taken if alert.is_true_positive),
        episode_entity_days=sum(alert.n_days for alert in taken),
        episode_malicious_days=len(covered_days),
        episode_insiders=len(episode_insiders),
        episode_carried_days=sum(alert.n_carried_days for alert in taken),
        cut_score=cut_score,
        tie_span_at_cut=tie_span,
        cut_is_arbitrary=arbitrary,
    )
    logger.info("%s", comparison.verdict())
    return comparison

"""A behaviour that lasted three weeks is one thing to investigate, not twenty-one.

PART 6B scores an entity on a day and forgets. That is the right unit for a *measurement* and the
wrong unit for an *investigation*: CERT r3.1's second insider is malicious across sixty calendar
days, and a queue built from entity-days can only ever offer an analyst those days one at a time,
competing with each other for the same budget. Fifty-three malicious entity-days presented as
fifty-three separate items is not fifty-three findings; it is one finding shattered into
fifty-three, and the shattering is what makes it invisible at a realistic budget.

This module assembles the shards. An **episode** is a run of one entity's anomalous days, held
together by a declared rule, carrying a start, an end, a trajectory and every day it contains.

**The boundary rule is declared, and it is inherited rather than invented.** Two candidate days of
one entity belong to the same episode when the gap between them is at most `EpisodePolicy.gap`.
The default is **seven days**, and it is not a number chosen here: `phos.sentiel.SentielConfig`
already sets the reasoning engine's correlation window to seven days, with a reason given at the
time — a window shorter than three days splits a working pattern across a weekend's absence, and a
week is the cadence an organisation already runs on. Using a *different* number for episodes would
mean PHOS held two answers to one question. `EPISODE_GAP_INHERITS_CORRELATION_WINDOW` asserts the
two stay equal, so they cannot drift apart silently.

**Nothing here is fitted to the known insiders.** The gap is inherited; the extension floor is read
off the score distribution with no label in sight, exactly as `thresholds_for_budgets` reads an
operating point; and `episode_sensitivity` exists so a report shows the *whole* sweep over both
parameters rather than the corner of it that flattered the result. A rule that had to be tuned to
find two people would tell you nothing about the third.

**Two thresholds, because they answer different questions.** A day joins an episode at
`extension_floor` — "was anything unusual happening?" — and an episode is worth an analyst's time
only if some day in it reaches `anchor_threshold` — "was anything unusual *enough*?". That
separation is the whole mechanism behind weak-signal accumulation: a day that could never win a
place in a 48-item queue on its own still becomes part of the story when it sits beside a day that
could. `phos.sentiel.weak_signals` measures how much of an episode's evidence arrives that way.

**An episode is a bigger thing to read than a day, and every number here says so.** Compressing
fifty-three entity-days into four episodes is only a gain if four episodes cost an analyst less
than fifty-three days did, and this module reports `Episode.n_days` on every episode so that
trade is visible rather than assumed. `phos.sentiel.compression` is where it is actually measured.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from datetime import datetime, timedelta
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from phos.ontology import EntityId, UtcDatetime
from phos.reasoning import ReasoningConfig

__all__ = [
    "EPISODE_GAP_INHERITS_CORRELATION_WINDOW",
    "EPISODE_UNIT_CAVEAT",
    "EXTENSION_FLOOR_QUANTILES",
    "GAP_SWEEP_DAYS",
    "Episode",
    "EpisodeDay",
    "EpisodePolicy",
    "EpisodeRanking",
    "assemble_episodes",
    "episode_sensitivity",
    "floor_at_quantile",
]

logger = logging.getLogger(__name__)

EPISODE_GAP_INHERITS_CORRELATION_WINDOW: Final = ReasoningConfig(
    correlation_window=timedelta(days=7)
).correlation_window
"""The declared episode gap, taken from the correlation window `SentielConfig` already sets.

Read from `phos.reasoning.ReasoningConfig` rather than restated as ``timedelta(days=7)``, so that
"how far apart may two related facts be?" has exactly one answer in Sentiel. A test asserts the two
are equal; if a later PART moves the correlation window, this moves with it or the test fails.
"""

EPISODE_UNIT_CAVEAT: Final = (
    "An EPISODE IS A LARGER UNIT OF READING THAN AN ENTITY-DAY. Compressing N entity-days into M "
    "episodes is a gain only if an analyst can work an episode for less than the N/M days it "
    "replaces. Every episode reports n_days so the trade is visible; no number in this module "
    "assumes an episode and a day cost the same to triage."
)

EXTENSION_FLOOR_QUANTILES: Final[tuple[float, ...]] = (0.50, 0.75, 0.90, 0.95, 0.99)
"""The extension floors a sensitivity table reports, as quantiles of the score distribution.

Quantiles rather than raw scores because a quantile is comparable across feature sets and policies,
and because it is read off the scores with no label consulted — the same discipline
``thresholds_for_budgets`` applies to an operating point. The whole tuple is reported; none of it
is selected.
"""

GAP_SWEEP_DAYS: Final[tuple[int, ...]] = (1, 2, 3, 7, 14)
"""The gaps a sensitivity table reports. Seven is the declared default; the rest bracket it."""

EpisodeRanking = Literal["peak", "total", "days", "breadth"]
"""Which number an episode queue is ordered by. Declared, never inferred from what scores best.

* ``peak`` — the highest single-day score in the episode. This is PART 6B's own ranking lifted to
  the episode unit, and it is the default for that reason: it changes the *unit*, not the detector.
* ``total`` — the sum over the episode's days. Rewards persistence, and will rank a long quiet
  drift above a short loud spike.
* ``days`` — how many days the episode spans. Ignores magnitude entirely.
* ``breadth`` — the largest number of distinct behaviour families that departed on any one day.
"""


class EpisodeDay(BaseModel):
    """One entity-day inside an episode, and the pointer back to what it was built from.

    Attributes:
        day: The window's start, midnight UTC.
        score: The `phos.sentiel.ScoredWindow` score for that entity-day.
        family_names: The distinct `phos.sentiel.BehaviourFamily` values that contributed to the
            day's score, sorted. Kept as names rather than a count because
            `phos.sentiel.weak_signals` needs to know *which* domains a day spoke for, not just
            how many — accumulation across domains is the whole question there.
        leading_feature: The largest single contributor, so an episode's day list names something
            an analyst can open.
        anchor: Whether this day on its own reaches the anchor threshold. An episode with exactly
            one anchor day and several non-anchor days is the weak-signal case.
    """

    model_config = ConfigDict(frozen=True)

    day: UtcDatetime
    score: float = Field(ge=0.0)
    family_names: tuple[str, ...] = ()
    leading_feature: str | None = None
    anchor: bool = False

    @property
    def families(self) -> int:
        """How many distinct behaviour families contributed to this day's score."""
        return len(self.family_names)


class Episode(BaseModel):
    """One entity's coherent stretch of anomalous behaviour.

    Attributes:
        entity_id: Whose behaviour this is. An episode is always about exactly one entity — the
            same rule ADR 0023 gives for a hypothesis, for the same reason.
        days: The entity-days it contains, earliest first. Never empty.
        anchor_threshold: The score a day had to reach to anchor the episode, recorded so the
            episode says what rule produced it.
        extension_floor: The score a day had to reach to join, recorded for the same reason.
        gap: The declared maximum gap between consecutive member days.

    Invariants:
        Days are strictly ascending and at least one of them is an anchor, because an episode with
        no anchor day was never worth reporting and would only dilute a queue.
    """

    model_config = ConfigDict(frozen=True)

    entity_id: EntityId
    days: tuple[EpisodeDay, ...] = Field(min_length=1)
    anchor_threshold: float = Field(ge=0.0)
    extension_floor: float = Field(ge=0.0)
    gap: timedelta = EPISODE_GAP_INHERITS_CORRELATION_WINDOW

    @model_validator(mode="after")
    def _ordered_and_anchored(self) -> Episode:
        """Refuse an unordered or unanchored episode rather than reporting one."""
        stamps = [day.day for day in self.days]
        if stamps != sorted(stamps) or len(set(stamps)) != len(stamps):
            raise ValueError(
                f"episode days for {self.entity_id} must be strictly ascending, got {stamps}"
            )
        if not any(day.anchor for day in self.days):
            raise ValueError(
                f"episode for {self.entity_id} starting {stamps[0].date()} has no anchor day: "
                "every day in it sits below the anchor threshold, so nothing in it earned a "
                "place in an operator's queue"
            )
        return self

    @property
    def start(self) -> datetime:
        """First day of the episode."""
        return self.days[0].day

    @property
    def end(self) -> datetime:
        """Last day of the episode."""
        return self.days[-1].day

    @property
    def n_days(self) -> int:
        """How many entity-days the episode contains. The reading cost of this one item."""
        return len(self.days)

    @property
    def span(self) -> timedelta:
        """Calendar time from the first day to the last. Zero for a single-day episode."""
        return self.end - self.start

    @property
    def peak(self) -> float:
        """The largest single-day score."""
        return max(day.score for day in self.days)

    @property
    def total(self) -> float:
        """Every day's score summed."""
        return sum(day.score for day in self.days)

    @property
    def breadth(self) -> int:
        """The most behaviour families that departed together on any one of its days."""
        return max(day.families for day in self.days)

    @property
    def n_anchor_days(self) -> int:
        """How many days would have reached an operator's queue on their own."""
        return sum(1 for day in self.days if day.anchor)

    @property
    def n_carried_days(self) -> int:
        """How many days are in this episode only because a neighbouring day anchored it.

        The weak-signal count: behaviour a per-day queue at this budget could never have shown an
        analyst, made visible by the company it keeps.
        """
        return self.n_days - self.n_anchor_days

    @property
    def trajectory(self) -> Literal["rising", "falling", "flat", "single"]:
        """Which way the episode is going, by comparing its first and last halves.

        A declared, threshold-free summary: the mean score of the later half against the earlier
        half, with the middle day of an odd-length episode counted in neither. ``flat`` when the
        two means are equal, which on real scores means only a genuinely symmetric episode.
        """
        if self.n_days == 1:
            return "single"
        half = self.n_days // 2
        earlier = [day.score for day in self.days[:half]]
        later = [day.score for day in self.days[self.n_days - half :]]
        first = sum(earlier) / len(earlier)
        last = sum(later) / len(later)
        if last > first:
            return "rising"
        if last < first:
            return "falling"
        return "flat"

    def rank_score(self, ranking: EpisodeRanking) -> float:
        """Return the number this episode is ranked by under ``ranking``."""
        if ranking == "peak":
            return self.peak
        if ranking == "total":
            return self.total
        if ranking == "days":
            return float(self.n_days)
        return float(self.breadth)

    def covers(self, day: datetime) -> bool:
        """Return whether ``day`` is one of this episode's member days.

        Membership, not span: a gap day inside an episode is *not* covered, because nothing was
        detected on it and claiming otherwise would inflate every recall built from episodes.
        """
        return any(member.day == day for member in self.days)


class EpisodePolicy(BaseModel):
    """The declared rule that turns scored entity-days into episodes.

    Attributes:
        anchor_threshold: The score a day must reach for its episode to be worth reporting. Set
            from an operating point on the score distribution, never from a label.
        extension_floor: The score a day must reach to join an episode at all. Must not exceed
            the anchor threshold — a floor above the anchor would mean a day could anchor an
            episode it is not allowed to join.
        gap: Largest allowed gap between consecutive member days. Defaults to
            `EPISODE_GAP_INHERITS_CORRELATION_WINDOW`.

    Invariants:
        ``extension_floor <= anchor_threshold`` and ``gap`` is a positive duration.
    """

    model_config = ConfigDict(frozen=True)

    anchor_threshold: float = Field(ge=0.0)
    extension_floor: float = Field(default=0.0, ge=0.0)
    gap: timedelta = EPISODE_GAP_INHERITS_CORRELATION_WINDOW

    @model_validator(mode="after")
    def _floor_below_anchor(self) -> EpisodePolicy:
        if self.extension_floor > self.anchor_threshold:
            raise ValueError(
                f"extension_floor {self.extension_floor} exceeds anchor_threshold "
                f"{self.anchor_threshold}: a day could anchor an episode it may not join"
            )
        if self.gap <= timedelta(0):
            raise ValueError(
                f"gap must be a positive duration, got {self.gap}: a zero gap would put every day "
                "in its own episode and assemble nothing"
            )
        return self


class _Candidate(BaseModel):
    """One entity-day offered to the assembler."""

    model_config = ConfigDict(frozen=True)

    entity_id: EntityId
    day: UtcDatetime
    score: float = Field(ge=0.0)
    family_names: tuple[str, ...] = ()
    leading_feature: str | None = None


def floor_at_quantile(scores: Sequence[float], quantile: float) -> float:
    """Return the score at ``quantile`` of the distribution, consulting no label.

    Args:
        scores: Every entity-day score in the run, in any order.
        quantile: In ``[0, 1]``. ``0.90`` is the top decile's lower bound.

    Returns:
        The score at that quantile by nearest-rank, or ``0.0`` for an empty distribution.

    Raises:
        ValueError: If ``quantile`` is outside ``[0, 1]``.
    """
    if not 0.0 <= quantile <= 1.0:
        raise ValueError(f"quantile must be in [0, 1], got {quantile}")
    if not scores:
        return 0.0
    ordered = sorted(scores)
    index = min(len(ordered) - 1, int(quantile * len(ordered)))
    return ordered[index]


def assemble_episodes(
    candidates: Iterable[tuple[EntityId, datetime, float, Sequence[str], str | None]],
    policy: EpisodePolicy,
) -> list[Episode]:
    """Group scored entity-days into episodes under a declared rule.

    Args:
        candidates: ``(entity_id, day, score, family_names, leading_feature)`` for every scored
            entity-day in the run, in any order. Days below `EpisodePolicy.extension_floor` are
            dropped here rather than by the caller, so the floor is applied in exactly one place.
        policy: The declared rule.

    Returns:
        Episodes ordered by start, then entity. Every returned episode has at least one anchor
        day; runs that never reached the anchor threshold are dropped, because an episode nothing
        in which was unusual enough to alert on is not a finding.

    Note:
        Pure and deterministic: the same candidates and the same policy always produce the same
        episodes, in the same order.
    """
    rows = [
        _Candidate(
            entity_id=entity_id,
            day=day,
            score=score,
            family_names=tuple(sorted(family_names)),
            leading_feature=leading_feature,
        )
        for entity_id, day, score, family_names, leading_feature in candidates
        if score >= policy.extension_floor
    ]

    by_entity: dict[EntityId, list[_Candidate]] = {}
    for row in rows:
        by_entity.setdefault(row.entity_id, []).append(row)

    episodes: list[Episode] = []
    dropped = 0
    for entity_id in sorted(by_entity):
        ordered = sorted(by_entity[entity_id], key=lambda item: item.day)
        run: list[_Candidate] = []
        for row in ordered:
            if run and row.day - run[-1].day > policy.gap:
                built = _build(entity_id, run, policy)
                if built is None:
                    dropped += 1
                else:
                    episodes.append(built)
                run = []
            run.append(row)
        if run:
            built = _build(entity_id, run, policy)
            if built is None:
                dropped += 1
            else:
                episodes.append(built)

    episodes.sort(key=lambda episode: (episode.start, episode.entity_id))
    logger.info(
        "assembled %d episode(s) from %d candidate entity-day(s) at floor %.4f / anchor %.4f / "
        "gap %s; %d run(s) dropped for reaching no anchor",
        len(episodes),
        len(rows),
        policy.extension_floor,
        policy.anchor_threshold,
        policy.gap,
        dropped,
    )
    return episodes


def _build(entity_id: EntityId, run: Sequence[_Candidate], policy: EpisodePolicy) -> Episode | None:
    """Return the episode a run of candidate days makes, or ``None`` if it never anchored."""
    days = tuple(
        EpisodeDay(
            day=row.day,
            score=row.score,
            family_names=row.family_names,
            leading_feature=row.leading_feature,
            anchor=row.score >= policy.anchor_threshold,
        )
        for row in run
    )
    if not any(day.anchor for day in days):
        return None
    return Episode(
        entity_id=entity_id,
        days=days,
        anchor_threshold=policy.anchor_threshold,
        extension_floor=policy.extension_floor,
        gap=policy.gap,
    )


class SensitivityRow(BaseModel):
    """What one ``(gap, extension floor)`` pair does to the episode set.

    Attributes:
        gap_days: The gap in whole days.
        quantile: The extension floor, as a quantile of the score distribution.
        extension_floor: The score that quantile resolved to.
        n_episodes: Episodes assembled.
        n_days: Entity-days those episodes contain.
        n_carried_days: Days present only because a neighbour anchored the episode.
        max_days: Days in the longest episode.
    """

    model_config = ConfigDict(frozen=True)

    gap_days: int = Field(ge=1)
    quantile: float = Field(ge=0.0, le=1.0)
    extension_floor: float = Field(ge=0.0)
    n_episodes: int = Field(ge=0)
    n_days: int = Field(ge=0)
    n_carried_days: int = Field(ge=0)
    max_days: int = Field(ge=0)


def episode_sensitivity(
    candidates: Sequence[tuple[EntityId, datetime, float, Sequence[str], str | None]],
    anchor_threshold: float,
    *,
    gaps: Sequence[int] = GAP_SWEEP_DAYS,
    quantiles: Sequence[float] = EXTENSION_FLOOR_QUANTILES,
) -> list[SensitivityRow]:
    """Return the full sweep over both declared parameters, so none of it can be cherry-picked.

    A boundary rule that only works at one setting is a rule fitted to the answer. Reporting the
    whole grid — including the settings that produce a worse episode set — is what makes the
    declared default readable as a choice rather than as a search result.

    Args:
        candidates: As `assemble_episodes`.
        anchor_threshold: The operating point, held fixed across the sweep.
        gaps: Gaps in days.
        quantiles: Extension floors as quantiles of the candidate score distribution.

    Returns:
        One row per pair, gap-major then quantile.
    """
    scores = [score for _, _, score, _, _ in candidates]
    rows: list[SensitivityRow] = []
    for gap_days in gaps:
        for quantile in quantiles:
            floor = min(floor_at_quantile(scores, quantile), anchor_threshold)
            episodes = assemble_episodes(
                candidates,
                EpisodePolicy(
                    anchor_threshold=anchor_threshold,
                    extension_floor=floor,
                    gap=timedelta(days=gap_days),
                ),
            )
            rows.append(
                SensitivityRow(
                    gap_days=gap_days,
                    quantile=quantile,
                    extension_floor=floor,
                    n_episodes=len(episodes),
                    n_days=sum(episode.n_days for episode in episodes),
                    n_carried_days=sum(episode.n_carried_days for episode in episodes),
                    max_days=max((episode.n_days for episode in episodes), default=0),
                )
            )
    return rows

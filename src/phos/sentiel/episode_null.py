"""Is the episode a real unit, or a gap rule chaining a high base rate? — Usefulness Phase U2.

`phos.sentiel.episodes` groups an entity's elevated days into one item when consecutive members sit
within a declared seven-day gap (ADR 0072). That rule claims something falsifiable: that an
entity's elevated days *cluster in time*. This module holds the only null that can falsify it.

**The null reshuffles each entity's own scores across their own days.** It holds fixed the entity's
activity calendar and their entire score distribution — so an entity the model finds unusual half
the time stays exactly that unusual — and destroys only the order. Everything the episode rule is
entitled to use is preserved except the one thing it claims to find.

An observed statistic *inside* this null is not proof that nothing real is there. It is proof that
the rule's output is reproduced with no temporal structure to find, which is the only sense in
which "an artefact of the gap rule" can be measured rather than asserted.

Split from `phos.sentiel.failure` — which asks why an individual's days do not alert — because the
two answer different questions and the repository keeps modules under 500 lines.
"""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "EpisodeNull",
    "coherence_permutation_null",
    "coherence_share",
    "episode_permutation_null",
]


# ------------------------------------------------------------------------------------------------
# The episode unit, read against the only null that can falsify it
# ------------------------------------------------------------------------------------------------


class EpisodeNull(BaseModel):
    """What the episode rule produces when every entity's own scores are reshuffled across days.

    The null preserves each entity's activity calendar **and** their whole score distribution, and
    destroys only the order. So it holds fixed everything the episode rule is entitled to use
    except the one thing it claims to find: that the elevated days of an entity cluster in time.

    An observed statistic inside this null is not evidence that the rule found nothing real — it is
    evidence that the rule's output is reproduced without any temporal structure to find, which is
    the only sense in which "an artefact of the gap rule" can be measured rather than asserted.
    """

    model_config = ConfigDict(frozen=True)

    n_iterations: int = Field(gt=0)
    seed: int
    observed: float
    mean: float
    low: float
    high: float
    p_at_least_observed: float = Field(ge=0.0, le=1.0)

    @property
    def inside_null(self) -> bool:
        """Whether the observed value falls inside the null's central 95% interval."""
        return self.low <= self.observed <= self.high


def _episodes[Row: tuple[Any, ...]](
    pairs: Sequence[Row], floor: float, anchor: float, gap: timedelta
) -> list[list[Row]]:
    """Assemble one entity's reportable episodes on the declared two-threshold rule.

    Generic over the row shape, and returns exactly the rows it was handed: ``(day, score)`` for
    the four structural statistics, ``(day, score, leading_feature)`` for the coherence null. The
    rule reads only the first two fields, so it is written once over both rather than duplicated —
    a second copy of the gap rule is the one thing the episode gate could not catch.

    The rule is `phos.sentiel.episodes`'. Reimplemented here over ``(day, score)`` pairs
    rather than over `Episode` objects so the null
    can be run tens of thousands of times without building a model instance per run. The runner
    asserts this agrees with the published episode count before using it, which is what keeps the
    shortcut honest.
    """
    members = [p for p in pairs if p[1] >= floor]
    runs: list[list[Row]] = []
    run: list[Row] = []
    for pair in members:
        if run and pair[0] - run[-1][0] > gap:
            runs.append(run)
            run = []
        run.append(pair)
    if run:
        runs.append(run)
    return [r for r in runs if any(p[1] >= anchor for p in r)]


def episode_permutation_null(
    by_entity: Mapping[str, Sequence[tuple[datetime, float]]],
    statistic: str,
    floor: float,
    anchor: float,
    gap: timedelta,
    *,
    iterations: int = 200,
    seed: int = 11,
    malicious: frozenset[tuple[str, datetime]] | None = None,
    budget: int | None = None,
) -> EpisodeNull:
    """Run the reshuffle null for one episode-set statistic.

    Args:
        by_entity: Each entity's ``(day, score)`` pairs, day-sorted.
        statistic: One of ``"n_episodes"``, ``"n_days"``, ``"longest"``, ``"n_long"``.
        floor: The extension floor a day must reach to join an episode.
        anchor: The anchor threshold an episode must contain to be reportable.
        gap: The declared maximum gap between member days.
        iterations: How many reshuffles.
        seed: The seed, recorded on the result so a reader can reproduce it.
        malicious: The ground-truth ``(entity, day)`` pairs. Required by ``"malicious_days"`` and
            ignored otherwise. The null holds every entity's calendar fixed, so a malicious day
            keeps its date under permutation and only the score standing on it changes.
        budget: How many episodes an operator reads. Required by ``"malicious_days"`` and ignored
            otherwise. Applied by ranking episodes on ``peak`` — the maximum day score, the
            ranking ADR 0072 published — and keeping the first ``budget``.

    Returns:
        The null, with the observed value beside it.
    """

    def measure(entity_pairs: Mapping[str, Sequence[tuple[datetime, float]]]) -> float:
        owned = [
            (entity, e)
            for entity, rows in entity_pairs.items()
            for e in _episodes(rows, floor, anchor, gap)
        ]
        episodes = [e for _entity, e in owned]
        if statistic == "n_episodes":
            return float(len(episodes))
        if statistic == "n_days":
            return float(sum(len(e) for e in episodes))
        if statistic == "longest":
            return float(max((len(e) for e in episodes), default=0))
        if statistic == "n_long":
            return float(sum(1 for e in episodes if len(e) >= 40))
        if statistic == "malicious_days":
            if malicious is None or budget is None:
                raise ValueError(
                    "the 'malicious_days' statistic needs both 'malicious' and 'budget'; "
                    "counting ground truth inside an unbounded queue would answer a different "
                    "question from the one an operator's budget asks"
                )
            queue = sorted(owned, key=lambda pair: -max(score for _day, score in pair[1]))[:budget]
            return float(
                sum(
                    1
                    for entity, episode in queue
                    for day, _score in episode
                    if (entity, day) in malicious
                )
            )
        raise ValueError(f"unknown statistic {statistic!r}")

    observed = measure(by_entity)
    rng = random.Random(seed)
    draws: list[float] = []
    for _ in range(iterations):
        shuffled: dict[str, list[tuple[datetime, float]]] = {}
        for entity, rows in by_entity.items():
            days = [r[0] for r in rows]
            scores = [r[1] for r in rows]
            rng.shuffle(scores)
            shuffled[entity] = list(zip(days, scores, strict=True))
        draws.append(measure(shuffled))

    draws.sort()
    lo = draws[int(0.025 * len(draws))]
    hi = draws[min(int(0.975 * len(draws)), len(draws) - 1)]
    at_least = sum(1 for d in draws if d >= observed) / len(draws)
    return EpisodeNull(
        n_iterations=iterations,
        seed=seed,
        observed=observed,
        mean=sum(draws) / len(draws),
        low=lo,
        high=hi,
        p_at_least_observed=at_least,
    )


def coherence_permutation_null(
    by_entity: Mapping[str, Sequence[tuple[datetime, float, str | None]]],
    floor: float,
    anchor: float,
    gap: timedelta,
    *,
    iterations: int = 200,
    seed: int = 11,
) -> EpisodeNull:
    """Run the reshuffle null for `coherence_share` averaged over multi-day episodes.

    Separate from `episode_permutation_null` because coherence needs a third field per day — the
    feature that led the score — and reshuffling the score **without** it would answer a question
    nobody asked: the leading feature and the score are two readings of the same scored day, so the
    null carries them together and destroys only their position in the calendar.

    That makes this the same null as the other four statistics: each entity's own observations
    redealt across their own days, with the entity's activity calendar, score distribution and
    leading-feature distribution all held fixed.

    Args:
        by_entity: Each entity's ``(day, score, leading_feature)`` triples, day-sorted. A
            ``None`` leading feature is read as the empty string, exactly as the runner reads it
            for the observed value, so the two cannot disagree about a day with no leading feature.
        floor: The extension floor a day must reach to join an episode.
        anchor: The anchor threshold an episode must contain to be reportable.
        gap: The declared maximum gap between member days.
        iterations: How many reshuffles.
        seed: The seed, recorded on the result.

    Returns:
        The null, with the observed mean coherence share beside it.
    """

    def measure(entity_rows: Mapping[str, Sequence[tuple[datetime, float, str | None]]]) -> float:
        shares = [
            share
            for rows in entity_rows.values()
            for episode in _episodes(rows, floor, anchor, gap)
            if (share := coherence_share([(row[2] or "") for row in episode])) is not None
        ]
        return sum(shares) / len(shares) if shares else 0.0

    observed = measure(by_entity)
    rng = random.Random(seed)
    draws: list[float] = []
    for _ in range(iterations):
        shuffled: dict[str, list[tuple[datetime, float, str | None]]] = {}
        for entity, rows in by_entity.items():
            days = [row[0] for row in rows]
            readings = [(row[1], row[2]) for row in rows]
            rng.shuffle(readings)
            shuffled[entity] = [
                (day, score, leading) for day, (score, leading) in zip(days, readings, strict=True)
            ]
        draws.append(measure(shuffled))

    draws.sort()
    return EpisodeNull(
        n_iterations=iterations,
        seed=seed,
        observed=observed,
        mean=sum(draws) / len(draws),
        low=draws[int(0.025 * len(draws))],
        high=draws[min(int(0.975 * len(draws)), len(draws) - 1)],
        p_at_least_observed=sum(1 for d in draws if d >= observed) / len(draws),
    )


def coherence_share(leading_features: Iterable[str]) -> float | None:
    """Return the share of an episode's days that share its single most common leading feature.

    The narrowest honest reading of "is this one story": if an episode's days are driven by
    different features on different days, whatever the rule grouped is not a story a human would
    tell. ``None`` for an episode of fewer than two days, which cannot disagree with itself.
    """
    features = list(leading_features)
    if len(features) < 2:
        return None
    return Counter(features).most_common(1)[0][1] / len(features)

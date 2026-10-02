"""Wiring `phos.sentiel.sequences` to a corpus, so a rare *order* can finally be evidence.

`sequences.sequence_surprise` has existed since Session S1 and has never been shown a corpus. Its
only callers are a fixture diagnostic (`rare_path_beats_count_baseline`) and the research report
that quotes it. `phos.ontology.EvidenceKind.SEQUENCE_ANOMALY` has existed since PART 1 and is
emitted by nothing at all: two reasoning templates match on it, and no engine has ever produced
one. This module closes both gaps against CERT r3.1.

**The claim being tested is narrow and stated up front.** A set of individually-ordinary actions,
performed in an unusual order, should be visible as evidence. The count features cannot express
that by construction — they are sums and cardinalities, and both are invariant to order. So the
measurement that matters is not "does sequence surprise fire?" but "**does it fire somewhere the
counts do not?**", and `SequenceScores` reports the ordered score beside
`sequences.count_baseline_surprise` on the same day so the comparison is forced.

**What is trained, and on what.** The n-gram multiset is built from the **attack-free training
prefix only** — the same split PART 6B fits its baselines on, cut at the first labelled malicious
instant — so nothing scored has contributed to the distribution it is judged against. Two
baselines are kept apart because they answer different questions:

* *population* — how rare is this path across the organisation's own history?
* *self* — how rare is it for this person? A cold-start entity with fewer than
  `SequencePolicy.min_self_windows` training days gets no self score at all, which is
  `phos.sentiel.peers`' rule ("unknown is not anomalous") applied one layer out.

**Every number that could have been tuned is declared instead.** ``n`` is **3**, because a bigram
is a single transition — already implicit in the token alphabet — and a trigram is the shortest
window that can express a *path*: A, then B, then C. The alert cut is the **99th percentile of the
training-prefix surprise distribution**, computed with no label in sight, in the same spirit as
``thresholds_for_budgets``. `SEQUENCE_SWEEP` carries the alternatives at ``n`` ∈ {2, 3, 4} and cuts
at {95, 99, 99.9} so a report shows the whole grid rather than the corner that flattered it.

**The arithmetic is the module it wires, not a copy of it.** `sequence_surprise` rebuilds its
`Counter` on every call, which is O(training set) per scored day and unusable across 200,000 of
them, so `TrainedSequences` counts once and applies the same Laplace formula. That is a
performance change and must not become a semantic one, so ``tests/sentiel/test_sequence_scoring.py``
asserts the two agree exactly on shared inputs. If they ever diverge, the test fails rather than
the numbers quietly drifting.
"""

from __future__ import annotations

import logging
import math
from collections import Counter
from collections.abc import Iterable, Sequence
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from phos.sentiel.sequences import count_baseline_surprise
from phos.sentiel.traces import DeclaredToken, EntityDayTrace

__all__ = [
    "DECLARED_NGRAM",
    "ORDER_INVARIANCE_CLAIM",
    "SEQUENCE_SWEEP",
    "SequencePolicy",
    "SequenceScores",
    "TrainedSequences",
    "ngrams_of",
    "score_day",
]

logger = logging.getLogger(__name__)

DECLARED_NGRAM: Final = 3
"""The declared window length. A bigram is one transition; a trigram is the shortest real path."""

SEQUENCE_SWEEP: Final[tuple[tuple[int, float], ...]] = tuple(
    (n, percentile) for n in (2, 3, 4) for percentile in (95.0, 99.0, 99.9)
)
"""Every ``(n, alert percentile)`` a report shows. Declared as a grid so none of it is a choice."""

ORDER_INVARIANCE_CLAIM: Final = (
    "Every PART 6B count feature is invariant to the order of an entity-day's events: sums and "
    "cardinalities cannot see order. So a sequence score can only earn its place by firing where "
    "the counts do not. SequenceScores reports the ordered surprise beside the bag-of-tokens "
    "surprise on the same day, and the run-level report gives their rank correlation, because a "
    "sequence score that merely re-expresses volume is a more expensive way to say nothing."
)


def ngrams_of(sequence: Sequence[DeclaredToken], n: int) -> list[tuple[str, ...]]:
    """Return the ``n``-grams of a token sequence, in order.

    A sequence shorter than ``n`` yields a single padded gram rather than nothing, so a very quiet
    entity-day still has a path to score. Padding uses a token value no `DeclaredToken` takes, so a
    padded gram can never collide with a real one.

    Args:
        sequence: The entity-day's declared tokens, already run-collapsed.
        n: Window length. Must be positive.

    Returns:
        The grams as tuples of token values.

    Raises:
        ValueError: If ``n`` is not positive.
    """
    if n < 1:
        raise ValueError(f"n must be positive, got {n}")
    values = [token.value for token in sequence]
    if not values:
        return []
    if len(values) < n:
        return [tuple(values + ["_"] * (n - len(values)))]
    return [tuple(values[index : index + n]) for index in range(len(values) - n + 1)]


class TrainedSequences(BaseModel):
    """An n-gram multiset learned from the attack-free prefix, and the cut read off it.

    Attributes:
        n: Window length the grams were counted at.
        counts: ``gram -> occurrences`` in the training prefix.
        total: Grams counted.
        alert_percentile: Which percentile of the training day-surprise distribution the cut sits
            at.
        alert_cut: The surprise a day must reach to raise sequence evidence. Read off training
            days only — no label, and no test day.
        training_days: Entity-days the multiset was built from.

    Invariants:
        The multiset is never updated after construction, so nothing scored can enter the
        distribution it is judged against.
    """

    model_config = ConfigDict(frozen=True)

    n: int = Field(ge=1)
    counts: dict[str, int] = Field(default_factory=dict)
    total: int = Field(default=0, ge=0)
    alert_percentile: float = Field(default=99.0, gt=0.0, lt=100.0)
    alert_cut: float = Field(default=0.0, ge=0.0)
    training_days: int = Field(default=0, ge=0)

    def surprise(self, gram: tuple[str, ...]) -> float:
        """Return the Laplace-smoothed negative log probability of one gram.

        Identical in value to `phos.sentiel.sequences.sequence_surprise` given the same training
        multiset — see this module's docstring, and the test that pins it.
        """
        vocab = len(self.counts) + 1
        probability = (self.counts.get(_key(gram), 0) + 1.0) / float(self.total + vocab)
        return -math.log(probability)

    def day_surprise(self, sequence: Sequence[DeclaredToken]) -> float:
        """Return an entity-day's mean per-gram surprise.

        The **mean** rather than the sum, deliberately: a sum grows with how many things somebody
        did, which would make this a volume feature wearing a sequence costume — and volume is
        already measured four different ways. A mean asks only "how unusual were the steps this
        day took?".
        """
        grams = ngrams_of(sequence, self.n)
        if not grams:
            return 0.0
        return sum(self.surprise(gram) for gram in grams) / float(len(grams))


def _key(gram: tuple[str, ...]) -> str:
    """Return the dict key for a gram. Joined, because a JSON object cannot hold a tuple key."""
    return "".join(gram)


class SequencePolicy(BaseModel):
    """The declared settings a sequence baseline is built under.

    Attributes:
        n: Window length. `DECLARED_NGRAM` by default.
        alert_percentile: Percentile of the training day-surprise distribution that becomes the
            alert cut.
        min_self_windows: Fewest training days an entity needs before it gets a *self* sequence
            baseline. Below it, no self score is produced at all — unknown is not anomalous.
            Eight, which is PHOS's one answer to "how many points before you may claim a
            baseline" (`phos.models.BehaviouralModel.min_samples`), reused rather than re-chosen.
    """

    model_config = ConfigDict(frozen=True)

    n: int = Field(default=DECLARED_NGRAM, ge=1)
    alert_percentile: float = Field(default=99.0, gt=0.0, lt=100.0)
    min_self_windows: int = Field(default=8, ge=1)


class SequenceScores(BaseModel):
    """One entity-day's ordered surprise, beside the order-blind baseline it must beat.

    Attributes:
        user_id: The actor.
        population: Mean per-gram surprise against the organisation's training paths.
        self_relative: The same against this entity's own training paths, or ``None`` when the
            entity had too few training days to have one.
        count_baseline: `phos.sentiel.sequences.count_baseline_surprise` over the same day's
            tokens — order-blind, and the thing an ordered score has to add something to.
        n_tokens: Collapsed tokens in the day.
        alerts: Whether `population` reached the declared cut.
    """

    model_config = ConfigDict(frozen=True)

    user_id: str
    population: float = Field(ge=0.0)
    self_relative: float | None = None
    count_baseline: float = Field(ge=0.0)
    n_tokens: int = Field(ge=0)
    alerts: bool = False


def train_population(
    traces: Iterable[EntityDayTrace], policy: SequencePolicy | None = None
) -> TrainedSequences:
    """Count n-grams over the attack-free prefix and read the alert cut off it.

    Args:
        traces: Training-prefix entity-days **only**. The caller owns the split; this function
            cannot check it, and a caller that passed test days would be training on what it is
            about to score.
        policy: Declared settings.

    Returns:
        The trained multiset with its cut.
    """
    settings = policy or SequencePolicy()
    counts: Counter[str] = Counter()
    sequences: list[tuple[DeclaredToken, ...]] = []
    for trace in traces:
        sequences.append(trace.sequence)
        counts.update(_key(gram) for gram in ngrams_of(trace.sequence, settings.n))

    trained = TrainedSequences(
        n=settings.n,
        counts=dict(counts),
        total=sum(counts.values()),
        alert_percentile=settings.alert_percentile,
        alert_cut=0.0,
        training_days=len(sequences),
    )
    # The cut is read off the training days' own surprises under the finished multiset, so it is a
    # property of what normal looked like, never of what is about to be scored.
    surprises = sorted(trained.day_surprise(sequence) for sequence in sequences)
    cut = _percentile(surprises, settings.alert_percentile)
    logger.info(
        "trained %d-gram sequence baseline on %d training entity-day(s): %d distinct gram(s), "
        "cut at p%.1f = %.4f",
        settings.n,
        len(sequences),
        len(counts),
        settings.alert_percentile,
        cut,
    )
    return trained.model_copy(update={"alert_cut": cut})


def train_self(
    traces: Iterable[EntityDayTrace], policy: SequencePolicy | None = None
) -> dict[str, TrainedSequences]:
    """Return a per-entity n-gram baseline for every entity with enough training days.

    Entities below `SequencePolicy.min_self_windows` are **absent from the mapping** rather than
    present with a neutral value, which is the distinction `phos.sentiel.peers` draws between "no
    baseline exists" and "the baseline has nothing to say yet".
    """
    settings = policy or SequencePolicy()
    by_entity: dict[str, list[tuple[DeclaredToken, ...]]] = {}
    for trace in traces:
        by_entity.setdefault(trace.user_id, []).append(trace.sequence)

    trained: dict[str, TrainedSequences] = {}
    for user_id, sequences in by_entity.items():
        if len(sequences) < settings.min_self_windows:
            continue
        counts: Counter[str] = Counter()
        for sequence in sequences:
            counts.update(_key(gram) for gram in ngrams_of(sequence, settings.n))
        trained[user_id] = TrainedSequences(
            n=settings.n,
            counts=dict(counts),
            total=sum(counts.values()),
            alert_percentile=settings.alert_percentile,
            training_days=len(sequences),
        )
    logger.info(
        "trained self sequence baselines for %d of %d entities (>= %d training days)",
        len(trained),
        len(by_entity),
        settings.min_self_windows,
    )
    return trained


def score_day(
    trace: EntityDayTrace,
    population: TrainedSequences,
    self_baselines: dict[str, TrainedSequences] | None = None,
) -> SequenceScores:
    """Score one entity-day against the trained paths, and against the order-blind baseline.

    Args:
        trace: The entity-day to score.
        population: The organisation's trained multiset.
        self_baselines: Per-entity multisets from `train_self`, when the caller wants the
            self-relative register too.

    Returns:
        The scores. ``self_relative`` is ``None`` for an entity with no self baseline.
    """
    tokens = [token.value for token in trace.sequence]
    mine = (self_baselines or {}).get(trace.user_id)
    surprise = population.day_surprise(trace.sequence)
    return SequenceScores(
        user_id=trace.user_id,
        population=surprise,
        self_relative=mine.day_surprise(trace.sequence) if mine is not None else None,
        count_baseline=count_baseline_surprise(
            tokens, [gram[0] for gram in ngrams_of(trace.sequence, 1)] or [""]
        )
        if tokens
        else 0.0,
        n_tokens=len(tokens),
        alerts=surprise >= population.alert_cut,
    )


def _percentile(ordered: Sequence[float], percentile: float) -> float:
    """Return the nearest-rank percentile of an already-sorted sequence."""
    if not ordered:
        return 0.0
    index = min(len(ordered) - 1, int(percentile / 100.0 * len(ordered)))
    return ordered[index]

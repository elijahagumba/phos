"""Classify *why* Sentiel fails on CERT r3.1, rather than treating 0.104 as a number to reduce.

Usefulness Phase item U2 (ADR 0074). The companion to `phos.eval.taxonomy`, which asked the same
question of Atlas and answered **modelling error, not missing evidence** (ADR 0075).

**Nothing here reduces a number, chooses a threshold, or edits a scorer.** The frozen PART 6B row —
precision 0.104 at 48 alerts, window recall 0.5 — is reproduced as a gate by the runner before any
figure in this module exists, and is never re-derived under its own name.

The deciding instrument is `day_ceiling`, and it is a **counterfactual settled by arithmetic rather
than by search**. `AggregationPolicy` sums one squashed term per speaking feature:

    score = Σ over speaking features of (1 - exp(-magnitude / score_scale))

Every term is below 1, whatever the magnitude. So a window in which ``k`` features spoke has
``score <= k`` — and if ``k`` is below the alert threshold, *no* magnitude on any of those features
can lift the day into the queue. Setting every speaking feature to infinite anomaly is the
strongest intervention available, and a day that still does not alert under it is **structurally
unalertable**: its failure is a property of the aggregation, not of how unusual the person was.

**The bound is ``<=`` and not ``<``, and the difference is floating point rather than mathematics.**
In exact arithmetic ``1 - exp(-m/s) < 1`` for every finite ``m``. In IEEE754 double precision the
term reaches exactly ``1.0`` once ``m / s`` exceeds **37.4299**, because ``exp(-37.43)`` is small
enough that ``1 - exp(-37.43)`` rounds to one. At `AggregationPolicy`'s scale of 3 that needs a
magnitude of **112.29**; the largest magnitude anywhere in the CERT r3.1 run is **18.768**, whose
term is 0.9980810939098075. So the strict inequality holds throughout this corpus and the
conservative ``<=`` is what the code asserts, which is the right way round: a bound that is loose
by a rounding error cannot overstate the finding.

That is the Sentiel analogue of ADR 0075's instrument. There, the model's own behaviour on
declared-normal data it never saw showed the alert load was the model's, not the plant's. Here, the
ceiling shows whether a missed day was missable at all.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from enum import Enum
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "CCH0959_MALICIOUS_ENTITY_DAYS",
    "CCH0959_STRUCTURALLY_UNALERTABLE_DAYS",
    "CEILING_PRECEDENCE",
    "PART_6B_ALERT_BUDGET",
    "PART_6B_ALERT_THRESHOLD",
    "BaselineShift",
    "DayCeiling",
    "InsiderVisibility",
    "LabelledEventProfile",
    "VisibilityVerdict",
    "baseline_shifts",
    "classify_insider",
    "contribution_curve",
    "day_ceiling",
    "depth_blind_ceiling_notice",
    "features_required",
    "labelled_event_profile",
    "score_ceiling",
]
PART_6B_ALERT_THRESHOLD: Final = 13.700640148454447
"""PART 6B's 48-alert operating-point threshold. Frozen; do not retune (ADR 0032 / 0076)."""

PART_6B_ALERT_BUDGET: Final = 48
"""Alert budget the frozen CERT 6B row was taken at."""
CCH0959_MALICIOUS_ENTITY_DAYS: Final = 42
"""Labelled malicious entity-days for CCH0959 on CERT r3.1 (ADR 0076 JSON)."""

CCH0959_STRUCTURALLY_UNALERTABLE_DAYS: Final = 31
"""CCH0959 days below the depth-blind ceiling (ADR 0076 JSON)."""


def depth_blind_ceiling_notice() -> str:
    """Return the Gate 2 ceiling paragraph for a Sentiel analyst render.

    Numbers are computed (`features_required`, `len(PEER_FEATURES)`) or frozen against the
    ADR 0076 classification JSON.
    """
    from phos.sentiel.featurise import PEER_FEATURES

    required = features_required(PART_6B_ALERT_THRESHOLD)
    n_features = len(PEER_FEATURES)
    return (
        f"This ranking has a known depth-blind ceiling. At the current "
        f"{PART_6B_ALERT_BUDGET}-alert operating point, at least {required} of {n_features} "
        f"features must speak at once for any entity-day to alert — depth of anomaly on fewer "
        f"features cannot reach the cut, whatever the magnitudes. On the labelled CERT r3.1 "
        f"second insider, {CCH0959_STRUCTURALLY_UNALERTABLE_DAYS} of "
        f"{CCH0959_MALICIOUS_ENTITY_DAYS} malicious entity-days were structurally unalertable "
        f"for that reason. This is a diagnosed limitation of the aggregation (ADR 0076), not a "
        f"gap in the data."
    )


CEILING_PRECEDENCE: Final = """\
A malicious day is read in this order, and the first clause that fits decides it:

1. ``n_speaking == 0``           -> EVIDENCE_ABSENT. No feature cleared the emission bar at all.
2. ``n_speaking < threshold``    -> STRUCTURALLY_UNALERTABLE. Features spoke, but too few: the
                                   score is bounded above by the count of speaking features, so
                                   the largest magnitude representable on every one of them still
                                   misses the cut.
3. ``score < threshold``         -> REACHABLE_BUT_SUBTHRESHOLD. Enough features spoke that the day
                                   *could* have alerted; their magnitudes were too small.
4. otherwise                     -> ALERTED.

Clause 2 is the one that matters and is the one no accuracy number would reveal. It separates "this
person was not unusual enough" from "this detector could not have said so however unusual they
were", and those point in opposite directions: the first is answered by evidence, the second only
by changing the aggregation.
"""


class VisibilityVerdict(str, Enum):
    """Why a labelled malicious entity-day did not reach the operator queue.

    ``str``-backed so it serialises readably into a report and a state file.
    """

    ALERTED = "alerted"
    REACHABLE_BUT_SUBTHRESHOLD = "reachable_but_subthreshold"
    STRUCTURALLY_UNALERTABLE = "structurally_unalertable"
    EVIDENCE_ABSENT = "evidence_absent"


def score_ceiling(n_speaking: int) -> float:
    """Return the highest score a window with ``n_speaking`` speaking features can ever reach.

    Exactly ``n_speaking``: ``1 - exp(-m/s) <= 1`` for every finite magnitude ``m`` and positive
    scale ``s``, so the sum of ``k`` such terms is at most ``k``.

    In exact arithmetic the bound is strict and the ceiling is an unreachable supremum. In IEEE754
    it is attainable, because a term saturates to exactly ``1.0`` once ``m / s`` exceeds 37.4299 —
    a magnitude of 112.29 at `AggregationPolicy`'s scale of 3, against a largest observed magnitude
    of 18.768 on CERT r3.1. The module asserts the attainable version, which is the conservative
    one: it can only ever *under*-state how unalertable a day is.
    """
    if n_speaking < 0:
        raise ValueError(f"n_speaking must be non-negative, got {n_speaking}")
    return float(n_speaking)


def features_required(threshold: float) -> int:
    """Return the fewest features that must speak at once for any window to reach ``threshold``.

    Because ``score <= n_speaking``, reaching ``threshold`` needs ``n_speaking >= threshold``, so
    at least ``ceil(threshold)`` features. Stated as its own function because it is the single
    number that makes the finding legible — at PART 6B's operating point of 13.700640148454447 it
    is **14**, and a corpus behaviour that moves fewer than 14 of the 34 features is invisible to
    this detector by construction, whatever the magnitudes.

    ``ceil`` rather than ``floor(threshold) + 1``: the two agree on every non-integer threshold,
    including the one that matters here, and differ on an integer one, where ``ceil`` is correct
    because a term can reach exactly 1.0 in floating point (see `score_ceiling`). The earlier form
    was off by one at an integer threshold and is recorded in ADR 0076 rather than quietly fixed.
    """
    if threshold < 0.0:
        raise ValueError(f"threshold must be non-negative, got {threshold}")
    return math.ceil(threshold)


class DayCeiling(BaseModel):
    """One entity-day, read against the ceiling its own speaking features impose.

    Attributes:
        day: The window's start.
        score: The score the aggregation actually produced.
        n_speaking: How many features cleared the emission bar and contributed a term.
        ceiling: The supremum of the score given ``n_speaking`` — see `score_ceiling`.
        threshold: The alert threshold this day is judged against.
        verdict: Which clause of `CEILING_PRECEDENCE` fits.
        strongest_feature: The feature with the largest magnitude, kept so a reader can see *what*
            the day was saying even when the day could not be heard.
        strongest_magnitude: That feature's magnitude.
    """

    model_config = ConfigDict(frozen=True)

    day: datetime
    score: float = Field(ge=0.0)
    n_speaking: int = Field(ge=0)
    ceiling: float = Field(ge=0.0)
    threshold: float = Field(gt=0.0)
    verdict: VisibilityVerdict
    strongest_feature: str | None = None
    strongest_magnitude: float | None = None


def day_ceiling(
    day: datetime,
    score: float,
    magnitudes: Mapping[str, float],
    threshold: float,
) -> DayCeiling:
    """Classify one entity-day by `CEILING_PRECEDENCE`.

    Args:
        day: The window's start.
        score: The aggregated score the scorer produced for this window.
        magnitudes: Every feature that spoke, mapped to its magnitude. Its length is the ceiling.
        threshold: The alert threshold — PART 6B's operating point, passed in rather than written
            here so this module holds no copy of a frozen number.

    Returns:
        The classified day.
    """
    n = len(magnitudes)
    ceiling = score_ceiling(n)
    strongest, magnitude = (None, None)
    if magnitudes:
        strongest = max(magnitudes, key=lambda f: (magnitudes[f], f))
        magnitude = magnitudes[strongest]

    if n == 0:
        verdict = VisibilityVerdict.EVIDENCE_ABSENT
    elif ceiling < threshold:
        verdict = VisibilityVerdict.STRUCTURALLY_UNALERTABLE
    elif score < threshold:
        verdict = VisibilityVerdict.REACHABLE_BUT_SUBTHRESHOLD
    else:
        verdict = VisibilityVerdict.ALERTED

    return DayCeiling(
        day=day,
        score=score,
        n_speaking=n,
        ceiling=ceiling,
        threshold=threshold,
        verdict=verdict,
        strongest_feature=strongest,
        strongest_magnitude=magnitude,
    )


class InsiderVisibility(BaseModel):
    """One labelled insider, and why their malicious days did or did not reach the queue.

    Attributes:
        user_id: The corpus's own identifier.
        scenario: The CERT red-team scenario number.
        n_malicious_days: Labelled malicious entity-days in the scored half.
        days: Every one of them, classified.
        best_rank: The best rank any of their malicious days reached in the whole scored queue.
            Kept because it is what settles "outranked": a day that never approaches the budget
            was never in contention, and calling it outranked would overstate how close it came.
        n_scored_days: The size of the queue ``best_rank`` is a rank within.
        own_ordinary_median: Median score of this entity's own *non*-malicious days in the scored
            half, or ``None`` when they have none. The sharpest single comparison available: a
            malicious median at or below it means the detector cannot separate this person's
            attack from this person's ordinary week, independently of any threshold.
        malicious_median: Median score of their malicious days.
    """

    model_config = ConfigDict(frozen=True)

    user_id: str
    scenario: str | None
    n_malicious_days: int = Field(ge=0)
    days: tuple[DayCeiling, ...]
    best_rank: int | None = None
    n_scored_days: int | None = None
    own_ordinary_median: float | None = None
    malicious_median: float | None = None

    @property
    def counts(self) -> dict[str, int]:
        """Return how many malicious days fell to each verdict."""
        tally = Counter(d.verdict.value for d in self.days)
        return {v.value: tally.get(v.value, 0) for v in VisibilityVerdict}

    @property
    def separates_from_own_ordinary(self) -> bool | None:
        """Whether this insider's malicious days out-score their own ordinary days at the median.

        ``None`` when they have no ordinary days to compare against, which is a refusal rather
        than a False: an entity present only while malicious cannot answer the question.
        """
        if self.own_ordinary_median is None or self.malicious_median is None:
            return None
        return self.malicious_median > self.own_ordinary_median


def classify_insider(
    user_id: str,
    scenario: str | None,
    malicious: Sequence[tuple[datetime, float, Mapping[str, float]]],
    threshold: float,
    *,
    best_rank: int | None = None,
    n_scored_days: int | None = None,
    ordinary_scores: Sequence[float] = (),
) -> InsiderVisibility:
    """Classify every malicious day of one insider.

    Args:
        user_id: The insider.
        scenario: Their CERT scenario number.
        malicious: One ``(day, score, magnitudes)`` triple per labelled malicious entity-day.
        threshold: The alert threshold.
        best_rank: Best rank any malicious day reached in the whole queue, if known.
        n_scored_days: Size of that queue, if known.
        ordinary_scores: Scores of this entity's own non-malicious days in the scored half.

    Returns:
        The insider's visibility record.
    """
    days = tuple(day_ceiling(d, s, m, threshold) for d, s, m in malicious)
    return InsiderVisibility(
        user_id=user_id,
        scenario=scenario,
        n_malicious_days=len(days),
        days=days,
        best_rank=best_rank,
        n_scored_days=n_scored_days,
        own_ordinary_median=_median([*ordinary_scores]) if ordinary_scores else None,
        malicious_median=_median([d.score for d in days]) if days else None,
    )


# ------------------------------------------------------------------------------------------------
# What a person's malicious days did to each feature, against their own attack-free history
# ------------------------------------------------------------------------------------------------


class BaselineShift(BaseModel):
    """One feature, measured on a person's malicious days against their own pre-attack days.

    The comparison uses a **fixed** pre-attack baseline — every day of theirs before the corpus's
    first labelled attack — rather than the trailing window the ``_dev`` family uses. That is
    deliberate and it is the generous choice: a trailing baseline chases a slow escalation and
    would flatter the finding. If a behaviour does not separate against a fixed baseline drawn from
    months of the same person's own history, no baseline over that person's history separates it.

    Attributes:
        feature: The feature.
        pre_mean: Mean over the person's pre-attack days.
        pre_stddev: Population standard deviation over those days.
        malicious_mean: Mean over their labelled malicious days.
        shift_z: ``(malicious_mean - pre_mean) / pre_stddev``, or ``None`` when the pre-attack days
            carry no spread at all — which is not zero and must not be reported as zero.
        ratio: ``malicious_mean / pre_mean``, or ``None`` when the pre-attack mean is zero. Kept
            beside ``shift_z`` because the plain ratio is what makes an onset legible: a person who
            went from 0.016 removable-device connections a day to 0.727 is doing something new, and
            a z-score alone does not say that.
    """

    model_config = ConfigDict(frozen=True)

    feature: str
    pre_mean: float
    pre_stddev: float = Field(ge=0.0)
    malicious_mean: float
    shift_z: float | None = None
    ratio: float | None = None


def baseline_shifts(
    pre_attack: Sequence[Mapping[str, float]],
    malicious: Sequence[Mapping[str, float]],
    features: Sequence[str],
) -> tuple[BaselineShift, ...]:
    """Measure every feature's shift from a person's own pre-attack days to their malicious ones.

    Args:
        pre_attack: One mapping per pre-attack day, feature to value. A feature absent from a day's
            mapping is read as 0.0, which is what the featuriser's own emission means.
        malicious: One mapping per labelled malicious day.
        features: The feature set, in emission order, so the output order is the corpus's and not
            a sort by the very quantity being reported.

    Returns:
        One `BaselineShift` per feature, in ``features`` order.
    """
    shifts: list[BaselineShift] = []
    for feature in features:
        before = [day.get(feature, 0.0) for day in pre_attack]
        after = [day.get(feature, 0.0) for day in malicious]
        if not before or not after:
            continue
        pre_mean = sum(before) / len(before)
        pre_var = sum((v - pre_mean) ** 2 for v in before) / len(before)
        pre_sd = math.sqrt(pre_var)
        mal_mean = sum(after) / len(after)
        shifts.append(
            BaselineShift(
                feature=feature,
                pre_mean=pre_mean,
                pre_stddev=pre_sd,
                malicious_mean=mal_mean,
                shift_z=((mal_mean - pre_mean) / pre_sd) if pre_sd > 0.0 else None,
                ratio=(mal_mean / pre_mean) if pre_mean != 0.0 else None,
            )
        )
    return tuple(shifts)


# ------------------------------------------------------------------------------------------------
# What the ground truth actually contains, so "the corpus does not have it" can be checked
# ------------------------------------------------------------------------------------------------


class LabelledEventProfile(BaseModel):
    """One insider's labelled malicious activity, counted from the corpus's own answer file.

    U2 must decide whether r3.1 contains the evidence at all, and that cannot be answered from the
    engine's own output: an engine that discards a channel reports nothing about it either way. So
    the ground truth is counted directly, in the units the corpus states it in.

    Attributes:
        user_id: The insider.
        n_events: Labelled malicious events.
        kinds: Event kind to count, e.g. ``{"http": 121, "device": 181, "email": 8}``.
        active_days: Distinct calendar days carrying at least one labelled event.
        span_days: Inclusive span from first to last labelled event.
        distinct_targets: Distinct hosts and recipients named across the labelled events. The count
            that matters for scenario 2: a motive stated in ten hostnames is in the corpus whether
            or not any feature can express it.
        top_targets: The most frequent targets with their counts, longest first.
    """

    model_config = ConfigDict(frozen=True)

    user_id: str
    n_events: int = Field(ge=0)
    kinds: dict[str, int]
    active_days: int = Field(ge=0)
    span_days: int = Field(ge=0)
    distinct_targets: int = Field(ge=0)
    top_targets: tuple[tuple[str, int], ...] = ()


def labelled_event_profile(
    user_id: str,
    rows: Iterable[tuple[str, datetime, str | None]],
    *,
    top: int = 12,
) -> LabelledEventProfile:
    """Summarise one insider's labelled events.

    Args:
        user_id: The insider.
        rows: ``(kind, when, target)`` per labelled event. ``target`` is the host or recipient the
            event names, or ``None`` for events that name neither. Passed in already parsed so this
            function holds no knowledge of CERT's file layout and is testable without the corpus.
        top: How many of the most frequent targets to keep.

    Returns:
        The profile. An empty ``rows`` yields zeroes rather than raising: an insider with no
        labelled events is a fact about the corpus, not an error.
    """
    kinds: Counter[str] = Counter()
    targets: Counter[str] = Counter()
    days: set[object] = set()
    stamps: list[datetime] = []
    total = 0
    for kind, when, target in rows:
        total += 1
        kinds[kind] += 1
        days.add(when.date())
        stamps.append(when)
        if target:
            targets[target] += 1
    span = (max(stamps).date() - min(stamps).date()).days + 1 if stamps else 0
    return LabelledEventProfile(
        user_id=user_id,
        n_events=total,
        kinds=dict(kinds),
        active_days=len(days),
        span_days=span,
        distinct_targets=len(targets),
        top_targets=tuple(targets.most_common(top)),
    )


def contribution_curve(
    magnitudes: Sequence[float], score_scale: float
) -> tuple[tuple[float, float], ...]:
    """Return ``(magnitude, contribution)`` pairs, so the flattening is in the record as data.

    The claim that the aggregation cannot be reached by depth rests on how quickly this curve
    saturates, and a reader should be able to see it rather than take it on trust.
    """
    return tuple((magnitude, 1.0 - math.exp(-magnitude / score_scale)) for magnitude in magnitudes)


def _median(values: list[float]) -> float | None:
    """Return the median, or ``None`` for an empty sequence."""
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0

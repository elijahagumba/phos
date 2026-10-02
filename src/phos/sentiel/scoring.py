"""One score per entity-window: the shape a wide feature set needs to be usable at all.

PART 6A measured the problem this module fixes, and measured it precisely enough to name the cause.
Twenty-six features scored one-alert-per-feature-per-window gave 3.58x the alerts of eight features
for 2.78x the true positives, and — worse — left an **irreducible floor of 1,668 alerts containing
no true positive at all**, which no threshold below ``1e6`` could remove. Below about 1,700 alerts
the enriched set was not worse than the starter set, it was unusable, and a real SOC works well
below that.

Two mechanisms produced that floor, and this module answers both.

**One alert per feature per window is the wrong unit.** An analyst triages a *person on a day*, not
a feature on a person on a day, and a feature set three times as wide should not mechanically
produce three times the alerts. `WindowScorer` aggregates every feature's deviation for one
``(entity, window)`` into a single score, so widening the feature set adds evidence to a fixed
number of alerts instead of multiplying the alerts.

**A per-key Gaussian has no scale for a sparse feature.** A ``(user, feature)`` training slice that
never varied gives a standard deviation of zero, `phos.ontology.ExpectedRange.zscore` returns
infinity for any departure, and `phos.models.clamp_magnitude` turns that into a permanent maximum.
The trap is that this reads as *infinitely anomalous* when what it actually means is
**unquantified**: the model knows the value is outside everything training saw and has no units in
which to say by how much. A user who never touched a thumb drive and connects one, and a user who
never touched a thumb drive and connects forty, are indistinguishable — the single most informative
distinction in the corpus, destroyed by the clamp.

The aggregation is a sum of **bounded per-feature contributions**::

    score(entity, window) = sum over candidate deviations of  1 - exp(-magnitude / score_scale)

Four properties, none of them chosen by looking at the answer:

- **No single feature can dominate.** Each term lies in ``[0, 1]``, so one clamped feature adds at
  most 1.0 out of a possible ``len(features)``. This is structural, not a threshold that happened
  to work: the bound holds for every input, including an infinite magnitude.
- **Monotone** in every magnitude and in the number of features that fired, so more evidence is
  never less score.
- **Order-independent**, because addition commutes — which matters because the contributions are
  stored as a set, not a sequence.
- **It is the shape PHOS already accumulates evidence in.** PART 4B's `update_confidence` adds
  ``EVIDENCE_STRENGTH x weight`` per piece of evidence in log-odds, bounded per item, additive and
  order-independent (ADR 0008). This score is that same sum one layer down, in units of "features'
  worth of evidence"; multiplying it by ``EVIDENCE_STRENGTH`` would give the log-odds 6C's
  reasoning layer will accumulate. Nothing here imports `phos.reasoning` — the wiring is 6C — but
  the shape is deliberately the one already in the system rather than a new invention.

The squash itself is `phos.models.uncalibrated_confidence` with its existing default scale of 3.0,
reused rather than re-derived, and it carries that function's warning: **this is not a calibrated
probability and nothing may show it to a user as one** (Constitution §3.3).

**What happens to a clamped feature, stated rather than hidden.** It is not dropped. When the
entity's own baseline has no spread, the scorer keeps that entity's own centre and **borrows the
population's spread** from `phos.models.FittedModel.feature_ranges` — the same feature-level
fallback the model already uses for a key training never saw, applied to a missing *scale* instead
of a missing *key*. The thumb-drive user who connects one device now scores under a standard
deviation and the one who connects forty saturates, which is the distinction the clamp destroyed.
Where the population has no spread either — a feature constant across every entity in training —
there is genuinely no scale anywhere, and the contribution stays saturated at its 1.0 ceiling and
is **counted** in `ScoringSummary.unquantified` so a report can say how much of its score came from
departures it could not measure.
"""

import logging
import math
from collections.abc import Iterable, Iterator
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from phos.eval.datasets import Dataset
from phos.eval.detectors import Detection
from phos.models.base import (
    MAX_MAGNITUDE,
    FittedModel,
    StaticRangeFittedModel,
    clamp_magnitude,
)
from phos.models.detector import uncalibrated_confidence
from phos.ontology import Deviation, EntityId, ExpectedRange, Observation, UtcDatetime
from phos.sentiel.featurise import (
    BASELINE_RELATIVE_SUFFIX,
    DIFFERENCE_SUFFIX,
    PEER_RELATIVE_SUFFIX,
    TREND_SUFFIX,
)

__all__ = [
    "AggregatedDetector",
    "AggregationPolicy",
    "FeatureContribution",
    "PrecomputedDetector",
    "ScoredWindow",
    "ScoringSummary",
    "WindowScorer",
    "borrowed_scale_range",
    "precision_policy",
    "static_range_model",
    "stem_of",
]

logger = logging.getLogger(__name__)

_DERIVED_SUFFIXES: tuple[str, ...] = (
    PEER_RELATIVE_SUFFIX,
    BASELINE_RELATIVE_SUFFIX,
    DIFFERENCE_SUFFIX,
    TREND_SUFFIX,
)
"""Longest-first so ``_peer`` is not eaten by a shorter suffix that is not a prefix of it."""


def stem_of(feature: str) -> str:
    """Return the starter count ``feature`` derives from, or ``feature`` itself if it is a count.

    ``logon_count_peer`` and ``logon_count_dev`` are the same behaviour judged against different
    populations; a stem weight named on ``logon_count`` must apply to both, or a volume discount
    would miss the enrichment that actually fires.
    """
    for suffix in _DERIVED_SUFFIXES:
        if feature.endswith(suffix):
            return feature[: -len(suffix)]
    return feature


def static_range_model(fitted: FittedModel) -> StaticRangeFittedModel:
    """Narrow a fitted model to one this scorer may aggregate, refusing one that cannot be.

    `phos.models.PerKeyBehaviouralModel.fit` is declared to return a `FittedModel`, which is the
    right contract for the model layer and too wide for this one: aggregating a window at a time
    requires that each observation be judged independently of the others, which
    `StaticRangeFittedModel` guarantees and an order-dependent model such as EWMA does not. This is
    the one place that requirement is checked, so callers narrow here rather than each asserting it.

    Args:
        fitted: Any fitted model.

    Returns:
        The same object, typed as something the scorer can use.

    Raises:
        TypeError: If the model's expectations move while it scores. A scorer that silently
            restarted an EWMA's state at every window would produce entirely ordinary-looking
            numbers that mean nothing, which is worse than a refusal.
    """
    if not isinstance(fitted, StaticRangeFittedModel):
        raise TypeError(
            f"{type(fitted).__name__} judges observations in sequence, so scoring one "
            "entity-window at a time would restart its state at every window. Aggregated scoring "
            "needs a StaticRangeFittedModel, whose expectations hold still while it scores."
        )
    return fitted


class AggregationPolicy(BaseModel):
    """How per-feature deviations combine into one entity-window score.

    Attributes:
        score_scale: Magnitude at which one feature contributes about 0.63 of its ceiling of 1.0.
            Three by default, which is `phos.models.ModelDetector`'s existing default and puts a
            three-sigma departure there — the conventional Gaussian band, and a number this PART
            inherited rather than chose.
        borrow_population_scale: Whether a feature whose entity-level baseline has no spread is
            re-judged against that entity's own centre and the population's spread. On by default.
            Turning it off restores PART 6A's behaviour — every such departure saturates — and
            exists so a test can reproduce the floor it removes.
        feature_weights: Per-feature multipliers applied after the bounded squash. Missing means
            1.0. Values are in ``(0, 1]``.
        stem_weights: Multipliers named on a starter count and applied to that count *and* its
            ``_dev`` / ``_diff`` / ``_trend`` / ``_peer`` companions. A named `feature_weights`
            entry wins over the stem.
        peer_match_factor: Multiplier applied to every contribution in a window where something
            departed from the person's own past and nothing departed from their peer group.
            1.0 (the default) is a no-op. This is the scoring-level expression of "unlike
            themselves, like their peers → do not lead the queue" — ADR 0023 forbids inventing a
            contradictory template without sanction evidence, so the lever lives here.
        min_out_of_band_families: Fewest distinct behaviour families that must fire before the
            window is scored at full strength. 1 (the default) is a no-op.
        single_family_factor: Multiplier when fewer families fired than `min_out_of_band_families`,
            unless a high-signal stem fired. 1.0 is a no-op.
        high_signal_stems: Starter counts that bypass the peer-match discount and the family gate.
            Empty by default. `precision_policy` names removable-device onset, which is the one
            CERT behaviour that is rare in normal traffic and named in the scenarios as a start.
        chronic_volume_halflife_days: If set, volume-stem contributions on a person who has been
            out-of-band on those stems for consecutive days are multiplied by
            ``0.5 ** ((streak - 1) / halflife)``. ``None`` (the default) is a no-op, so PART 6B
            numbers do not move. This is the scoring-level expression of "a backup week is not
            eight thefts": the first unusual day is unchanged; later copies of the same volume
            pattern decay. High-signal stems are never decayed.
        chronic_volume_stems: Starter counts the chronic discount applies to. Volume, not access.
        log_tag: Optional suffix for detector names in the experiment log, so an opt-in policy
            cannot overwrite a reference row.

    Notes:
        Every factor other than `score_scale` defaults so that `AggregationPolicy()` is the PART
        6B scorer. `precision_policy()` is a declared operating-point choice, not a fit, and the
        factors are unmeasured placeholders (Constitution §3.3).
    """

    model_config = ConfigDict(frozen=True)

    score_scale: float = Field(default=3.0, gt=0.0)
    borrow_population_scale: bool = True
    feature_weights: dict[str, float] = Field(default_factory=dict)
    stem_weights: dict[str, float] = Field(default_factory=dict)
    peer_match_factor: float = Field(default=1.0, gt=0.0, le=1.0)
    min_out_of_band_families: int = Field(default=1, ge=1)
    single_family_factor: float = Field(default=1.0, gt=0.0, le=1.0)
    high_signal_stems: tuple[str, ...] = ()
    chronic_volume_halflife_days: float | None = Field(default=None, gt=0.0)
    chronic_volume_stems: tuple[str, ...] = (
        "file_access_count",
        "distinct_files",
        "distinct_http_hosts",
    )
    log_tag: str = ""

    @field_validator("feature_weights", "stem_weights")
    @classmethod
    def _weights_are_strictly_positive_and_at_most_one(
        cls, value: dict[str, float]
    ) -> dict[str, float]:
        """Refuse a weight that would invert a contribution or break the per-feature ceiling."""
        for name, weight in value.items():
            if not 0.0 < weight <= 1.0:
                raise ValueError(
                    f"weight for {name!r} must be in (0, 1], got {weight}: a zero would drop "
                    "evidence silently and a weight above one would break the per-feature ceiling"
                )
        return value

    def weight_for(self, feature: str) -> float:
        """Return the multiplier for ``feature``, falling back from exact name to stem to 1.0."""
        if feature in self.feature_weights:
            return self.feature_weights[feature]
        stem = stem_of(feature)
        if stem in self.stem_weights:
            return self.stem_weights[stem]
        return 1.0

    def is_high_signal(self, feature: str) -> bool:
        """Return whether ``feature`` is (or derives from) a stem that must not be buried."""
        return stem_of(feature) in self.high_signal_stems

    @property
    def log_suffix(self) -> str:
        """Return ``:{log_tag}`` so a detector name can carry the policy, or empty."""
        return f":{self.log_tag}" if self.log_tag else ""


def precision_policy(*, chronic_volume_halflife_days: float | None = None) -> AggregationPolicy:
    """Return the opt-in policy that discounts volume, off-hours, and self-only departures.

    `AggregationPolicy()` is identity and is what every PART 6B number was scored under. This
    policy is a **declared operating-point choice**, not a fitted calibrator: the factors are
    placeholders chosen so a person who only looks busy, or who matches their peers, ranks below
    a person whose departure spans families or leaves the peer envelope. They are not measured
    discriminating powers and must not be read as calibrated (Constitution §3.3). On CERT r3.1
    at 48 alerts this policy **lost** to identity scoring (ADR 0032); it is not the headline.

    Args:
        chronic_volume_halflife_days: Optional persistence discount on repeated volume
            departures. ``None`` keeps the ADR 0028 policy byte-identical, including the
            ``:precision`` log tag. A positive value adds the discount and retags the detector
            ``:precision-chronic`` so it cannot overwrite the ADR 0028 row.
    """
    tag = "precision" if chronic_volume_halflife_days is None else "precision-chronic"
    return AggregationPolicy(
        stem_weights={
            "file_access_count": 0.25,
            "distinct_files": 0.25,
            "distinct_http_hosts": 0.25,
            "off_hours_logon_count": 0.35,
        },
        peer_match_factor=0.25,
        min_out_of_band_families=2,
        single_family_factor=0.2,
        high_signal_stems=("removable_device_connects",),
        chronic_volume_halflife_days=chronic_volume_halflife_days,
        log_tag=tag,
    )


class FeatureContribution(BaseModel):
    """What one feature contributed to an entity-window's score, and how it was judged.

    Stored so the score is reconstructable from its parts rather than asserted (Constitution §3.2):
    summing `contribution` over a `ScoredWindow`'s list returns its `ScoredWindow.score` exactly.

    Attributes:
        feature: The feature.
        value: The observed value.
        magnitude: The anomaly magnitude the contribution was computed from, **after** any scale
            substitution.
        contribution: ``1 - exp(-magnitude / score_scale)``, in ``[0, 1]``. The bound is open in
            arithmetic and closed in float64, where a clamped magnitude rounds to exactly 1.0 —
            which is the ceiling this whole design rests on, so it is admitted rather than
            validated away.
        scale_borrowed: Whether the entity's own baseline had no spread and the population's was
            used in its place.
        unquantified: Whether neither the entity nor the population offered a spread, so the
            magnitude is the clamped maximum and the contribution is at its ceiling. A departure
            that is real and unmeasurable, counted rather than quietly presented as a measurement.
    """

    model_config = ConfigDict(frozen=True)

    feature: str
    value: float
    magnitude: float = Field(ge=0.0)
    contribution: float = Field(ge=0.0, le=1.0)
    scale_borrowed: bool = False
    unquantified: bool = False


class ScoredWindow(BaseModel):
    """One entity's one window, scored across every feature that produced a candidate deviation.

    Attributes:
        entity_id: The entity the window is about.
        timestamp: The window's start.
        score: Sum of `FeatureContribution.contribution` over `contributions`.
        contributions: Every feature that cleared the model's emission bar, in descending
            contribution order then feature name, so the list is deterministic and the leading
            reason is first.
    """

    model_config = ConfigDict(frozen=True)

    entity_id: EntityId
    timestamp: UtcDatetime
    score: float = Field(ge=0.0)
    contributions: tuple[FeatureContribution, ...] = ()

    @property
    def leading_feature(self) -> str | None:
        """Return the feature that contributed most, or ``None`` if nothing did.

        Recorded on the emitted `Detection` so an alert names something an analyst can open. It is
        the largest single term, **not** the reason for the alert — the score is the sum, and the
        full list is here.
        """
        return self.contributions[0].feature if self.contributions else None

    def as_detection(self, score_scale: float) -> Detection:
        """Return this window as one PART 2 `Detection`.

        Args:
            score_scale: The `AggregationPolicy.score_scale` the score was built with, reused for
                the confidence squash so both live on the same scale.

        Returns:
            A detection whose `phos.eval.Detection.score` is the aggregate. Its ``confidence`` is
            **uncalibrated** — the same warning `phos.models.uncalibrated_confidence` carries.
        """
        return Detection(
            timestamp=self.timestamp,
            score=self.score,
            confidence=uncalibrated_confidence(self.score, score_scale),
            entity_ids=[self.entity_id],
            feature=self.leading_feature,
        )


class ScoringSummary(BaseModel):
    """What a scoring pass did, including the parts it could not measure.

    Attributes:
        windows: Entity-windows scored.
        contributions: Feature contributions that cleared the model's emission bar.
        borrowed: Contributions judged against the population's spread because the entity's own
            baseline had none.
        unquantified: Contributions left at the clamped maximum because no spread existed anywhere.
        unmodelled: Observations skipped because training never saw their feature at all —
            unknown is not anomalous, which is `phos.models.FittedModel.resolve_range`'s rule and
            not a new one.
        total_score: Every window score summed. On its own it says little; between two subsets of
            the **same** stream it is how much evidence a feature family actually contributed, and
            it turns "did the peer features earn their place?" into a measurement rather than an
            impression.
    """

    model_config = ConfigDict(frozen=True)

    windows: int = Field(default=0, ge=0)
    contributions: int = Field(default=0, ge=0)
    borrowed: int = Field(default=0, ge=0)
    unquantified: int = Field(default=0, ge=0)
    unmodelled: int = Field(default=0, ge=0)
    total_score: float = Field(default=0.0, ge=0.0)

    def note(self) -> str:
        """Return the one line a report carries so the unmeasured part is never invisible."""
        return (
            f"AGGREGATED SCORING: {self.windows:,} entity-windows scored from "
            f"{self.contributions:,} feature contributions; {self.borrowed:,} were judged against "
            f"the population's spread because the entity's own baseline had none, "
            f"{self.unquantified:,} stayed at the clamped maximum because no spread existed "
            f"anywhere and are therefore real but UNMEASURED departures, and {self.unmodelled:,} "
            f"observations were skipped because training never saw their feature. Total evidence "
            f"weight accumulated: {self.total_score:,.1f}."
        )


def borrowed_scale_range(own: ExpectedRange, population: ExpectedRange) -> ExpectedRange:
    """Return ``own``'s centre carrying ``population``'s spread.

    The entity's mean is kept because it is the thing the model *did* learn: this user's normal
    level. Only the spread is borrowed, because that is the thing a constant training slice failed
    to supply. The band multiplier is recovered from ``population`` so the substituted range keeps
    the same ``mean +- band_k * stddev`` shape the model builds, rather than inventing one.

    Args:
        own: The entity's own learned range. Its `phos.ontology.ExpectedRange.stddev` is zero.
        population: The feature-level range learned across every entity. Its ``stddev`` must be
            positive; a caller with a degenerate population range has no scale to borrow and must
            not call this.

    Returns:
        A range with ``own``'s feature, entity and mean, ``population``'s spread, and a
        ``learned_from_window`` spanning both, so the stored evidence says what it was built from.

    Raises:
        ValueError: If ``population`` has no spread either.
    """
    if population.stddev <= 0.0:
        raise ValueError(
            f"the feature-level range for {population.feature!r} has no spread either, so there "
            "is no scale to borrow; the caller must treat the departure as unquantified"
        )
    band_k = (population.high - population.mean) / population.stddev
    return ExpectedRange(
        feature=own.feature,
        entity_id=own.entity_id,
        low=own.mean - band_k * population.stddev,
        high=own.mean + band_k * population.stddev,
        mean=own.mean,
        stddev=population.stddev,
        learned_from_window=(
            min(own.learned_from_window[0], population.learned_from_window[0]),
            max(own.learned_from_window[1], population.learned_from_window[1]),
        ),
    )


class WindowScorer:
    """Aggregates a time-ordered observation stream into one score per entity-window.

    Mutable run state, created inside the call that uses it and never shared, so there is no global
    mutable state (Constitution §6). Peak memory is one window's entity buffers, not the corpus,
    which is what lets a corpus far larger than memory be scored in one pass.

    Attributes:
        fitted: The already-fitted model whose deviations are aggregated.
        policy: How the contributions combine.
        features: The features to score, or ``None`` for every feature the stream carries. A subset
            exists so one pass over one corpus can score two feature sets against the **same**
            fitted model — the only way "did the peer features add anything?" can be answered
            without also changing the model, the split and the corpus read.

    Note:
        The model must judge each observation independently of the others, which
        `phos.models.StaticRangeFittedModel` guarantees and an order-dependent model such as EWMA
        does not. That is a type requirement here rather than a docstring note, because a scorer
        that silently restarted an EWMA's state at every window would produce numbers that look
        entirely ordinary and mean nothing.
    """

    __slots__ = (
        "_borrowed",
        "_buffers",
        "_contributions",
        "_previous",
        "_total_score",
        "_unmodelled",
        "_unquantified",
        "_volume_last",
        "_volume_streak",
        "_windows",
        "features",
        "fitted",
        "policy",
    )

    def __init__(
        self,
        fitted: StaticRangeFittedModel,
        policy: AggregationPolicy | None = None,
        features: Iterable[str] | None = None,
    ) -> None:
        """Create an empty scorer.

        Args:
            fitted: The fitted model.
            policy: The aggregation policy. Defaults to `AggregationPolicy`.
            features: Restrict scoring to these features, or ``None`` to score every one.
        """
        self.fitted = fitted
        self.policy = policy or AggregationPolicy()
        self.features = frozenset(features) if features is not None else None
        self._buffers: dict[tuple[EntityId, datetime], list[Observation]] = {}
        self._previous: datetime | None = None
        self._windows = 0
        self._contributions = 0
        self._borrowed = 0
        self._unquantified = 0
        self._unmodelled = 0
        self._total_score = 0.0
        self._volume_streak: dict[EntityId, int] = {}
        self._volume_last: dict[EntityId, datetime] = {}

    def push(self, observation: Observation) -> list[ScoredWindow]:
        """Buffer one observation and return any entity-windows it completed.

        Args:
            observation: The next observation, in non-decreasing timestamp order.

        Returns:
            Every entity-window whose timestamp is now strictly in the past, ordered by timestamp
            then entity id. Usually empty; a whole window's worth when the stream moves on.

        Raises:
            ValueError: If the stream is not time-ordered. A late observation would land in a
                window already scored and reported, and be silently lost.
        """
        if self._previous is not None and observation.timestamp < self._previous:
            raise ValueError(
                f"observations must be time-ordered; {observation.timestamp} follows "
                f"{self._previous}. An entity-window is scored as soon as a later one begins, so "
                "an out-of-order stream would drop evidence into a window already reported."
            )
        completed = self._flush(before=observation.timestamp)
        self._previous = observation.timestamp
        if self.features is None or observation.feature in self.features:
            key = (observation.entity_ids[0], observation.timestamp)
            self._buffers.setdefault(key, []).append(observation)
        return completed

    def close(self) -> list[ScoredWindow]:
        """Return every entity-window still buffered, scored, and empty the scorer."""
        return self._flush(before=None)

    def summary(self) -> ScoringSummary:
        """Return what this scorer has done so far, unmeasured parts included."""
        return ScoringSummary(
            windows=self._windows,
            contributions=self._contributions,
            borrowed=self._borrowed,
            unquantified=self._unquantified,
            unmodelled=self._unmodelled,
            total_score=self._total_score,
        )

    def _flush(self, before: datetime | None) -> list[ScoredWindow]:
        """Score and drop every buffered window starting strictly before ``before``."""
        ready = sorted(key for key in self._buffers if before is None or key[1] < before)
        scored = []
        for key in sorted(ready, key=lambda item: (item[1], item[0])):
            scored.append(self._score(key[0], key[1], self._buffers.pop(key)))
        return scored

    def _score(
        self, entity_id: EntityId, timestamp: datetime, observations: list[Observation]
    ) -> ScoredWindow:
        """Combine one entity-window's observations into a single score."""
        by_id = {observation.id: observation for observation in observations}
        modelled = [
            observation
            for observation in observations
            if self.fitted.resolve_range(observation) is not None
        ]
        self._unmodelled += len(observations) - len(modelled)

        contributions = [
            contribution
            for deviation in self.fitted.score(modelled)
            if (contribution := self._contribution(deviation, by_id[deviation.observation_id]))
            is not None
        ]
        contributions = self._apply_peer_match(contributions, observations)
        contributions = self._apply_family_gate(contributions)
        contributions = self._apply_chronic_volume(entity_id, timestamp, contributions)
        contributions.sort(key=lambda item: (-item.contribution, item.feature))
        self._windows += 1
        self._contributions += len(contributions)
        score = math.fsum(item.contribution for item in contributions)
        self._total_score += score
        return ScoredWindow(
            entity_id=entity_id,
            timestamp=timestamp,
            score=score,
            contributions=tuple(contributions),
        )

    def _contribution(
        self, deviation: Deviation, observation: Observation
    ) -> FeatureContribution | None:
        """Return one feature's bounded contribution, substituting a scale where there is none.

        Returns:
            ``None`` when the re-judged magnitude no longer clears the model's emission bar, which
            happens exactly when a departure that was clamped for want of a scale turns out, once
            given one, to be ordinary. That is the floor being removed, one alert at a time.
        """
        magnitude = deviation.magnitude
        borrowed = False
        unquantified = False
        if magnitude >= MAX_MAGNITUDE:
            population = self.fitted.feature_ranges.get(observation.feature)
            if (
                self.policy.borrow_population_scale
                and population is not None
                and population.stddev > 0.0
            ):
                substitute = borrowed_scale_range(deviation.expected, population)
                magnitude = clamp_magnitude(substitute.zscore(observation.value))
                borrowed = True
            else:
                unquantified = True

        if magnitude < self.fitted.emit_k:
            return None
        if borrowed:
            self._borrowed += 1
        if unquantified:
            self._unquantified += 1
        raw = uncalibrated_confidence(magnitude, self.policy.score_scale)
        return FeatureContribution(
            feature=observation.feature,
            value=observation.value,
            magnitude=magnitude,
            contribution=raw * self.policy.weight_for(observation.feature),
            scale_borrowed=borrowed,
            unquantified=unquantified,
        )

    def _apply_peer_match(
        self,
        contributions: list[FeatureContribution],
        observations: list[Observation],
    ) -> list[FeatureContribution]:
        """Discount a window that left the person's own past but not their peer envelope.

        A user with no peer features at all is not a match: the group was never measured, and
        treating the absence as agreement would bury every ungrouped person. High-signal onset
        (a thumb drive that was never used) is not discounted either — that is rare in normal
        traffic and named in CERT's own scenarios as a start, not as busy-ness.
        """
        if self.policy.peer_match_factor == 1.0 or not contributions:
            return contributions
        peer_observed = any(
            observation.feature.endswith(PEER_RELATIVE_SUFFIX) for observation in observations
        )
        if not peer_observed:
            return contributions
        if any(item.feature.endswith(PEER_RELATIVE_SUFFIX) for item in contributions):
            return contributions
        if any(self.policy.is_high_signal(item.feature) for item in contributions):
            return contributions
        return [_rescaled(item, self.policy.peer_match_factor) for item in contributions]

    def _apply_family_gate(
        self, contributions: list[FeatureContribution]
    ) -> list[FeatureContribution]:
        """Discount a window whose out-of-band evidence sits in a single behaviour family.

        One family is how a backup, a late login, or a busy inbox looks. Two families, or a
        high-signal onset, is how the competing-set's "more than one artefact" bar is expressed
        at scoring time without inventing a contradictory template.
        """
        if (
            self.policy.min_out_of_band_families <= 1 and self.policy.single_family_factor == 1.0
        ) or not contributions:
            return contributions
        from phos.sentiel.templates import family_of

        families = {
            family for item in contributions if (family := family_of(item.feature)) is not None
        }
        if len(families) >= self.policy.min_out_of_band_families:
            return contributions
        if any(self.policy.is_high_signal(item.feature) for item in contributions):
            return contributions
        return [_rescaled(item, self.policy.single_family_factor) for item in contributions]

    def _apply_chronic_volume(
        self,
        entity_id: EntityId,
        timestamp: datetime,
        contributions: list[FeatureContribution],
    ) -> list[FeatureContribution]:
        """Decay repeated volume departures; leave the first unusual day intact.

        A backup that runs every day of a week is one administrative pattern, not seven thefts.
        High-signal stems (thumb-drive onset) are never decayed: rarity, not persistence, is
        what makes them informative. Consecutive means adjacent person-days (gap ≤ 36 hours).
        """
        if self.policy.chronic_volume_halflife_days is None:
            return contributions
        volume_stems = frozenset(self.policy.chronic_volume_stems)
        volume_fired = any(
            stem_of(item.feature) in volume_stems and not self.policy.is_high_signal(item.feature)
            for item in contributions
        )
        if not volume_fired:
            self._volume_streak[entity_id] = 0
            self._volume_last.pop(entity_id, None)
            return contributions

        last = self._volume_last.get(entity_id)
        streak = self._volume_streak.get(entity_id, 0)
        if last is not None and 0.0 < (timestamp - last).total_seconds() <= 36.0 * 3600.0:
            streak += 1
        else:
            streak = 1
        self._volume_streak[entity_id] = streak
        self._volume_last[entity_id] = timestamp
        if streak <= 1:
            return contributions
        factor = 0.5 ** ((streak - 1) / self.policy.chronic_volume_halflife_days)
        return [
            (
                _rescaled(item, factor)
                if stem_of(item.feature) in volume_stems
                and not self.policy.is_high_signal(item.feature)
                else item
            )
            for item in contributions
        ]


def _rescaled(item: FeatureContribution, factor: float) -> FeatureContribution:
    """Return ``item`` with its contribution multiplied by ``factor``, or ``item`` if that is 1."""
    if factor == 1.0:
        return item
    return item.model_copy(update={"contribution": item.contribution * factor})


def stream_scored_windows(
    observations: Iterable[Observation],
    fitted: StaticRangeFittedModel,
    policy: AggregationPolicy | None = None,
    features: Iterable[str] | None = None,
) -> Iterator[ScoredWindow]:
    """Yield one `ScoredWindow` per entity-window as a time-ordered stream completes them.

    Args:
        observations: The feature stream, in non-decreasing timestamp order.
        fitted: The fitted model.
        policy: The aggregation policy.
        features: Restrict scoring to these features, or ``None`` for all.

    Yields:
        Scored windows, ordered by timestamp then entity id.
    """
    scorer = WindowScorer(fitted, policy, features)
    for observation in observations:
        yield from scorer.push(observation)
    yield from scorer.close()


class AggregatedDetector(BaseModel):
    """Runs an aggregated `WindowScorer` as something the entity-aware evaluation can score.

    One `phos.eval.Detection` per entity-window rather than one per feature per window. Everything
    else is unchanged: the same fitted model, the same deviations, the same metric math. Only the
    unit of an alert moves, which is the whole of PART 6B's scoring change.

    Attributes:
        fitted: An already-fitted model. That it is fitted is guaranteed by its type, and that it
            judges observations independently is guaranteed by `StaticRangeFittedModel`.
        policy: How contributions combine.
        features: Score only these features, or ``None`` for all.
    """

    model_config = ConfigDict(frozen=True)

    fitted: StaticRangeFittedModel
    policy: AggregationPolicy = AggregationPolicy()
    features: frozenset[str] | None = None

    @property
    def name(self) -> str:
        """Identifies the detector in reports and the experiment log."""
        return f"aggregate:{self.fitted.name}{self.policy.log_suffix}"

    def run(self, dataset: Dataset) -> list[Detection]:
        """Return one detection per entity-window in ``dataset``.

        Args:
            dataset: The corpus to score. Should be the test half of a split, and must be
                time-ordered — which `phos.eval.Dataset` already requires.

        Returns:
            Detections ordered by timestamp then entity id.
        """
        return [
            window.as_detection(self.policy.score_scale)
            for window in stream_scored_windows(
                dataset.observations, self.fitted, self.policy, self.features
            )
        ]


class PrecomputedDetector(BaseModel):
    """A `phos.eval.Detector` that returns detections computed elsewhere.

    This exists for one reason and states it rather than hiding behind a general name: the real
    corpus does not fit in memory at PART 6B's feature width, so ``scripts`` scores it **as it
    streams** and cannot then hand `phos.sentiel.evaluate_entity_aware` a detector that would
    re-read it. The detections are the ones `AggregatedDetector` would have produced from the same
    stream — a test asserts exactly that — and the evaluation is unchanged.

    Attributes:
        name: The detector name to log, which should be the name of whatever produced them.
        detections: The alert set, in the order it was produced.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    detections: list[Detection] = Field(default_factory=list)

    def run(self, dataset: Dataset) -> list[Detection]:
        """Return the stored detections, ignoring ``dataset``."""
        del dataset
        return list(self.detections)

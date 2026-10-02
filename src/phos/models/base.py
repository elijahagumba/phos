"""The shared behavioural-model machinery: fit/score separation, keying, and honest splits.

PHOS detects by modelling normal and measuring departures from it, so this module defines what a
"behavioural model" *is* before any engine has one. Its three jobs:

- **Fit and score are different types.** `BehaviouralModel.fit` returns a `FittedModel`, and only
  a `FittedModel` can `score`. Scoring before fitting is unrepresentable rather than merely
  discouraged.
- **What a model *is* and how a baseline is *keyed* are separate.** `BehaviouralModel` is the bare
  contract; `PerKeyBehaviouralModel` adds the one-baseline-per-``(entity, feature)`` strategy the
  three shipped baselines share. Atlas's multivariate models (PART 5A) are `BehaviouralModel`s
  that are deliberately *not* per-key — they learn one joint model over every signal at once — so
  the contract has to sit above the strategy rather than inside it.
- **Everything a model emits is an ontology object.** Fitting learns `ExpectedRange`s; scoring
  emits `Deviation`s. There is no private alert format (Constitution §3.1).
- **Evaluation is honest by construction.** `train_test_split` returns an attack-free training
  prefix and a separate test corpus, so a model is never scored on data it learned from and the
  false-positive denominator never counts training hours.

No detection features, no reasoning and no calibration live here; PARTs 4-6 add those on top.
"""

import logging
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from phos.eval.datasets import Dataset, LabelledInterval
from phos.ontology import Deviation, EntityId, ExpectedRange, Observation

__all__ = [
    "FEATURE_LEVEL_ENTITY_ID",
    "MAX_MAGNITUDE",
    "BehaviouralModel",
    "FittedModel",
    "ModelKey",
    "PerKeyBehaviouralModel",
    "SplitPolicy",
    "StaticRangeFittedModel",
    "clamp_magnitude",
    "model_key",
    "train_test_split",
]

logger = logging.getLogger(__name__)

ModelKey = tuple[EntityId, str]
"""``(entity_id, feature)`` — the granularity at which a baseline is learned and looked up."""

FEATURE_LEVEL_ENTITY_ID: Final[EntityId] = "ent_featurelevel"
"""Entity recorded on a feature-level `ExpectedRange`.

Not a real entity. It is a readable sentinel in the ontology's id shape, so a `Deviation` judged
against the cross-entity fallback baseline says so in its own stored evidence rather than
silently claiming to be about one device.
"""

MAX_MAGNITUDE: Final = 1e6
"""Ceiling applied to every anomaly score.

`ExpectedRange.zscore` returns infinity for any departure from a perfectly constant feature, and
PART 1 says explicitly that callers wanting a finite magnitude must clamp it themselves. An
infinite `Deviation.magnitude` would also serialise to JSON ``null`` and fail to round-trip,
which would break traceability (Constitution §3.2).
"""


def model_key(observation: Observation) -> ModelKey:
    """Return the ``(entity_id, feature)`` key a baseline is learned and looked up under.

    Args:
        observation: The measurement to key. Its `entity_ids` is never empty (PART 1).

    Returns:
        The first entity id paired with the feature name.

    Note:
        An observation naming several entities describes a relationship, and this attributes it
        to the first one. That is a deliberate simplification for PART 3: relationship and
        peer-group keying is PART 6's problem, not this module's.
    """
    return (observation.entity_ids[0], observation.feature)


def clamp_magnitude(value: float) -> float:
    """Return ``abs(value)`` bounded above by `MAX_MAGNITUDE`.

    Args:
        value: A raw, possibly infinite, possibly signed anomaly score.

    Returns:
        A finite, non-negative magnitude fit for `Deviation.magnitude`.
    """
    return min(abs(value), MAX_MAGNITUDE)


# ------------------------------------------------------------------------------------------------
# Train/test split
# ------------------------------------------------------------------------------------------------


class SplitPolicy(BaseModel):
    """How a corpus is divided into a training prefix and an evaluation remainder.

    Attributes:
        train_fraction: Largest share of the corpus timeline the training prefix may cover. It is
            a ceiling, not a target: the prefix is cut shorter whenever that is what it takes to
            keep an attack out of training.
    """

    model_config = ConfigDict(frozen=True)

    train_fraction: float = Field(default=0.5, gt=0.0, le=1.0)


def train_test_split(dataset: Dataset, policy: SplitPolicy) -> tuple[Dataset, Dataset]:
    """Split ``dataset`` into an attack-free training prefix and the evaluation remainder.

    The training set is the longest time-ordered prefix that both stays within
    ``policy.train_fraction`` of the timeline and ends strictly before the earliest labelled
    attack. Labelled intervals are inclusive at both ends, so an observation stamped exactly at an
    attack's start is inside the attack and is excluded.

    Both halves come back as full `Dataset` objects so the harness scores only the test window.
    That is what keeps false-positives-per-normal-hour honest: hours the model trained on never
    enter the denominator.

    Args:
        dataset: The labelled corpus to divide.
        policy: The train fraction ceiling.

    Returns:
        ``(train, test)``. ``train`` carries no attack intervals by construction. ``test`` carries
        every interval that intersects its window. Either half may be empty — a corpus whose
        first observation is already under attack yields no training data at all, which is a fact
        about the corpus and is reported rather than worked around.

    Note:
        Pure and deterministic: the same dataset and policy always produce the same split.
    """
    observations = dataset.observations
    if not observations:
        return (
            _derived(dataset, "train", [], [], policy),
            _derived(dataset, "test", [], [], policy),
        )

    start = observations[0].timestamp
    cutoff = start + (observations[-1].timestamp - start) * policy.train_fraction
    first_attack = min((interval.start for interval in dataset.attack_intervals), default=None)

    train_count = 0
    for observation in observations:
        if observation.timestamp > cutoff:
            break
        if first_attack is not None and observation.timestamp >= first_attack:
            break
        train_count += 1

    train_observations = observations[:train_count]
    test_observations = observations[train_count:]
    logger.info(
        "split %s: %d training observations (attack-free), %d test observations",
        dataset.name,
        len(train_observations),
        len(test_observations),
    )
    return (
        _derived(dataset, "train", train_observations, [], policy),
        _derived(
            dataset,
            "test",
            test_observations,
            _intervals_intersecting(dataset.attack_intervals, test_observations),
            policy,
        ),
    )


def _intervals_intersecting(
    intervals: Sequence[LabelledInterval], observations: Sequence[Observation]
) -> list[LabelledInterval]:
    """Return the labelled intervals overlapping the span ``observations`` covers."""
    if not observations:
        return []
    start = observations[0].timestamp
    end = observations[-1].timestamp
    return [interval for interval in intervals if interval.start <= end and interval.end >= start]


def _derived(
    dataset: Dataset,
    part: str,
    observations: Sequence[Observation],
    intervals: Sequence[LabelledInterval],
    policy: SplitPolicy,
) -> Dataset:
    """Build one half of a split, recording the split itself in the provenance note."""
    return Dataset(
        name=f"{dataset.name}-{part}",
        domain=dataset.domain,
        observations=list(observations),
        attack_intervals=list(intervals),
        source_note=(
            f"{dataset.source_note} | {part} half of a train_fraction="
            f"{policy.train_fraction} attack-free-prefix split"
        ),
    )


# ------------------------------------------------------------------------------------------------
# The model interface
# ------------------------------------------------------------------------------------------------


class BehaviouralModel(BaseModel, ABC):
    """An unfitted model of normal behaviour. Learns what normal is; cannot score.

    The whole contract is `fit`: hand it a training corpus, receive something that can score. It
    says nothing about *how* normal is represented, because PHOS has two answers. The three
    baselines shipped in this package learn one range per `(entity_id, feature)` and share that
    machinery through `PerKeyBehaviouralModel`. Atlas's multivariate models learn a single joint
    model spanning every signal at once, and could not be expressed per key at all — modelling the
    plant as a related system is the entire point of them.

    Attributes:
        name: Identifies the model in reports and the experiment log.
        min_samples: Fewest training points a baseline needs before it is learned. What counts as
            a "point" is the subclass's business — one observation of a key, or one fully observed
            timestamp vector — but the meaning is the same: a handful of points is not evidence of
            what normal looks like.
        band_k: Width of the reported normal band, in units each subclass documents.
        emit_k: Emission threshold in the same normalised units as `Deviation.magnitude`. See
            `StaticRangeFittedModel.score` for why the default sits below `band_k`.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    min_samples: int = Field(default=8, ge=1)
    band_k: float = Field(default=3.0, ge=0.0)
    emit_k: float = Field(default=1.0, ge=0.0)

    @abstractmethod
    def fit(self, observations: Sequence[Observation]) -> "FittedModel":
        """Learn normal from ``observations`` and return something that can score.

        Args:
            observations: The training corpus. Should be attack-free — see `train_test_split`.

        Returns:
            A `FittedModel` carrying the learned expectations.
        """


class PerKeyBehaviouralModel(BehaviouralModel, ABC):
    """A `BehaviouralModel` that learns one independent baseline per `(entity_id, feature)`.

    One `ModelKey` gets one `ExpectedRange`, plus one aggregate per feature across every entity,
    which is the fallback when scoring a key that training never saw. Subclasses supply the
    statistics (`_learn`) and the fitted type (`_fitted`); the grouping, ordering and `min_samples`
    policy are shared here so all three baselines agree on them.

    Its defining assumption is that signals are independent — each is judged with no reference to
    any other. That is cheap and interpretable and it is why Gaussian, EWMA and IQR all live here.
    It is also the assumption `phos.atlas` exists to reject for industrial telemetry, where normal
    fluctuation is correlated across the plant and judging one signal in isolation mistakes
    correlated normality for anomaly.
    """

    def fit(self, observations: Sequence[Observation]) -> "FittedModel":
        """Learn one `ExpectedRange` per key, plus one per feature for the fallback level.

        Args:
            observations: The training corpus. Should be attack-free — see `train_test_split`.
                Order does not matter: each group is sorted by timestamp before it is learned
                from, so fitting is deterministic even for the order-sensitive EWMA model.

        Returns:
            A `FittedModel` carrying the learned expectations. Fitting on nothing yields a fitted
            model with no ranges, which then scores nothing.
        """
        by_key: dict[ModelKey, list[Observation]] = {}
        by_feature: dict[str, list[Observation]] = {}
        for observation in observations:
            by_key.setdefault(model_key(observation), []).append(observation)
            by_feature.setdefault(observation.feature, []).append(observation)

        expected_ranges: dict[ModelKey, ExpectedRange] = {}
        for key, group in by_key.items():
            if len(group) < self.min_samples:
                logger.debug(
                    "skipping key %s: %d < min_samples=%d", key, len(group), self.min_samples
                )
                continue
            values, window = _ordered_series(group)
            expected_ranges[key] = self._learn(key[0], key[1], values, window)

        feature_ranges: dict[str, ExpectedRange] = {}
        for feature, group in by_feature.items():
            if len(group) < self.min_samples:
                continue
            values, window = _ordered_series(group)
            feature_ranges[feature] = self._learn(FEATURE_LEVEL_ENTITY_ID, feature, values, window)

        logger.info(
            "fitted %s on %d observations: %d key baselines, %d feature baselines",
            self.name,
            len(observations),
            len(expected_ranges),
            len(feature_ranges),
        )
        return self._fitted(expected_ranges, feature_ranges)

    @abstractmethod
    def _learn(
        self,
        entity_id: EntityId,
        feature: str,
        values: Sequence[float],
        window: tuple[datetime, datetime],
    ) -> ExpectedRange:
        """Return the baseline this model learns from one group's values.

        Args:
            entity_id: The entity the range describes, or `FEATURE_LEVEL_ENTITY_ID`.
            feature: The feature the range describes.
            values: The group's values in timestamp order. Never empty.
            window: The ``(first, last)`` timestamps the values span.
        """

    @abstractmethod
    def _fitted(
        self,
        expected_ranges: Mapping[ModelKey, ExpectedRange],
        feature_ranges: Mapping[str, ExpectedRange],
    ) -> "FittedModel":
        """Wrap the learned ranges in this model's `FittedModel` type."""


def _ordered_series(
    observations: Sequence[Observation],
) -> tuple[list[float], tuple[datetime, datetime]]:
    """Return a group's values in timestamp order and the window they span."""
    ordered = sorted(observations, key=lambda observation: observation.timestamp)
    return (
        [observation.value for observation in ordered],
        (ordered[0].timestamp, ordered[-1].timestamp),
    )


class FittedModel(BaseModel, ABC):
    """A model that has learned what normal looks like and can now judge observations against it.

    Only this type can `score`, which is the whole point of separating it from `BehaviouralModel`.

    Attributes:
        name: Inherited from the model that produced it.
        expected_ranges: The learned baseline per `(entity_id, feature)` key.
        feature_ranges: The learned baseline per feature, aggregated across every entity. This is
            the fallback for a key training never saw.
        emit_k: Magnitude at or above which an observation becomes a candidate `Deviation`.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    expected_ranges: Mapping[ModelKey, ExpectedRange]
    feature_ranges: Mapping[str, ExpectedRange]
    emit_k: float = Field(ge=0.0)

    def resolve_range(self, observation: Observation) -> ExpectedRange | None:
        """Return the baseline to judge ``observation`` against, or ``None`` if there is none.

        Resolution order: the observation's exact `(entity_id, feature)` key, then the
        feature-level baseline aggregated across entities.

        Returns:
            ``None`` when the feature itself was never trained on. The caller must then emit no
            `Deviation`: an unrecognised feature is *unknown*, and unknown is not the same as
            anomalous. Asserting otherwise would manufacture evidence the model does not have.
        """
        key = model_key(observation)
        exact = self.expected_ranges.get(key)
        if exact is not None:
            return exact
        return self.feature_ranges.get(observation.feature)

    @abstractmethod
    def score(self, observations: Sequence[Observation]) -> list[Deviation]:
        """Return a `Deviation` for every observation this model judges to depart from normal."""


class StaticRangeFittedModel(FittedModel, ABC):
    """A `FittedModel` whose expectations hold still while it scores.

    Gaussian and IQR share this: every observation is judged against the same learned range, so
    scoring is order-independent and each observation is scored in isolation. EWMA does not — its
    expectation moves as it goes — so it implements `score` itself.
    """

    def score(self, observations: Sequence[Observation]) -> list[Deviation]:
        """Judge each observation against its learned range, in the order given.

        Args:
            observations: The measurements to score. Need not be the training set, and need not
                be sorted — a static range gives the same answer either way.

        Returns:
            One `Deviation` per observation whose magnitude reached `emit_k`, in input order.

        Note:
            `emit_k` is the emission threshold, and its default (1.0) deliberately sits *below*
            the default `band_k` (3.0) that shapes the reported `ExpectedRange`. A deviation is
            therefore a **candidate**: its `magnitude` is the authority on how far from normal the
            observation was, and the harness's own `alert_threshold` picks the operating point.
            A dense candidate set is what makes the threshold sweep meaningful. Set
            ``emit_k >= band_k`` for the stricter reading, where every emitted `Deviation` also
            falls outside its reported range.

            `Deviation.timestamp` is the observation's timestamp, not wall-clock now: this is an
            offline scorer, and stamping it with the current time would make runs irreproducible.
        """
        deviations: list[Deviation] = []
        for observation in observations:
            expected = self.resolve_range(observation)
            if expected is None:
                continue
            magnitude = self._magnitude(observation.value, expected)
            if magnitude < self.emit_k:
                continue
            deviations.append(
                Deviation(
                    observation_id=observation.id,
                    expected=expected,
                    magnitude=magnitude,
                    timestamp=observation.timestamp,
                )
            )
        return deviations

    @abstractmethod
    def _magnitude(self, value: float, expected: ExpectedRange) -> float:
        """Return this model's normalised, finite, non-negative anomaly score for ``value``."""

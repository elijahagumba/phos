"""The EWMA baseline: normal is what the signal has been doing lately.

An exponentially weighted moving average forgets the past geometrically, so its notion of normal
follows slow drift — a valve that gradually stiffens, a server whose load creeps up with a growing
user base — instead of flagging the drift itself as an incident. That makes it the natural
complement to the Gaussian baseline, which holds one fixed idea of normal forever.

The cost is that scoring is **sequential and order-dependent**: each observation is judged against
the state built from everything scored before it, then folded into that state. Two orderings of the
same observations legitimately produce different deviations, and the tests assert exactly that.
"""

import math
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import NamedTuple

from pydantic import Field

from phos.models.base import (
    FittedModel,
    ModelKey,
    PerKeyBehaviouralModel,
    clamp_magnitude,
    model_key,
)
from phos.ontology import Deviation, EntityId, ExpectedRange, Observation, UtcDatetime

__all__ = ["EwmaBaseline", "EwmaFittedModel", "ewma_update"]


def ewma_update(ema: float, variance: float, value: float, alpha: float) -> tuple[float, float]:
    """Fold one value into an exponentially weighted mean and variance.

    The standard incremental form: the variance update uses the residual against the *previous*
    mean, which is what keeps it non-negative without a correction term.

    Args:
        ema: Current exponentially weighted mean.
        variance: Current exponentially weighted variance. Never negative.
        value: The new observation's value.
        alpha: Smoothing factor in ``(0, 1]``. Larger forgets faster.

    Returns:
        The updated ``(ema, variance)``.
    """
    residual = value - ema
    return (ema + alpha * residual, (1.0 - alpha) * (variance + alpha * residual * residual))


class _LiveState(NamedTuple):
    """One key's moving baseline while scoring is in flight.

    Attributes:
        ema: The exponentially weighted mean as of the last observation folded in.
        variance: The matching exponentially weighted variance.
        window_start: Start of the training window the state was seeded from.
        last_seen: Latest timestamp folded into the state, so the dynamic `ExpectedRange` can
            state truthfully how much data it reflects.
    """

    ema: float
    variance: float
    window_start: UtcDatetime
    last_seen: UtcDatetime


class EwmaBaseline(PerKeyBehaviouralModel):
    """Learns an exponentially weighted mean and variance per key, in timestamp order.

    Attributes:
        name: ``"ewma"``.
        alpha: Smoothing factor. 0.3 weights the most recent point at 30% and decays from there,
            giving an effective memory of a few dozen samples.
        band_k: Half-width of the reported normal band in exponentially weighted standard
            deviations, so ``low, high = ema ± band_k · ew_std``.
        min_samples: Inherited. Fewest points a key needs before a baseline is learned.
        emit_k: Inherited. Magnitude at or above which an observation becomes a candidate
            `Deviation`.
    """

    name: str = "ewma"
    band_k: float = Field(default=3.0, ge=0.0)
    alpha: float = Field(default=0.3, gt=0.0, le=1.0)

    def _learn(
        self,
        entity_id: EntityId,
        feature: str,
        values: Sequence[float],
        window: tuple[datetime, datetime],
    ) -> ExpectedRange:
        """Run the EW recursion over the training values and return the state it ends in.

        The resulting `ExpectedRange` is the whole fitted state: ``mean`` is the final EMA and
        ``stddev`` the final EW standard deviation, which is all `score` needs to carry on from.
        Keeping the fitted state *as an ontology object* rather than in a private struct is
        Constitution §3.1 applied to a model's internals.
        """
        ema = values[0]
        variance = 0.0
        for value in values[1:]:
            ema, variance = ewma_update(ema, variance, value, self.alpha)
        stddev = math.sqrt(variance)
        return ExpectedRange(
            feature=feature,
            entity_id=entity_id,
            low=ema - self.band_k * stddev,
            high=ema + self.band_k * stddev,
            mean=ema,
            stddev=stddev,
            learned_from_window=window,
        )

    def _fitted(
        self,
        expected_ranges: Mapping[ModelKey, ExpectedRange],
        feature_ranges: Mapping[str, ExpectedRange],
    ) -> FittedModel:
        return EwmaFittedModel(
            name=self.name,
            expected_ranges=expected_ranges,
            feature_ranges=feature_ranges,
            emit_k=self.emit_k,
            band_k=self.band_k,
            alpha=self.alpha,
        )


class EwmaFittedModel(FittedModel):
    """A fitted EWMA baseline. Its expectation moves as it scores.

    Attributes:
        band_k: Half-width of the dynamic band in exponentially weighted standard deviations.
        alpha: Smoothing factor, carried over from the model that fitted this one.
    """

    band_k: float = Field(ge=0.0)
    alpha: float = Field(gt=0.0, le=1.0)

    def score(self, observations: Sequence[Observation]) -> list[Deviation]:
        """Judge each observation against the moving baseline, then fold it into that baseline.

        Each key starts from the state `fit` left it in and evolves independently. The
        `ExpectedRange` attached to a `Deviation` is the **dynamic** band as it stood at that
        timestep, captured before the observation was folded in — so the stored evidence says what
        the model actually expected at the moment it was surprised.

        Args:
            observations: The measurements to score, **in the order they should be processed**.
                This is not sorted internally: an EWMA's answer depends on the sequence it sees,
                and silently re-ordering the caller's data would hide that.

        Returns:
            One `Deviation` per observation whose magnitude reached `emit_k`, in input order.

        Note:
            Anomalous values are folded into the state like any other. That is standard EWMA
            behaviour and it means a sustained attack eventually drags the baseline toward itself.
            Freezing the update during a suspected incident is a real technique, but it belongs to
            the OT engine (PART 5), not to a shared baseline.
        """
        state: dict[ModelKey, _LiveState] = {}
        deviations: list[Deviation] = []
        for observation in observations:
            key = model_key(observation)
            current = state.get(key)
            if current is None:
                seed = self.resolve_range(observation)
                if seed is None:
                    continue
                start, end = seed.learned_from_window
                current = _LiveState(
                    ema=seed.mean, variance=seed.stddev**2, window_start=start, last_seen=end
                )

            expected = self._dynamic_range(key, observation.feature, current)
            magnitude = clamp_magnitude(expected.zscore(observation.value))
            if magnitude >= self.emit_k:
                deviations.append(
                    Deviation(
                        observation_id=observation.id,
                        expected=expected,
                        magnitude=magnitude,
                        timestamp=observation.timestamp,
                    )
                )

            ema, variance = ewma_update(
                current.ema, current.variance, observation.value, self.alpha
            )
            state[key] = _LiveState(
                ema=ema,
                variance=variance,
                window_start=current.window_start,
                # Monotonic, so the window can never invert if observations arrive out of order.
                last_seen=max(current.last_seen, observation.timestamp),
            )
        return deviations

    def _dynamic_range(self, key: ModelKey, feature: str, state: _LiveState) -> ExpectedRange:
        """Return the band the moving baseline expects right now.

        Attributed to the observed entity even when the state was seeded from the feature-level
        fallback: once seeded, the state tracks this key's own values and nothing else's.
        """
        stddev = math.sqrt(state.variance)
        return ExpectedRange(
            feature=feature,
            entity_id=key[0],
            low=state.ema - self.band_k * stddev,
            high=state.ema + self.band_k * stddev,
            mean=state.ema,
            stddev=stddev,
            learned_from_window=(state.window_start, state.last_seen),
        )

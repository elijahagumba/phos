"""Measured behaviour: observations, learned expectations, deviations and forecasts.

These are the raw behavioural facts. They carry no interpretation — turning a `Deviation` into
`Evidence` for a `Hypothesis` is the reasoning engine's job (PART 4), not this module's.
"""

import math
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from phos.ontology.enums import Domain
from phos.ontology.ids import (
    DEVIATION_PREFIX,
    FORECAST_PREFIX,
    OBSERVATION_PREFIX,
    DeviationId,
    EntityId,
    ForecastId,
    ObservationId,
    UtcDatetime,
    new_id,
)

__all__ = [
    "Deviation",
    "ExpectedRange",
    "Forecast",
    "ForecastMiss",
    "Observation",
]


class Observation(BaseModel):
    """A single measured behavioural fact at a point in time.

    Attributes:
        id: Stable opaque identifier, ``obs_*``.
        entity_ids: The entities the measurement concerns. At least one; more than one when the
            feature describes a relationship, e.g. traffic between a workstation and a PLC.
        feature: Name of the measured quantity, e.g. ``"interpacket_interval_ms"``.
        value: The measured value.
        timestamp: When it was measured, UTC.
        domain: Which engine produced it.
        context: Free-form string metadata about the measurement, e.g. protocol or port.
    """

    model_config = ConfigDict(frozen=True)

    id: ObservationId = Field(default_factory=lambda: new_id(OBSERVATION_PREFIX))
    entity_ids: list[EntityId] = Field(min_length=1)
    feature: str
    value: float
    timestamp: UtcDatetime
    domain: Domain
    context: dict[str, str] = Field(default_factory=dict)


class ExpectedRange(BaseModel):
    """Learned "normal" for one feature of one entity over a training window.

    This is the baseline a deviation is measured against. It is stored inside the `Deviation` it
    justifies so that the deviation remains explainable even if the model is later retrained —
    an instance of the traceability invariant.

    Attributes:
        feature: The feature this range describes.
        entity_id: The entity it was learned for.
        low: Inclusive lower bound of normal.
        high: Inclusive upper bound of normal.
        mean: Mean of the training window.
        stddev: Standard deviation of the training window; zero for a perfectly constant feature.
        learned_from_window: ``(start, end)`` of the training window, UTC.

    Invariants:
        ``low <= high``, ``stddev >= 0``, and the window is non-inverted.
    """

    model_config = ConfigDict(frozen=True)

    feature: str
    entity_id: EntityId
    low: float
    high: float
    mean: float
    stddev: float = Field(ge=0.0)
    learned_from_window: tuple[UtcDatetime, UtcDatetime]

    @model_validator(mode="after")
    def _check_bounds(self) -> Self:
        if self.low > self.high:
            raise ValueError(f"low ({self.low}) must not exceed high ({self.high})")
        start, end = self.learned_from_window
        if start > end:
            raise ValueError(f"learned_from_window is inverted: {start} > {end}")
        return self

    def contains(self, value: float) -> bool:
        """Return whether ``value`` falls within ``[low, high]`` (bounds inclusive)."""
        return self.low <= value <= self.high

    def zscore(self, value: float) -> float:
        """Return how many standard deviations ``value`` sits from the learned mean.

        For a constant feature (``stddev == 0``) any departure from the mean is infinitely
        surprising, so this returns signed infinity; the mean itself returns ``0.0``. Callers that
        need a finite magnitude should clamp it themselves rather than have this method lie.
        """
        if self.stddev == 0.0:
            if value == self.mean:
                return 0.0
            return math.copysign(math.inf, value - self.mean)
        return (value - self.mean) / self.stddev


class Deviation(BaseModel):
    """An observation that fell outside its expected range, with how far outside it fell.

    Attributes:
        id: Stable opaque identifier, ``dev_*``.
        observation_id: The observation that deviated. The store rejects unknown ids.
        expected: The baseline the observation was judged against, captured at judgement time.
        magnitude: How far outside normal, typically an absolute z-score. Never negative — the
            direction of the departure is recoverable from the observation and ``expected``.
        timestamp: When the deviation was detected, UTC.
    """

    model_config = ConfigDict(frozen=True)

    id: DeviationId = Field(default_factory=lambda: new_id(DEVIATION_PREFIX))
    observation_id: ObservationId
    expected: ExpectedRange
    magnitude: float = Field(ge=0.0)
    timestamp: UtcDatetime


class Forecast(BaseModel):
    """A predicted future value for one feature of one entity over a horizon.

    Attributes:
        id: Stable opaque identifier, ``fc_*``.
        entity_id: The entity the prediction is about.
        feature: The predicted feature.
        predicted_value: The value the model expects over the horizon.
        horizon: ``(start, end)`` of the period the prediction covers, UTC.

    Invariants:
        The horizon is non-inverted.
    """

    model_config = ConfigDict(frozen=True)

    id: ForecastId = Field(default_factory=lambda: new_id(FORECAST_PREFIX))
    entity_id: EntityId
    feature: str
    predicted_value: float
    horizon: tuple[UtcDatetime, UtcDatetime]

    @model_validator(mode="after")
    def _check_horizon(self) -> Self:
        start, end = self.horizon
        if start > end:
            raise ValueError(f"horizon is inverted: {start} > {end}")
        return self


class ForecastMiss(BaseModel):
    """The gap between what a forecast predicted and what actually happened.

    Attributes:
        id: Stable opaque identifier. Shares the ``fc_*`` prefix family with `Forecast`.
        forecast_id: The forecast that missed.
        observed_value: What was actually measured.
        error: Signed difference ``observed - predicted``. Signed deliberately: for predictive
            behavioural models the *direction* of the miss is diagnostic.
        timestamp: When the miss was recorded, UTC.
    """

    model_config = ConfigDict(frozen=True)

    id: ForecastId = Field(default_factory=lambda: new_id(FORECAST_PREFIX))
    forecast_id: ForecastId
    observed_value: float
    error: float
    timestamp: UtcDatetime

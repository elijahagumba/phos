"""The IQR baseline: normal is the middle of the data, and the tails do not get a vote.

Tukey's fence. The quartiles that define it are order statistics, so a handful of extreme values in
the training window barely move them — where the Gaussian baseline's mean and standard deviation
are dragged bodily toward any outlier and quietly widen the band until nothing looks abnormal any
more.

That matters in practice because PHOS trains on captured operational data, and real capture windows
are rarely as clean as their labels claim. When a training set may be contaminated, this is the
baseline to reach for; when it is genuinely clean, the Gaussian one is more sensitive.
"""

from collections.abc import Mapping, Sequence
from datetime import datetime

import numpy
from pydantic import Field

from phos.models.base import (
    MAX_MAGNITUDE,
    FittedModel,
    ModelKey,
    PerKeyBehaviouralModel,
    StaticRangeFittedModel,
    clamp_magnitude,
)
from phos.ontology import EntityId, ExpectedRange

__all__ = ["IqrBaseline", "IqrFittedModel"]


class IqrBaseline(PerKeyBehaviouralModel):
    """Learns Tukey's fence per key; scores by how far beyond the fence a value falls.

    Attributes:
        name: ``"iqr"``.
        band_k: Multiplier on the interquartile range, so
            ``low, high = Q1 - band_k · IQR, Q3 + band_k · IQR``. Note this multiplies the IQR,
            not a standard deviation as it does in the other two baselines. The default of 1.5 is
            Tukey's conventional fence.
        min_samples: Inherited. Fewest points a key needs before a baseline is learned.
        emit_k: Inherited. Magnitude at or above which an observation becomes a candidate
            `Deviation`.
    """

    name: str = "iqr"
    band_k: float = Field(default=1.5, ge=0.0)

    def _learn(
        self,
        entity_id: EntityId,
        feature: str,
        values: Sequence[float],
        window: tuple[datetime, datetime],
    ) -> ExpectedRange:
        """Return Tukey's fence over the group.

        `mean` and `stddev` are still computed and stored, because `ExpectedRange` is one shared
        type and a consumer — a UI axis, a later reasoning step — may want them. They play no part
        in this model's own bounds or scoring, which is the entire point of it.
        """
        first_quartile, third_quartile = (
            float(quantile) for quantile in numpy.quantile(values, [0.25, 0.75])
        )
        spread = third_quartile - first_quartile
        return ExpectedRange(
            feature=feature,
            entity_id=entity_id,
            low=first_quartile - self.band_k * spread,
            high=third_quartile + self.band_k * spread,
            mean=float(numpy.mean(values)),
            stddev=float(numpy.std(values)),
            learned_from_window=window,
        )

    def _fitted(
        self,
        expected_ranges: Mapping[ModelKey, ExpectedRange],
        feature_ranges: Mapping[str, ExpectedRange],
    ) -> FittedModel:
        return IqrFittedModel(
            name=self.name,
            expected_ranges=expected_ranges,
            feature_ranges=feature_ranges,
            emit_k=self.emit_k,
            band_k=self.band_k,
        )


class IqrFittedModel(StaticRangeFittedModel):
    """A fitted IQR baseline. Magnitude is the overshoot beyond the fence, in IQRs.

    Attributes:
        band_k: The fence multiplier, kept so the interquartile range can be recovered from the
            stored bounds.
    """

    band_k: float = Field(ge=0.0)

    def _magnitude(self, value: float, expected: ExpectedRange) -> float:
        """Return ``0`` inside the fence, else the distance beyond it divided by the IQR.

        Unlike the other two baselines this scores everything inside the band as exactly zero
        rather than as a small number: the fence makes no claim about *where* within normal a
        value sits. The practical consequence is a sparse candidate set — the harness's threshold
        sweep sees only genuine overshoots — which is a property of the model, not a defect.
        """
        if expected.contains(value):
            return 0.0
        overshoot = max(expected.low - value, value - expected.high)
        # Inverting low, high = Q1 - k·IQR, Q3 + k·IQR gives high - low = IQR · (1 + 2k).
        spread = (expected.high - expected.low) / (1.0 + 2.0 * self.band_k)
        if spread == 0.0:
            # A perfectly constant training window admits no departure at all, so any value
            # outside it is maximally surprising. Same reasoning as a zero-stddev z-score.
            return MAX_MAGNITUDE
        return clamp_magnitude(overshoot / spread)

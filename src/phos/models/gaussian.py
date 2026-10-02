"""The Gaussian baseline: normal is a mean and a spread, and surprise is a z-score.

The workhorse. It assumes a feature's normal values cluster around one level, which is true of a
great many measurements in both an industrial plant and an enterprise network, and it is cheap and
completely interpretable — every deviation it emits reduces to "this was N standard deviations from
the mean of these training points, over this window".

Its weakness is the flip side of that simplicity: the mean and standard deviation are both
sensitive to outliers in the *training* data, so a contaminated training window quietly widens the
band and hides real departures. `phos.models.iqr` is the robust answer to that, and the two are
compared directly in the tests.
"""

from collections.abc import Mapping, Sequence
from datetime import datetime

import numpy
from pydantic import Field

from phos.models.base import (
    FittedModel,
    ModelKey,
    PerKeyBehaviouralModel,
    StaticRangeFittedModel,
    clamp_magnitude,
)
from phos.ontology import EntityId, ExpectedRange

__all__ = ["GaussianBaseline", "GaussianFittedModel"]


class GaussianBaseline(PerKeyBehaviouralModel):
    """Learns a mean and standard deviation per key; scores by absolute z-score.

    Attributes:
        name: ``"gaussian"``.
        band_k: Half-width of the reported normal band in standard deviations, so
            ``low, high = mean ± band_k · stddev``. The default of 3 is the conventional
            three-sigma band.
        min_samples: Inherited. Fewest points a key needs before a baseline is learned.
        emit_k: Inherited. Magnitude at or above which an observation becomes a candidate
            `Deviation`.
    """

    name: str = "gaussian"
    band_k: float = Field(default=3.0, ge=0.0)

    def _learn(
        self,
        entity_id: EntityId,
        feature: str,
        values: Sequence[float],
        window: tuple[datetime, datetime],
    ) -> ExpectedRange:
        """Return ``mean ± band_k · stddev`` over the group.

        The standard deviation is the population one (``ddof=0``), matching PART 2's fixture
        detector so that a z-score means the same thing everywhere in PHOS.
        """
        mean = float(numpy.mean(values))
        stddev = float(numpy.std(values))
        return ExpectedRange(
            feature=feature,
            entity_id=entity_id,
            low=mean - self.band_k * stddev,
            high=mean + self.band_k * stddev,
            mean=mean,
            stddev=stddev,
            learned_from_window=window,
        )

    def _fitted(
        self,
        expected_ranges: Mapping[ModelKey, ExpectedRange],
        feature_ranges: Mapping[str, ExpectedRange],
    ) -> FittedModel:
        return GaussianFittedModel(
            name=self.name,
            expected_ranges=expected_ranges,
            feature_ranges=feature_ranges,
            emit_k=self.emit_k,
        )


class GaussianFittedModel(StaticRangeFittedModel):
    """A fitted Gaussian baseline. Magnitude is the absolute z-score of the observed value."""

    def _magnitude(self, value: float, expected: ExpectedRange) -> float:
        """Return ``|value - mean| / stddev``, clamped finite.

        `ExpectedRange.zscore` already handles a perfectly constant feature by returning infinity;
        `clamp_magnitude` turns that into a large finite number so the resulting `Deviation` still
        serialises and round-trips.
        """
        return clamp_magnitude(expected.zscore(value))

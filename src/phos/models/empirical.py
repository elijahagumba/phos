"""The empirical baseline: normal is the observed distribution, not a bell curve.

Command intervals and counts pile up on a few exact values. A Gaussian band is the mean plus or
minus three standard deviations, and that band can exclude a value that occurs often enough to
be ordinary, because the mean and the standard deviation do not know the value is a pile.
`IqrBaseline` is the wrong repair: when a count is nearly always one integer, the quartiles
coincide and Tukey's fence collapses onto that integer, so every other value that occurred in
the fit becomes maximally anomalous.

This model draws the band from the sample at the same one-sided tail a Gaussian ``band_k``
band claims. At the default ``band_k`` of 3 that tail is the standard-normal probability of
exceeding three standard deviations, about 0.00135. The number is inherited from that claim.
It is not searched against a false-alarm count.

Inside the band the magnitude is zero: the quantile makes no claim about where within normal a
value sits. Outside it, the magnitude is the absolute z-score against the same mean and
population standard deviation the Gaussian baseline stores, so a departure still reads as
"this many standard deviations from the training mean". A fit with no spread (``stddev == 0``)
makes any departure the maximum finite magnitude, the same clamp a zero-stddev z-score uses.
"""

import math
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

__all__ = ["EmpiricalBaseline", "EmpiricalFittedModel", "one_sided_gaussian_tail"]


def one_sided_gaussian_tail(band_k: float) -> float:
    """Return the standard-normal probability of exceeding ``band_k`` standard deviations.

    This is ``0.5 * erfc(band_k / sqrt(2))``. At ``band_k == 3`` it is approximately 0.00135,
    the tail a three-sigma Gaussian band claims on each side. Callers inherit that claim.
    Nothing in this function is fitted to observations.

    Args:
        band_k: Half-width of the nominal Gaussian band, in standard deviations. Never negative.

    Returns:
        A probability in ``(0, 0.5]``. Zero only in the limit of an infinite ``band_k``.
    """
    return 0.5 * math.erfc(band_k / math.sqrt(2.0))


class EmpiricalBaseline(PerKeyBehaviouralModel):
    """Learns an empirical quantile band per key; scores by z-score outside that band.

    Attributes:
        name: ``"empirical"``.
        band_k: Nominal Gaussian half-width whose one-sided tail sets the quantiles. The
            default of 3 asks for the same tail a three-sigma band claims (about 0.00135 each
            side). It does not multiply a standard deviation, and it is not a searched cutoff.
        min_samples: Inherited. Fewest points a key needs before a baseline is learned.
        emit_k: Inherited. Magnitude at or above which an observation becomes a candidate
            `Deviation`. Inside the band the magnitude is zero, so only values outside the
            quantile band can be emitted.
    """

    name: str = "empirical"
    band_k: float = Field(default=3.0, ge=0.0)

    def _learn(
        self,
        entity_id: EntityId,
        feature: str,
        values: Sequence[float],
        window: tuple[datetime, datetime],
    ) -> ExpectedRange:
        """Return the empirical quantile band at the inherited Gaussian tail.

        The quantiles use ``inverted_cdf``: the empirical quantile function, discontinuous,
        with no interpolation between order statistics. A pile that is thicker than the tail
        therefore lands on the pile itself. ``mean`` and ``stddev`` are the population moments
        (``ddof=0``), stored because a departure outside the band is still reported as a
        z-score, and because `ExpectedRange` is one shared type.
        """
        tail = one_sided_gaussian_tail(self.band_k)
        low, high = (
            float(quantile)
            for quantile in numpy.quantile(values, [tail, 1.0 - tail], method="inverted_cdf")
        )
        return ExpectedRange(
            feature=feature,
            entity_id=entity_id,
            low=low,
            high=high,
            mean=float(numpy.mean(values)),
            stddev=float(numpy.std(values)),
            learned_from_window=window,
        )

    def _fitted(
        self,
        expected_ranges: Mapping[ModelKey, ExpectedRange],
        feature_ranges: Mapping[str, ExpectedRange],
    ) -> FittedModel:
        return EmpiricalFittedModel(
            name=self.name,
            expected_ranges=expected_ranges,
            feature_ranges=feature_ranges,
            emit_k=self.emit_k,
        )


class EmpiricalFittedModel(StaticRangeFittedModel):
    """A fitted empirical baseline. Inside the band the score is zero; outside it is a z-score."""

    def _magnitude(self, value: float, expected: ExpectedRange) -> float:
        """Return ``0`` inside the quantile band, else the absolute z-score.

        A fit with no spread admits no departure at all, so any value outside it is maximally
        surprising. `ExpectedRange.zscore` already returns infinity in that case;
        `clamp_magnitude` turns it into `MAX_MAGNITUDE` so the `Deviation` still serialises.
        """
        if expected.contains(value):
            return 0.0
        if expected.stddev == 0.0:
            return MAX_MAGNITUDE
        return clamp_magnitude(expected.zscore(value))

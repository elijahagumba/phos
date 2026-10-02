"""What the harness scores: the detection record and the detector contract.

The :class:`Detector` protocol is deliberately the smallest thing the harness can measure — a
name and ``run(dataset) -> list[Detection]``. Keeping it this narrow is what lets PART 3's
behavioural models, and later the Atlas and Sentiel engines, be scored by this harness without
the harness ever changing.

:class:`Detection` is not an ontology object. It is the raw output of a detector at evaluation
time; turning detections into `Deviation` and `Evidence` is a later PART's job.
"""

import logging
from typing import Protocol, runtime_checkable

import numpy
from pydantic import BaseModel, ConfigDict, Field

from phos.eval.datasets import Dataset
from phos.ontology import EntityId, UtcDatetime

__all__ = ["Detection", "Detector", "ThresholdDetector"]

logger = logging.getLogger(__name__)


class Detection(BaseModel):
    """One detector output at one instant.

    Attributes:
        timestamp: When the flagged behaviour occurred, UTC.
        score: Raw anomaly score; higher means more anomalous. Unbounded and detector-specific,
            which is why the harness thresholds and sweeps it rather than comparing it across
            detectors.
        confidence: The detector's probability that this is genuinely an attack. Bounded to
            ``[0, 1]`` so it can be scored for calibration, but **not** calibrated by anything
            in this PART — fitting calibrators is PART 4. Until then, treat it as a normalised
            score, and never surface it to a user (Constitution §3.3).
        entity_ids: Entities the detection concerns.
        feature: The feature that triggered it, when the detector knows.
    """

    model_config = ConfigDict(frozen=True)

    timestamp: UtcDatetime
    score: float
    confidence: float = Field(ge=0.0, le=1.0)
    entity_ids: list[EntityId] = Field(default_factory=list)
    feature: str | None = None


@runtime_checkable
class Detector(Protocol):
    """Anything the harness can score."""

    @property
    def name(self) -> str:
        """Identifies the detector in the report and the experiment log.

        Read-only, so a detector may expose it as a plain attribute, a property, or a field on a
        frozen model — the harness only ever reads it.
        """
        ...

    def run(self, dataset: Dataset) -> list[Detection]:
        """Return detections for every observation the detector wishes to score."""
        ...


class ThresholdDetector(BaseModel):
    """Harness test fixture. **Not** a PHOS detection model.

    This exists solely so the harness has something real to score, making the harness's own
    tests end-to-end. It is a signature-free but entirely un-behavioural baseline: it looks at
    one value at a time and has no model of normal beyond a mean and a standard deviation
    computed over the whole corpus, including the attacks. Nothing in PHOS should import it
    outside tests, and no result it produces means anything about detection quality.

    Scores are computed **per feature**, so a wide-ranging feature cannot swamp a quiet one.

    Attributes:
        threshold: Emit a detection when its score is at least this. The default of ``0.0``
            emits one detection per observation in z-score mode, giving the harness the full
            score distribution its threshold sweep needs.
        use_zscore: Score by absolute z-score against the corpus mean, rather than the raw value.
        name: Identifies the detector in reports.
    """

    model_config = ConfigDict(frozen=True)

    threshold: float = 0.0
    use_zscore: bool = True
    name: str = "threshold-detector"

    def run(self, dataset: Dataset) -> list[Detection]:
        """Score every observation and return those at or above `threshold`, in time order."""
        statistics = self._feature_statistics(dataset) if self.use_zscore else {}

        detections: list[Detection] = []
        for observation in dataset.observations:
            if self.use_zscore:
                mean, stddev = statistics[observation.feature]
                # A perfectly constant feature has no spread to be surprised by. Every value
                # equals the mean, so nothing is anomalous and the score is zero by definition.
                score = 0.0 if stddev == 0.0 else abs(observation.value - mean) / stddev
            else:
                score = observation.value
            if score < self.threshold:
                continue
            detections.append(
                Detection(
                    timestamp=observation.timestamp,
                    score=score,
                    confidence=_squash(score),
                    entity_ids=list(observation.entity_ids),
                    feature=observation.feature,
                )
            )
        return detections

    @staticmethod
    def _feature_statistics(dataset: Dataset) -> dict[str, tuple[float, float]]:
        """Return ``{feature: (mean, population stddev)}`` over the whole corpus."""
        grouped: dict[str, list[float]] = {}
        for observation in dataset.observations:
            grouped.setdefault(observation.feature, []).append(observation.value)
        return {
            feature: (float(numpy.mean(values)), float(numpy.std(values)))
            for feature, values in grouped.items()
        }


def _squash(score: float) -> float:
    """Map a non-negative score onto ``[0, 1)`` monotonically.

    ``score / (1 + score)`` needs no upper bound on the score and preserves ordering, which is
    all the fixture detector needs. It is emphatically not a calibrated probability; PART 4
    replaces this with a fitted calibrator.
    """
    positive = max(score, 0.0)
    return positive / (1.0 + positive)

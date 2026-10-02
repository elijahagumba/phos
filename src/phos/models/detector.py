"""The adapter that lets the PART 2 harness score a behavioural model.

This is the join between the two halves built so far: a `FittedModel` speaks the ontology and emits
`Deviation`s, the harness speaks `Detection`s and knows nothing about models. `ModelDetector`
translates one into the other and nothing else, which is why the harness never had to change to
measure a real model.

The confidence it puts on each `Detection` is a **raw squash of the anomaly magnitude, not a
calibrated probability**. Constitution §3.3 forbids surfacing an uncalibrated confidence to a user,
and PART 4 replaces this with a fitted calibrator. Until then it exists only so the harness can
*measure* calibration — which is the honest order: measure first, claim later.
"""

import math

from pydantic import BaseModel, ConfigDict, Field

from phos.eval.datasets import Dataset
from phos.eval.detectors import Detection
from phos.models.base import FittedModel

__all__ = ["ModelDetector", "uncalibrated_confidence"]


def uncalibrated_confidence(magnitude: float, score_scale: float) -> float:
    """Squash a non-negative anomaly magnitude onto ``[0, 1]``.

    ``1 - exp(-magnitude / score_scale)`` is monotone, needs no upper bound on the magnitude, and
    saturates gently rather than clipping. Those are the only properties required of it.

    Args:
        magnitude: A `Deviation.magnitude`. Non-negative and finite by construction.
        score_scale: Magnitude mapping to roughly 0.63. Larger makes the squash more conservative.

    Returns:
        A number in ``[0, 1]``.

    Warning:
        This is **not** a probability that an attack occurred, and nothing may present it as one.
        It is a monotone re-expression of the anomaly score. PART 4 fits a real calibrator.
    """
    return 1.0 - math.exp(-magnitude / score_scale)


class ModelDetector(BaseModel):
    """Runs a fitted behavioural model as something `phos.eval.evaluate` can score.

    Deliberately does *not* split, fit, or retrain. The caller splits with
    `phos.models.base.train_test_split`, fits on the training half, and hands the fitted model
    here to be scored against the test half — so a reported number can never come from a model
    that saw the data it was scored on.

    Attributes:
        fitted: An already-fitted model. That it is already fitted is guaranteed by its type.
        score_scale: Magnitude that maps to a confidence of about 0.63. The default of 3 puts a
            three-sigma departure there, matching the conventional Gaussian band.
    """

    model_config = ConfigDict(frozen=True)

    fitted: FittedModel
    score_scale: float = Field(default=3.0, gt=0.0)

    @property
    def name(self) -> str:
        """Identifies the detector in reports and the experiment log."""
        return f"model:{self.fitted.name}"

    def run(self, dataset: Dataset) -> list[Detection]:
        """Score every observation in ``dataset`` and return one `Detection` per `Deviation`.

        Args:
            dataset: The corpus to score. Should be the test half of a split.

        Returns:
            Detections in the order the model emitted its deviations.

        Raises:
            ValueError: If the model returns a deviation for an observation the dataset does not
                contain. That would mean a `Deviation` whose evidence cannot be traced back to a
                measurement, so it is raised rather than dropped (Constitution §3.2).
        """
        by_id = {observation.id: observation for observation in dataset.observations}
        detections: list[Detection] = []
        for deviation in self.fitted.score(dataset.observations):
            observation = by_id.get(deviation.observation_id)
            if observation is None:
                raise ValueError(
                    f"{self.name} produced a deviation for unknown observation "
                    f"{deviation.observation_id!r}, which cannot be traced back to a measurement"
                )
            detections.append(
                Detection(
                    timestamp=observation.timestamp,
                    score=deviation.magnitude,
                    confidence=uncalibrated_confidence(deviation.magnitude, self.score_scale),
                    entity_ids=list(observation.entity_ids),
                    feature=observation.feature,
                )
            )
        return detections

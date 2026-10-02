"""The detector whose confidence is a probability, and the first path where §3.3 holds.

`phos.models.ModelDetector` reports ``1 - exp(-magnitude/scale)`` as its confidence. That number is
monotone in the anomaly score and bounded to ``[0, 1]``, and it is not a probability of anything —
it never saw a label. Constitution §3.3 forbids surfacing it, which until now left PHOS with no
user-facing confidence at all.

`CalibratedModelDetector` is the same scorer with the confidence replaced by a fitted calibrator's
output. Two properties make it a drop-in rather than a fork:

- **`score` is still the raw magnitude.** Only ``confidence`` changes. Every ``alert_threshold`` in
  the experiment log therefore keeps its meaning, and a calibrated run can be compared against the
  uncalibrated baseline on *the same alert set* — which is what makes the before/after ECE
  comparison a reading of one thing rather than of two different things.
- **It satisfies the same PART 2 `Detector` protocol**, so `phos.eval.evaluate` scores it without
  modification.

The calibrator must have been fitted on a **calibration split disjoint from the test split**
(`phos.reasoning.splits`). This class cannot check that — it receives an already-fitted calibrator
and has no way to know what it saw — so the discipline lives in the split and in the script that
uses it.
"""

import logging

import numpy
from pydantic import BaseModel, ConfigDict

from phos.eval.datasets import Dataset
from phos.eval.detectors import Detection
from phos.models.base import FittedModel
from phos.reasoning.calibration import FittedCalibrator

__all__ = ["CalibratedModelDetector"]

logger = logging.getLogger(__name__)

_TOLERANCE = 1e-9
"""Slack allowed on a calibrator's output before it is treated as a contract violation.

Wide enough to absorb a probability that lands a floating-point step outside ``[0, 1]``, narrow
enough that a calibrator genuinely returning something that is not a probability still raises.
"""


class CalibratedModelDetector(BaseModel):
    """Runs a fitted behavioural model with a calibrated probability as its confidence.

    Like `phos.models.ModelDetector`, it deliberately does not split, fit or retrain. The caller
    splits three ways, fits the model on train, fits the calibrator on calib, and hands both here
    to be scored against test — so neither the model nor the calibrator can have seen the data the
    reported numbers come from.

    Attributes:
        fitted: An already-fitted behavioural model. That it is fitted is guaranteed by its type.
        calibrator: An already-fitted calibrator, fitted on a **held-out calibration split**.

    Note:
        ``calibrator`` is typed as a `Protocol`, which is a structural contract: it guarantees a
        ``calibrate`` method exists, not that the method returns probabilities. `run` therefore
        checks the range of what comes back rather than trusting it.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    fitted: FittedModel
    calibrator: FittedCalibrator

    @property
    def name(self) -> str:
        """Identifies the detector in reports and the experiment log.

        Carries both halves — ``model:gaussian+isotonic`` — because the calibrator is part of what
        was measured, and a log that recorded only the model could not distinguish a calibrated run
        from the uncalibrated baseline it is meant to beat.
        """
        return f"model:{self.fitted.name}+{self.calibrator.name}"

    def run(self, dataset: Dataset) -> list[Detection]:
        """Score every observation, reporting the calibrated probability as the confidence.

        Args:
            dataset: The corpus to score. Should be the test slice of a three-way split.

        Returns:
            Detections in the order the model emitted its deviations, each carrying the raw
            magnitude as ``score`` and the calibrated probability as ``confidence``.

        Raises:
            ValueError: If the model emits a deviation for an observation the dataset does not
                contain — a detection that cannot be traced back to a measurement (§3.2), refused
                here exactly as `ModelDetector` refuses it. Or if the calibrator returns a value
                outside ``[0, 1]``, which is not a probability and must not reach a user (§3.3).
        """
        by_id = {observation.id: observation for observation in dataset.observations}
        deviations = self.fitted.score(dataset.observations)
        if not deviations:
            return []

        observations = []
        for deviation in deviations:
            observation = by_id.get(deviation.observation_id)
            if observation is None:
                raise ValueError(
                    f"{self.name} produced a deviation for unknown observation "
                    f"{deviation.observation_id!r}, which cannot be traced back to a measurement"
                )
            observations.append(observation)

        magnitudes = numpy.asarray([deviation.magnitude for deviation in deviations], dtype=float)
        confidences = self._calibrated(magnitudes)

        detections = [
            Detection(
                timestamp=observation.timestamp,
                score=deviation.magnitude,
                confidence=confidence,
                entity_ids=list(observation.entity_ids),
                feature=observation.feature,
            )
            for deviation, observation, confidence in zip(
                deviations, observations, confidences, strict=True
            )
        ]
        logger.info(
            "%s scored %s: %d detections, calibrated confidence in [%.4f, %.4f]",
            self.name,
            dataset.name,
            len(detections),
            min(confidences),
            max(confidences),
        )
        return detections

    def _calibrated(self, magnitudes: numpy.typing.NDArray[numpy.float64]) -> list[float]:
        """Calibrate a batch of magnitudes, refusing anything that is not a probability.

        Batched deliberately: one call for the whole corpus rather than one per detection, which on
        a 180,000-observation corpus is the difference between a vectorised interpolation and tens
        of thousands of Python-level calls.

        Raises:
            ValueError: If any calibrated value falls outside ``[0, 1]`` by more than `_TOLERANCE`.
        """
        calibrated = numpy.asarray(self.calibrator.calibrate(magnitudes), dtype=float)

        if calibrated.shape != magnitudes.shape:
            raise ValueError(
                f"calibrator {self.calibrator.name!r} returned {calibrated.shape} probabilities "
                f"for {magnitudes.shape} scores"
            )
        lowest = float(numpy.min(calibrated))
        highest = float(numpy.max(calibrated))
        if lowest < -_TOLERANCE or highest > 1.0 + _TOLERANCE:
            raise ValueError(
                f"calibrator {self.calibrator.name!r} returned values outside [0, 1] "
                f"(min {lowest}, max {highest}); a calibrated confidence must be a probability"
            )
        # Only floating-point slack survives the check above, so clipping cannot mask a real fault.
        return [float(value) for value in numpy.clip(calibrated, 0.0, 1.0)]

"""Turning an anomaly score into a probability that means what it says.

Constitution §3.3 forbids surfacing an uncalibrated confidence, and until now PHOS has had nothing
else. `phos.models.uncalibrated_confidence` squashes a magnitude through ``1 - exp(-m/scale)``,
which is monotone and bounded and *nothing more* — it never consulted a single label, so it has no
grounds to claim that 0.63 means "right about 63% of the time". Measured against real corpora it
plainly does not: the expected calibration error of that path is 0.33 on BATADAL and 0.65 on HAI.

A calibrator is fitted on ``(score, label)`` pairs and learns the mapping that was missing. Two
labelled calibrators are provided because they fail differently:

- `PlattCalibrator` — a logistic regression of label on score. Two parameters, smooth, monotone,
  and content with very little data. It can only express a sigmoid, so it is badly wrong whenever
  the true relationship is not one.
- `IsotonicCalibrator` — a non-parametric fit under a monotonicity constraint. It can express any
  non-decreasing shape, which is usually what an anomaly score's relationship to attack
  probability actually looks like, at the price of needing more data and of being a step function
  between the points it saw.

**ADR 0083 adds a third path that needs no labelled positives.** `NormalScoreCalibrator` fits the
empirical CDF of attack-free magnitudes alone. The weight is extremity under ordinary scores, not
P(attack | score) — see `NORMAL_SCORE_WEIGHT_CAVEAT`. That is what lets the Atlas vertical fit on a
declared-normal corpus without carving the labelled file down to feed isotonic.

**Which one wins is an empirical question, and it is not the same answer everywhere.** On BATADAL
isotonic roughly halves the calibration error while Platt makes it *worse* than doing nothing;
on HAI both are transformative. `scripts/calibrate_corpora.py` measures it rather than assuming
it, which is the only defensible way to choose (Constitution §3.5).

**A fitted calibrator is stored parameters, not a live estimator.** Both fitted types are frozen
Pydantic models holding plain floats, so a calibrated confidence can be reproduced from the record
instead of by re-running a fit — Constitution §3.7 — and so a calibrator can travel through the
API to the UI in PARTs 8-10 without pickling anything. sklearn is used to *fit*; it is not used to
predict, and no sklearn object outlives a fit call.

Fitting happens on a **held-out calibration split** (`phos.reasoning.splits`), never on the test
split. Fitting and measuring on the same data would manufacture the improvement this layer exists
to demonstrate.
"""

import logging
from collections.abc import Sequence
from typing import Final, Protocol, runtime_checkable

import numpy
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, Field

from phos.eval.datasets import Dataset
from phos.models.base import FittedModel

__all__ = [
    "NORMAL_SCORE_WEIGHT_CAVEAT",
    "Calibrator",
    "FittedCalibrator",
    "FittedIsotonicCalibrator",
    "FittedNormalScoreCalibrator",
    "FittedPlattCalibrator",
    "IsotonicCalibrator",
    "NormalScoreCalibrator",
    "PlattCalibrator",
    "calibrated_probabilities",
    "normal_scores_from",
    "scores_and_labels_from",
]

NORMAL_SCORE_WEIGHT_CAVEAT: Final = (
    "Normal-score CDF weights are not attack probabilities: the map is the empirical CDF of "
    "held-out attack-free magnitudes (ADR 0083). A weight of 0.9 means the score sits at or above "
    "about 90% of ordinary scores the model saw on normal data — not that an attack is 90% likely. "
    "Do not quote ECE against attack labels as evidence that these weights are calibrated "
    "probabilities under Constitution §3.3."
)

logger = logging.getLogger(__name__)

_PROBABILITY_TOLERANCE: Final = 1e-9
"""Slack allowed on a calibrator's output before it is treated as a contract violation.

Wide enough to absorb a probability that lands a floating-point step outside ``[0, 1]``, narrow
enough that a calibrator genuinely returning something that is not a probability still raises.
"""

Scores = NDArray[numpy.float64]
"""Raw anomaly scores — `Deviation.magnitude` values, in whatever units the model uses."""

Probabilities = NDArray[numpy.float64]
"""Calibrated probabilities in ``[0, 1]``."""


@runtime_checkable
class FittedCalibrator(Protocol):
    """A learned score-to-probability mapping."""

    @property
    def name(self) -> str:
        """Identifies the calibrator in detector names and the experiment log."""
        ...

    def calibrate(self, scores: Scores) -> Probabilities:
        """Map raw anomaly scores onto calibrated probabilities in ``[0, 1]``."""
        ...


@runtime_checkable
class Calibrator(Protocol):
    """Something that learns a `FittedCalibrator` from labelled scores."""

    def fit(self, scores: Scores, labels: Scores) -> FittedCalibrator:
        """Return a calibrator fitted on ``(score, label)`` pairs."""
        ...


def _validated(scores: Scores, labels: Scores) -> tuple[Scores, Scores]:
    """Return the inputs as clean float arrays, or raise naming exactly what is wrong.

    Every check here guards against a calibrator that would fit successfully and then lie. The
    single-class check is the important one: a logistic regression refuses one class on its own,
    but isotonic regression cheerfully returns a constant function, which is *perfectly calibrated
    and completely uninformative*. It would post an excellent ECE while carrying no signal at all,
    and nothing downstream would notice.

    Raises:
        ValueError: If the arrays are empty, differently sized, non-finite, not 0/1, or hold only
            one class.
    """
    score_array = numpy.asarray(scores, dtype=float).ravel()
    label_array = numpy.asarray(labels, dtype=float).ravel()

    if score_array.size == 0:
        raise ValueError("cannot fit a calibrator: no scores were given")
    if score_array.size != label_array.size:
        raise ValueError(
            f"scores and labels must be the same length, got {score_array.size} and "
            f"{label_array.size}"
        )
    if not numpy.all(numpy.isfinite(score_array)):
        raise ValueError("cannot fit a calibrator: every score must be finite")
    if not numpy.all(numpy.isin(label_array, (0.0, 1.0))):
        raise ValueError("cannot fit a calibrator: every label must be 0 or 1")

    positives = int(label_array.sum())
    if positives == 0 or positives == label_array.size:
        raise ValueError(
            f"cannot fit a calibrator: the calibration data must contain both classes, but "
            f"{positives} of {label_array.size} points are attacks. A single-class fit produces a "
            "constant calibrator, which scores a perfect calibration error while carrying no "
            "information — see phos.reasoning.splits for choosing a calibration slice"
        )
    return score_array, label_array


class FittedPlattCalibrator(BaseModel):
    """A fitted logistic map: ``sigmoid(coefficient · score + intercept)``.

    Attributes:
        name: ``"platt"``.
        coefficient: Slope on the raw score. Non-negative for any sane fit, which is what makes
            the mapping monotone.
        intercept: Offset, setting the score at which the probability passes one half.
    """

    model_config = ConfigDict(frozen=True)

    name: str = "platt"
    coefficient: float
    intercept: float

    def calibrate(self, scores: Scores) -> Probabilities:
        """Return ``sigmoid(coefficient · score + intercept)``, elementwise.

        Computed in the numerically stable direction for each sign so a large negative exponent
        cannot overflow: the naive form overflows ``exp`` for strongly negative logits, which is
        exactly what a very low anomaly score produces.
        """
        logits = self.coefficient * numpy.asarray(scores, dtype=float) + self.intercept
        calibrated: Probabilities = numpy.where(
            logits >= 0.0,
            1.0 / (1.0 + numpy.exp(-numpy.abs(logits))),
            numpy.exp(-numpy.abs(logits)) / (1.0 + numpy.exp(-numpy.abs(logits))),
        )
        return calibrated


class FittedIsotonicCalibrator(BaseModel):
    """A fitted step-free monotone map, stored as the interpolation knots it was fitted to.

    Attributes:
        name: ``"isotonic"``.
        score_thresholds: The fitted knot positions on the score axis, ascending.
        probability_thresholds: The fitted probability at each knot, non-decreasing.

    Invariants:
        The two tuples are the same non-empty length.
    """

    model_config = ConfigDict(frozen=True)

    name: str = "isotonic"
    score_thresholds: tuple[float, ...] = Field(min_length=1)
    probability_thresholds: tuple[float, ...] = Field(min_length=1)

    def calibrate(self, scores: Scores) -> Probabilities:
        """Interpolate linearly between the knots, clamping beyond either end.

        ``numpy.interp`` clamps to the first and last knot outside the fitted range, which is
        exactly what sklearn's ``out_of_bounds="clip"`` does — a test pins the two together. That
        equivalence is what allows this to be a stored value rather than a live estimator.
        """
        calibrated: Probabilities = numpy.interp(
            numpy.asarray(scores, dtype=float),
            numpy.asarray(self.score_thresholds, dtype=float),
            numpy.asarray(self.probability_thresholds, dtype=float),
        )
        return calibrated


class PlattCalibrator(BaseModel):
    """Fits a logistic regression of label on raw score.

    Attributes:
        seed: Recorded on every fit for reproducibility. The solver used here is deterministic, so
            this changes nothing today; it is on the record so a later switch to a stochastic
            solver cannot quietly make runs irreproducible.
    """

    model_config = ConfigDict(frozen=True)

    seed: int = 7

    def fit(self, scores: Scores, labels: Scores) -> FittedPlattCalibrator:
        """Fit the logistic and keep only its two learned parameters.

        Raises:
            ValueError: If the calibration data is degenerate — see `_validated`.
        """
        score_array, label_array = _validated(scores, labels)
        coefficient, intercept = _fit_logistic(score_array, label_array, self.seed)
        logger.info(
            "fitted platt calibrator on %d points (%d attacks): sigmoid(%.4f·score + %.4f)",
            score_array.size,
            int(label_array.sum()),
            coefficient,
            intercept,
        )
        return FittedPlattCalibrator(coefficient=coefficient, intercept=intercept)


class IsotonicCalibrator(BaseModel):
    """Fits a non-decreasing step function of label on raw score.

    Attributes:
        seed: Recorded for reproducibility. Isotonic regression is deterministic; see
            `PlattCalibrator.seed` for why it is carried anyway.
    """

    model_config = ConfigDict(frozen=True)

    seed: int = 7

    def fit(self, scores: Scores, labels: Scores) -> FittedIsotonicCalibrator:
        """Fit the isotonic regression and keep only its interpolation knots.

        Raises:
            ValueError: If the calibration data is degenerate — see `_validated`.
        """
        score_array, label_array = _validated(scores, labels)
        knot_scores, knot_probabilities = _fit_isotonic(score_array, label_array)
        logger.info(
            "fitted isotonic calibrator on %d points (%d attacks): %d knots spanning [%.3f, %.3f]",
            score_array.size,
            int(label_array.sum()),
            len(knot_scores),
            knot_probabilities[0],
            knot_probabilities[-1],
        )
        return FittedIsotonicCalibrator(
            score_thresholds=knot_scores,
            probability_thresholds=knot_probabilities,
        )


class FittedNormalScoreCalibrator(BaseModel):
    """Empirical CDF of attack-free magnitudes, stored as unique scores and their CDF values.

    Attributes:
        name: ``"normal-score-cdf"``.
        score_thresholds: Ascending unique calibration scores.
        weight_thresholds: ``#{normal ≤ knot} / n`` at each unique score (right-continuous CDF).
        n_calibration_scores: How many attack-free magnitudes the CDF was built from.
        weights_are_attack_probabilities: Always ``False``. The weight is extremity under the
            normal score distribution, not P(attack | score). See `NORMAL_SCORE_WEIGHT_CAVEAT`.
    """

    model_config = ConfigDict(frozen=True)

    name: str = "normal-score-cdf"
    score_thresholds: tuple[float, ...] = Field(min_length=1)
    weight_thresholds: tuple[float, ...] = Field(min_length=1)
    n_calibration_scores: int = Field(ge=1)
    weights_are_attack_probabilities: bool = False

    def calibrate(self, scores: Scores) -> Probabilities:
        """Return ``#{calibration scores ≤ m} / n`` for each probe ``m``.

        Exact empirical CDF via searchsorted — not a linear interpolation between knots — so a
        score between two observed normals inherits the CDF of the greatest observed score it
        dominates, matching the definition the unit tests lock.
        """
        probe = numpy.asarray(scores, dtype=float)
        knots = numpy.asarray(self.score_thresholds, dtype=float)
        weights = numpy.asarray(self.weight_thresholds, dtype=float)
        # side='right' - 1 → index of greatest knot ≤ probe; -1 means below all knots.
        indices = numpy.searchsorted(knots, probe, side="right") - 1
        calibrated: Probabilities = numpy.where(indices < 0, 0.0, weights[indices])
        return calibrated


class NormalScoreCalibrator(BaseModel):
    """Fits an empirical CDF on attack-free anomaly scores alone (ADR 0083).

    No labelled positives are required. The fitted map answers "how extreme is this score among
    ordinary scores?", which is enough to weight evidence when the only long history available is
    an unlabelled declared-normal corpus. It does **not** answer "how likely is an attack?".

    Attributes:
        seed: Recorded for reproducibility. The fit is deterministic; the seed is on the record so
            a later stochastic extension cannot quietly break §3.7.
    """

    model_config = ConfigDict(frozen=True)

    seed: int = 7

    def fit(self, scores: Scores) -> FittedNormalScoreCalibrator:
        """Build the empirical CDF of ``scores`` and keep only its knots.

        Args:
            scores: Magnitudes from a **held-out attack-free** calibration slice. Fit and calib
                must be disjoint; see `phos.reasoning.splits.attack_free_fit_calib_split`.

        Raises:
            ValueError: If ``scores`` is empty or any value is non-finite.
        """
        score_array = numpy.asarray(scores, dtype=float).ravel()
        if score_array.size == 0:
            raise ValueError("cannot fit a normal-score calibrator: no scores were given")
        if not numpy.all(numpy.isfinite(score_array)):
            raise ValueError("cannot fit a normal-score calibrator: every score must be finite")

        knot_scores, knot_weights = _empirical_cdf_knots(score_array)
        logger.info(
            "fitted normal-score-cdf calibrator on %d attack-free points: %d knots spanning "
            "[%.3f, %.3f] (weights are not attack probabilities)",
            score_array.size,
            len(knot_scores),
            knot_weights[0],
            knot_weights[-1],
        )
        return FittedNormalScoreCalibrator(
            score_thresholds=knot_scores,
            weight_thresholds=knot_weights,
            n_calibration_scores=int(score_array.size),
        )


def _empirical_cdf_knots(scores: Scores) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """Return ``(unique score, cdf)`` knots for ``weight(m) = #{scores ≤ m} / n``."""
    ordered = numpy.sort(scores)
    n = float(ordered.size)
    unique, counts = numpy.unique(ordered, return_counts=True)
    cumulative = numpy.cumsum(counts) / n
    return (
        tuple(float(value) for value in unique),
        tuple(float(value) for value in cumulative),
    )


def _fit_logistic(scores: Scores, labels: Scores, seed: int) -> tuple[float, float]:
    """Return ``(coefficient, intercept)`` from a logistic regression of ``labels`` on ``scores``.

    sklearn is confined to this function: it is untyped, so nothing it returns is allowed to reach
    a signature or a stored field without passing through ``float`` first.
    """
    from sklearn.linear_model import LogisticRegression

    model = LogisticRegression(random_state=seed).fit(scores.reshape(-1, 1), labels)
    return float(model.coef_[0][0]), float(model.intercept_[0])


def _fit_isotonic(scores: Scores, labels: Scores) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """Return the ``(score, probability)`` knots of an isotonic regression.

    As with `_fit_logistic`, sklearn stops here: the knots come back as plain float tuples.
    """
    from sklearn.isotonic import IsotonicRegression

    model = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0).fit(scores, labels)
    knot_scores = tuple(float(value) for value in model.X_thresholds_)
    knot_probabilities = tuple(float(value) for value in model.y_thresholds_)
    return knot_scores, knot_probabilities


def scores_and_labels_from(fitted: FittedModel, dataset: Dataset) -> tuple[Scores, Scores]:
    """Return the ``(score, label)`` training signal a calibrator is fitted on.

    Runs ``fitted`` over the dataset and pairs each **scored candidate** with the ground truth at
    its instant. Candidates, not out-of-band deviations: the calibrator's job is to map the score
    distribution the harness actually sweeps, and the harness sweeps every candidate. The
    out-of-band boundary applies later, when `phos.reasoning.boundary` promotes a deviation into
    `Evidence`. A candidate in unscored time (``Dataset.unscored_intervals``) is skipped: it is
    neither a positive nor a negative example.

    Args:
        fitted: A model already fitted on the *training* split.
        dataset: The **calibration** split — labelled, and disjoint from both train and test.

    Returns:
        ``(scores, labels)`` as parallel float arrays, one row per candidate, in the order the
        model emitted them. Both are empty when the model emits nothing.

    Raises:
        ValueError: If the model returns a deviation for an observation the dataset does not
            contain, which would be a label that cannot be traced to a measurement
            (Constitution §3.2). `phos.models.ModelDetector` refuses the same thing for the same
            reason.
    """
    by_id = {observation.id: observation for observation in dataset.observations}
    scores: list[float] = []
    labels: list[float] = []
    for deviation in fitted.score(dataset.observations):
        observation = by_id.get(deviation.observation_id)
        if observation is None:
            raise ValueError(
                f"{fitted.name} produced a deviation for unknown observation "
                f"{deviation.observation_id!r}, which cannot be labelled from this dataset"
            )
        is_attack = dataset.is_attack(observation.timestamp)
        if not is_attack and dataset.is_unscored(observation.timestamp):
            # Neither a positive nor a negative example (ADR 0082); it cannot teach the map.
            continue
        scores.append(deviation.magnitude)
        labels.append(float(is_attack))

    logger.info(
        "calibration signal from %s on %s: %d candidates, %d in attack windows",
        fitted.name,
        dataset.name,
        len(scores),
        int(sum(labels)),
    )
    return numpy.asarray(scores, dtype=float), numpy.asarray(labels, dtype=float)


def normal_scores_from(fitted: FittedModel, dataset: Dataset) -> Scores:
    """Return raw magnitudes from ``fitted`` on an attack-free calibration slice (ADR 0083).

    Unlike `scores_and_labels_from`, this path needs no labels: the one-class calibrator learns
    only the distribution of ordinary scores. Unscored intervals are skipped (they are not verified
    normal). Attack intervals are refused — fitting a "normal" CDF on attack magnitudes would
    quietly poison the map.

    Args:
        fitted: A model already fitted on a *disjoint* attack-free training prefix.
        dataset: Held-out attack-free calibration observations.

    Returns:
        One magnitude per scored candidate, in emission order. Empty when the model emits nothing.

    Raises:
        ValueError: If ``dataset`` carries any attack interval, or the model scores an unknown
            observation id.
    """
    if dataset.attack_intervals:
        raise ValueError(
            f"normal_scores_from requires an attack-free calibration slice, but {dataset.name!r} "
            f"carries {len(dataset.attack_intervals)} attack interval(s)"
        )
    by_id = {observation.id: observation for observation in dataset.observations}
    scores: list[float] = []
    for deviation in fitted.score(dataset.observations):
        observation = by_id.get(deviation.observation_id)
        if observation is None:
            raise ValueError(
                f"{fitted.name} produced a deviation for unknown observation "
                f"{deviation.observation_id!r}, which cannot be traced on this dataset"
            )
        if dataset.is_unscored(observation.timestamp):
            continue
        scores.append(deviation.magnitude)

    logger.info(
        "normal-score calibration signal from %s on %s: %d candidates (no labels used)",
        fitted.name,
        dataset.name,
        len(scores),
    )
    return numpy.asarray(scores, dtype=float)


def calibrated_probabilities(calibrator: FittedCalibrator, scores: Sequence[float]) -> list[float]:
    """Calibrate a batch of raw anomaly scores, refusing anything that is not a probability.

    The one place the calibrator's *output* is checked rather than trusted. `FittedCalibrator` is a
    structural `Protocol`: it guarantees a ``calibrate`` method exists, not that the method returns
    probabilities — and an evidence weight or a user-facing confidence that is not a probability
    violates Constitution §3.3. Every caller that turns scores into weights therefore needs this
    guard, so it lives here once instead of being re-derived at each of them.

    Batched deliberately — one call for a whole corpus rather than one per score — which on a
    180,000-observation corpus is the difference between a vectorised interpolation and tens of
    thousands of Python-level calls.

    Args:
        calibrator: An already-fitted calibrator, fitted on a **held-out calibration split**. This
            function cannot check that and does not try; the discipline lives in
            `phos.reasoning.splits` and in the scripts that use it.
        scores: The raw scores to map, in whatever units the model reports. Empty is answered with
            empty *without calling the calibrator*, because an sklearn-fitted map refuses an empty
            batch and "there was nothing to calibrate" is not an error.

    Returns:
        One probability in ``[0, 1]`` per score, in the order given.

    Raises:
        ValueError: If the calibrator returns a differently-shaped result, or any value outside
            ``[0, 1]`` by more than floating-point slack.
    """
    if not scores:
        return []

    requested: Scores = numpy.asarray(scores, dtype=float)
    calibrated = numpy.asarray(calibrator.calibrate(requested), dtype=float)
    if calibrated.shape != requested.shape:
        raise ValueError(
            f"calibrator {calibrator.name!r} returned {calibrated.shape} probabilities for "
            f"{requested.shape} scores"
        )

    lowest = float(numpy.min(calibrated))
    highest = float(numpy.max(calibrated))
    if lowest < -_PROBABILITY_TOLERANCE or highest > 1.0 + _PROBABILITY_TOLERANCE:
        raise ValueError(
            f"calibrator {calibrator.name!r} returned values outside [0, 1] (min {lowest}, max "
            f"{highest}); a calibrated probability is what an evidence weight and a user-facing "
            "confidence are both required to be"
        )
    # Only floating-point slack survives the check above, so clipping cannot mask a real fault.
    return [float(value) for value in numpy.clip(calibrated, 0.0, 1.0)]

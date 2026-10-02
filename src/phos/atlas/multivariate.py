"""Joint models of an industrial plant: normal is a shape, not a set of independent bands.

PART 3's baselines learn one range per signal and judge each reading alone. On a four-signal test
rig that is defensible. On HAI's seventy-nine signals it produced roughly 8,390 false positives per
normal hour, and the cause is structural rather than a bad threshold: when demand rises, *every*
demand-driven signal rises with it, so a per-signal baseline raises one alarm per signal for one
entirely ordinary event, and the alarms compound with the width of the plant.

The signals were never independent. A pump's flow follows a valve's position; a tank's level
follows its inflow and outflow. Normal operation therefore occupies a thin, low-dimensional
manifold inside the space of all possible readings, and the question worth asking about a moment is
not "is this signal high?" but **"does this combination of readings still lie on the manifold?"**.
Two models answer it:

- `PcaResidualModel` (primary) learns the manifold as the linear subspace that carries the bulk of
  normal variance, then projects each moment onto it. A moment that moved *along* the learned
  correlations reconstructs almost exactly and is not flagged; a moment that broke them cannot be
  rebuilt from the subspace, and the part that could not be rebuilt is the anomaly.
- `MahalanobisModel` (alternative) learns the covariance instead and asks, of each signal, what
  every *other* signal implies it should have read. A combination of individually unremarkable
  values that has never co-occurred is far in Mahalanobis distance even though no single reading
  is unusual.

**Neither is allowed to say "something is wrong somewhere."** A joint anomaly score with no
attribution would be a black box, which Constitution §3.2 forbids. Both models therefore emit
ordinary `Deviation`s, one per *signal* that broke, each carrying a **dynamic** `ExpectedRange`:
the value the rest of the plant implied for that signal, plus or minus its learned departure band.
"Given everything else, the outlet flow should have read 140.2 +/- 0.6; it read 100.0" is a
sentence with a defensible number in it.

**The counting unit is the moment, not the instrument.** Per-signal attribution is the right unit
for explaining a departure and the wrong unit for an operator budget: a thermal flicker that
slightly breaks several correlations is one plant-moment, not ten alerts. `MahalanobisModel`
therefore optionally gates emission on the joint Mahalanobis distance ``D_M`` of the moment —
learned as a quantile of attack-free training, and independently per phase under
`PhaseConditionalModel`. `JointMomentDetector` is the same scalar as a PART 2 `Detection`, so the
harness can score an actionable-alert rate without changing the ruler. The default is ungated, so
every number already on the experiment log stays comparable.

**A fitted model is stored parameters, not a live estimator.** Both fitted types are frozen
Pydantic models holding plain floats, so a score can be reproduced from the record rather than by
re-running a fit (Constitution §3.7) and a model can travel through the API in PART 8 without
pickling anything. scikit-learn is used to *fit* the PCA basis and nothing else; no estimator
object outlives `_principal_components`. That is the precedent `phos.reasoning.calibration` set in
PART 4A, followed here deliberately.

**Two signals the models decline to learn.** A signal that never varied across the training window
is dropped from the `SignalSpace`: a constant has no correlation with anything, so it can neither
inform a reconstruction nor be reconstructed from one. A signal absent from training is likewise
outside the space, and scoring simply ignores it. In both cases the model says nothing, because
unknown is not the same as anomalous — but the first case is a real gap, since a signal that was
constant for a week and moves today is interesting, and a joint model structurally cannot notice.
5B and 5C should decide whether a guard belongs beside the joint model; 5A does not close it.
"""

import logging
from abc import ABC, abstractmethod
from collections.abc import Sequence
from datetime import datetime
from enum import StrEnum
from typing import Final

import numpy
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, Field

from phos.atlas.vectorise import (
    NO_OBSERVATION,
    SignalSpace,
    VectorisedSeries,
    VectorisePolicy,
    vectorise,
)
from phos.eval.datasets import Dataset
from phos.eval.detectors import Detection
from phos.models import MAX_MAGNITUDE, BehaviouralModel, FittedModel, ModelKey
from phos.models.detector import uncalibrated_confidence
from phos.ontology import Deviation, EntityId, ExpectedRange, Observation, UtcDatetime

__all__ = [
    "MANIFOLD_BREAK_CONDITIONS",
    "SNAPSHOT_ASSUMPTIONS",
    "JointMomentDetector",
    "MahalanobisFittedModel",
    "MahalanobisModel",
    "MultivariateFittedModel",
    "MultivariateModel",
    "PcaResidualFittedModel",
    "PcaResidualModel",
    "ShrinkageTarget",
]

logger = logging.getLogger(__name__)

Matrix = NDArray[numpy.float64]
"""A ``(n_rows x n_signals)`` block of readings in the units they were measured in."""

Vector = NDArray[numpy.float64]
"""One value per signal, in `SignalSpace` column order."""

SNAPSHOT_ASSUMPTIONS: Final[tuple[str, ...]] = (
    "temporal_independence",
    "linear_feasible_set",
    "constants_dropped",
)
"""What the current joint models actually assume, named so a test can falsify them.

Session C1: a moment is scored without using ``x_{t-1}``; the feasible set is a linear
subspace (PCA) or an ellipsoid (Mahalanobis) in the coordinates the fit used; a signal
that never moved in training is dropped from the space. These are facts about the code,
not a claim that the plant is linear.
"""

MANIFOLD_BREAK_CONDITIONS: Final[tuple[str, ...]] = (
    "nonstationarity_capture_drift",
    "mixed_modes",
    "constant_in_train",
    "shrinkage_floor_mixed_scale",
)
"""Named conditions under which the snapshot manifold assumption is not valid.

- ``nonstationarity_capture_drift``: PCA's in-sample residual band is not the out-of-sample
  band (ADR 0009). Do not "fix" by fitting on the drifted set.
- ``mixed_modes``: pooling recipe steps or operating points inflates within-mode variance
  or, after declared routing with too few train rows, explodes FP (ADR 0018, 0048).
- ``constant_in_train``: a tag that never moved is dropped; later motion is invisible.
- ``shrinkage_floor_mixed_scale``: Ledoit-Wolf ``_shrink`` is in raw units, so mixed-scale
  batch pools floor every band (ADR 0018). Do not rewrite ``_shrink`` on public rows.
  Session C3 ships ``ShrinkageTarget.CORRELATION`` as a named option; it is not the default.
"""

_MAX_CONDITION_NUMBER: Final = 1.0 / numpy.finfo(numpy.float64).eps
"""Conditioning past which a covariance is treated as having no usable inverse.

The standard rule: a matrix whose condition number reaches the reciprocal of machine epsilon has
lost every significant digit in its inverse. Inverting past it produces numbers, not information.
"""


class ShrinkageTarget(StrEnum):
    """Where Ledoit-Wolf ``_shrink`` pulls the covariance.

    ``AVERAGE_VARIANCE`` is the public default: the target is ``(trace / width) * I`` in the
    **raw units** of the signals. That is the path that produced ungated distillation 18.72.
    Mixed-scale batch pools then floor every band (ADR 0018).

    ``CORRELATION`` standardises, shrinks toward the identity, and rescales. Session C3 ships
    this as a named option so a declared-mode inner model can use it. It is **not** the public
    default: ADR 0018 measured it inflating water-treatment's attack-free holdout.
    """

    AVERAGE_VARIANCE = "average_variance"
    CORRELATION = "correlation"


# ------------------------------------------------------------------------------------------------
# The unfitted models
# ------------------------------------------------------------------------------------------------


class MultivariateModel(BehaviouralModel, ABC):
    """A `BehaviouralModel` that learns one joint model spanning every signal at once.

    Everything the two concrete models share lives here: learning the `SignalSpace`, reshaping the
    corpus into a matrix, discarding signals nothing can be learned about, and refusing to fit at
    all on too little data. What differs — how the shape of normal is represented — is
    `_fit_joint`.

    Attributes:
        fill_policy: How much missing data the reshape tolerates. Stored on the fitted model so
            that scoring reassembles rows exactly the way fitting did; a model fitted on rows
            built one way and scored on rows built another would be measuring two plants.
        min_samples: Inherited, and counted in **fully observed timestamps** rather than in
            observations. A joint model learns from complete moments.
        band_k: Inherited. Half-width of the reported departure band, in learned spreads.
        emit_k: Inherited. Departure, in learned spreads, at which a signal becomes a candidate.
    """

    fill_policy: VectorisePolicy = VectorisePolicy()

    def fit(self, observations: Sequence[Observation]) -> "MultivariateFittedModel":
        """Learn the joint structure of normal from ``observations``.

        Args:
            observations: The training corpus. Should be attack-free — see
                `phos.models.train_test_split`. Order is irrelevant; rows are assembled in
                timestamp order.

        Returns:
            A `MultivariateFittedModel` holding the learned structure as plain numbers. Fitting
            on too little data, or on a corpus in which no signal varies, yields a model spanning
            no signals,
            which then scores nothing. That is reported through the log rather than raised: an
            empty corpus is a fact about the corpus, and the sibling baselines in `phos.models`
            answer it the same way.
        """
        space = SignalSpace.from_observations(observations)
        series = vectorise(observations, space, self.fill_policy)

        if series.n_rows < self.min_samples:
            logger.warning(
                "%s: only %d fully observed timestamp(s) across %d signal(s), fewer than "
                "min_samples=%d; the fitted model will span no signals and score nothing",
                self.name,
                series.n_rows,
                space.size,
                self.min_samples,
            )
            return self._empty()

        variable = [
            column
            for column in range(space.size)
            if float(numpy.std(series.matrix[:, column])) > 0.0
        ]
        if len(variable) < len(space.signals):
            dropped = [space.signals[c] for c in range(space.size) if c not in set(variable)]
            logger.info(
                "%s: %d signal(s) held constant across training and are outside the joint model: "
                "%s",
                self.name,
                len(dropped),
                ", ".join(f"{entity}/{feature}" for entity, feature in dropped[:8]),
            )
        if not variable:
            logger.warning("%s: no signal varied in training; nothing to learn", self.name)
            return self._empty()

        window = (series.timestamps[0], series.timestamps[-1])
        fitted = self._fit_joint(space.select(variable), series.matrix[:, variable], window)
        logger.info(
            "fitted %s on %d timestamps x %d signals (%d timestamps dropped for missing data)",
            self.name,
            series.n_rows,
            len(variable),
            series.dropped_timestamps,
        )
        return fitted

    @abstractmethod
    def _fit_joint(
        self,
        signal_space: SignalSpace,
        matrix: Matrix,
        window: tuple[datetime, datetime],
    ) -> "MultivariateFittedModel":
        """Learn this model's representation of normal from a complete training matrix.

        Args:
            signal_space: The signals the columns of ``matrix`` correspond to. Every one of them
                varies.
            matrix: ``(n_rows x n_signals)`` of training readings, at least ``min_samples`` rows.
            window: The ``(first, last)`` timestamps the rows span.
        """

    @abstractmethod
    def _empty(self) -> "MultivariateFittedModel":
        """Return this model's fitted form for "there was nothing to learn"."""


# ------------------------------------------------------------------------------------------------
# The fitted models
# ------------------------------------------------------------------------------------------------


class MultivariateFittedModel(FittedModel, ABC):
    """A learned joint model that scores a moment and attributes what it finds to a signal.

    Scoring is shared by both models because both answer the same two questions per cell — what
    did the rest of the plant imply this signal should read (`_expected_values`), and how far does
    a reading normally sit from that (`_signal_spread`) — and everything after those two answers
    is identical: build the dynamic range, measure the departure in spreads, and emit.

    Attributes:
        signal_space: The signals this model spans, in the column order its parameters are stored
            in. A signal outside it is ignored at score time.
        band_k: Half-width of the reported band, in learned spreads.
        fill_policy: The missing-data policy used at fit time, reapplied at score time.
        training_window: The ``(first, last)`` timestamps the model learned from, recorded on
            every `ExpectedRange` it emits. ``None`` only for a model that learned nothing.
        expected_ranges: Per signal, the learned band on its **departure from what the rest of the
            plant implies** — centred on zero, because a well-behaved plant departs from its own
            structure by nothing. This is genuinely the baseline each reading is judged against;
            what is *not* here is an expected value, because for a joint model there is no such
            thing as a fixed one. That number is computed per moment and lives on the emitted
            `Deviation`.
        feature_ranges: Always empty. The cross-entity fallback that `phos.models` uses for an
            unseen key has no meaning here — there is nothing in a learned subspace to reconstruct
            a signal the subspace does not contain.
    """

    model_config = ConfigDict(frozen=True)

    signal_space: SignalSpace
    band_k: float = Field(ge=0.0)
    fill_policy: VectorisePolicy
    training_window: tuple[UtcDatetime, UtcDatetime] | None

    def score(self, observations: Sequence[Observation]) -> list[Deviation]:
        """Judge each moment against the learned joint structure and attribute what broke.

        Args:
            observations: The measurements to score. Reassembled into rows using the same
                `fill_policy` the model was fitted with. Observations of signals outside
                `signal_space` are ignored.

        Returns:
            One `Deviation` per ``(timestamp, signal)`` whose departure reached `emit_k`, in
            ascending timestamp order and, within a timestamp, in `SignalSpace` column order.

        Note:
            Only a cell backed by a fresh observation can produce a `Deviation`. A cell carried
            forward from an earlier row still informs the reconstruction of the rest of the
            plant — that is the point of carrying it — but there is no measurement at that instant
            for a deviation to point back to, and inventing one would break traceability
            (Constitution §3.2).

            `Deviation.timestamp` is the observation's own timestamp, never wall-clock now: this
            is an offline scorer and stamping it with the current time would make a run
            irreproducible.
        """
        if self.signal_space.size == 0 or self.training_window is None:
            return []

        series, expected, magnitude = self.departures(observations)
        if series.n_rows == 0:
            return []

        return self._emit(
            series,
            observations,
            expected,
            self._signal_spread(),
            magnitude,
            self.training_window,
        )

    def _moment_mask(self, matrix: Matrix) -> NDArray[numpy.bool_]:
        """Return which assembled moments may emit per-signal deviations.

        The default is every moment. `MahalanobisFittedModel` overrides this with a joint-distance
        gate so a thermal flicker that is still on the learned manifold cannot multiply into one
        alert per instrument. PCA residual has no comparable scalar, and is left ungated.
        """
        return numpy.ones(matrix.shape[0], dtype=numpy.bool_)

    def departures(
        self, observations: Sequence[Observation]
    ) -> tuple[VectorisedSeries, Matrix, Matrix]:
        """Assemble ``observations`` and measure how far every cell sits from the joint structure.

        The seam `score` is built on, made public because plant-health metrics
        (`phos.atlas.stability`) need the departure of *every* reading rather than only the ones
        that crossed `emit_k`. Reading it directly is what keeps a stability number and a
        `Deviation` two views of one computation rather than two computations that might disagree.

        Args:
            observations: The measurements to assemble, using the fitted `fill_policy`.

        Returns:
            ``(series, expected, departure)``. ``expected`` holds, per cell, the value the rest of
            the plant implied, in the signal's own units; ``departure`` holds the absolute gap
            between reading and expectation measured in learned spreads — the same number that
            becomes `Deviation.magnitude`. Both are ``(n_rows x n_signals)`` over
            ``series.signal_space``. All three are empty for a model that learned nothing.
        """
        if self.signal_space.size == 0:
            empty = numpy.empty((0, 0), dtype=numpy.float64)
            return vectorise(observations, self.signal_space, self.fill_policy), empty, empty

        series = vectorise(observations, self.signal_space, self.fill_policy)
        expected = self._expected_values(series.matrix)
        return series, expected, _departure(series.matrix, expected, self._signal_spread())

    def _emit(
        self,
        series: VectorisedSeries,
        observations: Sequence[Observation],
        expected: Matrix,
        spread: Vector,
        magnitude: Matrix,
        window: tuple[datetime, datetime],
    ) -> list[Deviation]:
        """Turn the cells that reached `emit_k` into `Deviation`s naming their signal."""
        allowed = self._moment_mask(series.matrix)[:, numpy.newaxis]
        rows, columns = numpy.nonzero(
            (magnitude >= self.emit_k) & (series.source_index != NO_OBSERVATION) & allowed
        )

        deviations: list[Deviation] = []
        for row, column in zip(rows.tolist(), columns.tolist(), strict=True):
            entity_id, feature = self.signal_space.signals[column]
            centre = float(expected[row, column])
            half_width = self.band_k * float(spread[column])
            deviations.append(
                Deviation(
                    observation_id=observations[int(series.source_index[row, column])].id,
                    expected=ExpectedRange(
                        feature=feature,
                        entity_id=entity_id,
                        low=centre - half_width,
                        high=centre + half_width,
                        mean=centre,
                        stddev=float(spread[column]),
                        learned_from_window=window,
                    ),
                    magnitude=float(magnitude[row, column]),
                    timestamp=series.timestamps[row],
                )
            )
        return deviations

    @abstractmethod
    def _expected_values(self, matrix: Matrix) -> Matrix:
        """Return, per cell, the value the rest of the plant implied that signal should hold.

        Args:
            matrix: ``(n_rows x n_signals)`` of readings in `signal_space` column order.

        Returns:
            An array of the same shape, in the same units.
        """

    @abstractmethod
    def _signal_spread(self) -> Vector:
        """Return the learned, non-negative departure spread of each signal, in its own units."""


def _departure(matrix: Matrix, expected: Matrix, spread: Vector) -> Matrix:
    """Return the per-cell departure from ``expected``, measured in learned spreads.

    Mirrors `ExpectedRange.zscore` followed by `phos.models.clamp_magnitude`, vectorised: a signal
    whose learned spread is zero is infinitely surprised by any departure at all and unsurprised by
    none, and the infinity is clamped so the resulting `Deviation` still serialises.
    """
    residual = numpy.abs(matrix - expected)
    with numpy.errstate(divide="ignore", invalid="ignore"):
        scaled = residual / spread
    degenerate = numpy.broadcast_to(spread == 0.0, residual.shape)
    scaled = numpy.where(degenerate, numpy.where(residual == 0.0, 0.0, MAX_MAGNITUDE), scaled)
    return numpy.minimum(scaled, MAX_MAGNITUDE).astype(numpy.float64)


def _departure_bands(
    signal_space: SignalSpace,
    spread: Vector,
    band_k: float,
    window: tuple[datetime, datetime],
) -> dict[ModelKey, ExpectedRange]:
    """Build the stored per-signal band on departure from the joint structure.

    Centred on zero: the reconstruction of a training corpus is unbiased by construction, so
    "normal" for a departure is none of it, and the band is how much of it normal operation
    produces anyway.
    """
    return {
        signal: ExpectedRange(
            feature=signal[1],
            entity_id=signal[0],
            low=-band_k * float(spread[column]),
            high=band_k * float(spread[column]),
            mean=0.0,
            stddev=float(spread[column]),
            learned_from_window=window,
        )
        for column, signal in enumerate(signal_space.signals)
    }


# ------------------------------------------------------------------------------------------------
# PCA residual — the primary model
# ------------------------------------------------------------------------------------------------


def _principal_components(standardised: Matrix, variance_retained: float) -> tuple[Matrix, Vector]:
    """Fit the principal subspace of ``standardised`` and return it as plain arrays.

    The only scikit-learn call in Atlas, confined here so that nothing an untyped library returns
    reaches a stored field or a signature — the arrangement PART 4A adopted for the calibrators.

    Args:
        standardised: ``(n_rows x n_signals)``, each column already centred and scaled.
        variance_retained: Share of training variance the retained components must together
            explain. sklearn selects the smallest number of components that reaches it.

    Returns:
        ``(components, centre)`` — the ``(k x n_signals)`` basis and the ``(n_signals,)`` mean the
        projection is taken about.
    """
    from sklearn.decomposition import PCA

    pca = PCA(n_components=variance_retained, svd_solver="full")
    pca.fit(standardised)
    components = numpy.asarray(pca.components_, dtype=numpy.float64)
    centre = numpy.asarray(pca.mean_, dtype=numpy.float64)
    return components, centre


class PcaResidualModel(MultivariateModel):
    """Learns the subspace normal operation lives in; scores by what will not fit back into it.

    Attributes:
        name: ``"atlas-pca"``.
        variance_retained: Share of the training variance the retained components must explain.
            Strictly below 1: retaining *every* component reconstructs any input perfectly, which
            leaves no residual to measure and turns the model into an elaborate identity function.
            The default of 0.95 keeps the structure and discards the noise floor, which is
            precisely the split the residual is meant to expose.
        min_samples: Inherited. Counted in fully observed timestamps.
        band_k: Inherited. Half-width of the reported band, in residual standard deviations.
        emit_k: Inherited. Residual, in standard deviations, at which a signal is a candidate.
    """

    name: str = "atlas-pca"
    variance_retained: float = Field(default=0.95, gt=0.0, lt=1.0)

    def _fit_joint(
        self,
        signal_space: SignalSpace,
        matrix: Matrix,
        window: tuple[datetime, datetime],
    ) -> MultivariateFittedModel:
        """Standardise, fit the principal subspace, and learn each signal's residual spread."""
        signal_mean = numpy.mean(matrix, axis=0)
        signal_scale = numpy.std(matrix, axis=0)
        standardised = (matrix - signal_mean) / signal_scale

        components, centre = _principal_components(standardised, self.variance_retained)
        reconstructed = _project(standardised, components, centre)
        residual_stddev = numpy.std(standardised - reconstructed, axis=0) * signal_scale

        logger.info(
            "%s retained %d of %d components for %.0f%% of training variance",
            self.name,
            components.shape[0],
            signal_space.size,
            100.0 * self.variance_retained,
        )
        return PcaResidualFittedModel(
            name=self.name,
            expected_ranges=_departure_bands(signal_space, residual_stddev, self.band_k, window),
            feature_ranges={},
            emit_k=self.emit_k,
            band_k=self.band_k,
            signal_space=signal_space,
            fill_policy=self.fill_policy,
            training_window=window,
            signal_mean=_row(signal_mean),
            signal_scale=_row(signal_scale),
            centre=_row(centre),
            components=tuple(_row(component) for component in components),
            residual_stddev=_row(residual_stddev),
        )

    def _empty(self) -> MultivariateFittedModel:
        return PcaResidualFittedModel(
            name=self.name,
            expected_ranges={},
            feature_ranges={},
            emit_k=self.emit_k,
            band_k=self.band_k,
            signal_space=SignalSpace(),
            fill_policy=self.fill_policy,
            training_window=None,
            signal_mean=(),
            signal_scale=(),
            centre=(),
            components=(),
            residual_stddev=(),
        )


class PcaResidualFittedModel(MultivariateFittedModel):
    """A learned principal subspace and the residual band each signal normally sits inside.

    Attributes:
        signal_mean: Per-signal training mean, used to standardise before projecting.
        signal_scale: Per-signal training standard deviation. Every entry is positive — a constant
            signal never reaches the fit.
        centre: The point in standardised space the projection is taken about.
        components: The retained basis, one row per component, each of `signal_space` width.
        residual_stddev: Per signal, the standard deviation of its reconstruction residual across
            training, in the signal's own units. This is what a departure is measured in.
    """

    signal_mean: tuple[float, ...]
    signal_scale: tuple[float, ...]
    centre: tuple[float, ...]
    components: tuple[tuple[float, ...], ...]
    residual_stddev: tuple[float, ...]

    @property
    def n_components(self) -> int:
        """How many principal components the fit retained."""
        return len(self.components)

    def _expected_values(self, matrix: Matrix) -> Matrix:
        """Return each reading's reconstruction from the retained subspace, in raw units."""
        signal_mean = numpy.asarray(self.signal_mean, dtype=numpy.float64)
        signal_scale = numpy.asarray(self.signal_scale, dtype=numpy.float64)
        components = numpy.asarray(self.components, dtype=numpy.float64)
        centre = numpy.asarray(self.centre, dtype=numpy.float64)

        standardised = (matrix - signal_mean) / signal_scale
        return _project(standardised, components, centre) * signal_scale + signal_mean

    def _signal_spread(self) -> Vector:
        return numpy.asarray(self.residual_stddev, dtype=numpy.float64)


def _project(standardised: Matrix, components: Matrix, centre: Vector) -> Matrix:
    """Project onto the retained basis and return to the full space.

    A moment lying along the correlations the basis captured comes back almost unchanged; the part
    of a moment that the basis cannot express is exactly what is lost, and that loss is the signal.
    """
    offset = standardised - centre
    return (offset @ components.T) @ components + centre


# ------------------------------------------------------------------------------------------------
# Mahalanobis — the covariance-based alternative
# ------------------------------------------------------------------------------------------------


class MahalanobisModel(MultivariateModel):
    """Learns the covariance of normal; judges each signal against what the others imply.

    Where `PcaResidualModel` keeps a rank-limited summary of the correlation structure, this keeps
    all of it, in the inverse covariance. That buys an attribution with an unusually direct
    reading: the expected value it reports for a signal is the **conditional mean** of that signal
    given every other reading at that instant, and the spread it reports is the conditional
    standard deviation. "Given the rest of the plant, this should have read X +/- s" is not an
    analogy here; it is what the number is.

    Attributes:
        name: ``"atlas-mahalanobis"``.
        shrinkage: How far the empirical covariance is pulled towards a scaled identity before it
            is inverted, between 0 and 1. Industrial signals are often near-collinear and the
            empirical covariance of a wide plant is frequently singular or nearly so, in which
            case the inverse is numerical noise and every conditional expectation built from it is
            fiction. The default of 0.05 is enough to make the inverse stable while leaving the
            correlation structure intact.
        shrinkage_target: ``AVERAGE_VARIANCE`` (default, public path) or ``CORRELATION``
            (scale-invariant; Session C3 named option). Do not switch the public default.
        min_samples: Inherited. Counted in fully observed timestamps.
        band_k: Inherited. Half-width of the reported band, in conditional standard deviations.
        emit_k: Inherited. Conditional departure at which a signal becomes a candidate.
        joint_k: Minimum Mahalanobis distance at which a *moment* may emit per-signal deviations.
            ``0`` disables the gate, which is the default so every number already on the experiment
            log stays comparable. A thermal flicker whose combination of readings is still on the
            learned manifold then no longer multiplies into one alert per instrument.
        adaptive_joint_quantile: If set, `joint_k` is learned at fit time as this quantile of the
            training Mahalanobis distances, and the explicit `joint_k` is ignored. The envelope
            is therefore a property of attack-free operation of *this* plant (or, under
            `PhaseConditionalModel`, of this phase), not a number chosen by looking at the answer.
    """

    name: str = "atlas-mahalanobis"
    shrinkage: float = Field(default=0.05, ge=0.0, le=1.0)
    shrinkage_target: ShrinkageTarget = ShrinkageTarget.AVERAGE_VARIANCE
    joint_k: float = Field(default=0.0, ge=0.0)
    adaptive_joint_quantile: float | None = Field(default=None, ge=0.0, le=1.0)

    def _fit_joint(
        self,
        signal_space: SignalSpace,
        matrix: Matrix,
        window: tuple[datetime, datetime],
    ) -> MultivariateFittedModel:
        """Learn the mean and the shrunk precision matrix."""
        mean = numpy.mean(matrix, axis=0)
        covariance = numpy.atleast_2d(numpy.cov(matrix, rowvar=False, bias=True))
        precision = _invert(
            _shrink(covariance, self.shrinkage, target=self.shrinkage_target),
            self.shrinkage,
            self.name,
        )

        conditional_stddev = 1.0 / numpy.sqrt(numpy.diag(precision))
        distances = _mahalanobis_distances(mean, precision, matrix)
        if self.adaptive_joint_quantile is None:
            joint_k = self.joint_k
        else:
            joint_k = float(numpy.quantile(distances, self.adaptive_joint_quantile))
            logger.info(
                "%s: learned joint_k=%.4g as the %.4g quantile of %d training moment(s)",
                self.name,
                joint_k,
                self.adaptive_joint_quantile,
                int(distances.shape[0]),
            )
        return MahalanobisFittedModel(
            name=self.name,
            expected_ranges=_departure_bands(signal_space, conditional_stddev, self.band_k, window),
            feature_ranges={},
            emit_k=self.emit_k,
            band_k=self.band_k,
            signal_space=signal_space,
            fill_policy=self.fill_policy,
            training_window=window,
            mean=_row(mean),
            precision=tuple(_row(component) for component in precision),
            joint_k=joint_k,
        )

    def _empty(self) -> MultivariateFittedModel:
        return MahalanobisFittedModel(
            name=self.name,
            expected_ranges={},
            feature_ranges={},
            emit_k=self.emit_k,
            band_k=self.band_k,
            signal_space=SignalSpace(),
            fill_policy=self.fill_policy,
            training_window=None,
            mean=(),
            precision=(),
            joint_k=0.0,
        )


class MahalanobisFittedModel(MultivariateFittedModel):
    """A learned mean and precision matrix, read as a set of conditional expectations.

    Attributes:
        mean: Per-signal training mean.
        precision: The inverse of the shrunk training covariance, one row per signal. Everything
            this model reports is read off it: the conditional expectation of signal ``j`` is
            ``x_j - [P(x - mean)]_j / P_jj`` and its conditional standard deviation is
            ``1 / sqrt(P_jj)``.
        joint_k: Minimum Mahalanobis distance at which a moment may emit per-signal deviations.
            ``0`` leaves the ungated per-signal behaviour unchanged.
    """

    mean: tuple[float, ...]
    precision: tuple[tuple[float, ...], ...]
    joint_k: float = Field(default=0.0, ge=0.0)

    def mahalanobis_distance(self, observations: Sequence[Observation]) -> Vector:
        """Return the joint distance of each assembled moment from the learned centre.

        The scalar "how unusual is the plant right now" behind the per-signal attribution. It is
        offered for the stability metrics in `phos.atlas.stability` and for inspection; it is not
        what a `Deviation` carries, because a bare distance names no signal and Constitution §3.2
        requires that a conclusion name its evidence.

        Args:
            observations: Measurements to assemble and measure, using the fitted fill policy.

        Returns:
            One non-negative distance per surviving row, in ascending timestamp order. Empty for a
            model that learned nothing.
        """
        if self.signal_space.size == 0:
            return numpy.empty(0, dtype=numpy.float64)
        matrix = vectorise(observations, self.signal_space, self.fill_policy).matrix
        return self.distances_of(matrix)

    def distances_of(self, matrix: Matrix) -> Vector:
        """Return the joint distance of each row of an already-assembled matrix."""
        return _mahalanobis_distances(
            numpy.asarray(self.mean, dtype=numpy.float64),
            numpy.asarray(self.precision, dtype=numpy.float64),
            matrix,
        )

    def _moment_mask(self, matrix: Matrix) -> NDArray[numpy.bool_]:
        """Allow per-signal emission only on moments that left the learned joint envelope."""
        if self.joint_k <= 0.0:
            return numpy.ones(matrix.shape[0], dtype=numpy.bool_)
        return self.distances_of(matrix) >= self.joint_k

    def _expected_values(self, matrix: Matrix) -> Matrix:
        """Return the conditional mean of each signal given every other signal at that instant."""
        precision = numpy.asarray(self.precision, dtype=numpy.float64)
        offset = matrix - numpy.asarray(self.mean, dtype=numpy.float64)
        return matrix - (offset @ precision) / numpy.diag(precision)

    def _signal_spread(self) -> Vector:
        precision = numpy.asarray(self.precision, dtype=numpy.float64)
        return (1.0 / numpy.sqrt(numpy.diag(precision))).astype(numpy.float64)


class JointMomentDetector(BaseModel):
    """One alert per plant-moment, scored by Mahalanobis distance.

    The PART 2 harness counts each `Detection`. Scoring per-signal residuals therefore counts a
    single off-manifold instant once per instrument, which is how a batch column posted 449
    alerts/day-equivalent on distillation. This detector answers the plant-as-a-machine question
    instead: how far is *this moment* from the learned centre? Attribution still lives on the
    per-signal `Deviation`s the fitted model emits; this is the counting unit for an operator
    budget.

    A moment is emitted only when its distance reaches the fitted `joint_k`. With the default
    ungated model (`joint_k = 0`) every assembled moment is a candidate and the harness threshold
    is the operating point. With an adaptive envelope, the operating point is the learned
    quantile itself.

    **Dwell.** A control room does not page a one-sample flicker. `dwell_samples` is how many
    *consecutive* moments must sit at or above `joint_k` before the first alert of that run is
    emitted. ``1`` (the default) is ADR 0026's detector unchanged. The run counter resets the
    moment the plant returns below the envelope, so two flickers separated by a normal sample
    never accumulate into an alert. This is persistence, not a signature of a named attack.

    Attributes:
        fitted: An already-fitted Mahalanobis model.
        score_scale: Distance mapping to a confidence of about 0.63. Uncalibrated; nothing may
            present it as a probability (Constitution §3.3).
        dwell_samples: Consecutive jointly-unusual moments required before an alert. ``1``
            reproduces the ungated-in-time detector.
    """

    model_config = ConfigDict(frozen=True)

    fitted: MahalanobisFittedModel
    score_scale: float = Field(default=3.0, gt=0.0)
    dwell_samples: int = Field(default=1, ge=1)

    @property
    def name(self) -> str:
        """Identifies the detector in reports and the experiment log."""
        base = f"joint-moment:{self.fitted.name}"
        if self.dwell_samples == 1:
            return base
        return f"{base}:dwell-{self.dwell_samples}"

    def run(self, dataset: Dataset) -> list[Detection]:
        """Return one detection per jointly unusual moment that has also held for the dwell.

        Args:
            dataset: The corpus to score. Should be a test slice the model was not fitted on.

        Returns:
            Detections in timestamp order, one per assembled row whose Mahalanobis distance
            reached `fitted.joint_k` and whose immediately preceding
            ``dwell_samples - 1`` assembled rows did too. ``feature`` is empty: the score is a
            property of the plant at that instant, not of one signal. The per-signal
            `Deviation`s remain the explainable attribution.
        """
        if self.fitted.signal_space.size == 0:
            return []
        series = vectorise(dataset.observations, self.fitted.signal_space, self.fitted.fill_policy)
        if series.n_rows == 0:
            return []
        distances = self.fitted.distances_of(series.matrix)
        detections: list[Detection] = []
        run_length = 0
        for row, distance in enumerate(distances.tolist()):
            score = float(distance)
            if score < self.fitted.joint_k:
                run_length = 0
                continue
            run_length += 1
            if run_length < self.dwell_samples:
                continue
            detections.append(
                Detection(
                    timestamp=series.timestamps[row],
                    score=score,
                    confidence=uncalibrated_confidence(score, self.score_scale),
                    entity_ids=_entities_at(series, dataset.observations, row),
                    feature=None,
                )
            )
        return detections


def _entities_at(
    series: VectorisedSeries, observations: Sequence[Observation], row: int
) -> list[EntityId]:
    """Return the distinct entities measured at one assembled moment, in first-seen order."""
    seen: list[EntityId] = []
    for index in series.source_index[row].tolist():
        if index == NO_OBSERVATION:
            continue
        for entity_id in observations[int(index)].entity_ids:
            if entity_id not in seen:
                seen.append(entity_id)
    if seen:
        return seen
    return [entity_id for entity_id, _feature in series.signal_space.signals[:1]]


def _mahalanobis_distances(mean: Vector, precision: Matrix, matrix: Matrix) -> Vector:
    """Return ``sqrt((x-μ)ᵀ P (x-μ))`` for each row of ``matrix``."""
    offset = matrix - mean
    squared = numpy.sum(offset * (offset @ precision), axis=1)
    return numpy.sqrt(numpy.maximum(squared, 0.0)).astype(numpy.float64)


def _invert(covariance: Matrix, shrinkage: float, name: str) -> Matrix:
    """Invert a covariance matrix, or say plainly why the inverse would be meaningless.

    A wide industrial plant routinely contains signals that are exact linear combinations of
    others — a total flow that is the sum of two branch flows, a level reported in two units. The
    covariance of such a plant is singular, and every conditional expectation read off its inverse
    is fiction.

    The check is the **condition number**, not whether `numpy.linalg.inv` complains. LAPACK
    complains only for a matrix that is singular in exact arithmetic; a covariance assembled from
    real readings of a redundant signal is singular in principle and merely astronomically
    ill-conditioned in floating point, so it inverts without protest and returns numbers with no
    surviving precision in them. Relying on the exception would let exactly the realistic case
    through in silence.

    Raises:
        ValueError: If the covariance is singular or so ill-conditioned that its inverse carries
            no significant digits, naming the remedy rather than only the symptom.
    """
    conditioning = float(numpy.linalg.cond(covariance))
    if not numpy.isfinite(conditioning) or conditioning > _MAX_CONDITION_NUMBER:
        raise ValueError(
            f"{name}: the training covariance of these {covariance.shape[0]} signals is singular "
            f"at shrinkage={shrinkage} (condition number {conditioning:.3g}), so its inverse "
            "carries no significant digits and no conditional expectation can be built from it. "
            "At least one signal is an exact linear combination of others. Raise shrinkage above "
            "zero, or drop the redundant signal"
        )
    return numpy.asarray(numpy.linalg.inv(covariance), dtype=numpy.float64)


def _shrink(
    covariance: Matrix,
    shrinkage: float,
    *,
    target: ShrinkageTarget = ShrinkageTarget.AVERAGE_VARIANCE,
) -> Matrix:
    """Pull ``covariance`` towards a scaled identity of the same average variance.

    The standard Ledoit-Wolf target. It leaves the total variance unchanged while damping the
    off-diagonal structure, which is what makes a near-singular industrial covariance invertible
    without pretending the signals are independent.

    ``target=CORRELATION`` standardises first (ADR 0018 Option A). That is Session C3's named
    option, not the public default: mixed-scale plants stop flooring quiet tags, and continuous
    plants can inflate an attack-free holdout.
    """
    if shrinkage == 0.0:
        return covariance
    width = covariance.shape[0]
    identity = numpy.eye(width, dtype=numpy.float64)
    if target is ShrinkageTarget.CORRELATION:
        stddev = numpy.sqrt(numpy.maximum(numpy.diag(covariance), numpy.finfo(numpy.float64).tiny))
        scale = numpy.diag(1.0 / stddev)
        correlation = scale @ covariance @ scale
        shrunk_correlation = correlation * (1.0 - shrinkage) + identity * shrinkage
        restore = numpy.diag(stddev)
        shrunk: Matrix = restore @ shrunk_correlation @ restore
        return shrunk
    average_variance = float(numpy.trace(covariance)) / width
    raw: Matrix = covariance * (1.0 - shrinkage) + identity * (shrinkage * average_variance)
    return raw


def _row(values: Vector) -> tuple[float, ...]:
    """Convert a numpy vector into the plain floats a fitted model stores."""
    return tuple(float(value) for value in values)

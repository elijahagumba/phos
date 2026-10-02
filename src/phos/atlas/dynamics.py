"""A linear dynamical residual beside the snapshot joint models (Session C5).

Snapshot Mahalanobis / PCA score a moment without using ``x_{t-1}``. This module scores
the one-step prediction error of a declared-order VAR:

    x_t ≈ c + A x_{t-1} + … + A_lag x_{t-lag}

fitted only on the attack-free train matrix. The residual ``r_t = x_t - x̂_t`` is judged
with a shrunk covariance so each `Deviation` still carries a per-signal `ExpectedRange`
(Constitution §3.2). The first ``lag`` timestamps of a series have no predecessor and
are not emitted.

**Named experiment.** ``atlas-var1`` (default ``lag=1``). Snapshot Mahalanobis remains
available and remains the public comparison name. Do not overwrite ungated distillation
18.72 with this detector.

**Assumption.** Within a mode, the plant is approximately linear over the train horizon.
**Breaks.** A setpoint change not in train; unmodelled switching. Those are named so a
test can falsify them. Deep models stay out unless a nested ADR opens ``torch``.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Final

import numpy
from numpy.typing import NDArray
from pydantic import Field

from phos.atlas.multivariate import (
    Matrix,
    MultivariateFittedModel,
    MultivariateModel,
    Vector,
    _departure_bands,
    _invert,
    _row,
    _shrink,
)
from phos.atlas.vectorise import SignalSpace

__all__ = [
    "DYNAMICS_ASSUMPTIONS",
    "DYNAMICS_BREAK_CONDITIONS",
    "LinearDynamicsFittedModel",
    "LinearDynamicsModel",
]

logger = logging.getLogger(__name__)

DYNAMICS_ASSUMPTIONS: Final[tuple[str, ...]] = (
    "linear_within_mode",
    "declared_lag",
    "attack_free_train_only",
)
"""What the VAR residual actually assumes, named so a test can falsify them."""

DYNAMICS_BREAK_CONDITIONS: Final[tuple[str, ...]] = (
    "setpoint_change_not_in_train",
    "unmodelled_switching",
)
"""Named conditions under which the linear residual is not a valid plant model."""


class LinearDynamicsModel(MultivariateModel):
    """Fits a declared-order linear VAR and scores the one-step residual jointly.

    Attributes:
        name: ``"atlas-var1"`` by default. Changing ``lag`` does not silently reuse a
            public snapshot log name.
        lag: Number of previous complete moments used to predict the next. Must be ≥ 1.
        shrinkage: Passed to residual-covariance ``_shrink`` (public default target).
    """

    name: str = "atlas-var1"
    lag: int = Field(default=1, ge=1)
    shrinkage: float = Field(default=0.05, ge=0.0, le=1.0)

    def _fit_joint(
        self,
        signal_space: SignalSpace,
        matrix: Matrix,
        window: tuple[datetime, datetime],
    ) -> MultivariateFittedModel:
        """Ordinary least squares VAR, then a shrunk residual covariance."""
        lag = self.lag
        n_rows = matrix.shape[0]
        if n_rows <= lag:
            logger.warning(
                "%s: %d row(s) is not more than lag=%d; nothing to learn",
                self.name,
                n_rows,
                lag,
            )
            return self._empty()

        lagged = [matrix[lag - step : n_rows - step] for step in range(1, lag + 1)]
        design = numpy.column_stack([numpy.ones(n_rows - lag, dtype=numpy.float64), *lagged])
        targets = matrix[lag:]
        coefficients, *_ = numpy.linalg.lstsq(design, targets, rcond=None)
        predicted = design @ coefficients
        residual = targets - predicted
        covariance = numpy.atleast_2d(numpy.cov(residual, rowvar=False, bias=True))
        precision = _invert(_shrink(covariance, self.shrinkage), self.shrinkage, self.name)
        spread = 1.0 / numpy.sqrt(numpy.diag(precision))
        intercept = _row(numpy.asarray(coefficients[0], dtype=numpy.float64))
        transition = tuple(
            _row(numpy.asarray(row, dtype=numpy.float64)) for row in coefficients[1:]
        )
        return LinearDynamicsFittedModel(
            name=self.name,
            expected_ranges=_departure_bands(signal_space, spread, self.band_k, window),
            feature_ranges={},
            emit_k=self.emit_k,
            band_k=self.band_k,
            signal_space=signal_space,
            fill_policy=self.fill_policy,
            training_window=window,
            intercept=intercept,
            transition=transition,
            residual_precision=tuple(_row(component) for component in precision),
            lag=lag,
        )

    def _empty(self) -> MultivariateFittedModel:
        return LinearDynamicsFittedModel(
            name=self.name,
            expected_ranges={},
            feature_ranges={},
            emit_k=self.emit_k,
            band_k=self.band_k,
            signal_space=SignalSpace(),
            fill_policy=self.fill_policy,
            training_window=None,
            intercept=(),
            transition=(),
            residual_precision=(),
            lag=self.lag,
        )


class LinearDynamicsFittedModel(MultivariateFittedModel):
    """Stored VAR coefficients and residual precision.

    Attributes:
        intercept: Per-signal intercept ``c``.
        transition: Flattened lag blocks, each row a coefficient row of ``[A_1; …; A_lag]``.
        residual_precision: Inverse shrunk residual covariance.
        lag: Declared order used at fit time.
    """

    intercept: tuple[float, ...]
    transition: tuple[tuple[float, ...], ...]
    residual_precision: tuple[tuple[float, ...], ...]
    lag: int = Field(ge=1)

    def _expected_values(self, matrix: Matrix) -> Matrix:
        """One-step prediction; the first ``lag`` rows are placeholders and are masked from emit."""
        lag = self.lag
        n_rows, width = matrix.shape
        intercept = numpy.asarray(self.intercept, dtype=numpy.float64)
        expected = numpy.empty_like(matrix, dtype=numpy.float64)
        if width == 0:
            return expected
        expected[:lag] = intercept
        if n_rows <= lag:
            return expected
        transition = numpy.asarray(self.transition, dtype=numpy.float64)
        lagged = [matrix[lag - step : n_rows - step] for step in range(1, lag + 1)]
        design = numpy.column_stack(lagged)
        expected[lag:] = intercept + design @ transition
        return expected

    def _signal_spread(self) -> Vector:
        precision = numpy.asarray(self.residual_precision, dtype=numpy.float64)
        if precision.size == 0:
            return numpy.empty(0, dtype=numpy.float64)
        return (1.0 / numpy.sqrt(numpy.diag(precision))).astype(numpy.float64)

    def _moment_mask(self, matrix: Matrix) -> NDArray[numpy.bool_]:
        """The first ``lag`` rows have no predecessor; they must not raise a deviation."""
        allowed = numpy.ones(matrix.shape[0], dtype=numpy.bool_)
        allowed[: self.lag] = False
        return allowed

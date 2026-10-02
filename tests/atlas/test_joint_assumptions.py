"""Session C1: the snapshot joint model's assumptions are executable, not just docstring.

Pins from ``docs/category-defining-roadmap.md`` Session C1:

1. Scoring a complete moment does not use ``x_{t-1}`` (temporal independence).
2. The feasible set is a linear subspace (PCA) or an ellipsoid (Mahalanobis).
3. A named PCA out-of-sample break (ADR 0009): residual-band inflation under a
   larger noise floor, without fitting on the drifted set.

Do not change ``_shrink``. Do not overwrite public Mahalanobis log names.
"""

from datetime import UTC, datetime, timedelta

import numpy
import pytest

from phos.atlas.multivariate import (
    MANIFOLD_BREAK_CONDITIONS,
    SNAPSHOT_ASSUMPTIONS,
    MahalanobisFittedModel,
    MahalanobisModel,
    PcaResidualFittedModel,
    PcaResidualModel,
    _project,
)
from phos.models import FittedModel, GaussianBaseline
from phos.ontology import Deviation, Domain, Observation
from phos.reasoning import is_out_of_band

T0 = datetime(2026, 8, 23, 0, 0, tzinfo=UTC)
STEP = timedelta(seconds=1)
PLANT = "ent_c1plant"
SPEED = "pump_speed"
HEADER = "header_flow"
OUTLET = "outlet_flow"
LEVEL = "tank_level"


def _reading(row: int, feature: str, value: float) -> Observation:
    return Observation(
        id=f"obs_{row:08d}{feature[:4]}",
        entity_ids=[PLANT],
        feature=feature,
        value=value,
        timestamp=T0 + row * STEP,
        domain=Domain.ATLAS,
    )


def _plant_training(*, rows: int, seed: int, jitter: float) -> list[Observation]:
    """Four-signal plant: three demand-linked tags plus an independent level."""
    generator = numpy.random.default_rng(seed)
    demand = generator.normal(0.0, 1.0, rows)
    level = generator.normal(20.0, 1.0, rows)
    noise = generator.normal(0.0, jitter, (rows, 4))
    observations: list[Observation] = []
    for row in range(rows):
        observations.extend(
            [
                _reading(row, SPEED, 50.0 + 5.0 * demand[row] + noise[row, 0]),
                _reading(row, HEADER, 100.0 + 10.0 * demand[row] + noise[row, 1]),
                _reading(row, OUTLET, 100.0 + 10.0 * demand[row] + noise[row, 2]),
                _reading(row, LEVEL, level[row] + noise[row, 3]),
            ]
        )
    return observations


def _oob_rate(fitted: FittedModel, observations: list[Observation]) -> float:
    """Fraction of emitted deviations that sit outside their expected range."""
    by_id = {item.id: item for item in observations}
    scored = fitted.score(observations)
    if not scored:
        return 0.0
    hits = 0
    for deviation in scored:
        assert isinstance(deviation, Deviation)
        observation = by_id[deviation.observation_id]
        if is_out_of_band(deviation, observation):
            hits += 1
    return hits / len(scored)


def test_snapshot_assumptions_and_break_conditions_are_named() -> None:
    """C1: the code states what it assumes and when that assumption is invalid."""
    assert "temporal_independence" in SNAPSHOT_ASSUMPTIONS
    assert "linear_feasible_set" in SNAPSHOT_ASSUMPTIONS
    assert "constants_dropped" in SNAPSHOT_ASSUMPTIONS
    assert "nonstationarity_capture_drift" in MANIFOLD_BREAK_CONDITIONS
    assert "mixed_modes" in MANIFOLD_BREAK_CONDITIONS
    assert "constant_in_train" in MANIFOLD_BREAK_CONDITIONS
    assert "shrinkage_floor_mixed_scale" in MANIFOLD_BREAK_CONDITIONS


@pytest.mark.parametrize("model_type", [PcaResidualModel, MahalanobisModel])
def test_scoring_a_complete_moment_does_not_use_the_previous_timestamp(
    model_type: type[PcaResidualModel] | type[MahalanobisModel],
) -> None:
    """A snapshot model has no lag: wild ``x_{t-1}`` must not change the tip reconstruction."""
    train = _plant_training(rows=80, seed=3, jitter=0.02)
    fitted = model_type(min_samples=20).fit(train)
    tip_row = 99
    tip = [
        _reading(tip_row, SPEED, 50.0),
        _reading(tip_row, HEADER, 100.0),
        _reading(tip_row, OUTLET, 100.0),
        _reading(tip_row, LEVEL, 20.0),
    ]
    past_quiet = [
        _reading(tip_row - 1, SPEED, 50.0),
        _reading(tip_row - 1, HEADER, 100.0),
        _reading(tip_row - 1, OUTLET, 100.0),
        _reading(tip_row - 1, LEVEL, 20.0),
        *tip,
    ]
    past_wild = [
        _reading(tip_row - 1, SPEED, 500.0),
        _reading(tip_row - 1, HEADER, 5.0),
        _reading(tip_row - 1, OUTLET, 5.0),
        _reading(tip_row - 1, LEVEL, 200.0),
        *tip,
    ]
    _, expected_quiet, _ = fitted.departures(past_quiet)
    _, expected_wild, _ = fitted.departures(past_wild)
    _, expected_tip, _ = fitted.departures(tip)
    numpy.testing.assert_allclose(expected_quiet[-1], expected_wild[-1])
    numpy.testing.assert_allclose(expected_tip[-1], expected_quiet[-1])


def test_pca_feasible_set_is_a_linear_subspace_in_standardised_coordinates() -> None:
    fitted = PcaResidualModel(min_samples=20).fit(_plant_training(rows=80, seed=4, jitter=0.02))
    assert isinstance(fitted, PcaResidualFittedModel)
    components = numpy.asarray(fitted.components, dtype=numpy.float64)
    assert components.ndim == 2
    assert components.shape[1] == fitted.signal_space.size
    assert 1 <= components.shape[0] < fitted.signal_space.size
    standardised = numpy.zeros((1, fitted.signal_space.size), dtype=numpy.float64)
    reconstructed = _project(
        standardised,
        components,
        numpy.asarray(fitted.centre, dtype=numpy.float64),
    )
    assert reconstructed.shape == standardised.shape


def test_mahalanobis_feasible_set_is_an_ellipsoid_via_precision() -> None:
    fitted = MahalanobisModel(min_samples=20).fit(_plant_training(rows=80, seed=5, jitter=0.02))
    assert isinstance(fitted, MahalanobisFittedModel)
    precision = numpy.asarray(fitted.precision, dtype=numpy.float64)
    width = fitted.signal_space.size
    assert precision.shape == (width, width)
    symmetric = numpy.allclose(precision, precision.T)
    assert symmetric
    # Distance is sqrt((x-μ)ᵀ P (x-μ)): P must be usable as a metric (SPD after shrink).
    eigenvalues = numpy.linalg.eigvalsh(precision)
    assert float(numpy.min(eigenvalues)) > 0.0


def test_pca_residual_band_inflates_under_a_larger_noise_floor_more_than_the_marginal() -> None:
    """ADR 0009 named condition: in-sample residual band is not the out-of-sample band.

    Train with a tight residual; score the same correlation structure with a larger noise
    floor. Do not fit PCA on the drifted set. Gaussian bands include demand variance, so
    they inflate less than the PCA residual band.
    """
    train = _plant_training(rows=120, seed=1, jitter=0.02)
    test = _plant_training(rows=120, seed=2, jitter=0.5)
    pca = PcaResidualModel(min_samples=20).fit(train)
    gaussian = GaussianBaseline().fit(train)
    pca_train = _oob_rate(pca, train)
    pca_test = _oob_rate(pca, test)
    gauss_train = _oob_rate(gaussian, train)
    gauss_test = _oob_rate(gaussian, test)
    assert pca_train > 0.0 or pca_test > pca_train
    pca_inflation = pca_test / max(pca_train, 1e-9)
    gauss_inflation = gauss_test / max(gauss_train, 1e-9)
    assert pca_inflation > gauss_inflation, (
        f"PCA inflation {pca_inflation:.3f} should exceed Gaussian {gauss_inflation:.3f} "
        "under a larger residual noise floor (ADR 0009). Do not fit on the test set."
    )

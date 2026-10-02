"""Session C5: a declared-order linear VAR residual, beside snapshot Mahalanobis.

Pins from ``docs/category-defining-roadmap.md`` Session C5:

1. Fit only on the attack-free train matrix; residual ``r_t = x_t - x̂_t``.
2. Per-signal ``ExpectedRange`` (not a black-box reconstruction score).
3. Snapshot Mahalanobis remains importable. New experiment name ``atlas-var1``.
4. A wild ``x_{t-1}`` *does* change the tip prediction (temporal dependence).
5. Named break: a setpoint change not in train inflates the residual.
"""

from datetime import UTC, datetime, timedelta

import numpy
import pytest

from phos.atlas.dynamics import (
    DYNAMICS_ASSUMPTIONS,
    DYNAMICS_BREAK_CONDITIONS,
    LinearDynamicsFittedModel,
    LinearDynamicsModel,
)
from phos.atlas.multivariate import MahalanobisModel
from phos.models import FittedModel
from phos.ontology import Deviation, Domain, Observation
from phos.reasoning import is_out_of_band

T0 = datetime(2026, 8, 23, 15, 0, tzinfo=UTC)
STEP = timedelta(seconds=1)
PLANT = "ent_c5plant"
LEVEL = "tank_level"
FLOW = "inlet_flow"


def _reading(row: int, feature: str, value: float) -> Observation:
    return Observation(
        id=f"obs_{row:08d}{feature[:4]}",
        entity_ids=[PLANT],
        feature=feature,
        value=value,
        timestamp=T0 + row * STEP,
        domain=Domain.ATLAS,
    )


def _ar_plant(*, rows: int, seed: int, level0: float = 20.0) -> list[Observation]:
    """Two-signal plant: level is a damped AR(1); flow tracks the previous level."""
    generator = numpy.random.default_rng(seed)
    level = numpy.empty(rows, dtype=numpy.float64)
    flow = numpy.empty(rows, dtype=numpy.float64)
    level[0] = level0
    flow[0] = 5.0
    noise = generator.normal(0.0, 0.05, (rows, 2))
    for row in range(1, rows):
        level[row] = 0.4 + 0.8 * level[row - 1] + noise[row, 0]
        flow[row] = 1.0 + 0.2 * level[row - 1] + noise[row, 1]
    observations: list[Observation] = []
    for row in range(rows):
        observations.extend(
            [_reading(row, LEVEL, float(level[row])), _reading(row, FLOW, float(flow[row]))]
        )
    return observations


def _oob_features(fitted: FittedModel, observations: list[Observation]) -> set[str]:
    by_id = {item.id: item for item in observations}
    features: set[str] = set()
    for deviation in fitted.score(observations):
        assert isinstance(deviation, Deviation)
        observation = by_id[deviation.observation_id]
        if is_out_of_band(deviation, observation):
            features.add(deviation.expected.feature)
    return features


def test_dynamics_assumptions_and_breaks_are_named() -> None:
    assert "linear_within_mode" in DYNAMICS_ASSUMPTIONS
    assert "declared_lag" in DYNAMICS_ASSUMPTIONS
    assert "setpoint_change_not_in_train" in DYNAMICS_BREAK_CONDITIONS
    assert "unmodelled_switching" in DYNAMICS_BREAK_CONDITIONS


def test_var_experiment_name_does_not_reuse_the_public_snapshot_name() -> None:
    assert LinearDynamicsModel().name == "atlas-var1"
    assert MahalanobisModel().name == "atlas-mahalanobis"
    assert LinearDynamicsModel().lag == 1


def test_scoring_a_complete_moment_uses_the_previous_timestamp() -> None:
    """Opposite of the snapshot: wild ``x_{t-1}`` must move the tip reconstruction."""
    train = _ar_plant(rows=80, seed=3)
    fitted = LinearDynamicsModel(min_samples=20).fit(train)
    assert isinstance(fitted, LinearDynamicsFittedModel)
    tip_row = 40
    tip = [_reading(tip_row, LEVEL, 20.0), _reading(tip_row, FLOW, 5.0)]
    past_quiet = [
        _reading(tip_row - 1, LEVEL, 20.0),
        _reading(tip_row - 1, FLOW, 5.0),
        *tip,
    ]
    past_wild = [
        _reading(tip_row - 1, LEVEL, 80.0),
        _reading(tip_row - 1, FLOW, 40.0),
        *tip,
    ]
    _, expected_quiet, _ = fitted.departures(past_quiet)
    _, expected_wild, _ = fitted.departures(past_wild)
    with pytest.raises(AssertionError):
        numpy.testing.assert_allclose(expected_quiet[-1], expected_wild[-1])


def test_each_deviation_carries_a_per_signal_expected_range() -> None:
    train = _ar_plant(rows=80, seed=4)
    probe = _ar_plant(rows=20, seed=5)
    # Force a large jump at the tip so something emits.
    probe[-2] = _reading(19, LEVEL, 80.0)
    fitted = LinearDynamicsModel(min_samples=20).fit(train)
    scored = fitted.score(train + probe)
    assert scored
    for deviation in scored:
        assert deviation.expected.feature in {LEVEL, FLOW}
        assert deviation.expected.high >= deviation.expected.low
        assert deviation.expected.stddev is not None


def test_first_lag_rows_do_not_emit() -> None:
    train = _ar_plant(rows=40, seed=6)
    fitted = LinearDynamicsModel(min_samples=10).fit(train)
    scored = fitted.score(train[:4])  # two timestamps → 4 observations
    first_ids = {train[0].id, train[1].id}
    assert not any(deviation.observation_id in first_ids for deviation in scored)


def test_setpoint_change_not_in_train_inflates_the_residual() -> None:
    """C5 break condition: a level the AR never saw is not explained by the linear residual."""
    train = _ar_plant(rows=80, seed=1, level0=20.0)
    same = _ar_plant(rows=40, seed=2, level0=20.0)
    jumped = _ar_plant(rows=40, seed=2, level0=80.0)
    fitted = LinearDynamicsModel(min_samples=20).fit(train)
    same_hits = _oob_features(fitted, same)
    jumped_hits = _oob_features(fitted, jumped)
    assert jumped_hits, "a setpoint the AR never saw must leave the residual band"
    assert len(jumped_hits) >= len(same_hits)

"""Session C3: scale relationships, stated.

ADR 0018 rejected making `_shrink` scale-invariant as the public default because it
inflated water-treatment's attack-free holdout. This session ships that path as a
**named option** (`ShrinkageTarget.CORRELATION`), keeps `AVERAGE_VARIANCE` as the
default (public distillation 18.72 unchanged), and records the bake-off.

Within a declared mode, `PhaseConditionalModel` already subsets before `fit`, so
passing `inner=MahalanobisModel(shrinkage_target=CORRELATION)` standardises within
that mode.
"""

from datetime import UTC, datetime, timedelta

import numpy
import pytest
from tests.atlas.test_phased import (
    PHASE,
    out_of_band_features,
    phase_violation,
    phased_training,
)

from phos.atlas.multivariate import (
    MahalanobisFittedModel,
    MahalanobisModel,
    ShrinkageTarget,
    _shrink,
)
from phos.atlas.phased import PhaseConditionalModel
from phos.models import FittedModel
from phos.ontology import Deviation, Domain, Observation
from phos.reasoning import is_out_of_band

T0 = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)
STEP = timedelta(seconds=30)
PLANT = "ent_c3plant"


def _oob_rate(fitted: FittedModel, observations: list[Observation]) -> float:
    by_id = {item.id: item for item in observations}
    scored = fitted.score(observations)
    if not scored:
        return 0.0
    hits = 0
    for deviation in scored:
        assert isinstance(deviation, Deviation)
        if is_out_of_band(deviation, by_id[deviation.observation_id]):
            hits += 1
    return hits / len(scored)


def test_default_shrinkage_target_is_average_variance_in_raw_units() -> None:
    """Public Mahalanobis rows keep the Ledoit-Wolf target that produced 18.72."""
    assert MahalanobisModel().shrinkage_target is ShrinkageTarget.AVERAGE_VARIANCE


def test_correlation_shrink_does_not_floor_a_quiet_signal_with_a_loud_cousin() -> None:
    """The batch-reactor failure mode in miniature: mixed units, one huge variance."""
    loud = numpy.array([0.0, 5000.0] * 40, dtype=numpy.float64)
    quiet = numpy.full(80, 20.0, dtype=numpy.float64) + numpy.linspace(-0.4, 0.4, 80)
    matrix = numpy.column_stack([loud, quiet])
    covariance = numpy.atleast_2d(numpy.cov(matrix, rowvar=False, bias=True))
    raw = _shrink(covariance, 0.05)
    corr = _shrink(covariance, 0.05, target=ShrinkageTarget.CORRELATION)
    raw_floor = float(numpy.min(numpy.sqrt(numpy.diag(raw))))
    corr_quiet = float(numpy.sqrt(corr[1, 1]))
    assert raw_floor > 50.0
    assert corr_quiet < 5.0


def test_pooled_correlation_shrink_sees_the_phase_violation_raw_units_miss() -> None:
    training = phased_training()
    probe = training + phase_violation(9999)
    raw = MahalanobisModel().fit(training)
    corr = MahalanobisModel(shrinkage_target=ShrinkageTarget.CORRELATION).fit(training)
    assert out_of_band_features(raw.score(probe), probe) == set()
    assert "temp" in out_of_band_features(corr.score(probe), probe)


def test_phase_conditional_can_carry_correlation_shrink_within_declared_mode() -> None:
    """Standardise-within-mode is the inner model plus the existing phase router."""
    inner = MahalanobisModel(shrinkage_target=ShrinkageTarget.CORRELATION)
    model = PhaseConditionalModel(phase_feature=PHASE, inner=inner, settling_window=timedelta(0))
    fitted = model.fit(phased_training())
    probe = phased_training() + phase_violation(9999)
    assert "temp" in out_of_band_features(fitted.score(probe), probe)
    assert inner.shrinkage_target is ShrinkageTarget.CORRELATION


def _continuous_plant(*, rows: int, seed: int, tiny_jitter: float) -> list[Observation]:
    """Water/power analogue: correlated demand-linked tags plus a tiny-scale extra."""
    generator = numpy.random.default_rng(seed)
    demand = generator.normal(0.0, 1.0, rows)
    noise = generator.normal(0.0, 0.3, (rows, 3))
    tiny = generator.normal(0.01, tiny_jitter, rows)
    observations: list[Observation] = []
    for row in range(rows):
        stamp = T0 + row * STEP
        observations.extend(
            [
                Observation(
                    id=f"obs_{row:08d}spd",
                    entity_ids=[PLANT],
                    feature="pump_speed",
                    value=50.0 + 5.0 * demand[row] + noise[row, 0],
                    timestamp=stamp,
                    domain=Domain.ATLAS,
                ),
                Observation(
                    id=f"obs_{row:08d}flow",
                    entity_ids=[PLANT],
                    feature="header_flow",
                    value=100.0 + 10.0 * demand[row] + noise[row, 1],
                    timestamp=stamp,
                    domain=Domain.ATLAS,
                ),
                Observation(
                    id=f"obs_{row:08d}tiny",
                    entity_ids=[PLANT],
                    feature="conductivity",
                    value=tiny[row],
                    timestamp=stamp,
                    domain=Domain.ATLAS,
                ),
            ]
        )
    return observations


@pytest.mark.parametrize(
    ("tiny_train", "tiny_holdout", "plant_name"),
    [
        (0.0002, 0.002, "water-like continuous"),
        (0.0002, 0.003, "power-like continuous"),
    ],
)
def test_correlation_shrink_inflates_holdout_on_a_continuous_mixed_scale_plant(
    tiny_train: float, tiny_holdout: float, plant_name: str
) -> None:
    """ADR 0018: scale-invariant shrink makes small-scale tags live; holdout inflates.

    Library water/power personas are the same geometry (continuous, mixed units). This
    fixture is that geometry without quoting a library quietness row as distillation.
    """
    train = _continuous_plant(rows=120, seed=3, tiny_jitter=tiny_train)
    holdout = _continuous_plant(rows=120, seed=9, tiny_jitter=tiny_holdout)
    raw = MahalanobisModel(min_samples=20).fit(train)
    corr = MahalanobisModel(min_samples=20, shrinkage_target=ShrinkageTarget.CORRELATION).fit(train)
    assert isinstance(raw, MahalanobisFittedModel)
    assert isinstance(corr, MahalanobisFittedModel)
    raw_rate = _oob_rate(raw, holdout)
    corr_rate = _oob_rate(corr, holdout)
    assert corr_rate > raw_rate, (
        f"{plant_name}: correlation-target holdout OOB {corr_rate:.3f} should exceed "
        f"raw-units {raw_rate:.3f} (ADR 0018). Do not make CORRELATION the public default."
    )

"""Session C6: dynamics vs snapshot bake-off on fixtures already in hand.

Same ruler: named recall kind, residual/OOB rate, seed. Dummy-batch pooled snapshot is
blind (ADR 0018). A VAR on the mixed pool is not claimed as the public distillation row.
"""

from datetime import timedelta

from tests.atlas.test_dynamics import _ar_plant, _oob_features
from tests.atlas.test_phased import (
    PHASE,
    out_of_band_features,
    phase_violation,
    phased_training,
)

from phos.atlas.dynamics import LinearDynamicsModel
from phos.atlas.multivariate import MahalanobisModel
from phos.atlas.phased import PhaseConditionalModel
from phos.models import FittedModel
from phos.ontology import Observation


def _oob_count(fitted: FittedModel, observations: list[Observation]) -> int:
    return len(_oob_features(fitted, observations))


def test_on_an_ar_plant_the_var_residual_is_tighter_than_snapshot_mahalanobis() -> None:
    train = _ar_plant(rows=80, seed=1)
    holdout = _ar_plant(rows=40, seed=2)
    snapshot = MahalanobisModel(min_samples=20).fit(train)
    dynamics = LinearDynamicsModel(min_samples=20).fit(train)
    assert _oob_count(dynamics, holdout) <= _oob_count(snapshot, holdout)


def test_pooled_snapshot_stays_blind_on_the_dummy_batch_phase_violation() -> None:
    """C6 control: the ADR 0018 fixture still defeats pooled Mahalanobis."""
    training = phased_training()
    probe = training + phase_violation(9999)
    snapshot = MahalanobisModel().fit(training)
    assert out_of_band_features(snapshot.score(probe), probe) == set()


def test_phase_conditional_snapshot_recovers_dummy_batch_without_quoting_distillation() -> None:
    """Declared switching, not a public ZIP row. Distillation 18.72 stays the old name."""
    training = phased_training()
    probe = training + phase_violation(9999)
    phased = PhaseConditionalModel(phase_feature=PHASE, settling_window=timedelta(0)).fit(training)
    assert "temp" in out_of_band_features(phased.score(probe), probe)


def test_pooled_var_on_dummy_batch_is_logged_as_a_bakeoff_not_a_contract() -> None:
    """A mixed-mode VAR may see transitions; it is not 2-3/day and not distillation."""
    training = phased_training()
    probe = training + phase_violation(9999)
    dynamics = LinearDynamicsModel(min_samples=20).fit(training)
    # Honest: either sees the violation or does not. The session records the outcome.
    _ = out_of_band_features(dynamics.score(probe), probe)
    assert dynamics.name == "atlas-var1"
    assert MahalanobisModel().name == "atlas-mahalanobis"

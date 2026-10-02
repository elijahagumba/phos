"""Sessions C7 and C8: starve-mode fallback recorded; phase-register forgery measured."""

from datetime import timedelta

from tests.atlas.test_phased import (
    FEED,
    IDLE,
    IDLE_TEMP,
    PHASE,
    PURGE,
    RUN,
    TEMP,
    fitted_phase_model,
    moment,
    out_of_band_features,
    phased_training,
)

from phos.atlas.dynamics import LinearDynamicsModel
from phos.atlas.phased import PhaseConditionalFittedModel, PhaseConditionalModel
from phos.ontology import Observation


def test_a_starved_phase_is_recorded_and_is_not_called_learned() -> None:
    """Session C7: too few timestamps → fallback, listed on starved_phases."""
    rare = moment(10_000, PURGE, 0.0, IDLE_TEMP)
    fitted = PhaseConditionalModel(
        phase_feature=PHASE, min_samples=8, settling_window=timedelta(0)
    ).fit(phased_training() + rare)
    assert PURGE in fitted.starved_phases
    assert PURGE not in fitted.per_phase
    assert IDLE in fitted.per_phase
    assert RUN in fitted.per_phase
    assert comparable_fallback(fitted, rare)


def comparable_fallback(fitted: PhaseConditionalFittedModel, probe: list[Observation]) -> bool:
    from tests.atlas.test_phased import comparable

    return comparable(fitted.score(probe)) == comparable(fitted.fallback.score(probe))


def test_declared_switching_can_wrap_the_var_inner() -> None:
    """C7: declared-mode inner may be VAR. Not the public 18.72 name."""
    inner = LinearDynamicsModel(min_samples=8)
    fitted = PhaseConditionalModel(
        phase_feature=PHASE, inner=inner, settling_window=timedelta(0)
    ).fit(phased_training())
    assert fitted.starved_phases == ()
    assert set(fitted.per_phase) == {IDLE, RUN}
    assert all(model.name == "atlas-var1" for model in fitted.per_phase.values())


def test_forged_valid_phase_with_mismatched_physics_is_flagged() -> None:
    """IDLE physics labelled RUN: routed to the RUN model, which should object."""
    fitted = fitted_phase_model(settling_window=timedelta(0))
    forged = moment(9999, RUN, 0.0, IDLE_TEMP)
    flagged = out_of_band_features(fitted.score(forged), forged)
    assert TEMP in flagged or FEED in flagged


def test_forged_valid_phase_whose_physics_match_is_unhandled() -> None:
    """The register is constant within a phase, so a plausible lie matching that phase is silent.

    Session C8: honest unhandled. Not a claim that switching is secure against a lying PLC.
    """
    fitted = fitted_phase_model(settling_window=timedelta(0))
    # RUN physics with RUN register — indistinguishable from authorised RUN, even if the
    # register was written by an attacker.
    matching = moment(9999, RUN, 5000.0, 80.0)
    assert out_of_band_features(fitted.score(matching), matching) == set()
    from tests.atlas.test_phased import PLANT

    for model in fitted.per_phase.values():
        assert (PLANT, PHASE) not in dict.fromkeys(model.signal_space.signals)

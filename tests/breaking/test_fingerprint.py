"""The classifier that decides which detection results may be reported as clean."""

import pytest
from tests.breaking.conftest import ground_truth

from phos.breaking import (
    FALSIFIED_READING_TYPES,
    FingerprintStatus,
    assess_fingerprint,
)
from phos.synth import PlantDescription
from phos.synth.attacks import AttackType


def test_falsified_sensor_reading_is_caveated(plant: PlantDescription) -> None:
    assessment = assess_fingerprint(ground_truth("a", AttackType.LIAR, targets=("level_m",)), plant)
    assert assessment.status is FingerprintStatus.CAVEATED
    assert not assessment.is_clean
    assert assessment.drifting_targets == {"level_m": 0.02}


def test_correlation_break_on_a_drifting_sensor_is_caveated(plant: PlantDescription) -> None:
    assessment = assess_fingerprint(
        ground_truth("a", AttackType.CORRELATION_BREAK, targets=("level_m",)), plant
    )
    assert assessment.status is FingerprintStatus.CAVEATED


def test_actuator_attacks_are_clean_because_the_plant_senses_them_honestly(
    plant: PlantDescription,
) -> None:
    for attack_type in (AttackType.BLATANT, AttackType.STEALTH_DRIFT):
        assessment = assess_fingerprint(
            ground_truth("a", attack_type, targets=("pump_pct",)), plant
        )
        assert assessment.status is FingerprintStatus.CLEAN
        assert not assessment.falsifies_reading
        assert assessment.drifting_targets == {}


def test_stealth_drift_is_clean_even_though_the_part_expected_otherwise(
    plant: PlantDescription,
) -> None:
    """The PART named STEALTH_DRIFT as the fingerprinted case; D2's record says otherwise.

    A stealth drift moves an actuator and the plant senses the consequence through its ordinary
    path, drift included. Being *hard to see* is not the same property as *leaving a tell*, and
    caveating it anyway would bury the two genuinely contaminated rows among clean ones.
    """
    assessment = assess_fingerprint(
        ground_truth("a", AttackType.STEALTH_DRIFT, targets=("pump_pct",)), plant
    )
    assert assessment.status is FingerprintStatus.CLEAN


def test_setpoint_attacks_are_clean_because_a_setpoint_declares_no_drift(
    plant: PlantDescription,
) -> None:
    for attack_type in (AttackType.MIMIC, AttackType.ROGUE_COMMAND, AttackType.MIMIC_COMMAND):
        assessment = assess_fingerprint(
            ground_truth("a", attack_type, targets=("level_setpoint_m",), issuer="dev-1"),
            plant,
        )
        assert assessment.status is FingerprintStatus.CLEAN
        assert assessment.falsifies_reading
        assert "no target declares calibration drift" in assessment.reason


def test_falsifying_a_driftless_sensor_is_clean(plant: PlantDescription) -> None:
    """The rule turns on the declared drift, not on the signal's kind."""
    assessment = assess_fingerprint(
        ground_truth("a", AttackType.LIAR, targets=("steady_sensor",)), plant
    )
    assert assessment.status is FingerprintStatus.CLEAN
    assert assessment.falsifies_reading


def test_artefact_strength_falls_as_subtlety_rises(plant: PlantDescription) -> None:
    """The residual is worst where the attack is most obvious, which is how it must be read."""
    blatant = assess_fingerprint(ground_truth("a", AttackType.LIAR, subtlety=0.0), plant)
    invisible = assess_fingerprint(ground_truth("b", AttackType.LIAR, subtlety=0.99), plant)
    assert blatant.artefact_strength == pytest.approx(1.0)
    assert invisible.artefact_strength == pytest.approx(0.01)


def test_an_unknown_target_is_refused_rather_than_stamped_clean(plant: PlantDescription) -> None:
    with pytest.raises(KeyError):
        assess_fingerprint(ground_truth("a", AttackType.LIAR, targets=("nope",)), plant)


def test_falsified_reading_types_are_exactly_the_reading_manipulations() -> None:
    """Guards the mapping this module reads off D2's library, so a new type cannot slip past."""
    assert FALSIFIED_READING_TYPES == {
        AttackType.CORRELATION_BREAK,
        AttackType.LIAR,
        AttackType.MIMIC,
        AttackType.ROGUE_COMMAND,
        AttackType.MIMIC_COMMAND,
    }
    assert AttackType.BLATANT not in FALSIFIED_READING_TYPES
    assert AttackType.STEALTH_DRIFT not in FALSIFIED_READING_TYPES


def test_a_caveat_must_name_the_drift_that_justifies_it(plant: PlantDescription) -> None:
    """The flag and its evidence cannot disagree — the model refuses the incoherent pair."""
    from phos.breaking.fingerprint import FingerprintAssessment

    with pytest.raises(ValueError, match="incoherent"):
        FingerprintAssessment(
            attack_id="a",
            status=FingerprintStatus.CAVEATED,
            falsifies_reading=True,
            drifting_targets={},
            artefact_strength=1.0,
        )

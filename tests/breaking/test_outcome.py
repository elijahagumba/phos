"""The two result vocabularies, and the boundary that keeps them apart."""

import pytest
from tests.breaking.conftest import ground_truth

from phos.breaking import FingerprintStatus, assess_fingerprint
from phos.breaking.outcome import (
    AttackOutcome,
    DetectionVerdict,
    RobustnessOutcome,
    RobustnessVerdict,
)
from phos.breaking.truth import SignalExcursion, TrueStateVerdict
from phos.synth import PlantDescription
from phos.synth.attacks import AttackType, DifficultyLevel


def outcome(
    plant: PlantDescription,
    *,
    detected: bool,
    dangerous: bool = False,
    subtlety: float = 0.5,
    attack_type: AttackType = AttackType.LIAR,
    targets: tuple[str, ...] = ("level_m",),
    latency_seconds: float | None = None,
) -> AttackOutcome:
    """Assemble one outcome without running anything."""
    truth = ground_truth("a", attack_type, subtlety=subtlety, targets=targets)
    excursions: tuple[SignalExcursion, ...] = ()
    if dangerous:
        excursions = (
            SignalExcursion(
                signal="level_m",
                envelope_low=0.0,
                envelope_high=10.0,
                window_low=10.0,
                window_high=40.0,
                excess=30.0,
                margin=0.03,
            ),
        )
    return AttackOutcome(
        attack_id="a",
        attack_type=attack_type,
        subtlety=subtlety,
        difficulty=DifficultyLevel.for_subtlety(subtlety),
        corpus="fixture",
        detected=detected,
        n_alerts=1 if detected else 0,
        latency_seconds=latency_seconds if detected else None,
        fingerprint=assess_fingerprint(truth, plant),
        true_state=TrueStateVerdict(
            attack_id="a",
            dangerous=dangerous,
            excursions=excursions,
            peak_excess=30.0 if dangerous else 0.0,
            peak_signal="level_m" if dangerous else "",
        ),
    )


def test_a_detected_attack_is_caught(plant: PlantDescription) -> None:
    assert outcome(plant, detected=True).verdict is DetectionVerdict.CAUGHT


def test_a_quiet_atlas_on_a_calm_plant_is_an_ordinary_miss(plant: PlantDescription) -> None:
    result = outcome(plant, detected=False)
    assert result.verdict is DetectionVerdict.MISSED
    assert result.is_miss


def test_atlas_silent_while_the_true_state_went_dangerous_is_a_miss(
    plant: PlantDescription,
) -> None:
    """The acceptance case: all-clear over a plant that really was driven into danger."""
    result = outcome(plant, detected=False, dangerous=True)
    assert result.verdict is DetectionVerdict.MISSED_DANGEROUS
    assert result.is_miss


def test_a_dangerous_verdict_does_not_downgrade_a_real_catch(plant: PlantDescription) -> None:
    result = outcome(plant, detected=True, dangerous=True)
    assert result.verdict is DetectionVerdict.CAUGHT
    assert not result.is_miss


def test_the_zero_magnitude_control_is_neither_caught_nor_missed(
    plant: PlantDescription,
) -> None:
    result = outcome(plant, detected=False, dangerous=True, subtlety=1.0)
    assert result.is_inert
    assert result.verdict is DetectionVerdict.INERT
    assert not result.is_miss


def test_a_detection_on_the_inert_control_is_visible_rather_than_swallowed(
    plant: PlantDescription,
) -> None:
    """An alert on a manipulation of exactly zero magnitude is a leaked fingerprint."""
    result = outcome(plant, detected=True, subtlety=1.0)
    assert result.verdict is DetectionVerdict.INERT
    assert result.detected


def test_an_outcome_cannot_claim_a_detection_without_an_alert(plant: PlantDescription) -> None:
    truth = ground_truth("a", AttackType.LIAR)
    with pytest.raises(ValueError, match="incoherent"):
        AttackOutcome(
            attack_id="a",
            attack_type=AttackType.LIAR,
            subtlety=0.0,
            difficulty=DifficultyLevel.OBVIOUS,
            detected=True,
            n_alerts=0,
            fingerprint=assess_fingerprint(truth, plant),
            true_state=TrueStateVerdict(attack_id="a", dangerous=False),
        )


def test_an_undetected_window_cannot_carry_a_latency(plant: PlantDescription) -> None:
    truth = ground_truth("a", AttackType.LIAR)
    with pytest.raises(ValueError, match="cannot have one"):
        AttackOutcome(
            attack_id="a",
            attack_type=AttackType.LIAR,
            subtlety=0.0,
            difficulty=DifficultyLevel.OBVIOUS,
            detected=False,
            n_alerts=0,
            latency_seconds=12.0,
            fingerprint=assess_fingerprint(truth, plant),
            true_state=TrueStateVerdict(attack_id="a", dangerous=False),
        )


def test_latency_is_available_as_a_duration(plant: PlantDescription) -> None:
    result = outcome(plant, detected=True, latency_seconds=90.0)
    assert result.latency is not None
    assert result.latency.total_seconds() == 90.0
    assert outcome(plant, detected=False).latency is None


def test_clean_and_caveated_results_are_distinguishable(plant: PlantDescription) -> None:
    caveated = outcome(plant, detected=True, targets=("level_m",))
    clean = outcome(plant, detected=True, attack_type=AttackType.BLATANT, targets=("pump_pct",))
    assert not caveated.is_clean_evidence
    assert caveated.fingerprint.status is FingerprintStatus.CAVEATED
    assert clean.is_clean_evidence


def test_a_robustness_outcome_carries_nothing_about_detection() -> None:
    """The boundary D2 draws with a missing `interval()`, kept on the results side."""
    result = RobustnessOutcome(
        attack_id="h1",
        attack_type=AttackType.MALFORMED_RECORD,
        verdict=RobustnessVerdict.REFUSED,
        error_type="ParserError",
        detail="the adapter refused the file",
    )
    for forbidden in (
        "detected",
        "latency_seconds",
        "verdict_detection",
        "fingerprint",
        "subtlety",
    ):
        assert forbidden not in type(result).model_fields
    assert not hasattr(result, "interval")
    assert not hasattr(result, "is_miss")
    assert result.is_safe


def test_a_crash_is_the_only_unsafe_robustness_outcome() -> None:
    crashed = RobustnessOutcome(
        attack_id="h1",
        attack_type=AttackType.TRUNCATED,
        verdict=RobustnessVerdict.CRASHED,
        error_type="IndexError",
    )
    assert not crashed.is_safe
    completed = RobustnessOutcome(
        attack_id="h2",
        attack_type=AttackType.POISONED_BASELINE,
        verdict=RobustnessVerdict.COMPLETED,
    )
    assert completed.is_safe


def test_a_failure_must_name_its_exception() -> None:
    with pytest.raises(ValueError, match="naming the exception"):
        RobustnessOutcome(
            attack_id="h1",
            attack_type=AttackType.TRUNCATED,
            verdict=RobustnessVerdict.CRASHED,
        )


def test_an_input_hostile_type_cannot_be_recorded_as_a_detection_outcome() -> None:
    """D2 refuses it at ground truth, so an `AttackOutcome` for one cannot be built at all."""
    from tests.breaking.conftest import RUN_START

    from phos.synth.attacks import AttackGroundTruth

    with pytest.raises(ValueError, match="input-hostile"):
        AttackGroundTruth(
            attack_id="h1",
            type=AttackType.MALFORMED_RECORD,
            subtlety=0.0,
            started_at=RUN_START,
            ended_at=RUN_START,
        )

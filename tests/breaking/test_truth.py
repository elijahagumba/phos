"""Judging what the plant really did, from D1's record rather than from falsified readings."""

import pytest
from tests.breaking.conftest import ground_truth, true_state_record

from phos.breaking.truth import (
    DEFAULT_DANGER_MARGIN,
    TrueStateRecord,
    attack_windows_of,
    judge_true_state,
    load_true_state,
)
from phos.synth import PlantDescription
from phos.synth.attacks import AttackType

# Forty-eight samples at half-hourly steps: hours 0-24 of the fixture run. An attack declared at
# hour 1 for two hours therefore covers samples 2..6 inclusive.
CALM = [10.0] * 48


def test_a_calm_plant_is_not_dangerous(plant: PlantDescription) -> None:
    truth = ground_truth("a", AttackType.LIAR, targets=("level_m",))
    record = true_state_record({"level_m": CALM})
    verdict = judge_true_state(truth, record, plant, attack_windows_of([truth]))
    assert not verdict.dangerous
    assert verdict.excursions == ()


def test_a_liar_that_ran_the_true_state_away_is_dangerous(plant: PlantDescription) -> None:
    """The core case: the tank really overfilled, whatever the instruments said about it."""
    runaway = list(CALM)
    for index in range(2, 7):
        runaway[index] = 40.0
    truth = ground_truth("liar", AttackType.LIAR, targets=("level_m",))
    record = true_state_record({"level_m": runaway})

    verdict = judge_true_state(truth, record, plant, attack_windows_of([truth]))
    assert verdict.dangerous
    assert verdict.peak_signal == "level_m"
    assert verdict.peak_excess == pytest.approx(30.0)


def test_a_signal_the_attacker_held_directly_does_not_prove_danger(
    plant: PlantDescription,
) -> None:
    """An actuator driven by the attack left its envelope because the attack put it there."""
    driven = list(CALM)
    for index in range(2, 7):
        driven[index] = 90.0
    truth = ground_truth("blatant", AttackType.BLATANT, targets=("pump_pct",))
    record = true_state_record({"pump_pct": driven})

    verdict = judge_true_state(truth, record, plant, attack_windows_of([truth]))
    assert not verdict.dangerous
    assert verdict.excursions[0].driven
    assert verdict.excursions[0].excess == pytest.approx(80.0)


def test_a_consequence_of_a_driven_actuator_still_proves_danger(
    plant: PlantDescription,
) -> None:
    """Discounting the held signal must not discount what it did to the rest of the plant."""
    driven = list(CALM)
    consequence = list(CALM)
    for index in range(2, 7):
        driven[index] = 90.0
        consequence[index] = 25.0
    truth = ground_truth("blatant", AttackType.BLATANT, targets=("pump_pct",))
    record = true_state_record({"pump_pct": driven, "level_m": consequence})

    verdict = judge_true_state(truth, record, plant, attack_windows_of([truth]))
    assert verdict.dangerous
    assert verdict.peak_signal == "level_m"


def test_a_setpoint_written_by_a_rogue_command_is_discounted(plant: PlantDescription) -> None:
    written = list(CALM)
    for index in range(2, 7):
        written[index] = 55.0
    truth = ground_truth(
        "rogue", AttackType.ROGUE_COMMAND, targets=("level_setpoint_m",), issuer="dev-1"
    )
    record = true_state_record({"level_setpoint_m": written})

    verdict = judge_true_state(truth, record, plant, attack_windows_of([truth]))
    assert not verdict.dangerous


def test_the_margin_is_measured_in_the_signals_own_noise(plant: PlantDescription) -> None:
    """A hair past the envelope is the tail of ordinary operation, not a new regime."""
    nudged = list(CALM)
    nudged[3] = 10.0 + 2.0 * 0.01  # two noise stddevs past the envelope; margin is three
    truth = ground_truth("a", AttackType.LIAR, targets=("level_m",))
    record = true_state_record({"level_m": nudged})

    assert not judge_true_state(truth, record, plant, attack_windows_of([truth])).dangerous
    assert judge_true_state(
        truth, record, plant, attack_windows_of([truth]), margin_noises=1.0
    ).dangerous


def test_other_attack_windows_are_excluded_from_the_envelope(plant: PlantDescription) -> None:
    """One attack must not widen the envelope another is judged against."""
    values = list(CALM)
    for index in range(2, 7):
        values[index] = 40.0
    for index in range(20, 25):
        values[index] = 40.0
    judged = ground_truth("first", AttackType.LIAR, targets=("level_m",))
    other = ground_truth("second", AttackType.LIAR, targets=("level_m",), start_hours=10.0)
    record = true_state_record({"level_m": values})

    with_other_excluded = judge_true_state(
        judged, record, plant, attack_windows_of([judged, other])
    )
    assert with_other_excluded.dangerous

    # Forget the second window and its 40.0 samples join the envelope, hiding the first.
    forgetting = judge_true_state(judged, record, plant, attack_windows_of([judged]))
    assert not forgetting.dangerous


def test_a_negative_margin_is_refused(plant: PlantDescription) -> None:
    truth = ground_truth("a", AttackType.LIAR)
    record = true_state_record({"level_m": CALM})
    with pytest.raises(ValueError, match="must not be negative"):
        judge_true_state(truth, record, plant, attack_windows_of([truth]), margin_noises=-1.0)


def test_a_ragged_record_is_refused() -> None:
    from datetime import timedelta

    from tests.breaking.conftest import RUN_START

    with pytest.raises(ValueError, match="ragged"):
        TrueStateRecord(
            timestamps=(RUN_START, RUN_START + timedelta(minutes=30)),
            values={"level_m": (1.0,)},
        )


def test_a_verdict_must_name_the_excursion_that_justifies_it() -> None:
    from phos.breaking.truth import TrueStateVerdict

    with pytest.raises(ValueError, match="incoherent"):
        TrueStateVerdict(attack_id="a", dangerous=True, excursions=())


def test_signals_the_plant_does_not_declare_are_ignored(plant: PlantDescription) -> None:
    """A truth record may carry a column the plant no longer declares; it is not judged."""
    truth = ground_truth("a", AttackType.LIAR, targets=("level_m",))
    record = true_state_record({"level_m": CALM, "retired_signal": [0.0] * 20 + [999.0] * 28})
    verdict = judge_true_state(truth, record, plant, attack_windows_of([truth]))
    assert not verdict.dangerous


def test_load_reads_a_truth_file(tmp_path: "object", plant: PlantDescription) -> None:
    from pathlib import Path

    assert isinstance(tmp_path, Path)
    path = tmp_path / "truth.csv"
    path.write_text(
        "timestamp,level_m\n"
        "2026-05-01T00:00:00+00:00,10.00000\n"
        "2026-05-01T00:00:30+00:00,10.50000\n",
        encoding="utf-8",
    )
    record = load_true_state(path)
    assert record.signals() == ("level_m",)
    assert record.values["level_m"] == (10.0, 10.5)


def test_a_truth_file_without_timestamps_is_refused(tmp_path: "object") -> None:
    from pathlib import Path

    assert isinstance(tmp_path, Path)
    path = tmp_path / "truth.csv"
    path.write_text("level_m\n10.0\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no 'timestamp' column"):
        load_true_state(path)


def test_a_truth_file_without_signals_is_refused(tmp_path: "object") -> None:
    from pathlib import Path

    assert isinstance(tmp_path, Path)
    path = tmp_path / "truth.csv"
    path.write_text("timestamp\n2026-05-01T00:00:00+00:00\n", encoding="utf-8")
    with pytest.raises(ValueError, match="records no true state"):
        load_true_state(path)


def test_the_default_margin_is_conservative() -> None:
    """Documented here so a change to it is a change a test notices."""
    assert DEFAULT_DANGER_MARGIN == 3.0

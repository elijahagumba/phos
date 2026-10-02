"""What an attack declares about itself, and the separations that cannot be undone by hand.

Two of these tests matter more than the rest. The first is that a type's flavour is derived from
the type and cannot be assigned, so an input-hostile case cannot be recorded as a plant attack by
anyone, including a careless caller. The second is that `HostileGroundTruth` has no method that
produces a `LabelledInterval` — the boundary is enforced by the absence of a road, not by a
convention someone has to remember.
"""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from phos.eval import LabelledInterval
from phos.synth.attacks.spec import (
    ATTACKS_ARE_OURS_CAVEAT,
    INPUT_HOSTILE_IS_NOT_SECURITY_CAVEAT,
    AttackFlavour,
    AttackGroundTruth,
    AttackPlan,
    AttackType,
    DifficultyLevel,
    HostileGroundTruth,
    HostilePlan,
    strength_of,
)

START = datetime(2026, 4, 1, tzinfo=UTC)


def a_plan(**overrides: object) -> AttackPlan:
    """Return a valid detection plan with the given fields replaced."""
    fields: dict[str, object] = {
        "attack_id": "wt-blatant",
        "type": AttackType.BLATANT,
        "subtlety": 0.0,
        "start_hours": 6.0,
        "duration_hours": 1.0,
        "target": "intake_pump_speed_pct",
    }
    fields.update(overrides)
    return AttackPlan.model_validate(fields)


def a_truth(**overrides: object) -> AttackGroundTruth:
    """Return a valid detection ground truth with the given fields replaced."""
    fields: dict[str, object] = {
        "attack_id": "wt-blatant",
        "type": AttackType.BLATANT,
        "subtlety": 0.0,
        "started_at": START,
        "ended_at": START + timedelta(hours=1),
        "target_signals": ("intake_pump_speed_pct",),
        "manipulation": "intake pump held 60% above what the level loop asked for",
        "physical_effect": True,
        "truth_departure": {"clearwell_level_m": 1.4},
        "report_departure": {"clearwell_level_m": 1.4},
    }
    fields.update(overrides)
    return AttackGroundTruth.model_validate(fields)


class TestFlavour:
    """The separation the whole PART rests on."""

    @pytest.mark.parametrize(
        "attack_type",
        [
            AttackType.BLATANT,
            AttackType.STEALTH_DRIFT,
            AttackType.CORRELATION_BREAK,
            AttackType.LIAR,
            AttackType.MIMIC,
            AttackType.ROGUE_COMMAND,
            AttackType.MIMIC_COMMAND,
        ],
    )
    def test_plant_facing_types_are_detection(self, attack_type: AttackType) -> None:
        assert attack_type.flavour is AttackFlavour.DETECTION

    @pytest.mark.parametrize(
        "attack_type",
        [
            AttackType.MALFORMED_RECORD,
            AttackType.OUT_OF_RANGE,
            AttackType.TRUNCATED,
            AttackType.POISONED_BASELINE,
        ],
    )
    def test_pipeline_facing_types_are_input_hostile(self, attack_type: AttackType) -> None:
        assert attack_type.flavour is AttackFlavour.INPUT_HOSTILE

    def test_every_type_has_exactly_one_flavour(self) -> None:
        assert {t.flavour for t in AttackType} == set(AttackFlavour)

    def test_a_ground_truth_flavour_cannot_be_assigned(self) -> None:
        truth = a_truth()
        assert truth.flavour is AttackFlavour.DETECTION
        # Derived from the type, so a caller who supplies a flavour is overruled rather than
        # believed. There is no input that produces a detection attack labelled input-hostile.
        forced = AttackGroundTruth.model_validate(
            {**truth.model_dump(), "flavour": AttackFlavour.INPUT_HOSTILE.value}
        )
        assert forced.flavour is AttackFlavour.DETECTION
        with pytest.raises(ValidationError):
            truth.flavour = AttackFlavour.INPUT_HOSTILE  # type: ignore[misc]

    def test_an_input_hostile_ground_truth_offers_no_route_to_an_attack_interval(self) -> None:
        hostile = HostileGroundTruth(
            attack_id="hostile-malformed",
            type=AttackType.MALFORMED_RECORD,
            description="12 rows given a non-numeric value",
            rows_affected=12,
        )
        assert hostile.flavour is AttackFlavour.INPUT_HOSTILE
        # The boundary is the absence of a road: a detection attack has this method and an
        # input-hostile case does not, so nothing hostile can reach a corpus's attack intervals.
        assert "interval" in dir(AttackGroundTruth)
        assert "interval" not in dir(HostileGroundTruth)
        assert isinstance(a_truth().interval(), LabelledInterval)

    def test_a_detection_ground_truth_yields_the_interval_that_labels_it(self) -> None:
        interval = a_truth().interval()
        assert interval.start == START
        assert interval.end == START + timedelta(hours=1)
        assert interval.label == "attack"
        assert interval.attack_type == AttackType.BLATANT.value


class TestDifficulty:
    """The dial, and the band names a report reads off it."""

    @pytest.mark.parametrize(
        ("subtlety", "level"),
        [
            (0.0, DifficultyLevel.OBVIOUS),
            (0.24, DifficultyLevel.OBVIOUS),
            (0.25, DifficultyLevel.MODERATE),
            (0.59, DifficultyLevel.MODERATE),
            (0.6, DifficultyLevel.SUBTLE),
            (0.89, DifficultyLevel.SUBTLE),
            (0.9, DifficultyLevel.NEAR_INVISIBLE),
            (1.0, DifficultyLevel.NEAR_INVISIBLE),
        ],
    )
    def test_a_subtlety_lands_in_its_band(self, subtlety: float, level: DifficultyLevel) -> None:
        assert DifficultyLevel.for_subtlety(subtlety) is level

    def test_the_bands_tile_the_dial(self) -> None:
        seen = {DifficultyLevel.for_subtlety(step / 200.0) for step in range(201)}
        assert seen == set(DifficultyLevel)

    def test_a_subtlety_outside_the_dial_is_refused(self) -> None:
        for outside in (-0.01, 1.01):
            with pytest.raises(ValueError, match="subtlety"):
                DifficultyLevel.for_subtlety(outside)

    def test_strength_is_the_complement_of_subtlety(self) -> None:
        assert strength_of(0.0) == 1.0
        assert strength_of(1.0) == 0.0
        assert strength_of(0.25) == 0.75

    def test_full_subtlety_gives_exactly_zero_strength(self) -> None:
        # Exactly zero, not nearly: the anti-fingerprint property is bit-identity, and a
        # strength of 1e-17 would multiply into a manipulation that is small but present.
        assert strength_of(1.0) == 0.0

    def test_a_ground_truth_reports_the_band_its_subtlety_falls_in(self) -> None:
        assert a_truth(subtlety=0.95).difficulty is DifficultyLevel.NEAR_INVISIBLE
        assert a_truth(subtlety=0.0).difficulty is DifficultyLevel.OBVIOUS


class TestAttackPlan:
    """A detection plan refuses to be half-specified."""

    def test_a_valid_plan_survives(self) -> None:
        assert a_plan().target == "intake_pump_speed_pct"

    def test_a_plan_is_frozen(self) -> None:
        with pytest.raises(ValidationError):
            a_plan().subtlety = 0.5  # type: ignore[misc]

    def test_a_plan_refuses_an_input_hostile_type(self) -> None:
        with pytest.raises(ValidationError, match="input-hostile"):
            a_plan(type=AttackType.MALFORMED_RECORD)

    def test_a_plan_refuses_a_subtlety_off_the_dial(self) -> None:
        for outside in (-0.1, 1.1):
            with pytest.raises(ValidationError):
                a_plan(subtlety=outside)

    def test_a_plan_refuses_a_window_that_covers_no_time(self) -> None:
        with pytest.raises(ValidationError):
            a_plan(duration_hours=0.0)

    def test_a_plan_refuses_a_start_before_the_run(self) -> None:
        with pytest.raises(ValidationError):
            a_plan(start_hours=-1.0)

    @pytest.mark.parametrize(
        "attack_type",
        [
            AttackType.BLATANT,
            AttackType.STEALTH_DRIFT,
            AttackType.CORRELATION_BREAK,
            AttackType.LIAR,
            AttackType.MIMIC,
        ],
    )
    def test_a_plant_attack_must_name_the_signal_it_manipulates(
        self, attack_type: AttackType
    ) -> None:
        with pytest.raises(ValidationError, match="target"):
            a_plan(type=attack_type, target="", reference="x")

    @pytest.mark.parametrize("attack_type", [AttackType.CORRELATION_BREAK, AttackType.LIAR])
    def test_the_types_that_need_a_second_signal_refuse_to_go_without_one(
        self, attack_type: AttackType
    ) -> None:
        with pytest.raises(ValidationError, match="reference"):
            a_plan(type=attack_type, reference="")

    @pytest.mark.parametrize("attack_type", [AttackType.MIMIC, AttackType.MIMIC_COMMAND])
    def test_a_mimic_must_name_the_benign_event_it_wears_as_a_disguise(
        self, attack_type: AttackType
    ) -> None:
        with pytest.raises(ValidationError, match="mimics"):
            a_plan(type=attack_type, issuer="hmi", mimics="")

    def test_a_mimic_carries_the_event_kind_it_imitates(self) -> None:
        assert a_plan(type=AttackType.MIMIC, mimics="level_setpoint_change").mimics == (
            "level_setpoint_change"
        )

    @pytest.mark.parametrize("attack_type", [AttackType.ROGUE_COMMAND, AttackType.MIMIC_COMMAND])
    def test_a_command_attack_must_name_the_device_that_issued_it(
        self, attack_type: AttackType
    ) -> None:
        with pytest.raises(ValidationError, match="issuer"):
            a_plan(type=attack_type, issuer="")

    def test_a_command_attack_carries_its_issuer(self) -> None:
        # The device it writes *to* is not configured: it is read off the plant's register map
        # from the target signal, so a plan cannot name an address nothing is exposed at.
        plan = a_plan(type=AttackType.ROGUE_COMMAND, issuer="scada")
        assert plan.issuer == "scada"

    def test_a_plan_computes_its_window_from_the_run_start(self) -> None:
        plan = a_plan(start_hours=6.0, duration_hours=1.5)
        window = plan.window(START)
        assert window.start == START + timedelta(hours=6)
        assert window.end == START + timedelta(hours=7.5)

    def test_a_plan_reports_the_band_it_sits_in(self) -> None:
        assert a_plan(subtlety=0.7).difficulty is DifficultyLevel.SUBTLE


class TestHostilePlan:
    """An input-hostile plan is a different type, so the two cannot be confused at the config."""

    def test_a_valid_plan_survives(self) -> None:
        plan = HostilePlan(
            attack_id="hostile-out-of-range",
            type=AttackType.OUT_OF_RANGE,
            fraction=0.01,
            target="clearwell_level_m",
        )
        assert plan.type.flavour is AttackFlavour.INPUT_HOSTILE

    def test_a_hostile_plan_refuses_a_detection_type(self) -> None:
        with pytest.raises(ValidationError, match="detection"):
            HostilePlan(attack_id="wrong", type=AttackType.LIAR, fraction=0.01)

    def test_a_hostile_plan_refuses_a_fraction_off_the_unit_interval(self) -> None:
        for outside in (-0.1, 1.1):
            with pytest.raises(ValidationError):
                HostilePlan(attack_id="x", type=AttackType.TRUNCATED, fraction=outside)

    @pytest.mark.parametrize("attack_type", [AttackType.OUT_OF_RANGE, AttackType.POISONED_BASELINE])
    def test_the_kinds_that_corrupt_a_column_must_name_it(self, attack_type: AttackType) -> None:
        with pytest.raises(ValidationError, match="target"):
            HostilePlan(attack_id="x", type=attack_type, fraction=0.01, target="")

    @pytest.mark.parametrize("attack_type", [AttackType.MALFORMED_RECORD, AttackType.TRUNCATED])
    def test_the_kinds_that_corrupt_the_file_need_no_column(self, attack_type: AttackType) -> None:
        assert HostilePlan(attack_id="x", type=attack_type, fraction=0.01).target == ""


class TestGroundTruth:
    """What a generated corpus records about each attack."""

    def test_a_ground_truth_is_frozen(self) -> None:
        with pytest.raises(ValidationError):
            a_truth().subtlety = 0.5  # type: ignore[misc]

    def test_a_ground_truth_refuses_an_inverted_window(self) -> None:
        with pytest.raises(ValidationError, match="inverted"):
            a_truth(started_at=START + timedelta(hours=2), ended_at=START)

    def test_a_ground_truth_round_trips_through_json(self) -> None:
        truth = a_truth()
        assert AttackGroundTruth.model_validate_json(truth.model_dump_json()) == truth

    def test_the_serialised_form_carries_the_flavour_for_a_reader_of_the_manifest(self) -> None:
        assert '"flavour":"DETECTION"' in a_truth().model_dump_json().replace(" ", "")

    def test_the_largest_departure_is_the_headline_a_report_quotes(self) -> None:
        truth = a_truth(truth_departure={"a": 0.2, "b": 1.4, "c": 0.9})
        assert truth.peak_truth_departure() == pytest.approx(1.4)

    def test_an_attack_that_moved_nothing_reports_a_peak_of_zero(self) -> None:
        assert a_truth(truth_departure={}).peak_truth_departure() == 0.0

    def test_a_hostile_ground_truth_round_trips_through_json(self) -> None:
        hostile = HostileGroundTruth(
            attack_id="h", type=AttackType.TRUNCATED, description="tail removed", rows_affected=40
        )
        assert HostileGroundTruth.model_validate_json(hostile.model_dump_json()) == hostile


class TestCaveats:
    """The two sentences that have to travel with any number measured on this data."""

    def test_the_standing_caveat_says_the_attacks_are_ours(self) -> None:
        assert "imagination" in ATTACKS_ARE_OURS_CAVEAT
        assert "fingerprint" in ATTACKS_ARE_OURS_CAVEAT

    def test_the_input_hostile_caveat_refuses_the_security_claim(self) -> None:
        assert "not evidence" in INPUT_HOSTILE_IS_NOT_SECURITY_CAVEAT
        assert "deployment" in INPUT_HOSTILE_IS_NOT_SECURITY_CAVEAT


class TestTheGuardsThatCannotBeReachedByAConfig:
    """Refusals that protect a caller constructing these types directly rather than from TOML."""

    def test_a_strength_off_the_dial_is_refused(self) -> None:
        for outside in (-0.01, 1.01):
            with pytest.raises(ValueError, match="subtlety"):
                strength_of(outside)

    def test_an_input_hostile_type_cannot_be_recorded_as_a_detection_attack(self) -> None:
        # Unreachable from an AttackPlan, which refuses the type earlier. Guarded anyway, because
        # ground truth is also assembled in code and this is the last place to catch the mix-up.
        with pytest.raises(ValidationError, match="cannot be recorded as a detection attack"):
            a_truth(type=AttackType.TRUNCATED)

    def test_a_detection_type_cannot_be_recorded_as_input_hostile(self) -> None:
        with pytest.raises(ValidationError, match="cannot be recorded as input-hostile"):
            HostileGroundTruth(attack_id="x", type=AttackType.LIAR, description="wrong")

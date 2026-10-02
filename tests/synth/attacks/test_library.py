"""Staging an attack against a real plant, and every construction the library refuses.

The refusals carry as much weight as the constructions. An attack the library built anyway — a
correlation break on a relation the plant never declared, a mimic of an event that never happens, a
rogue command from the device that legitimately issues them — would be labelled in ground truth as
something it is not, and D3 would then measure Atlas against a lie.
"""

from datetime import timedelta

import pytest
from tests.synth.attacks.conftest import (
    BACKWASH,
    CHLORINE_DOSE,
    CLEARWELL_LEVEL,
    DISTRIBUTION_FLOW,
    INTAKE_SPEED,
    LEVEL_SETPOINT,
    LEVEL_SETPOINT_CHANGE,
    RAW_INFLOW,
    RESIDUAL_SETPOINT,
    a_spec,
)

from phos.synth import PlantRun, RunSpec, register_count, run_plant
from phos.synth.attacks.library import NormalReference, StagedAttack, stage_attack
from phos.synth.attacks.manipulations import (
    ActuatorOffset,
    ActuatorRamp,
    ReadingBlend,
    ReadingTrack,
)
from phos.synth.attacks.spec import AttackPlan, AttackType
from phos.synth.plant import CommandKind

# 02:00 to 05:00 — after the genuine level setpoint change at 01:00 and well before the residual
# one at 08:50, so nothing legitimate writes the setpoint an attack here is holding.
QUIET_START = 2.0
QUIET_HOURS = 3.0


def plan(**overrides: object) -> AttackPlan:
    """Return a plan in the quiet window with the given fields replaced."""
    fields: dict[str, object] = {
        "attack_id": "test",
        "type": AttackType.BLATANT,
        "subtlety": 0.0,
        "start_hours": QUIET_START,
        "duration_hours": QUIET_HOURS,
        "target": INTAKE_SPEED,
    }
    fields.update(overrides)
    return AttackPlan.model_validate(fields)


def staged(against: NormalReference, **overrides: object) -> StagedAttack:
    """Stage a plan against a reference run.

    The first parameter is deliberately not called ``reference``: ``reference`` is also the name
    of an `AttackPlan` field, and a keyword override of it would collide with the positional.
    """
    return stage_attack(plan(**overrides), against)


class TestNormalReference:
    """What the library is allowed to know about normal before it builds anything."""

    def test_it_carries_the_whole_reported_series(
        self, reference: NormalReference, clean_run: PlantRun
    ) -> None:
        assert reference.series(CLEARWELL_LEVEL) == tuple(clean_run.reported(CLEARWELL_LEVEL))

    def test_it_summarises_a_signal_the_way_the_run_does(
        self, reference: NormalReference, clean_run: PlantRun
    ) -> None:
        series = clean_run.reported(INTAKE_SPEED)
        assert reference.lowest(INTAKE_SPEED) == pytest.approx(min(series))
        assert reference.highest(INTAKE_SPEED) == pytest.approx(max(series))
        assert reference.mean(INTAKE_SPEED) == pytest.approx(sum(series) / len(series))

    def test_an_unknown_signal_is_refused(self, reference: NormalReference) -> None:
        with pytest.raises(KeyError, match="ghost"):
            reference.series("ghost")

    def test_it_reads_a_clock_back_to_a_sample_index(self, reference: NormalReference) -> None:
        assert reference.step_index(reference.spec.start) == 0
        assert reference.step_index(reference.spec.start + timedelta(minutes=30)) == 60

    def test_a_clock_before_the_run_is_refused(self, reference: NormalReference) -> None:
        with pytest.raises(ValueError, match="outside the run"):
            reference.step_index(reference.spec.start - timedelta(minutes=1))

    def test_a_clock_after_the_run_is_refused(self, reference: NormalReference) -> None:
        with pytest.raises(ValueError, match="outside the run"):
            reference.step_index(reference.spec.start + timedelta(hours=13))

    def test_it_knows_which_devices_legitimately_write(self, reference: NormalReference) -> None:
        # The works' operator HMI writes setpoints; the SCADA server only polls.
        assert reference.write_issuers == frozenset({"hmi"})

    def test_it_knows_which_benign_events_the_run_contained(
        self, reference: NormalReference
    ) -> None:
        assert reference.has_event(LEVEL_SETPOINT_CHANGE)
        assert reference.has_event(BACKWASH)
        assert not reference.has_event("nothing_of_the_sort")

    def test_it_knows_which_signals_an_event_kind_changes(self, reference: NormalReference) -> None:
        assert reference.event_touches(LEVEL_SETPOINT_CHANGE) == frozenset({LEVEL_SETPOINT})
        assert reference.event_touches(BACKWASH) == frozenset()

    def test_a_setpoint_change_counts_even_where_no_wire_carries_it(self) -> None:
        # The batch reactor has no control network. Its recipe changes move a setpoint and put
        # nothing on any wire, and they are still setpoint changes a mimic can hide among.
        batch = NormalReference.of(run_plant("batch-reactor", a_spec(hours=6.0)))
        assert "reactor_temp_setpoint_c" in batch.event_touches("recipe_change")
        assert batch.write_issuers == frozenset()

    def test_a_plant_with_no_network_has_no_legitimate_writers(self) -> None:
        batch = NormalReference.of(run_plant("batch-reactor", a_spec(hours=6.0)))
        assert batch.write_issuers == frozenset()


class TestBlatant:
    """The control case at the easy end of the dial."""

    def test_it_pushes_the_actuator_the_controller_was_driving(
        self, reference: NormalReference
    ) -> None:
        attack = staged(reference)
        assert isinstance(attack.injection, ActuatorOffset)
        assert attack.injection.actuator == INTAKE_SPEED
        assert attack.target_signals == (INTAKE_SPEED,)

    def test_it_pushes_toward_whichever_end_of_travel_has_room(
        self, reference: NormalReference
    ) -> None:
        # The intake pump sits at 64% on average, so there is more travel below it than above.
        attack = staged(reference)
        assert isinstance(attack.injection, ActuatorOffset)
        assert attack.injection.offset < 0.0

    def test_a_dosing_actuator_that_normally_sits_low_is_pushed_up(
        self, reference: NormalReference
    ) -> None:
        attack = staged(reference, target=CHLORINE_DOSE)
        assert isinstance(attack.injection, ActuatorOffset)
        assert attack.injection.offset > 0.0

    def test_subtlety_shrinks_the_push_to_nothing(self, reference: NormalReference) -> None:
        offsets = []
        for subtlety in (0.0, 0.5, 0.9, 1.0):
            attack = staged(reference, subtlety=subtlety)
            assert isinstance(attack.injection, ActuatorOffset)
            offsets.append(abs(attack.injection.offset))
        assert offsets == sorted(offsets, reverse=True)
        assert offsets[-1] == 0.0

    def test_it_stays_inside_the_actuator_travel(self, reference: NormalReference) -> None:
        attack = staged(reference)
        assert isinstance(attack.injection, ActuatorOffset)
        assert (attack.injection.low, attack.injection.high) == (0.0, 100.0)

    def test_a_signal_no_controller_drives_is_refused(self, reference: NormalReference) -> None:
        with pytest.raises(ValueError, match="actuator"):
            staged(reference, target=CLEARWELL_LEVEL)

    def test_it_puts_nothing_on_the_wire(self, reference: NormalReference) -> None:
        assert staged(reference).commands == ()


class TestStealthDrift:
    """Small enough to pass as drift, and the sum of it is not small."""

    def test_it_walks_the_actuator_across_the_window(self, reference: NormalReference) -> None:
        attack = staged(reference, type=AttackType.STEALTH_DRIFT, target=CHLORINE_DOSE)
        assert isinstance(attack.injection, ActuatorRamp)
        assert attack.injection.actuator == CHLORINE_DOSE
        assert attack.injection.total_offset > 0.0

    def test_no_single_sample_carries_a_step_a_detector_could_see(
        self, reference: NormalReference
    ) -> None:
        attack = staged(reference, type=AttackType.STEALTH_DRIFT, target=CHLORINE_DOSE)
        assert isinstance(attack.injection, ActuatorRamp)
        samples = QUIET_HOURS * 3600.0 / reference.spec.interval_seconds
        per_step = abs(attack.injection.total_offset) / samples
        # The dose transmitter's own noise is 0.01 mg/L. Each increment sits under it, so no view
        # of normal built on how far one reading is from the last can see this happening.
        assert per_step < reference.description.signal(CHLORINE_DOSE).noise_stddev

    def test_subtlety_shrinks_the_walk_to_nothing(self, reference: NormalReference) -> None:
        totals = []
        for subtlety in (0.0, 0.5, 1.0):
            attack = staged(reference, type=AttackType.STEALTH_DRIFT, target=CHLORINE_DOSE)
            attack = staged(
                reference, type=AttackType.STEALTH_DRIFT, target=CHLORINE_DOSE, subtlety=subtlety
            )
            assert isinstance(attack.injection, ActuatorRamp)
            totals.append(abs(attack.injection.total_offset))
        assert totals == sorted(totals, reverse=True)
        assert totals[-1] == 0.0

    def test_a_signal_no_controller_drives_is_refused(self, reference: NormalReference) -> None:
        with pytest.raises(ValueError, match="actuator"):
            staged(reference, type=AttackType.STEALTH_DRIFT, target=RAW_INFLOW)


class TestCorrelationBreak:
    """Built from the plant's own declaration, or not built at all."""

    def test_it_breaks_a_relation_the_plant_declares(self, reference: NormalReference) -> None:
        attack = staged(
            reference,
            type=AttackType.CORRELATION_BREAK,
            target=RAW_INFLOW,
            reference=INTAKE_SPEED,
        )
        assert isinstance(attack.injection, ReadingBlend)
        assert attack.injection.signal == RAW_INFLOW
        assert "square root of intake pump speed" in attack.manipulation

    def test_it_reports_the_signal_at_its_own_normal_centre(
        self, reference: NormalReference
    ) -> None:
        attack = staged(
            reference,
            type=AttackType.CORRELATION_BREAK,
            target=RAW_INFLOW,
            reference=INTAKE_SPEED,
        )
        assert isinstance(attack.injection, ReadingBlend)
        assert attack.injection.target == pytest.approx(reference.mean(RAW_INFLOW))

    def test_whatever_it_reports_lies_inside_the_range_the_signal_normally_takes(
        self, reference: NormalReference
    ) -> None:
        # A blend between the measured value and the normal mean is a convex combination of two
        # values that were both inside the normal range, so it cannot leave it. That is what
        # makes this attack invisible to any per-signal view of normal.
        attack = staged(
            reference,
            type=AttackType.CORRELATION_BREAK,
            target=RAW_INFLOW,
            reference=INTAKE_SPEED,
        )
        assert isinstance(attack.injection, ReadingBlend)
        assert reference.lowest(RAW_INFLOW) <= attack.injection.target
        assert attack.injection.target <= reference.highest(RAW_INFLOW)

    def test_a_relation_the_plant_never_declared_is_refused(
        self, reference: NormalReference
    ) -> None:
        with pytest.raises(ValueError, match="declares no coupling"):
            staged(
                reference,
                type=AttackType.CORRELATION_BREAK,
                target=RAW_INFLOW,
                reference=DISTRIBUTION_FLOW,
            )

    def test_the_relation_must_run_the_way_round_the_plan_says(
        self, reference: NormalReference
    ) -> None:
        # Intake speed drives raw inflow, not the other way about.
        with pytest.raises(ValueError, match="declares no coupling"):
            staged(
                reference,
                type=AttackType.CORRELATION_BREAK,
                target=INTAKE_SPEED,
                reference=RAW_INFLOW,
            )

    def test_subtlety_weakens_the_break_to_nothing(self, reference: NormalReference) -> None:
        strengths = []
        for subtlety in (0.0, 0.4, 1.0):
            attack = staged(
                reference,
                type=AttackType.CORRELATION_BREAK,
                target=RAW_INFLOW,
                reference=INTAKE_SPEED,
                subtlety=subtlety,
            )
            assert isinstance(attack.injection, ReadingBlend)
            strengths.append(attack.injection.strength)
        assert strengths == sorted(strengths, reverse=True)
        assert strengths[-1] == 0.0


class TestLiar:
    """False data injection, built only where a control loop will believe it."""

    def test_it_quotes_the_falsified_reading_against_its_setpoint(
        self, reference: NormalReference
    ) -> None:
        attack = staged(
            reference, type=AttackType.LIAR, target=CLEARWELL_LEVEL, reference=LEVEL_SETPOINT
        )
        assert isinstance(attack.injection, ReadingTrack)
        assert attack.injection.signal == CLEARWELL_LEVEL
        assert attack.injection.reference == LEVEL_SETPOINT

    def test_it_reports_short_of_target_so_the_loop_over_corrects(
        self, reference: NormalReference
    ) -> None:
        attack = staged(
            reference, type=AttackType.LIAR, target=CLEARWELL_LEVEL, reference=LEVEL_SETPOINT
        )
        assert isinstance(attack.injection, ReadingTrack)
        assert attack.injection.offset < 0.0

    def test_it_is_refused_where_no_control_loop_would_believe_it(
        self, reference: NormalReference
    ) -> None:
        # Nothing on this plant controls on raw inflow against the level setpoint, so falsifying
        # it would move no plant, and calling that false data injection would overstate it.
        with pytest.raises(ValueError, match="no control loop"):
            staged(reference, type=AttackType.LIAR, target=RAW_INFLOW, reference=LEVEL_SETPOINT)

    def test_the_manipulation_names_the_loop_it_deceives(self, reference: NormalReference) -> None:
        attack = staged(
            reference, type=AttackType.LIAR, target=CLEARWELL_LEVEL, reference=LEVEL_SETPOINT
        )
        assert INTAKE_SPEED in attack.manipulation

    def test_subtlety_weakens_the_lie_to_nothing(self, reference: NormalReference) -> None:
        strengths = []
        for subtlety in (0.0, 0.5, 1.0):
            attack = staged(
                reference,
                type=AttackType.LIAR,
                target=CLEARWELL_LEVEL,
                reference=LEVEL_SETPOINT,
                subtlety=subtlety,
            )
            assert isinstance(attack.injection, ReadingTrack)
            strengths.append(attack.injection.strength)
        assert strengths == sorted(strengths, reverse=True)
        assert strengths[-1] == 0.0


class TestMimic:
    """A disguise that has to be of something the plant genuinely does."""

    def test_it_holds_the_setpoint_a_genuine_event_writes(self, reference: NormalReference) -> None:
        attack = staged(
            reference,
            type=AttackType.MIMIC,
            target=LEVEL_SETPOINT,
            mimics=LEVEL_SETPOINT_CHANGE,
        )
        assert isinstance(attack.injection, ReadingBlend)
        assert attack.injection.signal == LEVEL_SETPOINT

    def test_the_value_it_dials_in_is_one_the_setpoint_legitimately_took(
        self, reference: NormalReference
    ) -> None:
        attack = staged(
            reference,
            type=AttackType.MIMIC,
            target=LEVEL_SETPOINT,
            mimics=LEVEL_SETPOINT_CHANGE,
        )
        assert isinstance(attack.injection, ReadingBlend)
        assert reference.lowest(LEVEL_SETPOINT) <= attack.injection.target
        assert attack.injection.target <= reference.highest(LEVEL_SETPOINT)

    def test_an_event_the_plant_never_performs_cannot_be_mimicked(
        self, reference: NormalReference
    ) -> None:
        with pytest.raises(ValueError, match="never performed"):
            staged(reference, type=AttackType.MIMIC, target=LEVEL_SETPOINT, mimics="tuesday_ritual")

    def test_an_event_that_writes_something_else_cannot_be_mimicked(
        self, reference: NormalReference
    ) -> None:
        # A backwash is genuine, but it writes no setpoint, so a setpoint change is not what one
        # looks like and the disguise would be of nothing.
        with pytest.raises(ValueError, match="does not write"):
            staged(reference, type=AttackType.MIMIC, target=LEVEL_SETPOINT, mimics=BACKWASH)

    def test_a_signal_no_operator_can_write_is_refused(self, reference: NormalReference) -> None:
        with pytest.raises(ValueError, match="setpoint"):
            staged(
                reference,
                type=AttackType.MIMIC,
                target=CLEARWELL_LEVEL,
                mimics=LEVEL_SETPOINT_CHANGE,
            )

    def test_it_puts_nothing_on_the_wire(self, reference: NormalReference) -> None:
        # The whole point of the plain mimic: the setpoint moves and no operator wrote it. An
        # attacker at the PLC leaves the telemetry looking like an ordinary shift change and the
        # capture showing no write at all.
        attack = staged(
            reference,
            type=AttackType.MIMIC,
            target=LEVEL_SETPOINT,
            mimics=LEVEL_SETPOINT_CHANGE,
        )
        assert attack.commands == ()

    def test_it_refuses_a_window_a_genuine_write_falls_inside(
        self, reference: NormalReference
    ) -> None:
        # The genuine level setpoint change is at 01:00. An attack holding that setpoint across
        # it would leave "who moved this" with two answers.
        with pytest.raises(ValueError, match="genuine"):
            staged(
                reference,
                type=AttackType.MIMIC,
                target=LEVEL_SETPOINT,
                mimics=LEVEL_SETPOINT_CHANGE,
                start_hours=0.5,
                duration_hours=2.0,
            )


class TestCommandAttacks:
    """Traffic that is consistent with the plant it claims to have changed."""

    def rogue(self, reference: NormalReference, **overrides: object) -> StagedAttack:
        """Stage a rogue command from the SCADA server, which legitimately only polls."""
        fields: dict[str, object] = {
            "type": AttackType.ROGUE_COMMAND,
            "target": LEVEL_SETPOINT,
            "issuer": "scada",
        }
        fields.update(overrides)
        return staged(reference, **fields)

    def test_a_rogue_command_comes_from_a_device_that_never_writes(
        self, reference: NormalReference
    ) -> None:
        attack = self.rogue(reference)
        assert attack.commands
        assert {scheduled.intent.issuer for scheduled in attack.commands} == {"scada"}
        assert {scheduled.intent.kind for scheduled in attack.commands} == {CommandKind.WRITE}

    def test_a_rogue_command_from_the_silent_engineering_station_is_allowed(
        self, reference: NormalReference
    ) -> None:
        """A declared workstation that never talks is a rogue issuer, not a ghost."""
        attack = self.rogue(reference, issuer="engineering")
        assert {scheduled.intent.issuer for scheduled in attack.commands} == {"engineering"}
        assert "engineering" not in reference.write_issuers

    def test_a_rogue_command_from_the_device_that_legitimately_writes_is_refused(
        self, reference: NormalReference
    ) -> None:
        with pytest.raises(ValueError, match="legitimately writes"):
            self.rogue(reference, issuer="hmi")

    def test_a_mimic_command_must_come_from_the_device_that_legitimately_writes(
        self, reference: NormalReference
    ) -> None:
        with pytest.raises(ValueError, match="never writes"):
            staged(
                reference,
                type=AttackType.MIMIC_COMMAND,
                target=LEVEL_SETPOINT,
                issuer="scada",
                mimics=LEVEL_SETPOINT_CHANGE,
            )

    def test_a_mimic_command_wears_the_operator_device_and_a_genuine_event_shape(
        self, reference: NormalReference
    ) -> None:
        attack = staged(
            reference,
            type=AttackType.MIMIC_COMMAND,
            target=LEVEL_SETPOINT,
            issuer="hmi",
            mimics=LEVEL_SETPOINT_CHANGE,
        )
        assert {scheduled.intent.issuer for scheduled in attack.commands} == {"hmi"}
        assert isinstance(attack.injection, ReadingBlend)
        assert reference.lowest(LEVEL_SETPOINT) <= attack.injection.target
        assert attack.injection.target <= reference.highest(LEVEL_SETPOINT)

    def test_an_unknown_device_is_refused(self, reference: NormalReference) -> None:
        with pytest.raises(KeyError, match="ghost"):
            self.rogue(reference, issuer="ghost")

    def test_the_write_goes_to_the_address_the_register_map_exposes(
        self, reference: NormalReference
    ) -> None:
        attack = self.rogue(reference)
        node, address = reference.description.control_network.address_of(  # type: ignore[union-attr]
            LEVEL_SETPOINT
        )
        for scheduled in attack.commands:
            assert scheduled.intent.target == node
            assert scheduled.intent.address == address
            assert scheduled.intent.quantity == 1

    def test_the_value_written_is_the_value_the_setpoint_then_reads(
        self, reference: NormalReference
    ) -> None:
        # Wire and telemetry must agree exactly. A write that said one thing while the setpoint
        # read another would let a detector find the attack by the inconsistency between two
        # outputs of one run — a tell of how D2 assembled it, not of what the attacker did.
        attack = self.rogue(reference)
        assert isinstance(attack.injection, ReadingBlend)
        assert attack.injection.strength == 1.0
        expected = register_count(
            reference.description.signal(LEVEL_SETPOINT), attack.injection.target
        )
        assert {scheduled.intent.values for scheduled in attack.commands} == {(expected,)}

    def test_subtlety_shrinks_the_traffic_to_a_single_command(
        self, reference: NormalReference
    ) -> None:
        counts = [len(self.rogue(reference, subtlety=s).commands) for s in (0.0, 0.5, 1.0)]
        assert counts == sorted(counts, reverse=True)
        assert counts[-1] == 1

    def test_at_full_subtlety_the_only_thing_wrong_is_who_sent_it(
        self, reference: NormalReference
    ) -> None:
        # The floor of a command attack is not zero: a packet either exists or it does not. What
        # the dial reaches is one write, carrying the value the setpoint already had, from a
        # device that has no business sending it. The device identity is the irreducible tell.
        attack = self.rogue(reference, subtlety=1.0)
        assert isinstance(attack.injection, ReadingBlend)
        anchor = reference.at(LEVEL_SETPOINT, reference.step_index(attack.injection.window.start))
        assert attack.injection.target == anchor

    def test_subtlety_shrinks_the_value_departure_to_nothing(
        self, reference: NormalReference
    ) -> None:
        anchor_index = None
        departures = []
        for subtlety in (0.0, 0.5, 1.0):
            attack = self.rogue(reference, subtlety=subtlety)
            assert isinstance(attack.injection, ReadingBlend)
            anchor_index = reference.step_index(attack.injection.window.start)
            anchor = reference.at(LEVEL_SETPOINT, anchor_index)
            departures.append(abs(attack.injection.target - anchor))
        assert departures == sorted(departures, reverse=True)
        assert departures[-1] == 0.0

    def test_every_command_lands_inside_the_attack_window(self, reference: NormalReference) -> None:
        attack = self.rogue(reference)
        window = attack.plan.window(reference.spec.start)
        for scheduled in attack.commands:
            assert window.contains(reference.spec.instant(scheduled.step_index))

    def test_a_plant_with_no_control_network_cannot_carry_a_command_attack(self) -> None:
        batch = NormalReference.of(run_plant("batch-reactor", a_spec(hours=6.0)))
        with pytest.raises(ValueError, match="no control network"):
            stage_attack(
                AttackPlan(
                    attack_id="x",
                    type=AttackType.ROGUE_COMMAND,
                    subtlety=0.0,
                    start_hours=1.0,
                    duration_hours=1.0,
                    target="reactor_temp_setpoint_c",
                    issuer="scada",
                ),
                batch,
            )

    def test_a_signal_on_no_register_block_is_refused(self, reference: NormalReference) -> None:
        with pytest.raises(ValueError, match="setpoint"):
            self.rogue(reference, target=CLEARWELL_LEVEL)


class TestTheSharedContract:
    """What every staged attack carries, whatever type it is."""

    def all_types(self, reference: NormalReference) -> list[StagedAttack]:
        """Stage one attack of every detection type against the works."""
        return [
            staged(reference),
            staged(reference, type=AttackType.STEALTH_DRIFT, target=CHLORINE_DOSE),
            staged(
                reference,
                type=AttackType.CORRELATION_BREAK,
                target=RAW_INFLOW,
                reference=INTAKE_SPEED,
            ),
            staged(
                reference, type=AttackType.LIAR, target=CLEARWELL_LEVEL, reference=LEVEL_SETPOINT
            ),
            staged(
                reference,
                type=AttackType.MIMIC,
                target=LEVEL_SETPOINT,
                mimics=LEVEL_SETPOINT_CHANGE,
            ),
            staged(reference, type=AttackType.ROGUE_COMMAND, target=LEVEL_SETPOINT, issuer="scada"),
            staged(
                reference,
                type=AttackType.MIMIC_COMMAND,
                target=LEVEL_SETPOINT,
                issuer="hmi",
                mimics=LEVEL_SETPOINT_CHANGE,
            ),
        ]

    def test_every_detection_type_can_be_staged_against_the_works(
        self, reference: NormalReference
    ) -> None:
        assert len(self.all_types(reference)) == 7

    def test_every_staged_attack_says_what_it_did_in_words(
        self, reference: NormalReference
    ) -> None:
        for attack in self.all_types(reference):
            assert len(attack.manipulation) > 20
            assert attack.target_signals

    def test_every_staged_attack_is_reproducible(self, reference: NormalReference) -> None:
        first = self.all_types(reference)
        second = self.all_types(reference)
        assert [attack.injection for attack in first] == [attack.injection for attack in second]
        assert [attack.commands for attack in first] == [attack.commands for attack in second]

    def test_the_window_is_the_plan_s_window(self, reference: NormalReference) -> None:
        for attack in self.all_types(reference):
            expected = attack.plan.window(reference.spec.start)
            assert attack.window == expected

    def test_an_attack_reaching_past_the_end_of_the_run_is_refused(
        self, reference: NormalReference
    ) -> None:
        with pytest.raises(ValueError, match="outside the run"):
            staged(reference, start_hours=11.0, duration_hours=6.0)

    def test_a_target_the_plant_never_declared_is_refused(self, reference: NormalReference) -> None:
        with pytest.raises(KeyError, match="ghost"):
            staged(reference, target="ghost")


class TestAcrossPlants:
    """The library is declaration-driven, so it works on a plant it was not written against."""

    @pytest.fixture(scope="class")
    def power(self) -> NormalReference:
        """Six hours of the generating set."""
        return NormalReference.of(run_plant("power-generation", a_spec(hours=6.0)))

    def test_a_liar_stages_against_the_generating_set_s_own_control_loop(
        self, power: NormalReference
    ) -> None:
        attack = stage_attack(
            AttackPlan(
                attack_id="pg-liar",
                type=AttackType.LIAR,
                subtlety=0.2,
                start_hours=1.0,
                duration_hours=2.0,
                target="feeder_voltage_kv",
                reference="feeder_voltage_setpoint_kv",
            ),
            power,
        )
        assert isinstance(attack.injection, ReadingTrack)
        assert "tap_position" in attack.manipulation

    def test_a_correlation_break_stages_against_a_relation_that_plant_declares(
        self, power: NormalReference
    ) -> None:
        attack = stage_attack(
            AttackPlan(
                attack_id="pg-corr",
                type=AttackType.CORRELATION_BREAK,
                subtlety=0.0,
                start_hours=1.0,
                duration_hours=2.0,
                target="bus_frequency_hz",
                reference="turbine_speed_rpm",
            ),
            power,
        )
        assert isinstance(attack.injection, ReadingBlend)
        assert attack.injection.signal == "bus_frequency_hz"

    def test_a_relation_that_plant_does_not_declare_is_refused_there_too(
        self, power: NormalReference
    ) -> None:
        with pytest.raises(ValueError, match="declares no coupling"):
            stage_attack(
                AttackPlan(
                    attack_id="pg-nope",
                    type=AttackType.CORRELATION_BREAK,
                    subtlety=0.0,
                    start_hours=1.0,
                    duration_hours=2.0,
                    target="bus_frequency_hz",
                    reference="transformer_oil_temp_c",
                ),
                power,
            )


def test_a_reference_and_a_run_of_the_same_spec_agree(clean_run: PlantRun) -> None:
    """The reference is a view of the run, not a second simulation of it."""
    spec: RunSpec = clean_run.spec
    again = NormalReference.of(run_plant("water-treatment", spec))
    assert again.series(RESIDUAL_SETPOINT) == tuple(clean_run.reported(RESIDUAL_SETPOINT))

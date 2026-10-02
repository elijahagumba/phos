"""The command layer: writes that move the process, and an authorisation nobody can read off it.

Two properties carry this module, and both are about honesty rather than plumbing.

**A write causes something.** Before this layer a benign event moved a setpoint and the write was
echoed onto the wire afterwards, carrying the value the setpoint had already taken. Deleting the
capture changed nothing, which makes an attacker's writes cosmetic and a harness built on them a
harness that never exercised the physics. The test that matters is the counterfactual one: the
same run with the write removed reaches a different true state.

**The authorisation is not on the wire.** An authorised write and an unauthorised one are the same
bytes, because in a real plant they are. The label lives in the recorded ground truth, derived
from the plant's declared policy, and a test asserts the two captures are byte-identical so that
nothing downstream can separate them by reading a tell this generator left behind.

The fixture is deliberately the same toy tank `test_plant.py` uses, extended with a declared write
authority, so that what is under test is the base class's discipline and not a plant's physics.
"""

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta

import pytest
from numpy.random import Generator
from pydantic import ValidationError
from tests.synth.conftest import (
    INFLOW,
    LEVEL,
    PUMP,
    SETPOINT,
    START,
    TANK_AREA_M2,
    TANK_DESCRIPTION,
    description_with,
)

from phos.synth.command import (
    Authorisation,
    NoCommands,
    PlannedCommandSource,
    PlannedWrite,
    WriteAuthority,
)
from phos.synth.plant import (
    BenignEvent,
    CommandKind,
    Plant,
    PlantDescription,
    PlantStep,
    RunSpec,
    SignalKind,
)
from phos.synth.process import PiController, accumulate, square_law_flow
from phos.synth.traffic import TrafficPolicy, modbus_frames

OPERATOR = "hmi"
POLLER = "scada"
UNGRANTED = "plc"
"""A device the policy grants nothing. The tank fixture has no silent workstation, so the PLC
stands in: what matters here is that the writer holds no grant, not what its role string says."""

TANK_AUTHORITY = WriteAuthority(
    grants={OPERATOR: frozenset({SETPOINT}), POLLER: frozenset({SETPOINT})}
)
"""The permissive policy: HMI and SCADA may both write the setpoint."""

STRICT_AUTHORITY = WriteAuthority(grants={OPERATOR: frozenset({SETPOINT})})
"""The strict policy: only the HMI may. Differs from `TANK_AUTHORITY` in one grant."""


class CommandedTank(Plant):
    """The `test_plant.py` tank with a declared write authority and no benign events.

    Events are dropped so that every write in a run comes from the command source under test and
    a counterfactual run differs by exactly the command that was removed.
    """

    def _authority(self) -> WriteAuthority:
        """The policy this fixture declares. Overridden to vary policy and nothing else."""
        return TANK_AUTHORITY

    def __init__(self, spec: RunSpec, **kwargs: object) -> None:
        """Build the fixture. Keyword arguments are forwarded to `Plant`."""
        self._description = description_with(write_authority=self._authority().model_dump())
        self._loop = PiController(gain=25.0, integral_time_seconds=600.0, low=0.0, high=100.0)
        super().__init__(spec, **kwargs)  # type: ignore[arg-type]

    @property
    def description(self) -> PlantDescription:
        return self._description

    def initial_state(self) -> Mapping[str, float]:
        return {LEVEL: 3.0, INFLOW: 20.0, PUMP: 33.0, SETPOINT: 3.0, "demand_m3ph": 20.0}

    def schedule_events(self, rng: Generator, spec: RunSpec) -> Sequence[BenignEvent]:
        return ()

    def begin_event(self, event: BenignEvent) -> None:
        return None

    def control(
        self,
        report: Mapping[str, float],
        active: BenignEvent | None,
        elapsed_hours: float,
        dt_seconds: float,
    ) -> Mapping[str, float]:
        return {
            PUMP: self._loop.update(
                measurement=report[LEVEL],
                setpoint=report[SETPOINT],
                dt_seconds=dt_seconds,
                bias=33.0,
            )
        }

    def advance(
        self,
        state: Mapping[str, float],
        actuators: Mapping[str, float],
        active: BenignEvent | None,
        elapsed_hours: float,
        dt_seconds: float,
    ) -> Mapping[str, float]:
        inflow = square_law_flow(actuators[PUMP], 60.0)
        level = accumulate(
            state[LEVEL],
            rate_per_second=(inflow - 20.0) / TANK_AREA_M2 / 3600.0,
            dt_seconds=dt_seconds,
            low=0.0,
            high=6.0,
        )
        return {
            LEVEL: level,
            INFLOW: inflow,
            PUMP: actuators[PUMP],
            SETPOINT: state[SETPOINT],
            "demand_m3ph": 20.0,
        }


class StrictTank(CommandedTank):
    """The same tank, granting the poller nothing. Differs from `CommandedTank` in policy only."""

    def _authority(self) -> WriteAuthority:
        return STRICT_AUTHORITY


def spec(steps: int = 90, seed: int = 11) -> RunSpec:
    """Return a run spec covering ``steps`` one-minute samples."""
    return RunSpec(
        seed=seed,
        start=START,
        duration=timedelta(minutes=steps),
        sample_interval=timedelta(minutes=1),
    )


def write_at(step: int, issuer: str, value: float = 5.0) -> PlannedCommandSource:
    """Return a source performing one setpoint write, from ``issuer``, at ``step``."""
    return PlannedCommandSource(
        {step: (PlannedWrite(issuer=issuer, signal=SETPOINT, value=value, reason="fixture"),)}
    )


def run(source: object = None, *, steps: int = 90) -> list[PlantStep]:
    """Step a fresh commanded tank through a whole run."""
    plant = (
        CommandedTank(spec(steps), commands=source)
        if source is not None
        else CommandedTank(spec(steps))
    )
    return [plant.step() for _ in range(steps)]


class TestTheEmptyInletChangesNothing:
    """`NoCommands` must be the `NoInjection` of this layer: a real object, and no effect."""

    def test_no_source_and_an_empty_source_produce_identical_runs(self) -> None:
        absent = run()
        empty = run(NoCommands())
        assert [step.truth.values for step in absent] == [step.truth.values for step in empty]
        assert [step.report.values for step in absent] == [step.report.values for step in empty]

    def test_a_run_without_commands_records_no_issued_command(self) -> None:
        assert all(step.issued == () for step in run())

    def test_a_source_that_writes_nowhere_leaves_the_run_untouched(self) -> None:
        quiet = PlannedCommandSource({})
        assert [step.truth.values for step in run(quiet)] == [step.truth.values for step in run()]


class TestAWriteCausesSomething:
    """The property the whole layer exists for: the command moves the plant."""

    def test_a_setpoint_write_moves_the_recorded_true_setpoint(self) -> None:
        steps = run(write_at(10, OPERATOR, value=5.0))
        assert steps[9].truth.values[SETPOINT] == pytest.approx(3.0)
        assert steps[10].truth.values[SETPOINT] == pytest.approx(5.0)

    def test_removing_the_write_reaches_a_different_true_state(self) -> None:
        """The counterfactual. A cosmetic write would leave these two runs identical."""
        commanded = run(write_at(10, OPERATOR, value=5.0))
        untouched = run()
        assert commanded[-1].truth.values[LEVEL] != pytest.approx(untouched[-1].truth.values[LEVEL])

    def test_the_loop_follows_the_written_setpoint(self) -> None:
        """A write that moved a number but not the process passes the first test and fails this.

        The loop is asked for a higher level, so it opens the pump and the level climbs — both
        against the sample the write landed on and against the run where it never happened.
        """
        commanded = run(write_at(10, OPERATOR, value=5.0))
        untouched = run()
        assert commanded[20].truth.values[PUMP] > commanded[9].truth.values[PUMP]
        assert commanded[-1].truth.values[LEVEL] > commanded[10].truth.values[LEVEL]
        assert commanded[-1].truth.values[LEVEL] > untouched[-1].truth.values[LEVEL]

    def test_a_write_outside_the_span_is_clamped_and_the_clamping_is_recorded(self) -> None:
        steps = run(write_at(10, OPERATOR, value=99.0))
        issued = steps[10].issued[0]
        assert issued.requested == pytest.approx(99.0)
        assert issued.applied == pytest.approx(6.0)
        assert issued.was_clamped is True

    def test_an_unclamped_write_says_so(self) -> None:
        assert run(write_at(10, OPERATOR, value=5.0))[10].issued[0].was_clamped is False


class TestAuthorisationIsDerivedFromTheDeclaration:
    """A scenario must not be able to label its own command."""

    def test_the_granted_station_writes_authorised(self) -> None:
        assert run(write_at(10, OPERATOR))[10].issued[0].authorised is Authorisation.AUTHORISED

    def test_a_known_station_without_a_grant_writes_unauthorised(self) -> None:
        """The compromised legitimate host: on the graph it is familiar, in policy it is not."""
        plant = StrictTank(spec(20), commands=write_at(10, POLLER))
        steps = [plant.step() for _ in range(20)]
        assert steps[10].issued[0].authorised is Authorisation.UNAUTHORISED

    def test_a_silent_station_writes_unauthorised(self) -> None:
        assert run(write_at(10, UNGRANTED))[10].issued[0].authorised is Authorisation.UNAUTHORISED

    def test_the_planned_write_carries_no_authorisation_field(self) -> None:
        """Structural: if a source could state it, the label would restate the author's intent."""
        assert not hasattr(
            PlannedWrite(issuer=OPERATOR, signal=SETPOINT, value=1.0, reason=""), "authorised"
        )

    def test_authority_refuses_a_grant_that_permits_nothing(self) -> None:
        with pytest.raises(ValidationError, match="empty signal set"):
            WriteAuthority(grants={OPERATOR: frozenset()})

    def test_authority_reports_its_declared_writers(self) -> None:
        assert TANK_AUTHORITY.writers() == frozenset({OPERATOR, POLLER})
        assert STRICT_AUTHORITY.writers() == frozenset({OPERATOR})


class TestTheWireCannotTellThemApart:
    """The anti-fingerprint property for this layer, in the idiom ADR 0016 set."""

    def test_an_authorised_and_an_unauthorised_write_render_identical_frames(self) -> None:
        """Two plants differing only in their declared policy. Same issuer, same write, same bytes.

        This is the discriminating form. Comparing one run against itself would prove nothing;
        what has to hold is that flipping the *ground truth* leaves the capture untouched, so that
        no downstream reader can recover the label from the wire.
        """
        permissive = CommandedTank(spec(30), commands=write_at(10, POLLER))
        strict = StrictTank(spec(30), commands=write_at(10, POLLER))
        left = [permissive.step() for _ in range(30)]
        right = [strict.step() for _ in range(30)]

        assert left[10].issued[0].authorised is Authorisation.AUTHORISED
        assert right[10].issued[0].authorised is Authorisation.UNAUTHORISED

        frames = (
            modbus_frames(permissive.description, left, TrafficPolicy(seed=3)),
            modbus_frames(strict.description, right, TrafficPolicy(seed=3)),
        )
        assert [frame.payload for frame in frames[0]] == [frame.payload for frame in frames[1]]

    def test_the_issued_record_never_reaches_the_command_intent(self) -> None:
        step = run(write_at(10, UNGRANTED))[10]
        (intent,) = [item for item in step.commands if item.kind is CommandKind.WRITE]
        rendered = f"{intent.kind}{intent.issuer}{intent.target}{intent.address}{intent.values}"
        assert "AUTHORISED" not in rendered
        assert "UNAUTHORISED" not in rendered

    def test_the_write_appears_on_the_wire_as_an_ordinary_write(self) -> None:
        step = run(write_at(10, UNGRANTED))[10]
        writes = [item for item in step.commands if item.kind is CommandKind.WRITE]
        assert len(writes) == 1
        assert writes[0].issuer == UNGRANTED
        assert writes[0].quantity == 1


class TestTheRefusalsAreLoud:
    """Every one of these would otherwise be a command that silently did nothing."""

    def test_writing_a_sensor_is_refused(self) -> None:
        source = PlannedCommandSource(
            {5: (PlannedWrite(issuer=OPERATOR, signal=LEVEL, value=1.0, reason="x"),)}
        )
        with pytest.raises(ValueError, match="not a setpoint"):
            run(source)

    def test_writing_an_actuator_is_refused_and_points_at_the_injection_door(self) -> None:
        source = PlannedCommandSource(
            {5: (PlannedWrite(issuer=OPERATOR, signal=PUMP, value=1.0, reason="x"),)}
        )
        with pytest.raises(ValueError, match="actuator injection door"):
            run(source)

    def test_an_undeclared_signal_is_refused(self) -> None:
        source = PlannedCommandSource(
            {5: (PlannedWrite(issuer=OPERATOR, signal="nope", value=1.0, reason="x"),)}
        )
        with pytest.raises(KeyError, match="nope"):
            run(source)

    def test_an_issuer_that_is_not_on_the_network_is_refused(self) -> None:
        with pytest.raises(KeyError, match="ghost"):
            run(write_at(5, "ghost"))

    def test_a_plant_with_no_declared_authority_refuses_to_record_one(self) -> None:
        class Undeclared(CommandedTank):
            @property
            def description(self) -> PlantDescription:
                return TANK_DESCRIPTION

        plant = Undeclared(spec(20), commands=write_at(5, OPERATOR))
        with pytest.raises(ValueError, match="declares no write authority"):
            for _ in range(20):
                plant.step()

    def test_a_negative_step_index_is_refused(self) -> None:
        with pytest.raises(ValueError, match="silently never"):
            PlannedCommandSource({-1: (PlannedWrite(OPERATOR, SETPOINT, 1.0, "x"),)})

    def test_a_plant_with_no_network_refuses_a_command_source(self) -> None:
        class Deaf(CommandedTank):
            @property
            def description(self) -> PlantDescription:
                return description_with(control_network=None, write_authority=None)

        with pytest.raises(ValueError, match="declares no control network"):
            Deaf(spec(20), commands=NoCommands())


class TestTheDeclarationIsValidated:
    """A policy that names things the plant does not have is a mistake, not a permission."""

    def test_a_grant_to_an_undeclared_node_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="undeclared node"):
            description_with(write_authority={"grants": {"ghost": frozenset({SETPOINT})}})

    def test_a_grant_of_an_undeclared_signal_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="undeclared signal"):
            description_with(write_authority={"grants": {OPERATOR: frozenset({"nope"})}})

    def test_a_grant_of_a_sensor_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="not something anyone can be permitted"):
            description_with(write_authority={"grants": {OPERATOR: frozenset({LEVEL})}})

    def test_an_authority_without_a_network_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="no control network"):
            description_with(
                control_network=None, write_authority={"grants": {OPERATOR: frozenset({SETPOINT})}}
            )


class TestTheSourceSeesOnlyWhatADeviceCouldSee:
    """An adversary reading the plant's unmeasured state would be an oracle, not an adversary."""

    def test_the_source_receives_the_reported_readings(self) -> None:
        seen: list[Mapping[str, float]] = []

        class Watcher(PlannedCommandSource):
            def writes_at(
                self, index: int, clock: datetime, reported: Mapping[str, float]
            ) -> Sequence[PlannedWrite]:
                seen.append(dict(reported))
                return super().writes_at(index, clock, reported)

        run(Watcher({}), steps=5)
        assert len(seen) == 5
        assert set(seen[0]) == set(TANK_DESCRIPTION.signal_keys())

    def test_the_source_is_never_handed_internal_state(self) -> None:
        """`demand_m3ph` is internal: it is in `TrueState.internal` and on no instrument."""
        seen: list[Mapping[str, float]] = []

        class Watcher(PlannedCommandSource):
            def writes_at(
                self, index: int, clock: datetime, reported: Mapping[str, float]
            ) -> Sequence[PlannedWrite]:
                seen.append(dict(reported))
                return ()

        steps = run(Watcher({}), steps=5)
        assert "demand_m3ph" in steps[0].truth.internal
        assert all("demand_m3ph" not in snapshot for snapshot in seen)


class TestTheRecordIsUsable:
    """Small guarantees the maintenance and scenario layers build on."""

    def test_issued_commands_carry_the_sample_they_landed_on(self) -> None:
        issued = run(write_at(10, OPERATOR))[10].issued[0]
        assert issued.step_index == 10
        assert issued.timestamp == START + timedelta(minutes=10)

    def test_issued_commands_name_the_register_they_touched(self) -> None:
        issued = run(write_at(10, OPERATOR))[10].issued[0]
        target, address = TANK_DESCRIPTION.control_network.address_of(SETPOINT)  # type: ignore[union-attr]
        assert (issued.target, issued.address) == (target, address)

    def test_the_scheduled_steps_are_reported_in_order(self) -> None:
        source = PlannedCommandSource(
            {
                7: (PlannedWrite(OPERATOR, SETPOINT, 4.0, "b"),),
                3: (PlannedWrite(OPERATOR, SETPOINT, 4.0, "a"),),
            }
        )
        assert source.scheduled_steps == (3, 7)

    def test_the_issued_record_is_immutable(self) -> None:
        issued = run(write_at(10, OPERATOR))[10].issued[0]
        with pytest.raises(AttributeError):
            issued.applied = 0.0  # type: ignore[misc]

    def test_a_setpoint_is_declared_a_setpoint(self) -> None:
        assert TANK_DESCRIPTION.signal(SETPOINT).kind is SignalKind.SETPOINT

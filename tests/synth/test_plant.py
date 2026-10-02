"""The plant interface, and the three properties D2 and D3 will depend on.

The plant here is a toy — one tank, one pump, one loop — and that is deliberate. What is under
test is not physics but the *discipline the base class enforces on every plant*: that truth is
recorded apart from what the instruments say, that an injection reaches the process through the
process's own mechanisms, and that the machinery delivering an injection leaves no trace of its
own. A two-signal tank makes all three checkable by hand. The real plants are exercised in
`test_plants.py`, where the subject is whether the physics is believable.

The property worth stating plainly, because everything D2 does rests on it: **a run through an
injection whose window has not opened is bit-identical to a run with no injection at all.** If
that is ever false, an attack could be found by looking for the machinery rather than for the
attack, and every detection number measured on this data afterwards would be worthless.
"""

import math
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from itertools import pairwise

import numpy
import pytest
from numpy.random import Generator
from pydantic import ValidationError

from phos.synth.injection import (
    CompositeInjection,
    HoldActuator,
    HoldReading,
    Injection,
    NoInjection,
    TimeWindow,
)
from phos.synth.plant import (
    MAX_REGISTER_COUNT,
    BenignEvent,
    CommandKind,
    ControlNetwork,
    Coupling,
    CouplingKind,
    EventPlan,
    NetworkNode,
    PhysicalUnit,
    Plant,
    PlantDescription,
    PlantStep,
    RegisterBlock,
    RunSpec,
    SignalKind,
    SignalSpec,
    lay_out_events,
    register_count,
)
from phos.synth.process import PiController, accumulate, cycle_factor, square_law_flow
from phos.synth.realism import RealismProfile

START = datetime(2026, 3, 1, tzinfo=UTC)
LEVEL = "level_m"
INFLOW = "inflow_m3ph"
PUMP = "pump_speed_pct"
SETPOINT = "level_setpoint_m"
TANK_AREA_M2 = 10.0

TANK_NETWORK = ControlNetwork(
    nodes=(
        NetworkNode(node_id="scada", label="SCADA server", ip="10.0.9.5", role="scada"),
        NetworkNode(node_id="plc", label="Tank PLC", ip="10.0.9.11", role="plc"),
        NetworkNode(node_id="hmi", label="Operator HMI", ip="10.0.9.20", role="hmi"),
    ),
    blocks=(
        RegisterBlock(node_id="plc", start_address=0, signals=(LEVEL, INFLOW, PUMP)),
        RegisterBlock(node_id="plc", start_address=100, signals=(SETPOINT,), writable=True),
    ),
    poller="scada",
    operator="hmi",
    poll_interval_seconds=120.0,
)

TANK_DESCRIPTION = PlantDescription(
    plant_id="tiny-tank",
    label="Tiny tank",
    industry="test fixture",
    summary="One tank, one pump, one level loop. A fixture, not a claim about any real plant.",
    model_source="Hand-built fixture for tests/synth/test_plant.py.",
    units=(
        PhysicalUnit(unit_id="tank", label="Storage tank"),
        PhysicalUnit(unit_id="pump", label="Feed pump"),
    ),
    signals=(
        SignalSpec(
            key=LEVEL,
            label="Tank level",
            unit="m",
            kind=SignalKind.SENSOR,
            physical_unit="tank",
            low=0.0,
            high=6.0,
            noise_stddev=0.01,
            drift_amplitude=0.02,
        ),
        SignalSpec(
            key=INFLOW,
            label="Feed flow",
            unit="m3/h",
            kind=SignalKind.SENSOR,
            physical_unit="pump",
            low=0.0,
            high=70.0,
            noise_stddev=0.3,
            drift_amplitude=0.2,
        ),
        SignalSpec(
            key=PUMP,
            label="Feed pump speed",
            unit="%",
            kind=SignalKind.ACTUATOR,
            physical_unit="pump",
            low=0.0,
            high=100.0,
            noise_stddev=0.05,
        ),
        SignalSpec(
            key=SETPOINT,
            label="Level setpoint",
            unit="m",
            kind=SignalKind.SETPOINT,
            physical_unit="tank",
            low=0.0,
            high=6.0,
            noise_stddev=0.0,
        ),
    ),
    couplings=(
        Coupling(
            driven=LEVEL,
            drivers=(INFLOW,),
            kind=CouplingKind.INTEGRATION,
            relation="level integrates inflow minus the demand drawn off the tank",
        ),
        Coupling(
            driven=INFLOW,
            drivers=(PUMP,),
            kind=CouplingKind.ALGEBRAIC,
            relation="flow follows the square root of pump speed",
        ),
        Coupling(
            driven=PUMP,
            drivers=(LEVEL, SETPOINT),
            kind=CouplingKind.CONTROL,
            relation="a PI loop holds level at setpoint",
        ),
    ),
    control_network=TANK_NETWORK,
)


def description_with(**overrides: object) -> PlantDescription:
    """Rebuild the fixture description with fields replaced, re-running every validator.

    `model_copy(update=...)` skips validation in Pydantic v2, so a variant built that way would
    construct happily and the test asserting it is refused would assert nothing.
    """
    return PlantDescription.model_validate({**TANK_DESCRIPTION.model_dump(), **overrides})


def network_with(**overrides: object) -> ControlNetwork:
    """Rebuild the fixture control network with fields replaced, re-running every validator."""
    return ControlNetwork.model_validate({**TANK_NETWORK.model_dump(), **overrides})


class TinyTank(Plant):
    """A one-tank fixture: level integrates net flow, a PI loop holds it at setpoint."""

    def __init__(
        self,
        spec: RunSpec,
        *,
        with_network: bool = True,
        realism: RealismProfile | None = None,
    ) -> None:
        """Build the fixture, optionally without its control network."""
        self._description = (
            TANK_DESCRIPTION if with_network else description_with(control_network=None)
        )
        self._loop = PiController(gain=25.0, integral_time_seconds=600.0, low=0.0, high=100.0)
        super().__init__(spec, realism=realism)

    @property
    def description(self) -> PlantDescription:
        return self._description

    def initial_state(self) -> Mapping[str, float]:
        return {LEVEL: 3.0, INFLOW: 20.0, PUMP: 33.0, SETPOINT: 3.0, "demand_m3ph": 20.0}

    def schedule_events(self, rng: Generator, spec: RunSpec) -> Sequence[BenignEvent]:
        at = spec.instant(20)
        return (
            BenignEvent(
                kind="setpoint_change",
                label="Operator raises the level setpoint",
                started_at=at,
                ended_at=at,
                writes=(SETPOINT,),
                detail="level setpoint 3.00 -> 3.60 m",
            ),
        )

    def begin_event(self, event: BenignEvent) -> None:
        self._state[SETPOINT] = 3.6

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
        demand = 20.0 + cycle_factor(elapsed_hours, 24.0, 8.0, 0.0)
        inflow = square_law_flow(actuators[PUMP], 60.0)
        level = accumulate(
            state[LEVEL],
            rate_per_second=(inflow - demand) / TANK_AREA_M2 / 3600.0,
            dt_seconds=dt_seconds,
            low=0.0,
            high=6.0,
        )
        return {
            LEVEL: level,
            INFLOW: inflow,
            PUMP: actuators[PUMP],
            SETPOINT: state[SETPOINT],
            "demand_m3ph": demand,
        }


def spec(steps: int = 60, seed: int = 11) -> RunSpec:
    """Return a run spec covering ``steps`` one-minute samples."""
    return RunSpec(
        seed=seed,
        start=START,
        duration=timedelta(minutes=steps),
        sample_interval=timedelta(minutes=1),
    )


def run(injection: Injection | None = None, *, steps: int = 60, seed: int = 11) -> list[PlantStep]:
    """Step a fresh tank through a whole run and return every sample."""
    plant = TinyTank(spec(steps, seed))
    return [plant.step(injection) for _ in range(steps)]


def reported(steps: Sequence[PlantStep], key: str) -> list[float]:
    """Return one signal's reported series."""
    return [step.report.values[key] for step in steps]


def truth(steps: Sequence[PlantStep], key: str) -> list[float]:
    """Return one signal's true series."""
    return [step.truth.values[key] for step in steps]


class TestTrueStateRecord:
    def test_truth_and_report_are_separate_records_of_the_same_instant(self) -> None:
        step = run(steps=5)[-1]
        assert step.truth.timestamp == step.report.timestamp
        assert set(step.truth.values) == set(step.report.values)

    def test_in_normal_operation_they_agree_within_the_declared_error_model(self) -> None:
        steps = run(steps=240)
        for step in steps:
            for signal in TANK_DESCRIPTION.signals:
                departure = abs(step.report.values[signal.key] - step.truth.values[signal.key])
                assert departure <= signal.drift_amplitude + 6.0 * signal.noise_stddev

    def test_they_are_not_merely_equal_because_the_instruments_are_imperfect(self) -> None:
        steps = run(steps=120)
        assert any(step.report.values[LEVEL] != step.truth.values[LEVEL] for step in steps)

    def test_a_discrete_signal_with_no_declared_error_is_reported_exactly(self) -> None:
        for step in run(steps=30):
            assert step.report.values[SETPOINT] == step.truth.values[SETPOINT]

    def test_truth_carries_process_state_no_instrument_is_on(self) -> None:
        step = run(steps=3)[-1]
        assert "demand_m3ph" in step.truth.internal
        assert "demand_m3ph" not in step.truth.values

    def test_a_plant_that_loses_a_signal_while_advancing_is_refused(self) -> None:
        class Forgetful(TinyTank):
            def advance(
                self,
                state: Mapping[str, float],
                actuators: Mapping[str, float],
                active: BenignEvent | None,
                elapsed_hours: float,
                dt_seconds: float,
            ) -> Mapping[str, float]:
                advanced = dict(
                    super().advance(state, actuators, active, elapsed_hours, dt_seconds)
                )
                del advanced[INFLOW]
                return advanced

        with pytest.raises(KeyError, match="lost signal"):
            Forgetful(spec()).step()


class TestCoupling:
    def test_the_level_actually_integrates_net_flow_rather_than_resembling_it(self) -> None:
        steps = run(steps=180)
        for earlier, later in pairwise(steps):
            demand = later.truth.internal["demand_m3ph"]
            expected = (
                earlier.truth.values[LEVEL]
                + (later.truth.values[INFLOW] - demand) / TANK_AREA_M2 / 3600.0 * 60.0
            )
            assert later.truth.values[LEVEL] == pytest.approx(expected, abs=1e-9)

    def test_the_loop_pushes_the_level_toward_its_setpoint_after_it_is_moved(self) -> None:
        steps = run(steps=400)
        before = truth(steps, LEVEL)[19]
        after = truth(steps, LEVEL)[-1]
        assert before < after


class TestInjectionLeavesNoTell:
    def test_an_absent_injection_and_an_inert_one_produce_identical_runs(self) -> None:
        without = run(None, steps=120)
        through = run(NoInjection(), steps=120)
        assert [step.report.values for step in without] == [step.report.values for step in through]
        assert [step.truth.values for step in without] == [step.truth.values for step in through]

    def test_a_run_is_bit_identical_until_the_injection_window_opens(self) -> None:
        opens_at = START + timedelta(minutes=60)
        held = HoldActuator(
            actuator=PUMP, value=90.0, window=TimeWindow(opens_at, opens_at + timedelta(minutes=20))
        )
        clean = run(None, steps=120)
        manipulated = run(held, steps=120)
        for before, after in zip(clean[:60], manipulated[:60], strict=True):
            assert before.report.values == after.report.values
            assert before.truth.values == after.truth.values
        assert clean[70].truth.values[PUMP] != manipulated[70].truth.values[PUMP]

    def test_the_command_traffic_is_unchanged_in_shape_by_an_injection(self) -> None:
        opens_at = START + timedelta(minutes=10)
        lying = HoldReading(
            signal=LEVEL, value=3.0, window=TimeWindow(opens_at, opens_at + timedelta(hours=1))
        )
        clean = run(None, steps=120)
        manipulated = run(lying, steps=120)
        assert [len(step.commands) for step in clean] == [
            len(step.commands) for step in manipulated
        ]

    def test_an_injection_is_consulted_on_every_step_including_the_inert_case(self) -> None:
        class Counting:
            def __init__(self) -> None:
                """Start both counters at zero."""
                self.actuator_calls = 0
                self.reading_calls = 0

            def actuator_overrides(
                self, clock: datetime, commanded: Mapping[str, float]
            ) -> Mapping[str, float]:
                self.actuator_calls += 1
                return {}

            def reading_overrides(
                self, clock: datetime, readings: Mapping[str, float]
            ) -> Mapping[str, float]:
                self.reading_calls += 1
                return {}

        counter = Counting()
        run(counter, steps=25)
        assert counter.actuator_calls == 25
        assert counter.reading_calls == 25


class TestInjectionReachesThePlant:
    def test_holding_an_actuator_changes_the_process_state_it_drives(self) -> None:
        opens_at = START + timedelta(minutes=30)
        held = HoldActuator(
            actuator=PUMP, value=95.0, window=TimeWindow(opens_at, opens_at + timedelta(hours=2))
        )
        clean = run(None, steps=180)
        manipulated = run(held, steps=180)
        assert manipulated[60].truth.values[PUMP] == 95.0
        assert manipulated[60].truth.values[INFLOW] > clean[60].truth.values[INFLOW]
        assert manipulated[120].truth.values[LEVEL] > clean[120].truth.values[LEVEL]

    def test_a_manipulated_actuator_is_visible_to_the_instruments_like_any_other_position(
        self,
    ) -> None:
        opens_at = START + timedelta(minutes=30)
        held = HoldActuator(
            actuator=PUMP, value=95.0, window=TimeWindow(opens_at, opens_at + timedelta(hours=2))
        )
        step = run(held, steps=180)[60]
        assert step.report.values[PUMP] == pytest.approx(95.0, abs=0.5)

    def test_falsifying_a_reading_leaves_the_true_state_telling_the_truth(self) -> None:
        opens_at = START + timedelta(minutes=30)
        lying = HoldReading(
            signal=LEVEL, value=3.0, window=TimeWindow(opens_at, opens_at + timedelta(hours=3))
        )
        steps = run(lying, steps=240)
        assert steps[100].report.values[LEVEL] == 3.0
        assert steps[100].truth.values[LEVEL] != 3.0

    def test_a_falsified_reading_reaches_the_plant_because_the_loop_believes_it(self) -> None:
        opens_at = START + timedelta(minutes=30)
        lying = HoldReading(
            signal=LEVEL, value=1.0, window=TimeWindow(opens_at, opens_at + timedelta(hours=3))
        )
        clean = run(None, steps=240)
        manipulated = run(lying, steps=240)
        # Told the tank is nearly empty, the loop opens the pump and the real level climbs.
        assert manipulated[120].truth.values[LEVEL] > clean[120].truth.values[LEVEL]

    def test_an_injection_naming_an_unknown_actuator_is_refused_not_ignored(self) -> None:
        window = TimeWindow(START, START + timedelta(hours=1))
        with pytest.raises(KeyError, match="not a declared actuator"):
            run(HoldActuator(actuator="no_such_valve", value=1.0, window=window), steps=3)

    def test_an_injection_may_not_move_a_signal_that_is_not_an_actuator(self) -> None:
        window = TimeWindow(START, START + timedelta(hours=1))
        with pytest.raises(KeyError, match="not a declared actuator"):
            run(HoldActuator(actuator=LEVEL, value=1.0, window=window), steps=3)

    def test_an_injection_naming_an_unknown_signal_is_refused_not_ignored(self) -> None:
        window = TimeWindow(START, START + timedelta(hours=1))
        with pytest.raises(KeyError, match="not a declared signal"):
            run(HoldReading(signal="no_such_meter", value=1.0, window=window), steps=3)


class TestDeterminism:
    def test_two_runs_from_one_seed_are_identical(self) -> None:
        assert [s.report.values for s in run(steps=90)] == [s.report.values for s in run(steps=90)]

    def test_two_seeds_produce_different_noise(self) -> None:
        first = reported(run(steps=90, seed=1), LEVEL)
        second = reported(run(steps=90, seed=2), LEVEL)
        assert first != second

    def test_the_underlying_process_is_the_same_process_under_either_seed(self) -> None:
        first = truth(run(steps=90, seed=1), LEVEL)
        second = truth(run(steps=90, seed=2), LEVEL)
        assert first[0] == pytest.approx(second[0], abs=0.05)


class TestBenignEvents:
    def test_the_schedule_is_visible_before_the_run_starts(self) -> None:
        plant = TinyTank(spec())
        assert [event.kind for event in plant.events] == ["setpoint_change"]

    def test_an_event_begins_exactly_once_at_its_own_instant(self) -> None:
        steps = run(steps=60)
        assert [step.index for step in steps if step.began is not None] == [20]

    def test_the_event_changes_the_plant_and_the_change_persists(self) -> None:
        steps = run(steps=60)
        assert steps[19].truth.values[SETPOINT] == 3.0
        assert steps[20].truth.values[SETPOINT] == 3.6
        assert steps[59].truth.values[SETPOINT] == 3.6

    def test_an_instantaneous_event_is_in_force_only_at_its_own_instant(self) -> None:
        steps = run(steps=60)
        assert [step.index for step in steps if step.active is not None] == [20]

    def test_overlapping_events_are_refused_because_two_could_be_in_force_at_once(self) -> None:
        class Overlapping(TinyTank):
            def schedule_events(self, rng: Generator, spec: RunSpec) -> Sequence[BenignEvent]:
                return (
                    BenignEvent(
                        kind="first",
                        label="First",
                        started_at=spec.instant(5),
                        ended_at=spec.instant(15),
                    ),
                    BenignEvent(
                        kind="second",
                        label="Second",
                        started_at=spec.instant(10),
                        ended_at=spec.instant(20),
                    ),
                )

        with pytest.raises(ValueError, match="overlap"):
            Overlapping(spec())

    def test_an_event_starting_between_samples_is_refused_because_nothing_would_begin_it(
        self,
    ) -> None:
        class OffGrid(TinyTank):
            def schedule_events(self, rng: Generator, spec: RunSpec) -> Sequence[BenignEvent]:
                at = spec.instant(5) + timedelta(seconds=13)
                return (BenignEvent(kind="odd", label="Odd", started_at=at, ended_at=at),)

        with pytest.raises(ValueError, match="not a sample instant"):
            OffGrid(spec())


class TestControlTraffic:
    def test_the_poller_reads_every_block_on_its_cycle(self) -> None:
        steps = run(steps=10)
        polls = [step.index for step in steps if step.commands]
        assert polls[:3] == [0, 2, 4]

    def test_a_poll_reads_the_declared_block_rather_than_an_invented_range(self) -> None:
        first = run(steps=4)[0].commands
        reads = [command for command in first if command.kind is CommandKind.READ]
        assert [(read.address, read.quantity) for read in reads] == [(0, 3), (100, 1)]

    def test_an_operator_event_puts_a_write_on_the_wire_carrying_the_new_value(self) -> None:
        writes = [
            command
            for step in run(steps=60)
            for command in step.commands
            if command.kind is CommandKind.WRITE
        ]
        assert len(writes) == 1
        assert writes[0].address == 100
        assert writes[0].issuer == "hmi"
        assert writes[0].values == (register_count(TANK_DESCRIPTION.signal(SETPOINT), 3.6),)

    def test_a_plant_with_no_control_network_generates_no_traffic_at_all(self) -> None:
        plant = TinyTank(spec(), with_network=False)
        assert all(plant.step().commands == () for _ in range(10))

    def test_a_poll_faster_than_the_sample_rate_polls_every_sample(self) -> None:
        fast = RunSpec(
            seed=3,
            start=START,
            duration=timedelta(minutes=5),
            sample_interval=timedelta(minutes=5),
        )
        plant = TinyTank(fast)
        assert plant.step().commands != ()


class TestRegisterCount:
    def test_the_bottom_of_the_span_reads_zero(self) -> None:
        assert register_count(TANK_DESCRIPTION.signal(LEVEL), 0.0) == 0

    def test_the_top_of_the_span_reads_full_scale(self) -> None:
        assert register_count(TANK_DESCRIPTION.signal(LEVEL), 6.0) == MAX_REGISTER_COUNT

    def test_a_value_past_the_span_saturates_as_a_real_converter_does(self) -> None:
        assert register_count(TANK_DESCRIPTION.signal(LEVEL), 99.0) == MAX_REGISTER_COUNT
        assert register_count(TANK_DESCRIPTION.signal(LEVEL), -99.0) == 0

    def test_the_count_is_monotonic_in_the_engineering_value(self) -> None:
        spec_ = TANK_DESCRIPTION.signal(LEVEL)
        assert register_count(spec_, 1.0) < register_count(spec_, 2.0)


class TestRunSpec:
    def test_counts_the_samples_that_fit_in_the_duration(self) -> None:
        assert spec(steps=90).n_steps == 90

    def test_names_the_instant_of_each_sample(self) -> None:
        assert spec().instant(3) == START + timedelta(minutes=3)

    @pytest.mark.parametrize(
        ("duration", "interval", "message"),
        [
            (timedelta(0), timedelta(minutes=1), "duration must be positive"),
            (timedelta(hours=1), timedelta(0), "sample_interval must be positive"),
            (timedelta(minutes=1), timedelta(hours=1), "holds no samples"),
        ],
    )
    def test_refuses_a_run_that_holds_no_samples(
        self, duration: timedelta, interval: timedelta, message: str
    ) -> None:
        with pytest.raises(ValidationError, match=message):
            RunSpec(seed=1, start=START, duration=duration, sample_interval=interval)


class TestDescriptionIsAClaimThatIsChecked:
    def test_refuses_a_signal_key_declared_twice(self) -> None:
        with pytest.raises(ValidationError, match="signal key twice"):
            description_with(signals=(*TANK_DESCRIPTION.signals, TANK_DESCRIPTION.signal(LEVEL)))

    def test_refuses_a_signal_sitting_on_an_undeclared_unit(self) -> None:
        stray = TANK_DESCRIPTION.signal(LEVEL).model_copy(update={"physical_unit": "nowhere"})
        with pytest.raises(ValidationError, match="undeclared unit"):
            description_with(signals=(stray, *TANK_DESCRIPTION.signals[1:]))

    def test_refuses_a_declared_unit_carrying_no_instrument(self) -> None:
        with pytest.raises(ValidationError, match="carrying no signal"):
            description_with(
                units=(*TANK_DESCRIPTION.units, PhysicalUnit(unit_id="ghost", label="Ghost"))
            )

    def test_refuses_a_physical_unit_declared_twice(self) -> None:
        with pytest.raises(ValidationError, match="physical unit twice"):
            description_with(units=(TANK_DESCRIPTION.units[0], *TANK_DESCRIPTION.units))

    def test_refuses_a_coupling_naming_a_signal_that_does_not_exist(self) -> None:
        bad = Coupling(
            driven=LEVEL, drivers=("phantom",), kind=CouplingKind.ALGEBRAIC, relation="nonsense"
        )
        with pytest.raises(ValidationError, match="undeclared signal"):
            description_with(couplings=(bad,))

    def test_refuses_a_signal_declared_as_its_own_driver(self) -> None:
        with pytest.raises(ValidationError, match="its own driver"):
            Coupling(
                driven=LEVEL, drivers=(LEVEL,), kind=CouplingKind.INTEGRATION, relation="circular"
            )

    def test_refuses_a_signal_whose_instrument_span_is_empty(self) -> None:
        with pytest.raises(ValidationError, match="empty span"):
            SignalSpec(
                key="broken",
                label="Broken",
                unit="m",
                kind=SignalKind.SENSOR,
                physical_unit="tank",
                low=5.0,
                high=5.0,
                noise_stddev=0.0,
            )

    def test_refuses_a_register_block_naming_a_signal_that_does_not_exist(self) -> None:
        network = network_with(
            blocks=(RegisterBlock(node_id="plc", start_address=0, signals=("ghost",)),)
        )
        with pytest.raises(ValidationError, match="undeclared signal"):
            description_with(control_network=network)

    def test_refuses_an_operator_writing_to_a_measurement(self) -> None:
        network = network_with(
            blocks=(RegisterBlock(node_id="plc", start_address=0, signals=(LEVEL,), writable=True),)
        )
        with pytest.raises(ValidationError, match="not something an operator can write"):
            description_with(control_network=network)


class TestControlNetworkIsAClaimThatIsChecked:
    def test_refuses_a_node_identifier_declared_twice(self) -> None:
        with pytest.raises(ValidationError, match="node identifier twice"):
            network_with(nodes=(*TANK_NETWORK.nodes, TANK_NETWORK.nodes[0]))

    def test_refuses_two_devices_at_one_address(self) -> None:
        clash = TANK_NETWORK.nodes[0].model_copy(update={"node_id": "other"})
        with pytest.raises(ValidationError, match="address twice"):
            network_with(nodes=(*TANK_NETWORK.nodes, clash))

    @pytest.mark.parametrize("role", ["poller", "operator"])
    def test_refuses_a_role_played_by_a_device_that_is_not_on_the_network(self, role: str) -> None:
        with pytest.raises(ValidationError, match=f"{role} 'ghost' is not a declared node"):
            network_with(**{role: "ghost"})

    def test_refuses_a_register_block_on_a_device_that_is_not_on_the_network(self) -> None:
        with pytest.raises(ValidationError, match="undeclared node"):
            network_with(
                blocks=(RegisterBlock(node_id="ghost", start_address=0, signals=(LEVEL,)),)
            )

    def test_refuses_two_signals_claiming_one_register(self) -> None:
        with pytest.raises(ValidationError, match="claimed by both"):
            network_with(
                blocks=(
                    RegisterBlock(node_id="plc", start_address=0, signals=(LEVEL, INFLOW)),
                    RegisterBlock(node_id="plc", start_address=1, signals=(PUMP,)),
                )
            )

    def test_looks_up_the_device_behind_an_identifier(self) -> None:
        assert TANK_NETWORK.node("plc").ip == "10.0.9.11"

    def test_refuses_to_invent_a_device_it_has_never_heard_of(self) -> None:
        with pytest.raises(KeyError, match="no node 'ghost'"):
            TANK_NETWORK.node("ghost")

    def test_finds_the_register_a_signal_is_exposed_at(self) -> None:
        assert TANK_NETWORK.address_of(INFLOW) == ("plc", 1)

    def test_says_so_when_nothing_on_the_wire_carries_a_signal(self) -> None:
        with pytest.raises(KeyError, match="on no register block"):
            TANK_NETWORK.address_of("demand_m3ph")

    def test_names_the_signal_behind_a_key_and_refuses_an_unknown_one(self) -> None:
        assert TANK_DESCRIPTION.signal(PUMP).kind is SignalKind.ACTUATOR
        with pytest.raises(KeyError, match="declares no signal"):
            TANK_DESCRIPTION.signal("ghost")


class TestInjectionPrimitives:
    def test_a_window_is_half_open_so_two_of_them_tile_time_without_overlapping(self) -> None:
        window = TimeWindow(START, START + timedelta(minutes=10))
        assert window.contains(START)
        assert window.contains(START + timedelta(minutes=9))
        assert not window.contains(START + timedelta(minutes=10))

    def test_refuses_an_inverted_window(self) -> None:
        with pytest.raises(ValueError, match="inverted"):
            TimeWindow(START + timedelta(hours=1), START)

    def test_the_null_injection_satisfies_the_protocol_it_stands_in_for(self) -> None:
        assert isinstance(NoInjection(), Injection)

    def test_a_composite_applies_every_part_with_the_last_winning_a_conflict(self) -> None:
        window = TimeWindow(START, START + timedelta(hours=1))
        composite = CompositeInjection(
            parts=[
                HoldActuator(actuator=PUMP, value=10.0, window=window),
                HoldReading(signal=LEVEL, value=2.0, window=window),
                HoldActuator(actuator=PUMP, value=80.0, window=window),
            ]
        )
        assert composite.actuator_overrides(START, {PUMP: 50.0}) == {PUMP: 80.0}
        assert composite.reading_overrides(START, {LEVEL: 3.0}) == {LEVEL: 2.0}

    def test_a_composite_of_nothing_is_a_no_op(self) -> None:
        composite = CompositeInjection(parts=[])
        assert composite.actuator_overrides(START, {PUMP: 50.0}) == {}
        assert composite.reading_overrides(START, {LEVEL: 3.0}) == {}

    def test_the_holds_leave_the_other_door_alone(self) -> None:
        window = TimeWindow(START, START + timedelta(hours=1))
        assert (
            HoldActuator(actuator=PUMP, value=1.0, window=window).reading_overrides(START, {}) == {}
        )
        assert (
            HoldReading(signal=LEVEL, value=1.0, window=window).actuator_overrides(START, {}) == {}
        )

    def test_a_hold_outside_its_window_overrides_nothing(self) -> None:
        window = TimeWindow(START, START + timedelta(minutes=10))
        later = START + timedelta(hours=2)
        assert (
            HoldActuator(actuator=PUMP, value=1.0, window=window).actuator_overrides(later, {})
            == {}
        )
        assert (
            HoldReading(signal=LEVEL, value=1.0, window=window).reading_overrides(later, {}) == {}
        )


class TestSensorModel:
    def test_a_reading_never_leaves_the_instrument_span(self) -> None:
        for step in run(steps=240):
            for signal in TANK_DESCRIPTION.signals:
                assert signal.low <= step.report.values[signal.key] <= signal.high

    def test_calibration_drift_is_present_and_slow(self) -> None:
        steps = run(steps=1440)
        residual = [step.report.values[LEVEL] - step.truth.values[LEVEL] for step in steps]
        first_hour = sum(residual[:60]) / 60.0
        last_hour = sum(residual[-60:]) / 60.0
        assert not math.isclose(first_hour, last_hour, abs_tol=1e-4)


class TestScheduleIntegrity:
    def test_refuses_an_event_that_ends_before_it_begins(self) -> None:
        with pytest.raises(ValidationError, match="inverted"):
            BenignEvent(
                kind="backwards",
                label="Backwards",
                started_at=START + timedelta(hours=1),
                ended_at=START,
            )

    def test_accepts_a_schedule_of_several_events_that_do_not_overlap(self) -> None:
        class Busy(TinyTank):
            def schedule_events(self, rng: Generator, spec: RunSpec) -> Sequence[BenignEvent]:
                return tuple(
                    BenignEvent(
                        kind="setpoint_change",
                        label=f"Change {index}",
                        started_at=spec.instant(index * 10),
                        ended_at=spec.instant(index * 10 + 2),
                    )
                    for index in range(1, 4)
                )

        plant = Busy(spec())
        assert len(plant.events) == 3

    def test_a_plant_remembers_the_run_it_was_built_for(self) -> None:
        wanted = spec(steps=42, seed=5)
        assert TinyTank(wanted).spec == wanted


class TestLayingOutEvents:
    PLAN = EventPlan(kind="wash", label="Wash", duration_steps=2)

    def test_places_events_round_robin_with_gaps_between_them(self) -> None:
        rng = numpy.random.default_rng(3)
        plans = (self.PLAN, EventPlan(kind="stop", label="Stop", duration_steps=4))
        events = lay_out_events(rng, spec(steps=200), plans, first_start_step=10, gap_steps=(5, 9))
        assert [event.kind for event in events][:4] == ["wash", "stop", "wash", "stop"]
        for earlier, later in pairwise(events):
            assert later.started_at > earlier.ended_at

    def test_draws_a_parameter_per_occurrence_so_two_are_not_identical(self) -> None:
        rng = numpy.random.default_rng(3)
        plan = EventPlan(
            kind="setpoint_change",
            label="Change",
            writes=(SETPOINT,),
            parameter_ranges={SETPOINT: (2.0, 4.0)},
        )
        events = lay_out_events(rng, spec(steps=400), (plan,), first_start_step=5, gap_steps=(5, 9))
        drawn = [event.parameters[SETPOINT] for event in events]
        assert len(set(drawn)) == len(drawn)
        assert all(2.0 <= value <= 4.0 for value in drawn)
        assert all(
            f"{value:.3f}" in event.detail for value, event in zip(drawn, events, strict=True)
        )

    def test_a_run_too_short_to_hold_one_event_holds_none(self) -> None:
        rng = numpy.random.default_rng(3)
        events = lay_out_events(
            rng, spec(steps=10), (self.PLAN,), first_start_step=9, gap_steps=(1, 2)
        )
        assert events == ()

    @pytest.mark.parametrize(
        ("plans", "first", "gap", "message"),
        [
            ((), 5, (1, 2), "no event plans"),
            ((PLAN,), 5, (0, 2), "at least one sample"),
            ((PLAN,), 5, (5, 2), "gap range is inverted"),
            ((PLAN,), -1, (1, 2), "cannot start before the run"),
        ],
    )
    def test_refuses_a_schedule_it_cannot_lay_out(
        self,
        plans: tuple[EventPlan, ...],
        first: int,
        gap: tuple[int, int],
        message: str,
    ) -> None:
        with pytest.raises(ValueError, match=message):
            lay_out_events(
                numpy.random.default_rng(1), spec(), plans, first_start_step=first, gap_steps=gap
            )


class TestRealismIsAdditive:
    """Wiring `phos.synth.realism` into sensing must not move a corpus that does not ask for it.

    ADR 0073 deferred this wiring precisely because it changes how every corpus is produced. The
    Usefulness Phase (U3) required a corpus-identity proof before doing it, and these are the unit
    half of that proof — the whole-corpus half regenerates every committed dataset and compares
    digests.
    """

    def test_spawning_a_third_seed_leaves_the_first_two_untouched(self) -> None:
        """The mechanism the byte-identity rests on, asserted rather than assumed.

        `Plant.__init__` moved from ``spawn(2)`` to ``spawn(3)`` to give realism its own generator.
        That is only safe because `SeedSequence.spawn` is deterministic by child index.
        """
        for seed in (0, 1, 11, 2026001):
            two = numpy.random.SeedSequence(seed).spawn(2)
            three = numpy.random.SeedSequence(seed).spawn(3)
            for a, b in zip(two, three[:2], strict=True):
                assert numpy.random.default_rng(a).random(8).tolist() == (
                    numpy.random.default_rng(b).random(8).tolist()
                )

    def test_a_plant_given_no_realism_matches_one_given_a_quiet_profile(self) -> None:
        """``None`` and a quiet profile are the same plant, reading for reading."""
        plain = [
            step.report.values
            for step in (lambda p: [p.step() for _ in range(60)])(TinyTank(spec()))
        ]
        quiet = TinyTank(spec(), realism=RealismProfile())
        quiet_reports = [quiet.step().report.values for _ in range(60)]
        assert plain == quiet_reports

    def test_a_quiet_profile_plans_nothing(self) -> None:
        """Empty in every field, so every effect below is a no-op rather than a small one."""
        plant = TinyTank(spec(), realism=RealismProfile())
        plan = plant._realism
        assert (plan.phenomena, plan.faults, plan.drifts, plan.dropouts) == ((), (), (), ())
        assert dict(plan.ageing) == {}

    def test_a_noisy_profile_actually_changes_what_the_instruments_report(self) -> None:
        """The other half: identity under a quiet profile is only meaningful if a loud one bites."""
        quiet = TinyTank(spec(), realism=RealismProfile())
        quiet_reports = [quiet.step().report.values for _ in range(60)]
        messy = TinyTank(spec(), realism=RealismProfile(sensor_faults=3))
        messy_reports = [messy.step().report.values for _ in range(60)]
        assert messy_reports != quiet_reports

    def test_the_same_profile_and_seed_reproduce_the_same_run(self) -> None:
        """Drawn once from a seeded generator, so it reproduces like everything else here."""
        profile = RealismProfile(sensor_faults=2)
        a = TinyTank(spec(), realism=profile)
        b = TinyTank(spec(), realism=profile)
        assert [a.step().report.values for _ in range(60)] == [
            b.step().report.values for _ in range(60)
        ]

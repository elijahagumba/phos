"""A chain of tanks that fill and empty, at whatever size and shape the spec says.

PART R2's first generated process. The three plants in this package are each one plant: the water
works has the clearwell it has, and a seed never gives it a second one. This module is the other
kind of thing — a *process* that a spec sizes, shapes and tunes, so that two plants built from it
are the same kind of works at different scales.

**The process.** Liquid is pumped through a chain of tanks and drawn off at the end by a demand
nobody at the site controls. Each tank has a level transmitter, a variable-speed pump filling it,
and a PI loop holding its level by varying that pump. Trains of tanks may run in parallel into a
common header, as a real works runs two or three streams side by side so one can be taken out for
maintenance.

**Why this process is worth generating.** Its central state is an *integral*: a level can only
move as fast as the difference between two flows, so a reading that disagrees with the flows
around it is not merely unusual, it is impossible. That is the relationship a joint model can
learn and a correlation-breaking attack has to violate. Chain several of them and the violation
has somewhere to propagate to.

**What the spec decides and this module obeys.** How many trains and how many stages in each; how
big every tank is; how much flow each pump can deliver; how fast the flow follows the pump; how
the demand swings over a day; every loop's gain, integral time and bias; which stages have a flow
meter at all and which are instrumented on level alone; how noisy and how drifty each transmitter
is; how often the control network is polled; and what every tag is called. This module reads all
of it through `phos.synth.plant_spec.PlantSpec.tag`, by *role*, so a drawn tag name never reaches
the physics.

**What this is not.** A model of a pumping station written from the general shape of one — not a
model of any particular station, and not validated against one. See ``MODEL_NOT_REALITY_CAVEAT``.
"""

from collections.abc import Mapping, Sequence
from typing import Final

from numpy.random import Generator

from phos.synth.command import CommandSource
from phos.synth.plant import (
    BenignEvent,
    Plant,
    PlantDescription,
    PlantStep,
    RunSpec,
    lay_out_events,
)
from phos.synth.plant_spec import PlantSpec, pi_controller
from phos.synth.process import PiController, accumulate, clamp, cycle_factor, square_law_flow
from phos.synth.realism import RealismProfile
from phos.synth.templates import register_template

__all__ = ["DEMAND_SURGE", "LEVEL_FLOW_PROCESS", "LevelFlowPlant", "flow_state_key"]

LEVEL_FLOW_PROCESS: Final = "level-flow-v1"
"""The name a spec puts in its ``process`` field to run on this physics."""

DEMAND_SURGE: Final = "demand_surge"
"""A benign event: the draw on the header rises for a while and the whole chain has to keep up."""

LEVEL: Final = "level"
INFLOW: Final = "inflow"
PUMP_SPEED: Final = "pump_speed"
LEVEL_SETPOINT: Final = "level_setpoint"
OUTFLOW: Final = "outflow"
"""The role vocabulary this process reads. A spec that uses other words is not this process."""


def flow_state_key(train: int, stage: int) -> str:
    """Return the internal state key holding one stage's true flow.

    Internal because a stage may have no flow meter on it: the physics still has a flow, and the
    plant still has to carry it forward between samples, but nothing publishes it. Named rather
    than positional so a reader of a true-state record can tell which stage it belongs to.
    """
    return f"_true_flow_t{train}_s{stage}"


class LevelFlowPlant(Plant):
    """A chain of pumped tanks, sized and tuned by its spec.

    See the module docstring for the process and for what the spec decides. Every number this
    class uses comes from `PlantSpec.parameters`, and every signal it touches is found by role.
    """

    def __init__(
        self,
        spec: RunSpec,
        *,
        commands: CommandSource | None = None,
        realism: RealismProfile | None = None,
        plant_spec: PlantSpec | None = None,
    ) -> None:
        """Build the chain and its loops for one run.

        Args:
            spec: The run to prepare for.
            commands: Who writes over the control network, or ``None``. See
                `phos.synth.plant.Plant`.
            realism: Ordinary trouble to apply, or ``None`` for a quiet profile.
            plant_spec: The plant to build. Required: unlike the three hand-written plants there
                is no canonical instance of this process, because a process is not a plant.

        Raises:
            ValueError: If no spec is given.
        """
        if plant_spec is None:
            raise ValueError(
                "LevelFlowPlant has no default plant: it is a process, not a plant. Draw one "
                "from the level_flow family, or build a spec by hand."
            )
        self._plant_spec = plant_spec
        self._description = plant_spec.describe()
        parameters = plant_spec.parameters
        self._trains = round(parameters["trains"])
        self._stages = round(parameters["stages"])
        self._tank_area_m2 = parameters["tank_area_m2"]
        self._max_pump_flow_m3ph = parameters["max_pump_flow_m3ph"]
        self._flow_tau_s = parameters["flow_tau_s"]
        self._level_span_m = parameters["level_span_m"]
        self._level_setpoint_fraction = parameters["level_setpoint_fraction"]
        self._demand_base_m3ph = parameters["demand_base_m3ph"]
        self._demand_daily_m3ph = parameters["demand_daily_m3ph"]
        self._demand_floor_m3ph = parameters["demand_floor_m3ph"]

        self._outflow_tag = plant_spec.tags_with_role(OUTFLOW)[0]
        self._loops: dict[tuple[int, int], PiController] = {}
        self._biases: dict[tuple[int, int], float] = {}
        for train in range(self._trains):
            for stage in range(self._stages):
                controller_id = loop_id(train, stage)
                self._loops[(train, stage)] = pi_controller(plant_spec, controller_id)
                self._biases[(train, stage)] = plant_spec.controller(controller_id).bias
        super().__init__(spec, commands=commands, realism=realism)

    @property
    def description(self) -> PlantDescription:
        """What this chain is: its tanks, its pumps and its loops, as the spec declared them."""
        return self._description

    def initial_state(self) -> Mapping[str, float]:
        """Start every tank at its setpoint, with the flows the opening demand implies.

        Starting at the setpoint rather than empty is deliberate: a run that opens with every
        loop driving hard to fill a tank spends its first hour in a transient nothing else in the
        corpus resembles, and a model fitted on it learns the startup rather than the plant.
        """
        setpoint = self._level_span_m * self._level_setpoint_fraction
        share = self._demand(0.0) / self._trains
        state: dict[str, float] = {}
        for train in range(self._trains):
            for stage in range(self._stages):
                state[flow_state_key(train, stage)] = share
                state[self._tag(LEVEL, train, stage)] = setpoint
                state[self._tag(PUMP_SPEED, train, stage)] = self._speed_for(share)
                state[self._tag(LEVEL_SETPOINT, train, stage)] = setpoint
                if self._plant_spec.has_role(INFLOW, train, stage):
                    state[self._tag(INFLOW, train, stage)] = share
        state[self._outflow_tag] = self._demand(0.0)
        return state

    def schedule_events(self, rng: Generator, spec: RunSpec) -> Sequence[BenignEvent]:
        """Lay this plant's own kinds of operational event through the run, round-robin."""
        disturbance = self._plant_spec.disturbance
        return lay_out_events(
            rng,
            spec,
            disturbance.plans(),
            first_start_step=disturbance.first_start_step(spec.n_steps),
            gap_steps=disturbance.gap_steps,
        )

    def begin_event(self, event: BenignEvent) -> None:
        """Apply the lasting part of an event: a moved level setpoint."""
        for key, value in event.parameters.items():
            if key in self._state and self._plant_spec.role_of(key) is not None:
                role = self._plant_spec.role_of(key)
                if role is not None and role.role == LEVEL_SETPOINT:
                    self._state[key] = value

    def control(
        self,
        report: Mapping[str, float],
        active: BenignEvent | None,
        elapsed_hours: float,
        dt_seconds: float,
    ) -> Mapping[str, float]:
        """Run every stage's level loop, each on what its own transmitter reported."""
        commands: dict[str, float] = {}
        for train in range(self._trains):
            for stage in range(self._stages):
                loop = self._loops[(train, stage)]
                commands[self._tag(PUMP_SPEED, train, stage)] = loop.update(
                    measurement=report[self._tag(LEVEL, train, stage)],
                    setpoint=report[self._tag(LEVEL_SETPOINT, train, stage)],
                    dt_seconds=dt_seconds,
                    bias=self._biases[(train, stage)],
                )
        return commands

    def advance(
        self,
        state: Mapping[str, float],
        actuators: Mapping[str, float],
        active: BenignEvent | None,
        elapsed_hours: float,
        dt_seconds: float,
    ) -> Mapping[str, float]:
        """Advance the chain one sample: flows first, then the levels they move.

        Flows are settled for the whole chain before any level is integrated, so that a stage's
        inflow and the stage above it's outflow are the same number rather than two numbers a
        sample apart. That is what makes the conservation relation exact rather than approximate,
        and it is the relation the whole process exists to carry.
        """
        demand = self._demand(elapsed_hours) * self._surge(active)
        share = demand / self._trains
        advanced: dict[str, float] = {}

        for train in range(self._trains):
            flows = [
                self._flow(state, actuators, train, stage, dt_seconds)
                for stage in range(self._stages)
            ]
            for stage in range(self._stages):
                out = flows[stage + 1] if stage + 1 < self._stages else share
                level = accumulate(
                    state[self._tag(LEVEL, train, stage)],
                    rate_per_second=(flows[stage] - out) / self._tank_area_m2 / 3600.0,
                    dt_seconds=dt_seconds,
                    low=0.0,
                    high=self._level_span_m,
                )
                advanced[flow_state_key(train, stage)] = flows[stage]
                advanced[self._tag(LEVEL, train, stage)] = level
                advanced[self._tag(PUMP_SPEED, train, stage)] = actuators[
                    self._tag(PUMP_SPEED, train, stage)
                ]
                advanced[self._tag(LEVEL_SETPOINT, train, stage)] = state[
                    self._tag(LEVEL_SETPOINT, train, stage)
                ]
                if self._plant_spec.has_role(INFLOW, train, stage):
                    advanced[self._tag(INFLOW, train, stage)] = flows[stage]

        advanced[self._outflow_tag] = demand
        return advanced

    def conservation_residuals(
        self, steps: Sequence[PlantStep], interval_seconds: float
    ) -> Mapping[str, float]:
        """Return each tank's volume balance residual over the run.

        A tank's level is an integral and nothing else: over any stretch, the change in stored
        volume has to equal everything that came in less everything that went out. That is the
        relation this whole process exists to carry, so it is the one the gate checks.

        Residuals are computed on the **true** state rather than the reported readings. A balance
        is a statement about the process; checking it against the instruments would be checking
        the sensor model, which has its own noise and drift and would fail an honest plant.

        Args:
            steps: Every sample of the run, in order.
            interval_seconds: The integration step.

        Returns:
            ``{"train N stage M volume": relative residual}``.
        """
        residuals: dict[str, float] = {}
        if len(steps) < 2:
            return residuals
        hours = interval_seconds / 3600.0
        for train in range(self._trains):
            for stage in range(self._stages):
                inflow = 0.0
                outflow = 0.0
                for step in steps[:-1]:
                    # Flows live in the true state's `internal` map, not its `values`: a stage
                    # may have no flow meter on it, so the quantity exists in the process and
                    # not in the instrument set.
                    flows = step.truth.internal
                    inflow += flows[flow_state_key(train, stage)] * hours
                    outflow += (
                        flows[flow_state_key(train, stage + 1)] * hours
                        if stage + 1 < self._stages
                        else step.truth.values[self._outflow_tag] / self._trains * hours
                    )
                stored = (
                    steps[-1].truth.values[self._tag(LEVEL, train, stage)]
                    - steps[0].truth.values[self._tag(LEVEL, train, stage)]
                ) * self._tank_area_m2
                throughput = max(inflow, outflow, 1e-9)
                residuals[f"train {train + 1} stage {stage + 1} volume"] = (
                    inflow - outflow - stored
                ) / throughput
        return residuals

    def tracking_loops(self) -> tuple[str, ...]:
        """Every level loop. All of them hold their setpoint for the whole of a normal run."""
        return tuple(
            loop_id(train, stage) for train in range(self._trains) for stage in range(self._stages)
        )

    def _flow(
        self,
        state: Mapping[str, float],
        actuators: Mapping[str, float],
        train: int,
        stage: int,
        dt_seconds: float,
    ) -> float:
        """Return one stage's flow this sample: the pump's demand, reached with a lag.

        A pump does not reach a new flow the instant its speed changes — the liquid in the main
        has to accelerate — and the lag is what makes a level loop a control problem rather than
        an algebraic one.
        """
        commanded = square_law_flow(
            clamp(actuators[self._tag(PUMP_SPEED, train, stage)], 0.0, 100.0),
            self._max_pump_flow_m3ph,
        )
        previous = state[flow_state_key(train, stage)]
        fraction = min(1.0, dt_seconds / self._flow_tau_s)
        return previous + (commanded - previous) * fraction

    def _demand(self, elapsed_hours: float) -> float:
        """Return the draw on the header: a daily rhythm with a floor under it."""
        swing = cycle_factor(
            elapsed_hours,
            period_hours=24.0,
            amplitude=self._demand_daily_m3ph,
            phase_hours=6.0,
        )
        return max(self._demand_base_m3ph + swing, self._demand_floor_m3ph)

    def _surge(self, active: BenignEvent | None) -> float:
        """Return the multiplier a demand surge is applying, or one when nothing is happening."""
        if active is None or active.kind != DEMAND_SURGE:
            return 1.0
        return 1.0 + active.parameters.get("demand_surge_fraction", 0.0)

    def _speed_for(self, flow: float) -> float:
        """Return the pump speed that delivers a flow, inverting the square-law characteristic."""
        fraction = clamp(flow / self._max_pump_flow_m3ph, 0.0, 1.0)
        return 100.0 * fraction**2

    def _tag(self, role: str, train: int = 0, stage: int = 0) -> str:
        """Return the tag name playing a role, which the spec drew and this class never guesses."""
        return self._plant_spec.tag(role, train=train, stage=stage)


def loop_id(train: int, stage: int) -> str:
    """Return the controller identifier of one stage's level loop.

    The one piece of naming this process fixes. A controller identifier is internal — it never
    reaches the telemetry, the capture or a detector — so fixing it costs nothing that tag-name
    randomisation is buying, and it lets the template ask for its own loops by name.
    """
    return f"level_t{train}_s{stage}"


register_template(LEVEL_FLOW_PROCESS, LevelFlowPlant)

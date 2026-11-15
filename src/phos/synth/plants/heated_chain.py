"""A pumped tank chain that is also heated, and the coupling that only exists because it is both.

PART R2's fifth generated process, and the hybrid one: it is `level_flow` and `thermal` in the
same plant, with both loops on every stage. That is worth doing for one reason, and it is not
that two processes are more impressive than one.

**A tank's thermal mass is its level.** Half-fill a heated vessel and it warms twice as fast for
the same duty. So the level loop and the temperature loop are not two independent plants sharing a
cabinet — moving a level setpoint changes how the temperature loop behaves, and a slow drift on a
level transmitter shows up as a temperature loop whose gain appears to have changed. Neither
parent family can produce that, because in `level_flow` nothing is hot and in `thermal` the holdup
is a constant.

The second hybrid coupling is transport: the flow that fills a tank also carries heat into it at
the upstream tank's temperature. A disturbance at the front of the chain arrives at the back as
*both* a level excursion and a temperature excursion, separated in time by the residence time,
which is itself set by the levels. An attacker who fakes one and not the other breaks a
relationship that spans two physical domains.

**The balances.** Per stage, with ``A`` the plan area, ``rho`` the density and ``cp`` the specific
heat:

    level:        A dh/dt = inflow - outflow
    temperature:  (A*h*rho*cp) dT/dt = flow*rho*cp*(inlet - T) + heater - UA*(T - ambient)

The flow term is integrated as the exponential approach it is, for the reason
`phos.synth.plants.thermal` sets out. The thermal capacity is recomputed every sample from the
current level, with a floor under it so a tank that has run dry does not divide by zero — a dry
heated tank is a plant PART R3 should refuse, not one that should crash.

**What this is not.** A model of a heated transfer system written from the general shape of one.
See ``MODEL_NOT_REALITY_CAVEAT``.
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
from phos.synth.process import (
    PiController,
    accumulate,
    clamp,
    cycle_factor,
    first_order,
    square_law_flow,
)
from phos.synth.realism import RealismProfile
from phos.synth.templates import register_template

__all__ = [
    "AMBIENT",
    "COLD_FEED",
    "DEMAND_SURGE",
    "DUTY",
    "HEATED_CHAIN_PROCESS",
    "INFLOW",
    "LEVEL",
    "LEVEL_SETPOINT",
    "OUTFLOW",
    "PUMP_SPEED",
    "TEMPERATURE",
    "TEMPERATURE_SETPOINT",
    "HeatedChainPlant",
    "flow_state_key",
    "level_loop_id",
    "temperature_loop_id",
]

HEATED_CHAIN_PROCESS: Final = "heated-chain-v1"
"""The name a spec puts in its ``process`` field to run on this physics."""

LEVEL: Final = "level"
INFLOW: Final = "inflow"
PUMP_SPEED: Final = "pump_speed"
LEVEL_SETPOINT: Final = "level_setpoint"
TEMPERATURE: Final = "temperature"
TEMPERATURE_SETPOINT: Final = "temperature_setpoint"
DUTY: Final = "duty"
OUTFLOW: Final = "outflow"
AMBIENT: Final = "ambient"
"""The role vocabulary this process reads — the union of its two parents', plus ambient."""

DEMAND_SURGE: Final = "demand_surge"
COLD_FEED: Final = "cold_feed_excursion"
_LEVEL_SETPOINT_CHANGE: Final = "level_setpoint_change"
_TEMPERATURE_SETPOINT_CHANGE: Final = "temperature_setpoint_change"
"""The benign events. Two of each parent's, because both halves of the plant are operated."""

_MIN_HOLDUP_FRACTION: Final = 0.02
"""Floor under the thermal capacity, as a fraction of a full tank.

A tank at zero level has zero heat capacity and an undefined temperature. Rather than divide by
zero, the balance behaves as though a film remained; the resulting temperature is meaningless and
the plant is one PART R3's gate should refuse on the evidence of the run."""


def level_loop_id(train: int, stage: int) -> str:
    """Return the controller identifier of one stage's level loop."""
    return f"level_t{train}_s{stage}"


def temperature_loop_id(train: int, stage: int) -> str:
    """Return the controller identifier of one stage's temperature loop."""
    return f"temperature_t{train}_s{stage}"


def flow_state_key(train: int, stage: int) -> str:
    """Return the internal state key holding one stage's true flow."""
    return f"_true_flow_t{train}_s{stage}"


class HeatedChainPlant(Plant):
    """A chain of pumped, heated tanks where the level is the thermal mass.

    See the module docstring for the two hybrid couplings and the balances.
    """

    def __init__(
        self,
        spec: RunSpec,
        *,
        commands: CommandSource | None = None,
        realism: RealismProfile | None = None,
        plant_spec: PlantSpec | None = None,
    ) -> None:
        """Build the chain and both sets of loops for one run.

        Args:
            spec: The run to prepare for.
            commands: Who writes over the control network, or ``None``.
            realism: Ordinary trouble to apply, or ``None`` for a quiet profile.
            plant_spec: The plant to build. Required: this is a process, not a plant.

        Raises:
            ValueError: If no spec is given.
        """
        if plant_spec is None:
            raise ValueError(
                "HeatedChainPlant has no default plant: it is a process, not a plant. Draw one "
                "from the hybrid family, or build a spec by hand."
            )
        self._plant_spec = plant_spec
        self._description = plant_spec.describe()
        p = plant_spec.parameters
        self._trains = round(p["trains"])
        self._stages = round(p["stages"])
        self._tank_area_m2 = p["tank_area_m2"]
        self._level_span_m = p["level_span_m"]
        self._max_pump_flow_m3ph = p["max_pump_flow_m3ph"]
        self._flow_tau_s = p["flow_tau_s"]
        self._density_kg_per_m3 = p["density_kg_per_m3"]
        self._heat_capacity = p["heat_capacity_kj_per_kg_k"]
        self._heater_rated_kw = p["heater_rated_kw"]
        self._ua_kw_per_k = p["ua_ambient_kw_per_k"]
        self._feed_temp_c = p["feed_temp_c"]
        self._ambient_base_c = p["ambient_base_c"]
        self._ambient_daily_c = p["ambient_daily_c"]
        self._demand_base_m3ph = p["demand_base_m3ph"]
        self._demand_daily_m3ph = p["demand_daily_m3ph"]
        self._demand_floor_m3ph = p["demand_floor_m3ph"]
        self._level_setpoint_fraction = p["level_setpoint_fraction"]
        self._temperature_setpoint_c = p["temperature_setpoint_c"]
        self._temperature_span_c = p["temperature_span_c"]

        self._outflow_tag = plant_spec.tags_with_role(OUTFLOW)[0]
        self._ambient_tag = plant_spec.tags_with_role(AMBIENT)[0]
        self._level_loops: dict[tuple[int, int], PiController] = {}
        self._temperature_loops: dict[tuple[int, int], PiController] = {}
        self._pump_bias: dict[tuple[int, int], float] = {}
        self._duty_bias: dict[tuple[int, int], float] = {}
        for train in range(self._trains):
            for stage in range(self._stages):
                here = (train, stage)
                self._level_loops[here] = pi_controller(plant_spec, level_loop_id(train, stage))
                self._temperature_loops[here] = pi_controller(
                    plant_spec, temperature_loop_id(train, stage)
                )
                self._pump_bias[here] = plant_spec.controller(level_loop_id(train, stage)).bias
                self._duty_bias[here] = plant_spec.controller(
                    temperature_loop_id(train, stage)
                ).bias
        super().__init__(spec, commands=commands, realism=realism)

    @property
    def description(self) -> PlantDescription:
        """What this chain is, as the spec declared it."""
        return self._description

    def initial_state(self) -> Mapping[str, float]:
        """Start every tank at its level and temperature setpoints, carrying the opening demand."""
        level = self._level_span_m * self._level_setpoint_fraction
        demand = self._demand(0.0)
        share = demand / self._trains
        ambient = self._ambient(0.0)
        state: dict[str, float] = {self._ambient_tag: ambient, self._outflow_tag: demand}
        for train in range(self._trains):
            for stage in range(self._stages):
                state[flow_state_key(train, stage)] = share
                state[self._tag(LEVEL, train, stage)] = level
                state[self._tag(LEVEL_SETPOINT, train, stage)] = level
                state[self._tag(PUMP_SPEED, train, stage)] = self._speed_for(share)
                state[self._tag(TEMPERATURE, train, stage)] = self._temperature_setpoint_c
                state[self._tag(TEMPERATURE_SETPOINT, train, stage)] = self._temperature_setpoint_c
                state[self._tag(DUTY, train, stage)] = 50.0
                if self._plant_spec.has_role(INFLOW, train, stage):
                    state[self._tag(INFLOW, train, stage)] = share
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
        """Apply the lasting part of an event: a moved level or temperature setpoint."""
        for key, value in event.parameters.items():
            role = self._plant_spec.role_of(key)
            if role is None or key not in self._state:
                continue
            if role.role in (LEVEL_SETPOINT, TEMPERATURE_SETPOINT):
                self._state[key] = value

    def control(
        self,
        report: Mapping[str, float],
        active: BenignEvent | None,
        elapsed_hours: float,
        dt_seconds: float,
    ) -> Mapping[str, float]:
        """Run both loops on every stage, each on what its own transmitter reported."""
        commands: dict[str, float] = {}
        for train in range(self._trains):
            for stage in range(self._stages):
                here = (train, stage)
                commands[self._tag(PUMP_SPEED, train, stage)] = self._level_loops[here].update(
                    measurement=report[self._tag(LEVEL, train, stage)],
                    setpoint=report[self._tag(LEVEL_SETPOINT, train, stage)],
                    dt_seconds=dt_seconds,
                    bias=self._pump_bias[here],
                )
                commands[self._tag(DUTY, train, stage)] = self._temperature_loops[here].update(
                    measurement=report[self._tag(TEMPERATURE, train, stage)],
                    setpoint=report[self._tag(TEMPERATURE_SETPOINT, train, stage)],
                    dt_seconds=dt_seconds,
                    bias=self._duty_bias[here],
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
        """Advance the chain one sample: flows, then levels, then the heat those levels carry."""
        demand = self._demand(elapsed_hours) * self._surge(active)
        share = demand / self._trains
        ambient = self._ambient(elapsed_hours)
        feed = self._feed_temperature(active)
        advanced: dict[str, float] = {
            self._ambient_tag: ambient,
            self._outflow_tag: demand,
        }

        for train in range(self._trains):
            flows = [
                self._flow(state, actuators, train, stage, dt_seconds)
                for stage in range(self._stages)
            ]
            inlet = feed
            for stage in range(self._stages):
                out = flows[stage + 1] if stage + 1 < self._stages else share
                level = accumulate(
                    state[self._tag(LEVEL, train, stage)],
                    rate_per_second=(flows[stage] - out) / self._tank_area_m2 / 3600.0,
                    dt_seconds=dt_seconds,
                    low=0.0,
                    high=self._level_span_m,
                )
                temperature = self._temperature(
                    state[self._tag(TEMPERATURE, train, stage)],
                    level=level,
                    inlet=inlet,
                    flow=flows[stage],
                    duty=actuators[self._tag(DUTY, train, stage)],
                    ambient=ambient,
                    dt_seconds=dt_seconds,
                )
                advanced[flow_state_key(train, stage)] = flows[stage]
                advanced[self._tag(LEVEL, train, stage)] = level
                advanced[self._tag(TEMPERATURE, train, stage)] = temperature
                advanced[self._tag(PUMP_SPEED, train, stage)] = actuators[
                    self._tag(PUMP_SPEED, train, stage)
                ]
                advanced[self._tag(DUTY, train, stage)] = actuators[self._tag(DUTY, train, stage)]
                advanced[self._tag(LEVEL_SETPOINT, train, stage)] = state[
                    self._tag(LEVEL_SETPOINT, train, stage)
                ]
                advanced[self._tag(TEMPERATURE_SETPOINT, train, stage)] = state[
                    self._tag(TEMPERATURE_SETPOINT, train, stage)
                ]
                if self._plant_spec.has_role(INFLOW, train, stage):
                    advanced[self._tag(INFLOW, train, stage)] = flows[stage]
                inlet = temperature
        return advanced

    def conservation_residuals(
        self, steps: Sequence[PlantStep], interval_seconds: float
    ) -> Mapping[str, float]:
        """Return each tank's volume balance residual over the run.

        Volume only. The energy balance on these vessels is checked indirectly, through the
        temperature loops' ability to hold setpoint, because stating it here would mean dividing
        by a thermal mass that the *other* loop is moving sample by sample — and a residual whose
        denominator is itself a controlled variable says more about the level loop than about the
        energy.

        Args:
            steps: Every sample of the run, in order.
            interval_seconds: The integration step.

        Returns:
            ``{"train N tank M volume": relative residual}``.
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
                residuals[f"train {train + 1} tank {stage + 1} volume"] = (
                    inflow - outflow - stored
                ) / throughput
        return residuals

    def tracking_loops(self) -> tuple[str, ...]:
        """Both loops on every stage. This plant is continuous, so both hold throughout."""
        return tuple(
            loop
            for train in range(self._trains)
            for stage in range(self._stages)
            for loop in (level_loop_id(train, stage), temperature_loop_id(train, stage))
        )

    def _temperature(
        self,
        previous: float,
        *,
        level: float,
        inlet: float,
        flow: float,
        duty: float,
        ambient: float,
        dt_seconds: float,
    ) -> float:
        """Return one tank's temperature after this sample.

        The capacity is recomputed from the *current* level, which is the hybrid coupling: a
        half-empty tank has half the thermal mass and warms twice as fast for the same duty.
        """
        holdup_m3 = max(level, self._level_span_m * _MIN_HOLDUP_FRACTION) * self._tank_area_m2
        capacity = holdup_m3 * self._density_kg_per_m3 * self._heat_capacity
        flow_capacity = max(flow * self._density_kg_per_m3 / 3600.0 * self._heat_capacity, 1e-9)
        after_flow = first_order(
            previous,
            target=inlet,
            dt_seconds=dt_seconds,
            tau_seconds=capacity / flow_capacity,
        )
        heater_kw = clamp(duty, 0.0, 100.0) / 100.0 * self._heater_rated_kw
        loss_kw = self._ua_kw_per_k * (previous - ambient)
        return clamp(
            after_flow + (heater_kw - loss_kw) * dt_seconds / capacity,
            0.0,
            self._temperature_span_c,
        )

    def _flow(
        self,
        state: Mapping[str, float],
        actuators: Mapping[str, float],
        train: int,
        stage: int,
        dt_seconds: float,
    ) -> float:
        """Return one stage's flow this sample: the pump's demand, reached with a lag."""
        commanded = square_law_flow(
            clamp(actuators[self._tag(PUMP_SPEED, train, stage)], 0.0, 100.0),
            self._max_pump_flow_m3ph,
        )
        previous = state[flow_state_key(train, stage)]
        reached: float = previous + (commanded - previous) * min(1.0, dt_seconds / self._flow_tau_s)
        return reached

    def _demand(self, elapsed_hours: float) -> float:
        """Return the draw on the chain: a daily rhythm with a floor under it."""
        swing = cycle_factor(
            elapsed_hours,
            period_hours=24.0,
            amplitude=self._demand_daily_m3ph,
            phase_hours=6.0,
        )
        return max(self._demand_base_m3ph + swing, self._demand_floor_m3ph)

    def _ambient(self, elapsed_hours: float) -> float:
        """Return the temperature of the room, which nobody controls."""
        return self._ambient_base_c + cycle_factor(
            elapsed_hours,
            period_hours=24.0,
            amplitude=self._ambient_daily_c,
            phase_hours=15.0,
        )

    def _surge(self, active: BenignEvent | None) -> float:
        """Return the multiplier a demand surge is applying, or one."""
        if active is None or active.kind != DEMAND_SURGE:
            return 1.0
        return 1.0 + active.parameters.get("demand_surge_fraction", 0.0)

    def _feed_temperature(self, active: BenignEvent | None) -> float:
        """Return what is arriving at the front of the chain, colder during an excursion."""
        if active is None or active.kind != COLD_FEED:
            return self._feed_temp_c
        return self._feed_temp_c - active.parameters.get("feed_drop_c", 0.0)

    def _speed_for(self, flow: float) -> float:
        """Return the pump speed that delivers a flow, inverting the square-law characteristic."""
        return 100.0 * clamp(flow / self._max_pump_flow_m3ph, 0.0, 1.0) ** 2

    def _tag(self, role: str, train: int = 0, stage: int = 0) -> str:
        """Return the tag name playing a role, which the spec drew and this class never guesses."""
        return self._plant_spec.tag(role, train=train, stage=stage)


register_template(HEATED_CHAIN_PROCESS, HeatedChainPlant)

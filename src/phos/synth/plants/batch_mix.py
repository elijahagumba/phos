"""Parallel batch trains, each stepping through a recipe rather than holding an operating point.

PART R2's fourth generated process, and the one whose notion of normal is a *sequence*. A tank
chain and a generating set have an operating point and spend their lives near it. A batch reactor
never settles: it fills, heats, reacts and empties, and starts again. The same temperature is
ordinary in one step of the recipe and impossible in another, so a model that learned a range for
each signal has learned almost nothing — what it needs is which step the plant is on, and the
only honest way to know that is from the signals themselves.

**Trains run independently and are deliberately not in step.** Each train's recipe is started at a
staggered offset, so at any instant one may be charging while another is discharging. A detector
cannot assume the site has one state, which is how a multi-train plant actually behaves and is the
thing a single-train model gets wrong.

**The couplings worth having.**

* Conversion rises with temperature through an Arrhenius rate, so a vessel held cooler converts
  slower and the recipe takes longer — a change in one signal shows up as a change in the *timing*
  of others.
* The agitator's power draw rises as the batch converts, because the mixture thickens. It is the
  only window onto conversion that is not the conversion meter itself, which makes the pair a
  relationship an attacker has to fake twice.
* Temperature is controlled through a cascade: a slow outer loop decides what the jacket should
  be at, and a fast inner loop gets the jacket there. Breaking the outer loop's reading moves the
  jacket in a way the inner loop faithfully carries out, which is a more interesting failure than
  moving a valve directly.

**What this is not.** A model of a batch process written from the general shape of one — not a
model of any particular reactor, and not validated against one. See ``MODEL_NOT_REALITY_CAVEAT``.
"""

import math
from collections.abc import Mapping, Sequence
from enum import IntEnum
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
from phos.synth.process import PiController, clamp, first_order, square_law_flow
from phos.synth.realism import RealismProfile
from phos.synth.templates import register_template

__all__ = [
    "AGITATOR_POWER",
    "AGITATOR_SPEED",
    "BATCH_MIX_PROCESS",
    "CHARGE",
    "CONVERSION",
    "DUTY",
    "FEED_VALVE",
    "JACKET_TEMPERATURE",
    "PHASE",
    "RECIPE_CHANGE",
    "TEMPERATURE",
    "TEMPERATURE_SETPOINT",
    "BatchMixPlant",
    "Phase",
    "converted_state_key",
    "jacket_loop_id",
    "temperature_loop_id",
    "timer_state_key",
]

BATCH_MIX_PROCESS: Final = "batch-mix-v1"
"""The name a spec puts in its ``process`` field to run on this physics."""

PHASE: Final = "phase"
CHARGE: Final = "charge"
TEMPERATURE: Final = "temperature"
TEMPERATURE_SETPOINT: Final = "temperature_setpoint"
JACKET_TEMPERATURE: Final = "jacket_temperature"
DUTY: Final = "duty"
FEED_VALVE: Final = "feed_valve"
AGITATOR_SPEED: Final = "agitator_speed"
AGITATOR_POWER: Final = "agitator_power"
CONVERSION: Final = "conversion"
"""The role vocabulary this process reads."""

RECIPE_CHANGE: Final = "recipe_change"
"""A benign event: an operator moves the reaction temperature the recipe calls for."""

HOLD_CHANGE: Final = "extended_hold"
"""A benign event: the react step is held longer than the recipe's default."""


class Phase(IntEnum):
    """Which step of the recipe a train is on.

    Published as a register value, which is why it is an integer a sensor can carry rather than a
    string. A detector reading this corpus sees the number; what it means is in the role map.

    Attributes:
        IDLE: Empty and waiting for the next batch.
        CHARGE: Filling with reagent.
        HEAT: Full, warming to reaction temperature.
        REACT: At temperature, converting.
        DISCHARGE: Emptying the finished batch.
    """

    IDLE = 0
    CHARGE = 1
    HEAT = 2
    REACT = 3
    DISCHARGE = 4


def temperature_loop_id(train: int) -> str:
    """Return the controller identifier of one train's outer temperature loop."""
    return f"reactor_temperature_t{train}"


def jacket_loop_id(train: int) -> str:
    """Return the controller identifier of one train's inner jacket loop."""
    return f"jacket_temperature_t{train}"


def timer_state_key(train: int) -> str:
    """Return the internal state key holding how long a train has been in its phase."""
    return f"_phase_timer_t{train}"


def converted_state_key(train: int) -> str:
    """Return the internal state key holding how much of a train's batch has converted.

    Internal because conversion is published as a percentage and the mass is what the physics
    carries forward; deriving one from the other every sample would lose it whenever the vessel
    is empty.
    """
    return f"_converted_kg_t{train}"


class BatchMixPlant(Plant):
    """Parallel batch trains, each stepping through a recipe its spec sizes and tunes.

    See the module docstring for the process, the phases and the couplings.
    """

    def __init__(
        self,
        spec: RunSpec,
        *,
        commands: CommandSource | None = None,
        realism: RealismProfile | None = None,
        plant_spec: PlantSpec | None = None,
    ) -> None:
        """Build the trains and their cascades for one run.

        Args:
            spec: The run to prepare for.
            commands: Who writes over the control network, or ``None``. See
                `phos.synth.plant.Plant`.
            realism: Ordinary trouble to apply, or ``None`` for a quiet profile.
            plant_spec: The plant to build. Required: this is a process, not a plant.

        Raises:
            ValueError: If no spec is given.
        """
        if plant_spec is None:
            raise ValueError(
                "BatchMixPlant has no default plant: it is a process, not a plant. Draw one from "
                "the batch_mix family, or build a spec by hand."
            )
        self._plant_spec = plant_spec
        self._description = plant_spec.describe()
        p = plant_spec.parameters
        self._trains = round(p["trains"])
        self._full_charge_kg = p["full_charge_kg"]
        self._feed_kgph = p["feed_kgph"]
        self._discharge_kgph = p["discharge_kgph"]
        self._heat_capacity = p["heat_capacity_kj_per_kg_k"]
        self._vessel_thermal_kg = p["vessel_thermal_kg"]
        self._wall_ua_kw_per_k = p["wall_ua_kw_per_k"]
        self._reaction_enthalpy = p["reaction_enthalpy_kj_per_kg"]
        self._prefactor = p["arrhenius_prefactor"]
        self._activation_k = p["arrhenius_temperature_k"]
        self._jacket_tau_s = p["jacket_tau_s"]
        self._jacket_cold_c = p["jacket_cold_c"]
        self._jacket_hot_c = p["jacket_hot_c"]
        self._feed_temp_c = p["feed_temp_c"]
        self._reaction_temp_c = p["reaction_temp_c"]
        self._temperature_span_c = p["temperature_span_c"]
        self._idle_seconds = p["idle_seconds"]
        self._hold_seconds = p["hold_seconds"]
        self._conversion_target = p["conversion_target_pct"]
        self._arrival_margin_c = p["arrival_margin_c"]
        self._agitator_base_kw = p["agitator_base_kw"]
        self._agitator_rated_kw = p["agitator_rated_kw"]
        self._agitator_rated_rpm = p["agitator_rated_rpm"]
        self._agitator_idle_rpm = p["agitator_idle_rpm"]
        self._viscosity_per_conversion = p["viscosity_per_conversion"]
        self._stagger_seconds = p["stagger_seconds"]

        self._masters: dict[int, PiController] = {}
        self._slaves: dict[int, PiController] = {}
        self._slave_bias: dict[int, float] = {}
        for train in range(self._trains):
            self._masters[train] = pi_controller(plant_spec, temperature_loop_id(train))
            self._slaves[train] = pi_controller(plant_spec, jacket_loop_id(train))
            self._slave_bias[train] = plant_spec.controller(jacket_loop_id(train)).bias
        super().__init__(spec, commands=commands, realism=realism)

    @property
    def description(self) -> PlantDescription:
        """What these trains are, as the spec declared them."""
        return self._description

    def initial_state(self) -> Mapping[str, float]:
        """Start every train idle, staggered so they do not run the recipe in lockstep.

        The stagger is applied as a head start on the idle timer, so train two is already part way
        through waiting when the run begins. Without it every train charges at the same instant
        for the whole run, and a detector could learn one train and know all of them.
        """
        state: dict[str, float] = {}
        for train in range(self._trains):
            state[timer_state_key(train)] = train * self._stagger_seconds
            state[converted_state_key(train)] = 0.0
            state[self._tag(PHASE, train)] = float(Phase.IDLE)
            state[self._tag(CHARGE, train)] = 0.0
            state[self._tag(TEMPERATURE, train)] = self._feed_temp_c
            state[self._tag(TEMPERATURE_SETPOINT, train)] = self._reaction_temp_c
            state[self._tag(JACKET_TEMPERATURE, train)] = self._jacket_cold_c
            state[self._tag(DUTY, train)] = 0.0
            state[self._tag(FEED_VALVE, train)] = 0.0
            state[self._tag(AGITATOR_SPEED, train)] = self._agitator_idle_rpm
            state[self._tag(AGITATOR_POWER, train)] = self._agitator_base_kw
            state[self._tag(CONVERSION, train)] = 0.0
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
        """Apply the lasting part of an event: a moved reaction temperature."""
        for key, value in event.parameters.items():
            role = self._plant_spec.role_of(key)
            if role is not None and role.role == TEMPERATURE_SETPOINT and key in self._state:
                self._state[key] = value

    def control(
        self,
        report: Mapping[str, float],
        active: BenignEvent | None,
        elapsed_hours: float,
        dt_seconds: float,
    ) -> Mapping[str, float]:
        """Run each train's cascade and the actuators its phase dictates.

        The feed valve and the agitator are not regulated: the recipe opens and shuts them by
        phase, which is what a batch plant does and is why they are not declared as loops.
        """
        commands: dict[str, float] = {}
        for train in range(self._trains):
            phase = Phase(round(report[self._tag(PHASE, train)]))
            jacket_target = self._jacket_demand(train, phase, report, dt_seconds)
            commands[self._tag(DUTY, train)] = self._slaves[train].update(
                measurement=report[self._tag(JACKET_TEMPERATURE, train)],
                setpoint=jacket_target,
                dt_seconds=dt_seconds,
                bias=self._slave_bias[train],
            )
            commands[self._tag(FEED_VALVE, train)] = 100.0 if phase is Phase.CHARGE else 0.0
            commands[self._tag(AGITATOR_SPEED, train)] = (
                self._agitator_rated_rpm
                if phase in (Phase.HEAT, Phase.REACT)
                else self._agitator_idle_rpm
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
        """Advance every train one sample: inventory, then heat, then reaction, then the phase."""
        hold = self._hold_for(active)
        advanced: dict[str, float] = {}
        for train in range(self._trains):
            advanced.update(self._advance_train(state, actuators, train, dt_seconds, hold))
        return advanced

    def _advance_train(
        self,
        state: Mapping[str, float],
        actuators: Mapping[str, float],
        train: int,
        dt_seconds: float,
        hold_seconds: float,
    ) -> dict[str, float]:
        """Advance one train and return everything it owns."""
        phase = Phase(round(state[self._tag(PHASE, train)]))
        level = state[self._tag(CHARGE, train)]
        mass = level / 100.0 * self._full_charge_kg
        converted = state[converted_state_key(train)]
        temperature = state[self._tag(TEMPERATURE, train)]

        feed = square_law_flow(
            clamp(actuators[self._tag(FEED_VALVE, train)], 0.0, 100.0), self._feed_kgph
        )
        charged = feed * dt_seconds / 3600.0
        drawn = (
            min(self._discharge_kgph * dt_seconds / 3600.0, mass)
            if phase is Phase.DISCHARGE
            else 0.0
        )
        share = converted / mass if mass > 1e-9 else 0.0
        converted = max(converted - drawn * share, 0.0)
        mass = clamp(mass - drawn + charged, 0.0, self._full_charge_kg)

        jacket = first_order(
            state[self._tag(JACKET_TEMPERATURE, train)],
            target=self._jacket_temperature(actuators[self._tag(DUTY, train)]),
            dt_seconds=dt_seconds,
            tau_seconds=self._jacket_tau_s,
        )

        # Cold reagent mixes with what is already in the vessel before any heat moves, which is
        # what makes a charge cool the batch down and gives the heat step something to do.
        holdup = (mass - charged) + self._vessel_thermal_kg
        mixed = (holdup * temperature + charged * self._feed_temp_c) / max(holdup + charged, 1e-9)
        capacity = (mass + self._vessel_thermal_kg) * self._heat_capacity
        # The wall term is an exponential approach rather than an Euler step: at low holdup the
        # explicit form has a gain above two per sample and diverges, which is an artefact and
        # not a reactor. `phos.synth.plants.batch` argues the same point.
        after_wall = first_order(
            mixed,
            target=jacket,
            dt_seconds=dt_seconds,
            tau_seconds=capacity / max(self._wall_ua_kw_per_k, 1e-9),
        )

        rate_per_second = self._prefactor * math.exp(-self._activation_k / (temperature + 273.15))
        unconverted = max(mass - converted, 0.0)
        reacted = min(rate_per_second * unconverted * dt_seconds, unconverted)
        converted += reacted
        temperature = clamp(
            after_wall + reacted * self._reaction_enthalpy / max(capacity, 1e-9),
            0.0,
            self._temperature_span_c,
        )

        level = 100.0 * mass / self._full_charge_kg
        conversion = 100.0 * converted / mass if mass > 1e-9 else 0.0
        speed = clamp(actuators[self._tag(AGITATOR_SPEED, train)], 0.0, self._agitator_rated_rpm)
        power = self._agitator_power(speed, conversion, level)

        timer = state[timer_state_key(train)] + dt_seconds
        next_phase, timer = self._next_phase(
            phase, timer, level, temperature, conversion, state, train, hold_seconds
        )

        return {
            timer_state_key(train): timer,
            converted_state_key(train): converted,
            self._tag(PHASE, train): float(next_phase),
            self._tag(CHARGE, train): level,
            self._tag(TEMPERATURE, train): temperature,
            self._tag(TEMPERATURE_SETPOINT, train): state[self._tag(TEMPERATURE_SETPOINT, train)],
            self._tag(JACKET_TEMPERATURE, train): jacket,
            self._tag(DUTY, train): actuators[self._tag(DUTY, train)],
            self._tag(FEED_VALVE, train): actuators[self._tag(FEED_VALVE, train)],
            self._tag(AGITATOR_SPEED, train): speed,
            self._tag(AGITATOR_POWER, train): power,
            self._tag(CONVERSION, train): conversion,
        }

    def conservation_residuals(
        self, steps: Sequence[PlantStep], interval_seconds: float
    ) -> Mapping[str, float]:
        """Return each train's mass balance residual over the run.

        What was charged less what was discharged has to equal what is still in the vessel. The
        charge and discharge rates are recomputed here from the actuators and the phase rather
        than read from a meter, because this process declares no feed flow transmitter — the
        quantity exists in the process and not in the instrument set.

        Args:
            steps: Every sample of the run, in order.
            interval_seconds: The integration step.

        Returns:
            ``{"train N mass": relative residual}``.
        """
        residuals: dict[str, float] = {}
        if len(steps) < 2:
            return residuals
        hours = interval_seconds / 3600.0
        for train in range(self._trains):
            charged = 0.0
            drawn = 0.0
            for step in steps[:-1]:
                values = step.truth.values
                charged += (
                    square_law_flow(
                        clamp(values[self._tag(FEED_VALVE, train)], 0.0, 100.0), self._feed_kgph
                    )
                    * hours
                )
                if Phase(round(values[self._tag(PHASE, train)])) is Phase.DISCHARGE:
                    drawn += min(
                        self._discharge_kgph * hours,
                        values[self._tag(CHARGE, train)] / 100.0 * self._full_charge_kg,
                    )
            stored = (
                (
                    steps[-1].truth.values[self._tag(CHARGE, train)]
                    - steps[0].truth.values[self._tag(CHARGE, train)]
                )
                / 100.0
                * self._full_charge_kg
            )
            throughput = max(charged, drawn, 1e-9)
            residuals[f"train {train + 1} mass"] = (charged - drawn - stored) / throughput
        return residuals

    def tracking_loops(self) -> tuple[str, ...]:
        """None of them, and that is the point of a batch plant.

        The temperature cascade is deliberately nowhere near its setpoint while the vessel is
        filling or emptying — the recipe holds a fixed service temperature in those steps — so
        judging it against setpoint across a whole run would refuse every correct plant. Whether
        the batch actually reaches temperature is visible instead in the phase machine: a vessel
        that never heats never leaves the heat step, which the variability check then catches
        because the phase signal stops moving.
        """
        return ()

    def _next_phase(
        self,
        phase: Phase,
        timer: float,
        level: float,
        temperature: float,
        conversion: float,
        state: Mapping[str, float],
        train: int,
        hold_seconds: float,
    ) -> tuple[Phase, float]:
        """Return the phase this train is on next, and its timer.

        Each transition is on a *measurable* condition — the vessel is full, the batch is up to
        temperature, it has converted enough — rather than on a fixed clock, so a train whose
        heating is slowed takes longer rather than moving on regardless. That is what makes the
        recipe's timing a signal in its own right.
        """
        target = state[self._tag(TEMPERATURE_SETPOINT, train)]
        if phase is Phase.IDLE:
            return (Phase.CHARGE, 0.0) if timer >= self._idle_seconds else (phase, timer)
        if phase is Phase.CHARGE:
            return (Phase.HEAT, 0.0) if level >= 99.0 else (phase, timer)
        if phase is Phase.HEAT:
            arrived = temperature >= target - self._arrival_margin_c
            return (Phase.REACT, 0.0) if arrived else (phase, timer)
        if phase is Phase.REACT:
            done = conversion >= self._conversion_target or timer >= hold_seconds
            return (Phase.DISCHARGE, 0.0) if done else (phase, timer)
        return (Phase.IDLE, 0.0) if level <= 1.0 else (phase, timer)

    def _jacket_demand(
        self, train: int, phase: Phase, report: Mapping[str, float], dt_seconds: float
    ) -> float:
        """Return the jacket temperature the recipe calls for in this phase.

        Only the heat and react steps are under closed-loop control; charging and discharging hold
        a fixed service temperature, which is what a recipe actually specifies. The outer loop is
        still stepped in those phases so its integral does not go stale between batches.
        """
        demand = self._masters[train].update(
            measurement=report[self._tag(TEMPERATURE, train)],
            setpoint=report[self._tag(TEMPERATURE_SETPOINT, train)],
            dt_seconds=dt_seconds,
        )
        if phase in (Phase.HEAT, Phase.REACT):
            return demand
        return self._jacket_cold_c

    def _jacket_temperature(self, duty: float) -> float:
        """Return the jacket temperature a valve position blends to."""
        fraction = clamp(duty, 0.0, 100.0) / 100.0
        return self._jacket_cold_c + (self._jacket_hot_c - self._jacket_cold_c) * fraction

    def _agitator_power(self, speed: float, conversion: float, level: float) -> float:
        """Return the agitator's power draw: cube of speed, by how full and how thick it is.

        The viscosity term is the useful part. The batch thickens as it converts, the drive feels
        it, and that makes the agitator's power a second witness to conversion — one an attacker
        faking the conversion meter has to fake as well.
        """
        thickness = 1.0 + self._viscosity_per_conversion * conversion / 100.0
        duty = (speed / max(self._agitator_rated_rpm, 1e-9)) ** 3 * level / 100.0
        return self._agitator_base_kw + self._agitator_rated_kw * duty * thickness

    def _hold_for(self, active: BenignEvent | None) -> float:
        """Return how long the react step holds, longer during an extended hold."""
        if active is None or active.kind != HOLD_CHANGE:
            return self._hold_seconds
        return self._hold_seconds * (1.0 + active.parameters.get("hold_extension", 0.0))

    def _tag(self, role: str, train: int = 0) -> str:
        """Return the tag name playing a role, which the spec drew and this class never guesses."""
        return self._plant_spec.tag(role, train=train, stage=0)


register_template(BATCH_MIX_PROCESS, BatchMixPlant)

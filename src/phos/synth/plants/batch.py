"""A jacketed batch reactor running an exothermic reaction, simulated.

The process: a stirred tank is charged with reagent, heated to reaction temperature through a
split-range jacket, held while an exothermic reaction converts the charge, then discharged. Then
it does it again. A cascade controller holds reactor temperature by moving a jacket temperature
setpoint, and a slave loop holds the jacket there by moving one valve that selects hot utility at
one end of its travel and chilled water at the other.

**Why this process, given there are already two continuous ones.** Its normal is a *sequence*, not
an operating point. Every signal here spends its life moving between regimes that have nothing in
common: a reactor at 25 C with an empty vessel and no agitation is perfectly normal during a
changeover and would be alarming halfway through a hold. A model that has learned the marginal
distribution of any one signal has learned almost nothing, because the question is never "is this
value normal" but "is this value normal *now*". That is a different kind of hard from anything a
water works or a generating set poses, and it is why the third plant is a batch plant.

**The couplings, which are the point.**

- ``conversion_pct`` integrates an Arrhenius rate in ``reactor_temp_c`` against the reagent still
  unconverted. Ten degrees roughly doubles it, so temperature does not merely correlate with
  conversion — it sets its speed.
- ``reactor_temp_c`` integrates the exotherm that conversion releases, plus heat through the
  jacket wall driven by ``jacket_temp_c`` minus reactor temperature. The reaction heats the
  reactor and the reactor speeds the reaction, which is the positive feedback every exothermic
  batch process is arranged to contain.
- ``reactor_level_pct`` integrates ``reagent_feed_kgph`` less the discharge rate.
- ``reactor_pressure_barg`` is vapour pressure — exponential in ``reactor_temp_c`` — scaled by how
  much liquid ``reactor_level_pct`` says is in the vessel.
- ``agitator_power_kw`` goes with the cube of ``agitator_speed_rpm``, with the liquid depth, and
  with a viscosity that rises as ``conversion_pct`` does. In a real plant that makes agitator
  power a soft sensor for conversion, and here it makes it a signal that ties three others
  together.
- ``jacket_flow_m3ph`` is **not monotonic** in ``jacket_valve_pct``. The valve is split-range:
  utility flows at both ends of its travel and neither at the middle, so flow is a V in valve
  position. Any model that assumes monotone relationships gets this one wrong, which is exactly
  why it is here.

**No control network, and that is an answer rather than an omission.** A jacketed reactor of this
kind is normally run from a DCS over a fieldbus Atlas cannot dissect. Emitting Modbus for it would
be fake realism. The consequence is a plant where Atlas has telemetry and no command visibility at
all — useful to D3, which is charged with mapping where Atlas goes blind, and where "no capture
exists for this process" is one of the honest answers.

**What this is not.** A model of batch reaction written from public descriptions of cascade
temperature control, Arrhenius kinetics and split-range jacket service. Not a model of any
particular reactor, and not validated against one. See `MODEL_NOT_REALITY_CAVEAT`.
"""

import math
from collections.abc import Mapping, Sequence
from typing import Final

from numpy.random import Generator

from phos.synth.command import CommandSource
from phos.synth.plant import (
    BenignEvent,
    Coupling,
    CouplingKind,
    EventPlan,
    PhysicalUnit,
    Plant,
    PlantDescription,
    RunSpec,
    SignalKind,
    SignalSpec,
    lay_out_events,
)
from phos.synth.process import PiController, clamp, first_order, square_law_flow
from phos.synth.realism import RealismProfile

__all__ = [
    "AGITATOR_POWER",
    "AGITATOR_SPEED",
    "BATCH_DESCRIPTION",
    "BATCH_PHASE",
    "CONVERSION",
    "FEED_VALVE",
    "JACKET_FLOW",
    "JACKET_TEMP",
    "JACKET_VALVE",
    "REACTOR_LEVEL",
    "REACTOR_PRESSURE",
    "REACTOR_TEMP",
    "REAGENT_FEED",
    "TEMP_SETPOINT",
    "BatchReactorPlant",
    "Phase",
]

BATCH_PHASE: Final = "batch_phase"
REACTOR_TEMP: Final = "reactor_temp_c"
REACTOR_PRESSURE: Final = "reactor_pressure_barg"
REACTOR_LEVEL: Final = "reactor_level_pct"
CONVERSION: Final = "conversion_pct"
JACKET_TEMP: Final = "jacket_temp_c"
JACKET_VALVE: Final = "jacket_valve_pct"
JACKET_FLOW: Final = "jacket_flow_m3ph"
FEED_VALVE: Final = "feed_valve_pct"
REAGENT_FEED: Final = "reagent_feed_kgph"
AGITATOR_SPEED: Final = "agitator_speed_rpm"
AGITATOR_POWER: Final = "agitator_power_kw"
TEMP_SETPOINT: Final = "reactor_temp_setpoint_c"

PHASE_TIMER: Final = "phase_timer_s"
REAGENT_MASS: Final = "reagent_mass_kg"
CONVERTED_MASS: Final = "converted_mass_kg"
CHARGE_TARGET: Final = "charge_target_pct"
HOLD_SECONDS: Final = "react_hold_s"
AGITATOR_TARGET: Final = "agitator_target_rpm"
BATCH_COUNT: Final = "batches_completed"

RECIPE_CHANGE: Final = "recipe_change"
EXTENDED_HOLD: Final = "extended_hold"
AGITATOR_CHANGE: Final = "agitator_speed_change"
CHARGE_SIZE_CHANGE: Final = "charge_size_change"


class Phase:
    """The batch phases, as the ordinal a phase register actually carries.

    A namespace of integers rather than an `Enum` because this is a *signal value*: it is
    published as a number, learned as a number, and would have to be converted back to one
    anywhere it was used.

    Attributes:
        IDLE: Vessel empty between batches.
        CHARGE: Reagent being fed in.
        HEAT: Vessel being brought up to reaction temperature.
        REACT: Exothermic hold while the charge converts.
        DISCHARGE: Product being pumped out.
    """

    IDLE: Final = 0
    CHARGE: Final = 1
    HEAT: Final = 2
    REACT: Final = 3
    DISCHARGE: Final = 4


_FULL_CHARGE_KG: Final = 4500.0
_MAX_FEED_KGPH: Final = 5400.0
_DISCHARGE_KGPH: Final = 7200.0
_HEAT_CAPACITY_KJ_PER_KG_K: Final = 2.0
_WALL_UA_KJ_PER_S_K: Final = 25.0
_REACTION_ENTHALPY_KJ_PER_KG: Final = 160.0
_ARRHENIUS_PREFACTOR: Final = 2.9e6
_ARRHENIUS_TEMPERATURE_K: Final = 8000.0
"""Activation energy over the gas constant, in kelvin. Sized so ten degrees roughly doubles rate."""

_JACKET_TAU_S: Final = 240.0
_JACKET_HOT_C: Final = 90.0
_JACKET_SPAN_C: Final = 0.85
_JACKET_PICKUP: Final = 0.30
_MAX_JACKET_FLOW_M3PH: Final = 32.0
_IDLE_SECONDS: Final = 900.0
_DEFAULT_HOLD_S: Final = 5400.0
_CHARGE_JACKET_C: Final = 25.0
"""Jacket held here while charging: a recipe does not heat a vessel it is still filling."""

_DISCHARGE_JACKET_C: Final = 35.0
"""Jacket held here while discharging: the batch is cooled down before it is pumped out."""

_HEAT_ARRIVAL_MARGIN_C: Final = 1.5
_CONVERSION_TARGET_PCT: Final = 96.0
_EMPTY_LEVEL_PCT: Final = 3.0
_VESSEL_THERMAL_KG: Final = 250.0
"""Steel equivalent of the empty vessel, so an idle reactor still has heat capacity."""

_FEED_TEMP_C: Final = 20.0
"""Reagent arrives at store temperature, which is what cools the vessel down on every charge."""

_PRESSURE_COEFFICIENT: Final = 0.0263
_PRESSURE_EXPONENT: Final = 0.0536
_AGITATOR_BASE_KW: Final = 0.5
_AGITATOR_RATED_KW: Final = 22.0
_AGITATOR_RATED_RPM: Final = 120.0
_VISCOSITY_PER_CONVERSION: Final = 1.8

BATCH_UNITS: Final = (
    PhysicalUnit(unit_id="reactor", label="Jacketed stirred-tank reactor"),
    PhysicalUnit(unit_id="jacket", label="Jacket service and utilities"),
    PhysicalUnit(unit_id="feed", label="Reagent feed system"),
    PhysicalUnit(unit_id="agitation", label="Agitator drive"),
)

BATCH_SIGNALS: Final = (
    SignalSpec(
        key=BATCH_PHASE,
        label="Batch phase",
        unit="step",
        kind=SignalKind.SENSOR,
        physical_unit="reactor",
        low=0.0,
        high=4.0,
        noise_stddev=0.0,
    ),
    SignalSpec(
        key=REACTOR_TEMP,
        label="Reactor temperature",
        unit="degC",
        kind=SignalKind.SENSOR,
        physical_unit="reactor",
        low=0.0,
        high=200.0,
        noise_stddev=0.06,
        drift_amplitude=0.12,
    ),
    SignalSpec(
        key=REACTOR_PRESSURE,
        label="Reactor pressure",
        unit="barg",
        kind=SignalKind.SENSOR,
        physical_unit="reactor",
        low=0.0,
        high=12.0,
        noise_stddev=0.008,
        drift_amplitude=0.015,
    ),
    SignalSpec(
        key=REACTOR_LEVEL,
        label="Reactor level",
        unit="%",
        kind=SignalKind.SENSOR,
        physical_unit="reactor",
        low=0.0,
        high=100.0,
        noise_stddev=0.10,
        drift_amplitude=0.15,
    ),
    SignalSpec(
        key=CONVERSION,
        label="Conversion",
        unit="%",
        kind=SignalKind.SENSOR,
        physical_unit="reactor",
        low=0.0,
        high=100.0,
        noise_stddev=0.22,
        drift_amplitude=0.30,
    ),
    SignalSpec(
        key=TEMP_SETPOINT,
        label="Reactor temperature setpoint",
        unit="degC",
        kind=SignalKind.SETPOINT,
        physical_unit="reactor",
        low=0.0,
        high=200.0,
        noise_stddev=0.0,
    ),
    SignalSpec(
        key=JACKET_TEMP,
        label="Jacket temperature",
        unit="degC",
        kind=SignalKind.SENSOR,
        physical_unit="jacket",
        low=-20.0,
        high=160.0,
        noise_stddev=0.08,
        drift_amplitude=0.15,
    ),
    SignalSpec(
        key=JACKET_VALVE,
        label="Jacket service valve",
        unit="%",
        kind=SignalKind.ACTUATOR,
        physical_unit="jacket",
        low=0.0,
        high=100.0,
        noise_stddev=0.08,
    ),
    SignalSpec(
        key=JACKET_FLOW,
        label="Jacket utility flow",
        unit="m3/h",
        kind=SignalKind.SENSOR,
        physical_unit="jacket",
        low=0.0,
        high=40.0,
        noise_stddev=0.07,
        drift_amplitude=0.10,
    ),
    SignalSpec(
        key=FEED_VALVE,
        label="Reagent feed valve",
        unit="%",
        kind=SignalKind.ACTUATOR,
        physical_unit="feed",
        low=0.0,
        high=100.0,
        noise_stddev=0.08,
    ),
    SignalSpec(
        key=REAGENT_FEED,
        label="Reagent feed rate",
        unit="kg/h",
        kind=SignalKind.SENSOR,
        physical_unit="feed",
        low=0.0,
        high=6000.0,
        noise_stddev=4.5,
        drift_amplitude=6.0,
    ),
    SignalSpec(
        key=AGITATOR_SPEED,
        label="Agitator speed",
        unit="rpm",
        kind=SignalKind.ACTUATOR,
        physical_unit="agitation",
        low=0.0,
        high=160.0,
        noise_stddev=0.12,
    ),
    SignalSpec(
        key=AGITATOR_POWER,
        label="Agitator power",
        unit="kW",
        kind=SignalKind.SENSOR,
        physical_unit="agitation",
        low=0.0,
        high=70.0,
        noise_stddev=0.09,
        drift_amplitude=0.14,
    ),
)

BATCH_COUPLINGS: Final = (
    Coupling(
        driven=CONVERSION,
        drivers=(REACTOR_TEMP, REACTOR_LEVEL),
        kind=CouplingKind.INTEGRATION,
        relation=(
            "conversion integrates an Arrhenius rate in reactor temperature against the reagent "
            "still unconverted; ten degrees roughly doubles the rate"
        ),
    ),
    Coupling(
        driven=REACTOR_TEMP,
        drivers=(JACKET_TEMP, CONVERSION, REACTOR_LEVEL, AGITATOR_POWER),
        kind=CouplingKind.INTEGRATION,
        relation=(
            "reactor temperature integrates heat through the jacket wall, the exotherm the "
            "conversion rate releases, and agitator work, over the thermal mass the charge implies"
        ),
    ),
    Coupling(
        driven=REACTOR_LEVEL,
        drivers=(REAGENT_FEED,),
        kind=CouplingKind.INTEGRATION,
        relation="level integrates the reagent fed in less the product pumped out on discharge",
    ),
    Coupling(
        driven=REACTOR_PRESSURE,
        drivers=(REACTOR_TEMP, REACTOR_LEVEL),
        kind=CouplingKind.ALGEBRAIC,
        relation=(
            "pressure is a vapour pressure exponential in reactor temperature, scaled by how much "
            "liquid the level implies"
        ),
    ),
    Coupling(
        driven=REAGENT_FEED,
        drivers=(FEED_VALVE,),
        kind=CouplingKind.ALGEBRAIC,
        relation="feed rate follows the square root of feed valve opening",
    ),
    Coupling(
        driven=JACKET_TEMP,
        drivers=(JACKET_VALVE, REACTOR_TEMP),
        kind=CouplingKind.LAG,
        relation=(
            "jacket temperature lags the utility temperature the split-range valve selects, "
            "pulled toward reactor temperature by what it picks up through the wall"
        ),
    ),
    Coupling(
        driven=JACKET_FLOW,
        drivers=(JACKET_VALVE,),
        kind=CouplingKind.ALGEBRAIC,
        relation=(
            "utility flow is a V in valve position, not monotone: the valve is split-range, so "
            "utility flows at both ends of its travel and neither at the middle"
        ),
    ),
    Coupling(
        driven=AGITATOR_POWER,
        drivers=(AGITATOR_SPEED, CONVERSION, REACTOR_LEVEL),
        kind=CouplingKind.ALGEBRAIC,
        relation=(
            "agitator power goes with the cube of speed, with liquid depth, and with a viscosity "
            "that rises as conversion does"
        ),
    ),
    Coupling(
        driven=JACKET_VALVE,
        drivers=(JACKET_TEMP, REACTOR_TEMP, TEMP_SETPOINT),
        kind=CouplingKind.CONTROL,
        relation=(
            "a cascade: the master loop turns reactor temperature error into a jacket temperature "
            "setpoint, and the slave loop holds the jacket there with the service valve"
        ),
    ),
    Coupling(
        driven=FEED_VALVE,
        drivers=(BATCH_PHASE, REACTOR_LEVEL),
        kind=CouplingKind.CONTROL,
        relation="the feed valve is open only during the charge phase, and shuts at target level",
    ),
    Coupling(
        driven=AGITATOR_SPEED,
        drivers=(BATCH_PHASE,),
        kind=CouplingKind.CONTROL,
        relation="agitator speed is set by the phase: stopped when idle, full through the hold",
    ),
)

BATCH_DESCRIPTION: Final = PlantDescription(
    plant_id="batch-reactor",
    label="Jacketed batch reactor",
    industry="chemical batch manufacturing",
    summary=(
        "A stirred tank charged with reagent, heated through a split-range jacket, held while an "
        "exothermic reaction converts the charge, then discharged — cycling through idle, charge, "
        "heat, react and discharge under cascade temperature control."
    ),
    model_source=(
        "Written from public descriptions of batch reaction control: cascade reactor/jacket "
        "temperature control, split-range jacket service, first-order Arrhenius kinetics with an "
        "exotherm fed back into the energy balance, and cube-law agitator power rising with "
        "viscosity. Not modelled on, or validated against, any particular reactor."
    ),
    units=BATCH_UNITS,
    signals=BATCH_SIGNALS,
    couplings=BATCH_COUPLINGS,
    control_network=None,
)

_EVENT_PLANS: Final = (
    EventPlan(
        kind=RECIPE_CHANGE,
        label="Grade change moves the reaction temperature",
        duration_steps=0,
        parameter_ranges={TEMP_SETPOINT: (78.0, 92.0)},
        detail="new reaction temperature:",
    ),
    EventPlan(
        kind=CHARGE_SIZE_CHANGE,
        label="Order size changes the charge",
        duration_steps=0,
        parameter_ranges={CHARGE_TARGET: (72.0, 92.0)},
        detail="new charge target:",
    ),
    EventPlan(
        kind=EXTENDED_HOLD,
        label="Quality hold extended pending a laboratory result",
        duration_steps=0,
        parameter_ranges={HOLD_SECONDS: (4800.0, 8400.0)},
        detail="new hold time:",
    ),
    EventPlan(
        kind=AGITATOR_CHANGE,
        label="Operator changes agitator speed",
        duration_steps=0,
        parameter_ranges={AGITATOR_TARGET: (95.0, 135.0)},
        detail="new agitator speed:",
    ),
)


class BatchReactorPlant(Plant):
    """A batch reactor cycling through five phases under cascade temperature control.

    See the module docstring for the process, the couplings and what the model is and is not.
    """

    def __init__(
        self,
        spec: RunSpec,
        *,
        commands: CommandSource | None = None,
        realism: RealismProfile | None = None,
    ) -> None:
        """Build the reactor and its cascade loops for one run.

        Args:
            spec: The run to prepare for.
            commands: Who writes over the control network, or ``None`` for the legacy
                echo path. See `phos.synth.plant.Plant`.
            realism: Ordinary trouble to apply, or ``None`` for a quiet profile. See
                `phos.synth.plant.Plant`.
        """
        self._master = PiController(gain=2.2, integral_time_seconds=900.0, low=5.0, high=90.0)
        self._slave = PiController(
            gain=3.5, integral_time_seconds=180.0, low=0.0, high=100.0, reverse_acting=True
        )
        super().__init__(spec, commands=commands, realism=realism)

    @property
    def description(self) -> PlantDescription:
        """The reactor: thirteen signals across four physical units, and no control network."""
        return BATCH_DESCRIPTION

    def initial_state(self) -> Mapping[str, float]:
        """Start empty, idle and cold — the state a reactor sits in between campaigns."""
        return {
            BATCH_PHASE: float(Phase.IDLE),
            REACTOR_TEMP: 24.0,
            REACTOR_PRESSURE: self._pressure(24.0, 0.0),
            REACTOR_LEVEL: 0.0,
            CONVERSION: 0.0,
            TEMP_SETPOINT: 85.0,
            JACKET_TEMP: 24.0,
            JACKET_VALVE: 50.0,
            JACKET_FLOW: self._utility_flow(50.0),
            FEED_VALVE: 0.0,
            REAGENT_FEED: 0.0,
            AGITATOR_SPEED: 0.0,
            AGITATOR_POWER: 0.0,
            PHASE_TIMER: 0.0,
            REAGENT_MASS: 0.0,
            CONVERTED_MASS: 0.0,
            CHARGE_TARGET: 85.0,
            HOLD_SECONDS: _DEFAULT_HOLD_S,
            AGITATOR_TARGET: 120.0,
            BATCH_COUNT: 0.0,
        }

    def schedule_events(self, rng: Generator, spec: RunSpec) -> Sequence[BenignEvent]:
        """Lay the four kinds of operational event through the run, round-robin."""
        return lay_out_events(
            rng,
            spec,
            _EVENT_PLANS,
            first_start_step=max(20, spec.n_steps // 10),
            gap_steps=(60, 400),
        )

    def begin_event(self, event: BenignEvent) -> None:
        """Apply a recipe, charge, hold or agitator change. All of them persist."""
        for key, value in event.parameters.items():
            self._state[key] = value

    def control(
        self,
        report: Mapping[str, float],
        active: BenignEvent | None,
        elapsed_hours: float,
        dt_seconds: float,
    ) -> Mapping[str, float]:
        """Run the cascade and the phase-driven actuators, on what the instruments reported."""
        phase = round(report[BATCH_PHASE])
        jacket_setpoint = self._jacket_setpoint(phase, report, dt_seconds)
        charging = phase == Phase.CHARGE
        return {
            JACKET_VALVE: self._slave.update(
                measurement=report[JACKET_TEMP],
                setpoint=jacket_setpoint,
                dt_seconds=dt_seconds,
                bias=50.0,
            ),
            FEED_VALVE: 100.0 if charging else 0.0,
            AGITATOR_SPEED: self._agitator_speed(phase),
        }

    def advance(
        self,
        state: Mapping[str, float],
        actuators: Mapping[str, float],
        active: BenignEvent | None,
        elapsed_hours: float,
        dt_seconds: float,
    ) -> Mapping[str, float]:
        """Advance the reactor one sample: inventory, then reaction, then heat, then the phase."""
        phase = round(state[BATCH_PHASE])
        feed = square_law_flow(actuators[FEED_VALVE], _MAX_FEED_KGPH)
        draw = _DISCHARGE_KGPH if phase == Phase.DISCHARGE else 0.0

        charged = feed * dt_seconds / 3600.0
        removed = min(draw * dt_seconds / 3600.0, state[REAGENT_MASS])
        held = state[REAGENT_MASS] - removed
        converted_share = (
            state[CONVERTED_MASS] / state[REAGENT_MASS] if state[REAGENT_MASS] else 0.0
        )
        converted = clamp(state[CONVERTED_MASS] - removed * converted_share, 0.0, held)
        mass = clamp(held + charged, 0.0, _FULL_CHARGE_KG)

        rate_per_second = _ARRHENIUS_PREFACTOR * math.exp(
            -_ARRHENIUS_TEMPERATURE_K / (state[REACTOR_TEMP] + 273.15)
        )
        reacted = min(rate_per_second * (mass - converted) * dt_seconds, mass - converted)
        converted = converted + reacted
        level = 100.0 * mass / _FULL_CHARGE_KG
        conversion = 100.0 * converted / mass if mass > 0.0 else 0.0

        agitator_power = self._agitator_power(actuators[AGITATOR_SPEED], conversion, level)
        jacket_temp = first_order(
            state[JACKET_TEMP],
            target=self._jacket_target(actuators[JACKET_VALVE], state[REACTOR_TEMP]),
            dt_seconds=dt_seconds,
            tau_seconds=_JACKET_TAU_S,
        )
        # Cold reagent mixes with whatever is already in the vessel before any heat moves. This is
        # what makes a charge cool the reactor down and gives the heat phase something to do.
        holdup = held + _VESSEL_THERMAL_KG
        mixed = (holdup * state[REACTOR_TEMP] + charged * _FEED_TEMP_C) / (holdup + charged)
        thermal_mass = (mass + _VESSEL_THERMAL_KG) * _HEAT_CAPACITY_KJ_PER_KG_K
        # The wall term is an exponential approach rather than an Euler step: at low holdup the
        # explicit form has a gain above two per sample and diverges, which is a numerical
        # artefact and not a reactor.
        after_wall = first_order(
            mixed,
            target=jacket_temp,
            dt_seconds=dt_seconds,
            tau_seconds=thermal_mass / _WALL_UA_KJ_PER_S_K,
        )
        source_kj = reacted * _REACTION_ENTHALPY_KJ_PER_KG + agitator_power * dt_seconds
        reactor_temp = clamp(after_wall + source_kj / thermal_mass, 0.0, 200.0)

        advanced = {
            BATCH_PHASE: float(phase),
            REACTOR_TEMP: reactor_temp,
            REACTOR_PRESSURE: self._pressure(reactor_temp, level),
            REACTOR_LEVEL: level,
            CONVERSION: conversion,
            TEMP_SETPOINT: state[TEMP_SETPOINT],
            JACKET_TEMP: jacket_temp,
            JACKET_VALVE: actuators[JACKET_VALVE],
            JACKET_FLOW: self._utility_flow(actuators[JACKET_VALVE]),
            FEED_VALVE: actuators[FEED_VALVE],
            REAGENT_FEED: feed,
            AGITATOR_SPEED: actuators[AGITATOR_SPEED],
            AGITATOR_POWER: agitator_power,
            PHASE_TIMER: state[PHASE_TIMER] + dt_seconds,
            REAGENT_MASS: mass,
            CONVERTED_MASS: converted,
            CHARGE_TARGET: state[CHARGE_TARGET],
            HOLD_SECONDS: state[HOLD_SECONDS],
            AGITATOR_TARGET: state[AGITATOR_TARGET],
            BATCH_COUNT: state[BATCH_COUNT],
        }
        return self._advance_phase(advanced)

    def _jacket_setpoint(self, phase: int, report: Mapping[str, float], dt_seconds: float) -> float:
        """Return the jacket temperature the recipe calls for in this phase.

        The cascade's master loop runs only while the batch is being heated and held. Filling and
        emptying are done to fixed jacket temperatures with the master in manual, which is how a
        recipe is actually written — you do not heat a vessel you are still charging — and it is
        why the reactor genuinely cools between batches instead of coasting hot forever.
        """
        if phase in (Phase.HEAT, Phase.REACT):
            return self._master.update(
                measurement=report[REACTOR_TEMP],
                setpoint=report[TEMP_SETPOINT],
                dt_seconds=dt_seconds,
                bias=45.0,
            )
        if phase == Phase.DISCHARGE:
            return _DISCHARGE_JACKET_C
        return _CHARGE_JACKET_C

    def _advance_phase(self, state: dict[str, float]) -> dict[str, float]:
        """Move the batch on to its next phase when this one's condition is met.

        The conditions are what a batch recipe actually specifies: fill to a level, heat to a
        temperature, hold for a time or until conversion, empty to a heel. Nothing here is on a
        wall clock, which is why two batches under one recipe still take slightly different
        lengths of time.
        """
        phase = round(state[BATCH_PHASE])
        timer = state[PHASE_TIMER]
        arrived = state[REACTOR_TEMP] >= state[TEMP_SETPOINT] - _HEAT_ARRIVAL_MARGIN_C
        done = state[CONVERSION] >= _CONVERSION_TARGET_PCT

        if phase == Phase.IDLE and timer >= _IDLE_SECONDS:
            return self._enter(state, Phase.CHARGE)
        if phase == Phase.CHARGE and state[REACTOR_LEVEL] >= state[CHARGE_TARGET]:
            return self._enter(state, Phase.HEAT)
        if phase == Phase.HEAT and arrived:
            return self._enter(state, Phase.REACT)
        if phase == Phase.REACT and (timer >= state[HOLD_SECONDS] or done):
            return self._enter(state, Phase.DISCHARGE)
        if phase == Phase.DISCHARGE and state[REACTOR_LEVEL] <= _EMPTY_LEVEL_PCT:
            finished = self._enter(state, Phase.IDLE)
            finished[BATCH_COUNT] = state[BATCH_COUNT] + 1.0
            return finished
        return state

    def _enter(self, state: dict[str, float], phase: int) -> dict[str, float]:
        """Return the state with a new phase entered and its timer restarted."""
        entered = dict(state)
        entered[BATCH_PHASE] = float(phase)
        entered[PHASE_TIMER] = 0.0
        return entered

    def _agitator_speed(self, phase: int) -> float:
        """Return the agitator speed the phase calls for, as a share of the operator's target."""
        share = {
            Phase.IDLE: 0.0,
            Phase.CHARGE: 0.5,
            Phase.HEAT: 1.0,
            Phase.REACT: 1.0,
            Phase.DISCHARGE: 0.65,
        }.get(phase, 0.0)
        return share * self._state[AGITATOR_TARGET]

    def _agitator_power(self, speed: float, conversion: float, level: float) -> float:
        """Return agitator power: cube law in speed, times viscosity, times liquid depth."""
        viscosity = 1.0 + _VISCOSITY_PER_CONVERSION * conversion / 100.0
        cube = (speed / _AGITATOR_RATED_RPM) ** 3
        return _AGITATOR_BASE_KW + _AGITATOR_RATED_KW * cube * viscosity * level / 100.0

    def _jacket_target(self, valve: float, reactor_temp: float) -> float:
        """Return the jacket temperature a valve position holds, pulled toward the reactor.

        The valve is split-range: shut against hot utility at 100%, shut against chilled water at
        0%, and passing neither in the middle of its travel.
        """
        supply = _JACKET_HOT_C - _JACKET_SPAN_C * valve
        return supply + _JACKET_PICKUP * (reactor_temp - supply)

    def _utility_flow(self, valve: float) -> float:
        """Return utility flow through the jacket: a V in valve position, zero at mid-travel."""
        return square_law_flow(abs(valve - 50.0) * 2.0, _MAX_JACKET_FLOW_M3PH)

    def _pressure(self, reactor_temp: float, level: float) -> float:
        """Return vessel pressure: vapour pressure in temperature, scaled by the liquid present."""
        vapour = _PRESSURE_COEFFICIENT * math.exp(_PRESSURE_EXPONENT * reactor_temp)
        return clamp(vapour * (0.35 + 0.0065 * level), 0.0, 12.0)

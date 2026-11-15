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
from pydantic import BaseModel, ConfigDict

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
from phos.synth.plant_spec import (
    Component,
    ComponentKind,
    Connection,
    ControllerKind,
    ControllerSpec,
    DisturbanceSpec,
    EventPlanSpec,
    PlantSpec,
    pi_controller,
)
from phos.synth.process import clamp, first_order, square_law_flow
from phos.synth.realism import RealismProfile
from phos.synth.templates import register_template

__all__ = [
    "AGITATOR_POWER",
    "AGITATOR_SPEED",
    "BATCH_COMPONENTS",
    "BATCH_CONNECTIONS",
    "BATCH_CONTROLLERS",
    "BATCH_DESCRIPTION",
    "BATCH_PHASE",
    "BATCH_SPEC",
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
    "BatchParameters",
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


class BatchParameters(BaseModel):
    """Every free number this reactor's physics reads, lifted out of the module's constants.

    The defaults are the values the hand-written plant carried, so `BATCH_SPEC` describes exactly
    the reactor that produced the corpora pinned in ``tests/synth/golden/``.

    Attributes:
        full_charge_kg: Mass in the vessel at a full charge.
        max_feed_kgph: Reagent feed rate with the feed valve wide open.
        discharge_kgph: Rate the vessel empties at during discharge.
        heat_capacity_kj_per_kg_k: Specific heat of the contents.
        wall_ua_kj_per_s_k: Heat transfer coefficient times area for the vessel wall. How fast
            heat crosses from the jacket to the contents.
        reaction_enthalpy_kj_per_kg: Heat released per kg converted. The reaction warms itself.
        arrhenius_prefactor: Rate constant's prefactor.
        arrhenius_temperature_k: Activation temperature. Together with the prefactor this is why
            the reaction runs away from you if the vessel gets too hot.
        jacket_tau_s: Time constant of the jacket's own temperature.
        jacket_hot_c: Jacket temperature with the valve fully on hot service.
        jacket_span_c: Fraction of the reactor temperature the jacket demand spans.
        jacket_pickup: Fraction of the reactor temperature the jacket demand starts from.
        max_jacket_flow_m3ph: Utility flow through the jacket at a fully open valve.
        idle_seconds: How long the vessel idles between batches.
        default_hold_s: How long the react phase holds, before any operator extends it.
        charge_jacket_c: Jacket temperature held while the vessel is being charged.
        discharge_jacket_c: Jacket temperature held while it is being emptied.
        heat_arrival_margin_c: How close to setpoint counts as heated, so the hold can start.
        conversion_target_pct: Conversion the recipe calls for before discharge.
        empty_level_pct: Level below which the vessel counts as empty.
        vessel_thermal_kg: Thermal mass of the steel itself, as an equivalent mass of contents.
            Why an empty vessel does not change temperature instantly.
        feed_temp_c: Temperature the reagent arrives at. Cold feed cools the batch.
        pressure_coefficient: Coefficient of the vapour-pressure relation.
        pressure_exponent: Its exponent.
        agitator_base_kw: Agitator power with the vessel empty — the drive's own losses.
        agitator_rated_kw: Agitator power at rated speed in a full vessel.
        agitator_rated_rpm: The speed that rating is quoted at.
        viscosity_per_conversion: How much harder the agitator works as conversion rises. The
            batch thickens as it reacts, and the drive feels it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    full_charge_kg: float = _FULL_CHARGE_KG
    max_feed_kgph: float = _MAX_FEED_KGPH
    discharge_kgph: float = _DISCHARGE_KGPH
    heat_capacity_kj_per_kg_k: float = _HEAT_CAPACITY_KJ_PER_KG_K
    wall_ua_kj_per_s_k: float = _WALL_UA_KJ_PER_S_K
    reaction_enthalpy_kj_per_kg: float = _REACTION_ENTHALPY_KJ_PER_KG
    arrhenius_prefactor: float = _ARRHENIUS_PREFACTOR
    arrhenius_temperature_k: float = _ARRHENIUS_TEMPERATURE_K
    jacket_tau_s: float = _JACKET_TAU_S
    jacket_hot_c: float = _JACKET_HOT_C
    jacket_span_c: float = _JACKET_SPAN_C
    jacket_pickup: float = _JACKET_PICKUP
    max_jacket_flow_m3ph: float = _MAX_JACKET_FLOW_M3PH
    idle_seconds: float = _IDLE_SECONDS
    default_hold_s: float = _DEFAULT_HOLD_S
    charge_jacket_c: float = _CHARGE_JACKET_C
    discharge_jacket_c: float = _DISCHARGE_JACKET_C
    heat_arrival_margin_c: float = _HEAT_ARRIVAL_MARGIN_C
    conversion_target_pct: float = _CONVERSION_TARGET_PCT
    empty_level_pct: float = _EMPTY_LEVEL_PCT
    vessel_thermal_kg: float = _VESSEL_THERMAL_KG
    feed_temp_c: float = _FEED_TEMP_C
    pressure_coefficient: float = _PRESSURE_COEFFICIENT
    pressure_exponent: float = _PRESSURE_EXPONENT
    agitator_base_kw: float = _AGITATOR_BASE_KW
    agitator_rated_kw: float = _AGITATOR_RATED_KW
    agitator_rated_rpm: float = _AGITATOR_RATED_RPM
    viscosity_per_conversion: float = _VISCOSITY_PER_CONVERSION


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


BATCH_COMPONENTS: Final = (
    Component(
        component_id="reactor",
        kind=ComponentKind.REACTOR,
        label="Jacketed stirred-tank reactor",
        physical_unit="reactor",
        signals=(BATCH_PHASE, REACTOR_TEMP, REACTOR_PRESSURE, REACTOR_LEVEL, CONVERSION),
        description=(
            "The vessel the whole process happens in. Unlike a water works or a power station it "
            "never settles: it fills, heats, reacts, empties, and starts again, so what counts as "
            "normal depends entirely on which step of the recipe it is on."
        ),
    ),
    Component(
        component_id="temperature_controller",
        kind=ComponentKind.CONTROLLER,
        label="Reactor temperature target",
        physical_unit="reactor",
        signals=(TEMP_SETPOINT,),
        description="The temperature the recipe calls for while the batch is reacting.",
    ),
    Component(
        component_id="discharge",
        kind=ComponentKind.SINK,
        label="Product discharge",
        physical_unit="reactor",
        description="Where the finished batch goes when the vessel empties.",
    ),
    Component(
        component_id="jacket_valve",
        kind=ComponentKind.VALVE,
        label="Jacket service valve",
        physical_unit="jacket",
        signals=(JACKET_VALVE,),
        description=(
            "Blends hot and cold utility into the jacket. Opening it further makes the jacket "
            "hotter, which is backwards from most valves and is why its loop is reverse acting."
        ),
    ),
    Component(
        component_id="jacket",
        kind=ComponentKind.EXCHANGER,
        label="Reactor jacket",
        physical_unit="jacket",
        signals=(JACKET_TEMP, JACKET_FLOW),
        description=(
            "A space around the outside of the vessel with hot or cold fluid in it. The only way "
            "heat gets into or out of the batch."
        ),
    ),
    Component(
        component_id="feed_valve",
        kind=ComponentKind.VALVE,
        label="Reagent feed valve",
        physical_unit="feed",
        signals=(FEED_VALVE,),
        description="Open during charging and shut the rest of the time. Nothing in between.",
    ),
    Component(
        component_id="feed_line",
        kind=ComponentKind.PIPE,
        label="Reagent feed line",
        physical_unit="feed",
        signals=(REAGENT_FEED,),
        description="The line into the vessel, with the flow meter that says how fast it fills.",
    ),
    Component(
        component_id="agitator",
        kind=ComponentKind.MIXER,
        label="Agitator drive",
        physical_unit="agitation",
        signals=(AGITATOR_SPEED, AGITATOR_POWER),
        description=(
            "Stirs the batch. How much power it draws says something no other instrument does: "
            "the mixture thickens as it converts, and the drive feels that."
        ),
    ),
)
"""What the reactor is made of, every signal owned exactly once."""

BATCH_CONNECTIONS: Final = (
    Connection(
        source="feed_valve", target="feed_line", medium="material", label="valve to the feed line"
    ),
    Connection(
        source="feed_line", target="reactor", medium="material", label="reagent into the vessel"
    ),
    Connection(
        source="jacket_valve", target="jacket", medium="utility", label="service into the jacket"
    ),
    Connection(
        source="jacket", target="reactor", medium="heat", label="heat across the vessel wall"
    ),
    Connection(
        source="agitator", target="reactor", medium="shaft", label="stirring, and the heat it adds"
    ),
    Connection(source="reactor", target="discharge", medium="material", label="finished batch out"),
    Connection(
        source="temperature_controller",
        target="jacket_valve",
        medium="signal",
        label="temperature target drives the jacket through the cascade",
    ),
)
"""Which way the material and the heat go, and what the recipe drives."""

BATCH_CONTROLLERS: Final = (
    ControllerSpec(
        controller_id="reactor_temperature",
        kind=ControllerKind.PI,
        measurement=REACTOR_TEMP,
        setpoint=TEMP_SETPOINT,
        output="jacket_temperature",
        gain=2.2,
        integral_time_seconds=900.0,
        low=5.0,
        high=90.0,
        description=(
            "The outer half of a cascade. It does not touch a valve: it decides what temperature "
            "the jacket should be at, and the inner loop is what gets the jacket there. Slow, "
            "because a vessel full of liquid is slow."
        ),
    ),
    ControllerSpec(
        controller_id="jacket_temperature",
        kind=ControllerKind.PI,
        measurement=JACKET_TEMP,
        output=JACKET_VALVE,
        gain=3.5,
        integral_time_seconds=180.0,
        low=0.0,
        high=100.0,
        reverse_acting=True,
        bias=50.0,
        description=(
            "The inner half. Holds the jacket at whatever the outer loop asked for, which during "
            "charging and discharging is a fixed temperature the recipe names instead."
        ),
    ),
)
"""The temperature cascade. The feed valve and the agitator are not regulated at all — the recipe
opens and shuts them by phase — so they are not loops and are not described as ones."""

BATCH_SPEC: Final = PlantSpec(
    plant_id=BATCH_DESCRIPTION.plant_id,
    label=BATCH_DESCRIPTION.label,
    industry=BATCH_DESCRIPTION.industry,
    summary=BATCH_DESCRIPTION.summary,
    model_source=BATCH_DESCRIPTION.model_source,
    process="batch-reactor-v1",
    parameters=BatchParameters().model_dump(),
    units=BATCH_UNITS,
    signals=BATCH_SIGNALS,
    components=BATCH_COMPONENTS,
    connections=BATCH_CONNECTIONS,
    controllers=BATCH_CONTROLLERS,
    couplings=BATCH_COUPLINGS,
    control_network=BATCH_DESCRIPTION.control_network,
    write_authority=BATCH_DESCRIPTION.write_authority,
    disturbance=DisturbanceSpec(
        event_plans=tuple(EventPlanSpec.from_plan(plan) for plan in _EVENT_PLANS),
        first_start_floor=20,
        first_start_divisor=10,
        gap_steps=(60, 400),
    ),
)
"""The reactor, declaratively. `BatchReactorPlant` builds this one unless handed another, and
`describe()` returns `BATCH_DESCRIPTION` field for field.

This plant declares no control network, so `scan_period_seconds` is ``None``: it is the plant
where Atlas is deaf to commands by construction, which is deliberate and is recorded in
`BATCH_DESCRIPTION` rather than explained away."""


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
        plant_spec: PlantSpec | None = None,
    ) -> None:
        """Build the reactor and its cascade loops for one run.

        Args:
            spec: The run to prepare for.
            commands: Who writes over the control network, or ``None`` for the legacy
                echo path. See `phos.synth.plant.Plant`.
            realism: Ordinary trouble to apply, or ``None`` for a quiet profile. See
                `phos.synth.plant.Plant`.
            plant_spec: The reactor to build, or ``None`` for `BATCH_SPEC` — the one this module
                has always described. See `phos.synth.plants.water.WaterTreatmentPlant`.
        """
        self._plant_spec = plant_spec if plant_spec is not None else BATCH_SPEC
        self._description = self._plant_spec.describe()
        self._p = BatchParameters.model_validate(dict(self._plant_spec.parameters))
        self._master = pi_controller(self._plant_spec, "reactor_temperature")
        self._slave = pi_controller(self._plant_spec, "jacket_temperature")
        self._slave_bias = self._plant_spec.controller("jacket_temperature").bias
        super().__init__(spec, commands=commands, realism=realism)

    @property
    def description(self) -> PlantDescription:
        """The reactor: thirteen signals across four physical units, and no control network."""
        return self._description

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
            HOLD_SECONDS: self._p.default_hold_s,
            AGITATOR_TARGET: 120.0,
            BATCH_COUNT: 0.0,
        }

    def schedule_events(self, rng: Generator, spec: RunSpec) -> Sequence[BenignEvent]:
        """Lay the four kinds of operational event through the run, round-robin."""
        disturbance = self._plant_spec.disturbance
        return lay_out_events(
            rng,
            spec,
            disturbance.plans(),
            first_start_step=disturbance.first_start_step(spec.n_steps),
            gap_steps=disturbance.gap_steps,
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
                bias=self._slave_bias,
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
        feed = square_law_flow(actuators[FEED_VALVE], self._p.max_feed_kgph)
        draw = self._p.discharge_kgph if phase == Phase.DISCHARGE else 0.0

        charged = feed * dt_seconds / 3600.0
        removed = min(draw * dt_seconds / 3600.0, state[REAGENT_MASS])
        held = state[REAGENT_MASS] - removed
        converted_share = (
            state[CONVERTED_MASS] / state[REAGENT_MASS] if state[REAGENT_MASS] else 0.0
        )
        converted = clamp(state[CONVERTED_MASS] - removed * converted_share, 0.0, held)
        mass = clamp(held + charged, 0.0, self._p.full_charge_kg)

        rate_per_second = self._p.arrhenius_prefactor * math.exp(
            -self._p.arrhenius_temperature_k / (state[REACTOR_TEMP] + 273.15)
        )
        reacted = min(rate_per_second * (mass - converted) * dt_seconds, mass - converted)
        converted = converted + reacted
        level = 100.0 * mass / self._p.full_charge_kg
        conversion = 100.0 * converted / mass if mass > 0.0 else 0.0

        agitator_power = self._agitator_power(actuators[AGITATOR_SPEED], conversion, level)
        jacket_temp = first_order(
            state[JACKET_TEMP],
            target=self._jacket_target(actuators[JACKET_VALVE], state[REACTOR_TEMP]),
            dt_seconds=dt_seconds,
            tau_seconds=self._p.jacket_tau_s,
        )
        # Cold reagent mixes with whatever is already in the vessel before any heat moves. This is
        # what makes a charge cool the reactor down and gives the heat phase something to do.
        holdup = held + self._p.vessel_thermal_kg
        mixed = (holdup * state[REACTOR_TEMP] + charged * self._p.feed_temp_c) / (holdup + charged)
        thermal_mass = (mass + self._p.vessel_thermal_kg) * self._p.heat_capacity_kj_per_kg_k
        # The wall term is an exponential approach rather than an Euler step: at low holdup the
        # explicit form has a gain above two per sample and diverges, which is a numerical
        # artefact and not a reactor.
        after_wall = first_order(
            mixed,
            target=jacket_temp,
            dt_seconds=dt_seconds,
            tau_seconds=thermal_mass / self._p.wall_ua_kj_per_s_k,
        )
        source_kj = reacted * self._p.reaction_enthalpy_kj_per_kg + agitator_power * dt_seconds
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
            return self._p.discharge_jacket_c
        return self._p.charge_jacket_c

    def _advance_phase(self, state: dict[str, float]) -> dict[str, float]:
        """Move the batch on to its next phase when this one's condition is met.

        The conditions are what a batch recipe actually specifies: fill to a level, heat to a
        temperature, hold for a time or until conversion, empty to a heel. Nothing here is on a
        wall clock, which is why two batches under one recipe still take slightly different
        lengths of time.
        """
        phase = round(state[BATCH_PHASE])
        timer = state[PHASE_TIMER]
        arrived = state[REACTOR_TEMP] >= state[TEMP_SETPOINT] - self._p.heat_arrival_margin_c
        done = state[CONVERSION] >= self._p.conversion_target_pct

        if phase == Phase.IDLE and timer >= self._p.idle_seconds:
            return self._enter(state, Phase.CHARGE)
        if phase == Phase.CHARGE and state[REACTOR_LEVEL] >= state[CHARGE_TARGET]:
            return self._enter(state, Phase.HEAT)
        if phase == Phase.HEAT and arrived:
            return self._enter(state, Phase.REACT)
        if phase == Phase.REACT and (timer >= state[HOLD_SECONDS] or done):
            return self._enter(state, Phase.DISCHARGE)
        if phase == Phase.DISCHARGE and state[REACTOR_LEVEL] <= self._p.empty_level_pct:
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
        viscosity = 1.0 + self._p.viscosity_per_conversion * conversion / 100.0
        cube = (speed / self._p.agitator_rated_rpm) ** 3
        return (
            self._p.agitator_base_kw + self._p.agitator_rated_kw * cube * viscosity * level / 100.0
        )

    def _jacket_target(self, valve: float, reactor_temp: float) -> float:
        """Return the jacket temperature a valve position holds, pulled toward the reactor.

        The valve is split-range: shut against hot utility at 100%, shut against chilled water at
        0%, and passing neither in the middle of its travel.
        """
        supply = self._p.jacket_hot_c - self._p.jacket_span_c * valve
        return supply + self._p.jacket_pickup * (reactor_temp - supply)

    def _utility_flow(self, valve: float) -> float:
        """Return utility flow through the jacket: a V in valve position, zero at mid-travel."""
        return square_law_flow(abs(valve - 50.0) * 2.0, self._p.max_jacket_flow_m3ph)

    def _pressure(self, reactor_temp: float, level: float) -> float:
        """Return vessel pressure: vapour pressure in temperature, scaled by the liquid present."""
        vapour = self._p.pressure_coefficient * math.exp(self._p.pressure_exponent * reactor_temp)
        return clamp(vapour * (0.35 + 0.0065 * level), 0.0, 12.0)


register_template("batch-reactor-v1", BatchReactorPlant)

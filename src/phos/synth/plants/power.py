"""An islanded gas-turbine generating set feeding a distribution transformer, simulated.

The process: one gas turbine drives a synchronous generator that supplies a local network. A
governor holds frequency by moving the fuel valve; an automatic voltage regulator holds generator
terminal voltage by moving excitation; an on-load tap changer holds the feeder-side voltage as
loading shifts through the day. The load itself is a town and an industrial customer, and neither
asks permission.

**Why this process, given there is already a water works.** Its dynamics are an order of magnitude
faster, and — more usefully — its central coupling is an *identity* rather than a lag. Three-phase
power is ``P = sqrt(3) . V . I . cos(phi)``, and that equation holds at every instant, exactly, on
real plant. A joint model that learns it has learned something a range check never could, and an
attacker who moves any one of the four numbers without moving the others has broken arithmetic
rather than merely stepped outside a band. Nothing in a water works is that tight.

**The couplings, which are the point.**

- ``feeder_current_a`` is fixed by ``generator_output_mw``, ``bus_voltage_kv`` and
  ``power_factor`` through the three-phase power identity. Not approximately — exactly.
- ``turbine_speed_rpm`` integrates the imbalance between the mechanical power the fuel valve
  admits and the electrical power the load draws. It is the only integrator in the machine and it
  is why a load step is visible before the governor answers it.
- ``bus_frequency_hz`` is ``turbine_speed_rpm`` divided by sixty, because a two-pole synchronous
  machine's shaft speed *is* the system frequency. Two signals, one physical quantity.
- ``bus_voltage_kv`` follows ``excitation_pct`` less a drop that grows with ``feeder_current_a``.
- ``feeder_voltage_kv`` is ``bus_voltage_kv`` through the ratio ``tap_position`` selects, less a
  line drop in current.
- ``transformer_oil_temp_c`` lags ``ambient_temp_c`` plus a rise going with the square of
  ``feeder_current_a`` — a thermal integral with a time constant of an hour, so it carries the
  memory of the last hour's loading rather than this instant's.

**The rhythms are two, and they are different shapes.** A smooth daily demand curve, and a
*stepped* three-shift industrial load that changes discontinuously at 08:00 and 16:00. A model
that has learned the sinusoid has not learned the step.

**What this is not.** A model of a generating set written from public descriptions of governor,
AVR and tap-changer behaviour and from textbook three-phase relations. Not a model of any
particular machine, and not validated against one. See `MODEL_NOT_REALITY_CAVEAT`.
"""

import math
from collections.abc import Mapping, Sequence
from typing import Final

from numpy.random import Generator
from pydantic import BaseModel, ConfigDict

from phos.synth.command import CommandSource, WriteAuthority
from phos.synth.plant import (
    BenignEvent,
    ControlNetwork,
    Coupling,
    CouplingKind,
    EventPlan,
    NetworkNode,
    PhysicalUnit,
    Plant,
    PlantDescription,
    RegisterBlock,
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
    fixed_setpoint,
    pi_controller,
)
from phos.synth.process import (
    accumulate,
    clamp,
    cycle_factor,
    first_order,
    shift_index,
)
from phos.synth.realism import RealismProfile
from phos.synth.templates import register_template

__all__ = [
    "AMBIENT_TEMP",
    "BUS_FREQUENCY",
    "BUS_VOLTAGE",
    "DISPATCH_SETPOINT",
    "EXCITATION",
    "EXHAUST_TEMP",
    "FEEDER_CURRENT",
    "FEEDER_VOLTAGE",
    "FUEL_VALVE",
    "GENERATOR_OUTPUT",
    "GRID_DEMAND",
    "POWER_COMPONENTS",
    "POWER_CONNECTIONS",
    "POWER_CONTROLLERS",
    "POWER_DESCRIPTION",
    "POWER_FACTOR",
    "POWER_SPEC",
    "TAP_POSITION",
    "TRANSFORMER_OIL_TEMP",
    "TURBINE_SPEED",
    "VOLTAGE_SETPOINT",
    "PowerGenerationPlant",
    "PowerParameters",
]

GRID_DEMAND: Final = "grid_demand_mw"
FUEL_VALVE: Final = "fuel_valve_pct"
TURBINE_SPEED: Final = "turbine_speed_rpm"
EXHAUST_TEMP: Final = "exhaust_temp_c"
GENERATOR_OUTPUT: Final = "generator_output_mw"
BUS_FREQUENCY: Final = "bus_frequency_hz"
EXCITATION: Final = "excitation_pct"
BUS_VOLTAGE: Final = "bus_voltage_kv"
FEEDER_VOLTAGE: Final = "feeder_voltage_kv"
FEEDER_CURRENT: Final = "feeder_current_a"
POWER_FACTOR: Final = "power_factor"
TRANSFORMER_OIL_TEMP: Final = "transformer_oil_temp_c"
AMBIENT_TEMP: Final = "ambient_temp_c"
TAP_POSITION: Final = "tap_position"
DISPATCH_SETPOINT: Final = "dispatch_setpoint_mw"
VOLTAGE_SETPOINT: Final = "feeder_voltage_setpoint_kv"

DISPATCH_CHANGE: Final = "dispatch_change"
LOAD_STEP: Final = "customer_load_step"
VOLTAGE_SETPOINT_CHANGE: Final = "voltage_setpoint_change"
FEEDER_SWITCHING: Final = "feeder_switching"

_RATED_MW: Final = 55.0
_NOMINAL_HZ: Final = 50.0
_RPM_PER_HZ: Final = 60.0
"""Two-pole machine: shaft speed in rpm is sixty times the electrical frequency in Hz."""

_INERTIA_RPM_PER_MW_S: Final = 1.1
_RATED_CURRENT_A: Final = 2000.0
_TOP_OIL_RISE_K: Final = 55.0
_OIL_TAU_S: Final = 3600.0
_EXHAUST_TAU_S: Final = 45.0
_VOLTAGE_TAU_S: Final = 8.0
_TAP_STEPS: Final = 16
_TAP_RATIO_PER_STEP: Final = 0.00625
_TAP_BASE_RATIO: Final = 0.98
_TAP_DEADBAND_KV: Final = 0.12
_TAP_DELAY_S: Final = 90.0
_LINE_DROP_KV_PER_A: Final = 3.0e-4
_BUS_DROP_KV_PER_A: Final = 6.0e-4
_ROOT_THREE: Final = math.sqrt(3.0)


class PowerParameters(BaseModel):
    """Every free number this machine's physics reads, lifted out of the module's constants.

    The defaults are the values the hand-written plant carried, so `POWER_SPEC` describes exactly
    the set that produced the corpora pinned in ``tests/synth/golden/``.

    Attributes:
        rated_mw: Output the machine is rated at. Also what the governor's feedforward is
            expressed as a fraction of.
        nominal_hz: The frequency the island runs at. `POWER_CONTROLLERS` states the governor's
            target separately, and PART R2's validity gate owes a check that the two agree.
        rpm_per_hz: Shaft speed per hertz, which is the machine's pole count in disguise.
        inertia_rpm_per_mw_s: How far the shaft slows per MW of unmatched load per second. The
            whole reason frequency moves at all.
        rated_current_a: Feeder current at rated output and nominal voltage.
        top_oil_rise_k: Transformer oil temperature rise above ambient at rated load.
        oil_tau_s: Time constant of that rise. Long: a transformer is a large warm thing.
        exhaust_tau_s: Time constant of exhaust temperature's response to fuel.
        voltage_tau_s: Time constant of bus voltage's response to excitation.
        tap_steps: Number of positions on the tap changer.
        tap_ratio_per_step: Turns-ratio change one tap step makes.
        tap_base_ratio: Turns ratio at tap position zero.
        tap_deadband_kv: Feeder voltage error the tap changer tolerates before it moves.
        tap_delay_s: Seconds the tap changer waits before moving, so it does not chase noise.
        line_drop_kv_per_a: Feeder voltage lost per amp, along the line.
        bus_drop_kv_per_a: Bus voltage lost per amp, through the machine's own impedance.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    rated_mw: float = _RATED_MW
    nominal_hz: float = _NOMINAL_HZ
    rpm_per_hz: float = _RPM_PER_HZ
    inertia_rpm_per_mw_s: float = _INERTIA_RPM_PER_MW_S
    rated_current_a: float = _RATED_CURRENT_A
    top_oil_rise_k: float = _TOP_OIL_RISE_K
    oil_tau_s: float = _OIL_TAU_S
    exhaust_tau_s: float = _EXHAUST_TAU_S
    voltage_tau_s: float = _VOLTAGE_TAU_S
    tap_steps: float = _TAP_STEPS
    tap_ratio_per_step: float = _TAP_RATIO_PER_STEP
    tap_base_ratio: float = _TAP_BASE_RATIO
    tap_deadband_kv: float = _TAP_DEADBAND_KV
    tap_delay_s: float = _TAP_DELAY_S
    line_drop_kv_per_a: float = _LINE_DROP_KV_PER_A
    bus_drop_kv_per_a: float = _BUS_DROP_KV_PER_A


POWER_UNITS: Final = (
    PhysicalUnit(unit_id="turbine", label="Gas turbine and fuel system"),
    PhysicalUnit(unit_id="generator", label="Synchronous generator and excitation"),
    PhysicalUnit(unit_id="transformer", label="Step-up transformer and tap changer"),
    PhysicalUnit(unit_id="feeder", label="Outgoing feeder and metering"),
)

POWER_SIGNALS: Final = (
    SignalSpec(
        key=FUEL_VALVE,
        label="Fuel control valve",
        unit="%",
        kind=SignalKind.ACTUATOR,
        physical_unit="turbine",
        low=0.0,
        high=100.0,
        noise_stddev=0.08,
    ),
    SignalSpec(
        key=TURBINE_SPEED,
        label="Turbine shaft speed",
        unit="rpm",
        kind=SignalKind.SENSOR,
        physical_unit="turbine",
        low=0.0,
        high=3600.0,
        noise_stddev=0.9,
        drift_amplitude=1.2,
    ),
    SignalSpec(
        key=EXHAUST_TEMP,
        label="Turbine exhaust temperature",
        unit="degC",
        kind=SignalKind.SENSOR,
        physical_unit="turbine",
        low=0.0,
        high=750.0,
        noise_stddev=1.4,
        drift_amplitude=2.0,
    ),
    SignalSpec(
        key=GENERATOR_OUTPUT,
        label="Generator active power",
        unit="MW",
        kind=SignalKind.SENSOR,
        physical_unit="generator",
        low=0.0,
        high=60.0,
        noise_stddev=0.04,
        drift_amplitude=0.03,
    ),
    SignalSpec(
        key=BUS_FREQUENCY,
        label="Bus frequency",
        unit="Hz",
        kind=SignalKind.SENSOR,
        physical_unit="generator",
        low=45.0,
        high=55.0,
        noise_stddev=0.003,
        drift_amplitude=0.004,
    ),
    SignalSpec(
        key=EXCITATION,
        label="Excitation",
        unit="%",
        kind=SignalKind.ACTUATOR,
        physical_unit="generator",
        low=0.0,
        high=100.0,
        noise_stddev=0.06,
    ),
    SignalSpec(
        key=BUS_VOLTAGE,
        label="Generator bus voltage",
        unit="kV",
        kind=SignalKind.SENSOR,
        physical_unit="generator",
        low=0.0,
        high=15.0,
        noise_stddev=0.006,
        drift_amplitude=0.010,
    ),
    SignalSpec(
        key=TAP_POSITION,
        label="Tap changer position",
        unit="step",
        kind=SignalKind.ACTUATOR,
        physical_unit="transformer",
        low=0.0,
        high=16.0,
        noise_stddev=0.0,
    ),
    SignalSpec(
        key=TRANSFORMER_OIL_TEMP,
        label="Transformer top-oil temperature",
        unit="degC",
        kind=SignalKind.SENSOR,
        physical_unit="transformer",
        low=-30.0,
        high=140.0,
        noise_stddev=0.25,
        drift_amplitude=0.4,
    ),
    SignalSpec(
        key=AMBIENT_TEMP,
        label="Ambient temperature",
        unit="degC",
        kind=SignalKind.SENSOR,
        physical_unit="transformer",
        low=-30.0,
        high=55.0,
        noise_stddev=0.12,
        drift_amplitude=0.2,
    ),
    SignalSpec(
        key=FEEDER_VOLTAGE,
        label="Feeder voltage",
        unit="kV",
        kind=SignalKind.SENSOR,
        physical_unit="feeder",
        low=0.0,
        high=15.0,
        noise_stddev=0.006,
        drift_amplitude=0.010,
    ),
    SignalSpec(
        key=FEEDER_CURRENT,
        label="Feeder current",
        unit="A",
        kind=SignalKind.SENSOR,
        physical_unit="feeder",
        low=0.0,
        high=3200.0,
        noise_stddev=1.8,
        drift_amplitude=2.5,
    ),
    SignalSpec(
        key=POWER_FACTOR,
        label="Feeder power factor",
        unit="cos(phi)",
        kind=SignalKind.SENSOR,
        physical_unit="feeder",
        low=0.50,
        high=1.00,
        noise_stddev=0.0015,
        drift_amplitude=0.002,
    ),
    SignalSpec(
        key=GRID_DEMAND,
        label="Network demand",
        unit="MW",
        kind=SignalKind.SENSOR,
        physical_unit="feeder",
        low=0.0,
        high=60.0,
        noise_stddev=0.05,
        drift_amplitude=0.04,
    ),
    SignalSpec(
        key=DISPATCH_SETPOINT,
        label="Dispatch setpoint",
        unit="MW",
        kind=SignalKind.SETPOINT,
        physical_unit="generator",
        low=0.0,
        high=60.0,
        noise_stddev=0.0,
    ),
    SignalSpec(
        key=VOLTAGE_SETPOINT,
        label="Feeder voltage setpoint",
        unit="kV",
        kind=SignalKind.SETPOINT,
        physical_unit="transformer",
        low=0.0,
        high=15.0,
        noise_stddev=0.0,
    ),
)

POWER_COUPLINGS: Final = (
    Coupling(
        driven=FEEDER_CURRENT,
        drivers=(GENERATOR_OUTPUT, BUS_VOLTAGE, POWER_FACTOR),
        kind=CouplingKind.ALGEBRAIC,
        relation=(
            "the three-phase power identity, exactly: I = P / (sqrt(3) . V . cos(phi)). Four "
            "signals, one equation, every instant"
        ),
    ),
    Coupling(
        driven=TURBINE_SPEED,
        drivers=(FUEL_VALVE, GENERATOR_OUTPUT),
        kind=CouplingKind.INTEGRATION,
        relation=(
            "shaft speed integrates the imbalance between the mechanical power the fuel valve "
            "admits and the electrical power the load draws"
        ),
    ),
    Coupling(
        driven=BUS_FREQUENCY,
        drivers=(TURBINE_SPEED,),
        kind=CouplingKind.ALGEBRAIC,
        relation="frequency is shaft speed over sixty; a two-pole machine's speed IS the frequency",
    ),
    Coupling(
        driven=GENERATOR_OUTPUT,
        drivers=(GRID_DEMAND, FEEDER_CURRENT),
        kind=CouplingKind.ALGEBRAIC,
        relation="output serves the demand plus losses that rise with the square of feeder current",
    ),
    Coupling(
        driven=BUS_VOLTAGE,
        drivers=(EXCITATION, FEEDER_CURRENT),
        kind=CouplingKind.LAG,
        relation="terminal voltage follows excitation less a drop proportional to load current",
    ),
    Coupling(
        driven=FEEDER_VOLTAGE,
        drivers=(BUS_VOLTAGE, TAP_POSITION, FEEDER_CURRENT),
        kind=CouplingKind.ALGEBRAIC,
        relation=(
            "feeder voltage is bus voltage through the ratio the tap position selects, less a "
            "line drop in current"
        ),
    ),
    Coupling(
        driven=TRANSFORMER_OIL_TEMP,
        drivers=(FEEDER_CURRENT, AMBIENT_TEMP),
        kind=CouplingKind.LAG,
        relation=(
            "top-oil temperature lags ambient plus a rise going with the square of load current, "
            "with an hour-long thermal time constant"
        ),
    ),
    Coupling(
        driven=EXHAUST_TEMP,
        drivers=(FUEL_VALVE, AMBIENT_TEMP),
        kind=CouplingKind.LAG,
        relation="exhaust temperature lags firing rate, offset by inlet air temperature",
    ),
    Coupling(
        driven=FUEL_VALVE,
        drivers=(BUS_FREQUENCY, DISPATCH_SETPOINT),
        kind=CouplingKind.CONTROL,
        relation="the governor holds frequency at 50 Hz, biased by the dispatch setpoint",
    ),
    Coupling(
        driven=EXCITATION,
        drivers=(BUS_VOLTAGE,),
        kind=CouplingKind.CONTROL,
        relation="the automatic voltage regulator holds generator bus voltage at 11 kV",
    ),
    Coupling(
        driven=TAP_POSITION,
        drivers=(FEEDER_VOLTAGE, VOLTAGE_SETPOINT),
        kind=CouplingKind.CONTROL,
        relation=(
            "the on-load tap changer steps once every ninety seconds while feeder voltage sits "
            "outside a 0.12 kV deadband around its setpoint"
        ),
    ),
)

POWER_NETWORK: Final = ControlNetwork(
    nodes=(
        NetworkNode(node_id="scada", label="Station SCADA", ip="10.40.0.10", role="scada"),
        NetworkNode(node_id="genset", label="Genset controller", ip="10.40.0.31", role="plc"),
        NetworkNode(node_id="meter", label="Feeder metering IED", ip="10.40.0.32", role="plc"),
        NetworkNode(node_id="hmi", label="Station HMI", ip="10.40.0.45", role="hmi"),
    ),
    blocks=(
        RegisterBlock(
            node_id="genset",
            start_address=40,
            signals=(
                FUEL_VALVE,
                TURBINE_SPEED,
                EXHAUST_TEMP,
                GENERATOR_OUTPUT,
                BUS_FREQUENCY,
                EXCITATION,
                BUS_VOLTAGE,
            ),
        ),
        RegisterBlock(
            node_id="meter",
            start_address=60,
            signals=(
                FEEDER_VOLTAGE,
                FEEDER_CURRENT,
                POWER_FACTOR,
                GRID_DEMAND,
                TAP_POSITION,
                TRANSFORMER_OIL_TEMP,
                AMBIENT_TEMP,
            ),
        ),
        RegisterBlock(
            node_id="genset",
            start_address=80,
            signals=(DISPATCH_SETPOINT, VOLTAGE_SETPOINT),
            writable=True,
        ),
    ),
    poller="scada",
    operator="hmi",
    poll_interval_seconds=10.0,
    unit_id=3,
)

POWER_AUTHORITY: Final = WriteAuthority(
    grants={"hmi": frozenset({DISPATCH_SETPOINT, VOLTAGE_SETPOINT})}
)
"""Who this station permits to write a setpoint: the station HMI, and nothing else.

Declared for the reason `phos.synth.plants.water.WATER_AUTHORITY` is declared, and granting the
same single station keeps the two networked plants comparable: an unauthorised write from
``scada`` is a known station on both, so a harness result cannot come from one plant having a
looser policy than the other.
"""

POWER_DESCRIPTION: Final = PlantDescription(
    plant_id="power-generation",
    label="Islanded gas turbine generating set",
    industry="power generation and distribution",
    summary=(
        "A gas turbine driving a synchronous generator into a step-up transformer and one outgoing "
        "feeder, with a governor on frequency, an AVR on bus voltage and an on-load tap changer on "
        "feeder voltage, serving a town's daily demand and a three-shift industrial customer."
    ),
    model_source=(
        "Written from textbook three-phase relations (P = sqrt(3).V.I.cos phi), swing-equation "
        "behaviour for a two-pole machine, IEC-style top-oil thermal response to load current, and "
        "public descriptions of governor, AVR and on-load tap-changer control. Not modelled on, or "
        "validated against, any particular machine."
    ),
    units=POWER_UNITS,
    signals=POWER_SIGNALS,
    couplings=POWER_COUPLINGS,
    control_network=POWER_NETWORK,
    write_authority=POWER_AUTHORITY,
)

_EVENT_PLANS: Final = (
    EventPlan(
        kind=LOAD_STEP,
        label="Industrial customer picks up or sheds load",
        duration_steps=180,
        parameter_ranges={"load_step_mw": (-6.0, 8.0)},
        detail="customer load stepped:",
    ),
    EventPlan(
        kind=DISPATCH_CHANGE,
        label="Operator changes the dispatch setpoint",
        duration_steps=0,
        writes=(DISPATCH_SETPOINT,),
        parameter_ranges={DISPATCH_SETPOINT: (24.0, 38.0)},
        detail="new dispatch setpoint:",
    ),
    EventPlan(
        kind=FEEDER_SWITCHING,
        label="Feeder switching changes the load mix",
        duration_steps=240,
        parameter_ranges={"power_factor_shift": (-0.06, 0.04)},
        detail="power factor shifted by switching:",
    ),
    EventPlan(
        kind=VOLTAGE_SETPOINT_CHANGE,
        label="Operator changes the feeder voltage setpoint",
        duration_steps=0,
        writes=(VOLTAGE_SETPOINT,),
        parameter_ranges={VOLTAGE_SETPOINT: (10.55, 11.15)},
        detail="new feeder voltage setpoint:",
    ),
)


POWER_COMPONENTS: Final = (
    Component(
        component_id="fuel_valve",
        kind=ComponentKind.VALVE,
        label="Fuel control valve",
        physical_unit="turbine",
        signals=(FUEL_VALVE,),
        description=(
            "How much gas the turbine is given. Opening it further is the only way the set can "
            "make more power."
        ),
    ),
    Component(
        component_id="gas_turbine",
        kind=ComponentKind.TURBINE,
        label="Gas turbine",
        physical_unit="turbine",
        signals=(TURBINE_SPEED, EXHAUST_TEMP),
        description=(
            "Burns the gas and turns the shaft. How hot the exhaust runs follows how hard it is "
            "working, with a lag."
        ),
    ),
    Component(
        component_id="generator",
        kind=ComponentKind.GENERATOR,
        label="Synchronous generator",
        physical_unit="generator",
        signals=(GENERATOR_OUTPUT, BUS_FREQUENCY),
        description=(
            "Turns shaft power into electrical power. Because this island has no grid behind it, "
            "frequency is the shaft's own speed: take more power than the turbine makes and the "
            "whole island slows down."
        ),
    ),
    Component(
        component_id="exciter",
        kind=ComponentKind.OTHER,
        label="Excitation system",
        physical_unit="generator",
        signals=(EXCITATION,),
        description=(
            "Feeds current to the generator's field winding. More excitation, higher voltage — "
            "this is the only handle the machine has on voltage."
        ),
    ),
    Component(
        component_id="generator_bus",
        kind=ComponentKind.BUS,
        label="Generator bus",
        physical_unit="generator",
        signals=(BUS_VOLTAGE,),
        description="The machine's own terminals, before the step-up transformer.",
    ),
    Component(
        component_id="dispatch_controller",
        kind=ComponentKind.CONTROLLER,
        label="Dispatch instruction",
        physical_unit="generator",
        signals=(DISPATCH_SETPOINT,),
        description=(
            "How much power the operator has told the set to make. The governor's feedforward is "
            "paced from it."
        ),
    ),
    Component(
        component_id="step_up_transformer",
        kind=ComponentKind.TRANSFORMER,
        label="Step-up transformer with on-load tap changer",
        physical_unit="transformer",
        signals=(TAP_POSITION, TRANSFORMER_OIL_TEMP),
        description=(
            "Raises the machine's voltage to the feeder's. Its tap changer does not glide: it "
            "waits out a timer and then moves one whole step, which is why its position staircases."
        ),
    ),
    Component(
        component_id="ambient",
        kind=ComponentKind.SOURCE,
        label="Ambient conditions",
        physical_unit="transformer",
        signals=(AMBIENT_TEMP,),
        description=(
            "The weather. Nobody controls it, and the transformer's oil temperature is measured "
            "from it rather than from zero."
        ),
    ),
    Component(
        component_id="voltage_controller",
        kind=ComponentKind.CONTROLLER,
        label="Feeder voltage target",
        physical_unit="transformer",
        signals=(VOLTAGE_SETPOINT,),
        description="The feeder voltage the tap changer is holding to.",
    ),
    Component(
        component_id="outgoing_feeder",
        kind=ComponentKind.FEEDER,
        label="Outgoing feeder and metering",
        physical_unit="feeder",
        signals=(FEEDER_VOLTAGE, FEEDER_CURRENT, POWER_FACTOR),
        description=(
            "The circuit leaving the site, with its metering. Power factor moves when the mix of "
            "customers on it changes, which is switching rather than anything the set did."
        ),
    ),
    Component(
        component_id="island_load",
        kind=ComponentKind.LOAD,
        label="Island demand",
        physical_unit="feeder",
        signals=(GRID_DEMAND,),
        description=(
            "What the island is actually drawing. The set has to follow it; nothing here gets to "
            "decide it."
        ),
    ),
)
"""What the generating set is made of, every signal owned exactly once."""

POWER_CONNECTIONS: Final = (
    Connection(source="fuel_valve", target="gas_turbine", medium="fuel", label="gas to the burner"),
    Connection(
        source="gas_turbine", target="generator", medium="shaft", label="shaft power to the rotor"
    ),
    Connection(
        source="exciter",
        target="generator",
        medium="electrical",
        label="field current to the rotor",
    ),
    Connection(
        source="generator",
        target="generator_bus",
        medium="electrical",
        label="machine terminals to the bus",
    ),
    Connection(
        source="generator_bus",
        target="step_up_transformer",
        medium="electrical",
        label="bus to the transformer's low-voltage winding",
    ),
    Connection(
        source="step_up_transformer",
        target="outgoing_feeder",
        medium="electrical",
        label="transformer to the outgoing feeder",
    ),
    Connection(
        source="outgoing_feeder",
        target="island_load",
        medium="electrical",
        label="feeder to the island's customers",
    ),
    Connection(
        source="ambient",
        target="step_up_transformer",
        medium="heat",
        label="ambient air the oil temperature is measured from",
    ),
    Connection(
        source="dispatch_controller",
        target="fuel_valve",
        medium="signal",
        label="dispatch paces the governor's feedforward",
    ),
    Connection(
        source="voltage_controller",
        target="step_up_transformer",
        medium="signal",
        label="voltage target drives the tap changer",
    ),
)
"""Which way the energy goes, and which instruction drives what."""

POWER_CONTROLLERS: Final = (
    ControllerSpec(
        controller_id="governor",
        kind=ControllerKind.PI,
        measurement=BUS_FREQUENCY,
        setpoint_value=_NOMINAL_HZ,
        output=FUEL_VALVE,
        gain=9.0,
        integral_time_seconds=25.0,
        low=0.0,
        high=100.0,
        description=(
            "Holds the island at nominal frequency by moving the fuel valve. Its feedforward is "
            "not a constant and so is not declared here: the template paces it from the dispatch "
            "setpoint, as a fraction of rated output."
        ),
    ),
    ControllerSpec(
        controller_id="avr",
        kind=ControllerKind.PI,
        measurement=BUS_VOLTAGE,
        setpoint_value=11.0,
        output=EXCITATION,
        gain=14.0,
        integral_time_seconds=6.0,
        low=0.0,
        high=100.0,
        bias=75.0,
        description="Holds the generator bus at nominal voltage by varying excitation.",
    ),
)
"""The two continuous regulators. The tap changer is neither a PI loop nor a hysteresis element —
it is a timer and a single step — so it stays in the template rather than being misdescribed as
one of the two control elements `phos.synth.process` implements."""

POWER_SPEC: Final = PlantSpec(
    plant_id=POWER_DESCRIPTION.plant_id,
    label=POWER_DESCRIPTION.label,
    industry=POWER_DESCRIPTION.industry,
    summary=POWER_DESCRIPTION.summary,
    model_source=POWER_DESCRIPTION.model_source,
    process="power-generation-v1",
    parameters=PowerParameters().model_dump(),
    units=POWER_UNITS,
    signals=POWER_SIGNALS,
    components=POWER_COMPONENTS,
    connections=POWER_CONNECTIONS,
    controllers=POWER_CONTROLLERS,
    couplings=POWER_COUPLINGS,
    control_network=POWER_NETWORK,
    write_authority=POWER_AUTHORITY,
    disturbance=DisturbanceSpec(
        event_plans=tuple(EventPlanSpec.from_plan(plan) for plan in _EVENT_PLANS),
        first_start_floor=60,
        first_start_divisor=12,
        gap_steps=(300, 2400),
    ),
)
"""The generating set, declaratively. `PowerGenerationPlant` builds this one unless handed
another, and `describe()` returns `POWER_DESCRIPTION` field for field."""


class PowerGenerationPlant(Plant):
    """A generating set with a governor, an AVR and a tap changer.

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
        """Build the machine and its regulators for one run.

        Args:
            spec: The run to prepare for.
            commands: Who writes over the control network, or ``None`` for the legacy
                echo path. See `phos.synth.plant.Plant`.
            realism: Ordinary trouble to apply, or ``None`` for a quiet profile. See
                `phos.synth.plant.Plant`.
            plant_spec: The set to build, or ``None`` for `POWER_SPEC` — the one this module has
                always described. See `phos.synth.plants.water.WaterTreatmentPlant`.
        """
        self._plant_spec = plant_spec if plant_spec is not None else POWER_SPEC
        self._description = self._plant_spec.describe()
        self._p = PowerParameters.model_validate(dict(self._plant_spec.parameters))
        self._governor = pi_controller(self._plant_spec, "governor")
        self._avr = pi_controller(self._plant_spec, "avr")
        self._governor_setpoint = fixed_setpoint(self._plant_spec, "governor")
        self._avr_setpoint = fixed_setpoint(self._plant_spec, "avr")
        self._avr_bias = self._plant_spec.controller("avr").bias
        self._tap_timer = 0.0
        super().__init__(spec, commands=commands, realism=realism)

    @property
    def description(self) -> PlantDescription:
        """The machine: sixteen signals across four physical units, on a Modbus network."""
        return self._description

    def initial_state(self) -> Mapping[str, float]:
        """Start from the electrical solution the machine settles at under the opening load."""
        demand = self._demand(0.0, None)
        factor = self._power_factor(0.0, None)
        ambient = self._ambient(0.0)
        output, current = self._electrical_solution(demand, 11.0, factor)
        excitation = self._excitation_for(11.0, current)
        tap = self._tap_for(10.8, 11.0, current)
        return {
            FUEL_VALVE: 100.0 * output / self._p.rated_mw,
            TURBINE_SPEED: self._p.nominal_hz * self._p.rpm_per_hz,
            EXHAUST_TEMP: self._exhaust_target(100.0 * output / self._p.rated_mw, ambient),
            GENERATOR_OUTPUT: output,
            BUS_FREQUENCY: self._p.nominal_hz,
            EXCITATION: excitation,
            BUS_VOLTAGE: 11.0,
            TAP_POSITION: tap,
            TRANSFORMER_OIL_TEMP: ambient
            + self._p.top_oil_rise_k * (current / self._p.rated_current_a) ** 2,
            AMBIENT_TEMP: ambient,
            FEEDER_VOLTAGE: self._feeder_voltage(11.0, tap, current),
            FEEDER_CURRENT: current,
            POWER_FACTOR: factor,
            GRID_DEMAND: demand,
            DISPATCH_SETPOINT: output,
            VOLTAGE_SETPOINT: 10.8,
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
        """Apply the lasting part of an event: a setpoint an operator moved."""
        for key, value in event.parameters.items():
            if key in (DISPATCH_SETPOINT, VOLTAGE_SETPOINT):
                self._state[key] = value

    def control(
        self,
        report: Mapping[str, float],
        active: BenignEvent | None,
        elapsed_hours: float,
        dt_seconds: float,
    ) -> Mapping[str, float]:
        """Run the governor, the AVR and the tap changer, all on what the instruments reported."""
        fuel = self._governor.update(
            measurement=report[BUS_FREQUENCY],
            setpoint=self._governor_setpoint,
            dt_seconds=dt_seconds,
            bias=100.0 * report[DISPATCH_SETPOINT] / self._p.rated_mw,
        )
        excitation = self._avr.update(
            measurement=report[BUS_VOLTAGE],
            setpoint=self._avr_setpoint,
            dt_seconds=dt_seconds,
            bias=self._avr_bias,
        )
        return {
            FUEL_VALVE: fuel,
            EXCITATION: excitation,
            TAP_POSITION: self._tap_step(
                report[FEEDER_VOLTAGE], report[VOLTAGE_SETPOINT], report[TAP_POSITION], dt_seconds
            ),
        }

    def advance(
        self,
        state: Mapping[str, float],
        actuators: Mapping[str, float],
        active: BenignEvent | None,
        elapsed_hours: float,
        dt_seconds: float,
    ) -> Mapping[str, float]:
        """Advance the machine one sample: load, then the electrical solution, then the thermals."""
        demand = self._demand(elapsed_hours, active)
        factor = self._power_factor(elapsed_hours, active)
        ambient = self._ambient(elapsed_hours)
        fuel = actuators[FUEL_VALVE]
        tap = actuators[TAP_POSITION]

        # The voltage settles first, against the load current the previous sample carried, and the
        # electrical solution is then taken at that voltage. Solving the other way round would
        # publish a current consistent with the *previous* voltage, and the power identity — the
        # coupling this plant exists to provide — would hold only approximately.
        bus_voltage = first_order(
            state[BUS_VOLTAGE],
            target=self._bus_voltage_target(actuators[EXCITATION], state[FEEDER_CURRENT]),
            dt_seconds=dt_seconds,
            tau_seconds=self._p.voltage_tau_s,
        )
        output, current = self._electrical_solution(demand, bus_voltage, factor)
        speed = accumulate(
            state[TURBINE_SPEED],
            rate_per_second=self._p.inertia_rpm_per_mw_s
            * (self._p.rated_mw * fuel / 100.0 - output),
            dt_seconds=dt_seconds,
            low=0.0,
            high=3600.0,
        )
        return {
            FUEL_VALVE: fuel,
            TURBINE_SPEED: speed,
            EXHAUST_TEMP: first_order(
                state[EXHAUST_TEMP],
                target=self._exhaust_target(fuel, ambient),
                dt_seconds=dt_seconds,
                tau_seconds=self._p.exhaust_tau_s,
            ),
            GENERATOR_OUTPUT: output,
            BUS_FREQUENCY: speed / self._p.rpm_per_hz,
            EXCITATION: actuators[EXCITATION],
            BUS_VOLTAGE: bus_voltage,
            TAP_POSITION: tap,
            TRANSFORMER_OIL_TEMP: first_order(
                state[TRANSFORMER_OIL_TEMP],
                target=ambient + self._p.top_oil_rise_k * (current / self._p.rated_current_a) ** 2,
                dt_seconds=dt_seconds,
                tau_seconds=self._p.oil_tau_s,
            ),
            AMBIENT_TEMP: ambient,
            FEEDER_VOLTAGE: self._feeder_voltage(bus_voltage, tap, current),
            FEEDER_CURRENT: current,
            POWER_FACTOR: factor,
            GRID_DEMAND: demand,
            DISPATCH_SETPOINT: state[DISPATCH_SETPOINT],
            VOLTAGE_SETPOINT: state[VOLTAGE_SETPOINT],
        }

    def _demand(self, elapsed_hours: float, active: BenignEvent | None) -> float:
        """Return what the network is drawing: a smooth daily curve plus a stepped shift load."""
        daily = cycle_factor(elapsed_hours, 24.0, 7.5, 12.0)
        shift = (0.0, 4.5, 2.0)[shift_index(elapsed_hours, 8.0, 3)]
        step = 0.0
        if active is not None and active.kind == LOAD_STEP:
            step = active.parameters.get("load_step_mw", 0.0)
        return clamp(26.0 + daily + shift + step, 4.0, 58.0)

    def _power_factor(self, elapsed_hours: float, active: BenignEvent | None) -> float:
        """Return the feeder power factor: it moves with the load mix, and with switching."""
        shift = 0.0
        if active is not None and active.kind == FEEDER_SWITCHING:
            shift = active.parameters.get("power_factor_shift", 0.0)
        return clamp(0.93 + cycle_factor(elapsed_hours, 24.0, 0.025, 4.0) + shift, 0.55, 0.99)

    def _ambient(self, elapsed_hours: float) -> float:
        """Return the air temperature: one daily cycle, peaking mid-afternoon."""
        return 14.0 + cycle_factor(elapsed_hours, 24.0, 7.0, 9.0)

    def _electrical_solution(
        self, demand: float, bus_voltage: float, factor: float
    ) -> tuple[float, float]:
        """Return ``(generator output MW, feeder current A)`` consistent with each other.

        Output has to cover the demand *and* the losses that the resulting current causes, so the
        two are mutually dependent. Two passes settle it to well inside the measurement noise, and
        settling it rather than approximating it is what keeps the power identity exact.
        """
        output = demand
        current = 0.0
        for _ in range(2):
            current = self._current_for(output, bus_voltage, factor)
            output = demand + 0.25 + 1.2e-7 * current**2
        return output, self._current_for(output, bus_voltage, factor)

    def _current_for(self, output_mw: float, bus_voltage_kv: float, factor: float) -> float:
        """Return the current three-phase power delivery implies. The identity, rearranged."""
        return output_mw * 1.0e6 / (_ROOT_THREE * max(bus_voltage_kv, 0.1) * 1000.0 * factor)

    def _bus_voltage_target(self, excitation: float, current: float) -> float:
        """Return the terminal voltage an excitation holds against a load current."""
        return 8.0 + 5.0 * excitation / 100.0 - self._p.bus_drop_kv_per_a * current

    def _excitation_for(self, bus_voltage: float, current: float) -> float:
        """Invert the excitation relation: the excitation that would hold ``bus_voltage``."""
        return clamp((bus_voltage - 8.0 + self._p.bus_drop_kv_per_a * current) * 20.0, 0.0, 100.0)

    def _feeder_voltage(self, bus_voltage: float, tap: float, current: float) -> float:
        """Return the feeder voltage: bus voltage through the tap ratio, less the line drop."""
        ratio = self._p.tap_base_ratio + self._p.tap_ratio_per_step * tap
        return bus_voltage * ratio - self._p.line_drop_kv_per_a * current

    def _tap_for(self, wanted: float, bus_voltage: float, current: float) -> float:
        """Return the tap position that would put the feeder closest to ``wanted``."""
        ratio = (wanted + self._p.line_drop_kv_per_a * current) / max(bus_voltage, 0.1)
        return clamp(
            round((ratio - self._p.tap_base_ratio) / self._p.tap_ratio_per_step),
            0.0,
            self._p.tap_steps,
        )

    def _tap_step(
        self, feeder_voltage: float, setpoint: float, tap: float, dt_seconds: float
    ) -> float:
        """Return the tap position after this sample.

        A tap changer is not modulating: it waits out a timer, then moves exactly one step, then
        waits again. That discreteness is the point — it gives the plant a signal that steps.
        """
        self._tap_timer += dt_seconds
        error = feeder_voltage - setpoint
        if self._tap_timer < self._p.tap_delay_s or abs(error) <= self._p.tap_deadband_kv:
            return tap
        self._tap_timer = 0.0
        return clamp(round(tap) + (-1.0 if error > 0.0 else 1.0), 0.0, self._p.tap_steps)

    def _exhaust_target(self, fuel: float, ambient: float) -> float:
        """Return the exhaust temperature a firing rate implies, from the inlet air up."""
        return ambient + 120.0 + 5.2 * fuel


register_template("power-generation-v1", PowerGenerationPlant)

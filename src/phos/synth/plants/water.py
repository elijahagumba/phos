"""A conventional surface-water treatment works, simulated.

The process: raw water is drawn from a river by a variable-speed intake pump, dosed with coagulant
and chlorine, filtered, and stored in a clearwell from which a booster set feeds the distribution
network. A city draws on that network to a daily rhythm nobody controls, and everything upstream
is arranged to keep up with it.

**Why this process.** It has the three properties that make water data hard, and they are hard in
different ways. Its central state is an *integral* — a clearwell level that can only move as fast
as the difference between two flows. Its central quality signal is *delayed*: chlorine dosed now
shows up as a residual an hour or more later, and how much later depends on how full the clearwell
is and how fast the city is drinking. And it has *accumulating* state nobody measures directly —
a filter fouling gradually between backwashes — which is what a headloss reading is actually
telling you about.

**The couplings, which are the point.**

- ``clearwell_level_m`` integrates ``raw_inflow_m3ph`` minus ``distribution_flow_m3ph``. Not
  correlated with them: computed from them, every step.
- ``raw_inflow_m3ph`` follows the square root of ``intake_pump_speed_pct``, because flow through a
  restriction is not proportional to how far it is open.
- ``chlorine_residual_mgpl`` depends on ``chlorine_dose_mgpl``, on ``clearwell_level_m`` and on
  ``distribution_flow_m3ph`` together, through the contact time the last two imply. This is the
  three-way coupling worth having: an attacker who moves any one of them and leaves the others
  alone breaks a relationship rather than a range.
- ``filtered_turbidity_ntu`` depends on ``raw_turbidity_ntu`` and ``coagulant_dose_mgpl``, with a
  lag. Under-dosing shows up downstream, not at the dosing point.
- ``filter_headloss_bar`` integrates the solids the filter has caught since its last backwash —
  ``raw_inflow_m3ph`` times ``raw_turbidity_ntu`` — and is the only view of an internal state no
  instrument is on.
- ``distribution_pressure_bar`` is a pump curve in ``booster_pump_speed_pct`` less a friction term
  in ``distribution_flow_m3ph`` squared.

**The benign events, which are the difficulty.** Operators raise and lower setpoints, filters are
backwashed, the intake is stopped for maintenance, and the river turns muddy after rain. All five
are legitimate, all five move several signals at once, and the last three move them *sharply*. A
plant where the only sharp change is an attack is a plant where detection is trivial and which
does not exist.

**What this is not.** A model of a water works written from public process descriptions — not a
model of any particular works, and not validated against one. See `MODEL_NOT_REALITY_CAVEAT`.
"""

import math
from collections.abc import Mapping, Sequence
from typing import Final

from numpy.random import Generator

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
from phos.synth.process import PiController, accumulate, clamp, cycle_factor, first_order
from phos.synth.realism import RealismProfile

__all__ = [
    "BOOSTER_SPEED",
    "CHLORINE_DOSE",
    "CHLORINE_RESIDUAL",
    "CLEARWELL_LEVEL",
    "COAGULANT_DOSE",
    "DISTRIBUTION_FLOW",
    "DISTRIBUTION_PRESSURE",
    "ENGINEERING",
    "FILTERED_TURBIDITY",
    "FILTER_HEADLOSS",
    "INTAKE_SPEED",
    "LEVEL_SETPOINT",
    "PRESSURE_SETPOINT",
    "RAW_INFLOW",
    "RAW_TURBIDITY",
    "RESIDUAL_SETPOINT",
    "WATER_DESCRIPTION",
    "WaterTreatmentPlant",
]

RAW_INFLOW: Final = "raw_inflow_m3ph"
INTAKE_SPEED: Final = "intake_pump_speed_pct"
RAW_TURBIDITY: Final = "raw_turbidity_ntu"
COAGULANT_DOSE: Final = "coagulant_dose_mgpl"
CHLORINE_DOSE: Final = "chlorine_dose_mgpl"
FILTERED_TURBIDITY: Final = "filtered_turbidity_ntu"
FILTER_HEADLOSS: Final = "filter_headloss_m"
CLEARWELL_LEVEL: Final = "clearwell_level_m"
CHLORINE_RESIDUAL: Final = "chlorine_residual_mgpl"
DISTRIBUTION_FLOW: Final = "distribution_flow_m3ph"
DISTRIBUTION_PRESSURE: Final = "distribution_pressure_bar"
BOOSTER_SPEED: Final = "booster_pump_speed_pct"
LEVEL_SETPOINT: Final = "clearwell_level_setpoint_m"
LEVEL_SETPOINT_OPERATING_LOW: Final = 2.6
"""Lowest clearwell setpoint an ordinary operator write on this plant already uses."""
LEVEL_SETPOINT_OPERATING_HIGH: Final = 3.8
"""Highest clearwell setpoint an ordinary operator write on this plant already uses."""
RESIDUAL_SETPOINT: Final = "chlorine_residual_setpoint_mgpl"
PRESSURE_SETPOINT: Final = "distribution_pressure_setpoint_bar"
ENGINEERING: Final = "engineering"
"""A declared OT workstation that emits no baseline traffic.

Writes from this node are the unknown-master shape ADR 0027 measures. The SCADA poller also
never *writes* in normal operation, but it *is* on the learned command graph, so a write from it
is an unexpected function on a known link — ADR 0014's remaining indistinguishability, not an
unknown master (ADR 0034)."""

FILTER_LOAD: Final = "filter_solids_load_m3ntu"
"""Internal: solids the filter has caught since its last backwash. No instrument is on it."""

CONTACT_TIME: Final = "chlorine_contact_time_h"
"""Internal: how long water sits in the clearwell, which sets how much chlorine survives."""

BACKWASH: Final = "filter_backwash"
INTAKE_STOP: Final = "intake_maintenance_stop"
RAW_EXCURSION: Final = "raw_water_excursion"
LEVEL_SETPOINT_CHANGE: Final = "level_setpoint_change"
RESIDUAL_SETPOINT_CHANGE: Final = "residual_setpoint_change"
PRESSURE_SETPOINT_CHANGE: Final = "pressure_setpoint_change"

_CLEARWELL_AREA_M2: Final = 250.0
_MAX_INTAKE_M3PH: Final = 260.0
_DEMAND_BASE_M3PH: Final = 180.0
_DEMAND_DAILY_M3PH: Final = 35.0
_DEMAND_HALF_DAILY_M3PH: Final = 30.0
_DEMAND_FLOOR_M3PH: Final = 30.0
_CHLORINE_DECAY_PER_HOUR: Final = 0.25
_RESIDUAL_TAU_S: Final = 1800.0
_TURBIDITY_TAU_S: Final = 600.0
_PRESSURE_TAU_S: Final = 120.0
_HEADLOSS_CLEAN_M: Final = 0.25
_HEADLOSS_PER_LOAD: Final = 4.5e-5
_BACKWASH_INTAKE_PCT: Final = 10.0
_MIN_FILTER_FRACTION: Final = 0.02
_MAX_FILTER_FRACTION: Final = 0.28
_COAGULANT_BASE_MGPL: Final = 0.6
_COAGULANT_PER_NTU: Final = 0.45

WATER_UNITS: Final = (
    PhysicalUnit(unit_id="intake", label="River intake and raw water pumps"),
    PhysicalUnit(unit_id="dosing", label="Chemical dosing skid"),
    PhysicalUnit(unit_id="filtration", label="Rapid gravity filter"),
    PhysicalUnit(unit_id="clearwell", label="Treated water clearwell"),
    PhysicalUnit(unit_id="distribution", label="Distribution booster set"),
)

WATER_SIGNALS: Final = (
    SignalSpec(
        key=RAW_INFLOW,
        label="Raw water inflow",
        unit="m3/h",
        kind=SignalKind.SENSOR,
        physical_unit="intake",
        low=0.0,
        high=300.0,
        noise_stddev=1.2,
        drift_amplitude=0.8,
    ),
    SignalSpec(
        key=INTAKE_SPEED,
        label="Intake pump speed",
        unit="%",
        kind=SignalKind.ACTUATOR,
        physical_unit="intake",
        low=0.0,
        high=100.0,
        noise_stddev=0.15,
    ),
    SignalSpec(
        key=RAW_TURBIDITY,
        label="Raw water turbidity",
        unit="NTU",
        kind=SignalKind.SENSOR,
        physical_unit="intake",
        low=0.0,
        high=60.0,
        noise_stddev=0.12,
        drift_amplitude=0.15,
    ),
    SignalSpec(
        key=COAGULANT_DOSE,
        label="Coagulant dose",
        unit="mg/L",
        kind=SignalKind.ACTUATOR,
        physical_unit="dosing",
        low=0.0,
        high=20.0,
        noise_stddev=0.03,
    ),
    SignalSpec(
        key=CHLORINE_DOSE,
        label="Chlorine dose",
        unit="mg/L",
        kind=SignalKind.ACTUATOR,
        physical_unit="dosing",
        low=0.0,
        high=6.0,
        noise_stddev=0.01,
    ),
    SignalSpec(
        key=FILTERED_TURBIDITY,
        label="Filtered water turbidity",
        unit="NTU",
        kind=SignalKind.SENSOR,
        physical_unit="filtration",
        low=0.0,
        high=6.0,
        noise_stddev=0.008,
        drift_amplitude=0.012,
    ),
    SignalSpec(
        key=FILTER_HEADLOSS,
        label="Filter headloss",
        unit="m",
        kind=SignalKind.SENSOR,
        physical_unit="filtration",
        low=0.0,
        high=3.5,
        noise_stddev=0.006,
        drift_amplitude=0.012,
    ),
    SignalSpec(
        key=CLEARWELL_LEVEL,
        label="Clearwell level",
        unit="m",
        kind=SignalKind.SENSOR,
        physical_unit="clearwell",
        low=0.0,
        high=6.0,
        noise_stddev=0.008,
        drift_amplitude=0.015,
    ),
    SignalSpec(
        key=CHLORINE_RESIDUAL,
        label="Free chlorine residual",
        unit="mg/L",
        kind=SignalKind.SENSOR,
        physical_unit="clearwell",
        low=0.0,
        high=3.0,
        noise_stddev=0.006,
        drift_amplitude=0.010,
    ),
    SignalSpec(
        key=DISTRIBUTION_FLOW,
        label="Distribution flow",
        unit="m3/h",
        kind=SignalKind.SENSOR,
        physical_unit="distribution",
        low=0.0,
        high=350.0,
        noise_stddev=1.4,
        drift_amplitude=0.9,
    ),
    SignalSpec(
        key=DISTRIBUTION_PRESSURE,
        label="Distribution pressure",
        unit="bar",
        kind=SignalKind.SENSOR,
        physical_unit="distribution",
        low=0.0,
        high=9.0,
        noise_stddev=0.015,
        drift_amplitude=0.02,
    ),
    SignalSpec(
        key=BOOSTER_SPEED,
        label="Booster pump speed",
        unit="%",
        kind=SignalKind.ACTUATOR,
        physical_unit="distribution",
        low=0.0,
        high=100.0,
        noise_stddev=0.15,
    ),
    SignalSpec(
        key=LEVEL_SETPOINT,
        label="Clearwell level setpoint",
        unit="m",
        kind=SignalKind.SETPOINT,
        physical_unit="clearwell",
        low=0.0,
        high=6.0,
        noise_stddev=0.0,
    ),
    SignalSpec(
        key=RESIDUAL_SETPOINT,
        label="Chlorine residual setpoint",
        unit="mg/L",
        kind=SignalKind.SETPOINT,
        physical_unit="clearwell",
        low=0.0,
        high=3.0,
        noise_stddev=0.0,
    ),
    SignalSpec(
        key=PRESSURE_SETPOINT,
        label="Distribution pressure setpoint",
        unit="bar",
        kind=SignalKind.SETPOINT,
        physical_unit="distribution",
        low=0.0,
        high=9.0,
        noise_stddev=0.0,
    ),
)

WATER_COUPLINGS: Final = (
    Coupling(
        driven=CLEARWELL_LEVEL,
        drivers=(RAW_INFLOW, DISTRIBUTION_FLOW),
        kind=CouplingKind.INTEGRATION,
        relation=(
            "level integrates (raw inflow - distribution flow) over the clearwell's 250 m2 plan "
            "area; it cannot move faster than that difference allows"
        ),
    ),
    Coupling(
        driven=RAW_INFLOW,
        drivers=(INTAKE_SPEED,),
        kind=CouplingKind.ALGEBRAIC,
        relation="inflow follows the square root of intake pump speed at 260 m3/h wide open",
    ),
    Coupling(
        driven=FILTERED_TURBIDITY,
        drivers=(RAW_TURBIDITY, COAGULANT_DOSE),
        kind=CouplingKind.LAG,
        relation=(
            "filtered turbidity lags a residual fraction of raw turbidity that falls "
            "exponentially with coagulant dose per unit of raw turbidity"
        ),
    ),
    Coupling(
        driven=FILTER_HEADLOSS,
        drivers=(RAW_INFLOW, RAW_TURBIDITY),
        kind=CouplingKind.INTEGRATION,
        relation=(
            "headloss rises with the solids caught since the last backwash, which is the integral "
            "of inflow times raw turbidity"
        ),
    ),
    Coupling(
        driven=CHLORINE_RESIDUAL,
        drivers=(CHLORINE_DOSE, CLEARWELL_LEVEL, DISTRIBUTION_FLOW),
        kind=CouplingKind.LAG,
        relation=(
            "residual lags the dose decayed over the contact time, and contact time is clearwell "
            "volume divided by distribution flow — so level and demand set how much dose survives"
        ),
    ),
    Coupling(
        driven=DISTRIBUTION_PRESSURE,
        drivers=(BOOSTER_SPEED, DISTRIBUTION_FLOW),
        kind=CouplingKind.LAG,
        relation=(
            "pressure lags a pump curve in booster speed squared, less a friction term in "
            "distribution flow squared"
        ),
    ),
    Coupling(
        driven=INTAKE_SPEED,
        drivers=(CLEARWELL_LEVEL, LEVEL_SETPOINT),
        kind=CouplingKind.CONTROL,
        relation="a PI loop holds clearwell level at its setpoint by moving the intake pump",
    ),
    Coupling(
        driven=CHLORINE_DOSE,
        drivers=(CHLORINE_RESIDUAL, RESIDUAL_SETPOINT),
        kind=CouplingKind.CONTROL,
        relation="a PI loop holds the residual at its setpoint by moving the chlorine dose",
    ),
    Coupling(
        driven=COAGULANT_DOSE,
        drivers=(RAW_TURBIDITY,),
        kind=CouplingKind.CONTROL,
        relation="coagulant is paced feedforward from raw turbidity, with no feedback",
    ),
    Coupling(
        driven=BOOSTER_SPEED,
        drivers=(DISTRIBUTION_PRESSURE, PRESSURE_SETPOINT),
        kind=CouplingKind.CONTROL,
        relation="a PI loop holds distribution pressure at its setpoint by moving the booster set",
    ),
)

WATER_NETWORK: Final = ControlNetwork(
    nodes=(
        NetworkNode(node_id="scada", label="SCADA server", ip="10.30.0.10", role="scada"),
        NetworkNode(node_id="plc_inlet", label="Inlet and dosing PLC", ip="10.30.0.21", role="plc"),
        NetworkNode(
            node_id="plc_outlet",
            label="Clearwell and distribution PLC",
            ip="10.30.0.22",
            role="plc",
        ),
        NetworkNode(node_id="hmi", label="Control room HMI", ip="10.30.0.40", role="hmi"),
        NetworkNode(
            node_id=ENGINEERING,
            label="Engineering workstation",
            ip="10.30.0.50",
            role="engineering",
        ),
    ),
    blocks=(
        RegisterBlock(
            node_id="plc_inlet",
            start_address=100,
            signals=(
                RAW_INFLOW,
                INTAKE_SPEED,
                RAW_TURBIDITY,
                COAGULANT_DOSE,
                CHLORINE_DOSE,
                FILTERED_TURBIDITY,
                FILTER_HEADLOSS,
            ),
        ),
        RegisterBlock(
            node_id="plc_outlet",
            start_address=200,
            signals=(
                CLEARWELL_LEVEL,
                CHLORINE_RESIDUAL,
                DISTRIBUTION_FLOW,
                DISTRIBUTION_PRESSURE,
                BOOSTER_SPEED,
            ),
        ),
        RegisterBlock(
            node_id="plc_outlet",
            start_address=300,
            signals=(LEVEL_SETPOINT, RESIDUAL_SETPOINT, PRESSURE_SETPOINT),
            writable=True,
        ),
    ),
    poller="scada",
    operator="hmi",
    poll_interval_seconds=30.0,
    unit_id=1,
)

WATER_AUTHORITY: Final = WriteAuthority(
    grants={"hmi": frozenset({LEVEL_SETPOINT, RESIDUAL_SETPOINT, PRESSURE_SETPOINT})}
)
"""Who this works permits to write a setpoint: the control-room HMI, and nothing else.

A declaration, not a discovery — the point of declaring it is that the authorisation recorded
against a write comes from a stated policy rather than from what some device was seen doing.

Three shapes fall out of granting exactly one station, and each is a case worth being able to
build. A write from ``hmi`` is authorised and comes from a known station. A write from ``scada``
is *unauthorised* and still comes from a known station — the compromised legitimate host, which
is the hard case, because the graph has learned that link and nothing structural is out of place.
A write from ``engineering`` is unauthorised and comes from a device that has never commanded
anything, which is the unknown-master shape ADR 0027 split the templates for.

Whether a real works lets its SCADA server write setpoints varies by site. This one does not, and
says so here, because a plant that permitted everything could not express the middle case.
"""

WATER_DESCRIPTION: Final = PlantDescription(
    plant_id="water-treatment",
    label="Surface water treatment works",
    industry="water treatment",
    summary=(
        "River intake, coagulant and chlorine dosing, rapid gravity filtration, a clearwell, and a "
        "booster set feeding a distribution network with a daily demand rhythm."
    ),
    model_source=(
        "Written from public descriptions of conventional surface-water treatment: coagulation "
        "and rapid gravity filtration, chlorine contact time in a clearwell with first-order "
        "decay, square-root valve/pump flow characteristics, and quadratic pump curves. Not "
        "modelled on, or validated against, any particular works."
    ),
    units=WATER_UNITS,
    signals=WATER_SIGNALS,
    couplings=WATER_COUPLINGS,
    control_network=WATER_NETWORK,
    write_authority=WATER_AUTHORITY,
)

_EVENT_PLANS: Final = (
    EventPlan(
        kind=LEVEL_SETPOINT_CHANGE,
        label="Operator moves the clearwell level setpoint",
        duration_steps=0,
        writes=(LEVEL_SETPOINT,),
        parameter_ranges={
            LEVEL_SETPOINT: (LEVEL_SETPOINT_OPERATING_LOW, LEVEL_SETPOINT_OPERATING_HIGH)
        },
        detail="new clearwell level setpoint:",
    ),
    EventPlan(
        kind=BACKWASH,
        label="Filter backwash",
        duration_steps=40,
        detail="filter taken off line and washed; intake throttled, solids load reset",
    ),
    EventPlan(
        kind=RESIDUAL_SETPOINT_CHANGE,
        label="Operator moves the chlorine residual setpoint",
        duration_steps=0,
        writes=(RESIDUAL_SETPOINT,),
        parameter_ranges={RESIDUAL_SETPOINT: (0.45, 0.85)},
        detail="new residual setpoint:",
    ),
    # A filter is washed several times for every setpoint an operator moves, so the wash appears
    # twice in the round-robin. Without that the fouling integral runs to the top of the
    # instrument's span between washes, which is not what a filter does.
    EventPlan(
        kind=BACKWASH,
        label="Filter backwash",
        duration_steps=40,
        detail="filter taken off line and washed; intake throttled, solids load reset",
    ),
    EventPlan(
        kind=RAW_EXCURSION,
        label="Raw water quality excursion after rainfall",
        duration_steps=240,
        parameter_ranges={"raw_turbidity_boost_ntu": (3.0, 11.0)},
        detail="river turbidity elevated:",
    ),
    EventPlan(
        kind=PRESSURE_SETPOINT_CHANGE,
        label="Operator moves the distribution pressure setpoint",
        duration_steps=0,
        writes=(PRESSURE_SETPOINT,),
        parameter_ranges={PRESSURE_SETPOINT: (3.9, 4.6)},
        detail="new distribution pressure setpoint:",
    ),
    EventPlan(
        kind=INTAKE_STOP,
        label="Intake stopped for planned maintenance",
        duration_steps=120,
        detail="intake pump stopped; clearwell draws down on demand",
    ),
)


class WaterTreatmentPlant(Plant):
    """A surface water treatment works with three closed loops and one feedforward.

    See the module docstring for the process, the couplings and what the model is and is not.
    """

    def __init__(
        self,
        spec: RunSpec,
        *,
        commands: CommandSource | None = None,
        realism: RealismProfile | None = None,
    ) -> None:
        """Build the works and its control loops for one run.

        Args:
            spec: The run to prepare for.
            commands: Who writes over the control network, or ``None`` for the legacy
                echo path. See `phos.synth.plant.Plant`.
            realism: Ordinary trouble to apply, or ``None`` for a quiet profile. See
                `phos.synth.plant.Plant`.
        """
        self._level_loop = PiController(gain=26.0, integral_time_seconds=900.0, low=0.0, high=100.0)
        self._residual_loop = PiController(
            gain=0.9, integral_time_seconds=1500.0, low=0.0, high=6.0
        )
        self._pressure_loop = PiController(
            gain=9.0, integral_time_seconds=300.0, low=0.0, high=100.0
        )
        super().__init__(spec, commands=commands, realism=realism)

    @property
    def description(self) -> PlantDescription:
        """The works: fifteen signals across five physical units, on a Modbus network."""
        return WATER_DESCRIPTION

    def initial_state(self) -> Mapping[str, float]:
        """Start from the steady state the loops would settle at under the opening demand."""
        demand = self._demand(0.0)
        inflow = demand
        speed = 100.0 * (inflow / _MAX_INTAKE_M3PH) ** 2
        turbidity = self._raw_turbidity(0.0, None)
        coagulant = self._coagulant(turbidity)
        contact = _CLEARWELL_AREA_M2 * 3.0 / max(demand, 1.0)
        survival = math.exp(-_CHLORINE_DECAY_PER_HOUR * contact)
        dose = 0.6 / survival
        return {
            RAW_INFLOW: inflow,
            INTAKE_SPEED: speed,
            RAW_TURBIDITY: turbidity,
            COAGULANT_DOSE: coagulant,
            CHLORINE_DOSE: dose,
            FILTERED_TURBIDITY: turbidity * self._filter_fraction(coagulant, turbidity),
            FILTER_HEADLOSS: _HEADLOSS_CLEAN_M,
            CLEARWELL_LEVEL: 3.0,
            CHLORINE_RESIDUAL: 0.6,
            DISTRIBUTION_FLOW: demand,
            DISTRIBUTION_PRESSURE: 4.2,
            BOOSTER_SPEED: self._booster_for(4.2, demand),
            LEVEL_SETPOINT: 3.0,
            RESIDUAL_SETPOINT: 0.6,
            PRESSURE_SETPOINT: 4.2,
            FILTER_LOAD: 0.0,
            CONTACT_TIME: contact,
        }

    def schedule_events(self, rng: Generator, spec: RunSpec) -> Sequence[BenignEvent]:
        """Lay the five kinds of operational event through the run, round-robin."""
        return lay_out_events(
            rng,
            spec,
            _EVENT_PLANS,
            first_start_step=max(30, spec.n_steps // 12),
            gap_steps=(120, 900),
        )

    def begin_event(self, event: BenignEvent) -> None:
        """Apply the lasting part of an event: a moved setpoint, or a washed filter."""
        for key, value in event.parameters.items():
            if key in (LEVEL_SETPOINT, RESIDUAL_SETPOINT, PRESSURE_SETPOINT):
                self._state[key] = value
        if event.kind == BACKWASH:
            self._state[FILTER_LOAD] = 0.0

    def control(
        self,
        report: Mapping[str, float],
        active: BenignEvent | None,
        elapsed_hours: float,
        dt_seconds: float,
    ) -> Mapping[str, float]:
        """Run the three loops and the feedforward, all on what the instruments reported."""
        manual = active.kind if active is not None else ""
        if manual == BACKWASH:
            intake = _BACKWASH_INTAKE_PCT
        elif manual == INTAKE_STOP:
            intake = 0.0
        else:
            intake = self._level_loop.update(
                measurement=report[CLEARWELL_LEVEL],
                setpoint=report[LEVEL_SETPOINT],
                dt_seconds=dt_seconds,
                bias=33.0,
            )
        return {
            INTAKE_SPEED: intake,
            COAGULANT_DOSE: self._coagulant(report[RAW_TURBIDITY]),
            CHLORINE_DOSE: self._residual_loop.update(
                measurement=report[CHLORINE_RESIDUAL],
                setpoint=report[RESIDUAL_SETPOINT],
                dt_seconds=dt_seconds,
                bias=1.4,
            ),
            BOOSTER_SPEED: self._pressure_loop.update(
                measurement=report[DISTRIBUTION_PRESSURE],
                setpoint=report[PRESSURE_SETPOINT],
                dt_seconds=dt_seconds,
                bias=55.0,
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
        """Advance the works one sample: flows, then storage, then quality."""
        demand = self._demand(elapsed_hours)
        turbidity = self._raw_turbidity(elapsed_hours, active)
        intake = actuators[INTAKE_SPEED]
        inflow = _MAX_INTAKE_M3PH * math.sqrt(clamp(intake, 0.0, 100.0) / 100.0)

        level = accumulate(
            state[CLEARWELL_LEVEL],
            rate_per_second=(inflow - demand) / _CLEARWELL_AREA_M2 / 3600.0,
            dt_seconds=dt_seconds,
            low=0.0,
            high=6.0,
        )
        load = state[FILTER_LOAD] + inflow * turbidity * dt_seconds / 3600.0
        headloss = clamp(_HEADLOSS_CLEAN_M + _HEADLOSS_PER_LOAD * load, 0.0, 3.5)

        coagulant = actuators[COAGULANT_DOSE]
        filtered = first_order(
            state[FILTERED_TURBIDITY],
            target=turbidity * self._filter_fraction(coagulant, turbidity),
            dt_seconds=dt_seconds,
            tau_seconds=_TURBIDITY_TAU_S,
        )

        contact = _CLEARWELL_AREA_M2 * level / max(demand, 1.0)
        survival = math.exp(-_CHLORINE_DECAY_PER_HOUR * contact)
        residual = first_order(
            state[CHLORINE_RESIDUAL],
            target=actuators[CHLORINE_DOSE] * survival,
            dt_seconds=dt_seconds,
            tau_seconds=_RESIDUAL_TAU_S,
        )

        booster = actuators[BOOSTER_SPEED]
        pressure = first_order(
            state[DISTRIBUTION_PRESSURE],
            target=self._pressure_for(booster, demand),
            dt_seconds=dt_seconds,
            tau_seconds=_PRESSURE_TAU_S,
        )

        return {
            RAW_INFLOW: inflow,
            INTAKE_SPEED: intake,
            RAW_TURBIDITY: turbidity,
            COAGULANT_DOSE: coagulant,
            CHLORINE_DOSE: actuators[CHLORINE_DOSE],
            FILTERED_TURBIDITY: filtered,
            FILTER_HEADLOSS: headloss,
            CLEARWELL_LEVEL: level,
            CHLORINE_RESIDUAL: clamp(residual, 0.0, 3.0),
            DISTRIBUTION_FLOW: demand,
            DISTRIBUTION_PRESSURE: clamp(pressure, 0.0, 9.0),
            BOOSTER_SPEED: booster,
            LEVEL_SETPOINT: state[LEVEL_SETPOINT],
            RESIDUAL_SETPOINT: state[RESIDUAL_SETPOINT],
            PRESSURE_SETPOINT: state[PRESSURE_SETPOINT],
            FILTER_LOAD: load,
            CONTACT_TIME: contact,
        }

    def _demand(self, elapsed_hours: float) -> float:
        """Return what the city is drawing: a daily rhythm with a morning peak and an evening bump.

        Exogenous by construction. Nothing in the works controls it, which is what makes it the
        driver every other signal is ultimately responding to.
        """
        daily = cycle_factor(elapsed_hours, 24.0, _DEMAND_DAILY_M3PH, 2.0)
        half = cycle_factor(elapsed_hours, 12.0, _DEMAND_HALF_DAILY_M3PH, 5.0)
        return max(_DEMAND_BASE_M3PH + daily + half, _DEMAND_FLOOR_M3PH)

    def _raw_turbidity(self, elapsed_hours: float, active: BenignEvent | None) -> float:
        """Return river turbidity: a slow natural wander, lifted while rainfall is washing in."""
        base = (
            6.0
            + cycle_factor(elapsed_hours, 72.0, 2.2, 10.0)
            + cycle_factor(elapsed_hours, 24.0, 0.7, 5.0)
        )
        boost = 0.0
        if active is not None and active.kind == RAW_EXCURSION:
            boost = active.parameters.get("raw_turbidity_boost_ntu", 0.0)
        return clamp(base + boost, 0.5, 60.0)

    def _coagulant(self, raw_turbidity: float) -> float:
        """Return the feedforward coagulant dose. Paced from turbidity, with no feedback."""
        return clamp(_COAGULANT_BASE_MGPL + _COAGULANT_PER_NTU * raw_turbidity, 0.0, 20.0)

    def _filter_fraction(self, coagulant: float, raw_turbidity: float) -> float:
        """Return the share of raw turbidity that survives coagulation and filtration.

        Falls exponentially with dose *per unit of raw turbidity*, so a dose that is generous for
        clean water is thin for muddy water — which is why an excursion shows downstream even
        though the dosing loop is working exactly as designed.
        """
        demand = max(0.35 * raw_turbidity, 0.1)
        return _MIN_FILTER_FRACTION + _MAX_FILTER_FRACTION * math.exp(-coagulant / demand)

    def _pressure_for(self, booster_speed: float, flow: float) -> float:
        """Return the pressure a booster speed produces against a flow: pump curve less friction."""
        return 1.0 + 9.0 * (booster_speed / 100.0) ** 2 - 3.0e-5 * flow**2

    def _booster_for(self, pressure: float, flow: float) -> float:
        """Invert the pump curve: the speed that would hold ``pressure`` at ``flow``."""
        squared = (pressure - 1.0 + 3.0e-5 * flow**2) / 9.0
        return clamp(100.0 * math.sqrt(max(squared, 0.0)), 0.0, 100.0)

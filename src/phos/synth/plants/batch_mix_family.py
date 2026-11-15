"""The `batch_mix` family: how a seed becomes one set of parallel batch trains.

PART R2. `phos.synth.plants.batch_mix` holds the physics, the phase machine and the couplings;
this module holds what may vary.

**Three parameters are derived, and all three are rates the recipe implies.** The feed rate is the
full charge divided by a drawn charge time, the discharge rate is the full charge divided by a
drawn discharge time, and the jacket's hot service temperature is the reaction temperature plus a
drawn approach. Drawing kilograms per hour directly gives vessels that fill in four seconds or in
nine hours; drawing the *time* gives a recipe, which is what an operator actually writes down.

**The Arrhenius constants are the one place a draw can quietly produce nonsense**, because the
rate is exponential in the activation temperature. The bounds below are narrow for that reason,
and the pair is drawn so that the rate at the reaction temperature lands in a usable band — fast
enough that a batch finishes inside its hold, slow enough that it does not finish during heating.
PART R3's gate is still what refuses the ones that get through.
"""

import math
from collections.abc import Mapping
from typing import Final

from phos.synth.families import BoundScale, ParameterBound, PlantFamily, bounded, register_family
from phos.synth.plant import Coupling, CouplingKind, PhysicalUnit, SignalKind, SignalSpec
from phos.synth.plant_spec import (
    Component,
    ComponentKind,
    Connection,
    ControllerKind,
    ControllerSpec,
    DisturbanceSpec,
    EventPlanSpec,
    PlantSpec,
)
from phos.synth.plants.batch_mix import (
    AGITATOR_POWER,
    AGITATOR_SPEED,
    BATCH_MIX_PROCESS,
    CHARGE,
    CONVERSION,
    DUTY,
    FEED_VALVE,
    HOLD_CHANGE,
    JACKET_TEMPERATURE,
    PHASE,
    RECIPE_CHANGE,
    TEMPERATURE,
    TEMPERATURE_SETPOINT,
    Phase,
    jacket_loop_id,
    temperature_loop_id,
)
from phos.synth.plants.spec_build import (
    RolePosition,
    draw_naming_scheme,
    modbus_network,
    operator_authority,
    render_tags,
    roles_from_tags,
)
from phos.synth.randomise import StreamDraw

__all__ = ["BATCH_MIX_BOUNDS", "BatchMixFamily"]

_PREFIXES: Final = ("", "RX", "BATCH", "R", "PLANT")

BATCH_MIX_BOUNDS: Final = (
    ParameterBound(
        "trains",
        1,
        3,
        BoundScale.INTEGER,
        "",
        "How many reactor trains run side by side. Each runs the recipe independently and they "
        "are started staggered, so the site is never in one state.",
    ),
    ParameterBound(
        "full_charge_kg",
        400.0,
        12000.0,
        BoundScale.LOG,
        "kg",
        "Mass in a vessel at a full charge.",
    ),
    ParameterBound(
        "charge_minutes",
        6.0,
        45.0,
        BoundScale.LINEAR,
        "min",
        "How long a vessel takes to fill. The feed rate is derived from this and the charge, "
        "because a recipe specifies a time and an operator would never quote a kg/h.",
    ),
    ParameterBound(
        "discharge_minutes",
        4.0,
        30.0,
        BoundScale.LINEAR,
        "min",
        "How long a vessel takes to empty. The discharge rate is derived from it.",
    ),
    ParameterBound(
        "heat_capacity_kj_per_kg_k",
        1.6,
        4.2,
        BoundScale.LINEAR,
        "kJ/kg/K",
        "Specific heat of the batch.",
    ),
    ParameterBound(
        "vessel_thermal_fraction",
        0.02,
        0.20,
        BoundScale.LINEAR,
        "",
        "Thermal mass of the steel itself, as a fraction of a full charge. Why an empty vessel "
        "does not change temperature instantly.",
    ),
    ParameterBound(
        "wall_ua_kw_per_k",
        2.0,
        60.0,
        BoundScale.LOG,
        "kW/K",
        "How fast heat crosses from the jacket into the batch. With the charge this sets how long "
        "the heat step takes.",
    ),
    ParameterBound(
        "reaction_enthalpy_kj_per_kg",
        40.0,
        400.0,
        BoundScale.LOG,
        "kJ/kg",
        "Heat released per kilogram converted. The reaction warms itself, which is why the loop "
        "has to back the jacket off once it starts.",
    ),
    ParameterBound(
        "arrhenius_temperature_k",
        5000.0,
        10000.0,
        BoundScale.LINEAR,
        "K",
        "Activation temperature of the reaction. With the prefactor this is why a batch held ten "
        "degrees cooler takes markedly longer, so a temperature attack shows up in the timing of "
        "everything downstream.",
    ),
    ParameterBound(
        "reaction_half_life_minutes",
        4.0,
        40.0,
        BoundScale.LOG,
        "min",
        "How long the reaction takes to convert half of what is left, at the reaction "
        "temperature. The Arrhenius prefactor is derived from this and the activation "
        "temperature, because a prefactor drawn directly produces batches that finish during "
        "heating or never finish at all.",
    ),
    ParameterBound(
        "jacket_tau_s",
        30.0,
        400.0,
        BoundScale.LOG,
        "s",
        "How long the jacket's own temperature takes to follow its valve.",
    ),
    ParameterBound(
        "jacket_cold_c",
        5.0,
        40.0,
        BoundScale.LINEAR,
        "degC",
        "Jacket temperature with the service valve shut — the cold utility.",
    ),
    ParameterBound(
        "jacket_approach_c",
        15.0,
        60.0,
        BoundScale.LINEAR,
        "degC",
        "How much hotter than the reaction temperature the hot utility is. The jacket has to be "
        "above the batch for heat to flow into it, and this is the margin a designer picks.",
    ),
    ParameterBound(
        "feed_temp_c",
        4.0,
        30.0,
        BoundScale.LINEAR,
        "degC",
        "Temperature the reagent arrives at. Cold feed cools the batch when it charges.",
    ),
    ParameterBound(
        "reaction_temp_c",
        55.0,
        140.0,
        BoundScale.LINEAR,
        "degC",
        "Temperature the recipe calls for while the batch reacts.",
    ),
    ParameterBound(
        "temperature_headroom",
        1.3,
        2.0,
        BoundScale.LINEAR,
        "",
        "How far above the reaction temperature the transmitters are calibrated, as a multiple.",
    ),
    ParameterBound(
        "idle_minutes",
        3.0,
        40.0,
        BoundScale.LINEAR,
        "min",
        "How long a vessel waits empty between batches — turnaround, cleaning, waiting for a "
        "tanker.",
    ),
    ParameterBound(
        "hold_minutes",
        20.0,
        180.0,
        BoundScale.LINEAR,
        "min",
        "How long the react step holds if conversion has not reached its target first.",
    ),
    ParameterBound(
        "conversion_target_pct",
        88.0,
        98.0,
        BoundScale.LINEAR,
        "%",
        "Conversion the recipe calls for before the batch may be discharged.",
    ),
    ParameterBound(
        "arrival_margin_c",
        0.5,
        4.0,
        BoundScale.LINEAR,
        "degC",
        "How close to setpoint counts as up to temperature, so the hold may start.",
    ),
    ParameterBound(
        "agitator_rated_kw",
        2.0,
        60.0,
        BoundScale.LOG,
        "kW",
        "Agitator power at rated speed in a full vessel.",
    ),
    ParameterBound(
        "agitator_base_fraction",
        0.01,
        0.10,
        BoundScale.LINEAR,
        "",
        "Power the drive takes with the vessel empty, as a fraction of its rating — its own "
        "losses.",
    ),
    ParameterBound(
        "agitator_rated_rpm",
        40.0,
        220.0,
        BoundScale.LINEAR,
        "rpm",
        "Speed the agitator's rating is quoted at, and what it runs at while heating and reacting.",
    ),
    ParameterBound(
        "agitator_idle_fraction",
        0.0,
        0.35,
        BoundScale.LINEAR,
        "",
        "Speed the agitator turns at outside the heat and react steps, as a fraction of rated. "
        "Some sites keep it ticking over and some stop it.",
    ),
    ParameterBound(
        "viscosity_per_conversion",
        0.4,
        3.0,
        BoundScale.LINEAR,
        "",
        "How much harder the agitator works at full conversion than at none. This is what makes "
        "the drive's power a second witness to conversion.",
    ),
    ParameterBound(
        "stagger_fraction",
        0.0,
        1.0,
        BoundScale.LINEAR,
        "",
        "How far apart the trains start their recipes, as a fraction of the idle time. At zero "
        "they run in lockstep, which is the case a detector could learn once and know all of.",
    ),
    ParameterBound(
        "temperature_noise_c",
        0.02,
        0.8,
        BoundScale.LOG,
        "degC",
        "Measurement noise on the batch and jacket temperature transmitters.",
    ),
    ParameterBound(
        "temperature_drift_c",
        0.005,
        0.4,
        BoundScale.LOG,
        "degC",
        "Bound on each temperature transmitter's slow calibration drift.",
    ),
    ParameterBound(
        "level_noise_pct",
        0.02,
        0.9,
        BoundScale.LOG,
        "%",
        "Measurement noise on the vessel's level.",
    ),
    ParameterBound(
        "power_noise_fraction",
        0.002,
        0.04,
        BoundScale.LOG,
        "",
        "Measurement noise on the agitator's power meter, as a fraction of its rating.",
    ),
    ParameterBound(
        "conversion_noise_pct",
        0.05,
        1.5,
        BoundScale.LOG,
        "%",
        "Measurement noise on the conversion analyser. Analysers are noisier than thermocouples, "
        "which is part of why the agitator's power is worth having.",
    ),
    ParameterBound(
        "temperature_gain",
        0.5,
        6.0,
        BoundScale.LOG,
        "K/K",
        "Proportional gain of the outer temperature loop, which asks the jacket for degrees "
        "rather than percent.",
    ),
    ParameterBound(
        "temperature_integral_s",
        300.0,
        2400.0,
        BoundScale.LOG,
        "s",
        "Integral time of the outer loop. Long, because a vessel full of liquid is slow.",
    ),
    ParameterBound(
        "jacket_gain",
        1.0,
        12.0,
        BoundScale.LOG,
        "%/K",
        "Proportional gain of the inner jacket loop.",
    ),
    ParameterBound(
        "jacket_integral_s",
        30.0,
        400.0,
        BoundScale.LOG,
        "s",
        "Integral time of the inner loop. Much shorter than the outer one, which is what makes "
        "the cascade stable rather than two loops fighting.",
    ),
    ParameterBound(
        "jacket_bias_pct",
        20.0,
        70.0,
        BoundScale.LINEAR,
        "%",
        "Service valve position the inner loop starts from before its own terms.",
    ),
    ParameterBound(
        "scan_period_s",
        5,
        60,
        BoundScale.INTEGER,
        "s",
        "How often the SCADA system polls every register block.",
    ),
    ParameterBound(
        "event_gap_low_steps",
        40,
        400,
        BoundScale.INTEGER,
        "samples",
        "Shortest quiet stretch between two benign events.",
    ),
    ParameterBound(
        "event_gap_span_steps",
        200,
        2000,
        BoundScale.INTEGER,
        "samples",
        "How much longer the longest quiet stretch may be than the shortest.",
    ),
    ParameterBound(
        "hold_extension",
        0.1,
        0.8,
        BoundScale.LINEAR,
        "",
        "How much longer an extended hold runs than the recipe's default.",
    ),
)
"""Everything the `batch_mix` family varies, rendered into ``docs/sim/README.md``."""


class BatchMixFamily(PlantFamily):
    """Parallel batch trains: the same recipe at different scales, rates and tunings."""

    @property
    def family_id(self) -> str:
        """The identifier this family is drawn by."""
        return "batch_mix"

    @property
    def label(self) -> str:
        """Human-readable name."""
        return "Parallel batch reactor trains"

    @property
    def process(self) -> str:
        """The physics every plant from this family runs on."""
        return BATCH_MIX_PROCESS

    @property
    def industry(self) -> str:
        """The sector this process belongs to."""
        return "batch chemistry"

    @property
    def summary(self) -> str:
        """What the process does, for a reader who is not an engineer."""
        return (
            "One or more reactor trains, each stepping through the same recipe: fill, heat, "
            "react, empty, wait, and start again. Nothing here holds an operating point, so the "
            "same temperature is ordinary at one step and impossible at another, and the trains "
            "are deliberately not in step with one another."
        )

    def bounds(self) -> tuple[ParameterBound, ...]:
        """Return everything this family varies, and the range it varies it over."""
        return BATCH_MIX_BOUNDS

    def draw(self, master_seed: int) -> PlantSpec:
        """Draw one set of batch trains.

        Args:
            master_seed: Seeds every draw below.

        Returns:
            The drawn plant, as a valid spec.
        """
        streams = self.streams(master_seed)
        limits = self.bounds_by_name()
        structure = streams.draw("structure")
        sizing = streams.draw("sizing")
        tuning = streams.draw("tuning")
        instruments = streams.draw("instruments")
        naming = streams.draw("naming")
        events = streams.draw("disturbance")

        trains = round(bounded(structure, limits, "trains"))
        parameters = _parameters(sizing, tuning, instruments, limits, trains)
        scheme = draw_naming_scheme(naming, _PREFIXES)
        tags = render_tags(scheme, _positions(trains))

        return PlantSpec(
            plant_id=f"batch-mix-{master_seed}",
            label=f"Batch reactor plant, {trains} train(s)",
            industry=self.industry,
            summary=self.summary,
            model_source=(
                f"Drawn by phos.synth.families from the {self.family_id} family at master seed "
                f"{master_seed}. A model of a batch process built from an inventory balance, an "
                "energy balance across a jacketed wall, an Arrhenius conversion rate and a "
                "measurable-condition phase machine. Not a model of any particular reactor and "
                "not validated against one."
            ),
            process=self.process,
            parameters=parameters,
            units=_units(trains),
            signals=_signals(parameters, trains, tags),
            components=_components(trains, tags),
            connections=_connections(trains),
            controllers=_controllers(parameters, trains, tags),
            couplings=_couplings(trains, tags),
            control_network=modbus_network(
                poll_interval_seconds=parameters["scan_period_s"],
                subnet="10.8",
                per_plc=_register_plan(trains, tags),
            ),
            write_authority=operator_authority(tags, (TEMPERATURE_SETPOINT,)),
            disturbance=_disturbance(events, limits, parameters, trains, tags),
            roles=roles_from_tags(tags),
        )


def _parameters(
    sizing: StreamDraw,
    tuning: StreamDraw,
    instruments: StreamDraw,
    limits: Mapping[str, ParameterBound],
    trains: int,
) -> dict[str, float]:
    """Draw the vessels, the recipe, the tuning and the instruments."""
    charge = bounded(sizing, limits, "full_charge_kg")
    charge_minutes = bounded(sizing, limits, "charge_minutes")
    discharge_minutes = bounded(sizing, limits, "discharge_minutes")
    heat_capacity = bounded(sizing, limits, "heat_capacity_kj_per_kg_k")
    thermal_fraction = bounded(sizing, limits, "vessel_thermal_fraction")
    reaction_temp = bounded(sizing, limits, "reaction_temp_c")
    approach = bounded(sizing, limits, "jacket_approach_c")
    activation = bounded(sizing, limits, "arrhenius_temperature_k")
    half_life_minutes = bounded(sizing, limits, "reaction_half_life_minutes")
    headroom = bounded(sizing, limits, "temperature_headroom")
    idle_minutes = bounded(sizing, limits, "idle_minutes")
    hold_minutes = bounded(sizing, limits, "hold_minutes")
    rated_rpm = bounded(sizing, limits, "agitator_rated_rpm")
    agitator_rated = bounded(sizing, limits, "agitator_rated_kw")
    base_fraction = bounded(sizing, limits, "agitator_base_fraction")
    idle_fraction = bounded(sizing, limits, "agitator_idle_fraction")
    stagger_fraction = bounded(sizing, limits, "stagger_fraction")

    # The prefactor that gives the drawn half-life at the drawn reaction temperature. Inverting
    # the Arrhenius form here rather than drawing the prefactor is what keeps the reaction on a
    # human timescale: a usable rate needs a prefactor spanning many orders of magnitude, so
    # drawn directly it almost never lands in one.
    rate_per_second = math.log(2.0) / (half_life_minutes * 60.0)
    prefactor = rate_per_second * math.exp(activation / (reaction_temp + 273.15))

    return {
        "trains": float(trains),
        "full_charge_kg": charge,
        "charge_minutes": charge_minutes,
        "feed_kgph": charge / (charge_minutes / 60.0),
        "discharge_minutes": discharge_minutes,
        "discharge_kgph": charge / (discharge_minutes / 60.0),
        "heat_capacity_kj_per_kg_k": heat_capacity,
        "vessel_thermal_fraction": thermal_fraction,
        "vessel_thermal_kg": charge * thermal_fraction,
        "wall_ua_kw_per_k": bounded(sizing, limits, "wall_ua_kw_per_k"),
        "reaction_enthalpy_kj_per_kg": bounded(sizing, limits, "reaction_enthalpy_kj_per_kg"),
        "arrhenius_temperature_k": activation,
        "reaction_half_life_minutes": half_life_minutes,
        "arrhenius_prefactor": prefactor,
        "jacket_tau_s": bounded(sizing, limits, "jacket_tau_s"),
        "jacket_cold_c": bounded(sizing, limits, "jacket_cold_c"),
        "jacket_approach_c": approach,
        "jacket_hot_c": reaction_temp + approach,
        "feed_temp_c": bounded(sizing, limits, "feed_temp_c"),
        "reaction_temp_c": reaction_temp,
        "temperature_headroom": headroom,
        "temperature_span_c": reaction_temp * headroom,
        "idle_minutes": idle_minutes,
        "idle_seconds": idle_minutes * 60.0,
        "hold_minutes": hold_minutes,
        "hold_seconds": hold_minutes * 60.0,
        "stagger_fraction": stagger_fraction,
        "stagger_seconds": idle_minutes * 60.0 * stagger_fraction,
        "conversion_target_pct": bounded(sizing, limits, "conversion_target_pct"),
        "arrival_margin_c": bounded(sizing, limits, "arrival_margin_c"),
        "agitator_rated_kw": agitator_rated,
        "agitator_base_fraction": base_fraction,
        "agitator_base_kw": agitator_rated * base_fraction,
        "agitator_rated_rpm": rated_rpm,
        "agitator_idle_fraction": idle_fraction,
        "agitator_idle_rpm": rated_rpm * idle_fraction,
        "viscosity_per_conversion": bounded(sizing, limits, "viscosity_per_conversion"),
        "temperature_gain": bounded(tuning, limits, "temperature_gain"),
        "temperature_integral_s": bounded(tuning, limits, "temperature_integral_s"),
        "jacket_gain": bounded(tuning, limits, "jacket_gain"),
        "jacket_integral_s": bounded(tuning, limits, "jacket_integral_s"),
        "jacket_bias_pct": bounded(tuning, limits, "jacket_bias_pct"),
        "temperature_noise_c": bounded(instruments, limits, "temperature_noise_c"),
        "temperature_drift_c": bounded(instruments, limits, "temperature_drift_c"),
        "level_noise_pct": bounded(instruments, limits, "level_noise_pct"),
        "power_noise_fraction": bounded(instruments, limits, "power_noise_fraction"),
        "conversion_noise_pct": bounded(instruments, limits, "conversion_noise_pct"),
        "scan_period_s": bounded(instruments, limits, "scan_period_s"),
    }


def _positions(trains: int) -> tuple[tuple[RolePosition, str], ...]:
    """Return every role position this plant has, with the unit its signal carries."""
    positions: list[tuple[RolePosition, str]] = []
    for train in range(trains):
        positions.append(((PHASE, train, 0), ""))
        positions.append(((CHARGE, train, 0), "pct"))
        positions.append(((TEMPERATURE, train, 0), "degC"))
        positions.append(((TEMPERATURE_SETPOINT, train, 0), "degC"))
        positions.append(((CONVERSION, train, 0), "pct"))
        positions.append(((JACKET_TEMPERATURE, train, 0), "degC"))
        positions.append(((DUTY, train, 0), "pct"))
        positions.append(((FEED_VALVE, train, 0), "pct"))
        positions.append(((AGITATOR_SPEED, train, 0), "rpm"))
        positions.append(((AGITATOR_POWER, train, 0), "kW"))
    return tuple(positions)


def reactor_unit(train: int) -> str:
    """Return the physical unit identifier one train's vessel instruments sit on."""
    return f"reactor{train + 1}"


def services_unit(train: int) -> str:
    """Return the physical unit identifier one train's jacket, feed and agitator sit on."""
    return f"services{train + 1}"


def _units(trains: int) -> tuple[PhysicalUnit, ...]:
    """Return two physical units per train: the vessel, and everything serving it."""
    units: list[PhysicalUnit] = []
    for train in range(trains):
        units.append(PhysicalUnit(unit_id=reactor_unit(train), label=f"Train {train + 1} reactor"))
        units.append(
            PhysicalUnit(
                unit_id=services_unit(train), label=f"Train {train + 1} jacket, feed and agitator"
            )
        )
    return tuple(units)


def _signals(
    parameters: Mapping[str, float], trains: int, tags: Mapping[RolePosition, str]
) -> tuple[SignalSpec, ...]:
    """Return the instruments, with the spans and noise this plant was drawn with."""
    span = parameters["temperature_span_c"]
    rated_kw = parameters["agitator_rated_kw"]
    power_noise = parameters["power_noise_fraction"] * rated_kw
    signals: list[SignalSpec] = []
    for train in range(trains):
        vessel = reactor_unit(train)
        services = services_unit(train)
        signals.append(
            SignalSpec(
                key=tags[(PHASE, train, 0)],
                label=f"Train {train + 1} recipe step",
                unit="step",
                kind=SignalKind.SENSOR,
                physical_unit=vessel,
                low=0.0,
                high=float(max(Phase)) + 1.0,
                noise_stddev=0.0,
            )
        )
        signals.append(
            SignalSpec(
                key=tags[(CHARGE, train, 0)],
                label=f"Train {train + 1} vessel level",
                unit="%",
                kind=SignalKind.SENSOR,
                physical_unit=vessel,
                low=0.0,
                high=100.0,
                noise_stddev=parameters["level_noise_pct"],
                drift_amplitude=parameters["level_noise_pct"] * 0.5,
            )
        )
        signals.append(
            SignalSpec(
                key=tags[(TEMPERATURE, train, 0)],
                label=f"Train {train + 1} batch temperature",
                unit="degC",
                kind=SignalKind.SENSOR,
                physical_unit=vessel,
                low=0.0,
                high=span,
                noise_stddev=parameters["temperature_noise_c"],
                drift_amplitude=parameters["temperature_drift_c"],
            )
        )
        signals.append(
            SignalSpec(
                key=tags[(CONVERSION, train, 0)],
                label=f"Train {train + 1} conversion",
                unit="%",
                kind=SignalKind.SENSOR,
                physical_unit=vessel,
                low=0.0,
                high=100.0,
                noise_stddev=parameters["conversion_noise_pct"],
                drift_amplitude=parameters["conversion_noise_pct"] * 0.5,
            )
        )
        signals.append(
            SignalSpec(
                key=tags[(TEMPERATURE_SETPOINT, train, 0)],
                label=f"Train {train + 1} reaction temperature setpoint",
                unit="degC",
                kind=SignalKind.SETPOINT,
                physical_unit=vessel,
                low=0.0,
                high=span,
                noise_stddev=0.0,
            )
        )
        signals.append(
            SignalSpec(
                key=tags[(JACKET_TEMPERATURE, train, 0)],
                label=f"Train {train + 1} jacket temperature",
                unit="degC",
                kind=SignalKind.SENSOR,
                physical_unit=services,
                low=0.0,
                high=span,
                noise_stddev=parameters["temperature_noise_c"],
                drift_amplitude=parameters["temperature_drift_c"],
            )
        )
        signals.append(
            SignalSpec(
                key=tags[(DUTY, train, 0)],
                label=f"Train {train + 1} jacket service valve",
                unit="%",
                kind=SignalKind.ACTUATOR,
                physical_unit=services,
                low=0.0,
                high=100.0,
                noise_stddev=parameters["power_noise_fraction"] * 10.0,
            )
        )
        signals.append(
            SignalSpec(
                key=tags[(FEED_VALVE, train, 0)],
                label=f"Train {train + 1} feed valve",
                unit="%",
                kind=SignalKind.ACTUATOR,
                physical_unit=services,
                low=0.0,
                high=100.0,
                noise_stddev=parameters["power_noise_fraction"] * 10.0,
            )
        )
        signals.append(
            SignalSpec(
                key=tags[(AGITATOR_SPEED, train, 0)],
                label=f"Train {train + 1} agitator speed",
                unit="rpm",
                kind=SignalKind.ACTUATOR,
                physical_unit=services,
                low=0.0,
                high=parameters["agitator_rated_rpm"] * 1.2,
                noise_stddev=parameters["power_noise_fraction"] * parameters["agitator_rated_rpm"],
            )
        )
        signals.append(
            SignalSpec(
                key=tags[(AGITATOR_POWER, train, 0)],
                label=f"Train {train + 1} agitator power",
                unit="kW",
                kind=SignalKind.SENSOR,
                physical_unit=services,
                low=0.0,
                high=rated_kw * 5.0,
                noise_stddev=power_noise,
                drift_amplitude=power_noise * 0.4,
            )
        )
    return tuple(signals)


def _components(trains: int, tags: Mapping[RolePosition, str]) -> tuple[Component, ...]:
    """Return what the plant is made of, with every signal owned exactly once."""
    components: list[Component] = []
    for train in range(trains):
        vessel = reactor_unit(train)
        services = services_unit(train)
        components.append(
            Component(
                component_id=f"reactor_t{train}",
                kind=ComponentKind.REACTOR,
                label=f"Train {train + 1} reactor",
                physical_unit=vessel,
                signals=(
                    tags[(PHASE, train, 0)],
                    tags[(CHARGE, train, 0)],
                    tags[(TEMPERATURE, train, 0)],
                    tags[(CONVERSION, train, 0)],
                ),
                description=(
                    "The vessel the batch happens in. It never settles: it fills, heats, reacts "
                    "and empties, so what counts as normal depends on which step it is on."
                ),
            )
        )
        components.append(
            Component(
                component_id=f"temp_loop_t{train}",
                kind=ComponentKind.CONTROLLER,
                label=f"Train {train + 1} temperature target",
                physical_unit=vessel,
                signals=(tags[(TEMPERATURE_SETPOINT, train, 0)],),
                description="The temperature the recipe calls for while the batch reacts.",
            )
        )
        components.append(
            Component(
                component_id=f"jacket_t{train}",
                kind=ComponentKind.EXCHANGER,
                label=f"Train {train + 1} jacket",
                physical_unit=services,
                signals=(tags[(JACKET_TEMPERATURE, train, 0)],),
                description=(
                    "A space around the vessel with hot or cold service in it. The only way heat "
                    "gets into or out of the batch."
                ),
            )
        )
        components.append(
            Component(
                component_id=f"jacket_valve_t{train}",
                kind=ComponentKind.VALVE,
                label=f"Train {train + 1} service valve",
                physical_unit=services,
                signals=(tags[(DUTY, train, 0)],),
                description="Blends hot and cold utility into the jacket.",
            )
        )
        components.append(
            Component(
                component_id=f"feed_valve_t{train}",
                kind=ComponentKind.VALVE,
                label=f"Train {train + 1} feed valve",
                physical_unit=services,
                signals=(tags[(FEED_VALVE, train, 0)],),
                description="Open while charging and shut the rest of the time. Nothing between.",
            )
        )
        components.append(
            Component(
                component_id=f"agitator_t{train}",
                kind=ComponentKind.MIXER,
                label=f"Train {train + 1} agitator",
                physical_unit=services,
                signals=(
                    tags[(AGITATOR_SPEED, train, 0)],
                    tags[(AGITATOR_POWER, train, 0)],
                ),
                description=(
                    "Stirs the batch. Its power draw says something no other instrument does: the "
                    "mixture thickens as it converts, and the drive feels it."
                ),
            )
        )
    return tuple(components)


def _connections(trains: int) -> tuple[Connection, ...]:
    """Return which way the material and the heat go."""
    connections: list[Connection] = []
    for train in range(trains):
        connections.append(
            Connection(
                source=f"feed_valve_t{train}",
                target=f"reactor_t{train}",
                medium="material",
                label="reagent into the vessel",
            )
        )
        connections.append(
            Connection(
                source=f"jacket_valve_t{train}",
                target=f"jacket_t{train}",
                medium="utility",
                label="service into the jacket",
            )
        )
        connections.append(
            Connection(
                source=f"jacket_t{train}",
                target=f"reactor_t{train}",
                medium="heat",
                label="heat across the vessel wall",
            )
        )
        connections.append(
            Connection(
                source=f"agitator_t{train}",
                target=f"reactor_t{train}",
                medium="shaft",
                label="stirring, and the heat it adds",
            )
        )
        connections.append(
            Connection(
                source=f"temp_loop_t{train}",
                target=f"jacket_valve_t{train}",
                medium="signal",
                label="temperature target drives the jacket through the cascade",
            )
        )
    return tuple(connections)


def _controllers(
    parameters: Mapping[str, float], trains: int, tags: Mapping[RolePosition, str]
) -> tuple[ControllerSpec, ...]:
    """Return a two-loop cascade per train, on the tuning this plant was drawn with."""
    controllers: list[ControllerSpec] = []
    for train in range(trains):
        controllers.append(
            ControllerSpec(
                controller_id=temperature_loop_id(train),
                kind=ControllerKind.PI,
                measurement=tags[(TEMPERATURE, train, 0)],
                setpoint=tags[(TEMPERATURE_SETPOINT, train, 0)],
                output=jacket_loop_id(train),
                gain=parameters["temperature_gain"],
                integral_time_seconds=parameters["temperature_integral_s"],
                low=parameters["jacket_cold_c"],
                high=parameters["jacket_hot_c"],
                description=(
                    "The outer half of a cascade. It touches no valve: it decides what "
                    "temperature the jacket should be at, in degrees."
                ),
            )
        )
        controllers.append(
            ControllerSpec(
                controller_id=jacket_loop_id(train),
                kind=ControllerKind.PI,
                measurement=tags[(JACKET_TEMPERATURE, train, 0)],
                output=tags[(DUTY, train, 0)],
                gain=parameters["jacket_gain"],
                integral_time_seconds=parameters["jacket_integral_s"],
                low=0.0,
                high=100.0,
                bias=parameters["jacket_bias_pct"],
                description=(
                    "The inner half. Holds the jacket at whatever the outer loop asked for, "
                    "which outside the heat and react steps is a fixed service temperature."
                ),
            )
        )
    return tuple(controllers)


def _couplings(trains: int, tags: Mapping[RolePosition, str]) -> tuple[Coupling, ...]:
    """Return the plant's claim about what makes its signals related."""
    couplings: list[Coupling] = []
    for train in range(trains):
        couplings.append(
            Coupling(
                driven=tags[(CHARGE, train, 0)],
                drivers=(tags[(FEED_VALVE, train, 0)], tags[(PHASE, train, 0)]),
                kind=CouplingKind.INTEGRATION,
                relation="level is the running total of what was charged less what was drawn off",
            )
        )
        couplings.append(
            Coupling(
                driven=tags[(TEMPERATURE, train, 0)],
                drivers=(
                    tags[(JACKET_TEMPERATURE, train, 0)],
                    tags[(CHARGE, train, 0)],
                    tags[(CONVERSION, train, 0)],
                ),
                kind=CouplingKind.INTEGRATION,
                relation=(
                    "batch temperature is the running balance of heat across the jacket wall, "
                    "cold reagent mixing in, and the reaction's own heat"
                ),
            )
        )
        couplings.append(
            Coupling(
                driven=tags[(CONVERSION, train, 0)],
                drivers=(tags[(TEMPERATURE, train, 0)],),
                kind=CouplingKind.INTEGRATION,
                relation="conversion accumulates at a rate exponential in batch temperature",
            )
        )
        couplings.append(
            Coupling(
                driven=tags[(AGITATOR_POWER, train, 0)],
                drivers=(
                    tags[(AGITATOR_SPEED, train, 0)],
                    tags[(CHARGE, train, 0)],
                    tags[(CONVERSION, train, 0)],
                ),
                kind=CouplingKind.ALGEBRAIC,
                relation=(
                    "agitator power is the cube of speed, by how full the vessel is, by how much "
                    "the batch has thickened"
                ),
            )
        )
        couplings.append(
            Coupling(
                driven=tags[(JACKET_TEMPERATURE, train, 0)],
                drivers=(tags[(DUTY, train, 0)],),
                kind=CouplingKind.LAG,
                relation="jacket temperature follows its service valve with a lag",
            )
        )
        couplings.append(
            Coupling(
                driven=tags[(DUTY, train, 0)],
                drivers=(
                    tags[(JACKET_TEMPERATURE, train, 0)],
                    tags[(TEMPERATURE, train, 0)],
                    tags[(TEMPERATURE_SETPOINT, train, 0)],
                ),
                kind=CouplingKind.CONTROL,
                relation="a cascade holds the batch at setpoint by holding the jacket somewhere",
            )
        )
    return tuple(couplings)


def _register_plan(
    trains: int, tags: Mapping[RolePosition, str]
) -> tuple[tuple[list[str], list[str]], ...]:
    """Return what each train's PLC exposes read-only, and what an operator may write."""
    plan: list[tuple[list[str], list[str]]] = []
    for train in range(trains):
        readable = [
            tags[(PHASE, train, 0)],
            tags[(CHARGE, train, 0)],
            tags[(TEMPERATURE, train, 0)],
            tags[(CONVERSION, train, 0)],
            tags[(JACKET_TEMPERATURE, train, 0)],
            tags[(DUTY, train, 0)],
            tags[(FEED_VALVE, train, 0)],
            tags[(AGITATOR_SPEED, train, 0)],
            tags[(AGITATOR_POWER, train, 0)],
        ]
        plan.append((readable, [tags[(TEMPERATURE_SETPOINT, train, 0)]]))
    return tuple(plan)


def _disturbance(
    draw: StreamDraw,
    limits: Mapping[str, ParameterBound],
    parameters: Mapping[str, float],
    trains: int,
    tags: Mapping[RolePosition, str],
) -> DisturbanceSpec:
    """Draw what normally happens to this plant, and how far apart."""
    gap_low = round(bounded(draw, limits, "event_gap_low_steps"))
    gap_high = gap_low + round(bounded(draw, limits, "event_gap_span_steps"))
    extension = bounded(draw, limits, "hold_extension")
    reaction = parameters["reaction_temp_c"]

    plans: list[EventPlanSpec] = [
        EventPlanSpec(
            kind=HOLD_CHANGE,
            label="The react step is held longer than the recipe's default",
            duration_steps=200,
            parameter_ranges={"hold_extension": (extension * 0.3, extension)},
            detail="react hold extended by a fraction of:",
        )
    ]
    for train in range(trains):
        target = tags[(TEMPERATURE_SETPOINT, train, 0)]
        plans.append(
            EventPlanSpec(
                kind=RECIPE_CHANGE,
                label=f"Operator changes train {train + 1}'s reaction temperature",
                duration_steps=0,
                writes=(target,),
                parameter_ranges={target: (reaction * 0.93, reaction * 1.07)},
                detail=f"new reaction temperature on train {train + 1}:",
            )
        )
    return DisturbanceSpec(
        event_plans=tuple(plans),
        first_start_floor=30,
        first_start_divisor=12,
        gap_steps=(gap_low, gap_high),
    )


register_family(BatchMixFamily())

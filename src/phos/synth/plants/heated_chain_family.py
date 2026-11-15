"""The `hybrid` family: how a seed becomes one heated tank chain.

PART R2's fifth family and the composed one. Its bounds are mostly the union of `level_flow`'s and
`thermal`'s, which is the point — a hybrid is not a third kind of plant, it is two kinds of plant
in one cabinet, and the parameters that describe it are the parameters that describe each half.

Two things are different from either parent, and both follow from the vessels being the same
vessels:

* ``heater_rated_kw`` is sized from the duty at the *level setpoint*, not at a fixed holdup,
  because the holdup is a thing the other loop is moving.
* ``density_kg_per_m3`` appears, which neither parent needs. `level_flow` works in volume and
  never asks what the liquid weighs; `thermal` works in mass and never asks how deep it is. A
  plant that is both has to convert between them, and the conversion is a property of the liquid.
"""

from collections.abc import Mapping
from typing import Final

from phos.synth.families import BoundScale, ParameterBound, PlantFamily, bounded, register_family
from phos.synth.plant import Coupling, CouplingKind, SignalKind, SignalSpec
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
from phos.synth.plants.heated_chain import (
    AMBIENT,
    COLD_FEED,
    DEMAND_SURGE,
    DUTY,
    HEATED_CHAIN_PROCESS,
    INFLOW,
    LEVEL,
    LEVEL_SETPOINT,
    OUTFLOW,
    PUMP_SPEED,
    TEMPERATURE,
    TEMPERATURE_SETPOINT,
    level_loop_id,
    temperature_loop_id,
)
from phos.synth.plants.spec_build import (
    RolePosition,
    draw_naming_scheme,
    modbus_network,
    operator_authority,
    render_tags,
    roles_from_tags,
    stage_unit_id,
    stage_units,
)
from phos.synth.randomise import StreamDraw

__all__ = ["HYBRID_BOUNDS", "HybridFamily"]

_PREFIXES: Final = ("", "HX", "TRANSFER", "HTF", "T")
_UTILITY_UNIT: Final = "utility"
_LEVEL_SETPOINT_CHANGE: Final = "level_setpoint_change"
_TEMPERATURE_SETPOINT_CHANGE: Final = "temperature_setpoint_change"

HYBRID_BOUNDS: Final = (
    ParameterBound(
        "trains", 1, 2, BoundScale.INTEGER, "", "How many heated chains run in parallel."
    ),
    ParameterBound(
        "stages",
        2,
        3,
        BoundScale.INTEGER,
        "",
        "How many heated tanks each chain is made of. Smaller than the unheated family's range "
        "because every stage here carries two loops and two transmitters.",
    ),
    ParameterBound(
        "tank_area_m2",
        10.0,
        150.0,
        BoundScale.LOG,
        "m2",
        "Plan area of every tank. With the level it is the volume, and with the density and the "
        "specific heat it is the thermal mass — which is why this one parameter sets both how "
        "fast the level moves and how fast the temperature does.",
    ),
    ParameterBound(
        "level_span_m",
        2.0,
        7.0,
        BoundScale.LINEAR,
        "m",
        "Height of every tank, and the calibrated span of its level transmitter.",
    ),
    ParameterBound(
        "level_setpoint_fraction",
        0.35,
        0.70,
        BoundScale.LINEAR,
        "",
        "Where in the tank the level loops hold, as a fraction of its height. It also decides the "
        "holdup the heaters are sized against.",
    ),
    ParameterBound(
        "pump_margin",
        1.3,
        3.0,
        BoundScale.LINEAR,
        "",
        "How much more flow each pump can deliver than its train's share of mean demand.",
    ),
    ParameterBound(
        "flow_tau_s",
        10.0,
        180.0,
        BoundScale.LOG,
        "s",
        "How long a pump takes to reach a new flow after its speed changes.",
    ),
    ParameterBound(
        "demand_base_m3ph",
        10.0,
        150.0,
        BoundScale.LOG,
        "m3/h",
        "Mean draw at the end of the chain.",
    ),
    ParameterBound(
        "demand_daily_m3ph",
        2.0,
        40.0,
        BoundScale.LOG,
        "m3/h",
        "Amplitude of the once-a-day swing in that draw.",
    ),
    ParameterBound(
        "demand_floor_fraction",
        0.1,
        0.5,
        BoundScale.LINEAR,
        "",
        "Fraction of mean draw the demand never falls below.",
    ),
    ParameterBound(
        "density_kg_per_m3",
        700.0,
        1050.0,
        BoundScale.LINEAR,
        "kg/m3",
        "Density of the liquid. Neither parent family needs it — one works in volume and the "
        "other in mass — and a plant that is both has to convert between them.",
    ),
    ParameterBound(
        "heat_capacity_kj_per_kg_k",
        1.8,
        4.2,
        BoundScale.LINEAR,
        "kJ/kg/K",
        "Specific heat of the liquid.",
    ),
    ParameterBound(
        "heater_margin",
        1.3,
        2.8,
        BoundScale.LINEAR,
        "",
        "How much more heat each heater can put in than the duty its tank needs at the level "
        "setpoint. Sized at the setpoint rather than at a fixed holdup, because the holdup is "
        "something the other loop is moving.",
    ),
    ParameterBound(
        "ua_ambient_kw_per_k",
        0.02,
        1.5,
        BoundScale.LOG,
        "kW/K",
        "How fast each tank loses heat to the room, per degree above it.",
    ),
    ParameterBound(
        "feed_temp_c",
        4.0,
        30.0,
        BoundScale.LINEAR,
        "degC",
        "Temperature of what arrives at the front of the chain.",
    ),
    ParameterBound(
        "ambient_base_c",
        2.0,
        28.0,
        BoundScale.LINEAR,
        "degC",
        "Mean temperature of the room or yard the tanks stand in.",
    ),
    ParameterBound(
        "ambient_daily_c",
        1.0,
        12.0,
        BoundScale.LINEAR,
        "degC",
        "How far the room's temperature swings over a day.",
    ),
    ParameterBound(
        "temperature_setpoint_c",
        35.0,
        95.0,
        BoundScale.LINEAR,
        "degC",
        "Temperature every tank in the chain is held at.",
    ),
    ParameterBound(
        "temperature_headroom",
        1.3,
        2.0,
        BoundScale.LINEAR,
        "",
        "How far above the setpoint the temperature transmitters are calibrated.",
    ),
    ParameterBound(
        "level_gain",
        4.0,
        40.0,
        BoundScale.LOG,
        "%/m",
        "Proportional gain of every level loop.",
    ),
    ParameterBound(
        "level_integral_s",
        240.0,
        2400.0,
        BoundScale.LOG,
        "s",
        "Integral time of every level loop.",
    ),
    ParameterBound(
        "pump_bias_pct",
        15.0,
        60.0,
        BoundScale.LINEAR,
        "%",
        "Pump speed the level loop starts from before its own terms.",
    ),
    ParameterBound(
        "temperature_gain",
        0.8,
        15.0,
        BoundScale.LOG,
        "%/K",
        "Proportional gain of every temperature loop. Harder to choose here than in the unheated "
        "family: the loop's effective gain changes with the level, so a tuning that is right at "
        "the setpoint is brisk when the tank is low.",
    ),
    ParameterBound(
        "temperature_integral_s",
        120.0,
        1800.0,
        BoundScale.LOG,
        "s",
        "Integral time of every temperature loop.",
    ),
    ParameterBound(
        "duty_bias_pct",
        10.0,
        55.0,
        BoundScale.LINEAR,
        "%",
        "Heater duty the temperature loop starts from before its own terms.",
    ),
    ParameterBound(
        "flow_meter_chance",
        0.4,
        1.0,
        BoundScale.LINEAR,
        "",
        "How likely each stage is to have a flow meter on its inlet.",
    ),
    ParameterBound(
        "level_noise_m",
        0.002,
        0.05,
        BoundScale.LOG,
        "m",
        "Measurement noise on every level transmitter.",
    ),
    ParameterBound(
        "level_drift_m",
        0.001,
        0.04,
        BoundScale.LOG,
        "m",
        "Bound on each level transmitter's slow drift. Worth watching in this family in "
        "particular: a drifting level transmitter moves the thermal mass the temperature loop is "
        "working against, so it shows up twice.",
    ),
    ParameterBound(
        "temperature_noise_c",
        0.01,
        0.7,
        BoundScale.LOG,
        "degC",
        "Measurement noise on every temperature transmitter.",
    ),
    ParameterBound(
        "temperature_drift_c",
        0.005,
        0.4,
        BoundScale.LOG,
        "degC",
        "Bound on each temperature transmitter's slow drift.",
    ),
    ParameterBound(
        "flow_noise_fraction",
        0.001,
        0.02,
        BoundScale.LOG,
        "",
        "Measurement noise on every flow meter, as a fraction of a pump's full flow.",
    ),
    ParameterBound(
        "actuator_noise_pct",
        0.01,
        0.5,
        BoundScale.LOG,
        "%",
        "Measurement noise on reported pump speed and heater duty.",
    ),
    ParameterBound(
        "scan_period_s",
        5,
        90,
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
        "surge_fraction",
        0.08,
        0.40,
        BoundScale.LINEAR,
        "",
        "How much a demand surge raises the draw while it lasts.",
    ),
    ParameterBound(
        "surge_steps",
        30,
        400,
        BoundScale.INTEGER,
        "samples",
        "How long a demand surge lasts.",
    ),
    ParameterBound(
        "feed_drop_c",
        2.0,
        15.0,
        BoundScale.LINEAR,
        "degC",
        "How much colder the feed turns during a cold-feed excursion.",
    ),
    ParameterBound(
        "feed_drop_steps",
        40,
        400,
        BoundScale.INTEGER,
        "samples",
        "How long a cold-feed excursion lasts.",
    ),
)
"""Everything the `hybrid` family varies, rendered into ``docs/sim/README.md``."""


class HybridFamily(PlantFamily):
    """Heated tank chains: two processes in one plant, with the level as the thermal mass."""

    @property
    def family_id(self) -> str:
        """The identifier this family is drawn by."""
        return "hybrid"

    @property
    def label(self) -> str:
        """Human-readable name."""
        return "Heated tank chain"

    @property
    def process(self) -> str:
        """The physics every plant from this family runs on."""
        return HEATED_CHAIN_PROCESS

    @property
    def industry(self) -> str:
        """The sector this process belongs to."""
        return "liquid handling and process heating"

    @property
    def summary(self) -> str:
        """What the process does, for a reader who is not an engineer."""
        return (
            "A chain of tanks that are pumped full and heated at the same time, each with a level "
            "loop and a temperature loop. The two halves are not independent: how full a tank is "
            "decides how fast it warms, so moving a level setpoint changes how the temperature "
            "loop behaves."
        )

    def bounds(self) -> tuple[ParameterBound, ...]:
        """Return everything this family varies, and the range it varies it over."""
        return HYBRID_BOUNDS

    def draw(self, master_seed: int) -> PlantSpec:
        """Draw one heated tank chain.

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
        stages = round(bounded(structure, limits, "stages"))
        chance = bounded(structure, limits, "flow_meter_chance")
        metered = {
            (train, stage): structure.uniform(f"flow_meter_t{train}_s{stage}", 0.0, 1.0) < chance
            for train in range(trains)
            for stage in range(stages)
        }

        parameters = _parameters(sizing, tuning, instruments, limits, trains, stages)
        scheme = draw_naming_scheme(naming, _PREFIXES)
        tags = render_tags(scheme, _positions(trains, stages, metered))

        return PlantSpec(
            plant_id=f"heated-chain-{master_seed}",
            label=f"Heated tank chain, {trains} train(s) of {stages}",
            industry=self.industry,
            summary=self.summary,
            model_source=(
                f"Drawn by phos.synth.families from the {self.family_id} family at master seed "
                f"{master_seed}. A model of a heated transfer chain built from a volume balance "
                "and an energy balance on the same vessels, so that the holdup one loop controls "
                "is the thermal mass the other works against. Not a model of any particular "
                "plant and not validated against one."
            ),
            process=self.process,
            parameters=parameters,
            units=stage_units(
                trains, stages, label="tank", extra=((_UTILITY_UNIT, "Header, demand and ambient"),)
            ),
            signals=_signals(parameters, trains, stages, metered, tags),
            components=_components(trains, stages, metered, tags),
            connections=_connections(trains, stages),
            controllers=_controllers(parameters, trains, stages, tags),
            couplings=_couplings(trains, stages, metered, tags),
            control_network=modbus_network(
                poll_interval_seconds=parameters["scan_period_s"],
                subnet="10.10",
                per_plc=_register_plan(trains, stages, metered, tags),
            ),
            write_authority=operator_authority(tags, (LEVEL_SETPOINT, TEMPERATURE_SETPOINT)),
            disturbance=_disturbance(events, limits, parameters, trains, tags),
            roles=roles_from_tags(tags),
        )


def _parameters(
    sizing: StreamDraw,
    tuning: StreamDraw,
    instruments: StreamDraw,
    limits: Mapping[str, ParameterBound],
    trains: int,
    stages: int,
) -> dict[str, float]:
    """Draw the tanks, the liquid, the heaters, the tunings and the instruments."""
    area = bounded(sizing, limits, "tank_area_m2")
    span = bounded(sizing, limits, "level_span_m")
    fraction = bounded(sizing, limits, "level_setpoint_fraction")
    demand_base = bounded(sizing, limits, "demand_base_m3ph")
    pump_margin = bounded(sizing, limits, "pump_margin")
    floor_fraction = bounded(sizing, limits, "demand_floor_fraction")
    density = bounded(sizing, limits, "density_kg_per_m3")
    heat_capacity = bounded(sizing, limits, "heat_capacity_kj_per_kg_k")
    heater_margin = bounded(sizing, limits, "heater_margin")
    ua = bounded(sizing, limits, "ua_ambient_kw_per_k")
    feed = bounded(sizing, limits, "feed_temp_c")
    ambient = bounded(sizing, limits, "ambient_base_c")
    setpoint = bounded(sizing, limits, "temperature_setpoint_c")
    headroom = bounded(sizing, limits, "temperature_headroom")

    # The duty a tank needs at its level setpoint: raise its share of the stream from feed
    # temperature to setpoint, and replace what the walls lose. Sized at the setpoint because
    # that is where the level loop holds it.
    share = demand_base / trains
    required_kw = share * density / 3600.0 * heat_capacity * (setpoint - feed) + ua * (
        setpoint - ambient
    )
    return {
        "trains": float(trains),
        "stages": float(stages),
        "tank_area_m2": area,
        "level_span_m": span,
        "level_setpoint_fraction": fraction,
        "pump_margin": pump_margin,
        "max_pump_flow_m3ph": share * pump_margin,
        "flow_tau_s": bounded(sizing, limits, "flow_tau_s"),
        "demand_base_m3ph": demand_base,
        "demand_daily_m3ph": bounded(sizing, limits, "demand_daily_m3ph"),
        "demand_floor_fraction": floor_fraction,
        "demand_floor_m3ph": demand_base * floor_fraction,
        "density_kg_per_m3": density,
        "heat_capacity_kj_per_kg_k": heat_capacity,
        "heater_margin": heater_margin,
        "heater_rated_kw": max(required_kw, 0.5) * heater_margin,
        "ua_ambient_kw_per_k": ua,
        "feed_temp_c": feed,
        "ambient_base_c": ambient,
        "ambient_daily_c": bounded(sizing, limits, "ambient_daily_c"),
        "temperature_setpoint_c": setpoint,
        "temperature_headroom": headroom,
        "temperature_span_c": setpoint * headroom,
        "level_gain": bounded(tuning, limits, "level_gain"),
        "level_integral_s": bounded(tuning, limits, "level_integral_s"),
        "pump_bias_pct": bounded(tuning, limits, "pump_bias_pct"),
        "temperature_gain": bounded(tuning, limits, "temperature_gain"),
        "temperature_integral_s": bounded(tuning, limits, "temperature_integral_s"),
        "duty_bias_pct": bounded(tuning, limits, "duty_bias_pct"),
        "level_noise_m": bounded(instruments, limits, "level_noise_m"),
        "level_drift_m": bounded(instruments, limits, "level_drift_m"),
        "temperature_noise_c": bounded(instruments, limits, "temperature_noise_c"),
        "temperature_drift_c": bounded(instruments, limits, "temperature_drift_c"),
        "flow_noise_fraction": bounded(instruments, limits, "flow_noise_fraction"),
        "actuator_noise_pct": bounded(instruments, limits, "actuator_noise_pct"),
        "scan_period_s": bounded(instruments, limits, "scan_period_s"),
    }


def _positions(
    trains: int, stages: int, metered: Mapping[tuple[int, int], bool]
) -> tuple[tuple[RolePosition, str], ...]:
    """Return every role position this plant has, with the unit its signal carries."""
    positions: list[tuple[RolePosition, str]] = []
    for train in range(trains):
        for stage in range(stages):
            positions.append(((LEVEL, train, stage), "m"))
            positions.append(((LEVEL_SETPOINT, train, stage), "m"))
            positions.append(((PUMP_SPEED, train, stage), "pct"))
            positions.append(((TEMPERATURE, train, stage), "degC"))
            positions.append(((TEMPERATURE_SETPOINT, train, stage), "degC"))
            positions.append(((DUTY, train, stage), "pct"))
            if metered[(train, stage)]:
                positions.append(((INFLOW, train, stage), "m3/h"))
    positions.append(((OUTFLOW, 0, stages), "m3/h"))
    positions.append(((AMBIENT, 1, stages), "degC"))
    return tuple(positions)


def _signals(
    parameters: Mapping[str, float],
    trains: int,
    stages: int,
    metered: Mapping[tuple[int, int], bool],
    tags: Mapping[RolePosition, str],
) -> tuple[SignalSpec, ...]:
    """Return the instruments, with the spans and noise this plant was drawn with."""
    span = parameters["level_span_m"]
    temp_span = parameters["temperature_span_c"]
    full_flow = parameters["max_pump_flow_m3ph"]
    flow_noise = parameters["flow_noise_fraction"] * full_flow
    signals: list[SignalSpec] = []
    for train in range(trains):
        for stage in range(stages):
            unit = stage_unit_id(train, stage)
            signals.append(
                SignalSpec(
                    key=tags[(LEVEL, train, stage)],
                    label=f"Train {train + 1} tank {stage + 1} level",
                    unit="m",
                    kind=SignalKind.SENSOR,
                    physical_unit=unit,
                    low=0.0,
                    high=span,
                    noise_stddev=parameters["level_noise_m"],
                    drift_amplitude=parameters["level_drift_m"],
                )
            )
            signals.append(
                SignalSpec(
                    key=tags[(TEMPERATURE, train, stage)],
                    label=f"Train {train + 1} tank {stage + 1} temperature",
                    unit="degC",
                    kind=SignalKind.SENSOR,
                    physical_unit=unit,
                    low=0.0,
                    high=temp_span,
                    noise_stddev=parameters["temperature_noise_c"],
                    drift_amplitude=parameters["temperature_drift_c"],
                )
            )
            if metered[(train, stage)]:
                signals.append(
                    SignalSpec(
                        key=tags[(INFLOW, train, stage)],
                        label=f"Train {train + 1} tank {stage + 1} inflow",
                        unit="m3/h",
                        kind=SignalKind.SENSOR,
                        physical_unit=unit,
                        low=0.0,
                        high=full_flow * 1.25,
                        noise_stddev=flow_noise,
                        drift_amplitude=flow_noise * 0.5,
                    )
                )
            signals.append(
                SignalSpec(
                    key=tags[(PUMP_SPEED, train, stage)],
                    label=f"Train {train + 1} tank {stage + 1} pump speed",
                    unit="%",
                    kind=SignalKind.ACTUATOR,
                    physical_unit=unit,
                    low=0.0,
                    high=100.0,
                    noise_stddev=parameters["actuator_noise_pct"],
                )
            )
            signals.append(
                SignalSpec(
                    key=tags[(DUTY, train, stage)],
                    label=f"Train {train + 1} tank {stage + 1} heater duty",
                    unit="%",
                    kind=SignalKind.ACTUATOR,
                    physical_unit=unit,
                    low=0.0,
                    high=100.0,
                    noise_stddev=parameters["actuator_noise_pct"],
                )
            )
            signals.append(
                SignalSpec(
                    key=tags[(LEVEL_SETPOINT, train, stage)],
                    label=f"Train {train + 1} tank {stage + 1} level setpoint",
                    unit="m",
                    kind=SignalKind.SETPOINT,
                    physical_unit=unit,
                    low=0.0,
                    high=span,
                    noise_stddev=0.0,
                )
            )
            signals.append(
                SignalSpec(
                    key=tags[(TEMPERATURE_SETPOINT, train, stage)],
                    label=f"Train {train + 1} tank {stage + 1} temperature setpoint",
                    unit="degC",
                    kind=SignalKind.SETPOINT,
                    physical_unit=unit,
                    low=0.0,
                    high=temp_span,
                    noise_stddev=0.0,
                )
            )
    signals.append(
        SignalSpec(
            key=tags[(OUTFLOW, 0, stages)],
            label="Chain outflow to demand",
            unit="m3/h",
            kind=SignalKind.SENSOR,
            physical_unit=_UTILITY_UNIT,
            low=0.0,
            high=full_flow * trains * 1.5,
            noise_stddev=flow_noise,
            drift_amplitude=flow_noise * 0.5,
        )
    )
    signals.append(
        SignalSpec(
            key=tags[(AMBIENT, 1, stages)],
            label="Ambient temperature",
            unit="degC",
            kind=SignalKind.SENSOR,
            physical_unit=_UTILITY_UNIT,
            low=-25.0,
            high=55.0,
            noise_stddev=parameters["temperature_noise_c"],
            drift_amplitude=parameters["temperature_drift_c"],
        )
    )
    return tuple(signals)


def _components(
    trains: int,
    stages: int,
    metered: Mapping[tuple[int, int], bool],
    tags: Mapping[RolePosition, str],
) -> tuple[Component, ...]:
    """Return what the plant is made of, with every signal owned exactly once."""
    components: list[Component] = []
    for train in range(trains):
        for stage in range(stages):
            unit = stage_unit_id(train, stage)
            components.append(
                Component(
                    component_id=f"tank_t{train}_s{stage}",
                    kind=ComponentKind.TANK,
                    label=f"Train {train + 1} heated tank {stage + 1}",
                    physical_unit=unit,
                    signals=(tags[(LEVEL, train, stage)], tags[(TEMPERATURE, train, stage)]),
                    description=(
                        "A tank that is both filled and heated. How full it is decides how fast "
                        "it warms, which is why its two loops are not independent."
                    ),
                )
            )
            components.append(
                Component(
                    component_id=f"pump_t{train}_s{stage}",
                    kind=ComponentKind.PUMP,
                    label=f"Train {train + 1} tank {stage + 1} pump",
                    physical_unit=unit,
                    signals=(tags[(PUMP_SPEED, train, stage)],),
                    description="Fills this tank from the one above it, or from the feed.",
                )
            )
            components.append(
                Component(
                    component_id=f"heater_t{train}_s{stage}",
                    kind=ComponentKind.HEATER,
                    label=f"Train {train + 1} tank {stage + 1} heater",
                    physical_unit=unit,
                    signals=(tags[(DUTY, train, stage)],),
                    description="Puts heat into this tank.",
                )
            )
            components.append(
                Component(
                    component_id=f"inlet_t{train}_s{stage}",
                    kind=ComponentKind.PIPE,
                    label=f"Train {train + 1} tank {stage + 1} inlet",
                    physical_unit=unit,
                    signals=((tags[(INFLOW, train, stage)],) if metered[(train, stage)] else ()),
                    description=(
                        "The pipe into the tank, carrying both liquid and the heat it holds."
                        + (
                            " A flow meter on it says how fast."
                            if metered[(train, stage)]
                            else " No flow meter here."
                        )
                    ),
                )
            )
            components.append(
                Component(
                    component_id=f"level_loop_t{train}_s{stage}",
                    kind=ComponentKind.CONTROLLER,
                    label=f"Train {train + 1} tank {stage + 1} level loop",
                    physical_unit=unit,
                    signals=(tags[(LEVEL_SETPOINT, train, stage)],),
                    description="Holds this tank at its target level by varying its pump.",
                )
            )
            components.append(
                Component(
                    component_id=f"temp_loop_t{train}_s{stage}",
                    kind=ComponentKind.CONTROLLER,
                    label=f"Train {train + 1} tank {stage + 1} temperature loop",
                    physical_unit=unit,
                    signals=(tags[(TEMPERATURE_SETPOINT, train, stage)],),
                    description="Holds this tank at its target temperature by varying its heater.",
                )
            )
    components.append(
        Component(
            component_id="header",
            kind=ComponentKind.PIPE,
            label="Common header",
            physical_unit=_UTILITY_UNIT,
            signals=(tags[(OUTFLOW, 0, stages)],),
            description="Where every chain discharges, and where the demand is measured.",
        )
    )
    components.append(
        Component(
            component_id="ambient",
            kind=ComponentKind.SOURCE,
            label="Ambient conditions",
            physical_unit=_UTILITY_UNIT,
            signals=(tags[(AMBIENT, 1, stages)],),
            description="The weather. Every tank loses heat to it.",
        )
    )
    components.append(
        Component(
            component_id="demand",
            kind=ComponentKind.LOAD,
            label="Downstream demand",
            physical_unit=_UTILITY_UNIT,
            description="Whatever is drawing hot liquid off the end of the chain.",
        )
    )
    return tuple(components)


def _connections(trains: int, stages: int) -> tuple[Connection, ...]:
    """Return which way the liquid and the heat go."""
    connections: list[Connection] = []
    for train in range(trains):
        for stage in range(stages):
            if stage:
                connections.append(
                    Connection(
                        source=f"tank_t{train}_s{stage - 1}",
                        target=f"pump_t{train}_s{stage}",
                        medium="liquid",
                        label="previous tank to the next pump",
                    )
                )
            connections.append(
                Connection(
                    source=f"pump_t{train}_s{stage}",
                    target=f"inlet_t{train}_s{stage}",
                    medium="liquid",
                    label="pump to its inlet main",
                )
            )
            connections.append(
                Connection(
                    source=f"inlet_t{train}_s{stage}",
                    target=f"tank_t{train}_s{stage}",
                    medium="liquid",
                    label="inlet carrying liquid and its heat into the tank",
                )
            )
            connections.append(
                Connection(
                    source=f"heater_t{train}_s{stage}",
                    target=f"tank_t{train}_s{stage}",
                    medium="heat",
                    label="heater into the tank",
                )
            )
            connections.append(
                Connection(
                    source=f"tank_t{train}_s{stage}",
                    target="ambient",
                    medium="heat",
                    label="loss through the tank walls",
                )
            )
            connections.append(
                Connection(
                    source=f"level_loop_t{train}_s{stage}",
                    target=f"pump_t{train}_s{stage}",
                    medium="signal",
                    label="level loop drives pump speed",
                )
            )
            connections.append(
                Connection(
                    source=f"temp_loop_t{train}_s{stage}",
                    target=f"heater_t{train}_s{stage}",
                    medium="signal",
                    label="temperature loop drives heater duty",
                )
            )
        connections.append(
            Connection(
                source=f"tank_t{train}_s{stages - 1}",
                target="header",
                medium="liquid",
                label="final tank into the common header",
            )
        )
    connections.append(
        Connection(source="header", target="demand", medium="liquid", label="header to the demand")
    )
    return tuple(connections)


def _controllers(
    parameters: Mapping[str, float],
    trains: int,
    stages: int,
    tags: Mapping[RolePosition, str],
) -> tuple[ControllerSpec, ...]:
    """Return a level loop and a temperature loop on every stage."""
    controllers: list[ControllerSpec] = []
    for train in range(trains):
        for stage in range(stages):
            controllers.append(
                ControllerSpec(
                    controller_id=level_loop_id(train, stage),
                    kind=ControllerKind.PI,
                    measurement=tags[(LEVEL, train, stage)],
                    setpoint=tags[(LEVEL_SETPOINT, train, stage)],
                    output=tags[(PUMP_SPEED, train, stage)],
                    gain=parameters["level_gain"],
                    integral_time_seconds=parameters["level_integral_s"],
                    low=0.0,
                    high=100.0,
                    bias=parameters["pump_bias_pct"],
                    description="Holds this tank's level by varying its pump.",
                )
            )
            controllers.append(
                ControllerSpec(
                    controller_id=temperature_loop_id(train, stage),
                    kind=ControllerKind.PI,
                    measurement=tags[(TEMPERATURE, train, stage)],
                    setpoint=tags[(TEMPERATURE_SETPOINT, train, stage)],
                    output=tags[(DUTY, train, stage)],
                    gain=parameters["temperature_gain"],
                    integral_time_seconds=parameters["temperature_integral_s"],
                    low=0.0,
                    high=100.0,
                    bias=parameters["duty_bias_pct"],
                    description=(
                        "Holds this tank's temperature by varying its heater. Its effective gain "
                        "depends on the level, which the other loop is moving."
                    ),
                )
            )
    return tuple(controllers)


def _couplings(
    trains: int,
    stages: int,
    metered: Mapping[tuple[int, int], bool],
    tags: Mapping[RolePosition, str],
) -> tuple[Coupling, ...]:
    """Return the plant's claim about what makes its signals related."""
    couplings: list[Coupling] = []
    ambient = tags[(AMBIENT, 1, stages)]
    outflow = tags[(OUTFLOW, 0, stages)]
    for train in range(trains):
        for stage in range(stages):
            upstream = (
                tags[(INFLOW, train, stage)]
                if metered[(train, stage)]
                else tags[(PUMP_SPEED, train, stage)]
            )
            downstream = tags[(PUMP_SPEED, train, stage + 1)] if stage + 1 < stages else outflow
            couplings.append(
                Coupling(
                    driven=tags[(LEVEL, train, stage)],
                    drivers=(upstream, downstream),
                    kind=CouplingKind.INTEGRATION,
                    relation="level is the running total of what came in less what went out",
                )
            )
            hot_upstream = tags[(TEMPERATURE, train, stage - 1)] if stage else upstream
            couplings.append(
                Coupling(
                    driven=tags[(TEMPERATURE, train, stage)],
                    drivers=(
                        tags[(DUTY, train, stage)],
                        tags[(LEVEL, train, stage)],
                        hot_upstream,
                        ambient,
                    ),
                    kind=CouplingKind.INTEGRATION,
                    relation=(
                        "temperature is the running balance of heater duty, the stream arriving "
                        "at the tank above's temperature, and loss to ambient — divided by a "
                        "thermal mass that is the level"
                    ),
                )
            )
            couplings.append(
                Coupling(
                    driven=tags[(PUMP_SPEED, train, stage)],
                    drivers=(
                        tags[(LEVEL, train, stage)],
                        tags[(LEVEL_SETPOINT, train, stage)],
                    ),
                    kind=CouplingKind.CONTROL,
                    relation="a PI loop holds the level at its setpoint",
                )
            )
            couplings.append(
                Coupling(
                    driven=tags[(DUTY, train, stage)],
                    drivers=(
                        tags[(TEMPERATURE, train, stage)],
                        tags[(TEMPERATURE_SETPOINT, train, stage)],
                    ),
                    kind=CouplingKind.CONTROL,
                    relation="a PI loop holds the temperature at its setpoint",
                )
            )
    return tuple(couplings)


def _register_plan(
    trains: int,
    stages: int,
    metered: Mapping[tuple[int, int], bool],
    tags: Mapping[RolePosition, str],
) -> tuple[tuple[list[str], list[str]], ...]:
    """Return what each train's PLC exposes read-only, and what an operator may write."""
    plan: list[tuple[list[str], list[str]]] = []
    for train in range(trains):
        readable: list[str] = []
        writable: list[str] = []
        for stage in range(stages):
            readable.append(tags[(LEVEL, train, stage)])
            readable.append(tags[(TEMPERATURE, train, stage)])
            if metered[(train, stage)]:
                readable.append(tags[(INFLOW, train, stage)])
            readable.append(tags[(PUMP_SPEED, train, stage)])
            readable.append(tags[(DUTY, train, stage)])
            writable.append(tags[(LEVEL_SETPOINT, train, stage)])
            writable.append(tags[(TEMPERATURE_SETPOINT, train, stage)])
        if train == 0:
            readable.append(tags[(OUTFLOW, 0, stages)])
            readable.append(tags[(AMBIENT, 1, stages)])
        plan.append((readable, writable))
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
    surge = bounded(draw, limits, "surge_fraction")
    surge_steps = round(bounded(draw, limits, "surge_steps"))
    feed_drop = bounded(draw, limits, "feed_drop_c")
    feed_steps = round(bounded(draw, limits, "feed_drop_steps"))
    span = parameters["level_span_m"]
    middle = parameters["level_setpoint_fraction"]
    temperature = parameters["temperature_setpoint_c"]

    plans: list[EventPlanSpec] = [
        EventPlanSpec(
            kind=DEMAND_SURGE,
            label="Downstream demand rises for a while",
            duration_steps=surge_steps,
            parameter_ranges={"demand_surge_fraction": (surge * 0.4, surge)},
            detail="demand raised by a fraction of:",
        ),
        EventPlanSpec(
            kind=COLD_FEED,
            label="What arrives at the front of the chain turns colder",
            duration_steps=feed_steps,
            parameter_ranges={"feed_drop_c": (feed_drop * 0.3, feed_drop)},
            detail="feed temperature dropped by:",
        ),
    ]
    for train in range(trains):
        level_target = tags[(LEVEL_SETPOINT, train, 0)]
        temp_target = tags[(TEMPERATURE_SETPOINT, train, 0)]
        plans.append(
            EventPlanSpec(
                kind=_LEVEL_SETPOINT_CHANGE,
                label=f"Operator moves train {train + 1}'s first level setpoint",
                duration_steps=0,
                writes=(level_target,),
                parameter_ranges={
                    level_target: (
                        span * max(0.15, middle - 0.12),
                        span * min(0.9, middle + 0.12),
                    )
                },
                detail=f"new level setpoint on train {train + 1}:",
            )
        )
        plans.append(
            EventPlanSpec(
                kind=_TEMPERATURE_SETPOINT_CHANGE,
                label=f"Operator moves train {train + 1}'s first temperature setpoint",
                duration_steps=0,
                writes=(temp_target,),
                parameter_ranges={temp_target: (temperature * 0.9, temperature * 1.08)},
                detail=f"new temperature setpoint on train {train + 1}:",
            )
        )
    return DisturbanceSpec(
        event_plans=tuple(plans),
        first_start_floor=30,
        first_start_divisor=12,
        gap_steps=(gap_low, gap_high),
    )


register_family(HybridFamily())

"""The `thermal` family: how a seed becomes one chain of heated vessels.

PART R2. `phos.synth.plants.thermal` holds the physics and the energy balance; this module holds
what may vary and turns a master seed into a `phos.synth.plant_spec.PlantSpec`.

**The heater rating is derived, not drawn.** Its bound is on ``heater_margin`` — how much more
heat a heater can put in than the duty its vessel actually needs — and the rating itself is
computed from the throughput, the temperature rise and the heat loss. Drawing kilowatts directly
produced chains whose heaters were pinned at full duty for an entire run, which is a plant with no
control behaviour in it. ``temperature_span_c`` is derived the same way, from the setpoint and a
drawn headroom.

**The bound that still matters most is the insulation.** ``ua_ambient_kw_per_k`` and
``heater_rated_kw`` together decide whether a vessel can reach its setpoint at all: a badly
lagged vessel with a small heater cannot be held at 130 °C however hard its loop pushes, and the
loop will sit at full duty for the whole run. That is a real plant — plenty of sites run a
process at the top of its capability — but it is also the shape a validity gate has to be able to
refuse, because a plant whose every heater is saturated has no control behaviour left to learn.
The ranges below make it uncommon rather than impossible, and PART R3 is what catches it.
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
from phos.synth.plants.thermal import (
    AMBIENT,
    COLD_FEED,
    DUTY,
    FLOW,
    TEMPERATURE,
    TEMPERATURE_SETPOINT,
    THERMAL_PROCESS,
    THROUGHPUT_CHANGE,
    duty_loop_id,
)
from phos.synth.randomise import StreamDraw

__all__ = ["THERMAL_BOUNDS", "ThermalFamily"]

_PREFIXES: Final = ("", "HT", "THERM", "UNIT", "H")
_UTILITY_UNIT: Final = "utility"
_SETPOINT_CHANGE: Final = "temperature_setpoint_change"

THERMAL_BOUNDS: Final = (
    ParameterBound(
        "trains",
        1,
        3,
        BoundScale.INTEGER,
        "",
        "How many chains of vessels run side by side.",
    ),
    ParameterBound(
        "stages",
        2,
        4,
        BoundScale.INTEGER,
        "",
        "How many heated vessels each chain is made of, counting in the direction of flow.",
    ),
    ParameterBound(
        "holdup_kg",
        200.0,
        20000.0,
        BoundScale.LOG,
        "kg",
        "How much fluid is in each vessel. With its heat capacity this is the thermal inertia — "
        "why a large vessel's temperature barely moves in a minute and a small one's does.",
    ),
    ParameterBound(
        "heat_capacity_kj_per_kg_k",
        1.8,
        4.2,
        BoundScale.LINEAR,
        "kJ/kg/K",
        "Specific heat of whatever is being heated. Water sits at the top of this range and most "
        "organic liquids near the bottom.",
    ),
    ParameterBound(
        "heater_margin",
        1.2,
        2.6,
        BoundScale.LINEAR,
        "",
        "How much more heat each heater can put in than the duty its vessel actually needs at the "
        "design point. This is how a heater is chosen: you work out the duty from the throughput, "
        "the temperature rise and the heat loss, and buy something with headroom over it. Drawing "
        "the rating independently produced chains whose heaters were pinned at full duty for the "
        "whole run — three draws in five — and a saturated loop has no control behaviour to learn.",
    ),
    ParameterBound(
        "ua_ambient_kw_per_k",
        0.02,
        2.5,
        BoundScale.LOG,
        "kW/K",
        "How fast each vessel loses heat to the room, per degree it is above it. A well-lagged "
        "vessel sits at the bottom of this range and a bare one at the top.",
    ),
    ParameterBound(
        "feed_temp_c",
        4.0,
        40.0,
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
        "Mean temperature of the room or the yard the vessels stand in.",
    ),
    ParameterBound(
        "ambient_daily_c",
        1.0,
        14.0,
        BoundScale.LINEAR,
        "degC",
        "How far the room's temperature swings over a day. A vessel outdoors swings more than one "
        "in a heated building, and the loops have to absorb it.",
    ),
    ParameterBound(
        "residence_minutes",
        12.0,
        240.0,
        BoundScale.LOG,
        "min",
        "How long fluid spends in each vessel at mean throughput — the holdup divided by the "
        "flow. The throughput in kilograms per hour is derived from it and the holdup, because "
        "the residence time is the quantity that actually matters and the one an engineer would "
        "quote. Drawn as a throughput directly, the residence time ranged from a minute to two "
        "days: a vessel whose contents turn over faster than the plant is sampled is not a hard "
        "plant, it is an unresolved one, and the energy balance said so on three draws in five.",
    ),
    ParameterBound(
        "flow_daily_fraction",
        0.02,
        0.30,
        BoundScale.LINEAR,
        "",
        "How far the throughput swings over a day, as a fraction of its mean.",
    ),
    ParameterBound(
        "temperature_setpoint_c",
        40.0,
        150.0,
        BoundScale.LINEAR,
        "degC",
        "What every vessel in the chain is held at.",
    ),
    ParameterBound(
        "temperature_headroom",
        1.25,
        2.0,
        BoundScale.LINEAR,
        "",
        "How far above the setpoint the transmitters are calibrated, as a multiple of it. Real "
        "spans carry headroom, and a signal that sits at the top of its own span all run is a "
        "signal whose range tells a detector nothing.",
    ),
    ParameterBound(
        "temperature_gain",
        0.8,
        18.0,
        BoundScale.LOG,
        "%/K",
        "Proportional gain of every temperature loop: how much duty it adds per degree of error.",
    ),
    ParameterBound(
        "temperature_integral_s",
        120.0,
        2400.0,
        BoundScale.LOG,
        "s",
        "Integral time of every temperature loop. A vessel with a long residence time needs a "
        "patient loop; a brisk one on a slow vessel hunts.",
    ),
    ParameterBound(
        "duty_bias_pct",
        5.0,
        55.0,
        BoundScale.LINEAR,
        "%",
        "Heater duty the loop starts from before its own terms, so the integral does not have to "
        "supply the whole operating point.",
    ),
    ParameterBound(
        "temperature_noise_c",
        0.01,
        0.9,
        BoundScale.LOG,
        "degC",
        "Measurement noise on every temperature transmitter.",
    ),
    ParameterBound(
        "temperature_drift_c",
        0.005,
        0.5,
        BoundScale.LOG,
        "degC",
        "Bound on each temperature transmitter's slow calibration drift. This is the one that "
        "matters: a thermocouple drifting half a degree over a week is ordinary, and it is also "
        "exactly what a slow sensor-spoofing attack looks like.",
    ),
    ParameterBound(
        "duty_noise_pct",
        0.01,
        0.6,
        BoundScale.LOG,
        "%",
        "Measurement noise on the reported heater duty.",
    ),
    ParameterBound(
        "flow_noise_fraction",
        0.001,
        0.025,
        BoundScale.LOG,
        "",
        "Measurement noise on the throughput meter, as a fraction of mean throughput.",
    ),
    ParameterBound(
        "scan_period_s",
        5,
        120,
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
        "feed_drop_c",
        2.0,
        18.0,
        BoundScale.LINEAR,
        "degC",
        "How much colder the feed turns during a cold-feed excursion — a tanker of cold material, "
        "or a change of source.",
    ),
    ParameterBound(
        "feed_drop_steps",
        40,
        500,
        BoundScale.INTEGER,
        "samples",
        "How long a cold-feed excursion lasts.",
    ),
    ParameterBound(
        "throughput_fraction",
        0.08,
        0.45,
        BoundScale.LINEAR,
        "",
        "How far a throughput change moves the stream while it lasts.",
    ),
    ParameterBound(
        "throughput_steps",
        40,
        500,
        BoundScale.INTEGER,
        "samples",
        "How long a throughput change lasts.",
    ),
)
"""Everything the `thermal` family varies, rendered into ``docs/sim/README.md``."""


class ThermalFamily(PlantFamily):
    """Chains of heated vessels: the same process at different sizes, duties and insulation."""

    @property
    def family_id(self) -> str:
        """The identifier this family is drawn by."""
        return "thermal"

    @property
    def label(self) -> str:
        """Human-readable name."""
        return "Heated vessel chain"

    @property
    def process(self) -> str:
        """The physics every plant from this family runs on."""
        return THERMAL_PROCESS

    @property
    def industry(self) -> str:
        """The sector this process belongs to."""
        return "process heating"

    @property
    def summary(self) -> str:
        """What the process does, for a reader who is not a process engineer."""
        return (
            "Fluid passes through a chain of heated vessels. Each has a heater held at a target "
            "temperature by its own loop, and each is fighting two things at once: the stream "
            "running through it carrying heat away, and the room around it taking heat out "
            "through the walls."
        )

    def bounds(self) -> tuple[ParameterBound, ...]:
        """Return everything this family varies, and the range it varies it over."""
        return THERMAL_BOUNDS

    def draw(self, master_seed: int) -> PlantSpec:
        """Draw one chain of heated vessels.

        Args:
            master_seed: Seeds every draw below.

        Returns:
            The drawn plant, as a valid spec. Whether its heaters can actually reach their
            setpoints is PART R3's question.
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

        parameters = _parameters(sizing, tuning, instruments, limits, trains, stages)
        scheme = draw_naming_scheme(naming, _PREFIXES)
        tags = render_tags(scheme, _positions(trains, stages))

        return PlantSpec(
            plant_id=f"thermal-{master_seed}",
            label=f"Heated vessel chain, {trains} train(s) of {stages}",
            industry=self.industry,
            summary=self.summary,
            model_source=(
                f"Drawn by phos.synth.families from the {self.family_id} family at master seed "
                f"{master_seed}. A model of a heated process built from an energy balance over "
                "each vessel — the stream through it, its heater and its loss to ambient — with "
                "PI duty control. Not a model of any particular plant and not validated against "
                "one."
            ),
            process=self.process,
            parameters=parameters,
            units=stage_units(
                trains, stages, label="vessel", extra=((_UTILITY_UNIT, "Ambient and utilities"),)
            ),
            signals=_signals(parameters, trains, stages, tags),
            components=_components(trains, stages, tags),
            connections=_connections(trains, stages),
            controllers=_controllers(parameters, trains, stages, tags),
            couplings=_couplings(trains, stages, tags),
            control_network=modbus_network(
                poll_interval_seconds=parameters["scan_period_s"],
                subnet="10.4",
                per_plc=_register_plan(trains, stages, tags),
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
    stages: int,
) -> dict[str, float]:
    """Draw how big the plant is, how it is tuned and how well it is instrumented."""
    setpoint = bounded(tuning, limits, "temperature_setpoint_c")
    headroom = bounded(tuning, limits, "temperature_headroom")
    holdup = bounded(sizing, limits, "holdup_kg")
    heat_capacity = bounded(sizing, limits, "heat_capacity_kj_per_kg_k")
    margin = bounded(sizing, limits, "heater_margin")
    ua = bounded(sizing, limits, "ua_ambient_kw_per_k")
    feed = bounded(sizing, limits, "feed_temp_c")
    ambient = bounded(sizing, limits, "ambient_base_c")
    residence_minutes = bounded(sizing, limits, "residence_minutes")
    flow = holdup / (residence_minutes / 60.0)
    # The duty the first vessel in the chain has to do: raise the whole stream from feed
    # temperature to setpoint, and replace what the walls lose. Later vessels need less, because
    # their inlet is already warm, so sizing every heater on the first one's duty is the
    # conservative choice a real design would make.
    required_kw = flow / 3600.0 * heat_capacity * (setpoint - feed) + ua * (setpoint - ambient)
    return {
        "trains": float(trains),
        "stages": float(stages),
        "holdup_kg": holdup,
        "heat_capacity_kj_per_kg_k": heat_capacity,
        "heater_margin": margin,
        "heater_rated_kw": required_kw * margin,
        "ua_ambient_kw_per_k": ua,
        "feed_temp_c": feed,
        "ambient_base_c": ambient,
        "ambient_daily_c": bounded(sizing, limits, "ambient_daily_c"),
        "residence_minutes": residence_minutes,
        "flow_base_kgph": flow,
        "flow_daily_fraction": bounded(sizing, limits, "flow_daily_fraction"),
        "temperature_setpoint_c": setpoint,
        "temperature_span_c": setpoint * headroom,
        "temperature_gain": bounded(tuning, limits, "temperature_gain"),
        "temperature_integral_s": bounded(tuning, limits, "temperature_integral_s"),
        "duty_bias_pct": bounded(tuning, limits, "duty_bias_pct"),
        "temperature_noise_c": bounded(instruments, limits, "temperature_noise_c"),
        "temperature_drift_c": bounded(instruments, limits, "temperature_drift_c"),
        "duty_noise_pct": bounded(instruments, limits, "duty_noise_pct"),
        "flow_noise_fraction": bounded(instruments, limits, "flow_noise_fraction"),
        "scan_period_s": bounded(instruments, limits, "scan_period_s"),
    }


def _positions(trains: int, stages: int) -> tuple[tuple[RolePosition, str], ...]:
    """Return every role position this plant has, with the unit its signal carries."""
    positions: list[tuple[RolePosition, str]] = []
    for train in range(trains):
        positions.append(((FLOW, train, 0), "kg/h"))
        for stage in range(stages):
            positions.append(((TEMPERATURE, train, stage), "degC"))
            positions.append(((TEMPERATURE_SETPOINT, train, stage), "degC"))
            positions.append(((DUTY, train, stage), "pct"))
    positions.append(((AMBIENT, 0, stages), "degC"))
    return tuple(positions)


def _signals(
    parameters: Mapping[str, float],
    trains: int,
    stages: int,
    tags: Mapping[RolePosition, str],
) -> tuple[SignalSpec, ...]:
    """Return the instruments, with the spans, noise and drift this plant was drawn with."""
    span = parameters["temperature_span_c"]
    flow_noise = parameters["flow_noise_fraction"] * parameters["flow_base_kgph"]
    signals: list[SignalSpec] = []
    for train in range(trains):
        signals.append(
            SignalSpec(
                key=tags[(FLOW, train, 0)],
                label=f"Train {train + 1} throughput",
                unit="kg/h",
                kind=SignalKind.SENSOR,
                physical_unit=stage_unit_id(train, 0),
                low=0.0,
                high=parameters["flow_base_kgph"] * 2.0,
                noise_stddev=flow_noise,
                drift_amplitude=flow_noise * 0.5,
            )
        )
        for stage in range(stages):
            unit = stage_unit_id(train, stage)
            signals.append(
                SignalSpec(
                    key=tags[(TEMPERATURE, train, stage)],
                    label=f"Train {train + 1} vessel {stage + 1} temperature",
                    unit="degC",
                    kind=SignalKind.SENSOR,
                    physical_unit=unit,
                    low=0.0,
                    high=span,
                    noise_stddev=parameters["temperature_noise_c"],
                    drift_amplitude=parameters["temperature_drift_c"],
                )
            )
            signals.append(
                SignalSpec(
                    key=tags[(DUTY, train, stage)],
                    label=f"Train {train + 1} vessel {stage + 1} heater duty",
                    unit="%",
                    kind=SignalKind.ACTUATOR,
                    physical_unit=unit,
                    low=0.0,
                    high=100.0,
                    noise_stddev=parameters["duty_noise_pct"],
                )
            )
            signals.append(
                SignalSpec(
                    key=tags[(TEMPERATURE_SETPOINT, train, stage)],
                    label=f"Train {train + 1} vessel {stage + 1} temperature setpoint",
                    unit="degC",
                    kind=SignalKind.SETPOINT,
                    physical_unit=unit,
                    low=0.0,
                    high=span,
                    noise_stddev=0.0,
                )
            )
    signals.append(
        SignalSpec(
            key=tags[(AMBIENT, 0, stages)],
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
    trains: int, stages: int, tags: Mapping[RolePosition, str]
) -> tuple[Component, ...]:
    """Return what the plant is made of, with every signal owned exactly once."""
    components: list[Component] = []
    for train in range(trains):
        components.append(
            Component(
                component_id=f"feed_t{train}",
                kind=ComponentKind.PIPE,
                label=f"Train {train + 1} feed line",
                physical_unit=stage_unit_id(train, 0),
                signals=(tags[(FLOW, train, 0)],),
                description=(
                    "The line bringing cold material into the chain, with the meter that says "
                    "how fast it is arriving. Nothing here controls it."
                ),
            )
        )
        for stage in range(stages):
            unit = stage_unit_id(train, stage)
            components.append(
                Component(
                    component_id=f"vessel_t{train}_s{stage}",
                    kind=ComponentKind.TANK,
                    label=f"Train {train + 1} vessel {stage + 1}",
                    physical_unit=unit,
                    signals=(tags[(TEMPERATURE, train, stage)],),
                    description=(
                        "A vessel of warm fluid. Its temperature is the running balance of the "
                        "heat its heater puts in, the heat the stream through it carries away, "
                        "and the heat it loses through its walls."
                    ),
                )
            )
            components.append(
                Component(
                    component_id=f"heater_t{train}_s{stage}",
                    kind=ComponentKind.HEATER,
                    label=f"Train {train + 1} vessel {stage + 1} heater",
                    physical_unit=unit,
                    signals=(tags[(DUTY, train, stage)],),
                    description=(
                        "Puts heat into the vessel. Its duty is the only handle the plant has on "
                        "temperature."
                    ),
                )
            )
            components.append(
                Component(
                    component_id=f"loop_t{train}_s{stage}",
                    kind=ComponentKind.CONTROLLER,
                    label=f"Train {train + 1} vessel {stage + 1} temperature loop",
                    physical_unit=unit,
                    signals=(tags[(TEMPERATURE_SETPOINT, train, stage)],),
                    description="Holds this vessel at its target by varying its heater's duty.",
                )
            )
    components.append(
        Component(
            component_id="ambient",
            kind=ComponentKind.SOURCE,
            label="Ambient conditions",
            physical_unit=_UTILITY_UNIT,
            signals=(tags[(AMBIENT, 0, stages)],),
            description=(
                "The weather, or the temperature of the building. Every vessel loses heat to it, "
                "and it swings over the day whether the plant likes it or not."
            ),
        )
    )
    return tuple(components)


def _connections(trains: int, stages: int) -> tuple[Connection, ...]:
    """Return which way the fluid and the heat go."""
    connections: list[Connection] = []
    for train in range(trains):
        connections.append(
            Connection(
                source=f"feed_t{train}",
                target=f"vessel_t{train}_s0",
                medium="process",
                label="cold feed into the first vessel",
            )
        )
        for stage in range(stages):
            connections.append(
                Connection(
                    source=f"heater_t{train}_s{stage}",
                    target=f"vessel_t{train}_s{stage}",
                    medium="heat",
                    label="heater into the vessel",
                )
            )
            connections.append(
                Connection(
                    source=f"loop_t{train}_s{stage}",
                    target=f"heater_t{train}_s{stage}",
                    medium="signal",
                    label="temperature loop drives heater duty",
                )
            )
            connections.append(
                Connection(
                    source=f"vessel_t{train}_s{stage}",
                    target="ambient",
                    medium="heat",
                    label="loss through the vessel walls",
                )
            )
            if stage + 1 < stages:
                connections.append(
                    Connection(
                        source=f"vessel_t{train}_s{stage}",
                        target=f"vessel_t{train}_s{stage + 1}",
                        medium="process",
                        label="warm fluid to the next vessel",
                    )
                )
    return tuple(connections)


def _controllers(
    parameters: Mapping[str, float],
    trains: int,
    stages: int,
    tags: Mapping[RolePosition, str],
) -> tuple[ControllerSpec, ...]:
    """Return one temperature loop per vessel, all on the tuning this plant was drawn with."""
    return tuple(
        ControllerSpec(
            controller_id=duty_loop_id(train, stage),
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
                f"Holds train {train + 1} vessel {stage + 1} at its setpoint by varying duty."
            ),
        )
        for train in range(trains)
        for stage in range(stages)
    )


def _couplings(trains: int, stages: int, tags: Mapping[RolePosition, str]) -> tuple[Coupling, ...]:
    """Return the plant's claim about what makes its signals related."""
    couplings: list[Coupling] = []
    ambient = tags[(AMBIENT, 0, stages)]
    for train in range(trains):
        flow = tags[(FLOW, train, 0)]
        for stage in range(stages):
            upstream = tags[(TEMPERATURE, train, stage - 1)] if stage else tags[(FLOW, train, 0)]
            couplings.append(
                Coupling(
                    driven=tags[(TEMPERATURE, train, stage)],
                    drivers=(tags[(DUTY, train, stage)], flow, ambient, upstream),
                    kind=CouplingKind.INTEGRATION,
                    relation=(
                        "temperature is the running balance of heater duty in, the stream "
                        "carrying heat away, and loss to ambient"
                    ),
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
    trains: int, stages: int, tags: Mapping[RolePosition, str]
) -> tuple[tuple[list[str], list[str]], ...]:
    """Return what each train's PLC exposes read-only, and what an operator may write."""
    plan: list[tuple[list[str], list[str]]] = []
    for train in range(trains):
        readable = [tags[(FLOW, train, 0)]]
        writable: list[str] = []
        for stage in range(stages):
            readable.append(tags[(TEMPERATURE, train, stage)])
            readable.append(tags[(DUTY, train, stage)])
            writable.append(tags[(TEMPERATURE_SETPOINT, train, stage)])
        if train == 0:
            readable.append(tags[(AMBIENT, 0, stages)])
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
    feed_drop = bounded(draw, limits, "feed_drop_c")
    feed_steps = round(bounded(draw, limits, "feed_drop_steps"))
    throughput = bounded(draw, limits, "throughput_fraction")
    throughput_steps = round(bounded(draw, limits, "throughput_steps"))
    setpoint = parameters["temperature_setpoint_c"]

    plans: list[EventPlanSpec] = [
        EventPlanSpec(
            kind=COLD_FEED,
            label="What arrives at the front of the chain turns colder",
            duration_steps=feed_steps,
            parameter_ranges={"feed_drop_c": (feed_drop * 0.3, feed_drop)},
            detail="feed temperature dropped by:",
        ),
        EventPlanSpec(
            kind=THROUGHPUT_CHANGE,
            label="Throughput is stepped up or down",
            duration_steps=throughput_steps,
            parameter_ranges={"throughput_fraction": (-throughput, throughput)},
            detail="throughput moved by a fraction of:",
        ),
    ]
    for train in range(trains):
        target = tags[(TEMPERATURE_SETPOINT, train, 0)]
        plans.append(
            EventPlanSpec(
                kind=_SETPOINT_CHANGE,
                label=f"Operator moves train {train + 1}'s first vessel setpoint",
                duration_steps=0,
                writes=(target,),
                parameter_ranges={target: (setpoint * 0.88, setpoint * 1.1)},
                detail=f"new temperature setpoint on train {train + 1}:",
            )
        )
    return DisturbanceSpec(
        event_plans=tuple(plans),
        first_start_floor=30,
        first_start_divisor=12,
        gap_steps=(gap_low, gap_high),
    )


register_family(ThermalFamily())

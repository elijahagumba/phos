"""The `level_flow` family: how a seed becomes one pumped tank chain.

PART R2. `phos.synth.plants.level_flow` holds the physics; this module holds what may vary and
turns a master seed into a `phos.synth.plant_spec.PlantSpec` the physics can run.

**Every number comes through a declared bound.** `bounds()` is data, the public table in
``docs/sim/README.md`` is rendered from it, and `phos.synth.families.bounded` refuses to draw a
parameter the family never named. A bound that is not in that list cannot reach a plant.

**The draws are split across named streams on purpose.** Structure, sizing, tuning, instruments,
naming and disturbance each take their numbers from their own stream, addressed by name rather
than by spawn index (`phos.synth.randomise`). Adding a stream later — for a fault model, say —
leaves every existing stream bit-identical, so plants drawn today are still the same plants
tomorrow.

**Two parameters are derived rather than drawn, and both are sizing.**
``max_pump_flow_m3ph`` is each train's share of mean demand times a drawn ``pump_margin``, and
``demand_floor_m3ph`` is mean demand times a drawn ``demand_floor_fraction``. They appear in the
drawn plant's parameters, which is what the physics reads, but their *bound* is on the ratio
rather than on the number — because the number on its own is meaningless. A 40 m³/h pump is
generous on one plant and hopeless on the next.

**What is deliberately left to PART R3.** A drawn plant here is a *valid document*: the structure
holds together, every signal has a role and an owner, and every loop has a target. Whether it
could physically exist — whether the pumps can meet the demand, whether the loops settle, whether
the levels stay inside their transmitters' spans — is the validity gate's question, and a draw
that fails it is refused and redrawn rather than nudged into range. The bounds below are chosen
to make that rare, not to make it impossible; narrowing them until nothing is ever refused would
hide what the family is actually capable of producing.
"""

from collections.abc import Mapping
from typing import Final

from phos.synth.command import WriteAuthority
from phos.synth.families import BoundScale, ParameterBound, PlantFamily, bounded, register_family
from phos.synth.plant import (
    ControlNetwork,
    Coupling,
    CouplingKind,
    NetworkNode,
    PhysicalUnit,
    RegisterBlock,
    SignalKind,
    SignalSpec,
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
    SignalRole,
)
from phos.synth.plants.level_flow import (
    DEMAND_SURGE,
    INFLOW,
    LEVEL,
    LEVEL_FLOW_PROCESS,
    LEVEL_SETPOINT,
    OUTFLOW,
    PUMP_SPEED,
    loop_id,
)
from phos.synth.randomise import NamingScheme, NumberStyle, StreamDraw

__all__ = ["LEVEL_FLOW_BOUNDS", "LevelFlowFamily"]

_PREFIXES: Final = ("", "PS", "WTW", "SITE", "P")
"""Tag prefixes a drawn plant may use. The empty one is there because plenty of sites have none."""

_SEPARATORS: Final = ("_", "-", ".")
_SUFFIXES: Final = ("", ".PV", "_VAL")
_SETPOINT_CHANGE: Final = "level_setpoint_change"

LEVEL_FLOW_BOUNDS: Final = (
    ParameterBound(
        "trains",
        1,
        3,
        BoundScale.INTEGER,
        "",
        "How many chains run side by side into the common header. Real sites run more than one so "
        "a stream can be taken out for maintenance without stopping supply.",
    ),
    ParameterBound(
        "stages",
        2,
        4,
        BoundScale.INTEGER,
        "",
        "How many tanks each chain is made of, counting in the direction of flow.",
    ),
    ParameterBound(
        "tank_area_m2",
        20.0,
        400.0,
        BoundScale.LOG,
        "m2",
        "Plan area of every tank. With the level span this is its volume, and it is what turns a "
        "flow imbalance into a rate of level change. Drawn in the log because a small balance "
        "tank and a large reservoir are two orders of magnitude apart.",
    ),
    ParameterBound(
        "level_span_m",
        2.5,
        9.0,
        BoundScale.LINEAR,
        "m",
        "Height of every tank, and the calibrated span of its level transmitter.",
    ),
    ParameterBound(
        "pump_margin",
        1.3,
        3.2,
        BoundScale.LINEAR,
        "",
        "How much more flow each pump can deliver than its train's share of mean demand. This is "
        "how a pump is actually chosen: you work out the duty and buy something with headroom "
        "over it. Drawing the pump size independently of the demand produced chains that could "
        "never keep up — seven draws in forty — and a plant whose pumps are flat out all run has "
        "no control behaviour left to learn.",
    ),
    ParameterBound(
        "flow_tau_s",
        10.0,
        240.0,
        BoundScale.LOG,
        "s",
        "How long a pump takes to reach a new flow after its speed changes — the liquid in the "
        "main has to accelerate. This lag is what makes a level loop a control problem.",
    ),
    ParameterBound(
        "demand_base_m3ph",
        20.0,
        260.0,
        BoundScale.LOG,
        "m3/h",
        "Mean draw on the header. Nobody at the site controls it; everything upstream is arranged "
        "to keep up with it.",
    ),
    ParameterBound(
        "demand_daily_m3ph",
        4.0,
        70.0,
        BoundScale.LOG,
        "m3/h",
        "Amplitude of the once-a-day swing in that draw — the morning and evening peaks.",
    ),
    ParameterBound(
        "demand_floor_fraction",
        0.1,
        0.5,
        BoundScale.LINEAR,
        "",
        "Fraction of the mean draw the header never falls below, even at four in the morning.",
    ),
    ParameterBound(
        "level_setpoint_fraction",
        0.35,
        0.70,
        BoundScale.LINEAR,
        "",
        "Where in the tank the loops hold the level, as a fraction of its height. Sites keep "
        "headroom above for a surge and a working volume below.",
    ),
    ParameterBound(
        "level_gain",
        4.0,
        45.0,
        BoundScale.LOG,
        "%/m",
        "Proportional gain of every level loop: how hard the pump responds to being off target.",
    ),
    ParameterBound(
        "level_integral_s",
        240.0,
        2400.0,
        BoundScale.LOG,
        "s",
        "Integral time of every level loop: how long it takes to repeat the proportional term, so "
        "how patiently it removes a standing offset.",
    ),
    ParameterBound(
        "pump_bias_pct",
        15.0,
        65.0,
        BoundScale.LINEAR,
        "%",
        "Pump speed the loop starts from before its own terms. A real loop carries a feedforward, "
        "and it keeps the integral from having to supply the whole operating point.",
    ),
    ParameterBound(
        "flow_meter_chance",
        0.35,
        1.0,
        BoundScale.LINEAR,
        "",
        "How likely each stage is to have a flow meter on its inlet at all. Below one, some tanks "
        "are instrumented on level alone — which is how a great many real sites are, and means a "
        "detector cannot assume every flow it needs is measured.",
    ),
    ParameterBound(
        "level_noise_m",
        0.002,
        0.06,
        BoundScale.LOG,
        "m",
        "Measurement noise on every level transmitter.",
    ),
    ParameterBound(
        "level_drift_m",
        0.001,
        0.05,
        BoundScale.LOG,
        "m",
        "Bound on each level transmitter's slow calibration drift.",
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
        "pump_noise_pct",
        0.01,
        0.5,
        BoundScale.LOG,
        "%",
        "Measurement noise on the reported pump speed.",
    ),
    ParameterBound(
        "scan_period_s",
        5,
        120,
        BoundScale.INTEGER,
        "s",
        "How often the SCADA system polls every register block. A plant polled every two minutes "
        "is a plant where a detector watching the wire sees far less than one polled every five "
        "seconds, and both exist.",
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
        "How much longer the longest quiet stretch may be than the shortest. Most of any run is "
        "normal, and this is what makes that true.",
    ),
    ParameterBound(
        "surge_fraction",
        0.08,
        0.45,
        BoundScale.LINEAR,
        "",
        "How much a demand surge raises the draw on the header while it lasts.",
    ),
    ParameterBound(
        "surge_steps",
        30,
        400,
        BoundScale.INTEGER,
        "samples",
        "How long a demand surge lasts.",
    ),
)
"""Everything the `level_flow` family varies. Rendered into ``docs/sim/README.md`` by
`phos.synth.families.bounds_table`, and a test fails if the document and this list disagree."""


class LevelFlowFamily(PlantFamily):
    """Pumped tank chains: the same process at different sizes, shapes and tunings."""

    @property
    def family_id(self) -> str:
        """The identifier this family is drawn by."""
        return "level_flow"

    @property
    def label(self) -> str:
        """Human-readable name."""
        return "Pumped tank chain"

    @property
    def process(self) -> str:
        """The physics every plant from this family runs on."""
        return LEVEL_FLOW_PROCESS

    @property
    def industry(self) -> str:
        """The sector this process belongs to."""
        return "water and liquid handling"

    @property
    def summary(self) -> str:
        """What the process does, for a reader who is not a process engineer."""
        return (
            "Liquid is pumped through a chain of tanks and drawn off at the end by a demand "
            "nobody at the site controls. Each tank has a level transmitter and a pump filling "
            "it, held at a target level by its own control loop. Chains may run side by side "
            "into a common header."
        )

    def bounds(self) -> tuple[ParameterBound, ...]:
        """Return everything this family varies, and the range it varies it over."""
        return LEVEL_FLOW_BOUNDS

    def draw(self, master_seed: int) -> PlantSpec:
        """Draw one pumped tank chain.

        Args:
            master_seed: Seeds every draw below.

        Returns:
            The drawn plant, as a valid spec. Not yet checked for whether it could physically
            exist — see the module docstring.
        """
        streams = self.streams(master_seed)
        limits = self.bounds_by_name()
        structure = streams.draw("structure")
        sizing = streams.draw("sizing")
        tuning = streams.draw("tuning")
        instruments = streams.draw("instruments")
        naming_draw = streams.draw("naming")
        disturbance = streams.draw("disturbance")

        trains = round(bounded(structure, limits, "trains"))
        stages = round(bounded(structure, limits, "stages"))
        meter_chance = bounded(structure, limits, "flow_meter_chance")
        metered = {
            (train, stage): structure.uniform(f"flow_meter_t{train}_s{stage}", 0.0, 1.0)
            < meter_chance
            for train in range(trains)
            for stage in range(stages)
        }

        parameters = _sizing(sizing, limits, trains)
        parameters.update(_tuning(tuning, limits))
        parameters["stages"] = float(stages)
        parameters["scan_period_s"] = bounded(instruments, limits, "scan_period_s")
        scheme = _scheme(naming_draw)

        tags = _tags(scheme, trains, stages, metered)
        roles = _roles(trains, stages, metered, tags)
        signals = _signals(parameters, instruments, limits, trains, stages, metered, tags)
        units = _units(trains, stages)

        return PlantSpec(
            plant_id=f"level-flow-{master_seed}",
            label=f"Pumped tank chain, {trains} train(s) of {stages}",
            industry=self.industry,
            summary=self.summary,
            model_source=(
                f"Drawn by phos.synth.families from the {self.family_id} family at master seed "
                f"{master_seed}. A model of a pumped tank chain built from the general shape of "
                "one — conservation of liquid in each tank, square-law pump characteristics and "
                "PI level control — not a model of any particular site and not validated "
                "against one."
            ),
            process=self.process,
            parameters=parameters,
            units=units,
            signals=signals,
            components=_components(trains, stages, metered, tags),
            connections=_connections(trains, stages),
            controllers=_controllers(parameters, trains, stages, tags),
            couplings=_couplings(trains, stages, metered, tags),
            control_network=_network(parameters, trains, stages, metered, tags),
            write_authority=_authority(tags),
            disturbance=_disturbance(disturbance, limits, parameters, trains, tags),
            roles=roles,
        )


def _sizing(
    draw: StreamDraw, limits: Mapping[str, ParameterBound], trains: int
) -> dict[str, float]:
    """Draw how big the plant is and how hard it is worked."""
    demand_base = bounded(draw, limits, "demand_base_m3ph")
    margin = bounded(draw, limits, "pump_margin")
    return {
        "trains": float(trains),
        "tank_area_m2": bounded(draw, limits, "tank_area_m2"),
        "level_span_m": bounded(draw, limits, "level_span_m"),
        "pump_margin": margin,
        "max_pump_flow_m3ph": demand_base / trains * margin,
        "flow_tau_s": bounded(draw, limits, "flow_tau_s"),
        "demand_base_m3ph": demand_base,
        "demand_daily_m3ph": bounded(draw, limits, "demand_daily_m3ph"),
        "demand_floor_m3ph": demand_base * bounded(draw, limits, "demand_floor_fraction"),
    }


def _tuning(draw: StreamDraw, limits: Mapping[str, ParameterBound]) -> dict[str, float]:
    """Draw where the loops hold the levels and how hard they push to do it."""
    return {
        "level_setpoint_fraction": bounded(draw, limits, "level_setpoint_fraction"),
        "level_gain": bounded(draw, limits, "level_gain"),
        "level_integral_s": bounded(draw, limits, "level_integral_s"),
        "pump_bias_pct": bounded(draw, limits, "pump_bias_pct"),
    }


def _scheme(draw: StreamDraw) -> NamingScheme:
    """Draw how this plant spells its tag names."""
    return NamingScheme(
        prefix=draw.choice("tag_prefix", _PREFIXES),
        separator=draw.choice("tag_separator", _SEPARATORS),
        number_style=NumberStyle(
            draw.choice("tag_number_style", tuple(style.value for style in NumberStyle))
        ),
        upper=draw.uniform("tag_upper", 0.0, 1.0) < 0.5,
        suffix=draw.choice("tag_suffix", _SUFFIXES),
        abbreviate=draw.uniform("tag_abbreviate", 0.0, 1.0) < 0.5,
    )


def _tags(
    scheme: NamingScheme, trains: int, stages: int, metered: dict[tuple[int, int], bool]
) -> dict[tuple[str, int, int], str]:
    """Render every signal's tag name, keyed by the role position it belongs to."""
    tags: dict[tuple[str, int, int], str] = {}
    for train in range(trains):
        for stage in range(stages):
            tags[(LEVEL, train, stage)] = scheme.tag(LEVEL, train, stage, "m")
            tags[(PUMP_SPEED, train, stage)] = scheme.tag(PUMP_SPEED, train, stage, "pct")
            tags[(LEVEL_SETPOINT, train, stage)] = scheme.tag(LEVEL_SETPOINT, train, stage, "m")
            if metered[(train, stage)]:
                tags[(INFLOW, train, stage)] = scheme.tag(INFLOW, train, stage, "m3/h")
    tags[(OUTFLOW, 0, stages)] = scheme.tag(OUTFLOW, 0, stages, "m3/h")
    return tags


def _roles(
    trains: int,
    stages: int,
    metered: dict[tuple[int, int], bool],
    tags: dict[tuple[str, int, int], str],
) -> dict[str, SignalRole]:
    """Return the tag-to-role map: the ground truth a randomised tag name is a disguise for."""
    return {
        tag: SignalRole(role=role, train=train, stage=stage)
        for (role, train, stage), tag in tags.items()
    }


def _units(trains: int, stages: int) -> tuple[PhysicalUnit, ...]:
    """Return one physical unit per stage, plus the header every train discharges into."""
    units = [
        PhysicalUnit(unit_id=unit_id(train, stage), label=f"Train {train + 1}, stage {stage + 1}")
        for train in range(trains)
        for stage in range(stages)
    ]
    units.append(PhysicalUnit(unit_id="header", label="Common header and demand"))
    return tuple(units)


def unit_id(train: int, stage: int) -> str:
    """Return the physical unit identifier one stage's instruments sit on."""
    return f"train{train + 1}_stage{stage + 1}"


def _signals(
    parameters: dict[str, float],
    draw: StreamDraw,
    limits: Mapping[str, ParameterBound],
    trains: int,
    stages: int,
    metered: dict[tuple[int, int], bool],
    tags: dict[tuple[str, int, int], str],
) -> tuple[SignalSpec, ...]:
    """Draw the instruments: their spans, their noise and their drift."""
    level_noise = bounded(draw, limits, "level_noise_m")
    level_drift = bounded(draw, limits, "level_drift_m")
    flow_noise = bounded(draw, limits, "flow_noise_fraction") * parameters["max_pump_flow_m3ph"]
    pump_noise = bounded(draw, limits, "pump_noise_pct")
    span = parameters["level_span_m"]
    full_flow = parameters["max_pump_flow_m3ph"]

    signals: list[SignalSpec] = []
    for train in range(trains):
        for stage in range(stages):
            unit = unit_id(train, stage)
            signals.append(
                SignalSpec(
                    key=tags[(LEVEL, train, stage)],
                    label=f"Train {train + 1} stage {stage + 1} level",
                    unit="m",
                    kind=SignalKind.SENSOR,
                    physical_unit=unit,
                    low=0.0,
                    high=span,
                    noise_stddev=level_noise,
                    drift_amplitude=level_drift,
                )
            )
            if metered[(train, stage)]:
                signals.append(
                    SignalSpec(
                        key=tags[(INFLOW, train, stage)],
                        label=f"Train {train + 1} stage {stage + 1} inflow",
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
                    label=f"Train {train + 1} stage {stage + 1} pump speed",
                    unit="%",
                    kind=SignalKind.ACTUATOR,
                    physical_unit=unit,
                    low=0.0,
                    high=100.0,
                    noise_stddev=pump_noise,
                )
            )
            signals.append(
                SignalSpec(
                    key=tags[(LEVEL_SETPOINT, train, stage)],
                    label=f"Train {train + 1} stage {stage + 1} level setpoint",
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
            key=tags[(OUTFLOW, 0, stages)],
            label="Header outflow to demand",
            unit="m3/h",
            kind=SignalKind.SENSOR,
            physical_unit="header",
            low=0.0,
            high=full_flow * trains * 1.5,
            noise_stddev=flow_noise,
            drift_amplitude=flow_noise * 0.5,
        )
    )
    return tuple(signals)


def _components(
    trains: int,
    stages: int,
    metered: dict[tuple[int, int], bool],
    tags: dict[tuple[str, int, int], str],
) -> tuple[Component, ...]:
    """Return what the plant is made of, with every signal owned exactly once."""
    components: list[Component] = []
    for train in range(trains):
        for stage in range(stages):
            unit = unit_id(train, stage)
            if stage == 0:
                components.append(
                    Component(
                        component_id=f"source_t{train}",
                        kind=ComponentKind.SOURCE,
                        label=f"Train {train + 1} supply",
                        physical_unit=unit,
                        description="Where this chain draws its liquid from.",
                    )
                )
            components.append(
                Component(
                    component_id=f"pump_t{train}_s{stage}",
                    kind=ComponentKind.PUMP,
                    label=f"Train {train + 1} stage {stage + 1} pump",
                    physical_unit=unit,
                    signals=(tags[(PUMP_SPEED, train, stage)],),
                    description=(
                        "A variable-speed pump filling this stage's tank. Running it faster is "
                        "the only way the level comes up."
                    ),
                )
            )
            components.append(
                Component(
                    component_id=f"inlet_t{train}_s{stage}",
                    kind=ComponentKind.PIPE,
                    label=f"Train {train + 1} stage {stage + 1} inlet",
                    physical_unit=unit,
                    signals=((tags[(INFLOW, train, stage)],) if metered[(train, stage)] else ()),
                    description=(
                        "The pipe from the pump into the tank."
                        + (
                            " A flow meter on it says how fast the tank is filling."
                            if metered[(train, stage)]
                            else " No flow meter here: this tank is watched on level alone."
                        )
                    ),
                )
            )
            components.append(
                Component(
                    component_id=f"tank_t{train}_s{stage}",
                    kind=ComponentKind.TANK,
                    label=f"Train {train + 1} stage {stage + 1} tank",
                    physical_unit=unit,
                    signals=(tags[(LEVEL, train, stage)],),
                    description=(
                        "A vessel holding liquid. Its level is the running total of what has "
                        "come in less what has gone out, so a reading that disagrees with the "
                        "flows around it is not unusual, it is impossible."
                    ),
                )
            )
            components.append(
                Component(
                    component_id=f"loop_t{train}_s{stage}",
                    kind=ComponentKind.CONTROLLER,
                    label=f"Train {train + 1} stage {stage + 1} level loop",
                    physical_unit=unit,
                    signals=(tags[(LEVEL_SETPOINT, train, stage)],),
                    description="Holds this tank at its target level by varying its pump.",
                )
            )
    components.append(
        Component(
            component_id="header_main",
            kind=ComponentKind.PIPE,
            label="Common header",
            physical_unit="header",
            signals=(tags[(OUTFLOW, 0, stages)],),
            description="Where every chain discharges, and where the demand is measured.",
        )
    )
    components.append(
        Component(
            component_id="demand",
            kind=ComponentKind.LOAD,
            label="Downstream demand",
            physical_unit="header",
            description=(
                "Whatever is drawing on the header. A daily rhythm nobody at the site controls, "
                "and the thing everything upstream is arranged to keep up with."
            ),
        )
    )
    return tuple(components)


def _connections(trains: int, stages: int) -> tuple[Connection, ...]:
    """Return which way the liquid goes, and which loop drives what."""
    connections: list[Connection] = []
    for train in range(trains):
        for stage in range(stages):
            if stage == 0:
                connections.append(
                    Connection(
                        source=f"source_t{train}",
                        target=f"pump_t{train}_s{stage}",
                        medium="liquid",
                        label="supply to the first pump",
                    )
                )
            else:
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
                    label="inlet main into the tank",
                )
            )
            connections.append(
                Connection(
                    source=f"loop_t{train}_s{stage}",
                    target=f"pump_t{train}_s{stage}",
                    medium="signal",
                    label="level loop drives pump speed",
                )
            )
        connections.append(
            Connection(
                source=f"tank_t{train}_s{stages - 1}",
                target="header_main",
                medium="liquid",
                label="final tank into the common header",
            )
        )
    connections.append(
        Connection(
            source="header_main", target="demand", medium="liquid", label="header to the demand"
        )
    )
    return tuple(connections)


def _controllers(
    parameters: dict[str, float],
    trains: int,
    stages: int,
    tags: dict[tuple[str, int, int], str],
) -> tuple[ControllerSpec, ...]:
    """Return one level loop per stage, all on the tuning this plant was drawn with."""
    return tuple(
        ControllerSpec(
            controller_id=loop_id(train, stage),
            kind=ControllerKind.PI,
            measurement=tags[(LEVEL, train, stage)],
            setpoint=tags[(LEVEL_SETPOINT, train, stage)],
            output=tags[(PUMP_SPEED, train, stage)],
            gain=parameters["level_gain"],
            integral_time_seconds=parameters["level_integral_s"],
            low=0.0,
            high=100.0,
            bias=parameters["pump_bias_pct"],
            description=(
                f"Holds train {train + 1} stage {stage + 1} at its setpoint by varying its pump."
            ),
        )
        for train in range(trains)
        for stage in range(stages)
    )


def _couplings(
    trains: int,
    stages: int,
    metered: dict[tuple[int, int], bool],
    tags: dict[tuple[str, int, int], str],
) -> tuple[Coupling, ...]:
    """Return the plant's claim about what makes its signals related."""
    couplings: list[Coupling] = []
    for train in range(trains):
        for stage in range(stages):
            upstream = (
                tags[(INFLOW, train, stage)]
                if metered[(train, stage)]
                else tags[(PUMP_SPEED, train, stage)]
            )
            downstream = (
                tags[(INFLOW, train, stage + 1)]
                if stage + 1 < stages and metered[(train, stage + 1)]
                else tags[(OUTFLOW, 0, stages)]
                if stage + 1 == stages
                else tags[(PUMP_SPEED, train, stage + 1)]
            )
            couplings.append(
                Coupling(
                    driven=tags[(LEVEL, train, stage)],
                    drivers=(upstream, downstream),
                    kind=CouplingKind.INTEGRATION,
                    relation="level is the running total of what came in less what went out",
                )
            )
            if metered[(train, stage)]:
                couplings.append(
                    Coupling(
                        driven=tags[(INFLOW, train, stage)],
                        drivers=(tags[(PUMP_SPEED, train, stage)],),
                        kind=CouplingKind.LAG,
                        relation="flow follows the square root of pump speed, with a lag",
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
    return tuple(couplings)


def _network(
    parameters: dict[str, float],
    trains: int,
    stages: int,
    metered: dict[tuple[int, int], bool],
    tags: dict[tuple[str, int, int], str],
) -> ControlNetwork:
    """Return the control network: a PLC per train, a poller, an operator and a quiet station."""
    nodes = [
        NetworkNode(node_id="scada", label="SCADA server", ip="10.2.0.5", role="scada"),
        NetworkNode(node_id="hmi", label="Operator HMI", ip="10.2.0.20", role="hmi"),
        NetworkNode(
            node_id="engineering",
            label="Engineering workstation",
            ip="10.2.0.40",
            role="engineering",
        ),
    ]
    blocks: list[RegisterBlock] = []
    address = 0
    for train in range(trains):
        node_id = f"plc{train + 1}"
        nodes.append(
            NetworkNode(
                node_id=node_id,
                label=f"Train {train + 1} PLC",
                ip=f"10.2.1.{train + 11}",
                role="plc",
            )
        )
        readable: list[str] = []
        writable: list[str] = []
        for stage in range(stages):
            readable.append(tags[(LEVEL, train, stage)])
            if metered[(train, stage)]:
                readable.append(tags[(INFLOW, train, stage)])
            readable.append(tags[(PUMP_SPEED, train, stage)])
            writable.append(tags[(LEVEL_SETPOINT, train, stage)])
        if train == 0:
            readable.append(tags[(OUTFLOW, 0, stages)])
        blocks.append(
            RegisterBlock(node_id=node_id, start_address=address, signals=tuple(readable))
        )
        address += len(readable)
        blocks.append(
            RegisterBlock(
                node_id=node_id, start_address=address, signals=tuple(writable), writable=True
            )
        )
        address += len(writable)
    return ControlNetwork(
        nodes=tuple(nodes),
        blocks=tuple(blocks),
        poller="scada",
        operator="hmi",
        poll_interval_seconds=parameters["scan_period_s"],
    )


def _authority(tags: dict[tuple[str, int, int], str]) -> WriteAuthority:
    """Return who may write what: the operator's HMI, and the setpoints only.

    The engineering workstation is declared on the network and granted nothing. That is the
    unknown-master shape ADR 0027 measures: a write from it is from a device that never issued a
    command in the baseline, which is a different thing from an unexpected write from the SCADA
    server, and the two are scored apart.
    """
    setpoints = frozenset(tag for (role, _, _), tag in tags.items() if role == LEVEL_SETPOINT)
    return WriteAuthority(grants={"hmi": setpoints})


def _disturbance(
    draw: StreamDraw,
    limits: Mapping[str, ParameterBound],
    parameters: dict[str, float],
    trains: int,
    tags: dict[tuple[str, int, int], str],
) -> DisturbanceSpec:
    """Draw what normally happens to this plant, and how far apart."""
    gap_low = round(bounded(draw, limits, "event_gap_low_steps"))
    gap_high = gap_low + round(bounded(draw, limits, "event_gap_span_steps"))
    surge = bounded(draw, limits, "surge_fraction")
    surge_steps = round(bounded(draw, limits, "surge_steps"))
    span = parameters["level_span_m"]
    middle = parameters["level_setpoint_fraction"]

    plans: list[EventPlanSpec] = []
    for train in range(trains):
        setpoint_tag = tags[(LEVEL_SETPOINT, train, 0)]
        plans.append(
            EventPlanSpec(
                kind=_SETPOINT_CHANGE,
                label=f"Operator moves train {train + 1}'s first level setpoint",
                duration_steps=0,
                writes=(setpoint_tag,),
                parameter_ranges={
                    setpoint_tag: (
                        span * max(0.15, middle - 0.12),
                        span * min(0.9, middle + 0.12),
                    )
                },
                detail=f"new level setpoint on train {train + 1}:",
            )
        )
        plans.append(
            EventPlanSpec(
                kind=DEMAND_SURGE,
                label="Downstream demand rises for a while",
                duration_steps=surge_steps,
                parameter_ranges={"demand_surge_fraction": (surge * 0.4, surge)},
                detail="demand raised by a fraction of:",
            )
        )
    return DisturbanceSpec(
        event_plans=tuple(plans),
        first_start_floor=30,
        first_start_divisor=12,
        gap_steps=(gap_low, gap_high),
    )


register_family(LevelFlowFamily())

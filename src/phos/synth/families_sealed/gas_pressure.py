"""A gas pressure network: compressible inventory, square-law transport, and a delayed loop.

PART R2's sealed example. The process is a pipeline of segments fed by one compressor and drawn on
at the far end. Three things about it are unlike anything in the open families, which is the whole
reason it is the one held back:

* **The inventory is compressible.** A tank's level is its contents. A pipeline segment's pressure
  *is* its contents — raise the pressure and you have put more gas in the same steel. The line
  "packs" and "unpacks", so the network stores energy in a way no liquid plant does.
* **Transport is square-law in pressure, not linear in anything.** Flow between two segments
  follows the difference of the *squares* of their pressures, so the same 2-bar drop moves very
  different amounts of gas at 10 bar and at 40 bar. A detector that learned a linear relationship
  between adjacent pressures has learned something false.
* **The controlled variable is at the far end of the line.** The compressor holds the *delivery*
  pressure, several segments downstream of itself, so every correction arrives after the whole
  line has repacked. That is a genuinely slow loop with real dead time, and it is the shape that
  makes a slow sensor-spoofing attack hardest to tell from ordinary operation.

**What this is not.** A model of a gas network written from the general shape of one — not a model
of any particular network, and not validated against one. See ``MODEL_NOT_REALITY_CAVEAT``.
"""

import math
from collections.abc import Mapping, Sequence
from typing import Final

from numpy.random import Generator

from phos.synth.command import CommandSource
from phos.synth.families import BoundScale, ParameterBound, PlantFamily, bounded, register_family
from phos.synth.plant import (
    BenignEvent,
    Coupling,
    CouplingKind,
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
from phos.synth.plants.spec_build import (
    RolePosition,
    draw_naming_scheme,
    modbus_network,
    operator_authority,
    render_tags,
    roles_from_tags,
)
from phos.synth.process import clamp, cycle_factor, first_order
from phos.synth.randomise import StreamDraw
from phos.synth.realism import RealismProfile
from phos.synth.templates import register_template

__all__ = [
    "GAS_PRESSURE_BOUNDS",
    "GAS_PRESSURE_PROCESS",
    "GasPressureFamily",
    "GasPressurePlant",
]

GAS_PRESSURE_PROCESS: Final = "gas-pressure-v1"
"""The name a spec puts in its ``process`` field to run on this physics."""

SEGMENT_PRESSURE: Final = "segment_pressure"
SUCTION_PRESSURE: Final = "suction_pressure"
COMPRESSOR_SPEED: Final = "compressor_speed"
PRESSURE_SETPOINT: Final = "pressure_setpoint"
FLOW: Final = "flow"
"""The role vocabulary this process reads."""

OFFTAKE_CHANGE: Final = "offtake_change"
"""A benign event: a customer's draw at the end of the line steps up or down."""

_SETPOINT_CHANGE: Final = "delivery_setpoint_change"
_COMPRESSOR_LOOP: Final = "delivery_pressure"
_PREFIXES: Final = ("", "GN", "PIPE", "CS", "TX")


class GasPressurePlant(Plant):
    """A pipeline of segments fed by one compressor, sized and tuned by its spec.

    See the module docstring for the three properties that make this process different from the
    open families.
    """

    def __init__(
        self,
        spec: RunSpec,
        *,
        commands: CommandSource | None = None,
        realism: RealismProfile | None = None,
        plant_spec: PlantSpec | None = None,
    ) -> None:
        """Build the network and its loop for one run.

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
                "GasPressurePlant has no default plant: it is a process, not a plant. Draw one "
                "from the sealed gas_pressure family, or build a spec by hand."
            )
        self._plant_spec = plant_spec
        self._description = plant_spec.describe()
        p = plant_spec.parameters
        self._segments = round(p["segments"])
        self._pack_bar_per_kg = p["pack_bar_per_kg"]
        self._conductance = p["conductance_kgph_per_bar2"]
        self._suction_bar = p["suction_bar"]
        self._max_ratio = p["max_pressure_ratio"]
        self._compressor_tau_s = p["compressor_tau_s"]
        self._delivery_setpoint_bar = p["delivery_setpoint_bar"]
        self._pressure_span_bar = p["pressure_span_bar"]
        self._offtake_base_kgph = p["offtake_base_kgph"]
        self._offtake_daily_kgph = p["offtake_daily_kgph"]

        self._loop = pi_controller(plant_spec, _COMPRESSOR_LOOP)
        self._bias = plant_spec.controller(_COMPRESSOR_LOOP).bias
        super().__init__(spec, commands=commands, realism=realism)

    @property
    def description(self) -> PlantDescription:
        """What this network is, as the spec declared it."""
        return self._description

    def initial_state(self) -> Mapping[str, float]:
        """Start the line packed to a profile that carries the opening offtake.

        Working backwards from the delivery setpoint through the square-law transport, so the run
        opens on a line that is already in balance rather than one the compressor has to fill.
        """
        offtake = self._offtake(0.0, None)
        pressures = self._steady_profile(offtake)
        state: dict[str, float] = {
            self._tag(SUCTION_PRESSURE): self._suction_bar,
            self._tag(COMPRESSOR_SPEED): self._speed_for(pressures[0]),
            self._tag(PRESSURE_SETPOINT): self._delivery_setpoint_bar,
        }
        for segment in range(self._segments):
            state[self._tag(SEGMENT_PRESSURE, segment)] = pressures[segment]
            state[self._tag(FLOW, segment)] = offtake
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
        """Apply the lasting part of an event: a moved delivery pressure setpoint."""
        for key, value in event.parameters.items():
            role = self._plant_spec.role_of(key)
            if role is not None and role.role == PRESSURE_SETPOINT and key in self._state:
                self._state[key] = value

    def control(
        self,
        report: Mapping[str, float],
        active: BenignEvent | None,
        elapsed_hours: float,
        dt_seconds: float,
    ) -> Mapping[str, float]:
        """Run the compressor loop on the pressure at the *far end* of the line."""
        delivery = report[self._tag(SEGMENT_PRESSURE, self._segments - 1)]
        return {
            self._tag(COMPRESSOR_SPEED): self._loop.update(
                measurement=delivery,
                setpoint=report[self._tag(PRESSURE_SETPOINT)],
                dt_seconds=dt_seconds,
                bias=self._bias,
            )
        }

    def advance(
        self,
        state: Mapping[str, float],
        actuators: Mapping[str, float],
        active: BenignEvent | None,
        elapsed_hours: float,
        dt_seconds: float,
    ) -> Mapping[str, float]:
        """Advance the line one sample: the compressor, then every segment's pack."""
        offtake = self._offtake(elapsed_hours, active)
        speed = clamp(actuators[self._tag(COMPRESSOR_SPEED)], 0.0, 100.0)
        discharge_target = self._suction_bar * (1.0 + (self._max_ratio - 1.0) * speed / 100.0)

        pressures = [state[self._tag(SEGMENT_PRESSURE, s)] for s in range(self._segments)]
        # The compressor's own discharge pressure follows its speed with a lag; everything
        # downstream of it is the line repacking, which is what makes the loop slow.
        inlet = first_order(
            pressures[0],
            target=discharge_target,
            dt_seconds=dt_seconds,
            tau_seconds=self._compressor_tau_s,
        )
        flows = [
            _square_law(pressures[index], pressures[index + 1], self._conductance)
            for index in range(self._segments - 1)
        ]
        flows.append(offtake)

        advanced: dict[str, float] = {
            self._tag(SUCTION_PRESSURE): self._suction_bar,
            self._tag(COMPRESSOR_SPEED): speed,
            self._tag(PRESSURE_SETPOINT): state[self._tag(PRESSURE_SETPOINT)],
        }
        for segment in range(self._segments):
            incoming = inlet_flow = (
                _square_law(inlet, pressures[0], self._conductance)
                if segment == 0
                else flows[segment - 1]
            )
            del inlet_flow
            change = (incoming - flows[segment]) * self._pack_bar_per_kg * dt_seconds / 3600.0
            advanced[self._tag(SEGMENT_PRESSURE, segment)] = clamp(
                pressures[segment] + change, 0.1, self._pressure_span_bar
            )
            advanced[self._tag(FLOW, segment)] = flows[segment]
        return advanced

    def _steady_profile(self, offtake: float) -> list[float]:
        """Return the pressure in every segment that carries this offtake in balance.

        Worked from the delivery end backwards: each segment upstream has to be higher by whatever
        the square law needs to push the offtake through. Inverting the transport rather than
        guessing a profile is what lets a run open settled.
        """
        pressures = [self._delivery_setpoint_bar]
        for _ in range(self._segments - 1):
            downstream = pressures[-1]
            needed = (offtake / max(self._conductance, 1e-9)) ** 2
            pressures.append(math.sqrt(downstream * downstream + needed))
        pressures.reverse()
        return [clamp(value, 0.1, self._pressure_span_bar) for value in pressures]

    def _offtake(self, elapsed_hours: float, active: BenignEvent | None) -> float:
        """Return the draw at the end of the line: a daily rhythm, stepped by a customer."""
        swing = cycle_factor(
            elapsed_hours,
            period_hours=24.0,
            amplitude=self._offtake_daily_kgph,
            phase_hours=7.0,
        )
        offtake = self._offtake_base_kgph + swing
        if active is not None and active.kind == OFFTAKE_CHANGE:
            offtake *= 1.0 + active.parameters.get("offtake_fraction", 0.0)
        return max(offtake, self._offtake_base_kgph * 0.05)

    def _speed_for(self, discharge_bar: float) -> float:
        """Return the compressor speed whose discharge pressure is this, inverting the ratio."""
        ratio = discharge_bar / max(self._suction_bar, 1e-9)
        return clamp(100.0 * (ratio - 1.0) / max(self._max_ratio - 1.0, 1e-9), 0.0, 100.0)

    def _tag(self, role: str, stage: int = 0) -> str:
        """Return the tag name playing a role, which the spec drew and this class never guesses."""
        return self._plant_spec.tag(role, train=0, stage=stage)


def _square_law(upstream_bar: float, downstream_bar: float, conductance: float) -> float:
    """Return the flow from one segment to the next, square-law in pressure.

    ``Q = k * sqrt(P_up^2 - P_down^2)``, and zero when the downstream pressure is the higher of
    the two: gas does not flow uphill in this model, and a negative square root is not a
    direction, it is a mistake.
    """
    difference = upstream_bar * upstream_bar - downstream_bar * downstream_bar
    if difference <= 0.0:
        return 0.0
    return conductance * math.sqrt(difference)


GAS_PRESSURE_BOUNDS: Final = (
    ParameterBound(
        "segments",
        2,
        5,
        BoundScale.INTEGER,
        "",
        "How many pipeline segments the line is divided into. More segments means more dead time "
        "between the compressor and the pressure it is holding.",
    ),
    ParameterBound(
        "pack_bar_per_kg",
        2e-5,
        2e-3,
        BoundScale.LOG,
        "bar/kg",
        "How much a segment's pressure rises per kilogram of gas put into it — the inverse of its "
        "line-pack capacity. A long large-bore segment sits at the bottom of this range.",
    ),
    ParameterBound(
        "conductance_kgph_per_bar2",
        20.0,
        900.0,
        BoundScale.LOG,
        "kg/h/bar2",
        "Transport coefficient between segments. Flow follows the difference of the squares of "
        "the pressures, so this is not a resistance in the electrical sense and the same pressure "
        "drop moves very different amounts of gas at different line pressures.",
    ),
    ParameterBound(
        "suction_bar",
        2.0,
        20.0,
        BoundScale.LOG,
        "bar",
        "Pressure at the compressor's inlet, held by whatever is upstream of this network.",
    ),
    ParameterBound(
        "max_pressure_ratio",
        1.4,
        3.2,
        BoundScale.LINEAR,
        "",
        "Compression ratio at full speed. With the suction pressure this is the highest discharge "
        "pressure the machine can reach, and so whether the delivery setpoint is reachable.",
    ),
    ParameterBound(
        "compressor_tau_s",
        5.0,
        90.0,
        BoundScale.LOG,
        "s",
        "How long the compressor takes to reach a new discharge pressure after a speed change. "
        "Fast compared with the line, which is the point: the delay the loop fights is the pipe, "
        "not the machine.",
    ),
    ParameterBound(
        "delivery_margin",
        1.08,
        1.6,
        BoundScale.LINEAR,
        "",
        "Delivery pressure setpoint as a multiple of suction pressure. Drawn as a ratio so it is "
        "always reachable in principle — whether it is reachable against the drawn offtake and "
        "conductance is PART R3's question.",
    ),
    ParameterBound(
        "pressure_headroom",
        1.25,
        1.9,
        BoundScale.LINEAR,
        "",
        "How far above the compressor's maximum discharge the transmitters are calibrated.",
    ),
    ParameterBound(
        "offtake_fraction_of_capacity",
        0.15,
        0.70,
        BoundScale.LINEAR,
        "",
        "Mean customer draw as a fraction of what the line can carry at full compression. The "
        "offtake itself is derived from it, because kilograms per hour means nothing without "
        "knowing the pipe.",
    ),
    ParameterBound(
        "offtake_daily_fraction",
        0.05,
        0.45,
        BoundScale.LINEAR,
        "",
        "How far the draw swings over a day, as a fraction of its mean. Gas networks swing hard: "
        "a cold morning is not a small perturbation.",
    ),
    ParameterBound(
        "pressure_gain",
        5.0,
        60.0,
        BoundScale.LOG,
        "%/bar",
        "Proportional gain of the compressor loop.",
    ),
    ParameterBound(
        "pressure_integral_s",
        120.0,
        1800.0,
        BoundScale.LOG,
        "s",
        "Integral time of the compressor loop. It has to be patient: it is holding a pressure "
        "several segments away from the machine it is driving.",
    ),
    ParameterBound(
        "speed_bias_pct",
        20.0,
        70.0,
        BoundScale.LINEAR,
        "%",
        "Compressor speed the loop starts from before its own terms.",
    ),
    ParameterBound(
        "pressure_noise_fraction",
        0.0005,
        0.01,
        BoundScale.LOG,
        "",
        "Measurement noise on every pressure transmitter, as a fraction of the calibrated span.",
    ),
    ParameterBound(
        "pressure_drift_fraction",
        0.0002,
        0.006,
        BoundScale.LOG,
        "",
        "Bound on each pressure transmitter's slow calibration drift.",
    ),
    ParameterBound(
        "flow_noise_fraction",
        0.002,
        0.03,
        BoundScale.LOG,
        "",
        "Measurement noise on every flow meter, as a fraction of mean offtake.",
    ),
    ParameterBound(
        "speed_noise_pct",
        0.01,
        0.5,
        BoundScale.LOG,
        "%",
        "Measurement noise on the reported compressor speed.",
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
        60,
        500,
        BoundScale.INTEGER,
        "samples",
        "Shortest quiet stretch between two benign events.",
    ),
    ParameterBound(
        "event_gap_span_steps",
        300,
        2500,
        BoundScale.INTEGER,
        "samples",
        "How much longer the longest quiet stretch may be than the shortest.",
    ),
    ParameterBound(
        "offtake_step_fraction",
        0.1,
        0.5,
        BoundScale.LINEAR,
        "",
        "How far a customer's draw steps while it lasts.",
    ),
    ParameterBound(
        "offtake_step_steps",
        60,
        600,
        BoundScale.INTEGER,
        "samples",
        "How long a customer's offtake change lasts.",
    ),
)
"""Everything the sealed `gas_pressure` family varies.

Not rendered into ``docs/sim/README.md``: a sealed family's bounds are not published, because the
public table is read by whoever is being examined on it."""


class GasPressureFamily(PlantFamily):
    """Gas pressure networks. **Sealed** — see `phos.synth.families_sealed`."""

    @property
    def family_id(self) -> str:
        """The identifier this family is drawn by."""
        return "gas_pressure"

    @property
    def label(self) -> str:
        """Human-readable name."""
        return "Gas pressure network"

    @property
    def process(self) -> str:
        """The physics every plant from this family runs on."""
        return GAS_PRESSURE_PROCESS

    @property
    def industry(self) -> str:
        """The sector this process belongs to."""
        return "gas transmission"

    @property
    def summary(self) -> str:
        """What the process does, for a reader who is not an engineer."""
        return (
            "A pipeline fed by one compressor and drawn on at the far end. The gas in the pipe is "
            "the inventory — raising the pressure puts more gas in the same steel — and the "
            "compressor is holding a pressure several segments downstream of itself, so every "
            "correction arrives only after the whole line has repacked."
        )

    @property
    def sealed(self) -> bool:
        """``True``. This family is absent from the default registry and from every listing."""
        return True

    def bounds(self) -> tuple[ParameterBound, ...]:
        """Return everything this family varies, and the range it varies it over."""
        return GAS_PRESSURE_BOUNDS

    def draw(self, master_seed: int) -> PlantSpec:
        """Draw one gas pressure network.

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

        segments = round(bounded(structure, limits, "segments"))
        parameters = _parameters(sizing, tuning, instruments, limits, segments)
        scheme = draw_naming_scheme(naming, _PREFIXES)
        tags = render_tags(scheme, _positions(segments))

        return PlantSpec(
            plant_id=f"gas-pressure-{master_seed}",
            label=f"Gas pressure network, {segments} segment(s)",
            industry=self.industry,
            summary=self.summary,
            model_source=(
                f"Drawn by phos.synth.families_sealed from the {self.family_id} family at master "
                f"seed {master_seed}. A model of a gas transmission line built from line-pack "
                "inventory, square-law transport between segments and a PI compressor loop on "
                "delivery pressure. Not a model of any particular network and not validated "
                "against one."
            ),
            process=self.process,
            parameters=parameters,
            units=_units(segments),
            signals=_signals(parameters, segments, tags),
            components=_components(segments, tags),
            connections=_connections(segments),
            controllers=_controllers(parameters, segments, tags),
            couplings=_couplings(segments, tags),
            control_network=modbus_network(
                poll_interval_seconds=parameters["scan_period_s"],
                subnet="10.12",
                per_plc=_register_plan(segments, tags),
            ),
            write_authority=operator_authority(tags, (PRESSURE_SETPOINT,)),
            disturbance=_disturbance(events, limits, parameters, tags),
            roles=roles_from_tags(tags),
        )


def _parameters(
    sizing: StreamDraw,
    tuning: StreamDraw,
    instruments: StreamDraw,
    limits: Mapping[str, ParameterBound],
    segments: int,
) -> dict[str, float]:
    """Draw the line, the compressor, the tuning and the instruments."""
    pack = bounded(sizing, limits, "pack_bar_per_kg")
    conductance = bounded(sizing, limits, "conductance_kgph_per_bar2")
    suction = bounded(sizing, limits, "suction_bar")
    ratio = bounded(sizing, limits, "max_pressure_ratio")
    margin = bounded(sizing, limits, "delivery_margin")
    headroom = bounded(sizing, limits, "pressure_headroom")
    capacity_fraction = bounded(sizing, limits, "offtake_fraction_of_capacity")
    daily_fraction = bounded(sizing, limits, "offtake_daily_fraction")

    max_discharge = suction * ratio
    delivery = min(suction * margin, max_discharge * 0.95)
    # What the line can carry at full compression, from the square law across one segment. The
    # offtake is a fraction of it, because kilograms per hour means nothing without the pipe.
    capacity = conductance * math.sqrt(
        max(max_discharge * max_discharge - delivery * delivery, 1e-9)
    )
    offtake = capacity * capacity_fraction

    return {
        "segments": float(segments),
        "pack_bar_per_kg": pack,
        "conductance_kgph_per_bar2": conductance,
        "suction_bar": suction,
        "max_pressure_ratio": ratio,
        "delivery_margin": margin,
        "delivery_setpoint_bar": delivery,
        "pressure_headroom": headroom,
        "pressure_span_bar": max_discharge * headroom,
        "compressor_tau_s": bounded(sizing, limits, "compressor_tau_s"),
        "offtake_fraction_of_capacity": capacity_fraction,
        "line_capacity_kgph": capacity,
        "offtake_base_kgph": offtake,
        "offtake_daily_fraction": daily_fraction,
        "offtake_daily_kgph": offtake * daily_fraction,
        "pressure_gain": bounded(tuning, limits, "pressure_gain"),
        "pressure_integral_s": bounded(tuning, limits, "pressure_integral_s"),
        "speed_bias_pct": bounded(tuning, limits, "speed_bias_pct"),
        "pressure_noise_fraction": bounded(instruments, limits, "pressure_noise_fraction"),
        "pressure_drift_fraction": bounded(instruments, limits, "pressure_drift_fraction"),
        "flow_noise_fraction": bounded(instruments, limits, "flow_noise_fraction"),
        "speed_noise_pct": bounded(instruments, limits, "speed_noise_pct"),
        "scan_period_s": bounded(instruments, limits, "scan_period_s"),
    }


def _positions(segments: int) -> tuple[tuple[RolePosition, str], ...]:
    """Return every role position this plant has, with the unit its signal carries."""
    positions: list[tuple[RolePosition, str]] = [
        ((SUCTION_PRESSURE, 0, 0), "bar"),
        ((COMPRESSOR_SPEED, 0, 0), "pct"),
        ((PRESSURE_SETPOINT, 0, 0), "bar"),
    ]
    for segment in range(segments):
        positions.append(((SEGMENT_PRESSURE, 0, segment), "bar"))
        positions.append(((FLOW, 0, segment), "kg/h"))
    return tuple(positions)


def segment_unit(segment: int) -> str:
    """Return the physical unit identifier one pipeline segment's instruments sit on."""
    return f"segment{segment + 1}"


def _units(segments: int) -> tuple[PhysicalUnit, ...]:
    """Return the compressor station and one unit per pipeline segment."""
    units = [PhysicalUnit(unit_id="station", label="Compressor station")]
    units.extend(
        PhysicalUnit(unit_id=segment_unit(segment), label=f"Pipeline segment {segment + 1}")
        for segment in range(segments)
    )
    return tuple(units)


def _signals(
    parameters: Mapping[str, float], segments: int, tags: Mapping[RolePosition, str]
) -> tuple[SignalSpec, ...]:
    """Return the instruments, with the spans and noise this plant was drawn with."""
    span = parameters["pressure_span_bar"]
    noise = parameters["pressure_noise_fraction"] * span
    drift = parameters["pressure_drift_fraction"] * span
    offtake = parameters["offtake_base_kgph"]
    flow_noise = parameters["flow_noise_fraction"] * offtake
    signals = [
        SignalSpec(
            key=tags[(SUCTION_PRESSURE, 0, 0)],
            label="Compressor suction pressure",
            unit="bar",
            kind=SignalKind.SENSOR,
            physical_unit="station",
            low=0.0,
            high=span,
            noise_stddev=noise,
            drift_amplitude=drift,
        ),
        SignalSpec(
            key=tags[(COMPRESSOR_SPEED, 0, 0)],
            label="Compressor speed",
            unit="%",
            kind=SignalKind.ACTUATOR,
            physical_unit="station",
            low=0.0,
            high=100.0,
            noise_stddev=parameters["speed_noise_pct"],
        ),
        SignalSpec(
            key=tags[(PRESSURE_SETPOINT, 0, 0)],
            label="Delivery pressure setpoint",
            unit="bar",
            kind=SignalKind.SETPOINT,
            physical_unit="station",
            low=0.0,
            high=span,
            noise_stddev=0.0,
        ),
    ]
    for segment in range(segments):
        unit = segment_unit(segment)
        signals.append(
            SignalSpec(
                key=tags[(SEGMENT_PRESSURE, 0, segment)],
                label=f"Segment {segment + 1} pressure",
                unit="bar",
                kind=SignalKind.SENSOR,
                physical_unit=unit,
                low=0.0,
                high=span,
                noise_stddev=noise,
                drift_amplitude=drift,
            )
        )
        signals.append(
            SignalSpec(
                key=tags[(FLOW, 0, segment)],
                label=f"Segment {segment + 1} outlet flow",
                unit="kg/h",
                kind=SignalKind.SENSOR,
                physical_unit=unit,
                low=0.0,
                high=max(parameters["line_capacity_kgph"] * 1.5, offtake * 3.0),
                noise_stddev=flow_noise,
                drift_amplitude=flow_noise * 0.5,
            )
        )
    return tuple(signals)


def _components(segments: int, tags: Mapping[RolePosition, str]) -> tuple[Component, ...]:
    """Return what the network is made of, with every signal owned exactly once."""
    components = [
        Component(
            component_id="upstream",
            kind=ComponentKind.SOURCE,
            label="Upstream supply",
            physical_unit="station",
            signals=(tags[(SUCTION_PRESSURE, 0, 0)],),
            description="Whatever feeds this network. Its pressure is held from outside.",
        ),
        Component(
            component_id="compressor",
            kind=ComponentKind.PUMP,
            label="Compressor",
            physical_unit="station",
            signals=(tags[(COMPRESSOR_SPEED, 0, 0)],),
            description=(
                "Raises the gas from suction to line pressure. The only handle the network has, "
                "and it is at the opposite end of the line from the pressure it is holding."
            ),
        ),
        Component(
            component_id="delivery_loop",
            kind=ComponentKind.CONTROLLER,
            label="Delivery pressure target",
            physical_unit="station",
            signals=(tags[(PRESSURE_SETPOINT, 0, 0)],),
            description="The pressure the far end of the line is supposed to hold.",
        ),
    ]
    for segment in range(segments):
        components.append(
            Component(
                component_id=f"segment_{segment}",
                kind=ComponentKind.PIPE,
                label=f"Pipeline segment {segment + 1}",
                physical_unit=segment_unit(segment),
                signals=(
                    tags[(SEGMENT_PRESSURE, 0, segment)],
                    tags[(FLOW, 0, segment)],
                ),
                description=(
                    "A length of pipe. Its pressure is its contents: push more gas in and the "
                    "pressure rises, which is how the line stores and releases gas."
                ),
            )
        )
    components.append(
        Component(
            component_id="offtake",
            kind=ComponentKind.LOAD,
            label="Customer offtake",
            physical_unit=segment_unit(segments - 1),
            description="The draw at the end of the line. Nothing here decides it.",
        )
    )
    return tuple(components)


def _connections(segments: int) -> tuple[Connection, ...]:
    """Return which way the gas goes."""
    connections = [
        Connection(
            source="upstream", target="compressor", medium="gas", label="supply to the compressor"
        ),
        Connection(
            source="compressor", target="segment_0", medium="gas", label="discharge into the line"
        ),
        Connection(
            source="delivery_loop",
            target="compressor",
            medium="signal",
            label="delivery target drives compressor speed",
        ),
    ]
    for segment in range(segments - 1):
        connections.append(
            Connection(
                source=f"segment_{segment}",
                target=f"segment_{segment + 1}",
                medium="gas",
                label="segment to the next, square-law in pressure",
            )
        )
    connections.append(
        Connection(
            source=f"segment_{segments - 1}",
            target="offtake",
            medium="gas",
            label="line to the customer",
        )
    )
    return tuple(connections)


def _controllers(
    parameters: Mapping[str, float], segments: int, tags: Mapping[RolePosition, str]
) -> tuple[ControllerSpec, ...]:
    """Return the one loop: the compressor, holding the pressure at the far end of the line."""
    return (
        ControllerSpec(
            controller_id=_COMPRESSOR_LOOP,
            kind=ControllerKind.PI,
            measurement=tags[(SEGMENT_PRESSURE, 0, segments - 1)],
            setpoint=tags[(PRESSURE_SETPOINT, 0, 0)],
            output=tags[(COMPRESSOR_SPEED, 0, 0)],
            gain=parameters["pressure_gain"],
            integral_time_seconds=parameters["pressure_integral_s"],
            low=0.0,
            high=100.0,
            bias=parameters["speed_bias_pct"],
            description=(
                "Holds the delivery pressure at the far end of the line by varying the "
                "compressor at the near end. Every correction arrives after the line has "
                "repacked, which is why its integral time is long."
            ),
        ),
    )


def _couplings(segments: int, tags: Mapping[RolePosition, str]) -> tuple[Coupling, ...]:
    """Return the network's claim about what makes its signals related."""
    couplings: list[Coupling] = [
        Coupling(
            driven=tags[(COMPRESSOR_SPEED, 0, 0)],
            drivers=(
                tags[(SEGMENT_PRESSURE, 0, segments - 1)],
                tags[(PRESSURE_SETPOINT, 0, 0)],
            ),
            kind=CouplingKind.CONTROL,
            relation="a PI loop holds the delivery pressure by varying the compressor",
        )
    ]
    for segment in range(segments):
        upstream = (
            tags[(COMPRESSOR_SPEED, 0, 0)]
            if segment == 0
            else tags[(SEGMENT_PRESSURE, 0, segment - 1)]
        )
        couplings.append(
            Coupling(
                driven=tags[(SEGMENT_PRESSURE, 0, segment)],
                drivers=(upstream, tags[(FLOW, 0, segment)]),
                kind=CouplingKind.INTEGRATION,
                relation=(
                    "pressure is the running total of gas put into this segment less gas taken "
                    "out of it — the line packing and unpacking"
                ),
            )
        )
        if segment + 1 < segments:
            couplings.append(
                Coupling(
                    driven=tags[(FLOW, 0, segment)],
                    drivers=(
                        tags[(SEGMENT_PRESSURE, 0, segment)],
                        tags[(SEGMENT_PRESSURE, 0, segment + 1)],
                    ),
                    kind=CouplingKind.ALGEBRAIC,
                    relation=(
                        "flow follows the square root of the difference of the squares of the two "
                        "pressures, which is not linear in either"
                    ),
                )
            )
    return tuple(couplings)


def _register_plan(
    segments: int, tags: Mapping[RolePosition, str]
) -> tuple[tuple[list[str], list[str]], ...]:
    """Return what the station PLC exposes read-only, and what an operator may write."""
    readable = [tags[(SUCTION_PRESSURE, 0, 0)], tags[(COMPRESSOR_SPEED, 0, 0)]]
    for segment in range(segments):
        readable.append(tags[(SEGMENT_PRESSURE, 0, segment)])
        readable.append(tags[(FLOW, 0, segment)])
    return ((readable, [tags[(PRESSURE_SETPOINT, 0, 0)]]),)


def _disturbance(
    draw: StreamDraw,
    limits: Mapping[str, ParameterBound],
    parameters: Mapping[str, float],
    tags: Mapping[RolePosition, str],
) -> DisturbanceSpec:
    """Draw what normally happens to this network, and how far apart."""
    gap_low = round(bounded(draw, limits, "event_gap_low_steps"))
    gap_high = gap_low + round(bounded(draw, limits, "event_gap_span_steps"))
    step = bounded(draw, limits, "offtake_step_fraction")
    step_steps = round(bounded(draw, limits, "offtake_step_steps"))
    target = tags[(PRESSURE_SETPOINT, 0, 0)]
    delivery = parameters["delivery_setpoint_bar"]

    return DisturbanceSpec(
        event_plans=(
            EventPlanSpec(
                kind=OFFTAKE_CHANGE,
                label="Customer draw at the end of the line steps up or down",
                duration_steps=step_steps,
                parameter_ranges={"offtake_fraction": (-step, step)},
                detail="offtake moved by a fraction of:",
            ),
            EventPlanSpec(
                kind=_SETPOINT_CHANGE,
                label="Operator moves the delivery pressure setpoint",
                duration_steps=0,
                writes=(target,),
                parameter_ranges={target: (delivery * 0.96, delivery * 1.04)},
                detail="new delivery pressure setpoint:",
            ),
        ),
        first_start_floor=60,
        first_start_divisor=12,
        gap_steps=(gap_low, gap_high),
    )


register_template(GAS_PRESSURE_PROCESS, GasPressurePlant)
register_family(GasPressureFamily())

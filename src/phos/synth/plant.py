"""What a simulated plant is: a declared process, a true state, and two doors into it.

This module holds the interface every plant in `phos.synth.plants` implements, and — more
importantly — the discipline that interface enforces. A concrete plant supplies physics, control
loops and an event schedule. Everything that has to be *identical across plants* lives here, in
one base class, so that the properties D2 and D3 depend on are structural rather than a habit
three modules happen to share.

**The true-state record.** Every step records what the plant is actually doing, `TrueState`,
separately from what its instruments say, `SensorReport`. In normal operation the two agree up to
the declared sensor error model — noise and a bounded calibration drift — and nothing else. The
separation exists for an attack D1 does not build: D2's fabricated telemetry drives the true state
somewhere dangerous while the instruments report calm, and that can only be labelled honestly if
truth was recorded independently of the instruments from the very first sample. Retrofitting it
later would mean reconstructing truth from the reports it was supposed to be independent of.

**The two doors.** `Injection` is consulted twice per step, always, even when nothing is attached:
once before the physics with what the controllers commanded, once after it with what the
instruments measured. See `phos.synth.injection` for why that is two doors rather than one, and
for the contract that keeps a manipulated run from being separable by anything but the
manipulation.

**Controllers act on reports, never on truth.** Every loop is handed the previous step's
*reported* readings. That is how a real loop works — a controller has no oracle — and it is what
makes falsified telemetry physically consequential rather than a cosmetic edit.

**Randomness is drawn in exactly one place and at a constant rate.** One fixed-size block of
normal deviates per step, taken before anything can branch, plus one draw at construction for the
per-instrument drift characteristics and the benign-event schedule. A plant therefore cannot
consume a different amount of randomness because of what happened to it, which is what makes the
bit-identity property in `tests/synth/test_plant.py` provable rather than lucky.

**The standing caveat.** A plant here is a *model* of an industrial process, written from public
descriptions of how such processes behave. It is not a plant. Its realism is a claim to be
defended, and `PlantDescription.model_source` is where each one defends it. Results obtained on
this data describe how Atlas handles our model of a plant — a necessary step toward, and not
evidence of, handling a real one.
"""

import math
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from itertools import pairwise
from typing import Final, Self

import numpy
from numpy.random import Generator
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, Field, model_validator

from phos.ontology import UtcDatetime
from phos.synth.command import (
    CommandSource,
    IssuedCommand,
    NoCommands,
    PlannedWrite,
    WriteAuthority,
)
from phos.synth.injection import Injection, NoInjection
from phos.synth.process import clamp
from phos.synth.realism import RealismPlan, RealismProfile, plan_realism

__all__ = [
    "DRIFT_PERIOD_HOURS",
    "MAX_REGISTER_COUNT",
    "MODEL_NOT_REALITY_CAVEAT",
    "SYNTHETIC_DERIVED",
    "SYNTHETIC_DERIVED_BANNER",
    "BenignEvent",
    "CommandIntent",
    "CommandKind",
    "ControlNetwork",
    "Coupling",
    "CouplingKind",
    "EventPlan",
    "NetworkNode",
    "PhysicalUnit",
    "Plant",
    "PlantDescription",
    "PlantStep",
    "RegisterBlock",
    "RunSpec",
    "SensorReport",
    "SignalKind",
    "SignalSpec",
    "TrueState",
    "lay_out_events",
    "register_count",
]

MODEL_NOT_REALITY_CAVEAT: Final = (
    "A synthetic plant is a MODEL of an industrial process, not an industrial process. Its "
    "physics, its rhythms and its imperfections were written from public descriptions of how such "
    "processes behave, and its realism is a claim to be defended rather than a property to be "
    "assumed — PlantDescription.model_source is where each plant states what it was built from. A "
    "detection result measured on this data says that Atlas handles OUR MODEL of a plant. That is "
    "a necessary step toward handling a real one and is not evidence of it."
)
"""Travels with every dataset, manifest and report the synthetic engine produces."""

SYNTHETIC_DERIVED: Final = "SYNTHETIC-DERIVED"
"""Label for diagnostic output that cannot validate anything against its own assumptions."""

SYNTHETIC_DERIVED_BANNER: Final = (
    "SYNTHETIC-DERIVED DIAGNOSTIC — NOT A MEASUREMENT, NOT A DETECTION CLAIM"
)
"""The banner every U3 diagnostic report and sidecar must carry."""

MAX_REGISTER_COUNT: Final = 0xFFFF
"""Largest raw count a 16-bit instrument register can hold."""

_SECONDS_PER_HOUR: Final = 3600.0
DRIFT_PERIOD_HOURS: Final = (48.0, 120.0)
"""Range the per-instrument calibration-drift period is drawn from: two to five days.

Long against any run, so within a run the drift reads as the slow one-directional wander a real
transmitter shows between calibrations, and bounded by construction so the agreement between truth
and report stays provable.
"""


class SignalKind(str, Enum):
    """What a signal *is*, which decides what may be done to it.

    Attributes:
        SENSOR: An instrument's reading of a process variable. Cannot be written by anyone.
        ACTUATOR: The position of a final control element, as reported back. Written by a control
            loop, and the only kind an actuator injection may move.
        SETPOINT: A target held in a controller. Changed by an operator, which is a benign event
            and — where the plant has a control network — a write on the wire.
    """

    SENSOR = "SENSOR"
    ACTUATOR = "ACTUATOR"
    SETPOINT = "SETPOINT"


class CouplingKind(str, Enum):
    """How one signal depends on others, named so a test can assert the right thing about it.

    Attributes:
        INTEGRATION: The driven signal accumulates its drivers — a level over net flow.
        LAG: The driven signal moves toward what its drivers imply, with a time constant.
        ALGEBRAIC: The driven signal is a direct function of its drivers at the same instant.
        CONTROL: The driven signal is a control loop's response to its drivers.
    """

    INTEGRATION = "INTEGRATION"
    LAG = "LAG"
    ALGEBRAIC = "ALGEBRAIC"
    CONTROL = "CONTROL"


class SignalSpec(BaseModel):
    """One instrumented quantity: what it is, where it sits, and how imperfectly it is measured.

    Attributes:
        key: The signal key. This is the CSV column, the `Observation.feature`, and the name the
            topology assigns to a physical unit — one string, so those three cannot drift apart.
        label: Human-readable name.
        unit: Engineering unit, e.g. ``"m3/h"``.
        kind: Sensor, actuator or setpoint.
        physical_unit: Identifier of the `PhysicalUnit` this signal is instrumented on. This is
            what makes the plant's topology a declaration rather than an inference.
        low: Bottom of the instrument's calibrated span. Readings are bounded by it, as a real
            transmitter's are.
        high: Top of the calibrated span.
        noise_stddev: Standard deviation of the instrument's measurement noise, in engineering
            units. Zero for a quantity read as a discrete register value.
        drift_amplitude: Bound on the instrument's slow calibration drift, in engineering units.
            The drift itself is a slow sinusoid whose period and phase are drawn once per run, so
            it is bounded by this figure at every instant.

    Invariants:
        ``low < high``, and both dispersion figures are non-negative.
    """

    model_config = ConfigDict(frozen=True)

    key: str = Field(min_length=1)
    label: str = Field(min_length=1)
    unit: str = Field(min_length=1)
    kind: SignalKind
    physical_unit: str = Field(min_length=1)
    low: float
    high: float
    noise_stddev: float = Field(ge=0.0)
    drift_amplitude: float = Field(default=0.0, ge=0.0)

    @model_validator(mode="after")
    def _check_span(self) -> Self:
        if self.low >= self.high:
            raise ValueError(
                f"signal {self.key!r} declares an empty span: low={self.low}, high={self.high}"
            )
        return self


class PhysicalUnit(BaseModel):
    """A piece of plant several instruments sit on — a tank, a filter, a transformer.

    Attributes:
        unit_id: Stable identifier, used as the subsystem id in the declared topology.
        label: Human-readable name, for the operator reading the topology listing.
    """

    model_config = ConfigDict(frozen=True)

    unit_id: str = Field(min_length=1)
    label: str = Field(min_length=1)


class Coupling(BaseModel):
    """A declared physical dependency of one signal on others.

    This is the part of a plant that makes its data worth generating. Signals that merely
    correlate can be produced by any random process; signals that are *coupled* move together
    because the process makes them, and it is that structure a joint model learns and D2's
    correlation-breaking attack will later try to violate. Declaring the couplings here rather
    than leaving them implicit in the physics does two things: it puts the plant's structure in
    the manifest where a reviewer can read it, and it lets `tests/synth/test_plants.py` check
    every declared dependency actually holds in the output.

    Attributes:
        driven: Signal key that depends on the others.
        drivers: Signal keys it depends on. At least one.
        kind: The shape of the dependency.
        relation: The dependency in words, specific enough to check by eye, e.g. ``"integrates
            raw_inflow_m3ph minus distribution_flow_m3ph"``.
    """

    model_config = ConfigDict(frozen=True)

    driven: str = Field(min_length=1)
    drivers: tuple[str, ...] = Field(min_length=1)
    kind: CouplingKind
    relation: str = Field(min_length=1)

    @model_validator(mode="after")
    def _check_not_self_driven(self) -> Self:
        if self.driven in self.drivers:
            raise ValueError(f"signal {self.driven!r} is declared as its own driver")
        return self


class NetworkNode(BaseModel):
    """One device on a plant's control network.

    Attributes:
        node_id: Stable identifier within the plant.
        label: Human-readable name.
        ip: The device's address, which is what `phos.atlas.packet` derives its entity id from.
        role: What the device does — ``"scada"``, ``"plc"``, ``"hmi"``. Descriptive only: Atlas
            infers no device type from traffic, and neither does this.
    """

    model_config = ConfigDict(frozen=True)

    node_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    ip: str = Field(min_length=1)
    role: str = Field(min_length=1)


class RegisterBlock(BaseModel):
    """A contiguous run of holding registers on one device, and the signals they carry.

    Attributes:
        node_id: The device hosting the registers.
        start_address: Address of the first register in the block.
        signals: Signal keys, in register order. One register each.
        writable: Whether an operator writes this block. Only setpoints and actuator commands are
            writable; a measurement is not something anyone can write.
    """

    model_config = ConfigDict(frozen=True)

    node_id: str = Field(min_length=1)
    start_address: int = Field(ge=0, le=MAX_REGISTER_COUNT)
    signals: tuple[str, ...] = Field(min_length=1)
    writable: bool = False


class ControlNetwork(BaseModel):
    """The control traffic a plant's process generates, declared rather than invented.

    Present only for plants whose real-world counterpart is actually run over the protocol Atlas
    can dissect. A plant that omits it produces telemetry and no capture, which is an honest
    statement about a process controlled over something else — and a useful one, because it gives
    D3 a plant where Atlas is deaf to commands by construction.

    Attributes:
        nodes: Every device on the network.
        blocks: The register map, block by block.
        poller: ``node_id`` of the device that cyclically reads the blocks.
        operator: ``node_id`` of the device an operator writes setpoints from.
        poll_interval_seconds: How often the poller reads every block.
        unit_id: Modbus unit identifier the devices answer on.

    Invariants:
        Node identifiers and addresses are unique; the poller and operator are declared nodes;
        register blocks do not overlap and name declared nodes.
    """

    model_config = ConfigDict(frozen=True)

    nodes: tuple[NetworkNode, ...] = Field(min_length=2)
    blocks: tuple[RegisterBlock, ...] = Field(min_length=1)
    poller: str = Field(min_length=1)
    operator: str = Field(min_length=1)
    poll_interval_seconds: float = Field(gt=0.0)
    unit_id: int = Field(default=1, ge=0, le=0xFF)

    @model_validator(mode="after")
    def _check_network(self) -> Self:
        ids = [node.node_id for node in self.nodes]
        if len(set(ids)) != len(ids):
            raise ValueError(f"control network declares a node identifier twice: {sorted(ids)}")
        addresses = [node.ip for node in self.nodes]
        if len(set(addresses)) != len(addresses):
            raise ValueError(f"control network declares an address twice: {sorted(addresses)}")
        for role, node_id in (("poller", self.poller), ("operator", self.operator)):
            if node_id not in ids:
                raise ValueError(f"{role} {node_id!r} is not a declared node")
        occupied: dict[int, str] = {}
        for block in self.blocks:
            if block.node_id not in ids:
                raise ValueError(f"register block names undeclared node {block.node_id!r}")
            for offset, signal in enumerate(block.signals):
                address = block.start_address + offset
                clash = occupied.get(address)
                if clash is not None:
                    raise ValueError(
                        f"register {address} on {block.node_id} is claimed by both {clash!r} and "
                        f"{signal!r}"
                    )
                occupied[address] = signal
        return self

    def node(self, node_id: str) -> NetworkNode:
        """Return the declared node with this identifier.

        Raises:
            KeyError: If no such node is declared.
        """
        for candidate in self.nodes:
            if candidate.node_id == node_id:
                return candidate
        raise KeyError(f"no node {node_id!r} on this control network")

    def address_of(self, signal: str) -> tuple[str, int]:
        """Return the ``(node_id, register address)`` a signal is exposed at.

        Raises:
            KeyError: If the signal is on no block, which means nothing on the wire carries it.
        """
        for block in self.blocks:
            for offset, key in enumerate(block.signals):
                if key == signal:
                    return block.node_id, block.start_address + offset
        raise KeyError(f"signal {signal!r} is on no register block")


class PlantDescription(BaseModel):
    """Everything about a plant that is a claim rather than a computation.

    A reviewer should be able to read this object and say whether the plant is plausible, without
    reading the physics — which is why the couplings and the topology are declared here rather
    than being implicit in the integration code.

    Attributes:
        plant_id: Stable identifier, used in dataset names and file paths.
        label: Human-readable name.
        industry: The sector this process belongs to, e.g. ``"water treatment"``.
        summary: What the process does, in a sentence or two.
        model_source: What the model was built from, named specifically. This is the plant's
            defence of its own realism and the counterpart of `phos.atlas.topology`'s ``source``.
        units: The physical units instruments sit on.
        signals: Every signal, in a fixed order that decides register and column order.
        couplings: The declared physical dependencies between signals.
        control_network: The control traffic the process generates, or ``None`` for a process
            controlled over something Atlas cannot dissect.
        write_authority: Which device the plant permits to write which signal. Declared, so that
            the authorisation recorded against a write is derived from policy rather than
            asserted by whatever produced the write. ``None`` means no policy was declared, which
            is not the same as "nobody may write": `Plant` refuses to record an authorisation it
            was never told, rather than defaulting a device to either answer.

    Invariants:
        Signal keys are unique; every signal sits on a declared unit; every declared unit carries
        at least one signal; couplings and register blocks reference declared signals; writable
        blocks hold no sensor; a declared write authority grants only declared, writable signals
        to declared nodes.
    """

    model_config = ConfigDict(frozen=True)

    plant_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    industry: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    model_source: str = Field(min_length=1)
    units: tuple[PhysicalUnit, ...] = Field(min_length=1)
    signals: tuple[SignalSpec, ...] = Field(min_length=2)
    couplings: tuple[Coupling, ...] = Field(min_length=1)
    control_network: ControlNetwork | None = None
    write_authority: WriteAuthority | None = None

    @model_validator(mode="after")
    def _check_declaration(self) -> Self:
        keys = [signal.key for signal in self.signals]
        if len(set(keys)) != len(keys):
            raise ValueError(f"plant {self.plant_id!r} declares a signal key twice: {sorted(keys)}")
        unit_ids = {unit.unit_id for unit in self.units}
        if len(unit_ids) != len(self.units):
            raise ValueError(f"plant {self.plant_id!r} declares a physical unit twice")
        known = set(keys)
        by_key = {signal.key: signal for signal in self.signals}

        for signal in self.signals:
            if signal.physical_unit not in unit_ids:
                raise ValueError(
                    f"signal {signal.key!r} sits on undeclared unit {signal.physical_unit!r}"
                )
        instrumented = {signal.physical_unit for signal in self.signals}
        bare = sorted(unit_ids - instrumented)
        if bare:
            raise ValueError(f"physical unit(s) carrying no signal: {', '.join(bare)}")

        for coupling in self.couplings:
            for referenced in (coupling.driven, *coupling.drivers):
                if referenced not in known:
                    raise ValueError(
                        f"coupling on {coupling.driven!r} references undeclared signal "
                        f"{referenced!r}"
                    )

        network = self.control_network
        if network is not None:
            for block in network.blocks:
                for key in block.signals:
                    if key not in known:
                        raise ValueError(f"register block references undeclared signal {key!r}")
                    if block.writable and by_key[key].kind is SignalKind.SENSOR:
                        raise ValueError(
                            f"writable register block carries sensor {key!r}; a measurement is not "
                            "something an operator can write"
                        )

        authority = self.write_authority
        if authority is not None:
            if network is None:
                raise ValueError(
                    f"plant {self.plant_id!r} declares a write authority but no control network; "
                    "there is nothing for a device to write over"
                )
            declared_nodes = {node.node_id for node in network.nodes}
            for node_id, granted in authority.grants.items():
                if node_id not in declared_nodes:
                    raise ValueError(
                        f"write authority grants to undeclared node {node_id!r}; a policy naming "
                        "a device the network does not have cannot authorise anything"
                    )
                for key in sorted(granted):
                    if key not in known:
                        raise ValueError(
                            f"write authority grants {node_id!r} undeclared signal {key!r}"
                        )
                    if by_key[key].kind is SignalKind.SENSOR:
                        raise ValueError(
                            f"write authority grants {node_id!r} sensor {key!r}; a measurement is "
                            "not something anyone can be permitted to write"
                        )
        return self

    def signal(self, key: str) -> SignalSpec:
        """Return the declared signal with this key.

        Raises:
            KeyError: If the plant declares no such signal.
        """
        for candidate in self.signals:
            if candidate.key == key:
                return candidate
        raise KeyError(f"plant {self.plant_id!r} declares no signal {key!r}")

    def signal_keys(self) -> tuple[str, ...]:
        """Return every signal key, in declaration order."""
        return tuple(signal.key for signal in self.signals)

    def keys_of_kind(self, kind: SignalKind) -> tuple[str, ...]:
        """Return the signal keys of one kind, in declaration order."""
        return tuple(signal.key for signal in self.signals if signal.kind is kind)


class RunSpec(BaseModel):
    """How long to run a plant for, how often to sample it, and from what seed.

    Attributes:
        seed: Seeds every random draw the run makes. Two runs with equal specs are identical
            (Constitution §3.7).
        start: First sample instant, UTC.
        duration: Wall-clock span to simulate.
        sample_interval: Spacing between samples. This is also the integration step, so dynamics
            faster than one interval are not represented — see the ADR.

    Invariants:
        Duration and interval are positive, and at least one sample fits in the duration.
    """

    model_config = ConfigDict(frozen=True)

    seed: int
    start: UtcDatetime
    duration: timedelta
    sample_interval: timedelta

    @model_validator(mode="after")
    def _check_span(self) -> Self:
        if self.duration <= timedelta(0):
            raise ValueError(f"duration must be positive, got {self.duration}")
        if self.sample_interval <= timedelta(0):
            raise ValueError(f"sample_interval must be positive, got {self.sample_interval}")
        if self.sample_interval > self.duration:
            raise ValueError(
                f"sample_interval {self.sample_interval} exceeds the {self.duration} run, so the "
                "run holds no samples"
            )
        return self

    @property
    def n_steps(self) -> int:
        """Number of samples the run produces."""
        return int(self.duration.total_seconds() // self.sample_interval.total_seconds())

    @property
    def interval_seconds(self) -> float:
        """Sample interval in seconds, which is also the integration step."""
        return self.sample_interval.total_seconds()

    def instant(self, index: int) -> datetime:
        """Return the timestamp of sample ``index``."""
        return self.start + index * self.sample_interval


class BenignEvent(BaseModel):
    """A legitimate operational event: a setpoint change, a startup, a backwash, a batch.

    These are what make synthetic data honestly difficult. A plant that only ever runs at one
    operating point is a plant where any change is an attack, which is a world detection is easy
    in and which does not exist. They are also the cover D2's mimic attack will need: an attacker
    who moves a setpoint is hiding among these, so the benign ones must be real and must be
    labelled, or the mimic has nothing to imitate and D3 cannot tell whether a detection landed on
    an attack or on a Tuesday morning shift change.

    Attributes:
        kind: Machine-readable class, e.g. ``"setpoint_change"``.
        label: Human-readable description of what happened.
        started_at: When it began, UTC. Always a sample instant.
        ended_at: When it finished, UTC. Equal to ``started_at`` for an instantaneous change.
        writes: Setpoint or actuator signals an operator wrote as part of this event. Where the
            plant has a control network these become writes on the wire, which is what ties the
            benign event in the telemetry to the benign event in the capture.
        parameters: Numbers the event carries — the new setpoint an operator dialled in, the size
            of a load step. Read by the plant's `begin_event`, and part of the ground truth D2 and
            D3 receive, so "what legitimately changed" is a number rather than a sentence to
            parse.
        detail: The specifics, e.g. ``"clearwell level setpoint 3.20 -> 3.60 m"``.

    Invariants:
        The window is not inverted.
    """

    model_config = ConfigDict(frozen=True)

    kind: str = Field(min_length=1)
    label: str = Field(min_length=1)
    started_at: UtcDatetime
    ended_at: UtcDatetime
    writes: tuple[str, ...] = ()
    parameters: dict[str, float] = Field(default_factory=dict)
    detail: str = ""

    @model_validator(mode="after")
    def _check_window(self) -> Self:
        if self.ended_at < self.started_at:
            raise ValueError(
                f"event {self.kind!r} is inverted: {self.started_at} > {self.ended_at}"
            )
        return self

    def contains(self, clock: datetime) -> bool:
        """Return whether ``clock`` falls inside the event, both bounds inclusive."""
        return self.started_at <= clock <= self.ended_at


class CommandKind(str, Enum):
    """What a control-network exchange was: a cyclic read, or an operator's write."""

    READ = "READ"
    WRITE = "WRITE"


@dataclass(frozen=True)
class EventPlan:
    """A kind of benign event a plant has, before it is placed anywhere in a run.

    Separating "what events this plant has" from "when they happened" keeps the schedule
    reproducible: the plans are static, and `lay_out_events` is the only thing that draws.

    Attributes:
        kind: Machine-readable class, e.g. ``"setpoint_change"``.
        label: Human-readable description.
        duration_steps: How many samples the event lasts. Zero for an instantaneous change.
        writes: Signals an operator writes as part of it.
        parameter_ranges: ``{name: (low, high)}`` drawn uniformly per occurrence — the new
            setpoint, the size of the step. Drawn rather than fixed so that two occurrences of one
            kind of event are not identical, which is what a mimic attack would otherwise only
            have to match once.
        detail: Prefix for the rendered detail line.
    """

    kind: str
    label: str
    duration_steps: int = 0
    writes: tuple[str, ...] = ()
    parameter_ranges: Mapping[str, tuple[float, float]] = field(default_factory=dict)
    detail: str = ""


def lay_out_events(
    rng: Generator,
    spec: RunSpec,
    plans: Sequence[EventPlan],
    first_start_step: int,
    gap_steps: tuple[int, int],
) -> tuple[BenignEvent, ...]:
    """Place a plant's event kinds through a run, round-robin, with random gaps between them.

    One function, shared by every plant, because the constraints are the same for all of them and
    are easy to get subtly wrong: events must not overlap (or "which event was in force" has two
    answers), must start on a sample instant (or nothing triggers them), and must be drawn from
    the setup generator rather than step by step (or the per-step randomness rate changes and the
    injection hook stops being invisible).

    Args:
        rng: The setup generator.
        spec: The run being scheduled over.
        plans: The event kinds, cycled in order.
        first_start_step: Sample index the first event may begin at. Non-zero so a run has some
            undisturbed operation to learn a baseline from.
        gap_steps: ``(low, high)`` samples of quiet between one event ending and the next
            beginning, drawn uniformly. The low bound must be at least one sample, or two events
            would abut and read as one.

    Returns:
        The events in time order. Empty when the run is too short to hold even the first one.

    Raises:
        ValueError: If the plans are empty, if the gap could be shorter than one sample, or if
            the first start is before the run.
    """
    if not plans:
        raise ValueError("a plant with no event plans has no benign events to lay out")
    low, high = gap_steps
    if low < 1:
        raise ValueError(f"gap between events must be at least one sample, got {low}")
    if high < low:
        raise ValueError(f"gap range is inverted: {gap_steps}")
    if first_start_step < 0:
        raise ValueError(f"first event cannot start before the run, got step {first_start_step}")

    events: list[BenignEvent] = []
    cursor = first_start_step
    position = 0
    while cursor < spec.n_steps:
        plan = plans[position % len(plans)]
        end = cursor + plan.duration_steps
        if end >= spec.n_steps:
            break
        parameters = {
            name: float(rng.uniform(bounds[0], bounds[1]))
            for name, bounds in plan.parameter_ranges.items()
        }
        rendered = "; ".join(f"{name}={value:.3f}" for name, value in parameters.items())
        events.append(
            BenignEvent(
                kind=plan.kind,
                label=plan.label,
                started_at=spec.instant(cursor),
                ended_at=spec.instant(end),
                writes=plan.writes,
                parameters=parameters,
                detail=f"{plan.detail} {rendered}".strip(),
            )
        )
        cursor = end + int(rng.integers(low, high + 1))
        position += 1
    return tuple(events)


@dataclass(frozen=True)
class CommandIntent:
    """One exchange the plant's control network performed, before it becomes bytes.

    Kept apart from the protocol encoding on purpose: a plant describes what its network *did*,
    and `phos.synth.traffic` decides what that looks like on the wire. The split keeps Modbus out
    of the physics and would let a second protocol be emitted from the same plants without
    touching them.

    Attributes:
        kind: Read or write.
        issuer: ``node_id`` of the device that sent it.
        target: ``node_id`` of the device it was sent to.
        address: First register address touched.
        quantity: How many registers.
        values: The register values written. Empty for a read.
        reason: Why it happened, e.g. ``"cyclic poll"``. Provenance, not protocol.
    """

    kind: CommandKind
    issuer: str
    target: str
    address: int
    quantity: int
    values: tuple[int, ...]
    reason: str


@dataclass(frozen=True)
class TrueState:
    """What the plant was actually doing at an instant, independent of any instrument.

    Not a Pydantic model: thousands of these exist per run and none of them is ontology — they are
    the simulation's own ground truth, the same way `VectorisedSeries` is computation rather than
    a stored type.

    Attributes:
        timestamp: The instant, UTC.
        values: True value of every declared signal, keyed by signal key.
        internal: Process state no instrument is on — inventories, fouling, controller memory.
            Recorded because D2 may need to say a manipulation drove an *unmeasured* quantity
            somewhere dangerous, which is the case telemetry alone can never establish.
    """

    timestamp: datetime
    values: Mapping[str, float]
    internal: Mapping[str, float]


@dataclass(frozen=True)
class SensorReport:
    """What the instruments said at an instant.

    In normal operation this is the true state seen through the declared error model — noise plus
    bounded calibration drift, then bounded by the instrument's span — and nothing else. Under a
    D2 reading injection it is whatever the attacker chose, while `TrueState` carries on telling
    the truth.

    Attributes:
        timestamp: The instant, UTC.
        values: Reported value of every declared signal, keyed by signal key.
    """

    timestamp: datetime
    values: Mapping[str, float]


@dataclass(frozen=True)
class PlantStep:
    """One sample: the truth, the report, what the network did, and what was going on.

    Attributes:
        index: Zero-based sample number.
        timestamp: The instant, UTC.
        truth: The true process state.
        report: What the instruments reported.
        began: The benign event that began at this instant, if any.
        active: The benign event in force at this instant, if any.
        commands: What the control network did at this instant — the observable exchange, which
            is what `phos.synth.traffic` turns into bytes.
        issued: What was really commanded and whether it was really authorised. Ground truth,
            recorded independently of ``commands`` for the same reason `TrueState` is recorded
            independently of `SensorReport`: an authorised write and an unauthorised one are the
            same bytes, so the label cannot come from the wire. Empty unless the plant was given
            a `CommandSource`.
    """

    index: int
    timestamp: datetime
    truth: TrueState
    report: SensorReport
    began: BenignEvent | None
    active: BenignEvent | None
    commands: tuple[CommandIntent, ...]
    issued: tuple[IssuedCommand, ...] = ()


def register_count(spec: SignalSpec, value: float) -> int:
    """Return the raw 16-bit count an instrument reports for an engineering value.

    Industrial devices do not put floats on the wire. A transmitter reports a count across its
    calibrated span — the digital form of the 4-20 mA loop it replaced — and the receiving system
    scales it back. Modelling that is what makes the generated capture carry the same kind of
    number a real one does, negative engineering values included.

    Args:
        spec: The signal, whose span defines the scaling.
        value: The engineering value to encode.

    Returns:
        A count in ``[0, 65535]``, saturating at the ends of the span as a real converter does.
    """
    fraction = (value - spec.low) / (spec.high - spec.low)
    return round(clamp(fraction, 0.0, 1.0) * MAX_REGISTER_COUNT)


class Plant(ABC):
    """A simulated industrial process, driven one sample at a time.

    Subclasses supply four things: what the process *is* (`description`), where it starts
    (`initial_state`), what its controllers do (`control`), and how it evolves (`advance`). Plus
    an event schedule, because a plant with no operational events is not a realistic plant.

    Everything else — the sensor model, the true-state record, both injection points, the
    randomness discipline and the command traffic implied by the declared register map — is here,
    identical for every plant.

    Mutable and single-use in the sense that it carries its state forward: construct one, step it
    through a run, and construct another for the next run. Nothing is global.
    """

    def __init__(
        self,
        spec: RunSpec,
        *,
        commands: CommandSource | None = None,
        realism: RealismProfile | None = None,
    ) -> None:
        """Prepare a plant to be stepped through ``spec``.

        Args:
            spec: The run to simulate. Known up front because the benign-event schedule is drawn
                once, here, which is what keeps per-step randomness at a constant rate.
            commands: Who writes to this plant over its control network. ``None`` means
                `NoCommands`, and a plant given nothing is byte-identical to one given
                `NoCommands` — the same idiom as `NoInjection`.

                Supplying a source changes where writes come from. Without one, a benign event's
                writes are echoed onto the wire *after* the event has already moved the setpoint,
                so the capture reports the physics rather than driving it. With one, the source is
                the sole origin of writes and each is applied to the plant's own state before the
                controllers run, so deleting a command changes the process. The two are not mixed:
                mixing them would put a causal write and a cosmetic one in the same run, and the
                difference between them is exactly what this layer exists to make real.
            realism: The ordinary trouble a real plant has — sensor faults, comms dropouts,
                ambient influence, ageing, grade changes, operator interventions, startup
                transitions. ``None`` means `RealismProfile()`, which is quiet, and **a plant given
                nothing is byte-identical to one given a quiet profile**: `plan_realism` returns an
                empty plan before it draws anything, the effects below are no-ops on an empty plan,
                and the generator this planning reads from is spawned as a *third* child of the
                run's seed, so neither the sensor-noise stream nor the existing setup stream shifts
                by one draw. That is what lets ADR 0073's corpora be reproduced byte for byte after
                this was wired, which is proved rather than asserted.

                The planner is never shown the attack schedule or the scenario — the structural
                refusal `phos.synth.realism` documents and `tests/synth/test_anti_bias.py` pins —
                so a benign phenomenon cannot be placed to coincide with, or to avoid, an attack.
        """
        description = self.description
        self._spec = spec
        self._signals = description.signals
        self._keys = description.signal_keys()
        self._actuator_keys = frozenset(description.keys_of_kind(SignalKind.ACTUATOR))
        self._writable_keys = frozenset(self._keys)

        # Three children, not two. `SeedSequence.spawn` is deterministic by child index, so
        # spawning a third leaves the first two bit-identical to what `spawn(2)` gave — asserted by
        # test, because the byte-identity of every ADR 0073 corpus rests on it.
        noise_seed, setup_seed, realism_seed = numpy.random.SeedSequence(spec.seed).spawn(3)
        self._rng: Generator = numpy.random.default_rng(noise_seed)
        setup: Generator = numpy.random.default_rng(setup_seed)

        width = len(self._signals)
        self._noise_stddev = numpy.array([s.noise_stddev for s in self._signals], dtype=float)
        self._drift_amplitude = numpy.array([s.drift_amplitude for s in self._signals], dtype=float)
        self._drift_period = setup.uniform(*DRIFT_PERIOD_HOURS, size=width)
        self._drift_phase = setup.uniform(0.0, DRIFT_PERIOD_HOURS[1], size=width)

        self._realism_profile = realism or RealismProfile()
        self._realism: RealismPlan = plan_realism(
            numpy.random.default_rng(realism_seed),
            spec.start,
            spec.duration,
            self._realism_profile,
            {s.key: (s.low, s.high) for s in self._signals},
        )
        self._ageing_rate = {
            key: total / max(spec.duration.total_seconds() / 3600.0, 1e-9)
            for key, total in self._realism.ageing.items()
        }

        self._state: dict[str, float] = dict(self.initial_state())
        self._events = tuple(self.schedule_events(setup, spec))
        self._check_events()
        self._by_start = {event.started_at: event for event in self._events}
        self._report: dict[str, float] = {key: self._state[key] for key in self._keys}
        self._index = 0

        network = description.control_network
        self._poll_every = (
            max(1, round(network.poll_interval_seconds / spec.interval_seconds))
            if network is not None
            else 0
        )

        self._commands: CommandSource = NoCommands() if commands is None else commands
        self._driven_by_commands = commands is not None
        self._setpoint_keys = frozenset(description.keys_of_kind(SignalKind.SETPOINT))
        if self._driven_by_commands and network is None:
            raise ValueError(
                f"plant {description.plant_id!r} was given a command source but declares no "
                "control network; there is nothing for a device to write over, and a write that "
                "reached the process without appearing on a wire would be ground truth no "
                "capture could ever carry"
            )

    @property
    @abstractmethod
    def description(self) -> PlantDescription:
        """What this plant is: its signals, its units, its couplings and its control network."""

    @abstractmethod
    def initial_state(self) -> Mapping[str, float]:
        """Return the true process state the run starts from.

        Must hold a value for every declared signal — a plant starts somewhere — and may hold
        further keys for state no instrument is on, which become `TrueState.internal`.
        """

    @abstractmethod
    def schedule_events(self, rng: Generator, spec: RunSpec) -> Sequence[BenignEvent]:
        """Return the benign operational events for the whole run, drawn once.

        Drawn here rather than sampled step by step so that per-step randomness stays at a
        constant rate, which is what makes an injected run bit-identical to a normal one until the
        injection actually fires.

        Args:
            rng: The setup generator. Separate from the sensor-noise stream, so changing an event
                schedule does not reshuffle every reading.
            spec: The run being scheduled over.

        Returns:
            The events, non-overlapping, each starting on a sample instant.
        """

    @abstractmethod
    def begin_event(self, event: BenignEvent) -> None:
        """Apply the persistent part of a benign event at the instant it begins.

        A setpoint change moves a setpoint and it stays moved; a backwash resets accumulated
        fouling. Effects that last only as long as the event — a unit held off through a
        shutdown — belong in `control` and `advance`, which are told which event is in force.
        """

    @abstractmethod
    def control(
        self,
        report: Mapping[str, float],
        active: BenignEvent | None,
        elapsed_hours: float,
        dt_seconds: float,
    ) -> Mapping[str, float]:
        """Return what each control loop commands, from what the instruments reported.

        Args:
            report: The **previous** sample's reported readings. Deliberately not the true state:
                a controller has no oracle, and this is what makes falsified telemetry
                consequential.
            active: The benign event in force, if any.
            elapsed_hours: Hours since the run began, for loops that follow a schedule.
            dt_seconds: The integration step.

        Returns:
            A value for every declared actuator. Keys that are not declared actuators are refused.
        """

    @abstractmethod
    def advance(
        self,
        state: Mapping[str, float],
        actuators: Mapping[str, float],
        active: BenignEvent | None,
        elapsed_hours: float,
        dt_seconds: float,
    ) -> Mapping[str, float]:
        """Return the true process state one step on.

        Args:
            state: The present true state.
            actuators: The actuator positions actually applied — after any injection, because an
                injected position is a real position and the plant must respond to it exactly as
                it responds to any other.
            active: The benign event in force, if any.
            elapsed_hours: Hours since the run began, for exogenous drivers.
            dt_seconds: The integration step.

        Returns:
            The new state, holding a value for every declared signal.
        """

    @property
    def spec(self) -> RunSpec:
        """The run this plant was constructed for."""
        return self._spec

    @property
    def events(self) -> tuple[BenignEvent, ...]:
        """The benign events scheduled for the whole run, in time order."""
        return self._events

    def step(self, injection: Injection | None = None) -> PlantStep:
        """Advance the plant by one sample and return everything that happened.

        Args:
            injection: The manipulation in force. ``None`` means `NoInjection`, which is a real
                object executing the same code rather than a branch that skips it.

        Returns:
            The sample: the true state, the reported readings, the benign events and the control
            traffic.

        Raises:
            KeyError: If an injection names a signal or actuator this plant does not declare, or
                if the plant's own physics loses a signal. Both are refusals rather than silent
                no-ops: a manipulation that quietly does nothing would be labelled as an attack
                that quietly did nothing, which is the worst possible ground truth.
        """
        hook = NoInjection() if injection is None else injection
        index = self._index
        clock = self._spec.instant(index)
        elapsed_hours = index * self._spec.interval_seconds / _SECONDS_PER_HOUR
        dt_seconds = self._spec.interval_seconds

        # One fixed-size block of randomness per step, drawn before anything else can happen, so
        # that no path through the rest of this method can shift the stream by a single draw.
        noise: NDArray[numpy.float64] = self._rng.standard_normal(len(self._signals))

        began = self._by_start.get(clock)
        if began is not None:
            self.begin_event(began)
        active = self._active_event(clock)

        # Writes land before the controllers run, which is what makes them causal: the setpoint a
        # write moves is the setpoint the loop closes on at the next scan, and the loop moves the
        # true state. The source is handed the *reported* readings, never the truth.
        issued = self._apply_writes(
            index, clock, self._commands.writes_at(index, clock, self._report)
        )

        commanded = dict(self.control(self._report, active, elapsed_hours, dt_seconds))
        actuators = self._override(
            commanded, hook.actuator_overrides(clock, commanded), self._actuator_keys, "actuator"
        )

        self._state = dict(self.advance(self._state, actuators, active, elapsed_hours, dt_seconds))
        truth = self._record_truth(clock)
        readings = self._sense(truth.values, noise, elapsed_hours, clock)
        reported = self._override(
            readings, hook.reading_overrides(clock, readings), self._writable_keys, "signal"
        )
        self._report = reported

        self._index += 1
        return PlantStep(
            index=index,
            timestamp=clock,
            truth=truth,
            report=SensorReport(timestamp=clock, values=reported),
            began=began,
            active=active,
            commands=self._command_intents(index, reported, began, issued),
            issued=issued,
        )

    def _check_events(self) -> None:
        """Refuse a schedule that overlaps or that starts off a sample instant.

        Raises:
            ValueError: If two events overlap, which would make "which event was in force" have
                two answers; or if an event starts between samples, where nothing would ever
                trigger it.
        """
        ordered = sorted(self._events, key=lambda event: event.started_at)
        for earlier, later in pairwise(ordered):
            if later.started_at <= earlier.ended_at:
                raise ValueError(
                    f"benign events overlap: {earlier.kind!r} ends {earlier.ended_at} and "
                    f"{later.kind!r} starts {later.started_at}"
                )
        interval = self._spec.sample_interval
        for event in self._events:
            offset = (event.started_at - self._spec.start) % interval
            if offset != timedelta(0):
                raise ValueError(
                    f"benign event {event.kind!r} starts at {event.started_at}, which is not a "
                    "sample instant, so nothing would ever begin it"
                )

    def _active_event(self, clock: datetime) -> BenignEvent | None:
        """Return the event in force at ``clock``, or ``None``. At most one, by `_check_events`."""
        for event in self._events:
            if event.contains(clock):
                return event
        return None

    def _override(
        self,
        values: Mapping[str, float],
        overrides: Mapping[str, float],
        permitted: frozenset[str],
        noun: str,
    ) -> dict[str, float]:
        """Apply an injection's overrides to a set of values.

        An empty override mapping copies the same values through the same code, which is what
        makes an inactive injection indistinguishable from no injection at all.

        Raises:
            KeyError: If an override names something outside ``permitted``.
        """
        applied = dict(values)
        for key, value in overrides.items():
            if key not in permitted:
                raise KeyError(
                    f"injection names {key!r}, which is not a declared {noun} of plant "
                    f"{self.description.plant_id!r}"
                )
            applied[key] = value
        return applied

    def _record_truth(self, clock: datetime) -> TrueState:
        """Split the state into the signals instruments are on and the state they are not.

        Raises:
            KeyError: If `advance` returned a state missing a declared signal.
        """
        values: dict[str, float] = {}
        for key in self._keys:
            if key not in self._state:
                raise KeyError(
                    f"plant {self.description.plant_id!r} lost signal {key!r} while advancing"
                )
            values[key] = self._state[key]
        internal = {key: value for key, value in self._state.items() if key not in values}
        return TrueState(timestamp=clock, values=values, internal=internal)

    def _sense(
        self,
        truth: Mapping[str, float],
        noise: NDArray[numpy.float64],
        elapsed_hours: float,
        clock: datetime,
    ) -> dict[str, float]:
        """Return what the instruments report: the true state through the declared error model.

        Two imperfections are always present, both bounded and both declared per signal: gaussian
        measurement noise, and a slow calibration drift whose period and phase were drawn once for
        the run. The reading is then bounded by the instrument's calibrated span, as a real
        transmitter's is.

        On top of those sit the declared `phos.synth.realism` effects, and **every one of them is a
        no-op under a quiet profile**, which is what keeps a plant given no profile byte-identical
        to every corpus generated before this was wired:

        * **ambient influence** and **ageing** move the *true* quantity the instrument is reading,
          so they are added before the span clamp and are indistinguishable from process behaviour,
          which is what they are;
        * a **sensor fault** is applied last, after the clamp's input is formed but as the
          instrument's own reading — a frozen transmitter reports its stuck value and a walked
          calibration reports an offset, and neither is a fact about the process.

        That ordering is the claim: the first two are the plant, the third is the instrument, and a
        detector that cannot tell them apart is failing at something real rather than at an artefact
        of how this harness stacks its arithmetic.
        """
        reported: dict[str, float] = {}
        for position, spec in enumerate(self._signals):
            drift = float(self._drift_amplitude[position]) * math.sin(
                2.0
                * math.pi
                * (elapsed_hours - float(self._drift_phase[position]))
                / float(self._drift_period[position])
            )
            raw = (
                truth[spec.key]
                + drift
                + float(self._noise_stddev[position]) * float(noise[position])
            )
            for influence in self._realism.drifts:
                if influence.signal == spec.key:
                    raw += influence.at(elapsed_hours)
            ageing = self._ageing_rate.get(spec.key)
            if ageing is not None:
                raw += ageing * elapsed_hours
            for fault in self._realism.faults:
                if fault.signal == spec.key:
                    raw = fault.apply(clock, raw)
            # Plain floats, not numpy scalars: these values are written to CSV with `repr`, and a
            # numpy scalar's repr is `np.float64(1.5)` rather than `1.5`. A corpus is not the
            # place to leak the type of the array the noise came out of.
            reported[spec.key] = float(clamp(raw, spec.low, spec.high))
        return reported

    def _apply_writes(
        self, index: int, clock: datetime, writes: Sequence[PlannedWrite]
    ) -> tuple[IssuedCommand, ...]:
        """Apply a source's writes to the plant's own state and record what really happened.

        Every refusal here is loud for one reason: a write that quietly did nothing would be
        recorded as a command that quietly did nothing, and a harness whose ground truth says an
        attacker acted when the process never felt it is worse than one with no ground truth.

        Args:
            index: The sample the writes land on.
            clock: The instant, UTC.
            writes: What the source asked for, in engineering units.

        Returns:
            One `IssuedCommand` per write, in the order performed.

        Raises:
            ValueError: If the plant declares no write authority — an authorisation that was never
                declared must not be guessed in either direction; if a write names a signal that
                is not a setpoint; or if the plant has no control network.
            KeyError: If the signal, the issuing device or the target register is not declared.
        """
        if not writes:
            return ()

        description = self.description
        network = description.control_network
        if network is None:
            raise ValueError(f"plant {description.plant_id!r} has no control network to write over")
        authority = description.write_authority
        if authority is None:
            raise ValueError(
                f"plant {description.plant_id!r} declares no write authority, so whether a write "
                "was authorised cannot be recorded; declare one rather than letting the ground "
                "truth default to an answer nobody stated"
            )

        issued: list[IssuedCommand] = []
        for write in writes:
            spec = description.signal(write.signal)
            if write.signal not in self._setpoint_keys:
                raise ValueError(
                    f"{write.issuer!r} wrote {write.signal!r}, which is a {spec.kind.value} and "
                    "not a setpoint. Only a setpoint is moved by a write here; forcing a final "
                    "control element is the actuator injection door in phos.synth.injection, "
                    "which already models it"
                )
            network.node(write.issuer)
            target, address = network.address_of(write.signal)
            applied = clamp(write.value, spec.low, spec.high)
            self._state[write.signal] = applied
            issued.append(
                IssuedCommand(
                    step_index=index,
                    timestamp=clock,
                    issuer=write.issuer,
                    target=target,
                    address=address,
                    signal=write.signal,
                    requested=write.value,
                    applied=applied,
                    authorised=authority.authorisation_of(write.issuer, write.signal),
                    reason=write.reason,
                )
            )
        return tuple(issued)

    def _command_intents(
        self,
        index: int,
        reported: Mapping[str, float],
        began: BenignEvent | None,
        issued: Sequence[IssuedCommand],
    ) -> tuple[CommandIntent, ...]:
        """Return the control traffic this sample generated.

        Two things happen on an industrial control network and both are modelled here: the SCADA
        server reads every register block on its cycle, and a setpoint gets written. Nothing else —
        a plant that invented traffic it had no process reason for would be teaching D3 to detect
        noise.

        Where the writes come from depends on whether the plant was given a `CommandSource`. With
        one, they are the writes that were actually applied to the process, carrying the value the
        plant actually took. Without one, they are the legacy echo of a benign event's writes,
        emitted after the event has already moved the setpoint. The two never appear in the same
        run — see `Plant.__init__`.

        An issued write's `reason` names the source's own provenance and its authorisation does not
        appear at all, because neither is on a real wire. The bytes an intruder writes and the
        bytes an engineer writes are the same bytes.
        """
        network = self.description.control_network
        if network is None:
            return ()

        intents: list[CommandIntent] = []
        if index % self._poll_every == 0:
            for block in network.blocks:
                intents.append(
                    CommandIntent(
                        kind=CommandKind.READ,
                        issuer=network.poller,
                        target=block.node_id,
                        address=block.start_address,
                        quantity=len(block.signals),
                        values=(),
                        reason="cyclic poll",
                    )
                )

        if self._driven_by_commands:
            for command in issued:
                intents.append(
                    CommandIntent(
                        kind=CommandKind.WRITE,
                        issuer=command.issuer,
                        target=command.target,
                        address=command.address,
                        quantity=1,
                        values=(
                            register_count(
                                self.description.signal(command.signal), command.applied
                            ),
                        ),
                        reason=command.reason,
                    )
                )
        elif began is not None:
            for key in began.writes:
                node_id, address = network.address_of(key)
                intents.append(
                    CommandIntent(
                        kind=CommandKind.WRITE,
                        issuer=network.operator,
                        target=node_id,
                        address=address,
                        quantity=1,
                        values=(register_count(self.description.signal(key), reported[key]),),
                        reason=f"operator: {began.kind}",
                    )
                )
        return tuple(intents)

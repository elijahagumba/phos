"""A plant as a document: what it is made of, what is connected to what, and every free number.

PART R1. `phos.synth.plants` holds three plants whose structure is in their source code — six
tanks are six tanks because somebody typed six, and a gain is a gain because somebody tuned it.
A `PlantSpec` is the same plant said declaratively: the components and the connections between
them, the controllers with their settings, the instruments with their tag names and error models,
the scan period the control network is polled at, the disturbance model, and the parameter set the
process physics reads. It is frozen, it round-trips through JSON, and `build_plant` turns one back
into a running `phos.synth.plant.Plant`.

**What a spec holds, and what it does not.** The physics body itself stays a named, registered
*process template* — ``"water-treatment-v1"`` and its two siblings — and the spec supplies the
numbers that template reads. This is a deliberate split and it is worth being plain about, because
the alternative was considered and declined:

* Lifting the roughly sixty hand-tuned constants out of the three plants into
  `PlantSpec.parameters` leaves the arithmetic untouched. A template reads
  ``self._p.max_intake_m3ph`` where it read ``_MAX_INTAKE_M3PH``, which is the same double in the
  same operation in the same order, so the corpora pinned in ``tests/synth/golden/`` stay
  byte-identical and that is checked rather than hoped for.
* Making the spec an *executable* dataflow graph instead would mean a node type for every bespoke
  computation these plants do — Arrhenius kinetics, vessel mixing, a batch phase state machine, a
  tap-changer's stepping logic, a pump curve — which is the same bespoke code wearing a
  declarative coat, at a real risk of moving the last bits of every float by reassociating the
  operations.

So the component graph here is a *declaration* that its template must honour, not the thing that
executes. That is the stance `phos.synth.topology` already takes, and for the same reason: a
structure derived from the statistics it is meant to explain explains nothing. `PlantSpec` refuses
a graph that disagrees with the instruments — every signal is owned by exactly one component, and a
component's signals must sit on the component's own physical unit — so the declaration cannot
quietly drift away from the plant it describes.

**What this buys.** PART R2 draws a plant from a family by drawing a `PlantSpec`: the parameters,
the tag names, the sensor layout, the controller tunings, the scan period, the disturbance
schedule, and whatever structure its template is written to vary. Nothing downstream — the
integrator, the sensor model, the Modbus writer, the injection hook, the topology renderer — needs
to know whether the spec it was handed was typed by a person or drawn from a seed.

**The standing caveat is not weakened by any of this.** A spec describes a model of an industrial
process, not a plant. See ``MODEL_NOT_REALITY_CAVEAT``.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from enum import Enum
from typing import Final, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from phos.synth.command import WriteAuthority
from phos.synth.plant import (
    ControlNetwork,
    Coupling,
    EventPlan,
    PhysicalUnit,
    PlantDescription,
    SignalKind,
    SignalSpec,
)
from phos.synth.process import Hysteresis, PiController

__all__ = [
    "SPEC_VERSION",
    "Component",
    "ComponentKind",
    "Connection",
    "ControllerKind",
    "ControllerSpec",
    "DisturbanceSpec",
    "EventPlanSpec",
    "PlantSpec",
    "SignalRole",
    "SpecError",
    "component_signals",
    "fixed_setpoint",
    "pi_controller",
    "signals_of_kind",
]

SPEC_VERSION: Final = 1
"""Bumped when the spec layout changes incompatibly. A reader refuses a version it does not know."""


class SpecError(ValueError):
    """Raised when a spec does not describe a plant that could be built."""


class ComponentKind(str, Enum):
    """What a piece of plant *is*, as a drawing would label it.

    Deliberately a closed list. A generator in PART R2 picks from these, and PART V4 draws a
    schematic symbol for each, so a free-text kind would be a symbol nobody drew.

    Attributes:
        TANK: A vessel holding an inventory — a clearwell, a sump, a day tank.
        REACTOR: A vessel where something is converted, with its own thermal mass.
        PUMP: A machine that moves fluid.
        VALVE: A final control element that restricts flow.
        PIPE: A connection carrying fluid between two components.
        FILTER: A separation stage that accumulates what it removes.
        MIXER: A point where two streams combine, or an agitator.
        HEATER: Something that puts heat in.
        EXCHANGER: Something that moves heat between two streams — a jacket, a cooler.
        TURBINE: A prime mover.
        GENERATOR: A machine converting shaft power to electrical power.
        TRANSFORMER: A winding pair, with or without a tap changer.
        BUS: An electrical node several circuits connect to.
        FEEDER: An outgoing electrical circuit.
        LOAD: A demand the plant serves and does not control.
        SOURCE: Where material or energy enters the modelled boundary.
        SINK: Where it leaves.
        CONTROLLER: A control loop, where the drawing shows one as a component.
        OTHER: Anything the list above does not name. Used rather than guessed at.
    """

    TANK = "TANK"
    REACTOR = "REACTOR"
    PUMP = "PUMP"
    VALVE = "VALVE"
    PIPE = "PIPE"
    FILTER = "FILTER"
    MIXER = "MIXER"
    HEATER = "HEATER"
    EXCHANGER = "EXCHANGER"
    TURBINE = "TURBINE"
    GENERATOR = "GENERATOR"
    TRANSFORMER = "TRANSFORMER"
    BUS = "BUS"
    FEEDER = "FEEDER"
    LOAD = "LOAD"
    SOURCE = "SOURCE"
    SINK = "SINK"
    CONTROLLER = "CONTROLLER"
    OTHER = "OTHER"


class SignalRole(BaseModel):
    """What a signal *is* in its process, independently of what it is called.

    This is the mapping PART R2 needs and PART R3 writes into every generated plant's output as
    ground truth. A family draws its tag names — ``LT_201.PV`` on one seed, ``tank2_level_m`` on
    the next — precisely so that nothing downstream can key off a name. A process template still
    has to find the second stage's level transmitter, and a reviewer still has to be able to say
    what a column in the telemetry means. Both ask the role, not the name.

    Attributes:
        role: What the signal measures or commands, from the family's own vocabulary —
            ``"level"``, ``"inflow"``, ``"pump_speed"``, ``"temperature"``. Stable across seeds
            and across naming schemes; it is the thing the tag name is a disguise for.
        train: Which parallel train the signal belongs to, counting from zero. Plants with one
            train leave it at zero.
        stage: Which stage within that train, counting from zero in the direction of flow.

    Invariants:
        Train and stage are non-negative. A plant declares at most one signal per
        ``(role, train, stage)``, which is what makes `PlantSpec.tag` a lookup rather than a
        search.
    """

    model_config = ConfigDict(frozen=True)

    role: str = Field(min_length=1)
    train: int = Field(default=0, ge=0)
    stage: int = Field(default=0, ge=0)

    @property
    def position(self) -> tuple[str, int, int]:
        """The triple this role occupies, which is unique within a plant."""
        return (self.role, self.train, self.stage)


class Component(BaseModel):
    """One piece of plant, and the instruments that sit on it.

    Attributes:
        component_id: Stable identifier within the plant.
        kind: What it is.
        label: Human-readable name, as an operator would say it.
        physical_unit: The `phos.synth.plant.PhysicalUnit` this component belongs to. Several
            components may share a unit — an intake pump and its rising main are both "intake" —
            and the unit is what the declared topology groups by.
        signals: Signal keys instrumented on this component, in declaration order. May be empty
            for a component nothing measures directly, such as a length of pipe.
        description: What this component does, in a sentence, for a reader who is not a process
            engineer. PART V4 shows it on hover.
    """

    model_config = ConfigDict(frozen=True)

    component_id: str = Field(min_length=1)
    kind: ComponentKind
    label: str = Field(min_length=1)
    physical_unit: str = Field(min_length=1)
    signals: tuple[str, ...] = ()
    description: str = ""


class Connection(BaseModel):
    """A declared link between two components: what flows, and which way.

    Attributes:
        source: ``component_id`` the material, energy or signal leaves.
        target: ``component_id`` it arrives at.
        medium: What travels — ``"water"``, ``"heat"``, ``"electrical"``, ``"material"``.
            Descriptive; nothing branches on it, but a connection whose medium is unrecorded
            cannot be drawn correctly or checked by eye.
        label: The link in words, e.g. ``"rising main from the intake to the dosing point"``.
    """

    model_config = ConfigDict(frozen=True)

    source: str = Field(min_length=1)
    target: str = Field(min_length=1)
    medium: str = Field(min_length=1)
    label: str = ""

    @model_validator(mode="after")
    def _check_not_self_connected(self) -> Self:
        if self.source == self.target:
            raise ValueError(f"component {self.source!r} is declared as connected to itself")
        return self


class ControllerKind(str, Enum):
    """The control elements a plant is built from, both already implemented in `phos.synth.process`.

    Attributes:
        PI: A proportional-integral loop with back-calculated anti-windup.
        HYSTERESIS: An on/off element with a dead band between its two switching points.
    """

    PI = "PI"
    HYSTERESIS = "HYSTERESIS"


class ControllerSpec(BaseModel):
    """One control loop: what it measures, what it drives, and how it is tuned.

    The settings are the ones `phos.synth.process` already takes, so building a controller from a
    spec constructs exactly the object the hand-written plant constructed.

    Attributes:
        controller_id: Stable identifier within the plant.
        kind: PI or hysteresis.
        measurement: Signal key the loop reads. What the instrument *reported*, never the true
            state — see `phos.synth.process.PiController`.
        output: What the loop drives: either a signal key, which must be an actuator, or the
            ``controller_id`` of another loop, which makes this one that loop's cascade master and
            its output that loop's target.
        setpoint: Signal key holding the target, for a PI loop whose target an operator can
            move. ``None`` for a hysteresis element, whose two bounds are its target, and for a
            loop holding to a fixed value.
        setpoint_value: A fixed target, for a PI loop holding to a number nobody writes — a
            governor on nominal frequency, an AVR on nominal bus voltage. Exactly one of this and
            ``setpoint`` is given for a PI loop: a target that is both a signal and a constant has
            two answers, and a loop with neither is not holding to anything.
        gain: Proportional gain, PI only. Positive.
        integral_time_seconds: Seconds for the integral to repeat the proportional term, PI only.
        low: Lower output limit, PI only.
        high: Upper output limit, PI only.
        reverse_acting: Whether the output must rise when the measurement rises. PI only.
        bias: Feedforward added before the loop's own terms, PI only. Declared here because it is
            part of the tuning: it is what keeps the integral from having to supply the whole
            operating point.
        on_below: Engages when the measurement falls below this, hysteresis only.
        off_above: Releases when the measurement rises above this, hysteresis only.
        description: What this loop is for, in plain language.

    Invariants:
        A PI loop declares at most one kind of target and all four PI settings, and neither
        hysteresis bound; a hysteresis element declares both bounds, no target and none of the
        PI settings. That a PI loop declares *at least* one target is checked by `PlantSpec`
        rather than here, because the third way to have one — being the slave of a cascade — is
        a fact about the plant and not about the loop.
    """

    model_config = ConfigDict(frozen=True)

    controller_id: str = Field(min_length=1)
    kind: ControllerKind
    measurement: str = Field(min_length=1)
    output: str = Field(min_length=1)
    setpoint: str | None = None
    setpoint_value: float | None = None
    gain: float | None = None
    integral_time_seconds: float | None = None
    low: float | None = None
    high: float | None = None
    reverse_acting: bool = False
    bias: float = 0.0
    on_below: float | None = None
    off_above: float | None = None
    description: str = ""

    @model_validator(mode="after")
    def _check_settings(self) -> Self:
        pi_fields = ("gain", "integral_time_seconds", "low", "high")
        band_fields = ("on_below", "off_above")
        if self.kind is ControllerKind.PI:
            missing = [name for name in pi_fields if getattr(self, name) is None]
            if missing:
                raise ValueError(
                    f"PI loop {self.controller_id!r} is missing {', '.join(missing)}; a loop with "
                    "an unstated tuning is not a loop"
                )
            if self.setpoint is not None and self.setpoint_value is not None:
                raise ValueError(
                    f"PI loop {self.controller_id!r} declares both a setpoint signal and a fixed "
                    "setpoint; its target would have two answers"
                )
            present = [name for name in band_fields if getattr(self, name) is not None]
            if present:
                raise ValueError(
                    f"PI loop {self.controller_id!r} declares {', '.join(present)}, which belongs "
                    "to a hysteresis element"
                )
        else:
            if self.setpoint is not None or self.setpoint_value is not None:
                raise ValueError(
                    f"hysteresis element {self.controller_id!r} declares a setpoint; its band is "
                    "its target"
                )
            missing = [name for name in band_fields if getattr(self, name) is None]
            if missing:
                raise ValueError(
                    f"hysteresis element {self.controller_id!r} is missing {', '.join(missing)}"
                )
            present = [name for name in pi_fields if getattr(self, name) is not None]
            if present:
                raise ValueError(
                    f"hysteresis element {self.controller_id!r} declares {', '.join(present)}, "
                    "which belongs to a PI loop"
                )
        return self

    def build(self) -> PiController | Hysteresis:
        """Construct the control element this spec describes.

        Returns:
            The element, in its initial state.

        Raises:
            SpecError: If a setting this kind needs is absent. Unreachable for a validated spec,
                which is why it is checked rather than assumed: the two could drift apart.
            ValueError: If the settings describe no loop — a non-positive gain or integral time,
                inverted output limits, or an inverted band. Raised by `phos.synth.process`,
                which is where those relations are argued.
        """
        if self.kind is ControllerKind.PI:
            if (
                self.gain is None
                or self.integral_time_seconds is None
                or self.low is None
                or self.high is None
            ):
                raise SpecError(f"PI loop {self.controller_id!r} has an incomplete tuning")
            return PiController(
                gain=self.gain,
                integral_time_seconds=self.integral_time_seconds,
                low=self.low,
                high=self.high,
                reverse_acting=self.reverse_acting,
            )
        if self.on_below is None or self.off_above is None:
            raise SpecError(f"hysteresis element {self.controller_id!r} has an incomplete band")
        return Hysteresis(on_below=self.on_below, off_above=self.off_above)


class EventPlanSpec(BaseModel):
    """A kind of benign operational event, in the serialisable form of `plant.EventPlan`.

    `EventPlan` is a frozen dataclass carrying a `Mapping`, which is right for the integrator and
    wrong for a document. This is the same thing with a JSON round trip, and `to_plan` is the one
    conversion.

    Attributes:
        kind: Machine-readable class, e.g. ``"setpoint_change"``.
        label: Human-readable description.
        duration_steps: How many samples it lasts. Zero for an instantaneous change.
        writes: Signals an operator writes as part of it.
        parameter_ranges: ``{name: (low, high)}``, drawn uniformly per occurrence.
        detail: Prefix for the rendered detail line.
    """

    model_config = ConfigDict(frozen=True)

    kind: str = Field(min_length=1)
    label: str = Field(min_length=1)
    duration_steps: int = Field(default=0, ge=0)
    writes: tuple[str, ...] = ()
    parameter_ranges: Mapping[str, tuple[float, float]] = Field(default_factory=dict)
    detail: str = ""

    def to_plan(self) -> EventPlan:
        """Return the `plant.EventPlan` the scheduler takes."""
        return EventPlan(
            kind=self.kind,
            label=self.label,
            duration_steps=self.duration_steps,
            writes=self.writes,
            parameter_ranges=dict(self.parameter_ranges),
            detail=self.detail,
        )

    @classmethod
    def from_plan(cls, plan: EventPlan) -> EventPlanSpec:
        """Return the serialisable form of an existing `plant.EventPlan`."""
        return cls(
            kind=plan.kind,
            label=plan.label,
            duration_steps=plan.duration_steps,
            writes=plan.writes,
            parameter_ranges={
                name: (low, high) for name, (low, high) in plan.parameter_ranges.items()
            },
            detail=plan.detail,
        )


class DisturbanceSpec(BaseModel):
    """The normal operational variety a plant has, and how it is laid through a run.

    This is the disturbance model, and it is part of the plant rather than part of the run: a
    works where the filters are backwashed is a different works from one where they are not. The
    placement itself is drawn per seed by `phos.synth.plant.lay_out_events`; what is declared here
    is what kinds of thing happen and how far apart.

    Attributes:
        event_plans: The kinds of benign event this plant has, cycled round-robin.
        first_start_floor: Earliest sample index the first event may begin at.
        first_start_divisor: The first event may also not begin before ``n_steps // this``, so a
            long run gets proportionally more undisturbed operation to learn a baseline from. The
            later of the two bounds wins.
        gap_steps: ``(low, high)`` samples of quiet between one event ending and the next
            beginning, drawn uniformly.

    Invariants:
        The gap's low bound is at least one sample, and does not exceed its high bound.
    """

    model_config = ConfigDict(frozen=True)

    event_plans: tuple[EventPlanSpec, ...] = Field(min_length=1)
    first_start_floor: int = Field(ge=0)
    first_start_divisor: int = Field(gt=0)
    gap_steps: tuple[int, int]

    @model_validator(mode="after")
    def _check_gap(self) -> Self:
        low, high = self.gap_steps
        if low < 1:
            raise ValueError(
                f"gap_steps low bound is {low}; two events a sample apart abut and read as one"
            )
        if low > high:
            raise ValueError(f"gap_steps is inverted: {low} exceeds {high}")
        return self

    def plans(self) -> tuple[EventPlan, ...]:
        """Return the event kinds in the form the scheduler takes."""
        return tuple(plan.to_plan() for plan in self.event_plans)

    def first_start_step(self, n_steps: int) -> int:
        """Return the earliest sample index the first event may begin at, for a run this long."""
        return max(self.first_start_floor, n_steps // self.first_start_divisor)


class PlantSpec(BaseModel):
    """A whole plant, declaratively: its parts, its loops, its instruments and its free numbers.

    Attributes:
        spec_version: Layout version. A reader refuses one it does not know.
        plant_id: Stable identifier. Used in dataset names and file paths.
        label: Human-readable name.
        industry: The sector this process belongs to.
        summary: What the process does, in a sentence or two.
        model_source: What the model was built from, named specifically. The plant's defence of
            its own realism — see `phos.synth.plant.PlantDescription`.
        process: Identifier of the registered process template that holds this plant's physics,
            e.g. ``"water-treatment-v1"``. `build_plant` resolves it.
        parameters: Every free number the template reads — capacities, time constants, flow
            coefficients, reaction constants. Flat, named, and all floats, so a family in PART R2
            draws a plant by drawing this mapping.
        units: The physical units instruments sit on.
        signals: Every signal, in the order that decides register and column order.
        components: What the plant is made of.
        connections: What is connected to what.
        controllers: The control loops and their tunings.
        couplings: The declared physical dependencies between signals.
        control_network: The control traffic the process generates, whose
            ``poll_interval_seconds`` is the plant's scan period. ``None`` for a process
            controlled over something Atlas cannot dissect.
        write_authority: Which device may write which signal.
        disturbance: The normal operational events and how they are laid out.
        roles: What each signal *is*, keyed by signal key — the ground truth a randomised tag
            name is a disguise for. Empty is allowed and means the plant has not said; a drawn
            plant always says, because without it a template could not find its own instruments
            and a reviewer could not read its telemetry.

    Invariants:
        Every component sits on a declared unit; every signal is owned by exactly one component
        and sits on that component's unit; every connection names declared components; every
        controller reads, targets and drives declared signals of the right kind; every declared
        role names a declared signal and no two signals share a role position; and the
        `PlantDescription` this builds satisfies its own invariants.
    """

    model_config = ConfigDict(frozen=True)

    spec_version: int = SPEC_VERSION
    plant_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    industry: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    model_source: str = Field(min_length=1)
    process: str = Field(min_length=1)
    parameters: Mapping[str, float] = Field(default_factory=dict)
    units: tuple[PhysicalUnit, ...] = Field(min_length=1)
    signals: tuple[SignalSpec, ...] = Field(min_length=2)
    components: tuple[Component, ...] = Field(min_length=1)
    connections: tuple[Connection, ...] = ()
    controllers: tuple[ControllerSpec, ...] = ()
    couplings: tuple[Coupling, ...] = Field(min_length=1)
    control_network: ControlNetwork | None = None
    write_authority: WriteAuthority | None = None
    disturbance: DisturbanceSpec
    roles: Mapping[str, SignalRole] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_declaration(self) -> Self:
        if self.spec_version != SPEC_VERSION:
            raise ValueError(
                f"plant {self.plant_id!r} carries spec_version {self.spec_version}; this code "
                f"reads {SPEC_VERSION}"
            )
        by_key = {signal.key: signal for signal in self.signals}
        unit_ids = {unit.unit_id for unit in self.units}

        component_ids: set[str] = set()
        owner: dict[str, str] = {}
        for component in self.components:
            if component.component_id in component_ids:
                raise ValueError(
                    f"plant {self.plant_id!r} declares component {component.component_id!r} twice"
                )
            component_ids.add(component.component_id)
            if component.physical_unit not in unit_ids:
                raise ValueError(
                    f"component {component.component_id!r} sits on undeclared unit "
                    f"{component.physical_unit!r}"
                )
            for key in component.signals:
                signal = by_key.get(key)
                if signal is None:
                    raise ValueError(
                        f"component {component.component_id!r} owns undeclared signal {key!r}"
                    )
                if key in owner:
                    raise ValueError(
                        f"signal {key!r} is owned by both {owner[key]!r} and "
                        f"{component.component_id!r}; a measurement is on one piece of plant"
                    )
                owner[key] = component.component_id
                if signal.physical_unit != component.physical_unit:
                    raise ValueError(
                        f"component {component.component_id!r} is on unit "
                        f"{component.physical_unit!r} but owns signal {key!r}, which is "
                        f"instrumented on {signal.physical_unit!r}; the drawing and the "
                        "instruments disagree"
                    )

        unowned = sorted(set(by_key) - set(owner))
        if unowned:
            raise ValueError(
                f"plant {self.plant_id!r} declares signal(s) no component owns: "
                f"{', '.join(unowned)}. A reading has to come from somewhere."
            )

        for connection in self.connections:
            for end, component_id in (("source", connection.source), ("target", connection.target)):
                if component_id not in component_ids:
                    raise ValueError(
                        f"connection {end} {component_id!r} is not a declared component"
                    )

        seen_controllers: set[str] = set()
        for controller in self.controllers:
            if controller.controller_id in seen_controllers:
                raise ValueError(
                    f"plant {self.plant_id!r} declares controller "
                    f"{controller.controller_id!r} twice"
                )
            seen_controllers.add(controller.controller_id)
            self._check_controller_signals(controller, by_key)
        self._check_targets()
        self._check_roles(by_key)

        self.describe()
        return self

    def _check_controller_signals(
        self, controller: ControllerSpec, by_key: Mapping[str, SignalSpec]
    ) -> None:
        """Check one loop reads, targets and drives signals the plant actually has.

        Raises:
            ValueError: If a named signal is undeclared, or is of a kind that cannot play that
                part — a loop cannot drive a measurement, and cannot hold to an actuator.
        """
        required: list[tuple[str, str, SignalKind | None]] = [
            ("measurement", controller.measurement, None),
        ]
        if controller.output not in {other.controller_id for other in self.controllers}:
            required.append(("output", controller.output, SignalKind.ACTUATOR))
        if controller.setpoint is not None:
            required.append(("setpoint", controller.setpoint, SignalKind.SETPOINT))
        for part, key, expected in required:
            signal = by_key.get(key)
            if signal is None:
                raise ValueError(
                    f"controller {controller.controller_id!r} names undeclared signal {key!r} "
                    f"as its {part}"
                )
            if expected is not None and signal.kind is not expected:
                raise ValueError(
                    f"controller {controller.controller_id!r} uses {key!r} as its {part}, but it "
                    f"is a {signal.kind.value} and a {part} must be a {expected.value}"
                )

    def _check_roles(self, by_key: Mapping[str, SignalSpec]) -> None:
        """Check the role map names real signals and gives each position to one of them.

        Raises:
            ValueError: If a role is declared for a signal the plant does not have, or if two
                signals claim the same role in the same train and stage — which would make
                `tag` ambiguous and a template's lookup arbitrary.
        """
        taken: dict[tuple[str, int, int], str] = {}
        for key, role in self.roles.items():
            if key not in by_key:
                raise ValueError(
                    f"plant {self.plant_id!r} declares a role for undeclared signal {key!r}"
                )
            clash = taken.get(role.position)
            if clash is not None:
                raise ValueError(
                    f"signals {clash!r} and {key!r} both claim role {role.role!r} on train "
                    f"{role.train} stage {role.stage}; a role names one instrument"
                )
            taken[role.position] = key

    def _check_targets(self) -> None:
        """Check every PI loop is holding to something, across the whole plant.

        A loop has a target three ways: a setpoint signal an operator can write, a fixed value,
        or — in a cascade — the output of the loop above it. The third is only visible here,
        which is why this check is not on `ControllerSpec`.

        Raises:
            ValueError: If a PI loop has no target at all, or has two.
        """
        driven_by_cascade = {
            controller.output
            for controller in self.controllers
            if controller.output in {other.controller_id for other in self.controllers}
        }
        for controller in self.controllers:
            if controller.kind is not ControllerKind.PI:
                continue
            targets = [
                controller.setpoint is not None,
                controller.setpoint_value is not None,
                controller.controller_id in driven_by_cascade,
            ]
            if not any(targets):
                raise ValueError(
                    f"PI loop {controller.controller_id!r} holds to nothing: it declares no "
                    "setpoint signal, no fixed setpoint, and no loop cascades into it"
                )
            if sum(targets) > 1:
                raise ValueError(
                    f"PI loop {controller.controller_id!r} has more than one target; a loop "
                    "regulating to two things regulates to neither"
                )

    def cascade_slave(self, controller_id: str) -> str | None:
        """Return the loop this one cascades into, or ``None`` if it drives a signal directly.

        Raises:
            KeyError: If the plant declares no such controller.
        """
        output = self.controller(controller_id).output
        known = {other.controller_id for other in self.controllers}
        return output if output in known else None

    def describe(self) -> PlantDescription:
        """Return the declaration the integrator, the manifest and the topology all read.

        Returns:
            The `PlantDescription` this spec means. Equal, field for field, to the one a
            hand-written plant returned before PART R1 — which `tests/synth/test_plant_spec.py`
            asserts for all three.

        Raises:
            ValueError: If the description's own invariants do not hold.
        """
        return PlantDescription(
            plant_id=self.plant_id,
            label=self.label,
            industry=self.industry,
            summary=self.summary,
            model_source=self.model_source,
            units=self.units,
            signals=self.signals,
            couplings=self.couplings,
            control_network=self.control_network,
            write_authority=self.write_authority,
        )

    def component(self, component_id: str) -> Component:
        """Return the declared component with this identifier.

        Raises:
            KeyError: If the plant declares no such component.
        """
        for candidate in self.components:
            if candidate.component_id == component_id:
                return candidate
        raise KeyError(f"plant {self.plant_id!r} declares no component {component_id!r}")

    def controller(self, controller_id: str) -> ControllerSpec:
        """Return the declared controller with this identifier.

        Raises:
            KeyError: If the plant declares no such controller.
        """
        for candidate in self.controllers:
            if candidate.controller_id == controller_id:
                return candidate
        raise KeyError(f"plant {self.plant_id!r} declares no controller {controller_id!r}")

    def tag(self, role: str, train: int = 0, stage: int = 0) -> str:
        """Return the signal key playing this role, whatever it happens to be called.

        This is how a process template finds its instruments. A family draws the names; the
        template never sees them.

        Args:
            role: The role, from the family's vocabulary.
            train: Which parallel train.
            stage: Which stage within it.

        Returns:
            The signal key.

        Raises:
            KeyError: If no signal plays that role there. The message names the roles the plant
                does declare, because a template asking for the wrong one would otherwise fail
                much later as a missing column.
        """
        for key, declared in self.roles.items():
            if declared.position == (role, train, stage):
                return key
        known = sorted({declared.role for declared in self.roles.values()})
        raise KeyError(
            f"plant {self.plant_id!r} has no {role!r} on train {train} stage {stage}; "
            f"it declares {', '.join(known) if known else 'no roles at all'}"
        )

    def has_role(self, role: str, train: int = 0, stage: int = 0) -> bool:
        """Return whether any signal plays this role there.

        A family may leave a stage uninstrumented — not every tank on a real site has a flow
        meter on its inlet — so a template asks before it reaches.
        """
        return any(declared.position == (role, train, stage) for declared in self.roles.values())

    def tags_with_role(self, role: str) -> tuple[str, ...]:
        """Return every signal key playing this role, ordered by train then stage."""
        matching = [
            (declared.train, declared.stage, key)
            for key, declared in self.roles.items()
            if declared.role == role
        ]
        return tuple(key for _, _, key in sorted(matching))

    def role_of(self, key: str) -> SignalRole | None:
        """Return what a signal is, or ``None`` if the plant has not said."""
        return self.roles.get(key)

    def components_on(self, unit_id: str) -> tuple[Component, ...]:
        """Return the components sitting on one physical unit, in declaration order."""
        return tuple(
            component for component in self.components if component.physical_unit == unit_id
        )

    @property
    def scan_period_seconds(self) -> float | None:
        """How often the control network is polled, or ``None`` for a plant with no network."""
        return None if self.control_network is None else self.control_network.poll_interval_seconds

    def to_json(self) -> str:
        """Render the spec as indented JSON, deterministically.

        Returns:
            The document, newline-terminated. Field order is the declaration order above, not
            sorted, so a spec reads like the plant it describes.
        """
        return json.dumps(json.loads(self.model_dump_json()), indent=2) + "\n"

    @classmethod
    def from_json(cls, document: str) -> PlantSpec:
        """Read a spec back from the JSON `to_json` writes.

        Args:
            document: The serialised spec.

        Returns:
            The spec, revalidated in full — a document that was edited into something
            unbuildable is refused here rather than at the first integration step.

        Raises:
            SpecError: If the document is not readable as a spec. The message names the plant
                where the document got far enough to say.
        """
        try:
            raw = json.loads(document)
        except json.JSONDecodeError as error:
            raise SpecError(f"not readable as JSON: {error}") from error
        try:
            return cls.model_validate(raw)
        except ValueError as error:
            name = raw.get("plant_id", "<unnamed>") if isinstance(raw, dict) else "<unnamed>"
            raise SpecError(f"document does not describe plant {name!r}: {error}") from error


def pi_controller(spec: PlantSpec, controller_id: str) -> PiController:
    """Return the PI loop a spec declares, built and in its initial state.

    A template asks for its loops by name rather than by position, so adding a loop to a spec
    cannot silently hand an existing one to the wrong part of the process.

    Args:
        spec: The plant.
        controller_id: Which loop.

    Returns:
        The constructed loop.

    Raises:
        KeyError: If the plant declares no such controller.
        SpecError: If it declares one, but as a hysteresis element rather than a PI loop.
    """
    declared = spec.controller(controller_id)
    element = declared.build()
    if not isinstance(element, PiController):
        raise SpecError(
            f"controller {controller_id!r} on plant {spec.plant_id!r} is a "
            f"{declared.kind.value} element, and a PI loop was asked for"
        )
    return element


def fixed_setpoint(spec: PlantSpec, controller_id: str) -> float:
    """Return the fixed target a declared PI loop holds to.

    Args:
        spec: The plant.
        controller_id: Which loop.

    Returns:
        The target.

    Raises:
        KeyError: If the plant declares no such controller.
        SpecError: If that loop holds to a setpoint *signal* rather than a fixed value. A
            template that asked for the wrong one would otherwise silently regulate to ``None``.
    """
    declared = spec.controller(controller_id)
    if declared.setpoint_value is None:
        raise SpecError(
            f"controller {controller_id!r} on plant {spec.plant_id!r} holds to signal "
            f"{declared.setpoint!r}, not to a fixed value"
        )
    return declared.setpoint_value


def signals_of_kind(spec: PlantSpec, kind: SignalKind) -> tuple[str, ...]:
    """Return a spec's signal keys of one kind, in declaration order."""
    return tuple(signal.key for signal in spec.signals if signal.kind is kind)


def component_signals(components: Sequence[Component]) -> tuple[str, ...]:
    """Return every signal the given components own, in component then declaration order."""
    return tuple(key for component in components for key in component.signals)

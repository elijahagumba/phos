"""The graded attack library: each attack, and what a plant must declare for it to exist at all.

Every attack here is built *from the plant's own declaration* rather than from a hand-written
recipe per plant. A correlation break is constructed from a `Coupling` the plant declares; a liar
is refused unless a declared `CouplingKind.CONTROL` relation says some loop will actually believe
the falsified reading; a mimic is refused unless the run genuinely contained the operational event
it claims to be wearing. The point is not elegance. It is that an attack the library built anyway
would be *labelled in ground truth as something it is not*, and D3 would then measure Atlas against
a lie. Refusing is the feature.

**The dial.** `AttackPlan.subtlety` runs from 0 (blatant) to 1 (zero magnitude), and
`strength_of` turns it into the multiplier every manipulation scales by. Turning subtlety up
shrinks the departure monotonically, and at 1.0 the departure is exactly zero — which is the
anti-fingerprint control, not a shipped attack.

The command attacks are the exception, and honestly so. A packet either exists or it does not, so
there is no continuous path to "no command at all". What the dial reaches for them is *one* write,
carrying the value the setpoint already had, from a device with no business sending it. The
irreducible tell of a command attack is who sent it, and that is the correct floor.

**Wire and telemetry must agree.** A rogue write that appeared on the wire while the setpoint it
wrote never moved would be findable by comparing the two outputs of one run — a tell of how D2
assembled the corpus, not of what an attacker did. So a command attack is a *setpoint hold plus
the traffic that would have caused it*: the injection pins the setpoint to exactly the value the
write carries, and the write carries exactly the value the setpoint then reads.

**Three attacks on one setpoint, distinguished by what reaches the wire.** `MIMIC` moves a
setpoint with no write at all, which is an attacker at the PLC. `MIMIC_COMMAND` moves it with a
plausible write from the device that legitimately writes, which is an attacker at the HMI.
`ROGUE_COMMAND` moves it with a write from a device that never writes anything. Same telemetry
shape, three different evidence pictures — which is exactly what D3 needs to find out whether
command visibility is worth anything.
"""

import logging
import statistics
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from phos.synth.attacks.manipulations import (
    ActuatorOffset,
    ActuatorRamp,
    ReadingBlend,
    ReadingTrack,
)
from phos.synth.attacks.spec import AttackPlan, AttackType
from phos.synth.injection import Injection, TimeWindow
from phos.synth.plant import (
    BenignEvent,
    CommandIntent,
    CommandKind,
    ControlNetwork,
    Coupling,
    CouplingKind,
    PlantDescription,
    RunSpec,
    SignalKind,
    SignalSpec,
    register_count,
)
from phos.synth.process import clamp
from phos.synth.run import PlantRun

__all__ = [
    "NormalReference",
    "ScheduledCommand",
    "StagedAttack",
    "stage_attack",
]

logger = logging.getLogger(__name__)

_BLATANT_TRAVEL: Final = 0.6
"""Share of an actuator's travel the blatant attack pushes it through at full magnitude."""

_DRIFT_TRAVEL: Final = 0.45
"""Share of an actuator's travel the stealth drift walks it through across the whole window. Lower
than the blatant figure because it is spread over hours: what makes it stealthy is the increment,
not the total, and the total still has to reach somewhere dangerous."""

_LIAR_DEFICIT: Final = 0.06
"""How far under its setpoint the liar reports, as a share of the instrument's span. Large enough
that a loop acts on it, small enough that "a little under target" is an ordinary thing to read."""

_ROGUE_TRAVEL: Final = 0.35
"""Share of a setpoint's span a rogue command dials it through at full magnitude. Unlike the
mimic, this is free to leave the range the setpoint legitimately takes — that is what makes it
rogue rather than plausible."""

_MAX_COMMANDS: Final = 6
"""Writes a command attack puts on the wire at full magnitude. One at the subtle end."""


@dataclass(frozen=True)
class NormalReference:
    """What normal operation looked like, measured from a clean run of the same plant and seed.

    Every attack is parameterised against this rather than against hand-chosen numbers, and that
    is what lets the library make claims it can keep: a manipulation blended toward a value this
    run actually took cannot leave the range this run actually occupied, so "every signal stays
    inside its own normal range" is true by construction rather than by luck.

    It also carries the *whole* reported series, not a summary. A command attack needs to know
    what a setpoint read at one particular instant, because the value it writes has to be the
    value the setpoint then reports — see the module docstring.

    Attributes:
        description: The plant's declaration. The source of every coupling, span and register
            address the library reasons about.
        spec: The run the reference was measured over. An attack window is validated against it.
        reported: Every signal's reported series, keyed by signal, in sample order.
        events: The benign operational events the clean run contained. What a mimic must be a
            mimic *of*, and what an attack window must not collide with.
        write_issuers: Devices that issued a write on the control network. A rogue command must
            come from outside this set and a mimic command from inside it.
    """

    description: PlantDescription
    spec: RunSpec
    reported: Mapping[str, tuple[float, ...]]
    events: tuple[BenignEvent, ...]
    write_issuers: frozenset[str]

    @classmethod
    def of(cls, run: PlantRun) -> "NormalReference":
        """Measure a clean run.

        Args:
            run: A run of the plant with no injection applied. Nothing checks that it was clean —
                nothing can — so the caller is responsible for handing over a normal run. The
                injector in `phos.synth.attacks.inject` is the only thing that builds one.

        Returns:
            The reference.
        """
        return cls(
            description=run.description,
            spec=run.spec,
            reported={
                key: tuple(step.report.values[key] for step in run.steps)
                for key in run.description.signal_keys()
            },
            events=run.events,
            write_issuers=frozenset(
                intent.issuer
                for step in run.steps
                for intent in step.commands
                if intent.kind is CommandKind.WRITE
            ),
        )

    def series(self, key: str) -> tuple[float, ...]:
        """Return a signal's whole reported series.

        Raises:
            KeyError: If the plant declares no such signal.
        """
        if key not in self.reported:
            raise KeyError(f"plant {self.description.plant_id!r} declares no signal {key!r}")
        return self.reported[key]

    def mean(self, key: str) -> float:
        """Return where a signal normally sits."""
        return statistics.fmean(self.series(key))

    def lowest(self, key: str) -> float:
        """Return the lowest value a signal took in normal operation."""
        return min(self.series(key))

    def highest(self, key: str) -> float:
        """Return the highest value a signal took in normal operation."""
        return max(self.series(key))

    def at(self, key: str, index: int) -> float:
        """Return what a signal reported at one sample.

        Raises:
            KeyError: If the plant declares no such signal.
            IndexError: If the sample is outside the run.
        """
        return self.series(key)[index]

    def step_index(self, clock: datetime) -> int:
        """Return the sample index an instant falls in.

        Raises:
            ValueError: If the instant lies outside the run, which would silently place an attack
                where there is no data to attack.
        """
        offset = (clock - self.spec.start).total_seconds()
        span = self.spec.n_steps * self.spec.interval_seconds
        if offset < 0.0 or offset >= span:
            raise ValueError(
                f"{clock.isoformat()} is outside the run, which spans "
                f"{self.spec.start.isoformat()} for {self.spec.duration}"
            )
        return int(offset // self.spec.interval_seconds)

    def has_event(self, kind: str) -> bool:
        """Return whether the clean run contained an operational event of this kind."""
        return any(event.kind == kind for event in self.events)

    def event_touches(self, kind: str) -> frozenset[str]:
        """Return the signals operational events of this kind change.

        Both routes count: what an operator *wrote on the wire*, and what the event carries in its
        parameters. They are not the same set, and the difference matters. A works run over Modbus
        records a setpoint change as a write; a batch reactor with no control network records the
        same kind of change as a parameter and puts nothing on any wire, because there is no wire.
        Taking only the writes would say that plant performs no setpoint changes at all, and a
        mimic of one would be refused on a plant that genuinely does them.
        """
        return frozenset(
            key
            for event in self.events
            if event.kind == kind
            for key in (*event.writes, *event.parameters)
        )


@dataclass(frozen=True)
class ScheduledCommand:
    """One control-network exchange an attack adds to a run, and the sample it lands on.

    Attributes:
        step_index: The sample the exchange happens at.
        intent: What the exchange was, in D1's own type — so the traffic renderer treats it
            exactly as it treats a cyclic poll or an operator's write, with no branch anywhere
            for "this one is an attack".
    """

    step_index: int
    intent: CommandIntent


@dataclass(frozen=True)
class StagedAttack:
    """A planned attack bound to a plant: how it reaches in, and what it claims to be doing.

    Staged rather than measured. What the attack *did* is only known once the manipulated run has
    been simulated and compared against the clean one, which is `phos.synth.attacks.inject`'s job.

    Attributes:
        plan: The config that produced it.
        window: When it is in force.
        injection: How it reaches the plant, through D1's hook. Every attack has one, including
            the command attacks — a write that changed nothing on the plant would be inconsistent
            with the capture that carried it.
        commands: Extra control-network exchanges it puts on the wire. Empty for the attacks that
            reach the plant without touching the network.
        target_signals: The signals the manipulation acts on directly.
        manipulation: What is being done, in words a reviewer can check against the plant.
    """

    plan: AttackPlan
    window: TimeWindow
    injection: Injection
    commands: tuple[ScheduledCommand, ...]
    target_signals: tuple[str, ...]
    manipulation: str


def stage_attack(plan: AttackPlan, reference: NormalReference) -> StagedAttack:
    """Bind a planned attack to a plant, refusing anything the plant does not support.

    Args:
        plan: The attack to build.
        reference: What normal looked like on the plant it is being built against.

    Returns:
        The staged attack, ready to be run through `phos.synth.run.run_plant`.

    Raises:
        KeyError: If the plan names a signal or a device the plant does not declare.
        ValueError: If the plant cannot support this attack — an actuator attack on something no
            controller drives, a correlation break on a relation the plant never declared, a liar
            no control loop would believe, a mimic of an event that never happened, a rogue
            command from the device that legitimately issues them, or a window that runs off the
            end of the run or across a genuine operator write.
    """
    window = _validated_window(plan, reference)
    builder = _BUILDERS[plan.type]
    injection, commands, targets, words = builder(plan, reference, window)
    logger.debug(
        "staged %s (%s, subtlety %.2f) on %s: %s",
        plan.attack_id,
        plan.type.value,
        plan.subtlety,
        reference.description.plant_id,
        words,
    )
    return StagedAttack(
        plan=plan,
        window=window,
        injection=injection,
        commands=commands,
        target_signals=targets,
        manipulation=words,
    )


_Built = tuple[Injection, tuple[ScheduledCommand, ...], tuple[str, ...], str]


def _validated_window(plan: AttackPlan, reference: NormalReference) -> TimeWindow:
    """Return the plan's window, refusing one that does not fit inside the run.

    Raises:
        ValueError: If either end falls outside the run. An attack half off the end of a corpus
            would be labelled for its whole planned length while only part of it happened.
    """
    window = plan.window(reference.spec.start)
    reference.step_index(window.start)
    last = reference.spec.instant(reference.spec.n_steps - 1)
    if window.end > last:
        raise ValueError(
            f"attack {plan.attack_id!r} ends at {window.end.isoformat()}, outside the run, which "
            f"holds samples up to {last.isoformat()}"
        )
    return window


def _actuator(reference: NormalReference, key: str) -> SignalSpec:
    """Return a declared actuator.

    Raises:
        KeyError: If the plant declares no such signal.
        ValueError: If the signal is not an actuator. Only a final control element can be pushed;
            pushing a measurement would be falsifying telemetry, which is a different attack with
            a different label.
    """
    spec = reference.description.signal(key)
    if spec.kind is not SignalKind.ACTUATOR:
        raise ValueError(
            f"{key!r} is a {spec.kind.value.lower()}, not an actuator; only a final control "
            "element can be driven away from what its controller commanded"
        )
    return spec


def _setpoint(reference: NormalReference, key: str) -> SignalSpec:
    """Return a declared setpoint.

    Raises:
        KeyError: If the plant declares no such signal.
        ValueError: If the signal is not a setpoint. A measurement is not something an operator
            writes, so an attack dressed as one could not be dressed as an operator's action.
    """
    spec = reference.description.signal(key)
    if spec.kind is not SignalKind.SETPOINT:
        raise ValueError(
            f"{key!r} is a {spec.kind.value.lower()}, not a setpoint; only a setpoint is "
            "something an operator legitimately dials in, so only a setpoint can be disguised "
            "as one doing it"
        )
    return spec


def _declared_coupling(description: PlantDescription, driven: str, driver: str) -> Coupling:
    """Return the coupling the plant declares from ``driver`` to ``driven``.

    Raises:
        ValueError: If no such coupling is declared. A correlation break has to break a relation
            the plant *claims* exists, or the label would assert a violation of nothing.
    """
    for coupling in description.couplings:
        if coupling.driven == driven and driver in coupling.drivers:
            return coupling
    raise ValueError(
        f"plant {description.plant_id!r} declares no coupling from {driver!r} to {driven!r}, so "
        "there is no declared relation here to break"
    )


def _control_coupling(description: PlantDescription, measurement: str, setpoint: str) -> Coupling:
    """Return the control loop that acts on ``measurement`` against ``setpoint``.

    Raises:
        ValueError: If no declared control relation joins the two. False data injection is only
            false data injection where something believes the data; falsifying a reading nothing
            acts on moves no plant, and labelling that as driving the true state somewhere
            dangerous would overstate it.
    """
    for coupling in description.couplings:
        if (
            coupling.kind is CouplingKind.CONTROL
            and measurement in coupling.drivers
            and setpoint in coupling.drivers
        ):
            return coupling
    raise ValueError(
        f"plant {description.plant_id!r} declares no control loop acting on {measurement!r} "
        f"against {setpoint!r}, so no control loop would believe a lie told here"
    )


def _network(reference: NormalReference) -> ControlNetwork:
    """Return the plant's control network.

    Raises:
        ValueError: If it has none. A process controlled over something Atlas cannot dissect
            produces no capture, and a command attack on it would be an attack on nothing.
    """
    network = reference.description.control_network
    if network is None:
        raise ValueError(
            f"plant {reference.description.plant_id!r} declares no control network, so it emits "
            "no commands and a command attack on it would put traffic on a wire that does not "
            "exist"
        )
    return network


def _direction(reference: NormalReference, spec: SignalSpec) -> float:
    """Return which way to push a signal: toward whichever end of its span has room.

    A manipulation pushed toward the end the signal already sits near would run out of travel
    before it reached its full magnitude, and the dial would then stop meaning what it says.
    """
    centre = reference.mean(spec.key)
    return -1.0 if (centre - spec.low) > (spec.high - centre) else 1.0


def _refuse_genuine_write(reference: NormalReference, key: str, window: TimeWindow) -> None:
    """Refuse an attack window a genuine operator write to the same signal falls inside.

    Raises:
        ValueError: If one does. Two hands on one setpoint at one moment would leave "who moved
            this" with two answers, and the whole value of synthetic data is that it has one.
    """
    for event in reference.events:
        if key in event.writes and window.contains(event.started_at):
            raise ValueError(
                f"a genuine {event.kind!r} writes {key!r} at {event.started_at.isoformat()}, "
                "inside this attack's window; move the window so ground truth has one answer for "
                "who moved this setpoint"
            )


def _build_blatant(plan: AttackPlan, reference: NormalReference, window: TimeWindow) -> _Built:
    """Push an actuator hard away from what its controller asked for."""
    spec = _actuator(reference, plan.target)
    offset = _direction(reference, spec) * _BLATANT_TRAVEL * (spec.high - spec.low) * plan.strength
    injection = ActuatorOffset(
        actuator=plan.target, offset=offset, low=spec.low, high=spec.high, window=window
    )
    words = (
        f"{plan.target} driven {offset:+.3f} {spec.unit} away from what its controller commanded, "
        f"held for {plan.duration_hours:g} h"
    )
    return injection, (), (plan.target,), words


def _build_stealth_drift(
    plan: AttackPlan, reference: NormalReference, window: TimeWindow
) -> _Built:
    """Walk an actuator away from its controller, a fraction of the noise floor at a time."""
    spec = _actuator(reference, plan.target)
    total = _direction(reference, spec) * _DRIFT_TRAVEL * (spec.high - spec.low) * plan.strength
    injection = ActuatorRamp(
        actuator=plan.target, total_offset=total, low=spec.low, high=spec.high, window=window
    )
    samples = max(1.0, plan.duration_hours * 3600.0 / reference.spec.interval_seconds)
    words = (
        f"{plan.target} walked {total:+.3f} {spec.unit} from its controller's command over "
        f"{plan.duration_hours:g} h, about {abs(total) / samples:.5f} {spec.unit} per sample "
        f"against a measurement noise of {spec.noise_stddev:g}"
    )
    return injection, (), (plan.target,), words


def _build_correlation_break(
    plan: AttackPlan, reference: NormalReference, window: TimeWindow
) -> _Built:
    """Sever a declared relation while leaving both its signals inside their own normal ranges."""
    coupling = _declared_coupling(reference.description, plan.target, plan.reference)
    spec = reference.description.signal(plan.target)
    centre = reference.mean(plan.target)
    injection = ReadingBlend(
        signal=plan.target,
        target=centre,
        strength=plan.strength,
        low=spec.low,
        high=spec.high,
        window=window,
        jitter=spec.noise_stddev,
    )
    words = (
        f"{plan.target} reported toward its own normal centre of {centre:.3f} {spec.unit} while "
        f"{plan.reference} carries on moving, breaking the declared "
        f"{coupling.kind.value.lower()} relation — {coupling.relation}"
    )
    return injection, (), (plan.target,), words


def _build_liar(plan: AttackPlan, reference: NormalReference, window: TimeWindow) -> _Built:
    """Report a measurement permanently short of its setpoint, so its loop over-corrects."""
    loop = _control_coupling(reference.description, plan.target, plan.reference)
    spec = reference.description.signal(plan.target)
    deficit = _LIAR_DEFICIT * (spec.high - spec.low)
    injection = ReadingTrack(
        signal=plan.target,
        reference=plan.reference,
        offset=-deficit,
        strength=plan.strength,
        low=spec.low,
        high=spec.high,
        window=window,
        jitter=spec.noise_stddev,
    )
    words = (
        f"{plan.target} reported {deficit:.3f} {spec.unit} under {plan.reference} whatever it "
        f"truly reads, so the loop driving {loop.driven} corrects a shortfall that is not there "
        "and the true state runs away while the telemetry stays calm"
    )
    return injection, (), (plan.target,), words


def _mimicked_value(plan: AttackPlan, reference: NormalReference, anchor: float) -> float:
    """Return the setpoint a mimic dials in: a value this setpoint legitimately took.

    Raises:
        ValueError: If the run contained no event of the kind being mimicked, or if that kind
            writes something else. A disguise has to be of something the plant genuinely does, or
            the attack is not hiding among anything.
    """
    if not reference.has_event(plan.mimics):
        raise ValueError(
            f"plant {reference.description.plant_id!r} never performed a {plan.mimics!r} in this "
            "run, so there is nothing of that kind to hide among"
        )
    if plan.target not in reference.event_touches(plan.mimics):
        raise ValueError(
            f"a genuine {plan.mimics!r} does not write {plan.target!r}, so moving that setpoint "
            "is not what one looks like"
        )
    low = reference.lowest(plan.target)
    high = reference.highest(plan.target)
    edge = low if (anchor - low) > (high - anchor) else high
    return anchor + plan.strength * (edge - anchor)


def _rogue_value(
    plan: AttackPlan, reference: NormalReference, spec: SignalSpec, anchor: float
) -> float:
    """Return the setpoint a rogue command dials in, free to leave the legitimate range."""
    reach = _direction(reference, spec) * _ROGUE_TRAVEL * (spec.high - spec.low) * plan.strength
    return clamp(anchor + reach, spec.low, spec.high)


def _write_commands(
    plan: AttackPlan,
    reference: NormalReference,
    window: TimeWindow,
    spec: SignalSpec,
    value: float,
) -> tuple[ScheduledCommand, ...]:
    """Return the writes a command attack puts on the wire, spread across its window.

    Every write carries the value the setpoint is pinned to, so the capture and the telemetry
    agree exactly. The ``reason`` recorded here is provenance for ground truth only — the traffic
    renderer never puts it in a byte, so it cannot become a tell.

    Raises:
        KeyError: If the issuing device is not on the plant's network, or the signal is on no
            register block.
        ValueError: If the issuer's write history is the wrong way round for this attack.
    """
    network = _network(reference)
    network.node(plan.issuer)
    writes_legitimately = plan.issuer in reference.write_issuers
    if plan.type is AttackType.ROGUE_COMMAND and writes_legitimately:
        raise ValueError(
            f"{plan.issuer!r} legitimately writes on this network, so a write from it is not a "
            "rogue command; a rogue command comes from a device with no history of issuing one"
        )
    if plan.type is AttackType.MIMIC_COMMAND and not writes_legitimately:
        raise ValueError(
            f"{plan.issuer!r} never writes on this network, so a write from it imitates nobody; "
            "mimicking an operator means using the device that legitimately writes"
        )

    node_id, address = network.address_of(plan.target)
    count = 1 + round(plan.strength * (_MAX_COMMANDS - 1))
    first = reference.step_index(window.start)
    last = reference.step_index(window.end) - 1
    count = min(count, last - first + 1)
    span = last - first
    counts = (register_count(spec, value),)
    return tuple(
        ScheduledCommand(
            step_index=first + round(position * span / count),
            intent=CommandIntent(
                kind=CommandKind.WRITE,
                issuer=plan.issuer,
                target=node_id,
                address=address,
                quantity=1,
                values=counts,
                reason=f"{plan.type.value}: {plan.attack_id}",
            ),
        )
        for position in range(count)
    )


def _build_setpoint_attack(
    plan: AttackPlan, reference: NormalReference, window: TimeWindow
) -> _Built:
    """Hold a setpoint at an attacker's value, with or without the traffic that would explain it.

    The three types that reach a plant through its setpoints share this construction, because the
    difference between them is not what happens to the plant — it is what a network analyst can
    see. See the module docstring.
    """
    if plan.type.is_command_attack:
        _network(reference)
    spec = _setpoint(reference, plan.target)
    _refuse_genuine_write(reference, plan.target, window)

    anchor = reference.at(plan.target, reference.step_index(window.start))
    if plan.type is AttackType.ROGUE_COMMAND:
        value = _rogue_value(plan, reference, spec, anchor)
        shape = "a value no operator has dialled in"
    else:
        value = _mimicked_value(plan, reference, anchor)
        shape = f"a value inside the range a genuine {plan.mimics!r} uses"

    # Strength 1.0, not the plan's: the dial is carried entirely by how far `value` sits from the
    # anchor, so that the setpoint is pinned to exactly the number a write would have carried.
    injection = ReadingBlend(
        signal=plan.target,
        target=value,
        strength=1.0,
        low=spec.low,
        high=spec.high,
        window=window,
        jitter=spec.noise_stddev,
    )
    commands = (
        _write_commands(plan, reference, window, spec, value) if plan.type.is_command_attack else ()
    )
    seen = (
        f"{len(commands)} write(s) from {plan.issuer}"
        if commands
        else "no write anywhere on the network"
    )
    words = (
        f"{plan.target} held at {value:.3f} {spec.unit} — {shape}, against {anchor:.3f} before — "
        f"with {seen}"
    )
    return injection, commands, (plan.target,), words


_Build = Callable[[AttackPlan, NormalReference, TimeWindow], _Built]

_BUILDERS: Final[Mapping[AttackType, _Build]] = {
    AttackType.BLATANT: _build_blatant,
    AttackType.STEALTH_DRIFT: _build_stealth_drift,
    AttackType.CORRELATION_BREAK: _build_correlation_break,
    AttackType.LIAR: _build_liar,
    AttackType.MIMIC: _build_setpoint_attack,
    AttackType.ROGUE_COMMAND: _build_setpoint_attack,
    AttackType.MIMIC_COMMAND: _build_setpoint_attack,
}
"""One builder per detection type. A type absent from this table raises at staging rather than
producing an attack that quietly does nothing — which is the ground truth D1 warned against."""

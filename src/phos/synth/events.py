"""What happens to a plant during a run, and the record that says so.

PART R4. `docs/sim/coverage.md` is the audit this module acts on: most of the *effects* R4 asks
for already exist, in `phos.synth.injection` and `phos.synth.realism`, and what was missing is the
**label** — a record saying what kind of thing happened, which layer it acted on, whether it had a
physical consequence, and whether it stayed inside the instruments' normal ranges.

So this module is mostly labelling and scheduling, and that is the audit working rather than a
shortcut. Two effects here are genuinely new, because nothing in the package produced them:

* `SensorReplay` — a signal reporting its own earlier values. Not the same shape as a drift or a
  bias: a replay is drawn from the plant's own history, so every statistic of the signal taken
  alone is exactly right, and only its disagreement with everything else gives it away.
* `ValveExercise` — a valve stroked through its travel and returned, as routine maintenance.
  Physically a large actuator excursion with no process reason, which is the hardest benign thing
  for a detector to accept.

**Every effect is scheduled from seeds, and nothing here searches.** R4 says so explicitly, and
PART S7's breaker is a separate package for the reason ADR 0435 gives for sealing a family: a
generator that could aim at a detector's weak spot is no longer generating data, it is tuning
against a target. There is nowhere in this module to put a detector's response, and that is
deliberate.

**Most of a run is normal, by construction rather than by luck.** `plan_events` refuses a
catalogue whose events would cover more than a declared fraction of the run, and the fraction is
a named number rather than a literal.

**Nothing here touches a real device.** Every effect acts on in-memory simulated values. The
network-layer effects — modification in transit, a polling flood, replay of captured traffic — act
on the frames `phos.synth.traffic` writes into a file and on nothing else.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Final

from numpy.random import Generator

from phos.synth.injection import HoldActuator, HoldReading, Injection, TimeWindow
from phos.synth.plant import PlantStep, RunSpec, SignalKind, SignalSpec
from phos.synth.plant_spec import PlantSpec
from phos.synth.traffic import WireFrame
from phos.synth.wire import (
    InTransitChange,
    PollBurst,
    TrafficReplay,
    WireManipulation,
    apply_wire_events,
)

__all__ = [
    "INVENTORY_ROLES",
    "MAX_EVENT_FRACTION",
    "EventCatalogue",
    "EventKind",
    "EventLayer",
    "EventRecord",
    "EventSchedule",
    "EventsError",
    "Leak",
    "ScheduledEvent",
    "SensorReplay",
    "ValveExercise",
    "assess_events",
    "plan_events",
]

logger = logging.getLogger(__name__)

MAX_EVENT_FRACTION: Final = 0.25
"""Most of a run must be normal, and this is what "most" means.

A quarter is already generous: a corpus where a quarter of the time something is happening is far
busier than a real plant, and a detector measured on it would see a false-alarm denominator three
times smaller than the one it will meet in service. The number is here, named, so that a change to
it is a change somebody has to argue for."""

MIN_NORMAL_GAP: Final = timedelta(minutes=20)
"""Shortest quiet stretch between two events.

Not merely so that "which event was in force" has one answer — `TimeWindow` is half-open, which
already settles that — but so a detector has somewhere to recover. Two events a minute apart are
one event as far as anything watching is concerned."""


class EventsError(ValueError):
    """Raised when a schedule cannot be laid out as asked."""


class EventKind(StrEnum):
    """What class of thing happened, which is what a scorer counts by.

    Attributes:
        ATTACK: Somebody did this on purpose. Has an issuer.
        FAULT: Equipment went wrong. No issuer, no intent, and shaped like an attack — which is
            the whole difficulty.
        MAINTENANCE: Somebody did this on purpose and was entitled to. A work order covers it.
        OPERATOR: Ordinary operation, including getting it wrong and putting it right.
    """

    ATTACK = "attack"
    FAULT = "fault"
    MAINTENANCE = "maintenance"
    OPERATOR = "operator"


class EventLayer(StrEnum):
    """Where an effect was applied, which decides what could possibly have noticed it.

    R4 asks for this on every record and it is the field the existing `AttackGroundTruth` does not
    carry. It matters because the layer bounds what is detectable: a falsified *reading* leaves the
    process untouched, so only a model of how signals relate can catch it, while a manipulated
    *actuator* moves the plant and a physical model can.

    Attributes:
        SENSOR: What the instruments reported. The true state is unaffected.
        ACTUATOR: What the final control elements did. The process is affected.
        PROCESS: The physical state directly — inventory leaving by a route nothing meters.
        CONTROLLER: A control loop's own settings.
        NETWORK: The frames on the wire. Telemetry and physics are both unaffected.
    """

    SENSOR = "sensor"
    ACTUATOR = "actuator"
    PROCESS = "process"
    CONTROLLER = "controller"
    NETWORK = "network"


@dataclass(frozen=True)
class EventRecord:
    """One thing that happened, in the form R4 asks for and a scorer can read.

    Attributes:
        event_id: Stable identifier within the run.
        kind: Attack, fault, maintenance or ordinary operation.
        type: The technique or the fault type, in this package's own words —
            ``"sensor_replay"``, ``"stuck_valve"``, ``"valve_exercised"``.
        layer: Where the effect was applied.
        started_at: First instant the event covers, UTC.
        ended_at: First instant after it, UTC. Half-open, matching `TimeWindow`.
        signals: The tags it touched.
        physical_effect: Whether the plant's true state moved because of this event, measured
            over *every* signal rather than only the one the event named. Measured by
            `assess_events` rather than declared, because intent is not consequence — and because
            a sensor-layer falsification does move the process, through the loop that believes
            it. That is not an accident of the model; it is the reason a fabricated reading is
            worth attacking with (see `phos.synth.process.PiController`).
        within_normal_range: Whether every reading the plant produced during the event stayed
            inside the band that signal occupies when nothing is happening. Measured, not
            declared, and over every signal: a manipulation meant to be stealthy can overshoot,
            and an actuator stroked through its travel disturbs the signals above it even though
            the actuator's own reading is of course inside the actuator's own range.
        technique: The closest public ICS ATT&CK technique, or ``""``. A reading of the technique
            descriptions rather than an authoritative classification — see
            ``docs/sim/coverage.md``.
        issuer: The device or person responsible, for an attack or an operator action. Empty for
            a fault, which has nobody.
        detail: What happened, in a sentence.
    """

    event_id: str
    kind: EventKind
    type: str
    layer: EventLayer
    started_at: datetime
    ended_at: datetime
    signals: tuple[str, ...] = ()
    physical_effect: bool = False
    within_normal_range: bool = True
    technique: str = ""
    issuer: str = ""
    detail: str = ""

    @property
    def window(self) -> TimeWindow:
        """The span this event covers."""
        return TimeWindow(start=self.started_at, end=self.ended_at)

    def document(self) -> dict[str, object]:
        """Return the record as the labels file carries it."""
        return {
            "event_id": self.event_id,
            "kind": self.kind.value,
            "type": self.type,
            "layer": self.layer.value,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat(),
            "signals": list(self.signals),
            "physical_effect": self.physical_effect,
            "within_normal_range": self.within_normal_range,
            "technique": self.technique,
            "issuer": self.issuer,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class SensorReplay:
    """A signal reporting a stretch of its own earlier values, over and over.

    The one sensor-layer gap the audit found. A replay is not a drift and not a bias: the values
    are the plant's own, so the signal's mean, its variance, its rate of change and its
    autocorrelation are all exactly what they should be. Nothing about the signal *by itself* is
    wrong. What is wrong is that it no longer agrees with anything else — the level stops
    responding to the flows, the temperature stops responding to the duty — which is why this is
    the manipulation that separates a joint model from a per-signal one.

    Looping rather than running out: a real replay runs as long as the attacker needs it to, and a
    recording that stopped would announce itself at the moment it stopped.

    Attributes:
        window: When the replay is in force.
        signal: The tag being replayed.
        samples: The recorded values, in order. Captured from this plant's own earlier output by
            `plan_events`, which is what an attacker with a tap would have.
        interval: The spacing the samples were recorded at.

    Invariants:
        There is at least one sample and the interval is positive. A pure function of the clock,
        as `Injection` requires: nothing here counts calls.
    """

    window: TimeWindow
    signal: str
    samples: tuple[float, ...]
    interval: timedelta

    def __post_init__(self) -> None:
        """Refuse a replay with nothing to play.

        Raises:
            EventsError: If there are no samples, or the interval is not positive. Either would
                make the manipulation a silent no-op, which is worse than an error.
        """
        if not self.samples:
            raise EventsError(f"a replay of {self.signal!r} has no recorded samples")
        if self.interval <= timedelta(0):
            raise EventsError(f"a replay of {self.signal!r} has a non-positive interval")

    def actuator_overrides(
        self, clock: datetime, commanded: Mapping[str, float]
    ) -> Mapping[str, float]:
        """Return no overrides: a replay acts on what is reported, not on what is done."""
        del clock, commanded
        return {}

    def reading_overrides(
        self, clock: datetime, readings: Mapping[str, float]
    ) -> Mapping[str, float]:
        """Return the recorded value for this instant, while the replay is in force."""
        del readings
        if not self.window.contains(clock):
            return {}
        elapsed = (clock - self.window.start).total_seconds()
        index = int(elapsed // self.interval.total_seconds()) % len(self.samples)
        return {self.signal: self.samples[index]}


@dataclass(frozen=True)
class ValveExercise:
    """A valve stroked through its travel and returned, as routine maintenance.

    The hardest benign thing in the catalogue for a detector to accept, which is exactly why it is
    worth generating. Physically it is a large actuator excursion with no process reason: the
    valve goes to one end of its travel, comes back to the other, and returns to where the loop
    wanted it — and the process is disturbed the whole time, because the valve really did move.
    A detector that has learned "a big unexplained actuator movement is an attack" will call this
    one every time, and it will be wrong, and a work order says so.

    The stroke is a triangle in time rather than a step, because a valve has a travel time and an
    instantaneous full-travel move is not a thing an actuator does.

    Attributes:
        window: When the exercise runs.
        actuator: The tag being stroked.
        low: One end of the travel.
        high: The other end.

    Invariants:
        ``low < high``. A pure function of the clock.
    """

    window: TimeWindow
    actuator: str
    low: float
    high: float

    def __post_init__(self) -> None:
        """Refuse a stroke with no travel.

        Raises:
            EventsError: If the two ends are the same or inverted, which exercises nothing.
        """
        if not self.low < self.high:
            raise EventsError(
                f"exercising {self.actuator!r} from {self.low} to {self.high} is no travel at all"
            )

    def actuator_overrides(
        self, clock: datetime, commanded: Mapping[str, float]
    ) -> Mapping[str, float]:
        """Return where the stroke has the valve at this instant."""
        del commanded
        if not self.window.contains(clock):
            return {}
        span = (self.window.end - self.window.start).total_seconds()
        if span <= 0.0:
            return {}
        fraction = (clock - self.window.start).total_seconds() / span
        # Out and back: up through the travel over the first half, down over the second.
        position = 2.0 * fraction if fraction < 0.5 else 2.0 * (1.0 - fraction)
        return {self.actuator: self.low + (self.high - self.low) * position}

    def reading_overrides(
        self, clock: datetime, readings: Mapping[str, float]
    ) -> Mapping[str, float]:
        """Return no overrides: the valve really moved, so the instruments tell the truth."""
        del clock, readings
        return {}


INVENTORY_ROLES: Final = frozenset({"level", "charge", "segment_pressure"})
"""Roles whose signal is a stored inventory a leak can drain.

A leak removes material that was being *held* — a tank's level, a batch vessel's charge, a
pipeline segment's pressure. There is no meaning to leaking from a temperature or a flow, so a
plant with no inventory signal has no leak to plan.

**Two of the five open families genuinely have none**, and that is a fact about them rather than
an omission. A heated vessel chain holds fluid, but its holdup is a *parameter* and no instrument
is on it; a generating set stores nothing at all. A leak on either would have to be aimed at a
temperature or a current, so it is refused — or skipped, where the caller asked for what a plant
can host rather than for a specific list. See `plan_events`."""


@dataclass(frozen=True)
class Leak:
    """Inventory draining from the process by a route nothing meters.

    A process-layer fault, through `phos.synth.injection.ProcessLoss`: it removes material from the
    true state directly — no actuator opened, no instrument on the loss — and the consequences
    follow from the physics. The level falls, the loop sees it through the sensor and pumps harder,
    the measured inflow rises to chase a level that keeps sinking. Nothing is painted on; the
    inventory really is lower, and everything downstream follows.

    It is the one fault a conservation check is built to catch. What leaves by the leak is in none
    of the declared inflows or outflows, so the balance stops closing — which is exactly how a real
    leak is found, and why a fault that merely edited the telemetry would be the giveaway that it
    was never a leak.

    Attributes:
        window: When the leak is open.
        signal: The inventory signal it drains.
        per_step: How much to remove from that signal each sample, in its engineering unit. A
            per-step amount rather than a rate so that `state_losses` is a pure lookup and the
            plant's sampling interval has already been accounted for by `plan_events`.

    Invariants:
        The per-step amount is positive. A pure function of the clock.
    """

    window: TimeWindow
    signal: str
    per_step: float

    def __post_init__(self) -> None:
        """Refuse a leak that drains nothing.

        Raises:
            EventsError: If the per-step amount is not positive.
        """
        if self.per_step <= 0.0:
            raise EventsError(f"a leak of {self.signal!r} removes {self.per_step} per step")

    def actuator_overrides(
        self, clock: datetime, commanded: Mapping[str, float]
    ) -> Mapping[str, float]:
        """Return no overrides: a leak commands no actuator."""
        del clock, commanded
        return {}

    def reading_overrides(
        self, clock: datetime, readings: Mapping[str, float]
    ) -> Mapping[str, float]:
        """Return no overrides: a leak falsifies nothing. The instruments read the lower level."""
        del clock, readings
        return {}

    def state_losses(self, clock: datetime, state: Mapping[str, float]) -> Mapping[str, float]:
        """Return the inventory drained this step, while the leak is open."""
        del state
        return {self.signal: self.per_step} if self.window.contains(clock) else {}


@dataclass(frozen=True)
class ScheduledEvent:
    """One planned event: what it does, and the record that says what it was.

    An event acts on exactly one of two places. A plant-layer or process-layer event carries an
    `injection` and no `wire`; a network-layer event carries a `wire` and no `injection`, because
    its effect is on the capture and the plant never sees it. Both are never set at once — the
    layer in the record says which, and the schedule routes each to the right place.

    Attributes:
        record: The label, before the facts that can only be measured are filled in.
        injection: The plant- or process-layer effect, or ``None`` for a network-layer event.
        wire: The network-layer manipulation, or ``None`` for a plant- or process-layer event.
    """

    record: EventRecord
    injection: Injection | None = None
    wire: WireManipulation | None = None


@dataclass(frozen=True)
class EventCatalogue:
    """How many of each kind of thing to put in a run.

    Counts rather than rates, so a schedule is reproducible from a seed without depending on how
    long the run happens to be — and so that asking for more than will fit is an error rather
        than a silent truncation.

    Attributes:
        sensor_replays: Attacks replaying a signal's own earlier values.
        stuck_valves: Faults pinning an actuator where it stands.
        pump_trips: Faults driving an actuator to zero.
        leaks: Faults removing inventory by a route nothing meters. Needs a process-layer hook;
            zero until PART R4's second half builds one.
        sensors_offline: Maintenance taking a transmitter out of service.
        valves_exercised: Maintenance stroking a valve through its travel.
        loops_in_manual: Maintenance holding a loop's output while somebody works on it.
        operator_slips: An operator writing a setpoint wrong and correcting it. Deferred; see
            ``docs/sim/coverage.md``. Left at zero.
        in_transit_changes: Network-layer attacks holding one meter's reported value on the wire.
        poll_bursts: Network-layer polling floods.
        traffic_replays: Network-layer replays of a captured window.
        event_minutes: How long one event lasts, as ``(low, high)`` minutes, drawn per event.
    """

    sensor_replays: int = 0
    stuck_valves: int = 0
    pump_trips: int = 0
    leaks: int = 0
    sensors_offline: int = 0
    valves_exercised: int = 0
    loops_in_manual: int = 0
    operator_slips: int = 0
    in_transit_changes: int = 0
    poll_bursts: int = 0
    traffic_replays: int = 0
    event_minutes: tuple[float, float] = (20.0, 120.0)

    def total(self) -> int:
        """How many events this catalogue asks for."""
        return (
            self.sensor_replays
            + self.stuck_valves
            + self.pump_trips
            + self.leaks
            + self.sensors_offline
            + self.valves_exercised
            + self.loops_in_manual
            + self.operator_slips
            + self.in_transit_changes
            + self.poll_bursts
            + self.traffic_replays
        )

    def __post_init__(self) -> None:
        """Refuse a catalogue that does not describe a schedule.

        Raises:
            EventsError: If a count is negative or the duration range is empty.
        """
        low, high = self.event_minutes
        if low <= 0.0 or high < low:
            raise EventsError(f"event_minutes {self.event_minutes} is not a range of durations")


@dataclass(frozen=True)
class EventSchedule:
    """Everything planned for one run, and the one injection that applies it.

    Attributes:
        events: The planned events, in time order.
        run: The run they were laid out over.
        skipped: One line per event the plant could not host, when `plan_events` was asked to
            skip rather than refuse. Empty otherwise. Kept so a caller that asked for "whatever
            this plant can carry" can report what that turned out to exclude, instead of the
            absence being invisible.
    """

    events: tuple[ScheduledEvent, ...]
    run: RunSpec
    skipped: tuple[str, ...] = ()

    @property
    def records(self) -> tuple[EventRecord, ...]:
        """Every event's label, in time order."""
        return tuple(event.record for event in self.events)

    def injection(self) -> Injection | None:
        """Return the one injection that applies every effect, or ``None`` if there are none.

        ``None`` rather than an empty composite so that a run with no events takes exactly the
        path a run given no injection takes — which is what keeps a corpus with an empty
        catalogue byte-identical to one generated before events existed.
        """
        parts = [event.injection for event in self.events if event.injection is not None]
        if not parts:
            return None
        if len(parts) == 1:
            return parts[0]
        from phos.synth.injection import CompositeInjection

        return CompositeInjection(parts=parts)

    def apply_to_capture(self, frames: Sequence[WireFrame]) -> tuple[WireFrame, ...]:
        """Return the capture with every network-layer event applied, in schedule order.

        A plant- or process-layer event is already in the frames, because it changed the run the
        capture was built from. A network-layer event is not — it acts on the wire alone — so it
        is applied here. With no network events the frames are returned unchanged, which keeps a
        corpus whose catalogue has none byte-identical.
        """
        changes = [event.wire for event in self.events if isinstance(event.wire, InTransitChange)]
        bursts = [event.wire for event in self.events if isinstance(event.wire, PollBurst)]
        replays = [event.wire for event in self.events if isinstance(event.wire, TrafficReplay)]
        return apply_wire_events(frames, changes=changes, bursts=bursts, replays=replays)

    def covered_seconds(self) -> float:
        """How much of the run has something happening in it, double-counting nothing."""
        spans = sorted((record.started_at, record.ended_at) for record in self.records)
        covered = 0.0
        current_end: datetime | None = None
        for start, end in spans:
            if current_end is None or start >= current_end:
                covered += (end - start).total_seconds()
                current_end = end
            elif end > current_end:
                covered += (end - current_end).total_seconds()
                current_end = end
        return covered

    def normal_fraction(self) -> float:
        """What fraction of the run nothing is happening in."""
        total = self.run.duration.total_seconds()
        return 1.0 - self.covered_seconds() / total if total > 0.0 else 1.0


def plan_events(
    spec: PlantSpec,
    run: RunSpec,
    rng: Generator,
    catalogue: EventCatalogue,
    history: Sequence[PlantStep] = (),
    skip_impossible: bool = False,
) -> EventSchedule:
    """Lay a catalogue of events out over a run, leaving most of it normal.

    Args:
        spec: The plant the events happen to.
        run: The run to lay them out over.
        rng: Where the placement and the parameters are drawn from. A stream of its own, so that
            changing the event schedule cannot move a single physical parameter.
        catalogue: How many of each kind to place.
        history: A completed normal run of this plant, used as the recording a `SensorReplay`
            plays back. Empty means no replay can be planned, and asking for one is an error
            rather than a silently dropped event — an attacker needs a tap before a replay.
        skip_impossible: Whether to skip an event this plant cannot host rather than refuse the
            whole schedule. ``False`` by default, because a specific request for a specific event
            should fail loudly if it cannot be met. ``True`` is for a caller asking for *whatever
            this plant can carry* — the command line's ``--events N`` across families with
            different physics — and what was skipped is recorded in `EventSchedule.skipped` so it
            is reported rather than lost.

    Returns:
        The schedule, with every event's record.

    Raises:
        EventsError: If the events will not fit while leaving `MAX_EVENT_FRACTION` of the run
            normal, if the plant has no signal of the kind an event needs, or if a replay was
            asked for without a recording.
    """
    if catalogue.total() == 0:
        return EventSchedule(events=(), run=run)

    windows = _windows(run, rng, catalogue)
    description = spec.describe()
    actuators = description.keys_of_kind(SignalKind.ACTUATOR)
    sensors = tuple(signal for signal in spec.signals if signal.kind is SignalKind.SENSOR)
    if not actuators or not sensors:
        raise EventsError(
            f"plant {spec.plant_id!r} has {len(actuators)} actuator(s) and {len(sensors)} "
            "sensor(s); there is nothing for an event to act on"
        )
    wire_wanted = catalogue.in_transit_changes + catalogue.poll_bursts + catalogue.traffic_replays
    if wire_wanted and spec.control_network is None:
        raise EventsError(
            f"plant {spec.plant_id!r} has no control network, so there is no wire to carry a "
            "network-layer event; ask for none on a process run over something Atlas cannot see"
        )

    planned: list[ScheduledEvent] = []
    issue = iter(windows)
    for _ in range(catalogue.sensor_replays):
        planned.append(_replay(spec, next(issue), rng, sensors, history))
    for _ in range(catalogue.stuck_valves):
        planned.append(_stuck_valve(next(issue), rng, actuators, history))
    for _ in range(catalogue.pump_trips):
        planned.append(_pump_trip(next(issue), rng, actuators))
    skipped: list[str] = []
    for _ in range(catalogue.leaks):
        window = next(issue)
        try:
            planned.append(_leak(window, rng, spec, run))
        except EventsError:
            if not skip_impossible:
                raise
            skipped.append("leak: this process stores no inventory to drain")
    for _ in range(catalogue.sensors_offline):
        planned.append(_sensor_offline(next(issue), rng, sensors))
    for _ in range(catalogue.valves_exercised):
        planned.append(_valve_exercised(next(issue), rng, spec, actuators))
    for _ in range(catalogue.loops_in_manual):
        planned.append(_loop_in_manual(next(issue), rng, actuators, history))
    for _ in range(catalogue.in_transit_changes):
        planned.append(_in_transit(next(issue), rng, spec))
    for _ in range(catalogue.poll_bursts):
        planned.append(_poll_burst(next(issue), rng, spec, run))
    for _ in range(catalogue.traffic_replays):
        planned.append(_traffic_replay(next(issue), run))

    planned.sort(key=lambda event: event.record.started_at)
    schedule = EventSchedule(events=tuple(planned), run=run, skipped=tuple(skipped))
    normal = schedule.normal_fraction()
    if normal < 1.0 - MAX_EVENT_FRACTION:
        raise EventsError(
            f"{catalogue.total()} event(s) would leave only {normal:.2%} of the run normal, "
            f"below the {1.0 - MAX_EVENT_FRACTION:.2%} a corpus must keep. Ask for fewer, or for "
            "shorter ones."
        )
    logger.debug(
        "%s: %d event(s), %.0f%% of the run normal",
        spec.plant_id,
        len(planned),
        normal * 100.0,
    )
    return schedule


def _windows(run: RunSpec, rng: Generator, catalogue: EventCatalogue) -> tuple[TimeWindow, ...]:
    """Lay out non-overlapping windows with a quiet stretch between each.

    Placed by walking forward from a start offset rather than by drawing instants and sorting,
    because drawing and sorting gives no control over the gaps and would quietly let two events
    abut — which reads as one event to anything watching.

    Raises:
        EventsError: If the run is too short to hold the events with their gaps.
    """
    count = catalogue.total()
    low, high = catalogue.event_minutes
    durations = [timedelta(minutes=float(rng.uniform(low, high))) for _ in range(count)]
    needed = sum(durations, timedelta()) + MIN_NORMAL_GAP * (count + 1)
    if needed > run.duration:
        raise EventsError(
            f"{count} event(s) of {low:g} to {high:g} minutes with {MIN_NORMAL_GAP} between them "
            f"need {needed}, and the run is {run.duration}"
        )

    slack = (run.duration - needed).total_seconds()
    offsets = (
        sorted(float(rng.uniform(0.0, slack)) for _ in range(count)) if slack > 0 else [0.0] * count
    )
    windows: list[TimeWindow] = []
    cursor = run.start + MIN_NORMAL_GAP
    previous_offset = 0.0
    for duration, offset in zip(durations, offsets, strict=True):
        cursor += timedelta(seconds=offset - previous_offset)
        previous_offset = offset
        windows.append(TimeWindow(start=cursor, end=cursor + duration))
        cursor += duration + MIN_NORMAL_GAP
    return tuple(windows)


def _pick(rng: Generator, options: Sequence[str]) -> str:
    """Choose one option, from a sequence so the choice is reproducible."""
    return options[int(rng.integers(0, len(options)))]


def _replay(
    spec: PlantSpec,
    window: TimeWindow,
    rng: Generator,
    sensors: Sequence[SignalSpec],
    history: Sequence[PlantStep],
) -> ScheduledEvent:
    """Plan a sensor replay from a stretch of the plant's own earlier output.

    Raises:
        EventsError: If there is no recording. An attacker needs a tap before a replay, and
            inventing the values would make this a fabrication rather than a replay.
    """
    if not history:
        raise EventsError(
            "a sensor replay needs a recording of the plant's own earlier output; run the plant "
            "normally first and pass the steps as `history`"
        )
    signal = sensors[int(rng.integers(0, len(sensors)))]
    length = min(len(history), max(4, len(history) // 4))
    start = int(rng.integers(0, max(1, len(history) - length)))
    samples = tuple(step.report.values[signal.key] for step in history[start : start + length])
    interval = (
        history[1].timestamp - history[0].timestamp if len(history) > 1 else timedelta(seconds=30)
    )
    return ScheduledEvent(
        record=EventRecord(
            event_id=f"replay-{signal.key}-{window.start:%Y%m%dT%H%M%S}",
            kind=EventKind.ATTACK,
            type="sensor_replay",
            layer=EventLayer.SENSOR,
            started_at=window.start,
            ended_at=window.end,
            signals=(signal.key,),
            physical_effect=False,
            technique="T0856 Spoof Reporting Message",
            issuer="unknown",
            detail=(
                f"{signal.key} reports {len(samples)} of its own earlier readings on a loop, so "
                "every statistic of the signal alone is correct and only its disagreement with "
                "the rest of the plant gives it away"
            ),
        ),
        injection=SensorReplay(
            window=window, signal=signal.key, samples=samples, interval=interval
        ),
    )


def _held_at(actuator: str, window: TimeWindow, history: Sequence[PlantStep], what: str) -> float:
    """Return where an actuator was when a window opened, from a normal run of the same plant.

    `Injection` implementations must be pure functions of their arguments, so an effect that means
    "stay where you are" cannot discover that for itself — it has no memory and is forbidden one.
    The value is therefore read out of a normal run, the same way `SensorReplay` gets its
    recording: an effect that depends on the plant's own behaviour needs the plant to have
    behaved first.

    Raises:
        EventsError: If there is no normal run to read it from. Holding at an invented number
            would turn a stuck valve into a valve driven somewhere, which is a different fault.
    """
    if not history:
        raise EventsError(
            f"{what} on {actuator!r} has to hold the actuator where it was, which needs a normal "
            "run of this plant to read it from; pass the steps as `history`"
        )
    for step in history:
        if step.timestamp >= window.start:
            return step.truth.values[actuator]
    return history[-1].truth.values[actuator]


def _stuck_valve(
    window: TimeWindow,
    rng: Generator,
    actuators: Sequence[str],
    history: Sequence[PlantStep],
) -> ScheduledEvent:
    """Plan a valve that stops responding where it stands."""
    actuator = _pick(rng, actuators)
    held = _held_at(actuator, window, history, "a stuck valve")
    return ScheduledEvent(
        record=EventRecord(
            event_id=f"stuck-{actuator}-{window.start:%Y%m%dT%H%M%S}",
            kind=EventKind.FAULT,
            type="stuck_valve",
            layer=EventLayer.ACTUATOR,
            started_at=window.start,
            ended_at=window.end,
            signals=(actuator,),
            physical_effect=True,
            detail=(
                f"{actuator} stops responding and stays at {held:.2f}, where it happened to be; "
                "its loop keeps asking and nothing happens, so the integral winds up while the "
                "process drifts"
            ),
        ),
        injection=HoldActuator(actuator=actuator, value=held, window=window),
    )


def _pump_trip(window: TimeWindow, rng: Generator, actuators: Sequence[str]) -> ScheduledEvent:
    """Plan a machine stopping."""
    actuator = _pick(rng, actuators)
    return ScheduledEvent(
        record=EventRecord(
            event_id=f"trip-{actuator}-{window.start:%Y%m%dT%H%M%S}",
            kind=EventKind.FAULT,
            type="pump_trip",
            layer=EventLayer.ACTUATOR,
            started_at=window.start,
            ended_at=window.end,
            signals=(actuator,),
            physical_effect=True,
            detail=f"{actuator} trips to zero and stays there until it is reset",
        ),
        injection=HoldActuator(actuator=actuator, value=0.0, window=window),
    )


def _leak(window: TimeWindow, rng: Generator, spec: PlantSpec, run: RunSpec) -> ScheduledEvent:
    """Plan a leak draining one of the plant's inventory signals.

    Raises:
        EventsError: If the plant has no inventory signal to drain — a leak means nothing on a
            process that stores none, and aiming it at a temperature would be the wrong fault.
    """
    candidates = [
        signal
        for signal in spec.signals
        if signal.kind is SignalKind.SENSOR
        and (role := spec.role_of(signal.key)) is not None
        and role.role in INVENTORY_ROLES
    ]
    if not candidates:
        raise EventsError(
            f"plant {spec.plant_id!r} has no inventory signal (a level or a pressure) to leak "
            "from; a leak cannot be planned on a process that stores none"
        )
    signal = candidates[int(rng.integers(0, len(candidates)))]
    span = signal.high - signal.low
    # Drain a tenth to a half of the span over the window, drawn, then spread evenly across the
    # samples in it so the per-step amount is independent of the sampling rate.
    fraction = float(rng.uniform(0.1, 0.5))
    steps_in_window = max(
        1, int((window.end - window.start).total_seconds() // run.interval_seconds)
    )
    per_step = span * fraction / steps_in_window
    return ScheduledEvent(
        record=EventRecord(
            event_id=f"leak-{signal.key}-{window.start:%Y%m%dT%H%M%S}",
            kind=EventKind.FAULT,
            type="leak",
            layer=EventLayer.PROCESS,
            started_at=window.start,
            ended_at=window.end,
            signals=(signal.key,),
            physical_effect=True,
            detail=(
                f"{signal.key} drains by {span * fraction:.2f} {signal.unit} over the window, by a "
                "route nothing meters; the loop chases the falling inventory, and the conservation "
                "balance stops closing because what left is in no declared flow"
            ),
        ),
        injection=Leak(window=window, signal=signal.key, per_step=per_step),
    )


def _block_address(spec: PlantSpec, rng: Generator) -> tuple[int, str]:
    """Return a readable register block's start address and the signal it carries first."""
    network = spec.control_network
    assert network is not None  # guarded in plan_events
    readable = [block for block in network.blocks if not block.writable and block.signals]
    block = readable[int(rng.integers(0, len(readable)))]
    return block.start_address, block.signals[0]


def _in_transit(window: TimeWindow, rng: Generator, spec: PlantSpec) -> ScheduledEvent:
    """Plan a reported value held on the wire, between the device and the historian."""
    address, signal = _block_address(spec, rng)
    held = int(rng.integers(0, 0x10000))
    return ScheduledEvent(
        record=EventRecord(
            event_id=f"in-transit-{address}-{window.start:%Y%m%dT%H%M%S}",
            kind=EventKind.ATTACK,
            type="value_modification_in_transit",
            layer=EventLayer.NETWORK,
            started_at=window.start,
            ended_at=window.end,
            signals=(signal,),
            physical_effect=False,
            technique="T0830 Adversary-in-the-Middle",
            issuer="unknown",
            detail=(
                f"{signal} is held at a false count on the wire while the plant carries on; the "
                "historian and the operator see the false value, the process does not"
            ),
        ),
        wire=InTransitChange(window=window, address=address, held_count=held),
    )


def _poll_burst(
    window: TimeWindow, rng: Generator, spec: PlantSpec, run: RunSpec
) -> ScheduledEvent:
    """Plan a polling flood against a device in the window."""
    address, _ = _block_address(spec, rng)
    count = int((window.end - window.start).total_seconds() / max(run.interval_seconds, 1.0) * 20)
    return ScheduledEvent(
        record=EventRecord(
            event_id=f"poll-burst-{address}-{window.start:%Y%m%dT%H%M%S}",
            kind=EventKind.ATTACK,
            type="polling_flood",
            layer=EventLayer.NETWORK,
            started_at=window.start,
            ended_at=window.end,
            physical_effect=False,
            technique="T0814 Denial of Service",
            issuer="unknown",
            detail=(
                f"a device is read about {count} times across the window, far above its scan "
                "rate, which no honest poll loop produces"
            ),
        ),
        wire=PollBurst(window=window, count=max(count, 1), template_address=address),
    )


def _traffic_replay(window: TimeWindow, run: RunSpec) -> ScheduledEvent:
    """Plan a replay of an earlier window of traffic into this one.

    The copied window is a fixed short span at the very start of the run, which the scheduler
    guarantees is before any event window — so the replay never overlaps its own source however
    early the destination is placed.
    """
    source = TimeWindow(
        start=run.start, end=run.start + min(MIN_NORMAL_GAP, window.end - window.start)
    )
    return ScheduledEvent(
        record=EventRecord(
            event_id=f"replay-wire-{window.start:%Y%m%dT%H%M%S}",
            kind=EventKind.ATTACK,
            type="traffic_replay",
            layer=EventLayer.NETWORK,
            started_at=window.start,
            ended_at=window.end,
            physical_effect=False,
            technique="T0830 Adversary-in-the-Middle",
            issuer="unknown",
            detail=(
                "a window of earlier traffic is copied onto the wire again, genuine frames and "
                "all, so it reports what the plant was doing then while it does something else now"
            ),
        ),
        wire=TrafficReplay(source=source, at=window),
    )


def _sensor_offline(
    window: TimeWindow, rng: Generator, sensors: Sequence[SignalSpec]
) -> ScheduledEvent:
    """Plan a transmitter taken out of service, with a work order behind it."""
    signal = sensors[int(rng.integers(0, len(sensors)))]
    held = signal.low + (signal.high - signal.low) * 0.5
    return ScheduledEvent(
        record=EventRecord(
            event_id=f"offline-{signal.key}-{window.start:%Y%m%dT%H%M%S}",
            kind=EventKind.MAINTENANCE,
            type="sensor_offline",
            layer=EventLayer.SENSOR,
            started_at=window.start,
            ended_at=window.end,
            signals=(signal.key,),
            physical_effect=False,
            issuer="maintenance",
            detail=(
                f"{signal.key} is out of service for calibration and reads a held value. Looks "
                "exactly like a frozen transmitter, and is not one, because a work order covers it"
            ),
        ),
        injection=HoldReading(signal=signal.key, value=held, window=window),
    )


def _valve_exercised(
    window: TimeWindow, rng: Generator, spec: PlantSpec, actuators: Sequence[str]
) -> ScheduledEvent:
    """Plan a valve stroked through its travel and returned."""
    actuator = _pick(rng, actuators)
    signal = spec.describe().signal(actuator)
    return ScheduledEvent(
        record=EventRecord(
            event_id=f"exercise-{actuator}-{window.start:%Y%m%dT%H%M%S}",
            kind=EventKind.MAINTENANCE,
            type="valve_exercised",
            layer=EventLayer.ACTUATOR,
            started_at=window.start,
            ended_at=window.end,
            signals=(actuator,),
            physical_effect=True,
            issuer="maintenance",
            detail=(
                f"{actuator} is stroked from {signal.low:g} to {signal.high:g} and back under a "
                "work order. The process really is disturbed, because the valve really moved"
            ),
        ),
        injection=ValveExercise(window=window, actuator=actuator, low=signal.low, high=signal.high),
    )


def _loop_in_manual(
    window: TimeWindow,
    rng: Generator,
    actuators: Sequence[str],
    history: Sequence[PlantStep],
) -> ScheduledEvent:
    """Plan a loop held while somebody works on it."""
    actuator = _pick(rng, actuators)
    held = _held_at(actuator, window, history, "a loop in manual")
    return ScheduledEvent(
        record=EventRecord(
            event_id=f"manual-{actuator}-{window.start:%Y%m%dT%H%M%S}",
            kind=EventKind.MAINTENANCE,
            type="controller_in_manual",
            layer=EventLayer.ACTUATOR,
            started_at=window.start,
            ended_at=window.end,
            signals=(actuator,),
            physical_effect=True,
            issuer="operator",
            detail=(
                f"{actuator}'s loop is put in manual at {held:.2f} while work goes on, then "
                "handed back. The same shape as a stuck valve, and entirely legitimate"
            ),
        ),
        injection=HoldActuator(actuator=actuator, value=held, window=window),
    )


def assess_events(
    records: Sequence[EventRecord],
    normal: Sequence[PlantStep],
    disturbed: Sequence[PlantStep],
) -> tuple[EventRecord, ...]:
    """Fill in the two facts about an event that can only be measured.

    R4 asks every record to say whether a physical effect occurred and whether the event stayed
    inside normal sensor ranges. Neither is knowable when the event is planned: a manipulation
    *meant* to be stealthy can overshoot, and one meant to move the process can fail to. Declaring
    them would make a stealth result unearned, so they are measured by comparing the disturbed run
    against the same plant run normally.

    Args:
        records: The planned records.
        normal: The same plant, same seed, no events.
        disturbed: The run the events were applied to.

    Returns:
        The records with ``physical_effect`` and ``within_normal_range`` as measured.

    Raises:
        EventsError: If the two runs are not the same length, which would make every comparison
            meaningless rather than merely wrong.
    """
    if len(normal) != len(disturbed):
        raise EventsError(
            f"the normal run has {len(normal)} samples and the disturbed one {len(disturbed)}; "
            "they must be the same run with and without events"
        )
    # What "normal range" means here is the range normal operation actually occupies, not the
    # instrument's calibrated span. A report is clamped into its span by `phos.synth.plant`, so a
    # check against the span can never fail and would call every manipulation stealthy. The
    # honest question is whether the event pushed a reading outside where that reading goes when
    # nothing is happening — which is what a detector watching ranges would have to notice.
    envelope = _normal_envelope(normal)

    assessed: list[EventRecord] = []
    for record in records:
        inside = record.window
        moved = False
        in_range = True
        for plain, actual in zip(normal, disturbed, strict=True):
            if not inside.contains(actual.timestamp):
                continue
            # Both questions are asked of the *whole plant*, not only of the tag the event names.
            # An actuator stroked through its travel disturbs the level above it, and measuring
            # only the actuator would call that stealthy because a valve's own reading is of
            # course inside a valve's own range. What a detector watches is every signal, so what
            # is measured is every signal.
            for key, true_value in actual.truth.values.items():
                if abs(true_value - plain.truth.values[key]) > _MOVED_TOLERANCE:
                    moved = True
                low, high = envelope[key]
                margin = (high - low) * _ENVELOPE_TOLERANCE
                if not low - margin <= actual.report.values[key] <= high + margin:
                    in_range = False
        assessed.append(
            EventRecord(
                event_id=record.event_id,
                kind=record.kind,
                type=record.type,
                layer=record.layer,
                started_at=record.started_at,
                ended_at=record.ended_at,
                signals=record.signals,
                physical_effect=moved,
                within_normal_range=in_range,
                technique=record.technique,
                issuer=record.issuer,
                detail=record.detail,
            )
        )
    return tuple(assessed)


_MOVED_TOLERANCE: Final = 1e-9
"""How far the true state must differ from a normal run to count as having moved.

Floating-point slack rather than a physical threshold: the two runs are the same plant on the same
seed, so outside an event's influence they are bit-identical, and any difference at all is the
event's doing."""

_ENVELOPE_TOLERANCE: Final = 0.02
"""How far outside normal operation's own range a reading may go and still count as inside it.

Not zero, because the normal run and the disturbed run have the same sensor noise only where the
event is not acting: a signal the event never touched can still sit a hair outside the normal
envelope at an instant, and calling that "left the normal range" would make the measure useless.
Two percent of the envelope is well inside what a detector watching ranges could act on."""


def _normal_envelope(normal: Sequence[PlantStep]) -> dict[str, tuple[float, float]]:
    """Return the range each signal's reading occupies over a run with nothing happening.

    This is the reference "normal range" that a stealthy event has to stay inside. It is measured
    from the plant rather than declared, because a signal's calibrated span is much wider than the
    band it actually lives in — a level transmitter spanning nought to eight metres on a works
    that holds three is a span no manipulation would ever leave.
    """
    if not normal:
        return {}
    envelope: dict[str, tuple[float, float]] = {}
    for key in normal[0].report.values:
        series = [step.report.values[key] for step in normal]
        envelope[key] = (min(series), max(series))
    return envelope

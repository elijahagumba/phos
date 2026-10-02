"""The injection hook: how something outside the simulation reaches inside it.

D1 builds no attacks. What it builds is the *door* an attack will later come through, and the
door has to be designed before anything walks through it, because a door added afterwards leaves
marks. This module is that design.

**Two ways in, and they are the two a real attacker has.**

1. `actuator_overrides` replaces what the controller commanded before the physics runs. That is
   an attacker who has moved a final control element — written a coil, driven a valve, changed a
   speed reference. The plant then responds exactly as it would to any other actuator position,
   because it *is* an actuator position: nothing downstream knows the number came from anywhere
   unusual.
2. `reading_overrides` replaces what an instrument reported after the physics runs. That is an
   attacker who has falsified telemetry — a compromised PLC, a manipulated historian feed. The
   true process state is unaffected and keeps evolving; only the report lies.

The second is the interesting one, and it is only interesting because of a decision made in
`phos.synth.plant`: **control loops act on reported readings, never on the true state.** A
fabricated reading therefore has physical consequences — the controller believes it and acts —
rather than being a cosmetic edit to a column of numbers.

**The contract that makes a manipulated run fight fair.** Anything a run does differently because
an injection was present must be the manipulation itself, never an artefact of the machinery that
delivered it. Three rules hold that line, and `tests/synth/test_plant.py` enforces all three:

- *An injection is consulted on every step, unconditionally.* `NoInjection` is a real object that
  returns empty mappings, not a ``None`` that skips a branch, so the code path is identical
  whether or not anything is attached.
- *An injection never touches the plant's random stream.* It is handed values and a clock and
  nothing else. The plant draws a fixed-size block of noise once per step before any injection is
  consulted, so the noise a run sees cannot shift by so much as one draw.
- *An empty override mapping is a no-op by construction*, because applying it copies the same
  values through the same code.

The consequence, stated as a property: a run with an injection whose window has not opened yet is
**bit-identical** to a run with no injection at all. After the window opens the runs diverge, and
they diverge because the plant genuinely moved — which is the only difference an attack should
leave.

**Nothing here is an attack, and nothing here is labelled.** `HoldActuator` and `HoldReading` are
mechanism — "put this actuator at this value between these times", "report this instead of that".
Attack intent, staging and ground-truth labelling are D2's, built on top of these.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

__all__ = [
    "CompositeInjection",
    "HoldActuator",
    "HoldReading",
    "Injection",
    "NoInjection",
    "TimeWindow",
]


@dataclass(frozen=True)
class TimeWindow:
    """A half-open span an injection is active over, ``[start, end)``.

    Half-open so that two consecutive windows tile time without an instant belonging to both,
    which would make "which manipulation was in force here" ambiguous for D2's labelling.

    Attributes:
        start: First instant the window covers, UTC.
        end: First instant after it, UTC.
    """

    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        """Refuse an inverted window.

        Raises:
            ValueError: If ``end`` precedes ``start``, which covers no time and would silently
                do nothing.
        """
        if self.end < self.start:
            raise ValueError(f"window is inverted: {self.start} > {self.end}")

    def contains(self, clock: datetime) -> bool:
        """Return whether ``clock`` falls in the window, start inclusive, end exclusive."""
        return self.start <= clock < self.end


@runtime_checkable
class Injection(Protocol):
    """Something that perturbs a plant from outside, through the plant's own mechanisms.

    Implementations must be **pure functions of their arguments**. In particular they must not
    draw random numbers from the plant, must not mutate what they are handed, and must not depend
    on how many times they have been called: the plant consults an injection on every step, and a
    call count that mattered would make the manipulation depend on the sampling rate rather than
    on the clock.
    """

    def actuator_overrides(
        self, clock: datetime, commanded: Mapping[str, float]
    ) -> Mapping[str, float]:
        """Return actuator values to apply instead of what the controller commanded.

        Args:
            clock: The instant being simulated, UTC.
            commanded: What each control loop asked for, keyed by actuator signal.

        Returns:
            The subset of actuators to override, and what to hold them at. Empty for no
            manipulation — which is the normal case, and is a no-op by construction.
        """
        ...

    def reading_overrides(
        self, clock: datetime, readings: Mapping[str, float]
    ) -> Mapping[str, float]:
        """Return values to report instead of what the instruments measured.

        Args:
            clock: The instant being simulated, UTC.
            readings: What each instrument measured from the true state, keyed by signal.

        Returns:
            The subset of signals to falsify, and what to report for them. Empty for no
            manipulation. The true state is unaffected either way — that separation is what lets
            D2 label a fabricated reading honestly.
        """
        ...


@dataclass(frozen=True)
class NoInjection:
    """The absence of a manipulation, as an object rather than as a missing branch.

    A plant always has an injection. Normal operation is this one. That is why a normal run and a
    run through an inactive injection execute the same code in the same order — the property the
    whole hook depends on.
    """

    def actuator_overrides(
        self, clock: datetime, commanded: Mapping[str, float]
    ) -> Mapping[str, float]:
        """Return no overrides."""
        return {}

    def reading_overrides(
        self, clock: datetime, readings: Mapping[str, float]
    ) -> Mapping[str, float]:
        """Return no overrides."""
        return {}


@dataclass(frozen=True)
class HoldActuator:
    """Hold one actuator at a fixed value for a window, whatever the controller asks for.

    Mechanism, not attack: this is what "an actuator was moved and stayed moved" looks like from
    inside the plant, and it is the same thing whether the hand on it was an operator's or an
    intruder's. Deciding which, and labelling it, is D2's.

    Attributes:
        actuator: Signal key of the actuator to hold. Must be a declared actuator of the plant;
            the plant refuses an unknown key rather than silently doing nothing.
        value: The value to hold it at, in the actuator's own engineering unit.
        window: When the hold is in force.
    """

    actuator: str
    value: float
    window: TimeWindow

    def actuator_overrides(
        self, clock: datetime, commanded: Mapping[str, float]
    ) -> Mapping[str, float]:
        """Return the held actuator while the window is open."""
        if self.window.contains(clock):
            return {self.actuator: self.value}
        return {}

    def reading_overrides(
        self, clock: datetime, readings: Mapping[str, float]
    ) -> Mapping[str, float]:
        """Return no overrides: this manipulation moves plant, it does not falsify telemetry."""
        return {}


@dataclass(frozen=True)
class HoldReading:
    """Report a fixed value for one signal for a window, whatever the instrument measured.

    The true state carries on evolving underneath, which is exactly the situation D2's fabricated
    telemetry will need and exactly why `phos.synth.plant` records truth separately from report.

    Attributes:
        signal: Signal key to falsify. Must be a declared signal of the plant.
        value: The value to report, in the signal's own engineering unit.
        window: When the falsification is in force.
    """

    signal: str
    value: float
    window: TimeWindow

    def actuator_overrides(
        self, clock: datetime, commanded: Mapping[str, float]
    ) -> Mapping[str, float]:
        """Return no overrides: this manipulation falsifies telemetry, it does not move plant."""
        return {}

    def reading_overrides(
        self, clock: datetime, readings: Mapping[str, float]
    ) -> Mapping[str, float]:
        """Return the falsified reading while the window is open."""
        if self.window.contains(clock):
            return {self.signal: self.value}
        return {}


@dataclass(frozen=True)
class CompositeInjection:
    """Several injections applied together, in order.

    Later parts win a conflict over the same key. Stated rather than left to chance, because a
    composite whose resolution order was undefined would make a D2 scenario non-reproducible.

    Attributes:
        parts: The injections to apply, in precedence order — last wins.
    """

    parts: Sequence[Injection]

    def actuator_overrides(
        self, clock: datetime, commanded: Mapping[str, float]
    ) -> Mapping[str, float]:
        """Return every part's actuator overrides, merged with later parts winning."""
        merged: dict[str, float] = {}
        for part in self.parts:
            merged.update(part.actuator_overrides(clock, commanded))
        return merged

    def reading_overrides(
        self, clock: datetime, readings: Mapping[str, float]
    ) -> Mapping[str, float]:
        """Return every part's reading overrides, merged with later parts winning."""
        merged: dict[str, float] = {}
        for part in self.parts:
            merged.update(part.reading_overrides(clock, readings))
        return merged

"""The four ways D2 reaches into a plant, and why each is a no-op when turned all the way down.

These are `phos.synth.injection.Injection` implementations and nothing more. They carry no attack
semantics, no labels and no knowledge of which plant they are pointed at — a `ReadingBlend` is
"report this instead of that, partially" whether the hand on it is an intruder's or a calibration
technician's. `phos.synth.attacks.library` decides what each one *means*, and
`phos.synth.attacks.spec` records it.

D1 supplies two of these already: `HoldActuator` and `HoldReading` put a signal at an *absolute*
value. D2 needs the relative forms instead, and the reason is the difficulty dial. A manipulation
has to be able to shrink continuously to nothing, and an absolute hold cannot: "hold this valve at
90%" is either applied or not, with no path to zero magnitude. Every manipulation here is defined
as a *departure* from what the plant was going to do anyway, so multiplying that departure by
`strength_of(1.0)` — which is exactly ``0.0`` — hands back the value that was handed in.

**Three properties every manipulation upholds, all tested directly:**

* *Closed outside its window.* No override at all before it opens or after it closes, so D1's
  bit-identity property extends unchanged to every attack D2 builds.
* *A no-op at zero magnitude.* The arithmetic is applied unconditionally and happens to be
  identity. There is no branch that skips it, because a branch is a difference in the code path
  and the whole discipline here is that there is only one code path.
* *Bounded by the instrument's span.* D1's `_sense` bounds every reading by the transmitter's
  calibrated span, so a falsified reading that sat outside it would be findable by a range check
  that no normal reading ever trips. That is a tell of the injection rather than of the attack,
  and it is exactly the kind of leak that would make every later detection number worthless.
  Actuator manipulations are bounded for the physical counterpart of the same reason: a valve
  cannot be driven past its stops.

**Why a falsified reading carries jitter.** Pull a reading all the way onto a chosen value and the
signal goes perfectly smooth, and a transmitter that suddenly stopped being noisy announces itself
to the crudest variance check there is. That would let a detector find the *injection* rather than
the attack, which is the failure this whole discipline exists to prevent. So a falsified reading
carries pseudo-noise: deterministic, a pure function of the clock and the signal's name, and drawn
from `pseudo_noise` rather than from the plant — because touching the plant's random stream is the
one thing D1's hook forbids. The library sets the jitter to the signal's *own declared*
``noise_stddev``, which makes it right in every case including the case where the right answer is
zero: a setpoint declares no noise, so a held setpoint stays exactly constant, which is what a real
setpoint does.

The residual, stated rather than hidden: pseudo-noise reproduces the instrument's noise and not
its slow calibration drift, whose phase is drawn from the plant's setup generator and cannot be
reconstructed from outside. At full strength a falsified signal is therefore drift-free. See the
ADR.
"""

import zlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from phos.synth.injection import TimeWindow
from phos.synth.process import clamp

__all__ = [
    "ActuatorOffset",
    "ActuatorRamp",
    "ReadingBlend",
    "ReadingTrack",
    "pseudo_noise",
]

_MIX_A: Final = 0x9E3779B97F4A7C15
_MIX_B: Final = 0xBF58476D1CE4E5B9
_MIX_C: Final = 0x94D049BB133111EB
_MASK: Final = 0xFFFFFFFFFFFFFFFF
_DEVIATES: Final = 3
"""Uniform draws summed per sample. Three is the smallest number whose sum on [-1, 1) has a
standard deviation of exactly one — variance 1/3 each — so the result needs no rescaling and its
shape is already a passable bell rather than a flat top."""


def _uniform(seed: int) -> float:
    """Return a deterministic value in ``[-1, 1)`` from an integer, via splitmix64's finaliser."""
    mixed = (seed + _MIX_A) & _MASK
    mixed = ((mixed ^ (mixed >> 30)) * _MIX_B) & _MASK
    mixed = ((mixed ^ (mixed >> 27)) * _MIX_C) & _MASK
    mixed ^= mixed >> 31
    return mixed / float(1 << 63) - 1.0


def pseudo_noise(clock: datetime, signal: str) -> float:
    """Return a deterministic deviate of unit standard deviation for one signal at one instant.

    Pure, reproducible, and drawn from nothing the plant owns. An injection may not touch the
    plant's random stream — that is what keeps the per-step randomness rate constant and the
    bit-identity property provable — so a manipulation that needs noise has to make its own.

    Args:
        clock: The instant, UTC. Quantised to the millisecond, so two runs of the same spec draw
            the same deviates.
        signal: The signal the deviate is for. Two falsified signals get uncorrelated noise
            rather than the same series twice, which would be a correlation no plant has.

    Returns:
        A deviate with mean zero and standard deviation one.
    """
    ticks = int(clock.timestamp() * 1000.0)
    stream = zlib.crc32(signal.encode("utf-8"))
    return sum(_uniform(ticks * _DEVIATES + stream + offset) for offset in range(_DEVIATES))


def _check_span(low: float, high: float) -> None:
    """Refuse an inverted or empty span.

    Raises:
        ValueError: If ``low`` is not below ``high``. A manipulation bounded by an empty span
            would pin its signal to a constant, which looks exactly like a plant that is steady.
    """
    if low >= high:
        raise ValueError(f"manipulation declares an empty span: low={low}, high={high}")


def _require(values: Mapping[str, float], key: str, noun: str) -> float:
    """Return ``values[key]``, refusing an absence rather than substituting a default.

    Raises:
        KeyError: If the key is absent. A manipulation that quietly did nothing because it named
            the wrong signal would be labelled as an attack that quietly did nothing, which is
            the worst ground truth a corpus can carry.
    """
    if key not in values:
        raise KeyError(f"manipulation names {noun} {key!r}, which this step does not carry")
    return values[key]


@dataclass(frozen=True)
class ActuatorOffset:
    """Push one actuator a fixed distance from wherever the controller put it.

    The blunt instrument: a valve driven open, a pump driven hard, a dose driven up. Because the
    departure is relative to the commanded position rather than absolute, the plant keeps
    controlling around it and the manipulation stays the same size whatever the loop is doing.

    Attributes:
        actuator: Signal key of the actuator to push. Must be a declared actuator of the plant.
        offset: How far to push it, in the actuator's own engineering unit. Signed.
        low: Bottom of the actuator's travel.
        high: Top of its travel.
        window: When the push is in force.
    """

    actuator: str
    offset: float
    low: float
    high: float
    window: TimeWindow

    def __post_init__(self) -> None:
        """Refuse an empty span."""
        _check_span(self.low, self.high)

    def actuator_overrides(
        self, clock: datetime, commanded: Mapping[str, float]
    ) -> Mapping[str, float]:
        """Return the actuator pushed by the offset, bounded by its travel."""
        if not self.window.contains(clock):
            return {}
        commanded_value = _require(commanded, self.actuator, "actuator")
        return {self.actuator: clamp(commanded_value + self.offset, self.low, self.high)}

    def reading_overrides(
        self, clock: datetime, readings: Mapping[str, float]
    ) -> Mapping[str, float]:
        """Return no overrides: this moves plant, and the instruments report it honestly."""
        return {}


@dataclass(frozen=True)
class ActuatorRamp:
    """Walk one actuator away from the controller's command, a little at a time.

    The offset grows linearly from nothing at the window's start to ``total_offset`` at its end,
    so no single sample carries a step larger than ``total_offset`` divided by the number of
    samples in the window. Over a long enough window each increment sits under the instrument's
    own noise and reads as ordinary drift, while the accumulated departure is large. That is the
    attack: it is invisible to any view of normal built on how far one reading is from the last.

    Attributes:
        actuator: Signal key of the actuator to walk.
        total_offset: The departure reached at the far end of the window. Signed.
        low: Bottom of the actuator's travel.
        high: Top of its travel.
        window: When the walk is in force, and the span the ramp is measured across.
    """

    actuator: str
    total_offset: float
    low: float
    high: float
    window: TimeWindow

    def __post_init__(self) -> None:
        """Refuse an empty span or a window of no width.

        Raises:
            ValueError: If the window covers no time, which would make the ramp's slope
                undefined rather than merely steep.
        """
        _check_span(self.low, self.high)
        if self.window.end <= self.window.start:
            raise ValueError("a ramp needs a window with width; this one covers no time")

    def actuator_overrides(
        self, clock: datetime, commanded: Mapping[str, float]
    ) -> Mapping[str, float]:
        """Return the actuator walked by however far the ramp has got, bounded by its travel."""
        if not self.window.contains(clock):
            return {}
        commanded_value = _require(commanded, self.actuator, "actuator")
        elapsed = (clock - self.window.start).total_seconds()
        span = (self.window.end - self.window.start).total_seconds()
        reached = self.total_offset * (elapsed / span)
        return {self.actuator: clamp(commanded_value + reached, self.low, self.high)}

    def reading_overrides(
        self, clock: datetime, readings: Mapping[str, float]
    ) -> Mapping[str, float]:
        """Return no overrides: this moves plant, and the instruments report it honestly."""
        return {}


@dataclass(frozen=True)
class ReadingBlend:
    """Pull one instrument's report toward a fixed value, by a fraction of the way.

    At full strength the instrument reports the target and nothing else, which severs whatever
    relationship the signal had with the rest of the plant. At lower strengths it reports
    something between the truth and the target, so the relationship is weakened rather than cut —
    which is the same attack, harder to see.

    The true process state is untouched. Whether that matters depends on the signal: a reading a
    control loop consumes is physically consequential, because the loop believes it; a reading
    nothing consumes is a lie told only to whoever is watching.

    Attributes:
        signal: Signal key to falsify. Must be a declared signal of the plant.
        target: The value to pull the report toward, in the signal's own engineering unit.
        strength: How far to pull it, ``0.0`` (no change) to ``1.0`` (report the target).
        low: Bottom of the instrument's calibrated span.
        high: Top of it.
        window: When the falsification is in force.
        jitter: Standard deviation of the pseudo-noise the falsified value carries, in the
            signal's engineering unit. Zero leaves it perfectly smooth, which is right for a
            setpoint and a giveaway for anything else — see the module docstring.
    """

    signal: str
    target: float
    strength: float
    low: float
    high: float
    window: TimeWindow
    jitter: float = 0.0

    def __post_init__(self) -> None:
        """Refuse an empty span."""
        _check_span(self.low, self.high)

    def actuator_overrides(
        self, clock: datetime, commanded: Mapping[str, float]
    ) -> Mapping[str, float]:
        """Return no overrides: this falsifies telemetry and moves no plant directly."""
        return {}

    def reading_overrides(
        self, clock: datetime, readings: Mapping[str, float]
    ) -> Mapping[str, float]:
        """Return the report pulled toward the target, bounded by the instrument's span."""
        if not self.window.contains(clock):
            return {}
        measured = _require(readings, self.signal, "signal")
        aimed = self.target + self.jitter * pseudo_noise(clock, self.signal)
        blended = measured + self.strength * (aimed - measured)
        return {self.signal: clamp(blended, self.low, self.high)}


@dataclass(frozen=True)
class ReadingTrack:
    """Pull one instrument's report toward a value quoted against *another* reported signal.

    This is what makes false data injection convincing. A falsified reading pinned to a constant
    is calm but dead, and stops looking normal the moment the plant's operating point moves. A
    falsified reading quoted against a setpoint — "always a little under target" — stays plausible
    through setpoint changes, shift patterns and everything else an operator does, because it is
    tracking the same thing the honest reading would have tracked.

    Pointed at a signal a control loop consumes, it is also physically consequential in the worst
    way: the loop is told it is slightly short of target, acts to correct a deficit that is not
    there, and is told again. The report stays calm precisely while the true state runs away.

    Attributes:
        signal: Signal key to falsify.
        reference: Signal key whose *reported* value the falsification is quoted against. Read
            from the same step's readings, so it follows the reference wherever it goes.
        offset: How far from the reference to report, in the signal's engineering unit. Signed.
        strength: How far to pull the report toward that value, ``0.0`` to ``1.0``.
        low: Bottom of the instrument's calibrated span.
        high: Top of it.
        window: When the falsification is in force.
        jitter: Standard deviation of the pseudo-noise the falsified value carries. A fabricated
            level that never wobbles is a fabricated level anyone can spot.
    """

    signal: str
    reference: str
    offset: float
    strength: float
    low: float
    high: float
    window: TimeWindow
    jitter: float = 0.0

    def __post_init__(self) -> None:
        """Refuse an empty span."""
        _check_span(self.low, self.high)

    def actuator_overrides(
        self, clock: datetime, commanded: Mapping[str, float]
    ) -> Mapping[str, float]:
        """Return no overrides.

        The plant moves because a control loop believes the falsified reading, not because this
        manipulation touched an actuator. That indirection is the whole attack.
        """
        return {}

    def reading_overrides(
        self, clock: datetime, readings: Mapping[str, float]
    ) -> Mapping[str, float]:
        """Return the report pulled toward the reference plus the offset, bounded by the span."""
        if not self.window.contains(clock):
            return {}
        measured = _require(readings, self.signal, "signal")
        reference = _require(readings, self.reference, "reference signal")
        aimed = reference + self.offset + self.jitter * pseudo_noise(clock, self.signal)
        blended = measured + self.strength * (aimed - measured)
        return {self.signal: clamp(blended, self.low, self.high)}

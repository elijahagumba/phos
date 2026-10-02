"""The primitives a simulated plant is assembled from: accumulation, lag, rhythm, control.

A plant is realistic to exactly the degree that its signals are produced by *mechanism* rather
than by drawing from a distribution that happens to look right. These are the mechanisms. A tank
level is an `accumulate` over net flow; a temperature is a `first_order` lag toward what the
jacket is doing; a demand curve is a `cycle_factor`; a valve position is whatever a `PiController`
decided the last time it looked at a reading. Nothing in `phos.synth.plants` writes a signal
directly as noise around a constant.

They live in one module, apart from any particular plant, for two reasons. The arithmetic is
shared — three plants integrate, three plants lag — and it can be tested for what the name claims
without reference to any process. And a controller is a *stateful* object, so having exactly one
implementation means the anti-windup argument is made once and holds everywhere.

**Nothing here draws a random number.** Randomness enters a plant in two places only — the sensor
model and the benign-event schedule — both seeded from one place in `phos.synth.plant`. A
primitive that reached for a generator of its own would put a third, unseeded stream into a
system whose whole claim is reproducibility (Constitution §3.7).
"""

import math
from dataclasses import dataclass, field

__all__ = [
    "Hysteresis",
    "PiController",
    "accumulate",
    "clamp",
    "cycle_factor",
    "first_order",
    "shift_index",
    "square_law_flow",
]


def clamp(value: float, low: float, high: float) -> float:
    """Return ``value`` confined to ``[low, high]``.

    Args:
        value: The number to confine.
        low: Inclusive lower bound.
        high: Inclusive upper bound.

    Returns:
        The bounded value.

    Raises:
        ValueError: If the bounds are inverted. Silently returning ``low`` for every input would
            pin a signal to a constant and look exactly like a plant that is simply steady.
    """
    if low > high:
        raise ValueError(f"bounds are inverted: low={low} exceeds high={high}")
    return max(low, min(high, value))


def accumulate(
    current: float, rate_per_second: float, dt_seconds: float, low: float, high: float
) -> float:
    """Advance an accumulating quantity by a rate applied over an interval.

    This is what makes a tank level a *level* rather than a number that resembles one: it is the
    running integral of net inflow, so it can only change as fast as the flows into and out of it
    allow. The physical coupling every level signal in `phos.synth.plants` declares is this
    function.

    Args:
        current: The present quantity.
        rate_per_second: Net rate of change, in units of the quantity per second. Negative draws
            the quantity down.
        dt_seconds: Length of the interval.
        low: Physical floor — a vessel does not hold a negative volume.
        high: Physical ceiling — a full vessel overflows rather than continuing to fill.

    Returns:
        The advanced quantity, bounded.
    """
    return clamp(current + rate_per_second * dt_seconds, low, high)


def first_order(current: float, target: float, dt_seconds: float, tau_seconds: float) -> float:
    """Move a lagging quantity toward a target by one exponential step.

    Real plant does not arrive: a jacket warms toward the coolant temperature, a transformer's oil
    warms toward what its loading implies, and both take a time constant to get most of the way.
    Using the exact exponential rather than a Euler step keeps the result stable for any step
    size, which matters because the sample interval is the integration step here.

    Args:
        current: The present value.
        target: The value the quantity is heading toward.
        dt_seconds: Length of the interval.
        tau_seconds: Time constant — one of them covers ``1 - 1/e`` of the remaining gap.

    Returns:
        The advanced value. Equal to ``current`` when it already sits on the target.

    Raises:
        ValueError: If the time constant is not positive, which describes no lag at all.
    """
    if tau_seconds <= 0.0:
        raise ValueError(f"time constant must be positive, got {tau_seconds}")
    return current + (target - current) * (1.0 - math.exp(-dt_seconds / tau_seconds))


def cycle_factor(
    elapsed_hours: float, period_hours: float, amplitude: float, phase_hours: float
) -> float:
    """Return the value of a smooth cycle at a point in time.

    The daily rhythm of a water network's demand, the ambient temperature a transformer sits in,
    the diurnal load a feeder carries — an industrial signal that repeats does so on a clock, and
    this is that clock. Zero at its phase, peaking a quarter-period later.

    Args:
        elapsed_hours: Hours since the run began.
        period_hours: Length of one full cycle.
        amplitude: Peak departure from zero.
        phase_hours: Where in the cycle the run began.

    Returns:
        The cycle's contribution, in ``[-amplitude, amplitude]``.

    Raises:
        ValueError: If the period is not positive, which describes no cycle.
    """
    if period_hours <= 0.0:
        raise ValueError(f"period must be positive, got {period_hours}")
    return amplitude * math.sin(2.0 * math.pi * (elapsed_hours - phase_hours) / period_hours)


def shift_index(elapsed_hours: float, shift_hours: float, shifts: int) -> int:
    """Return which operating shift a moment falls in.

    Plants run to a roster as well as to a clock, and the step between one shift's operating point
    and the next is a discontinuity no sinusoid produces. Keeping the two apart matters for D2:
    an attacker who moves a setpoint is hiding among shift changes, not among smooth cycles.

    Args:
        elapsed_hours: Hours since the run began.
        shift_hours: Length of one shift.
        shifts: How many shifts make a day.

    Returns:
        The zero-based index of the shift, cycling with the day.

    Raises:
        ValueError: If the shifts do not tile a 24-hour day, which would make the index drift
            against the daily cycle it is supposed to sit beside.
    """
    day = shift_hours * shifts
    if not math.isclose(day, 24.0):
        raise ValueError(
            f"{shifts} shift(s) of {shift_hours}h do not tile the day; they span {day}h"
        )
    return int((elapsed_hours % day) // shift_hours)


def square_law_flow(opening_percent: float, maximum_flow: float) -> float:
    """Return the flow a valve passes at a given opening.

    Flow through a restriction goes with the square root of the pressure drop across it, so a
    valve's opening and the flow it passes are not proportional — half open passes appreciably
    more than half the flow. Modelling that is what makes a valve's signal and a flow signal
    *coupled but not identical*, which is precisely the structure a joint model has to learn.

    Args:
        opening_percent: Valve opening, 0 to 100. Below zero is treated as shut rather than
            producing the root of a negative number.
        maximum_flow: Flow at full opening, in whatever unit the plant uses.

    Returns:
        The flow passed.
    """
    fraction = clamp(opening_percent, 0.0, 100.0) / 100.0
    return maximum_flow * math.sqrt(fraction)


@dataclass
class PiController:
    """A proportional-integral loop with back-calculated anti-windup.

    One implementation, used by every closed loop in every plant, so that the awkward part —
    what the integral does while the actuator is against its stop — is argued once. The method is
    back-calculation: the integral is corrected by however much the output had to be clipped, so
    a loop that saturates recovers as soon as the error reverses instead of staying pinned while
    a stale integral unwinds.

    **Controllers act on what the sensors report, never on the true process state.** That is how a
    real loop works and it is load-bearing for the rest of the engine: it is the reason a
    fabricated reading has physical consequences rather than cosmetic ones.

    Mutable by design — a controller *is* its accumulated state — so one instance belongs to one
    plant instance and is never shared.

    Attributes:
        gain: Proportional gain. Positive; the direction of action is `reverse_acting`.
        integral_time_seconds: Seconds for the integral term to repeat the proportional one.
            Smaller integrates faster.
        low: Lower limit of the actuator this loop drives.
        high: Upper limit of the actuator this loop drives.
        reverse_acting: ``False`` for a loop whose output must rise when the measurement falls
            (filling a tank); ``True`` for one whose output must rise when the measurement rises
            (cooling a reactor). Named as a control engineer would name it.
    """

    gain: float
    integral_time_seconds: float
    low: float
    high: float
    reverse_acting: bool = False
    _integral: float = field(default=0.0, init=False, repr=False)

    def __post_init__(self) -> None:
        """Refuse settings that describe no loop.

        Raises:
            ValueError: If the gain or the integral time is not positive, or the output limits
                are inverted.
        """
        if self.gain <= 0.0:
            raise ValueError(f"gain must be positive, got {self.gain}; use reverse_acting for sign")
        if self.integral_time_seconds <= 0.0:
            raise ValueError(f"integral time must be positive, got {self.integral_time_seconds}")
        if self.low > self.high:
            raise ValueError(f"output limits are inverted: low={self.low} exceeds high={self.high}")

    @property
    def integral(self) -> float:
        """The accumulated term, exposed so anti-windup can be asserted rather than assumed."""
        return self._integral

    def update(
        self, measurement: float, setpoint: float, dt_seconds: float, bias: float = 0.0
    ) -> float:
        """Advance the loop by one interval and return the actuator output.

        Args:
            measurement: What the instrument *reported*, not what the plant is truly doing.
            setpoint: The value the loop is holding to.
            dt_seconds: Length of the interval.
            bias: Feedforward contribution added before the loop's own terms — a dose rate
                proportional to flow, a fuel demand proportional to dispatch. Real loops carry
                one, and it keeps the integral from having to supply the whole operating point.

        Returns:
            The output, bounded by the actuator's limits.
        """
        error = measurement - setpoint if self.reverse_acting else setpoint - measurement
        proposed = self._integral + error * dt_seconds / self.integral_time_seconds
        raw = bias + self.gain * (error + proposed)
        output = clamp(raw, self.low, self.high)
        self._integral = proposed + (output - raw) / self.gain
        return output


@dataclass
class Hysteresis:
    """An on/off element that switches on one bound and off on another.

    Not every industrial control is modulating. A duty pump starts when a level falls through its
    start point and runs until the level rises through its stop point, and the gap between the two
    is what stops it chattering. That gap also gives a plant a *discrete* behaviour alongside its
    continuous ones, which is a different shape of normal for a model to learn.

    Attributes:
        on_below: Engages when the measurement falls below this.
        off_above: Releases when the measurement rises above this.
        engaged: Present state. Mutable — this element is its state.
    """

    on_below: float
    off_above: float
    engaged: bool = False

    def __post_init__(self) -> None:
        """Refuse a band that is the wrong way round.

        Raises:
            ValueError: If ``on_below`` is not below ``off_above``, which describes an element
                that switches on and off at the same measurement and chatters every step.
        """
        if self.on_below >= self.off_above:
            raise ValueError(
                f"band is inverted: on_below={self.on_below} must sit below "
                f"off_above={self.off_above}"
            )

    def update(self, measurement: float) -> bool:
        """Advance the element and return whether it is now engaged.

        Args:
            measurement: What the instrument reported.

        Returns:
            The state after this measurement. Unchanged while the measurement sits inside the
            band, which is the whole purpose of the band.
        """
        if self.engaged:
            if measurement > self.off_above:
                self.engaged = False
        elif measurement < self.on_below:
            self.engaged = True
        return self.engaged

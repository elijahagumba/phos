"""The four ways D2 reaches into a plant, and the properties that keep them from cheating.

Three properties are checked for every manipulation here, because they are what stop an attack
being findable by its machinery rather than by its effect:

* **Closed outside its window.** No override at all before it opens or after it closes.
* **A no-op at zero strength.** Not "small" — the value handed back is the value handed in, bit
  for bit, so a fully subtle attack produces a run identical to a normal one.
* **Inside the instrument's span.** D1 bounds every reading by the transmitter's calibrated span.
  A falsified reading that sat outside it would be findable by a range check that no normal
  reading ever trips, which is a tell of the injection and not of the attack.
"""

import math
import statistics
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from itertools import pairwise

import pytest

from phos.synth.attacks.manipulations import (
    ActuatorOffset,
    ActuatorRamp,
    ReadingBlend,
    ReadingTrack,
    pseudo_noise,
)
from phos.synth.injection import Injection, TimeWindow

START = datetime(2026, 4, 1, tzinfo=UTC)
WINDOW = TimeWindow(start=START + timedelta(hours=1), end=START + timedelta(hours=2))
INSIDE = START + timedelta(hours=1, minutes=30)
BEFORE = START + timedelta(minutes=30)
AFTER = START + timedelta(hours=3)

COMMANDED: Mapping[str, float] = {"pump_pct": 40.0, "dose_mgpl": 1.4}
READINGS: Mapping[str, float] = {"level_m": 3.1, "level_setpoint_m": 3.2, "flow_m3ph": 180.0}


def every_manipulation(strength: float) -> list[Injection]:
    """Return one of each manipulation, all built at the same strength."""
    return [
        ActuatorOffset(
            actuator="pump_pct", offset=55.0 * strength, low=0.0, high=100.0, window=WINDOW
        ),
        ActuatorRamp(
            actuator="pump_pct", total_offset=30.0 * strength, low=0.0, high=100.0, window=WINDOW
        ),
        ReadingBlend(
            signal="level_m", target=1.0, strength=strength, low=0.0, high=6.0, window=WINDOW
        ),
        ReadingTrack(
            signal="level_m",
            reference="level_setpoint_m",
            offset=-0.4,
            strength=strength,
            low=0.0,
            high=6.0,
            window=WINDOW,
        ),
    ]


class TestTheSharedContract:
    """What every manipulation must do, whatever it does."""

    @pytest.mark.parametrize("clock", [BEFORE, AFTER])
    @pytest.mark.parametrize("index", range(4))
    def test_nothing_is_overridden_outside_the_window(self, index: int, clock: datetime) -> None:
        manipulation = every_manipulation(1.0)[index]
        assert manipulation.actuator_overrides(clock, COMMANDED) == {}
        assert manipulation.reading_overrides(clock, READINGS) == {}

    @pytest.mark.parametrize("index", range(4))
    def test_at_zero_strength_the_value_handed_back_is_the_value_handed_in(
        self, index: int
    ) -> None:
        manipulation = every_manipulation(0.0)[index]
        for override, source in (
            (manipulation.actuator_overrides(INSIDE, COMMANDED), COMMANDED),
            (manipulation.reading_overrides(INSIDE, READINGS), READINGS),
        ):
            for key, value in override.items():
                # Bit-for-bit, not approximately: this is what makes a fully subtle attack
                # produce a run identical to a normal one.
                assert value == source[key]
                assert math.copysign(1.0, value) == math.copysign(1.0, source[key])

    @pytest.mark.parametrize("index", range(4))
    def test_a_manipulation_does_not_mutate_what_it_is_handed(self, index: int) -> None:
        manipulation = every_manipulation(1.0)[index]
        commanded = dict(COMMANDED)
        readings = dict(READINGS)
        manipulation.actuator_overrides(INSIDE, commanded)
        manipulation.reading_overrides(INSIDE, readings)
        assert commanded == COMMANDED
        assert readings == READINGS

    @pytest.mark.parametrize("index", range(4))
    def test_a_manipulation_is_a_function_of_its_arguments_alone(self, index: int) -> None:
        manipulation = every_manipulation(1.0)[index]
        first = (
            manipulation.actuator_overrides(INSIDE, COMMANDED),
            manipulation.reading_overrides(INSIDE, READINGS),
        )
        for _ in range(5):
            assert (
                manipulation.actuator_overrides(INSIDE, COMMANDED),
                manipulation.reading_overrides(INSIDE, READINGS),
            ) == first

    @pytest.mark.parametrize("index", range(4))
    def test_every_manipulation_satisfies_the_injection_protocol(self, index: int) -> None:
        assert isinstance(every_manipulation(1.0)[index], Injection)

    @pytest.mark.parametrize("index", range(4))
    def test_a_manipulation_refuses_an_inverted_span(self, index: int) -> None:
        inverted: list[Callable[[], Injection]] = [
            lambda: ActuatorOffset(actuator="p", offset=1.0, low=10.0, high=1.0, window=WINDOW),
            lambda: ActuatorRamp(actuator="p", total_offset=1.0, low=10.0, high=1.0, window=WINDOW),
            lambda: ReadingBlend(
                signal="s", target=1.0, strength=1.0, low=10.0, high=1.0, window=WINDOW
            ),
            lambda: ReadingTrack(
                signal="s",
                reference="r",
                offset=0.0,
                strength=1.0,
                low=10.0,
                high=1.0,
                window=WINDOW,
            ),
        ]
        with pytest.raises(ValueError, match="span"):
            inverted[index]()


class TestActuatorOffset:
    """A final control element pushed away from where the controller wanted it."""

    def test_the_actuator_moves_by_the_offset(self) -> None:
        offset = ActuatorOffset(
            actuator="pump_pct", offset=25.0, low=0.0, high=100.0, window=WINDOW
        )
        assert offset.actuator_overrides(INSIDE, COMMANDED) == {"pump_pct": 65.0}

    def test_only_the_named_actuator_moves(self) -> None:
        offset = ActuatorOffset(
            actuator="pump_pct", offset=25.0, low=0.0, high=100.0, window=WINDOW
        )
        assert set(offset.actuator_overrides(INSIDE, COMMANDED)) == {"pump_pct"}

    def test_the_actuator_cannot_be_driven_past_its_stops(self) -> None:
        offset = ActuatorOffset(
            actuator="pump_pct", offset=500.0, low=0.0, high=100.0, window=WINDOW
        )
        assert offset.actuator_overrides(INSIDE, COMMANDED) == {"pump_pct": 100.0}

    def test_it_falsifies_no_telemetry(self) -> None:
        offset = ActuatorOffset(
            actuator="pump_pct", offset=25.0, low=0.0, high=100.0, window=WINDOW
        )
        assert offset.reading_overrides(INSIDE, READINGS) == {}

    def test_an_actuator_the_controller_did_not_command_is_refused(self) -> None:
        offset = ActuatorOffset(actuator="ghost", offset=1.0, low=0.0, high=1.0, window=WINDOW)
        with pytest.raises(KeyError, match="ghost"):
            offset.actuator_overrides(INSIDE, COMMANDED)


class TestActuatorRamp:
    """The stealth drift: no single step is alarming, and the sum of them is."""

    def test_the_offset_grows_across_the_window(self) -> None:
        ramp = ActuatorRamp(
            actuator="pump_pct", total_offset=40.0, low=0.0, high=100.0, window=WINDOW
        )
        quarters = [
            ramp.actuator_overrides(WINDOW.start + timedelta(minutes=15 * n), COMMANDED)["pump_pct"]
            for n in range(4)
        ]
        assert quarters == [40.0, 50.0, 60.0, 70.0]

    def test_it_starts_from_no_offset_at_all(self) -> None:
        ramp = ActuatorRamp(
            actuator="pump_pct", total_offset=40.0, low=0.0, high=100.0, window=WINDOW
        )
        assert ramp.actuator_overrides(WINDOW.start, COMMANDED) == {"pump_pct": 40.0}

    def test_each_step_is_a_small_fraction_of_the_whole(self) -> None:
        # 120 samples across the window: no single increment is more than a hundredth of the
        # total departure, which is what "passes as ordinary drift" has to mean.
        ramp = ActuatorRamp(
            actuator="pump_pct", total_offset=40.0, low=0.0, high=100.0, window=WINDOW
        )
        step = timedelta(seconds=30)
        values = [
            ramp.actuator_overrides(WINDOW.start + step * n, COMMANDED)["pump_pct"]
            for n in range(120)
        ]
        increments = [later - earlier for earlier, later in pairwise(values)]
        assert max(increments) <= 40.0 / 100.0
        assert values[-1] - values[0] == pytest.approx(40.0 * 119 / 120)

    def test_the_ramp_is_bounded_by_the_actuator_stops(self) -> None:
        ramp = ActuatorRamp(
            actuator="pump_pct", total_offset=400.0, low=0.0, high=100.0, window=WINDOW
        )
        assert ramp.actuator_overrides(INSIDE, COMMANDED) == {"pump_pct": 100.0}

    def test_a_window_of_no_width_is_refused(self) -> None:
        empty = TimeWindow(start=START, end=START)
        with pytest.raises(ValueError, match="no time"):
            ActuatorRamp(actuator="p", total_offset=1.0, low=0.0, high=1.0, window=empty)


class TestReadingBlend:
    """Telemetry pulled toward a value of the attacker's choosing."""

    def test_full_strength_reports_the_target(self) -> None:
        blend = ReadingBlend(
            signal="level_m", target=1.0, strength=1.0, low=0.0, high=6.0, window=WINDOW
        )
        assert blend.reading_overrides(INSIDE, READINGS) == {"level_m": 1.0}

    def test_half_strength_reports_the_midpoint(self) -> None:
        blend = ReadingBlend(
            signal="level_m", target=1.1, strength=0.5, low=0.0, high=6.0, window=WINDOW
        )
        assert blend.reading_overrides(INSIDE, READINGS)["level_m"] == pytest.approx(2.1)

    def test_the_report_is_bounded_by_the_instrument_span(self) -> None:
        blend = ReadingBlend(
            signal="level_m", target=99.0, strength=1.0, low=0.0, high=6.0, window=WINDOW
        )
        assert blend.reading_overrides(INSIDE, READINGS) == {"level_m": 6.0}

    def test_it_moves_no_plant(self) -> None:
        blend = ReadingBlend(
            signal="level_m", target=1.0, strength=1.0, low=0.0, high=6.0, window=WINDOW
        )
        assert blend.actuator_overrides(INSIDE, COMMANDED) == {}

    def test_a_signal_no_instrument_measured_is_refused(self) -> None:
        blend = ReadingBlend(
            signal="ghost", target=1.0, strength=1.0, low=0.0, high=6.0, window=WINDOW
        )
        with pytest.raises(KeyError, match="ghost"):
            blend.reading_overrides(INSIDE, READINGS)


class TestReadingTrack:
    """The liar: telemetry quoted against another signal, so it reads as permanently calm."""

    def test_full_strength_reports_the_reference_plus_the_offset(self) -> None:
        track = ReadingTrack(
            signal="level_m",
            reference="level_setpoint_m",
            offset=-0.4,
            strength=1.0,
            low=0.0,
            high=6.0,
            window=WINDOW,
        )
        assert track.reading_overrides(INSIDE, READINGS)["level_m"] == pytest.approx(2.8)

    def test_the_report_follows_the_reference_wherever_it_goes(self) -> None:
        track = ReadingTrack(
            signal="level_m",
            reference="level_setpoint_m",
            offset=-0.4,
            strength=1.0,
            low=0.0,
            high=6.0,
            window=WINDOW,
        )
        moved = {**READINGS, "level_setpoint_m": 4.0}
        assert track.reading_overrides(INSIDE, moved)["level_m"] == pytest.approx(3.6)

    def test_the_report_is_bounded_by_the_instrument_span(self) -> None:
        track = ReadingTrack(
            signal="level_m",
            reference="level_setpoint_m",
            offset=-50.0,
            strength=1.0,
            low=0.0,
            high=6.0,
            window=WINDOW,
        )
        assert track.reading_overrides(INSIDE, READINGS) == {"level_m": 0.0}

    def test_a_missing_reference_is_refused(self) -> None:
        track = ReadingTrack(
            signal="level_m",
            reference="ghost",
            offset=0.0,
            strength=1.0,
            low=0.0,
            high=6.0,
            window=WINDOW,
        )
        with pytest.raises(KeyError, match="ghost"):
            track.reading_overrides(INSIDE, READINGS)

    def test_it_moves_no_plant_directly(self) -> None:
        # The plant moves because a control loop believes the falsified reading, not because
        # this manipulation touched an actuator. That indirection is the whole attack.
        track = ReadingTrack(
            signal="level_m",
            reference="level_setpoint_m",
            offset=-0.4,
            strength=1.0,
            low=0.0,
            high=6.0,
            window=WINDOW,
        )
        assert track.actuator_overrides(INSIDE, COMMANDED) == {}


class TestPseudoNoise:
    """The jitter a falsified reading carries, and why it is not drawn from the plant."""

    def test_it_is_the_same_every_time_for_one_instant_and_signal(self) -> None:
        assert pseudo_noise(INSIDE, "level_m") == pseudo_noise(INSIDE, "level_m")

    def test_two_signals_get_uncorrelated_series_rather_than_the_same_one(self) -> None:
        clocks = [START + timedelta(seconds=30 * n) for n in range(400)]
        first = [pseudo_noise(clock, "level_m") for clock in clocks]
        second = [pseudo_noise(clock, "flow_m3ph") for clock in clocks]
        assert first != second
        correlation = statistics.correlation(first, second)
        assert abs(correlation) < 0.15

    def test_it_has_unit_standard_deviation_so_a_signal_s_own_noise_figure_is_the_scale(
        self,
    ) -> None:
        clocks = [START + timedelta(seconds=30 * n) for n in range(4000)]
        draws = [pseudo_noise(clock, "level_m") for clock in clocks]
        assert statistics.fmean(draws) == pytest.approx(0.0, abs=0.05)
        assert statistics.pstdev(draws) == pytest.approx(1.0, abs=0.05)

    def test_it_stays_inside_the_range_three_uniform_draws_can_reach(self) -> None:
        clocks = [START + timedelta(seconds=30 * n) for n in range(2000)]
        assert all(-3.0 <= pseudo_noise(clock, "level_m") < 3.0 for clock in clocks)


class TestJitter:
    """A falsified reading that never wobbles is a falsified reading anyone can spot."""

    def falsified(self, jitter: float) -> list[float]:
        """Return 300 samples of a fully falsified level reading."""
        blend = ReadingBlend(
            signal="level_m",
            target=3.0,
            strength=1.0,
            low=0.0,
            high=6.0,
            window=TimeWindow(start=START, end=START + timedelta(hours=4)),
            jitter=jitter,
        )
        return [
            blend.reading_overrides(START + timedelta(seconds=30 * n), READINGS)["level_m"]
            for n in range(300)
        ]

    def test_without_jitter_the_falsified_signal_is_perfectly_smooth(self) -> None:
        assert statistics.pstdev(self.falsified(0.0)) == 0.0

    def test_with_jitter_it_carries_noise_of_the_size_it_was_given(self) -> None:
        assert statistics.pstdev(self.falsified(0.05)) == pytest.approx(0.05, rel=0.15)

    def test_the_jittered_value_still_centres_on_the_target(self) -> None:
        assert statistics.fmean(self.falsified(0.05)) == pytest.approx(3.0, abs=0.02)

    def test_jitter_does_not_leak_at_zero_strength(self) -> None:
        # The jitter enters through the target, which is multiplied by strength, so a fully
        # subtle attack is still bit-identical to no attack at all.
        blend = ReadingBlend(
            signal="level_m",
            target=1.0,
            strength=0.0,
            low=0.0,
            high=6.0,
            window=WINDOW,
            jitter=0.5,
        )
        assert blend.reading_overrides(INSIDE, READINGS) == {"level_m": READINGS["level_m"]}

    def test_a_tracked_reading_carries_jitter_too(self) -> None:
        track = ReadingTrack(
            signal="level_m",
            reference="level_setpoint_m",
            offset=-0.4,
            strength=1.0,
            low=0.0,
            high=6.0,
            window=TimeWindow(start=START, end=START + timedelta(hours=4)),
            jitter=0.02,
        )
        values = [
            track.reading_overrides(START + timedelta(seconds=30 * n), READINGS)["level_m"]
            for n in range(300)
        ]
        assert statistics.pstdev(values) > 0.0
        assert statistics.fmean(values) == pytest.approx(2.8, abs=0.01)

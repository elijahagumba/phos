"""The primitives every simulated plant is assembled from.

These are the pieces that make a plant *behave* rather than merely emit numbers: an integrator
that accumulates, a lag that resists, controllers that close a loop, and the cyclic and drifting
terms that stop a signal being flat. They are tested here in isolation, at the level of "does the
arithmetic mean what the name says", so that a plant's own tests can be about its physics rather
than about whether its integrator integrates.

Everything here is a pure function or a small object with explicit state. Nothing draws random
numbers: randomness enters a plant through its sensor model and its event schedule, both seeded
in one place, and a primitive that reached for a global generator would break that.
"""

import math

import pytest

from phos.synth.process import (
    Hysteresis,
    PiController,
    accumulate,
    clamp,
    cycle_factor,
    first_order,
    shift_index,
    square_law_flow,
)


class TestClamp:
    def test_passes_a_value_inside_the_bounds_through(self) -> None:
        assert clamp(0.5, 0.0, 1.0) == 0.5

    @pytest.mark.parametrize(("value", "expected"), [(-3.0, 0.0), (7.0, 1.0)])
    def test_bounds_a_value_outside_them(self, value: float, expected: float) -> None:
        assert clamp(value, 0.0, 1.0) == expected

    def test_refuses_inverted_bounds_rather_than_returning_a_nonsense_value(self) -> None:
        with pytest.raises(ValueError, match="inverted"):
            clamp(0.5, 1.0, 0.0)


class TestAccumulate:
    def test_adds_rate_times_elapsed_time(self) -> None:
        assert accumulate(10.0, rate_per_second=0.5, dt_seconds=4.0, low=0.0, high=100.0) == 12.0

    def test_a_negative_rate_draws_the_level_down(self) -> None:
        assert accumulate(10.0, rate_per_second=-0.5, dt_seconds=4.0, low=0.0, high=100.0) == 8.0

    def test_holds_at_the_floor_because_a_tank_does_not_go_negative(self) -> None:
        assert accumulate(1.0, rate_per_second=-10.0, dt_seconds=1.0, low=0.0, high=100.0) == 0.0

    def test_holds_at_the_ceiling_because_a_full_tank_overflows_rather_than_grows(self) -> None:
        assert accumulate(99.0, rate_per_second=10.0, dt_seconds=1.0, low=0.0, high=100.0) == 100.0


class TestFirstOrder:
    def test_moves_toward_the_target_without_reaching_it_in_one_step(self) -> None:
        moved = first_order(0.0, target=10.0, dt_seconds=1.0, tau_seconds=10.0)
        assert 0.0 < moved < 10.0

    def test_one_time_constant_covers_the_textbook_share_of_the_gap(self) -> None:
        moved = first_order(0.0, target=1.0, dt_seconds=10.0, tau_seconds=10.0)
        assert moved == pytest.approx(1.0 - math.exp(-1.0))

    def test_a_long_step_converges_on_the_target(self) -> None:
        assert first_order(0.0, target=5.0, dt_seconds=1000.0, tau_seconds=1.0) == pytest.approx(
            5.0
        )

    def test_sitting_on_the_target_is_a_fixed_point(self) -> None:
        assert first_order(5.0, target=5.0, dt_seconds=3.0, tau_seconds=10.0) == 5.0

    def test_refuses_a_non_positive_time_constant_which_would_divide_by_zero(self) -> None:
        with pytest.raises(ValueError, match="time constant"):
            first_order(0.0, target=1.0, dt_seconds=1.0, tau_seconds=0.0)


class TestCycleFactor:
    def test_completes_one_full_cycle_over_its_period(self) -> None:
        at_start = cycle_factor(0.0, period_hours=24.0, amplitude=1.0, phase_hours=0.0)
        one_period_later = cycle_factor(24.0, period_hours=24.0, amplitude=1.0, phase_hours=0.0)
        assert at_start == pytest.approx(one_period_later)

    def test_peaks_a_quarter_period_after_its_phase(self) -> None:
        peak = cycle_factor(6.0, period_hours=24.0, amplitude=2.0, phase_hours=0.0)
        assert peak == pytest.approx(2.0)

    def test_amplitude_scales_the_swing(self) -> None:
        small = cycle_factor(6.0, period_hours=24.0, amplitude=1.0, phase_hours=0.0)
        large = cycle_factor(6.0, period_hours=24.0, amplitude=3.0, phase_hours=0.0)
        assert large == pytest.approx(3.0 * small)

    def test_refuses_a_non_positive_period_which_has_no_cycle(self) -> None:
        with pytest.raises(ValueError, match="period"):
            cycle_factor(1.0, period_hours=0.0, amplitude=1.0, phase_hours=0.0)


class TestShiftIndex:
    @pytest.mark.parametrize(
        ("hours", "expected"), [(0.0, 0), (7.9, 0), (8.0, 1), (16.0, 2), (23.9, 2), (24.0, 0)]
    )
    def test_selects_the_shift_the_clock_falls_in(self, hours: float, expected: int) -> None:
        assert shift_index(hours, shift_hours=8.0, shifts=3) == expected

    def test_refuses_a_shift_count_that_does_not_tile_the_day(self) -> None:
        with pytest.raises(ValueError, match="tile"):
            shift_index(1.0, shift_hours=7.0, shifts=3)


class TestSquareLawFlow:
    def test_a_shut_valve_passes_nothing(self) -> None:
        assert square_law_flow(0.0, maximum_flow=100.0) == 0.0

    def test_a_fully_open_valve_passes_the_maximum(self) -> None:
        assert square_law_flow(100.0, maximum_flow=100.0) == pytest.approx(100.0)

    def test_half_open_passes_more_than_half_because_the_relation_is_not_linear(self) -> None:
        assert square_law_flow(50.0, maximum_flow=100.0) > 50.0

    def test_a_negative_opening_is_treated_as_shut_rather_than_producing_a_complex_root(
        self,
    ) -> None:
        assert square_law_flow(-10.0, maximum_flow=100.0) == 0.0


class TestPiController:
    def test_a_measurement_on_setpoint_holds_the_output_still(self) -> None:
        controller = PiController(gain=1.0, integral_time_seconds=10.0, low=0.0, high=100.0)
        first = controller.update(measurement=50.0, setpoint=50.0, dt_seconds=1.0, bias=20.0)
        second = controller.update(measurement=50.0, setpoint=50.0, dt_seconds=1.0, bias=20.0)
        assert first == 20.0
        assert second == 20.0

    def test_a_measurement_below_setpoint_drives_the_output_up(self) -> None:
        controller = PiController(gain=1.0, integral_time_seconds=10.0, low=0.0, high=100.0)
        assert controller.update(measurement=40.0, setpoint=50.0, dt_seconds=1.0, bias=20.0) > 20.0

    def test_a_measurement_above_setpoint_drives_the_output_down(self) -> None:
        controller = PiController(gain=1.0, integral_time_seconds=10.0, low=0.0, high=100.0)
        assert controller.update(measurement=60.0, setpoint=50.0, dt_seconds=1.0, bias=20.0) < 20.0

    def test_a_sustained_error_keeps_accumulating_which_is_what_the_integral_is_for(self) -> None:
        controller = PiController(gain=1.0, integral_time_seconds=10.0, low=0.0, high=100.0)
        outputs = [
            controller.update(measurement=40.0, setpoint=50.0, dt_seconds=1.0, bias=20.0)
            for _ in range(3)
        ]
        assert outputs[0] < outputs[1] < outputs[2]

    def test_the_output_is_bounded_by_the_actuator_it_drives(self) -> None:
        controller = PiController(gain=50.0, integral_time_seconds=1.0, low=0.0, high=100.0)
        for _ in range(20):
            output = controller.update(measurement=0.0, setpoint=50.0, dt_seconds=1.0, bias=0.0)
        assert output == 100.0

    def test_windup_does_not_strand_the_output_at_the_limit_when_the_error_reverses(self) -> None:
        controller = PiController(gain=5.0, integral_time_seconds=1.0, low=0.0, high=100.0)
        for _ in range(50):
            controller.update(measurement=0.0, setpoint=50.0, dt_seconds=1.0, bias=0.0)
        recovered = controller.update(measurement=100.0, setpoint=50.0, dt_seconds=1.0, bias=0.0)
        assert recovered < 100.0

    def test_refuses_a_non_positive_integral_time(self) -> None:
        with pytest.raises(ValueError, match="integral time"):
            PiController(gain=1.0, integral_time_seconds=0.0, low=0.0, high=100.0)

    def test_refuses_inverted_output_limits(self) -> None:
        with pytest.raises(ValueError, match="inverted"):
            PiController(gain=1.0, integral_time_seconds=1.0, low=100.0, high=0.0)


class TestHysteresis:
    def test_starts_in_the_state_it_was_given(self) -> None:
        switch = Hysteresis(on_below=20.0, off_above=80.0, engaged=False)
        assert switch.update(50.0) is False

    def test_engages_once_the_measurement_falls_through_the_lower_bound(self) -> None:
        switch = Hysteresis(on_below=20.0, off_above=80.0, engaged=False)
        assert switch.update(19.0) is True

    def test_stays_engaged_inside_the_band_which_is_the_whole_point(self) -> None:
        switch = Hysteresis(on_below=20.0, off_above=80.0, engaged=False)
        switch.update(19.0)
        assert switch.update(50.0) is True

    def test_releases_once_the_measurement_rises_through_the_upper_bound(self) -> None:
        switch = Hysteresis(on_below=20.0, off_above=80.0, engaged=True)
        assert switch.update(81.0) is False

    def test_refuses_a_band_whose_bounds_are_the_wrong_way_round(self) -> None:
        with pytest.raises(ValueError, match="band"):
            Hysteresis(on_below=80.0, off_above=20.0, engaged=False)


class TestPiControllerDirection:
    def test_a_direct_loop_opens_its_actuator_when_the_measurement_falls(self) -> None:
        filling = PiController(gain=1.0, integral_time_seconds=10.0, low=0.0, high=100.0)
        assert filling.update(measurement=40.0, setpoint=50.0, dt_seconds=1.0, bias=50.0) > 50.0

    def test_a_reverse_loop_opens_its_actuator_when_the_measurement_rises(self) -> None:
        cooling = PiController(
            gain=1.0, integral_time_seconds=10.0, low=0.0, high=100.0, reverse_acting=True
        )
        assert cooling.update(measurement=60.0, setpoint=50.0, dt_seconds=1.0, bias=50.0) > 50.0

    def test_the_two_directions_are_mirror_images_of_each_other(self) -> None:
        direct = PiController(gain=2.0, integral_time_seconds=5.0, low=-100.0, high=100.0)
        reverse = PiController(
            gain=2.0, integral_time_seconds=5.0, low=-100.0, high=100.0, reverse_acting=True
        )
        assert direct.update(40.0, 50.0, 1.0) == pytest.approx(-reverse.update(40.0, 50.0, 1.0))

    def test_refuses_a_non_positive_gain_because_sign_is_expressed_by_the_action(self) -> None:
        with pytest.raises(ValueError, match="gain"):
            PiController(gain=-1.0, integral_time_seconds=1.0, low=0.0, high=100.0)


class TestPiControllerAntiWindup:
    def test_the_integral_is_wound_back_by_however_much_the_output_was_clipped(self) -> None:
        controller = PiController(gain=5.0, integral_time_seconds=1.0, low=0.0, high=100.0)
        controller.update(measurement=0.0, setpoint=50.0, dt_seconds=1.0)
        # Unclipped the loop asked for 5*(50+50) = 500; clipping to 100 removes 400/5 from the
        # integral, leaving 50 - 80.
        assert controller.integral == pytest.approx(-30.0)

    def test_an_unsaturated_loop_keeps_its_integral_untouched(self) -> None:
        controller = PiController(gain=1.0, integral_time_seconds=10.0, low=0.0, high=100.0)
        controller.update(measurement=45.0, setpoint=50.0, dt_seconds=2.0, bias=20.0)
        assert controller.integral == pytest.approx(1.0)

    def test_a_saturated_loop_settles_rather_than_accumulating_without_bound(self) -> None:
        controller = PiController(gain=5.0, integral_time_seconds=1.0, low=0.0, high=100.0)
        for _ in range(30):
            controller.update(measurement=0.0, setpoint=50.0, dt_seconds=1.0)
        assert controller.integral == pytest.approx(-30.0)

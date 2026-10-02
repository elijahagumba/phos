"""Operational realism: the benign phenomena that make a false-positive figure mean anything.

Everything here is benign. What is under test is that a quiet profile changes nothing, that a
messy one produces the kinds of trouble that actually confuse a detector, and that the effects do
what they say — a frozen transmitter freezes, a drifting one drifts, a dropout drops.

That the generator cannot see the attack schedule is enforced in `test_anti_bias.py`.
"""

from datetime import UTC, datetime, timedelta

import numpy
import pytest
from pydantic import ValidationError

from phos.synth.plant import RunSpec
from phos.synth.realism import (
    AmbientDrift,
    CommsDropout,
    PhenomenonKind,
    RealismPlan,
    RealismProfile,
    SensorFault,
    plan_realism,
)

START = datetime(2026, 3, 1, tzinfo=UTC)
SPANS = {
    "level_m": (0.0, 6.0),
    "flow_m3ph": (0.0, 120.0),
    "pressure_bar": (0.0, 8.0),
}


def spec(days: int = 30) -> RunSpec:
    """Return a minute-sampled run of ``days`` days."""
    return RunSpec(
        seed=1,
        start=START,
        duration=timedelta(days=days),
        sample_interval=timedelta(minutes=1),
    )


def plan(profile: RealismProfile | None = None, seed: int = 3) -> RealismPlan:
    """Plan realism over a 30-day run with the given profile."""
    run = spec()
    return plan_realism(
        numpy.random.default_rng(seed), run.start, run.duration, profile or RealismProfile(), SPANS
    )


class TestAQuietProfileChangesNothing:
    """The additive property: realism off reproduces every earlier corpus byte for byte."""

    def test_the_default_profile_asks_for_nothing(self) -> None:
        assert RealismProfile().is_quiet() is True

    def test_a_quiet_plan_is_empty_in_every_field(self) -> None:
        result = plan()
        assert result.phenomena == ()
        assert result.faults == ()
        assert result.drifts == ()
        assert result.dropouts == ()
        assert dict(result.ageing) == {}

    def test_any_requested_phenomenon_makes_the_profile_not_quiet(self) -> None:
        assert RealismProfile(sensor_faults=1).is_quiet() is False
        assert RealismProfile(ambient_signals=("level_m",)).is_quiet() is False


class TestTheTroubleIsTheTroubleRealPlantsHave:
    """Seven kinds, and the confusing ones marked as confusing."""

    def test_a_grade_change_moves_several_signals_together(self) -> None:
        result = plan(RealismProfile(grade_changes=2))
        changes = [i for i in result.phenomena if i.kind is PhenomenonKind.GRADE_CHANGE]
        assert len(changes) == 2
        assert all(len(item.signals) > 1 for item in changes)

    def test_ageing_carries_a_signal_one_way_across_the_run(self) -> None:
        result = plan(RealismProfile(ageing_signals=("level_m",), ageing_fraction=0.1))
        assert dict(result.ageing) == {"level_m": pytest.approx(0.6)}

    def test_ambient_drift_is_a_slow_cycle(self) -> None:
        result = plan(RealismProfile(ambient_signals=("level_m",), ambient_amplitude=0.05))
        (drift,) = result.drifts
        assert drift.period_hours > 2000.0
        assert drift.amplitude == pytest.approx(0.3)

    def test_sensor_faults_appear_as_both_frozen_and_drifting(self) -> None:
        result = plan(RealismProfile(sensor_faults=12), seed=11)
        assert any(fault.stuck_at is not None for fault in result.faults)
        assert any(fault.stuck_at is None and fault.offset for fault in result.faults)

    def test_dropouts_appear_with_and_without_retransmission(self) -> None:
        result = plan(RealismProfile(comms_dropouts=12), seed=11)
        assert any(item.retransmits for item in result.dropouts)
        assert any(not item.retransmits for item in result.dropouts)

    def test_the_confusing_kinds_are_marked_confusing(self) -> None:
        result = plan(
            RealismProfile(
                grade_changes=1,
                sensor_faults=1,
                comms_dropouts=1,
                operator_interventions=1,
                startup_transitions=1,
            )
        )
        assert len(result.attack_like()) == 5

    def test_a_seasonal_influence_is_not_marked_attack_like(self) -> None:
        """Not everything benign is confusing. A slow seasonal cycle is just weather."""
        result = plan(RealismProfile(ambient_signals=("level_m",)))
        assert result.attack_like() == ()

    def test_nothing_runs_past_the_end_of_the_run(self) -> None:
        result = plan(RealismProfile(grade_changes=3, sensor_faults=3, comms_dropouts=3))
        end = spec().start + spec().duration
        assert all(item.ended_at <= end for item in result.phenomena)

    def test_phenomena_are_earliest_first(self) -> None:
        messy = plan(RealismProfile(grade_changes=4, sensor_faults=4))
        starts = [item.started_at for item in messy.phenomena]
        assert starts == sorted(starts)


class TestTheEffectsDoWhatTheySay:
    """Each effect applied by hand, so a plant wiring it in has something to trust."""

    def test_a_frozen_transmitter_reports_one_value(self) -> None:
        fault = SensorFault(
            signal="level_m",
            started_at=START,
            ended_at=START + timedelta(hours=2),
            stuck_at=3.0,
        )
        assert fault.apply(START + timedelta(hours=1), 4.5) == pytest.approx(3.0)

    def test_a_walked_calibration_offsets_the_reading(self) -> None:
        fault = SensorFault(
            signal="level_m", started_at=START, ended_at=START + timedelta(hours=2), offset=0.4
        )
        assert fault.apply(START + timedelta(hours=1), 3.0) == pytest.approx(3.4)

    def test_a_fault_outside_its_window_changes_nothing(self) -> None:
        fault = SensorFault(
            signal="level_m", started_at=START, ended_at=START + timedelta(hours=2), offset=0.4
        )
        assert fault.apply(START + timedelta(hours=9), 3.0) == pytest.approx(3.0)

    def test_ambient_drift_is_bounded_by_its_amplitude(self) -> None:
        drift = AmbientDrift(signal="level_m", amplitude=0.5, period_hours=2400.0, phase_hours=0.0)
        assert all(abs(drift.at(hour)) <= 0.5 for hour in range(0, 3000, 37))

    def test_a_segment_wide_dropout_drops_every_device(self) -> None:
        dropout = CommsDropout(
            started_at=START, ended_at=START + timedelta(minutes=5), node_id=None, retransmits=True
        )
        assert dropout.drops(START + timedelta(minutes=1), "scada") is True
        assert dropout.drops(START + timedelta(minutes=1), "hmi") is True

    def test_a_device_dropout_drops_only_that_device(self) -> None:
        dropout = CommsDropout(
            started_at=START,
            ended_at=START + timedelta(minutes=5),
            node_id="hmi",
            retransmits=False,
        )
        assert dropout.drops(START + timedelta(minutes=1), "hmi") is True
        assert dropout.drops(START + timedelta(minutes=1), "scada") is False

    def test_a_dropout_outside_its_window_drops_nothing(self) -> None:
        dropout = CommsDropout(
            started_at=START, ended_at=START + timedelta(minutes=5), node_id=None, retransmits=True
        )
        assert dropout.drops(START + timedelta(hours=3), "scada") is False


class TestTheProfileIsValidated:
    """A profile that cannot happen is a declaration mistake."""

    def test_an_undeclared_signal_is_refused(self) -> None:
        with pytest.raises(KeyError, match="undeclared signal"):
            plan(RealismProfile(ambient_signals=("no_such_signal",)))

    def test_a_non_positive_dropout_duration_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="dropout_duration must be positive"):
            RealismProfile(comms_dropouts=1, dropout_duration=timedelta(0))

    def test_a_negative_count_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            RealismProfile(sensor_faults=-1)

    def test_a_fraction_outside_zero_to_one_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            RealismProfile(ageing_fraction=2.0)


class TestItIsReproducible:
    """Constitution §3.7. Same seed, same trouble."""

    def test_the_same_seed_gives_the_same_plan(self) -> None:
        profile = RealismProfile(sensor_faults=4)
        assert plan(profile, seed=9).phenomena == plan(profile, seed=9).phenomena

    def test_a_different_seed_gives_different_trouble(self) -> None:
        profile = RealismProfile(sensor_faults=4)
        assert plan(profile, seed=9).phenomena != plan(profile, seed=10).phenomena

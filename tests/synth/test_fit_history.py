"""Gate 1's fit-history safeguard, as a property rather than an intention."""

import re
from datetime import timedelta

import pytest

from phos.synth.fit_history import (
    FitHistoryTooShortError,
    assert_fit_history,
    declared_cycles,
    required_fit_history,
)
from phos.synth.plant import DRIFT_PERIOD_HOURS
from phos.synth.run import PLANT_IDS


class TestDerivation:
    def test_every_plant_includes_the_instrument_drift_upper_bound(self) -> None:
        for plant_id in PLANT_IDS:
            names = {cycle.name for cycle in declared_cycles(plant_id)}
            assert any("calibration-drift" in name for name in names)
            assert required_fit_history(plant_id).hours == DRIFT_PERIOD_HOURS[1]

    def test_water_declares_its_demand_and_turbidity_cycles(self) -> None:
        hours = {cycle.hours for cycle in declared_cycles("water-treatment")}
        assert {12.0, 24.0, 72.0, 120.0} <= hours

    def test_power_declares_its_demand_shift_and_ambient_cycles(self) -> None:
        hours = {cycle.hours for cycle in declared_cycles("power-generation")}
        assert {8.0, 24.0, 120.0} <= hours

    def test_batch_declared_timers_are_shorter_than_instrument_drift(self) -> None:
        timers = next(
            cycle for cycle in declared_cycles("batch-reactor") if "batch timers" in cycle.name
        )
        assert timers.hours < DRIFT_PERIOD_HOURS[1]


class TestEnforcement:
    @pytest.mark.parametrize("plant_id", PLANT_IDS)
    def test_refuses_below_the_derived_history(self, plant_id: str) -> None:
        slowest = required_fit_history(plant_id)
        just_under = timedelta(hours=slowest.hours) - timedelta(seconds=1)
        with pytest.raises(FitHistoryTooShortError, match=re.escape(slowest.name)):
            assert_fit_history(plant_id, just_under)

    @pytest.mark.parametrize("plant_id", PLANT_IDS)
    def test_accepts_at_or_above_the_derived_history(self, plant_id: str) -> None:
        slowest = required_fit_history(plant_id)
        assert_fit_history(plant_id, timedelta(hours=slowest.hours))
        assert_fit_history(plant_id, timedelta(hours=slowest.hours + 1.0))

    def test_an_unknown_plant_is_refused_where_it_is_named(self) -> None:
        with pytest.raises(KeyError, match="no plant 'refinery'"):
            required_fit_history("refinery")

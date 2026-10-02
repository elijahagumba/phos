"""The registry and the run result: one simulation, many projections of it.

Everything downstream — telemetry, capture, topology, manifest — is taken from a single `PlantRun`,
so the property worth testing here is that a run is a complete and self-consistent record of what
happened, and that naming a plant that does not exist fails where it is named rather than an hour
into a sweep.
"""

from datetime import UTC, datetime, timedelta

import pytest

from phos.synth.injection import HoldActuator, TimeWindow
from phos.synth.plant import RunSpec
from phos.synth.plants.water import INTAKE_SPEED, RAW_INFLOW
from phos.synth.realism import RealismProfile
from phos.synth.run import PLANT_FACTORIES, PLANT_IDS, build_plant, run_plant

START = datetime(2026, 6, 1, tzinfo=UTC)


def spec(steps: int = 120, seed: int = 31) -> RunSpec:
    """Return a short run spec at thirty-second sampling."""
    return RunSpec(
        seed=seed,
        start=START,
        duration=timedelta(seconds=30) * steps,
        sample_interval=timedelta(seconds=30),
    )


class TestRegistry:
    def test_every_registered_identifier_builds_a_plant_that_declares_it(self) -> None:
        for plant_id in PLANT_IDS:
            assert build_plant(plant_id, spec()).description.plant_id == plant_id

    def test_the_identifiers_are_sorted_so_listings_and_errors_are_stable(self) -> None:
        assert list(PLANT_IDS) == sorted(PLANT_FACTORIES)

    def test_an_unknown_plant_is_refused_with_the_known_ones_named(self) -> None:
        with pytest.raises(KeyError, match="no plant 'refinery'"):
            build_plant("refinery", spec())

    def test_three_plants_from_three_industries_are_registered(self) -> None:
        industries = {build_plant(plant_id, spec()).description.industry for plant_id in PLANT_IDS}
        assert len(industries) == 3


class TestPlantRun:
    def test_holds_one_step_per_sample_the_spec_asked_for(self) -> None:
        run = run_plant("water-treatment", spec(steps=90))
        assert len(run.steps) == 90
        assert run.timestamps[0] == START
        assert run.timestamps[-1] == START + timedelta(seconds=30) * 89

    def test_carries_the_plant_declaration_and_the_spec_that_produced_it(self) -> None:
        wanted = spec(seed=99)
        run = run_plant("power-generation", wanted)
        assert run.plant_id == "power-generation"
        assert run.spec == wanted
        assert run.description.plant_id == "power-generation"

    def test_carries_the_benign_events_as_ground_truth_in_their_own_right(self) -> None:
        run = run_plant("batch-reactor", spec(steps=600))
        assert run.events
        assert all(event.started_at >= START for event in run.events)

    def test_counts_the_control_traffic_it_generated(self) -> None:
        assert run_plant("water-treatment", spec(steps=60)).command_count > 0

    def test_a_plant_with_no_control_network_generated_none(self) -> None:
        assert run_plant("batch-reactor", spec(steps=60)).command_count == 0

    def test_reports_and_truth_are_both_reachable_and_are_not_the_same_series(self) -> None:
        run = run_plant("water-treatment", spec(steps=200))
        assert run.reported(RAW_INFLOW) != run.true_values(RAW_INFLOW)
        assert len(run.reported(RAW_INFLOW)) == len(run.steps)

    @pytest.mark.parametrize("method", ["reported", "true_values"])
    def test_asking_for_a_signal_the_plant_does_not_have_is_refused(self, method: str) -> None:
        run = run_plant("water-treatment", spec(steps=5))
        with pytest.raises(KeyError, match="declares no signal"):
            getattr(run, method)("no_such_meter")

    def test_a_run_is_reproducible_from_its_identifier_and_spec_alone(self) -> None:
        wanted = spec(steps=150, seed=7)
        first = run_plant("power-generation", wanted)
        again = run_plant("power-generation", wanted)
        assert [step.report.values for step in first.steps] == [
            step.report.values for step in again.steps
        ]

    def test_the_injection_hook_is_reachable_from_the_same_entry_point_d2_will_use(self) -> None:
        window = TimeWindow(START + timedelta(minutes=10), START + timedelta(minutes=40))
        held = HoldActuator(actuator=INTAKE_SPEED, value=95.0, window=window)
        clean = run_plant("water-treatment", spec(steps=120))
        manipulated = run_plant("water-treatment", spec(steps=120), held)
        assert clean.true_values(RAW_INFLOW)[:20] == manipulated.true_values(RAW_INFLOW)[:20]
        assert manipulated.true_values(RAW_INFLOW)[60] > clean.true_values(RAW_INFLOW)[60]


class TestRealPlantsForwardRealism:
    """The three registered plants, and the factory, must be able to receive a profile.

    ADR 0077 said the phenomena can happen to a plant. Until the constructors forwarded `realism`,
    that was true of the base class and of `TinyTank` only.
    """

    @pytest.mark.parametrize("plant_id", PLANT_IDS)
    def test_none_and_a_quiet_profile_give_identical_readings(self, plant_id: str) -> None:
        wanted = spec(steps=90, seed=11)
        plain = run_plant(plant_id, wanted)
        quiet = run_plant(plant_id, wanted, realism=RealismProfile())
        assert [step.report.values for step in plain.steps] == [
            step.report.values for step in quiet.steps
        ]
        assert plain.realism.phenomena == ()
        assert quiet.realism.phenomena == ()

    @pytest.mark.parametrize("plant_id", PLANT_IDS)
    def test_a_non_quiet_profile_changes_the_readings(self, plant_id: str) -> None:
        wanted = spec(steps=120, seed=11)
        quiet = run_plant(plant_id, wanted, realism=RealismProfile())
        messy = run_plant(plant_id, wanted, realism=RealismProfile(sensor_faults=4))
        assert [step.report.values for step in messy.steps] != [
            step.report.values for step in quiet.steps
        ]
        assert messy.realism.faults

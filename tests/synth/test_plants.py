"""Whether the three plants are believable, and whether their couplings are real.

`test_plant.py` tests the machinery every plant shares. This module tests the plants themselves,
against the standard the PART sets: signals related *through the process* rather than correlated
by coincidence, imperfection that is present rather than assumed, and rhythms that a model could
actually learn.

Three kinds of test, and the first is the one that matters most:

1. **Every declared coupling is checked.** Where the relation is exact — a level integrating net
   flow, the three-phase power identity, frequency as shaft speed over sixty — it is checked to
   floating-point tolerance against the true state. Where it is not, the driving actuator is held
   somewhere else through the injection hook and the driven signal has to move by more than
   measurement noise. A coupling that survives both is a mechanism, not a correlation.
2. **The imperfections are present.** Noise, calibration drift, daily cycles, shift steps and
   benign operational events, each asserted rather than assumed.
3. **Nothing is degenerate.** No signal sits constant for a whole run, no two signals are the same
   series, and nothing leaves the span its instrument declares.
"""

import math
import statistics
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from itertools import pairwise

import pytest

from phos.synth.injection import HoldActuator, TimeWindow
from phos.synth.plant import (
    CouplingKind,
    Plant,
    PlantDescription,
    PlantStep,
    RunSpec,
    SignalKind,
)
from phos.synth.plants import BatchReactorPlant, PowerGenerationPlant, WaterTreatmentPlant
from phos.synth.plants import batch as b
from phos.synth.plants import power as p
from phos.synth.plants import water as w

START = datetime(2026, 5, 1, tzinfo=UTC)
PlantFactory = Callable[[RunSpec], Plant]

PLANTS: dict[str, tuple[PlantFactory, PlantDescription, timedelta]] = {
    "water-treatment": (WaterTreatmentPlant, w.WATER_DESCRIPTION, timedelta(seconds=30)),
    "power-generation": (PowerGenerationPlant, p.POWER_DESCRIPTION, timedelta(seconds=10)),
    "batch-reactor": (BatchReactorPlant, b.BATCH_DESCRIPTION, timedelta(seconds=60)),
}

FULL_CYCLE_STEPS: dict[str, int] = {
    "water-treatment": 5000,
    "power-generation": 7000,
    "batch-reactor": 1400,
}
"""Samples needed for the event schedule to work once through every kind of event it has.

A setpoint only moves when an operator moves it, so "this signal is never constant" is a claim
about a run long enough to contain one of each event — not about an arbitrary window. Short of
that the test would be asserting how often operators happen to touch things.
"""


def spec_for(plant_id: str, steps: int, seed: int = 17) -> RunSpec:
    """Return a run spec of ``steps`` samples at the plant's own sampling rate."""
    interval = PLANTS[plant_id][2]
    return RunSpec(seed=seed, start=START, duration=interval * steps, sample_interval=interval)


def run_steps(
    plant_id: str, steps: int, injection: object = None, seed: int = 17
) -> list[PlantStep]:
    """Step a fresh plant through a run and return every sample."""
    factory = PLANTS[plant_id][0]
    plant = factory(spec_for(plant_id, steps, seed))
    return [plant.step(injection) for _ in range(steps)]  # type: ignore[arg-type]


def series(steps: Sequence[PlantStep], key: str, *, truth: bool = False) -> list[float]:
    """Return one signal's series, reported by default or true on request."""
    if truth:
        return [step.truth.values[key] for step in steps]
    return [step.report.values[key] for step in steps]


# --- Every declared coupling, checked ----------------------------------------------------------


def actuator_driven_couplings() -> list[tuple[str, str, str]]:
    """Return ``(plant_id, driven, actuator)`` for every coupling an actuator drives.

    Control couplings are excluded: their driven signal *is* the actuator, so holding it would
    make the test true by definition. What is left is the physics.
    """
    cases: list[tuple[str, str, str]] = []
    for plant_id, (_, description, _interval) in PLANTS.items():
        actuators = set(description.keys_of_kind(SignalKind.ACTUATOR))
        for coupling in description.couplings:
            if coupling.kind is CouplingKind.CONTROL:
                continue
            for driver in coupling.drivers:
                if driver in actuators:
                    cases.append((plant_id, coupling.driven, driver))
    return cases


@pytest.mark.parametrize(
    ("plant_id", "driven", "actuator"),
    actuator_driven_couplings(),
    ids=lambda value: str(value),
)
def test_a_declared_coupling_moves_when_the_actuator_driving_it_is_held(
    plant_id: str, driven: str, actuator: str
) -> None:
    steps = 700
    description = PLANTS[plant_id][1]
    clean = run_steps(plant_id, steps)
    spec = PLANTS[plant_id][1].signal(actuator)
    normal = statistics.fmean(series(clean, actuator, truth=True))
    span = spec.high - spec.low
    far = spec.low + (0.15 * span if normal > spec.low + 0.5 * span else 0.85 * span)

    window = TimeWindow(START, START + PLANTS[plant_id][2] * steps)
    held = run_steps(plant_id, steps, HoldActuator(actuator=actuator, value=far, window=window))

    departure = max(
        abs(after - before)
        for before, after in zip(
            series(clean, driven, truth=True), series(held, driven, truth=True), strict=True
        )
    )
    assert departure > 5.0 * max(description.signal(driven).noise_stddev, 1e-6)


class TestWaterCouplingsAreExact:
    def test_the_clearwell_level_is_the_integral_of_net_flow(self) -> None:
        steps = run_steps("water-treatment", 600)
        area = w._CLEARWELL_AREA_M2
        for earlier, later in pairwise(steps):
            net = later.truth.values[w.RAW_INFLOW] - later.truth.values[w.DISTRIBUTION_FLOW]
            expected = earlier.truth.values[w.CLEARWELL_LEVEL] + net / area / 3600.0 * 30.0
            assert later.truth.values[w.CLEARWELL_LEVEL] == pytest.approx(expected, abs=1e-9)

    def test_inflow_follows_the_square_root_of_pump_speed(self) -> None:
        for step in run_steps("water-treatment", 400):
            speed = step.truth.values[w.INTAKE_SPEED]
            expected = w._MAX_INTAKE_M3PH * (speed / 100.0) ** 0.5
            assert step.truth.values[w.RAW_INFLOW] == pytest.approx(expected, abs=1e-9)

    def test_chlorine_residual_depends_on_level_and_demand_and_not_on_dose_alone(self) -> None:
        steps = run_steps("water-treatment", 2000)
        contact = [step.truth.internal[w.CONTACT_TIME] for step in steps]
        residual_per_dose = [
            step.truth.values[w.CHLORINE_RESIDUAL] / step.truth.values[w.CHLORINE_DOSE]
            for step in steps
        ]
        # More contact time destroys more chlorine, so the survival fraction has to fall as the
        # contact time rises. A residual that depended on dose alone would show no relationship.
        assert statistics.correlation(contact, residual_per_dose) < -0.5

    def test_filter_headloss_only_ever_rises_between_backwashes(self) -> None:
        steps = run_steps("water-treatment", 2400)
        washes = {step.index for step in steps if step.began and step.began.kind == w.BACKWASH}
        assert washes
        for earlier, later in pairwise(steps):
            if later.index in washes:
                continue
            assert later.truth.values[w.FILTER_HEADLOSS] >= earlier.truth.values[w.FILTER_HEADLOSS]

    def test_a_backwash_resets_the_solids_the_filter_is_holding(self) -> None:
        steps = run_steps("water-treatment", 2400)
        washed = [step for step in steps if step.began and step.began.kind == w.BACKWASH]
        assert washed
        before = steps[washed[0].index - 1].truth.internal[w.FILTER_LOAD]
        assert washed[0].truth.internal[w.FILTER_LOAD] < before


class TestPowerCouplingsAreExact:
    def test_the_three_phase_power_identity_holds_at_every_instant(self) -> None:
        root_three = 3.0**0.5
        for step in run_steps("power-generation", 900):
            values = step.truth.values
            implied = (
                root_three
                * values[p.BUS_VOLTAGE]
                * 1000.0
                * values[p.FEEDER_CURRENT]
                * values[p.POWER_FACTOR]
                / 1.0e6
            )
            assert implied == pytest.approx(values[p.GENERATOR_OUTPUT], rel=1e-9)

    def test_frequency_is_shaft_speed_because_they_are_one_physical_quantity(self) -> None:
        for step in run_steps("power-generation", 600):
            assert step.truth.values[p.BUS_FREQUENCY] == pytest.approx(
                step.truth.values[p.TURBINE_SPEED] / 60.0, abs=1e-12
            )

    def test_shaft_speed_integrates_the_power_imbalance(self) -> None:
        steps = run_steps("power-generation", 600)
        for earlier, later in pairwise(steps):
            imbalance = (
                p._RATED_MW * later.truth.values[p.FUEL_VALVE] / 100.0
                - later.truth.values[p.GENERATOR_OUTPUT]
            )
            expected = (
                earlier.truth.values[p.TURBINE_SPEED] + p._INERTIA_RPM_PER_MW_S * imbalance * 10.0
            )
            assert later.truth.values[p.TURBINE_SPEED] == pytest.approx(expected, abs=1e-9)

    def test_the_governor_holds_frequency_at_fifty_across_a_whole_day(self) -> None:
        frequency = series(run_steps("power-generation", 8640), p.BUS_FREQUENCY)
        assert statistics.fmean(frequency) == pytest.approx(50.0, abs=0.02)
        assert max(abs(value - 50.0) for value in frequency) < 1.5

    def test_oil_temperature_lags_rather_than_tracks_the_load_that_heats_it(self) -> None:
        steps = run_steps("power-generation", 8640)
        current = series(steps, p.FEEDER_CURRENT, truth=True)
        oil = series(steps, p.TRANSFORMER_OIL_TEMP, truth=True)
        immediate = statistics.correlation(current, oil)
        delayed = statistics.correlation(current[:-180], oil[180:])
        assert delayed > immediate


class TestBatchCouplingsAndRhythm:
    def test_the_reactor_cycles_through_its_phases_in_recipe_order(self) -> None:
        phases = [round(value) for value in series(run_steps("batch-reactor", 900), b.BATCH_PHASE)]
        transitions = [(earlier, later) for earlier, later in pairwise(phases) if earlier != later]
        assert transitions
        for earlier, later in transitions:
            assert later == (earlier + 1) % 5

    def test_every_phase_is_actually_visited(self) -> None:
        phases = {round(value) for value in series(run_steps("batch-reactor", 900), b.BATCH_PHASE)}
        assert phases == {0, 1, 2, 3, 4}

    def test_conversion_only_rises_while_a_charge_is_reacting(self) -> None:
        steps = run_steps("batch-reactor", 900)
        for earlier, later in pairwise(steps):
            if later.truth.internal[b.REAGENT_MASS] >= earlier.truth.internal[b.REAGENT_MASS]:
                assert (
                    later.truth.internal[b.CONVERTED_MASS]
                    >= earlier.truth.internal[b.CONVERTED_MASS] - 1e-9
                )

    def test_the_reaction_runs_faster_when_it_is_run_hotter(self) -> None:
        steps = run_steps("batch-reactor", 900)
        reacting = [
            step
            for step in steps
            if round(step.truth.values[b.BATCH_PHASE]) == b.Phase.REACT
            and step.truth.values[b.CONVERSION] < 60.0
        ]
        assert len(reacting) > 30
        temperature = [step.truth.values[b.REACTOR_TEMP] for step in reacting]
        rate = [math.exp(-b._ARRHENIUS_TEMPERATURE_K / (t + 273.15)) for t in temperature]
        assert statistics.correlation(temperature, rate) > 0.99

    def test_utility_flow_is_not_monotone_in_the_valve_that_sets_it(self) -> None:
        steps = run_steps("batch-reactor", 900)
        pairs = sorted(
            (step.truth.values[b.JACKET_VALVE], step.truth.values[b.JACKET_FLOW]) for step in steps
        )
        lowest = min(pairs, key=lambda pair: pair[1])
        assert 30.0 < lowest[0] < 70.0
        assert pairs[0][1] > lowest[1]
        assert pairs[-1][1] > lowest[1]

    def test_agitator_power_reveals_the_conversion_inside_the_vessel(self) -> None:
        steps = [
            step
            for step in run_steps("batch-reactor", 900)
            if round(step.truth.values[b.BATCH_PHASE]) == b.Phase.REACT
        ]
        conversion = [step.truth.values[b.CONVERSION] for step in steps]
        power = [step.truth.values[b.AGITATOR_POWER] for step in steps]
        assert statistics.correlation(conversion, power) > 0.8

    def test_the_reactor_is_charged_cold_and_heated_rather_than_coasting_hot(self) -> None:
        steps = run_steps("batch-reactor", 900)
        charging = [
            step.truth.values[b.REACTOR_TEMP]
            for step in steps
            if round(step.truth.values[b.BATCH_PHASE]) == b.Phase.CHARGE
        ]
        holding = [
            step.truth.values[b.REACTOR_TEMP]
            for step in steps
            if round(step.truth.values[b.BATCH_PHASE]) == b.Phase.REACT
        ]
        assert min(charging) < 40.0
        assert min(holding) > 60.0

    def test_the_reactor_has_no_control_network_because_a_dcs_is_not_modbus(self) -> None:
        assert b.BATCH_DESCRIPTION.control_network is None
        assert all(step.commands == () for step in run_steps("batch-reactor", 60))


# --- Imperfection, rhythm and non-degeneracy ---------------------------------------------------


@pytest.mark.parametrize("plant_id", list(PLANTS))
class TestEveryPlantIsHonestlyImperfect:
    def test_no_signal_sits_perfectly_still_for_a_whole_run(self, plant_id: str) -> None:
        steps = run_steps(plant_id, FULL_CYCLE_STEPS[plant_id])
        for key in PLANTS[plant_id][1].signal_keys():
            assert len(set(series(steps, key))) > 1, key

    def test_no_two_signals_are_the_same_series(self, plant_id: str) -> None:
        steps = run_steps(plant_id, 400)
        seen: dict[tuple[float, ...], str] = {}
        for key in PLANTS[plant_id][1].signal_keys():
            values = tuple(series(steps, key))
            clash = seen.get(values)
            assert clash is None, f"{key} is identical to {clash}"
            seen[values] = key

    def test_nothing_ever_leaves_the_span_its_instrument_declares(self, plant_id: str) -> None:
        steps = run_steps(plant_id, 900)
        for signal in PLANTS[plant_id][1].signals:
            values = series(steps, signal.key)
            assert min(values) >= signal.low
            assert max(values) <= signal.high

    def test_measurement_noise_is_present_on_every_instrument_declaring_it(
        self, plant_id: str
    ) -> None:
        steps = run_steps(plant_id, 600)
        for signal in PLANTS[plant_id][1].signals:
            if signal.noise_stddev == 0.0:
                continue
            residual = [
                step.report.values[signal.key] - step.truth.values[signal.key] for step in steps
            ]
            assert statistics.pstdev(residual) > 0.3 * signal.noise_stddev, signal.key

    def test_benign_operational_events_happen_and_are_labelled(self, plant_id: str) -> None:
        steps = run_steps(plant_id, 2000)
        began = [step.began for step in steps if step.began is not None]
        assert len(began) >= 2
        assert all(event.label and event.kind for event in began)

    def test_a_run_is_reproducible_from_its_seed_and_differs_under_another(
        self, plant_id: str
    ) -> None:
        first = [step.report.values for step in run_steps(plant_id, 300, seed=4)]
        again = [step.report.values for step in run_steps(plant_id, 300, seed=4)]
        other = [step.report.values for step in run_steps(plant_id, 300, seed=5)]
        assert first == again
        assert first != other


class TestRhythmsAreRealAndDifferent:
    def test_water_demand_follows_a_daily_cycle_with_a_morning_peak(self) -> None:
        steps = run_steps("water-treatment", 2880)
        flow = series(steps, w.DISTRIBUTION_FLOW)
        morning = statistics.fmean(flow[7 * 120 : 10 * 120])
        night = statistics.fmean(flow[0:120] + flow[-120:])
        assert morning > night + 20.0

    def test_the_power_plant_carries_a_stepped_shift_load_as_well_as_a_smooth_one(self) -> None:
        steps = run_steps("power-generation", 8640)
        demand = series(steps, p.GRID_DEMAND, truth=True)
        before_shift = statistics.fmean(demand[8 * 360 - 60 : 8 * 360])
        after_shift = statistics.fmean(demand[8 * 360 : 8 * 360 + 60])
        assert after_shift - before_shift > 3.0

    def test_the_reactor_has_no_daily_cycle_at_all_because_a_batch_is_not_a_day(self) -> None:
        steps = run_steps("batch-reactor", 1440)
        level = series(steps, b.REACTOR_LEVEL, truth=True)
        first_day_half = statistics.fmean(level[:720])
        second_day_half = statistics.fmean(level[720:])
        assert abs(first_day_half - second_day_half) < 25.0


class TestCalibrationDrift:
    @pytest.mark.parametrize("plant_id", list(PLANTS))
    def test_instruments_drift_slowly_and_stay_inside_their_declared_bound(
        self, plant_id: str
    ) -> None:
        steps = run_steps(plant_id, 2000)
        for signal in PLANTS[plant_id][1].signals:
            if signal.drift_amplitude == 0.0:
                continue
            residual = [
                step.report.values[signal.key] - step.truth.values[signal.key] for step in steps
            ]
            window = max(len(residual) // 10, 2)
            early = statistics.fmean(residual[:window])
            late = statistics.fmean(residual[-window:])
            assert abs(early - late) <= signal.drift_amplitude * 2.0 + signal.noise_stddev

"""ADR 0122: the PHOS ICSSim corpus's schedule and its declared split. Nothing here runs ICSSim."""

from __future__ import annotations

import itertools

import pytest
from scripts.icssim.generate_corpus import ICSSIM_COMMIT, RUNS
from scripts.icssim.phos_icssim import (
    ATTACK_KINDS,
    BOTTLE_LEVEL_MAX_DEFAULT,
    BOTTLE_MAX_LEVEL,
    DURATIONS,
    GAP_S,
    LEGAL_FLOW_FRACTION,
    SCENARIOS,
    SETPOINT_BAND,
    SUBFLOOR_STEPS,
    TANK_LEVEL_MAX_DEFAULT,
    TANK_OUTPUT_FLOW_RATE,
    VALVE_FORCE_OFF,
    VALVE_RELEASE,
    WARMUP_S,
    bottle_setpoint_band,
    legal_output_flow,
    reported_level,
    schedule,
)

from phos.atlas.command_response import HORIZON_STEPS
from phos.eval.build_declaration import build_seed_blocks


@pytest.mark.parametrize("name", sorted(SCENARIOS))
@pytest.mark.parametrize("seed", [96001, 96011, 96101, 7])
def test_a_schedule_is_a_function_of_its_seed(name: str, seed: int) -> None:
    assert schedule(name, seed) == schedule(name, seed)


@pytest.mark.parametrize("name", sorted(SCENARIOS))
@pytest.mark.parametrize("seed", range(96011, 96021))
def test_events_are_ordered_apart_and_inside_the_run(name: str, seed: int) -> None:
    events = schedule(name, seed)
    duration = SCENARIOS[name].duration_s
    assert events
    assert events[0].start >= WARMUP_S
    for earlier, later in itertools.pairwise(events):
        assert later.start - earlier.end >= GAP_S - 0.2
    assert all(event.start < event.end <= duration - 120 for event in events)


@pytest.mark.parametrize("seed", range(96101, 96121))
def test_every_mixed_run_holds_every_declared_kind(seed: int) -> None:
    kinds = {event.kind for event in schedule("mixed", seed)}
    assert kinds == set(SCENARIOS["mixed"].kinds)


def test_normal_runs_carry_no_attack() -> None:
    for seed in (96001, 96002, 96003):
        assert all(event.label == "benign" for event in schedule("normal", seed))


def test_labels_follow_the_declared_kinds() -> None:
    for event in schedule("mixed", 96011):
        assert (event.label == "attack") is (event.kind in ATTACK_KINDS)
    assert "maintenance" not in ATTACK_KINDS
    assert "mimic_maintenance" in ATTACK_KINDS


def test_development_and_held_out_seeds_are_disjoint() -> None:
    development = {seed for _scenario, seed in RUNS["development"]["runs"]}  # type: ignore[attr-defined]
    held_out = {seed for _scenario, seed in RUNS["held-out"]["runs"]}  # type: ignore[attr-defined]
    assert not development & held_out
    assert held_out == set(range(96101, 96121))
    assert all(scenario == "mixed" for scenario, _ in RUNS["held-out"]["runs"])  # type: ignore[attr-defined]
    blocks = []
    for spec in RUNS.values():
        runs = spec["runs"]
        assert isinstance(runs, list)
        blocks.append({int(seed) for _scenario, seed in runs})
    for left, right in itertools.combinations(blocks, 2):
        assert not left & right


def test_legal_flow_stays_on_the_plant_curve_and_off_the_detector() -> None:
    """ADR 0295. The fraction band is the instrument band. Flow is the plant's own value."""
    assert LEGAL_FLOW_FRACTION == (0.03, 0.08)
    assert reported_level(9.5, 0.08) == 10.0
    assert reported_level(4.0, 0.05) == 4.2
    assert legal_output_flow(4.2, output_valve_open=True) == TANK_OUTPUT_FLOW_RATE
    assert legal_output_flow(4.2, output_valve_open=False) == 0.0
    assert legal_output_flow(0.0, output_valve_open=True) == 0.0
    for seed in range(96411, 96415):
        found = [event for event in schedule("mixed3", seed) if event.kind == "legal_flow"]
        assert found
        for event in found:
            fraction = event.params["fraction"]
            assert isinstance(fraction, float)
            assert LEGAL_FLOW_FRACTION[0] <= fraction <= LEGAL_FLOW_FRACTION[1]
            assert event.label == "attack"
            assert set(event.params) == {"fraction"}


def test_icssim_is_pinned_to_a_full_commit() -> None:
    assert len(ICSSIM_COMMIT) == 40


def test_in_range_command_uses_the_ordinary_band_and_the_existing_valve_values() -> None:
    """ADR 0301. The band and the mode values are the ones the generator already had."""
    assert SETPOINT_BAND == (6.5, 7.5)
    assert VALVE_FORCE_OFF == 1
    assert VALVE_RELEASE == 3
    assert SCENARIOS["in_range"].kinds == ("setpoint", "maintenance", "in_range_command")
    short, long = DURATIONS["in_range_command"]
    assert short == 3 * HORIZON_STEPS
    assert long == 180
    for seed in range(96611, 96619):
        found = [event for event in schedule("in_range", seed) if event.kind == "in_range_command"]
        assert found
        for event in found:
            assert event.label == "attack"
            value = event.params["value"]
            assert isinstance(value, float)
            assert SETPOINT_BAND[0] <= value <= SETPOINT_BAND[1]
            assert event.params["tag"] == "tank_level_max"
            assert event.params["hold_tag"] == "tank_input_valve_mode"
            assert event.params["hold_value"] == float(VALVE_FORCE_OFF)
            assert event.params["release_value"] == float(VALVE_RELEASE)
            assert short - 0.2 <= event.end - event.start <= long + 0.2


def test_subfloor_walk_takes_720_steps_across_the_ordinary_band() -> None:
    """ADR 0301. The step is the band divided by the harness floor, with no extra jump."""
    assert SUBFLOOR_STEPS == 720
    assert SCENARIOS["subfloor"].kinds == ("setpoint", "maintenance", "subfloor_walk")
    step = (SETPOINT_BAND[1] - SETPOINT_BAND[0]) / SUBFLOOR_STEPS
    assert step == pytest.approx(1.0 / 720)
    for seed in range(96811, 96819):
        found = [event for event in schedule("subfloor", seed) if event.kind == "subfloor_walk"]
        assert found
        for event in found:
            assert event.label == "attack"
            assert event.params["start"] == SETPOINT_BAND[0]
            assert event.params["end"] == SETPOINT_BAND[1]
            assert event.params["steps"] == float(SUBFLOOR_STEPS)
            assert event.end - event.start == 720


def test_day1_seeds_match_the_declaration_and_stay_disjoint() -> None:
    """ADR 0301. The walk roles exist so the gate can name them, and they overlap nothing."""
    dev = RUNS["development4"]["runs"]
    held = RUNS["held-out4"]["runs"]
    walk = RUNS["development4-walk"]["runs"]
    walk_held = RUNS["held-out4-walk"]["runs"]
    assert isinstance(dev, list)
    assert isinstance(held, list)
    assert isinstance(walk, list)
    assert isinstance(walk_held, list)
    assert [seed for scenario, seed in dev if scenario == "normal"] == [96601, 96602, 96603]
    assert [seed for scenario, seed in dev if scenario == "in_range"] == list(range(96611, 96619))
    assert [seed for _scenario, seed in held] == list(range(96701, 96721))
    assert all(scenario == "in_range" for scenario, _seed in held)
    assert [seed for scenario, seed in walk if scenario == "normal"] == [96801, 96802, 96803]
    assert [seed for scenario, seed in walk if scenario == "subfloor"] == list(range(96811, 96819))
    assert [seed for _scenario, seed in walk_held] == list(range(96901, 96921))
    assert all(scenario == "subfloor" for scenario, _seed in walk_held)


def test_joint_command_moves_two_loop_setpoints_inside_the_plant_bands() -> None:
    """ADR 0316. The tank band is the existing one. The bottle band uses its half-width."""
    low, high = bottle_setpoint_band()
    half = (SETPOINT_BAND[1] - SETPOINT_BAND[0]) / 2
    assert (SETPOINT_BAND[0] + SETPOINT_BAND[1]) / 2 == TANK_LEVEL_MAX_DEFAULT
    assert low == BOTTLE_LEVEL_MAX_DEFAULT - half
    assert high == min(BOTTLE_LEVEL_MAX_DEFAULT + half, BOTTLE_MAX_LEVEL)
    assert high <= BOTTLE_MAX_LEVEL
    assert SCENARIOS["joint"].kinds == ("setpoint", "maintenance", "joint_command")
    short, long = DURATIONS["joint_command"]
    assert short == 3 * HORIZON_STEPS
    assert long == 180
    for seed in range(98011, 98019):
        found = [event for event in schedule("joint", seed) if event.kind == "joint_command"]
        assert found
        for event in found:
            assert event.label == "attack"
            tank = event.params["tank_value"]
            bottle = event.params["bottle_value"]
            assert isinstance(tank, float)
            assert isinstance(bottle, float)
            assert SETPOINT_BAND[0] <= tank <= SETPOINT_BAND[1]
            assert low <= bottle <= high
            assert event.params["tank_tag"] == "tank_level_max"
            assert event.params["bottle_tag"] == "bottle_level_max"
            assert "hold_tag" not in event.params
            assert short - 0.2 <= event.end - event.start <= long + 0.2


def test_joint_seeds_match_the_declaration_and_stay_disjoint() -> None:
    """ADR 0316. The new blocks overlap neither each other nor the seeds already registered."""
    dev = RUNS["development5"]["runs"]
    held = RUNS["held-out5"]["runs"]
    assert isinstance(dev, list)
    assert isinstance(held, list)
    assert [seed for scenario, seed in dev if scenario == "normal"] == [98001, 98002, 98003]
    assert [seed for scenario, seed in dev if scenario == "joint"] == list(range(98011, 98019))
    assert [seed for _scenario, seed in held] == list(range(98101, 98121))
    assert all(scenario == "joint" for scenario, _seed in held)
    fresh = {int(seed) for _scenario, seed in [*dev, *held]}
    used = set().union(*build_seed_blocks().values())
    assert fresh.isdisjoint(used)

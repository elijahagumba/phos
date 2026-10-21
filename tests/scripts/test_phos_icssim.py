"""ADR 0122: the PHOS ICSSim corpus's schedule and its declared split. Nothing here runs ICSSim."""

from __future__ import annotations

import itertools

import pytest
from scripts.icssim.generate_corpus import ICSSIM_COMMIT, RUNS
from scripts.icssim.phos_icssim import (
    ATTACK_KINDS,
    GAP_S,
    LEGAL_FLOW_FRACTION,
    SCENARIOS,
    TANK_OUTPUT_FLOW_RATE,
    WARMUP_S,
    legal_output_flow,
    reported_level,
    schedule,
)


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

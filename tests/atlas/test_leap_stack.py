"""ADR 0308: joint moves and walks share one page, and the misses fall by half."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from phos.atlas.consistency import ALERTS_PER_SHIFT
from phos.atlas.consistency_windows import EVENT_WINDOW
from phos.atlas.joint_setpoint import SETPOINT_BAND, SetpointStep, joint_moves
from phos.atlas.leap_stack import stack_page
from phos.atlas.subfloor_walk import WALK_STEPS, subfloor_walks

WHEN = datetime(2026, 10, 22, 11, 0, tzinfo=UTC)
LOW, HIGH = SETPOINT_BAND


def _pair(index: int) -> tuple[SetpointStep, SetpointStep]:
    base = index * (EVENT_WINDOW + 5)
    origin = WHEN + timedelta(seconds=base)
    return (
        SetpointStep(f"a{index}", origin, 7.0),
        SetpointStep(f"b{index}", origin + timedelta(seconds=1), 7.1),
    )


def _walk(index: int) -> tuple[SetpointStep, ...]:
    origin = WHEN + timedelta(hours=index + 1)
    span = HIGH - LOW
    return tuple(
        SetpointStep(
            f"w{index}",
            origin + timedelta(seconds=step),
            LOW + span * step / WALK_STEPS,
        )
        for step in range(WALK_STEPS)
    )


def test_four_joints_and_four_walks_cut_the_better_checkers_misses_in_half() -> None:
    steps: list[SetpointStep] = []
    for index in range(4):
        steps.extend(_pair(index))
        steps.extend(_walk(index))
    joint_only = joint_moves(steps)
    walk_only = subfloor_walks(steps)
    assert len(joint_only) == 4
    assert len(walk_only) == 4
    champion_misses = 8 - max(len(joint_only), len(walk_only))
    page = stack_page(steps)
    stack_misses = 8 - len(page)
    assert champion_misses == 4
    assert stack_misses <= champion_misses // 2
    assert len(page) == 8
    assert len(page) <= ALERTS_PER_SHIFT
    assert {hit.kind for hit in page} == {"joint", "walk"}


def test_a_lone_in_band_write_adds_no_alert() -> None:
    assert stack_page((SetpointStep("tank_level_max", WHEN, 7.0),)) == ()

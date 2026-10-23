"""ADR 0311: handoffs share the page with joint moves and walks."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from phos.atlas.consistency import ALERTS_PER_SHIFT, SHIFT_SECONDS
from phos.atlas.consistency_windows import EVENT_WINDOW
from phos.atlas.handoff_page import handoff_page
from phos.atlas.joint_setpoint import SETPOINT_BAND, SetpointStep
from phos.atlas.leap_stack import stack_page
from phos.atlas.subfloor_walk import WALK_STEPS

WHEN = datetime(2026, 10, 22, 13, 0, tzinfo=UTC)
LOW, HIGH = SETPOINT_BAND


def _joint(index: int) -> tuple[SetpointStep, SetpointStep]:
    origin = WHEN + timedelta(seconds=index * (EVENT_WINDOW + 5))
    return (
        SetpointStep(f"j{index}a", origin, 7.0),
        SetpointStep(f"j{index}b", origin + timedelta(seconds=1), 7.1),
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


def _handoff(index: int) -> tuple[SetpointStep, SetpointStep]:
    origin = WHEN + timedelta(days=1, seconds=index * SHIFT_SECONDS)
    return (
        SetpointStep(f"h{index}a", origin, 7.0),
        SetpointStep(f"h{index}b", origin + timedelta(seconds=EVENT_WINDOW + 1), 7.0),
    )


def _fixture() -> tuple[SetpointStep, ...]:
    steps: list[SetpointStep] = []
    for index in range(2):
        steps.extend(_joint(index))
        steps.extend(_walk(index))
    for index in range(8):
        steps.extend(_handoff(index))
    return tuple(steps)


def test_eight_handoffs_on_a_full_page_cut_the_stack_misses_in_half() -> None:
    steps = _fixture()
    stack = stack_page(steps)
    assert len(stack) == 4
    assert {hit.kind for hit in stack} == {"joint", "walk"}
    champion_misses = 8
    page = handoff_page(steps)
    handoff_hits = [hit for hit in page if hit.kind == "handoff"]
    page_misses = 8 - len(handoff_hits)
    assert champion_misses == 8
    assert page_misses <= champion_misses // 2
    assert len(page) == ALERTS_PER_SHIFT
    assert {hit.kind for hit in page} == {"joint", "walk", "handoff"}


def test_a_lone_in_band_write_adds_no_alert() -> None:
    assert handoff_page((SetpointStep("tank_level_max", WHEN, 7.0),)) == ()


def test_handoff_page_does_not_call_budget_alerts(monkeypatch: pytest.MonkeyPatch) -> None:
    import phos.atlas.consistency as consistency
    import phos.atlas.handoff_page as handoff_page_module

    def trap(*_args: object, **_kwargs: object) -> tuple[list[int], list[int], list[float]]:
        raise AssertionError("budget_alerts was called")

    monkeypatch.setattr(consistency, "budget_alerts", trap)
    assert not hasattr(handoff_page_module, "budget_alerts")
    assert len(handoff_page(_fixture())) == ALERTS_PER_SHIFT

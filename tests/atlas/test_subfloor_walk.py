"""ADR 0307: a 720-step in-band walk is a class the joint check does not see."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from phos.atlas.consistency import ALERTS_PER_SHIFT
from phos.atlas.incident_pack import IncidentAlert, incidents_inside_budget
from phos.atlas.joint_setpoint import SETPOINT_BAND, SetpointStep, joint_moves
from phos.atlas.subfloor_walk import WALK_STEPS, subfloor_walks

WHEN = datetime(2026, 10, 22, 10, 0, tzinfo=UTC)
LOW, HIGH = SETPOINT_BAND


def _walk(tag: str, steps: int, *, origin: datetime = WHEN) -> tuple[SetpointStep, ...]:
    span = HIGH - LOW
    return tuple(
        SetpointStep(tag, origin + timedelta(seconds=index), LOW + span * index / WALK_STEPS)
        for index in range(steps)
    )


def test_the_joint_check_is_silent_on_one_tag_walked_720_steps() -> None:
    steps = _walk("tank_level_max", WALK_STEPS)
    assert joint_moves(steps) == ()
    found = subfloor_walks(steps)
    assert len(found) == 1
    assert found[0].at == steps[0].at
    assert found[0].steps == WALK_STEPS
    assert found[0].tag == "tank_level_max"


def test_719_steps_are_not_a_walk() -> None:
    assert subfloor_walks(_walk("tank_level_max", WALK_STEPS - 1)) == ()


def test_one_step_and_an_outside_value_add_nothing() -> None:
    lone = (SetpointStep("tank_level_max", WHEN, 7.0),)
    outside = _walk("bottle_level_max", WALK_STEPS)
    outside = tuple(SetpointStep(step.tag, step.at, HIGH + 1.0) for step in outside)
    assert subfloor_walks(lone) == ()
    assert subfloor_walks(outside) == ()


def test_a_two_second_gap_splits_the_walk_below_the_floor() -> None:
    steps = list(_walk("tank_level_max", WALK_STEPS))
    broken = steps[400]
    steps[400] = SetpointStep(broken.tag, broken.at + timedelta(seconds=2), broken.value)
    assert subfloor_walks(steps) == ()


def test_twelve_walks_miss_at_most_half_inside_eight() -> None:
    alerts: list[IncidentAlert] = []
    for index in range(12):
        origin = WHEN + timedelta(hours=index)
        found = subfloor_walks(_walk(f"tag{index}", WALK_STEPS, origin=origin))
        assert len(found) == 1
        assert joint_moves(_walk(f"tag{index}", WALK_STEPS, origin=origin)) == ()
        alerts.append(IncidentAlert(f"w{index}", found[0].at, found[0].score, f"w{index}"))
    shown = incidents_inside_budget(tuple(alerts), packed=True)
    missed = 12 - len(shown)
    assert len(shown) == ALERTS_PER_SHIFT
    assert missed <= 12 // 2

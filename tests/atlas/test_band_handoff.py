"""ADR 0310: the same in-band value on a second tag, after the joint window."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from phos.atlas.band_handoff import band_handoffs
from phos.atlas.consistency import ALERTS_PER_SHIFT, SHIFT_SECONDS
from phos.atlas.consistency_windows import EVENT_WINDOW
from phos.atlas.incident_pack import IncidentAlert, incidents_inside_budget
from phos.atlas.joint_setpoint import SETPOINT_BAND, SetpointStep, joint_moves
from phos.atlas.leap_stack import stack_page
from phos.atlas.subfloor_walk import subfloor_walks

WHEN = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)
LOW, HIGH = SETPOINT_BAND


def _step(tag: str, seconds: int, value: float = 7.0) -> SetpointStep:
    return SetpointStep(tag, WHEN + timedelta(seconds=seconds), value)


def _pair(index: int) -> tuple[SetpointStep, SetpointStep]:
    base = index * SHIFT_SECONDS
    return (
        _step(f"a{index}", base, 7.0),
        _step(f"b{index}", base + EVENT_WINDOW + 1, 7.0),
    )


def test_a_second_tag_after_the_window_is_one_handoff_at_the_first_write() -> None:
    steps = (_step("tank_level_max", 0, 6.5), _step("bottle_level_max", EVENT_WINDOW + 1, 6.5))
    found = band_handoffs(steps)
    assert len(found) == 1
    assert found[0].at == steps[0].at
    assert found[0].tags == ("bottle_level_max", "tank_level_max")
    assert found[0].value == 6.5
    assert found[0].score == 2.0
    assert "confidence" not in found[0].__dict__


def test_the_joint_window_and_the_walk_and_the_stack_stay_silent() -> None:
    steps = _pair(0)
    assert joint_moves(steps) == ()
    assert subfloor_walks(steps) == ()
    assert stack_page(steps) == ()
    assert len(band_handoffs(steps)) == 1


def test_two_tags_inside_the_joint_window_are_not_a_handoff() -> None:
    steps = (_step("tank_level_max", 0), _step("bottle_level_max", EVENT_WINDOW))
    assert band_handoffs(steps) == ()
    assert len(joint_moves(steps)) == 1


def test_the_same_tag_does_not_hand_off_to_itself() -> None:
    steps = (_step("tank_level_max", 0), _step("tank_level_max", EVENT_WINDOW + 1))
    assert band_handoffs(steps) == ()


def test_a_different_value_is_not_a_handoff() -> None:
    steps = (_step("tank_level_max", 0, 6.5), _step("bottle_level_max", EVENT_WINDOW + 1, 7.5))
    assert band_handoffs(steps) == ()


def test_a_value_outside_the_band_is_not_this_class() -> None:
    steps = (
        _step("tank_level_max", 0, LOW - 0.1),
        _step("bottle_level_max", EVENT_WINDOW + 1, LOW - 0.1),
        _step("flow_max", 0, HIGH + 0.1),
        _step("flow_min", EVENT_WINDOW + 1, HIGH + 0.1),
    )
    assert band_handoffs(steps) == ()


def test_a_gap_of_one_shift_is_not_a_handoff() -> None:
    steps = (_step("tank_level_max", 0), _step("bottle_level_max", SHIFT_SECONDS))
    assert band_handoffs(steps) == ()
    inside = (_step("tank_level_max", 0), _step("bottle_level_max", SHIFT_SECONDS - 1))
    assert len(band_handoffs(inside)) == 1


def test_twelve_handoffs_keep_half_the_misses_inside_eight() -> None:
    steps: list[SetpointStep] = []
    alerts = []
    for index in range(12):
        pair = _pair(index)
        steps.extend(pair)
        found = band_handoffs(pair)
        assert len(found) == 1
        alerts.append(IncidentAlert(f"h{index}", found[0].at, found[0].score, f"h{index}"))
    assert joint_moves(steps) == ()
    assert subfloor_walks(steps) == ()
    assert stack_page(steps) == ()
    assert len(band_handoffs(steps)) == 12
    shown = incidents_inside_budget(tuple(alerts), packed=True)
    missed = 12 - len(shown)
    assert len(shown) == ALERTS_PER_SHIFT
    assert missed <= 12 // 2


def test_an_empty_inlet_stays_empty_and_a_naive_time_raises() -> None:
    assert band_handoffs(()) == ()
    naive = SetpointStep("tank_level_max", datetime(2026, 10, 22, 12, 0), 7.0)
    later = _step("bottle_level_max", EVENT_WINDOW + 1)
    with pytest.raises(ValueError, match="timezone-aware"):
        band_handoffs((naive, later))


def test_band_handoffs_does_not_call_budget_alerts(monkeypatch: pytest.MonkeyPatch) -> None:
    import phos.atlas.band_handoff as band_handoff
    import phos.atlas.consistency as consistency

    def trap(*_args: object, **_kwargs: object) -> tuple[list[int], list[int], list[float]]:
        raise AssertionError("budget_alerts was called")

    monkeypatch.setattr(consistency, "budget_alerts", trap)
    assert not hasattr(band_handoff, "budget_alerts")
    assert len(band_handoffs(_pair(0))) == 1

"""ADR 0305: two in-band setpoints together are a class one setpoint does not show."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from phos.atlas.consistency import ALERTS_PER_SHIFT
from phos.atlas.consistency_windows import EVENT_WINDOW
from phos.atlas.incident_pack import IncidentAlert, incidents_inside_budget
from phos.atlas.joint_setpoint import SETPOINT_BAND, SetpointStep, joint_moves
from phos.atlas.program_transfer import refuse_function_code

WHEN = datetime(2026, 10, 22, 9, 0, tzinfo=UTC)


def _step(tag: str, seconds: int, value: float = 7.0) -> SetpointStep:
    return SetpointStep(tag, WHEN + timedelta(seconds=seconds), value)


def test_one_setpoint_inside_the_band_raises_nothing() -> None:
    assert joint_moves((_step("tank_level_max", 0),)) == ()


def test_two_tags_inside_the_band_are_one_move_at_the_first_write() -> None:
    steps = (_step("tank_level_max", 0, 6.5), _step("bottle_level_max", 10, 7.5))
    found = joint_moves(steps)
    assert len(found) == 1
    assert found[0].at == steps[0].at
    assert found[0].tags == ("bottle_level_max", "tank_level_max")
    assert found[0].score == 2.0
    assert "confidence" not in found[0].__dict__


def test_two_tags_outside_the_window_do_not_join() -> None:
    steps = (
        _step("tank_level_max", 0),
        _step("bottle_level_max", EVENT_WINDOW + 1),
    )
    assert joint_moves(steps) == ()


def test_a_value_outside_the_band_is_not_this_class() -> None:
    low, high = SETPOINT_BAND
    steps = (
        _step("tank_level_max", 0, low - 0.1),
        _step("bottle_level_max", 5, high + 0.1),
    )
    assert joint_moves(steps) == ()


def test_four_joint_moves_are_caught_and_a_single_write_adds_no_false_alert() -> None:
    steps = []
    for index in range(4):
        base = index * (EVENT_WINDOW + 5)
        steps.append(_step("tank_level_max", base))
        steps.append(_step("bottle_level_max", base + 2))
    steps.append(_step("tank_level_min", 50_000))
    found = joint_moves(steps)
    assert len(found) == 4
    singles = joint_moves((_step("tank_level_min", 50_000),))
    assert singles == ()


def test_twelve_joint_moves_keep_half_the_misses_inside_eight() -> None:
    alerts = []
    for index in range(12):
        base = index * (EVENT_WINDOW + 5)
        move = joint_moves((_step("tank_level_max", base), _step("bottle_level_max", base + 1)))
        assert len(move) == 1
        alerts.append(IncidentAlert(f"j{index}", move[0].at, move[0].score, f"j{index}"))
    shown = incidents_inside_budget(tuple(alerts), packed=True)
    missed = 12 - len(shown)
    assert len(shown) == ALERTS_PER_SHIFT
    assert missed <= 12 // 2


def test_a_function_code_is_not_a_setpoint_step() -> None:
    with pytest.raises(ValueError, match="not a program transfer"):
        refuse_function_code(6)
    assert joint_moves(()) == ()

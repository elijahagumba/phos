"""ADR 0301: the champion denominator is misses, false alerts, and delay."""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.lane_e_icssim_baseline import (
    ClassAccount,
    Event,
    RunWindow,
    _median,
    _rate,
    attack_directories,
    class_account,
)


def _event(kind: str, start: float, end: float, label: str = "attack") -> Event:
    return Event(kind=kind, label=label, start=start, end=end)


def test_the_champion_is_whichever_misses_fewer() -> None:
    account = class_account(
        (
            RunWindow(
                duration_s=3600.0,
                events=(
                    _event("in_range_command", 10.0, 20.0),
                    _event("in_range_command", 40.0, 50.0),
                ),
                frozen=(15.0,),
                lane1=(),
            ),
        ),
        "in_range_command",
    )
    assert account.events == 2
    assert account.misses_frozen == 1
    assert account.misses_lane1 == 2
    assert account.champion == "frozen"
    assert account.misses_champion == 1
    assert account.delays_frozen == (5.0,)
    assert account.delays_lane1 == ()


def test_an_alert_outside_the_class_window_is_a_false_alert() -> None:
    account = class_account(
        (
            RunWindow(
                duration_s=7200.0,
                events=(
                    _event("in_range_command", 100.0, 200.0),
                    _event("setpoint", 300.0, 301.0, label="benign"),
                ),
                frozen=(150.0, 300.5, 500.0),
                lane1=(150.0,),
            ),
        ),
        "in_range_command",
    )
    assert account.false_frozen == 2
    assert account.false_lane1 == 0
    assert account.misses_frozen == 0
    assert _rate(account.false_frozen, account.duration_s) == pytest.approx(1.0)


def test_tied_misses_keep_the_lower_false_alert_count_and_a_full_tie_keeps_frozen() -> None:
    quieter = class_account(
        (RunWindow(3600.0, (_event("in_range_command", 0.0, 10.0),), (1.0, 20.0), (1.0,)),),
        "in_range_command",
    )
    assert quieter.misses_frozen == quieter.misses_lane1 == 0
    assert quieter.champion == "lane1"
    tied = class_account(
        (RunWindow(3600.0, (_event("in_range_command", 0.0, 10.0),), (1.0,), (1.0,)),),
        "in_range_command",
    )
    assert tied.champion == "frozen"


def test_the_delay_uses_the_earliest_alert_inside_the_window() -> None:
    account = class_account(
        (RunWindow(3600.0, (_event("subfloor_walk", 10.0, 30.0),), (25.0, 12.0), ()),),
        "subfloor_walk",
    )
    assert account.delays_frozen == (2.0,)
    assert _median(account.delays_frozen) == "2.000000"
    assert _median(()) == "none"


def test_a_zero_duration_is_refused() -> None:
    with pytest.raises(ValueError, match="duration_s"):
        _rate(1, 0.0)


def test_the_walk_runs_are_opened_with_the_older_attack_directories(tmp_path: Path) -> None:
    """ADR 0301. Day 1 is `in_range-*`. The fallback corpus is `subfloor-*`."""
    for name in (
        "normal-96801",
        "subfloor-96811",
        "in_range-96611",
        "mixed-96011",
        "mixed2-96211",
        "notes",
    ):
        (tmp_path / name).mkdir()
    found = [path.name for path in attack_directories(tmp_path)]
    assert found == ["in_range-96611", "mixed-96011", "mixed2-96211", "subfloor-96811"]


def test_account_fields_are_the_ones_the_report_prints() -> None:
    account = class_account((), "in_range_command")
    assert isinstance(account, ClassAccount)
    assert account.events == 0
    assert account.champion == "frozen"

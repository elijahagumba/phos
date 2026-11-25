"""A drain whose level never changes is a break. A drain whose level changes is silence.

One sample is not a drain. A flat stretch inside a longer drain that also moves is not a
separate drain, and it is silence.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from phos.atlas.declared_law import (
    STILL_DRAIN,
    DrainSample,
    LawOutcome,
    LawRegister,
    Standing,
    assess_plant,
)

WHEN = datetime(2026, 1, 1, tzinfo=UTC)
REGISTER = LawRegister((STILL_DRAIN,))
HELD = "still_drain. Every drain of two or more samples changes the level."
UNSTATED = (
    "still_drain. No drain of two or more samples was supplied, so still_drain was not stated."
)


def _row(
    index: int,
    level: float,
    *,
    outlet: float = 1.0,
    inlet: float = 0.0,
    flow: float = 0.0001,
    mode: float = 3.0,
) -> DrainSample:
    return DrainSample(
        at=WHEN + timedelta(seconds=index),
        level=level,
        input_valve=inlet,
        input_mode=mode,
        output_valve=outlet,
        output_mode=mode,
        flow=flow,
    )


def test_a_drain_that_holds_its_level_is_one_break() -> None:
    report = assess_plant(register=REGISTER, drain_samples=(_row(0, 6.5), _row(1, 6.5)))
    assert len(report.broken) == 1
    assert report.broken[0].name == "still_drain"
    assert report.broken[0].time == WHEN
    assert report.broken[0].statement == (
        "still_drain. The level stayed at 6.5 while the outlet was open and the inlet was shut."
    )
    assert report.held == ()
    assert report.unstated == ()


def test_a_drain_that_changes_is_silence() -> None:
    report = assess_plant(register=REGISTER, drain_samples=(_row(0, 6.5), _row(1, 6.4667)))
    assert report.broken == ()
    assert report.held == (LawOutcome("still_drain", Standing.HELD, HELD),)


def test_a_flat_stretch_inside_a_drain_that_also_moves_is_silence() -> None:
    rows = (
        _row(0, 6.6),
        _row(1, 6.5),
        _row(2, 6.5),
        _row(3, 6.5),
        _row(4, 6.1),
    )
    report = assess_plant(register=REGISTER, drain_samples=rows)
    assert report.broken == ()
    assert report.held == (LawOutcome("still_drain", Standing.HELD, HELD),)


def test_a_closed_valve_ends_the_drain_and_does_not_join_the_two_sides() -> None:
    rows = (
        _row(0, 6.5),
        _row(1, 6.5),
        _row(2, 6.5, outlet=0.0, flow=0.0),
        _row(3, 4.0),
        _row(4, 3.9),
    )
    report = assess_plant(register=REGISTER, drain_samples=rows)
    assert len(report.broken) == 1
    assert report.broken[0].time == WHEN


def test_one_sample_leaves_the_law_unstated() -> None:
    report = assess_plant(register=REGISTER, drain_samples=(_row(0, 6.5),))
    assert report.broken == ()
    assert report.held == ()
    assert report.unstated == (LawOutcome("still_drain", Standing.UNSTATED, UNSTATED),)


def test_an_empty_inlet_leaves_the_law_unstated() -> None:
    report = assess_plant(register=REGISTER)
    assert report.unstated == (LawOutcome("still_drain", Standing.UNSTATED, UNSTATED),)


def test_two_separate_flat_drains_keep_time_order() -> None:
    rows = (
        _row(0, 6.5),
        _row(1, 6.5),
        _row(2, 6.5, outlet=0.0, flow=0.0),
        _row(3, 4.0),
        _row(4, 4.0),
    )
    report = assess_plant(register=REGISTER, drain_samples=rows)
    assert tuple(item.time for item in report.broken) == (WHEN, WHEN + timedelta(seconds=3))

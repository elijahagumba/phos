"""A valve forced off release is a break only when no work order covers that tag and time.

Release is silence. A work order on a different tag does not cover the write. A plant that
named no valve, or named one and then supplied no write to it, leaves the law unstated.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from phos.atlas.declared_law import (
    UNBOOKED_COMMAND,
    LawOutcome,
    LawRegister,
    Standing,
    assess_plant,
)
from phos.atlas.joint_setpoint import SetpointStep
from phos.atlas.program_transfer import TransferWorkOrder

WHEN = datetime(2026, 1, 1, tzinfo=UTC)
OUTPUT = "tank_output_valve_mode"
INPUT = "tank_input_valve_mode"
VALVES = frozenset({OUTPUT, INPUT})
REGISTER = LawRegister((UNBOOKED_COMMAND,))
HELD = (
    "unbooked_command. No valve write forces a mode away from release "
    "without a work order covering it."
)


def _step(tag: str, value: float, at: datetime = WHEN) -> SetpointStep:
    return SetpointStep(tag, at, value)


def _order(tag: str, start: datetime = WHEN, end: datetime | None = None) -> TransferWorkOrder:
    stop = WHEN + timedelta(hours=1) if end is None else end
    return TransferWorkOrder(start=start, end=stop, tag=tag)


def test_an_uncovered_force_is_one_break() -> None:
    report = assess_plant((_step(OUTPUT, 1.0),), register=REGISTER, valve_tags=VALVES)
    assert len(report.broken) == 1
    assert report.broken[0].name == "unbooked_command"
    assert report.broken[0].time == WHEN
    assert report.broken[0].statement == (
        "unbooked_command. tank_output_valve_mode was forced to 1, and no work order covers it."
    )
    assert report.held == ()
    assert report.unstated == ()


def test_a_work_order_on_the_same_tag_is_silence() -> None:
    report = assess_plant(
        (_step(OUTPUT, 1.0),),
        register=REGISTER,
        work_orders=(_order(OUTPUT),),
        valve_tags=VALVES,
    )
    assert report.broken == ()
    assert report.held == (LawOutcome("unbooked_command", Standing.HELD, HELD),)


def test_a_work_order_on_the_other_valve_does_not_cover() -> None:
    report = assess_plant(
        (_step(OUTPUT, 1.0),),
        register=REGISTER,
        work_orders=(_order(INPUT),),
        valve_tags=VALVES,
    )
    assert len(report.broken) == 1
    assert report.broken[0].statement.startswith("unbooked_command. tank_output_valve_mode ")


def test_the_ends_of_a_work_order_are_included() -> None:
    end = WHEN + timedelta(minutes=10)
    covered = assess_plant(
        (_step(OUTPUT, 1.0, end),),
        register=REGISTER,
        work_orders=(_order(OUTPUT, end=end),),
        valve_tags=VALVES,
    )
    assert covered.broken == ()
    later = assess_plant(
        (_step(OUTPUT, 1.0, end + timedelta(seconds=1)),),
        register=REGISTER,
        work_orders=(_order(OUTPUT, end=end),),
        valve_tags=VALVES,
    )
    assert len(later.broken) == 1


def test_a_release_write_is_silence_with_no_work_order() -> None:
    report = assess_plant((_step(OUTPUT, 3.0),), register=REGISTER, valve_tags=VALVES)
    assert report.broken == ()
    assert report.held == (LawOutcome("unbooked_command", Standing.HELD, HELD),)


def test_forcing_the_valve_open_is_a_break_when_uncovered() -> None:
    report = assess_plant((_step(INPUT, 2.0),), register=REGISTER, valve_tags=VALVES)
    assert len(report.broken) == 1
    assert report.broken[0].statement == (
        "unbooked_command. tank_input_valve_mode was forced to 2, and no work order covers it."
    )


def test_a_release_beside_an_uncovered_force_does_not_add_a_break() -> None:
    later = WHEN + timedelta(minutes=5)
    report = assess_plant(
        (_step(OUTPUT, 1.0), _step(OUTPUT, 3.0, later), _step("tank_level_max", 7.0, later)),
        register=REGISTER,
        valve_tags=VALVES,
    )
    assert len(report.broken) == 1
    assert report.broken[0].time == WHEN


def test_no_named_valve_leaves_the_law_unstated() -> None:
    report = assess_plant((_step(OUTPUT, 1.0),), register=REGISTER)
    assert report.broken == ()
    assert report.held == ()
    assert report.unstated == (
        LawOutcome(
            "unbooked_command",
            Standing.UNSTATED,
            "unbooked_command. No valve tag was named, so unbooked_command was not stated.",
        ),
    )


def test_a_named_valve_with_no_write_to_it_leaves_the_law_unstated() -> None:
    report = assess_plant((_step("tank_level_max", 7.0),), register=REGISTER, valve_tags=VALVES)
    assert report.broken == ()
    assert report.unstated == (
        LawOutcome(
            "unbooked_command",
            Standing.UNSTATED,
            "unbooked_command. No write touched a valve, so unbooked_command was not stated.",
        ),
    )


def test_two_uncovered_forces_keep_time_order() -> None:
    later = WHEN + timedelta(minutes=2)
    report = assess_plant(
        (_step(INPUT, 2.0, later), _step(OUTPUT, 1.0)),
        register=REGISTER,
        valve_tags=VALVES,
    )
    assert tuple(item.time for item in report.broken) == (WHEN, later)

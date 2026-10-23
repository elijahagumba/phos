"""ADR 0312: an unbooked transfer keeps its place among the process hits."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from phos.atlas.consistency import ALERTS_PER_SHIFT, SHIFT_SECONDS
from phos.atlas.consistency_windows import EVENT_WINDOW
from phos.atlas.handoff_booking import TagBooking
from phos.atlas.handoff_page import handoff_page
from phos.atlas.joint_setpoint import SetpointStep
from phos.atlas.program_transfer import (
    GO_AND_LOOK,
    Booking,
    BookingKind,
    ProgramAct,
    TransferReport,
    transfer_report,
)
from phos.atlas.shift_brief import shift_brief

WHEN = datetime(2026, 10, 22, 16, 0, tzinfo=UTC)


def _handoff(index: int) -> tuple[SetpointStep, SetpointStep]:
    origin = WHEN + timedelta(seconds=1_000 + index * 700)
    value = 6.5 + index * 0.1
    return (
        SetpointStep(f"a{index}", origin, value),
        SetpointStep(f"b{index}", origin + timedelta(seconds=EVENT_WINDOW + 1), value),
    )


def _transfer(index: int, *, booked: bool = False) -> tuple[TransferReport, datetime]:
    at = WHEN + timedelta(seconds=index)
    act = (ProgramAct.DOWNLOAD, ProgramAct.UPLOAD, ProgramAct.ONLINE_EDIT)[index % 3]
    bookings: tuple[Booking, ...] = ()
    if booked:
        bookings = (
            Booking(
                BookingKind.DOWNTIME, act, WHEN - timedelta(minutes=1), WHEN + timedelta(hours=1)
            ),
        )
    return (transfer_report(act, bookings, at=at), at)


def test_four_unbooked_transfers_stay_inside_eight_handoffs() -> None:
    steps: list[SetpointStep] = []
    for index in range(8):
        steps.extend(_handoff(index))
    transfers = tuple(_transfer(index) for index in range(4))
    process = handoff_page(tuple(steps))
    assert len(process) == ALERTS_PER_SHIFT
    assert {hit.kind for hit in process} == {"handoff"}
    brief = shift_brief(steps, transfers)
    transfer_slots = [slot for slot in brief if slot.kind == "transfer"]
    assert len(brief) == ALERTS_PER_SHIFT
    assert len(transfer_slots) == 4
    assert 4 - len(transfer_slots) <= 4 // 2
    assert all(slot.instruction == GO_AND_LOOK for slot in transfer_slots)
    assert all(slot.lead is None for slot in transfer_slots)
    assert all(slot.next_observation for slot in transfer_slots)


def test_a_booked_transfer_takes_no_slot() -> None:
    steps = _handoff(0)
    brief = shift_brief(steps, (_transfer(0, booked=True),))
    assert [slot.kind for slot in brief] == ["handoff"]


def test_a_covering_tag_booking_frees_the_slot() -> None:
    steps = _handoff(0)
    origin = steps[0].at
    booking = TagBooking(
        ("a0", "b0"),
        origin - timedelta(minutes=1),
        origin + timedelta(hours=1),
    )
    assert shift_brief(steps, (), (booking,)) == ()
    bare = shift_brief(steps)
    assert len(bare) == 1
    assert bare[0].instruction == GO_AND_LOOK
    assert bare[0].lead is None


def test_a_joint_stays_beside_the_transfer() -> None:
    steps = (
        SetpointStep("tank_level_max", WHEN + timedelta(minutes=10), 7.0),
        SetpointStep("bottle_level_max", WHEN + timedelta(minutes=10, seconds=2), 7.1),
    )
    brief = shift_brief(steps, (_transfer(0),))
    assert [slot.kind for slot in brief] == ["transfer", "joint"]
    assert brief[1].instruction is None


def test_nine_unbooked_transfers_keep_the_earliest_eight() -> None:
    transfers = tuple(_transfer(index) for index in range(9))
    brief = shift_brief((), transfers)
    assert len(brief) == ALERTS_PER_SHIFT
    assert {slot.kind for slot in brief} == {"transfer"}


def test_a_second_shift_raises_and_budget_alerts_is_not_called(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import phos.atlas.consistency as consistency
    import phos.atlas.shift_brief as shift_brief_module

    def trap(*_args: object, **_kwargs: object) -> tuple[list[int], list[int], list[float]]:
        raise AssertionError("budget_alerts was called")

    monkeypatch.setattr(consistency, "budget_alerts", trap)
    assert not hasattr(shift_brief_module, "budget_alerts")
    later = WHEN + timedelta(seconds=SHIFT_SECONDS)
    steps = (
        SetpointStep("tank_level_max", WHEN, 7.0),
        SetpointStep("bottle_level_max", later, 7.0),
    )
    with pytest.raises(ValueError, match="one shift"):
        shift_brief(steps)

"""ADR 0302: a program transfer is not a register write, and an unbooked one says go and look."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from phos.atlas.consistency import ALERTS_PER_SHIFT
from phos.atlas.packet.modbus import FunctionCode
from phos.atlas.program_transfer import (
    GO_AND_LOOK,
    NEXT_OBSERVATION,
    Booking,
    BookingKind,
    OtherAlert,
    ProgramAct,
    TransferWorkOrder,
    refuse_function_code,
    shift_page,
    transfer_report,
)
from phos.atlas.templates import (
    ENGINEERING_MAINTENANCE_TEMPLATE_ID,
    UNAUTHORISED_CONTROL_TEMPLATE_ID,
)
from phos.reasoning import INSUFFICIENT_EVIDENCE_TEMPLATE_ID, tied_lead_ids

WHEN = datetime(2026, 10, 22, 8, 0, tzinfo=UTC)
START = WHEN - timedelta(hours=1)
END = WHEN + timedelta(hours=1)
STORIES = (
    ENGINEERING_MAINTENANCE_TEMPLATE_ID,
    UNAUTHORISED_CONTROL_TEMPLATE_ID,
)
CODES = (
    FunctionCode.READ_COILS,
    FunctionCode.READ_DISCRETE_INPUTS,
    FunctionCode.READ_HOLDING_REGISTERS,
    FunctionCode.READ_INPUT_REGISTERS,
    FunctionCode.WRITE_SINGLE_COIL,
    FunctionCode.WRITE_SINGLE_REGISTER,
    FunctionCode.WRITE_MULTIPLE_COILS,
    FunctionCode.WRITE_MULTIPLE_REGISTERS,
)


def test_each_act_keeps_its_own_name() -> None:
    assert [act.value for act in ProgramAct] == ["download", "upload", "online_edit"]
    for act in ProgramAct:
        report = transfer_report(act, (), (), at=WHEN)
        assert report.act is act
        assert report.act.value == act.value


@pytest.mark.parametrize("code", CODES)
def test_a_function_code_is_never_a_download(code: int) -> None:
    with pytest.raises(ValueError, match="not a program transfer"):
        refuse_function_code(code)
    assert str(code) not in {act.value for act in ProgramAct}


def test_an_empty_inlet_stays_empty_and_says_go_and_look() -> None:
    bookings: list[Booking] = []
    orders: list[TransferWorkOrder] = []
    report = transfer_report(ProgramAct.DOWNLOAD, bookings, orders, at=WHEN)
    assert bookings == []
    assert orders == []
    assert report.alert is True
    assert report.instruction == GO_AND_LOOK
    assert report.instruction == "Go and look."
    assert report.lead is None


def test_both_stories_stay_and_neither_leads() -> None:
    report = transfer_report(ProgramAct.UPLOAD, (), (), at=WHEN)
    assert report.stories == STORIES
    assert report.tied_lead_ids == STORIES
    assert tied_lead_ids(report.hypotheses) == STORIES
    assert INSUFFICIENT_EVIDENCE_TEMPLATE_ID in {item.template_id for item in report.hypotheses}
    assert report.lead is None
    assert report.lead != UNAUTHORISED_CONTROL_TEMPLATE_ID
    assert "confidence" not in report.__dict__


@pytest.mark.parametrize(
    "kind",
    (BookingKind.DOWNTIME, BookingKind.COMMISSIONING, BookingKind.CHECK_IN),
)
def test_a_covering_booking_withdraws_the_alert_and_does_not_pick(kind: BookingKind) -> None:
    booking = Booking(kind=kind, act=ProgramAct.ONLINE_EDIT, start=START, end=END)
    report = transfer_report(ProgramAct.ONLINE_EDIT, (booking,), (), at=WHEN)
    assert report.alert is False
    assert report.instruction is None
    assert report.tied_lead_ids == STORIES
    assert report.lead is None


def test_a_tag_work_order_does_not_cover_the_transfer() -> None:
    order = TransferWorkOrder(start=START, end=END, tag="tank_level_max")
    report = transfer_report(ProgramAct.DOWNLOAD, (), (order,), at=WHEN)
    assert order.act is None
    assert report.alert is True
    assert report.instruction == "Go and look."
    assert report.lead != UNAUTHORISED_CONTROL_TEMPLATE_ID


def test_a_work_order_that_names_the_act_withdraws_the_alert_only() -> None:
    order = TransferWorkOrder(start=START, end=END, act=ProgramAct.DOWNLOAD)
    report = transfer_report(ProgramAct.DOWNLOAD, (), (order,), at=WHEN)
    assert report.alert is False
    assert report.instruction is None
    assert report.tied_lead_ids == STORIES
    assert report.lead is None


def test_a_booking_for_another_act_or_another_hour_does_not_cover() -> None:
    other_act = Booking(kind=BookingKind.DOWNTIME, act=ProgramAct.UPLOAD, start=START, end=END)
    other_hour = Booking(
        kind=BookingKind.DOWNTIME,
        act=ProgramAct.DOWNLOAD,
        start=WHEN + timedelta(hours=2),
        end=WHEN + timedelta(hours=3),
    )
    for booking in (other_act, other_hour):
        report = transfer_report(ProgramAct.DOWNLOAD, (booking,), (), at=WHEN)
        assert report.alert is True
        assert report.instruction == "Go and look."


def _others(scores: list[float]) -> tuple[OtherAlert, ...]:
    return tuple(
        OtherAlert(at=WHEN + timedelta(minutes=index), score=score, key=f"o{index}")
        for index, score in enumerate(scores)
    )


def _open(act: ProgramAct, minute: int) -> tuple:
    at = WHEN + timedelta(minutes=minute)
    return transfer_report(act, (), (), at=at), at


def test_eight_others_and_one_unbooked_transfer_stay_inside_eight() -> None:
    others = _others([8, 7, 6, 5, 4, 3, 2, 1])
    report, at = _open(ProgramAct.DOWNLOAD, 30)
    page = shift_page(others, ((report, at),))
    assert len(page) == ALERTS_PER_SHIFT == 8
    kept = [slot.report for slot in page if slot.report is not None]
    assert kept == [report]
    assert kept[0].instruction == "Go and look."
    assert kept[0].tied_lead_ids == STORIES
    assert kept[0].lead is None
    assert "o7" not in {slot.other.key for slot in page if slot.other is not None}


def test_a_booked_transfer_does_not_take_a_slot() -> None:
    booking = Booking(kind=BookingKind.DOWNTIME, act=ProgramAct.DOWNLOAD, start=START, end=END)
    report = transfer_report(ProgramAct.DOWNLOAD, (booking,), (), at=WHEN)
    page = shift_page(_others([1, 2, 3, 4, 5, 6, 7, 8]), ((report, WHEN),))
    assert len(page) == 8
    assert all(slot.report is None for slot in page)
    assert [slot.other.key for slot in page if slot.other is not None] == [
        f"o{index}" for index in range(7, -1, -1)
    ]


def test_one_unbooked_transfer_and_no_other_alerts_is_that_one_slot() -> None:
    report, at = _open(ProgramAct.UPLOAD, 0)
    page = shift_page((), ((report, at),))
    assert len(page) == 1
    assert page[0].report is report


def test_nine_unbooked_transfers_keep_eight() -> None:
    acts = list(ProgramAct)
    pairs = [_open(acts[index % 3], index) for index in range(9)]
    page = shift_page((), pairs)
    assert len(page) == 8
    kept_at = [slot.at for slot in page]
    assert pairs[-1][1] not in kept_at


def test_the_lowest_other_score_is_what_leaves() -> None:
    others = _others([5, 1, 4, 3, 8, 7, 6, 2])
    report, at = _open(ProgramAct.ONLINE_EDIT, 30)
    page = shift_page(others, ((report, at),))
    other_keys = [slot.other.key for slot in page if slot.other is not None]
    assert "o1" not in other_keys
    assert any(slot.report is report for slot in page)
    assert len(page) == 8


def test_a_tag_only_work_order_still_holds_a_slot_inside_eight() -> None:
    order = TransferWorkOrder(start=START, end=END, tag="tank_level_max")
    report = transfer_report(ProgramAct.DOWNLOAD, (), (order,), at=WHEN)
    page = shift_page(_others([8, 7, 6, 5, 4, 3, 2, 1]), ((report, WHEN),))
    assert len(page) == 8
    assert any(slot.report is report and slot.report.instruction == "Go and look." for slot in page)


def test_the_next_observation_names_the_booking_and_does_not_pick() -> None:
    report = transfer_report(ProgramAct.DOWNLOAD, (), (), at=WHEN)
    assert report.next_observation == NEXT_OBSERVATION
    assert report.next_observation == "A booking that names this act and covers this hour."
    assert "%" not in report.next_observation
    booking = Booking(kind=BookingKind.CHECK_IN, act=ProgramAct.DOWNLOAD, start=START, end=END)
    covered = transfer_report(ProgramAct.DOWNLOAD, (booking,), (), at=WHEN)
    assert covered.alert is False
    assert covered.next_observation is None
    assert covered.lead is None
    assert covered.tied_lead_ids == STORIES


def test_shift_page_does_not_call_budget_alerts(monkeypatch: pytest.MonkeyPatch) -> None:
    import phos.atlas.consistency as consistency
    import phos.atlas.program_transfer as program_transfer

    def trap(*_args: object, **_kwargs: object) -> tuple[list[int], list[int], list[float]]:
        raise AssertionError("budget_alerts was called")

    monkeypatch.setattr(consistency, "budget_alerts", trap)
    assert not hasattr(program_transfer, "budget_alerts")
    report, at = _open(ProgramAct.DOWNLOAD, 1)
    shift_page(_others([3, 2, 1]), ((report, at),))

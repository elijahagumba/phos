"""Only a broken declared law takes a slot. Held and unstated take none.

A slot enters only as a LawBreak. A subclass that adds a magnitude is refused.
Every sentence names its law. A score-word is refused.
"""

from __future__ import annotations

import dataclasses
import inspect
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from phos.atlas.consistency_windows import EVENT_WINDOW
from phos.atlas.declared_law import (
    ALLOWED_WRITER,
    CONTROLLER_VALVE,
    JOINT_MOVE,
    LAWS,
    OPERATOR_PAGE_CEILING,
    PROGRAM_TRANSFER,
    SUBFLOOR_WALK,
    ControllerSample,
    DeclaredLaw,
    LawBreak,
    LawOutcome,
    LawRegister,
    LawReport,
    Standing,
    WriterWrite,
    assess_plant,
    breaks_from_plant,
    cited_statement,
    law_page,
    page_from_report,
)
from phos.atlas.handoff_booking import TagBooking
from phos.atlas.joint_setpoint import SETPOINT_BAND, SetpointStep
from phos.atlas.program_transfer import Booking, BookingKind, ProgramAct, TransferWorkOrder
from phos.atlas.subfloor_walk import WALK_STEPS

WHEN = datetime(2026, 10, 23, 8, 0, tzinfo=UTC)
LOW, HIGH = SETPOINT_BAND
ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "src" / "phos" / "atlas" / "declared_law.py"
DECLARED = LawRegister(LAWS)


def _walk(tag: str, steps: int) -> tuple[SetpointStep, ...]:
    span = HIGH - LOW
    return tuple(
        SetpointStep(tag, WHEN + timedelta(seconds=index), LOW + span * index / WALK_STEPS)
        for index in range(steps)
    )


def _joint_and_walk() -> tuple[SetpointStep, ...]:
    """A 720-step walk plus one other in-band tag inside the joint window."""
    other = SetpointStep("bottle_level_max", WHEN + timedelta(seconds=10), HIGH)
    return (*_walk("tank_level_max", WALK_STEPS), other)


def test_one_in_band_setpoint_write_produces_no_break() -> None:
    step = SetpointStep("tank_level_max", WHEN, 7.0)
    assert breaks_from_plant((step,), register=DECLARED) == ()


def test_two_in_band_tags_inside_the_window_are_one_joint_break_without_a_score() -> None:
    steps = (
        SetpointStep("tank_level_max", WHEN, 6.5),
        SetpointStep("bottle_level_max", WHEN + timedelta(seconds=10), 7.5),
    )
    found = breaks_from_plant(steps, register=DECLARED)
    assert len(found) == 1
    item = found[0]
    assert item.name == "joint_move" == JOINT_MOVE.name
    assert item.time == steps[0].at
    assert item.statement == (
        "joint_move. Tags bottle_level_max and tank_level_max were written inside "
        "the ordinary band and joined on the frozen event window."
    )
    assert tuple(LawBreak.__dataclass_fields__) == ("name", "time", "statement")
    assert "score" not in item.__dict__
    assert not hasattr(item, "score")
    assert law_page(found, register=DECLARED) == found


def test_719_steps_are_silence_and_720_steps_are_one_walk_break() -> None:
    assert WALK_STEPS == 720
    assert breaks_from_plant(_walk("tank_level_max", WALK_STEPS - 1), register=DECLARED) == ()
    steps = _walk("tank_level_max", WALK_STEPS)
    found = breaks_from_plant(steps, register=DECLARED)
    assert len(found) == 1
    assert found[0].name == "subfloor_walk"
    assert found[0].time == steps[0].at
    assert found[0].statement == (
        "subfloor_walk. Tag tank_level_max was walked across the ordinary band "
        "for the frozen walk length."
    )
    assert "score" not in found[0].__dict__


def test_an_unbooked_transfer_is_one_break_and_a_covering_booking_is_silence() -> None:
    open_page = breaks_from_plant(
        transfers=((ProgramAct.DOWNLOAD, WHEN),),
        register=DECLARED,
    )
    assert len(open_page) == 1
    assert open_page[0].name == "program_transfer"
    assert open_page[0].time == WHEN
    assert open_page[0].statement == (
        "program_transfer. An unbooked download was supplied, and no booking covers that act."
    )
    booking = Booking(
        kind=BookingKind.DOWNTIME,
        act=ProgramAct.DOWNLOAD,
        start=WHEN - timedelta(hours=1),
        end=WHEN + timedelta(hours=1),
    )
    covered = breaks_from_plant(
        transfers=((ProgramAct.DOWNLOAD, WHEN),),
        register=DECLARED,
        bookings=(booking,),
    )
    assert covered == ()
    covered_report = assess_plant(
        transfers=((ProgramAct.DOWNLOAD, WHEN),),
        register=DECLARED,
        bookings=(booking,),
    )
    assert covered_report.broken == ()
    assert covered_report.held == (
        LawOutcome(
            "program_transfer",
            Standing.HELD,
            "program_transfer. Program transfers were supplied, "
            "and a booking or a work order covers each act.",
        ),
    )
    assert covered_report.held[0].time is None
    order = TransferWorkOrder(
        WHEN - timedelta(hours=1),
        WHEN + timedelta(hours=1),
        ProgramAct.DOWNLOAD,
    )
    ordered = assess_plant(
        transfers=((ProgramAct.DOWNLOAD, WHEN),),
        register=LawRegister((PROGRAM_TRANSFER,)),
        work_orders=(order,),
    )
    assert ordered.broken == ()
    assert ordered.unstated == ()
    assert ordered.held[0].name == "program_transfer"
    assert ordered.held[0].standing is Standing.HELD
    assert ordered.held[0].time is None


def test_a_handoff_with_a_booking_that_names_both_tags_produces_none() -> None:
    steps = (
        SetpointStep("tank_level_max", WHEN, 7.0),
        SetpointStep("bottle_level_max", WHEN + timedelta(seconds=EVENT_WINDOW + 1), 7.0),
    )
    open_page = breaks_from_plant(steps, register=DECLARED)
    assert len(open_page) == 1
    assert open_page[0].name == "band_handoff"
    assert open_page[0].time == steps[0].at
    assert open_page[0].statement.startswith("band_handoff. ")
    assert "tank_level_max" in open_page[0].statement
    assert "bottle_level_max" in open_page[0].statement
    booking = TagBooking(
        ("bottle_level_max", "tank_level_max"),
        WHEN - timedelta(minutes=5),
        WHEN + timedelta(hours=1),
    )
    assert breaks_from_plant(steps, register=DECLARED, tag_bookings=(booking,)) == ()
    covered_report = assess_plant(steps, register=DECLARED, tag_bookings=(booking,))
    assert covered_report.broken == ()
    handoff = next(item for item in covered_report.held if item.name == "band_handoff")
    assert handoff.standing is Standing.HELD
    assert handoff.time is None
    assert handoff.statement == (
        "band_handoff. Setpoint steps were supplied, and they are not an open handoff."
    )


def test_nine_breaks_keep_the_earliest_eight_and_leave_off_the_later_loud_one() -> None:
    early = tuple(
        LawBreak(
            "joint_move",
            WHEN + timedelta(minutes=index),
            f"joint_move. Broken fact {index}.",
        )
        for index in range(8)
    )
    loud = LawBreak(
        "subfloor_walk",
        WHEN + timedelta(hours=5),
        "subfloor_walk. Residual magnitude would have ranked this later break first.",
    )
    page = law_page((loud, *reversed(early)), register=DECLARED)
    assert len(page) == 8 == OPERATOR_PAGE_CEILING
    assert page == early
    assert loud not in page
    assert page[-1].time < loud.time


def test_an_empty_inlet_is_an_empty_page() -> None:
    assert breaks_from_plant(register=DECLARED) == ()
    assert law_page((), register=DECLARED) == ()


def test_a_naive_time_raises() -> None:
    naive = datetime(2026, 10, 23, 8, 0)
    with pytest.raises(ValueError, match="timezone-aware"):
        law_page((LawBreak("joint_move", naive, "joint_move. A fact."),), register=DECLARED)
    with pytest.raises(ValueError, match="timezone-aware"):
        breaks_from_plant((SetpointStep("tank_level_max", naive, 7.0),), register=DECLARED)
    with pytest.raises(ValueError, match="timezone-aware"):
        breaks_from_plant(transfers=((ProgramAct.UPLOAD, naive),), register=DECLARED)
    with pytest.raises(ValueError, match="timezone-aware"):
        breaks_from_plant(
            register=DECLARED,
            writes=(WriterWrite("console", naive),),
            allowed_stations=frozenset({"console"}),
        )


def test_the_module_does_not_import_the_residual_detector() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    assert "phos.atlas.consistency" not in source
    assert "budget_alerts" not in source
    assert "feature_scores" not in source


def test_a_break_has_name_time_and_statement_and_no_confidence() -> None:
    assert tuple(LawBreak.__dataclass_fields__) == ("name", "time", "statement")
    item = LawBreak("joint_move", WHEN, "Tags a and b moved together.")
    assert set(item.__dict__) == {"name", "time", "statement"}
    for banned in ("confidence", "probability", "weight", "magnitude", "score"):
        assert banned not in LawBreak.__dataclass_fields__
        assert banned not in LawRegister.__dataclass_fields__


def test_a_declared_law_is_a_name_and_a_statement_with_no_threshold() -> None:
    assert tuple(DeclaredLaw.__dataclass_fields__) == ("name", "statement")
    assert tuple(LawRegister.__dataclass_fields__) == ("laws",)
    assert tuple(law.name for law in LAWS) == (
        "joint_move",
        "subfloor_walk",
        "band_handoff",
        "program_transfer",
        "allowed_writer",
        "controller_valve",
    )
    for law in LAWS:
        assert not any(character.isdigit() for character in law.statement)


def test_the_same_time_orders_by_law_name() -> None:
    handoff = LawBreak("band_handoff", WHEN, "band_handoff. A handoff.")
    walk = LawBreak("subfloor_walk", WHEN, "subfloor_walk. A walk.")
    assert law_page((walk, handoff), register=DECLARED) == (handoff, walk)


def test_fewer_than_eight_is_a_complete_page() -> None:
    breaks = tuple(
        LawBreak("joint_move", WHEN + timedelta(minutes=index), f"joint_move. Fact {index}.")
        for index in range(3)
    )
    assert law_page(breaks, register=DECLARED) == breaks
    page_signature = inspect.signature(law_page)
    plant_signature = inspect.signature(breaks_from_plant)
    report_signature = inspect.signature(page_from_report)
    assessment_signature = inspect.signature(assess_plant)
    assert "limit" not in page_signature.parameters
    assert "limit" not in report_signature.parameters
    assert list(assessment_signature.parameters) == list(plant_signature.parameters)
    for name in assessment_signature.parameters:
        left = assessment_signature.parameters[name]
        right = plant_signature.parameters[name]
        assert left.kind is right.kind
        assert left.default == right.default
    for signature in (page_signature, plant_signature, report_signature, assessment_signature):
        parameter = signature.parameters["register"]
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
        assert parameter.default is inspect.Parameter.empty


def test_an_empty_register_is_silence_when_the_steps_would_have_matched() -> None:
    steps = _joint_and_walk()
    transfers = ((ProgramAct.DOWNLOAD, WHEN),)
    matched = breaks_from_plant(steps, transfers, register=DECLARED)
    assert {item.name for item in matched} == {
        "joint_move",
        "program_transfer",
        "subfloor_walk",
    }
    quiet = assess_plant(steps, transfers, register=LawRegister(()))
    assert quiet.held == ()
    assert quiet.broken == ()
    assert quiet.unstated == ()
    assert breaks_from_plant(steps, transfers, register=LawRegister(())) == quiet.broken
    assert law_page((), register=LawRegister(())) == ()
    assert page_from_report(quiet, register=LawRegister(())) == ()


def test_only_a_declared_joint_move_breaks_and_the_walk_on_the_same_steps_does_not() -> None:
    steps = _joint_and_walk()
    found = breaks_from_plant(steps, register=LawRegister((JOINT_MOVE,)))
    assert tuple(item.name for item in found) == ("joint_move",)
    assert found[0].time == WHEN
    assert "subfloor_walk" not in {item.name for item in found}


def test_law_page_raises_when_a_break_name_is_not_in_the_register() -> None:
    declared = LawBreak("joint_move", WHEN, "joint_move. A joint the plant declared.")
    stranger = LawBreak(
        "subfloor_walk",
        WHEN + timedelta(minutes=1),
        "subfloor_walk. A walk the plant did not declare.",
    )
    with pytest.raises(ValueError, match="subfloor_walk is not in the register"):
        law_page((declared, stranger), register=LawRegister((JOINT_MOVE,)))
    with pytest.raises(ValueError, match="joint_move is not in the register"):
        law_page((declared,), register=LawRegister(()))
    invented = LawBreak("not_a_law", WHEN, "not_a_law. A name with no predicate.")
    with pytest.raises(ValueError, match="not_a_law is not in the register"):
        law_page((invented,), register=DECLARED)
    stranger_report = LawReport(held=(), broken=(stranger,), unstated=())
    with pytest.raises(ValueError, match="subfloor_walk is not in the register"):
        page_from_report(stranger_report, register=LawRegister((JOINT_MOVE,)))


def test_a_register_refuses_a_duplicated_law_name() -> None:
    with pytest.raises(ValueError, match="duplicate law name: joint_move"):
        LawRegister((JOINT_MOVE, JOINT_MOVE))
    twin = DeclaredLaw("joint_move", "The same name in other words, with no threshold.")
    with pytest.raises(ValueError, match="duplicate law name: joint_move"):
        LawRegister((JOINT_MOVE, twin))


def test_a_full_register_keeps_the_earliest_eight_of_nine_by_time() -> None:
    names = ("joint_move", "subfloor_walk", "band_handoff", "program_transfer")
    early = tuple(
        LawBreak(
            names[index % 4],
            WHEN + timedelta(minutes=index),
            f"{names[index % 4]}. Broken fact {index}.",
        )
        for index in range(8)
    )
    loud = LawBreak(
        "program_transfer",
        WHEN + timedelta(hours=5),
        "program_transfer. Residual magnitude would have ranked this later break first.",
    )
    page = law_page((loud, *reversed(early)), register=LawRegister(LAWS))
    assert tuple(law.name for law in LAWS) == (*names, "allowed_writer", "controller_valve")
    assert len(page) == 8 == OPERATOR_PAGE_CEILING
    assert page == early
    assert loud not in page
    assert page[-1].time < loud.time
    assert all(item.name in names for item in page)


def test_declared_joint_move_with_empty_steps_is_unstated_and_takes_no_slot() -> None:
    register = LawRegister((JOINT_MOVE,))
    report = assess_plant(register=register)
    assert report.held == ()
    assert report.broken == ()
    assert report.unstated == (
        LawOutcome(
            "joint_move",
            Standing.UNSTATED,
            "joint_move. No setpoint steps were supplied, so joint_move was not checked.",
        ),
    )
    assert report.unstated[0].time is None
    assert page_from_report(report, register=register) == ()
    assert breaks_from_plant(register=register) == report.broken


def test_declared_joint_move_with_one_in_band_write_is_held_and_takes_no_slot() -> None:
    register = LawRegister((JOINT_MOVE,))
    step = SetpointStep("tank_level_max", WHEN, 7.0)
    report = assess_plant((step,), register=register)
    assert report.broken == ()
    assert report.unstated == ()
    assert report.held == (
        LawOutcome(
            "joint_move",
            Standing.HELD,
            "joint_move. Setpoint steps were supplied, and they are not a joint move.",
        ),
    )
    assert report.held[0].time is None
    assert len(page_from_report(report, register=register)) == 0


def test_declared_joint_move_with_two_in_band_tags_is_broken_and_takes_one_slot() -> None:
    register = LawRegister((JOINT_MOVE,))
    steps = (
        SetpointStep("tank_level_max", WHEN, 6.5),
        SetpointStep("bottle_level_max", WHEN + timedelta(seconds=10), 7.5),
    )
    report = assess_plant(steps, register=register)
    assert report.held == ()
    assert report.unstated == ()
    assert len(report.broken) == 1
    assert report.broken[0].name == "joint_move"
    assert report.broken[0].time == steps[0].at
    page = page_from_report(report, register=register)
    assert len(page) == 1
    assert page == report.broken
    assert breaks_from_plant(steps, register=register) == report.broken
    assert law_page(report.broken, register=register) == page


def test_a_719_step_chain_is_held_and_a_720_step_chain_is_broken() -> None:
    assert WALK_STEPS == 720
    register = LawRegister((SUBFLOOR_WALK,))
    short = assess_plant(_walk("tank_level_max", 719), register=register)
    assert short.broken == ()
    assert short.unstated == ()
    assert short.held == (
        LawOutcome(
            "subfloor_walk",
            Standing.HELD,
            "subfloor_walk. Setpoint steps were supplied, "
            "and they are not a walk of the frozen length.",
        ),
    )
    assert short.held[0].standing is not Standing.UNSTATED
    assert short.held[0].time is None
    assert len(page_from_report(short, register=register)) == 0
    full = assess_plant(_walk("tank_level_max", WALK_STEPS), register=register)
    assert full.held == ()
    assert full.unstated == ()
    assert len(full.broken) == 1
    assert full.broken[0].name == "subfloor_walk"
    assert len(page_from_report(full, register=register)) == 1


def test_one_broken_joint_one_held_walk_and_one_unstated_transfer_fill_one_slot() -> None:
    register = LawRegister((JOINT_MOVE, SUBFLOOR_WALK, PROGRAM_TRANSFER))
    steps = (
        SetpointStep("tank_level_max", WHEN, 6.5),
        SetpointStep("bottle_level_max", WHEN + timedelta(seconds=10), 7.5),
    )
    report = assess_plant(steps, register=register)
    assert tuple(item.name for item in report.broken) == ("joint_move",)
    assert tuple((item.name, item.standing, item.time) for item in report.held) == (
        ("subfloor_walk", Standing.HELD, None),
    )
    assert tuple((item.name, item.standing, item.time) for item in report.unstated) == (
        ("program_transfer", Standing.UNSTATED, None),
    )
    names = {item.name for item in report.held}
    names.update(item.name for item in report.broken)
    names.update(item.name for item in report.unstated)
    assert "band_handoff" not in names
    page = page_from_report(report, register=register)
    assert len(page) == 1
    assert tuple(item.name for item in page) == ("joint_move",)
    assert page == report.broken


def test_nine_broken_laws_keep_the_earliest_eight_and_held_outcomes_take_no_slot() -> None:
    transfers = tuple((ProgramAct.DOWNLOAD, WHEN + timedelta(minutes=index)) for index in range(9))
    report = assess_plant(
        (SetpointStep("tank_level_max", WHEN, 7.0),),
        transfers,
        register=DECLARED,
    )
    assert len(report.broken) == 9
    assert {item.name for item in report.broken} == {"program_transfer"}
    assert tuple(item.name for item in report.held) == (
        "band_handoff",
        "joint_move",
        "subfloor_walk",
    )
    assert all(item.standing is Standing.HELD and item.time is None for item in report.held)
    assert report.unstated == (
        LawOutcome(
            "allowed_writer",
            Standing.UNSTATED,
            "allowed_writer. The allowed set is empty, so allowed_writer was not stated.",
        ),
        LawOutcome(
            "controller_valve",
            Standing.UNSTATED,
            "controller_valve. No controller sample was supplied, "
            "so controller_valve was not checked.",
        ),
    )
    assert report.unstated[0].time is None
    assert report.unstated[1].time is None
    page = page_from_report(report, register=DECLARED)
    assert len(page) == 8 == OPERATOR_PAGE_CEILING
    assert page == report.broken[:8]
    assert report.broken[8] not in page
    assert page[-1].time < report.broken[8].time
    assert {item.name for item in report.held}.isdisjoint({item.name for item in page})
    assert {item.name for item in report.unstated}.isdisjoint({item.name for item in page})


def test_a_law_absent_from_the_register_is_on_none_of_the_three_lists() -> None:
    register = LawRegister((JOINT_MOVE,))
    report = assess_plant(
        _joint_and_walk(),
        ((ProgramAct.DOWNLOAD, WHEN),),
        register=register,
    )
    names = {item.name for item in report.held}
    names.update(item.name for item in report.broken)
    names.update(item.name for item in report.unstated)
    assert names == {"joint_move"}
    assert report.held == ()
    assert report.unstated == ()
    assert tuple(item.name for item in report.broken) == ("joint_move",)
    for absent in ("subfloor_walk", "band_handoff", "program_transfer"):
        assert absent not in names
    page = page_from_report(report, register=register)
    assert tuple(item.name for item in page) == ("joint_move",)


def test_an_outcome_has_no_score_and_the_module_still_skips_the_residual_detector() -> None:
    assert tuple(LawOutcome.__dataclass_fields__) == ("name", "standing", "statement", "time")
    assert tuple(LawReport.__dataclass_fields__) == ("held", "broken", "unstated")
    assert LawOutcome.__dataclass_fields__["time"].default is None
    for banned in ("confidence", "score", "weight", "magnitude", "probability"):
        assert banned not in LawOutcome.__dataclass_fields__
        assert banned not in LawReport.__dataclass_fields__
        assert banned not in Standing.__members__
    assert [item.value for item in Standing] == ["held", "broken", "unstated"]
    for item in Standing:
        assert type(item.value) is str
        assert not item.value.isdigit()
    source = SOURCE.read_text(encoding="utf-8")
    assert "phos.atlas.consistency" not in source
    assert "budget_alerts" not in source
    assert "feature_scores" not in source
    with pytest.raises(ValueError, match="no time"):
        LawOutcome("joint_move", Standing.HELD, "Setpoint steps were supplied.", WHEN)
    with pytest.raises(ValueError, match="no time"):
        LawOutcome("joint_move", Standing.UNSTATED, "No setpoint steps were supplied.", WHEN)
    with pytest.raises(ValueError, match="names its time"):
        LawOutcome("joint_move", Standing.BROKEN, "Two tags moved.")
    with pytest.raises(ValueError, match="two standings"):
        LawReport(
            held=(LawOutcome("joint_move", Standing.HELD, "Setpoint steps were supplied."),),
            broken=(LawBreak("joint_move", WHEN, "Two tags moved."),),
            unstated=(),
        )


def _names(report: LawReport) -> set[str]:
    found = {item.name for item in report.held}
    found.update(item.name for item in report.broken)
    found.update(item.name for item in report.unstated)
    return found


def test_an_undeclared_outside_write_is_on_none_of_the_three_lists() -> None:
    register = LawRegister((JOINT_MOVE,))
    report = assess_plant(
        register=register,
        writes=(WriterWrite("workshop", WHEN),),
        allowed_stations=frozenset({"console"}),
    )
    assert "allowed_writer" not in _names(report)
    assert report.broken == ()
    assert len(page_from_report(report, register=register)) == 0
    assert (
        breaks_from_plant(
            register=register,
            writes=(WriterWrite("workshop", WHEN),),
            allowed_stations=frozenset({"console"}),
        )
        == ()
    )


def test_an_empty_allowed_set_is_unstated_when_a_write_is_present() -> None:
    register = LawRegister((ALLOWED_WRITER,))
    report = assess_plant(
        register=register,
        writes=(WriterWrite("workshop", WHEN),),
        allowed_stations=frozenset(),
    )
    assert report.held == ()
    assert report.broken == ()
    assert report.unstated == (
        LawOutcome(
            "allowed_writer",
            Standing.UNSTATED,
            "allowed_writer. The allowed set is empty, so allowed_writer was not stated.",
        ),
    )
    assert report.unstated[0].time is None
    assert len(page_from_report(report, register=register)) == 0


def test_a_declared_allowed_writer_with_no_writes_is_unstated() -> None:
    register = LawRegister((ALLOWED_WRITER,))
    report = assess_plant(
        register=register,
        writes=(),
        allowed_stations=frozenset({"console"}),
    )
    assert report.held == ()
    assert report.broken == ()
    assert report.unstated == (
        LawOutcome(
            "allowed_writer",
            Standing.UNSTATED,
            "allowed_writer. No writes were supplied, so allowed_writer was not checked.",
        ),
    )
    assert len(page_from_report(report, register=register)) == 0


def test_a_station_inside_the_allowed_set_is_held_and_takes_no_slot() -> None:
    register = LawRegister((ALLOWED_WRITER,))
    report = assess_plant(
        register=register,
        writes=(WriterWrite("console", WHEN),),
        allowed_stations=frozenset({"console"}),
    )
    assert report.broken == ()
    assert report.unstated == ()
    assert report.held == (
        LawOutcome(
            "allowed_writer",
            Standing.HELD,
            "allowed_writer. Writes were supplied, and every station is inside the declared set.",
        ),
    )
    assert report.held[0].time is None
    assert len(page_from_report(report, register=register)) == 0
    joint = LawRegister((JOINT_MOVE, ALLOWED_WRITER))
    steps = (
        SetpointStep("tank_level_max", WHEN, 6.5),
        SetpointStep("bottle_level_max", WHEN + timedelta(seconds=10), 7.5),
    )
    beside = assess_plant(
        steps,
        register=joint,
        writes=(WriterWrite("console", WHEN),),
        allowed_stations=frozenset({"console"}),
    )
    assert tuple(item.name for item in beside.broken) == ("joint_move",)
    assert tuple((item.name, item.standing) for item in beside.held) == (
        ("allowed_writer", Standing.HELD),
    )
    assert "allowed_writer" not in {item.name for item in beside.broken}
    assert len(page_from_report(beside, register=joint)) == 1


def test_a_station_outside_the_allowed_set_is_one_break_per_write() -> None:
    register = LawRegister((ALLOWED_WRITER,))
    outside = WriterWrite("workshop", WHEN)
    alone = assess_plant(
        register=register,
        writes=(outside,),
        allowed_stations=frozenset({"console"}),
    )
    assert alone.held == ()
    assert alone.unstated == ()
    assert len(alone.broken) == 1
    assert alone.broken[0].name == "allowed_writer"
    assert alone.broken[0].time == outside.at
    assert alone.broken[0].statement == (
        "allowed_writer. Station workshop wrote, and it is outside the declared set."
    )
    page = page_from_report(alone, register=register)
    assert len(page) == 1
    assert page == alone.broken
    assert (
        breaks_from_plant(
            register=register,
            writes=(outside,),
            allowed_stations=frozenset({"console"}),
        )
        == alone.broken
    )
    later = WriterWrite("yard", WHEN + timedelta(minutes=2))
    inside = WriterWrite("console", WHEN + timedelta(minutes=1))
    mixed = assess_plant(
        register=register,
        writes=(outside, inside, later),
        allowed_stations=frozenset({"console"}),
    )
    assert mixed.held == ()
    assert mixed.unstated == ()
    assert len(mixed.broken) == 2
    assert tuple(item.time for item in mixed.broken) == (outside.at, later.at)
    assert mixed.broken[0].statement == (
        "allowed_writer. Station workshop wrote, and it is outside the declared set."
    )
    assert mixed.broken[1].statement == (
        "allowed_writer. Station yard wrote, and it is outside the declared set."
    )
    assert all("console" not in item.statement for item in mixed.broken)
    assert len(page_from_report(mixed, register=register)) == 2


def test_nine_outside_writes_keep_the_earliest_eight() -> None:
    register = LawRegister((ALLOWED_WRITER,))
    writes = tuple(
        WriterWrite(f"outsider-{index}", WHEN + timedelta(minutes=index)) for index in range(9)
    )
    report = assess_plant(
        register=register,
        writes=writes,
        allowed_stations=frozenset({"console"}),
    )
    assert report.held == ()
    assert report.unstated == ()
    assert len(report.broken) == 9
    page = page_from_report(report, register=register)
    assert len(page) == 8 == OPERATOR_PAGE_CEILING
    assert page == report.broken[:8]
    assert report.broken[8] not in page
    assert page[-1].time < report.broken[8].time
    assert report.broken[8].statement == (
        "allowed_writer. Station outsider-8 wrote, and it is outside the declared set."
    )
    assert writes[8].at == report.broken[8].time


def test_writer_write_has_no_score_and_an_empty_station_is_refused() -> None:
    assert tuple(WriterWrite.__dataclass_fields__) == ("station", "at")
    assert ALLOWED_WRITER.name == "allowed_writer"
    assert tuple(DeclaredLaw.__dataclass_fields__) == ("name", "statement")
    for banned in ("confidence", "score", "weight", "magnitude", "probability"):
        assert banned not in WriterWrite.__dataclass_fields__
        assert banned not in DeclaredLaw.__dataclass_fields__
        assert banned not in LawBreak.__dataclass_fields__
    source = SOURCE.read_text(encoding="utf-8")
    assert "phos.atlas.consistency" not in source
    assert "budget_alerts" not in source
    assert "feature_scores" not in source
    assert "command_consistency" not in source
    with pytest.raises(ValueError, match="station is empty"):
        WriterWrite("", WHEN)
    signature = inspect.signature(assess_plant)
    for name in ("writes", "allowed_stations"):
        parameter = signature.parameters[name]
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert "function_code" not in signature.parameters


def _controller(
    *,
    level: float = 5.0,
    level_min: float = 2.0,
    level_max: float = 8.0,
    input_valve: float = 1.0,
    input_mode: float = 3.0,
    bottle_level: float = 1.0,
    bottle_max: float = 2.0,
    belt: float = 1.0,
    output_valve: float = 1.0,
    output_mode: float = 3.0,
    at: datetime = WHEN,
) -> ControllerSample:
    """One release-mode sample. Inside both bands unless a caller overrides a field."""
    return ControllerSample(
        at=at,
        level=level,
        level_min=level_min,
        level_max=level_max,
        input_valve=input_valve,
        input_mode=input_mode,
        bottle_level=bottle_level,
        bottle_max=bottle_max,
        belt=belt,
        output_valve=output_valve,
        output_mode=output_mode,
    )


def test_an_undeclared_controller_disagreement_is_on_none_of_the_three_lists() -> None:
    register = LawRegister((JOINT_MOVE,))
    sample = _controller(level=9.0, input_valve=1.0, bottle_level=3.0, output_valve=1.0)
    report = assess_plant(register=register, controller=sample)
    assert "controller_valve" not in _names(report)
    assert report.broken == ()
    assert report.held == ()
    assert tuple(item.name for item in report.unstated) == ("joint_move",)
    assert len(page_from_report(report, register=register)) == 0
    assert breaks_from_plant(register=register, controller=sample) == ()


def test_a_declared_controller_with_no_sample_is_unstated() -> None:
    register = LawRegister((CONTROLLER_VALVE,))
    report = assess_plant(register=register)
    assert report.held == ()
    assert report.broken == ()
    assert report.unstated == (
        LawOutcome(
            "controller_valve",
            Standing.UNSTATED,
            "controller_valve. No controller sample was supplied, "
            "so controller_valve was not checked.",
        ),
    )
    assert report.unstated[0].time is None
    assert len(page_from_report(report, register=register)) == 0
    steps = (
        SetpointStep("tank_level_max", WHEN, 6.5),
        SetpointStep("bottle_level_max", WHEN + timedelta(seconds=10), 7.5),
    )
    beside = assess_plant(steps, register=LawRegister((JOINT_MOVE, CONTROLLER_VALVE)))
    assert tuple(item.name for item in beside.broken) == ("joint_move",)
    assert tuple((item.name, item.standing) for item in beside.unstated) == (
        ("controller_valve", Standing.UNSTATED),
    )
    assert beside.held == ()
    assert len(page_from_report(beside, register=LawRegister((JOINT_MOVE, CONTROLLER_VALVE)))) == 1


def test_a_valve_mode_that_is_not_release_is_unstated() -> None:
    register = LawRegister((CONTROLLER_VALVE,))
    manual_input = _controller(
        level=9.0,
        input_valve=1.0,
        input_mode=1.0,
        bottle_level=3.0,
        output_valve=1.0,
        output_mode=3.0,
    )
    report = assess_plant(register=register, controller=manual_input)
    assert report.held == ()
    assert report.broken == ()
    assert report.unstated == (
        LawOutcome(
            "controller_valve",
            Standing.UNSTATED,
            "controller_valve. A valve mode is not release, so controller_valve was not stated.",
        ),
    )
    assert report.unstated[0].time is None
    assert len(page_from_report(report, register=register)) == 0
    manual_output = _controller(
        level=9.0,
        input_valve=1.0,
        input_mode=3.0,
        output_mode=1.0,
        output_valve=1.0,
        bottle_level=3.0,
    )
    other = assess_plant(register=register, controller=manual_output)
    assert other.broken == ()
    assert other.held == ()
    assert other.unstated[0].standing is Standing.UNSTATED
    assert len(page_from_report(other, register=register)) == 0


def test_both_modes_release_and_agreement_outside_the_band_is_held() -> None:
    register = LawRegister((CONTROLLER_VALVE,))
    sample = _controller(level=9.0, input_valve=0.0, bottle_level=1.0, belt=1.0, output_valve=1.0)
    report = assess_plant(register=register, controller=sample)
    assert report.broken == ()
    assert report.unstated == ()
    assert report.held == (
        LawOutcome(
            "controller_valve",
            Standing.HELD,
            "controller_valve. A controller sample was supplied, both modes are release, "
            "and neither side disagrees.",
        ),
    )
    assert report.held[0].time is None
    assert len(page_from_report(report, register=register)) == 0
    assert breaks_from_plant(register=register, controller=sample) == ()


def test_an_input_valve_outside_the_band_is_one_break() -> None:
    register = LawRegister((CONTROLLER_VALVE,))
    above = _controller(level=9.0, input_valve=1.0, bottle_level=1.0, belt=0.0, output_valve=1.0)
    report = assess_plant(register=register, controller=above)
    assert report.held == ()
    assert report.unstated == ()
    assert len(report.broken) == 1
    assert report.broken[0].name == "controller_valve"
    assert report.broken[0].time == above.at
    assert report.broken[0].statement == (
        "controller_valve. The input valve is 1, and the rule required 0."
    )
    page = page_from_report(report, register=register)
    assert len(page) == 1
    assert page == report.broken
    below = _controller(level=1.0, input_valve=0.0, bottle_level=1.0, belt=0.0, output_valve=1.0)
    low = assess_plant(register=register, controller=below)
    assert len(low.broken) == 1
    assert low.broken[0].statement == (
        "controller_valve. The input valve is 0, and the rule required 1."
    )
    assert low.held == ()
    at_max = _controller(level=8.0, input_valve=1.0, bottle_level=1.0, belt=0.0, output_valve=1.0)
    edge = assess_plant(register=register, controller=at_max)
    assert edge.broken == ()
    assert edge.held[0].standing is Standing.HELD
    at_min = _controller(level=2.0, input_valve=0.0, bottle_level=1.0, belt=0.0, output_valve=1.0)
    floor = assess_plant(register=register, controller=at_min)
    assert floor.broken == ()
    assert floor.held[0].standing is Standing.HELD
    only_output = _controller(
        level=8.0,
        input_valve=1.0,
        bottle_level=3.0,
        belt=0.0,
        output_valve=1.0,
    )
    output_only = assess_plant(register=register, controller=only_output)
    assert len(output_only.broken) == 1
    assert "input valve" not in output_only.broken[0].statement
    assert "output valve" in output_only.broken[0].statement


def test_an_output_valve_that_disagrees_is_one_break() -> None:
    register = LawRegister((CONTROLLER_VALVE,))
    full_bottle = _controller(bottle_level=3.0, belt=0.0, output_valve=1.0)
    report = assess_plant(register=register, controller=full_bottle)
    assert report.held == ()
    assert len(report.broken) == 1
    assert report.broken[0].statement == (
        "controller_valve. The output valve is 1, and the rule required 0."
    )
    assert "output valve" in report.broken[0].statement
    assert len(page_from_report(report, register=register)) == 1
    past_filler = _controller(bottle_level=1.0, belt=1.1, output_valve=1.0)
    belt = assess_plant(register=register, controller=past_filler)
    assert len(belt.broken) == 1
    assert belt.broken[0].statement == (
        "controller_valve. The output valve is 1, and the rule required 0."
    )
    assert belt.held == ()
    at_both_ends = _controller(bottle_level=2.0, belt=1.0, output_valve=1.0)
    ends = assess_plant(register=register, controller=at_both_ends)
    assert ends.broken == ()
    assert ends.held[0].standing is Standing.HELD
    bottle_end = _controller(bottle_level=2.0, belt=0.0, output_valve=1.0)
    assert assess_plant(register=register, controller=bottle_end).broken == ()
    belt_end = _controller(bottle_level=1.0, belt=1.0, output_valve=1.0)
    assert assess_plant(register=register, controller=belt_end).broken == ()
    closed_at_the_end = _controller(bottle_level=2.0, belt=1.0, output_valve=0.0)
    closed = assess_plant(register=register, controller=closed_at_the_end)
    assert len(closed.broken) == 1
    assert closed.broken[0].statement == (
        "controller_valve. The output valve is 0, and the rule required 1."
    )


def test_both_sides_disagree_are_two_breaks_and_the_page_holds_both() -> None:
    register = LawRegister((CONTROLLER_VALVE,))
    sample = _controller(level=9.0, input_valve=1.0, bottle_level=3.0, belt=0.0, output_valve=1.0)
    report = assess_plant(register=register, controller=sample)
    assert report.held == ()
    assert report.unstated == ()
    assert len(report.broken) == 2
    assert report.broken[0].statement == (
        "controller_valve. The input valve is 1, and the rule required 0."
    )
    assert report.broken[1].statement == (
        "controller_valve. The output valve is 1, and the rule required 0."
    )
    assert report.broken[0].time == sample.at == report.broken[1].time
    assert report.broken[0].name == report.broken[1].name == "controller_valve"
    page = page_from_report(report, register=register)
    assert len(page) == 2
    assert len(page) < OPERATOR_PAGE_CEILING
    assert page == report.broken
    assert breaks_from_plant(register=register, controller=sample) == report.broken
    assert "score" not in page[0].__dict__
    assert "score" not in page[1].__dict__
    assert tuple(ControllerSample.__dataclass_fields__) == (
        "at",
        "level",
        "level_min",
        "level_max",
        "input_valve",
        "input_mode",
        "bottle_level",
        "bottle_max",
        "belt",
        "output_valve",
        "output_mode",
    )
    for banned in ("confidence", "score", "weight", "magnitude", "probability"):
        assert banned not in ControllerSample.__dataclass_fields__
        assert banned not in page[0].__dict__
    assert CONTROLLER_VALVE.name == "controller_valve"
    parameter = inspect.signature(assess_plant).parameters["controller"]
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert parameter.default is None


def test_a_naive_controller_time_raises() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        _controller(at=datetime(2026, 10, 23, 8, 0))


def test_the_module_does_not_import_consistency_or_the_walk_column() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    assert "@dataclass(frozen=True)\nclass ControllerSample:" in source
    for banned in (
        "phos.atlas.consistency",
        "walk_consistency",
        "budget_alerts",
        "feature_scores",
        "command_consistency",
    ):
        assert banned not in source


def test_a_magnitude_subclass_is_refused_and_does_not_enter_the_page() -> None:
    @dataclasses.dataclass(frozen=True)
    class MagnitudeBreak(LawBreak):
        magnitude: float

    earliest = MagnitudeBreak(
        "joint_move",
        WHEN,
        "A magnitude would have been first if the type were ignored.",
        magnitude=9.0,
    )
    later = LawBreak(
        "subfloor_walk",
        WHEN + timedelta(minutes=1),
        "A genuine break that is not placed, because the call raises.",
    )
    assert earliest.name in {law.name for law in DECLARED.laws}
    assert earliest.time < later.time
    assert isinstance(earliest, LawBreak)
    assert type(earliest) is not LawBreak
    would_have_led = sorted((earliest, later), key=lambda item: (item.time, item.name))
    assert would_have_led[0] is earliest
    placed: tuple[LawBreak, ...] = ()
    with pytest.raises(ValueError, match="only a LawBreak enters the page"):
        placed = law_page((earliest, later), register=DECLARED)
    assert earliest not in placed
    assert placed == ()
    report = LawReport(held=(), broken=(earliest,), unstated=())
    with pytest.raises(ValueError, match="only a LawBreak enters the page"):
        page_from_report(report, register=DECLARED)


def test_law_break_fields_are_name_time_and_statement() -> None:
    break_names = [field.name for field in dataclasses.fields(LawBreak)]
    outcome_names = [field.name for field in dataclasses.fields(LawOutcome)]
    assert break_names == ["name", "time", "statement"]
    assert outcome_names == ["name", "standing", "statement", "time"]
    for banned in ("confidence", "score", "weight", "magnitude", "probability"):
        assert banned not in break_names
        assert banned not in outcome_names


def test_the_law_module_does_not_import_the_residual_or_other_page_builders() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    for banned in (
        "phos.atlas.consistency",
        "walk_consistency",
        "command_consistency",
        "drift_consistency",
        "bending_consistency",
        "breadth_consistency",
        "phos.atlas.queue",
        "phos.atlas.grouping",
        "shift_brief",
        "handoff_page",
        "leap_stack",
        "budget_alerts",
        "feature_scores",
    ):
        assert banned not in source


def test_a_genuine_law_break_whose_name_is_declared_still_enters() -> None:
    item = LawBreak("joint_move", WHEN, "joint_move. Tags a and b moved together.")
    assert type(item) is LawBreak
    assert item.name in {law.name for law in DECLARED.laws}
    assert item.statement.startswith("joint_move. ")
    page = law_page((item,), register=DECLARED)
    assert page == (item,)
    report = LawReport(held=(), broken=(item,), unstated=())
    assert page_from_report(report, register=DECLARED) == (item,)


def test_a_joint_break_starts_with_joint_move_and_names_both_tags() -> None:
    steps = (
        SetpointStep("tank_level_max", WHEN, 6.5),
        SetpointStep("bottle_level_max", WHEN + timedelta(seconds=10), 7.5),
    )
    found = breaks_from_plant(steps, register=LawRegister((JOINT_MOVE,)))
    assert len(found) == 1
    statement = found[0].statement
    assert statement.startswith("joint_move. ")
    assert "tank_level_max" in statement
    assert "bottle_level_max" in statement


def test_writer_and_controller_breaks_name_the_station_and_the_valve() -> None:
    writer = assess_plant(
        register=LawRegister((ALLOWED_WRITER,)),
        writes=(WriterWrite("workshop", WHEN),),
        allowed_stations=frozenset({"console"}),
    )
    assert len(writer.broken) == 1
    assert writer.broken[0].statement.startswith("allowed_writer. ")
    assert "workshop" in writer.broken[0].statement
    valve = assess_plant(
        register=LawRegister((CONTROLLER_VALVE,)),
        controller=_controller(
            level=9.0,
            input_valve=1.0,
            bottle_level=1.0,
            belt=0.0,
            output_valve=1.0,
        ),
    )
    assert len(valve.broken) == 1
    assert valve.broken[0].statement.startswith("controller_valve. ")
    assert "input valve" in valve.broken[0].statement


def test_a_held_outcome_and_an_unstated_outcome_each_start_with_their_law_name() -> None:
    held = assess_plant(
        (SetpointStep("tank_level_max", WHEN, 7.0),),
        register=LawRegister((SUBFLOOR_WALK,)),
    )
    assert len(held.held) == 1
    assert held.held[0].standing is Standing.HELD
    assert held.held[0].statement.startswith("subfloor_walk. ")
    unstated = assess_plant(register=LawRegister((PROGRAM_TRANSFER,)))
    assert len(unstated.unstated) == 1
    assert unstated.unstated[0].standing is Standing.UNSTATED
    assert unstated.unstated[0].statement.startswith("program_transfer. ")


def test_cited_statement_refuses_confidence_and_magnitude_and_returns_no_sentence() -> None:
    for word in (
        "confidence",
        "CONFIDENCE",
        "probability",
        "weight",
        "magnitude",
        "Magnitude",
        "score",
    ):
        refused: str | None = None
        fact = f"The {word} is not a fact."
        with pytest.raises(ValueError, match=word.casefold()) as caught:
            refused = cited_statement(JOINT_MOVE, fact)
        assert refused is None
        assert f"joint_move. {fact}" not in str(caught.value)
    blank: str | None = None
    with pytest.raises(ValueError, match="not empty"):
        blank = cited_statement(JOINT_MOVE, "   ")
    assert blank is None
    allowed = cited_statement(
        CONTROLLER_VALVE,
        "The input valve is 1.5, and the rule required 0.",
    )
    assert allowed == ("controller_valve. The input valve is 1.5, and the rule required 0.")


def test_law_page_refuses_an_uncited_break_and_does_not_place_it() -> None:
    uncited = LawBreak("joint_move", WHEN, "Tags a and b moved together.")
    later = LawBreak(
        "subfloor_walk",
        WHEN + timedelta(minutes=1),
        "subfloor_walk. Tag tank_level_max was walked across the ordinary band "
        "for the frozen walk length.",
    )
    assert type(uncited) is LawBreak
    assert uncited.name in {law.name for law in DECLARED.laws}
    assert not uncited.statement.startswith("joint_move. ")
    placed: tuple[LawBreak, ...] = ()
    with pytest.raises(ValueError, match="joint_move does not name its law"):
        placed = law_page((uncited, later), register=DECLARED)
    assert uncited not in placed
    assert later not in placed
    assert placed == ()
    report = LawReport(held=(), broken=(uncited,), unstated=())
    with pytest.raises(ValueError, match="joint_move does not name its law"):
        page_from_report(report, register=DECLARED)


def test_law_break_fields_remain_name_time_statement_and_residuals_stay_unimported() -> None:
    assert [field.name for field in dataclasses.fields(LawBreak)] == [
        "name",
        "time",
        "statement",
    ]
    source = SOURCE.read_text(encoding="utf-8")
    for banned in (
        "phos.atlas.consistency",
        "walk_consistency",
        "command_consistency",
        "drift_consistency",
        "bending_consistency",
        "breadth_consistency",
        "phos.atlas.queue",
        "phos.atlas.grouping",
        "shift_brief",
        "handoff_page",
        "leap_stack",
        "budget_alerts",
        "feature_scores",
    ):
        assert banned not in source

"""Named rows become assess_plant's arguments. A function code does not.

ADR 0325. These rows are constructed in the test. No capture is opened.
"""

from __future__ import annotations

import ast
import dataclasses
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from phos.atlas.declared_law import (
    ALLOWED_WRITER,
    CONTROLLER_VALVE,
    JOINT_MOVE,
    LAWS,
    PROGRAM_TRANSFER,
    ControllerSample,
    LawBreak,
    LawRegister,
    LawReport,
    WriterWrite,
    assess_plant,
    page_from_report,
)
from phos.atlas.handoff_booking import TagBooking
from phos.atlas.joint_setpoint import SETPOINT_BAND, SetpointStep
from phos.atlas.law_inlet import (
    PLC1_CONTROLLER_TAGS,
    HistorianRow,
    LawInlet,
    inlet_from_tables,
)
from phos.atlas.packet.frame import Endpoint, FrameSource
from phos.atlas.packet.messages import (
    Direction,
    MalformedFrame,
    MalformedReason,
    ModbusMessage,
)
from phos.atlas.program_transfer import (
    Booking,
    BookingKind,
    ProgramAct,
    TransferWorkOrder,
    refuse_function_code,
)

WHEN = datetime(2026, 10, 23, 8, 0, tzinfo=UTC)
ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "src" / "phos" / "atlas" / "law_inlet.py"
FRAME = FrameSource(capture="/captures/plant.pcap", frame_index=0)
CLIENT = Endpoint(ip="10.0.0.9", port=40000)
SERVER = Endpoint(ip="10.0.0.2", port=502)
_SCORE_WORDS = ("confidence", "probability", "weight", "magnitude", "score")


def _report_of(inlet: LawInlet) -> LawReport:
    return assess_plant(
        inlet.steps,
        inlet.transfers,
        register=inlet.register,
        bookings=inlet.bookings,
        work_orders=inlet.work_orders,
        tag_bookings=inlet.tag_bookings,
        writes=inlet.writes,
        allowed_stations=inlet.allowed_stations,
        controller=inlet.controller,
    )


_RESIDUAL = (
    "consistency",
    "command_consistency",
    "walk_consistency",
    "drift_consistency",
    "bending_consistency",
    "breadth_consistency",
    "queue",
    "grouping",
    "shift_brief",
    "handoff_page",
    "leap_stack",
)


def _message(function_code: int) -> ModbusMessage:
    return ModbusMessage(
        source=FRAME,
        timestamp=WHEN,
        src=CLIENT,
        dst=SERVER,
        direction=Direction.REQUEST,
        transaction_id=1,
        unit_id=17,
        function_code=function_code,
        function_name=(
            "write_multiple_registers" if function_code == 16 else "read_holding_registers"
        ),
    )


def _malformed() -> MalformedFrame:
    return MalformedFrame(
        protocol="modbus",
        source=FRAME,
        timestamp=WHEN,
        src=CLIENT,
        dst=SERVER,
        reason=MalformedReason.SHORT_HEADER,
        detail="the header was short",
        payload_length=3,
    )


def _controller_rows() -> tuple[HistorianRow, ...]:
    values = {
        "tank_level_value": 4.0,
        "tank_level_min": 2.0,
        "tank_level_max": 6.0,
        "tank_input_valve_status": 0.0,
        "tank_input_valve_mode": 3.0,
        "bottle_level_value": 1.0,
        "bottle_level_max": 1.5,
        "bottle_distance_to_filler_value": 0.5,
        "tank_output_valve_status": 1.0,
        "tank_output_valve_mode": 3.0,
    }
    return tuple(HistorianRow(tag, WHEN, value) for tag, value in values.items())


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[-1] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            found.add(node.module.split(".")[-1])
            found.update(alias.name for alias in node.names)
    return found


def test_a_listed_tag_becomes_a_step_and_an_unlisted_tag_does_not() -> None:
    rows = (
        HistorianRow("tank_level_max", WHEN, 7.0),
        HistorianRow("tank_level_value", WHEN, 4.0),
    )
    inlet = inlet_from_tables(
        register=LawRegister(()),
        historian=rows,
        setpoint_tags=frozenset({"tank_level_max"}),
    )
    assert inlet.steps == (SetpointStep("tank_level_max", WHEN, 7.0),)
    assert inlet.controller is None


def test_omitting_the_controller_map_leaves_the_sample_unset() -> None:
    inlet = inlet_from_tables(register=LawRegister(()), historian=_controller_rows())
    assert inlet.controller is None
    assert inlet.steps == ()


def test_ten_rows_at_one_time_are_one_controller_sample() -> None:
    inlet = inlet_from_tables(
        register=LawRegister(()),
        historian=_controller_rows(),
        controller_tags=PLC1_CONTROLLER_TAGS,
    )
    assert inlet.controller == ControllerSample(
        at=WHEN,
        level=4.0,
        level_min=2.0,
        level_max=6.0,
        input_valve=0.0,
        input_mode=3.0,
        bottle_level=1.0,
        bottle_max=1.5,
        belt=0.5,
        output_valve=1.0,
        output_mode=3.0,
    )


def test_a_partial_controller_map_is_refused() -> None:
    rows = _controller_rows()[:-1]
    with pytest.raises(ValueError, match="tank_output_valve_mode"):
        inlet_from_tables(
            register=LawRegister(()),
            historian=rows,
            controller_tags=PLC1_CONTROLLER_TAGS,
        )


def test_a_second_controller_row_is_refused() -> None:
    extra = HistorianRow("tank_level_value", WHEN, 5.0)
    with pytest.raises(ValueError, match="more than one row"):
        inlet_from_tables(
            register=LawRegister(()),
            historian=(*_controller_rows(), extra),
            controller_tags=PLC1_CONTROLLER_TAGS,
        )


def test_a_modbus_station_is_the_callers_string() -> None:
    inlet = inlet_from_tables(
        register=LawRegister((PROGRAM_TRANSFER,)),
        modbus_writes=(("hmi-1", _message(16)), ("hmi-1", _message(3))),
    )
    assert inlet.writes == (WriterWrite("hmi-1", WHEN), WriterWrite("hmi-1", WHEN))
    assert inlet.transfers == ()
    report = _report_of(inlet)
    assert all(item.name != "program_transfer" for item in report.broken)
    assert report.unstated[0].name == "program_transfer"


def test_an_empty_modbus_station_is_refused() -> None:
    with pytest.raises(ValueError, match="station is empty"):
        inlet_from_tables(
            register=LawRegister(()),
            modbus_writes=(("", _message(16)),),
        )


def test_a_malformed_frame_is_not_an_inlet() -> None:
    with pytest.raises(ValueError, match="malformed"):
        inlet_from_tables(register=LawRegister(LAWS), malformed=(_malformed(),))


def test_an_int_act_is_refused_and_no_inlet_is_returned() -> None:
    with pytest.raises(ValueError, match="not a program transfer"):
        inlet_from_tables(
            register=LawRegister(LAWS),
            transfers=((16, WHEN),),
        )
    with pytest.raises(ValueError, match="not a program transfer"):
        refuse_function_code(16)


def test_a_named_act_is_copied_and_a_naive_time_is_refused() -> None:
    copied = inlet_from_tables(
        register=LawRegister(()),
        transfers=((ProgramAct.DOWNLOAD, WHEN),),
    )
    assert copied.transfers == ((ProgramAct.DOWNLOAD, WHEN),)
    naive = datetime(2026, 10, 23, 8, 0)
    with pytest.raises(ValueError, match="timezone"):
        inlet_from_tables(
            register=LawRegister(()),
            transfers=((ProgramAct.DOWNLOAD, naive),),
        )


def test_bookings_and_the_register_pass_through() -> None:
    booking = Booking(
        BookingKind.DOWNTIME,
        ProgramAct.UPLOAD,
        WHEN,
        WHEN + timedelta(hours=1),
    )
    order = TransferWorkOrder(WHEN, WHEN + timedelta(hours=1), act=ProgramAct.DOWNLOAD)
    tags = TagBooking(("tank_level_max", "bottle_level_max"), WHEN, WHEN + timedelta(hours=1))
    register = LawRegister((CONTROLLER_VALVE,))
    inlet = inlet_from_tables(
        register=register,
        bookings=(booking,),
        work_orders=(order,),
        tag_bookings=(tags,),
        allowed_stations=frozenset({"hmi-1"}),
    )
    assert isinstance(inlet, LawInlet)
    assert inlet.register is register
    assert inlet.bookings == (booking,)
    assert inlet.work_orders == (order,)
    assert inlet.tag_bookings == (tags,)
    assert inlet.allowed_stations == frozenset({"hmi-1"})
    assert inlet.steps == ()
    assert inlet.writes == ()
    assert inlet.controller is None


def test_the_module_does_not_read_a_function_code_or_a_residual() -> None:
    text = SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(text)
    attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    assert "function_code" not in attributes
    assert "unit_id" not in attributes
    assert "src" not in attributes
    assert "dst" not in attributes
    calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "assess_plant" not in calls
    assert "open" not in calls
    imported = _imports(SOURCE)
    assert "refuse_function_code" in imported
    assert imported.isdisjoint(_RESIDUAL)


def test_an_empty_register_yields_three_empty_lists() -> None:
    low, high = SETPOINT_BAND
    inlet = inlet_from_tables(
        register=LawRegister(()),
        historian=(
            HistorianRow("tank_level_max", WHEN, low),
            HistorianRow("bottle_level_max", WHEN + timedelta(seconds=10), high),
        ),
        setpoint_tags=frozenset({"tank_level_max", "bottle_level_max"}),
    )
    report = _report_of(inlet)
    assert report.held == ()
    assert report.broken == ()
    assert report.unstated == ()


def test_named_setpoint_rows_cite_the_joint_law() -> None:
    low, high = SETPOINT_BAND
    inlet = inlet_from_tables(
        register=LawRegister((JOINT_MOVE,)),
        historian=(
            HistorianRow("tank_level_max", WHEN, low),
            HistorianRow("bottle_level_max", WHEN + timedelta(seconds=10), high),
        ),
        setpoint_tags=frozenset({"tank_level_max", "bottle_level_max"}),
    )
    report = _report_of(inlet)
    page = page_from_report(report, register=inlet.register)
    assert len(page) == 1
    assert len(page) <= 8
    statement = page[0].statement
    assert statement.startswith("joint_move. ")
    folded = statement.casefold()
    assert all(word not in folded for word in _SCORE_WORDS)
    names = {item.name for item in report.held}
    names.update(item.name for item in report.broken)
    names.update(item.name for item in report.unstated)
    assert names == {"joint_move"}


def test_nine_outside_writes_keep_the_earliest_eight() -> None:
    named = tuple(
        WriterWrite(f"station-{index}", WHEN + timedelta(seconds=index)) for index in range(9)
    )
    inlet = inlet_from_tables(
        register=LawRegister((ALLOWED_WRITER,)),
        writes=named,
        allowed_stations=frozenset({"hmi-1"}),
    )
    page = page_from_report(_report_of(inlet), register=inlet.register)
    assert len(page) == 8
    assert page[-1].time == named[7].at
    assert all(item.statement.startswith(f"{item.name}. ") for item in page)


def test_a_magnitude_subclass_is_refused_beside_the_inlet() -> None:
    @dataclasses.dataclass(frozen=True)
    class MagnitudeBreak(LawBreak):
        magnitude: float

    inlet = inlet_from_tables(register=LawRegister((JOINT_MOVE,)))
    foreign = MagnitudeBreak("joint_move", WHEN, "joint_move. A magnitude.", magnitude=9.0)
    with pytest.raises(ValueError, match="only a LawBreak"):
        page_from_report(
            _report_of(inlet).__class__(held=(), broken=(foreign,), unstated=()),
            register=inlet.register,
        )

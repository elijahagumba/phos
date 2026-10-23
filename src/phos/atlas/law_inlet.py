"""Named rows become the arguments ``assess_plant`` already takes.

A historian row becomes a setpoint step only when the caller listed its tag.
A Modbus message contributes a write only beside a station string the caller
supplied. A function code is not read. A program act is a ``ProgramAct`` the
caller named. An integer offered as an act is refused, and no inlet is
returned. A malformed frame raises before an inlet exists.

This module does not call ``assess_plant``, does not open a file, and does
not import the residual detectors. ADR 0325. Nothing here is a score.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Final

from phos.atlas.declared_law import ControllerSample, LawRegister, WriterWrite
from phos.atlas.handoff_booking import TagBooking
from phos.atlas.joint_setpoint import SetpointStep
from phos.atlas.packet.messages import MalformedFrame, ModbusMessage
from phos.atlas.program_transfer import (
    Booking,
    ProgramAct,
    TransferWorkOrder,
    refuse_function_code,
)

__all__ = [
    "PLC1_CONTROLLER_TAGS",
    "HistorianRow",
    "LawInlet",
    "inlet_from_tables",
]

logger = logging.getLogger(__name__)

_CONTROLLER_FIELDS: Final[tuple[str, ...]] = (
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

PLC1_CONTROLLER_TAGS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "level": "tank_level_value",
        "level_min": "tank_level_min",
        "level_max": "tank_level_max",
        "input_valve": "tank_input_valve_status",
        "input_mode": "tank_input_valve_mode",
        "bottle_level": "bottle_level_value",
        "bottle_max": "bottle_level_max",
        "belt": "bottle_distance_to_filler_value",
        "output_valve": "tank_output_valve_status",
        "output_mode": "tank_output_valve_mode",
    }
)
"""Tag names already written on ``ControllerSample``. The caller passes them."""


@dataclass(frozen=True)
class HistorianRow:
    """One historian row the caller already named.

    Attributes:
        tag: The tag name on the row. Empty is refused.
        at: When the row was taken. Timezone-aware.
        value: The value the row already holds.
    """

    tag: str
    at: datetime
    value: float


@dataclass(frozen=True)
class LawInlet:
    """The arguments ``assess_plant`` already takes, and no others.

    Attributes:
        steps: Setpoint writes whose tags the caller listed.
        transfers: Program acts the caller named, with their times.
        register: The laws the plant named. Required. Not filled here.
        bookings: Bookings that can cover a program act.
        work_orders: Work orders that can cover a program act.
        tag_bookings: Bookings that name both tags of a handoff.
        writes: Station writes the caller named.
        allowed_stations: Stations the plant allowed to write.
        controller: One controller sample, or ``None`` when the map was omitted.
    """

    steps: tuple[SetpointStep, ...]
    transfers: tuple[tuple[ProgramAct, datetime], ...]
    register: LawRegister
    bookings: tuple[Booking, ...]
    work_orders: tuple[TransferWorkOrder, ...]
    tag_bookings: tuple[TagBooking, ...]
    writes: tuple[WriterWrite, ...]
    allowed_stations: frozenset[str]
    controller: ControllerSample | None


def inlet_from_tables(
    *,
    register: LawRegister,
    historian: Sequence[HistorianRow] = (),
    setpoint_tags: frozenset[str] = frozenset(),
    controller_tags: Mapping[str, str] | None = None,
    writes: Sequence[WriterWrite] = (),
    modbus_writes: Sequence[tuple[str, ModbusMessage]] = (),
    malformed: Sequence[MalformedFrame] = (),
    transfers: Sequence[tuple[ProgramAct | int, datetime]] = (),
    bookings: Sequence[Booking] = (),
    work_orders: Sequence[TransferWorkOrder] = (),
    tag_bookings: Sequence[TagBooking] = (),
    allowed_stations: frozenset[str] = frozenset(),
) -> LawInlet:
    """Copy named tables onto one ``LawInlet``.

    A historian tag becomes a setpoint step only when it is in
    ``setpoint_tags``. ``controller`` is ``None`` when ``controller_tags`` is
    omitted. When the map is passed, each of the ten ``ControllerSample``
    fields names one tag, each of those tags has one row, and the rows share
    one time. A dissected write uses the station string the caller passed and
    the message timestamp. An empty ``malformed`` sequence is ignored. A
    non-empty one raises, and no inlet is returned.

    Args:
        register: The laws the plant named. Stored, not evaluated.
        historian: Rows the caller already named.
        setpoint_tags: Tags that are setpoint steps. Other tags are not steps.
        controller_tags: Field name to historian tag. ``None`` leaves the
            sample unset. ``PLC1_CONTROLLER_TAGS`` is the quoted map.
        writes: Station writes the caller already built.
        modbus_writes: Each pair is a station string and one dissected message.
        malformed: Frames a dissector already refused. Any frame raises.
        transfers: Acts the caller named. An integer is refused.
        bookings: Bookings copied onto the inlet.
        work_orders: Work orders copied onto the inlet.
        tag_bookings: Handoff bookings copied onto the inlet.
        allowed_stations: The set the plant named. Empty stays empty.

    Returns:
        One inlet. It has no score field.

    Raises:
        ValueError: If a time is naive, a station or a tag is empty, a
            function code is offered as an act, a malformed frame is present,
            or the controller map does not pick exactly one shared sample.
    """
    if len(malformed) > 0:
        raise ValueError("a malformed frame is not a write")
    inlet = LawInlet(
        steps=_steps(historian, setpoint_tags),
        transfers=_transfers(transfers),
        register=register,
        bookings=tuple(bookings),
        work_orders=tuple(work_orders),
        tag_bookings=tuple(tag_bookings),
        writes=_writes(writes, modbus_writes),
        allowed_stations=frozenset(allowed_stations),
        controller=_controller(historian, controller_tags),
    )
    logger.info(
        "law inlet steps %s writes %s transfers %s controller %s",
        len(inlet.steps),
        len(inlet.writes),
        len(inlet.transfers),
        inlet.controller is not None,
    )
    return inlet


def _aware(moment: datetime, name: str) -> None:
    """Raise when ``moment`` has no timezone."""
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _steps(
    historian: Sequence[HistorianRow],
    setpoint_tags: frozenset[str],
) -> tuple[SetpointStep, ...]:
    """Return a step for each listed tag, in row order."""
    steps: list[SetpointStep] = []
    for row in historian:
        if row.tag == "":
            raise ValueError("tag is empty")
        _aware(row.at, "historian time")
        if row.tag in setpoint_tags:
            steps.append(SetpointStep(row.tag, row.at, row.value))
    return tuple(steps)


def _transfers(
    transfers: Sequence[tuple[ProgramAct | int, datetime]],
) -> tuple[tuple[ProgramAct, datetime], ...]:
    """Copy caller-named acts. An integer is refused and nothing is returned."""
    copied: list[tuple[ProgramAct, datetime]] = []
    for act, at in transfers:
        if type(act) is int:
            refuse_function_code(act)
            raise RuntimeError("a function code returns no inlet")
        if type(act) is not ProgramAct:
            raise ValueError("a program act is download, upload, or online edit")
        _aware(at, "transfer time")
        copied.append((act, at))
    return tuple(copied)


def _writes(
    writes: Sequence[WriterWrite],
    modbus_writes: Sequence[tuple[str, ModbusMessage]],
) -> tuple[WriterWrite, ...]:
    """Copy named writes, then one write per dissected pair."""
    copied: list[WriterWrite] = []
    for write in writes:
        if write.station == "":
            raise ValueError("station is empty")
        _aware(write.at, "write time")
        copied.append(write)
    for station, message in modbus_writes:
        if type(message) is not ModbusMessage:
            raise ValueError("a dissected write is a ModbusMessage")
        if station == "":
            raise ValueError("station is empty")
        _aware(message.timestamp, "message time")
        copied.append(WriterWrite(station, message.timestamp))
    return tuple(copied)


def _controller(
    historian: Sequence[HistorianRow],
    controller_tags: Mapping[str, str] | None,
) -> ControllerSample | None:
    """Build one sample, or leave it unset when the caller passed no map."""
    if controller_tags is None:
        return None
    if set(controller_tags) != set(_CONTROLLER_FIELDS):
        raise ValueError("controller map names the ten fields")
    tags = tuple(controller_tags[field] for field in _CONTROLLER_FIELDS)
    if any(tag == "" for tag in tags):
        raise ValueError("controller tag is empty")
    if len(set(tags)) != len(tags):
        raise ValueError("controller map repeats a tag")
    chosen: list[HistorianRow] = []
    for tag in tags:
        rows = [row for row in historian if row.tag == tag]
        if len(rows) == 0:
            raise ValueError(f"controller tag {tag} has no row")
        if len(rows) > 1:
            raise ValueError(f"controller tag {tag} has more than one row")
        chosen.append(rows[0])
    if len({row.at for row in chosen}) != 1:
        raise ValueError("controller rows do not share one time")
    by_field = dict(zip(_CONTROLLER_FIELDS, chosen, strict=True))
    return ControllerSample(
        at=chosen[0].at,
        level=by_field["level"].value,
        level_min=by_field["level_min"].value,
        level_max=by_field["level_max"].value,
        input_valve=by_field["input_valve"].value,
        input_mode=by_field["input_mode"].value,
        bottle_level=by_field["bottle_level"].value,
        bottle_max=by_field["bottle_max"].value,
        belt=by_field["belt"].value,
        output_valve=by_field["output_valve"].value,
        output_mode=by_field["output_mode"].value,
    )

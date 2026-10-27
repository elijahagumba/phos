#!/usr/bin/env python3
"""Constructed cases for the law-page invariant bars 5 to 8 (ADR 0333).

Bars 5 to 8 are not reachable from ordinary corpus rows: a development run need not
produce a ninth break, never offers a ``LawBreak`` subclass, carries ``modbus.csv`` and
no pcap, and always names its laws. Each one therefore needs a case built on purpose.

Every function here **returns a value and counts nothing**. The counting stays in
``scripts/lane_law_inlet_invariants.py``, so the thresholds live in one place and this
module cannot quietly decide a bar was met. Nothing here scores, thresholds or detects.
"""

from __future__ import annotations

import struct
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Final

ROOT: Final = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from phos.atlas.declared_law import (  # noqa: E402
    LawBreak,
    LawRegister,
    WriterWrite,
    cited_statement,
)
from phos.atlas.law_inlet import HistorianRow, LawInlet, inlet_from_tables  # noqa: E402
from phos.atlas.packet.frame import Endpoint, FrameSource, RawFrame, Transport  # noqa: E402
from phos.atlas.packet.messages import MalformedFrame  # noqa: E402
from phos.atlas.packet.modbus import MODBUS_PORT, ModbusDissector  # noqa: E402

__all__ = [
    "PROBE_BREAKS",
    "empty_register_inlet",
    "magnitude_break",
    "probe_breaks",
    "refused_frames",
]

#: How many breaks the ceiling case offers. More than the ceiling, so the ninth break by
#: time has to be absent for bar 5 to be met.
PROBE_BREAKS: Final = 12


class _MagnitudeBreak(LawBreak):
    """A subclass carrying a magnitude, so bar 6 has something the page must refuse.

    ``law_page`` admits a value only when ``type(item) is LawBreak``, because a subclass
    can carry exactly this field. The attribute name is the word the page refuses, so a
    page that placed one would be visibly wrong rather than quietly wrong.
    """

    def __init__(self, name: str, time: datetime, statement: str, magnitude: float) -> None:
        """Build the subclass and record the magnitude the page must never see.

        Args:
            name: The law the break names.
            time: When the broken fact happened. Timezone-aware.
            statement: The cited sentence.
            magnitude: The field that makes this a different type.
        """
        super().__init__(name=name, time=time, statement=statement)
        object.__setattr__(self, "magnitude", magnitude)


def probe_breaks(register: LawRegister, at: datetime) -> tuple[LawBreak, ...]:
    """Return more breaks than the ceiling, one second apart, on the run's own clock.

    Args:
        register: The laws the plant named. Names are cycled so every law appears.
        at: The run's first sample time. The breaks count seconds from it.

    Returns:
        ``PROBE_BREAKS`` breaks in ascending time order.
    """
    laws = register.laws
    return tuple(
        LawBreak(
            name=laws[index % len(laws)].name,
            time=at + timedelta(seconds=index),
            statement=cited_statement(
                laws[index % len(laws)],
                f"probe break {index} at the run's own clock.",
            ),
        )
        for index in range(PROBE_BREAKS)
    )


def magnitude_break(register: LawRegister, at: datetime) -> LawBreak:
    """Return a ``LawBreak`` subclass instance for bar 6.

    Args:
        register: The laws the plant named. The first law's name is used, so the break is
            refused for its type rather than for an unregistered name.
        at: The break's time.

    Returns:
        An instance whose type is not ``LawBreak``.
    """
    law = register.laws[0]
    return _MagnitudeBreak(
        name=law.name,
        time=at,
        statement=cited_statement(law, "probe subclass offered to the page."),
        magnitude=1.0,
    )


def refused_frames(at: datetime) -> tuple[MalformedFrame, ...]:
    """Return frames this repository's own dissector claimed and then refused.

    Three deliberate faults: a payload shorter than the MBAP header, a wrong protocol id,
    and a declared length past the buffer. The corpus carries ``modbus.csv`` and no pcap,
    so there is no capture to mutate. The dissector is the real one, and a frame it does
    not claim is a fault in this probe rather than a result.

    Args:
        at: The capture time to stamp each probe frame with.

    Returns:
        The frames the dissector refused.

    Raises:
        SystemExit: If the dissector does not claim a probe frame.
    """
    dissector = ModbusDissector()
    payloads = (
        b"\x00\x01",
        struct.pack(">HHHB", 1, 7, 6, 1) + b"\x03\x00\x00\x00\x01",
        struct.pack(">HHHB", 1, 0, 600, 1) + b"\x03\x00\x00\x00\x01",
    )
    refused: list[MalformedFrame] = []
    for index, payload in enumerate(payloads):
        frame = RawFrame(
            source=FrameSource(capture="probe", frame_index=index),
            timestamp=at,
            transport=Transport.TCP,
            src=Endpoint(ip="10.0.0.9", port=40000 + index),
            dst=Endpoint(ip="10.0.0.1", port=MODBUS_PORT),
            payload=payload,
        )
        if not dissector.claims(frame):
            raise SystemExit("the probe frame was not claimed; the port pair is wrong")
        outcome = dissector.dissect(frame)
        if isinstance(outcome, MalformedFrame):
            refused.append(outcome)
    return tuple(refused)


def empty_register_inlet(at: datetime) -> LawInlet:
    """Return an inlet with facts and an empty register, for bar 8.

    The facts would match a predicate if the plant had named one: a setpoint row and a
    write from a station outside the allowed set. The register names nothing, so the
    assessment must still be three empty lists.

    Args:
        at: The time to stamp the row and the write with.

    Returns:
        One inlet whose register is empty.
    """
    return inlet_from_tables(
        register=LawRegister(laws=()),
        historian=(HistorianRow(tag="tank_level_max", at=at, value=4.0),),
        setpoint_tags=frozenset({"tank_level_max"}),
        writes=(WriterWrite(station="attacker", at=at),),
        allowed_stations=frozenset({"operator"}),
    )

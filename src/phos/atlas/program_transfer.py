"""A program transfer the caller already named, and the alert when nothing booked it.

Download, upload, and online edit are three acts. A Modbus register or coil write is none of
them (ADR 0302). This module does not read a function code and decide. The caller supplies
the act. An empty booking list and an empty work-order list stay empty.

An unbooked transfer raises a security alert whose instruction is ``Go and look.`` Both
stories stay visible, and neither is a unique lead. A booking or a work order that names the
same act and covers the hour withdraws the alert only. It does not pick a winner. A missing
booking is not a verdict of attack.

Hypothesis confidence is computed only so the existing tie rule can see two equal stories.
It is not a field of the report.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Final

from phos.atlas.consistency import ALERTS_PER_SHIFT, SHIFT_SECONDS
from phos.atlas.templates import (
    ENGINEERING_MAINTENANCE_TEMPLATE_ID,
    UNAUTHORISED_CONTROL_TEMPLATE_ID,
)
from phos.ontology import Domain, Hypothesis, HypothesisStatus
from phos.reasoning import INSUFFICIENT_EVIDENCE_TEMPLATE_ID, tied_lead_ids

__all__ = [
    "GO_AND_LOOK",
    "NEXT_OBSERVATION",
    "Booking",
    "BookingKind",
    "OtherAlert",
    "ProgramAct",
    "ShiftSlot",
    "TransferReport",
    "TransferWorkOrder",
    "refuse_function_code",
    "shift_page",
    "transfer_report",
]

logger = logging.getLogger(__name__)

GO_AND_LOOK: Final = "Go and look."
"""The instruction on an unbooked transfer. The words are the invariant, not a paraphrase."""

NEXT_OBSERVATION: Final = "A booking that names this act and covers this hour."
"""The one fact that would withdraw the alert. It does not pick a story."""

_STORIES: Final = (
    ENGINEERING_MAINTENANCE_TEMPLATE_ID,
    UNAUTHORISED_CONTROL_TEMPLATE_ID,
)
_TIED_CONFIDENCE: Final = 0.5
"""Equal on both stories so `tied_lead_ids` is non-empty. Not a reported confidence."""


class ProgramAct(StrEnum):
    """The three program-transfer acts. A register write is not a member."""

    DOWNLOAD = "download"
    UPLOAD = "upload"
    ONLINE_EDIT = "online_edit"


class BookingKind(StrEnum):
    """Why a supplied booking would cover an act. Absence of one is not an attack."""

    DOWNTIME = "downtime"
    COMMISSIONING = "commissioning"
    CHECK_IN = "check_in"


@dataclass(frozen=True)
class Booking:
    """A booking the caller already holds. This module does not create one.

    Attributes:
        kind: Downtime, commissioning, or a check-in.
        act: The program-transfer act the booking names.
        start: Inclusive start. Timezone-aware.
        end: Inclusive end. Timezone-aware.
    """

    kind: BookingKind
    act: ProgramAct
    start: datetime
    end: datetime


@dataclass(frozen=True)
class TransferWorkOrder:
    """A work order the caller already holds.

    ``act`` is set only when the order names a program-transfer act. A tag-only order
    leaves ``act`` as ``None`` and does not cover a transfer.

    Attributes:
        start: Inclusive start. Timezone-aware.
        end: Inclusive end. Timezone-aware.
        act: The act the order names, or ``None`` when it only names a tag.
        tag: The tag a tag-only order names.
    """

    start: datetime
    end: datetime
    act: ProgramAct | None = None
    tag: str | None = None


@dataclass(frozen=True)
class TransferReport:
    """The page for one supplied program transfer.

    Attributes:
        act: The act the caller named.
        stories: Maintenance and unauthorised control, both present.
        tied_lead_ids: The same two ids. Non-empty, so neither is a unique lead.
        hypotheses: The competing set, including insufficient evidence. Confidence on
            these objects is the tie's input. It is not a field of this report.
        lead: Always ``None``. The tie is the refusal to pick.
        alert: True when no supplied record covers the act at ``at``.
        instruction: ``Go and look.`` when ``alert`` is true, otherwise ``None``.
        next_observation: The booking that would withdraw the alert, or ``None`` when
            a covering record is already supplied. Not a confidence.
    """

    act: ProgramAct
    stories: tuple[str, str]
    tied_lead_ids: tuple[str, ...]
    hypotheses: tuple[Hypothesis, ...]
    lead: None
    alert: bool
    instruction: str | None
    next_observation: str | None


@dataclass(frozen=True)
class OtherAlert:
    """An alert some other allocator already chose for this shift.

    Attributes:
        at: When it fires. Timezone-aware.
        score: The allocator's rank. Higher stays when the page is full.
        key: A stable name so a test can see which alert left.
    """

    at: datetime
    score: float
    key: str


@dataclass(frozen=True)
class ShiftSlot:
    """One place on the shift page. A transfer slot has no other alert, and the reverse.

    Attributes:
        at: When this slot fires.
        report: The unbooked transfer, when this slot is one.
        other: The allocator's alert, when this slot is one.
    """

    at: datetime
    report: TransferReport | None = None
    other: OtherAlert | None = None


def shift_page(
    others: Sequence[OtherAlert],
    transfers: Sequence[tuple[TransferReport, datetime]],
) -> tuple[ShiftSlot, ...]:
    """Keep at most one shift's worth of alerts.

    Unbooked transfers stay. Booked transfers are omitted. Other alerts leave from the
    lowest score until the page holds ``ALERTS_PER_SHIFT``. An unbooked transfer is not
    removed to save an other alert. When the unbooked transfers themselves exceed the
    budget, the earliest stay, and a shared time keeps the earlier act name.

    Args:
        others: Alerts already chosen for this same shift.
        transfers: Each report with the time it happened.

    Returns:
        At most ``ALERTS_PER_SHIFT`` slots. Transfers first, then other alerts from the
        highest score.

    Raises:
        ValueError: If a time is naive, or the times span a second shift.
    """
    _one_shift([item.at for item in others] + [at for _report, at in transfers])
    kept = [(report, at) for report, at in transfers if report.alert]
    kept.sort(key=lambda item: (item[1], item[0].act.value))
    kept = kept[:ALERTS_PER_SHIFT]
    room = ALERTS_PER_SHIFT - len(kept)
    ranked = sorted(others, key=lambda item: (-item.score, item.at, item.key))
    chosen = ranked[:room]
    slots = [ShiftSlot(at=at, report=report) for report, at in kept]
    slots.extend(ShiftSlot(at=item.at, other=item) for item in chosen)
    logger.info("shift page transfers=%s others=%s", len(kept), len(chosen))
    return tuple(slots)


def _one_shift(moments: Sequence[datetime]) -> None:
    """Raise when the times are naive or cover more than one shift."""
    for moment in moments:
        _require_aware(moment, "shift time")
    if len(moments) < 2:
        return
    span = max(moments) - min(moments)
    if span >= timedelta(seconds=SHIFT_SECONDS):
        raise ValueError("shift_page takes one shift")


def refuse_function_code(code: int) -> None:
    """Refuse to turn a Modbus function code into a program-transfer act.

    Args:
        code: A function code from the wire, including register and coil writes.

    Raises:
        ValueError: Always. No code is a download, an upload, or an online edit.
    """
    raise ValueError(
        f"function code {code} is not a program transfer; "
        "download, upload, and online_edit are supplied by the caller"
    )


def transfer_report(
    act: ProgramAct,
    bookings: Sequence[Booking] = (),
    work_orders: Sequence[TransferWorkOrder] = (),
    *,
    at: datetime,
) -> TransferReport:
    """Report one named act against the bookings and work orders the caller supplied.

    Args:
        act: The program transfer. Not inferred.
        bookings: Covering records already in hand. An empty sequence stays empty.
        work_orders: Work orders already in hand. An order covers the act only when it
            names that act and its interval contains ``at``.
        at: When the transfer happened. Timezone-aware.

    Returns:
        Both stories, a non-empty tie, and ``Go and look.`` when nothing covers ``act``.

    Raises:
        ValueError: If ``at`` or a record's interval is naive, or an interval ends
            before it starts.
    """
    _require_aware(at, "at")
    covered = any(_booking_covers(booking, act, at) for booking in bookings) or any(
        _order_covers(order, act, at) for order in work_orders
    )
    hypotheses = _competing(at)
    tie = tied_lead_ids(hypotheses)
    alert = not covered
    logger.info("program transfer %s alert=%s", act.value, alert)
    return TransferReport(
        act=act,
        stories=_STORIES,
        tied_lead_ids=tie,
        hypotheses=hypotheses,
        lead=None,
        alert=alert,
        instruction=GO_AND_LOOK if alert else None,
        next_observation=NEXT_OBSERVATION if alert else None,
    )


def _booking_covers(booking: Booking, act: ProgramAct, at: datetime) -> bool:
    """Return whether this supplied booking names ``act`` and contains ``at``."""
    _require_interval(booking.start, booking.end, "booking")
    return booking.act is act and booking.start <= at <= booking.end


def _order_covers(order: TransferWorkOrder, act: ProgramAct, at: datetime) -> bool:
    """Return whether this work order names ``act`` and contains ``at``.

    A tag-only order has ``act is None`` and does not cover.
    """
    _require_interval(order.start, order.end, "work order")
    return order.act is act and order.start <= at <= order.end


def _competing(at: datetime) -> tuple[Hypothesis, ...]:
    """Both stories at the same confidence, plus insufficient evidence.

    The confidence is equal so the tie rule keeps both. It is not returned on the report.
    """
    return tuple(
        Hypothesis(
            label=template_id,
            template_id=template_id,
            domain=Domain.ATLAS,
            prior=_TIED_CONFIDENCE,
            confidence=_TIED_CONFIDENCE,
            status=HypothesisStatus.ACTIVE,
            created_at=at,
            updated_at=at,
        )
        for template_id in (*_STORIES, INSUFFICIENT_EVIDENCE_TEMPLATE_ID)
    )


def _require_aware(moment: datetime, name: str) -> None:
    """Raise when ``moment`` has no timezone."""
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _require_interval(start: datetime, end: datetime, name: str) -> None:
    """Raise when an interval is naive or runs backwards."""
    _require_aware(start, f"{name} start")
    _require_aware(end, f"{name} end")
    if end < start:
        raise ValueError(f"{name} ends before it starts")

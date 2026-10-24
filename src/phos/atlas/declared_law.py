"""The operator page: only a broken declared law takes a slot.

A declared law is held, broken, or unstated. Held means the inlet had facts
and the predicate returned silence. Unstated means the law is named and the
inlet has no facts that law can be checked against, or the register names a
law this page has no check for. That unchecked name is listed once. It is
not dropped. Broken means the predicate returned an alert. Only a broken law
is a ``LawBreak``, and only that list enters the page. Held and unstated are
listed and take no slot. A law the register does not name is on none of the
three lists. The three lists partition the register: one named law is in one
list.

There is no score, confidence, probability, weight, or magnitude on an
outcome. A held or unstated outcome carries no time. Time is recorded only
for a break. The page orders breaks by that time, then the law name. The page
keeps at most the operator ceiling fixed in ``docs/v1-roadmap.md`` section
2.0. Fewer broken laws is a complete page. Residual magnitude does not create
a slot and does not order one.

An empty register evaluates nothing. A break whose name is absent from the
register is refused. Admission is a boolean. It is not a threshold, a weight,
a residual, or a confidence. A slot enters the page only as a ``LawBreak``,
the exact type. A subclass is a different type and is refused, including one
that adds a magnitude. It is not placed. This adds no new law and no new
threshold.

Every sentence names the declared law it came from, then the fact that made
the law held, broken, or unstated. ``cited_statement`` builds that sentence
and is the only builder. The fact stays the checkable one: the tags, the
station, the valve, or the act. A fact that contains the word confidence,
probability, weight, magnitude, or score is refused, and no sentence is
returned. The refusal is the word. It is not a threshold, and it does not
search a number. A decimal the plant already uses is allowed when none of
those words appear. ``law_page`` refuses a break whose statement does not
start with that law's name, and it refuses a statement that contains one of
those words. Both checks run with the exact-type check, before the page is
ordered. An uncited break is not placed. A break that carries a score-word
is not placed, and nothing else in that call is placed either.

The laws are the predicates already written for a joint in-band move, a walk of
the frozen length, a handoff, and a program transfer, plus one directory law:
a write from a station outside the set the plant named. A station inside that
set is silence for the directory law. An empty set means the directory was not
stated, so the law is unstated. This module does not invent a known-station
unexpected-function law, a band, or an attack class. It does not read a learned
graph, and it does not score a probability. A Modbus function code stays
refused by the transfer module. A function code is not a station. The caller
supplies the station name. This page has no inlet for a function code.

The controller comparison is the PLC1 rule, copied here as literals. Both
valve modes must be the release value. The input valve is closed when the
level is strictly above its maximum and open when the level is strictly below
its minimum. Inside that band, including either end, that side does not break.
The output valve is closed when the bottle is strictly above its maximum or
the belt is strictly past the filler, and open otherwise. Manual mode means
this automatic law was not stated. There is no divisor, no onset score, no
third-peak calibration, and no residual on this law. Omitting the sample
leaves the four older laws and the directory law unchanged.

No corpus is scored here. The frozen residual detector is not called. This
module does not import that detector or the other page builders. This page
is not a field result.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Final

from phos.atlas.band_handoff import band_handoffs
from phos.atlas.handoff_booking import TagBooking, handoff_notices
from phos.atlas.joint_setpoint import SetpointStep, joint_moves
from phos.atlas.program_transfer import (
    Booking,
    ProgramAct,
    TransferWorkOrder,
    transfer_report,
)
from phos.atlas.subfloor_walk import subfloor_walks

__all__ = [
    "ALLOWED_WRITER",
    "BAND_HANDOFF",
    "CONTROLLER_VALVE",
    "JOINT_MOVE",
    "LAWS",
    "OPERATOR_PAGE_CEILING",
    "PROGRAM_TRANSFER",
    "SUBFLOOR_WALK",
    "ControllerSample",
    "DeclaredLaw",
    "LawBreak",
    "LawOutcome",
    "LawRegister",
    "LawReport",
    "Standing",
    "WriterWrite",
    "assess_plant",
    "breaks_from_plant",
    "cited_statement",
    "law_page",
    "page_from_report",
]

logger = logging.getLogger(__name__)

OPERATOR_PAGE_CEILING: Final = 8
"""Alerts per shift in ``docs/v1-roadmap.md`` section 2.0. Not searched."""

_SCORE_WORDS: Final[tuple[str, ...]] = (
    "confidence",
    "probability",
    "weight",
    "magnitude",
    "score",
)
"""Words that refuse a sentence. The refusal is the word, not a number."""

_JOINT_UNSTATED: Final = "No setpoint steps were supplied, so joint_move was not checked."
_JOINT_HELD: Final = "Setpoint steps were supplied, and they are not a joint move."
_WALK_UNSTATED: Final = "No setpoint steps were supplied, so subfloor_walk was not checked."
_WALK_HELD: Final = "Setpoint steps were supplied, and they are not a walk of the frozen length."
_HANDOFF_UNSTATED: Final = "No setpoint steps were supplied, so band_handoff was not checked."
_HANDOFF_HELD: Final = "Setpoint steps were supplied, and they are not an open handoff."
_TRANSFER_UNSTATED: Final = (
    "No program transfers were supplied, so program_transfer was not checked."
)
_TRANSFER_HELD: Final = (
    "Program transfers were supplied, and a booking or a work order covers each act."
)
_WRITER_SET_UNSTATED: Final = "The allowed set is empty, so allowed_writer was not stated."
_WRITER_WRITES_UNSTATED: Final = "No writes were supplied, so allowed_writer was not checked."
_WRITER_HELD: Final = "Writes were supplied, and every station is inside the declared set."
_CONTROLLER_ABSENT: Final = (
    "No controller sample was supplied, so controller_valve was not checked."
)
_CONTROLLER_MANUAL: Final = "A valve mode is not release, so controller_valve was not stated."
_CONTROLLER_HELD: Final = (
    "A controller sample was supplied, both modes are release, and neither side disagrees."
)
_UNCHECKED_UNSTATED: Final = "This page has no check for this law, so it was not stated."

# PLC1 at bcfd1844d3f063850c69f2643f6a052bac03d8ec, which is not in this
# repository, as quoted in data/phos-icssim-dev/roles.toml. Not tuned.
_VALVE_CLOSED: Final = 0.0
"""What the quoted line writes to close a valve."""
_VALVE_OPEN: Final = 1.0
"""What the quoted line writes to open a valve."""
_MODE_RELEASE: Final = 3.0
"""The release value the generator already uses. Any other mode is manual."""
_BELT_PAST_FILLER: Final = 1.0
"""The belt distance the quoted output line compares with a strict greater-than."""


class Standing(StrEnum):
    """Whether a declared law is held, broken, or unstated.

    The values are the words ``held``, ``broken``, and ``unstated``. They are
    not numbers. Nothing on the page sorts by them.
    """

    HELD = "held"
    BROKEN = "broken"
    UNSTATED = "unstated"


@dataclass(frozen=True)
class DeclaredLaw:
    """A law the plant or the operator already declared.

    Attributes:
        name: The law's name.
        statement: What was declared, in words. No numeric threshold.
    """

    name: str
    statement: str


@dataclass(frozen=True)
class LawBreak:
    """One declared law the supplied facts make false.

    Attributes:
        name: The law that is false.
        time: When the broken fact happened. Timezone-aware.
        statement: The law name, then the broken fact, in a sentence a person
            can check.
    """

    name: str
    time: datetime
    statement: str


@dataclass(frozen=True)
class LawOutcome:
    """One declared law after a single check.

    Attributes:
        name: The law's name.
        standing: Held, broken, or unstated. A word, not a rank.
        statement: The law name, then what the check found, in a sentence a
            person can read.
        time: When the broken fact happened. ``None`` unless ``standing`` is
            broken, so a held or unstated outcome cannot be ranked by a clock.
    """

    name: str
    standing: Standing
    statement: str
    time: datetime | None = None

    def __post_init__(self) -> None:
        """Refuse a time on a held or unstated outcome, and a broken one with none."""
        if not isinstance(self.standing, Standing):
            raise ValueError("standing is held, broken, or unstated")
        if self.standing is Standing.BROKEN:
            if self.time is None:
                raise ValueError("a broken outcome names its time")
            _require_aware(self.time, "time")
            return
        if self.time is not None:
            raise ValueError("a held or unstated outcome has no time")


@dataclass(frozen=True)
class LawRegister:
    """The laws a plant has named as in force.

    An empty register names nothing, so nothing is evaluated. The same name
    twice is refused. The field is the laws themselves. There is no weight.

    Attributes:
        laws: The declared laws. Each name appears once.
    """

    laws: tuple[DeclaredLaw, ...]

    def __post_init__(self) -> None:
        """Refuse a register that names one law twice."""
        seen: set[str] = set()
        for law in self.laws:
            if law.name in seen:
                raise ValueError(f"duplicate law name: {law.name}")
            seen.add(law.name)


@dataclass(frozen=True)
class LawReport:
    """Held, broken, and unstated laws from one pass over the inlet.

    Attributes:
        held: Declared laws whose facts were checked and kept silent. No slot.
        broken: Declared laws the facts make false. The only list that can take a slot.
        unstated: Declared laws with no facts to check. No slot.
    """

    held: tuple[LawOutcome, ...]
    broken: tuple[LawBreak, ...]
    unstated: tuple[LawOutcome, ...]

    def __post_init__(self) -> None:
        """Refuse a law that appears in more than one list."""
        _refuse_mixed_standings(self)


@dataclass(frozen=True)
class WriterWrite:
    """One write from a station the caller named.

    A function code is not a station. This record does not infer one, and it
    does not read a learned graph. There is no score, confidence, probability,
    weight, or magnitude.

    Attributes:
        station: The station name the caller supplied. Empty is refused.
        at: When the write happened. Timezone-aware when the inlet is checked.
    """

    station: str
    at: datetime

    def __post_init__(self) -> None:
        """Refuse a write that does not name its station."""
        if self.station == "":
            raise ValueError("station is empty")


@dataclass(frozen=True)
class ControllerSample:
    """One sample of the PLC1 valve comparison.

    The nine measurements are the plant's own tags, under the names this page
    uses. There is no score, confidence, probability, weight, or magnitude.

    Attributes:
        at: When the sample was taken. Timezone-aware.
        level: ``tank_level_value``.
        level_min: ``tank_level_min``.
        level_max: ``tank_level_max``.
        input_valve: ``tank_input_valve_status``.
        input_mode: ``tank_input_valve_mode``.
        bottle_level: ``bottle_level_value``.
        bottle_max: ``bottle_level_max``.
        belt: ``bottle_distance_to_filler_value``.
        output_valve: ``tank_output_valve_status``.
        output_mode: ``tank_output_valve_mode``.
    """

    at: datetime
    level: float
    level_min: float
    level_max: float
    input_valve: float
    input_mode: float
    bottle_level: float
    bottle_max: float
    belt: float
    output_valve: float
    output_mode: float

    def __post_init__(self) -> None:
        """Refuse a sample whose time has no timezone."""
        _require_aware(self.at, "controller time")


JOINT_MOVE: Final = DeclaredLaw(
    name="joint_move",
    statement=(
        "Two or more different tags written inside the ordinary setpoint band, "
        "and joined on the frozen event window, are one move. One tag is silence."
    ),
)
SUBFLOOR_WALK: Final = DeclaredLaw(
    name="subfloor_walk",
    statement=(
        "One tag walked across the ordinary band for the frozen walk length is one walk. "
        "A shorter chain is silence."
    ),
)
BAND_HANDOFF: Final = DeclaredLaw(
    name="band_handoff",
    statement=(
        "The same ordinary value on a second tag after the joint window is a handoff "
        "while no booking names both tags. A booking that names both tags is silence."
    ),
)
PROGRAM_TRANSFER: Final = DeclaredLaw(
    name="program_transfer",
    statement=(
        "An unbooked download, upload, or online edit is a break. A booking that names "
        "the act and covers the time is silence. A function code is not an act."
    ),
)
ALLOWED_WRITER: Final = DeclaredLaw(
    name="allowed_writer",
    statement=(
        "A write from a station outside the declared set is a break. A station inside "
        "the set is silence. An empty set means the law was not stated."
    ),
)
CONTROLLER_VALVE: Final = DeclaredLaw(
    name="controller_valve",
    statement=(
        "When both valve modes are release, the input comparison closes the valve when "
        "the level is strictly above its maximum and opens it when the level is strictly "
        "below its minimum, and inside the band, including either end, that side does not "
        "break. The output comparison closes the valve when the bottle is strictly above "
        "its maximum or the belt is strictly past the filler, and opens it otherwise. "
        "Manual mode means this law was not stated."
    ),
)
LAWS: Final[tuple[DeclaredLaw, ...]] = (
    JOINT_MOVE,
    SUBFLOOR_WALK,
    BAND_HANDOFF,
    PROGRAM_TRANSFER,
    ALLOWED_WRITER,
    CONTROLLER_VALVE,
)

_ACT_WORDS: Final[dict[ProgramAct, str]] = {
    ProgramAct.DOWNLOAD: "download",
    ProgramAct.UPLOAD: "upload",
    ProgramAct.ONLINE_EDIT: "online edit",
}


def _score_word(text: str) -> str | None:
    """Return the first score-word in ``text``, if any.

    The match is the word as a substring, in any case. A decimal is not a
    score-word. This is the same test ``cited_statement`` and ``law_page`` use,
    so a sentence one of them refuses cannot slip through the other.

    Args:
        text: The fact, or the whole sentence a caller is trying to place.

    Returns:
        The score-word, folded, or ``None`` when the text carries none.
    """
    folded = text.casefold()
    for word in _SCORE_WORDS:
        if word in folded:
            return word
    return None


def cited_statement(law: DeclaredLaw, fact: str) -> str:
    """Name the law, then the fact. A score-word is refused.

    The sentence is the law's name, a period, a space, and the fact with
    surrounding whitespace removed. An empty fact is refused. A fact that
    contains confidence, probability, weight, magnitude, or score, in any
    case, is refused, and this function does not return a sentence. A decimal
    the plant already uses is allowed when none of those words appear. This
    function does not search for a number.

    Args:
        law: The declared law the sentence names.
        fact: The checkable fact. It still names the tags, the station, the
            valve, or the act.

    Returns:
        The law name, then the stripped fact.

    Raises:
        ValueError: If ``fact`` is empty after stripping, or if it contains a
            score-word. No sentence is returned in either case.
    """
    cleaned = fact.strip()
    if cleaned == "":
        raise ValueError("a cited fact is not empty")
    word = _score_word(cleaned)
    if word is not None:
        raise ValueError(f"a cited fact does not carry {word}")
    return f"{law.name}. {cleaned}"


def law_page(breaks: Sequence[LawBreak], *, register: LawRegister) -> tuple[LawBreak, ...]:
    """Place broken laws on the operator page.

    Order is time, then law name. At most the operator ceiling stay. An empty
    inlet returns an empty page. A later break is not promoted for being louder
    under a residual, because a break carries no magnitude. A break whose name
    the register did not declare is refused. It is not dropped and it is not
    sorted in. Held and unstated outcomes are not breaks, so this function
    cannot place them.

    A value is admitted only when ``type(item) is LawBreak`` and its statement
    starts with that law's name, a period, and a space, and the statement does
    not contain a score-word. ``isinstance`` is not enough, because a subclass
    can carry a magnitude. Those checks run before the page is ordered. A
    different type raises and is not placed. A statement that does not name
    its law raises and is not placed. A statement that contains confidence,
    probability, weight, magnitude, or score raises and is not placed, and
    nothing else in that call is placed. The ceiling and the sort key are
    unchanged.

    Args:
        breaks: Broken laws the caller already holds.
        register: The laws the plant named. Required. There is no default.

    Returns:
        The earliest breaks, at most ``OPERATOR_PAGE_CEILING``. Fewer than that
        is the whole page.

    Raises:
        ValueError: If a value is not exactly a ``LawBreak``, a statement does
            not start with its law name, a statement contains a score-word, a
            time is naive, or a break's name is not in ``register``.
    """
    names = _law_names(register)
    for item in breaks:
        # isinstance is not enough: a subclass can carry a magnitude.
        admitted = type(item) is LawBreak
        if not admitted:
            raise ValueError("only a LawBreak enters the page")
        if not item.statement.startswith(f"{item.name}. "):
            raise ValueError(f"{item.name} does not name its law")
        word = _score_word(item.statement)
        if word is not None:
            raise ValueError(f"a placed sentence does not carry {word}")
        _require_aware(item.time, "time")
        if item.name not in names:
            raise ValueError(f"{item.name} is not in the register")
    ordered = sorted(breaks, key=lambda item: (item.time, item.name))
    page = tuple(ordered[:OPERATOR_PAGE_CEILING])
    logger.info("law page %s of %s breaks", len(page), len(breaks))
    return page


def page_from_report(report: LawReport, *, register: LawRegister) -> tuple[LawBreak, ...]:
    """Place the report's broken laws on the operator page.

    ``law_page`` is the only function that awards a slot. This function passes
    it ``report.broken`` and nothing else. Held and unstated outcomes are not
    ``LawBreak`` values, so they cannot take one of the eight places. A
    subclass inside that tuple is still a different type, so ``law_page``
    refuses it and it is not placed. A genuine break whose statement does not
    start with its law name is refused there too, and it is not placed. A
    statement that contains a score-word is refused there too, and nothing
    from that call is placed.

    Args:
        report: One assessment of the plant.
        register: The laws the plant named. Required. There is no default.

    Returns:
        The earliest breaks, at most ``OPERATOR_PAGE_CEILING``.

    Raises:
        ValueError: If a value is not exactly a ``LawBreak``, a statement does
            not start with its law name, a statement contains a score-word, a
            time is naive, or a break's name is not in ``register``.
    """
    return law_page(report.broken, register=register)


def assess_plant(
    steps: Sequence[SetpointStep] = (),
    transfers: Sequence[tuple[ProgramAct, datetime]] = (),
    *,
    register: LawRegister,
    bookings: Sequence[Booking] = (),
    work_orders: Sequence[TransferWorkOrder] = (),
    tag_bookings: Sequence[TagBooking] = (),
    writes: Sequence[WriterWrite] = (),
    allowed_stations: frozenset[str] = frozenset(),
    controller: ControllerSample | None = None,
) -> LawReport:
    """Judge each named law once, as held, broken, or unstated.

    A predicate runs only when its law name is in ``register``. Joint, walk,
    and handoff are unstated when ``steps`` is empty. Program transfer is
    unstated when ``transfers`` is empty. Allowed writer is unstated when
    ``writes`` is empty or ``allowed_stations`` is empty. An empty set stays
    unstated even when writes are present, and it is not a break. The controller
    comparison is unstated when ``controller`` is omitted, and unstated when
    either valve mode is not release. An empty inlet is not a break. When the
    inlet has facts and the predicate returns silence, the law is held. When
    the predicate returns an alert, the law is broken, one ``LawBreak`` per
    alert. A station inside the allowed set is silence for ``allowed_writer``
    even when another declared law is broken. An empty register returns three
    empty lists, including when the steps, the writes, or the sample would have
    matched a predicate the plant did not name. A name in the register that no
    predicate placed is unstated, once. It is not dropped, and it is not a
    break. Omitting ``controller`` leaves the four older laws and
    ``allowed_writer`` unchanged.

    Args:
        steps: Setpoint writes the joint, walk, and handoff checks already take.
        transfers: Each program act with the time it happened. The caller supplies
            the act. A function code is not an act.
        register: The laws the plant named. Required. There is no default.
        bookings: Bookings that can cover a program act.
        work_orders: Work orders that can cover a program act when they name it.
        tag_bookings: Bookings that name both tags of a handoff.
        writes: Writes whose station the caller named. A function code is not a
            station, and this function does not infer one.
        allowed_stations: Stations the plant allowed to write. Empty means the
            directory was not stated.
        controller: One PLC1 sample. ``None`` means the comparison was not supplied.

    Returns:
        Held laws ordered by name, broken laws ordered by time then name, and
        unstated laws ordered by name. Held and unstated do not compete with
        broken for the operator ceiling.

    Raises:
        ValueError: If a supplied time is naive, a booking check already written
            rejects the record, or one law would occupy two lists.
    """
    _require_inlet(steps, transfers, bookings, work_orders, tag_bookings, writes)
    names = _law_names(register)
    held: list[LawOutcome] = []
    broken: list[LawBreak] = []
    unstated: list[LawOutcome] = []
    if JOINT_MOVE.name in names:
        _classify(
            _joint_breaks(steps),
            has_facts=len(steps) > 0,
            law=JOINT_MOVE,
            unstated_statement=_JOINT_UNSTATED,
            held_statement=_JOINT_HELD,
            held=held,
            broken=broken,
            unstated=unstated,
        )
    if SUBFLOOR_WALK.name in names:
        _classify(
            _walk_breaks(steps),
            has_facts=len(steps) > 0,
            law=SUBFLOOR_WALK,
            unstated_statement=_WALK_UNSTATED,
            held_statement=_WALK_HELD,
            held=held,
            broken=broken,
            unstated=unstated,
        )
    if BAND_HANDOFF.name in names:
        _classify(
            _handoff_breaks(steps, tag_bookings),
            has_facts=len(steps) > 0,
            law=BAND_HANDOFF,
            unstated_statement=_HANDOFF_UNSTATED,
            held_statement=_HANDOFF_HELD,
            held=held,
            broken=broken,
            unstated=unstated,
        )
    if PROGRAM_TRANSFER.name in names:
        _classify(
            _transfer_breaks(transfers, bookings, work_orders),
            has_facts=len(transfers) > 0,
            law=PROGRAM_TRANSFER,
            unstated_statement=_TRANSFER_UNSTATED,
            held_statement=_TRANSFER_HELD,
            held=held,
            broken=broken,
            unstated=unstated,
        )
    if ALLOWED_WRITER.name in names:
        directory_stated = len(allowed_stations) > 0
        _classify(
            _writer_breaks(writes, allowed_stations),
            has_facts=directory_stated and len(writes) > 0,
            law=ALLOWED_WRITER,
            unstated_statement=(
                _WRITER_SET_UNSTATED if not directory_stated else _WRITER_WRITES_UNSTATED
            ),
            held_statement=_WRITER_HELD,
            held=held,
            broken=broken,
            unstated=unstated,
        )
    if CONTROLLER_VALVE.name in names:
        if controller is None:
            _classify(
                (),
                has_facts=False,
                law=CONTROLLER_VALVE,
                unstated_statement=_CONTROLLER_ABSENT,
                held_statement=_CONTROLLER_HELD,
                held=held,
                broken=broken,
                unstated=unstated,
            )
        elif not _modes_released(controller):
            _classify(
                (),
                has_facts=False,
                law=CONTROLLER_VALVE,
                unstated_statement=_CONTROLLER_MANUAL,
                held_statement=_CONTROLLER_HELD,
                held=held,
                broken=broken,
                unstated=unstated,
            )
        else:
            _classify(
                _controller_breaks(controller),
                has_facts=True,
                law=CONTROLLER_VALVE,
                unstated_statement=_CONTROLLER_ABSENT,
                held_statement=_CONTROLLER_HELD,
                held=held,
                broken=broken,
                unstated=unstated,
            )
    listed = {item.name for item in held}
    listed.update(item.name for item in broken)
    listed.update(item.name for item in unstated)
    for law in register.laws:
        if law.name in listed:
            continue
        unstated.append(_listed(law, Standing.UNSTATED, _UNCHECKED_UNSTATED))
    report = LawReport(
        held=tuple(sorted(held, key=lambda item: item.name)),
        broken=tuple(sorted(broken, key=lambda item: (item.time, item.name))),
        unstated=tuple(sorted(unstated, key=lambda item: item.name)),
    )
    logger.info(
        "declared-law assessment held %s broken %s unstated %s",
        len(report.held),
        len(report.broken),
        len(report.unstated),
    )
    return report


def breaks_from_plant(
    steps: Sequence[SetpointStep] = (),
    transfers: Sequence[tuple[ProgramAct, datetime]] = (),
    *,
    register: LawRegister,
    bookings: Sequence[Booking] = (),
    work_orders: Sequence[TransferWorkOrder] = (),
    tag_bookings: Sequence[TagBooking] = (),
    writes: Sequence[WriterWrite] = (),
    allowed_stations: frozenset[str] = frozenset(),
    controller: ControllerSample | None = None,
) -> tuple[LawBreak, ...]:
    """Return the broken list from one assessment of the plant.

    The predicates run inside ``assess_plant``. This function returns that
    report's broken tuple, so a second pass cannot disagree. A held or
    unstated law contributes nothing here. The ceiling is applied by
    ``law_page``, not here. Omitting ``writes`` and ``allowed_stations`` leaves
    the joint, walk, handoff, and transfer laws as they were. Omitting
    ``controller`` leaves the four older laws and ``allowed_writer`` unchanged.

    Args:
        steps: Setpoint writes the joint, walk, and handoff checks already take.
        transfers: Each program act with the time it happened. The caller supplies
            the act. A function code is not an act.
        register: The laws the plant named. Required. There is no default.
        bookings: Bookings that can cover a program act.
        work_orders: Work orders that can cover a program act when they name it.
        tag_bookings: Bookings that name both tags of a handoff.
        writes: Writes whose station the caller named. A function code is not a
            station, and this function does not infer one.
        allowed_stations: Stations the plant allowed to write. Empty means the
            directory was not stated.
        controller: One PLC1 sample. ``None`` means the comparison was not supplied.

    Returns:
        Every admitted break, earliest time first, then law name. An empty
        inlet, and an empty register, are empty.

    Raises:
        ValueError: If a supplied time is naive, or a booking check already written
            rejects the record.
    """
    broken = assess_plant(
        steps,
        transfers,
        register=register,
        bookings=bookings,
        work_orders=work_orders,
        tag_bookings=tag_bookings,
        writes=writes,
        allowed_stations=allowed_stations,
        controller=controller,
    ).broken
    logger.info("declared-law breaks %s", len(broken))
    return broken


def _law_names(register: LawRegister) -> frozenset[str]:
    """Return the law names the plant named."""
    return frozenset(law.name for law in register.laws)


def _listed(law: DeclaredLaw, standing: Standing, statement: str) -> LawOutcome:
    """One held or unstated outcome. It carries no time.

    ``statement`` is the fact. The sentence on the outcome names ``law``,
    then that fact.
    """
    if standing is Standing.BROKEN:
        raise ValueError("a broken law is a break, not a listed outcome")
    return LawOutcome(
        name=law.name,
        standing=standing,
        statement=cited_statement(law, statement),
    )


def _classify(
    found: tuple[LawBreak, ...],
    *,
    has_facts: bool,
    law: DeclaredLaw,
    unstated_statement: str,
    held_statement: str,
    held: list[LawOutcome],
    broken: list[LawBreak],
    unstated: list[LawOutcome],
) -> None:
    """Place one declared law into exactly one of the three lists.

    Args:
        found: Alerts from the one predicate call for ``law``.
        has_facts: Whether the inlet had facts that law can be checked against.
        law: The declared law being placed.
        unstated_statement: The sentence used when the inlet has no facts.
        held_statement: The sentence used when the predicate returned silence.
        held: Outcomes whose facts were checked and kept silent.
        broken: Breaks the predicate returned.
        unstated: Outcomes with no facts to check.

    Raises:
        ValueError: If the predicate returned a break when the inlet had no facts.
    """
    if not has_facts:
        if found:
            raise ValueError(f"{law.name} returned a break with no facts to check")
        unstated.append(_listed(law, Standing.UNSTATED, unstated_statement))
        return
    if found:
        broken.extend(found)
        return
    held.append(_listed(law, Standing.HELD, held_statement))


def _names_at(outcomes: tuple[LawOutcome, ...], standing: Standing) -> set[str]:
    """Return the law names in ``outcomes``, refusing a mismatched standing."""
    names: set[str] = set()
    for item in outcomes:
        if item.standing is not standing:
            raise ValueError(f"{item.name} is {item.standing.value}, not {standing.value}")
        if item.name in names:
            raise ValueError(f"duplicate law name: {item.name}")
        names.add(item.name)
    return names


def _refuse_mixed_standings(report: LawReport) -> None:
    """Raise when one law is held and broken, or any other pair of lists."""
    held = _names_at(report.held, Standing.HELD)
    unstated = _names_at(report.unstated, Standing.UNSTATED)
    broken = {item.name for item in report.broken}
    overlap = held & unstated | held & broken | unstated & broken
    if overlap:
        joined = ", ".join(sorted(overlap))
        raise ValueError(f"a law has two standings: {joined}")


def _joint_breaks(steps: Sequence[SetpointStep]) -> tuple[LawBreak, ...]:
    """One break per joint move. One tag contributes nothing."""
    found: list[LawBreak] = []
    for move in joint_moves(steps):
        found.append(
            LawBreak(
                name=JOINT_MOVE.name,
                time=move.at,
                statement=cited_statement(
                    JOINT_MOVE,
                    (
                        f"Tags {_names(move.tags)} were written inside the ordinary band "
                        "and joined on the frozen event window."
                    ),
                ),
            )
        )
    return tuple(found)


def _walk_breaks(steps: Sequence[SetpointStep]) -> tuple[LawBreak, ...]:
    """One break per walk, timed at the first step. A short chain contributes nothing."""
    found: list[LawBreak] = []
    for walk in subfloor_walks(steps):
        found.append(
            LawBreak(
                name=SUBFLOOR_WALK.name,
                time=walk.at,
                statement=cited_statement(
                    SUBFLOOR_WALK,
                    (
                        f"Tag {walk.tag} was walked across the ordinary band "
                        "for the frozen walk length."
                    ),
                ),
            )
        )
    return tuple(found)


def _handoff_breaks(
    steps: Sequence[SetpointStep],
    tag_bookings: Sequence[TagBooking],
) -> tuple[LawBreak, ...]:
    """One break per handoff that is still an alert. A covering booking is silence."""
    handoffs = band_handoffs(steps)
    notices = handoff_notices(steps, tag_bookings)
    if len(handoffs) != len(notices):
        raise ValueError("handoff and notice disagree")
    found: list[LawBreak] = []
    for handoff, notice in zip(handoffs, notices, strict=True):
        if handoff.at != notice.at or handoff.tags != notice.tags:
            raise ValueError("handoff and notice disagree")
        if not notice.alert:
            continue
        found.append(
            LawBreak(
                name=BAND_HANDOFF.name,
                time=notice.at,
                statement=cited_statement(
                    BAND_HANDOFF,
                    (
                        f"Tags {_names(notice.tags)} share one ordinary value after the joint "
                        "window, and no booking names both tags."
                    ),
                ),
            )
        )
    return tuple(found)


def _writer_breaks(
    writes: Sequence[WriterWrite],
    allowed_stations: frozenset[str],
) -> tuple[LawBreak, ...]:
    """One break per write whose station is outside the declared set.

    An empty set returns nothing. The caller records that inlet as unstated.
    A station inside the set contributes nothing. The same station on two
    writes is two breaks.

    Args:
        writes: Writes whose station the caller named.
        allowed_stations: Stations the plant allowed to write.

    Returns:
        One break per outside write, in inlet order. The statement names the
        station.
    """
    if not allowed_stations:
        return ()
    found: list[LawBreak] = []
    for write in writes:
        if write.station in allowed_stations:
            continue
        found.append(
            LawBreak(
                name=ALLOWED_WRITER.name,
                time=write.at,
                statement=cited_statement(
                    ALLOWED_WRITER,
                    f"Station {write.station} wrote, and it is outside the declared set.",
                ),
            )
        )
    return tuple(found)


def _modes_released(sample: ControllerSample) -> bool:
    """Return whether both valve modes are the plant's release value."""
    return sample.input_mode == _MODE_RELEASE and sample.output_mode == _MODE_RELEASE


def _input_required(sample: ControllerSample) -> float | None:
    """Return the input value the quoted line writes, or None inside the band.

    The maximum comparison is first, the same ``if`` / ``elif`` order as the
    quoted line. Either end of the band is inside it: the comparison is strict.

    Args:
        sample: One controller sample whose modes are already release.

    Returns:
        ``0.0`` when the level is strictly above its maximum, ``1.0`` when the
        level is strictly below its minimum, and None otherwise.
    """
    if sample.level > sample.level_max:
        return _VALVE_CLOSED
    if sample.level < sample.level_min:
        return _VALVE_OPEN
    return None


def _output_required(sample: ControllerSample) -> float:
    """Return the output value the quoted line writes.

    Strictly above the bottle maximum, or strictly past the filler, closes the
    valve. Every other reading opens it, including either equality.

    Args:
        sample: One controller sample whose modes are already release.

    Returns:
        ``0.0`` when the close test is true, and ``1.0`` otherwise.
    """
    if sample.bottle_level > sample.bottle_max or sample.belt > _BELT_PAST_FILLER:
        return _VALVE_CLOSED
    return _VALVE_OPEN


def _plain(number: float) -> str:
    """Render a valve value the way the plant writes a whole number."""
    return format(number, ".12g")


def _valve_break(side: str, actual: float, required: float, at: datetime) -> LawBreak:
    """One break naming the valve and the value the rule required.

    Args:
        side: ``input valve`` or ``output valve``.
        actual: The valve in the sample.
        required: The value the quoted line writes.
        at: When the sample was taken.

    Returns:
        A break with no score. The statement names the valve and the required value.
    """
    return LawBreak(
        name=CONTROLLER_VALVE.name,
        time=at,
        statement=cited_statement(
            CONTROLLER_VALVE,
            f"The {side} is {_plain(actual)}, and the rule required {_plain(required)}.",
        ),
    )


def _controller_breaks(sample: ControllerSample) -> tuple[LawBreak, ...]:
    """One break per side whose valve is not the value the quoted line writes.

    An input reading inside the band, including either end, contributes nothing.
    The output side always has a required value. Both breaks, when both sides
    disagree, carry the sample time. This function does not decide the standing.
    The caller passes it to the one-list rule, so a break is not also held.

    Args:
        sample: One sample whose modes are both release.

    Returns:
        Zero, one, or two breaks, input side first.
    """
    found: list[LawBreak] = []
    required_input = _input_required(sample)
    if required_input is not None and sample.input_valve != required_input:
        found.append(_valve_break("input valve", sample.input_valve, required_input, sample.at))
    required_output = _output_required(sample)
    if sample.output_valve != required_output:
        found.append(_valve_break("output valve", sample.output_valve, required_output, sample.at))
    return tuple(found)


def _transfer_breaks(
    transfers: Sequence[tuple[ProgramAct, datetime]],
    bookings: Sequence[Booking],
    work_orders: Sequence[TransferWorkOrder],
) -> tuple[LawBreak, ...]:
    """One break per unbooked act. A covering booking or work order is silence."""
    found: list[LawBreak] = []
    for act, at in transfers:
        report = transfer_report(act, bookings, work_orders, at=at)
        if not report.alert:
            continue
        found.append(
            LawBreak(
                name=PROGRAM_TRANSFER.name,
                time=at,
                statement=cited_statement(
                    PROGRAM_TRANSFER,
                    (
                        f"An unbooked {_ACT_WORDS[act]} was supplied, "
                        "and no booking covers that act."
                    ),
                ),
            )
        )
    return tuple(found)


def _names(tags: Sequence[str]) -> str:
    """Join tag names so a person can read which ones moved."""
    if len(tags) == 2:
        return f"{tags[0]} and {tags[1]}"
    if len(tags) > 2:
        head = ", ".join(tags[:-1])
        return f"{head}, and {tags[-1]}"
    if len(tags) == 1:
        return tags[0]
    raise ValueError("a break names at least one tag")


def _require_inlet(
    steps: Sequence[SetpointStep],
    transfers: Sequence[tuple[ProgramAct, datetime]],
    bookings: Sequence[Booking],
    work_orders: Sequence[TransferWorkOrder],
    tag_bookings: Sequence[TagBooking],
    writes: Sequence[WriterWrite],
) -> None:
    """Raise when any supplied time is naive."""
    for step in steps:
        _require_aware(step.at, "setpoint time")
    for _act, at in transfers:
        _require_aware(at, "transfer time")
    for booking in bookings:
        _require_aware(booking.start, "booking start")
        _require_aware(booking.end, "booking end")
    for order in work_orders:
        _require_aware(order.start, "work order start")
        _require_aware(order.end, "work order end")
    for tag_booking in tag_bookings:
        _require_aware(tag_booking.start, "tag booking start")
        _require_aware(tag_booking.end, "tag booking end")
    for write in writes:
        _require_aware(write.at, "write time")


def _require_aware(moment: datetime, name: str) -> None:
    """Raise when ``moment`` has no timezone."""
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")

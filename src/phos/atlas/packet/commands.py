"""The command stream, normalised: who commanded whom, when, and over what.

P1 answers "what does this frame say". This module answers "who did what to whom", which is the
form every behavioural question in P2 is asked in. It sits between P1's typed messages and the two
things built on them — `behaviour` (what a device's commanding *looks like*) and `graph` (who a
device commands *at all*) — so that the judgement calls both depend on are made once, here, and
tested once.

There are three of them.

**A device is its network address, and nothing finer.** `device_entity_id` maps an IP to a stable
`EntityId` of the form ``ent_10.0.0.9``. Readable rather than opaque, following
`phos.models.FEATURE_LEVEL_ENTITY_ID`, because an operator asking "which device is this?" should
not need a lookup table to find out. The honest limits travel with it: NAT hides many devices
behind one address, DHCP moves an address between devices, and a Modbus gateway fronts several
units behind one. The gateway case is the one this module can see, so `CommandEvent.unit_id`
preserves the sub-address without folding it into identity — a second protocol would carry a
different notion of sub-address, and identities that changed shape by protocol could not be
compared. Refining the granularity is a later PART's decision, and it needs a *declared* device map
rather than an inference, for the reasons `phos.atlas.topology` sets out.

**Only a request is a command.** A response is the device answering, not acting, and `Direction`
``UNKNOWN`` is P1 reporting that the transport could not settle which end was which. Reading either
as a command would attribute an action to whichever end happened to send the bytes. Both are
counted instead.

**Nothing is silently dropped, so coverage stays measurable.** `CommandStreamStats` counts every
result into exactly one bucket and `accounts_for_every_result` reconciles them, the same discipline
`CaptureStats` applies one layer down. The bucket worth knowing about is ``uninterpreted``: a
message from a protocol that has a dissector but no command interpretation here. That is a gap in
*this* module, distinct from `UnparsedMessage`'s gap in dissection, and a stream that is mostly
uninterpreted must not read as a stream with no commands in it.

**No `Entity` objects are minted.** Naming a device a PLC, an HMI or an engineering workstation
from its traffic is an inference, and `EntityType`'s industrial set has no member for "a device we
have not been told the type of". Observations reference entities by id and the store does not
require the entity to exist, so P2 emits ids and leaves typing to whoever is actually told.
"""

import logging
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from phos.atlas.packet.dissect import DissectionResult
from phos.atlas.packet.frame import FrameSource
from phos.atlas.packet.messages import (
    MAX_BYTE_VALUE,
    MAX_REGISTER_VALUE,
    Direction,
    MalformedFrame,
    ModbusMessage,
    UnparsedMessage,
)
from phos.atlas.packet.modbus import FunctionCode
from phos.ontology import ENTITY_PREFIX, EntityId, UtcDatetime

__all__ = [
    "REGISTER_WRITE_FUNCTIONS",
    "WRITE_FUNCTIONS",
    "CommandEvent",
    "CommandStreamStats",
    "Window",
    "command_events",
    "device_entity_id",
    "format_frame_ranges",
    "frame_ranges",
    "is_register_write",
    "is_write",
    "stream_span",
    "tile_windows",
    "window_index",
]

logger = logging.getLogger(__name__)

WRITE_FUNCTIONS: Final = frozenset(
    {
        FunctionCode.WRITE_SINGLE_COIL,
        FunctionCode.WRITE_SINGLE_REGISTER,
        FunctionCode.WRITE_MULTIPLE_COILS,
        FunctionCode.WRITE_MULTIPLE_REGISTERS,
    }
)
"""Function codes that change plant state rather than read it.

Membership is by explicit enumeration, never by inference from the code's value or its name. An
unrecognised code — including an exception code, which has bit 7 set and could be mistaken for a
high-numbered function — is *not* a write, because attributing a write a device never made would
manufacture the most serious kind of evidence Atlas can hold.
"""

REGISTER_WRITE_FUNCTIONS: Final = frozenset(
    {FunctionCode.WRITE_SINGLE_REGISTER, FunctionCode.WRITE_MULTIPLE_REGISTERS}
)
"""Writes whose payload is a 16-bit register value, and therefore comparable across messages.

Coil writes are excluded on purpose. Function 5 carries the raw 16-bit field ``0x0000`` or
``0xFF00``; function 15 carries bits unpacked to ``0`` or ``1``. Both mean "on" or "off", in two
encodings three orders of magnitude apart, and a value range computed over the pair would describe
neither. Coil write *activity* is still visible — in the per-function counts and in the write
address features — so nothing is lost but the meaningless number.
"""


def device_entity_id(ip: str) -> EntityId:
    """Return the stable entity id for the device at ``ip``.

    Args:
        ip: The address in presentation form, as `Endpoint.ip` carries it.

    Returns:
        ``ent_<ip>`` — deterministic, so two runs over one capture agree (Constitution §3.7), and
        readable, so a feature keyed to it names its device without a lookup (§3.2).

    Raises:
        ValueError: If ``ip`` is empty. A blank id would merge every unidentified device into one
            entity and describe a device that does not exist.
    """
    if not ip:
        raise ValueError("a device entity id needs a non-empty address")
    return f"{ENTITY_PREFIX}_{ip}"


def is_write(function_code: int) -> bool:
    """Return whether ``function_code`` changes plant state. See `WRITE_FUNCTIONS`."""
    return function_code in WRITE_FUNCTIONS


def is_register_write(function_code: int) -> bool:
    """Return whether ``function_code`` writes 16-bit registers. See `REGISTER_WRITE_FUNCTIONS`."""
    return function_code in REGISTER_WRITE_FUNCTIONS


class CommandEvent(BaseModel):
    """One command, reduced to the facts a behavioural model needs, provenance intact.

    A projection of `ModbusMessage` rather than a replacement for it: everything here is already on
    the message, and the point of the narrower type is that `behaviour` and `graph` agree on which
    of those fields a command *is*.

    Attributes:
        issuer: Entity id of the device that issued the command.
        target: Entity id of the device it was issued to.
        issuer_ip: The issuer's address, kept so context and error messages can name it.
        target_ip: The target's address.
        protocol: The protocol the command was decoded from.
        function_code: The raw function code, exactly as it arrived. Unrecognised codes are kept
            rather than normalised — an unusual code on a known link is precisely what `graph`
            exists to surface.
        function_name: P1's readable name for the code.
        unit_id: The gateway sub-address the message carried. Preserved, deliberately not part of
            `target`; see the module docstring.
        reference_address: Starting coil or register address, where the wire carried one.
        quantity: How many coils or registers, where the wire carried one.
        values: Decoded data, read as `ModbusMessage.values` documents.
        timestamp: When the frame was captured, UTC.
        source: The capture and frame index it came from.
    """

    model_config = ConfigDict(frozen=True)

    issuer: EntityId = Field(min_length=1)
    target: EntityId = Field(min_length=1)
    issuer_ip: str = Field(min_length=1)
    target_ip: str = Field(min_length=1)
    protocol: str = Field(min_length=1)
    function_code: int = Field(ge=0, le=MAX_BYTE_VALUE)
    function_name: str = Field(min_length=1)
    unit_id: int = Field(ge=0, le=MAX_BYTE_VALUE)
    reference_address: int | None = Field(default=None, ge=0, le=MAX_REGISTER_VALUE)
    quantity: int | None = Field(default=None, ge=0)
    values: tuple[int, ...] = ()
    timestamp: UtcDatetime
    source: FrameSource


@dataclass
class CommandStreamStats:
    """Running count of what a message stream contained and how much of it became commands.

    Mutable and owned by the caller, matching `CaptureStats`: `command_events` is lazy, so the
    counts are only complete once the iterator is exhausted.

    Attributes:
        results_seen: Every result taken off the stream.
        commands: Results that became a `CommandEvent`.
        responses: Devices answering rather than acting.
        undirected: Messages P1 could not assign a direction to.
        unparsed: Traffic no dissector claimed — a gap in *dissection*.
        uninterpreted: Messages a dissector decoded that this module cannot read as commands — a
            gap in *interpretation*. Counted apart from `unparsed` because the two are fixed in
            different places, and a stream that is mostly one must not read as the other.
        malformed: Frames a dissector claimed and refused.
    """

    results_seen: int = 0
    commands: int = 0
    responses: int = 0
    undirected: int = 0
    unparsed: int = 0
    uninterpreted: int = 0
    malformed: int = 0

    def accounts_for_every_result(self) -> bool:
        """Whether every result seen landed in exactly one outcome counter.

        Returns:
            True when the six outcome counters sum to `results_seen`. A False means a result was
            lost, which would make every coverage number taken from these counts wrong.
        """
        return self.results_seen == (
            self.commands
            + self.responses
            + self.undirected
            + self.unparsed
            + self.uninterpreted
            + self.malformed
        )


def command_events(
    results: Iterable[DissectionResult], stats: CommandStreamStats | None = None
) -> Iterator[CommandEvent]:
    """Turn a dissected message stream into the commands within it, lazily.

    Args:
        results: What `dissect_capture` yields. Consumed one at a time, so a gigabyte capture
            never has to be held in memory here.
        stats: Optional caller-owned accumulator. Everything that did *not* become a command is
            counted there, which is the only way to tell a quiet network from an unreadable one.

    Yields:
        One `CommandEvent` per request, in stream order.
    """
    stats = stats if stats is not None else CommandStreamStats()
    for result in results:
        stats.results_seen += 1
        event = _classify(result, stats)
        if event is not None:
            yield event


def _classify(result: DissectionResult, stats: CommandStreamStats) -> CommandEvent | None:
    """Count one result into its bucket and return the command it is, if it is one.

    The order of the checks is the definition of the buckets and is deliberately explicit:
    `UnparsedMessage` is an `IcsMessage` carrying `Direction.UNKNOWN`, so testing direction before
    type would file every unclaimed frame as undirected traffic and hide the dissection gap.
    """
    if isinstance(result, MalformedFrame):
        stats.malformed += 1
        return None
    if isinstance(result, UnparsedMessage):
        stats.unparsed += 1
        return None
    if not isinstance(result, ModbusMessage):
        # A dissector exists for this protocol, but nothing here knows how to read its commands.
        # A second protocol earns a branch above this line; until then the gap is a number.
        stats.uninterpreted += 1
        return None
    if result.direction is Direction.RESPONSE:
        stats.responses += 1
        return None
    if result.direction is Direction.UNKNOWN:
        stats.undirected += 1
        return None

    stats.commands += 1
    return CommandEvent(
        issuer=device_entity_id(result.src.ip),
        target=device_entity_id(result.dst.ip),
        issuer_ip=result.src.ip,
        target_ip=result.dst.ip,
        protocol=result.protocol,
        function_code=result.function_code,
        function_name=result.function_name,
        unit_id=result.unit_id,
        reference_address=result.reference_address,
        quantity=result.quantity,
        values=result.values,
        timestamp=result.timestamp,
        source=result.source,
    )


def stream_span(results: Sequence[DissectionResult]) -> tuple[datetime, datetime] | None:
    """Return the period a stream covers, or ``None`` if it is empty.

    Args:
        results: Every result the stream produced — commands, responses, unclaimed traffic and
            refusals alike.

    Returns:
        ``(earliest, latest)`` timestamp.

    Note:
        Deliberately computed over *every* result rather than over the commands. Unparsed traffic
        and refused frames are still evidence that the wire was live at that instant, and a span
        drawn from commands alone would end at the last command — making a device that fell silent
        at the end of a capture look as though the capture ended with it.
    """
    if not results:
        return None
    timestamps = [result.timestamp for result in results]
    return (min(timestamps), max(timestamps))


def format_frame_ranges(bounds: Mapping[str, tuple[int, int]]) -> str:
    """Render per-capture frame index bounds as ``path:first-last``, joined by ``;``.

    Args:
        bounds: ``{capture path: (lowest index, highest index)}``.

    Returns:
        The rendered ranges, sorted by capture path so the string is stable across runs.

    Note:
        A range rather than a list of every index: a busy window holds thousands of frames, and
        the range together with the window bounds is enough to recompute the value exactly. It is
        kept **per capture** because a frame index means nothing without the file it counts
        within, so pooling two captures' indices would produce a range that points at neither.
    """
    return ";".join(f"{capture}:{low}-{high}" for capture, (low, high) in sorted(bounds.items()))


def frame_ranges(events: Iterable[CommandEvent]) -> str:
    """Return the `format_frame_ranges` rendering of the frames ``events`` came from."""
    bounds: dict[str, tuple[int, int]] = {}
    for event in events:
        index = event.source.frame_index
        low, high = bounds.get(event.source.capture, (index, index))
        bounds[event.source.capture] = (min(low, index), max(high, index))
    return format_frame_ranges(bounds)


class Window(BaseModel):
    """One half-open slice of time, ``[start, end)``, that features are computed over.

    Attributes:
        index: Position in the tiling, from zero. Carried so an ordering can be stated without
            comparing timestamps.
        start: Inclusive lower bound, UTC.
        end: Exclusive upper bound, UTC.

    Invariants:
        ``start <= end``.
    """

    model_config = ConfigDict(frozen=True)

    index: int = Field(ge=0)
    start: UtcDatetime
    end: UtcDatetime

    @model_validator(mode="after")
    def _check_bounds(self) -> Self:
        if self.start > self.end:
            raise ValueError(f"window is inverted: {self.start} > {self.end}")
        return self

    def contains(self, moment: datetime) -> bool:
        """Return whether ``moment`` falls in ``[start, end)``.

        Half-open so consecutive windows partition time: an event on a boundary belongs to exactly
        one window, and a count taken across the tiling neither loses it nor counts it twice.
        """
        return self.start <= moment < self.end


def tile_windows(start: datetime, end: datetime, duration: timedelta) -> tuple[Window, ...]:
    """Tile ``[start, end]`` into consecutive windows of ``duration``, dropping a partial tail.

    Args:
        start: First instant the stream covered.
        end: Last instant it covered.
        duration: Length of one window.

    Returns:
        The windows fully covered by the span, in order. Possibly empty.

    Raises:
        ValueError: If ``duration`` is not positive, or the span is inverted.

    Note:
        **The trailing partial window is dropped rather than reported short.** A device polling
        once a second, measured over the last eleven seconds of a one-minute window, has a command
        count of eleven where every other window says sixty — which is not a quiet device, it is a
        window that ended early, and a baseline learned from both would carry the artefact
        forever. Dropping it is the same choice `phos.atlas.vectorise` makes for a row it cannot
        fill honestly. The cost is real and is the caller's to know: a capture shorter than two
        windows yields at most one, and one shorter than a single window yields none at all.
    """
    if duration <= timedelta(0):
        raise ValueError(f"window duration must be positive, not {duration}")
    if end < start:
        raise ValueError(f"span is inverted: {start} > {end}")

    count = int((end - start) / duration)
    return tuple(
        Window(index=index, start=start + duration * index, end=start + duration * (index + 1))
        for index in range(count)
    )


def window_index(moment: datetime, windows: Sequence[Window]) -> int | None:
    """Return the index of the window holding ``moment``, or ``None`` if no window does.

    Args:
        moment: The instant to place.
        windows: A tiling from `tile_windows`, which is contiguous and ordered.

    Returns:
        The index, or ``None`` for an instant before the tiling starts or inside the partial tail
        `tile_windows` dropped. ``None`` means "this instant is not measured", never "this instant
        is normal".
    """
    if not windows:
        return None
    first = windows[0]
    duration = first.end - first.start
    if moment < first.start or duration <= timedelta(0):
        return None
    index = int((moment - first.start) / duration)
    if index >= len(windows):
        return None
    return index

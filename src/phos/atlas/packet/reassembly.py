"""Bounded TCP reassembly for capture files.

This is not a socket. It never reads the network. A caller hands it segments
already taken from a capture, in capture order, and it returns the contiguous
bytes that became readable, or a `FlowRefusal`.

The caps are PHOS limits from ADR 0345, not protocol maxima. A breach is
returned. It is not an exception, and the segment that would have broken the
cap is not stored. An overlap, including a retransmission of bytes already
delivered, refuses the flow. Keeping one of the two copies would be a splice
the declaration forbids.

`dissect_capture` does not call this module. Modbus stays on one `RawFrame`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Final

from phos.atlas.packet.frame import FrameSource

__all__ = [
    "BYTE_CAP",
    "FLOW_CAP",
    "MAX_BUFFERED_BYTES_PER_FLOW",
    "MAX_CONCURRENT_FLOWS",
    "MAX_OUT_OF_ORDER_SEGMENTS",
    "MAX_SEGMENT_OCTETS",
    "OVERLAP",
    "PDU_LENGTH",
    "REORDER_CAP",
    "SEGMENT_TOO_LONG",
    "ContiguousStream",
    "DeliveredOctets",
    "FlowKey",
    "FlowRefusal",
    "FlowRefusalReason",
    "Reassembler",
    "TcpSegment",
]

MAX_BUFFERED_BYTES_PER_FLOW: Final = 131072
"""Most octets one flow may hold while it waits. ADR 0345."""

MAX_CONCURRENT_FLOWS: Final = 256
"""Most directional flows remembered at once. ADR 0345."""

MAX_OUT_OF_ORDER_SEGMENTS: Final = 16
"""Most segments stored ahead of a gap. The next one is a refusal. ADR 0345."""

MAX_SEGMENT_OCTETS: Final = 65535
"""A captured segment longer than this is refused and not stored. ADR 0345."""

_MOD: Final = 0x1_0000_0000
_HALF: Final = 0x8000_0000


class FlowRefusalReason(str):
    """Why a flow or a segment was refused.

    A string subclass rather than an Enum so a refusal's reason compares equal
    to the literal written in ADR 0345, and so a new reason does not require
    touching `MalformedReason`.
    """


SEGMENT_TOO_LONG: Final[FlowRefusalReason] = FlowRefusalReason("SEGMENT_TOO_LONG")
BYTE_CAP: Final[FlowRefusalReason] = FlowRefusalReason("BYTE_CAP")
FLOW_CAP: Final[FlowRefusalReason] = FlowRefusalReason("FLOW_CAP")
REORDER_CAP: Final[FlowRefusalReason] = FlowRefusalReason("REORDER_CAP")
OVERLAP: Final[FlowRefusalReason] = FlowRefusalReason("OVERLAP")
PDU_LENGTH: Final[FlowRefusalReason] = FlowRefusalReason("PDU_LENGTH")


@dataclass(frozen=True)
class FlowKey:
    """One direction of a TCP conversation.

    Attributes:
        src_ip: Source address, presentation form.
        src_port: Source port.
        dst_ip: Destination address.
        dst_port: Destination port.
    """

    src_ip: str
    src_port: int
    dst_ip: str
    dst_port: int


@dataclass(frozen=True)
class TcpSegment:
    """One captured TCP segment, payload included.

    Attributes:
        key: The direction it travelled.
        seq: The 32-bit sequence number of the first payload octet.
        payload: The TCP payload. Empty is an acknowledgement and changes nothing.
        source: The capture frame it came from, when the caller has one.
    """

    key: FlowKey
    seq: int
    payload: bytes
    source: FrameSource | None = None


@dataclass(frozen=True)
class FlowRefusal:
    """A recorded refusal. Not an exception, and not a decoded message.

    Attributes:
        key: The flow, when one was named.
        reason: Which cap or overlap fired.
        detail: A short explanation a test can assert on.
    """

    key: FlowKey | None
    reason: FlowRefusalReason
    detail: str


@dataclass(frozen=True)
class DeliveredOctets:
    """Contiguous payload octets `Reassembler.push` could hand onward.

    Attributes:
        key: The flow they belong to.
        data: The new contiguous bytes, in order. Empty when the segment was
            stored ahead of a gap or carried no payload.
    """

    key: FlowKey
    data: bytes


def _add(seq: int, count: int) -> int:
    """Advance a sequence number by ``count``, modulo 2^32."""
    return (seq + count) % _MOD


def _ahead(seq: int, base: int) -> int:
    """Signed distance of ``seq`` from ``base``.

    Negative means ``seq`` is before ``base``. The width is the 32-bit TCP
    sequence space.
    """
    delta = (seq - base) & 0xFFFFFFFF
    if delta >= _HALF:
        return delta - _MOD
    return delta


def _ranges_overlap(origin: int, origin_len: int, other: int, other_len: int) -> bool:
    """Whether two non-empty sequence ranges share an octet."""
    if origin_len <= 0 or other_len <= 0:
        return False
    delta = _ahead(other, origin)
    return delta < origin_len and delta + other_len > 0


@dataclass
class _Hold:
    """Mutable state for one flow. Not part of the public surface."""

    next_seq: int | None = None
    ooo: list[tuple[int, bytes]] = field(default_factory=list)
    refusal: FlowRefusal | None = None

    def buffered_octets(self) -> int:
        """Octets sitting ahead of the cursor. Delivered octets are not counted."""
        return sum(len(payload) for _, payload in self.ooo)


class Reassembler:
    """Reassembles directional TCP payloads inside the ADR 0345 caps."""

    def __init__(self) -> None:
        """Start with no flows."""
        self._flows: dict[FlowKey, _Hold] = {}

    @property
    def flow_count(self) -> int:
        """How many flows are remembered, including ones already refused."""
        return len(self._flows)

    def buffered_octets(self, key: FlowKey) -> int:
        """Octets held ahead of the cursor for ``key``. Zero if the flow is unknown."""
        hold = self._flows.get(key)
        if hold is None:
            return 0
        return hold.buffered_octets()

    def out_of_order_count(self, key: FlowKey) -> int:
        """Stored-ahead segments for ``key``. Zero if the flow is unknown."""
        hold = self._flows.get(key)
        if hold is None:
            return 0
        return len(hold.ooo)

    def push(self, segment: TcpSegment) -> DeliveredOctets | FlowRefusal:
        """Accept one segment.

        Args:
            segment: A captured segment. The payload is untrusted.

        Returns:
            The contiguous octets that became available, or a refusal. A refusal
            stores nothing from this segment. A flow already refused stays refused.
        """
        hold = self._flows.get(segment.key)
        if hold is not None and hold.refusal is not None:
            return hold.refusal
        if len(segment.payload) > MAX_SEGMENT_OCTETS:
            return FlowRefusal(
                segment.key,
                SEGMENT_TOO_LONG,
                f"segment is {len(segment.payload)} octets",
            )
        if not segment.payload:
            return DeliveredOctets(segment.key, b"")

        if hold is None:
            if len(self._flows) >= MAX_CONCURRENT_FLOWS:
                return FlowRefusal(
                    segment.key,
                    FLOW_CAP,
                    f"{MAX_CONCURRENT_FLOWS} flows are already open",
                )
            hold = _Hold()
            self._flows[segment.key] = hold

        if hold.next_seq is None:
            hold.next_seq = _add(segment.seq, len(segment.payload))
            return DeliveredOctets(segment.key, segment.payload)

        delta = _ahead(segment.seq, hold.next_seq)
        if delta < 0:
            return self._refuse(hold, segment.key, OVERLAP, "overlaps octets already delivered")
        for stored_seq, stored in hold.ooo:
            if _ranges_overlap(segment.seq, len(segment.payload), stored_seq, len(stored)):
                return self._refuse(hold, segment.key, OVERLAP, "overlaps a stored segment")
        if delta == 0:
            data = segment.payload
            hold.next_seq = _add(hold.next_seq, len(data))
            data += self._drain(hold)
            return DeliveredOctets(segment.key, data)
        if len(hold.ooo) >= MAX_OUT_OF_ORDER_SEGMENTS:
            return self._refuse(
                hold,
                segment.key,
                REORDER_CAP,
                f"{MAX_OUT_OF_ORDER_SEGMENTS} out-of-order segments are already stored",
            )
        if hold.buffered_octets() + len(segment.payload) > MAX_BUFFERED_BYTES_PER_FLOW:
            return self._refuse(
                hold,
                segment.key,
                BYTE_CAP,
                f"buffer would exceed {MAX_BUFFERED_BYTES_PER_FLOW} octets",
            )
        hold.ooo.append((segment.seq, segment.payload))
        return DeliveredOctets(segment.key, b"")

    def _refuse(
        self, hold: _Hold, key: FlowKey, reason: FlowRefusalReason, detail: str
    ) -> FlowRefusal:
        """Remember the refusal and return it. The offending segment is not stored."""
        refusal = FlowRefusal(key, reason, detail)
        hold.refusal = refusal
        return refusal

    def _drain(self, hold: _Hold) -> bytes:
        """Pull stored segments that now start at the cursor. The cursor is set."""
        assert hold.next_seq is not None
        gathered = bytearray()
        progressed = True
        while progressed:
            progressed = False
            remaining: list[tuple[int, bytes]] = []
            for seq, payload in hold.ooo:
                if _ahead(seq, hold.next_seq) == 0:
                    gathered.extend(payload)
                    hold.next_seq = _add(hold.next_seq, len(payload))
                    progressed = True
                else:
                    remaining.append((seq, payload))
            hold.ooo = remaining
        return bytes(gathered)


class ContiguousStream:
    """A buffer a dissector reads with `take` or `take_pdu`.

    Bytes are appended only by `extend`. A length check that fails does not
    consume the header. Later `take_pdu` calls return that same refusal.
    `take` can still read octets already buffered, because they were not consumed.

    Attributes:
        key: The flow these bytes belong to.
    """

    def __init__(self, key: FlowKey) -> None:
        """Start empty.

        Args:
            key: Named on every refusal this stream returns.
        """
        self.key = key
        self._buf = bytearray()
        self._refusal: FlowRefusal | None = None

    def extend(self, data: bytes) -> FlowRefusal | None:
        """Append ``data`` if it fits in the per-flow cap.

        Args:
            data: Contiguous octets already reassembled.

        Returns:
            None when they were appended. A `FlowRefusal` when they were not.
            A refusal here does not discard octets already buffered.
        """
        if self._refusal is not None:
            return self._refusal
        if len(self._buf) + len(data) > MAX_BUFFERED_BYTES_PER_FLOW:
            return FlowRefusal(
                self.key,
                BYTE_CAP,
                f"unread buffer would exceed {MAX_BUFFERED_BYTES_PER_FLOW} octets",
            )
        self._buf.extend(data)
        return None

    def take(self, count: int) -> bytes | FlowRefusal | None:
        """Return the next ``count`` octets, or None if they have not arrived.

        A prior PDU-length refusal does not hide octets already buffered. The
        caller stops by honouring the refusal from `take_pdu`.

        Args:
            count: How many octets the caller needs. Zero returns an empty bytes.

        Returns:
            The octets, None while the buffer is short, or a refusal for a
            negative count.
        """
        if count < 0:
            self._refusal = FlowRefusal(self.key, PDU_LENGTH, "a negative read")
            return self._refusal
        if len(self._buf) < count:
            return None
        taken = bytes(self._buf[:count])
        del self._buf[:count]
        return taken

    def take_pdu(
        self, header_octets: int, length_of: Callable[[bytes], int]
    ) -> bytes | FlowRefusal | None:
        """Return one PDU whose total length is computed from a complete header.

        ``length_of`` is called only when ``header_octets`` are already buffered.
        A length below the header size, or above the per-flow cap, refuses the
        stream and leaves the header in place.

        Args:
            header_octets: How many octets `length_of` needs.
            length_of: Maps that header to the total PDU length, header included.

        Returns:
            The PDU, None while it is incomplete, or a refusal.
        """
        if self._refusal is not None:
            return self._refusal
        if header_octets < 1 or header_octets > MAX_BUFFERED_BYTES_PER_FLOW:
            self._refusal = FlowRefusal(self.key, PDU_LENGTH, "header size is not usable")
            return self._refusal
        if len(self._buf) < header_octets:
            return None
        header = bytes(self._buf[:header_octets])
        total = length_of(header)
        if total < header_octets or total > MAX_BUFFERED_BYTES_PER_FLOW:
            self._refusal = FlowRefusal(
                self.key,
                PDU_LENGTH,
                f"declared PDU length {total} is not between {header_octets} and "
                f"{MAX_BUFFERED_BYTES_PER_FLOW}",
            )
            return self._refusal
        if len(self._buf) < total:
            return None
        taken = bytes(self._buf[:total])
        del self._buf[:total]
        return taken

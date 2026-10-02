"""Turning a plant's control-network activity into a capture Atlas can actually read.

A plant says *what* its network did — this SCADA polled that PLC's register block, this operator
wrote that setpoint. This module says what that looked like on the wire: Modbus/TCP application
data units, inside TCP segments, inside IP, inside Ethernet, inside a pcap file. The split keeps
protocol encoding out of the physics and means a second protocol could be emitted from the same
plants without touching them.

**The bytes are built by hand and read back by the real dissector.** Nothing here imports
`phos.atlas.packet`; the frames are assembled with `struct` and the test in
`tests/synth/test_traffic.py` runs the capture through `dissect_capture` and asserts that every
frame comes back a decoded `ModbusMessage` and not one `MalformedFrame`. A generator that used the
parser's own types would be testing the parser against itself and would prove nothing about
whether the bytes are right.

**What makes this a capture rather than a stream of ADUs.** Each conversation opens with a real
three-way handshake, sequence numbers advance by the bytes actually sent, and the IP and TCP
checksums are computed rather than zeroed. None of that is needed to make the dissector happy —
it is needed so that the capture is not trivially separable from a real one, which is the same
standard the injection hook is held to. A capture whose checksums are all zero announces itself.

**Timing carries jitter, and the jitter has its own generator.** A poll that lands on the exact
sample instant every time would give the command-interval features in `phos.atlas.packet.behaviour`
a coefficient of variation of exactly zero, which no real SCADA scan produces. The jitter is drawn
from a generator seeded here, never from the plant's — so adding or changing it cannot shift a
single reading in the telemetry, and the two outputs of one run stay independently reproducible.

**Register values are raw counts, not engineering units**, because that is what an instrument puts
on a 16-bit register. `phos.synth.plant.register_count` does the conversion, and the capture
therefore carries the same kind of number a real one does.
"""

import logging
import struct
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Final

import numpy

from phos.synth.plant import (
    CommandIntent,
    CommandKind,
    ControlNetwork,
    PlantDescription,
    PlantStep,
    register_count,
)
from phos.synth.realism import CommsDropout

__all__ = [
    "MODBUS_PORT",
    "TrafficPolicy",
    "WireFrame",
    "modbus_frames",
    "write_pcap",
]

logger = logging.getLogger(__name__)

MODBUS_PORT: Final = 502
"""The registered Modbus server port. Every PLC in a generated capture listens here."""

_PCAP_MAGIC: Final = 0xA1B2C3D4
_PCAP_VERSION: Final = (2, 4)
_PCAP_SNAPLEN: Final = 65535
_LINKTYPE_ETHERNET: Final = 1
_ETHERTYPE_IPV4: Final = 0x0800
_IP_PROTO_TCP: Final = 6
_IP_TTL: Final = 64
_TCP_WINDOW: Final = 8192
_TCP_HEADER_WORDS: Final = 5

_FLAG_SYN: Final = 0x02
_FLAG_PSH: Final = 0x08
_FLAG_ACK: Final = 0x10

_FUNCTION_READ_HOLDING: Final = 3
_FUNCTION_WRITE_SINGLE: Final = 6
_MBAP_PROTOCOL_ID: Final = 0
_MAX_TRANSACTION_ID: Final = 0xFFFF
_FIRST_CLIENT_PORT: Final = 41000
_MICROSECONDS: Final = 1_000_000
_INTER_REQUEST_GAP_MS: Final = 0.4
"""How long a client waits after an answer before its next request on the same connection."""


@dataclass(frozen=True)
class TrafficPolicy:
    """How the generated capture is timed and addressed.

    Attributes:
        seed: Seeds the timing jitter. Separate from the plant's seed on purpose — see the module
            docstring.
        poll_jitter_ms: Upper bound on how late a poll leaves the SCADA server relative to the
            sample instant. Real scan cycles are not metronomes.
        response_delay_ms: ``(low, high)`` bounds on how long a device takes to answer.

    Invariants:
        The jitter bound is non-negative and the response-delay range is not inverted.
    """

    seed: int = 1
    poll_jitter_ms: float = 45.0
    response_delay_ms: tuple[float, float] = (1.5, 9.0)

    def __post_init__(self) -> None:
        """Refuse a timing policy that cannot produce ordered, plausible frames.

        Raises:
            ValueError: If the jitter is negative, or the delay range is inverted or negative.
        """
        low, high = self.response_delay_ms
        if self.poll_jitter_ms < 0.0:
            raise ValueError(f"poll jitter cannot be negative, got {self.poll_jitter_ms}")
        if low < 0.0 or high < low:
            raise ValueError(f"response delay range is not usable: {self.response_delay_ms}")


@dataclass(frozen=True)
class WireFrame:
    """One frame, ready to be serialised: who sent it, when, and what it carried.

    Attributes:
        timestamp: When it left, UTC.
        src_ip: Sending address.
        src_port: Sending port.
        dst_ip: Receiving address.
        dst_port: Receiving port.
        seq: TCP sequence number.
        ack: TCP acknowledgement number.
        flags: TCP flag bits.
        payload: The transport payload — a Modbus ADU, or empty for a handshake frame.
    """

    timestamp: datetime
    src_ip: str
    src_port: int
    dst_ip: str
    dst_port: int
    seq: int
    ack: int
    flags: int
    payload: bytes


@dataclass
class _Conversation:
    """One TCP connection between a client and a PLC, and the sequence state on both sides."""

    client_ip: str
    client_port: int
    server_ip: str
    client_seq: int
    server_seq: int
    free_at: datetime
    transaction_id: int = 1

    def next_transaction(self) -> int:
        """Return the next MBAP transaction id, wrapping as the protocol's field does."""
        current = self.transaction_id
        self.transaction_id = current % _MAX_TRANSACTION_ID + 1
        return current


def modbus_frames(
    description: PlantDescription,
    steps: Sequence[PlantStep],
    policy: TrafficPolicy | None = None,
    dropouts: Sequence[CommsDropout] = (),
) -> tuple[WireFrame, ...]:
    """Render a plant's control-network activity as Modbus/TCP frames.

    Args:
        description: The plant, whose control network says who talks to whom and which registers
            carry which signals.
        steps: The run's samples, in order. Each sample's reported readings are what the PLCs
            answer a poll with, so a manipulated reading manipulates the capture too — which is
            the whole point of having one plant feed both outputs.
        policy: Timing and addressing. Defaults are a plausible SCADA scan.
        dropouts: Declared stretches where the control network loses frames, from
            `phos.synth.realism`. **Empty by default, and empty means byte-identical**: with no
            dropout the loop below takes the same branch for every exchange and draws the same
            jitter in the same order, which is what lets every capture generated before this
            parameter existed be reproduced exactly.

            A covered exchange is *lost*. If its dropout retransmits, the exchange is re-sent the
            moment service returns, which puts a gap and then a burst in the capture; if it does
            not, the exchange is simply missing. Those are the two shapes a real transport failure
            leaves, and they are what U1's `communication_artefacts` category looks for and what
            refusal register R11 records HAI's prepared corpus could not have shown at all — the
            10-second downsample makes any finer irregularity unobservable by construction.

    Returns:
        Every frame, in timestamp order. Empty for a plant with no control network — a process
        run over something Atlas cannot dissect produces no capture, and saying so with an empty
        result is more honest than inventing traffic for it.

    Raises:
        ValueError: If a command intent asks for something this encoder does not emit — a
            multi-register write, or a read of a block that is not on the register map. Both are
            refusals rather than silent omissions: a capture missing the exchange a plant said it
            made would be ground truth that lies.
    """
    network = description.control_network
    if network is None:
        logger.debug("plant %s declares no control network; no capture", description.plant_id)
        return ()

    settings = policy or TrafficPolicy()
    rng = numpy.random.default_rng(settings.seed)
    conversations: dict[tuple[str, str], _Conversation] = {}
    frames: list[WireFrame] = []

    for step in steps:
        for intent in step.commands:
            request_pdu, response_pdu = _encode(description, network, intent, step.report.values)
            conversation = _conversation_for(network, intent, conversations, frames, step.timestamp)
            # One transaction id per exchange, echoed by the server, as the protocol requires.
            transaction_id = conversation.next_transaction()
            request = _mbap(transaction_id, network.unit_id, request_pdu)
            response = _mbap(transaction_id, network.unit_id, response_pdu)
            offset = float(rng.uniform(0.0, settings.poll_jitter_ms))
            delay = float(rng.uniform(*settings.response_delay_ms))
            # Drawn before the dropout is consulted, so the jitter stream is a function of the
            # exchanges a plant made and not of where the network happened to fail.
            covering = next(
                (d for d in dropouts if d.drops(step.timestamp, intent.target)),
                None,
            )
            if covering is not None and not covering.retransmits:
                continue
            at = step.timestamp if covering is None else covering.ended_at
            # A client does not pipeline: the next request on a connection waits for the previous
            # answer. Without that, two block reads scheduled at the same instant could overtake
            # each other under independent jitter, and the sequence numbers on one connection
            # would go backwards — which no TCP endpoint does and any analyst would notice.
            sent = max(at + timedelta(milliseconds=offset), conversation.free_at)
            frames.append(
                WireFrame(
                    timestamp=sent,
                    src_ip=conversation.client_ip,
                    src_port=conversation.client_port,
                    dst_ip=conversation.server_ip,
                    dst_port=MODBUS_PORT,
                    seq=conversation.client_seq,
                    ack=conversation.server_seq,
                    flags=_FLAG_PSH | _FLAG_ACK,
                    payload=request,
                )
            )
            conversation.client_seq += len(request)
            frames.append(
                WireFrame(
                    timestamp=sent + timedelta(milliseconds=delay),
                    src_ip=conversation.server_ip,
                    src_port=MODBUS_PORT,
                    dst_ip=conversation.client_ip,
                    dst_port=conversation.client_port,
                    seq=conversation.server_seq,
                    ack=conversation.client_seq,
                    flags=_FLAG_PSH | _FLAG_ACK,
                    payload=response,
                )
            )
            conversation.server_seq += len(response)
            conversation.free_at = sent + timedelta(milliseconds=delay + _INTER_REQUEST_GAP_MS)

    frames.sort(key=lambda frame: frame.timestamp)
    logger.debug("rendered %d frames for %s", len(frames), description.plant_id)
    return tuple(frames)


def _conversation_for(
    network: ControlNetwork,
    intent: CommandIntent,
    conversations: dict[tuple[str, str], _Conversation],
    frames: list[WireFrame],
    clock: datetime,
) -> _Conversation:
    """Return the connection this exchange belongs to, opening it with a handshake if new."""
    client_ip = network.node(intent.issuer).ip
    server_ip = network.node(intent.target).ip
    key = (client_ip, server_ip)
    conversation = conversations.get(key)
    if conversation is not None:
        return conversation

    conversation = _Conversation(
        client_ip=client_ip,
        client_port=_FIRST_CLIENT_PORT + len(conversations),
        server_ip=server_ip,
        client_seq=1000,
        server_seq=5000,
        free_at=clock - timedelta(seconds=1),
    )
    conversations[key] = conversation
    frames.extend(_handshake(conversation, clock))
    conversation.client_seq += 1
    conversation.server_seq += 1
    return conversation


def _handshake(conversation: _Conversation, clock: datetime) -> list[WireFrame]:
    """Return the three frames that open a TCP connection, just before its first exchange."""
    opened_at = clock - timedelta(milliseconds=6)
    client_isn = conversation.client_seq
    server_isn = conversation.server_seq
    return [
        WireFrame(
            timestamp=opened_at,
            src_ip=conversation.client_ip,
            src_port=conversation.client_port,
            dst_ip=conversation.server_ip,
            dst_port=MODBUS_PORT,
            seq=client_isn,
            ack=0,
            flags=_FLAG_SYN,
            payload=b"",
        ),
        WireFrame(
            timestamp=opened_at + timedelta(milliseconds=2),
            src_ip=conversation.server_ip,
            src_port=MODBUS_PORT,
            dst_ip=conversation.client_ip,
            dst_port=conversation.client_port,
            seq=server_isn,
            ack=client_isn + 1,
            flags=_FLAG_SYN | _FLAG_ACK,
            payload=b"",
        ),
        WireFrame(
            timestamp=opened_at + timedelta(milliseconds=4),
            src_ip=conversation.client_ip,
            src_port=conversation.client_port,
            dst_ip=conversation.server_ip,
            dst_port=MODBUS_PORT,
            seq=client_isn + 1,
            ack=server_isn + 1,
            flags=_FLAG_ACK,
            payload=b"",
        ),
    ]


def _encode(
    description: PlantDescription,
    network: ControlNetwork,
    intent: CommandIntent,
    reported: Mapping[str, float],
) -> tuple[bytes, bytes]:
    """Return the ``(request, response)`` protocol data units for one exchange.

    Raises:
        ValueError: If the intent is a multi-register write, which this encoder does not emit, or
            a read of an address the register map does not describe.
    """
    if intent.kind is CommandKind.WRITE:
        if intent.quantity != 1 or len(intent.values) != 1:
            raise ValueError(
                f"this encoder writes one register at a time; {intent.reason!r} asked for "
                f"{intent.quantity}"
            )
        body = struct.pack(">BHH", _FUNCTION_WRITE_SINGLE, intent.address, intent.values[0])
        return body, body

    counts = _register_counts(description, network, intent, reported)
    request = struct.pack(">BHH", _FUNCTION_READ_HOLDING, intent.address, intent.quantity)
    response = struct.pack(">BB", _FUNCTION_READ_HOLDING, 2 * len(counts)) + b"".join(
        struct.pack(">H", value) for value in counts
    )
    return request, response


def _register_counts(
    description: PlantDescription,
    network: ControlNetwork,
    intent: CommandIntent,
    reported: Mapping[str, float],
) -> tuple[int, ...]:
    """Return the raw counts a PLC answers a block read with.

    Raises:
        ValueError: If no declared block starts at the address that was read.
    """
    for block in network.blocks:
        if block.node_id == intent.target and block.start_address == intent.address:
            return tuple(
                register_count(description.signal(key), reported[key]) for key in block.signals
            )
    raise ValueError(
        f"no register block on {intent.target} starts at address {intent.address}; a capture "
        "cannot answer a read the register map does not describe"
    )


def write_pcap(frames: Iterable[WireFrame], path: Path) -> int:
    """Serialise frames into a libpcap file, Ethernet link type.

    Args:
        frames: The frames, in the order they should appear. `modbus_frames` returns them sorted.
        path: File to write. Overwritten if it exists.

    Returns:
        How many frames were written, so a caller can record it in a manifest rather than
        re-reading the file to find out.
    """
    written = 0
    with path.open("wb") as handle:
        handle.write(
            struct.pack(
                "<IHHiIII",
                _PCAP_MAGIC,
                _PCAP_VERSION[0],
                _PCAP_VERSION[1],
                0,
                0,
                _PCAP_SNAPLEN,
                _LINKTYPE_ETHERNET,
            )
        )
        for index, frame in enumerate(frames):
            packet = _ethernet(frame, index)
            epoch = frame.timestamp.timestamp()
            seconds = int(epoch // 1)
            microseconds = min(round((epoch - seconds) * _MICROSECONDS), _MICROSECONDS - 1)
            handle.write(struct.pack("<IIII", seconds, microseconds, len(packet), len(packet)))
            handle.write(packet)
            written += 1
    logger.debug("wrote %d frames to %s", written, path)
    return written


def _ethernet(frame: WireFrame, index: int) -> bytes:
    """Wrap a frame's IP packet in an Ethernet II header, with MACs derived from the addresses."""
    return (
        _mac(frame.dst_ip)
        + _mac(frame.src_ip)
        + struct.pack(">H", _ETHERTYPE_IPV4)
        + _ipv4(frame, index)
    )


def _mac(ip: str) -> bytes:
    """Return a stable locally-administered MAC for an IPv4 address."""
    return bytes([0x02, 0x00, *(int(octet) for octet in ip.split("."))])


def _ipv4(frame: WireFrame, index: int) -> bytes:
    """Return the IPv4 packet carrying a frame's TCP segment, with a computed header checksum."""
    segment = _tcp(frame)
    total_length = 20 + len(segment)
    header = struct.pack(
        ">BBHHHBBH4s4s",
        0x45,
        0,
        total_length,
        index & 0xFFFF,
        0x4000,
        _IP_TTL,
        _IP_PROTO_TCP,
        0,
        _address(frame.src_ip),
        _address(frame.dst_ip),
    )
    checksum = _checksum(header)
    return header[:10] + struct.pack(">H", checksum) + header[12:] + segment


def _tcp(frame: WireFrame) -> bytes:
    """Return the TCP segment, checksummed over the standard IPv4 pseudo-header."""
    header = struct.pack(
        ">HHIIBBHHH",
        frame.src_port,
        frame.dst_port,
        frame.seq & 0xFFFFFFFF,
        frame.ack & 0xFFFFFFFF,
        _TCP_HEADER_WORDS << 4,
        frame.flags,
        _TCP_WINDOW,
        0,
        0,
    )
    segment = header + frame.payload
    pseudo = (
        _address(frame.src_ip)
        + _address(frame.dst_ip)
        + struct.pack(">BBH", 0, _IP_PROTO_TCP, len(segment))
    )
    checksum = _checksum(pseudo + segment)
    return header[:16] + struct.pack(">H", checksum) + header[18:] + frame.payload


def _address(ip: str) -> bytes:
    """Return an IPv4 address as its four wire bytes."""
    return bytes(int(octet) for octet in ip.split("."))


def _checksum(data: bytes) -> int:
    """Return the internet checksum of ``data``, padded to an even length.

    Folded twice, unconditionally. A `while` loop would be the textbook form and would leave a
    branch that only ever goes one way for buffers this size, which is a coverage lie rather than
    a safety net.
    """
    padded = data + b"\x00" * (len(data) % 2)
    total = int(sum(struct.unpack(f">{len(padded) // 2}H", padded)))
    total = (total & 0xFFFF) + (total >> 16)
    total = (total & 0xFFFF) + (total >> 16)
    return ~total & 0xFFFF


def _mbap(transaction_id: int, unit_id: int, pdu: bytes) -> bytes:
    """Wrap a Modbus PDU in its MBAP header."""
    return struct.pack(">HHHB", transaction_id, _MBAP_PROTOCOL_ID, len(pdu) + 1, unit_id) + pdu

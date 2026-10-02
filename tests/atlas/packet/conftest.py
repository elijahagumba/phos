"""Hand-built capture bytes for the packet-adapter tests.

Every fixture here writes wire bytes with `struct.pack` rather than with the parsing library the
adapter uses. That is deliberate: a fixture built by `dpkt` would test `dpkt` against itself, and
the malformed cases — a lying length field, a truncated record, a byte count that runs past the
buffer — are precisely the ones a writer library refuses to produce. Hand-built bytes are the only
way to hand the parser something an adversary could actually send.

The builders are exposed as fixtures returning callables so that a test can construct exactly the
capture it needs inline, and so that no test module has to import a sibling test module.
"""

import struct
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from phos.atlas.packet import (
    Direction,
    Endpoint,
    FrameSource,
    FunctionCode,
    MalformedFrame,
    MalformedReason,
    ModbusMessage,
    RawFrame,
    Transport,
    UnparsedMessage,
)

# --- Link, network and transport layers -------------------------------------------------------

ETHERTYPE_IPV4 = 0x0800
ETHERTYPE_IPV6 = 0x86DD
ETHERTYPE_ARP = 0x0806

IP_PROTO_TCP = 6
IP_PROTO_UDP = 17
IP_PROTO_ICMP = 1

LINKTYPE_ETHERNET = 1
LINKTYPE_RAW_IP = 101

DEFAULT_SRC_IP = "10.0.0.1"
DEFAULT_DST_IP = "10.0.0.2"


def ethernet(ethertype: int, body: bytes) -> bytes:
    """Wrap ``body`` in an Ethernet II header."""
    return b"\xaa" * 6 + b"\xbb" * 6 + struct.pack(">H", ethertype) + body


def ipv4(
    proto: int,
    body: bytes,
    src: str = DEFAULT_SRC_IP,
    dst: str = DEFAULT_DST_IP,
    total_length: int | None = None,
) -> bytes:
    """Wrap ``body`` in an IPv4 header.

    ``total_length`` defaults to the honest value; pass one explicitly to build a header that
    lies about how much payload follows.
    """
    declared = 20 + len(body) if total_length is None else total_length
    src_raw = bytes(int(part) for part in src.split("."))
    dst_raw = bytes(int(part) for part in dst.split("."))
    header = struct.pack(">BBHHHBBH4s4s", 0x45, 0, declared, 1, 0, 64, proto, 0, src_raw, dst_raw)
    return header + body


def ipv6(next_header: int, body: bytes) -> bytes:
    """Wrap ``body`` in an IPv6 header with fixed 2001:: endpoints."""
    src = b"\x20\x01" + b"\x00" * 14
    dst = b"\x20\x01" + b"\x00" * 13 + b"\x02"
    return struct.pack(">IHBB", 0x60000000, len(body), next_header, 64) + src + dst + body


def tcp(sport: int, dport: int, payload: bytes = b"") -> bytes:
    """Build a TCP segment with a 20-byte header and no options."""
    return struct.pack(">HHIIBBHHH", sport, dport, 1, 1, 0x50, 0x18, 8192, 0, 0) + payload


def udp(sport: int, dport: int, payload: bytes = b"") -> bytes:
    """Build a UDP datagram."""
    return struct.pack(">HHHH", sport, dport, 8 + len(payload), 0) + payload


def tcp_frame(sport: int, dport: int, payload: bytes = b"") -> bytes:
    """Build a complete Ethernet/IPv4/TCP frame carrying ``payload``."""
    return ethernet(ETHERTYPE_IPV4, ipv4(IP_PROTO_TCP, tcp(sport, dport, payload)))


def udp_frame(sport: int, dport: int, payload: bytes = b"") -> bytes:
    """Build a complete Ethernet/IPv4/UDP frame carrying ``payload``."""
    return ethernet(ETHERTYPE_IPV4, ipv4(IP_PROTO_UDP, udp(sport, dport, payload)))


# --- Capture containers ------------------------------------------------------------------------

PCAP_MAGIC_LE = 0xA1B2C3D4
PCAPNG_SHB_TYPE = 0x0A0D0D0A
PCAPNG_IDB_TYPE = 0x00000001
PCAPNG_EPB_TYPE = 0x00000006


def pcap_bytes(
    frames: Sequence[tuple[int, int, bytes]],
    linktype: int = LINKTYPE_ETHERNET,
    snaplen: int = 65535,
) -> bytes:
    """Build a classic libpcap file.

    Args:
        frames: ``(seconds, microseconds, frame bytes)`` records, in capture order.
        linktype: The DLT the global header declares.
        snaplen: Declared snapshot length.

    Returns:
        The complete file contents.
    """
    out = struct.pack("<IHHiIII", PCAP_MAGIC_LE, 2, 4, 0, 0, snaplen, linktype)
    for seconds, microseconds, raw in frames:
        out += struct.pack("<IIII", seconds, microseconds, len(raw), len(raw)) + raw
    return out


def pcapng_bytes(frames: Sequence[tuple[int, bytes]], linktype: int = LINKTYPE_ETHERNET) -> bytes:
    """Build a pcapng file with one section, one interface and one EPB per frame.

    Args:
        frames: ``(timestamp in microseconds since the epoch, frame bytes)`` records.
        linktype: The link type the interface description block declares.

    Returns:
        The complete file contents.
    """
    shb_body = struct.pack("<IHHq", 0x1A2B3C4D, 1, 0, -1)
    shb = (
        struct.pack("<II", PCAPNG_SHB_TYPE, len(shb_body) + 12)
        + shb_body
        + struct.pack("<I", len(shb_body) + 12)
    )
    idb_body = struct.pack("<HHI", linktype, 0, 65535)
    idb = (
        struct.pack("<II", PCAPNG_IDB_TYPE, len(idb_body) + 12)
        + idb_body
        + struct.pack("<I", len(idb_body) + 12)
    )
    out = shb + idb
    for timestamp_us, raw in frames:
        padding = (-len(raw)) % 4
        body = (
            struct.pack(
                "<IIIII", 0, timestamp_us >> 32, timestamp_us & 0xFFFFFFFF, len(raw), len(raw)
            )
            + raw
            + b"\x00" * padding
        )
        total = len(body) + 12
        out += struct.pack("<II", PCAPNG_EPB_TYPE, total) + body + struct.pack("<I", total)
    return out


# --- Modbus ADUs -------------------------------------------------------------------------------

MODBUS_SERVER_PORT = 502
CLIENT_PORT = 5555


def modbus_adu(
    pdu: bytes,
    transaction_id: int = 0x1234,
    unit_id: int = 17,
    protocol_id: int = 0,
    length: int | None = None,
) -> bytes:
    """Build a Modbus/TCP ADU: a 7-byte MBAP header followed by ``pdu``.

    ``length`` defaults to the honest value (``len(pdu) + 1``, covering the unit id and the PDU);
    pass one explicitly to build a header that lies about how much follows.
    """
    declared = len(pdu) + 1 if length is None else length
    return struct.pack(">HHHB", transaction_id, protocol_id, declared, unit_id) + pdu


# --- Fixtures ----------------------------------------------------------------------------------


@pytest.fixture
def write_pcap(tmp_path: Path) -> Callable[..., Path]:
    """Return a callable that writes a classic pcap into the test's temp directory."""

    def _write(
        frames: Sequence[tuple[int, int, bytes]],
        name: str = "capture.pcap",
        linktype: int = LINKTYPE_ETHERNET,
    ) -> Path:
        path = tmp_path / name
        path.write_bytes(pcap_bytes(frames, linktype=linktype))
        return path

    return _write


@pytest.fixture
def write_pcapng(tmp_path: Path) -> Callable[..., Path]:
    """Return a callable that writes a pcapng file into the test's temp directory."""

    def _write(
        frames: Sequence[tuple[int, bytes]],
        name: str = "capture.pcapng",
        linktype: int = LINKTYPE_ETHERNET,
    ) -> Path:
        path = tmp_path / name
        path.write_bytes(pcapng_bytes(frames, linktype=linktype))
        return path

    return _write


@pytest.fixture
def write_raw(tmp_path: Path) -> Callable[[bytes, str], Path]:
    """Return a callable that writes arbitrary bytes to a file, for corrupt-container tests."""

    def _write(data: bytes, name: str = "corrupt.pcap") -> Path:
        path = tmp_path / name
        path.write_bytes(data)
        return path

    return _write


def make_frame(
    payload: bytes,
    src_port: int = CLIENT_PORT,
    dst_port: int = MODBUS_SERVER_PORT,
    transport: Transport = Transport.TCP,
    frame_index: int = 0,
    capture: str = "/captures/test.pcap",
    timestamp: datetime | None = None,
) -> RawFrame:
    """Build a `RawFrame` directly, for dissector tests that need no capture file."""
    return RawFrame(
        source=FrameSource(capture=capture, frame_index=frame_index),
        timestamp=timestamp or datetime(2026, 8, 12, 9, 30, tzinfo=UTC),
        transport=transport,
        src=Endpoint(ip=DEFAULT_SRC_IP, port=src_port),
        dst=Endpoint(ip=DEFAULT_DST_IP, port=dst_port),
        payload=payload,
    )


@pytest.fixture
def frame_factory() -> Callable[..., RawFrame]:
    """Return `make_frame`, so tests can build frames without a capture file."""
    return make_frame


# --- P2: dissected messages, built directly ----------------------------------------------------
#
# The behaviour layer consumes a *stream of typed messages*, not bytes, so its tests build messages
# rather than captures. Going through wire bytes would test P1's dissection a second time and make
# every behavioural fixture an exercise in packing ADUs; the P1 modules already prove that path.

EPOCH = datetime(2026, 8, 14, 9, 0, tzinfo=UTC)
"""Fixed instant every P2 fixture is anchored to, so no test depends on the wall clock."""

DEFAULT_CAPTURE = "/captures/plant.pcap"
ISSUER_IP = "10.0.0.9"
TARGET_IP = "10.0.0.20"


def make_modbus_message(
    function_code: int = FunctionCode.READ_HOLDING_REGISTERS,
    *,
    src_ip: str = ISSUER_IP,
    dst_ip: str = TARGET_IP,
    direction: Direction = Direction.REQUEST,
    timestamp: datetime = EPOCH,
    frame_index: int = 0,
    capture: str = DEFAULT_CAPTURE,
    reference_address: int | None = 100,
    quantity: int | None = None,
    values: Sequence[int] = (),
    unit_id: int = 1,
    function_name: str | None = None,
) -> ModbusMessage:
    """Build one dissected Modbus message, defaulting to a read request from issuer to target."""
    return ModbusMessage(
        source=FrameSource(capture=capture, frame_index=frame_index),
        timestamp=timestamp,
        src=Endpoint(ip=src_ip, port=CLIENT_PORT),
        dst=Endpoint(ip=dst_ip, port=MODBUS_SERVER_PORT),
        direction=direction,
        transaction_id=1,
        unit_id=unit_id,
        function_code=function_code,
        function_name=function_name or f"function_{function_code}",
        reference_address=reference_address,
        quantity=quantity,
        values=tuple(values),
    )


def make_unparsed_message(
    *,
    src_ip: str = ISSUER_IP,
    dst_ip: str = TARGET_IP,
    timestamp: datetime = EPOCH,
    frame_index: int = 0,
    capture: str = DEFAULT_CAPTURE,
    payload_length: int = 40,
) -> UnparsedMessage:
    """Build traffic no dissector claimed — the coverage gap P2 must count and never feature."""
    return UnparsedMessage(
        source=FrameSource(capture=capture, frame_index=frame_index),
        timestamp=timestamp,
        src=Endpoint(ip=src_ip, port=CLIENT_PORT),
        dst=Endpoint(ip=dst_ip, port=80),
        payload_length=payload_length,
    )


def make_malformed_frame(
    *,
    src_ip: str = ISSUER_IP,
    dst_ip: str = TARGET_IP,
    timestamp: datetime = EPOCH,
    frame_index: int = 0,
    capture: str = DEFAULT_CAPTURE,
    reason: MalformedReason = MalformedReason.SHORT_HEADER,
) -> MalformedFrame:
    """Build a refusal — traffic a dissector claimed and could not validate."""
    return MalformedFrame(
        protocol="modbus",
        source=FrameSource(capture=capture, frame_index=frame_index),
        timestamp=timestamp,
        src=Endpoint(ip=src_ip, port=CLIENT_PORT),
        dst=Endpoint(ip=dst_ip, port=MODBUS_SERVER_PORT),
        reason=reason,
        detail="hand-built refusal",
        payload_length=3,
    )


def command_series(
    count: int,
    *,
    start: datetime = EPOCH,
    interval: timedelta = timedelta(seconds=1),
    function_codes: Sequence[int] = (FunctionCode.READ_HOLDING_REGISTERS,),
    src_ip: str = ISSUER_IP,
    dst_ip: str = TARGET_IP,
    first_frame_index: int = 0,
    capture: str = DEFAULT_CAPTURE,
    reference_address: int | None = 100,
    values: Sequence[int] = (),
) -> list[ModbusMessage]:
    """Build ``count`` commands at a fixed rhythm, cycling through ``function_codes``.

    The rhythm is exact, which is what lets a test assert a hand-computed interval mean and a
    coefficient of variation of zero. Frame indices advance with the series so provenance is
    checkable too.
    """
    return [
        make_modbus_message(
            function_codes[index % len(function_codes)],
            src_ip=src_ip,
            dst_ip=dst_ip,
            timestamp=start + interval * index,
            frame_index=first_frame_index + index,
            capture=capture,
            reference_address=reference_address,
            values=values,
        )
        for index in range(count)
    ]


@pytest.fixture
def modbus_message() -> Callable[..., ModbusMessage]:
    """Return `make_modbus_message`."""
    return make_modbus_message


@pytest.fixture
def unparsed_message() -> Callable[..., UnparsedMessage]:
    """Return `make_unparsed_message`."""
    return make_unparsed_message


@pytest.fixture
def malformed_frame() -> Callable[..., MalformedFrame]:
    """Return `make_malformed_frame`."""
    return make_malformed_frame


@pytest.fixture
def series() -> Callable[..., list[ModbusMessage]]:
    """Return `command_series`."""
    return command_series

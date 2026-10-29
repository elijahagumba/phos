"""Reading a capture file without trusting a byte of it.

`read_frames` opens a pcap or pcapng file and yields one `RawFrame` per frame it can peel down to
a transport payload. It is the outermost layer of the adapter and therefore the first code an
adversary's bytes reach, so two properties matter more than anything it decodes.

**It streams.** Industrial captures are gigabytes. Nothing here materialises a capture, a frame
list, or an accumulated buffer: the reader is a generator over a generator, and memory stays
proportional to one frame rather than to the file. `TestStreamsRatherThanLoads` measures that by
taking one frame from a five-hundred-frame capture and asserting only one was read, because
"it looks lazy" is not a property anyone can maintain.

**It counts what it cannot decode.** A capture is full of traffic that never becomes a frame —
ARP, ICMP, non-IP link chatter, a snapped-off final record. Dropping those silently would make
every later coverage number a lie by omission, so every frame read lands in exactly one of four
counters and `CaptureStats.accounts_for_every_frame` asserts the arithmetic closes. A capture that
yields nothing tells you *why* it yielded nothing.

**Where the trust boundary sits.** dpkt is a parser being handed adversary-chosen bytes, so its
failures are expected input, not defects: `dpkt.UnpackError`, `struct.error` and the timestamp
conversion's `OverflowError`/`OSError` are caught, counted, and logged around exactly the calls
that parse untrusted data. Our own construction of `RawFrame` sits deliberately *outside* those
handlers — a `ValidationError` there would mean PHOS had a bug, and since `ValidationError`
subclasses `ValueError` a wider net would swallow it and turn that bug into a quietly shrinking
frame count. See ADR 0012.

A corrupt record header stops the read rather than trying to resynchronise. Record framing carries
no marker to resynchronise *on*, so scanning forward for something that looks like a header is
guesswork that an adversary chooses the outcome of; `CaptureStats.truncated` records that the tail
was abandoned, and everything read before it is still delivered.

This module knows no industrial protocol. It hands over bytes and provenance; what they mean is
`dissect`'s question.
"""

import logging
import socket
import struct
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import dpkt
from dpkt.ethernet import Ethernet
from dpkt.ip import IP
from dpkt.ip6 import IP6
from dpkt.pcap import DLT_EN10MB, UniversalReader
from dpkt.tcp import TCP
from dpkt.udp import UDP

from phos.atlas.packet.frame import Endpoint, FrameSource, RawFrame, Transport

__all__ = [
    "CaptureError",
    "CaptureStats",
    "read_frames",
]

logger = logging.getLogger(__name__)

_UNTRUSTED_PARSE_ERRORS: Final = (dpkt.UnpackError, struct.error, ValueError)
"""What a parser handed adversary-chosen bytes is expected to raise.

Caught only around calls that parse untrusted input, never around PHOS's own validation.
"""

_IPV4_ADDRESS_BYTES: Final = 4
"""Length of a packed IPv4 address, used to pick the family for presentation formatting."""


class CaptureError(ValueError):
    """A file that cannot be read as a capture at all.

    Distinct from a malformed *frame*, which is counted and skipped. This is the container itself
    being unreadable — wrong magic, empty file, a header that is not a capture header — which
    means the caller named the wrong file rather than that an attacker sent odd traffic. It is
    raised rather than counted, because there is nothing to count.

    Subclasses `ValueError` so a caller that only knows about the built-in still catches it,
    matching `phos.atlas.topology.TopologyError`.
    """


@dataclass
class CaptureStats:
    """Running count of what a capture contained and how much of it survived the peel.

    Mutable and owned by the caller: `read_frames` is lazy, so the counts are only complete once
    the iterator is exhausted, and a caller-supplied accumulator is the honest way to expose a
    number that is still being computed. Passing one in is optional — the reader keeps its own if
    you do not care.

    Attributes:
        frames_read: Frames taken off the file, decodable or not.
        frames_yielded: Frames that became a `RawFrame` with a non-empty payload.
        frames_undecodable: Frames that could not be peeled to a transport payload — not IP, not
            TCP or UDP, truncated, or carrying a timestamp outside the representable range.
        frames_without_payload: Frames that peeled cleanly but carried no transport bytes, a bare
            TCP acknowledgement being the usual case. Counted apart from the undecodable ones
            because they are a property of the conversation, not a gap in our decoding.
        link_type: The DLT the capture declared, recorded even when unsupported so a capture that
            yields nothing explains itself.
        truncated: Whether the read stopped early on a corrupt record header.
    """

    frames_read: int = 0
    frames_yielded: int = 0
    frames_undecodable: int = 0
    frames_without_payload: int = 0
    link_type: int | None = None
    truncated: bool = False

    def accounts_for_every_frame(self) -> bool:
        """Whether every frame read landed in exactly one outcome counter.

        Returns:
            True when yielded, undecodable and payload-free frames sum to the frames read. A
            False here means the reader lost a frame somewhere, which would make every coverage
            number computed from these counts wrong.
        """
        return self.frames_read == (
            self.frames_yielded + self.frames_undecodable + self.frames_without_payload
        )


def read_frames(path: Path, stats: CaptureStats | None = None) -> Iterator[RawFrame]:
    """Stream the frames of a capture, peeled to their transport payloads.

    Args:
        path: The ``.pcap`` or ``.pcapng`` file to read.
        stats: Optional caller-owned accumulator. Updated as the iterator advances, so it is only
            complete once iteration finishes.

    Yields:
        One `RawFrame` per frame that peeled to a non-empty TCP or UDP payload, in capture order.
        A frame's index counts every frame in the file, including the ones skipped, so it matches
        what a packet analyser shows for the same capture.

    Raises:
        CaptureError: If the file is not a readable capture. Surfaces on first iteration, not at
            call time, because this is a generator.
        FileNotFoundError: If the path does not exist.
    """
    counters = CaptureStats() if stats is None else stats
    capture_name = str(path)

    with path.open("rb") as handle:
        try:
            reader = UniversalReader(handle)
            link_type = int(reader.datalink())
        except _UNTRUSTED_PARSE_ERRORS as error:
            raise CaptureError(
                f"{capture_name} is not a readable pcap or pcapng capture"
            ) from error

        counters.link_type = link_type
        is_ethernet = link_type == DLT_EN10MB
        if not is_ethernet:
            logger.warning(
                "capture %s declares link type %d; only Ethernet (%d) is peeled, so every frame "
                "will be counted undecodable",
                capture_name,
                link_type,
                DLT_EN10MB,
            )

        records = iter(reader)
        index = 0
        while True:
            try:
                epoch_seconds, buffer = next(records)
            except StopIteration:
                break
            except _UNTRUSTED_PARSE_ERRORS as error:
                counters.truncated = True
                logger.warning(
                    "capture %s has a corrupt record at frame %d (%s); stopping the read rather "
                    "than guessing where the next record begins",
                    capture_name,
                    index,
                    error,
                )
                break

            counters.frames_read += 1
            source = FrameSource(capture=capture_name, frame_index=index)
            index += 1
            frame = _peel(buffer, epoch_seconds, source, is_ethernet)
            if frame is None:
                counters.frames_undecodable += 1
                continue
            if not frame.payload:
                counters.frames_without_payload += 1
                continue
            counters.frames_yielded += 1
            yield frame


def _peel(
    buffer: bytes, epoch_seconds: float, source: FrameSource, is_ethernet: bool
) -> RawFrame | None:
    """Peel one frame to its transport payload.

    Args:
        buffer: The captured frame bytes, entirely untrusted.
        epoch_seconds: Capture time as seconds since the epoch, as the container reported it.
        source: Provenance to attach to the resulting frame.
        is_ethernet: Whether the capture's link type is one this reader understands.

    Returns:
        The peeled frame, or None if it is not IP over Ethernet carrying TCP or UDP, if any
        header was truncated, or if the timestamp is outside the representable range. A None is
        always counted by the caller, never dropped.
    """
    if not is_ethernet:
        return None

    layers = _peel_layers(buffer)
    if layers is None:
        return None
    timestamp = _to_utc(epoch_seconds)
    if timestamp is None:
        logger.debug(
            "frame %d carries an unrepresentable timestamp %r", source.frame_index, epoch_seconds
        )
        return None

    return RawFrame(
        source=source,
        timestamp=timestamp,
        transport=layers.transport,
        src=Endpoint(ip=layers.source_ip, port=layers.source_port),
        dst=Endpoint(ip=layers.destination_ip, port=layers.destination_port),
        payload=layers.payload,
        dst_mac=layers.dst_mac,
        src_mac=layers.src_mac,
        ethertype=layers.ethertype,
        tcp_seq=layers.tcp_seq,
    )


@dataclass(frozen=True)
class _Peeled:
    """One frame reduced to the fields `RawFrame` stores. Private to this module."""

    transport: Transport
    source_ip: str
    source_port: int
    destination_ip: str
    destination_port: int
    payload: bytes
    dst_mac: str
    src_mac: str
    ethertype: int
    tcp_seq: int | None


def _mac(raw: bytes) -> str:
    """Format six octets as lowercase colon-separated hex."""
    return ":".join(f"{octet:02x}" for octet in raw)


def _peel_layers(buffer: bytes) -> _Peeled | None:
    """Run the third-party parser over untrusted bytes and convert what it returns to our own types.

    The Ethernet destination, source, and type field are read from the first 14 octets
    before the parser is allowed to look past them. A type of 0x8100 stays 0x8100.
    Every other value crosses back as a `str`, `int` or `bytes`, so nothing dpkt
    produced flows on into PHOS.

    Returns:
        The peeled fields, or None if the frame is not IP over Ethernet carrying TCP or
        UDP, or any header was short.
    """
    if len(buffer) < 14:
        return None
    dst_mac = _mac(buffer[0:6])
    src_mac = _mac(buffer[6:12])
    ethertype = int.from_bytes(buffer[12:14], "big")
    try:
        link = Ethernet(buffer)
        network = link.data
        if not isinstance(network, IP | IP6):
            return None

        segment = network.data
        if isinstance(segment, TCP):
            transport = Transport.TCP
            tcp_seq: int | None = int(segment.seq) & 0xFFFFFFFF
        elif isinstance(segment, UDP):
            transport = Transport.UDP
            tcp_seq = None
        else:
            return None

        return _Peeled(
            transport,
            _address(bytes(network.src)),
            int(segment.sport),
            _address(bytes(network.dst)),
            int(segment.dport),
            bytes(segment.data),
            dst_mac,
            src_mac,
            ethertype,
            tcp_seq,
        )
    except _UNTRUSTED_PARSE_ERRORS:
        return None


def _address(packed: bytes) -> str:
    """Format a packed IPv4 or IPv6 address for presentation."""
    family = socket.AF_INET if len(packed) == _IPV4_ADDRESS_BYTES else socket.AF_INET6
    return socket.inet_ntop(family, packed)


def _to_utc(epoch_seconds: float) -> datetime | None:
    """Convert a capture timestamp to UTC, or None if it is outside the representable range.

    pcapng carries a 64-bit timestamp, so a capture can name an instant no `datetime` can hold.
    That is hostile input like any other and is contained here rather than allowed to raise.
    """
    try:
        return datetime.fromtimestamp(epoch_seconds, UTC)
    except (OverflowError, OSError, ValueError):
        return None

"""The network-layer manipulations, as transforms on an already-built capture.

PART R4. `docs/sim/coverage.md` found that the simulator could perturb a plant at two layers —
what the instruments report and what the actuators do — and that `phos.synth.traffic.modbus_frames`
builds the capture from a completed run and takes no manipulation at all. So three of R4's target
attacks had nowhere to attach: a value changed between the device and the historian, a device
answered with far more polls than a scan would make, and a stretch of captured traffic sent again.

This module is that layer, and its whole character is that it touches the *capture* and nothing
else. The plant's physics is untouched; its telemetry is untouched. That asymmetry is the point:
an operator reading the historian sees one thing, the wire carried another, and a detector that
compares the two has the evidence that separates them. Every function here takes a tuple of
`phos.synth.traffic.WireFrame` and returns a tuple of them — it reaches no device and opens no
socket, and `tests/synth/test_no_network.py` holds that for the whole package.

**Applied after the frames are built, not inside the builder.** `modbus_frames` is left exactly as
it was, so every capture produced before this module existed is byte-for-byte identical — the six
corpora in ``tests/synth/golden/`` are the proof. It is also the more faithful model: a tap on the
wire sees finished frames, not the generator's intentions.

**Duplicate sequence numbers are correct here and are not a bug to tidy away.** A repeated stretch
of traffic carries TCP sequence numbers that were already used, and `docs/sim/recon.md` §5 records
that the Modbus dissector does no stream reassembly — it decodes each application message where it
finds it. A capture whose sequence numbers were quietly renumbered would be a capture of an event
that never happened, so they are left as they are.
"""

from __future__ import annotations

import logging
import struct
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import timedelta
from typing import Final

from phos.synth.injection import TimeWindow
from phos.synth.traffic import MODBUS_PORT, WireFrame

__all__ = [
    "InTransitChange",
    "PollBurst",
    "TrafficReplay",
    "WireError",
    "WireManipulation",
    "apply_wire_events",
    "polled_values_in",
]

logger = logging.getLogger(__name__)

_MBAP_LENGTH: Final = 7
"""Bytes of MBAP header before the Modbus PDU: transaction id, protocol id, length, unit id."""

_FUNCTION_READ_HOLDING: Final = 3
_FUNCTION_WRITE_SINGLE: Final = 6
"""The two function codes the traffic writer emits, mirrored here so a change can be recognised."""


class WireError(ValueError):
    """Raised when a wire manipulation is asked for something it cannot do."""


def _is_response(frame: WireFrame) -> bool:
    """Return whether a frame is a server answering, i.e. coming *from* the Modbus port."""
    return frame.src_port == MODBUS_PORT


def _read_response_registers(payload: bytes) -> tuple[int, ...] | None:
    """Return the register values a read-holding response carries, or ``None`` if it is not one.

    The response layout is the MBAP header, then the function code, then a byte count, then that
    many bytes of big-endian register values. Anything that does not parse as exactly that is
    left alone — a write echo, a malformed frame, a handshake — because this is a reader, and a
    reader that guessed would corrupt frames it was never asked to touch.
    """
    if len(payload) < _MBAP_LENGTH + 2:
        return None
    pdu = payload[_MBAP_LENGTH:]
    if pdu[0] != _FUNCTION_READ_HOLDING:
        return None
    byte_count = pdu[1]
    body = pdu[2 : 2 + byte_count]
    if byte_count % 2 != 0 or len(body) != byte_count:
        return None
    return struct.unpack(f">{byte_count // 2}H", body)


def _transaction_id(payload: bytes) -> int | None:
    """Return the MBAP transaction identifier a frame carries, or ``None`` if it is too short.

    The server echoes it on the response, so it is how a response is paired back to the request
    that named the address it answers.
    """
    if len(payload) < 2:
        return None
    return int.from_bytes(payload[:2], "big")


def _read_request_address(payload: bytes) -> int | None:
    """Return the start address a read-holding request asks for, or ``None`` if it is not one."""
    pdu = payload[_MBAP_LENGTH:]
    if len(pdu) < 5 or pdu[0] != _FUNCTION_READ_HOLDING:
        return None
    return int.from_bytes(pdu[1:3], "big")


def _rewrite_first_register(payload: bytes, value: int) -> bytes:
    """Return a read-holding response with its first register replaced by ``value``.

    Only the first, because the attack this models changes one signal's reported count — the
    others on the same block pass through untouched, which is what makes the tampered reading
    disagree with the plant while its neighbours still agree with it.
    """
    header = payload[: _MBAP_LENGTH + 2]
    body = bytearray(payload[_MBAP_LENGTH + 2 :])
    struct.pack_into(">H", body, 0, value & 0xFFFF)
    return bytes(header) + bytes(body)


@dataclass(frozen=True)
class InTransitChange:
    """A reported register value altered between the device and the historian.

    The closest fit in the public ICS ATT&CK matrix is adversary-in-the-middle (see
    ``docs/sim/coverage.md`` for why the mapping is a reading of the technique and not a
    classification). It is the network-layer twin of `phos.synth.events.SensorReplay`: both make
    the wire say something the plant did not, and the difference is only where the lie is inserted
    — into the instrument's reading, or into the packet carrying it.

    Attributes:
        window: When the change is in force.
        address: The register start address whose block is targeted. The first register of a
            matching read response is rewritten.
        held_count: The raw 16-bit count to substitute. A count rather than an engineering value,
            because this acts on the wire, where everything is already a count — and because an
            attacker on the wire has the count and not the calibration to turn it back.

    Invariants:
        The count is a 16-bit unsigned value.
    """

    window: TimeWindow
    address: int
    held_count: int

    def __post_init__(self) -> None:
        """Refuse a count that is not a register value.

        Raises:
            WireError: If the count does not fit in 16 bits.
        """
        if not 0 <= self.held_count <= 0xFFFF:
            raise WireError(f"{self.held_count} is not a 16-bit register count")

    def rewrite(self, frames: Sequence[WireFrame]) -> tuple[WireFrame, ...]:
        """Return the frames with this block's read responses in the window altered.

        A response does not carry the address it answered, so it is paired back to its request by
        the MBAP transaction identifier the server echoes, keyed by the conversation so the same
        identifier on two PLCs is not confused — the pairing `tests/synth/test_outputs.py` already
        relies on. Only responses to a read of ``address`` are rewritten, so the tampered meter
        disagrees with the plant while every other signal on the same block still agrees: one
        false reading, which is what an in-transit hold looks like downstream.
        """
        pending: dict[tuple[str, str, int], int] = {}
        changed: list[WireFrame] = []
        for frame in frames:
            transaction = _transaction_id(frame.payload)
            if not _is_response(frame):
                address = _read_request_address(frame.payload)
                if address is not None and transaction is not None:
                    pending[(frame.src_ip, frame.dst_ip, transaction)] = address
                changed.append(frame)
                continue
            answered = (
                pending.pop((frame.dst_ip, frame.src_ip, transaction), None)
                if transaction is not None
                else None
            )
            if (
                answered == self.address
                and self.window.contains(frame.timestamp)
                and _read_response_registers(frame.payload) is not None
            ):
                changed.append(
                    replace(frame, payload=_rewrite_first_register(frame.payload, self.held_count))
                )
            else:
                changed.append(frame)
        return tuple(changed)


@dataclass(frozen=True)
class PollBurst:
    """Many extra read requests to one device in a short time, far above its scan rate.

    The closest fit is a denial-of-service technique (``docs/sim/coverage.md``). It models a device
    being asked for data much faster than a SCADA scan would ask — the shape that drives the
    command-interval features in `phos.atlas.packet.behaviour` to a coefficient of variation no
    honest poll loop produces. It injects *requests only*: a flood is the client misbehaving, and
    whether the device answers each one is the device's business and not the attacker's.

    Attributes:
        window: When the burst runs.
        count: How many extra requests to inject, spread evenly across the window.
        template_address: The register address the injected reads ask for. A real one, so the
            requests are well-formed and the dissector decodes them rather than refusing them —
            a flood of malformed frames is a different thing and belongs to the input-hostile path.

    Invariants:
        At least one request, and a non-negative address.
    """

    window: TimeWindow
    count: int
    template_address: int

    def __post_init__(self) -> None:
        """Refuse a burst that floods nothing.

        Raises:
            WireError: If the count is not positive or the address is negative.
        """
        if self.count < 1:
            raise WireError(f"a poll burst of {self.count} injects nothing")
        if self.template_address < 0:
            raise WireError(f"{self.template_address} is not a register address")

    def inject(self, frames: Sequence[WireFrame]) -> tuple[WireFrame, ...]:
        """Return the frames plus the burst, matched to a real conversation in the window.

        The injected requests borrow the addressing of a genuine read request already in the
        window — same client, same server, same ports — because a flood comes from an endpoint
        that is really talking to the device, not from an address that never appears elsewhere.
        That is also what makes it a harder case than a rogue source: nothing about *where* the
        requests come from is wrong, only how many and how fast.

        Returns the frames in timestamp order. Does nothing, and says so in the log, if no read
        request is found in the window to borrow from — there is no device to flood if nobody was
        talking to one.
        """
        exemplar = next(
            (
                frame
                for frame in frames
                if not _is_response(frame)
                and self.window.contains(frame.timestamp)
                and len(frame.payload) >= _MBAP_LENGTH + 1
                and frame.payload[_MBAP_LENGTH] == _FUNCTION_READ_HOLDING
            ),
            None,
        )
        if exemplar is None:
            logger.debug("poll burst found no conversation in its window; nothing injected")
            return tuple(frames)

        span = (self.window.end - self.window.start).total_seconds()
        step = span / self.count if span > 0 else 0.0
        request = _read_request(self.template_address)
        burst = [
            replace(
                exemplar,
                timestamp=self.window.start + timedelta(seconds=step * index),
                payload=request,
            )
            for index in range(self.count)
        ]
        return tuple(sorted((*frames, *burst), key=lambda frame: frame.timestamp))


@dataclass(frozen=True)
class TrafficReplay:
    """A stretch of captured traffic copied to a later instant and sent again.

    There is no dedicated public technique for this; adversary-in-the-middle is the nearest
    (``docs/sim/coverage.md``). It models an attacker who recorded a window of exchanges and
    played them back — the frames are genuine, byte for byte, including the readings they carry,
    so the replayed segment reports whatever the plant was doing *then* while the plant is now
    doing something else. It is the capture-layer counterpart of a sensor replay, and it reuses
    sequence numbers for the reason the module docstring gives.

    Attributes:
        source: The window to copy, by capture time.
        at: The instant the copy is placed at. The segment is shifted so its first frame lands
            here and the rest keep their original spacing.

    Invariants:
        The source window is non-empty and the destination does not fall inside it, which would
        interleave a segment with itself.
    """

    source: TimeWindow
    at: TimeWindow

    def __post_init__(self) -> None:
        """Refuse a replay that would overlap its own source.

        Raises:
            WireError: If the destination starts inside the source window.
        """
        if self.source.contains(self.at.start):
            raise WireError("a replay cannot be placed inside the window it copies")

    def inject(self, frames: Sequence[WireFrame]) -> tuple[WireFrame, ...]:
        """Return the frames plus a shifted copy of the source window."""
        captured = [frame for frame in frames if self.source.contains(frame.timestamp)]
        if not captured:
            logger.debug("traffic replay found nothing to copy in its source window")
            return tuple(frames)
        shift = self.at.start - captured[0].timestamp
        copied = [replace(frame, timestamp=frame.timestamp + shift) for frame in captured]
        return tuple(sorted((*frames, *copied), key=lambda frame: frame.timestamp))


def _read_request(address: int) -> bytes:
    """Return a well-formed read-holding request ADU for one register at ``address``."""
    pdu = struct.pack(">BHH", _FUNCTION_READ_HOLDING, address, 1)
    mbap = struct.pack(">HHHB", 0, 0, len(pdu) + 1, 1)
    return mbap + pdu


WireManipulation = InTransitChange | PollBurst | TrafficReplay
"""Any one of the three network-layer manipulations. A union rather than a protocol because the
three act on the capture through differently named methods — a rewrite in place, an injection of
new frames — and `apply_wire_events` dispatches on the type."""


def apply_wire_events(
    frames: Sequence[WireFrame],
    changes: Sequence[InTransitChange] = (),
    bursts: Sequence[PollBurst] = (),
    replays: Sequence[TrafficReplay] = (),
) -> tuple[WireFrame, ...]:
    """Apply every wire manipulation to a built capture, in a fixed order.

    The order is fixed — rewrites, then bursts, then replays — so the result is reproducible, and
    a replay copies the traffic *after* any rewrite has altered it, which is what a real recorder
    taps: whatever was on the wire, tampering included.

    Args:
        frames: The capture as `modbus_frames` built it.
        changes: In-transit value changes.
        bursts: Poll bursts.
        replays: Traffic replays.

    Returns:
        The manipulated capture, in timestamp order. With no manipulations it returns the frames
        unchanged, which is what keeps a corpus with none byte-identical.
    """
    result = tuple(frames)
    for change in changes:
        result = change.rewrite(result)
    for burst in bursts:
        result = burst.inject(result)
    for replay in replays:
        result = replay.inject(result)
    return result


def polled_values_in(frames: Sequence[WireFrame], window: TimeWindow) -> list[tuple[int, ...]]:
    """Return the register values every read response in a window carried.

    A small read-only helper for tests and for `assess_events`' network-layer counterpart: it lets
    a caller confirm what the wire actually said over a stretch without re-dissecting the capture,
    which is useful precisely because the wire can now disagree with the telemetry.
    """
    values: list[tuple[int, ...]] = []
    for frame in frames:
        # Only genuine responses, from the server port. A read *request* to a low address can
        # parse as a zero-register response by coincidence — its address's high byte reads as a
        # byte count of zero — so without the port check an injected poll would be counted as a
        # reading, which it is not.
        if not _is_response(frame) or not window.contains(frame.timestamp):
            continue
        registers = _read_response_registers(frame.payload)
        if registers:
            values.append(registers)
    return values

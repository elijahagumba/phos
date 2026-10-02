"""Modbus/TCP, dissected correctly and defensively.

Modbus is the most widely deployed and best documented ICS protocol, which makes it the right one
to do properly rather than the first of five done approximately. Everything here decodes one
application data unit: a 7-byte MBAP header — transaction id, protocol id, length, unit id —
followed by a PDU of a function code and its data.

**This module is an attack surface, and it is written as one.** Every byte it reads was chosen by
whoever sent the frame. The discipline, applied without exception:

- *Check before reading.* No index, slice or unpack happens until the bytes it needs are known to
  be present. There is no path where a length taken off the wire sizes a read that has not first
  been compared against the buffer that actually arrived.
- *Cap before allocating.* The MBAP length field is bounded to the protocol's own maximum before
  anything downstream uses it, so the largest structure any frame can ask this module to build is
  a 253-byte PDU — at most 2,000 unpacked coil bits. A frame cannot request a large allocation.
- *Refuse, never raise.* Every failure returns a `MalformedFrame` naming a specific reason. The
  function does not throw, and there is no `try` block wrapping the decode to make that true: it
  is true because the checks come first. `tests/atlas/packet/test_hardening.py` fires many
  thousands of random and mutated frames at it and asserts nothing escapes.

**Claiming is by port alone, deliberately.** A cheap structural pre-check would be easy and would
be wrong: bytes that are not Modbus arriving on port 502 would stop being claimed and would fall
through to `UnparsedMessage`, which reads as "no dissector covers this" — exactly the wrong thing
to say about rubbish aimed at a PLC. Claiming by port means such traffic reaches this dissector and
is recorded as malformed, which is a finding. See ADR 0012.

**Two limits worth knowing rather than discovering.** P1 does no TCP stream reassembly, so an ADU
split across segments, or two ADUs pipelined into one, is refused as `LENGTH_MISMATCH` or
`TRAILING_BYTES` rather than half-parsed — visible and countable, and the honest report of a
capability P1 does not have. And dissection is stateless: nothing correlates a response to its
request, so fields the response does not itself carry stay ``None`` instead of being back-filled
from a request this module never saw.
"""

import struct
from dataclasses import dataclass
from typing import Final

from phos.atlas.packet.frame import RawFrame, Transport
from phos.atlas.packet.messages import (
    MODBUS_PROTOCOL,
    Direction,
    MalformedFrame,
    MalformedReason,
    ModbusMessage,
)

__all__ = [
    "MAX_READ_COILS",
    "MAX_READ_REGISTERS",
    "MAX_WRITE_COILS",
    "MAX_WRITE_REGISTERS",
    "MBAP_HEADER_LENGTH",
    "MODBUS_PORT",
    "FunctionCode",
    "ModbusDissector",
]

MODBUS_PORT: Final = 502
"""The registered Modbus server port. Which end it sits on is what decides direction."""

MBAP_HEADER_LENGTH: Final = 7
"""Transaction id (2), protocol id (2), length (2), unit id (1)."""

_BYTES_BEFORE_LENGTH_COUNT: Final = 6
"""How many header bytes precede the region the MBAP length field measures.

The length field counts the unit id and the PDU — everything after itself — so a complete ADU is
this many bytes plus the declared length.
"""

_MBAP_PROTOCOL_ID: Final = 0
"""The only protocol id Modbus/TCP permits. Anything else is not this protocol."""

_MIN_LENGTH_FIELD: Final = 2
"""Smallest honest length: one unit id and one function code."""

_MAX_LENGTH_FIELD: Final = 254
"""Largest honest length: one unit id and the 253-byte maximum PDU.

This is the cap that makes every later allocation bounded, which is why it is checked before the
payload is even compared against it.
"""

_EXCEPTION_MASK: Final = 0x80
"""Bit 7 of the function code, set by a server reporting an exception."""

MAX_READ_COILS: Final = 2000
"""Protocol limit on coils or discrete inputs per read request."""

MAX_READ_REGISTERS: Final = 125
"""Protocol limit on registers per read request."""

MAX_WRITE_COILS: Final = 1968
"""Protocol limit on coils per write-multiple request."""

MAX_WRITE_REGISTERS: Final = 123
"""Protocol limit on registers per write-multiple request."""

_MAX_READ_RESPONSE_BYTES: Final = MAX_READ_REGISTERS * 2
"""Most data bytes a legal read response can carry: 125 registers, or the 2,000 coils that pack
into the same 250 bytes. Both limits land on the same number, which is what lets one check cover
either.

Load-bearing, and not implied by the MBAP length cap. A 253-byte PDU leaves room for a byte count
of 251, which would unpack to 2,008 coils — eight past what any legal read can return. The cap
bounds the *ADU*; this bounds what a count field inside it may then ask to be built.
"""

_BITS_PER_BYTE: Final = 8
_REGISTER_BYTES: Final = 2
_ADDRESS_AND_QUANTITY_BYTES: Final = 4
"""A starting address and a count, the body shared by read requests and write-multiple responses."""

_WRITE_MULTIPLE_PREAMBLE_BYTES: Final = 5
"""Address (2), quantity (2) and byte count (1), before a write-multiple request's data."""


class FunctionCode:
    """The Modbus function codes this dissector decodes.

    A namespace of constants rather than an `Enum`: an unrecognised code is a *valid* message here
    (`function_name` becomes ``"unknown(<n>)"``), so the code arriving off the wire is an ordinary
    integer that may legitimately fall outside this set, and an enum would invite converting it.
    """

    READ_COILS: Final = 1
    READ_DISCRETE_INPUTS: Final = 2
    READ_HOLDING_REGISTERS: Final = 3
    READ_INPUT_REGISTERS: Final = 4
    WRITE_SINGLE_COIL: Final = 5
    WRITE_SINGLE_REGISTER: Final = 6
    WRITE_MULTIPLE_COILS: Final = 15
    WRITE_MULTIPLE_REGISTERS: Final = 16


_FUNCTION_NAMES: Final[dict[int, str]] = {
    FunctionCode.READ_COILS: "read_coils",
    FunctionCode.READ_DISCRETE_INPUTS: "read_discrete_inputs",
    FunctionCode.READ_HOLDING_REGISTERS: "read_holding_registers",
    FunctionCode.READ_INPUT_REGISTERS: "read_input_registers",
    FunctionCode.WRITE_SINGLE_COIL: "write_single_coil",
    FunctionCode.WRITE_SINGLE_REGISTER: "write_single_register",
    FunctionCode.WRITE_MULTIPLE_COILS: "write_multiple_coils",
    FunctionCode.WRITE_MULTIPLE_REGISTERS: "write_multiple_registers",
}

_READ_FUNCTIONS: Final = frozenset(
    {
        FunctionCode.READ_COILS,
        FunctionCode.READ_DISCRETE_INPUTS,
        FunctionCode.READ_HOLDING_REGISTERS,
        FunctionCode.READ_INPUT_REGISTERS,
    }
)

_BIT_FUNCTIONS: Final = frozenset(
    {
        FunctionCode.READ_COILS,
        FunctionCode.READ_DISCRETE_INPUTS,
        FunctionCode.WRITE_MULTIPLE_COILS,
    }
)
"""Functions addressing coils or discrete inputs, whose data arrives bit-packed."""

_SINGLE_WRITE_FUNCTIONS: Final = frozenset(
    {FunctionCode.WRITE_SINGLE_COIL, FunctionCode.WRITE_SINGLE_REGISTER}
)


@dataclass(frozen=True)
class _Body:
    """The fields a PDU body yielded. Absent fields are ones the wire did not carry."""

    reference_address: int | None = None
    quantity: int | None = None
    values: tuple[int, ...] = ()
    exception_code: int | None = None


@dataclass(frozen=True)
class _Refusal:
    """Why a body could not be decoded, on its way to becoming a `MalformedFrame`."""

    reason: MalformedReason
    detail: str


class ModbusDissector:
    """Decodes Modbus/TCP application data units, and refuses everything else on port 502."""

    name: Final = MODBUS_PROTOCOL

    def claims(self, frame: RawFrame) -> bool:
        """Whether the frame is Modbus/TCP traffic by its ports.

        Args:
            frame: The peeled frame.

        Returns:
            True for TCP with the Modbus server port at either end. Port alone, with no look at
            the payload: see the module docstring for why a structural pre-check would hide
            exactly the traffic worth seeing.
        """
        return frame.transport is Transport.TCP and MODBUS_PORT in (
            frame.src.port,
            frame.dst.port,
        )

    def dissect(self, frame: RawFrame) -> ModbusMessage | MalformedFrame:
        """Decode one claimed frame, or record why it could not be decoded.

        Args:
            frame: The peeled frame. Its payload is entirely untrusted.

        Returns:
            A `ModbusMessage`, or a `MalformedFrame` naming the specific reason. Never raises,
            for any input whatsoever.
        """
        payload = frame.payload
        if len(payload) < MBAP_HEADER_LENGTH:
            return self._refuse(
                frame,
                MalformedReason.SHORT_HEADER,
                f"payload of {len(payload)} bytes is shorter than the "
                f"{MBAP_HEADER_LENGTH}-byte MBAP header",
            )

        transaction_id, protocol_id, declared_length, unit_id = struct.unpack_from(
            ">HHHB", payload, 0
        )
        if protocol_id != _MBAP_PROTOCOL_ID:
            return self._refuse(
                frame,
                MalformedReason.BAD_HEADER_FIELD,
                f"MBAP protocol id is {protocol_id}, and Modbus/TCP permits only "
                f"{_MBAP_PROTOCOL_ID}",
            )
        if not _MIN_LENGTH_FIELD <= declared_length <= _MAX_LENGTH_FIELD:
            return self._refuse(
                frame,
                MalformedReason.FIELD_OUT_OF_RANGE,
                f"MBAP length field is {declared_length}, outside the permitted "
                f"{_MIN_LENGTH_FIELD}-{_MAX_LENGTH_FIELD}",
            )

        expected_total = _BYTES_BEFORE_LENGTH_COUNT + declared_length
        if len(payload) < expected_total:
            return self._refuse(
                frame,
                MalformedReason.LENGTH_MISMATCH,
                f"MBAP length field of {declared_length} needs {expected_total} bytes but "
                f"{len(payload)} arrived",
            )
        if len(payload) > expected_total:
            return self._refuse(
                frame,
                MalformedReason.TRAILING_BYTES,
                f"{len(payload) - expected_total} bytes follow an ADU declaring "
                f"{expected_total}; P1 dissects one ADU per frame and does no stream reassembly",
            )

        protocol_data_unit = payload[MBAP_HEADER_LENGTH:expected_total]
        function_code = protocol_data_unit[0]
        body = _decode_body(function_code, protocol_data_unit[1:], _direction(frame))
        if isinstance(body, _Refusal):
            return self._refuse(frame, body.reason, body.detail)

        return ModbusMessage(
            source=frame.source,
            timestamp=frame.timestamp,
            src=frame.src,
            dst=frame.dst,
            direction=_direction(frame),
            transaction_id=int(transaction_id),
            unit_id=int(unit_id),
            function_code=function_code,
            function_name=_function_name(function_code),
            reference_address=body.reference_address,
            quantity=body.quantity,
            values=body.values,
            exception_code=body.exception_code,
        )

    def _refuse(self, frame: RawFrame, reason: MalformedReason, detail: str) -> MalformedFrame:
        """Record a claimed frame that failed validation, keeping its provenance."""
        return MalformedFrame(
            protocol=self.name,
            source=frame.source,
            timestamp=frame.timestamp,
            src=frame.src,
            dst=frame.dst,
            reason=reason,
            detail=detail,
            payload_length=len(frame.payload),
        )


def _direction(frame: RawFrame) -> Direction:
    """Which way the frame travelled, decided by which end holds the server port.

    A transport fact, kept as one. When both ends are the server port the answer is `UNKNOWN`
    rather than a guess, and the body is then left undecoded rather than read through a layout
    that may be the wrong one.
    """
    to_server = frame.dst.port == MODBUS_PORT
    from_server = frame.src.port == MODBUS_PORT
    if to_server and not from_server:
        return Direction.REQUEST
    if from_server and not to_server:
        return Direction.RESPONSE
    return Direction.UNKNOWN


def _function_name(function_code: int) -> str:
    """Readable name for a function code, including unrecognised and exception forms."""
    if function_code & _EXCEPTION_MASK:
        base = function_code & ~_EXCEPTION_MASK
        return f"{_FUNCTION_NAMES.get(base, f'unknown({base})')}.exception"
    return _FUNCTION_NAMES.get(function_code, f"unknown({function_code})")


def _decode_body(function_code: int, data: bytes, direction: Direction) -> _Body | _Refusal:
    """Decode a PDU body, choosing the layout from the function code and the direction.

    Args:
        function_code: The raw function code byte.
        data: The bytes after it, untrusted and of any length including zero.
        direction: Which way the frame travelled.

    Returns:
        The decoded fields, or a `_Refusal`. An unrecognised function code is decoded to an empty
        body rather than refused — the header was sound, and the frame is real traffic worth
        counting even though its body means nothing to us.
    """
    if function_code & _EXCEPTION_MASK:
        if len(data) != 1:
            return _Refusal(
                MalformedReason.SHORT_BODY,
                f"exception response carries {len(data)} data bytes, and exactly 1 is required",
            )
        return _Body(exception_code=data[0])

    if function_code not in _FUNCTION_NAMES:
        return _Body()
    if direction is Direction.UNKNOWN:
        return _Body()
    if direction is Direction.REQUEST:
        return _decode_request(function_code, data)
    return _decode_response(function_code, data)


def _decode_request(function_code: int, data: bytes) -> _Body | _Refusal:
    """Decode the body of a request."""
    if function_code in _READ_FUNCTIONS:
        if len(data) != _ADDRESS_AND_QUANTITY_BYTES:
            return _wrong_body_size(data, _ADDRESS_AND_QUANTITY_BYTES, "a read request")
        limit = MAX_READ_COILS if function_code in _BIT_FUNCTIONS else MAX_READ_REGISTERS
        quantity = _u16(data, 2)
        refusal = _check_quantity(quantity, limit)
        if refusal is not None:
            return refusal
        return _Body(reference_address=_u16(data, 0), quantity=quantity)

    if function_code in _SINGLE_WRITE_FUNCTIONS:
        return _decode_single_write(data)

    if len(data) < _WRITE_MULTIPLE_PREAMBLE_BYTES:
        return _Refusal(
            MalformedReason.SHORT_BODY,
            f"a write-multiple request needs at least {_WRITE_MULTIPLE_PREAMBLE_BYTES} body "
            f"bytes for its address, quantity and byte count, and {len(data)} arrived",
        )
    quantity = _u16(data, 2)
    byte_count = data[4]
    supplied = data[_WRITE_MULTIPLE_PREAMBLE_BYTES:]
    if len(supplied) != byte_count:
        return _byte_count_past_buffer(byte_count, len(supplied))

    if function_code == FunctionCode.WRITE_MULTIPLE_COILS:
        refusal = _check_quantity(quantity, MAX_WRITE_COILS)
        if refusal is not None:
            return refusal
        expected = (quantity + _BITS_PER_BYTE - 1) // _BITS_PER_BYTE
        if byte_count != expected:
            return _inconsistent_count(byte_count, expected, quantity, "coils")
        return _Body(
            reference_address=_u16(data, 0),
            quantity=quantity,
            values=_unpack_bits(supplied, quantity),
        )

    refusal = _check_quantity(quantity, MAX_WRITE_REGISTERS)
    if refusal is not None:
        return refusal
    expected = quantity * _REGISTER_BYTES
    if byte_count != expected:
        return _inconsistent_count(byte_count, expected, quantity, "registers")
    return _Body(
        reference_address=_u16(data, 0),
        quantity=quantity,
        values=_unpack_registers(supplied),
    )


def _decode_response(function_code: int, data: bytes) -> _Body | _Refusal:
    """Decode the body of a response."""
    if function_code in _READ_FUNCTIONS:
        if not data:
            return _Refusal(
                MalformedReason.SHORT_BODY,
                "a read response carries no byte count at all",
            )
        byte_count = data[0]
        supplied = data[1:]
        if len(supplied) != byte_count:
            return _byte_count_past_buffer(byte_count, len(supplied))
        if byte_count == 0:
            return _Refusal(
                MalformedReason.FIELD_OUT_OF_RANGE,
                "a read response declares a byte count of 0, and must return at least one byte",
            )
        if byte_count > _MAX_READ_RESPONSE_BYTES:
            return _Refusal(
                MalformedReason.FIELD_OUT_OF_RANGE,
                f"a read response declares {byte_count} data bytes, beyond the "
                f"{_MAX_READ_RESPONSE_BYTES} a legal read can return",
            )
        if function_code in _BIT_FUNCTIONS:
            return _Body(values=_unpack_bits(supplied, byte_count * _BITS_PER_BYTE))
        if byte_count % _REGISTER_BYTES:
            return _Refusal(
                MalformedReason.INCONSISTENT_COUNT,
                f"a register read response declares an odd byte count of {byte_count}, which "
                f"cannot describe whole {_REGISTER_BYTES}-byte registers",
            )
        return _Body(values=_unpack_registers(supplied))

    if function_code in _SINGLE_WRITE_FUNCTIONS:
        return _decode_single_write(data)

    if len(data) != _ADDRESS_AND_QUANTITY_BYTES:
        return _wrong_body_size(data, _ADDRESS_AND_QUANTITY_BYTES, "a write-multiple response")
    limit = MAX_WRITE_COILS if function_code in _BIT_FUNCTIONS else MAX_WRITE_REGISTERS
    quantity = _u16(data, 2)
    refusal = _check_quantity(quantity, limit)
    if refusal is not None:
        return refusal
    return _Body(reference_address=_u16(data, 0), quantity=quantity)


def _decode_single_write(data: bytes) -> _Body | _Refusal:
    """Decode a write-single body, which is identical in a request and its echoed response.

    The value is reported exactly as it arrived. For a coil, Modbus permits only ``0x0000`` and
    ``0xFF00``; anything else is a structurally sound frame carrying an illegal value, which is a
    behavioural finding for P2 rather than a parse failure.
    """
    if len(data) != _ADDRESS_AND_QUANTITY_BYTES:
        return _wrong_body_size(data, _ADDRESS_AND_QUANTITY_BYTES, "a write-single message")
    return _Body(reference_address=_u16(data, 0), values=(_u16(data, 2),))


def _check_quantity(quantity: int, limit: int) -> _Refusal | None:
    """Refuse a coil or register count of zero, or one beyond the protocol's limit."""
    if not 1 <= quantity <= limit:
        return _Refusal(
            MalformedReason.FIELD_OUT_OF_RANGE,
            f"a quantity of {quantity} is outside the permitted 1-{limit}",
        )
    return None


def _wrong_body_size(data: bytes, expected: int, described: str) -> _Refusal:
    """Refuse a fixed-size body that arrived at the wrong size."""
    return _Refusal(
        MalformedReason.SHORT_BODY,
        f"{described} needs exactly {expected} body bytes and {len(data)} arrived",
    )


def _byte_count_past_buffer(byte_count: int, supplied: int) -> _Refusal:
    """Refuse a declared byte count that does not match the bytes actually present."""
    return _Refusal(
        MalformedReason.SHORT_BODY,
        f"a byte count of {byte_count} does not match the {supplied} data bytes present",
    )


def _inconsistent_count(byte_count: int, expected: int, quantity: int, unit: str) -> _Refusal:
    """Refuse a byte count that contradicts the quantity it accompanies."""
    return _Refusal(
        MalformedReason.INCONSISTENT_COUNT,
        f"a byte count of {byte_count} contradicts {quantity} {unit}, which need {expected}",
    )


def _u16(data: bytes, offset: int) -> int:
    """Read a big-endian 16-bit field. The caller has already checked the bytes are present."""
    return int.from_bytes(data[offset : offset + _REGISTER_BYTES], "big")


def _unpack_bits(data: bytes, count: int) -> tuple[int, ...]:
    """Unpack ``count`` coils from bit-packed bytes, least-significant bit of each byte first.

    ``count`` is bounded by the caller against the protocol's limits, and the buffer is bounded by
    the MBAP length cap, so the tuple this builds can never exceed 2,000 entries.
    """
    return tuple(
        (data[index // _BITS_PER_BYTE] >> (index % _BITS_PER_BYTE)) & 1 for index in range(count)
    )


def _unpack_registers(data: bytes) -> tuple[int, ...]:
    """Unpack big-endian 16-bit registers. The caller has checked the length is even."""
    return tuple(
        int.from_bytes(data[offset : offset + _REGISTER_BYTES], "big")
        for offset in range(0, len(data), _REGISTER_BYTES)
    )

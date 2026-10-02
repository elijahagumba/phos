"""What a dissector is allowed to say: typed messages, and typed refusals.

Three outcomes, and every frame reaching a dissector produces exactly one of them:

- an **`IcsMessage`** — the bytes were understood, and the decoded fields say what was asked or
  answered;
- an **`UnparsedMessage`** — nobody claimed the frame, so all that is known is that traffic
  existed, how much of it, and between whom;
- a **`MalformedFrame`** — a dissector claimed the frame and then could not validate it.

**The three are distinct types rather than one type with a status field**, because the difference
between "we did not look at this" and "we looked and it was wrong" is the difference between a
coverage gap and a finding, and a consumer that can confuse them will eventually report one as the
other. `MalformedFrame` deliberately does not inherit `IcsMessage`: a parse failure is not a
message, and no ``isinstance`` check downstream can be tricked into treating it as decoded traffic.

**Nothing is silently dropped.** Traffic on a protocol no dissector implements still produces an
object. That is what makes coverage measurable instead of assumed — a capture where 90% of frames
come back `UnparsedMessage` is a capture Atlas mostly cannot hear, and P1 would rather say so.

**Fields are populated only where the wire actually carried them.** A Modbus read *response*
carries a byte count but not the address that was read, so `reference_address` is ``None`` there
rather than back-filled from the request. Recovering it would need request/response correlation,
which is stateful, which is not P1. A ``None`` here means "the bytes did not say", never "we did
not bother", and never a guess.

**Every numeric field is bounded.** The values arrive from bytes an adversary chose, so the model
refuses anything outside the protocol's own range. Those bounds are also the tripwire the fuzz
suite in `tests/atlas/packet/test_hardening.py` depends on: a decode that ran past its buffer or
misread a field width produces a value outside the range and fails loudly here, rather than
flowing on as a plausible-looking number. See ADR 0012.
"""

from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from phos.atlas.packet.frame import Endpoint, FrameSource
from phos.ontology import UtcDatetime

__all__ = [
    "MAX_REGISTER_VALUE",
    "MODBUS_PROTOCOL",
    "UNKNOWN_PROTOCOL",
    "Direction",
    "IcsMessage",
    "MalformedFrame",
    "MalformedReason",
    "ModbusMessage",
    "UnparsedMessage",
]

MAX_REGISTER_VALUE: int = 0xFFFF
"""Largest value a 16-bit Modbus register or address field can hold."""

MAX_BYTE_VALUE: int = 0xFF
"""Largest value a one-byte protocol field can hold."""

MODBUS_PROTOCOL: str = "modbus"
"""Name `ModbusMessage` reports, and the name on a `MalformedFrame` the Modbus dissector refused."""

UNKNOWN_PROTOCOL: str = "unknown"
"""Protocol name for traffic no dissector claimed. Names the absence of a dissector, not a guess."""

_Register = Annotated[int, Field(ge=0, le=MAX_REGISTER_VALUE)]
"""One decoded value: a 16-bit register, or a single coil expressed as 0 or 1."""


class Direction(str, Enum):
    """Which way a message was travelling.

    ``UNKNOWN`` is a real answer, not a failure. It is what an honest dissector reports when the
    transport cannot settle the question — traffic between two server ports, say — and it stops
    a request layout being applied to response bytes on a guess.
    """

    REQUEST = "REQUEST"
    RESPONSE = "RESPONSE"
    UNKNOWN = "UNKNOWN"


class MalformedReason(str, Enum):
    """Why a dissector refused a frame it had claimed.

    The members name *shapes* of failure rather than fields of any one protocol, so a DNP3 or
    S7comm dissector added later reuses them instead of inventing a parallel vocabulary. The
    specifics go in `MalformedFrame.detail`.

    Attributes:
        SHORT_HEADER: Fewer bytes present than the protocol's fixed header requires.
        BAD_HEADER_FIELD: A header field held a value the protocol does not permit.
        LENGTH_MISMATCH: A declared length disagreed with the bytes actually present.
        TRAILING_BYTES: More bytes followed the message than its declared length accounts for.
        SHORT_BODY: The body was shorter than the function or command within it requires.
        FIELD_OUT_OF_RANGE: A count or quantity exceeded the protocol's stated limit.
        INCONSISTENT_COUNT: Two count fields that must agree did not.
    """

    SHORT_HEADER = "SHORT_HEADER"
    BAD_HEADER_FIELD = "BAD_HEADER_FIELD"
    LENGTH_MISMATCH = "LENGTH_MISMATCH"
    TRAILING_BYTES = "TRAILING_BYTES"
    SHORT_BODY = "SHORT_BODY"
    FIELD_OUT_OF_RANGE = "FIELD_OUT_OF_RANGE"
    INCONSISTENT_COUNT = "INCONSISTENT_COUNT"


class IcsMessage(BaseModel):
    """A frame a dissector understood, with its provenance intact.

    The base carries only what is true of any industrial protocol message. Everything a specific
    protocol decodes lives on its subclass, so adding a protocol never widens this type.

    Attributes:
        protocol: Name of the protocol the message was decoded as.
        source: The capture and frame index the bytes came from.
        timestamp: When the frame was captured, timezone-aware UTC.
        src: The sending endpoint.
        dst: The receiving endpoint.
        direction: Whether this was a request, a response, or undetermined.
    """

    model_config = ConfigDict(frozen=True)

    protocol: str = Field(min_length=1)
    source: FrameSource
    timestamp: UtcDatetime
    src: Endpoint
    dst: Endpoint
    direction: Direction


class ModbusMessage(IcsMessage):
    """One Modbus/TCP application data unit, decoded.

    **How to read `values`.** Modbus addresses two different things and the field reflects which:

    - *Register* functions (3, 4, 6, 16) — one entry per 16-bit register, in wire order.
    - *Bit-packed coil payloads* (read responses for functions 1 and 2, and write-multiple-coils
      requests, function 15) — one entry per coil, ``0`` or ``1``, unpacked least-significant-bit
      first as Modbus packs them. Where the wire carries the coil count (function 15) exactly that
      many are unpacked; where it does not (functions 1 and 2 responses carry a byte count and
      nothing else, because the count was in the *request*) all ``byte_count * 8`` bits are
      unpacked and up to seven of the trailing entries are padding. Distinguishing them would need
      request/response correlation, which P1 does not do, so the padding is reported rather than
      guessed away.
    - *Function 5*, write single coil — a single entry holding the raw 16-bit field, ``0x0000`` or
      ``0xFF00``, because that is a 16-bit field on the wire and not a packed bit. Values other
      than those two are illegal in the protocol but are reported as they arrived: the frame is
      structurally sound, and whether a device should have sent it is a behavioural question for
      P2, not a parse failure.
    - Messages carrying no data payload — read requests, write-multiple responses — hold ``()``.

    Attributes:
        transaction_id: MBAP transaction identifier, echoed by the server.
        unit_id: MBAP unit identifier — the addressed device behind a gateway.
        function_code: The raw function code byte. For an exception response this is the original
            code with bit 7 set, e.g. ``0x83``, because that is what the wire said.
        function_name: Readable name, e.g. ``"read_holding_registers"``. An unrecognised code
            becomes ``"unknown(<n>)"`` — a decoded message, not a failure. An exception response
            is suffixed ``".exception"``.
        reference_address: Starting address, where the wire carried one.
        quantity: Number of coils or registers asked for, where the wire carried one.
        values: The decoded data, read as described above.
        exception_code: The Modbus exception code, set only on an exception response.
    """

    model_config = ConfigDict(frozen=True)

    protocol: str = Field(default=MODBUS_PROTOCOL, min_length=1)
    transaction_id: int = Field(ge=0, le=MAX_REGISTER_VALUE)
    unit_id: int = Field(ge=0, le=MAX_BYTE_VALUE)
    function_code: int = Field(ge=0, le=MAX_BYTE_VALUE)
    function_name: str = Field(min_length=1)
    reference_address: int | None = Field(default=None, ge=0, le=MAX_REGISTER_VALUE)
    quantity: int | None = Field(default=None, ge=0)
    values: tuple[_Register, ...] = ()
    exception_code: int | None = Field(default=None, ge=0, le=MAX_BYTE_VALUE)


class UnparsedMessage(IcsMessage):
    """Traffic no dissector claimed, recorded so the coverage gap is visible.

    Carries no decoded content by design — inventing structure for a protocol P1 does not
    implement would be worse than saying nothing. What it does carry is enough to measure how much
    of a capture Atlas can actually hear, and enough for a later dissector to be aimed at the
    ports that matter.

    Attributes:
        payload_length: Size of the transport payload that went undissected, in bytes.
    """

    model_config = ConfigDict(frozen=True)

    protocol: str = Field(default=UNKNOWN_PROTOCOL, min_length=1)
    direction: Direction = Direction.UNKNOWN
    payload_length: int = Field(ge=0)


class MalformedFrame(BaseModel):
    """A frame a dissector claimed and then refused, with the reason recorded.

    Deliberately not an `IcsMessage`. Malformed traffic near an industrial protocol is itself
    behaviourally interesting — it is what a fuzzing or reconnaissance tool leaves behind — so it
    is kept, but keeping it as a *message* would let a consumer count it as understood traffic.

    The payload is recorded by length only. Retaining adversary-chosen bytes in memory and passing
    them downstream buys nothing P2 needs and widens what the rest of the system has to be safe
    against; the frame index is enough to go back to the capture and look.

    Attributes:
        protocol: The dissector that claimed and then refused the frame.
        source: The capture and frame index the bytes came from.
        timestamp: When the frame was captured, timezone-aware UTC.
        src: The sending endpoint.
        dst: The receiving endpoint.
        reason: Which shape of failure this was.
        detail: The specifics, in a sentence, naming the values that disagreed. Required and
            non-empty: an unexplained rejection cannot be audited, which is the point of the type.
        payload_length: Size of the payload that failed to parse, in bytes.
    """

    model_config = ConfigDict(frozen=True)

    protocol: str = Field(min_length=1)
    source: FrameSource
    timestamp: UtcDatetime
    src: Endpoint
    dst: Endpoint
    reason: MalformedReason
    detail: str = Field(min_length=1)
    payload_length: int = Field(ge=0)

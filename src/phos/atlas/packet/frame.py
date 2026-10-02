"""What a frame is once the link, network and transport layers have been peeled off.

These are the types every dissected message is anchored to. They exist so that the answer to "why
does Atlas believe this?" can always be walked back to a specific run of bytes in a specific file:
`FrameSource` names the capture and the position within it, and every message a dissector produces
carries one.

**Traceability is a field, not a convention.** Constitution §3.2 requires that anything a user
could see be reconstructable from stored evidence. A packet adapter is the furthest point from the
screen in that chain, so it is where the chain is most easily broken — a parser that yields bare
tuples of decoded values is impossible to audit once the capture has moved on. Nothing here is
produced without its provenance attached.

**`RawFrame.frame_index` is computed from `FrameSource`, not stored beside it.** Two fields
holding the same number is two fields that can disagree, and a disagreement between "which frame
was this" and "which frame do we say this was" is exactly the kind of quiet corruption that makes
an audit trail worthless. See ADR 0012.

This module knows nothing about any industrial protocol. It is the boundary between "bytes off the
wire" and "a message we claim to understand", and the split is what lets a second dissector be
added later without touching the reader.
"""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, computed_field

from phos.ontology import UtcDatetime

__all__ = [
    "Endpoint",
    "FrameSource",
    "RawFrame",
    "Transport",
]

MAX_PORT: int = 65535
"""Largest value a TCP or UDP port number can take."""


class Transport(str, Enum):
    """The transport layer a frame's payload was carried over.

    Only the two the reader peels. A frame carried over anything else never becomes a `RawFrame`
    at all — it is counted as undecodable so the gap in coverage stays visible.
    """

    TCP = "TCP"
    UDP = "UDP"


class Endpoint(BaseModel):
    """One end of a conversation: an IP address and a port.

    Attributes:
        ip: The address in presentation form, IPv4 or IPv6. A string rather than an
            `ipaddress` object so the type stays trivially JSON-serialisable, matching the
            ontology's convention for identifiers.
        port: The TCP or UDP port, 0 to 65535. Bounded here rather than trusted, because the
            value arrives from adversary-supplied bytes.
    """

    model_config = ConfigDict(frozen=True)

    ip: str = Field(min_length=1)
    port: int = Field(ge=0, le=MAX_PORT)


class FrameSource(BaseModel):
    """Where a frame came from, precisely enough to go back and look at it.

    Attributes:
        capture: Path of the capture file the frame was read from, as a string so the value
            survives serialisation unchanged.
        frame_index: Zero-based position of the frame within that capture, counting every frame
            the reader saw — including the ones it could not decode — so the index still matches
            what a packet analyser shows for the same file.
    """

    model_config = ConfigDict(frozen=True)

    capture: str = Field(min_length=1)
    frame_index: int = Field(ge=0)


class RawFrame(BaseModel):
    """A frame peeled down to its transport payload, with its provenance attached.

    This is what a dissector is handed. It has been decoded far enough to know who was talking to
    whom and over what, and no further: the payload is untouched bytes, because deciding what they
    mean is the dissector's job and doing any of it here would put protocol knowledge in the
    reader.

    Attributes:
        source: The capture and frame index this came from.
        timestamp: When the frame was captured, timezone-aware UTC.
        transport: TCP or UDP.
        src: The sending endpoint.
        dst: The receiving endpoint.
        payload: The transport payload, exactly as captured. May be empty — a bare TCP
            acknowledgement carries no bytes.
    """

    model_config = ConfigDict(frozen=True)

    source: FrameSource
    timestamp: UtcDatetime
    transport: Transport
    src: Endpoint
    dst: Endpoint
    payload: bytes

    @computed_field  # type: ignore[prop-decorator]
    @property
    def frame_index(self) -> int:
        """Position of this frame in its capture, read from `source`.

        Computed rather than stored so there is exactly one place the number lives and no way for
        a frame to disagree with the source it names.
        """
        return self.source.frame_index

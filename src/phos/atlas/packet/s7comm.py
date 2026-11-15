"""ISO-on-TCP: the envelope S7 travels in, read as an envelope and named as one.

S7 is not an open standard. Siemens says so in its own manual — S7 communication is
"vendor-specific communication between SIMATIC CPUs (not an open standard)" (*Communication
Function Manual*, 11/2025 A5E03735815-AN, §9, printed p.161) — and the spec-auditor for this lane
searched that manual family and found no published job byte, no opcode and no frame layout. What
*is* published, in primary text, is the envelope S7 is carried in: RFC 1006 puts ISO transport on
TCP, RFC 905 defines the TPDU inside it, and IANA registers exactly one service on port 102,
``iso-tsap``, "ISO-TSAP Class 0".

**So this module reads the envelope, and says so.** The message it emits is ``iso-tsap`` — the
registered service name — and never ``s7comm``. A consumer reading that name knows Atlas has read
the transport S7 travels in and has not read S7. That is the lane's honest ceiling (ADR 0347), and
it is enforced by the type rather than by convention: `IsoTsapMessage.protocol` is a
``Literal["iso-tsap"]``, so no caller can build a message claiming otherwise, and nothing here can
produce a `ProgramAct`, a station or a peer role, because no such field exists.

**What is decoded is two headers, and nothing behind them.** A TPKT header (version, reserved,
packet length, RFC 1006 §6) and a COTP TPDU header (length indicator and TPDU code, RFC 905 §13.2,
plus the fixed part the code names — the references and reason of a DR, the reject cause of an ER,
the credit and sequence field of an ED, and the EOT and TPDU-NR of a DT). Each fixed part is checked
for before it is read, and a TPDU whose header cannot contain its own fixed part is refused rather
than reported as a message with missing fields. The application octets after the COTP header are
**counted and carried by length only** — not decoded, not stored, not named S7. That is what
`user_data_length` reports, and it is the whole of what this module says about them.

**This module is an attack surface, and it is written as one.** Every byte it reads was chosen by
whoever sent the frame. The discipline, applied without exception:

- *Check before reading.* No index, slice or unpack happens until the bytes it needs are known to
  be present. The TPKT length is compared with the bytes that actually arrived before it is used as
  a slice bound, so a frame declaring 65,535 octets while carrying eight is a refusal and never an
  allocation.
- *Cap before allocating.* RFC 1006 §6 gives 65535 as the TPKT ceiling and 65531 as the TPDU
  ceiling, and the declared length is a 16-bit field, so 65535 is the largest value it can carry at
  all — the ceiling is the field's own width, which is why the check that can actually fail is the
  one against the buffer. The 128-octet CR bound (RFC 905 §13.3) and the 254-octet LI bound
  (RFC 905 §13.2.1, with 255 reserved) are checked as they are read. *65524 is deliberately absent:*
  RFC 1006 states it as a maximum TSDU and it contradicts the memo's own minus-3 rule and X.224
  §13.7.5, so it is quoted in ADR 0347 and coded nowhere.
- *Refuse, never raise.* Every failure returns a `MalformedFrame` naming a specific reason. There is
  no `try` block wrapping the decode to make that true: it is true because the checks come first.
  `tests/atlas/packet/test_s7comm_hardening.py` fires thousands of random, mutated, truncated and
  length-lying frames at it and asserts nothing escapes.

**Claiming is by port alone, deliberately.** Port 102 is a port claim — for ``iso-tsap``, which IANA
registers there, not for S7 and not for MMS (ADR 0345, resolved by ADR 0347). A structural
pre-check would be easy and would be wrong: bytes that are not an ISO-on-TCP envelope arriving on
102 would stop being claimed and would fall through to `UnparsedMessage`, which reads as "no
dissector covers this" — exactly the wrong thing to say about rubbish aimed at a PLC. Claiming by
port means such traffic reaches this dissector and is recorded as malformed, which is a finding.
The same argument Modbus makes for 502 (ADR 0012), applied to 102.

**Three things this module refuses to refuse**, each because the bytes on this port are lawful and a
refusal would manufacture malformations on real Siemens traffic:

- *A non-zero reserved octet.* RFC 1006 never defines the field; RFC 2126 §4.3 assigns it 0 and
  §6.10 says it "should be ignored on input" for interoperability with RFC 1006. It is recorded on
  every decoded message and never a refusal reason, for any value.
- *A COTP class other than 0.* Siemens labels its own open-communication transport "(Class 4)"
  (11/2025 -AN, §8.2, Table 8-1) and RFC 2126 adds class 2 over TCP. A hard class check would
  refuse the traffic this lane exists to read. The octet is recorded where the wire carried it and
  nothing is inferred from it.
- *A CR or CC carrying user data or a third parameter.* RFC 905 §8.2.2 c) and d) forbid both in bare
  ISO class 0, but RFC 1006 §5 opens with "identical to the protocol for ISO transport class 0,
  **with the following exceptions**", the first being that initial data "may be exchanged during
  connection establishment". What *is* kept from that clause is the genuine bound: a CR TPDU shall
  not exceed 128 octets (RFC 905 §13.3), and it is applied to the declared header length rather than
  to the user data, because the declaration keeps user data lawful here.

**Only a class-0 DT is read at all, and the rule that excludes the rest is the length indicator.**
The DT fixed part decoded here is the class-0 one — EOT is bit 8 of octet 3, TPDU-NR is bits 7-1 of
octet 3 (RFC 905 §13.7.3) — and the TPDU code matcher is the exact ``1111 0000`` that text prints.

A class-4 DT carries a longer fixed part: DST-REF first, then TPDU-NR and EOT, then a variable part
(RFC 905 §13.7.1 b), and its extended format runs to LI 4 or 7. Because the class-0 DT has no
variable part at all, this module requires a length indicator of exactly 2 and **refuses every
other value** as `INCONSISTENT_COUNT`. That refusal is what makes a class-4 DT unreachable here: its
header cannot be 2 octets, so it is refused rather than misread through a layout one octet too
short. Nothing in this module ever decodes a class-4 DT's fields, and no message can report them.

**That is the right outcome for this port, and the cost is worth stating.** RFC 1006 §6 says
"only TPDUs formatted for transport class 0 are exchanged" on TCP 102, so a class-4 DT is outside
what this lane was declared to read; refusing it is the honest answer rather than a guess at its
layout. The consequence an operator will actually see is a connection whose CR reports
``cotp_class=4`` — the octet is recorded, and never a refusal reason — followed by **refused data
TPDUs**. That is the shape of a class-4 estate on this port: setup visible, data refused. It is a
real limit of the lane, and it is recorded here rather than discovered in a capture.

Because every accepted DT is class 0, `eot` and `tpdu_nr` are always populated on a decoded message
and are never ``None`` there. A DT carrying ROA (``1111 0001``) is named ``unknown(<n>)`` rather
than guessed at: the bytes did not say which layout to use, and guessing one is the failure mode
this package exists to prevent.

**The length-indicator rule also fixes what the DT count can report.** `user_data_length` is derived
from the verified TPKT length rather than from the length indicator, so one attacker-chosen octet
can no longer declare a whole S7 job to be header: before both changes, the same 22 application
octets reported 22, 21, 17, 11 and 0 octets of user data as the length indicator varied.

**A limitation worth knowing rather than discovering:** this module dissects exactly one TPKT per
frame and does no TCP stream reassembly. A TPKT split across two segments is refused as
`LENGTH_MISMATCH` (the first segment declares more than it carries) or `BAD_HEADER_FIELD` (a later
segment begins mid-TPKT, so its first octet is not version 3), and two TPKTs coalesced into one
segment are refused as `TRAILING_BYTES`. That matters in practice: a 5,000-octet program download
becomes four segments at an ordinary 1,460-octet MSS and none of them decodes. The refusal is the
honest report of a capability this module does not have, and it is visible and countable rather than
half-parsed. A caller that needs stream reassembly should use the reassembly foundation
(`reassembly.ContiguousStream.take_pdu`) and hand this module the complete PDU it yields; nothing in
this module imports or calls it, by design.

**Nothing is inferred from a TSAP.** RFC 905 §13.3.4 a) defines TSAP-ID as an opaque
"identifier of the calling or called TSAP" and gives it no structure. Any meaning in an S7 TSAP is a
Siemens convention no primary source publishes, so `calling_tsap` and `called_tsap` hold the
parameter's octets exactly as they arrived, and ``None`` where the wire carried no such parameter.
``None`` means "the bytes did not say", never "we did not look".

**A consequence worth stating, so nobody discovers it:** an IEC 61850 MMS frame is an ISO-on-TCP
frame, and this module decodes it as a valid `IsoTsapMessage` with its application payload unread.
That is correct. The module does not claim the frame is S7 and does not claim it is MMS — it claims
the envelope, which both of them are.
"""

import struct
from dataclasses import dataclass
from typing import Final, Literal

from pydantic import ConfigDict, Field

from phos.atlas.packet.frame import RawFrame, Transport
from phos.atlas.packet.messages import (
    MAX_BYTE_VALUE,
    Direction,
    IcsMessage,
    MalformedFrame,
    MalformedReason,
)

__all__ = [
    "CALLED_TSAP_PARAMETER",
    "CALLING_TSAP_PARAMETER",
    "CR_MAX_OCTETS",
    "ISO_TSAP_PORT",
    "ISO_TSAP_PROTOCOL",
    "LI_RESERVED_FOR_EXTENSIONS",
    "MAX_LENGTH_INDICATOR",
    "TPDU_MAX_OCTETS",
    "TPKT_HEADER_LENGTH",
    "TPKT_MAX_OCTETS",
    "TPKT_MIN_OCTETS",
    "TPKT_VERSION",
    "IsoTsapDissector",
    "IsoTsapMessage",
    "IsoTsapProtocolName",
    "TpduCode",
]

ISO_TSAP_PORT: Final = 102
"""The registered ``iso-tsap`` port, tcp and udp, "ISO-TSAP Class 0".

Exactly one service is registered on 102. Claiming the port claims ISO transport on TCP, which is a
claim about the registry; it is not a claim that the payload is S7, and not a claim that it is MMS.
"""

IsoTsapProtocolName = Literal["iso-tsap"]
"""The only protocol name this module may report, as a type rather than a habit.

``str`` would let a caller — or a future edit — report ``"s7comm"``, which would say Atlas had read
an application it has no published format for. A ``Literal`` makes that unrepresentable.
"""

ISO_TSAP_PROTOCOL: Final[IsoTsapProtocolName] = "iso-tsap"
"""IANA's name for the service on port 102, and the name every message from here carries."""

TPKT_HEADER_LENGTH: Final = 4
"""Version (1), reserved (1), packet length (2), per RFC 1006 §6."""

TPKT_VERSION: Final = 3
"""The only value RFC 1006 §6 permits: "This field is always 3 for the version described"."""

TPKT_MIN_OCTETS: Final = 7
"""Smallest legal TPKT, counting the header (RFC 1006 §6).

Load-bearing, and it corroborates the COTP side independently: 4 octets of TPKT header plus the
3-octet class-0 DT header is exactly 7, so a 7-octet packet is a legal DT carrying no user data and
not a short one.
"""

TPKT_MAX_OCTETS: Final = 65535
"""Largest TPKT, counting the header (RFC 1006 §6).

Also the width of the field that carries it: a 16-bit length cannot declare more, so this bound
holds by construction and the check that can actually fail is the one against the bytes present.
"""

TPDU_MAX_OCTETS: Final = 65531
"""Largest TPDU inside a maximum TPKT: 65535 less the 4-octet header (RFC 1006 §6).

The coded bound on what may follow the TPKT header. It bounds `user_data_length` in the model, so a
decode that ran past its buffer fails loudly at validation rather than flowing on as a huge number.
"""

MAX_LENGTH_INDICATOR: Final = 254
"""Largest legal length indicator (RFC 905 §13.2.1)."""

LI_RESERVED_FOR_EXTENSIONS: Final = 255
"""The one length-indicator value RFC 905 §13.2.1 reserves "for possible extensions".

Refused as `FIELD_OUT_OF_RANGE`: it does not describe a header this module can measure, and reading
it as 255 octets would be inventing a header the standard has not defined.
"""

CR_MAX_OCTETS: Final = 128
"""A CR TPDU "shall not exceed 128 octets" (RFC 905 §13.3).

Applied to the declared header length, not to the user data: RFC 1006 §5 permits initial data during
connection establishment, and refusing a CR for carrying it would refuse lawful setup (audit D6).
"""

CALLING_TSAP_PARAMETER: Final = 0xC1
"""Parameter code ``1100 0001``, the calling TSAP-ID (RFC 905 §13.3.4 a)."""

CALLED_TSAP_PARAMETER: Final = 0xC2
"""Parameter code ``1100 0010``, the called TSAP-ID (RFC 905 §13.3.4 a)."""

_TPDU_NIBBLE_MASK: Final = 0xF0
"""Bits 8-5 of the TPDU code octet, where CR and CC carry their credit field (RFC 905 §13.1)."""

_COTP_MIN_HEADER_OCTETS: Final = 3
"""Length indicator, code, and octet 3 — the least a TPDU that names a kind can carry.

Guaranteed by `TPKT_MIN_OCTETS` being ``TPKT_HEADER_LENGTH + 3``; checked anyway, so the safety of
the slice below does not rest on a constant two modules away.
"""

_DT_LENGTH_INDICATOR: Final = 2
"""A class-0 DT's length indicator is **exactly 2**, not a floor (RFC 905 §13.7.1 a).

The normal format for classes 0 and 1 is ``| LI | DT | TPDU-NR and EOT | User Data |`` — no
variable part. Its header is therefore the code octet and octet 3, and §13.2.1 defines LI as the
header length *excluding* the length indicator and user data, so the only truthful value is 2. An LI
above 2 would declare some of the user data to be a variable part the format does not have, which
§13.2.2.1 calls a protocol error: "if the fixed part cannot be contained within the header (as
defined by LI) this is a protocol error".

Pinning it is what stops one attacker-chosen octet from hiding a whole S7 job: before this, varying
the LI over the same 22 application octets made the same frame report 22, 21, 17, 11 and 0 octets of
user data.
"""

_DT_HEADER_OCTETS: Final = 3
"""A class-0 DT header from the length indicator on: LI, code, TPDU-NR/EOT (RFC 905 §13.7.1 a)."""

_ED_HEADER_OCTETS: Final = 4
"""An ED header from the length indicator onward: LI, code, credit, TPDU-NR/EOT.

One more than the DT's, because RFC 1006 §6's expedited format carries a credit octet between the
code and the sequence field. That extra octet is the difference between a correct user-data count
and a silent off-by-one, so it is named rather than written as a bare ``4`` at the call site.
"""

_DR_FIXED_PART_OCTETS: Final = 6
"""A DR's fixed part is the code + DST-REF (2) + SRC-REF (2) + REASON (1): LI >= 6.

RFC 905 §13.5.1 gives the structure and §13.5.3 the fields. The code octet (octet 2) is inside the
header LI measures (§13.2.1), which is why this is 6 and not the 5 the field list alone suggests.
"""

_ER_FIXED_PART_OCTETS: Final = 4
"""An ER's fixed part is the code + DST-REF (2) + Reject Cause (1): LI >= 4 (RFC 905 §13.12.1)."""

_ED_LENGTH_INDICATOR: Final = 3
"""An ED's length indicator is **exactly 3**, not a floor (RFC 1006 §6).

RFC 1006 gives the expedited TPDU as ``| header length | code | credit | TPDU-NR and EOT | user
data |`` and says its format is "nearly identical to the format for the normal data, DT, TPDU. The
only difference is that the value used for the TPDU's code is ED, not DT". There is no variable
part column, exactly as for the class-0 DT, so three octets of header is the only truthful value and
an LI above it would declare a variable part the format does not have.

This is what stops the DT defect from surviving here under another name: with a *floor* of 3, the
same six application octets reported 6, 5, 4 and 1 octets of user data as one attacker-chosen octet
varied.
"""

_ED_MAX_USER_DATA: Final = 16
"""Most octets an expedited TSDU may carry (RFC 1006 §6, quoting the TP specification).

"Note that the TP specification limits the size of an expedited transport service data unit (XSDU)
to 16 octets." RFC 905 §13.8.5 says the same field "contains an expedited TSDU (1 to 16 octets)".
Applies to ED only: a DT's user data is bounded by the TPKT length, not by this, because the XSDU is
the expedited service's unit and nothing else on this port has one.
"""

_EOT_MASK: Final = 0x80
"""EOT is bit 8 of octet 3, and RFC 905 §13.2 makes bit 8 the high bit (RFC 905 §13.7.3)."""

_TPDU_NR_MASK: Final = 0x7F
"""TPDU-NR occupies bits 7-1 of octet 3: the seven low bits, with no shift (RFC 905 §13.7.3).

RFC 905 §13.2 numbers bits from 1 at the *low* end, so bit 1 is worth 1 and bit 8 is worth 128.
"Bits 7-1" is therefore the low seven bits, and octet 3 is read as ``octet & 0x7F``. Shifting first
would read bits 8-2 instead and would put EOT back inside TPDU-NR, which is the error this constant
exists to make impossible.
"""

_CONNECT_FIXED_PART_OCTETS: Final = 6
"""A CR or CC fixed part is octets 2 to 7, so such a TPDU's LI is at least 6.

RFC 905 §13.3.1 gives the CR structure and §13.3.3 the fields; §13.4.1 and §13.4.3 say the same for
the CC. Octets 2 to 7 are the code, DST-REF (2), SRC-REF (2) and the class/options octet, so a
shorter header is a connection TPDU with no reference fields at all.

**This floor does not contradict the rule that a CR or CC carrying user data is never refused.** RFC
1006 §5 permits initial data during connection establishment, and its *Connection Establishment*
clause says the CR and CC "may exchange initial user data, using the user data fields of these
TPDUs" — the user data field lies *past* the LI-declared header, so it never shortens the fixed
part. A CR with LI 6 and 100 octets after it is lawful and still decodes; a CR with LI 2 has lost
its own reference fields and is the protocol error §13.2.2.1 names.
"""

_PREFERRED_CLASS_OCTET: Final = 6
"""Index of octet 7 in the COTP header: the same octet in a CR and in a CC (RFC 905 §13.3.3 e)."""

_PREFERRED_CLASS_SHIFT: Final = 4
"""Preferred class is bits 8-5 of octet 7 (RFC 905 §13.3.3 e)."""

_PREFERRED_CLASS_MASK: Final = 0x0F
"""Four bits: ``0000`` class 0 through ``0100`` class 4 (RFC 905 §13.3.3 e)."""

_PARAMETER_HEADER_OCTETS: Final = 2
"""A parameter is ``code``, ``length``, then that many octets of value (RFC 905 §13.3.4)."""

_DANGLING_VARIABLE_PART_OCTETS: Final = 1
"""A variable part this long cannot hold a parameter, so it cannot lawfully exist.

RFC 905 §13.2.3: "The variable part is used to define less frequently used parameters. If the
variable part is present, it shall contain one or more parameters", and its note fixes the
variable part's length as "LI minus the length of the fixed part". A parameter is at least two
octets — a code and a length — so a variable part of exactly one octet declares a parameter field
that is not there.

The rule is applied to every TPDU whose fixed-part size this module knows, rather than to the codes
that happen to carry a variable part today: CR and CC were already caught by the parameter walk in
`_decode_parameters`, and DR and ER were not, which is how the same shape survived on two of the
four. DT and ED are unaffected because their length indicators are exact values, so the difference
tested here can never be 1 for them.
"""

_MAX_PARAMETER_OCTETS: Final = 255
"""A parameter's length is one octet, so its value cannot be longer than this."""


class TpduCode:
    """The TPDU code octets this module names, from RFC 905 §13.1 Table 8.

    A namespace of constants rather than an `Enum`, for the reason `FunctionCode` gives: an
    unrecognised code is a *valid* message here (`message_type` becomes ``"unknown(<n>)"``), so the
    octet arriving off the wire is an ordinary integer that may legitimately fall outside this set.
    """

    CONNECTION_REQUEST: Final = 0xE0
    CONNECTION_CONFIRM: Final = 0xD0
    DISCONNECT_REQUEST: Final = 0x80
    DATA: Final = 0xF0
    ERROR: Final = 0x70
    EXPEDITED_DATA: Final = 0x10


_TPDU_NAMES: Final[dict[int, str]] = {
    TpduCode.DISCONNECT_REQUEST: "disconnect_request",
    TpduCode.DATA: "data",
    TpduCode.ERROR: "error",
    TpduCode.EXPEDITED_DATA: "expedited_data",
}
"""The codes RFC 905 Table 8 prints with no variable bits. CR and CC are matched by their nibble."""


@dataclass(frozen=True)
class _TsapParameters:
    """The TSAP-IDs a CR or CC carried. Absent parameters are ``None``, never guessed."""

    calling_tsap: bytes | None = None
    called_tsap: bytes | None = None


@dataclass(frozen=True)
class _DataTransferFields:
    """What a DT fixed part yielded, where the layout read was the one this module can interpret."""

    eot: bool | None = None
    tpdu_nr: int | None = None


@dataclass(frozen=True)
class _Refusal:
    """Why part of a claimed frame could not be decoded, on its way to a `MalformedFrame`."""

    reason: MalformedReason
    detail: str


class IsoTsapMessage(IcsMessage):
    """One ISO-on-TCP message: a TPKT header and the COTP TPDU it carries.

    Defined here rather than in `messages.py` so the shared model is not widened by a protocol that
    reads one envelope (ADR 0347).

    **How to read the fields.** Every field below was on the wire; nothing is back-filled from a
    connection this module never saw, and nothing is inferred from a value. `calling_tsap` and
    `called_tsap` are the parameter octets exactly as they arrived — RFC 905 §13.3.4 gives a TSAP-ID
    no structure, so no station, role or rack/slot is read out of them. `user_data_length` is a
    count, not a decode: the application octets are not carried, not stored and not named.

    Attributes:
        protocol: Always ``"iso-tsap"``. A ``Literal``, so ``"s7comm"`` is unrepresentable.
        tpkt_version: TPKT version octet. Always 3 on a decoded message, since anything else is
            refused; carried so the fact is inspectable rather than assumed.
        reserved_octet: The TPKT reserved octet, recorded for every value and never refused
            (RFC 2126 §6.10: "should be ignored on input").
        tpkt_length: The declared packet length, counting the 4-octet TPKT header. Always between
            `TPKT_MIN_OCTETS` and `TPKT_MAX_OCTETS` on a decoded message, and always equal to the
            number of octets present, because both disagreements are refusals.
        cotp_code: The raw TPDU code octet, including the credit bits of a CR or CC.
        message_type: Readable name of the TPDU kind — ``"connection_request"``,
            ``"connection_confirm"``, ``"disconnect_request"``, ``"data"``, ``"error"``,
            ``"expedited_data"``, or ``"unknown(<n>)"`` for a code RFC 905 does not name here. An
            unknown code is a decoded message, not a failure: the envelope was sound.
        eot: Bit 8 of octet 3 of a DT, and always populated on one: every accepted DT is a class-0
            DT, because any other length indicator is refused. ``None`` for every non-DT TPDU, whose
            fixed part has no EOT field.
        tpdu_nr: Bits 7-1 of octet 3 of a DT, zero in class 0, and always populated on one for the
            same reason. ``None`` for every non-DT TPDU.
        cotp_class: Preferred class from octet 7 of a CR or CC. ``None`` for every other TPDU,
            because a bare DT does not carry its class and this module does not guess it.
        calling_tsap: The 0xC1 parameter's octets, where a CR or CC carried one.
        called_tsap: The 0xC2 parameter's octets, where a CR or CC carried one.
        user_data_length: Octets after the COTP header, counted and carried by length only.
    """

    model_config = ConfigDict(frozen=True)

    protocol: IsoTsapProtocolName = ISO_TSAP_PROTOCOL
    tpkt_version: int = Field(ge=0, le=MAX_BYTE_VALUE)
    reserved_octet: int = Field(ge=0, le=MAX_BYTE_VALUE)
    tpkt_length: int = Field(ge=TPKT_MIN_OCTETS, le=TPKT_MAX_OCTETS)
    cotp_code: int = Field(ge=0, le=MAX_BYTE_VALUE)
    message_type: str = Field(min_length=1)
    eot: bool | None = None
    tpdu_nr: int | None = Field(default=None, ge=0, le=_TPDU_NR_MASK)
    cotp_class: int | None = Field(default=None, ge=0, le=_PREFERRED_CLASS_MASK)
    calling_tsap: bytes | None = Field(default=None, max_length=_MAX_PARAMETER_OCTETS)
    called_tsap: bytes | None = Field(default=None, max_length=_MAX_PARAMETER_OCTETS)
    user_data_length: int = Field(ge=0, le=TPDU_MAX_OCTETS)


class IsoTsapDissector:
    """Decodes ISO-on-TCP envelopes, and refuses every malformed one on port 102."""

    name: Final = ISO_TSAP_PROTOCOL

    def claims(self, frame: RawFrame) -> bool:
        """Whether the frame is ISO-on-TCP traffic by its ports.

        Args:
            frame: The peeled frame.

        Returns:
            True for TCP with port 102 at either end. Port alone, with no look at the payload: 102
            is a claim about the service IANA registers there, and a structural pre-check would
            hide exactly the traffic worth seeing — malformed envelopes aimed at a PLC would become
            "nobody looked at this" instead of a recorded refusal. See the module docstring.
        """
        return frame.transport is Transport.TCP and ISO_TSAP_PORT in (
            frame.src.port,
            frame.dst.port,
        )

    def dissect(self, frame: RawFrame) -> IsoTsapMessage | MalformedFrame:
        """Decode one claimed frame, or record why it could not be decoded.

        Args:
            frame: The peeled frame. Its payload is entirely untrusted.

        Returns:
            An `IsoTsapMessage`, or a `MalformedFrame` naming the specific reason. Never raises,
            for any input whatsoever.

        The order of the checks is the contract. The declared length is compared with the bytes
        present *before* it is used as a slice bound, and with the 7-octet minimum *before* that, so
        no frame can make this function allocate or index by a number it chose. There is no `try`
        here: safety is the ordering, not a net underneath it.
        """
        payload = frame.payload
        if len(payload) < TPKT_HEADER_LENGTH:
            return self._refuse(
                frame,
                MalformedReason.SHORT_HEADER,
                f"payload of {len(payload)} bytes is shorter than the "
                f"{TPKT_HEADER_LENGTH}-octet TPKT header",
            )

        tpkt_version, reserved_octet, tpkt_length = struct.unpack_from(">BBH", payload, 0)
        if tpkt_version != TPKT_VERSION:
            return self._refuse(
                frame,
                MalformedReason.BAD_HEADER_FIELD,
                f"TPKT version is {tpkt_version}, and RFC 1006 permits only {TPKT_VERSION}",
            )
        if tpkt_length < TPKT_MIN_OCTETS:
            return self._refuse(
                frame,
                MalformedReason.FIELD_OUT_OF_RANGE,
                f"packet length is {tpkt_length}, below the {TPKT_MIN_OCTETS}-octet minimum for a "
                f"TPKT that carries a TPDU; checked before any slice is taken",
            )
        if tpkt_length > len(payload):
            return self._refuse(
                frame,
                MalformedReason.LENGTH_MISMATCH,
                f"packet length of {tpkt_length} needs that many octets but {len(payload)} arrived",
            )
        if tpkt_length < len(payload):
            return self._refuse(
                frame,
                MalformedReason.TRAILING_BYTES,
                f"{len(payload) - tpkt_length} bytes follow a TPKT declaring {tpkt_length}; this "
                f"module dissects one TPKT per frame",
            )

        connection_oriented_transport = payload[TPKT_HEADER_LENGTH:tpkt_length]
        if len(connection_oriented_transport) < _COTP_MIN_HEADER_OCTETS:
            return self._refuse(
                frame,
                MalformedReason.SHORT_HEADER,
                f"a TPKT may not be {tpkt_length} octets: its COTP part would carry "
                f"{len(connection_oriented_transport)} octets and a TPDU needs at least "
                f"{_COTP_MIN_HEADER_OCTETS}",
            )

        length_indicator = connection_oriented_transport[0]
        if length_indicator == LI_RESERVED_FOR_EXTENSIONS:
            return self._refuse(
                frame,
                MalformedReason.FIELD_OUT_OF_RANGE,
                f"length indicator is {LI_RESERVED_FOR_EXTENSIONS}, which RFC 905 reserves for "
                f"extensions and which therefore describes no header this module can measure",
            )

        if length_indicator == 0:
            return self._refuse(
                frame,
                MalformedReason.INCONSISTENT_COUNT,
                "length indicator 0 declares a header of one octet -- the length indicator "
                "alone -- so there is no TPDU code at all and octet 2 would be user data read as "
                "a header",
            )

        header_end = length_indicator + 1
        if header_end > len(connection_oriented_transport):
            return self._refuse(
                frame,
                MalformedReason.INCONSISTENT_COUNT,
                f"length indicator {length_indicator} claims a {header_end}-octet TPDU header but "
                f"{len(connection_oriented_transport)} octets arrived",
            )

        cotp_code = connection_oriented_transport[1]
        message_type = _message_type(cotp_code)
        cotp_class = _preferred_class(connection_oriented_transport, length_indicator)

        fixed_part = _fixed_part_refusal(cotp_code, length_indicator)
        if fixed_part is not None:
            return self._refuse(frame, fixed_part.reason, fixed_part.detail)

        data_transfer = _decode_data_transfer(connection_oriented_transport, cotp_code)

        if message_type == "connection_request" and header_end > CR_MAX_OCTETS:
            return self._refuse(
                frame,
                MalformedReason.FIELD_OUT_OF_RANGE,
                f"a CR header of {header_end} octets exceeds the {CR_MAX_OCTETS} RFC 905 §13.3 "
                f"permits; the bound is applied to the header, not to lawful initial user data",
            )

        parameters = _decode_parameters(connection_oriented_transport, length_indicator)
        if isinstance(parameters, _Refusal):
            return self._refuse(frame, parameters.reason, parameters.detail)

        user_data_length = _user_data_length(cotp_code, tpkt_length, header_end)
        if cotp_code == TpduCode.EXPEDITED_DATA and user_data_length > _ED_MAX_USER_DATA:
            return self._refuse(
                frame,
                MalformedReason.FIELD_OUT_OF_RANGE,
                f"an ED carries {user_data_length} octets of expedited data, beyond the "
                f"{_ED_MAX_USER_DATA}-octet XSDU limit RFC 1006 §6 states; the limit applies to "
                f"expedited data only and not to a DT",
            )

        return IsoTsapMessage(
            source=frame.source,
            timestamp=frame.timestamp,
            src=frame.src,
            dst=frame.dst,
            direction=_direction(frame),
            tpkt_version=int(tpkt_version),
            reserved_octet=int(reserved_octet),
            tpkt_length=int(tpkt_length),
            cotp_code=int(cotp_code),
            message_type=message_type,
            eot=data_transfer.eot,
            tpdu_nr=data_transfer.tpdu_nr,
            cotp_class=cotp_class,
            calling_tsap=parameters.calling_tsap,
            called_tsap=parameters.called_tsap,
            user_data_length=user_data_length,
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
    """Which way the frame travelled, decided by which end holds the registered port.

    A transport fact, kept as one, exactly as the Modbus dissector keeps it. 102 is the registered
    ``iso-tsap`` server port, so a frame addressed to it is a request and one sent from it is a
    response. When both ends hold the port the answer is `UNKNOWN` rather than a guess. Nothing here
    is a statement about which peer is an engineering station and which is a controller: that is a
    peer role, and this lane does not produce one.
    """
    to_server = frame.dst.port == ISO_TSAP_PORT
    from_server = frame.src.port == ISO_TSAP_PORT
    if to_server and not from_server:
        return Direction.REQUEST
    if from_server and not to_server:
        return Direction.RESPONSE
    return Direction.UNKNOWN


def _message_type(cotp_code: int) -> str:
    """Readable name for a TPDU code octet, including unrecognised ones.

    CR and CC are matched on their high nibble because bits 4-1 carry the credit field (RFC 905
    §13.1 Table 8). DR, DT, ER and ED are matched on the whole octet, which makes the DT matcher the
    exact ``1111 0000`` RFC 905 prints — class-0-specific, as spec-audit D3 says: X.224 prints
    ``1111 000y`` with bit 1 carrying ROA for classes 1, 3 and 4, so a DT with ROA set
    arrives here as ``unknown(<n>)`` rather than being read through a class-0 layout the bytes never
    promised. An unknown code is still a decoded message: the envelope was sound, and the frame is
    real traffic worth counting even though its TPDU kind means nothing to this module.
    """
    if cotp_code & _TPDU_NIBBLE_MASK == TpduCode.CONNECTION_REQUEST:
        return "connection_request"
    if cotp_code & _TPDU_NIBBLE_MASK == TpduCode.CONNECTION_CONFIRM:
        return "connection_confirm"
    return _TPDU_NAMES.get(cotp_code, f"unknown({cotp_code})")


def _preferred_class(cotp: bytes, length_indicator: int) -> int | None:
    """The preferred class recorded on a CR or CC, or ``None`` where the wire did not carry one.

    Octet 7 bits 8-5 (RFC 905 §13.3.3 e). Read only for CR and CC; a bare DT does not carry its
    class at all, so this is ``None`` for every TPDU except those two, and nothing is inferred from
    the value.

    The length-indicator guard below is defence in depth rather than a live path:
    `_fixed_part_refusal` refuses any CR or CC whose header does not reach octet 7, so by the time
    this runs the octet is present. It stays because this function must not index past its buffer
    even if a later edit reorders the checks — the same reason `_COTP_MIN_HEADER_OCTETS` survives
    upstream.
    """
    code = cotp[1]
    if code & _TPDU_NIBBLE_MASK not in (TpduCode.CONNECTION_REQUEST, TpduCode.CONNECTION_CONFIRM):
        return None
    if length_indicator < _CONNECT_FIXED_PART_OCTETS:
        return None
    return (cotp[_PREFERRED_CLASS_OCTET] >> _PREFERRED_CLASS_SHIFT) & _PREFERRED_CLASS_MASK


def _fixed_part_minimum(cotp_code: int) -> int | None:
    """The least length indicator a TPDU with this code needs, or ``None`` if it has no floor.

    Args:
        cotp_code: The raw TPDU code octet.

    Returns:
        The minimum header length, or ``None`` for a code this module does not measure.

    CR and CC are matched on their high nibble because their low nibble is the credit field, so
    ``0xE0`` and ``0xE7`` are the same TPDU kind and must get the same floor (RFC 905 §13.2.2.2).
    Every other measured code has a fixed low nibble and is matched exactly, which keeps a code that
    merely shares a nibble with DR, ER or ED out of their floors.
    """
    if cotp_code & _TPDU_NIBBLE_MASK in (
        TpduCode.CONNECTION_REQUEST,
        TpduCode.CONNECTION_CONFIRM,
    ):
        return _CONNECT_FIXED_PART_OCTETS
    return _FIXED_PART_MINIMUMS.get(cotp_code)


def _fixed_part_refusal(cotp_code: int, length_indicator: int) -> _Refusal | None:
    """Refuse a TPDU whose length indicator cannot cover the fixed part its code implies.

    Args:
        cotp_code: The raw TPDU code octet.
        length_indicator: The TPDU's first octet, already checked against the octets present.

    Returns:
        A `_Refusal` with `INCONSISTENT_COUNT` when the fixed part does not fit inside the declared
        header, or ``None`` when it does or when the code is one this module does not measure.

    **Why a TPDU needs this at all.** §13.2.2.1 makes the code the thing that defines the fixed
    part: "If any of the parameters of the fixed part have an invalid value, or if the fixed part
    cannot be contained within the header (as defined by LI) this is a protocol error." A TPDU
    whose LI stops short of its own reference fields does not carry those fields, so decoding it as
    a named message would report the fields' absence as user data — mislabelling header octets that
    were never sent.

    **CR and CC are included, and that is not a conflict with their user-data latitude.** RFC 1006
    §5 permits initial data during connection establishment, and its *Connection Establishment*
    clause says the CR and CC "may exchange initial user data, using the user data fields of these
    TPDUs". A user data field lies *past* the header the length indicator measures, so it can make a
    CR longer but never shorter: a CR with LI 6 and 100 octets after it is lawful and still decodes,
    while a CR with LI 2 has thrown away its DST-REF and SRC-REF and is exactly the protocol error
    §13.2.2.1 names. The floor bounds the header, and the refusal of user data — which this module
    never does — is a different question that this check does not touch.

    **DT and ED are not minimums but exact values**, and they share one rule because their formats
    share one property: neither has a variable part. A class-0 DT is ``| LI | DT | TPDU-NR and EOT |
    user data |`` (RFC 905 §13.7.1 a) and RFC 1006's ED is ``| header length | code | credit |
    TPDU-NR and EOT | user data |`` (§6, "nearly identical to the format for the normal data, DT,
    TPDU"), so each fixes its length indicator — 2 and 3 respectively — and an LI above it would
    declare a variable part the format does not have. Both directions are refused here, in one
    place, so no caller can be handed a user-data count that the sender steered. With a floor rather
    than an exact value, the same six application octets in an ED reported 6, 5, 4 and 1 as the LI
    varied; that is the DT defect under another name, and this is where it is closed.
    """
    if cotp_code == TpduCode.DATA:
        if length_indicator != _DT_LENGTH_INDICATOR:
            return _Refusal(
                MalformedReason.INCONSISTENT_COUNT,
                f"a DT declares a length indicator of {length_indicator}, and RFC 905 §13.7.1 a "
                f"gives the class-0 DT no variable part, so its length indicator is exactly "
                f"{_DT_LENGTH_INDICATOR} and no other value describes a TPDU this format has",
            )
        return None

    if cotp_code == TpduCode.EXPEDITED_DATA:
        if length_indicator != _ED_LENGTH_INDICATOR:
            return _Refusal(
                MalformedReason.INCONSISTENT_COUNT,
                f"an ED declares a length indicator of {length_indicator}, and RFC 1006 §6 gives "
                f"the expedited TPDU the DT format with no variable part, so its length indicator "
                f"is exactly {_ED_LENGTH_INDICATOR} and no other value describes a TPDU this "
                f"format has",
            )
        return None

    minimum = _fixed_part_minimum(cotp_code)
    if minimum is not None and length_indicator < minimum:
        return _Refusal(
            MalformedReason.INCONSISTENT_COUNT,
            f"a {_message_type(cotp_code)} declares a length indicator of {length_indicator}, and "
            f"its fixed part needs at least {minimum} octets of header before any user data",
        )
    if minimum is not None and length_indicator - minimum == _DANGLING_VARIABLE_PART_OCTETS:
        return _Refusal(
            MalformedReason.INCONSISTENT_COUNT,
            f"a {_message_type(cotp_code)} declares a length indicator of {length_indicator}, "
            f"leaving a one-octet variable part after its {minimum}-octet fixed part; RFC 905 "
            f"§13.2.3 says a variable part, if present, shall contain one or more parameters, and "
            f"a parameter needs a code octet and a length octet",
        )
    return None


_FIXED_PART_MINIMUMS: Final[dict[int, int]] = {
    TpduCode.DISCONNECT_REQUEST: _DR_FIXED_PART_OCTETS,
    TpduCode.ERROR: _ER_FIXED_PART_OCTETS,
}
"""The least length indicator each measured TPDU needs, keyed by its exact code octet.

Only the codes whose low nibble is fixed **and whose header may legitimately be longer than its
fixed part** live here. Three kinds are deliberately absent and each has its own rule in
`_fixed_part_refusal`: DT and ED fix their length indicator to an exact value because their formats
have no variable part, and CR and CC carry their low nibble as credit so they are resolved by nibble
rather than by exact code.
"""


def _decode_data_transfer(cotp: bytes, cotp_code: int) -> _DataTransferFields:
    """Decode a DT's octet 3 into EOT and TPDU-NR, or leave both unset for every other TPDU.

    Args:
        cotp: The COTP part of the TPKT, at least three octets, whose length indicator
            `_fixed_part_refusal` has already proved is exactly 2 for a DT.
        cotp_code: The raw TPDU code octet.

    Returns:
        The EOT flag and TPDU-NR, both ``None`` where the TPDU is not a DT. There is no refusal path
        left here: the length-indicator rule a DT needs is enforced before this function is called,
        so that one rule lives in one place.

    **A class-4 DT never reaches this function.** It is refused upstream by the length-indicator
    rule: the class-0 DT fixes LI at 2 (RFC 905 §13.7.1 a) while a class-4 DT's fixed part runs to
    LI 4 or 7 (§13.7.1 b, c), so `_fixed_part_refusal` refuses every such header as
    `INCONSISTENT_COUNT`. That is correct on this port — RFC 1006 §6 exchanges only class-0 TPDUs —
    and it means the class-0 reading below is applied to frames that really are class 0, not to a
    guess about one whose class is unknown. An operator on a class-4 estate sees a CR recording
    ``cotp_class=4`` followed by refused data TPDUs; the setup is visible and the data is honestly
    refused rather than misread.

    An ED TPDU is decoded as ``expedited_data`` and gets no EOT or TPDU-NR here, deliberately. RFC
    1006 §6 gives it a *different* fixed part from X.224's class-1 ED and says its credit octet is
    "always ZERO on output and ignored on input", so reading its octets through the class-0 DT
    layout would be guessing which of two shapes the sender used. The spec-audit's D4 says an
    honest refusal to decode it is acceptable; the declaration's done list does not ask for it. The
    TPDU is named and its user data counted, and neither is inferred.

    **What does govern an ED is fixed, and is enforced in `dissect`:** its length indicator is
    exactly 3 and its user data is capped at the 16-octet XSDU — the LI through
    `_fixed_part_refusal`, the cap by an explicit `FIELD_OUT_OF_RANGE` refusal. So the count this
    module reports for an ED cannot be steered by the length indicator and cannot exceed 16, which
    is the property the DT rules were tightened to give.

    The length indicator is not re-checked here: `_fixed_part_refusal` has already refused any DT
    whose LI is not exactly 2, so this function can read octet 3 without a guard of its own.
    """
    if cotp_code != TpduCode.DATA:
        return _DataTransferFields()
    return _DataTransferFields(
        eot=bool(cotp[2] & _EOT_MASK),
        tpdu_nr=cotp[2] & _TPDU_NR_MASK,
    )


def _user_data_length(cotp_code: int, tpkt_length: int, header_end: int) -> int:
    """How many application octets follow the COTP header, counted and never decoded.

    Args:
        cotp_code: The raw TPDU code octet.
        tpkt_length: The declared and verified packet length, which bounds the TPDU.
        header_end: Where the COTP header ends, ``length_indicator + 1``.

    Returns:
        The number of octets after the header.

    **A DT's and an ED's count come from the TPKT length, not from the length indicator.** Both
    formats have a fixed header and no variable part, so the application data is whatever the packet
    carries beyond that header. Deriving it from the TPKT is the form that cannot be steered: the
    length indicator is one attacker-chosen octet, whereas the TPKT length has already been proved
    equal to the octets present, so the count is tied to bytes that actually arrived.

    The two headers are not the same width, and getting this wrong is a silent off-by-one:

    - a DT's is three octets — LI, code, TPDU-NR/EOT (RFC 905 §13.7.1 a) — so the count is
      ``tpkt_length - 4 - 3``;
    - an ED's is **four** — LI, code, credit, TPDU-NR/EOT (RFC 1006 §6) — because the expedited
      format inserts a credit octet that the DT does not have, so the count is
      ``tpkt_length - 4 - 4``.

    With `_fixed_part_refusal` fixing each length indicator the two derivations agree, which is the
    point — neither count *depends* on that being enforced somewhere else. For every other TPDU the
    declared header really can carry a variable part, so the length indicator is the right source
    and is used as it was.
    """
    if cotp_code == TpduCode.DATA:
        return tpkt_length - TPKT_HEADER_LENGTH - _DT_HEADER_OCTETS
    if cotp_code == TpduCode.EXPEDITED_DATA:
        return tpkt_length - TPKT_HEADER_LENGTH - _ED_HEADER_OCTETS
    return tpkt_length - TPKT_HEADER_LENGTH - header_end


def _decode_parameters(cotp: bytes, length_indicator: int) -> _TsapParameters | _Refusal:
    """Read the TSAP-ID parameters a CR or CC carried inside its own header.

    Args:
        cotp: The COTP part of the TPKT.
        length_indicator: Its first octet; the parameter field ends at ``length_indicator + 1``.

    Returns:
        The calling and called TSAP octets, each ``None`` where no such parameter was carried, or a
        `_Refusal` if a parameter overruns the header it lives in.

    The variable part is ``[code][length][value...]`` triples (RFC 905 §13.3.4), parsed **only**
    inside the region the length indicator declares and bounds-checked at every step: a code octet
    and a length octet must both be inside the header before either is read, and the value must end
    inside it before it is sliced. The value is carried verbatim — RFC 905 gives TSAP-ID no
    structure, so no station, no role and no rack/slot is read out of it.

    Parameters this module does not name (maximum TPDU size 0xC0, additional option selection, and
    anything a later standard adds) are skipped without complaint: RFC 1006 §5 permits a CR to
    negotiate them, and a third parameter is never a refusal. A repeated code keeps the first value
    it carried rather than overwriting it — the wire said two things, and this module does not
    silently prefer the later one.
    """
    if (cotp[1] & _TPDU_NIBBLE_MASK) not in (
        TpduCode.CONNECTION_REQUEST,
        TpduCode.CONNECTION_CONFIRM,
    ):
        return _TsapParameters()
    if length_indicator < _CONNECT_FIXED_PART_OCTETS:
        return _TsapParameters()

    header_end = length_indicator + 1
    cursor = _CONNECT_FIXED_PART_OCTETS + 1
    calling_tsap: bytes | None = None
    called_tsap: bytes | None = None

    while cursor < header_end:
        if cursor + _PARAMETER_HEADER_OCTETS > header_end:
            return _Refusal(
                MalformedReason.INCONSISTENT_COUNT,
                f"a parameter at octet {cursor + 1} has {header_end - cursor} octets left in the "
                f"header, and its code and length need {_PARAMETER_HEADER_OCTETS}",
            )
        parameter_code = cotp[cursor]
        parameter_length = cotp[cursor + 1]
        value_start = cursor + _PARAMETER_HEADER_OCTETS
        value_end = value_start + parameter_length
        if value_end > header_end:
            return _Refusal(
                MalformedReason.INCONSISTENT_COUNT,
                f"parameter {parameter_code:#04x} declares {parameter_length} octets and only "
                f"{header_end - value_start} remain inside the length indicator",
            )
        value = cotp[value_start:value_end]
        if parameter_code == CALLING_TSAP_PARAMETER and calling_tsap is None:
            calling_tsap = value
        elif parameter_code == CALLED_TSAP_PARAMETER and called_tsap is None:
            called_tsap = value
        cursor = value_end

    return _TsapParameters(calling_tsap=calling_tsap, called_tsap=called_tsap)

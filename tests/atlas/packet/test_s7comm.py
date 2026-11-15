"""Tests for the ISO-on-TCP dissector (ADR 0347).

Correctness first — every expected field below is computed by hand from RFC 1006 and RFC 905, not
from what the code happens to produce. Then the declaration's fifteen done-list items and its six
refusals, each with its own assertion, because "it returned a MalformedFrame" is not evidence the
parser understood what was wrong with it.

The envelope fixtures are built with `struct.pack` from octets written out here, never with a
writer library and never from a dissector: the malformed cases — a lying length, a length indicator
that overruns its own TPDU, a truncated sweep at every byte — are exactly the ones a library refuses
to produce.

The random and mutated assault lives in `test_s7comm_hardening.py`.
"""

import struct

import pytest
from tests.atlas.packet.conftest import CLIENT_PORT, make_frame

from phos.atlas.packet import (
    Direction,
    DissectorRegistry,
    MalformedFrame,
    MalformedReason,
    RawFrame,
    Transport,
    UnparsedMessage,
)
from phos.atlas.packet.s7comm import (
    CR_MAX_OCTETS,
    ISO_TSAP_PORT,
    TPKT_MAX_OCTETS,
    IsoTsapDissector,
    IsoTsapMessage,
)

S7_JOB_BYTES = bytes.fromhex("3201000001000e000000")
"""A plausible S7 application body, used **only as opaque user data**.

This is the shape an S7 job request has, and it is here so the tests can prove that the dissector
counts those octets and reads nothing out of them. No field of it is named, asserted or decoded, and
no `ProgramAct` can come from it — the message type has no such field (ADR 0347).
"""


def tpkt(
    cotp: bytes,
    *,
    version: int = 3,
    reserved: int = 0,
    length: int | None = None,
    trailing: bytes = b"",
) -> bytes:
    """Build a TPKT: version, reserved, a 16-bit packet length, then the COTP part.

    ``length`` defaults to the honest value; pass one explicitly to build a header that lies about
    how much follows. ``trailing`` appends octets the declared length does not account for.
    """
    declared = 4 + len(cotp) if length is None else length
    return struct.pack(">BBH", version, reserved, declared) + cotp + trailing


def cotp_header(length_indicator: int, code: int, fixed: bytes = b"") -> bytes:
    """Build a COTP header with the given length indicator, a TPDU code, and a fixed part."""
    return bytes([length_indicator, code]) + fixed


def dt(*, eot: bool = True, tpdu_nr: int = 0, user_data: bytes = b"") -> bytes:
    """Build a class-0 DT TPDU: LI 2, code 0xF0, then octet 3 holding EOT and TPDU-NR.

    Bit 8 is the high bit and bit 1 the low (RFC 905 §13.2), so EOT is 0x80 and TPDU-NR occupies
    the low seven bits. Class 0 requires TPDU-NR to be zero, and the builder defaults to that.
    """
    octet3 = (0x80 if eot else 0x00) | (tpdu_nr & 0x7F)
    return cotp_header(2, 0xF0, bytes([octet3])) + user_data


def connect(
    *,
    code: int = 0xE0,
    preferred_class: int = 0,
    options: int = 0,
    parameters: bytes = b"",
    user_data: bytes = b"",
    credit: int = 0,
    length_indicator: int | None = None,
) -> bytes:
    """Build a CR (0xE0) or CC (0xD0) TPDU with its six-octet fixed part and a variable part.

    The fixed part is octets 2 to 7: the code, DST-REF (2), SRC-REF (2) and octet 7, whose bits 8-5
    are the preferred class and whose bits 4-1 are options (RFC 905 §13.3.3). The length indicator
    therefore counts six octets plus whatever variable part follows.
    """
    fixed = struct.pack(">HHB", 0x0001, 0x0002, (preferred_class << 4) | (options & 0x0F))
    variable = parameters
    declared = 6 + len(variable) if length_indicator is None else length_indicator
    return bytes([declared, code | credit]) + fixed + variable + user_data


def tsap_parameter(code: int, value: bytes) -> bytes:
    """Build a TSAP-ID parameter: code, length, value (RFC 905 §13.3.4 a)."""
    return bytes([code, len(value)]) + value


def dissect(frame: RawFrame) -> IsoTsapMessage | MalformedFrame:
    """Run one frame through the dissector."""
    return IsoTsapDissector().dissect(frame)


def decoded(frame: RawFrame) -> IsoTsapMessage:
    """Dissect a frame that must decode, failing loudly if it did not."""
    result = dissect(frame)
    assert isinstance(result, IsoTsapMessage), result
    return result


def refused(frame: RawFrame) -> MalformedFrame:
    """Dissect a frame that must be refused, failing loudly if it decoded."""
    result = dissect(frame)
    assert isinstance(result, MalformedFrame), result
    return result


def in_frame(
    payload: bytes, *, src_port: int = CLIENT_PORT, dst_port: int = ISO_TSAP_PORT
) -> RawFrame:
    """A TCP frame carrying ``payload`` on the registered port, towards the server by default."""
    return make_frame(payload, src_port=src_port, dst_port=dst_port)


class TestClaims:
    """The claim rule ADR 0347 resolves: port 102 is a claim for ``iso-tsap``, and only that."""

    def test_claims_traffic_towards_the_registered_port(self) -> None:
        assert IsoTsapDissector().claims(in_frame(b"\x00" * 7))

    def test_claims_traffic_from_the_registered_port(self) -> None:
        assert IsoTsapDissector().claims(
            in_frame(b"\x00" * 7, src_port=ISO_TSAP_PORT, dst_port=CLIENT_PORT)
        )

    def test_claims_when_both_ends_hold_the_registered_port(self) -> None:
        assert IsoTsapDissector().claims(
            in_frame(b"\x00" * 7, src_port=ISO_TSAP_PORT, dst_port=ISO_TSAP_PORT)
        )

    def test_ignores_traffic_that_touches_neither_end(self) -> None:
        assert not IsoTsapDissector().claims(in_frame(b"\x00" * 7, src_port=44000, dst_port=80))

    def test_ignores_udp_because_iso_on_tcp_is_tcp(self) -> None:
        # IANA registers 102 for udp too, but a UDP datagram is one packet, not a TPKT stream.
        frame = make_frame(b"\x00" * 7, dst_port=ISO_TSAP_PORT, transport=Transport.UDP)
        assert not IsoTsapDissector().claims(frame)

    def test_claims_by_port_alone_so_rubbish_on_102_is_a_finding(self) -> None:
        # Deliberately no structural pre-check: bytes that are not an envelope arriving on 102 must
        # reach `dissect` and be recorded as malformed, not quietly become unparsed traffic.
        assert IsoTsapDissector().claims(in_frame(b"GET / HTTP/1.1\r\n"))

    def test_names_itself_iso_tsap(self) -> None:
        assert IsoTsapDissector().name == "iso-tsap"

    def test_a_non_102_port_is_never_claimed_even_with_a_perfect_envelope(self) -> None:
        # The module must not steal traffic: a flawless TPKT anywhere else is somebody else's.
        perfect = tpkt(dt())
        assert not IsoTsapDissector().claims(in_frame(perfect, src_port=5555, dst_port=502))

    def test_dispatch_leaves_a_non_102_frame_unparsed(self) -> None:
        registry = DissectorRegistry([IsoTsapDissector()])
        result = registry.dispatch(in_frame(tpkt(dt()), src_port=5555, dst_port=502))
        assert isinstance(result, UnparsedMessage)
        assert result.protocol == "unknown"


class TestDataTransfer:
    """DT is the TPDU an S7 job or response travels in, and the only one with a bit-level layout."""

    def test_a_valid_dt_request_decodes(self) -> None:
        message = decoded(in_frame(tpkt(dt(eot=True, tpdu_nr=0, user_data=S7_JOB_BYTES))))

        assert message.protocol == "iso-tsap"
        assert message.tpkt_version == 3
        assert message.reserved_octet == 0
        assert message.cotp_code == 0xF0
        assert message.message_type == "data"
        assert message.direction is Direction.REQUEST
        assert message.eot is True
        assert message.tpdu_nr == 0
        assert message.user_data_length == len(S7_JOB_BYTES)

    def test_eot_is_bit_8_of_octet_3(self) -> None:
        # Bit 8 is the high bit (RFC 905 §13.2), so a set EOT is 0x80 and nothing else is.
        assert decoded(in_frame(tpkt(dt(eot=True)))).eot is True

    def test_eot_clear_is_reported_as_false_not_none(self) -> None:
        # False means "the wire said this is not the end"; None means "the wire did not say".
        assert decoded(in_frame(tpkt(dt(eot=False)))).eot is False

    @pytest.mark.parametrize("tpdu_nr", [0, 1, 2, 63, 64, 125, 126, 127])
    def test_tpdu_nr_is_bits_7_to_1_of_octet_3(self, tpdu_nr: int) -> None:
        # RFC 905 §13.2 numbers bit 1 at the low end, so bits 7-1 are the low seven bits.
        message = decoded(in_frame(tpkt(dt(tpdu_nr=tpdu_nr))))
        assert message.tpdu_nr == tpdu_nr

    def test_eot_and_tpdu_nr_occupy_different_bits(self) -> None:
        # TPDU-NR 1 with EOT set is octet 3 == 0x81. Reading either from the wrong bit fails here.
        message = decoded(in_frame(tpkt(cotp_header(2, 0xF0, b"\x81"))))
        assert message.eot is True
        assert message.tpdu_nr == 1

    def test_a_dt_response_travelling_from_the_port_decodes(self) -> None:
        message = decoded(
            in_frame(tpkt(dt(user_data=S7_JOB_BYTES)), src_port=ISO_TSAP_PORT, dst_port=CLIENT_PORT)
        )
        assert message.direction is Direction.RESPONSE

    def test_a_dt_between_two_registered_ports_has_no_direction(self) -> None:
        message = decoded(in_frame(tpkt(dt()), src_port=ISO_TSAP_PORT, dst_port=ISO_TSAP_PORT))
        assert message.direction is Direction.UNKNOWN

    def test_user_data_is_counted_and_never_decoded(self) -> None:
        # The count is the whole of what this module says about the application octets.
        message = decoded(in_frame(tpkt(dt(user_data=S7_JOB_BYTES))))
        assert message.user_data_length == len(S7_JOB_BYTES) == 10
        assert not hasattr(message, "job")
        assert "3201" not in message.model_dump_json()

    def test_a_dt_with_no_user_data_is_legal_and_not_short(self) -> None:
        # 7 octets is exactly 4 of TPKT header and 3 of class-0 DT header (audit, TPKT minimum).
        message = decoded(in_frame(tpkt(dt())))
        assert message.user_data_length == 0
        assert len(tpkt(dt())) == 7

    def test_a_dt_never_records_a_class(self) -> None:
        # A bare DT does not carry its class, and this module does not infer it.
        assert decoded(in_frame(tpkt(dt()))).cotp_class is None

    def test_every_dt_gets_the_class_0_layout_unconditionally(self) -> None:
        # Octet 3 of 0xFF: EOT is bit 8 and TPDU-NR is the low seven bits, so this decodes as
        # eot=True and tpdu_nr=127. The point is that it happens with no condition on a class -- a
        # DT cannot carry one -- so this is the pin on the lane's accepted limitation rather than a
        # restatement of bit positions. 0xFF is deliberately the degenerate case the declaration
        # names, and it does prove that EOT is not folded into TPDU-NR: a layout that ORed the EOT
        # bit back in would report 255.
        message = decoded(in_frame(tpkt(cotp_header(2, 0xF0, b"\xff"))))
        assert message.message_type == "data"
        assert message.eot is True
        assert message.tpdu_nr == 0xFF & 0x7F == 127
        assert message.cotp_class is None

    def test_an_asymmetric_octet_3_separates_the_two_candidate_readings(self) -> None:
        # 0xFF cannot distinguish the low-seven-bits reading from a bits-8-2 reading, because 0xFF
        # shifted either way is still 127. 0x80 does: bit 8 set and every bit below clear must give
        # tpdu_nr 0, and 0x81 must give 1. This is the assertion that would actually catch a shift.
        high_only = decoded(in_frame(tpkt(cotp_header(2, 0xF0, b"\x80"))))
        assert high_only.eot is True
        assert high_only.tpdu_nr == 0

        with_low_bit = decoded(in_frame(tpkt(cotp_header(2, 0xF0, b"\x81"))))
        assert with_low_bit.eot is True
        assert with_low_bit.tpdu_nr == 1

    def test_a_dt_on_a_connection_that_negotiated_class_4_is_still_read_as_class_0(self) -> None:
        # The limitation, stated as a test: a DT has no class field, so the CR's class-4 request
        # cannot reach the DT's decode. The DT gets the class-0 layout and records no class of its
        # own; only the CR reports class 4. Nothing here is correlated because nothing here is
        # stateful, and this is what that costs.
        class_4_cr = decoded(in_frame(tpkt(connect(preferred_class=4))))
        assert class_4_cr.cotp_class == 4

        following_dt = decoded(in_frame(tpkt(cotp_header(2, 0xF0, b"\xff"))))
        assert following_dt.cotp_class is None
        assert following_dt.eot is True
        assert following_dt.tpdu_nr == 127

    def test_a_dt_whose_length_indicator_is_below_2_is_inconsistent(self) -> None:
        # The done list, item 7: the class-0 fixed part needs octets 2 and 3. LI 1 leaves octet 3
        # outside the declared header, and LI 0 leaves no code octet at all.
        for length_indicator in (0, 1):
            payload = bytes([length_indicator, 0xF0]) + bytes(10)
            result = refused(in_frame(tpkt(payload)))
            assert result.reason is MalformedReason.INCONSISTENT_COUNT, f"LI {length_indicator}"

    def test_a_dt_with_roa_set_is_unknown_rather_than_read_as_class_0(self) -> None:
        # X.224 prints 1111 000y with bit 1 carrying ROA in classes 1, 3 and 4 (audit D3). The bytes
        # did not say which layout they use, so the code is named rather than guessed at.
        message = decoded(in_frame(tpkt(cotp_header(2, 0xF1, b"\x80"))))
        assert message.message_type == "unknown(241)"
        assert message.eot is None
        assert message.tpdu_nr is None

    def test_a_maximum_length_dt_decodes_without_decoding_its_body(self) -> None:
        user_data = bytes(TPKT_MAX_OCTETS - 4 - 3)
        message = decoded(in_frame(tpkt(dt(user_data=user_data))))
        assert message.tpkt_length == TPKT_MAX_OCTETS
        assert message.user_data_length == TPKT_MAX_OCTETS - 7


class TestEveryTpduCode:
    """Each code RFC 905 Table 8 names is decoded to its own name, and unknown codes are decoded."""

    def test_connection_request(self) -> None:
        message = decoded(in_frame(tpkt(connect(code=0xE0))))
        assert message.message_type == "connection_request"
        assert message.cotp_code == 0xE0

    def test_connection_request_is_matched_on_its_high_nibble(self) -> None:
        # Bits 4-1 are the credit field. A CR claiming credit 7 is still a CR (RFC 905 §13.3.3).
        message = decoded(in_frame(tpkt(connect(code=0xE0, credit=0x07))))
        assert message.message_type == "connection_request"
        assert message.cotp_code == 0xE7

    def test_connection_confirm(self) -> None:
        message = decoded(in_frame(tpkt(connect(code=0xD0))))
        assert message.message_type == "connection_confirm"
        assert message.cotp_code == 0xD0

    def test_connection_confirm_is_matched_on_its_high_nibble(self) -> None:
        message = decoded(in_frame(tpkt(connect(code=0xD0, credit=0x0F))))
        assert message.message_type == "connection_confirm"

    def test_disconnect_request(self) -> None:
        message = decoded(in_frame(tpkt(cotp_header(6, 0x80, struct.pack(">HHBB", 1, 2, 0, 0)))))
        assert message.message_type == "disconnect_request"
        assert message.cotp_code == 0x80

    def test_data(self) -> None:
        assert decoded(in_frame(tpkt(dt()))).message_type == "data"

    def test_error(self) -> None:
        # ER: code 0x70, DST-REF (2), then the reject cause.
        message = decoded(in_frame(tpkt(cotp_header(4, 0x70, struct.pack(">HB", 1, 0)))))
        assert message.message_type == "error"
        assert message.cotp_code == 0x70

    def test_expedited_data(self) -> None:
        # RFC 1006 §6 permits a non-standard ED TPDU on this port even though class 0 has none.
        message = decoded(in_frame(tpkt(cotp_header(3, 0x10, b"\x00\x80") + b"\xaa")))
        assert message.message_type == "expedited_data"
        assert message.user_data_length == 1

    def test_expedited_data_does_not_get_the_class_0_dt_layout(self) -> None:
        # RFC 1006's ED has a different fixed part from a DT (audit D4). Nothing is read from it.
        message = decoded(in_frame(tpkt(cotp_header(3, 0x10, b"\x00\x80"))))
        assert message.message_type == "expedited_data"
        assert message.eot is None
        assert message.tpdu_nr is None


class TestExpeditedData:
    """RFC 1006 §6 gives ED the DT format with no variable part, and caps its XSDU at 16 octets.

    Two independent properties, both enforced: the length indicator is **exactly 3**, so the
    user-data count cannot be steered by it, and the expedited payload is capped at 16.
    """

    def test_an_ed_at_length_indicator_three_decodes(self) -> None:
        message = decoded(in_frame(tpkt(cotp_header(3, 0x10, b"\x00\x80") + bytes(6))))
        assert message.message_type == "expedited_data"
        assert message.user_data_length == 6

    @pytest.mark.parametrize("length_indicator", [4, 5, 8])
    def test_an_ed_whose_length_indicator_is_not_three_is_inconsistent(
        self, length_indicator: int
    ) -> None:
        result = refused(in_frame(tpkt(cotp_header(length_indicator, 0x10) + bytes(20))))
        assert result.reason is MalformedReason.INCONSISTENT_COUNT
        assert "length indicator" in result.detail

    def test_the_ed_user_data_count_cannot_be_steered_by_the_length_indicator(self) -> None:
        # The identical six application octets, with only the length indicator changed. LI 3 must
        # report all six; every other value must refuse rather than report a smaller number. Before
        # the exact-value rule, this frame reported 6, 5, 4 and 1 as the LI varied.
        #
        # The ED fixed part here is the credit and TPDU-NR/EOT pair, so LI 3 is the one value that
        # makes the header end exactly where the application data begins.
        application = bytes(6)
        ed_header = b"\x00\x80"
        steered: list[int] = []
        for length_indicator in (3, 4, 5, 8):
            cotp = cotp_header(length_indicator, 0x10) + ed_header + application
            result = dissect(in_frame(tpkt(cotp)))
            if isinstance(result, IsoTsapMessage):
                steered.append(result.user_data_length)
                assert result.user_data_length == len(application)
            else:
                assert result.reason is MalformedReason.INCONSISTENT_COUNT
        assert steered == [6], "only LI 3 may decode, reporting all six octets"

    def test_an_ed_carrying_exactly_the_xsdu_limit_decodes(self) -> None:
        message = decoded(in_frame(tpkt(cotp_header(3, 0x10, b"\x00\x80") + bytes(16))))
        assert message.user_data_length == 16

    def test_an_ed_one_octet_past_the_xsdu_limit_is_field_out_of_range(self) -> None:
        # RFC 1006 §6: "the TP specification limits the size of an expedited transport service data
        # unit (XSDU) to 16 octets." A count beyond a stated limit is FIELD_OUT_OF_RANGE.
        result = refused(in_frame(tpkt(cotp_header(3, 0x10, b"\x00\x80") + bytes(17))))
        assert result.reason is MalformedReason.FIELD_OUT_OF_RANGE
        assert "16" in result.detail and "XSDU" in result.detail

    def test_an_ed_far_past_the_xsdu_limit_is_refused_the_same_way(self) -> None:
        result = refused(in_frame(tpkt(cotp_header(3, 0x10, b"\x00\x80") + bytes(5000))))
        assert result.reason is MalformedReason.FIELD_OUT_OF_RANGE

    def test_an_ed_with_no_user_data_decodes(self) -> None:
        # RFC 1006 §6 sets no lower bound on the ED payload; RFC 905 §13.8.5's "(1 to 16 octets)"
        # describes the expedited TSDU, and a TPDU carrying none is not refused by either text.
        message = decoded(in_frame(tpkt(cotp_header(3, 0x10, b"\x00\x80"))))
        assert message.user_data_length == 0
        assert message.message_type == "expedited_data"

    def test_the_ed_count_comes_from_the_tpkt_length_not_the_ed_header_width(self) -> None:
        # An off-by-one here is silent: the ED header is four octets (LI, code, credit, TPDU-NR/EOT)
        # against the DT's three, so the count is tpkt_length - 8 and not tpkt_length - 7.
        for user_octets in (0, 1, 6, 16):
            cotp = cotp_header(3, 0x10, b"\x00\x80") + bytes(user_octets)
            payload = tpkt(cotp)
            assert len(payload) == 8 + user_octets
            message = decoded(in_frame(payload))
            assert message.user_data_length == user_octets

    def test_a_dt_is_not_held_to_the_xsdu_limit(self) -> None:
        # The 16-octet cap is the expedited service's unit and applies to ED only. A DT carries the
        # protocol's full user data, bounded by the TPKT length instead.
        message = decoded(in_frame(tpkt(dt(user_data=bytes(5000)))))
        assert message.user_data_length == 5000

    @pytest.mark.parametrize("code", [0x00, 0x30, 0x50, 0x60, 0xC0, 0xA0, 0xFF])
    def test_an_unknown_tpdu_code_is_decoded_not_refused(self, code: int) -> None:
        # The envelope was sound. An unrecognised TPDU kind is a decoded message, not a failure.
        message = decoded(in_frame(tpkt(cotp_header(2, code, b"\x00"))))
        assert message.message_type == f"unknown({code})"
        assert message.cotp_code == code

    def test_dc_is_unknown_because_table_8_marks_it_not_class_0(self) -> None:
        # 1100 0000 (DC) and 0101 zzzz (RJ) are named by RFC 905 but not valid in class 0. They are
        # decoded as unknown rather than refused: the TPDU code is not this lane's to police.
        assert decoded(in_frame(tpkt(cotp_header(2, 0xC0, b"\x00")))).message_type == "unknown(192)"
        assert decoded(in_frame(tpkt(cotp_header(2, 0x50, b"\x00")))).message_type == "unknown(80)"


class TestTheReservedOctet:
    """Done-list item 8, and refusal 1 in ADR 0347: any value is recorded and never refused."""

    @pytest.mark.parametrize("reserved", [0x00, 0x01, 0x7F, 0x80, 0xFE, 0xFF])
    def test_every_reserved_value_is_recorded_and_decoded(self, reserved: int) -> None:
        message = decoded(in_frame(tpkt(dt(), reserved=reserved)))
        assert message.reserved_octet == reserved
        assert message.message_type == "data"

    def test_zero_is_the_only_value_rfc_2126_assigns_and_it_is_still_just_recorded(self) -> None:
        assert decoded(in_frame(tpkt(dt(), reserved=0x00))).reserved_octet == 0x00

    def test_a_non_zero_reserved_octet_is_never_a_refusal_reason(self) -> None:
        # RFC 2126 §6.10: "this field should be ignored on input". A refusal would be a defect.
        for reserved in range(0x100):
            frame = in_frame(tpkt(dt(), reserved=reserved))
            assert isinstance(dissect(frame), IsoTsapMessage), f"reserved {reserved:#04x} refused"


class TestTheCotpClass:
    """Done-list item 9 and refusal 2: a class other than 0 is recorded and never refused."""

    @pytest.mark.parametrize("preferred_class", [0, 1, 2, 3, 4, 5, 15])
    def test_every_class_value_decodes(self, preferred_class: int) -> None:
        message = decoded(in_frame(tpkt(connect(preferred_class=preferred_class))))
        assert message.cotp_class == preferred_class
        assert message.message_type == "connection_request"

    def test_class_4_is_recorded_and_not_refused(self) -> None:
        # Siemens labels its open-communication transport "(Class 4)" (11/2025 -AN §8.2, Table 8-1).
        message = decoded(in_frame(tpkt(connect(preferred_class=4))))
        assert message.cotp_class == 4
        assert message.message_type == "connection_request"

    def test_the_class_is_recorded_on_a_connection_confirm_too(self) -> None:
        message = decoded(in_frame(tpkt(connect(code=0xD0, preferred_class=4))))
        assert message.cotp_class == 4

    def test_a_class_outside_the_four_bits_is_still_recorded_as_bits_8_to_5(self) -> None:
        # Only bits 8-5 are the class; the option bits below them are not part of it.
        message = decoded(in_frame(tpkt(connect(preferred_class=4, options=0x0F))))
        assert message.cotp_class == 4

    def test_the_option_bits_below_the_class_are_not_read_into_it(self) -> None:
        # Bits 4-1 are options and "have no meaning" in class 0 (RFC 905 §13.3.3 NOTES).
        message = decoded(in_frame(tpkt(connect(preferred_class=0, options=0x0A))))
        assert message.cotp_class == 0

    def test_an_unrecorded_class_is_none_not_zero(self) -> None:
        # A DT does not carry a class. Reporting 0 would be inventing a value the wire never had.
        assert decoded(in_frame(tpkt(dt()))).cotp_class is None


class TestConnectionSetup:
    """Done-list item 10 and refusal 4: a CR/CC with user data or extra parameters decodes."""

    def test_a_cr_with_both_tsaps_decodes(self) -> None:
        parameters = tsap_parameter(0xC1, b"\x01\x00") + tsap_parameter(0xC2, b"\x01\x02")
        message = decoded(in_frame(tpkt(connect(parameters=parameters))))

        assert message.calling_tsap == b"\x01\x00"
        assert message.called_tsap == b"\x01\x02"
        assert message.user_data_length == 0

    def test_a_cr_carrying_user_data_decodes(self) -> None:
        # RFC 1006 §5: initial data "may be exchanged during connection establishment".
        parameters = tsap_parameter(0xC1, b"\x01\x00") + tsap_parameter(0xC2, b"\x01\x02")
        message = decoded(in_frame(tpkt(connect(parameters=parameters, user_data=b"\xde\xad"))))
        assert message.user_data_length == 2
        assert message.calling_tsap == b"\x01\x00"

    def test_a_cr_carrying_a_third_parameter_decodes(self) -> None:
        # Maximum TPDU size (0xC0) is a lawful third parameter this module does not name.
        parameters = (
            tsap_parameter(0xC1, b"\x01\x00")
            + tsap_parameter(0xC2, b"\x01\x02")
            + tsap_parameter(0xC0, b"\x0b")
        )
        message = decoded(in_frame(tpkt(connect(parameters=parameters))))
        assert message.calling_tsap == b"\x01\x00"
        assert message.called_tsap == b"\x01\x02"

    def test_a_connection_confirm_carrying_user_data_decodes(self) -> None:
        message = decoded(in_frame(tpkt(connect(code=0xD0, user_data=b"\x01\x02\x03"))))
        assert message.message_type == "connection_confirm"
        assert message.user_data_length == 3

    def test_absent_tsaps_are_none_rather_than_guessed(self) -> None:
        message = decoded(in_frame(tpkt(connect())))
        assert message.calling_tsap is None
        assert message.called_tsap is None

    def test_only_the_calling_tsap_present(self) -> None:
        parameters = tsap_parameter(0xC1, b"\x01\x00")
        message = decoded(in_frame(tpkt(connect(parameters=parameters))))
        assert message.calling_tsap == b"\x01\x00"
        assert message.called_tsap is None

    def test_a_tsap_is_carried_verbatim_and_never_interpreted(self) -> None:
        # RFC 905 §13.3.4 gives TSAP-ID no structure. Octets that look like rack/slot stay octets.
        value = bytes.fromhex("0301")
        message = decoded(in_frame(tpkt(connect(parameters=tsap_parameter(0xC1, value)))))
        assert message.calling_tsap == value
        assert not hasattr(message, "station")
        assert not hasattr(message, "rack")
        assert not hasattr(message, "slot")

    def test_an_empty_tsap_parameter_is_carried_as_empty(self) -> None:
        # A zero-length value is what the wire said; None would mean "no parameter arrived".
        message = decoded(in_frame(tpkt(connect(parameters=tsap_parameter(0xC1, b"")))))
        assert message.calling_tsap == b""

    def test_a_parameter_overrunning_the_header_is_inconsistent(self) -> None:
        # Declared length 9, but only 2 octets remain inside the length indicator.
        parameters = bytes([0xC1, 0x09]) + b"\x01\x00"
        result = refused(in_frame(tpkt(connect(parameters=parameters))))
        assert result.reason is MalformedReason.INCONSISTENT_COUNT

    def test_a_parameter_with_only_a_code_octet_is_inconsistent(self) -> None:
        # Two octets are needed for a code and a length; one remains inside the header.
        overrunning = tpkt(bytes([7, 0xE0]) + struct.pack(">HHB", 1, 2, 0) + b"\xc1")
        result = refused(in_frame(overrunning))
        assert result.reason is MalformedReason.INCONSISTENT_COUNT

    def test_a_cr_tpdus_own_length_is_bounded_at_128(self) -> None:
        # RFC 905 §13.3: "The length of the CR TPDU shall not exceed 128 octets."
        over = bytes([128, 0xE0]) + bytes(127)
        assert len(over) == 129
        result = refused(in_frame(tpkt(over)))
        assert result.reason is MalformedReason.FIELD_OUT_OF_RANGE

    def test_a_cr_at_exactly_128_octets_still_decodes(self) -> None:
        # The boundary the bound sits on must remain usable. LI 127 means a 128-octet header: the
        # two LI/code octets plus six fixed plus a 121-octet variable part, filled here by one
        # well-formed 0xC1 parameter so the frame is a CR and not a pile of octets.
        at_limit = bytes([127, 0xE0]) + connect(parameters=tsap_parameter(0xC1, bytes(119)))[2:]
        assert len(at_limit) == CR_MAX_OCTETS
        message = decoded(in_frame(tpkt(at_limit)))
        assert message.message_type == "connection_request"
        assert message.calling_tsap == bytes(119)

    def test_a_cc_is_not_bounded_at_128_because_the_clause_names_the_cr(self) -> None:
        # The bound is quoted for the CR. Applying it to a CC would refuse traffic the text allows.
        large = bytes([200, 0xD0]) + struct.pack(">HHB", 1, 2, 0) + bytes(195)
        message = decoded(in_frame(tpkt(large)))
        assert message.message_type == "connection_confirm"

    def test_parameters_are_only_read_from_a_connection_tpdu(self) -> None:
        # A DT's variable part is user data, not parameters, and must not be read as TSAP-IDs.
        message = decoded(in_frame(tpkt(dt(user_data=tsap_parameter(0xC1, b"\x01\x00")))))
        assert message.calling_tsap is None
        assert message.user_data_length == 4


class TestTheVariablePartMustHoldAParameter:
    """A declared variable part must be able to contain at least one whole parameter.

    RFC 905 §13.2.3: "If the variable part is present, it shall contain one or more parameters."
    A parameter is a code octet and a length octet (RFC 905 §13.2.3 diagram), so a declared
    variable part of exactly one octet can hold nothing and is a protocol error. The CR/CC path had
    this check through `_decode_parameters`; DR and ER did not, and that asymmetry is what these
    tests close. The rule is applied to every TPDU whose fixed-part size the module knows, so a
    TPDU added later cannot miss it.
    """

    @pytest.mark.parametrize(
        ("code", "fixed_part"),
        [(0x80, 6), (0x70, 4), (0xE0, 6), (0xD0, 6)],
        ids=["dr", "er", "cr", "cc"],
    )
    def test_a_one_octet_variable_part_is_refused(self, code: int, fixed_part: int) -> None:
        # LI one past the fixed part leaves a single octet of variable part, which cannot be a
        # parameter however it is read.
        body = bytes([fixed_part + 1, code]) + bytes(fixed_part - 1) + bytes([0xC1])
        result = refused(in_frame(tpkt(body)))
        assert result.reason is MalformedReason.INCONSISTENT_COUNT
        assert "13.2.3" in result.detail
        assert "variable part" in result.detail

    @pytest.mark.parametrize(
        ("code", "fixed_part"),
        [(0x80, 6), (0x70, 4), (0xE0, 6), (0xD0, 6)],
        ids=["dr", "er", "cr", "cc"],
    )
    def test_a_length_indicator_exactly_at_the_fixed_part_still_decodes(
        self, code: int, fixed_part: int
    ) -> None:
        # LI == fixed part is a TPDU with NO variable part, which is lawful and must not be refused.
        # This is the twin that stops the rule above becoming an off-by-one.
        body = bytes([fixed_part, code]) + bytes(fixed_part - 1)
        message = decoded(in_frame(tpkt(body)))
        assert message.message_type != "data"
        assert message.user_data_length == 0

    @pytest.mark.parametrize(
        ("code", "fixed_part"),
        [(0x80, 6), (0x70, 4), (0xE0, 6), (0xD0, 6)],
        ids=["dr", "er", "cr", "cc"],
    )
    def test_a_two_octet_variable_part_still_decodes(self, code: int, fixed_part: int) -> None:
        # The smallest lawful variable part: one parameter with a zero-length value.
        body = bytes([fixed_part + 2, code]) + bytes(fixed_part - 1) + bytes([0xE0, 0x00])
        message = decoded(in_frame(tpkt(body)))
        assert message.user_data_length == 0

    def test_the_rule_covers_every_named_tpdu_whose_fixed_part_is_known(self) -> None:
        # The genericity guard, and the reason this class exists rather than two more specials: for
        # every TPDU the module names and measures, a one-octet variable part must refuse. If a
        # seventh TPDU is added with a fixed-part size and no such check, this fails.
        measured = {
            "connection_request": (0xE0, 6),
            "connection_confirm": (0xD0, 6),
            "disconnect_request": (0x80, 6),
            "error": (0x70, 4),
        }
        for name, (code, fixed_part) in measured.items():
            body = bytes([fixed_part + 1, code]) + bytes(fixed_part - 1) + bytes([0xC1])
            result = dissect(in_frame(tpkt(body)))
            assert isinstance(result, MalformedFrame), (
                f"{name} accepted a one-octet variable part, so the rule is not generic"
            )
            assert result.reason is MalformedReason.INCONSISTENT_COUNT

    def test_the_rule_is_vacuous_for_the_two_exact_length_tpdus(self) -> None:
        # DT and ED fix their length indicator exactly, so the fixed part is always the whole
        # header and there is never a variable part to measure. They must be untouched by this rule
        # while still being refused by their own, for an LI above the exact value.
        assert decoded(in_frame(tpkt(dt()))).user_data_length == 0
        assert refused(in_frame(tpkt(cotp_header(3, 0xF0, b"\x80")))).reason is (
            MalformedReason.INCONSISTENT_COUNT
        )
        assert decoded(in_frame(tpkt(cotp_header(3, 0x10, b"\x00\x80")))).user_data_length == 0
        assert refused(in_frame(tpkt(cotp_header(4, 0x10, b"\x00\x80")))).reason is (
            MalformedReason.INCONSISTENT_COUNT
        )


class TestTheDoneList:
    """ADR 0347's fifteen items, each asserted against the reason the declaration names."""

    def test_item_1_a_payload_shorter_than_four_octets_is_short_header(self) -> None:
        for length in range(4):
            result = refused(in_frame(bytes(length)))
            assert result.reason is MalformedReason.SHORT_HEADER, f"{length} octets"

    def test_item_2_a_version_other_than_3_is_bad_header_field(self) -> None:
        for version in (0, 1, 2, 4, 5, 0xFF):
            if version == 3:
                continue
            result = refused(in_frame(tpkt(dt(), version=version)))
            assert result.reason is MalformedReason.BAD_HEADER_FIELD, f"version {version}"

    def test_item_2_is_reachable_because_the_claim_is_the_port_not_the_version(self) -> None:
        # ADR 0347's resolved ambiguity: a wrong version on a *claimed* frame is BAD_HEADER_FIELD.
        # That is only observable if a wrong version is claimed, which it is, by port.
        frame = in_frame(tpkt(dt(), version=4))
        assert IsoTsapDissector().claims(frame)
        assert refused(frame).reason is MalformedReason.BAD_HEADER_FIELD

    def test_item_3_a_declared_length_below_7_is_field_out_of_range(self) -> None:
        for declared in range(7):
            frame = in_frame(bytes([3, 0, declared >> 8, declared & 0xFF]) + bytes(20))
            assert isinstance(frame.payload, bytes) and len(frame.payload) > 7
            result = refused(frame)
            assert result.reason is MalformedReason.FIELD_OUT_OF_RANGE, f"length {declared}"

    def test_item_3_is_checked_before_any_slice_is_taken(self) -> None:
        # A 4-octet payload declaring 6 cannot be sliced at 6; the ORDER of checks is what proves
        # the check runs first, and the reason names the field rather than the buffer.
        result = refused(in_frame(bytes([3, 0, 0, 6])))
        assert result.reason is MalformedReason.FIELD_OUT_OF_RANGE
        assert "before any slice" in result.detail

    def test_item_4_a_length_greater_than_the_bytes_present_is_length_mismatch(self) -> None:
        for present in (7, 10, 100):
            result = refused(in_frame(bytes([3, 0, 0xFF, 0xFF]) + bytes(present - 4)))
            assert result.reason is MalformedReason.LENGTH_MISMATCH, f"{present} octets"

    def test_item_4_never_allocates_the_declared_size(self) -> None:
        # 65,535 declared, 7 present. Nothing may try to build 65,535 octets of anything.
        result = refused(in_frame(bytes([3, 0, 0xFF, 0xFF]) + bytes(3)))
        assert result.reason is MalformedReason.LENGTH_MISMATCH
        assert result.payload_length == 7

    def test_item_5_a_length_smaller_than_the_bytes_present_is_trailing_bytes(self) -> None:
        result = refused(in_frame(tpkt(dt(), trailing=b"\x00\x00")))
        assert result.reason is MalformedReason.TRAILING_BYTES

    def test_item_5_a_pipelined_second_tpkt_is_trailing_bytes(self) -> None:
        # P1 dissects one TPKT per frame and does no stream reassembly; the honest report of that.
        result = refused(in_frame(tpkt(dt()) + tpkt(dt())))
        assert result.reason is MalformedReason.TRAILING_BYTES

    def test_item_6_a_length_indicator_of_255_is_field_out_of_range(self) -> None:
        result = refused(in_frame(tpkt(bytes([255, 0xF0]) + bytes(30))))
        assert result.reason is MalformedReason.FIELD_OUT_OF_RANGE
        assert "extensions" in result.detail

    def test_item_7_an_li_claiming_more_header_than_present_is_inconsistent(self) -> None:
        result = refused(in_frame(tpkt(bytes([254, 0xF0]) + bytes(3))))
        assert result.reason is MalformedReason.INCONSISTENT_COUNT

    def test_item_7_a_dt_with_an_li_below_2_is_inconsistent(self) -> None:
        result = refused(in_frame(tpkt(bytes([1, 0xF0]) + bytes(10))))
        assert result.reason is MalformedReason.INCONSISTENT_COUNT

    def test_item_8_the_reserved_octet_is_recorded_and_never_a_reason(self) -> None:
        for reserved in (0x00, 0xFF):
            message = decoded(in_frame(tpkt(dt(), reserved=reserved)))
            assert message.reserved_octet == reserved

    def test_item_9_a_class_other_than_0_is_recorded_and_never_a_reason(self) -> None:
        message = decoded(in_frame(tpkt(connect(preferred_class=4))))
        assert message.cotp_class == 4

    def test_item_10_a_cr_with_user_data_or_a_third_parameter_decodes(self) -> None:
        parameters = (
            tsap_parameter(0xC1, b"\x01\x00")
            + tsap_parameter(0xC2, b"\x01\x02")
            + tsap_parameter(0xC0, b"\x0d")
        )
        message = decoded(in_frame(tpkt(connect(parameters=parameters, user_data=b"\xaa"))))
        assert message.user_data_length == 1

    def test_item_11_eot_is_bit_8_and_tpdu_nr_bits_7_to_1_on_a_dt(self) -> None:
        message = decoded(in_frame(tpkt(cotp_header(2, 0xF0, bytes([0xFF])))))
        assert message.eot is True
        assert message.tpdu_nr == 0x7F
        message = decoded(in_frame(tpkt(cotp_header(2, 0xF0, bytes([0x80])))))
        assert message.eot is True
        assert message.tpdu_nr == 0
        message = decoded(in_frame(tpkt(cotp_header(2, 0xF0, bytes([0x00])))))
        assert message.eot is False
        assert message.tpdu_nr == 0

    def test_item_12_no_program_act_station_or_peer_role_from_any_input(self) -> None:
        inputs = (
            tpkt(dt(user_data=S7_JOB_BYTES)),
            tpkt(connect(parameters=tsap_parameter(0xC1, b"\x03\x01"))),
            tpkt(cotp_header(2, 0xF1, b"\x80")),
            tpkt(cotp_header(2, 0x00)),
            bytes([3, 0, 0xFF, 0xFF]) + bytes(3),
            b"\x03",
        )
        for payload in inputs:
            result = dissect(in_frame(payload))
            assert isinstance(result, IsoTsapMessage | MalformedFrame)
            for forbidden in ("act", "program_act", "station", "peer_role", "job", "opcode"):
                assert forbidden not in type(result).model_fields, (
                    f"{type(result).__name__} exposes {forbidden}"
                )

    def test_item_15_every_result_traces_to_its_frame(self) -> None:
        frame = make_frame(
            tpkt(dt(user_data=b"\x01")),
            src_port=CLIENT_PORT,
            dst_port=ISO_TSAP_PORT,
            frame_index=77,
            capture="/captures/plant.pcap",
        )
        for result in (dissect(frame), dissect(make_frame(b"\x00", dst_port=ISO_TSAP_PORT))):
            assert result.source == frame.source or result.source.frame_index == 0
            assert result.timestamp is not None
            assert result.src.port in (CLIENT_PORT, ISO_TSAP_PORT)


class TestProtocolIsNeverS7comm:
    """ADR 0347's central honest-ceiling requirement, asserted directly."""

    def test_the_dissector_name_is_not_s7comm(self) -> None:
        # Read through a plain ``str`` so the comparison is a runtime assertion rather than one
        # mypy resolves to a constant; the property being checked is about the value at run time.
        name: str = IsoTsapDissector.name
        assert name != "s7comm"
        assert name == "iso-tsap"

    def test_every_message_reports_iso_tsap(self) -> None:
        for payload in (
            tpkt(dt(user_data=S7_JOB_BYTES)),
            tpkt(connect()),
            tpkt(cotp_header(2, 0x00, b"\x00")),
        ):
            # Compared as a plain string so this stays a runtime assertion: mypy knows the Literal
            # cannot be "s7comm", which is the property, and asserting it statically would hide it.
            assert str(decoded(in_frame(payload)).protocol) == "iso-tsap"

    def test_every_refusal_reports_iso_tsap(self) -> None:
        for payload in (b"\x03", bytes([3, 0, 0xFF, 0xFF]), tpkt(dt(), version=4)):
            assert refused(in_frame(payload)).protocol == "iso-tsap"

    def test_the_string_s7comm_is_unrepresentable_in_the_message_model(self) -> None:
        # A Literal rather than a str: a caller cannot build a message claiming to have read S7.
        from pydantic import ValidationError

        message = decoded(in_frame(tpkt(dt())))
        with pytest.raises(ValidationError):
            IsoTsapMessage(**{**message.model_dump(), "protocol": "s7comm"})

    def test_the_module_never_mentions_the_s7_protocol_name_as_a_value(self) -> None:
        # "S7" appears in prose explaining the ceiling, never as a protocol name in a field.
        import inspect

        from phos.atlas.packet import s7comm

        source = inspect.getsource(s7comm)
        assert 'protocol="s7comm"' not in source
        assert '"s7comm"' not in source.replace('``"s7comm"``', "")


class TestTraceability:
    """Every decoded message and every refusal carries the frame it came from (done list 15)."""

    def test_a_decoded_message_carries_source_timestamp_and_endpoints(self) -> None:
        frame = make_frame(
            tpkt(dt()),
            src_port=CLIENT_PORT,
            dst_port=ISO_TSAP_PORT,
            frame_index=5,
            capture="/c/plant.pcap",
        )
        message = decoded(frame)
        assert message.source.capture == "/c/plant.pcap"
        assert message.source.frame_index == 5
        assert message.timestamp == frame.timestamp
        assert message.src == frame.src
        assert message.dst == frame.dst

    def test_a_refusal_carries_source_and_the_payload_length_that_failed(self) -> None:
        frame = make_frame(tpkt(dt(), version=4), dst_port=ISO_TSAP_PORT, frame_index=9)
        result = refused(frame)
        assert result.source.frame_index == 9
        assert result.payload_length == len(frame.payload)

    def test_every_refusal_has_a_detail_naming_the_disagreement(self) -> None:
        cases = (
            b"",
            bytes([4, 0, 0, 7]) + bytes(3),
            bytes([3, 0, 0, 6]),
            bytes([3, 0, 0xFF, 0xFF]),
            tpkt(dt(), trailing=b"\x00"),
            tpkt(bytes([255, 0xF0]) + bytes(3)),
            tpkt(bytes([254, 0xF0]) + bytes(3)),
            tpkt(cotp_header(1, 0xF0)),
        )
        for payload in cases:
            result = refused(in_frame(payload))
            assert isinstance(result.reason, MalformedReason)
            assert result.detail


class TestTheSeam:
    """The dissector joins the registry without Modbus or the seam being touched (done list 14)."""

    def test_it_satisfies_the_dissector_protocol(self) -> None:
        from phos.atlas.packet import ProtocolDissector

        assert isinstance(IsoTsapDissector(), ProtocolDissector)

    def test_the_registry_dispatches_a_102_frame_to_it_and_a_502_frame_to_modbus(self) -> None:
        from phos.atlas.packet import ModbusDissector

        registry = DissectorRegistry([ModbusDissector(), IsoTsapDissector()])
        iso = registry.dispatch(in_frame(tpkt(dt())))
        assert isinstance(iso, IsoTsapMessage)
        assert iso.protocol == "iso-tsap"

        modbus = registry.dispatch(
            make_frame(bytes.fromhex("123400000006110300640002"), dst_port=502)
        )
        assert modbus.protocol == "modbus"

    def test_both_can_be_registered_without_a_name_clash(self) -> None:
        from phos.atlas.packet import ModbusDissector

        registry = DissectorRegistry([ModbusDissector()]).with_dissector(IsoTsapDissector())
        assert registry.names == ("modbus", "iso-tsap")


class TestTheFixtureBuildersThemselves:
    """The hand-built octets are checked against the constants they claim to satisfy."""

    def test_a_built_dt_is_seven_octets_and_says_so(self) -> None:
        assert len(tpkt(dt())) == 7

    def test_a_built_cr_has_a_six_octet_fixed_part_and_li_six(self) -> None:
        built = connect()
        # LI (1) + code (1) + six fixed octets (octets 2-7): the LI counts the code, not itself.
        assert built[0] == 6
        assert len(built) == 7

    def test_a_built_tsap_parameter_carries_its_length(self) -> None:
        parameter = tsap_parameter(0xC1, b"\x01\x00")
        assert parameter == b"\xc1\x02\x01\x00"

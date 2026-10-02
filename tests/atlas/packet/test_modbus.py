"""Tests for the Modbus/TCP dissector.

Correctness first — every expected field below is computed by hand from the Modbus application
protocol specification, not from what the code happens to produce. Then refusal: each way a frame
can be wrong has its own test asserting the specific reason, because "it returned a MalformedFrame"
is not evidence the parser understood what was wrong with it.

The random and mutated-input assault lives in `test_hardening.py`.
"""

from collections.abc import Callable
from pathlib import Path

import pytest
from tests.atlas.packet.conftest import (
    CLIENT_PORT,
    MODBUS_SERVER_PORT,
    make_frame,
    modbus_adu,
    tcp_frame,
)

from phos.atlas.packet import (
    Direction,
    DissectorRegistry,
    MalformedFrame,
    MalformedReason,
    ModbusDissector,
    ModbusMessage,
    RawFrame,
    Transport,
    dissect_capture,
)


def request_frame(pdu: bytes, **adu: object) -> RawFrame:
    """A frame travelling towards the Modbus server port."""
    return make_frame(
        modbus_adu(pdu, **adu),  # type: ignore[arg-type]
        src_port=CLIENT_PORT,
        dst_port=MODBUS_SERVER_PORT,
    )


def response_frame(pdu: bytes, **adu: object) -> RawFrame:
    """A frame travelling away from the Modbus server port."""
    return make_frame(
        modbus_adu(pdu, **adu),  # type: ignore[arg-type]
        src_port=MODBUS_SERVER_PORT,
        dst_port=CLIENT_PORT,
    )


def decoded(frame: RawFrame) -> ModbusMessage:
    """Dissect a frame that must decode, failing loudly if it did not."""
    result = ModbusDissector().dissect(frame)
    assert isinstance(result, ModbusMessage), result
    return result


def refused(frame: RawFrame) -> MalformedFrame:
    """Dissect a frame that must be refused, failing loudly if it decoded."""
    result = ModbusDissector().dissect(frame)
    assert isinstance(result, MalformedFrame), result
    return result


class TestClaims:
    def test_claims_traffic_towards_the_server_port(self) -> None:
        assert ModbusDissector().claims(make_frame(b"\x00" * 12, dst_port=502))

    def test_claims_traffic_from_the_server_port(self) -> None:
        assert ModbusDissector().claims(make_frame(b"\x00" * 12, src_port=502, dst_port=5555))

    def test_ignores_traffic_that_touches_neither_end(self) -> None:
        assert not ModbusDissector().claims(make_frame(b"\x00" * 12, src_port=44000, dst_port=80))

    def test_ignores_udp_because_modbus_tcp_is_tcp(self) -> None:
        frame = make_frame(b"\x00" * 12, dst_port=502, transport=Transport.UDP)
        assert not ModbusDissector().claims(frame)

    def test_claims_by_port_alone_so_rubbish_on_502_is_a_finding(self) -> None:
        # Deliberately no structural pre-check: bytes that are not Modbus arriving on the Modbus
        # port must reach `dissect` and be recorded as malformed, not quietly become unparsed
        # traffic. That distinction is the whole point of claiming by port.
        assert ModbusDissector().claims(make_frame(b"GET / HTTP/1.1\r\n", dst_port=502))

    def test_names_itself_modbus(self) -> None:
        assert ModbusDissector().name == "modbus"


class TestReadRequests:
    def test_read_holding_registers(self) -> None:
        # FC 3, start address 100 (0x0064), 2 registers.
        message = decoded(request_frame(bytes.fromhex("03") + bytes.fromhex("00640002")))
        assert message.function_code == 3
        assert message.function_name == "read_holding_registers"
        assert message.reference_address == 100
        assert message.quantity == 2
        assert message.values == ()
        assert message.exception_code is None
        assert message.direction is Direction.REQUEST

    def test_carries_the_mbap_header_through(self) -> None:
        message = decoded(
            request_frame(bytes.fromhex("0300640002"), transaction_id=0xBEEF, unit_id=42)
        )
        assert message.transaction_id == 0xBEEF
        assert message.unit_id == 42
        assert message.protocol == "modbus"

    def test_read_coils(self) -> None:
        # FC 1, start address 19 (0x0013), 37 coils (0x0025).
        message = decoded(request_frame(bytes.fromhex("01") + bytes.fromhex("00130025")))
        assert message.function_name == "read_coils"
        assert message.reference_address == 19
        assert message.quantity == 37

    def test_read_discrete_inputs(self) -> None:
        message = decoded(request_frame(bytes.fromhex("02") + bytes.fromhex("00C40016")))
        assert message.function_name == "read_discrete_inputs"
        assert message.reference_address == 196
        assert message.quantity == 22

    def test_read_input_registers(self) -> None:
        message = decoded(request_frame(bytes.fromhex("04") + bytes.fromhex("00080001")))
        assert message.function_name == "read_input_registers"
        assert message.reference_address == 8
        assert message.quantity == 1


class TestReadResponses:
    def test_read_holding_registers_response_decodes_registers(self) -> None:
        # FC 3, byte count 4, registers 0x000A = 10 and 0x0014 = 20.
        message = decoded(response_frame(bytes.fromhex("03") + bytes.fromhex("04000A0014")))
        assert message.function_name == "read_holding_registers"
        assert message.values == (10, 20)
        assert message.direction is Direction.RESPONSE

    def test_a_read_response_does_not_invent_the_address_that_was_read(self) -> None:
        # The address was in the request. Back-filling it would need request/response
        # correlation, which P1 does not do — so the field says "the bytes did not carry this".
        message = decoded(response_frame(bytes.fromhex("03") + bytes.fromhex("04000A0014")))
        assert message.reference_address is None
        assert message.quantity is None

    def test_read_coils_response_unpacks_bits_least_significant_first(self) -> None:
        # FC 1, byte count 3, data CD 6B 05 — the specification's own worked example.
        # 0xCD = 1100 1101 -> 1,0,1,1,0,0,1,1
        # 0x6B = 0110 1011 -> 1,1,0,1,0,1,1,0
        # 0x05 = 0000 0101 -> 1,0,1,0,0,0,0,0
        message = decoded(response_frame(bytes.fromhex("01") + bytes.fromhex("03CD6B05")))
        # fmt: off — one row per source byte, so the unpacking above can be checked by eye.
        assert message.values == (
            1,
            0,
            1,
            1,
            0,
            0,
            1,
            1,
            1,
            1,
            0,
            1,
            0,
            1,
            1,
            0,
            1,
            0,
            1,
            0,
            0,
            0,
            0,
            0,
        )
        # fmt: on

    def test_a_coil_read_response_reports_its_padding_rather_than_guessing(self) -> None:
        # The coil count lived in the request, so all 8 bits of the single byte are reported.
        message = decoded(response_frame(bytes.fromhex("02") + bytes.fromhex("0103")))
        assert message.values == (1, 1, 0, 0, 0, 0, 0, 0)

    def test_read_input_registers_response(self) -> None:
        message = decoded(response_frame(bytes.fromhex("04") + bytes.fromhex("02000A")))
        assert message.values == (10,)


class TestWrites:
    def test_write_single_coil(self) -> None:
        # FC 5, address 172 (0x00AC), value 0xFF00 = on.
        message = decoded(request_frame(bytes.fromhex("05") + bytes.fromhex("00ACFF00")))
        assert message.function_name == "write_single_coil"
        assert message.reference_address == 172
        assert message.values == (0xFF00,)
        assert message.quantity is None

    def test_write_single_coil_reports_an_illegal_value_as_it_arrived(self) -> None:
        # 0x1234 is not a legal coil value, but the frame is structurally sound. Whether a device
        # should have sent it is a behavioural question for P2, not a parse failure.
        message = decoded(request_frame(bytes.fromhex("05") + bytes.fromhex("00AC1234")))
        assert message.values == (0x1234,)

    def test_write_single_register(self) -> None:
        # FC 6, address 1, value 3.
        message = decoded(request_frame(bytes.fromhex("06") + bytes.fromhex("00010003")))
        assert message.function_name == "write_single_register"
        assert message.reference_address == 1
        assert message.values == (3,)

    def test_write_single_register_response_echoes_the_request(self) -> None:
        message = decoded(response_frame(bytes.fromhex("06") + bytes.fromhex("00010003")))
        assert message.reference_address == 1
        assert message.values == (3,)
        assert message.direction is Direction.RESPONSE

    def test_write_multiple_registers_request(self) -> None:
        # FC 16, address 1, 2 registers, byte count 4, values 0x000A = 10 and 0x0102 = 258.
        message = decoded(request_frame(bytes.fromhex("10") + bytes.fromhex("0001000204000A0102")))
        assert message.function_name == "write_multiple_registers"
        assert message.reference_address == 1
        assert message.quantity == 2
        assert message.values == (10, 258)

    def test_write_multiple_registers_response_carries_only_the_extent(self) -> None:
        message = decoded(response_frame(bytes.fromhex("10") + bytes.fromhex("00010002")))
        assert message.reference_address == 1
        assert message.quantity == 2
        assert message.values == ()

    def test_write_multiple_coils_request_unpacks_exactly_the_declared_coils(self) -> None:
        # FC 15, address 19, 10 coils, byte count 2, data CD 01.
        # The count is on the wire here, so exactly 10 bits are reported and the 6 padding bits
        # of the second byte are not.
        message = decoded(request_frame(bytes.fromhex("0F") + bytes.fromhex("0013000A02CD01")))
        assert message.function_name == "write_multiple_coils"
        assert message.reference_address == 19
        assert message.quantity == 10
        assert message.values == (1, 0, 1, 1, 0, 0, 1, 1, 1, 0)

    def test_write_multiple_coils_response(self) -> None:
        message = decoded(response_frame(bytes.fromhex("0F") + bytes.fromhex("0013000A")))
        assert message.reference_address == 19
        assert message.quantity == 10
        assert message.values == ()


class TestExceptions:
    def test_an_exception_response_carries_its_code(self) -> None:
        # FC 3 with bit 7 set = 0x83, exception code 2 (illegal data address).
        message = decoded(response_frame(bytes.fromhex("8302")))
        assert message.function_code == 0x83
        assert message.function_name == "read_holding_registers.exception"
        assert message.exception_code == 2
        assert message.direction is Direction.RESPONSE

    def test_an_exception_on_an_unknown_function_is_still_readable(self) -> None:
        message = decoded(response_frame(bytes.fromhex("E501")))
        assert message.function_name == "unknown(101).exception"
        assert message.exception_code == 1

    def test_an_exception_is_decoded_whichever_way_it_travelled(self) -> None:
        # The exception bit is a structural fact; direction stays a transport fact.
        message = decoded(request_frame(bytes.fromhex("8302")))
        assert message.exception_code == 2
        assert message.direction is Direction.REQUEST


class TestUnknownFunctions:
    def test_an_unrecognised_function_code_decodes_rather_than_fails(self) -> None:
        message = decoded(request_frame(bytes.fromhex("65") + bytes.fromhex("0001")))
        assert message.function_code == 0x65
        assert message.function_name == "unknown(101)"
        assert message.values == ()
        assert message.reference_address is None

    def test_an_unrecognised_function_with_no_data_decodes(self) -> None:
        assert decoded(request_frame(bytes.fromhex("65"))).function_name == "unknown(101)"


class TestDirection:
    def test_towards_the_server_port_is_a_request(self) -> None:
        assert decoded(request_frame(bytes.fromhex("0300640002"))).direction is Direction.REQUEST

    def test_away_from_the_server_port_is_a_response(self) -> None:
        assert (
            decoded(response_frame(bytes.fromhex("0304000A0014"))).direction is Direction.RESPONSE
        )

    def test_server_port_at_both_ends_is_undetermined(self) -> None:
        frame = make_frame(modbus_adu(bytes.fromhex("0300640002")), src_port=502, dst_port=502)
        assert decoded(frame).direction is Direction.UNKNOWN

    def test_an_undetermined_direction_decodes_no_payload_fields(self) -> None:
        # Choosing between the request and response layouts on a guess would invent an address
        # that may not be there. The header is still reported; the body is not.
        frame = make_frame(modbus_adu(bytes.fromhex("0300640002")), src_port=502, dst_port=502)
        message = decoded(frame)
        assert message.function_name == "read_holding_registers"
        assert message.reference_address is None
        assert message.quantity is None
        assert message.values == ()


class TestMalformedHeaders:
    @pytest.mark.parametrize("length", [0, 1, 3, 6])
    def test_a_payload_too_short_for_the_mbap_header(self, length: int) -> None:
        malformed = refused(make_frame(b"\x00" * length, dst_port=502))
        assert malformed.reason is MalformedReason.SHORT_HEADER
        assert malformed.payload_length == length
        assert malformed.protocol == "modbus"

    def test_a_non_zero_protocol_id(self) -> None:
        malformed = refused(request_frame(bytes.fromhex("0300640002"), protocol_id=1))
        assert malformed.reason is MalformedReason.BAD_HEADER_FIELD
        assert "protocol id" in malformed.detail

    def test_non_modbus_bytes_on_the_modbus_port(self) -> None:
        # "GET " reads as transaction id 0x4745 and protocol id 0x5420, which is not Modbus.
        malformed = refused(make_frame(b"GET / HTTP/1.1\r\n\r\n", dst_port=502))
        assert malformed.reason is MalformedReason.BAD_HEADER_FIELD

    @pytest.mark.parametrize("declared", [0, 1, 255, 65535])
    def test_a_length_field_outside_the_protocol_limits(self, declared: int) -> None:
        malformed = refused(request_frame(bytes.fromhex("0300640002"), length=declared))
        assert malformed.reason is MalformedReason.FIELD_OUT_OF_RANGE

    def test_a_length_field_claiming_more_bytes_than_arrived(self) -> None:
        malformed = refused(request_frame(bytes.fromhex("0300640002"), length=40))
        assert malformed.reason is MalformedReason.LENGTH_MISMATCH
        assert "40" in malformed.detail

    def test_a_length_field_claiming_fewer_bytes_than_arrived(self) -> None:
        # Two ADUs pipelined into one segment. P1 dissects one message per frame and does no
        # stream reassembly, so the extra bytes are surfaced rather than half-parsed or dropped.
        pipelined = modbus_adu(bytes.fromhex("0300640002")) + modbus_adu(
            bytes.fromhex("0300660002")
        )
        malformed = refused(make_frame(pipelined, dst_port=502))
        assert malformed.reason is MalformedReason.TRAILING_BYTES


class TestMalformedBodies:
    @pytest.mark.parametrize("pdu", ["03", "030064", "0300640002" + "00"])
    def test_a_read_request_body_of_the_wrong_size(self, pdu: str) -> None:
        malformed = refused(request_frame(bytes.fromhex(pdu)))
        assert malformed.reason is MalformedReason.SHORT_BODY

    @pytest.mark.parametrize(
        ("pdu", "described"),
        [("030064007E", "126 registers"), ("0100640BB9", "3001 coils")],
    )
    def test_a_read_quantity_beyond_the_protocol_limit(self, pdu: str, described: str) -> None:
        malformed = refused(request_frame(bytes.fromhex(pdu)))
        assert malformed.reason is MalformedReason.FIELD_OUT_OF_RANGE
        assert described.split()[0] in malformed.detail

    @pytest.mark.parametrize("pdu", ["0300640000", "0100640000"])
    def test_a_read_quantity_of_zero(self, pdu: str) -> None:
        malformed = refused(request_frame(bytes.fromhex(pdu)))
        assert malformed.reason is MalformedReason.FIELD_OUT_OF_RANGE

    def test_a_read_response_byte_count_running_past_the_buffer(self) -> None:
        # Byte count claims 200 bytes; four arrived. Reading it would run off the end.
        malformed = refused(response_frame(bytes.fromhex("03") + bytes.fromhex("C8000A0014")))
        assert malformed.reason is MalformedReason.SHORT_BODY

    def test_a_read_response_with_no_byte_count_at_all(self) -> None:
        malformed = refused(response_frame(bytes.fromhex("03")))
        assert malformed.reason is MalformedReason.SHORT_BODY

    def test_a_read_response_byte_count_of_zero(self) -> None:
        malformed = refused(response_frame(bytes.fromhex("0300")))
        assert malformed.reason is MalformedReason.FIELD_OUT_OF_RANGE

    def test_a_register_read_response_with_an_odd_byte_count(self) -> None:
        # Registers are 16 bits, so an odd byte count cannot describe whole registers.
        malformed = refused(response_frame(bytes.fromhex("03") + bytes.fromhex("03000A00")))
        assert malformed.reason is MalformedReason.INCONSISTENT_COUNT

    def test_a_single_write_body_of_the_wrong_size(self) -> None:
        assert refused(request_frame(bytes.fromhex("0600AC"))).reason is MalformedReason.SHORT_BODY

    def test_a_write_multiple_request_too_short_to_hold_its_own_header(self) -> None:
        malformed = refused(request_frame(bytes.fromhex("10") + bytes.fromhex("00010002")))
        assert malformed.reason is MalformedReason.SHORT_BODY

    def test_a_write_multiple_byte_count_running_past_the_buffer(self) -> None:
        # Byte count claims 200; two arrived.
        malformed = refused(request_frame(bytes.fromhex("10") + bytes.fromhex("00010002C80102")))
        assert malformed.reason is MalformedReason.SHORT_BODY

    def test_a_write_multiple_registers_quantity_beyond_the_limit(self) -> None:
        malformed = refused(
            request_frame(bytes.fromhex("10") + bytes.fromhex("000100C80400010002"))
        )
        assert malformed.reason is MalformedReason.FIELD_OUT_OF_RANGE

    def test_a_write_multiple_registers_byte_count_disagreeing_with_its_quantity(self) -> None:
        # 2 registers need 4 bytes; the frame declares 6 and supplies 6.
        malformed = refused(
            request_frame(bytes.fromhex("10") + bytes.fromhex("0001000206000A0102FFFF"))
        )
        assert malformed.reason is MalformedReason.INCONSISTENT_COUNT

    def test_a_write_multiple_coils_quantity_beyond_the_limit(self) -> None:
        malformed = refused(request_frame(bytes.fromhex("0F") + bytes.fromhex("00130800020102")))
        assert malformed.reason is MalformedReason.FIELD_OUT_OF_RANGE

    def test_a_write_multiple_coils_byte_count_disagreeing_with_its_quantity(self) -> None:
        # 10 coils need 2 bytes; the frame declares 3 and supplies 3.
        malformed = refused(request_frame(bytes.fromhex("0F") + bytes.fromhex("0013000A03CD0100")))
        assert malformed.reason is MalformedReason.INCONSISTENT_COUNT

    def test_a_write_multiple_response_of_the_wrong_size(self) -> None:
        malformed = refused(response_frame(bytes.fromhex("10") + bytes.fromhex("000100")))
        assert malformed.reason is MalformedReason.SHORT_BODY

    def test_a_write_multiple_response_quantity_beyond_the_limit(self) -> None:
        malformed = refused(response_frame(bytes.fromhex("10") + bytes.fromhex("000100C8")))
        assert malformed.reason is MalformedReason.FIELD_OUT_OF_RANGE

    def test_a_write_multiple_coils_response_quantity_beyond_the_limit(self) -> None:
        malformed = refused(response_frame(bytes.fromhex("0F") + bytes.fromhex("00130800")))
        assert malformed.reason is MalformedReason.FIELD_OUT_OF_RANGE

    @pytest.mark.parametrize("pdu", ["83", "830201"])
    def test_an_exception_response_that_is_not_exactly_one_byte(self, pdu: str) -> None:
        malformed = refused(response_frame(bytes.fromhex(pdu)))
        assert malformed.reason is MalformedReason.SHORT_BODY


class TestTraceability:
    def test_a_decoded_message_names_its_source_frame(self) -> None:
        frame = make_frame(
            modbus_adu(bytes.fromhex("0300640002")),
            dst_port=502,
            frame_index=91,
            capture="/captures/plant.pcap",
        )
        message = decoded(frame)
        assert message.source.frame_index == 91
        assert message.source.capture == "/captures/plant.pcap"
        assert message.timestamp == frame.timestamp

    def test_a_refusal_names_its_source_frame_just_as_precisely(self) -> None:
        frame = make_frame(b"\x00" * 3, dst_port=502, frame_index=91, capture="/captures/x.pcap")
        malformed = refused(frame)
        assert malformed.source.frame_index == 91
        assert malformed.source.capture == "/captures/x.pcap"
        assert malformed.timestamp == frame.timestamp
        assert malformed.src == frame.src
        assert malformed.dst == frame.dst

    def test_end_to_end_from_a_capture_file(self, write_pcap: Callable[..., Path]) -> None:
        # The whole vertical: bytes on disk to a decoded write command, traceable to its frame.
        write_pdu = bytes.fromhex("10") + bytes.fromhex("0001000204000A0102")
        path = write_pcap(
            [
                (1700000000, 0, tcp_frame(5555, 502, modbus_adu(write_pdu))),
                (1700000001, 0, tcp_frame(502, 5555, modbus_adu(bytes.fromhex("1000010002")))),
            ]
        )
        results = list(dissect_capture(path, DissectorRegistry([ModbusDissector()])))

        assert isinstance(results[0], ModbusMessage)
        assert results[0].function_name == "write_multiple_registers"
        assert results[0].values == (10, 258)
        assert results[0].direction is Direction.REQUEST
        assert results[0].source.frame_index == 0

        assert isinstance(results[1], ModbusMessage)
        assert results[1].direction is Direction.RESPONSE
        assert results[1].source.frame_index == 1

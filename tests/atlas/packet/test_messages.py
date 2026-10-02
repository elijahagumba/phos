"""Tests for the typed message model dissectors produce."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from phos.atlas.packet import (
    Direction,
    Endpoint,
    FrameSource,
    IcsMessage,
    MalformedFrame,
    MalformedReason,
    ModbusMessage,
    UnparsedMessage,
)

SOURCE = FrameSource(capture="/captures/plant.pcap", frame_index=4)
WHEN = datetime(2026, 8, 12, 9, 30, tzinfo=UTC)
CLIENT = Endpoint(ip="10.0.0.1", port=5555)
SERVER = Endpoint(ip="10.0.0.2", port=502)

BASE: dict[str, object] = {
    "source": SOURCE,
    "timestamp": WHEN,
    "src": CLIENT,
    "dst": SERVER,
    "direction": Direction.REQUEST,
}


def modbus(**overrides: object) -> ModbusMessage:
    fields: dict[str, object] = {
        **BASE,
        "transaction_id": 0x1234,
        "unit_id": 17,
        "function_code": 3,
        "function_name": "read_holding_registers",
    }
    fields.update(overrides)
    return ModbusMessage(**fields)  # type: ignore[arg-type]


class TestDirection:
    def test_covers_request_response_and_unknown(self) -> None:
        assert {member.value for member in Direction} == {"REQUEST", "RESPONSE", "UNKNOWN"}

    def test_is_string_backed(self) -> None:
        assert Direction.REQUEST == "REQUEST"


class TestMalformedReason:
    def test_every_reason_is_protocol_agnostic(self) -> None:
        # The reasons name shapes of failure, not Modbus fields, so a later dissector reuses them.
        assert {member.value for member in MalformedReason} == {
            "SHORT_HEADER",
            "BAD_HEADER_FIELD",
            "LENGTH_MISMATCH",
            "TRAILING_BYTES",
            "SHORT_BODY",
            "FIELD_OUT_OF_RANGE",
            "INCONSISTENT_COUNT",
        }


class TestIcsMessage:
    def test_carries_provenance_endpoints_and_direction(self) -> None:
        message = IcsMessage(protocol="test", **BASE)  # type: ignore[arg-type]
        assert message.protocol == "test"
        assert message.source is SOURCE
        assert message.timestamp == WHEN
        assert message.direction is Direction.REQUEST

    def test_is_frozen(self) -> None:
        message = IcsMessage(protocol="test", **BASE)  # type: ignore[arg-type]
        with pytest.raises(ValidationError):
            message.protocol = "other"  # type: ignore[misc]


class TestModbusMessage:
    def test_is_an_ics_message(self) -> None:
        assert isinstance(modbus(), IcsMessage)

    def test_names_its_protocol_without_being_told(self) -> None:
        assert modbus().protocol == "modbus"

    def test_undecoded_fields_default_to_absent(self) -> None:
        message = modbus()
        assert message.reference_address is None
        assert message.quantity is None
        assert message.exception_code is None
        assert message.values == ()

    def test_is_frozen(self) -> None:
        with pytest.raises(ValidationError):
            modbus().unit_id = 2  # type: ignore[misc]

    @pytest.mark.parametrize("unit_id", [-1, 256])
    def test_rejects_a_unit_id_outside_one_byte(self, unit_id: int) -> None:
        with pytest.raises(ValidationError):
            modbus(unit_id=unit_id)

    @pytest.mark.parametrize("unit_id", [0, 255])
    def test_accepts_the_unit_id_boundaries(self, unit_id: int) -> None:
        assert modbus(unit_id=unit_id).unit_id == unit_id

    @pytest.mark.parametrize("code", [-1, 256])
    def test_rejects_a_function_code_outside_one_byte(self, code: int) -> None:
        with pytest.raises(ValidationError):
            modbus(function_code=code)

    @pytest.mark.parametrize("transaction_id", [-1, 65536])
    def test_rejects_a_transaction_id_outside_two_bytes(self, transaction_id: int) -> None:
        with pytest.raises(ValidationError):
            modbus(transaction_id=transaction_id)

    @pytest.mark.parametrize("address", [-1, 65536])
    def test_rejects_a_reference_address_outside_the_address_space(self, address: int) -> None:
        with pytest.raises(ValidationError):
            modbus(reference_address=address)

    def test_rejects_a_negative_quantity(self) -> None:
        with pytest.raises(ValidationError):
            modbus(quantity=-1)

    @pytest.mark.parametrize("code", [-1, 256])
    def test_rejects_an_exception_code_outside_one_byte(self, code: int) -> None:
        with pytest.raises(ValidationError):
            modbus(exception_code=code)

    @pytest.mark.parametrize("value", [-1, 65536])
    def test_rejects_a_value_outside_a_16_bit_register(self, value: int) -> None:
        # This bound is the tripwire the fuzz suite relies on: a decode that ran past its buffer
        # or misread a width would produce a value outside it and fail loudly rather than flow on.
        with pytest.raises(ValidationError):
            modbus(values=(value,))

    def test_accepts_a_full_register_range_of_values(self) -> None:
        assert modbus(values=(0, 65535)).values == (0, 65535)

    def test_rejects_an_empty_function_name(self) -> None:
        with pytest.raises(ValidationError):
            modbus(function_name="")

    def test_values_are_a_tuple_even_when_given_a_list(self) -> None:
        assert modbus(values=[1, 2]).values == (1, 2)


class TestUnparsedMessage:
    def test_is_an_ics_message_carrying_only_a_length(self) -> None:
        message = UnparsedMessage(**BASE, payload_length=120)  # type: ignore[arg-type]
        assert isinstance(message, IcsMessage)
        assert message.payload_length == 120

    def test_declares_that_nothing_was_decoded(self) -> None:
        message = UnparsedMessage(**BASE, payload_length=0)  # type: ignore[arg-type]
        assert message.protocol == "unknown"

    def test_rejects_a_negative_length(self) -> None:
        with pytest.raises(ValidationError):
            UnparsedMessage(**BASE, payload_length=-1)  # type: ignore[arg-type]

    def test_is_frozen(self) -> None:
        message = UnparsedMessage(**BASE, payload_length=1)  # type: ignore[arg-type]
        with pytest.raises(ValidationError):
            message.payload_length = 2  # type: ignore[misc]


class TestMalformedFrame:
    def _malformed(self, **overrides: object) -> MalformedFrame:
        fields: dict[str, object] = {
            "protocol": "modbus",
            "source": SOURCE,
            "timestamp": WHEN,
            "src": CLIENT,
            "dst": SERVER,
            "reason": MalformedReason.SHORT_HEADER,
            "detail": "payload of 3 bytes is shorter than the 7-byte MBAP header",
            "payload_length": 3,
        }
        fields.update(overrides)
        return MalformedFrame(**fields)  # type: ignore[arg-type]

    def test_is_not_an_ics_message(self) -> None:
        # A frame that failed validation is not a message. Keeping it off the IcsMessage branch
        # means a consumer cannot treat a parse failure as decoded traffic by accident.
        assert not isinstance(self._malformed(), IcsMessage)

    def test_records_what_failed_and_why(self) -> None:
        malformed = self._malformed()
        assert malformed.reason is MalformedReason.SHORT_HEADER
        assert "7-byte MBAP header" in malformed.detail
        assert malformed.protocol == "modbus"
        assert malformed.payload_length == 3

    def test_keeps_the_provenance_of_the_frame_that_failed(self) -> None:
        assert self._malformed().source == SOURCE

    def test_is_frozen(self) -> None:
        with pytest.raises(ValidationError):
            self._malformed().reason = MalformedReason.SHORT_BODY  # type: ignore[misc]

    def test_rejects_an_empty_detail(self) -> None:
        # An unexplained rejection cannot be audited, which is the whole purpose of the type.
        with pytest.raises(ValidationError):
            self._malformed(detail="")

    def test_rejects_a_negative_payload_length(self) -> None:
        with pytest.raises(ValidationError):
            self._malformed(payload_length=-1)

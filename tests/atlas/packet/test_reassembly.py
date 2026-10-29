"""The foundation declared in ADR 0345: reassembly, framing, pairing, claim order."""

from datetime import UTC, datetime, timedelta

import pytest
from tests.atlas.packet.conftest import make_frame

from phos.atlas.packet import (
    MAX_BUFFERED_BYTES_PER_FLOW,
    MAX_CONCURRENT_FLOWS,
    MAX_OPEN_PAIRS,
    MAX_OUT_OF_ORDER_SEGMENTS,
    MAX_SEGMENT_OCTETS,
    MODBUS_PORT,
    PAIR_EXPIRY,
    ContiguousStream,
    DeliveredOctets,
    DissectorRegistry,
    FlowKey,
    FlowRefusal,
    ModbusDissector,
    PairMatch,
    PairMiss,
    PairTable,
    PairWaiting,
    Reassembler,
    TcpSegment,
)
from phos.atlas.packet.frame import RawFrame
from phos.atlas.packet.messages import (
    MODBUS_PROTOCOL,
    Direction,
    IcsMessage,
    MalformedFrame,
    ModbusMessage,
    UnparsedMessage,
)
from phos.atlas.packet.pairing import EXPIRED, PAIR_CAP, SUPERSEDED, UNSOLICITED
from phos.atlas.packet.reassembly import (
    BYTE_CAP,
    OVERLAP,
    PDU_LENGTH,
    REORDER_CAP,
    SEGMENT_TOO_LONG,
    _ranges_overlap,
)

WHEN = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)
KEY = FlowKey("10.0.0.1", 40000, "10.0.0.2", 102)


def _seg(seq: int, payload: bytes, key: FlowKey = KEY) -> TcpSegment:
    return TcpSegment(key, seq, payload)


def _data(result: DeliveredOctets | FlowRefusal) -> bytes:
    assert isinstance(result, DeliveredOctets)
    return result.data


class TestReassembly:
    def test_in_order_segments_concatenate(self) -> None:
        machine = Reassembler()
        assert _data(machine.push(_seg(0, b"AB"))) == b"AB"
        assert _data(machine.push(_seg(2, b"CD"))) == b"CD"

    def test_a_gap_is_not_filled_with_zeros(self) -> None:
        machine = Reassembler()
        assert _data(machine.push(_seg(0, b"A"))) == b"A"
        assert _data(machine.push(_seg(2, b"C"))) == b""
        assert _data(machine.push(_seg(1, b"B"))) == b"BC"

    def test_sequence_numbers_wrap_the_32_bit_space(self) -> None:
        machine = Reassembler()
        assert _data(machine.push(_seg(0xFFFFFFFF, b"Z"))) == b"Z"
        assert _data(machine.push(_seg(0, b"Y"))) == b"Y"

    def test_an_overlap_refuses_the_flow_and_stores_nothing(self) -> None:
        machine = Reassembler()
        assert _data(machine.push(_seg(0, b"ABCD"))) == b"ABCD"
        refused = machine.push(_seg(2, b"XX"))
        assert isinstance(refused, FlowRefusal)
        assert refused.reason == OVERLAP
        assert machine.buffered_octets(KEY) == 0
        again = machine.push(_seg(4, b"ZZ"))
        assert isinstance(again, FlowRefusal)
        assert again.reason == OVERLAP

    def test_an_in_order_segment_that_covers_a_stored_byte_is_an_overlap(self) -> None:
        machine = Reassembler()
        assert _data(machine.push(_seg(0, b"AB"))) == b"AB"
        assert _data(machine.push(_seg(3, b"X"))) == b""
        refused = machine.push(_seg(2, b"CD"))
        assert isinstance(refused, FlowRefusal)
        assert refused.reason == OVERLAP
        assert machine.buffered_octets(KEY) == 1
        assert isinstance(machine.push(_seg(4, b"")), FlowRefusal)
        assert isinstance(machine.push(_seg(4, b"Y" * 70000)), FlowRefusal)

    def test_a_retransmission_is_an_overlap(self) -> None:
        machine = Reassembler()
        machine.push(_seg(0, b"AB"))
        refused = machine.push(_seg(0, b"AB"))
        assert isinstance(refused, FlowRefusal)
        assert refused.reason == OVERLAP

    def test_the_17th_out_of_order_segment_is_refused(self) -> None:
        machine = Reassembler()
        assert _data(machine.push(_seg(0, b"A"))) == b"A"
        for index in range(MAX_OUT_OF_ORDER_SEGMENTS):
            seq = 2 + index * 2
            assert _data(machine.push(_seg(seq, b"Z"))) == b""
        refused = machine.push(_seg(2 + MAX_OUT_OF_ORDER_SEGMENTS * 2, b"Z"))
        assert isinstance(refused, FlowRefusal)
        assert refused.reason == REORDER_CAP
        assert machine.out_of_order_count(KEY) == MAX_OUT_OF_ORDER_SEGMENTS

    def test_the_byte_cap_does_not_keep_a_shortened_segment(self) -> None:
        machine = Reassembler()
        machine.push(_seg(0, b"A"))
        first = b"B" * 65535
        assert _data(machine.push(_seg(2, first))) == b""
        assert _data(machine.push(_seg(2 + 65535, b"C" * 65535))) == b""
        refused = machine.push(_seg(2 + 65535 + 65535, b"DDD"))
        assert isinstance(refused, FlowRefusal)
        assert refused.reason == BYTE_CAP
        assert machine.buffered_octets(KEY) == 65535 * 2

    def test_a_segment_over_65535_octets_is_not_stored(self) -> None:
        machine = Reassembler()
        refused = machine.push(_seg(0, b"Q" * (MAX_SEGMENT_OCTETS + 1)))
        assert isinstance(refused, FlowRefusal)
        assert refused.reason == SEGMENT_TOO_LONG
        assert machine.flow_count == 0
        assert _data(machine.push(_seg(0, b"ok"))) == b"ok"

    def test_the_257th_flow_is_refused(self) -> None:
        machine = Reassembler()
        for index in range(MAX_CONCURRENT_FLOWS):
            key = FlowKey("10.0.0.1", index, "10.0.0.2", 102)
            assert _data(machine.push(TcpSegment(key, 0, b"x"))) == b"x"
        extra = FlowKey("10.0.0.1", 99999, "10.0.0.2", 102)
        refused = machine.push(TcpSegment(extra, 0, b"y"))
        assert isinstance(refused, FlowRefusal)
        assert refused.reason == "FLOW_CAP"
        assert machine.flow_count == MAX_CONCURRENT_FLOWS

    def test_an_empty_segment_does_not_move_the_cursor(self) -> None:
        machine = Reassembler()
        assert _data(machine.push(_seg(5, b""))) == b""
        assert machine.flow_count == 0
        assert _data(machine.push(_seg(5, b"A"))) == b"A"

    def test_a_gap_that_closes_keeps_a_segment_still_ahead_of_the_next_gap(self) -> None:
        # Two segments are stored ahead of two separate gaps. Closing the first gap may only
        # release the run that is now contiguous; the one still past a gap stays where it is.
        machine = Reassembler()
        assert _data(machine.push(_seg(0, b"A"))) == b"A"
        assert _data(machine.push(_seg(3, b"D"))) == b""
        assert _data(machine.push(_seg(5, b"F"))) == b""
        assert _data(machine.push(_seg(1, b"BC"))) == b"BCD"
        assert machine.out_of_order_count(KEY) == 1
        assert machine.buffered_octets(KEY) == 1
        assert _data(machine.push(_seg(4, b"E"))) == b"EF"
        assert machine.out_of_order_count(KEY) == 0

    def test_a_refused_flow_does_not_refuse_the_others(self) -> None:
        machine = Reassembler()
        other = FlowKey("10.0.0.3", 40001, "10.0.0.4", 102)
        assert _data(machine.push(_seg(0, b"AB"))) == b"AB"
        assert isinstance(machine.push(_seg(0, b"AB")), FlowRefusal)
        assert _data(machine.push(TcpSegment(other, 9, b"CD"))) == b"CD"
        assert _data(machine.push(TcpSegment(other, 11, b"EF"))) == b"EF"
        assert isinstance(machine.push(_seg(2, b"CD")), FlowRefusal)

    def test_the_overlap_guard_answers_for_a_range_with_no_octets(self) -> None:
        # `push` returns early on an empty payload, so the guard never sees a zero length in
        # practice. It still has to answer, because a later caller may not filter first.
        assert _ranges_overlap(0, 0, 0, 4) is False
        assert _ranges_overlap(0, 4, 0, 0) is False
        assert _ranges_overlap(0, 4, 2, 4) is True


class TestFraming:
    def test_take_waits_until_enough_octets_arrive(self) -> None:
        stream = ContiguousStream(KEY)
        assert stream.extend(b"abcd") is None
        assert stream.take(6) is None
        assert stream.extend(b"ef") is None
        assert stream.take(6) == b"abcdef"

    def test_take_pdu_does_not_ask_for_a_length_before_the_header_arrives(self) -> None:
        stream = ContiguousStream(KEY)
        calls = 0

        def length_of(header: bytes) -> int:
            nonlocal calls
            calls += 1
            return int.from_bytes(header, "big")

        assert stream.take_pdu(2, length_of) is None
        assert calls == 0
        assert stream.extend(b"\x00\x04WXYZ") is None
        assert stream.take_pdu(2, length_of) == b"\x00\x04WX"
        assert calls == 1

    def test_a_lying_length_does_not_consume_the_header(self) -> None:
        stream = ContiguousStream(KEY)
        assert stream.extend(b"\x00\x01AB") is None
        refused = stream.take_pdu(2, lambda _header: 1)
        assert isinstance(refused, FlowRefusal)
        assert refused.reason == PDU_LENGTH
        assert stream.take(2) == b"\x00\x01"

    def test_extend_refuses_a_buffer_past_the_cap_without_shortening(self) -> None:
        stream = ContiguousStream(KEY)
        assert stream.extend(b"A" * MAX_BUFFERED_BYTES_PER_FLOW) is None
        refused = stream.extend(b"B")
        assert isinstance(refused, FlowRefusal)
        assert refused.reason == BYTE_CAP
        assert stream.take(1) == b"A"


class TestPairing:
    def test_a_response_completes_the_request(self) -> None:
        table = PairTable()
        stored = table.offer(KEY, b"\x00\x07", is_request=True, at=WHEN, token="ask")
        assert stored == (PairWaiting(KEY, b"\x00\x07"),)
        matched = table.offer(KEY, b"\x00\x07", is_request=False, at=WHEN, token="answer")
        assert matched == (PairMatch(KEY, b"\x00\x07", "ask", "answer"),)

    def test_a_response_with_no_request_is_a_miss(self) -> None:
        table = PairTable()
        missed = table.offer(KEY, b"\x01", is_request=False, at=WHEN, token="late")
        assert missed == (PairMiss(KEY, b"\x01", UNSOLICITED),)

    def test_expiry_is_recorded_before_the_pair_is_dropped(self) -> None:
        table = PairTable()
        table.offer(KEY, b"\x02", is_request=True, at=WHEN, token="old")
        later = WHEN + PAIR_EXPIRY + timedelta(seconds=1)
        events = table.offer(KEY, b"\x03", is_request=True, at=later, token="new")
        assert PairMiss(KEY, b"\x02", EXPIRED) in events
        assert table.open_count(KEY) == 1

    def test_the_257th_open_pair_is_not_stored(self) -> None:
        table = PairTable()
        for index in range(MAX_OPEN_PAIRS):
            tx = index.to_bytes(2, "big")
            assert table.offer(KEY, tx, is_request=True, at=WHEN, token=index)[-1] == PairWaiting(
                KEY, tx
            )
        extra = table.offer(KEY, b"\xff\xff", is_request=True, at=WHEN, token="no")
        assert extra == (PairMiss(KEY, b"\xff\xff", PAIR_CAP),)
        assert table.open_count(KEY) == MAX_OPEN_PAIRS

    def test_a_second_request_records_the_first_as_superseded(self) -> None:
        table = PairTable()
        table.offer(KEY, b"\x04", is_request=True, at=WHEN, token="first")
        events = table.offer(KEY, b"\x04", is_request=True, at=WHEN, token="second")
        assert events[0] == PairMiss(KEY, b"\x04", SUPERSEDED)
        assert events[1] == PairWaiting(KEY, b"\x04")

    def test_pairing_does_not_write_into_a_modbus_message(self) -> None:
        message = ModbusMessage(
            source=make_frame(b"\x00").source,
            timestamp=WHEN,
            src=make_frame(b"\x00").src,
            dst=make_frame(b"\x00").dst,
            direction=Direction.REQUEST,
            transaction_id=7,
            unit_id=1,
            function_code=3,
            function_name="read_holding_registers",
        )
        table = PairTable()
        table.offer(KEY, b"\x00\x07", is_request=True, at=WHEN, token=message)
        assert message.reference_address is None
        assert message.protocol == MODBUS_PROTOCOL

    def test_a_naive_timestamp_is_a_caller_error(self) -> None:
        table = PairTable()
        with pytest.raises(ValueError):
            table.offer(
                KEY,
                b"\x00",
                is_request=True,
                at=datetime(2026, 10, 29, 12, 0),
                token=None,
            )


class _PayloadStub:
    """A dissector that decides from the payload rather than the port.

    Two of these prove the registry's order means what it says: the first one to claim is the
    only one that runs, and one that declines is passed over rather than ending the dispatch.
    """

    def __init__(self, name: str, wanted_parity: int | None) -> None:
        """Claim a non-empty payload whose first octet has ``wanted_parity``, or any if None."""
        self.name = name
        self._wanted_parity = wanted_parity

    def claims(self, frame: RawFrame) -> bool:
        """Look inside the payload, which is what makes this a claim and not a port rule."""
        if not frame.payload:
            return False
        if self._wanted_parity is None:
            return True
        return frame.payload[0] % 2 == self._wanted_parity

    def dissect(self, frame: RawFrame) -> IcsMessage | MalformedFrame:
        """Say nothing about the bytes beyond which stub was reached."""
        return IcsMessage(
            protocol=self.name,
            source=frame.source,
            timestamp=frame.timestamp,
            src=frame.src,
            dst=frame.dst,
            direction=Direction.UNKNOWN,
        )


class _Port502Stub(_PayloadStub):
    """A later dissector that would take port 502 if it were ever asked."""

    def __init__(self) -> None:
        """Name itself so a result makes clear which dissector produced it."""
        super().__init__("not-modbus", None)

    def claims(self, frame: RawFrame) -> bool:
        """Claim the Modbus port, exactly as a careless new dissector would."""
        return MODBUS_PORT in (frame.src.port, frame.dst.port)


class TestClaimOrder:
    def test_a_declining_dissector_falls_through_to_the_next(self) -> None:
        registry = DissectorRegistry([_PayloadStub("even", 0), _PayloadStub("either", None)])
        even = registry.dispatch(make_frame(b"\x02"))
        odd = registry.dispatch(make_frame(b"\x01"))
        assert even.protocol == "even"
        assert odd.protocol == "either"

    def test_a_dissector_that_claims_nothing_leaves_the_frame_unparsed(self) -> None:
        registry = DissectorRegistry([_PayloadStub("even", 0)])
        assert isinstance(registry.dispatch(make_frame(b"\x01")), UnparsedMessage)

    def test_modbus_registered_first_keeps_port_502(self) -> None:
        registry = DissectorRegistry([ModbusDissector(), _Port502Stub()])
        result = registry.dispatch(make_frame(b"\x00\x01"))
        assert isinstance(result, MalformedFrame)
        assert result.protocol == MODBUS_PROTOCOL

    def test_the_same_pair_the_other_way_round_shows_the_order_decided_it(self) -> None:
        # Without this, the test above would pass even if registration order were ignored.
        registry = DissectorRegistry([_Port502Stub(), ModbusDissector()])
        assert registry.dispatch(make_frame(b"\x00\x01")).protocol == "not-modbus"

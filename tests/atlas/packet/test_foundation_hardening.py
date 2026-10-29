"""The foundation refuses rather than guesses. ADR 0345.

Two halves. The seeded corpus (seed 20261029) holds the reassembler to the four claims
ADR 0345 names: nothing raises, a delivered slice is a prefix of the in-order bytes, no
cap is exceeded, and the corpus finishes inside its budget. The framing tests hold
`ContiguousStream` to the rule that makes those caps worth having, which is that a length
a header declares is checked before a single octet is removed, and a check that fails
leaves the header where it was for every later caller to find.
"""

import random
import time

from phos.atlas.packet import (
    MAX_BUFFERED_BYTES_PER_FLOW,
    MAX_CONCURRENT_FLOWS,
    MAX_OUT_OF_ORDER_SEGMENTS,
    ContiguousStream,
    DeliveredOctets,
    FlowKey,
    FlowRefusal,
    Reassembler,
    TcpSegment,
)
from phos.atlas.packet.reassembly import FLOW_CAP, PDU_LENGTH, SEGMENT_TOO_LONG

FUZZ_SEED = 20261029
STREAM_KEY = FlowKey("10.2.0.1", 3000, "10.2.0.2", 4000)
LISTS = 2000
BUDGET_SECONDS = 30.0
_MOD = 0x100000000


class _FlowWatch:
    """Checks one flow against the prefix claim without copying the reassembler."""

    def __init__(self) -> None:
        self.dead = False
        self.origin: int | None = None
        self.covered: dict[int, int] = {}
        self.delivered = bytearray()

    def accept(self, seq: int, payload: bytes, data: bytes) -> None:
        """Record an accepted segment and require ``data`` to be the new in-order prefix."""
        if self.origin is None and payload:
            self.origin = seq
        for offset, octet in enumerate(payload):
            position = (seq + offset) & 0xFFFFFFFF
            assert position not in self.covered
            self.covered[position] = octet
        self.delivered.extend(data)
        assert bytes(self.delivered) == self._contiguous()

    def _contiguous(self) -> bytes:
        if self.origin is None:
            return b""
        out = bytearray()
        position = self.origin
        while position in self.covered and len(out) <= len(self.delivered):
            out.append(self.covered[position])
            position = (position + 1) & 0xFFFFFFFF
            if len(out) > _MOD:
                break
        return bytes(out)


def test_fuzz_never_raises_and_stays_inside_the_caps() -> None:
    """Two thousand random segment lists stay inside the caps and finish in time."""
    rng = random.Random(FUZZ_SEED)
    started = time.monotonic()
    for _list in range(LISTS):
        machine = Reassembler()
        watches: dict[FlowKey, _FlowWatch] = {}
        key = FlowKey("10.1.0.1", 1000, "10.1.0.2", 2000)
        seq = rng.randrange(_MOD)
        for _segment in range(rng.randint(1, 30)):
            kind = rng.randrange(10)
            if kind == 0:
                payload = b"Q" * (65536 + rng.randint(0, 100))
            else:
                payload = bytes(rng.getrandbits(8) for _ in range(rng.randint(0, 40)))
            if kind == 1:
                seq = (seq - rng.randint(1, 8)) & 0xFFFFFFFF
            elif kind == 2:
                seq = (seq + rng.randint(2, 50)) & 0xFFFFFFFF
            _push(machine, watches, key, seq, payload)
            if kind not in (0, 1) and payload and not watches[key].dead:
                seq = (seq + len(payload)) & 0xFFFFFFFF
        extra = FlowKey("10.9.0.1", rng.randint(1, 500), "10.9.0.2", 9)
        _push(machine, watches, extra, 0, b"z")
        assert machine.flow_count <= MAX_CONCURRENT_FLOWS
    assert time.monotonic() - started < BUDGET_SECONDS


def _push(
    machine: Reassembler,
    watches: dict[FlowKey, _FlowWatch],
    key: FlowKey,
    seq: int,
    payload: bytes,
) -> None:
    watch = watches.setdefault(key, _FlowWatch())
    result = machine.push(TcpSegment(key, seq, payload))
    assert isinstance(result, DeliveredOctets | FlowRefusal)
    assert machine.flow_count <= MAX_CONCURRENT_FLOWS
    assert machine.buffered_octets(key) <= MAX_BUFFERED_BYTES_PER_FLOW
    assert machine.out_of_order_count(key) <= MAX_OUT_OF_ORDER_SEGMENTS
    if watch.dead:
        assert isinstance(result, FlowRefusal)
        return
    if isinstance(result, FlowRefusal):
        if result.reason not in (SEGMENT_TOO_LONG, FLOW_CAP):
            watch.dead = True
        return
    watch.accept(seq, payload, result.data)


class TestTheStreamChecksBeforeItConsumes:
    """A declared length is checked first, and a failed check consumes nothing."""

    def test_a_header_larger_than_the_cap_is_refused_without_asking_for_a_length(self) -> None:
        stream = ContiguousStream(STREAM_KEY)

        def never(_header: bytes) -> int:
            raise AssertionError("length_of was called for an unusable header size")

        refused = stream.take_pdu(MAX_BUFFERED_BYTES_PER_FLOW + 1, never)
        assert isinstance(refused, FlowRefusal)
        assert refused.reason == PDU_LENGTH

    def test_a_header_of_no_octets_is_refused(self) -> None:
        stream = ContiguousStream(STREAM_KEY)
        refused = stream.take_pdu(0, lambda _header: 4)
        assert isinstance(refused, FlowRefusal)
        assert refused.reason == PDU_LENGTH

    def test_one_refusal_is_handed_back_to_every_later_caller(self) -> None:
        stream = ContiguousStream(STREAM_KEY)
        assert stream.extend(b"\x00\x01AB") is None
        first = stream.take_pdu(2, lambda _header: 1)
        assert isinstance(first, FlowRefusal)
        assert stream.take_pdu(2, lambda _header: 4) is first
        assert stream.extend(b"CD") is first

    def test_a_negative_read_is_refused(self) -> None:
        stream = ContiguousStream(STREAM_KEY)
        refused = stream.take(-1)
        assert isinstance(refused, FlowRefusal)
        assert refused.reason == PDU_LENGTH

    def test_a_pdu_whose_body_has_not_arrived_is_waited_for(self) -> None:
        stream = ContiguousStream(STREAM_KEY)
        assert stream.extend(b"\x00\x06WX") is None
        assert stream.take_pdu(2, lambda header: int.from_bytes(header, "big")) is None
        assert stream.extend(b"YZ") is None
        assert stream.take_pdu(2, lambda header: int.from_bytes(header, "big")) == b"\x00\x06WXYZ"

"""The hardening suite: what happens when the bytes are chosen to break the parser.

Everything else in this package tests that the adapter understands well-formed traffic. This
module tests the property the adapter actually has to have in production, which is that no input
whatsoever gets it to misbehave. A packet parser in a security product sits at the end of a wire
an attacker controls; if it can be made to crash, hang, read past a buffer or allocate without
bound, it is a liability rather than a sensor.

Four claims are made here, and each is measured rather than asserted by inspection:

1. **It never raises.** Every input produces a `ModbusMessage` or a `MalformedFrame` — including
   thousands of random and mutated ones. This subsumes out-of-bounds *indexing*, which in Python
   is an `IndexError`.
2. **It never reads out of bounds silently.** An out-of-range *slice* in Python is quiet, so
   "no exception" is not enough on its own. Every decoded message is therefore checked against its
   own field bounds: a decode that ran off the end of a buffer or misread a field width produces a
   value outside the protocol's range, and `ModbusMessage`'s validation turns that into a loud
   `ValidationError` — which claim 1 would catch. The two claims interlock deliberately.
3. **It never allocates without bound.** The MBAP length cap runs before any count field is used
   to size anything, so the largest structure any frame can induce is 2,000 coil bits. Asserted on
   every decoded message.
4. **It always terminates.** The parser contains no unbounded loop — every loop is over a
   `range` whose bound has already been checked — and the suite completes a large corpus inside a
   generous wall-clock budget.

The corpus is generated from one fixed seed, so a failure here is reproducible exactly
(Constitution §7).
"""

import random
import struct
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from tests.atlas.packet.conftest import (
    CLIENT_PORT,
    LINKTYPE_ETHERNET,
    make_frame,
    modbus_adu,
    pcap_bytes,
    tcp_frame,
)

from phos.atlas.packet import (
    MAX_READ_COILS,
    MAX_REGISTER_VALUE,
    MODBUS_PORT,
    CaptureError,
    CaptureStats,
    DissectorRegistry,
    MalformedFrame,
    MalformedReason,
    ModbusDissector,
    ModbusMessage,
    RawFrame,
    UnparsedMessage,
    dissect_capture,
    read_frames,
)

SEED = 20260814
"""Fixed so a failure is reproducible exactly. Changing it is changing the experiment."""

RANDOM_INPUTS = 2000
"""Purely random payloads on the Modbus port."""

MUTATED_INPUTS = 2000
"""Valid frames with one thing broken — the inputs most likely to slip past a check."""

TIME_BUDGET_SECONDS = 30.0
"""Generous by roughly two orders of magnitude. It can only fail if something truly hangs."""

MAX_MBAP_LENGTH_FIELD = 254
MAX_PDU_BYTES = 253

VALID_PDUS: tuple[bytes, ...] = (
    bytes.fromhex("0300640002"),  # read holding registers request
    bytes.fromhex("0304000A0014"),  # read holding registers response
    bytes.fromhex("0100130025"),  # read coils request
    bytes.fromhex("0103CD6B05"),  # read coils response
    bytes.fromhex("0500ACFF00"),  # write single coil
    bytes.fromhex("0600010003"),  # write single register
    bytes.fromhex("0F0013000A02CD01"),  # write multiple coils request
    bytes.fromhex("100001000204000A0102"),  # write multiple registers request
    bytes.fromhex("1000010002"),  # write multiple registers response
    bytes.fromhex("8302"),  # exception response
    bytes.fromhex("650001"),  # unknown function code
)
"""Well-formed PDUs. The mutation corpus is built by breaking these one way at a time."""


def dissect_payload(
    payload: bytes, src_port: int = CLIENT_PORT, dst_port: int = MODBUS_PORT
) -> object:
    """Run one payload through the dissector as it would arrive on the Modbus port."""
    return ModbusDissector().dissect(make_frame(payload, src_port=src_port, dst_port=dst_port))


def assert_contained(result: object, frame: RawFrame) -> None:
    """Assert one dissection outcome is well-formed, bounded, and traceable.

    This is the whole hardening contract applied to a single result. Claims 2 and 3 live here:
    every numeric field is re-checked against the protocol's range, and the size of anything the
    frame caused to be allocated is bounded.
    """
    assert isinstance(result, ModbusMessage | MalformedFrame), (
        f"dissecting {frame.payload.hex()} produced {type(result).__name__}"
    )
    assert result.source == frame.source, "a result must trace back to the frame it came from"
    assert result.timestamp == frame.timestamp

    if isinstance(result, MalformedFrame):
        assert isinstance(result.reason, MalformedReason)
        assert result.detail, "a refusal with no explanation cannot be audited"
        assert result.payload_length == len(frame.payload)
        assert result.protocol == "modbus"
        return

    assert 0 <= result.function_code <= 0xFF
    assert 0 <= result.unit_id <= 0xFF
    assert 0 <= result.transaction_id <= MAX_REGISTER_VALUE
    assert result.function_name
    assert result.reference_address is None or 0 <= result.reference_address <= MAX_REGISTER_VALUE
    assert result.quantity is None or result.quantity >= 0
    assert result.exception_code is None or 0 <= result.exception_code <= 0xFF
    assert all(0 <= value <= MAX_REGISTER_VALUE for value in result.values)
    assert len(result.values) <= MAX_READ_COILS, "a frame must not induce an unbounded allocation"


def random_payloads(rng: random.Random, count: int) -> Iterator[bytes]:
    """Yield purely random payloads, including empty, tiny, and larger-than-legal ones."""
    for _ in range(count):
        length = rng.choice(
            [
                rng.randint(0, 8),  # around the MBAP header boundary
                rng.randint(0, 32),  # around the small-PDU boundary
                rng.randint(0, 300),  # around the maximum ADU
                rng.randint(0, 70_000),  # far beyond anything legal
            ]
        )
        yield bytes(rng.getrandbits(8) for _ in range(length))


def mutated_payloads(rng: random.Random, count: int) -> Iterator[bytes]:
    """Yield well-formed ADUs with exactly one thing broken.

    Near-miss inputs are the ones that find missing checks: a frame that is wrong in one field is
    far more likely to slip past a bounds test than a frame that is random throughout.
    """
    for _ in range(count):
        adu = bytearray(modbus_adu(rng.choice(VALID_PDUS)))
        mutation = rng.randint(0, 6)

        if mutation == 0:  # flip one bit
            index = rng.randrange(len(adu))
            adu[index] ^= 1 << rng.randint(0, 7)
        elif mutation == 1:  # truncate
            adu = adu[: rng.randrange(len(adu))]
        elif mutation == 2:  # append rubbish
            adu.extend(rng.getrandbits(8) for _ in range(rng.randint(1, 40)))
        elif mutation == 3:  # delete one byte
            del adu[rng.randrange(len(adu))]
        elif mutation == 4:  # lie about the length
            struct.pack_into(">H", adu, 4, rng.randint(0, 0xFFFF))
        elif mutation == 5:  # overwrite one byte
            adu[rng.randrange(len(adu))] = rng.getrandbits(8)
        else:  # pipeline a second ADU into the same segment
            adu.extend(modbus_adu(rng.choice(VALID_PDUS)))

        yield bytes(adu)


class TestNothingEscapes:
    """Claim 1, 2 and 3: over a large generated corpus, on every code path."""

    def test_random_bytes_on_the_modbus_port_never_break_the_parser(self) -> None:
        rng = random.Random(SEED)
        outcomes: dict[str, int] = {"decoded": 0, "refused": 0}

        for payload in random_payloads(rng, RANDOM_INPUTS):
            frame = make_frame(payload, dst_port=MODBUS_PORT)
            result = ModbusDissector().dissect(frame)
            assert_contained(result, frame)
            outcomes["decoded" if isinstance(result, ModbusMessage) else "refused"] += 1

        assert outcomes["decoded"] + outcomes["refused"] == RANDOM_INPUTS
        assert outcomes["refused"] > 0, "random bytes should mostly be refused"

    def test_mutated_valid_frames_never_break_the_parser(self) -> None:
        rng = random.Random(SEED + 1)
        for payload in mutated_payloads(rng, MUTATED_INPUTS):
            frame = make_frame(payload, dst_port=MODBUS_PORT)
            assert_contained(ModbusDissector().dissect(frame), frame)

    def test_the_corpus_exercises_both_outcomes(self) -> None:
        # A fuzz run where everything is refused proves much less than one where valid frames
        # still decode, because a parser that refuses unconditionally would also pass.
        rng = random.Random(SEED + 1)
        decoded = sum(
            isinstance(dissect_payload(payload), ModbusMessage)
            for payload in mutated_payloads(rng, MUTATED_INPUTS)
        )
        assert decoded > 0, "mutation should still leave some frames decodable"

    def test_random_bytes_are_safe_in_both_directions(self) -> None:
        # Response layouts are a separate set of code paths from request layouts.
        rng = random.Random(SEED + 2)
        for payload in random_payloads(rng, 500):
            frame = make_frame(payload, src_port=MODBUS_PORT, dst_port=CLIENT_PORT)
            assert_contained(ModbusDissector().dissect(frame), frame)

    def test_random_bytes_are_safe_with_an_undetermined_direction(self) -> None:
        rng = random.Random(SEED + 3)
        for payload in random_payloads(rng, 500):
            frame = make_frame(payload, src_port=MODBUS_PORT, dst_port=MODBUS_PORT)
            assert_contained(ModbusDissector().dissect(frame), frame)

    def test_the_whole_corpus_terminates_well_inside_its_budget(self) -> None:
        # Claim 4. The parser has no unbounded loop; this is the measurement that says so.
        rng = random.Random(SEED + 4)
        started = time.monotonic()
        for payload in random_payloads(rng, RANDOM_INPUTS):
            dissect_payload(payload)
        for payload in mutated_payloads(rng, MUTATED_INPUTS):
            dissect_payload(payload)
        elapsed = time.monotonic() - started

        assert elapsed < TIME_BUDGET_SECONDS, (
            f"{RANDOM_INPUTS + MUTATED_INPUTS} inputs took {elapsed:.1f}s"
        )


class TestEveryMalformedCategoryIsRecorded:
    """The specific shapes §5.5 names, swept systematically rather than sampled."""

    def test_every_truncation_of_a_valid_adu_is_refused(self) -> None:
        # Not one truncation — every one, at every byte boundary.
        for pdu in VALID_PDUS:
            adu = modbus_adu(pdu)
            for cut in range(len(adu)):
                result = dissect_payload(adu[:cut])
                assert isinstance(result, MalformedFrame), f"{adu[:cut].hex()} decoded"
                assert result.reason in {
                    MalformedReason.SHORT_HEADER,
                    MalformedReason.LENGTH_MISMATCH,
                }

    def test_every_lying_length_field_is_refused(self) -> None:
        pdu = bytes.fromhex("0300640002")
        honest = len(pdu) + 1
        for declared in range(0, 300):
            if declared == honest:
                continue
            result = dissect_payload(modbus_adu(pdu, length=declared))
            assert isinstance(result, MalformedFrame), f"length {declared} decoded"
            assert result.reason in {
                MalformedReason.FIELD_OUT_OF_RANGE,
                MalformedReason.LENGTH_MISMATCH,
                MalformedReason.TRAILING_BYTES,
            }

    def test_an_honest_length_field_still_decodes(self) -> None:
        pdu = bytes.fromhex("0300640002")
        assert isinstance(dissect_payload(modbus_adu(pdu, length=len(pdu) + 1)), ModbusMessage)

    @pytest.mark.parametrize(
        ("function_code", "limit"),
        [(0x01, 2000), (0x02, 2000), (0x03, 125), (0x04, 125)],
    )
    def test_every_oversized_read_quantity_is_refused(self, function_code: int, limit: int) -> None:
        for quantity in (limit + 1, limit + 2, 0x00FF, 0x7FFF, 0xFFFF):
            pdu = bytes([function_code]) + struct.pack(">HH", 0x0064, quantity)
            result = dissect_payload(modbus_adu(pdu))
            if quantity <= limit:
                continue
            assert isinstance(result, MalformedFrame), f"fc {function_code} qty {quantity} decoded"
            assert result.reason is MalformedReason.FIELD_OUT_OF_RANGE

    @pytest.mark.parametrize(
        ("function_code", "limit"),
        [(0x0F, 1968), (0x10, 123)],
    )
    def test_every_oversized_write_quantity_is_refused(
        self, function_code: int, limit: int
    ) -> None:
        for quantity in (limit + 1, 0x0FFF, 0xFFFF):
            pdu = (
                bytes([function_code])
                + struct.pack(">HH", 0x0001, quantity)
                + bytes([4])
                + b"\x00\x01\x00\x02"
            )
            result = dissect_payload(modbus_adu(pdu))
            assert isinstance(result, MalformedFrame)
            assert result.reason is MalformedReason.FIELD_OUT_OF_RANGE

    def test_every_short_body_is_refused_for_every_known_function(self) -> None:
        # For each function, every body strictly shorter than a valid one must be refused rather
        # than read into whatever bytes happen to follow.
        for pdu in VALID_PDUS:
            if pdu[0] & 0x80 or pdu[0] not in range(1, 17):
                continue
            for cut in range(1, len(pdu)):
                result = dissect_payload(modbus_adu(pdu[:cut]))
                assert isinstance(result, MalformedFrame), f"{pdu[:cut].hex()} decoded"
                assert result.reason in {
                    MalformedReason.SHORT_BODY,
                    MalformedReason.INCONSISTENT_COUNT,
                    MalformedReason.FIELD_OUT_OF_RANGE,
                }

    def test_a_byte_count_pointing_past_the_buffer_is_refused(self) -> None:
        for byte_count in (1, 5, 100, 200, 255):
            pdu = bytes([0x03, byte_count]) + b"\x00\x0a"
            result = dissect_payload(modbus_adu(pdu), src_port=MODBUS_PORT, dst_port=CLIENT_PORT)
            if byte_count == 2:
                continue
            assert isinstance(result, MalformedFrame)
            assert result.reason is MalformedReason.SHORT_BODY

    def test_an_oversized_payload_is_refused_without_being_read(self) -> None:
        # 70 KB on port 502. The MBAP cap refuses it on the length field, long before anything
        # sizes an allocation from it.
        result = dissect_payload(b"\x00" * 70_000)
        assert isinstance(result, MalformedFrame)
        assert result.reason is MalformedReason.FIELD_OUT_OF_RANGE

    def test_an_internally_consistent_oversized_adu_is_still_refused(self) -> None:
        # The case random mutation will not find, because it needs three fields to agree: a
        # length field beyond the protocol maximum, a payload that really is that long, and a
        # byte count that matches the data present. Without the MBAP cap this decodes happily
        # into 2,040 coils. The cap is what stops it, so the assertion is on the reason.
        pdu = bytes([0x01, 255]) + bytes(255)
        adu = modbus_adu(pdu)
        assert int.from_bytes(adu[4:6], "big") > MAX_MBAP_LENGTH_FIELD
        assert len(adu) == len(pdu) + 7

        result = dissect_payload(adu, src_port=MODBUS_PORT, dst_port=CLIENT_PORT)
        assert isinstance(result, MalformedFrame)
        assert result.reason is MalformedReason.FIELD_OUT_OF_RANGE

    def test_a_byte_count_beyond_what_a_legal_read_returns_is_refused(self) -> None:
        # A 253-byte PDU has room for a byte count of 251, which would unpack to 2,008 coils —
        # eight past the protocol's own limit. The MBAP cap does not bound this; only a check on
        # the count itself does.
        pdu = bytes([0x01, 251]) + bytes(251)
        assert len(pdu) == MAX_PDU_BYTES

        result = dissect_payload(modbus_adu(pdu), src_port=MODBUS_PORT, dst_port=CLIENT_PORT)
        assert isinstance(result, MalformedFrame)
        assert result.reason is MalformedReason.FIELD_OUT_OF_RANGE

    def test_a_maximum_legal_adu_still_decodes(self) -> None:
        # The boundary the cap sits on must remain usable: 125 registers is a legal read.
        pdu = bytes([0x03, 250]) + bytes(250)
        result = dissect_payload(modbus_adu(pdu), src_port=MODBUS_PORT, dst_port=CLIENT_PORT)
        assert isinstance(result, ModbusMessage)
        assert len(result.values) == 125

    def test_the_largest_allocation_any_frame_can_induce_is_bounded(self) -> None:
        # 250 bytes of coil data is the most a legal ADU can carry: 2,000 bits.
        pdu = bytes([0x01, 250]) + bytes(250)
        result = dissect_payload(modbus_adu(pdu), src_port=MODBUS_PORT, dst_port=CLIENT_PORT)
        assert isinstance(result, ModbusMessage)
        assert len(result.values) == MAX_READ_COILS


class TestTheCaptureLayerIsHardenedToo:
    """Hostile bytes reach the container reader before they reach any dissector."""

    def test_random_file_bytes_never_crash_the_reader(
        self, write_raw: Callable[[bytes, str], Path]
    ) -> None:
        rng = random.Random(SEED + 5)
        for index in range(200):
            data = bytes(rng.getrandbits(8) for _ in range(rng.randint(0, 400)))
            path = write_raw(data, f"fuzz{index}.pcap")
            try:
                list(read_frames(path))
            except CaptureError:
                pass  # the documented outcome for a file that is not a capture

    def test_a_valid_header_with_random_records_never_crashes_the_reader(
        self, write_raw: Callable[[bytes, str], Path]
    ) -> None:
        rng = random.Random(SEED + 6)
        header = struct.pack("<IHHiIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, LINKTYPE_ETHERNET)
        for index in range(200):
            body = bytes(rng.getrandbits(8) for _ in range(rng.randint(0, 500)))
            stats = CaptureStats()
            frames = list(read_frames(write_raw(header + body, f"body{index}.pcap"), stats))

            assert all(isinstance(frame, RawFrame) for frame in frames)
            assert stats.accounts_for_every_frame()

    def test_mutated_frames_inside_a_real_capture_never_crash_the_pipeline(
        self, write_raw: Callable[[bytes, str], Path]
    ) -> None:
        # The end-to-end version: hostile ADUs arriving inside a structurally valid capture.
        rng = random.Random(SEED + 7)
        records = [
            (1700000000 + index, 0, tcp_frame(CLIENT_PORT, MODBUS_PORT, payload))
            for index, payload in enumerate(mutated_payloads(rng, 300))
        ]
        path = write_raw(pcap_bytes(records), "mutated.pcap")

        stats = CaptureStats()
        results = list(dissect_capture(path, DissectorRegistry([ModbusDissector()]), stats))

        assert len(results) == stats.frames_yielded
        assert stats.accounts_for_every_frame()
        assert all(
            isinstance(result, ModbusMessage | MalformedFrame | UnparsedMessage)
            for result in results
        )

    def test_a_capture_whose_frames_are_random_bytes_never_crashes_the_pipeline(
        self, write_raw: Callable[[bytes, str], Path]
    ) -> None:
        rng = random.Random(SEED + 8)
        records = [
            (
                1700000000 + index,
                0,
                bytes(rng.getrandbits(8) for _ in range(rng.randint(0, 120))),
            )
            for index in range(300)
        ]
        path = write_raw(pcap_bytes(records), "randomframes.pcap")

        stats = CaptureStats()
        list(dissect_capture(path, DissectorRegistry([ModbusDissector()]), stats))
        assert stats.frames_read == 300
        assert stats.accounts_for_every_frame()

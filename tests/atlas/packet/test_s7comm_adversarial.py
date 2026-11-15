"""The red team's adversarial suite for the ISO-on-TCP dissector (ADR 0347/0348).

Written by the red team, on a seed the engineer did not use (**990001**), and deliberately not a
re-run of `test_s7comm.py` or `test_s7comm_hardening.py`. This file has one job: try to break the
dissector, and where it cannot, pin the behaviour so a later edit cannot quietly break it. Nothing
here imports the engineer's fixtures or its builders; every octet below is written out or packed
inline, so an edit to a sibling test module cannot change what this file proves.

**Read the failures before reading the passes.** A test in this file that fails is a finding, not
a broken test — the red-team report at `eval_runs/build/lane-g/s7comm/red-team.md` names each one
and the input bytes that produce it. No test here was weakened to go green. Where the module's
declared behaviour and RFC 905 disagree, the test asserts the **RFC**, so it fails until the
engineer decides which of the two is right.

The four hardening claims are re-asserted here on this file's own corpus, because a claim the
engineer proves on their seed is not a claim about the input space:

1. nothing escapes — every input yields a message or a refusal, never an exception;
2. every decoded field is inside the bound `IsoTsapMessage` declares;
3. no structure grows past the caps, measured by the bytes actually present;
4. the corpus finishes inside a wall-clock budget.
"""

from __future__ import annotations

import random
import struct
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Final

import pytest
from tests.atlas.packet.conftest import CLIENT_PORT

from phos.atlas.packet import (
    Direction,
    DissectorRegistry,
    MalformedFrame,
    MalformedReason,
    ModbusDissector,
    RawFrame,
    Transport,
    UnparsedMessage,
)
from phos.atlas.packet.frame import Endpoint, FrameSource
from phos.atlas.packet.s7comm import (
    CR_MAX_OCTETS,
    ISO_TSAP_PORT,
    TPDU_MAX_OCTETS,
    TPKT_MAX_OCTETS,
    TPKT_MIN_OCTETS,
    IsoTsapDissector,
    IsoTsapMessage,
)

SEED: Final = 990001
"""The red team's own seed. NOT 20261105, which ADR 0347 fixes for the engineer's corpus."""

XSDU_MAX_OCTETS: Final = 16
"""Most octets an expedited TSDU may carry, from the RFC rather than from the module.

RFC 1006 §6: *"the TP specification limits the size of an expedited transport service data unit
(XSDU) to 16 octets."* RFC 905 §13.8.5 says the same field "contains an expedited TSDU (1 to 16
octets)". Written out here on purpose: importing the module's own constant would make the test agree
with the code by construction rather than with the standard.
"""

TIME_BUDGET_SECONDS: Final = 30.0
"""Generous by two orders of magnitude; it can only fire if something truly hangs."""

FIXED_INSTANT: Final = datetime(2026, 11, 6, 0, 0, tzinfo=UTC)

MINIMUM_FIXED_PART_LENGTH_INDICATOR: Final[dict[int, int]] = {
    0xE0: 6,  # CR:  LI counts octets 2-7 (RFC 905 §13.3.1)
    0xD0: 6,  # CC:  LI counts octets 2-7 (RFC 905 §13.3.1)
    0x80: 6,  # DR:  LI counts octets 2-7 (RFC 905 §13.5.1, §13.5.3)
    0x70: 4,  # ER:  LI counts octets 2-5 (RFC 905 §13.12.1, §13.12.3)
    0x10: 3,  # ED:  LI counts octets 2-4 (RFC 1006 p.14: code, credit, TPDU-NR/EOT)
    0xF0: 2,  # DT:  LI counts octets 2-3 (RFC 905 §13.7.1 a, class 0/1 normal format)
}
"""The least a length indicator may be for each TPDU that carries a fixed part.

Computed from the structure diagrams in the cited sections, not from the module. The module
enforces this floor for DT only; `TestFixedPartMinimums` is where the gap for DR, ER and ED is
recorded. CR and CC appear here for completeness of the reference, not as a finding — the
module's choice to decode them with the class unset is documented in `_preferred_class`.
"""


# --- builders, inline, so this file depends on no sibling test module -------------------------


def envelope(
    cotp: bytes, *, version: int = 3, reserved: int = 0, declared: int | None = None
) -> bytes:
    """Wrap a COTP part in a TPKT whose length field is honest unless overridden."""
    length = 4 + len(cotp) if declared is None else declared
    return struct.pack(">BBH", version, reserved, length) + cotp


def frame(
    payload: bytes, *, src: int = CLIENT_PORT, dst: int = ISO_TSAP_PORT, index: int = 0
) -> RawFrame:
    """A TCP frame on the registered port, built without the conftest helper."""
    return RawFrame(
        source=FrameSource(capture="/redteam/s7comm.pcap", frame_index=index),
        timestamp=FIXED_INSTANT,
        transport=Transport.TCP,
        src=Endpoint(ip="10.0.0.1", port=src),
        dst=Endpoint(ip="10.0.0.2", port=dst),
        payload=payload,
    )


def dissect(payload: bytes, **kwargs: int) -> IsoTsapMessage | MalformedFrame:
    """Run one payload through a fresh dissector."""
    return IsoTsapDissector().dissect(frame(payload, **kwargs))


def connect(code: int = 0xE0, *, cls: int = 0, params: bytes = b"", li: int | None = None) -> bytes:
    """A CR/CC COTP header with a six-octet fixed part and ``params`` after it."""
    declared = 6 + len(params) if li is None else li
    return bytes([declared, code]) + struct.pack(">HHB", 1, 2, cls << 4) + params


# --- the corpus, on seed 990001 --------------------------------------------------------------


def random_payloads(rng: random.Random, count: int) -> Iterator[bytes]:
    """Purely random payloads sized around every boundary this module defends."""
    for _ in range(count):
        length = rng.choice(
            [rng.randint(0, 4), rng.randint(0, 9), rng.randint(0, 260), rng.randint(0, 70_000)]
        )
        yield bytes(rng.getrandbits(8) for _ in range(length))


def structurally_hostile(rng: random.Random, count: int) -> Iterator[bytes]:
    """Well-formed TPKT/COTP envelopes with deliberately hostile VALUES.

    This is the generator the brief asks for and the engineer's file does not have: the envelope
    is always structurally plausible — version 3, a length that often matches — so the decode is
    driven deep into the COTP and parameter code rather than being turned away at the header.
    """
    boundary_lengths = (0, 1, 4, 5, 6, 7, 8, 9, 65534, 65535)
    for _ in range(count):
        li = rng.choice(
            [
                rng.randrange(0, 12),  # the interesting floor
                rng.randrange(120, 135),  # the CR bound and just past it
                rng.randrange(0, 256),  # the whole field
            ]
        )
        code = rng.choice([0xE0, 0xD0, 0x80, 0xF0, 0x70, 0x10, rng.getrandbits(8)])
        if rng.random() < 0.5:
            code = (code & 0xF0) | rng.randrange(16)  # exercise the credit nibble
        body_length = max(0, li - 1) if rng.random() < 0.8 else rng.randrange(0, 260)
        body = bytes(rng.getrandbits(8) for _ in range(body_length))
        user_data = bytes(rng.getrandbits(8) for _ in range(rng.choice([0, 0, 1, 7, 100])))
        cotp = bytes([li, code]) + body + user_data
        honest = 4 + len(cotp)
        declared = rng.choice([*boundary_lengths, honest, max(0, honest - 1), honest + 1])
        yield envelope(cotp, reserved=rng.getrandbits(8), declared=declared & 0xFFFF)


def assert_contained(result: IsoTsapMessage | MalformedFrame, source: RawFrame) -> None:
    """The hardening contract, applied to one outcome: typed, bounded, traceable, never S7."""
    assert isinstance(result, IsoTsapMessage | MalformedFrame), (
        f"dissecting {source.payload.hex()} produced {type(result).__name__}"
    )
    assert result.source == source.source
    assert result.timestamp == source.timestamp
    assert result.src == source.src
    assert result.dst == source.dst
    assert result.protocol == "iso-tsap", "the lane never reports s7comm"

    if isinstance(result, MalformedFrame):
        assert isinstance(result.reason, MalformedReason)
        assert result.detail, "a refusal with no explanation cannot be audited"
        assert result.payload_length == len(source.payload)
        return

    assert result.tpkt_version == 3
    assert 0 <= result.reserved_octet <= 0xFF
    assert TPKT_MIN_OCTETS <= result.tpkt_length <= TPKT_MAX_OCTETS
    assert result.tpkt_length == len(source.payload)
    assert 0 <= result.cotp_code <= 0xFF
    assert result.message_type
    assert result.eot is None or isinstance(result.eot, bool)
    assert result.tpdu_nr is None or 0 <= result.tpdu_nr <= 0x7F
    assert result.cotp_class is None or 0 <= result.cotp_class <= 0x0F
    assert result.calling_tsap is None or len(result.calling_tsap) <= 255
    assert result.called_tsap is None or len(result.called_tsap) <= 255
    assert 0 <= result.user_data_length <= TPDU_MAX_OCTETS


# --- 1. the four hardening claims, on this file's seed and generator --------------------------


class TestNothingEscapesOnSeed990001:
    """Claims 1, 2 and 3, over a corpus this file generates and the engineer never saw."""

    def test_random_bytes_never_break_the_parser(self) -> None:
        rng = random.Random(SEED)
        seen: dict[str, int] = {"decoded": 0, "refused": 0}
        for payload in random_payloads(rng, 2000):
            source = frame(payload)
            result = IsoTsapDissector().dissect(source)
            assert_contained(result, source)
            seen["decoded" if isinstance(result, IsoTsapMessage) else "refused"] += 1
        assert sum(seen.values()) == 2000
        assert seen["refused"] > 0

    def test_structurally_hostile_envelopes_never_break_the_parser(self) -> None:
        rng = random.Random(SEED + 1)
        seen: dict[str, int] = {"decoded": 0, "refused": 0}
        for payload in structurally_hostile(rng, 4000):
            source = frame(payload)
            result = IsoTsapDissector().dissect(source)
            assert_contained(result, source)
            seen["decoded" if isinstance(result, IsoTsapMessage) else "refused"] += 1
        # Both outcomes must occur, or the generator proves only that one branch works.
        assert seen["decoded"] > 0, "a corpus that only refuses proves nothing about decoding"
        assert seen["refused"] > 0, "a corpus that only decodes proves nothing about refusing"

    def test_mutated_valid_envelopes_never_break_the_parser(self) -> None:
        rng = random.Random(SEED + 2)
        bases = (
            envelope(bytes([2, 0xF0, 0x80])),
            envelope(bytes([2, 0xF0, 0x00]) + bytes.fromhex("320100000500000e0000")),
            envelope(connect(params=b"\xc1\x02\x01\x00\xc2\x02\x01\x02")),
            envelope(connect(0xD0, cls=4, params=b"\xc0\x01\x0b")),
            envelope(bytes([5, 0x80]) + struct.pack(">HHB", 2, 1, 0)),
            envelope(bytes([4, 0x70]) + struct.pack(">HB", 1, 0)),
            envelope(bytes([3, 0x10, 0x00, 0x80]) + b"\xaa"),
        )
        for _ in range(3000):
            mutated = bytearray(rng.choice(bases))
            for _ in range(rng.randrange(0, 3)):
                if not mutated:
                    break
                match rng.randrange(5):
                    case 0:
                        mutated[rng.randrange(len(mutated))] ^= 1 << rng.randrange(8)
                    case 1:
                        mutated[rng.randrange(len(mutated))] = rng.getrandbits(8)
                    case 2:
                        mutated = mutated[: rng.randrange(len(mutated))]
                    case 3:
                        mutated.extend(rng.getrandbits(8) for _ in range(rng.randrange(1, 8)))
                    case _:
                        del mutated[rng.randrange(len(mutated))]
            payload = bytes(mutated)
            source = frame(payload)
            assert_contained(IsoTsapDissector().dissect(source), source)

    def test_the_corpus_terminates_inside_its_budget(self) -> None:
        started = time.monotonic()
        rng = random.Random(SEED + 3)
        for payload in random_payloads(rng, 2000):
            dissect(payload)
        for payload in structurally_hostile(rng, 4000):
            dissect(payload)
        elapsed = time.monotonic() - started
        assert elapsed < TIME_BUDGET_SECONDS, f"6,000 hostile inputs took {elapsed:.1f}s"


# --- 2. the parameter parser, attacked directly ----------------------------------------------


class TestTheParameterParser:
    """`_decode_parameters` walks [code][length][value] inside the declared header.

    Every case here asserts the reason the *declaration* names — `INCONSISTENT_COUNT` for a
    parameter that overruns the header it lives in — so a silent truncation or an `IndexError`
    is a failure, not an acceptable alternative.
    """

    def test_a_parameter_declaring_255_octets_inside_a_six_octet_header_is_inconsistent(
        self,
    ) -> None:
        # LI 8: fixed part 6, so one octet of variable part. A 0xFF length needs 255.
        cotp = bytes([8, 0xE0]) + struct.pack(">HHB", 1, 2, 0) + bytes([0xC1, 0xFF])
        result = dissect(envelope(cotp))
        assert isinstance(result, MalformedFrame)
        assert result.reason is MalformedReason.INCONSISTENT_COUNT

    def test_a_parameter_code_as_the_last_header_octet_is_inconsistent(self) -> None:
        # LI 7: the header ends one octet after the fixed part, holding a code and no length.
        cotp = bytes([7, 0xE0]) + struct.pack(">HHB", 1, 2, 0) + bytes([0xC1])
        result = dissect(envelope(cotp))
        assert isinstance(result, MalformedFrame)
        assert result.reason is MalformedReason.INCONSISTENT_COUNT

    def test_a_hundred_zero_length_parameters_do_not_loop_or_overrun(self) -> None:
        # 100 x [code][0] = 200 octets of variable part, so the header is 207 octets — past the
        # CR's own 128-octet bound. The refusal must be the CR bound, and it must not be an
        # IndexError from the walk reaching the end of a shorter header.
        params = bytes([0xC1, 0x00]) * 100
        result = dissect(envelope(connect(params=params)))
        assert isinstance(result, MalformedFrame)
        assert result.reason is MalformedReason.FIELD_OUT_OF_RANGE

    def test_a_hundred_zero_length_parameters_on_a_cc_decode(self) -> None:
        # The same shape on a CC has no bound (RFC 905 §13.3 names the CR), so it must decode.
        params = bytes([0xC1, 0x00]) * 100
        result = dissect(envelope(connect(0xD0, params=params)))
        assert isinstance(result, IsoTsapMessage), result
        assert result.message_type == "connection_confirm"
        assert result.calling_tsap == b"", "an empty value is carried as empty, not as None"

    def test_parameters_that_exactly_fill_the_header_decode(self) -> None:
        result = dissect(envelope(connect(params=b"\xc1\x02\x01\x00")))
        assert isinstance(result, IsoTsapMessage), result
        assert result.calling_tsap == b"\x01\x00"

    def test_parameters_that_overrun_by_exactly_one_are_inconsistent(self) -> None:
        result = dissect(envelope(connect(params=b"\xc1\x02\x01\x00\xc1")))
        assert isinstance(result, MalformedFrame)
        assert result.reason is MalformedReason.INCONSISTENT_COUNT

    def test_an_li_that_ends_inside_a_value_is_inconsistent(self) -> None:
        # The header says the 0xC1 value is five octets; only zero remain inside the LI.
        cotp = bytes([8, 0xE0]) + struct.pack(">HHB", 1, 2, 0) + bytes([0xC1, 0x05, 0x01, 0x00])
        result = dissect(envelope(cotp))
        assert isinstance(result, MalformedFrame)
        assert result.reason is MalformedReason.INCONSISTENT_COUNT

    def test_an_li_that_ends_exactly_after_a_value_decodes(self) -> None:
        cotp = bytes([10, 0xE0]) + struct.pack(">HHB", 1, 2, 0) + bytes([0xC1, 0x02, 0x01, 0x00])
        result = dissect(envelope(cotp))
        assert isinstance(result, IsoTsapMessage), result
        assert result.calling_tsap == b"\x01\x00"

    @pytest.mark.parametrize("length", [0, 1, 2, 3, 6, 7, 8, 9, 127, 128, 246, 247, 254, 255])
    def test_every_parameter_length_is_measured_not_trusted(self, length: int) -> None:
        # Exactly one parameter declaring ``length``, inside a header that really holds it, on a
        # CC (so the CR bound does not fire first). The value must come back verbatim.
        params = bytes([0xC1, length]) + bytes(length)
        if 6 + len(params) > 254:
            pytest.skip("does not fit a length indicator")
        result = dissect(envelope(connect(0xD0, params=params)))
        assert isinstance(result, IsoTsapMessage), result
        assert result.calling_tsap == bytes(length)

    def test_a_repeated_code_keeps_the_first_value(self) -> None:
        params = bytes([0xC1, 2, 0x03, 0x01, 0xC1, 2, 0x03, 0x02])
        result = dissect(envelope(connect(params=params)))
        assert isinstance(result, IsoTsapMessage), result
        assert result.calling_tsap == b"\x03\x01", "the wire said two things; the first is kept"

    def test_parameters_are_never_read_from_a_dt(self) -> None:
        # A DT's octets after the fixed part are application data, not parameters.
        body = bytes([0xC1, 0x02, 0x03, 0x01])
        result = dissect(envelope(bytes([2, 0xF0, 0x80]) + body))
        assert isinstance(result, IsoTsapMessage), result
        assert result.calling_tsap is None
        assert result.called_tsap is None
        assert result.user_data_length == len(body)

    def test_a_dt_with_a_large_declared_header_does_not_yield_parameters(self) -> None:
        # The same parameter shape, this time inside a 254-octet declared header on a DT. The
        # intent is unchanged by the length-indicator rule: the parameter walk must never run for
        # a DT, and its octets must never become TSAPs. Two facts establish that and this asserts
        # both, so the test still means something whichever one the reader trusts.
        fake = bytes([0xC1, 0x02, 0x03, 0x01]) + bytes(248)
        payload = envelope(bytes([254, 0xF0, 0x80]) + fake)

        # (i) LI 254 on a DT is refused outright. RFC 905 §13.7.1 a gives the class-0 DT no
        # variable part, so its length indicator is exactly 2 and there is no declared header for
        # a walk to run inside in the first place.
        result = dissect(payload)
        assert isinstance(result, MalformedFrame), (
            f"a DT declaring a 254-octet header decoded as "
            f"{getattr(result, 'message_type', '?')}: {payload.hex()}"
        )
        assert result.reason is MalformedReason.INCONSISTENT_COUNT

        # A refusal is not a message, so it structurally cannot carry a TSAP or a station.
        assert "calling_tsap" not in MalformedFrame.model_fields
        assert "called_tsap" not in MalformedFrame.model_fields

        # (ii) No length indicator opens the walk, because it is gated on the TPDU code and not on
        # the header length. Sweeping all 256 values shows no DT ever yields a TSAP, including
        # LI 2 — the one value that decodes — where the parameter-shaped octets stay user data.
        for length_indicator in range(256):
            cotp = bytes([length_indicator, 0xF0, 0x80]) + fake
            outcome = dissect(envelope(cotp))
            assert isinstance(outcome, IsoTsapMessage | MalformedFrame)
            if isinstance(outcome, IsoTsapMessage):
                assert outcome.calling_tsap is None, f"LI {length_indicator} produced a TSAP"
                assert outcome.called_tsap is None, f"LI {length_indicator} produced a TSAP"
                assert not hasattr(outcome, "station")
                assert not hasattr(outcome, "rack")
                assert not hasattr(outcome, "slot")

        # The LI 2 case is the one worth naming: the octets really are carried, as a count only.
        legal = dissect(envelope(bytes([2, 0xF0, 0x80]) + fake))
        assert isinstance(legal, IsoTsapMessage), legal
        assert legal.user_data_length == len(fake)
        assert legal.calling_tsap is None


# --- 3. off-by-one on the three boundaries that matter ---------------------------------------


class TestTheBoundariesThatMustDecode:
    """A boundary the module refuses by one octet is as wrong as one it overruns by one."""

    def test_a_seven_octet_packet_is_a_legal_dt_with_no_user_data(self) -> None:
        # The module's own docstring: "a 7-octet packet is a legal DT carrying no user data".
        payload = bytes.fromhex("0300000702f080")
        assert len(payload) == TPKT_MIN_OCTETS == 7
        result = dissect(payload)
        assert isinstance(result, IsoTsapMessage), result
        assert result.user_data_length == 0
        assert result.message_type == "data"
        assert result.eot is True

    def test_li_plus_one_equal_to_the_cotp_length_decodes_with_zero_user_data(self) -> None:
        cotp = bytes([2, 0xF0, 0x80])
        assert 2 + 1 == len(cotp)
        result = dissect(envelope(cotp))
        assert isinstance(result, IsoTsapMessage), result
        assert result.user_data_length == 0

    def test_tpkt_length_exactly_equal_to_the_payload_decodes(self) -> None:
        payload = bytes.fromhex("0300000b02f080aabbccdd")
        assert int.from_bytes(payload[2:4], "big") == len(payload)
        result = dissect(payload)
        assert isinstance(result, IsoTsapMessage), result
        assert result.tpkt_length == len(payload)
        assert result.user_data_length == 4

    def test_tpkt_length_one_past_the_payload_is_refused(self) -> None:
        payload = bytes.fromhex("0300000c02f080aabbccdd")
        assert int.from_bytes(payload[2:4], "big") == len(payload) + 1
        result = dissect(payload)
        assert isinstance(result, MalformedFrame)
        assert result.reason is MalformedReason.LENGTH_MISMATCH

    def test_a_tpkt_declaring_seven_with_three_cotp_octets_decodes(self) -> None:
        result = dissect(bytes.fromhex("0300000702f000"))
        assert isinstance(result, IsoTsapMessage), result
        assert result.eot is False, "0x00 has EOT clear, which is False and not None"
        assert result.tpdu_nr == 0

    def test_every_dt_octet_three_value_is_read_as_bit_eight_and_bits_seven_to_one(self) -> None:
        # The exhaustive version of the engineer's asymmetric probe: all 256 octet-3 values.
        for octet in range(0x100):
            result = dissect(envelope(bytes([2, 0xF0, octet])))
            assert isinstance(result, IsoTsapMessage), f"octet 3 = {octet:#04x} refused"
            assert result.eot is bool(octet & 0x80), f"EOT wrong at {octet:#04x}"
            assert result.tpdu_nr == octet & 0x7F, f"TPDU-NR wrong at {octet:#04x}"


# --- 4. truncation at every byte of every fixture --------------------------------------------


DECODABLE_FIXTURES: Final[tuple[bytes, ...]] = (
    envelope(bytes([2, 0xF0, 0x80])),
    envelope(bytes([2, 0xF0, 0x80]) + bytes.fromhex("320100000500000e0000")),
    envelope(connect(params=b"\xc1\x02\x01\x00\xc2\x02\x01\x02")),
    envelope(connect(0xD0, cls=4, params=b"\xc0\x01\x0b")),
    envelope(bytes([6, 0x80]) + struct.pack(">HHB", 2, 1, 0)),
    envelope(bytes([4, 0x70]) + struct.pack(">HB", 1, 0)),
    envelope(bytes([3, 0x10, 0x00, 0x80]) + b"\xaa"),
    envelope(bytes([2, 0x00, 0x00]) + b"\xde\xad"),
)
"""Envelopes that decode at full length. Every prefix of each must be refused."""

REFUSED_AT_FULL_LENGTH_FIXTURES: Final[tuple[bytes, ...]] = (
    bytes.fromhex("0300ffff02f080010203"),  # declares 65535, carries 10
    bytes.fromhex("03000006"),  # declares 6, below the TPKT minimum
)
"""Envelopes that are refused even at full length; every prefix must still be a refusal."""

TRUNCATION_FIXTURES: Final = DECODABLE_FIXTURES + REFUSED_AT_FULL_LENGTH_FIXTURES


class TestTruncationAtEveryByte:
    """All prefixes of all fixtures. Nothing may raise, and nothing may decode."""

    @pytest.mark.parametrize("index", range(len(TRUNCATION_FIXTURES)))
    def test_every_prefix_is_refused_and_traces_to_its_frame(self, index: int) -> None:
        fixture = TRUNCATION_FIXTURES[index]
        for cut in range(len(fixture)):
            source = frame(fixture[:cut], index=cut)
            result = IsoTsapDissector().dissect(source)
            assert_contained(result, source)
            assert isinstance(result, MalformedFrame), (
                f"fixture {index} truncated to {cut} of {len(fixture)} decoded: "
                f"{fixture[:cut].hex()}"
            )

    def test_every_decodable_fixture_decodes_at_full_length(self) -> None:
        # Without this, the sweep above would pass on a dissector that refuses everything.
        for index, fixture in enumerate(DECODABLE_FIXTURES):
            result = dissect(fixture)
            assert isinstance(result, IsoTsapMessage), (
                f"fixture {index} refused: {getattr(result, 'detail', '')} :: {fixture.hex()}"
            )


# --- 5. length lies in both directions, and the 16-bit wrap ----------------------------------


class TestTheLengthLies:
    """The packet length field, swept across its whole range against one honest envelope."""

    def test_the_whole_16_bit_field_is_swept(self) -> None:
        base = bytearray(bytes.fromhex("0300000a02f080010203"))
        assert len(base) == 10
        for declared in range(0x10000):
            struct.pack_into(">H", base, 2, declared)
            result = dissect(bytes(base))
            if declared == 10:
                assert isinstance(result, IsoTsapMessage), f"honest length {declared} refused"
                continue
            assert isinstance(result, MalformedFrame), f"length {declared} decoded"
            assert result.reason is (
                MalformedReason.FIELD_OUT_OF_RANGE
                if declared < TPKT_MIN_OCTETS
                else MalformedReason.LENGTH_MISMATCH
                if declared > 10
                else MalformedReason.TRAILING_BYTES
            ), f"length {declared} gave {result.reason}"

    def test_65536_cannot_be_declared_because_the_field_is_16_bits(self) -> None:
        # The brief lists 65536 as a boundary. It is not representable; what reaches the wire is 0.
        with pytest.raises(struct.error):
            struct.pack(">H", 65536)
        assert struct.pack(">H", 65536 & 0xFFFF) == b"\x00\x00"
        result = dissect(bytes.fromhex("03000000") + bytes(20))
        assert isinstance(result, MalformedFrame)
        assert result.reason is MalformedReason.FIELD_OUT_OF_RANGE

    @pytest.mark.parametrize("declared", [0, 1, 4, 5, 6, 7, 8, 9, 65534, 65535])
    def test_every_declared_length_boundary_is_handled(self, declared: int) -> None:
        payload = struct.pack(">BBH", 3, 0, declared) + bytes.fromhex("02f080") + b"\x01\x02\x03"
        result = dissect(payload)
        if declared == len(payload):
            assert isinstance(result, IsoTsapMessage)
            return
        assert isinstance(result, MalformedFrame)
        assert result.reason is (
            MalformedReason.FIELD_OUT_OF_RANGE
            if declared < TPKT_MIN_OCTETS
            else MalformedReason.LENGTH_MISMATCH
            if declared > len(payload)
            else MalformedReason.TRAILING_BYTES
        )

    def test_an_honest_length_with_a_much_larger_payload_following_is_trailing_bytes(self) -> None:
        payload = bytes.fromhex("0300000a02f080010203") + bytes(65525)
        assert len(payload) == 65535
        result = dissect(payload)
        assert isinstance(result, MalformedFrame)
        assert result.reason is MalformedReason.TRAILING_BYTES
        assert "65525" in result.detail


# --- 6. wrong protocol on the right port, and the reverse ------------------------------------


class TestThePortClaim:
    """The claim rule: TCP with 102 at either end, and nothing else, by port alone."""

    PERFECT: Final = bytes.fromhex("0300000702f080")

    def test_the_registered_port_is_claimed_at_either_end_and_at_both(self) -> None:
        dissector = IsoTsapDissector()
        for src, dst in (
            (CLIENT_PORT, ISO_TSAP_PORT),
            (ISO_TSAP_PORT, CLIENT_PORT),
            (ISO_TSAP_PORT, ISO_TSAP_PORT),
        ):
            assert dissector.claims(frame(self.PERFECT, src=src, dst=dst)), f"{src}->{dst}"

    def test_a_valid_envelope_on_modbus_s_port_is_not_claimed(self) -> None:
        assert not IsoTsapDissector().claims(frame(self.PERFECT, src=CLIENT_PORT, dst=502))

    def test_a_valid_envelope_on_an_arbitrary_port_is_not_claimed(self) -> None:
        assert not IsoTsapDissector().claims(frame(self.PERFECT, src=CLIENT_PORT, dst=4444))

    def test_a_udp_frame_on_102_is_not_claimed(self) -> None:
        udp = RawFrame(
            source=FrameSource(capture="/redteam/udp.pcap", frame_index=0),
            timestamp=FIXED_INSTANT,
            transport=Transport.UDP,
            src=Endpoint(ip="10.0.0.1", port=CLIENT_PORT),
            dst=Endpoint(ip="10.0.0.2", port=ISO_TSAP_PORT),
            payload=self.PERFECT,
        )
        assert not IsoTsapDissector().claims(udp)

    def test_random_bytes_on_102_are_claimed_so_the_refusal_is_a_finding(self) -> None:
        rng = random.Random(SEED + 10)
        for payload in random_payloads(rng, 200):
            assert IsoTsapDissector().claims(frame(payload, dst=ISO_TSAP_PORT))

    def test_a_modbus_adu_on_502_never_reaches_this_dissector(self) -> None:
        registry = DissectorRegistry([ModbusDissector(), IsoTsapDissector()])
        adu = bytes.fromhex("123400000006110300640002")
        result = registry.dispatch(frame(adu, src=CLIENT_PORT, dst=502))
        assert result.protocol == "modbus"
        assert isinstance(result, IsoTsapMessage | MalformedFrame) is False or (
            not isinstance(result, IsoTsapMessage)
        )

    def test_a_malformed_adu_on_502_stays_modbus(self) -> None:
        registry = DissectorRegistry([ModbusDissector(), IsoTsapDissector()])
        result = registry.dispatch(frame(b"\xde\xad\xbe\xef", src=CLIENT_PORT, dst=502))
        assert isinstance(result, MalformedFrame)
        assert result.protocol == "modbus", "this lane must not steal Modbus refusals"

    def test_a_102_frame_on_an_unclaimed_port_is_unparsed(self) -> None:
        registry = DissectorRegistry([IsoTsapDissector()])
        result = registry.dispatch(frame(self.PERFECT, src=5555, dst=4444))
        assert isinstance(result, UnparsedMessage)
        assert result.protocol == "unknown"

    def test_direction_is_unknown_between_two_registered_ports(self) -> None:
        direct = dissect(self.PERFECT)
        assert isinstance(direct, IsoTsapMessage), direct
        assert direct.direction is Direction.REQUEST
        from_server = dissect(self.PERFECT, src=ISO_TSAP_PORT, dst=CLIENT_PORT)
        assert isinstance(from_server, IsoTsapMessage), from_server
        assert from_server.direction is Direction.RESPONSE
        between = dissect(self.PERFECT, src=ISO_TSAP_PORT, dst=ISO_TSAP_PORT)
        assert isinstance(between, IsoTsapMessage), between
        assert between.direction is Direction.UNKNOWN


# --- 7. impossibility probes: the things the module says cannot happen -----------------------


class TestTheImpossibilities:
    """Try to make the module produce what it says it cannot."""

    def test_the_protocol_name_s7comm_is_unrepresentable(self) -> None:
        from pydantic import ValidationError

        message = dissect(bytes.fromhex("0300000702f080"))
        assert isinstance(message, IsoTsapMessage)
        with pytest.raises(ValidationError):
            IsoTsapMessage(**{**message.model_dump(), "protocol": "s7comm"})

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("tpdu_nr", 128),
            ("tpdu_nr", -1),
            ("cotp_class", 16),
            ("cotp_class", -1),
            ("tpkt_version", 256),
            ("reserved_octet", 256),
            ("tpkt_length", 6),
            ("tpkt_length", 65536),
            ("user_data_length", 65532),
            ("user_data_length", -1),
            ("calling_tsap", bytes(256)),
            ("called_tsap", bytes(256)),
        ],
    )
    def test_the_message_model_enforces_every_declared_bound(
        self, field: str, value: object
    ) -> None:
        # Claim 2's tripwire: if the decode ever produced one of these, validation would raise.
        from pydantic import ValidationError

        base = {
            "source": FrameSource(capture="/redteam/x.pcap", frame_index=0),
            "timestamp": FIXED_INSTANT,
            "src": Endpoint(ip="10.0.0.1", port=CLIENT_PORT),
            "dst": Endpoint(ip="10.0.0.2", port=ISO_TSAP_PORT),
            "direction": Direction.REQUEST,
            "tpkt_version": 3,
            "reserved_octet": 0,
            "tpkt_length": 7,
            "cotp_code": 0xF0,
            "message_type": "data",
            "user_data_length": 0,
            field: value,
        }
        with pytest.raises(ValidationError):
            IsoTsapMessage(**base)  # type: ignore[arg-type]

    def test_no_application_field_exists_on_either_outcome(self) -> None:
        forbidden = {
            "act",
            "program_act",
            "station",
            "peer_role",
            "job",
            "opcode",
            "s7",
            "rack",
            "slot",
            "function_code",
            "pdu_reference",
        }
        for model in (IsoTsapMessage, MalformedFrame):
            for name in model.model_fields:
                assert name not in forbidden, f"{model.__name__} exposes {name}"

    def test_every_outcome_reports_iso_tsap_and_the_right_provenance(self) -> None:
        cases = (
            bytes.fromhex("0300000702f080"),
            b"",
            b"\x03",
            bytes.fromhex("0300ffff") + bytes(3),
            bytes.fromhex("0300000a02f080010203") + b"\x00",
            bytes.fromhex("03000008ff000000"),
        )
        for index, payload in enumerate(cases):
            source = frame(payload, index=index)
            result = IsoTsapDissector().dissect(source)
            assert result.protocol == "iso-tsap", f"case {index} reported {result.protocol}"
            assert result.source == source.source
            assert result.timestamp == source.timestamp
            assert result.src == source.src
            assert result.dst == source.dst


# --- 8. resource attacks ---------------------------------------------------------------------


class TestResources:
    """Time, memory, and determinism, measured rather than asserted."""

    def test_a_one_megabyte_payload_is_refused_without_being_copied(self) -> None:
        result = dissect(bytes(1_000_000))
        assert isinstance(result, MalformedFrame)
        assert result.payload_length == 1_000_000

    def test_a_one_megabyte_payload_declaring_the_maximum_is_trailing_bytes(self) -> None:
        payload = struct.pack(">BBH", 3, 0, TPKT_MAX_OCTETS) + bytes(999_996)
        result = dissect(payload)
        assert isinstance(result, MalformedFrame)
        assert result.reason is MalformedReason.TRAILING_BYTES
        assert result.payload_length == 1_000_000

    def test_a_seventy_thousand_octet_payload_past_the_tpkt_maximum(self) -> None:
        payload = struct.pack(">BBH", 3, 0, TPKT_MAX_OCTETS) + bytes(69_996)
        result = dissect(payload)
        assert isinstance(result, MalformedFrame)
        assert result.reason is MalformedReason.TRAILING_BYTES

    def test_a_maximum_size_tpkt_decodes_and_is_contained(self) -> None:
        user_data = bytes(TPKT_MAX_OCTETS - 4 - 3)
        payload = struct.pack(">BBH", 3, 0, TPKT_MAX_OCTETS) + bytes([2, 0xF0, 0x80]) + user_data
        assert len(payload) == TPKT_MAX_OCTETS
        result = dissect(payload)
        assert isinstance(result, IsoTsapMessage), result
        assert result.user_data_length == TPKT_MAX_OCTETS - 7 == 65528

    def test_a_hundred_thousand_envelopes_complete_inside_the_budget(self) -> None:
        payload = bytes.fromhex("0300000702f080")
        dissector = IsoTsapDissector()
        started = time.monotonic()
        for index in range(100_000):
            assert isinstance(dissector.dissect(frame(payload, index=index)), IsoTsapMessage)
        elapsed = time.monotonic() - started
        assert elapsed < TIME_BUDGET_SECONDS, f"100,000 envelopes took {elapsed:.1f}s"

    def test_identical_input_gives_identical_output_over_ten_thousand_calls(self) -> None:
        # No state leak: the same bytes must not decode differently on the ten-thousandth call.
        # The frame index is held constant on purpose — it is provenance, not decoded content, so
        # varying it would compare two different frames rather than the same input twice.
        payload = (
            struct.pack(">BBH", 3, 0, TPKT_MAX_OCTETS)
            + bytes([2, 0xF0, 0x80])
            + bytes(TPKT_MAX_OCTETS - 7)
        )
        dissector = IsoTsapDissector()
        first = dissector.dissect(frame(payload)).model_dump()
        for _ in range(10_000):
            assert dissector.dissect(frame(payload)).model_dump() == first

    def test_alternating_inputs_do_not_perturb_each_other(self) -> None:
        a = bytes.fromhex("0300000702f080")
        b = bytes.fromhex("0300000902f000aabb")
        dissector = IsoTsapDissector()
        reference = (
            dissector.dissect(frame(a)).model_dump(),
            dissector.dissect(frame(b)).model_dump(),
        )
        for _ in range(5_000):
            assert dissector.dissect(frame(a)).model_dump() == reference[0]
            assert dissector.dissect(frame(b)).model_dump() == reference[1]

    def test_two_dissector_instances_are_indistinguishable(self) -> None:
        payload = envelope(connect(params=b"\xc1\x02\x01\x00"))
        first = IsoTsapDissector().dissect(frame(payload))
        second = IsoTsapDissector().dissect(frame(payload))
        assert first == second


# --- 9. the refusals that must not happen ----------------------------------------------------


class TestTheForbiddenRefusals:
    """ADR 0347's four: reserved, class, CR/CC user data, and a third parameter.

    Each must DECODE. A refusal here is a defect against the declaration, not against this file.
    """

    @pytest.mark.parametrize("reserved", range(0x100))
    def test_every_reserved_octet_decodes(self, reserved: int) -> None:
        result = dissect(struct.pack(">BBH", 3, reserved, 7) + bytes([2, 0xF0, 0x80]))
        assert isinstance(result, IsoTsapMessage), f"reserved {reserved:#04x} refused: {result}"
        assert result.reserved_octet == reserved

    @pytest.mark.parametrize("cls", range(16))
    def test_every_preferred_class_decodes(self, cls: int) -> None:
        for code in (0xE0, 0xD0):
            result = dissect(envelope(connect(code, cls=cls)))
            assert isinstance(result, IsoTsapMessage), f"class {cls} refused: {result}"
            assert result.cotp_class == cls

    def test_a_cr_carrying_one_hundred_octets_of_user_data_decodes(self) -> None:
        result = dissect(
            envelope(
                connect(
                    params=b"\xc1\x02\x01\x00",
                )
                + bytes(100)
            )
        )
        assert isinstance(result, IsoTsapMessage), result
        assert result.message_type == "connection_request"
        assert result.user_data_length == 100
        assert result.calling_tsap == b"\x01\x00"

    def test_a_cr_carrying_a_third_parameter_decodes(self) -> None:
        params = b"\xc1\x02\x01\x00" + b"\xc2\x02\x01\x02" + b"\xc0\x01\x0b"
        result = dissect(envelope(connect(params=params)))
        assert isinstance(result, IsoTsapMessage), result
        assert result.calling_tsap == b"\x01\x00"
        assert result.called_tsap == b"\x01\x02"

    def test_a_cr_carrying_twenty_parameters_decodes(self) -> None:
        params = b"".join(bytes([0xC0, 0x01, n & 0xFF]) for n in range(20))
        result = dissect(envelope(connect(params=params)))
        assert isinstance(result, IsoTsapMessage), result

    def test_a_cr_at_the_128_octet_bound_decodes_and_one_past_it_does_not(self) -> None:
        at_bound = (
            bytes([127, 0xE0]) + struct.pack(">HHB", 1, 2, 0) + bytes([0xC1, 119]) + bytes(119)
        )
        assert len(at_bound) == CR_MAX_OCTETS
        assert isinstance(dissect(envelope(at_bound)), IsoTsapMessage)

        over = bytes([128, 0xE0]) + struct.pack(">HHB", 1, 2, 0) + bytes([0xC1, 120]) + bytes(120)
        assert len(over) == CR_MAX_OCTETS + 1
        result = dissect(envelope(over))
        assert isinstance(result, MalformedFrame)
        assert result.reason is MalformedReason.FIELD_OUT_OF_RANGE

    def test_the_128_octet_bound_is_not_applied_to_a_cc(self) -> None:
        # RFC 905 §13.3 names the CR. Applying the bound to a CC would refuse lawful traffic.
        params = bytes([0xC1, 194]) + bytes(194)
        cotp = bytes([6 + len(params), 0xD0]) + struct.pack(">HHB", 1, 2, 0) + params
        assert len(cotp) == 203
        result = dissect(envelope(cotp))
        assert isinstance(result, IsoTsapMessage), result
        assert result.message_type == "connection_confirm"
        assert result.called_tsap is None
        assert result.calling_tsap == bytes(194)


# --- 10. the fixed-part minimums: where this file disagrees with the module ------------------


class TestFixedPartMinimums:
    """The length indicator must be at least as long as the fixed part the TPDU code implies.

    **Round 1** found that DR, ER and ED were decoded whatever their length indicator said, and
    that CR and CC were deliberately excluded from the floor. **Round 2** fixed the first three.
    **Round 3** fixed the last two, so every named TPDU now has a floor:

    | TPDU | floor | citation |
    |---|---|---|
    | DR `0x80` | LI >= 6 | RFC 905 §13.5.1, §13.5.3 |
    | ER `0x70` | LI >= 4 | RFC 905 §13.12.1, §13.12.3 |
    | ED `0x10` | LI >= 3 | RFC 1006 p.14 |
    | CR `0xE0`-`0xEF` | LI >= 6 | RFC 905 §13.3.1, matched by nibble per §13.2.2.2 |
    | CC `0xD0`-`0xDF` | LI >= 6 | RFC 905 §13.4.1, matched by nibble per §13.2.2.2 |
    | DT `0xF0` | LI **exactly** 2 | RFC 905 §13.7.1 a: no variable part in class 0 |

    The assertions below are unchanged from round 1 for DR, ER and ED — they were written against
    the RFCs, not against the module, so a fix that satisfies the RFC satisfies them without an
    edit. That is the point of writing them that way: this class needed no correction when the code
    changed, and would fail again if the floors were removed.

    `TestNoNamedTpduIsLeftUnchecked` at the end of this file is the proof that the family is now
    exhausted rather than merely patched in three more places.
    """

    @pytest.mark.parametrize(("code", "need"), [(0x80, 6), (0x70, 4), (0x10, 3)])
    def test_a_tpdu_shorter_than_its_own_fixed_part_is_not_a_decoded_message(
        self, code: int, need: int
    ) -> None:
        for li in range(1, need):
            payload = envelope(bytes([li, code]) + bytes(20))
            result = dissect(payload)
            assert isinstance(result, MalformedFrame), (
                f"code {code:#04x} with LI {li} decoded as "
                f"{getattr(result, 'message_type', '?')}, but that TPDU's fixed part needs "
                f"LI >= {need} (RFC 905; RFC 1006 p.14 for ED). Bytes: {payload.hex()}"
            )

    def test_a_disconnect_request_with_no_dst_ref_is_not_silently_accepted(self) -> None:
        # RFC 905 §13.5.1: the DR's fixed part is the code (octet 2) + DST-REF (2) + SRC-REF (2)
        # + REASON (1), so octets 2-7. LI counts the header excluding itself (§13.2.1), so the
        # floor is 6 and not the 5 that counting the fields alone suggests. LI 1 declares a header
        # one octet past the length indicator, containing the code and no reference at all.
        payload = bytes.fromhex("030000080180dead")
        result = dissect(payload)
        assert isinstance(result, MalformedFrame), (
            f"a DR with LI 1 and no reference field decoded as "
            f"{getattr(result, 'message_type', '?')}, reporting "
            f"{getattr(result, 'user_data_length', '?')} octets of user data. "
            f"Bytes: {payload.hex()}"
        )

    def test_an_error_tpdu_with_no_reject_cause_is_not_silently_accepted(self) -> None:
        # RFC 905 §13.12.1: ER fixed part is DST-REF (2) + Reject Cause (1), so octets 2-4.
        payload = bytes.fromhex("030000080170dead")
        result = dissect(payload)
        assert isinstance(result, MalformedFrame), (
            f"an ER with LI 1 and no reject cause decoded as "
            f"{getattr(result, 'message_type', '?')}. Bytes: {payload.hex()}"
        )

    def test_an_expedited_data_tpdu_with_no_tpdu_nr_is_not_silently_accepted(self) -> None:
        # RFC 1006 p.14: the ED TPDU is length, code, credit, TPDU-NR/EOT, then user data, so its
        # fixed part reaches octet 4 and LI must be at least 3.
        payload = envelope(bytes([1, 0x10]) + b"\xde\xad")
        result = dissect(payload)
        assert isinstance(result, MalformedFrame), (
            f"an ED with LI 1 and no TPDU-NR/EOT field decoded as "
            f"{getattr(result, 'message_type', '?')}. Bytes: {payload.hex()}"
        )

    @pytest.mark.parametrize("code", [0xE0, 0xD0])
    def test_a_connect_tpdu_with_no_reference_fields_is_refused(self, code: int) -> None:
        # Round 2 pinned this as a decision: a CR/CC whose declared header stopped short of octet 7
        # decoded with the class unset, because the declaration named no refusal for that shape. The
        # floor landed in round 3, so the pin is flipped to the refusal it predicted. The intent is
        # unchanged — a connect TPDU must not be reported as a decoded message when its own
        # reference fields are missing — and it now asserts RFC 905 §13.3.1/§13.4.1 rather than a
        # decision to tolerate.
        payload = envelope(bytes([2, code, 0x00, 0x01]))
        result = dissect(payload)
        assert isinstance(result, MalformedFrame), (
            f"code {code:#04x} with LI 2 and no DST-REF/SRC-REF decoded as "
            f"{getattr(result, 'message_type', '?')} with class "
            f"{getattr(result, 'cotp_class', '?')}. Bytes: {payload.hex()}"
        )
        assert result.reason is MalformedReason.INCONSISTENT_COUNT


# --- 11. the length indicator as a lever on user_data_length ---------------------------------


class TestTheLengthIndicatorGovernsUserData:
    """The lever D2 found, and the refusal that closed it.

    RFC 905 §13.7.1 a gives the class-0 DT a three-octet header — LI, code, TPDU-NR/EOT — and no
    variable part at all, so ``user_data_length`` for a DT is ``tpkt_length - 7`` by construction.

    **Round 1 recorded a defect here:** the module derived the count from the attacker-chosen
    length indicator instead, so the same 22 application octets were reported as 22, 21, 17, 11
    and 0 as the LI varied. **Round 2: fixed by refusal.** A DT now accepts only LI 2
    (`INCONSISTENT_COUNT` otherwise) and the count comes from the verified TPKT length, so the
    lever is gone in both directions. These tests keep the evidence: they would fail again if
    either half of the fix were removed.
    """

    @pytest.mark.parametrize("swallowed", [1, 5, 22])
    def test_a_larger_length_indicator_silently_reduces_the_reported_user_data(
        self, swallowed: int
    ) -> None:
        # Expectation corrected after ADR 0347's judge and engineer resolved a conflict in the fix
        # brief: this test originally asserted the frame DECODES with udl=22, which would report a
        # right number for a TPDU RFC 905 §13.7.1 a says cannot exist. It now asserts the refusal.
        # The application octets are the SAME in every case. Only the length indicator changes,
        # and it is allowed to declare some of those octets to be header. On a class-0 DT there is
        # no variable part at all (RFC 905 §13.7.1 a), so octet 4 is user data by construction and
        # every one of these applications is 22 octets.
        application = bytes.fromhex("320100000500000e00000401120a1002000000000000")
        assert len(application) == 22
        cotp = bytes([2 + swallowed, 0xF0, 0x80]) + application
        payload = envelope(cotp)
        result = dissect(payload)
        assert isinstance(result, MalformedFrame), (
            f"a DT with LI {2 + swallowed} decoded as "
            f"{getattr(result, 'message_type', '?')} reporting "
            f"{getattr(result, 'user_data_length', '?')} of 22 application octets — a class-0 DT "
            f"has no variable part, so its length indicator is exactly 2. Bytes: {payload.hex()}"
        )
        assert result.reason is MalformedReason.INCONSISTENT_COUNT

    def test_a_dt_can_be_made_to_report_zero_user_data_while_carrying_a_whole_s7_job(self) -> None:
        # Expectation corrected after ADR 0347's judge and engineer resolved a conflict in the fix
        # brief: this test originally asserted the frame DECODES with udl=22. It now asserts the
        # refusal, which is the outcome that makes hiding 22 octets impossible rather than merely
        # miscounted.
        application = bytes.fromhex("320100000500000e00000401120a1002000000000000")
        cotp = bytes([2 + len(application), 0xF0, 0x80]) + application
        payload = envelope(cotp)
        result = dissect(payload)
        assert isinstance(result, MalformedFrame), (
            f"22 octets of application data reported as "
            f"{getattr(result, 'user_data_length', '?')}; the length indicator was allowed to hide "
            f"all of it. Bytes: {payload.hex()}"
        )
        assert result.reason is MalformedReason.INCONSISTENT_COUNT


# --- 12. round 2: the D2 fix, attacked from every angle it did not cover --------------------


class TestUserDataLengthCannotLie:
    """D2's lever, re-attacked after the fix that closed it.

    The fix has two halves: a DT's length indicator must be exactly 2, and a DT's
    ``user_data_length`` is derived from the verified TPKT length rather than from the LI. These
    tests attack both halves independently, because either one alone would leave the number
    steerable — the refusal stops a lying LI reaching the count, and the derivation stops the count
    depending on that refusal being enforced somewhere else.
    """

    def test_a_dt_length_indicator_is_two_and_no_other_value(self) -> None:
        for length_indicator in range(256):
            cotp = bytes([length_indicator, 0xF0, 0x80]) + bytes(6)
            result = dissect(envelope(cotp))
            if length_indicator == 2:
                assert isinstance(result, IsoTsapMessage), f"LI 2 refused: {result}"
                continue
            assert isinstance(result, MalformedFrame), (
                f"a DT with LI {length_indicator} decoded as "
                f"{getattr(result, 'message_type', '?')}: {envelope(cotp).hex()}"
            )
            expected = (
                MalformedReason.FIELD_OUT_OF_RANGE
                if length_indicator == 255
                else MalformedReason.INCONSISTENT_COUNT
            )
            assert result.reason is expected, f"LI {length_indicator}: {result.reason}"

    def test_the_count_equals_the_octets_after_the_three_octet_header(self) -> None:
        # Every DT length the TPKT field can express, below the maximum: the count must be exactly
        # the octets after TPKT(4) + COTP(3). Nothing at all may be absorbed into a header.
        for total in range(7, 600):
            cotp = bytes([2, 0xF0, 0x80]) + bytes(total - 7)
            result = dissect(envelope(cotp))
            assert isinstance(result, IsoTsapMessage), f"total {total}: {result}"
            assert result.user_data_length == total - 7, (
                f"TPKT of {total} octets reported {result.user_data_length} application octets"
            )

    def test_padding_after_the_three_octet_header_is_counted_not_hidden(self) -> None:
        # The exact shape D2 used to steal: application octets preceded by a run that an LI could
        # once declare to be header. With LI pinned to 2 there is no header for them to join.
        application = bytes.fromhex("320100000500000e00000401120a1002000000000000")
        for padding in (0, 1, 5, 22, 100):
            cotp = bytes([2, 0xF0, 0x80]) + bytes(padding) + application
            payload = envelope(cotp)
            result = dissect(payload)
            assert isinstance(result, IsoTsapMessage), result
            assert result.user_data_length == padding + len(application), (
                f"{padding} filler + {len(application)} application octets reported as "
                f"{result.user_data_length}. Bytes: {payload.hex()}"
            )

    def test_a_tpkt_longer_than_the_dt_still_cannot_inflate_the_count(self) -> None:
        # A declared length beyond the bytes present is refused before any count is taken, so a
        # sender cannot raise user_data_length without supplying the octets.
        cotp = bytes([2, 0xF0, 0x80]) + bytes(10)
        for declared in (4 + len(cotp) + 1, 4 + len(cotp) + 100, 65535):
            payload = struct.pack(">BBH", 3, 0, declared) + cotp
            result = dissect(payload)
            assert isinstance(result, MalformedFrame), f"declared {declared} decoded"
            assert result.reason is MalformedReason.LENGTH_MISMATCH

    def test_the_maximum_dt_reports_exactly_its_application_octets(self) -> None:
        cotp = bytes([2, 0xF0, 0x80]) + bytes(TPKT_MAX_OCTETS - 7)
        payload = envelope(cotp)
        assert len(payload) == TPKT_MAX_OCTETS
        result = dissect(payload)
        assert isinstance(result, IsoTsapMessage), result
        assert result.user_data_length == TPKT_MAX_OCTETS - 7 == 65528

    def test_no_dt_ever_reports_a_count_that_disagrees_with_its_bytes(self) -> None:
        # The invariant, over a random sample of well-formed DTs of every legal size.
        rng = random.Random(SEED + 60)
        for _ in range(500):
            total = rng.choice([7, 8, 9, 100, 1_500, 5_000, TPKT_MAX_OCTETS])
            cotp = bytes([2, 0xF0, 0x80]) + bytes(rng.getrandbits(8) for _ in range(total - 7))
            payload = envelope(cotp)
            result = dissect(payload)
            assert isinstance(result, IsoTsapMessage), f"total {total}: {result}"
            assert result.user_data_length == len(payload) - 7


# --- 13. round 2: the D1 fix, and the asymmetry it leaves -----------------------------------


class TestFixedPartFloorsAfterTheFix:
    """The minimum floors, confirmed both ways: refused below, decoded at and above.

    Round 1 found that DR, ER and ED were decoded whatever their length indicator said. Round 2's
    module refused them below LI 6, 4 and 3. A floor that refuses *at* its own minimum would be just
    as wrong — it would refuse conformant traffic — so each is checked from both sides.

    **Round 4 removed ED from this class.** Its LI is now *exactly* 3, not a floor of 3, because
    RFC 1006 §6's expedited format has no variable part — so LI 4 and 5 must now refuse, which is
    the opposite of what a floor sweep asserts. ED's exact-value behaviour is checked in
    `TestTheExpeditedDataShape` below; this class covers the four shapes that really do take a
    minimum. The distinction is the round-4 lesson, so the parametrisation is deliberately narrower
    than it was.
    """

    @pytest.mark.parametrize(("code", "need"), [(0x80, 6), (0x70, 4)])
    def test_the_floor_has_four_bands_not_one_monotone_run(self, code: int, need: int) -> None:
        # **Round 5 correction.** This test used to assert that every LI from the floor upward
        # decodes, which is a monotone assumption and was never true: floor+1 leaves a *one-octet*
        # variable part, and RFC 905 §13.2.3 says a variable part, if present, shall contain one or
        # more parameters — a parameter being [code][length][value], two octets minimum. The four
        # bands below are the actual rule, and asserting all four is a stronger test than the old
        # one because it pins the shape of the rule rather than only its lower bound.
        #
        #   LI <  floor      the fixed part does not fit            -> INCONSISTENT_COUNT
        #   LI == floor      no variable part at all, lawful         -> decodes
        #   LI == floor + 1  a one-octet variable part, cannot hold
        #                    a two-octet parameter                   -> INCONSISTENT_COUNT
        #   LI >= floor + 2  room for at least one real parameter    -> decodes
        for length_indicator in range(0, need + 4):
            cotp = bytes([length_indicator, code]) + bytes(max(0, length_indicator - 1)) + bytes(8)
            result = dissect(envelope(cotp))
            band = (
                "below the fixed part"
                if length_indicator < need
                else "exactly at the fixed part, no variable part"
                if length_indicator == need
                else "a one-octet variable part"
                if length_indicator == need + 1
                else "a variable part that can hold a parameter"
            )
            if length_indicator == need or length_indicator >= need + 2:
                assert isinstance(result, IsoTsapMessage), (
                    f"code {code:#04x} with LI {length_indicator} ({band}) refused: {result}"
                )
            else:
                assert isinstance(result, MalformedFrame), (
                    f"code {code:#04x} with LI {length_indicator} ({band}) decoded as "
                    f"{getattr(result, 'message_type', '?')}, floor {need}: "
                    f"{envelope(cotp).hex()}"
                )
                assert result.reason is MalformedReason.INCONSISTENT_COUNT

    @pytest.mark.parametrize(("code", "need"), [(0x80, 6), (0x70, 4)])
    def test_the_dangling_variable_part_refusal_names_its_own_reason(
        self, code: int, need: int
    ) -> None:
        # The floor and the dangling-variable-part rule can both produce INCONSISTENT_COUNT, so the
        # enum alone does not tell an operator which rule fired. Floor+1 must give the variable-part
        # detail, not the fixed-part one — otherwise a reader diagnosing a capture would chase the
        # wrong field.
        cotp = bytes([need + 1, code]) + bytes(need) + bytes(8)
        result = dissect(envelope(cotp))
        assert isinstance(result, MalformedFrame), result
        assert result.reason is MalformedReason.INCONSISTENT_COUNT
        assert "variable part" in result.detail, (
            f"floor+1 should be refused for its one-octet variable part, but the detail says: "
            f"{result.detail!r}"
        )
        assert "13.2.3" in result.detail or "13.2.3" in result.detail.replace("§", "")

    @pytest.mark.parametrize("code", [0x80, 0x70, 0x10])
    def test_the_refusal_detail_names_the_tpdu_and_its_minimum(self, code: int) -> None:
        # A refusal an operator cannot read is not much better than a mis-decode.
        result = dissect(envelope(bytes([1, code]) + bytes(6)))
        assert isinstance(result, MalformedFrame)
        assert result.detail
        assert any(word in result.detail for word in ("fixed part", "length indicator"))

    def test_a_dt_whose_length_indicator_exceeds_two_is_inconsistent(self) -> None:
        for length_indicator in range(3, 255):
            result = dissect(envelope(bytes([length_indicator, 0xF0, 0x80]) + bytes(4)))
            if length_indicator + 1 > len(bytes(4)) + 3:
                continue  # already an overrun; the floor is not what refuses it
            assert isinstance(result, MalformedFrame), f"LI {length_indicator} decoded"
            assert result.reason is MalformedReason.INCONSISTENT_COUNT


class TestTheConnectionTpduFloor:
    """CR and CC: the floor that landed in round 3, and the RFC 1006 permission it must not eat.

    **Round 2 pinned an asymmetry** — CR and CC were the two named TPDUs with no fixed-part floor,
    so a CR with LI 2 decoded and reported the octets that should have been DST-REF and SRC-REF as
    application data. That was recorded here as a decision, with a note saying the pin should
    become a refusal assertion once the floor landed.

    **Round 3: it landed.** `_fixed_part_minimum` now resolves CR and CC **by high nibble**, so
    ``0xE0`` through ``0xEF`` and ``0xD0`` through ``0xDF`` all get the floor of 6 — necessary
    because a CR's low nibble is the credit field (RFC 905 §13.2.2.2), not part of its kind. The
    tests below were flipped from "decodes with the class unset" to "refuses", which is exactly the
    change the round-2 note predicted, and the positive tests that follow are the guard against the
    floor swallowing RFC 1006 §5's initial-user-data permission.
    """

    @pytest.mark.parametrize("code", [0xE0, 0xD0])
    def test_a_connect_tpdu_below_its_fixed_part_is_inconsistent(self, code: int) -> None:
        for length_indicator in (1, 2, 3, 4, 5):
            cotp = bytes([length_indicator, code]) + bytes(max(0, length_indicator - 1)) + bytes(6)
            payload = envelope(cotp)
            result = dissect(payload)
            assert isinstance(result, MalformedFrame), (
                f"code {code:#04x} with LI {length_indicator} decoded as "
                f"{getattr(result, 'message_type', '?')}: {payload.hex()}"
            )
            assert result.reason is MalformedReason.INCONSISTENT_COUNT

    def test_the_cost_is_now_a_refusal_rather_than_a_misreported_count(self) -> None:
        # This is the round-2 pin, flipped exactly as its own note asked. The same seven octets of
        # a genuine CR, read under a truthful and a lying LI: the truthful reading still reports no
        # application data, and the lying one — which used to report four octets of DST-REF and
        # SRC-REF as user data — is now refused instead of miscounted.
        fixed = struct.pack(">HHB", 1, 2, 0)
        honest = dissect(envelope(bytes([6, 0xE0]) + fixed))
        assert isinstance(honest, IsoTsapMessage), honest
        assert honest.cotp_class == 0
        assert honest.user_data_length == 0

        lying = dissect(envelope(bytes([2, 0xE0]) + fixed))
        assert isinstance(lying, MalformedFrame), (
            "a CR whose header stops short of its own DST-REF and SRC-REF must be refused, not "
            f"reported with those octets counted as user data: {lying}"
        )
        assert lying.reason is MalformedReason.INCONSISTENT_COUNT

    @pytest.mark.parametrize("credit", range(16))
    def test_the_floor_matches_cr_and_cc_by_nibble_not_by_whole_octet(self, credit: int) -> None:
        # RFC 905 §13.2.2.2: bits 4-1 of the code are the credit field, so 0xE7 is a CR exactly as
        # 0xE0 is. A floor keyed on the base octet only would let 0xE7 through unchecked.
        for base in (0xE0, 0xD0):
            code = base | credit
            below = dissect(envelope(bytes([5, code]) + bytes(4) + bytes(6)))
            assert isinstance(below, MalformedFrame), (
                f"code {code:#04x} (credit {credit}) with LI 5 decoded: {below}"
            )
            assert below.reason is MalformedReason.INCONSISTENT_COUNT

            at = dissect(envelope(bytes([6, code]) + bytes(5) + bytes(6)))
            assert isinstance(at, IsoTsapMessage), f"code {code:#04x} with LI 6 refused: {at}"
            assert at is not None and 0 <= (at.cotp_class or 0) <= 15

    def test_initial_user_data_at_the_floor_still_decodes_and_is_counted(self) -> None:
        # The guard on RFC 1006 §5. Initial user data uses "the user data fields of these TPDUs",
        # which lie past the header LI measures, so it lengthens a CR and never shortens the header.
        # A floor that refused this would be manufacturing a malformation out of lawful setup.
        for octets in (0, 1, 100, 500, 5_000):
            payload = envelope(bytes([6, 0xE0]) + struct.pack(">HHB", 1, 2, 0) + bytes(octets))
            result = dissect(payload)
            assert isinstance(result, IsoTsapMessage), (
                f"a CR at LI 6 carrying {octets} octets of initial user data was refused: {result}"
            )
            assert result.message_type == "connection_request"
            assert result.cotp_class == 0
            assert result.user_data_length == octets

    def test_a_third_parameter_at_the_floor_still_decodes(self) -> None:
        # The other half of the guard: the floor bounds the header's *minimum*, not its maximum.
        # A CR with LI above 6 and two TSAPs plus a 0xC0 maximum-TPDU-size parameter is lawful.
        params = b"\xc1\x02\x01\x00" + b"\xc2\x02\x01\x02" + b"\xc0\x01\x0b"
        payload = envelope(bytes([6 + len(params), 0xE0]) + struct.pack(">HHB", 1, 2, 0) + params)
        result = dissect(payload)
        assert isinstance(result, IsoTsapMessage), result
        assert result.calling_tsap == b"\x01\x00"
        assert result.called_tsap == b"\x01\x02"
        assert result.user_data_length == 0

    def test_both_together_initial_user_data_after_a_third_parameter(self) -> None:
        params = b"\xc1\x02\x01\x00" + b"\xc2\x02\x01\x02" + b"\xc0\x01\x0b"
        payload = envelope(
            bytes([6 + len(params), 0xE0]) + struct.pack(">HHB", 1, 2, 0) + params + bytes(40)
        )
        result = dissect(payload)
        assert isinstance(result, IsoTsapMessage), result
        assert result.calling_tsap == b"\x01\x00"
        assert result.user_data_length == 40

    def test_a_connection_confirm_at_the_floor_carrying_user_data_decodes(self) -> None:
        # RFC 1006 §5 names the CC as well as the CR, so the permission is symmetric even though
        # the 128-octet bound is not (RFC 905 §13.3 names the CR only).
        payload = envelope(bytes([6, 0xD0]) + struct.pack(">HHB", 1, 2, 0x40) + bytes(20))
        result = dissect(payload)
        assert isinstance(result, IsoTsapMessage), result
        assert result.message_type == "connection_confirm"
        assert result.cotp_class == 4
        assert result.user_data_length == 20

    @pytest.mark.parametrize("code", [0x00, 0x30, 0x50, 0x60, 0xC0, 0xF1, 0xF2, 0xFF])
    def test_an_unnamed_code_has_no_floor_and_is_never_refused_for_its_header(
        self, code: int
    ) -> None:
        # A code this module does not name has no fixed part it can claim to know, so there is
        # nothing to measure the header against. Decoding it as unknown(<n>) is the honest answer.
        for length_indicator in (1, 2, 4):
            cotp = bytes([length_indicator, code]) + bytes(max(0, length_indicator - 1)) + bytes(4)
            result = dissect(envelope(cotp))
            assert isinstance(result, IsoTsapMessage), (
                f"code {code:#04x} LI {length_indicator} refused: {result}"
            )
            assert result.message_type == f"unknown({code})"


# --- 14. round 2: the class-4 DT consequence of pinning LI to 2 -----------------------------


class TestTheClassFourDataTransferConsequence:
    """A class-4 DT is now refused, and that is a change in what the lane can read.

    RFC 905 §13.7.1 gives three DT layouts: **a)** classes 0 and 1,
    ``LI | DT | TPDU-NR/EOT``; **b)** classes 2, 3 and 4,
    ``LI | DT | DST-REF | TPDU-NR/EOT | Variable | User``; **c)** the extended
    form of the same. Only layout **a)** has LI 2.

    Pinning a DT's LI to 2 therefore refuses **every** class-4 DT, which is the layout a connection
    that negotiated class 4 would actually use. Before the fix such a DT decoded — through the
    class-0 layout, wrong by an octet, which is the limitation the module documents and ADR 0348
    accepted. After the fix it is a recorded malformation.

    This is not a defect against the module's own stated position, and RFC 1006 §6 supports the
    class-0-only reading: "only TPDUs formatted for transport class 0 are exchanged". It is a
    *narrowing* that the docstring does not yet describe, because its class-4 paragraph still says
    a class-4 DT "would be wrong by an octet" — which describes a decode that can no longer happen.
    These tests record the narrowing and would catch a future decision either way.
    """

    def test_a_class_four_normal_dt_is_refused(self) -> None:
        # RFC 905 §13.7.1 b: DST-REF (2) then TPDU-NR/EOT, so LI >= 4.
        cotp = bytes([4, 0xF0]) + struct.pack(">H", 0x0001) + bytes([0x80]) + b"\xde\xad"
        result = dissect(envelope(cotp))
        assert isinstance(result, MalformedFrame), (
            f"a class-4 DT decoded as {getattr(result, 'message_type', '?')}: "
            f"{envelope(cotp).hex()}"
        )
        assert result.reason is MalformedReason.INCONSISTENT_COUNT

    def test_a_class_four_extended_dt_is_refused(self) -> None:
        # RFC 905 §13.7.1 c: an eight-octet fixed part, so LI >= 7.
        cotp = bytes([7, 0xF0]) + struct.pack(">H", 1) + bytes([0, 0, 0, 0x80]) + b"\xde\xad"
        result = dissect(envelope(cotp))
        assert isinstance(result, MalformedFrame)
        assert result.reason is MalformedReason.INCONSISTENT_COUNT

    def test_a_connection_still_negotiates_class_four(self) -> None:
        # The narrowing is confined to DT. A CR or CC proposing class 4 still decodes and still
        # records the class — which is what makes the DT refusal worth documenting: the module
        # says yes to the connection and no to every frame on it.
        for code in (0xE0, 0xD0):
            result = dissect(envelope(bytes([6, code]) + struct.pack(">HHB", 1, 2, 0x40)))
            assert isinstance(result, IsoTsapMessage), result
            assert result.cotp_class == 4

    def test_the_documented_class_four_limitation_describes_no_reachable_decode(self) -> None:
        # A pin on the documentation gap, expressed as the thing a reader would try to do: build
        # the class-4 DT the docstring's paragraph is about and see what happens. Nothing decodes,
        # so the paragraph's "would be wrong by an octet" cannot be observed.
        decoded_class_four_dts = []
        for length_indicator in range(0, 32):
            cotp = bytes([length_indicator, 0xF0]) + bytes(max(0, length_indicator - 1)) + b"\xde"
            result = dissect(envelope(cotp))
            if isinstance(result, IsoTsapMessage):
                decoded_class_four_dts.append(length_indicator)
        assert decoded_class_four_dts == [2], (
            "only the class-0 layout decodes; every class-4 DT length indicator is refused. "
            f"Decodable DTs: {decoded_class_four_dts}"
        )


# --- 15. round 3: the D1 family, proved exhausted rather than patched -----------------------


class TestNoNamedTpduIsLeftUnchecked:
    """The D1 family — a *named* TPDU decoded with a fixed part the module does not enforce.

    It produced three findings, each found by sweeping rather than by guessing:

    1. **round 1** — DR, ER and ED were decoded at any length indicator (D1);
    2. **round 2** — CR and CC were excluded from the floor by an argued decision, and the round-2
       report recorded that the D1 *shape* therefore survived on those two;
    3. **round 3** — the CR/CC floor landed, matched by high nibble.

    Three findings in one family means the question "is it exhausted?" has to be answered by a
    sweep over the whole input space the family ranges over, not by checking the three fixes. That
    is what this class does: for every one of the 256 code octets and every one of the 256 length
    indicators, it asks whether the module reports a **named** message, and if it does, whether the
    length indicator it accepted can actually contain that TPDU's fixed part.

    **A code that decodes as ``unknown(<n>)`` is not in the family.** The module claims no fixed
    part for a code RFC 905 does not name, so there is nothing to enforce and nothing to be wrong.
    That distinction is the whole reason the family has a boundary at all.
    """

    #: The length indicator each named TPDU requires, from the RFC structure diagrams.
    #:
    #: **Two entries are minimums and two are exact values, and the difference is load-bearing.**
    #: A TPDU with a *variable part* can legitimately declare any header length at or above its
    #: fixed part: LI 6 is the floor for a CR, but LI 17 is lawful too because the extra octets are
    #: parameters. A TPDU with **no variable part** has exactly one truthful value, and accepting a
    #: larger one lets the sender declare application octets to be header — which is the D2 defect.
    #:
    #: DT and ED are the two no-variable-part shapes on this port, and RFC 905 §13.7.4 and §13.8.4
    #: put nothing in their variable part except a Class-4-only checksum, so in class 0 there is no
    #: lawful content at all. They are exact. **Do not "fix" them back into minimums.**
    #:
    #: | message_type | LI | kind | citation |
    #: |---|---|---|---|
    #: | disconnect_request | >= 6 | minimum | §13.5.1, §13.5.3 |
    #: | error | >= 4 | minimum | §13.12.1, §13.12.3 |
    #: | connection_request | >= 6 | minimum | §13.3.1 |
    #: | connection_confirm | >= 6 | minimum | §13.4.1 |
    #: | data | == 2 | **exact** | §13.7.1 a: no variable part in class 0 |
    #: | expedited_data | == 3 | **exact** | RFC 1006 §6: the DT format with a credit octet |
    MINIMUM: Final[dict[str, int]] = {
        "disconnect_request": 6,  # §13.5.1: code + DST-REF + SRC-REF + REASON, octets 2-7
        "error": 4,  # §13.12.1: code + DST-REF + Reject Cause, octets 2-5
        "connection_request": 6,  # §13.3.1: octets 2-7, then a real variable part
        "connection_confirm": 6,  # §13.4.1: octets 2-7, then a real variable part
    }

    #: The two shapes with no variable part, where the length indicator is a single value.
    EXACT: Final[dict[str, int]] = {
        "data": 2,  # §13.7.1 a: LI | DT | TPDU-NR/EOT | User Data
        "expedited_data": 3,  # RFC 1006 §6: LI | code | credit | TPDU-NR/EOT | User Data
    }

    @property
    def all_expected(self) -> dict[str, tuple[int, str]]:
        """Every named TPDU as ``(value, kind)``, so a test can branch on which rule applies."""
        return {
            **{name: (value, "minimum") for name, value in self.MINIMUM.items()},
            **{name: (value, "exact") for name, value in self.EXACT.items()},
        }

    def test_the_table_covers_every_named_message_the_module_can_emit(self) -> None:
        # The guard on the guard: if the module ever grows a seventh TPDU name, this fails rather
        # than silently leaving the new name out of the sweep below. The probe list includes 3
        # because ED now requires *exactly* 3, so LI 2 and LI 20 never produce one.
        every_named: set[str] = set()
        for code in range(256):
            for length_indicator in (2, 3, 6, 20):
                conn = bytes([length_indicator, code]) + bytes(max(0, length_indicator - 1))
                result = dissect(envelope(conn))
                if isinstance(result, IsoTsapMessage) and not result.message_type.startswith(
                    "unknown("
                ):
                    every_named.add(result.message_type)
        assert every_named == set(self.all_expected), (
            "a named TPDU exists that the family sweep does not know the fixed part of: "
            f"{sorted(every_named ^ set(self.all_expected))}"
        )

    def test_no_named_tpdu_decodes_outside_its_declared_length_indicator_rule(self) -> None:
        # The exhaustive sweep. 65,536 code x LI combinations, each a complete TPDU whose declared
        # header really is as long as the length indicator says, so the length indicator is the
        # only thing that can justify a refusal.
        #
        # It checks both directions of the two rules, because round 4 found that an
        # over-permissive rule is as much a defect as a missing one:
        #   * a minimum shape must not decode below its floor (D1);
        #   * an exact shape must not decode at any value other than its one truthful value (D2).
        offenders: list[str] = []
        for code in range(256):
            for length_indicator in range(256):
                conn = bytes([length_indicator, code]) + bytes(max(0, length_indicator - 1))
                result = dissect(envelope(conn))
                if not isinstance(result, IsoTsapMessage):
                    continue
                if result.message_type.startswith("unknown("):
                    continue
                rule = self.all_expected.get(result.message_type)
                if rule is None:
                    offenders.append(f"code {code:#04x} LI {length_indicator}: no rule")
                    continue
                value, kind = rule
                if kind == "exact" and length_indicator != value:
                    offenders.append(
                        f"code {code:#04x} LI {length_indicator} -> {result.message_type} "
                        f"decoded, but that shape is exact at {value}"
                    )
                elif kind == "minimum" and length_indicator < value:
                    offenders.append(
                        f"code {code:#04x} LI {length_indicator} -> {result.message_type} "
                        f"decoded below its floor of {value}"
                    )
        assert not offenders, f"a named TPDU decoded outside its rule: {offenders[:5]}"

    def test_every_named_tpdu_does_decode_at_its_own_value(self) -> None:
        # The other direction, and the one an over-tight rule would fail: each TPDU must remain
        # readable at its own minimum or exact value, or the rule has started refusing conformant
        # traffic instead of malformed traffic.
        for message_type, (value, _kind) in self.all_expected.items():
            decoded_at_value = False
            for code in range(256):
                conn = bytes([value, code]) + bytes(value - 1)
                result = dissect(envelope(conn))
                if isinstance(result, IsoTsapMessage) and result.message_type == message_type:
                    decoded_at_value = True
                    break
            assert decoded_at_value, f"{message_type} does not decode at its own value of {value}"

    def test_the_two_exact_shapes_are_exactly_two(self) -> None:
        # Round 4's own lesson, pinned: the module names six TPDUs, four have a real variable part
        # and take a minimum, and exactly two (DT and ED) have none and take an exact value. If a
        # third exact shape ever appears, or one of these two becomes a minimum again, this fails.
        assert set(self.EXACT) == {"data", "expedited_data"}
        assert set(self.MINIMUM) == {
            "disconnect_request",
            "error",
            "connection_request",
            "connection_confirm",
        }
        assert not set(self.EXACT) & set(self.MINIMUM)

    def test_no_named_tpdu_without_a_variable_part_accepts_a_larger_indicator(self) -> None:
        # The direct statement of the D2 rule, independent of the table above: for DT and ED,
        # every length indicator other than the truthful one must refuse, with the same wire
        # octets. The two headers are different widths — DT's is LI+code+octet3 (3 octets), ED's
        # is LI+code+credit+octet3 (4) — so each is built with its own prefix, and each carries
        # few enough application octets to stay inside ED's 16-octet XSDU cap.
        application = b"\xde\xad\xbe\xef\x01\x02"
        for code, exact, prefix in ((0xF0, 2, b""), (0x10, 3, b"\x00")):
            for length_indicator in range(256):
                cotp = bytes([length_indicator, code]) + prefix + bytes([0x80]) + application
                result = dissect(envelope(cotp))
                if length_indicator == exact:
                    assert isinstance(result, IsoTsapMessage), (
                        f"code {code:#04x} LI {length_indicator} refused: {result}"
                    )
                    assert result.user_data_length == len(application)
                else:
                    assert isinstance(result, MalformedFrame), (
                        f"code {code:#04x} LI {length_indicator} decoded as "
                        f"{getattr(result, 'message_type', '?')} with "
                        f"udl={getattr(result, 'user_data_length', '?')} — this shape has no "
                        f"variable part, so {exact} is its only truthful length indicator"
                    )

    def test_an_unnamed_code_is_never_in_the_family_at_any_length_indicator(self) -> None:
        # A code the module does not name has no fixed part it can claim, so it must decode at
        # every length indicator without this family applying to it. If one of these ever started
        # arriving as a *named* type, the sweep above would catch it — this pins the other half.
        #
        # The sweep starts at LI 2 because LI 1 makes a 6-octet TPKT, which is below the protocol's
        # own 7-octet minimum and is refused upstream for that reason, not by this family.
        named_codes = {
            0xF0,  # DT
            0x80,  # DR
            0x70,  # ER
            0x10,  # ED
            *range(0xE0, 0xF0),  # CR, all sixteen credit values
            *range(0xD0, 0xE0),  # CC, all sixteen credit values
        }
        for code in range(256):
            if code in named_codes:
                continue
            for length_indicator in (2, 6, 20):
                conn = bytes([length_indicator, code]) + bytes(max(0, length_indicator - 1))
                result = dissect(envelope(conn))
                assert isinstance(result, IsoTsapMessage), (
                    f"unnamed code {code:#04x} refused at LI {length_indicator}: {result}"
                )
                assert result.message_type == f"unknown({code})"

    @pytest.mark.parametrize("code", [0x10, 0x70, 0x80, 0xD0, 0xE0, 0xF0])
    def test_breaking_either_kind_of_rule_would_be_caught(self, code: int) -> None:
        # A mutation check expressed as an assertion rather than a claim. For each named code:
        # below its value must refuse, at its value must decode. Then the two rules diverge, and
        # both directions are asserted because a rule is only pinned if its boundary is:
        #
        #   * an **exact** shape (DT, ED) must refuse at value + 1 — a larger LI declares a
        #     variable part the format does not have (D2);
        #   * a **minimum** shape (CR, CC, DR, ER) must refuse at value + 1 too, for a different
        #     reason — that octet is a one-octet variable part that cannot hold a two-octet
        #     parameter (RFC 905 §13.2.3, round 5) — and must decode again at value + 2.
        #
        # Round 4 added the value + 1 case for exact shapes; round 5 discovered the same case was
        # missing for minimums, which is why this test now asserts it for both kinds.
        name = {
            0x10: "expedited_data",
            0x70: "error",
            0x80: "disconnect_request",
            0xD0: "connection_confirm",
            0xE0: "connection_request",
            0xF0: "data",
        }[code]
        value, kind = self.all_expected[name]

        short = dissect(envelope(bytes([value - 1, code]) + bytes(max(0, value - 2)) + bytes(6)))
        assert isinstance(short, MalformedFrame), (
            f"code {code:#04x} at LI {value - 1} decoded: {short}"
        )
        assert short.reason is MalformedReason.INCONSISTENT_COUNT

        at = dissect(envelope(bytes([value, code]) + bytes(value - 1)))
        assert isinstance(at, IsoTsapMessage), f"code {code:#04x} at LI {value} refused: {at}"

        # value + 1 refuses for BOTH kinds, and the detail distinguishes which rule fired.
        over = dissect(envelope(bytes([value + 1, code]) + bytes(value) + bytes(6)))
        assert isinstance(over, MalformedFrame), (
            f"code {code:#04x} at LI {value + 1} decoded, but {name} is {kind} at {value}: {over}"
        )
        assert over.reason is MalformedReason.INCONSISTENT_COUNT
        assert "variable part" in over.detail
        if kind == "minimum":
            assert "13.2.3" in over.detail
            # And value + 2 is lawful again, which is what separates a minimum from an exact value.
            back = dissect(envelope(bytes([value + 2, code]) + bytes(value + 1) + bytes(6)))
            assert isinstance(back, IsoTsapMessage), (
                f"code {code:#04x} at LI {value + 2} refused — a minimum shape with room for one "
                f"parameter must decode: {back}"
            )


# --- 16. round 4: ED is an exact shape, and its XSDU is capped ------------------------------


class TestTheExpeditedDataShape:
    """ED's length indicator is exactly 3, and its expedited data is capped at 16 octets.

    **Round 4 found that ED was the D2 defect under another name.** With a *floor* of 3 rather than
    an exact value, the same six application octets reported 6, 5, 4 and 1 octets of user data as
    one attacker-chosen octet varied — precisely the lever that made the DT fix a fix. RFC 1006 §6
    gives the expedited TPDU as ``| header length | code | credit | TPDU-NR and EOT | user data |``
    and calls it "nearly identical to the format for the normal data, DT, TPDU", so it has no
    variable part either, and 3 is its only truthful length indicator.

    RFC 1006 §6 also caps the expedited TSDU: "the TP specification limits the size of an expedited
    transport service data unit (XSDU) to 16 octets". RFC 905 §13.8.5 says the field "contains an
    expedited TSDU (1 to 16 octets)".
    """

    APPLICATION: Final = b"\xde\xad\xbe\xef\x01\x02"

    @staticmethod
    def ed(user_data: bytes = b"", *, octet_3: int = 0x80) -> bytes:
        """A well-formed ED: LI 3, code 0x10, credit 0x00, TPDU-NR/EOT, then user data."""
        return bytes([3, 0x10, 0x00, octet_3]) + user_data

    def test_the_length_indicator_is_exactly_three(self) -> None:
        # The steering test, done the only way that isolates the lever: the wire octets after the
        # code are held fixed and only the length indicator changes. Under a floor, several of
        # these decoded with different counts; under an exact value, exactly one does.
        for length_indicator in range(256):
            cotp = bytes([length_indicator, 0x10, 0x00, 0x80]) + self.APPLICATION
            result = dissect(envelope(cotp))
            if length_indicator == 3:
                assert isinstance(result, IsoTsapMessage), f"LI 3 refused: {result}"
                assert result.user_data_length == len(self.APPLICATION)
                continue
            assert isinstance(result, MalformedFrame), (
                f"an ED with LI {length_indicator} decoded as "
                f"{getattr(result, 'message_type', '?')} reporting "
                f"{getattr(result, 'user_data_length', '?')} of {len(self.APPLICATION)} "
                f"application octets. This shape has no variable part, so 3 is its only truthful "
                f"length indicator."
            )
            expected = (
                MalformedReason.FIELD_OUT_OF_RANGE
                if length_indicator == 255
                else MalformedReason.INCONSISTENT_COUNT
            )
            assert result.reason is expected, f"LI {length_indicator}: {result.reason}"

    def test_the_count_equals_the_octets_after_the_four_octet_header(self) -> None:
        # Every ED size from 0 to 16 user octets: the count must be exactly the trailing octets,
        # derived from the TPKT length and never from the length indicator.
        for count in range(XSDU_MAX_OCTETS + 1):
            payload = envelope(self.ed(bytes(count)))
            result = dissect(payload)
            assert isinstance(result, IsoTsapMessage), f"{count} user octets: {result}"
            assert result.user_data_length == count, (
                f"an ED carrying {count} octets reported {result.user_data_length}"
            )
            assert result.user_data_length == len(payload) - 8

    def test_xsdu_cap_boundary(self) -> None:
        # RFC 1006 §6: 16 is the ceiling, so 16 decodes and 17 refuses.
        sixteen = dissect(envelope(self.ed(bytes(16))))
        assert isinstance(sixteen, IsoTsapMessage), sixteen
        assert sixteen.user_data_length == 16

        seventeen = dissect(envelope(self.ed(bytes(17))))
        assert isinstance(seventeen, MalformedFrame)
        assert seventeen.reason is MalformedReason.FIELD_OUT_OF_RANGE

        for count in (18, 100, 5_000):
            result = dissect(envelope(self.ed(bytes(count))))
            assert isinstance(result, MalformedFrame), f"{count} octets decoded"
            assert result.reason is MalformedReason.FIELD_OUT_OF_RANGE

    def test_an_ed_with_no_user_data_decodes(self) -> None:
        # RFC 905 §13.8.5 says the field is 1 to 16 octets, but a zero-octet ED is a shape the
        # module accepts and the declaration never refuses, so it must not start refusing now.
        result = dissect(envelope(self.ed()))
        assert isinstance(result, IsoTsapMessage), result
        assert result.user_data_length == 0
        assert result.message_type == "expedited_data"

    def test_the_xsdu_detail_says_it_is_expedited_only(self) -> None:
        # The refusal has to be readable: an operator who sees this must not conclude that a DT
        # with 5,000 octets is illegal, because a DT's user data is bounded by the TPKT instead.
        result = dissect(envelope(self.ed(bytes(17))))
        assert isinstance(result, MalformedFrame)
        assert "XSDU" in result.detail or "expedited" in result.detail
        assert "16" in result.detail
        assert "DT" in result.detail, "the detail must distinguish ED's cap from a DT's lack of one"

    def test_the_cap_is_not_applied_to_a_dt(self) -> None:
        # The other half of "expedited data only": a DT carrying far more than 16 octets is lawful.
        for count in (0, 16, 17, 1_000, TPKT_MAX_OCTETS - 7):
            cotp = bytes([2, 0xF0, 0x80]) + bytes(count)
            result = dissect(envelope(cotp))
            assert isinstance(result, IsoTsapMessage), f"DT with {count} octets refused: {result}"
            assert result.user_data_length == count

    def test_the_cap_is_not_applied_to_the_other_tpdus(self) -> None:
        # Nor to a CR/CC/DR/ER: none of them carries an XSDU.
        for cotp in (
            bytes([6, 0xE0]) + struct.pack(">HHB", 1, 2, 0) + bytes(100),
            bytes([6, 0xD0]) + struct.pack(">HHB", 1, 2, 0) + bytes(100),
            bytes([6, 0x80]) + struct.pack(">HHB", 2, 1, 0) + bytes(100),
            bytes([4, 0x70]) + struct.pack(">HB", 1, 0) + bytes(100),
        ):
            result = dissect(envelope(cotp))
            assert isinstance(result, IsoTsapMessage), f"{cotp[1]:#04x} refused: {result}"
            assert result.user_data_length == 100

    def test_a_tpkt_longer_than_the_ed_still_cannot_inflate_the_count(self) -> None:
        cotp = self.ed(bytes(4))
        for declared in (4 + len(cotp) + 1, 4 + len(cotp) + 100, 65535):
            payload = struct.pack(">BBH", 3, 0, declared) + cotp
            result = dissect(payload)
            assert isinstance(result, MalformedFrame), f"declared {declared} decoded"
            assert result.reason is MalformedReason.LENGTH_MISMATCH

    def test_padding_before_the_application_octets_is_counted_not_hidden(self) -> None:
        # Padding stays within the 16-octet XSDU: 0/1/5 filler plus the 6 application octets is at
        # most 11, so the cap is not what these cases are testing.
        for padding in (0, 1, 5):
            payload = envelope(self.ed(bytes(padding) + self.APPLICATION))
            result = dissect(payload)
            assert isinstance(result, IsoTsapMessage), result
            assert result.user_data_length == padding + len(self.APPLICATION)

    def test_ed_does_not_get_the_class_0_dt_layout(self) -> None:
        # Pinned since round 1 and unchanged: RFC 1006's ED has a different fixed part from X.224's
        # class-1 ED (spec-audit D4), so nothing is read out of octet 3 into eot/tpdu_nr.
        result = dissect(envelope(self.ed(b"\xaa", octet_3=0xFF)))
        assert isinstance(result, IsoTsapMessage), result
        assert result.eot is None
        assert result.tpdu_nr is None
        assert result.message_type == "expedited_data"


# --- 17. round 4: the variable-part gap this round found ------------------------------------


class TestVariablePartPresence:
    """A DR or ER with a one-octet variable part cannot contain a parameter, and is accepted.

    **This is a finding, not a pin.** RFC 905 §13.2.3: *"The variable part is used to define less
    frequently used parameters. **If the variable part is present, it shall contain one or more
    parameters.**"* A parameter is ``[code][length][value...]`` — at least two octets — so a
    variable part of exactly one octet can contain nothing and is a protocol error by the
    standard's own words.

    The module walks CR and CC's variable part with `_decode_parameters` and refuses a dangling
    code octet there. It does not walk DR's or ER's, so the same shape is accepted:

    - ``0300000c07800002000100e0`` — a DR with LI 7, i.e. a one-octet variable part ``e0``
    - ``0300000a0570000100c1`` — an ER with LI 5, i.e. a one-octet variable part ``c1``

    Both decode as named messages with ``user_data_length=0``. Neither raises, neither overruns,
    and neither is a memory-safety problem: this is a **correctness** gap of the same shape as D1
    (a named TPDU accepted in a form its own standard forbids), one layer further in.

    I am reporting it rather than calling it a lane breaker. The consequence is small — the octets
    are counted as header rather than as data, and both TPDUs are terminal (a disconnect or an
    error), so nothing downstream builds a feature on them. But it is a real gap and the fix is
    cheap: the same two-octet-minimum check `_decode_parameters` already applies, applied to any
    non-empty declared variable part.

    These tests assert the RFC, so they fail until the check lands. That failure is the finding.
    """

    def test_a_dr_with_a_one_octet_variable_part_is_refused(self) -> None:
        # RFC 905 §13.5.1 fixed part is octets 2-7 (LI 6). LI 7 declares one octet of variable
        # part, which §13.2.3 says must contain at least one two-octet parameter.
        payload = bytes.fromhex("0300000c07800002000100e0")
        result = dissect(payload)
        assert isinstance(result, MalformedFrame), (
            "a DR with a one-octet variable part decoded as "
            f"{getattr(result, 'message_type', '?')} "
            f"(udl={getattr(result, 'user_data_length', '?')}). "
            "RFC 905 §13.2.3: if the variable part is present it shall contain one or more "
            f"parameters, and a parameter needs two octets. Bytes: {payload.hex()}"
        )
        assert result.reason is MalformedReason.INCONSISTENT_COUNT

    def test_an_er_with_a_one_octet_variable_part_is_refused(self) -> None:
        # RFC 905 §13.12.1 fixed part is octets 2-5 (LI 4), so LI 5 is a one-octet variable part.
        payload = bytes.fromhex("0300000a0570000100c1")
        result = dissect(payload)
        assert isinstance(result, MalformedFrame), (
            "an ER with a one-octet variable part decoded as "
            f"{getattr(result, 'message_type', '?')}. RFC 905 §13.2.3 requires at least one "
            f"two-octet parameter. Bytes: {payload.hex()}"
        )
        assert result.reason is MalformedReason.INCONSISTENT_COUNT

    def test_the_minimum_two_octet_variable_part_still_decodes(self) -> None:
        # The guard in the other direction: a fix must not refuse a lawful one-parameter variable
        # part. A DR with LI 8 is the fixed part plus ``E0 00`` — the clearing parameter of
        # §13.5.4 a) with a zero-length value.
        dr = dissect(bytes.fromhex("0300000d08800002000100e000"))
        assert isinstance(dr, IsoTsapMessage), dr
        assert dr.message_type == "disconnect_request"
        assert dr.user_data_length == 0

        er = dissect(bytes.fromhex("0300000b0670000100c100"))
        assert isinstance(er, IsoTsapMessage), er
        assert er.message_type == "error"
        assert er.user_data_length == 0

    def test_a_dr_or_er_with_no_variable_part_still_decodes(self) -> None:
        # LI exactly at the fixed part is the no-variable-part case, and is lawful.
        dr = dissect(envelope(bytes([6, 0x80]) + struct.pack(">HHB", 2, 1, 0)))
        assert isinstance(dr, IsoTsapMessage), dr
        assert dr.user_data_length == 0

        er = dissect(envelope(bytes([4, 0x70]) + struct.pack(">HB", 1, 0)))
        assert isinstance(er, IsoTsapMessage), er
        assert er.user_data_length == 0

    def test_the_cr_cc_walk_already_refuses_the_same_shape(self) -> None:
        # The contrast that makes this a gap rather than a style choice: the module already knows
        # how to check this, and applies it to two of the four TPDUs that have a variable part.
        cr = dissect(envelope(bytes([7, 0xE0]) + struct.pack(">HHB", 1, 2, 0) + bytes([0xC1])))
        assert isinstance(cr, MalformedFrame), (
            f"the CR path does not refuse a one-octet variable part either: {cr}"
        )
        assert cr.reason is MalformedReason.INCONSISTENT_COUNT


# --- 18. round 5: the one-octet variable-part rule, and that it is generic ------------------


class TestTheVariablePartRuleIsGeneric:
    """The round-4 finding's fix, verified as a *rule* rather than as two special cases.

    RFC 905 §13.2.3: *"If the variable part is present, it shall contain one or more parameters."*
    A parameter is ``[code][length][value...]`` — two octets minimum — so a declared variable part
    of exactly one octet cannot contain anything and is a protocol error.

    The module implements this once, in `_fixed_part_refusal`, guarded on `_fixed_part_minimum`
    returning a value. CR and CC reach that guard through the nibble branch, so they inherit the
    rule without naming it. This class proves the inheritance rather than assuming it: if a future
    edit special-cased DR and ER, the CR/CC arms below would fail.
    """

    MINIMUM: Final[dict[str, tuple[int, int]]] = {
        "disconnect_request": (0x80, 6),
        "error": (0x70, 4),
        "connection_request": (0xE0, 6),
        "connection_confirm": (0xD0, 6),
    }

    @pytest.mark.parametrize("name", sorted(MINIMUM))
    def test_all_four_minimum_tpdus_have_the_same_four_bands(self, name: str) -> None:
        code, fixed = self.MINIMUM[name]
        bands = {
            fixed - 1: "refuse",
            fixed: "decode",
            fixed + 1: "refuse",
            fixed + 2: "decode",
            fixed + 6: "decode",
        }
        for length_indicator, expected in bands.items():
            cotp = bytes([length_indicator, code]) + bytes(max(0, length_indicator - 1)) + bytes(8)
            result = dissect(envelope(cotp))
            if expected == "decode":
                assert isinstance(result, IsoTsapMessage), (
                    f"{name} at LI {length_indicator} refused: {result}"
                )
            else:
                assert isinstance(result, MalformedFrame), (
                    f"{name} at LI {length_indicator} decoded: {result}"
                )
                assert result.reason is MalformedReason.INCONSISTENT_COUNT

    def test_cr_and_cc_inherit_the_rule_without_naming_it(self) -> None:
        # The generic claim, stated as the thing that would break it: CR/CC go through the nibble
        # branch of `_fixed_part_minimum`, not `_FIXED_PART_MINIMUMS`, so a rule keyed only on the
        # dict would silently miss them.
        for code in (0xE0, 0xD0):
            at = dissect(envelope(bytes([7, code]) + bytes(6) + bytes(8)))
            assert isinstance(at, MalformedFrame), (
                f"code {code:#04x} at LI 7 (a one-octet variable part) decoded: {at}"
            )
            assert at.reason is MalformedReason.INCONSISTENT_COUNT
            assert "13.2.3" in at.detail

    @pytest.mark.parametrize("credit", range(16))
    def test_the_rule_follows_the_credit_nibble_too(self, credit: int) -> None:
        # The floor is resolved by high nibble, so the variable-part rule must follow the same
        # resolution: 0xE7 is a CR and its LI 7 must refuse exactly as 0xE0's does.
        for base in (0xE0, 0xD0):
            code = base | credit
            result = dissect(envelope(bytes([7, code]) + bytes(6) + bytes(8)))
            assert isinstance(result, MalformedFrame), f"code {code:#04x} at LI 7 decoded: {result}"
            assert result.reason is MalformedReason.INCONSISTENT_COUNT

    def test_the_rule_is_vacuous_for_the_two_exact_shapes(self) -> None:
        # DT and ED take the exact-LI branch and return before the minimum branch is reached, so
        # the variable-part rule must never be the reason either of them refuses. Checked on the
        # detail string, not just the enum, because both refusals are INCONSISTENT_COUNT.
        #
        # The sweep starts at 2 and stops before 255 because LI 0 and LI 255 are refused by the
        # generic header checks (a one-octet header, and the value reserved for extensions) before
        # any TPDU-specific rule is consulted — so those two values say nothing about this rule.
        # The body is sized to the declared header so the exact-LI rule is actually reached: a
        # short body would let the header-overrun check fire first and hide the rule under test.
        for length_indicator in range(2, 255):
            dt = dissect(
                envelope(bytes([length_indicator, 0xF0, 0x80]) + bytes(length_indicator - 1))
            )
            if isinstance(dt, MalformedFrame):
                assert "13.2.3" not in dt.detail, (
                    f"a DT at LI {length_indicator} was refused by the variable-part rule, which "
                    f"does not apply to it: {dt.detail}"
                )
                assert "exactly 2" in dt.detail

            ed = dissect(
                envelope(bytes([length_indicator, 0x10, 0x00, 0x80]) + bytes(length_indicator - 1))
            )
            if isinstance(ed, MalformedFrame):
                assert "13.2.3" not in ed.detail, (
                    f"an ED at LI {length_indicator} was refused by the variable-part rule: "
                    f"{ed.detail}"
                )
                assert "exactly 3" in ed.detail

    def test_a_three_octet_variable_part_is_lawful(self) -> None:
        # The rule must refuse exactly one octet and no other odd length: a single parameter with
        # a one-octet value is three octets, and is well formed.
        for code, fixed in ((0x80, 6), (0x70, 4)):
            cotp = bytes([fixed + 3, code]) + bytes(fixed - 1) + bytes([0xC1, 0x01, 0xAA])
            result = dissect(envelope(cotp))
            assert isinstance(result, IsoTsapMessage), (
                f"code {code:#04x} with a 3-octet variable part refused: {result}"
            )

    def test_a_five_octet_variable_part_is_lawful(self) -> None:
        # One parameter with a three-octet value: code + length + 3 = 5 octets.
        parameter = bytes([0xC1, 0x03, 1, 2, 3])
        dr = dissect(envelope(bytes([11, 0x80]) + struct.pack(">HHB", 2, 1, 0) + parameter))
        assert isinstance(dr, IsoTsapMessage), dr
        assert dr.user_data_length == 0

    def test_the_two_refusals_are_distinguishable_by_their_detail(self) -> None:
        # Both below-floor and one-octet-variable-part are INCONSISTENT_COUNT, so an operator
        # reading a capture needs the detail to say which field was wrong.
        below = dissect(envelope(bytes([5, 0x80]) + bytes(4) + bytes(6)))
        assert isinstance(below, MalformedFrame)
        assert "fixed part" in below.detail and "13.2.3" not in below.detail

        dangling = dissect(envelope(bytes([7, 0x80]) + bytes(6) + bytes(6)))
        assert isinstance(dangling, MalformedFrame)
        assert "variable part" in dangling.detail and "13.2.3" in dangling.detail

    def test_the_cr_lawful_setup_cases_still_decode(self) -> None:
        # The regression that matters most for this rule: RFC 1006 §5's permission and a third
        # parameter both lengthen the TPDU legitimately, and neither may be caught by a check
        # aimed at a one-octet variable part.
        for octets in (0, 1, 100, 5_000):
            result = dissect(
                envelope(bytes([6, 0xE0]) + struct.pack(">HHB", 1, 2, 0) + bytes(octets))
            )
            assert isinstance(result, IsoTsapMessage), result
            assert result.user_data_length == octets

        params = b"\xc1\x02\x01\x00" + b"\xc2\x02\x01\x02" + b"\xc0\x01\x0b"
        result = dissect(
            envelope(bytes([6 + len(params), 0xE0]) + struct.pack(">HHB", 1, 2, 0) + params)
        )
        assert isinstance(result, IsoTsapMessage), result
        assert result.calling_tsap == b"\x01\x00"
        assert result.called_tsap == b"\x01\x02"

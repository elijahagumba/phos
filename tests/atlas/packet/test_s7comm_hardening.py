"""The S7comm lane's hardening suite: what happens when the bytes on 102 are chosen to break it.

This is the same four claims `test_hardening.py` makes for Modbus, applied to the ISO-on-TCP
envelope, on the seed ADR 0347 declares. A packet parser in a security product sits at the end of a
wire an attacker controls; if it can be made to crash, hang, read past a buffer or allocate without
bound, it is a liability rather than a sensor.

1. **It never raises.** Every input produces an `IsoTsapMessage` or a `MalformedFrame` — including
   two thousand random payloads and two thousand mutated valid envelopes. This subsumes
   out-of-bounds *indexing*, which in Python is an `IndexError`.
2. **It never reads out of bounds silently.** An out-of-range *slice* in Python is quiet, so "no
   exception" is not enough. Every decoded message is therefore re-checked against its own declared
   bounds: a decode that ran off the end of a buffer or misread a field width produces a value
   outside the range and `IsoTsapMessage`'s validation turns it into a loud `ValidationError`, which
   claim 1 would catch. The two claims interlock deliberately.
3. **It never allocates without bound.** The declared packet length is compared with the bytes
   present and with 65535 before it bounds any slice, so the largest structure any frame can induce
   is bounded by the octets that actually arrived. Asserted on every decoded message.
4. **It always terminates.** Every loop is over a `range` or a cursor bounded by a checked value, so
   the corpus completes inside a declared wall-clock budget.

The corpus is generated from one fixed seed, so a failure here is reproducible exactly
(Constitution §7). **The seed is 20261105 and is written in ADR 0347; changing it is changing the
experiment.**

The envelope fixtures are built here with `struct.pack` from octets written out in this file. They
mirror the shapes in `test_s7comm.py` rather than importing them, so an edit to one file's builder
cannot quietly change what the other file proves — and neither module imports the other.
"""

import random
import struct
import time
from collections.abc import Iterator
from typing import Final

import pytest
from tests.atlas.packet.conftest import CLIENT_PORT, make_frame

from phos.atlas.packet import (
    DissectorRegistry,
    MalformedFrame,
    MalformedReason,
    RawFrame,
    UnparsedMessage,
)
from phos.atlas.packet.s7comm import (
    CR_MAX_OCTETS,
    ISO_TSAP_PORT,
    LI_RESERVED_FOR_EXTENSIONS,
    MAX_LENGTH_INDICATOR,
    TPDU_MAX_OCTETS,
    TPKT_HEADER_LENGTH,
    TPKT_MAX_OCTETS,
    TPKT_MIN_OCTETS,
    IsoTsapDissector,
    IsoTsapMessage,
)

SEED: Final = 20261105
"""Declared in ADR 0347, fixed, and not to be changed. Changing it is changing the experiment."""

FIXED_SEED: Final = SEED
"""Readable alias: the seed is fixed by the declaration, not by this module's preference."""

RANDOM_INPUTS: Final = 2000
"""Purely random payloads on port 102, as the declaration's corpus names."""

MUTATED_INPUTS: Final = 2000
"""Valid envelopes with one thing broken — the inputs most likely to slip past a check."""

TIME_BUDGET_SECONDS: Final = 30.0
"""Generous by roughly two orders of magnitude. It can only fail if something truly hangs."""

OTHER_PORT: Final = 5555
"""A port no dissector in this lane claims, for the non-interference test."""


def envelope(
    cotp: bytes,
    *,
    reserved: int = 0,
    version: int = 3,
    declared: int | None = None,
    trailing: bytes = b"",
) -> bytes:
    """Wrap a COTP part in a TPKT whose length field is honest unless overridden.

    Deriving the declared length from the octets present is what stops this corpus being a corpus of
    typos: only a mutation is allowed to make the header disagree with the payload, which is the
    point of the mutation sweep and not of the fixtures.
    """
    length = TPKT_HEADER_LENGTH + len(cotp) if declared is None else declared
    return struct.pack(">BBH", version, reserved, length) + cotp + trailing


VALID_ENVELOPES: tuple[bytes, ...] = (
    envelope(bytes([2, 0xF0, 0x80])),  # DT, EOT set, no user data
    envelope(bytes([2, 0xF0, 0x00]) + b"\x32\x01\x00"),  # DT with an S7-shaped body
    envelope(bytes([2, 0xF0, 0x00]) + b"\xde\xad"),  # DT, EOT clear
    envelope(bytes([2, 0xF1, 0x80]) + b"\x01\x02", reserved=0xAA),  # DT with ROA, reserved set
    envelope(bytes([6, 0xE0]) + struct.pack(">HHB", 1, 2, 0x00)),  # CR
    envelope(bytes([6, 0xD0]) + struct.pack(">HHB", 1, 2, 0x40) + b"\x00"),  # CC, class 4
    envelope(bytes([6, 0x80]) + struct.pack(">HHB", 1, 2, 0x00)),  # DR, LI 6: both refs + reason
    envelope(bytes([4, 0x70]) + struct.pack(">HB", 1, 0)),  # ER, LI 4: DST-REF + reject cause
    envelope(bytes([3, 0x10, 0x00, 0x80]) + b"\xaa"),  # ED, LI 3: credit + TPDU-NR/EOT
    envelope(bytes([2, 0x00, 0x00]) + b"\x00\x00"),  # unknown TPDU code
    envelope(
        bytes([13, 0xE0]) + struct.pack(">HHB", 1, 2, 0x00) + b"\xc1\x02\x01\x00" + b"\xc2\x01\x01"
    ),  # CR with both TSAPs, the second a one-octet value
    envelope(bytes([6, 0xE0]) + struct.pack(">HHB", 1, 2, 0x00) + b"\xaa\xbb"),  # CR with data
)
"""Well-formed envelopes. The mutation corpus is built by breaking these one way at a time."""


def dissect_payload(
    payload: bytes, *, src_port: int = CLIENT_PORT, dst_port: int = ISO_TSAP_PORT
) -> IsoTsapMessage | MalformedFrame:
    """Run one payload through the dissector as it would arrive on the registered port."""
    return IsoTsapDissector().dissect(make_frame(payload, src_port=src_port, dst_port=dst_port))


def assert_contained(result: IsoTsapMessage | MalformedFrame, frame: RawFrame) -> None:
    """Assert one dissection outcome is well-formed, bounded, and traceable.

    This is the whole hardening contract applied to a single result. Claims 2 and 3 live here:
    every numeric field is re-checked against its declared bound, and the size of anything the
    frame caused to be allocated is bounded by what actually arrived.
    """
    assert isinstance(result, IsoTsapMessage | MalformedFrame), (
        f"dissecting {frame.payload.hex()} produced {type(result).__name__}"
    )
    assert result.source == frame.source, "a result must trace back to the frame it came from"
    assert result.timestamp == frame.timestamp
    assert result.src == frame.src
    assert result.dst == frame.dst
    assert result.protocol == "iso-tsap", "the lane never reports s7comm"

    if isinstance(result, MalformedFrame):
        assert isinstance(result.reason, MalformedReason)
        assert result.detail, "a refusal with no explanation cannot be audited"
        assert result.payload_length == len(frame.payload)
        return

    assert result.tpkt_version == 3, "only version 3 decodes"
    assert 0 <= result.reserved_octet <= 0xFF
    assert TPKT_MIN_OCTETS <= result.tpkt_length <= TPKT_MAX_OCTETS
    assert result.tpkt_length == len(frame.payload), "a decoded length is the bytes present"
    assert 0 <= result.cotp_code <= 0xFF
    assert result.message_type
    assert result.eot is None or isinstance(result.eot, bool)
    assert result.tpdu_nr is None or 0 <= result.tpdu_nr <= 0x7F
    assert result.cotp_class is None or 0 <= result.cotp_class <= 0x0F
    assert result.calling_tsap is None or 0 <= len(result.calling_tsap) <= 255
    assert result.called_tsap is None or 0 <= len(result.called_tsap) <= 255
    assert 0 <= result.user_data_length <= TPDU_MAX_OCTETS
    assert result.user_data_length <= result.tpkt_length, (
        "user data cannot be longer than the packet carrying it"
    )


def random_payloads(rng: random.Random, count: int) -> Iterator[bytes]:
    """Yield purely random payloads, including empty, tiny, and larger-than-legal ones."""
    for _ in range(count):
        length = rng.choice(
            [
                rng.randint(0, 8),  # around the TPKT header and minimum boundary
                rng.randint(0, 64),  # around the small-TPDU boundary
                rng.randint(0, 300),  # around the LI ceiling
                rng.randint(0, 70_000),  # far beyond anything legal
            ]
        )
        yield bytes(rng.getrandbits(8) for _ in range(length))


def mutated_payloads(rng: random.Random, count: int) -> Iterator[bytes]:
    """Yield well-formed envelopes with exactly one thing broken.

    Near-miss inputs are the ones that find missing checks: an envelope wrong in one field is far
    more likely to slip past a bounds test than one that is random throughout. The mutations are
    aimed at the fields this lane's refusals are about — the TPKT length, the version, the length
    indicator, the TPDU code, the reserved octet and the parameter list.
    """
    for _ in range(count):
        envelope = bytearray(rng.choice(VALID_ENVELOPES))
        mutation = rng.randint(0, 9)

        if mutation == 0:  # flip one bit
            index = rng.randrange(len(envelope))
            envelope[index] ^= 1 << rng.randint(0, 7)
        elif mutation == 1:  # truncate
            envelope = envelope[: rng.randrange(len(envelope))]
        elif mutation == 2:  # append rubbish
            envelope.extend(rng.getrandbits(8) for _ in range(rng.randint(1, 40)))
        elif mutation == 3:  # delete one byte
            del envelope[rng.randrange(len(envelope))]
        elif mutation == 4:  # lie about the TPKT length
            struct.pack_into(">H", envelope, 2, rng.randint(0, 0xFFFF))
        elif mutation == 5:  # overwrite one byte
            envelope[rng.randrange(len(envelope))] = rng.getrandbits(8)
        elif mutation == 6:  # rewrite the version octet
            envelope[0] = rng.getrandbits(8)
        elif mutation == 7:  # rewrite the length indicator
            envelope[TPKT_HEADER_LENGTH] = rng.getrandbits(8)
        elif mutation == 8:  # rewrite the TPDU code
            envelope[TPKT_HEADER_LENGTH + 1] = rng.getrandbits(8)
        else:  # pipeline a second envelope into the same segment
            envelope.extend(rng.choice(VALID_ENVELOPES))

        yield bytes(envelope)


class TestNothingEscapes:
    """Claims 1, 2 and 3: over the declared corpus, on every code path."""

    def test_random_bytes_on_the_registered_port_never_break_the_parser(self) -> None:
        rng = random.Random(FIXED_SEED)
        outcomes: dict[str, int] = {"decoded": 0, "refused": 0}

        for payload in random_payloads(rng, RANDOM_INPUTS):
            frame = make_frame(payload, dst_port=ISO_TSAP_PORT)
            result = IsoTsapDissector().dissect(frame)
            assert_contained(result, frame)
            outcomes["decoded" if isinstance(result, IsoTsapMessage) else "refused"] += 1

        assert outcomes["decoded"] + outcomes["refused"] == RANDOM_INPUTS
        assert outcomes["refused"] > 0, "random bytes should mostly be refused"

    def test_mutated_valid_envelopes_never_break_the_parser(self) -> None:
        rng = random.Random(FIXED_SEED + 1)
        for payload in mutated_payloads(rng, MUTATED_INPUTS):
            frame = make_frame(payload, dst_port=ISO_TSAP_PORT)
            assert_contained(IsoTsapDissector().dissect(frame), frame)

    def test_the_corpus_exercises_both_outcomes(self) -> None:
        # A fuzz run where everything is refused proves much less than one where valid envelopes
        # still decode, because a parser that refuses unconditionally would also pass.
        rng = random.Random(FIXED_SEED + 1)
        decoded = 0
        for payload in mutated_payloads(rng, MUTATED_INPUTS):
            if isinstance(dissect_payload(payload), IsoTsapMessage):
                decoded += 1
        assert decoded > 0, "mutation should still leave some frames decodable"
        assert decoded < MUTATED_INPUTS, "and some should be refused"

    def test_both_outcomes_occur_across_the_declared_corpus(self) -> None:
        # The declaration asks that both outcomes occur, because a corpus that refuses everything
        # proves less. It asks it of the *corpus*, not of one branch of it: uniformly random bytes
        # essentially never spell a version 3 and a matching 16-bit length at once, so the random
        # branch is a refusal corpus by construction and the mutated branch is the half that
        # decodes. Claiming otherwise for random bytes would be a claim about luck.
        rng = random.Random(FIXED_SEED)
        random_outcomes = {
            "decoded" if isinstance(dissect_payload(p), IsoTsapMessage) else "refused"
            for p in random_payloads(rng, RANDOM_INPUTS)
        }
        mutated_rng = random.Random(FIXED_SEED + 1)
        mutated_outcomes = {
            "decoded" if isinstance(dissect_payload(p), IsoTsapMessage) else "refused"
            for p in mutated_payloads(mutated_rng, MUTATED_INPUTS)
        }

        assert random_outcomes == {"refused"}, (
            "uniformly random bytes should not be mistaken for envelopes"
        )
        assert mutated_outcomes == {"decoded", "refused"}, (
            "the mutation corpus must produce both outcomes, or it proves only that refusal works"
        )

    def test_random_bytes_are_safe_in_both_directions(self) -> None:
        rng = random.Random(FIXED_SEED + 2)
        for payload in random_payloads(rng, 500):
            frame = make_frame(payload, src_port=ISO_TSAP_PORT, dst_port=CLIENT_PORT)
            assert_contained(IsoTsapDissector().dissect(frame), frame)

    def test_random_bytes_are_safe_when_both_ends_hold_the_port(self) -> None:
        rng = random.Random(FIXED_SEED + 3)
        for payload in random_payloads(rng, 500):
            frame = make_frame(payload, src_port=ISO_TSAP_PORT, dst_port=ISO_TSAP_PORT)
            assert_contained(IsoTsapDissector().dissect(frame), frame)

    def test_the_whole_corpus_terminates_well_inside_its_budget(self) -> None:
        # Claim 4. The parser has no unbounded loop; this is the measurement that says so.
        rng = random.Random(FIXED_SEED + 4)
        started = time.monotonic()
        for payload in random_payloads(rng, RANDOM_INPUTS):
            dissect_payload(payload)
        for payload in mutated_payloads(rng, MUTATED_INPUTS):
            dissect_payload(payload)
        elapsed = time.monotonic() - started

        assert elapsed < TIME_BUDGET_SECONDS, (
            f"{RANDOM_INPUTS + MUTATED_INPUTS} inputs took {elapsed:.1f}s"
        )


class TestNoTrafficIsStolen:
    """The module must not claim what is not on its port, however perfect the envelope looks."""

    def test_random_bytes_on_a_non_102_port_are_never_claimed(self) -> None:
        rng = random.Random(FIXED_SEED + 10)
        for payload in random_payloads(rng, 500):
            frame = make_frame(payload, src_port=OTHER_PORT, dst_port=502)
            assert not IsoTsapDissector().claims(frame)

    def test_a_perfect_envelope_off_the_port_is_not_claimed(self) -> None:
        for envelope in VALID_ENVELOPES:
            assert not IsoTsapDissector().claims(
                make_frame(envelope, src_port=OTHER_PORT, dst_port=OTHER_PORT)
            )

    def test_a_non_102_frame_stays_unparsed_through_the_registry(self) -> None:
        registry = DissectorRegistry([IsoTsapDissector()])
        for envelope in VALID_ENVELOPES:
            frame = make_frame(envelope, src_port=OTHER_PORT, dst_port=OTHER_PORT)
            assert isinstance(registry.dispatch(frame), UnparsedMessage)

    def test_every_valid_envelope_is_claimed_on_the_port(self) -> None:
        # The other half: the port claim actually catches all of these, so the corpus above is not
        # a corpus of frames nothing was ever going to look at.
        for envelope in VALID_ENVELOPES:
            assert IsoTsapDissector().claims(make_frame(envelope, dst_port=ISO_TSAP_PORT))


class TestTheTruncationSweep:
    """Every truncation of every valid envelope, at every byte boundary, not a sample."""

    @pytest.mark.parametrize("index", range(len(VALID_ENVELOPES)))
    def test_every_truncation_of_a_valid_envelope_is_refused(self, index: int) -> None:
        envelope = VALID_ENVELOPES[index]
        for cut in range(len(envelope)):
            truncated = envelope[:cut]
            result = dissect_payload(truncated)
            assert isinstance(result, MalformedFrame), (
                f"envelope {index} truncated to {cut} of {len(envelope)} decoded: {truncated.hex()}"
            )
            assert result.reason in {
                MalformedReason.SHORT_HEADER,
                MalformedReason.LENGTH_MISMATCH,
                MalformedReason.INCONSISTENT_COUNT,
            }, f"envelope {index} cut {cut}: {result.reason}"

    @pytest.mark.parametrize("index", range(len(VALID_ENVELOPES)))
    def test_every_truncation_of_every_envelope_traces_to_its_frame(self, index: int) -> None:
        envelope = VALID_ENVELOPES[index]
        for cut in range(len(envelope)):
            frame = make_frame(envelope[:cut], dst_port=ISO_TSAP_PORT, frame_index=cut)
            result = IsoTsapDissector().dissect(frame)
            assert_contained(result, frame)

    def test_every_honest_envelope_still_decodes_at_full_length(self) -> None:
        # The sweep above would pass trivially if nothing ever decoded, so the full envelopes are
        # asserted to decode in the same suite that refuses every prefix of them.
        for envelope in VALID_ENVELOPES:
            result = dissect_payload(envelope)
            assert isinstance(result, IsoTsapMessage), (
                f"{envelope.hex()} refused: {getattr(result, 'detail', '')}"
            )


class TestTheLengthLieSweep:
    """The 16-bit packet length, swept across its whole range plus every boundary that matters."""

    def test_every_lying_length_field_is_refused(self) -> None:
        # A fixed, honest 10-octet envelope whose length field is rewritten to every value the
        # field can hold. Only the honest value may decode.
        envelope = bytearray(
            struct.pack(">BBH", 3, 0, 10) + bytes([2, 0xF0, 0x80]) + b"\x01\x02\x03"
        )
        honest = len(envelope)
        assert honest == 10

        for declared in range(0x10000):
            struct.pack_into(">H", envelope, 2, declared)
            result = dissect_payload(bytes(envelope))
            if declared == honest:
                assert isinstance(result, IsoTsapMessage), (
                    f"length {declared} is honest and must decode"
                )
                continue
            assert isinstance(result, MalformedFrame), f"length {declared} decoded"
            expected = (
                MalformedReason.FIELD_OUT_OF_RANGE
                if declared < TPKT_MIN_OCTETS
                else MalformedReason.LENGTH_MISMATCH
                if declared > len(envelope)
                else MalformedReason.TRAILING_BYTES
            )
            assert result.reason is expected, f"length {declared}: {result.reason}"

    @pytest.mark.parametrize("declared", [6, 7, 8, 9, 10, 65534, 65535])
    def test_every_declared_length_boundary_is_handled(self, declared: int) -> None:
        # The boundaries named in the declaration, each against a 10-octet payload: 6 is below the
        # minimum, 7 through 10 are honest-but-short, and the top two are beyond the buffer.
        envelope = struct.pack(">BBH", 3, 0, declared) + bytes([2, 0xF0, 0x80]) + b"\x01\x02\x03"
        result = dissect_payload(envelope)
        if declared == len(envelope):
            assert isinstance(result, IsoTsapMessage)
            return
        assert isinstance(result, MalformedFrame)
        expected = (
            MalformedReason.FIELD_OUT_OF_RANGE
            if declared < TPKT_MIN_OCTETS
            else MalformedReason.LENGTH_MISMATCH
            if declared > len(envelope)
            else MalformedReason.TRAILING_BYTES
        )
        assert result.reason is expected

    def test_65536_wraps_in_the_field_and_cannot_be_declared(self) -> None:
        # The declaration's boundary list names 65536. A 16-bit field cannot hold it, so what a
        # sender can actually put on the wire is 0 — and a declared 0 must be refused, not read as
        # "no length". This test is what makes that boundary meaningful rather than aspirational.
        packed = struct.pack(">H", 65536 & 0xFFFF)
        assert packed == b"\x00\x00"
        result = dissect_payload(struct.pack(">BB", 3, 0) + packed + bytes(20))
        assert isinstance(result, MalformedFrame)
        assert result.reason is MalformedReason.FIELD_OUT_OF_RANGE

    def test_no_declared_length_ever_sizes_an_allocation(self) -> None:
        # 65,535 declared, 4 present: the slice bound is the bytes present, never the field.
        rng = random.Random(FIXED_SEED + 20)
        for _ in range(200):
            declared = rng.choice([0xFFFE, 0xFFFF, 0x8000, 0x1000])
            payload = struct.pack(">BBH", 3, 0, declared) + bytes(rng.randint(0, 12))
            result = dissect_payload(payload)
            assert isinstance(result, MalformedFrame)
            assert result.reason is MalformedReason.LENGTH_MISMATCH
            assert result.payload_length == len(payload)


class TestTheDirectionSweep:
    """102 as source, as destination, and at both ends — the direction is a transport fact."""

    def test_102_as_destination_is_a_request(self) -> None:
        message = dissect_payload(VALID_ENVELOPES[0])
        assert isinstance(message, IsoTsapMessage)

    def test_102_as_source_is_safe_and_contained(self) -> None:
        rng = random.Random(FIXED_SEED + 30)
        for payload in random_payloads(rng, 300):
            frame = make_frame(payload, src_port=ISO_TSAP_PORT, dst_port=CLIENT_PORT)
            assert_contained(IsoTsapDissector().dissect(frame), frame)

    def test_102_at_both_ends_is_safe_and_contained(self) -> None:
        rng = random.Random(FIXED_SEED + 31)
        for payload in random_payloads(rng, 300):
            frame = make_frame(payload, src_port=ISO_TSAP_PORT, dst_port=ISO_TSAP_PORT)
            assert_contained(IsoTsapDissector().dissect(frame), frame)

    def test_every_valid_envelope_decodes_in_all_three_directions(self) -> None:
        for envelope in VALID_ENVELOPES:
            for src_port, dst_port in (
                (CLIENT_PORT, ISO_TSAP_PORT),
                (ISO_TSAP_PORT, CLIENT_PORT),
                (ISO_TSAP_PORT, ISO_TSAP_PORT),
            ):
                frame = make_frame(envelope, src_port=src_port, dst_port=dst_port)
                result = IsoTsapDissector().dissect(frame)
                assert isinstance(result, IsoTsapMessage), (
                    f"{envelope.hex()} refused from {src_port} to {dst_port}: "
                    f"{getattr(result, 'detail', '')}"
                )


class TestTheAdversarialShapes:
    """The specific shapes an ISO-on-TCP parser is attacked with, swept rather than sampled."""

    def test_a_payload_of_every_legal_length_up_to_the_header_is_refused(self) -> None:
        for length in range(TPKT_HEADER_LENGTH):
            result = dissect_payload(bytes(length))
            assert isinstance(result, MalformedFrame)
            assert result.reason is MalformedReason.SHORT_HEADER

    def test_a_tpkt_of_every_length_from_4_to_the_minimum_is_field_out_of_range(self) -> None:
        # 4, 5 and 6 are at or above the TPKT header but below the minimum that can carry a TPDU.
        for declared in range(TPKT_HEADER_LENGTH, TPKT_MIN_OCTETS):
            payload = struct.pack(">BBH", 3, 0, declared) + bytes(declared - 4)
            result = dissect_payload(payload)
            assert isinstance(result, MalformedFrame)
            assert result.reason is MalformedReason.FIELD_OUT_OF_RANGE, f"length {declared}"

    def test_every_length_indicator_of_255_is_refused(self) -> None:
        for reserved in (LI_RESERVED_FOR_EXTENSIONS,):
            result = dissect_payload(struct.pack(">BBH", 3, 0, 40) + bytes([reserved]) + bytes(35))
            assert isinstance(result, MalformedFrame)
            assert result.reason is MalformedReason.FIELD_OUT_OF_RANGE

    def test_every_length_indicator_up_to_254_is_measured_against_the_buffer(self) -> None:
        # A LI that claims more header than arrived is inconsistent; one that does not is decoded,
        # with LI 0 as the one documented exception -- it declares a one-octet header, leaving no
        # TPDU code at all, so octet 2 would be user data read as a header.
        #
        # The code here is 0x00, an unnamed TPDU with no fixed-part floor, which is what makes this
        # a sweep of the LI bound itself. A DT cannot be used for it: from this change onward a DT
        # accepts only LI 2, and that rule has its own sweep
        # (`test_no_dt_offset_from_2_can_hide_application_octets`).
        for length_indicator in range(MAX_LENGTH_INDICATOR + 1):
            body = bytes([length_indicator]) + bytes(6)
            result = dissect_payload(envelope(body))
            if length_indicator == 0 or length_indicator + 1 > len(body):
                assert isinstance(result, MalformedFrame), f"LI {length_indicator} decoded"
                assert result.reason is MalformedReason.INCONSISTENT_COUNT
            else:
                assert isinstance(result, IsoTsapMessage), f"LI {length_indicator} refused"

    def test_every_tpdu_code_is_either_named_or_decoded_as_unknown(self) -> None:
        # No code is refused *for being unknown*: the envelope was sound, whatever the TPDU kind
        # turned out to be. The codes that DO have a fixed-part floor (CR, CC, DR, ER, ED) are
        # given a header long enough to hold it, so this sweep tests the code space rather than the
        # floors; the floors have their own sweep below and in the adversarial suite.
        named = {
            "connection_request",
            "connection_confirm",
            "disconnect_request",
            "data",
            "error",
            "expedited_data",
        }
        floor = {0x80: 6, 0x70: 4, 0x10: 3}
        for code in range(0x100):
            if code == 0xF0:
                length_indicator = 2
            elif code & 0xF0 in (0xE0, 0xD0):
                length_indicator = 6
            else:
                length_indicator = floor.get(code, 2)
            body = bytes([length_indicator, code]) + bytes(max(length_indicator + 1 - 2, 0) + 4)
            result = dissect_payload(struct.pack(">BBH", 3, 0, 4 + len(body)) + body)
            assert isinstance(result, IsoTsapMessage), f"code {code:#04x} refused: {result}"
            assert result.message_type in named or result.message_type == f"unknown({code})"

    @pytest.mark.parametrize("code", [0xE0, 0xE7, 0xDF, 0xD0])
    def test_every_connect_tpdu_floor_is_enforced_below_it_and_decodes_at_it(
        self, code: int
    ) -> None:
        # The CR/CC floor, swept including the credit nibble: 0xE7 is a CR with credit 7 and must
        # get the same floor as 0xE0, which a lookup keyed on the whole octet would have missed.
        for length_indicator in range(6):
            body = bytes([length_indicator, code]) + bytes(20)
            result = dissect_payload(struct.pack(">BBH", 3, 0, 4 + len(body)) + body)
            assert isinstance(result, MalformedFrame), f"code {code:#04x} LI {length_indicator}"
            assert result.reason is MalformedReason.INCONSISTENT_COUNT
            assert result.detail

        at_floor = bytes([6, code]) + bytes(5) + bytes(4)
        result = dissect_payload(struct.pack(">BBH", 3, 0, 4 + len(at_floor)) + at_floor)
        assert isinstance(result, IsoTsapMessage), result
        assert result.cotp_class == 0

    def test_a_connect_tpdu_with_initial_user_data_still_decodes_above_the_floor(self) -> None:
        # RFC 1006 §5 permits initial data in a CR/CC, and it lives PAST the header, so it can make
        # the TPDU longer but never the header shorter. The floor bounds the header only.
        body = bytes([6, 0xE0]) + struct.pack(">HHB", 1, 2, 0) + bytes(100)
        result = dissect_payload(struct.pack(">BBH", 3, 0, 4 + len(body)) + body)
        assert isinstance(result, IsoTsapMessage), result
        assert result.message_type == "connection_request"
        assert result.user_data_length == 100
        assert result.cotp_class == 0

    @pytest.mark.parametrize(("code", "floor"), [(0x80, 6), (0x70, 4), (0x10, 3)])
    def test_every_fixed_part_floor_is_enforced_at_every_value_below_it(
        self, code: int, floor: int
    ) -> None:
        # D1, swept: a DR, ER or ED whose length indicator stops short of its own fixed part is not
        # a decodable message, because the reference fields it must carry are not there to read.
        for length_indicator in range(floor):
            body = bytes([length_indicator, code]) + bytes(20)
            result = dissect_payload(struct.pack(">BBH", 3, 0, 4 + len(body)) + body)
            assert isinstance(result, MalformedFrame), (
                f"code {code:#04x} with LI {length_indicator} decoded"
            )
            assert result.reason is MalformedReason.INCONSISTENT_COUNT
            assert result.detail

    @pytest.mark.parametrize(("code", "floor"), [(0x80, 6), (0x70, 4), (0x10, 3)])
    def test_every_fixed_part_floor_still_decodes_at_the_floor(self, code: int, floor: int) -> None:
        # The boundary the floor sits on must remain usable, or the floor would be refusing lawful
        # traffic rather than malformed traffic.
        body = bytes([floor, code]) + bytes(floor - 1) + bytes(4)
        result = dissect_payload(struct.pack(">BBH", 3, 0, 4 + len(body)) + body)
        assert isinstance(result, IsoTsapMessage), result

    @pytest.mark.parametrize("length_indicator", [0, 1, 3, 4, 7, 13, 24, 100, 254])
    def test_no_dt_offset_from_2_can_hide_application_octets(self, length_indicator: int) -> None:
        # D2, swept. A class-0 DT has no variable part (RFC 905 §13.7.1 a), so LI is exactly 2 and
        # every other value is refused. Before this, the same 22 application octets reported 22,
        # 21, 17, 11 and 0 octets depending on one attacker-chosen octet.
        application = bytes.fromhex("320100000500000e00000401120a1002000000000000")
        body = bytes([length_indicator, 0xF0, 0x80]) + application
        result = dissect_payload(struct.pack(">BBH", 3, 0, 4 + len(body)) + body)
        assert isinstance(result, MalformedFrame), (
            f"DT with LI {length_indicator} decoded as "
            f"{getattr(result, 'message_type', '?')} reporting "
            f"{getattr(result, 'user_data_length', '?')} of 22 application octets"
        )
        assert result.reason is MalformedReason.INCONSISTENT_COUNT

    def test_a_dt_at_li_2_reports_every_application_octet(self) -> None:
        # The other half: pinned to 2, the count is the whole job and nothing is hidden.
        application = bytes.fromhex("320100000500000e00000401120a1002000000000000")
        body = bytes([2, 0xF0, 0x80]) + application
        result = dissect_payload(struct.pack(">BBH", 3, 0, 4 + len(body)) + body)
        assert isinstance(result, IsoTsapMessage), result
        assert result.user_data_length == len(application) == 22

    def test_every_reserved_octet_decodes(self) -> None:
        for reserved in range(0x100):
            result = dissect_payload(struct.pack(">BBH", 3, reserved, 7) + bytes([2, 0xF0, 0x80]))
            assert isinstance(result, IsoTsapMessage), f"reserved {reserved:#04x} refused"
            assert result.reserved_octet == reserved

    def test_every_tsap_parameter_length_is_bounded_by_the_header(self) -> None:
        # A parameter length that overruns the length indicator is inconsistent at every value, one
        # that exactly fills it decodes with the value carried verbatim, and a header the CR bound
        # rejects is refused as FIELD_OUT_OF_RANGE because 128 octets is the CR's own limit.
        #
        # The sweep stops at 245 because ``6 + 2 + length`` must still fit a length-indicator octet;
        # the values above it are covered by the LI sweep, which is the field that would overflow.
        for length in range(0xF6):
            header = (
                bytes([6 + 2 + length, 0xE0])
                + struct.pack(">HHB", 1, 2, 0)
                + bytes([0xC1, length])
                + bytes(length)
            )
            assert len(header) == length + 9
            result = dissect_payload(envelope(header))
            if len(header) > CR_MAX_OCTETS:
                assert isinstance(result, MalformedFrame), f"length {length} decoded"
                assert result.reason is MalformedReason.FIELD_OUT_OF_RANGE
                continue
            assert isinstance(result, IsoTsapMessage), f"length {length} refused: {result}"
            assert result.calling_tsap == bytes(length)

    def test_every_cr_header_length_from_0_to_254_is_handled(self) -> None:
        for length_indicator in range(MAX_LENGTH_INDICATOR + 1):
            body = bytes([length_indicator, 0xE0]) + bytes(min(length_indicator, 40))
            result = dissect_payload(struct.pack(">BBH", 3, 0, 4 + len(body)) + body)
            assert isinstance(result, IsoTsapMessage | MalformedFrame), f"LI {length_indicator}"
            if length_indicator + 1 > len(body):
                assert isinstance(result, MalformedFrame)
                assert result.reason is MalformedReason.INCONSISTENT_COUNT

    def test_a_cr_one_octet_over_the_bound_is_refused_and_at_the_bound_is_not(self) -> None:
        # A 128-octet CR: LI 127, a six-octet fixed part, and one 0xC1 parameter filling the rest,
        # so the header is a real parameter list and not a run of zero octets.
        at_bound = (
            bytes([127, 0xE0]) + struct.pack(">HHB", 1, 2, 0) + bytes([0xC1, 119]) + bytes(119)
        )
        assert len(at_bound) == CR_MAX_OCTETS
        assert isinstance(dissect_payload(envelope(at_bound)), IsoTsapMessage)

        over = bytes([128, 0xE0]) + struct.pack(">HHB", 1, 2, 0) + bytes([0xC1, 120]) + bytes(120)
        assert len(over) == CR_MAX_OCTETS + 1
        result = dissect_payload(envelope(over))
        assert isinstance(result, MalformedFrame)
        assert result.reason is MalformedReason.FIELD_OUT_OF_RANGE

    def test_an_envelope_at_the_maximum_tpkt_size_is_contained(self) -> None:
        # The largest thing the protocol permits, carried whole. Nothing may be truncated and
        # nothing may be allocated beyond it.
        user_data = bytes(TPKT_MAX_OCTETS - TPKT_HEADER_LENGTH - 3)
        payload = struct.pack(">BBH", 3, 0, TPKT_MAX_OCTETS) + bytes([2, 0xF0, 0x80]) + user_data
        assert len(payload) == TPKT_MAX_OCTETS
        frame = make_frame(payload, dst_port=ISO_TSAP_PORT)
        result = IsoTsapDissector().dissect(frame)
        assert_contained(result, frame)
        assert isinstance(result, IsoTsapMessage)
        assert result.user_data_length == TPKT_MAX_OCTETS - TPKT_MIN_OCTETS


class TestNothingFromTheApplicationEscapes:
    """ADR 0347's refusal register: no act, no station, no role, no S7 name, from any input."""

    def test_no_decoded_message_exposes_an_application_field(self) -> None:
        forbidden = {"act", "program_act", "station", "peer_role", "job", "opcode", "s7"}
        for field in IsoTsapMessage.model_fields:
            assert field not in forbidden, f"IsoTsapMessage exposes {field}"

    def test_the_whole_corpus_produces_only_envelope_fields(self) -> None:
        rng = random.Random(FIXED_SEED + 40)
        allowed = set(IsoTsapMessage.model_fields)
        for payload in random_payloads(rng, 200):
            result = dissect_payload(payload)
            if isinstance(result, IsoTsapMessage):
                assert set(result.model_dump()) == allowed

    def test_the_message_never_serialises_the_payload_bytes(self) -> None:
        # The count is carried; the octets are not.
        payload = envelope(bytes([2, 0xF0, 0x80]) + b"\xde\xad\xbe\xef")
        message = dissect_payload(payload)
        assert isinstance(message, IsoTsapMessage)
        assert message.user_data_length == 4
        assert "deadbeef" not in message.model_dump_json().lower()

    def test_no_corpus_result_reports_s7comm(self) -> None:
        rng = random.Random(FIXED_SEED + 41)
        for payload in random_payloads(rng, 300):
            assert dissect_payload(payload).protocol == "iso-tsap"
        for payload in mutated_payloads(rng, 300):
            assert dissect_payload(payload).protocol == "iso-tsap"

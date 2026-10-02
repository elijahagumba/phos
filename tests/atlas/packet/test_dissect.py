"""Tests for the dissector seam: the registry, dispatch, and the top-level pipeline.

The seam's whole purpose is that adding a protocol later touches nothing that already works, so
the tests here deliberately use a stub dissector for a protocol PHOS does not implement. If these
pass without `modbus.py` being involved, the seam is real.
"""

import itertools
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from tests.atlas.packet.conftest import make_frame, tcp_frame

from phos.atlas.packet import (
    CaptureStats,
    Direction,
    DissectorRegistry,
    IcsMessage,
    MalformedFrame,
    MalformedReason,
    ModbusDissector,
    ProtocolDissector,
    RawFrame,
    UnparsedMessage,
    dissect_capture,
)

DNP3_PORT = 20000


class StubDnp3Dissector:
    """A second dissector, implemented only here. Proves a protocol can be added from outside."""

    name = "stub-dnp3"

    def claims(self, frame: RawFrame) -> bool:
        return DNP3_PORT in (frame.src.port, frame.dst.port)

    def dissect(self, frame: RawFrame) -> IcsMessage | MalformedFrame:
        return IcsMessage(
            protocol=self.name,
            source=frame.source,
            timestamp=frame.timestamp,
            src=frame.src,
            dst=frame.dst,
            direction=Direction.UNKNOWN,
        )


class StubRefusingDissector:
    """A dissector that claims everything and refuses everything."""

    name = "stub-refuse"

    def claims(self, frame: RawFrame) -> bool:
        return True

    def dissect(self, frame: RawFrame) -> IcsMessage | MalformedFrame:
        return MalformedFrame(
            protocol=self.name,
            source=frame.source,
            timestamp=frame.timestamp,
            src=frame.src,
            dst=frame.dst,
            reason=MalformedReason.BAD_HEADER_FIELD,
            detail="the stub refuses everything",
            payload_length=len(frame.payload),
        )


class TestProtocolDissector:
    def test_a_stub_satisfies_the_protocol(self) -> None:
        assert isinstance(StubDnp3Dissector(), ProtocolDissector)

    def test_the_modbus_dissector_satisfies_the_protocol(self) -> None:
        assert isinstance(ModbusDissector(), ProtocolDissector)

    def test_something_that_is_not_a_dissector_does_not(self) -> None:
        assert not isinstance(object(), ProtocolDissector)


class TestDissectorRegistry:
    def test_an_empty_registry_leaves_everything_unparsed(self) -> None:
        result = DissectorRegistry().dispatch(make_frame(b"\x01\x02", dst_port=502))
        assert isinstance(result, UnparsedMessage)
        assert result.payload_length == 2
        assert result.protocol == "unknown"
        assert result.direction is Direction.UNKNOWN

    def test_dispatches_to_the_dissector_that_claims_the_frame(self) -> None:
        registry = DissectorRegistry([StubDnp3Dissector()])
        result = registry.dispatch(make_frame(b"\x05", dst_port=DNP3_PORT))
        assert isinstance(result, IcsMessage)
        assert result.protocol == "stub-dnp3"

    def test_traffic_no_dissector_claims_becomes_unparsed_not_malformed(self) -> None:
        # Honest coverage: "nobody looked at this" is not "we looked and it was wrong".
        registry = DissectorRegistry([StubDnp3Dissector()])
        result = registry.dispatch(make_frame(b"GET / HTTP/1.1", src_port=44000, dst_port=80))
        assert not isinstance(result, MalformedFrame)
        assert isinstance(result, UnparsedMessage)

    def test_the_first_claiming_dissector_wins(self) -> None:
        registry = DissectorRegistry([StubRefusingDissector(), StubDnp3Dissector()])
        result = registry.dispatch(make_frame(b"\x05", dst_port=DNP3_PORT))
        assert isinstance(result, MalformedFrame)
        assert result.protocol == "stub-refuse"

    def test_registration_order_is_preserved(self) -> None:
        registry = DissectorRegistry([ModbusDissector(), StubDnp3Dissector()])
        assert registry.names == ("modbus", "stub-dnp3")

    def test_exposes_the_dissectors_themselves_in_the_same_order(self) -> None:
        modbus, dnp3 = ModbusDissector(), StubDnp3Dissector()
        assert DissectorRegistry([modbus, dnp3]).dissectors == (modbus, dnp3)

    def test_a_dissector_can_be_added_without_touching_the_registry(self) -> None:
        # The pluggability criterion: a new protocol is a new object, not an edit.
        base = DissectorRegistry([ModbusDissector()])
        extended = base.with_dissector(StubDnp3Dissector())

        assert extended.names == ("modbus", "stub-dnp3")
        assert isinstance(extended.dispatch(make_frame(b"\x05", dst_port=DNP3_PORT)), IcsMessage)

    def test_adding_a_dissector_leaves_the_original_registry_alone(self) -> None:
        base = DissectorRegistry([ModbusDissector()])
        base.with_dissector(StubDnp3Dissector())

        assert base.names == ("modbus",)
        assert isinstance(base.dispatch(make_frame(b"\x05", dst_port=DNP3_PORT)), UnparsedMessage)

    def test_two_dissectors_claiming_the_same_name_are_refused(self) -> None:
        # Two dissectors under one name make every message's `protocol` field ambiguous.
        with pytest.raises(ValueError, match="stub-dnp3"):
            DissectorRegistry([StubDnp3Dissector(), StubDnp3Dissector()])

    def test_the_duplicate_check_applies_when_extending_too(self) -> None:
        with pytest.raises(ValueError, match="modbus"):
            DissectorRegistry([ModbusDissector()]).with_dissector(ModbusDissector())

    def test_dispatch_preserves_the_frames_provenance(self) -> None:
        frame = make_frame(b"\x01", dst_port=9999, frame_index=42, capture="/c/x.pcap")
        result = DissectorRegistry().dispatch(frame)
        assert result.source.frame_index == 42
        assert result.source.capture == "/c/x.pcap"
        assert result.timestamp == frame.timestamp


class TestDissectCapture:
    def test_runs_the_whole_pipeline_over_a_capture(self, write_pcap: Callable[..., Path]) -> None:
        request = bytes.fromhex("123400000006110300640002")
        path = write_pcap(
            [
                (1700000000, 0, tcp_frame(5555, 502, request)),
                (1700000001, 0, tcp_frame(44000, 80, b"GET / HTTP/1.1")),
            ]
        )
        results = list(dissect_capture(path, DissectorRegistry([ModbusDissector()])))

        assert len(results) == 2
        assert results[0].protocol == "modbus"
        assert isinstance(results[1], UnparsedMessage)

    def test_every_result_traces_back_to_its_frame(self, write_pcap: Callable[..., Path]) -> None:
        path = write_pcap(
            [(1700000000 + i, 0, tcp_frame(5555, 502, b"\x00" * 12)) for i in range(3)]
        )
        results = list(dissect_capture(path, DissectorRegistry([ModbusDissector()])))
        assert [result.source.frame_index for result in results] == [0, 1, 2]
        assert all(result.source.capture == str(path) for result in results)

    def test_returns_an_iterator(self, write_pcap: Callable[..., Path]) -> None:
        path = write_pcap([(1700000000, 0, tcp_frame(5555, 502, b"x"))])
        assert isinstance(dissect_capture(path, DissectorRegistry()), Iterator)

    def test_is_lazy_all_the_way_down(self, write_pcap: Callable[..., Path]) -> None:
        path = write_pcap([(1700000000 + i, 0, tcp_frame(5555, 502, b"xx")) for i in range(500)])
        stats = CaptureStats()
        results = dissect_capture(path, DissectorRegistry([ModbusDissector()]), stats)

        next(results)
        assert stats.frames_read == 1

        list(itertools.islice(results, 2))
        assert stats.frames_read == 3

    def test_surfaces_capture_stats_alongside_the_messages(
        self, write_pcap: Callable[..., Path]
    ) -> None:
        path = write_pcap(
            [
                (1700000000, 0, tcp_frame(5555, 502, b"\x00" * 12)),
                (1700000001, 0, tcp_frame(5555, 502, b"")),
            ]
        )
        stats = CaptureStats()
        results = list(dissect_capture(path, DissectorRegistry([ModbusDissector()]), stats))

        assert len(results) == 1
        assert stats.frames_read == 2
        assert stats.frames_without_payload == 1
        assert stats.accounts_for_every_frame()

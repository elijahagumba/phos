"""Tests for the traceability types every dissected message is anchored to."""

from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from phos.atlas.packet import Endpoint, FrameSource, RawFrame, Transport


class TestEndpoint:
    def test_holds_an_address_and_port(self) -> None:
        endpoint = Endpoint(ip="10.0.0.4", port=502)
        assert endpoint.ip == "10.0.0.4"
        assert endpoint.port == 502

    def test_is_frozen(self) -> None:
        endpoint = Endpoint(ip="10.0.0.4", port=502)
        with pytest.raises(ValidationError):
            endpoint.port = 503  # type: ignore[misc]

    @pytest.mark.parametrize("port", [-1, 65536, 100000])
    def test_rejects_a_port_outside_the_16_bit_range(self, port: int) -> None:
        with pytest.raises(ValidationError):
            Endpoint(ip="10.0.0.4", port=port)

    @pytest.mark.parametrize("port", [0, 65535])
    def test_accepts_the_range_boundaries(self, port: int) -> None:
        assert Endpoint(ip="10.0.0.4", port=port).port == port

    def test_rejects_an_empty_address(self) -> None:
        with pytest.raises(ValidationError):
            Endpoint(ip="", port=502)

    def test_accepts_an_ipv6_address(self) -> None:
        assert Endpoint(ip="2001::2", port=502).ip == "2001::2"

    def test_equal_endpoints_compare_and_hash_equal(self) -> None:
        assert Endpoint(ip="10.0.0.4", port=502) == Endpoint(ip="10.0.0.4", port=502)
        assert len({Endpoint(ip="10.0.0.4", port=502), Endpoint(ip="10.0.0.4", port=502)}) == 1


class TestFrameSource:
    def test_names_the_capture_and_the_frame_within_it(self) -> None:
        source = FrameSource(capture="/captures/plant.pcap", frame_index=7)
        assert source.capture == "/captures/plant.pcap"
        assert source.frame_index == 7

    def test_is_frozen(self) -> None:
        source = FrameSource(capture="/captures/plant.pcap", frame_index=7)
        with pytest.raises(ValidationError):
            source.frame_index = 8  # type: ignore[misc]

    def test_rejects_a_negative_frame_index(self) -> None:
        with pytest.raises(ValidationError):
            FrameSource(capture="/captures/plant.pcap", frame_index=-1)

    def test_rejects_an_unnamed_capture(self) -> None:
        with pytest.raises(ValidationError):
            FrameSource(capture="", frame_index=0)

    def test_accepts_the_first_frame(self) -> None:
        assert FrameSource(capture="c.pcap", frame_index=0).frame_index == 0


class TestTransport:
    def test_covers_the_two_transports_the_reader_peels(self) -> None:
        assert {member.value for member in Transport} == {"TCP", "UDP"}

    def test_is_string_backed(self) -> None:
        assert Transport.TCP == "TCP"


class TestRawFrame:
    def _frame(self, **overrides: object) -> RawFrame:
        fields: dict[str, object] = {
            "source": FrameSource(capture="/captures/plant.pcap", frame_index=3),
            "timestamp": datetime(2026, 8, 12, 9, 30, tzinfo=UTC),
            "transport": Transport.TCP,
            "src": Endpoint(ip="10.0.0.1", port=5555),
            "dst": Endpoint(ip="10.0.0.2", port=502),
            "payload": b"\x00\x01",
        }
        fields.update(overrides)
        return RawFrame(**fields)  # type: ignore[arg-type]

    def test_carries_the_peeled_transport_payload_and_its_endpoints(self) -> None:
        frame = self._frame()
        assert frame.payload == b"\x00\x01"
        assert frame.src.port == 5555
        assert frame.dst.port == 502
        assert frame.transport is Transport.TCP

    def test_frame_index_is_the_source_index(self) -> None:
        # One source of truth: the index cannot disagree with the FrameSource it is read from.
        assert self._frame().frame_index == 3

    def test_frame_index_appears_in_a_dump(self) -> None:
        assert self._frame().model_dump()["frame_index"] == 3

    def test_is_frozen(self) -> None:
        frame = self._frame()
        with pytest.raises(ValidationError):
            frame.payload = b"other"  # type: ignore[misc]

    def test_rejects_a_naive_timestamp(self) -> None:
        with pytest.raises(ValidationError):
            self._frame(timestamp=datetime(2026, 8, 12, 9, 30))

    def test_normalises_the_timestamp_to_utc(self) -> None:
        east = timezone(timedelta(hours=2))
        frame = self._frame(timestamp=datetime(2026, 8, 12, 11, 30, tzinfo=east))
        assert frame.timestamp == datetime(2026, 8, 12, 9, 30, tzinfo=UTC)
        assert frame.timestamp.tzinfo is UTC

    def test_accepts_an_empty_payload(self) -> None:
        assert self._frame(payload=b"").payload == b""

    def test_the_link_fields_are_absent_on_a_frame_built_without_them(self) -> None:
        # ADR 0345 adds them as optional so a frame built the old way still validates.
        frame = self._frame()
        assert frame.dst_mac is None
        assert frame.src_mac is None
        assert frame.ethertype is None
        assert frame.tcp_seq is None

    def test_carries_the_link_fields_when_the_reader_saw_them(self) -> None:
        frame = self._frame(
            dst_mac="aa:aa:aa:aa:aa:aa",
            src_mac="bb:bb:bb:bb:bb:bb",
            ethertype=0x0800,
            tcp_seq=1,
        )
        assert frame.dst_mac == "aa:aa:aa:aa:aa:aa"
        assert frame.ethertype == 0x0800
        assert frame.tcp_seq == 1

    @pytest.mark.parametrize("ethertype", [-1, 0x10000])
    def test_rejects_an_ethertype_outside_the_16_bit_field(self, ethertype: int) -> None:
        with pytest.raises(ValidationError):
            self._frame(ethertype=ethertype)

    @pytest.mark.parametrize("ethertype", [0, 0x8100, 0xFFFF])
    def test_accepts_every_value_the_16_bit_field_can_hold(self, ethertype: int) -> None:
        # 0x8100 is a value, not a name. The reader does not rename it.
        assert self._frame(ethertype=ethertype).ethertype == ethertype

    @pytest.mark.parametrize("seq", [-1, 0x1_0000_0000])
    def test_rejects_a_sequence_number_outside_the_32_bit_space(self, seq: int) -> None:
        with pytest.raises(ValidationError):
            self._frame(tcp_seq=seq)

    @pytest.mark.parametrize("seq", [0, 0xFFFFFFFF])
    def test_accepts_the_edges_of_the_sequence_space(self, seq: int) -> None:
        assert self._frame(tcp_seq=seq).tcp_seq == seq

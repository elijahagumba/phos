"""Tests for the streaming capture reader.

The reader is the first thing hostile bytes touch, and the first place a coverage claim can be
quietly wrong. These tests hold it to both: what it decodes must be exactly right, and what it
cannot decode must be counted rather than dropped.
"""

import itertools
import struct
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from tests.atlas.packet.conftest import (
    ETHERTYPE_ARP,
    ETHERTYPE_IPV4,
    ETHERTYPE_IPV6,
    IP_PROTO_ICMP,
    IP_PROTO_TCP,
    LINKTYPE_ETHERNET,
    LINKTYPE_RAW_IP,
    ethernet,
    ipv4,
    ipv6,
    pcap_bytes,
    tcp,
    tcp_frame,
    udp_frame,
)

from phos.atlas.packet import CaptureError, CaptureStats, RawFrame, Transport, read_frames

MODBUS_PAYLOAD = bytes.fromhex("123400000006110300640002")


class TestReadsWhatItCan:
    def test_yields_frames_in_capture_order_with_endpoints_and_payloads(
        self, write_pcap: Callable[..., Path]
    ) -> None:
        path = write_pcap(
            [
                (1700000000, 0, tcp_frame(5555, 502, b"first")),
                (1700000001, 500000, tcp_frame(502, 5555, b"second")),
            ]
        )
        frames = list(read_frames(path))

        assert [frame.payload for frame in frames] == [b"first", b"second"]
        assert frames[0].src.ip == "10.0.0.1"
        assert frames[0].src.port == 5555
        assert frames[0].dst.port == 502
        assert frames[1].src.port == 502

    def test_timestamps_survive_to_the_microsecond(self, write_pcap: Callable[..., Path]) -> None:
        path = write_pcap([(1700000000, 123456, tcp_frame(5555, 502, b"x"))])
        (frame,) = read_frames(path)
        assert frame.timestamp == datetime(2023, 11, 14, 22, 13, 20, 123456, tzinfo=UTC)
        assert frame.timestamp.tzinfo is UTC

    def test_reads_pcapng_as_well_as_pcap(self, write_pcapng: Callable[..., Path]) -> None:
        path = write_pcapng([(1700000000_123456, tcp_frame(5555, 502, MODBUS_PAYLOAD))])
        (frame,) = read_frames(path)
        assert frame.payload == MODBUS_PAYLOAD
        assert frame.timestamp == datetime(2023, 11, 14, 22, 13, 20, 123456, tzinfo=UTC)

    def test_peels_udp(self, write_pcap: Callable[..., Path]) -> None:
        path = write_pcap([(1700000000, 0, udp_frame(4000, 502, b"datagram"))])
        (frame,) = read_frames(path)
        assert frame.transport is Transport.UDP
        assert frame.payload == b"datagram"

    def test_peels_ipv6(self, write_pcap: Callable[..., Path]) -> None:
        path = write_pcap(
            [(1700000000, 0, ethernet(ETHERTYPE_IPV6, ipv6(IP_PROTO_TCP, tcp(5555, 502, b"v6"))))]
        )
        (frame,) = read_frames(path)
        assert frame.src.ip == "2001::"
        assert frame.dst.ip == "2001::2"
        assert frame.payload == b"v6"

    def test_every_frame_names_its_capture_and_index(self, write_pcap: Callable[..., Path]) -> None:
        path = write_pcap([(1700000000 + i, 0, tcp_frame(5555, 502, b"x")) for i in range(3)])
        frames = list(read_frames(path))
        assert [frame.frame_index for frame in frames] == [0, 1, 2]
        assert all(frame.source.capture == str(path) for frame in frames)

    def test_frame_index_counts_frames_it_could_not_decode(
        self, write_pcap: Callable[..., Path]
    ) -> None:
        # The index must match what a packet analyser shows for the same file, so an operator
        # asked to look at frame 2 finds the frame we meant.
        path = write_pcap(
            [
                (1700000000, 0, tcp_frame(5555, 502, b"first")),
                (1700000001, 0, ethernet(ETHERTYPE_ARP, b"\x00" * 28)),
                (1700000002, 0, tcp_frame(5555, 502, b"third")),
            ]
        )
        frames = list(read_frames(path))
        assert [frame.frame_index for frame in frames] == [0, 2]


class TestStreamsRatherThanLoads:
    def test_returns_an_iterator(self, write_pcap: Callable[..., Path]) -> None:
        path = write_pcap([(1700000000, 0, tcp_frame(5555, 502, b"x"))])
        assert isinstance(read_frames(path), Iterator)

    def test_reads_only_as_far_as_it_is_asked_to(self, write_pcap: Callable[..., Path]) -> None:
        # The capture is 500 frames. Taking one must not have read the other 499 — this is the
        # bounded-memory requirement, measured rather than asserted by inspection.
        path = write_pcap([(1700000000 + i, 0, tcp_frame(5555, 502, b"x")) for i in range(500)])
        stats = CaptureStats()
        frames = read_frames(path, stats)

        next(frames)
        assert stats.frames_read == 1

        list(itertools.islice(frames, 3))
        assert stats.frames_read == 4

        list(frames)
        assert stats.frames_read == 500


class TestCountsWhatItCannot:
    def test_non_ip_traffic_is_undecodable_not_dropped_silently(
        self, write_pcap: Callable[..., Path]
    ) -> None:
        path = write_pcap([(1700000000, 0, ethernet(ETHERTYPE_ARP, b"\x00" * 28))])
        stats = CaptureStats()
        assert list(read_frames(path, stats)) == []
        assert stats.frames_read == 1
        assert stats.frames_undecodable == 1

    def test_non_tcp_or_udp_traffic_is_undecodable(self, write_pcap: Callable[..., Path]) -> None:
        path = write_pcap(
            [
                (
                    1700000000,
                    0,
                    ethernet(ETHERTYPE_IPV4, ipv4(IP_PROTO_ICMP, b"\x08\x00" + b"\x00" * 6)),
                )
            ]
        )
        stats = CaptureStats()
        assert list(read_frames(path, stats)) == []
        assert stats.frames_undecodable == 1

    def test_a_truncated_frame_is_undecodable(self, write_pcap: Callable[..., Path]) -> None:
        path = write_pcap([(1700000000, 0, b"\xaa\xbb")])
        stats = CaptureStats()
        assert list(read_frames(path, stats)) == []
        assert stats.frames_undecodable == 1

    def test_an_ip_header_lying_short_about_its_payload_is_undecodable(
        self, write_pcap: Callable[..., Path]
    ) -> None:
        # total_length claims the packet ends at the IP header, so no transport layer survives.
        path = write_pcap(
            [
                (
                    1700000000,
                    0,
                    ethernet(
                        ETHERTYPE_IPV4, ipv4(IP_PROTO_TCP, tcp(5555, 502, b"x"), total_length=20)
                    ),
                )
            ]
        )
        stats = CaptureStats()
        assert list(read_frames(path, stats)) == []
        assert stats.frames_undecodable == 1

    def test_a_frame_with_no_transport_payload_is_counted_separately(
        self, write_pcap: Callable[..., Path]
    ) -> None:
        # A bare acknowledgement decoded perfectly and carries nothing to dissect. Calling it
        # undecodable would understate coverage; yielding it would flood P2 with empty messages.
        path = write_pcap([(1700000000, 0, tcp_frame(5555, 502, b""))])
        stats = CaptureStats()
        assert list(read_frames(path, stats)) == []
        assert stats.frames_undecodable == 0
        assert stats.frames_without_payload == 1

    def test_an_unsupported_link_type_is_recorded_rather_than_misparsed(
        self, write_pcap: Callable[..., Path]
    ) -> None:
        path = write_pcap(
            [(1700000000, 0, b"\x45\x00\x00\x14" + b"\x00" * 16)], linktype=LINKTYPE_RAW_IP
        )
        stats = CaptureStats()
        assert list(read_frames(path, stats)) == []
        assert stats.link_type == LINKTYPE_RAW_IP
        assert stats.frames_read == 1
        assert stats.frames_undecodable == 1

    def test_records_the_link_type_it_did_support(self, write_pcap: Callable[..., Path]) -> None:
        path = write_pcap([(1700000000, 0, tcp_frame(5555, 502, b"x"))])
        stats = CaptureStats()
        list(read_frames(path, stats))
        assert stats.link_type == LINKTYPE_ETHERNET


class TestHostileContainers:
    def test_a_file_that_is_not_a_capture_raises_a_named_error(
        self, write_raw: Callable[[bytes, str], Path]
    ) -> None:
        path = write_raw(b"this is not a capture file at all", "notacapture.pcap")
        with pytest.raises(CaptureError, match="not a readable pcap"):
            list(read_frames(path))

    def test_an_empty_file_raises_a_named_error(
        self, write_raw: Callable[[bytes, str], Path]
    ) -> None:
        path = write_raw(b"", "empty.pcap")
        with pytest.raises(CaptureError):
            list(read_frames(path))

    def test_a_missing_file_raises_the_standard_error(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            list(read_frames(tmp_path / "absent.pcap"))

    def test_a_truncated_record_header_stops_the_read_and_is_recorded(
        self, write_raw: Callable[[bytes, str], Path]
    ) -> None:
        # A capture whose final record header is cut in half. Everything before it is still
        # delivered; the read stops there because record framing cannot be resynchronised.
        good = pcap_bytes([(1700000000, 0, tcp_frame(5555, 502, b"first"))])
        path = write_raw(good + struct.pack("<II", 1700000001, 0), "cut.pcap")
        stats = CaptureStats()
        frames = list(read_frames(path, stats))

        assert [frame.payload for frame in frames] == [b"first"]
        assert stats.truncated is True

    def test_a_record_claiming_more_bytes_than_remain_is_undecodable(
        self, write_raw: Callable[[bytes, str], Path]
    ) -> None:
        header = struct.pack("<IHHiIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, LINKTYPE_ETHERNET)
        record = struct.pack("<IIII", 1700000000, 0, 9999, 9999) + b"\xaa" * 10
        stats = CaptureStats()
        assert list(read_frames(write_raw(header + record, "short.pcap"), stats)) == []
        assert stats.frames_read == 1
        assert stats.frames_undecodable == 1

    def test_a_timestamp_no_datetime_can_hold_is_undecodable_not_a_crash(
        self, write_pcapng: Callable[..., Path]
    ) -> None:
        # pcapng carries a 64-bit microsecond timestamp, so a capture can name an instant far
        # outside the year range `datetime` supports. That is hostile input like any other.
        path = write_pcapng([(0xFFFFFFFFFFFFFFFF, tcp_frame(5555, 502, b"x"))])
        stats = CaptureStats()
        assert list(read_frames(path, stats)) == []
        assert stats.frames_read == 1
        assert stats.frames_undecodable == 1
        assert stats.accounts_for_every_frame()

    def test_a_clean_capture_is_not_marked_truncated(self, write_pcap: Callable[..., Path]) -> None:
        path = write_pcap([(1700000000, 0, tcp_frame(5555, 502, b"x"))])
        stats = CaptureStats()
        list(read_frames(path, stats))
        assert stats.truncated is False


class TestCaptureStats:
    def test_starts_empty(self) -> None:
        stats = CaptureStats()
        assert stats.frames_read == 0
        assert stats.frames_yielded == 0
        assert stats.frames_undecodable == 0
        assert stats.frames_without_payload == 0
        assert stats.link_type is None
        assert stats.truncated is False

    def test_every_frame_read_is_accounted_for(self, write_pcap: Callable[..., Path]) -> None:
        path = write_pcap(
            [
                (1700000000, 0, tcp_frame(5555, 502, b"payload")),
                (1700000001, 0, ethernet(ETHERTYPE_ARP, b"\x00" * 28)),
                (1700000002, 0, tcp_frame(5555, 502, b"")),
                (1700000003, 0, udp_frame(4000, 502, b"more")),
            ]
        )
        stats = CaptureStats()
        frames = list(read_frames(path, stats))

        assert len(frames) == 2
        assert stats.frames_read == 4
        assert stats.frames_yielded == 2
        assert stats.frames_undecodable == 1
        assert stats.frames_without_payload == 1
        assert stats.accounts_for_every_frame()

    def test_an_unaccounted_frame_is_visible(self) -> None:
        stats = CaptureStats(frames_read=5, frames_yielded=1)
        assert not stats.accounts_for_every_frame()

    def test_reading_without_stats_still_works(self, write_pcap: Callable[..., Path]) -> None:
        path = write_pcap([(1700000000, 0, tcp_frame(5555, 502, b"x"))])
        assert len(list(read_frames(path))) == 1

    def test_frames_are_raw_frames(self, write_pcap: Callable[..., Path]) -> None:
        path = write_pcap([(1700000000, 0, tcp_frame(5555, 502, b"x"))])
        assert all(isinstance(frame, RawFrame) for frame in read_frames(path))

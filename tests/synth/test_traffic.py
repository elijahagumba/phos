"""Whether the generated capture is a capture: real bytes, read by the real dissector.

The acceptance standard for this path is narrow and checkable — a Modbus-emitting plant must
produce traffic the packet adapter parses without a single malformed frame — so that is the first
thing tested, end to end, through `phos.atlas.packet.dissect_capture` and nothing shorter.

Beyond that the tests are about the capture not announcing itself. Checksums are verified the way
a receiver verifies them (a correct header sums to zero over its own checksum field), every
exchange is accounted for in both directions, and the polling rhythm carries jitter, because a
scan that lands on the exact same millisecond forever would give the command-interval features a
coefficient of variation of zero and no real SCADA server does that.
"""

import statistics
import struct
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from pathlib import Path

import pytest

from phos.atlas.packet import (
    CaptureStats,
    CommandStreamStats,
    DissectionResult,
    DissectorRegistry,
    MalformedFrame,
    ModbusDissector,
    ModbusMessage,
    UnparsedMessage,
    command_events,
    device_entity_id,
    dissect_capture,
)
from phos.synth.plant import (
    CommandIntent,
    CommandKind,
    PlantStep,
    RunSpec,
    SensorReport,
    TrueState,
    register_count,
)
from phos.synth.plants import water
from phos.synth.run import PlantRun, run_plant
from phos.synth.traffic import MODBUS_PORT, TrafficPolicy, modbus_frames, write_pcap

START = datetime(2026, 9, 1, tzinfo=UTC)
REGISTRY = DissectorRegistry([ModbusDissector()])


def spec(steps: int = 120, seed: int = 21) -> RunSpec:
    """Return a short run spec at thirty-second sampling."""
    return RunSpec(
        seed=seed,
        start=START,
        duration=timedelta(seconds=30) * steps,
        sample_interval=timedelta(seconds=30),
    )


def capture(run: PlantRun, path: Path, policy: TrafficPolicy | None = None) -> int:
    """Render a run's control traffic into a pcap at ``path`` and return the frame count."""
    return write_pcap(modbus_frames(run.description, run.steps, policy), path)


def packets(path: Path) -> list[bytes]:
    """Return every packet in a pcap, parsed without the library under test."""
    raw = path.read_bytes()
    magic, _major, _minor, _zone, _sigfigs, _snaplen, link = struct.unpack_from("<IHHiIII", raw, 0)
    assert magic == 0xA1B2C3D4
    assert link == 1
    out: list[bytes] = []
    offset = 24
    while offset < len(raw):
        _seconds, _micros, included, original = struct.unpack_from("<IIII", raw, offset)
        assert included == original
        offset += 16
        out.append(raw[offset : offset + included])
        offset += included
    return out


def ones_complement(data: bytes) -> int:
    """Return the internet checksum of ``data``. Zero over a header that already carries one."""
    padded = data + b"\x00" * (len(data) % 2)
    total = int(sum(struct.unpack(f">{len(padded) // 2}H", padded)))
    total = (total & 0xFFFF) + (total >> 16)
    total = (total & 0xFFFF) + (total >> 16)
    return ~total & 0xFFFF


class TestThePacketAdapterReadsIt:
    def test_every_frame_with_a_payload_decodes_as_modbus(self, tmp_path: Path) -> None:
        run = run_plant("water-treatment", spec())
        path = tmp_path / "capture.pcap"
        capture(run, path)
        results = list(dissect(path))
        assert results
        assert all(isinstance(result, ModbusMessage) for result in results)

    def test_not_one_frame_is_malformed(self, tmp_path: Path) -> None:
        run = run_plant("power-generation", spec())
        path = tmp_path / "capture.pcap"
        capture(run, path)
        assert [result for result in dissect(path) if isinstance(result, MalformedFrame)] == []

    def test_no_traffic_falls_through_undissected(self, tmp_path: Path) -> None:
        run = run_plant("water-treatment", spec())
        path = tmp_path / "capture.pcap"
        capture(run, path)
        assert [result for result in dissect(path) if isinstance(result, UnparsedMessage)] == []

    def test_the_reader_accounts_for_every_frame_in_the_file(self, tmp_path: Path) -> None:
        run = run_plant("water-treatment", spec())
        path = tmp_path / "capture.pcap"
        written = capture(run, path)
        stats = CaptureStats()
        list(dissect(path, stats))
        assert stats.frames_read == written
        assert stats.accounts_for_every_frame()
        assert stats.frames_undecodable == 0

    def test_the_handshake_frames_are_counted_as_carrying_no_payload(self, tmp_path: Path) -> None:
        run = run_plant("water-treatment", spec())
        path = tmp_path / "capture.pcap"
        capture(run, path)
        stats = CaptureStats()
        list(dissect(path, stats))
        # Three frames open each conversation, and there is one conversation per client/server
        # pair: SCADA to each PLC, and the HMI to the PLC holding the setpoints.
        assert stats.frames_without_payload == 9

    def test_the_command_stream_reads_one_command_per_request(self, tmp_path: Path) -> None:
        run = run_plant("water-treatment", spec())
        path = tmp_path / "capture.pcap"
        capture(run, path)
        stream = CommandStreamStats()
        events = list(command_events(dissect(path), stream))
        assert len(events) == run.command_count
        assert stream.responses == run.command_count
        assert stream.uninterpreted == 0
        assert stream.malformed == 0

    def test_the_commands_name_the_devices_the_plant_declared(self, tmp_path: Path) -> None:
        run = run_plant("water-treatment", spec(steps=40))
        path = tmp_path / "capture.pcap"
        capture(run, path)
        network = run.description.control_network
        assert network is not None
        issuers = {event.issuer for event in command_events(dissect(path))}
        assert device_entity_id(network.node("scada").ip) in issuers
        assert device_entity_id(network.node("engineering").ip) not in issuers


class TestTheBytesSayWhatThePlantSaid:
    def test_a_poll_reads_the_block_the_register_map_declares(self, tmp_path: Path) -> None:
        run = run_plant("water-treatment", spec(steps=20))
        path = tmp_path / "capture.pcap"
        capture(run, path)
        reads = [
            event
            for event in command_events(dissect(path))
            if event.function_name == "read_holding_registers"
        ]
        network = run.description.control_network
        assert network is not None
        declared = {(block.start_address, len(block.signals)) for block in network.blocks}
        assert {(read.reference_address, read.quantity) for read in reads} == declared

    def test_a_response_carries_the_counts_of_the_readings_at_that_instant(
        self, tmp_path: Path
    ) -> None:
        run = run_plant("water-treatment", spec(steps=6))
        path = tmp_path / "capture.pcap"
        capture(run, path)
        network = run.description.control_network
        assert network is not None
        expected = {
            tuple(
                register_count(run.description.signal(key), run.steps[0].report.values[key])
                for key in block.signals
            )
            for block in network.blocks
        }
        # One response per block at the first instant. Which arrives first depends on how the
        # three connections interleave, so the set is what is asserted, not the order.
        answered = {
            result.values
            for result in dissect(path)
            if isinstance(result, ModbusMessage)
            and result.function_code == 3
            and result.values
            and result.timestamp < run.steps[1].timestamp
        }
        assert answered == expected

    def test_an_operator_write_carries_the_setpoint_that_was_moved(self, tmp_path: Path) -> None:
        run = run_plant("water-treatment", spec(steps=400))
        path = tmp_path / "capture.pcap"
        capture(run, path)
        writes = [
            event
            for event in command_events(dissect(path))
            if event.function_name == "write_single_register"
        ]
        assert writes
        intents = [
            (intent, step)
            for step in run.steps
            for intent in step.commands
            if intent.kind is CommandKind.WRITE
        ]
        assert len(writes) == len(intents)
        for write, (intent, _step) in zip(writes, intents, strict=True):
            assert write.reference_address == intent.address
            assert write.values == intent.values

    def test_a_plant_with_no_control_network_produces_no_frames(self) -> None:
        run = run_plant("batch-reactor", spec(steps=60))
        assert modbus_frames(run.description, run.steps) == ()


class TestTheCaptureDoesNotAnnounceItself:
    def test_the_ip_header_checksum_verifies(self, tmp_path: Path) -> None:
        run = run_plant("water-treatment", spec(steps=10))
        path = tmp_path / "capture.pcap"
        capture(run, path)
        for packet in packets(path):
            assert ones_complement(packet[14:34]) == 0

    def test_the_tcp_checksum_verifies_over_its_pseudo_header(self, tmp_path: Path) -> None:
        run = run_plant("water-treatment", spec(steps=10))
        path = tmp_path / "capture.pcap"
        capture(run, path)
        for packet in packets(path):
            total_length = struct.unpack_from(">H", packet, 16)[0]
            segment = packet[34 : 14 + total_length]
            pseudo = packet[26:34] + struct.pack(">BBH", 0, 6, len(segment))
            assert ones_complement(pseudo + segment) == 0

    def test_sequence_numbers_advance_by_the_bytes_actually_sent(self, tmp_path: Path) -> None:
        run = run_plant("water-treatment", spec(steps=10))
        path = tmp_path / "capture.pcap"
        capture(run, path)
        seen: dict[tuple[str, int, str, int], tuple[int, int]] = {}
        for packet in packets(path):
            source = ".".join(str(byte) for byte in packet[26:30])
            destination = ".".join(str(byte) for byte in packet[30:34])
            src_port, dst_port, sequence = struct.unpack_from(">HHI", packet, 34)
            total_length = struct.unpack_from(">H", packet, 16)[0]
            payload = len(packet[54 : 14 + total_length])
            # The full four-tuple: two PLC-side conversations share the server's address and port
            # and have entirely separate sequence spaces.
            key = (source, src_port, destination, dst_port)
            previous = seen.get(key)
            if previous is not None and payload:
                assert sequence == previous[0] + previous[1]
            if payload:
                seen[key] = (sequence, payload)

    def test_the_polling_rhythm_is_not_a_metronome(self, tmp_path: Path) -> None:
        run = run_plant("water-treatment", spec(steps=120))
        path = tmp_path / "capture.pcap"
        capture(run, path)
        events = [
            event for event in command_events(dissect(path)) if event.reference_address == 200
        ]
        gaps = [
            (later.timestamp - earlier.timestamp).total_seconds()
            for earlier, later in pairwise(events)
        ]
        assert statistics.pstdev(gaps) > 0.001

    def test_a_response_always_follows_its_request(self, tmp_path: Path) -> None:
        run = run_plant("water-treatment", spec(steps=20))
        path = tmp_path / "capture.pcap"
        capture(run, path)
        stamps = [result.timestamp for result in dissect(path)]
        assert stamps == sorted(stamps)


class TestReproducibility:
    def test_the_same_run_and_policy_produce_an_identical_file(self, tmp_path: Path) -> None:
        first, second = tmp_path / "a.pcap", tmp_path / "b.pcap"
        capture(run_plant("water-treatment", spec()), first)
        capture(run_plant("water-treatment", spec()), second)
        assert first.read_bytes() == second.read_bytes()

    def test_the_traffic_seed_moves_the_timing_and_nothing_else(self, tmp_path: Path) -> None:
        run = run_plant("water-treatment", spec(steps=60))
        first, second = tmp_path / "a.pcap", tmp_path / "b.pcap"
        assert capture(run, first, TrafficPolicy(seed=1)) == capture(
            run, second, TrafficPolicy(seed=2)
        )
        assert first.read_bytes() != second.read_bytes()
        # Independent connections interleave differently under different jitter, so what has to
        # match is the content, not the arrival order.
        payloads = [
            sorted(
                # A read response carries no address: P1 does not back-fill it from the
                # request, so -1 stands in for "the wire did not say" while sorting.
                (
                    result.function_code,
                    -1 if result.reference_address is None else result.reference_address,
                    result.values,
                )
                for result in dissect(path)
                if isinstance(result, ModbusMessage)
            )
            for path in (first, second)
        ]
        assert payloads[0] == payloads[1]

    def test_turning_the_jitter_off_gives_an_exactly_periodic_scan(self, tmp_path: Path) -> None:
        run = run_plant("water-treatment", spec(steps=30))
        path = tmp_path / "capture.pcap"
        capture(run, path, TrafficPolicy(poll_jitter_ms=0.0, response_delay_ms=(2.0, 2.0)))
        events = [
            event for event in command_events(dissect(path)) if event.reference_address == 200
        ]
        gaps = {
            (later.timestamp - earlier.timestamp).total_seconds()
            for earlier, later in pairwise(events)
        }
        assert gaps == {30.0}


class TestRefusals:
    def _step(self, intent: CommandIntent) -> PlantStep:
        """Return a single hand-built sample carrying one command intent."""
        run = run_plant("water-treatment", spec(steps=1))
        original = run.steps[0]
        return PlantStep(
            index=0,
            timestamp=original.timestamp,
            truth=TrueState(
                timestamp=original.timestamp, values=original.truth.values, internal={}
            ),
            report=SensorReport(timestamp=original.timestamp, values=original.report.values),
            began=None,
            active=None,
            commands=(intent,),
        )

    def test_a_multi_register_write_is_refused_rather_than_quietly_dropped(self) -> None:
        intent = CommandIntent(
            kind=CommandKind.WRITE,
            issuer="hmi",
            target="plc_outlet",
            address=300,
            quantity=2,
            values=(1, 2),
            reason="hand-built",
        )
        with pytest.raises(ValueError, match="one register at a time"):
            modbus_frames(water.WATER_DESCRIPTION, [self._step(intent)])

    def test_a_read_of_an_address_the_map_does_not_describe_is_refused(self) -> None:
        intent = CommandIntent(
            kind=CommandKind.READ,
            issuer="scada",
            target="plc_outlet",
            address=999,
            quantity=1,
            values=(),
            reason="hand-built",
        )
        with pytest.raises(ValueError, match="no register block"):
            modbus_frames(water.WATER_DESCRIPTION, [self._step(intent)])

    @pytest.mark.parametrize(
        ("jitter", "delay", "message"),
        [
            (-1.0, (1.0, 2.0), "jitter cannot be negative"),
            (1.0, (-1.0, 2.0), "not usable"),
            (1.0, (5.0, 2.0), "not usable"),
        ],
    )
    def test_a_timing_policy_that_cannot_produce_plausible_frames_is_refused(
        self, jitter: float, delay: tuple[float, float], message: str
    ) -> None:
        with pytest.raises(ValueError, match=message):
            TrafficPolicy(poll_jitter_ms=jitter, response_delay_ms=delay)


def dissect(path: Path, stats: CaptureStats | None = None) -> list[DissectionResult]:
    """Dissect a capture with the real registry, returning every result.

    Typed as the dissector's own union rather than narrowed to what a correct capture produces —
    narrowing it would make the assertions that *nothing* came back malformed or unparsed
    unreachable, which is to say it would delete them.
    """
    return list(dissect_capture(path, REGISTRY, stats))


def test_the_server_port_is_the_registered_modbus_one() -> None:
    assert MODBUS_PORT == 502

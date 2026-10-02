"""The non-empty dropout path in `modbus_frames`, which the identity proof never exercises.

Two transport-model decisions, pinned here and recorded in ADR 0078:

1. A dropped exchange still consumes its conversation's Modbus transaction id. The plant issued
   the command; the network lost it. Empty dropout sets stay byte-identical either way; this
   choice is the implemented order (id allocated before the dropout is consulted).
2. A whole-segment dropout does not suppress the TCP handshake of a connection first opened
   during it. `_conversation_for` emits the handshake before dropouts are consulted. The dropout
   covers Modbus request/response PDUs, not TCP connection setup.
"""

from __future__ import annotations

import struct
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from phos.synth.plant import RunSpec
from phos.synth.realism import CommsDropout
from phos.synth.run import PlantRun, run_plant
from phos.synth.traffic import TrafficPolicy, WireFrame, modbus_frames

START = datetime(2026, 3, 1, tzinfo=UTC)
_SYN = 0x02
_PLC_INLET = "plc_inlet"
_PLC_INLET_IP = "10.30.0.21"


def _water_run(hours: float = 2.0, seed: int = 11) -> PlantRun:
    """Return a quiet water-treatment run at 30-second sampling."""
    spec = RunSpec(
        seed=seed,
        start=START,
        duration=timedelta(hours=hours),
        sample_interval=timedelta(seconds=30),
    )
    return run_plant("water-treatment", spec)


def _frames(run: PlantRun, dropouts: Sequence[CommsDropout] = ()) -> tuple[WireFrame, ...]:
    """Render ``run`` with ``dropouts`` under the probe's traffic policy."""
    return modbus_frames(run.description, run.steps, TrafficPolicy(seed=1), dropouts=dropouts)


def _window() -> tuple[datetime, datetime]:
    """Return the first twenty minutes of the probe run."""
    return START, START + timedelta(minutes=20)


def _in_window(frame: WireFrame) -> bool:
    began, ended = _window()
    return began <= frame.timestamp <= ended


def _is_syn(frame: WireFrame) -> bool:
    return bool(frame.flags & _SYN) and not frame.payload


def _is_pdu(frame: WireFrame) -> bool:
    return bool(frame.payload)


def _touches(frame: WireFrame, ip: str) -> bool:
    return frame.src_ip == ip or frame.dst_ip == ip


def _transaction_id(frame: WireFrame) -> int:
    assert frame.payload, "handshake frames have no transaction id"
    return int(struct.unpack_from(">H", frame.payload)[0])


def _seqs_never_go_backwards(frames: Sequence[WireFrame]) -> None:
    last: dict[tuple[str, int, str, int], int] = {}
    for frame in frames:
        key = (frame.src_ip, frame.src_port, frame.dst_ip, frame.dst_port)
        previous = last.get(key)
        if previous is not None:
            assert frame.seq >= previous
        last[key] = frame.seq


def _uncovered_identical(
    baseline: Sequence[WireFrame], other: Sequence[WireFrame], ip: str
) -> None:
    left = [f for f in baseline if not _touches(f, ip)]
    right = [f for f in other if not _touches(f, ip)]
    assert left == right


class TestEmptyDropoutPath:
    def test_passing_an_empty_tuple_matches_passing_nothing(self) -> None:
        run = _water_run()
        assert _frames(run) == _frames(run, dropouts=())

    def test_a_plant_with_no_control_network_yields_no_frames(self) -> None:
        spec = RunSpec(
            seed=11, start=START, duration=timedelta(hours=2), sample_interval=timedelta(seconds=30)
        )
        run = run_plant("batch-reactor", spec)
        dropout = CommsDropout(*_window(), node_id=None, retransmits=False)
        assert _frames(run, dropouts=(dropout,)) == ()


class TestNamedNodeDropout:
    def test_retransmits_false_sends_no_pdu_to_the_node_inside_the_window(self) -> None:
        run = _water_run()
        dropout = CommsDropout(*_window(), node_id=_PLC_INLET, retransmits=False)
        frames = _frames(run, dropouts=(dropout,))
        inside = [f for f in frames if _in_window(f) and _touches(f, _PLC_INLET_IP) and _is_pdu(f)]
        assert inside == []

    def test_retransmits_true_sends_no_pdu_inside_the_window_then_a_burst(self) -> None:
        run = _water_run()
        none = _frames(run)
        dropout = CommsDropout(*_window(), node_id=_PLC_INLET, retransmits=True)
        dropped = _frames(run, dropouts=(dropout,))
        inside = [f for f in dropped if _in_window(f) and _touches(f, _PLC_INLET_IP) and _is_pdu(f)]
        assert inside == []
        burst_end = _window()[1] + timedelta(seconds=30)
        burst = [
            f
            for f in dropped
            if (
                _window()[1] <= f.timestamp <= burst_end
                and _touches(f, _PLC_INLET_IP)
                and _is_pdu(f)
            )
        ]
        quiet = [
            f
            for f in none
            if (
                _window()[1] <= f.timestamp <= burst_end
                and _touches(f, _PLC_INLET_IP)
                and _is_pdu(f)
            )
        ]
        assert len(burst) > len(quiet)
        requests_dropped = sum(
            1
            for f in dropped
            if _touches(f, _PLC_INLET_IP) and f.dst_ip == _PLC_INLET_IP and _is_pdu(f)
        )
        requests_none = sum(
            1
            for f in none
            if _touches(f, _PLC_INLET_IP) and f.dst_ip == _PLC_INLET_IP and _is_pdu(f)
        )
        assert requests_dropped == requests_none

    def test_a_named_node_leaves_other_connections_byte_identical(self) -> None:
        run = _water_run()
        none = _frames(run)
        dropout = CommsDropout(*_window(), node_id=_PLC_INLET, retransmits=False)
        dropped = _frames(run, dropouts=(dropout,))
        _uncovered_identical(none, dropped, _PLC_INLET_IP)

    def test_sequence_numbers_never_go_backwards(self) -> None:
        run = _water_run()
        for retransmits in (False, True):
            dropout = CommsDropout(*_window(), node_id=_PLC_INLET, retransmits=retransmits)
            _seqs_never_go_backwards(_frames(run, dropouts=(dropout,)))


class TestTransportModelDecisions:
    def test_a_dropped_exchange_still_consumes_its_transaction_id(self) -> None:
        """Decision 1: ids are allocated per plant-made exchange, including lost ones."""
        run = _water_run()
        none = _frames(run)
        dropout = CommsDropout(*_window(), node_id=_PLC_INLET, retransmits=False)
        dropped = _frames(run, dropouts=(dropout,))
        first_after = next(
            f
            for f in dropped
            if f.timestamp > _window()[1] and f.dst_ip == _PLC_INLET_IP and _is_pdu(f)
        )
        counterpart = next(
            f
            for f in none
            if f.timestamp == first_after.timestamp
            and f.dst_ip == _PLC_INLET_IP
            and f.src_port == first_after.src_port
            and _is_pdu(f)
        )
        # The first request after the window carries the same id it has with no dropout,
        # so the ids of lost exchanges were consumed rather than reused.
        assert _transaction_id(first_after) == _transaction_id(counterpart)

    def test_a_whole_segment_dropout_still_emits_the_handshake_of_a_new_connection(self) -> None:
        """Decision 2: TCP setup is not covered; Modbus PDUs are."""
        run = _water_run()
        dropout = CommsDropout(*_window(), node_id=None, retransmits=False)
        frames = _frames(run, dropouts=(dropout,))
        inside_pdu = [f for f in frames if _in_window(f) and _is_pdu(f)]
        inside_syn = [f for f in frames if _in_window(f) and _is_syn(f)]
        assert inside_pdu == []
        assert inside_syn  # at least the handshake of a connection first opened during it
        _seqs_never_go_backwards(frames)

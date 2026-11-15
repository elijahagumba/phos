"""The network-layer manipulations act on the capture, leave the plant alone, and still parse.

PART R4 asks that each new event type acts on the correct layer, that its labels match its
intervals, and that the output stays valid. For the wire layer "valid" has a sharp meaning: the
manipulated capture must still go through `phos.atlas.packet.dissect_capture` — the real dissector,
unchanged — so the two claims checked hardest here are that a tampered or flooded or replayed
capture parses, and that the telemetry the same run produced is untouched by any of it.

The last is the whole character of this layer and the reason it is worth having: an in-transit
change makes the wire disagree with the historian, and a test that did not pin the historian as
unchanged would not be testing that at all.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from phos.atlas.packet import DissectorRegistry, MalformedFrame, ModbusMessage, dissect_capture
from phos.atlas.packet.modbus import ModbusDissector
from phos.synth.families import get_family
from phos.synth.injection import TimeWindow
from phos.synth.plant import RunSpec
from phos.synth.plant_spec import PlantSpec
from phos.synth.templates import build_from_spec
from phos.synth.traffic import TrafficPolicy, WireFrame, modbus_frames, write_pcap
from phos.synth.validity import Thresholds, draw_valid
from phos.synth.wire import (
    InTransitChange,
    PollBurst,
    TrafficReplay,
    WireError,
    apply_wire_events,
    polled_values_in,
)

FAST = Thresholds(hours=2.0)
START = datetime(2026, 11, 13, tzinfo=UTC)
REGISTRY = DissectorRegistry([ModbusDissector()])


@pytest.fixture(scope="module")
def spec() -> PlantSpec:
    """A plant that speaks Modbus, so it has a capture to manipulate."""
    return draw_valid(get_family("level_flow"), 74_000, FAST).spec


@pytest.fixture(scope="module")
def run(spec: PlantSpec) -> RunSpec:
    return RunSpec(
        seed=11,
        start=START,
        duration=timedelta(hours=6),
        sample_interval=timedelta(seconds=spec.scan_period_seconds or 30.0),
    )


@pytest.fixture(scope="module")
def frames(spec: PlantSpec, run: RunSpec) -> tuple[WireFrame, ...]:
    """A normal capture of the plant, before anything touches it."""
    plant = build_from_spec(spec, run)
    steps = tuple(plant.step(None) for _ in range(run.n_steps))
    return modbus_frames(spec.describe(), steps, TrafficPolicy(seed=1))


def _window(run: RunSpec, start_hours: float, minutes: float) -> TimeWindow:
    """Return a window inside the run, by hours from its start."""
    start = run.start + timedelta(hours=start_hours)
    return TimeWindow(start=start, end=start + timedelta(minutes=minutes))


def _dissect(frames: tuple[WireFrame, ...], tmp_path: Path) -> list[object]:
    """Write a capture and read it back through the real dissector."""
    path = tmp_path / "capture.pcap"
    write_pcap(frames, path)
    return list(dissect_capture(path, REGISTRY))


def test_no_manipulations_leave_the_capture_identical(frames: tuple[WireFrame, ...]) -> None:
    """What keeps a corpus with no wire events byte-identical to one from before they existed."""
    assert apply_wire_events(frames) == frames


# --------------------------------------------------------------------------------------------
# in-transit change
# --------------------------------------------------------------------------------------------


def test_an_in_transit_change_holds_one_block_inside_its_window(
    spec: PlantSpec, run: RunSpec, frames: tuple[WireFrame, ...]
) -> None:
    window = _window(run, 1.0, 30.0)
    address = spec.control_network.blocks[0].start_address  # type: ignore[union-attr]

    changed = apply_wire_events(
        frames, changes=[InTransitChange(window=window, address=address, held_count=42000)]
    )

    held = sum(1 for registers in polled_values_in(changed, window) if registers[:1] == (42000,))
    after = _window(run, 1.6, 30.0)
    held_after = sum(
        1 for registers in polled_values_in(changed, after) if registers[:1] == (42000,)
    )

    assert held > 0, "the targeted block's responses were not altered"
    assert held_after == 0, "the change leaked past its window"
    assert len(changed) == len(frames), "a rewrite changes payloads, not the number of frames"


def test_an_in_transit_change_leaves_the_other_blocks_alone(
    spec: PlantSpec, run: RunSpec, frames: tuple[WireFrame, ...]
) -> None:
    """One false meter, not every meter on the device: the tell is that it disagrees alone."""
    window = _window(run, 1.0, 30.0)
    address = spec.control_network.blocks[0].start_address  # type: ignore[union-attr]

    changed = apply_wire_events(
        frames, changes=[InTransitChange(window=window, address=address, held_count=42000)]
    )

    in_window = polled_values_in(changed, window)
    unheld = [registers for registers in in_window if registers[:1] != (42000,)]
    assert unheld, "every response was rewritten; the change was not confined to one block"


def test_a_tampered_capture_still_dissects(
    spec: PlantSpec, run: RunSpec, frames: tuple[WireFrame, ...], tmp_path: Path
) -> None:
    window = _window(run, 1.0, 30.0)
    address = spec.control_network.blocks[0].start_address  # type: ignore[union-attr]
    changed = apply_wire_events(
        frames, changes=[InTransitChange(window=window, address=address, held_count=5)]
    )

    messages = _dissect(changed, tmp_path)

    assert messages
    assert not [message for message in messages if isinstance(message, MalformedFrame)]


def test_a_count_that_is_not_a_register_value_is_refused() -> None:
    window = TimeWindow(start=START, end=START + timedelta(hours=1))

    with pytest.raises(WireError, match="16-bit"):
        InTransitChange(window=window, address=0, held_count=70000)


# --------------------------------------------------------------------------------------------
# poll burst
# --------------------------------------------------------------------------------------------


def test_a_poll_burst_adds_requests_and_the_plant_readings_are_untouched(
    spec: PlantSpec, run: RunSpec, frames: tuple[WireFrame, ...]
) -> None:
    window = _window(run, 2.0, 20.0)
    address = spec.control_network.blocks[0].start_address  # type: ignore[union-attr]

    flooded = apply_wire_events(
        frames, bursts=[PollBurst(window=window, count=300, template_address=address)]
    )

    assert len(flooded) == len(frames) + 300
    # the readings already on the wire are not altered by adding requests beside them
    before = polled_values_in(frames, window)
    after = polled_values_in(flooded, window)
    assert after[: len(before)] == before


def test_a_flooded_capture_still_dissects(
    spec: PlantSpec, run: RunSpec, frames: tuple[WireFrame, ...], tmp_path: Path
) -> None:
    window = _window(run, 2.0, 20.0)
    address = spec.control_network.blocks[0].start_address  # type: ignore[union-attr]
    flooded = apply_wire_events(
        frames, bursts=[PollBurst(window=window, count=300, template_address=address)]
    )

    messages = _dissect(flooded, tmp_path)

    assert not [message for message in messages if isinstance(message, MalformedFrame)]
    reads = [
        message
        for message in messages
        if isinstance(message, ModbusMessage) and message.reference_address == address
    ]
    assert len(reads) > 300, "the injected reads are not in the dissected capture"


def test_a_burst_with_no_conversation_to_borrow_does_nothing(frames: tuple[WireFrame, ...]) -> None:
    """There is no device to flood if nobody was talking to one in the window."""
    empty = TimeWindow(start=START - timedelta(days=1), end=START - timedelta(hours=23))

    assert (
        apply_wire_events(frames, bursts=[PollBurst(window=empty, count=50, template_address=0)])
        == frames
    )


def test_a_burst_of_nothing_is_refused() -> None:
    window = TimeWindow(start=START, end=START + timedelta(hours=1))

    with pytest.raises(WireError, match="injects nothing"):
        PollBurst(window=window, count=0, template_address=0)


# --------------------------------------------------------------------------------------------
# traffic replay
# --------------------------------------------------------------------------------------------


def test_a_replay_copies_a_window_to_a_later_time(
    run: RunSpec, frames: tuple[WireFrame, ...]
) -> None:
    source = _window(run, 0.5, 15.0)
    destination = _window(run, 3.0, 15.0)
    in_source = sum(1 for frame in frames if source.contains(frame.timestamp))

    replayed = apply_wire_events(frames, replays=[TrafficReplay(source=source, at=destination)])

    assert len(replayed) == len(frames) + in_source
    # the copies carry the source window's own bytes, placed at the destination
    copied = [
        frame for frame in replayed if destination.contains(frame.timestamp) and frame not in frames
    ]
    assert len(copied) == in_source


def test_a_replayed_capture_still_dissects(
    run: RunSpec, frames: tuple[WireFrame, ...], tmp_path: Path
) -> None:
    source = _window(run, 0.5, 15.0)
    destination = _window(run, 3.0, 15.0)
    replayed = apply_wire_events(frames, replays=[TrafficReplay(source=source, at=destination)])

    messages = _dissect(replayed, tmp_path)

    assert not [message for message in messages if isinstance(message, MalformedFrame)], (
        "replayed frames reuse sequence numbers, and the dissector does no reassembly, so they "
        "must still decode"
    )


def test_a_replay_into_its_own_source_is_refused() -> None:
    source = TimeWindow(start=START, end=START + timedelta(hours=1))
    inside = TimeWindow(start=START + timedelta(minutes=30), end=START + timedelta(minutes=45))

    with pytest.raises(WireError, match="inside the window it copies"):
        TrafficReplay(source=source, at=inside)


def test_a_replay_of_an_empty_window_does_nothing(
    run: RunSpec, frames: tuple[WireFrame, ...]
) -> None:
    empty = TimeWindow(start=START - timedelta(days=1), end=START - timedelta(hours=23))
    destination = _window(run, 3.0, 15.0)

    assert (
        apply_wire_events(frames, replays=[TrafficReplay(source=empty, at=destination)]) == frames
    )


# --------------------------------------------------------------------------------------------
# all three together, and the telemetry underneath
# --------------------------------------------------------------------------------------------


def test_the_capture_can_disagree_with_the_telemetry_which_is_the_point(
    spec: PlantSpec, run: RunSpec, frames: tuple[WireFrame, ...]
) -> None:
    """The plant produced the frames; the wire layer changed them; the plant did not change.

    `frames` came from a run of the plant. Manipulating them cannot reach back and alter that run,
    so the telemetry the same run would write is exactly what it was. The wire and the historian
    now say different things, and a detector comparing them is the only thing that can tell.
    """
    window = _window(run, 1.0, 30.0)
    address = spec.control_network.blocks[0].start_address  # type: ignore[union-attr]

    manipulated = apply_wire_events(
        frames,
        changes=[InTransitChange(window=window, address=address, held_count=1)],
        bursts=[PollBurst(window=window, count=50, template_address=address)],
        replays=[TrafficReplay(source=_window(run, 0.2, 10.0), at=_window(run, 4.0, 10.0))],
    )

    # the capture changed
    assert manipulated != frames
    # a fresh run of the same plant is identical to the one frames came from: untouched
    plant = build_from_spec(spec, run)
    again = modbus_frames(
        spec.describe(),
        tuple(plant.step(None) for _ in range(run.n_steps)),
        TrafficPolicy(seed=1),
    )
    assert again == frames

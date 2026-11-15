"""A generated plant goes in through the same doors a downloaded corpus does.

PART R3's two load-bearing claims, and they are about Atlas rather than about the generator:

* the telemetry loads through `phos.eval.LabelledCsvAdapter` — the adapter a prepared CSV from HAI
  goes through — with no special case for synthetic data;
* the capture parses through `phos.atlas.packet.dissect_capture` with the real Modbus dissector,
  without one malformed frame, and **every register the poller read carries the value the
  telemetry published for that signal**, to within the quantisation an industrial device imposes.

The second is the one worth the most. The capture and the telemetry are two projections of one
simulated run, so if they disagreed about what the plant said, a detector that watched the wire
and the historian would be right to distrust both — and nothing else in the suite would notice.

Neither test modifies Atlas or imports anything but its public entry points.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from phos.atlas.packet import DissectorRegistry, MalformedFrame, ModbusMessage, dissect_capture
from phos.atlas.packet.modbus import ModbusDissector
from phos.eval.datasets import LabelledCsvAdapter
from phos.synth.families import get_family
from phos.synth.outputs import (
    CAPTURE_FILE,
    CONTROL_FILE,
    LABELS_FILE,
    MANIFEST_FILE,
    PLANT_FILE,
    REGISTERS_FILE,
    TELEMETRY_FILE,
    TOPOLOGY_FILE,
    GeneratedPlant,
    OutputError,
    generate_plant,
    verify,
)
from phos.synth.plant import register_count
from phos.synth.plant_spec import PlantSpec
from phos.synth.telemetry import LABEL_COLUMN, TIMESTAMP_COLUMN
from phos.synth.topology import subsystems, subsystems_from_components
from phos.synth.validity import Thresholds

FAST = Thresholds(hours=2.0)
REGISTRY = DissectorRegistry([ModbusDissector()])
HOURS = 3.0


@pytest.fixture(scope="module")
def plant(tmp_path_factory: pytest.TempPathFactory) -> GeneratedPlant:
    """One generated plant on disk, shared: generating it is the slow part."""
    directory = tmp_path_factory.mktemp("plants")
    return generate_plant(get_family("level_flow"), 61_000, directory, hours=HOURS, thresholds=FAST)


def test_every_file_the_part_asks_for_is_written(plant: GeneratedPlant) -> None:
    written = {file.filename for file in plant.manifest.files}

    assert written == {
        TELEMETRY_FILE,
        LABELS_FILE,
        TOPOLOGY_FILE,
        PLANT_FILE,
        CONTROL_FILE,
        REGISTERS_FILE,
        CAPTURE_FILE,
    }
    for filename in written | {MANIFEST_FILE}:
        assert (plant.directory / filename).exists()


def test_the_manifest_hashes_verify(plant: GeneratedPlant) -> None:
    assert verify(plant.directory) == []


def test_a_single_flipped_byte_is_caught(plant: GeneratedPlant, tmp_path: Path) -> None:
    """Otherwise the digests are decoration."""
    copy = tmp_path / "copy"
    copy.mkdir()
    for file in (
        *plant.manifest.files,
        type(plant.manifest.files[0])(
            filename=MANIFEST_FILE, kind="manifest-json", records=0, sha256="0" * 64, size_bytes=0
        ),
    ):
        (copy / file.filename).write_bytes((plant.directory / file.filename).read_bytes())
    telemetry = copy / TELEMETRY_FILE
    raw = bytearray(telemetry.read_bytes())
    raw[-3] = raw[-3] ^ 0x01
    telemetry.write_bytes(bytes(raw))

    problems = verify(copy)

    assert any(TELEMETRY_FILE in problem for problem in problems), problems


def test_a_directory_with_no_manifest_is_a_different_problem(tmp_path: Path) -> None:
    with pytest.raises(OutputError, match=r"holds no manifest\.json"):
        verify(tmp_path)


def test_the_manifest_records_the_whole_regeneration_recipe(plant: GeneratedPlant) -> None:
    manifest = plant.manifest

    assert manifest.family_id == "level_flow"
    assert manifest.master_seed == 61_000
    assert manifest.child_seed in (61_000, plant.draw.child_seed)
    assert manifest.rejections == plant.draw.rejection_count
    assert len(manifest.rejection_reasons) == manifest.rejections
    assert manifest.parameters, "the drawn parameters have to be readable without redrawing"
    assert manifest.validity_hours == FAST.hours
    assert manifest.samples > 0
    assert any("MODEL" in caveat or "simulat" in caveat.lower() for caveat in manifest.caveats)


def test_the_telemetry_loads_through_atlas_own_ingest_path(plant: GeneratedPlant) -> None:
    """The adapter a prepared HAI CSV goes through, with no special case for synthetic data."""
    loaded = LabelledCsvAdapter(
        path=plant.directory / TELEMETRY_FILE,
        timestamp_column=TIMESTAMP_COLUMN,
        label_column=LABEL_COLUMN,
    ).load()

    declared = set(plant.manifest.description.signal_keys())
    assert {observation.feature for observation in loaded.observations} == declared
    assert len(loaded.observations) == plant.manifest.samples * len(declared)
    assert loaded.attack_intervals == [], "PART R3 generates no attacks"


def test_the_capture_parses_without_one_malformed_frame(plant: GeneratedPlant) -> None:
    results = list(dissect_capture(plant.directory / CAPTURE_FILE, REGISTRY))

    assert results, "a plant with a control network must produce traffic"
    malformed = [result for result in results if isinstance(result, MalformedFrame)]
    assert malformed == [], f"{len(malformed)} malformed frame(s)"


def test_every_polled_register_carries_what_the_telemetry_published(
    plant: GeneratedPlant,
) -> None:
    """The claim that stops the wire and the historian disagreeing about one plant.

    A read request carries the address and its response carries the values, so the two are paired
    by the conversation *and* the MBAP transaction identifier — a capture with a PLC per train has
    several conversations in flight, and the identifier is only unique within one of them. Pairing
    on the identifier alone silently mixed the trains up and reported 945 mismatches out of 8344.
    """
    spec = PlantSpec.from_json((plant.directory / PLANT_FILE).read_text(encoding="utf-8"))
    description = spec.describe()
    network = spec.control_network
    assert network is not None
    by_address = {
        block.start_address + offset: key
        for block in network.blocks
        for offset, key in enumerate(block.signals)
    }

    with (plant.directory / TELEMETRY_FILE).open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    published = {
        key: {register_count(description.signal(key), float(row[key])) for row in rows}
        for key in description.signal_keys()
    }

    pending: dict[tuple[str, str, int], int] = {}
    checked = 0
    for message in dissect_capture(plant.directory / CAPTURE_FILE, REGISTRY):
        if not isinstance(message, ModbusMessage):
            continue
        conversation = (str(message.src), str(message.dst), message.transaction_id)
        if message.reference_address is not None and not message.values:
            pending[conversation] = message.reference_address
            continue
        base = pending.pop((str(message.dst), str(message.src), message.transaction_id), None)
        if base is None or not message.values:
            continue
        for offset, raw in enumerate(message.values):
            key = by_address.get(base + offset)
            if key is None or not published[key]:
                continue
            checked += 1
            # Within one count: the capture encodes the full-precision reported value and the CSV
            # holds it rounded to five decimals, so the two can land either side of a boundary.
            assert any(abs(raw - count) <= 1 for count in published[key]), (
                f"{key} was polled as {raw}, which is no value the telemetry published"
            )

    assert checked == plant.manifest.samples * len(description.signal_keys()), (
        "every published reading should be polled exactly once"
    )


def test_the_topology_groups_the_plant_by_its_own_structure(plant: GeneratedPlant) -> None:
    spec = PlantSpec.from_json((plant.directory / PLANT_FILE).read_text(encoding="utf-8"))

    assert subsystems_from_components(spec) == subsystems(spec.describe())


def test_the_plant_document_rebuilds_the_plant(plant: GeneratedPlant) -> None:
    rebuilt = PlantSpec.from_json((plant.directory / PLANT_FILE).read_text(encoding="utf-8"))

    assert rebuilt.describe() == plant.manifest.description
    assert dict(rebuilt.parameters) == dict(plant.manifest.parameters)


def test_the_labels_say_what_legitimately_happened(plant: GeneratedPlant) -> None:
    document = json.loads((plant.directory / LABELS_FILE).read_text(encoding="utf-8"))

    assert document["attack_intervals"] == []
    assert len(document["benign_events"]) == len(plant.manifest.events)
    for event in document["benign_events"]:
        assert event["kind"] and event["started_at"] <= event["ended_at"]
    assert document["caveats"]


def test_the_control_export_describes_every_loop_and_every_role(plant: GeneratedPlant) -> None:
    spec = PlantSpec.from_json((plant.directory / PLANT_FILE).read_text(encoding="utf-8"))
    document = json.loads((plant.directory / CONTROL_FILE).read_text(encoding="utf-8"))

    assert {loop["id"] for loop in document["loops"]} == {
        controller.controller_id for controller in spec.controllers
    }
    assert set(document["roles"]) == set(spec.roles)
    for loop in document["loops"]:
        assert loop["description"], f"{loop['id']} has no plain-language description"
        assert loop["target"]["kind"] in ("setpoint_signal", "fixed", "cascade")
    assert document["scan_period_seconds"] == spec.scan_period_seconds


def test_the_register_map_covers_the_wire_and_carries_the_spans(plant: GeneratedPlant) -> None:
    spec = PlantSpec.from_json((plant.directory / PLANT_FILE).read_text(encoding="utf-8"))
    document = json.loads((plant.directory / REGISTERS_FILE).read_text(encoding="utf-8"))
    network = spec.control_network
    assert network is not None

    mapped = {
        entry["address"]: entry
        for block in document["control_network"]["blocks"]
        for entry in block["registers"]
    }
    expected = {
        block.start_address + offset: key
        for block in network.blocks
        for offset, key in enumerate(block.signals)
    }
    assert set(mapped) == set(expected)
    for address, key in expected.items():
        entry = mapped[address]
        assert entry["signal"] == key
        assert entry["role"], f"{key} has no role in the register map"
        # Without the span a reader of the capture cannot turn a count back into a value.
        assert entry["span_low"] < entry["span_high"]
        assert entry["count_at_low"] == 0
        assert entry["count_at_high"] == 65535


def test_regeneration_is_byte_identical(tmp_path: Path) -> None:
    """Same family, same seed, same files — which is what makes storing them unnecessary."""
    first = generate_plant(
        get_family("thermal"), 61_001, tmp_path / "a", hours=2.0, thresholds=FAST
    )
    second = generate_plant(
        get_family("thermal"), 61_001, tmp_path / "b", hours=2.0, thresholds=FAST
    )

    assert {file.filename: file.sha256 for file in first.manifest.files} == {
        file.filename: file.sha256 for file in second.manifest.files
    }
    for file in first.manifest.files:
        assert (first.directory / file.filename).read_bytes() == (
            second.directory / file.filename
        ).read_bytes()


def test_a_plant_with_no_control_network_writes_no_capture_and_says_so(tmp_path: Path) -> None:
    """Not every process is run over something Atlas can dissect, and that is a statement."""
    generated = generate_plant(
        get_family("batch_mix"), 61_002, tmp_path, hours=2.0, thresholds=FAST, with_capture=True
    )
    document = json.loads((generated.directory / REGISTERS_FILE).read_text(encoding="utf-8"))

    if generated.manifest.description.control_network is None:
        assert not (generated.directory / CAPTURE_FILE).exists()
        assert document["control_network"] is None
        assert "not a missing output" in document["note"]
    else:
        assert (generated.directory / CAPTURE_FILE).exists()


def test_a_run_holding_no_samples_is_refused_rather_than_written(tmp_path: Path) -> None:
    """Refused, and refused as an output problem.

    A header row and no data loads without error and scores as a corpus where nothing went wrong,
    which is the most expensive kind of silence a measurement pipeline can hold. `RunSpec` is
    what catches it; this asserts the refusal reaches the caller as an `OutputError` rather than
    as a pydantic stack trace, because the command line reports the one and not the other.
    """
    with pytest.raises(OutputError, match="is not a run"):
        generate_plant(
            get_family("level_flow"),
            61_003,
            tmp_path,
            hours=0.0001,
            sample_interval_seconds=3600.0,
            thresholds=FAST,
        )


def test_the_command_line_lists_generates_and_verifies(tmp_path: Path) -> None:
    """The three verbs PART R3 asks for, plus the one that checks what they wrote."""
    from scripts.generate_plants import main

    assert main(["list-families"]) == 0
    assert (
        main(
            [
                "generate",
                "level_flow",
                "61004",
                "--hours",
                "2",
                "--validity-hours",
                "2",
                "--out",
                str(tmp_path),
            ]
        )
        == 0
    )
    written = sorted(path.name for path in tmp_path.iterdir())
    assert written == ["level-flow-61004"]
    assert main(["verify", str(tmp_path / "level-flow-61004")]) == 0


def test_the_command_line_refuses_a_family_it_does_not_have(tmp_path: Path) -> None:
    """Including a sealed one, which it reports exactly as one that does not exist."""
    from scripts.generate_plants import main

    assert main(["generate", "not_a_family", "1", "--out", str(tmp_path)]) == 2
    assert main(["generate", "gas_pressure", "1", "--out", str(tmp_path)]) == 2
    assert not list(tmp_path.iterdir())


# --------------------------------------------------------------------------------------------
# PART R4: a corpus can carry events, across all four layers
# --------------------------------------------------------------------------------------------


def _event_catalogue() -> object:
    """One of each layer, short enough to fit a day while leaving most of it normal."""
    from phos.synth.events import EventCatalogue

    return EventCatalogue(
        sensor_replays=1,
        stuck_valves=1,
        pump_trips=1,
        leaks=1,
        sensors_offline=1,
        valves_exercised=1,
        in_transit_changes=1,
        poll_bursts=1,
        traffic_replays=1,
        event_minutes=(12.0, 25.0),
    )


@pytest.fixture(scope="module")
def disturbed(tmp_path_factory: pytest.TempPathFactory) -> GeneratedPlant:
    """A generated corpus that carries events on every layer."""
    directory = tmp_path_factory.mktemp("events")
    return generate_plant(
        get_family("level_flow"),
        62_100,
        directory,
        hours=24.0,
        thresholds=FAST,
        events=_event_catalogue(),  # type: ignore[arg-type]
        event_seed=7,
    )


def test_a_corpus_with_events_still_verifies(disturbed: GeneratedPlant) -> None:
    assert verify(disturbed.directory) == []


def test_the_labels_carry_the_scripted_events_across_layers(disturbed: GeneratedPlant) -> None:
    document = json.loads((disturbed.directory / LABELS_FILE).read_text(encoding="utf-8"))
    scripted = document["scripted_events"]

    layers = {event["layer"] for event in scripted}
    assert {"sensor", "actuator", "process", "network"} <= layers
    kinds = {event["kind"] for event in scripted}
    assert {"attack", "fault", "maintenance"} <= kinds
    # the detection targets are the attacks and faults, not the maintenance
    target_ids = {interval["event_id"] for interval in document["attack_intervals"]}
    for event in scripted:
        if event["kind"] in ("attack", "fault"):
            assert event["event_id"] in target_ids
        if event["kind"] == "maintenance":
            assert event["event_id"] not in target_ids


def test_a_corpus_with_events_still_ingests_through_atlas(disturbed: GeneratedPlant) -> None:
    loaded = LabelledCsvAdapter(
        path=disturbed.directory / TELEMETRY_FILE,
        timestamp_column=TIMESTAMP_COLUMN,
        label_column=LABEL_COLUMN,
    ).load()

    assert len(loaded.observations) == disturbed.manifest.samples * len(
        disturbed.manifest.description.signal_keys()
    )


def test_a_capture_with_network_events_still_dissects(disturbed: GeneratedPlant) -> None:
    results = list(dissect_capture(disturbed.directory / CAPTURE_FILE, REGISTRY))

    assert results
    assert not [result for result in results if isinstance(result, MalformedFrame)], (
        "network-layer events reuse sequence numbers and inject frames, and the result must "
        "still parse through the real dissector"
    )


def test_a_corpus_with_events_regenerates_byte_identical(tmp_path: Path) -> None:
    catalogue = _event_catalogue()
    first = generate_plant(
        get_family("level_flow"),
        62_101,
        tmp_path / "a",
        hours=12.0,
        thresholds=FAST,
        events=catalogue,  # type: ignore[arg-type]
        event_seed=3,
    )
    second = generate_plant(
        get_family("level_flow"),
        62_101,
        tmp_path / "b",
        hours=12.0,
        thresholds=FAST,
        events=catalogue,  # type: ignore[arg-type]
        event_seed=3,
    )

    assert {f.filename: f.sha256 for f in first.manifest.files} == {
        f.filename: f.sha256 for f in second.manifest.files
    }


def test_a_normal_corpus_is_unchanged_by_the_events_plumbing(tmp_path: Path) -> None:
    """A corpus generated with no catalogue takes the same path as before events existed."""
    plain = generate_plant(
        get_family("level_flow"), 62_102, tmp_path / "plain", hours=6.0, thresholds=FAST
    )
    document = json.loads((plain.directory / LABELS_FILE).read_text(encoding="utf-8"))

    assert document["attack_intervals"] == []
    assert document["scripted_events"] == []

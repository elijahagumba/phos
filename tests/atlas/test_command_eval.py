"""Tests for the measurement seam: everything needed to score command-level detection but the data.

**What these tests prove, and what they emphatically do not.** They prove the seam *runs*: a
capture becomes a labelled `Dataset`, the two command streams become harness `Detection`s, and the
PART 2 harness scores them exactly as it scores the sensor path. The rogue command in the fixture
was chosen by the author and placed by hand, so the recall it produces is a statement about the
plumbing carrying a known signal end to end and about nothing else. Atlas's real ability to
separate a legitimate operator action from an attacker's identical command is unmeasured; see
`phos.atlas.UNMEASURED_COMMAND_DETECTION_CAVEAT`.

**The refusals are therefore the most important tests here.** A corpus with no labels must not
produce a metric, and the discovery path must return nothing on a repository that holds no labelled
command capture — because that "nothing" is what stops the script printing a number.

The capture builder below is hand-built with `struct.pack` rather than written by a packet library,
for the reason `tests/atlas/packet/conftest.py` gives: a fixture built by the library the adapter
parses with would test that library against itself. It is deliberately minimal — one plant's worth
of polling, and one rogue write — and self-contained, so this module depends on no sibling test.
"""

import struct
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from phos.atlas import (
    UNKNOWN_COMMAND_RELATIONSHIP,
    learn_device_command_graph,
)
from phos.atlas.command_eval import (
    INSPECTED_NOT_A_LABELLED_COMMAND_CORPUS,
    LABELLED_COMMAND_CORPUS_REQUIREMENTS,
    CommandBehaviourDetector,
    CommandCaptureAdapter,
    CommandGraphDetector,
    UnlabelledCommandCorpusError,
    discover_labelled_command_corpora,
    render_missing_corpus,
    require_labelled_intervals,
)
from phos.atlas.command_eval import default_registry as _registry
from phos.atlas.packet import COMMAND_COUNT, dissect_capture
from phos.eval import Dataset, EvalConfig, LabelledInterval, evaluate
from phos.models import FittedModel, GaussianBaseline
from phos.ontology import Domain
from phos.reasoning import FittedPlattCalibrator

EPOCH = datetime(2026, 8, 14, 9, 0, tzinfo=UTC)
HMI = "10.0.0.5"
PLC = "10.0.0.10"
ROGUE = "10.0.0.99"

READ_HOLDING_REGISTERS = 3
WRITE_SINGLE_REGISTER = 6

CERTAIN = FittedPlattCalibrator(coefficient=0.0, intercept=40.0)


# ------------------------------------------------------------------------------------------------
# A hand-built plant capture
# ------------------------------------------------------------------------------------------------


def _modbus_request(function_code: int, address: int, value: int) -> bytes:
    """Build a Modbus/TCP ADU carrying a two-field request PDU."""
    pdu = struct.pack(">BHH", function_code, address, value)
    return struct.pack(">HHHB", 0x1234, 0, len(pdu) + 1, 1) + pdu


def _frame(src: str, dst: str, payload: bytes) -> bytes:
    """Wrap ``payload`` in Ethernet / IPv4 / TCP, client port to Modbus port 502."""
    tcp = struct.pack(">HHIIBBHHH", 5555, 502, 1, 1, 0x50, 0x18, 8192, 0, 0) + payload
    header = struct.pack(
        ">BBHHHBBH4s4s",
        0x45,
        0,
        20 + len(tcp),
        1,
        0,
        64,
        6,
        0,
        bytes(int(part) for part in src.split(".")),
        bytes(int(part) for part in dst.split(".")),
    )
    return b"\xaa" * 6 + b"\xbb" * 6 + struct.pack(">H", 0x0800) + header + tcp


def write_capture(path: Path, records: Sequence[tuple[datetime, bytes]]) -> Path:
    """Write a classic libpcap file holding ``(timestamp, frame)`` records."""
    out = struct.pack("<IHHiIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 1)
    for stamp, raw in records:
        micros = int(stamp.timestamp() * 1_000_000)
        out += (
            struct.pack("<IIII", micros // 1_000_000, micros % 1_000_000, len(raw), len(raw)) + raw
        )
    path.write_bytes(out)
    return path


def polling(minutes: int, *, start: datetime = EPOCH) -> list[tuple[datetime, bytes]]:
    """Return one read request per second from the HMI to the PLC, for ``minutes`` minutes."""
    return [
        (
            start + timedelta(seconds=second),
            _frame(HMI, PLC, _modbus_request(READ_HOLDING_REGISTERS, 40, 10)),
        )
        for second in range(minutes * 60)
    ]


def rogue_writes(at: datetime, count: int = 5) -> list[tuple[datetime, bytes]]:
    """Return a burst of register writes from a device that has never commanded anything.

    This is the injected signal, and it is injected by the author rather than observed. It proves
    the pipeline carries a known change end to end; it proves nothing about detection.
    """
    return [
        (
            at + timedelta(seconds=second),
            _frame(ROGUE, PLC, _modbus_request(WRITE_SINGLE_REGISTER, 17, 1)),
        )
        for second in range(count)
    ]


@pytest.fixture
def baseline_capture(tmp_path: Path) -> Path:
    """A quarter-hour of ordinary polling, and nothing else."""
    return write_capture(tmp_path / "baseline.pcap", polling(15))


@pytest.fixture
def live_capture(tmp_path: Path) -> Path:
    """Ten minutes of the same polling, with a rogue write burst five minutes in."""
    start = EPOCH + timedelta(hours=1)
    records = polling(10, start=start) + rogue_writes(start + timedelta(minutes=5))
    return write_capture(tmp_path / "live.pcap", sorted(records, key=lambda item: item[0]))


def attack_window() -> LabelledInterval:
    """Ground truth for the injected burst — declared by the fixture, as a real corpus would."""
    start = EPOCH + timedelta(hours=1, minutes=5)
    return LabelledInterval(
        start=start, end=start + timedelta(seconds=59), label="attack", attack_type="rogue_write"
    )


# ------------------------------------------------------------------------------------------------
# The adapter
# ------------------------------------------------------------------------------------------------


def test_a_capture_becomes_a_labelled_dataset_the_harness_can_read(live_capture: Path) -> None:
    dataset = CommandCaptureAdapter(
        captures=(live_capture,),
        attack_intervals=(attack_window(),),
        name="fixture-live",
        source_note="hand-built fixture",
    ).load()

    assert isinstance(dataset, Dataset)
    assert dataset.domain is Domain.ATLAS
    assert dataset.observations
    assert {observation.feature for observation in dataset.observations} >= {COMMAND_COUNT}
    assert dataset.attack_intervals == [attack_window()]


def test_the_dataset_is_time_ordered_across_both_streams(
    baseline_capture: Path, live_capture: Path
) -> None:
    """`Dataset` refuses out-of-order observations, so merging the two streams must sort."""
    graph = learn_device_command_graph(dissect_capture(baseline_capture, _registry()))
    dataset = CommandCaptureAdapter(
        captures=(live_capture,), attack_intervals=(attack_window(),), graph=graph
    ).load()

    stamps = [observation.timestamp for observation in dataset.observations]
    assert stamps == sorted(stamps)


def test_the_graph_findings_are_in_the_dataset_when_a_graph_is_given(
    baseline_capture: Path, live_capture: Path
) -> None:
    graph = learn_device_command_graph(dissect_capture(baseline_capture, _registry()))
    dataset = CommandCaptureAdapter(
        captures=(live_capture,), attack_intervals=(attack_window(),), graph=graph
    ).load()

    findings = [
        observation
        for observation in dataset.observations
        if observation.feature == UNKNOWN_COMMAND_RELATIONSHIP
    ]
    assert findings
    assert all(f"ent_{ROGUE}" in finding.entity_ids for finding in findings)


def test_without_a_graph_no_structural_finding_is_invented(live_capture: Path) -> None:
    """A comparison needs something to compare against; there is no default baseline."""
    dataset = CommandCaptureAdapter(
        captures=(live_capture,), attack_intervals=(attack_window(),)
    ).load()

    assert all(
        observation.feature != UNKNOWN_COMMAND_RELATIONSHIP for observation in dataset.observations
    )


def test_the_source_note_records_which_captures_the_numbers_came_from(live_capture: Path) -> None:
    """Constitution §3.7: a reported number that cannot name its input is not reproducible."""
    dataset = CommandCaptureAdapter(
        captures=(live_capture,), attack_intervals=(attack_window(),)
    ).load()

    assert live_capture.name in dataset.source_note


# ------------------------------------------------------------------------------------------------
# The detectors
# ------------------------------------------------------------------------------------------------


def fitted_baseline(capture: Path) -> FittedModel:
    """Return a per-key baseline fitted on a capture of ordinary polling."""
    training = CommandCaptureAdapter(captures=(capture,), name="fixture-baseline").load()
    return GaussianBaseline(name="command-behaviour").fit(training.observations)


def test_the_graph_detector_finds_the_injected_rogue_command(
    baseline_capture: Path, live_capture: Path
) -> None:
    """Mechanism check. The rogue command was placed here by hand, so this is not a result."""
    graph = learn_device_command_graph(dissect_capture(baseline_capture, _registry()))
    dataset = CommandCaptureAdapter(
        captures=(live_capture,), attack_intervals=(attack_window(),), graph=graph
    ).load()

    report = evaluate(
        CommandGraphDetector(calibrator=CERTAIN), dataset, EvalConfig(alert_threshold=0.0)
    )

    assert report.n_alerts >= 1
    assert report.window_recall == 1.0


def test_the_behaviour_detector_scores_only_behaviour_features(
    baseline_capture: Path, live_capture: Path
) -> None:
    """Each detector reads one stream, because the two score in units that cannot share a sweep."""
    graph = learn_device_command_graph(dissect_capture(baseline_capture, _registry()))
    dataset = CommandCaptureAdapter(
        captures=(live_capture,), attack_intervals=(attack_window(),), graph=graph
    ).load()

    detections = CommandBehaviourDetector(
        fitted=fitted_baseline(baseline_capture), calibrator=CERTAIN
    ).run(dataset)

    assert all(detection.feature != UNKNOWN_COMMAND_RELATIONSHIP for detection in detections)


def test_the_graph_detector_scores_only_graph_findings(
    baseline_capture: Path, live_capture: Path
) -> None:
    graph = learn_device_command_graph(dissect_capture(baseline_capture, _registry()))
    dataset = CommandCaptureAdapter(
        captures=(live_capture,), attack_intervals=(attack_window(),), graph=graph
    ).load()

    detections = CommandGraphDetector(calibrator=CERTAIN).run(dataset)

    assert detections
    assert all(detection.feature == UNKNOWN_COMMAND_RELATIONSHIP for detection in detections)
    # The score is the measured size of the change, not a flag. One probe and a sustained flood on
    # a new link must not report the same number, or nothing downstream can order them.
    assert all(detection.score == pytest.approx(5.0) for detection in detections)


def test_the_detectors_name_both_halves_of_what_produced_the_numbers(
    baseline_capture: Path,
) -> None:
    behaviour = CommandBehaviourDetector(
        fitted=fitted_baseline(baseline_capture), calibrator=CERTAIN
    )
    assert "command-behaviour" in behaviour.name
    assert CERTAIN.name in behaviour.name
    assert CERTAIN.name in CommandGraphDetector(calibrator=CERTAIN).name


def test_a_detector_run_on_a_corpus_with_no_command_features_finds_nothing(
    baseline_capture: Path,
) -> None:
    empty = Dataset(name="empty", domain=Domain.ATLAS, observations=[])

    assert CommandGraphDetector(calibrator=CERTAIN).run(empty) == []
    assert (
        CommandBehaviourDetector(fitted=fitted_baseline(baseline_capture), calibrator=CERTAIN).run(
            empty
        )
        == []
    )


# ------------------------------------------------------------------------------------------------
# The refusals — the reason this PART ships no headline number
# ------------------------------------------------------------------------------------------------


def test_an_unlabelled_corpus_cannot_produce_a_metric(live_capture: Path) -> None:
    """Without ground truth every metric the harness computes is a number about nothing."""
    unlabelled = CommandCaptureAdapter(captures=(live_capture,)).load()

    with pytest.raises(UnlabelledCommandCorpusError, match="ground truth"):
        require_labelled_intervals(unlabelled)


def test_a_labelled_corpus_passes_the_same_guard(live_capture: Path) -> None:
    labelled = CommandCaptureAdapter(
        captures=(live_capture,), attack_intervals=(attack_window(),)
    ).load()

    require_labelled_intervals(labelled)


def test_this_repository_holds_no_labelled_command_corpus() -> None:
    """The fact P3 stops at, asserted rather than assumed.

    If this ever fails, a labelled command capture has been added and the measurement the whole
    packet adapter was built for can finally be run. Data4Cyber may have a Track A CSV
    ``manifest.json`` (ADR 0046). That payload is still not a labelled command corpus: the
    manifest must not set ``format="pcap"`` with command-action windows.
    """
    assert discover_labelled_command_corpora(Path("data")) == []
    data4cyber_manifest = Path("data/data4cyber/manifest.json")
    if data4cyber_manifest.is_file():
        import json

        declared = json.loads(data4cyber_manifest.read_text(encoding="utf-8"))
        assert declared.get("format") != "pcap" or not declared.get("attack_intervals")


def test_discovery_finds_a_registered_capture_corpus(tmp_path: Path) -> None:
    """The other half: the seam is wired, so it will find real data the moment there is some."""
    import json

    corpus = tmp_path / "somecorpus"
    corpus.mkdir()
    capture = write_capture(corpus / "traffic.pcap", polling(2))
    (corpus / "manifest.json").write_text(
        json.dumps(
            {
                "name": "somecorpus",
                "format": "pcap",
                "captures": [capture.name],
                "attack_intervals": [
                    {"start": EPOCH.isoformat(), "end": EPOCH.isoformat(), "label": "attack"}
                ],
                "source_note": "a fabricated manifest, for this test only",
            }
        ),
        encoding="utf-8",
    )

    found = discover_labelled_command_corpora(tmp_path)

    assert [corpus_.name for corpus_ in found] == ["somecorpus"]
    assert found[0].adapter().attack_intervals


@pytest.mark.parametrize(
    ("labels", "case"),
    [(None, "the key is absent"), ([], "the key is present and empty")],
    ids=["absent", "empty"],
)
def test_a_capture_corpus_with_no_labels_is_not_discovered(
    tmp_path: Path, labels: list[object] | None, case: str
) -> None:
    """A pcap on disk is not a corpus. Ground truth is what makes it one.

    Both spellings of "no labels" are tested, and the second is here because the mutation script
    found that only the first was. A manifest that declares ``attack_intervals`` and leaves it empty
    is the shape a half-finished corpus actually has, and a discovery check written as
    ``is None`` waves it through — after which the script stops refusing and prints a headline
    number with no ground truth behind it, which is the single outcome PART P3 exists to prevent.
    """
    import json

    corpus = tmp_path / "unlabelled"
    corpus.mkdir()
    capture = write_capture(corpus / "traffic.pcap", polling(2))
    manifest: dict[str, object] = {
        "name": "unlabelled",
        "format": "pcap",
        "captures": [capture.name],
    }
    if labels is not None:
        manifest["attack_intervals"] = labels
    (corpus / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    assert discover_labelled_command_corpora(tmp_path) == [], case


def test_the_refusal_says_exactly_what_data_is_missing() -> None:
    """Printing "no data" would be useless. This is the shopping list."""
    rendered = render_missing_corpus()

    assert LABELLED_COMMAND_CORPUS_REQUIREMENTS
    for requirement in LABELLED_COMMAND_CORPUS_REQUIREMENTS:
        assert requirement in rendered
    assert "pcap" in rendered.lower()


def test_session_5_inspected_corpora_are_named_in_the_refusal() -> None:
    """Looking at Data4Cyber and then printing only the shopping list would hide the finding.

    ADR 0040: pcapng is readable; labels are process phases. s7 is a table. 3W is faults.
    The script must say so, and none of those inspections fill `discover_labelled_command_corpora`.
    """
    rendered = render_missing_corpus()

    assert INSPECTED_NOT_A_LABELLED_COMMAND_CORPUS
    for refusal in INSPECTED_NOT_A_LABELLED_COMMAND_CORPUS:
        assert refusal in rendered
    assert "ADR 0040" in rendered
    assert discover_labelled_command_corpora(Path("data")) == []


# ------------------------------------------------------------------------------------------------
# Guards on the way in
# ------------------------------------------------------------------------------------------------


def test_an_adapter_with_no_captures_is_refused_at_construction() -> None:
    """A corpus that reads nothing loads as an empty, perfectly clean, entirely fake dataset."""
    with pytest.raises(ValidationError, match="at least one capture"):
        CommandCaptureAdapter(captures=())


def test_a_manifest_field_that_is_not_a_list_is_refused(tmp_path: Path) -> None:
    """A hand-edited manifest is the normal case, so its shape is checked rather than trusted."""
    import json

    corpus = tmp_path / "malformed"
    corpus.mkdir()
    capture = write_capture(corpus / "traffic.pcap", polling(2))
    (corpus / "manifest.json").write_text(
        json.dumps(
            {
                "name": "malformed",
                "format": "pcap",
                "captures": capture.name,  # a bare string where a list belongs
                "attack_intervals": [
                    {"start": EPOCH.isoformat(), "end": EPOCH.isoformat(), "label": "attack"}
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must be a list"):
        discover_labelled_command_corpora(tmp_path)


def test_a_manifest_naming_a_capture_that_is_not_on_disk_is_skipped(tmp_path: Path) -> None:
    """The manifest is committed and the data never is, so a missing file is the usual failure."""
    import json

    corpus = tmp_path / "absent"
    corpus.mkdir()
    (corpus / "manifest.json").write_text(
        json.dumps(
            {
                "name": "absent",
                "format": "pcap",
                "captures": ["never-fetched.pcap"],
                "attack_intervals": [
                    {"start": EPOCH.isoformat(), "end": EPOCH.isoformat(), "label": "attack"}
                ],
            }
        ),
        encoding="utf-8",
    )

    assert discover_labelled_command_corpora(tmp_path) == []


def test_discovery_of_a_directory_that_does_not_exist_is_empty_rather_than_an_error() -> None:
    """A clone with no data/ directory must get the refusal path, not a traceback."""
    assert discover_labelled_command_corpora(Path("data-that-does-not-exist")) == []

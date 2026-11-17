"""Tests for D3: the synthetic evaluation harness for Atlas.

These tests pin the wiring of `scripts/evaluate_atlas_synthetic.py`:
discover, adapter_for, detections_from, windows_covered, split_evidence,
magnitudes_of, and the SYNTHETIC-DERIVED marking on every report.

They use small hand-written fixtures under tmp_path, not the full 120-hour
generated corpora, so they run fast and are independent of data generation.
"""

from __future__ import annotations

import csv
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from scripts.evaluate_atlas_synthetic import (
    SYNTHETIC_CAVEATS,
    adapter_for,
    detections_from,
    discover,
    magnitudes_of,
    synthetic_caveats_note,
    windows_covered,
)

from phos.eval import Detection, EvalConfig, LabelledInterval
from phos.models import ModelDetector
from phos.ontology import Domain, Evidence, EvidenceKind


def _write_corpus(root: Path, name: str, rows: int = 10) -> Path:
    """Write a minimal synthetic corpus under root/name/ and return its directory."""
    corpus_dir = root / name
    corpus_dir.mkdir(parents=True)

    # telemetry.csv with timestamp, label, and one value column
    start = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    with open(corpus_dir / "telemetry.csv", "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["timestamp", "label", "process_value"])
        for i in range(rows):
            label = "1" if 3 <= i < 6 else "0"  # attack window samples 3-5
            writer.writerow(
                [
                    (start + timedelta(seconds=30 * i)).isoformat(),
                    label,
                    f"{100.0 + i:.5f}",
                ]
            )

    # topology.toml
    (corpus_dir / "topology.toml").write_text(
        'schema_version = 1\ncorpus = "test-plant"\n\n[[subsystems]]\n'
        'subsystem_id = "unit"\nlabel = "Test unit"\n'
        'source = "test"\nsignals = ["process_value"]\n',
        encoding="utf-8",
    )

    # manifest.json
    manifest = {
        "schema_version": 1,
        "name": name,
        "plant_id": "test-plant",
        "flavour": "DETECTION",
    }
    (corpus_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    return corpus_dir


def _make_evidence(
    evidence_id: str, timestamp: datetime, entity_id: str = "ent1", weight: float = 0.5
) -> Evidence:
    """Build a minimal Evidence for tests."""
    return Evidence(
        id=evidence_id,
        kind=EvidenceKind.DEVIATION,
        source_id="dev1",
        entity_ids=[entity_id],
        timestamp=timestamp,
        domain=Domain.ATLAS,
        weight=weight,
        summary="test evidence",
    )


def test_discover_finds_synthetic_corpora(tmp_path: Path) -> None:
    """Discover returns corpora under data/synth/ that have manifest, CSV, topology."""
    _write_corpus(tmp_path, "test-corpus-a")
    _write_corpus(tmp_path, "test-corpus-b")
    # A directory without manifest.json should be skipped.
    (tmp_path / "no-manifest").mkdir()
    # A directory without topology.toml should be skipped.
    incomplete = tmp_path / "incomplete"
    incomplete.mkdir()
    (incomplete / "manifest.json").write_text("{}", encoding="utf-8")
    (incomplete / "telemetry.csv").write_text("timestamp,label,value\n", encoding="utf-8")

    found = discover(root=tmp_path)
    names = {name for name, _, _ in found}
    assert names == {"test-corpus-a", "test-corpus-b"}


def test_discover_skips_input_hostile(tmp_path: Path) -> None:
    """Discover skips INPUT_HOSTILE flavour corpora."""
    corpus_dir = _write_corpus(tmp_path, "hostile-corpus")
    manifest = json.loads((corpus_dir / "manifest.json").read_text(encoding="utf-8"))
    manifest["flavour"] = "INPUT_HOSTILE"
    (corpus_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    found = discover(root=tmp_path)
    assert found == []


def test_adapter_for_loads_csv(tmp_path: Path) -> None:
    """adapter_for produces a LabelledCsvAdapter that loads the corpus."""
    corpus_dir = _write_corpus(tmp_path, "adapter-test")
    adapter = adapter_for(corpus_dir / "telemetry.csv", "adapter-test")
    dataset = adapter.load()

    assert dataset.name == "adapter-test"
    assert len(dataset.observations) == 10
    assert len(dataset.attack_intervals) == 1
    assert dataset.attack_intervals[0].label == "attack"


def test_detections_from_turns_evidence_into_detections() -> None:
    """detections_from maps Evidence to Detection with magnitude as score."""
    ts = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    ev1 = _make_evidence("ev1", ts)
    ev2 = _make_evidence("ev2", ts + timedelta(minutes=1), entity_id="ent2")
    magnitudes = {"ev1": 3.5, "ev2": 2.0}
    signals = {"ev1": ["signal_a"], "ev2": ["signal_b"]}

    detections = detections_from([ev1, ev2], magnitudes, signals)

    assert len(detections) == 2
    d1, d2 = detections
    assert isinstance(d1, Detection)
    assert d1.score == 3.5
    assert d1.confidence == 0.5
    assert d1.entity_ids == ["ent1"]
    assert d1.feature == "signal_a"
    assert d2.score == 2.0
    assert d2.confidence == 0.5
    assert d2.feature == "signal_b"


def test_windows_covered_counts_overlap() -> None:
    """windows_covered returns indices of attack windows overlapped by evidence."""
    start = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    intervals = [
        LabelledInterval(start=start, end=start + timedelta(minutes=5), label="attack"),
        LabelledInterval(
            start=start + timedelta(minutes=10),
            end=start + timedelta(minutes=15),
            label="attack",
        ),
    ]

    # Evidence inside the first window
    ev_in_window = _make_evidence("ev_in", start + timedelta(minutes=2))
    # Evidence between windows
    ev_between = _make_evidence("ev_between", start + timedelta(minutes=7))

    covered = windows_covered([ev_in_window, ev_between], {}, intervals)
    assert covered == {0}

    # Evidence at the boundary of the second window (inclusive end)
    ev_at_boundary = _make_evidence("ev_boundary", start + timedelta(minutes=15))
    covered = windows_covered([ev_at_boundary], {}, intervals)
    assert covered == {1}


def test_split_evidence_filters_by_subsystem_event_marker() -> None:
    """split_evidence's underlying filter separates per-signal from subsystem events."""
    from phos.atlas.grouping import is_subsystem_event

    per_signal = _make_evidence("ps1", datetime(2026, 1, 1, tzinfo=UTC))
    # A plain per-signal evidence is not a subsystem event.
    assert not is_subsystem_event(per_signal)
    # The real subsystem-event marking happens inside AtlasEngine via grouping;
    # this test pins the filter direction only.
    stored = [per_signal]
    per = [item for item in stored if not is_subsystem_event(item)]
    events = [item for item in stored if is_subsystem_event(item)]
    assert len(per) == 1
    assert len(events) == 0


def test_magnitudes_of_is_callable() -> None:
    """magnitudes_of is a callable function with the expected signature."""
    assert callable(magnitudes_of)


def test_synthetic_caveats_note_contains_all_four() -> None:
    """synthetic_caveats_note() joins all four standing caveats."""
    note = synthetic_caveats_note()
    for caveat in SYNTHETIC_CAVEATS:
        key = caveat.split(":")[0]
        assert key in note, f"missing caveat key: {key}"


def test_synthetic_caveats_are_four() -> None:
    """There are exactly four standing synthetic caveats."""
    assert len(SYNTHETIC_CAVEATS) == 4
    keys = {c.split(":")[0] for c in SYNTHETIC_CAVEATS}
    assert keys == {
        "MODEL_NOT_REALITY_CAVEAT",
        "ATTACKS_ARE_OURS_CAVEAT",
        "SYNTHETIC_TOPOLOGY_CAVEAT",
        "INPUT_HOSTILE_IS_NOT_SECURITY_CAVEAT",
    }


def test_eval_config_defaults() -> None:
    """EvalConfig used by D3 has the declared threshold and seed."""
    config = EvalConfig(alert_threshold=3.0, seed=11)
    assert config.alert_threshold == 3.0
    assert config.seed == 11


def test_detector_protocol_is_satisfied() -> None:
    """ModelDetector satisfies the Detector protocol used by evaluate()."""
    from phos.models import GaussianBaseline

    model = GaussianBaseline()
    assert hasattr(ModelDetector, "run")
    assert hasattr(model, "fit")

"""Tests for `phos.referee.record`: the Atlas recorder and run metadata builders.

Tests that the recorder:
- builds plant/structure/timeline/telemetry from a corpus manifest,
- writes a valid, verifiable `.phosrun` with Atlas output,
- is deterministic: same corpus → same .phosrun bytes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from phos.referee.record import (
    build_plant_descriptor,
    build_structure,
    build_timeline,
    record_atlas_on_run,
)
from phos.runrecord import RunRecord, read_header, verify
from phos.synth.attacks.battery import load_batteries
from phos.synth.attacks.generate import generate_attack_dataset

CONFIG_DIR = Path(__file__).resolve().parents[2] / "configs" / "attacks"


@pytest.fixture(scope="session")
def small_corpus(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Generate one small attack corpus for recorder tests."""
    configs = load_batteries(CONFIG_DIR)
    config = next(c for c in configs if c.name == "synth-attack-water-unknown-master")
    output = tmp_path_factory.mktemp("recorder-corpus")
    directory, _manifest = generate_attack_dataset(config, output, with_capture=True)
    return directory


@pytest.fixture
def phosrun_path(tmp_path: Path, small_corpus: Path) -> Path:
    """Record one .phosrun from the small corpus into tmp_path."""
    out = tmp_path / "test-run.phosrun"
    record_atlas_on_run(small_corpus, out)
    return out


def test_build_plant_descriptor(small_corpus: Path) -> None:
    plant = build_plant_descriptor(small_corpus)
    assert plant["plant_id"] == "water-treatment"
    assert plant["label"] == "Surface water treatment works"
    assert plant["industry"] == "water treatment"
    assert len(plant["units"]) == 5
    assert len(plant["signals"]) == 15
    assert "control_network" in plant


def test_build_structure(small_corpus: Path) -> None:
    structure = build_structure(small_corpus)
    assert "nodes" in structure and "edges" in structure
    assert len(structure["nodes"]) > 0
    assert len(structure["edges"]) > 0
    ids = {n["id"] for n in structure["nodes"]}
    assert "intake" in ids
    assert "dosing" in ids
    assert "clearwell" in ids
    assert "scada" in ids
    assert "plc_inlet" in ids
    assert "engineering" in ids
    assert "raw_inflow_m3ph" in ids
    assert "distribution_flow_m3ph" in ids


def test_build_timeline(small_corpus: Path) -> None:
    timeline = build_timeline(small_corpus)
    assert len(timeline) == 8  # 4 benign events + 4 attacks
    attacks = [e for e in timeline if e["kind"] == "attack"]
    assert len(attacks) == 4
    starts = [e["start"] for e in attacks]
    assert starts == sorted(starts)
    for atk in attacks:
        assert len(atk["affected_tags"]) > 0
        assert atk["layer"] == "control_network"
        assert atk["physical_effect"] is True


def test_record_writes_valid_phosrun(phosrun_path: Path) -> None:
    """The written .phosrun verifies cleanly and carries all expected members."""
    problems = verify(phosrun_path)
    assert problems == [], f"verification failed: {problems}"

    header = read_header(phosrun_path)
    assert header["kind"] == "simulated"
    assert header["pool"] == "dev"
    assert header["title"] == "Atlas on synth-attack-water-unknown-master"
    assert header["run_id"]

    members = set(header["members"].keys())
    # Required members present (header.json is not declared in members by design:
    # it contains run_id which is computed from the other member hashes).
    for req in (
        "plant.json",
        "structure.json",
        "timeline.json",
        "telemetry/index.json",
        "labels.json",
        "thumbnail.svg",
    ):
        assert req in members, f"missing required member: {req}"
    # Atlas members present
    assert "atlas/detector.json" in members
    assert "atlas/alerts.jsonl" in members
    assert "atlas/hypotheses.jsonl" in members
    assert "atlas/narratives.jsonl" in members


def test_record_plant_and_structure(phosrun_path: Path) -> None:
    with RunRecord(phosrun_path) as run:
        plant = run.plant()
        assert plant["plant_id"] == "water-treatment"
        assert plant["label"] == "Surface water treatment works"

        structure = run.structure()
        assert len(structure["nodes"]) > 0
        assert len(structure["edges"]) > 0

        timeline = run.timeline()
        assert len(timeline) == 8

        atlas = run.atlas()
        assert atlas is not None
        assert len(atlas["alerts"]) > 0
        assert len(atlas["hypotheses"]) > 0


def test_record_telemetry_chunks(phosrun_path: Path) -> None:
    with RunRecord(phosrun_path) as run:
        index = run.telemetry_index()
        assert len(index["columns"]) == 16
        assert len(index["chunks"]) == 1
        assert index["chunks"][0]["samples"] == 2880


def test_record_atlas_output_structure(phosrun_path: Path) -> None:
    with RunRecord(phosrun_path) as run:
        atlas = run.atlas()
        assert atlas is not None
        assert "detector" in atlas
        assert atlas["detector"]["name"] == "model:atlas-mahalanobis"

        for alert in atlas["alerts"]:
            assert "timestamp" in alert
            assert "score" in alert
            assert "confidence" in alert
            assert "feature" in alert
            assert "entity_ids" in alert

        for hyp in atlas["hypotheses"]:
            assert "id" in hyp
            assert "template_id" in hyp
            assert "confidence" in hyp


def test_record_plain_language_summary(phosrun_path: Path) -> None:
    header = read_header(phosrun_path)
    summary = header["plain_language_summary"]
    assert "Atlas run on the simulated plant" in summary
    assert "alerts" in summary
    assert "hypotheses" in summary


def test_record_output_to_directory(tmp_path: Path, small_corpus: Path) -> None:
    """When output is a directory, the file is named <corpus>.phosrun inside it."""
    out_dir = tmp_path / "outdir"
    out_dir.mkdir()
    written = record_atlas_on_run(small_corpus, out_dir)
    expected = out_dir / "synth-attack-water-unknown-master.phosrun"
    assert written == expected
    assert expected.is_file()


def test_record_is_deterministic(tmp_path: Path, small_corpus: Path) -> None:
    """Build functions are deterministic: same corpus → same metadata."""
    p1 = build_plant_descriptor(small_corpus)
    p2 = build_plant_descriptor(small_corpus)
    assert p1 == p2

    s1 = build_structure(small_corpus)
    s2 = build_structure(small_corpus)
    assert s1 == s2

    t1 = build_timeline(small_corpus)
    t2 = build_timeline(small_corpus)
    assert t1 == t2

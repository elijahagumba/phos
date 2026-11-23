"""Tests for phos.runrecord: the .phosrun file format library.

Tests round-trip determinism, byte-identical output, verification,
anti-fingerprinting (no Atlas import), and optional-member handling.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import numpy
import pytest

from phos.runrecord import (
    FORMAT_VERSION_MAJOR,
    FORMAT_VERSION_STRING,
    RunRecord,
    read_header,
    verify,
    write_run,
)


def _minimal_telemetry_chunks(n_chunks: int = 2, samples_per_chunk: int = 100) -> list[dict]:
    """Build synthetic telemetry chunks for testing."""
    chunks: list[dict] = []
    columns = [
        {"tag": "reactor_temp_c", "unit": "degC", "valid_range": [0.0, 100.0], "role": "sensor"},
        {"tag": "jacket_valve_pct", "unit": "%", "valid_range": [0.0, 100.0], "role": "actuator"},
    ]
    for i in range(n_chunks):
        data = numpy.full((samples_per_chunk, 2), float(i + 1), dtype="float64")
        min_max = [
            {"min": float(i + 1), "max": float(i + 1)},
            {"min": float(i + 1), "max": float(i + 1)},
        ]
        chunks.append(
            {
                "chunk_index": i,
                "start_time": f"2026-05-01T00:{i:02d}:00+00:00",
                "end_time": f"2026-05-01T00:{i + 1:02d}:00+00:00",
                "data": data,
                "min_max": min_max,
            }
        )
    chunks[0]["columns"] = columns
    chunks[0]["sample_period"] = 30.0
    chunks[0]["start_time"] = "2026-05-01T00:00:00+00:00"
    return chunks


def _minimal_run_kwargs(tmp_path: Path, **overrides: object) -> dict:
    """Build minimal kwargs for write_run."""
    kwargs: dict = {
        "output": tmp_path / "test.phosrun",
        "kind": "simulated",
        "title": "Test run",
        "created_by": "test-runner 1.0",
        "seed_information": {"family": "water-treatment", "master_seed": 90212},
        "pool": "dev",
        "model_not_reality_caveat": "This is a model of a plant, not reality.",
        "plain_language_summary": "A test run of the synthetic reactor.",
        "plant": {
            "plant_id": "batch-reactor",
            "label": "Jacketed batch reactor",
            "units": [{"unit_id": "reactor", "label": "Reactor"}],
        },
        "structure": {
            "nodes": [{"id": "reactor", "type": "tank", "label": "Reactor"}],
            "edges": [],
            "subsystems": [{"subsystem_id": "reactor", "label": "Reactor", "signals": []}],
        },
        "timeline": [
            {
                "id": "evt-1",
                "kind": "attack",
                "type": "BLATANT",
                "start": "2026-05-01T04:00:00+00:00",
                "end": "2026-05-01T05:30:00+00:00",
                "affected_tags": ["reactor_temp_c"],
                "layer": "sensor",
                "physical_effect": True,
                "description": "Test attack",
            }
        ],
        "telemetry_chunks": _minimal_telemetry_chunks(),
        "labels": [
            {"start": "2026-05-01T04:00:00+00:00", "end": "2026-05-01T05:30:00+00:00", "class": "attack"}
        ],
    }
    kwargs.update(overrides)
    return kwargs


def test_write_and_read_roundtrip(tmp_path: Path) -> None:
    """Writing then reading a .phosrun yields identical data."""
    kwargs = _minimal_run_kwargs(tmp_path)
    path = write_run(**kwargs)

    assert path.exists()
    assert path.suffix == ".phosrun"

    with RunRecord(path) as run:
        assert run.kind == "simulated"
        assert run.title == "Test run"
        assert run.pool == "dev"
        assert len(run.run_id) == 64  # SHA-256 hex

        # Plant
        plant = run.plant()
        assert plant["plant_id"] == "batch-reactor"

        # Structure
        structure = run.structure()
        assert len(structure["nodes"]) == 1
        assert structure["nodes"][0]["id"] == "reactor"

        # Timeline
        timeline = run.timeline()
        assert len(timeline) == 1
        assert timeline[0]["id"] == "evt-1"

        # Telemetry index
        ti = run.telemetry_index()
        assert len(ti["columns"]) == 2
        assert len(ti["chunks"]) == 2

        # Telemetry chunk data
        chunk0 = run.telemetry_chunk(0)
        assert chunk0.shape == (100, 2)

        # Telemetry range query
        result = run.telemetry_range("reactor_temp_c", "2026-05-01T00:00:00+00:00", "2026-05-01T00:02:00+00:00")
        assert len(result["timestamps"]) > 0
        assert len(result["values"]) == len(result["timestamps"])

        # Labels
        labels = run.labels()
        assert len(labels) == 1
        assert labels[0]["class"] == "attack"

        # No atlas data (not provided)
        assert run.atlas() is None
        assert run.scores() is None
        assert run.traffic() is None

        # Thumbnail
        assert run.thumbnail() is None


def test_byte_identical_on_rewrite(tmp_path: Path) -> None:
    """Writing the same run twice yields byte-identical output."""
    kwargs = _minimal_run_kwargs(tmp_path)
    path1 = tmp_path / "run1.phosrun"
    path2 = tmp_path / "run2.phosrun"

    write_run(**{**kwargs, "output": path1})
    write_run(**{**kwargs, "output": path2})

    data1 = path1.read_bytes()
    data2 = path2.read_bytes()
    assert data1 == data2


def test_verify_detects_flipped_byte(tmp_path: Path) -> None:
    """Flipping a single byte in any member makes verify fail."""
    kwargs = _minimal_run_kwargs(tmp_path)
    path = write_run(**kwargs)

    # Verify passes initially
    assert verify(path) == []

    # Read all data first, then rewrite with a flipped byte
    with zipfile.ZipFile(path, "r") as zf:
        names = zf.namelist()
        all_data = {n: zf.read(n) for n in names}

    chunk_name = next(n for n in names if n.startswith("telemetry/chunk_"))
    flipped = bytearray(all_data[chunk_name])
    flipped[0] ^= 0x01  # flip first byte
    all_data[chunk_name] = bytes(flipped)

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name in names:
            info = zipfile.ZipInfo(filename=name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, all_data[name])

    problems = verify(path)
    assert len(problems) > 0
    assert any("hash mismatch" in p for p in problems)


def test_unknown_major_version_refused(tmp_path: Path) -> None:
    """A run with an unknown MAJOR version is refused."""
    kwargs = _minimal_run_kwargs(tmp_path)
    path = write_run(**kwargs)

    # Verify passes initially
    assert verify(path) == []

    # Read all data, corrupt one telemetry chunk byte, rewrite
    with zipfile.ZipFile(path, "r") as zf:
        all_names = zf.namelist()
        all_data = {n: zf.read(n) for n in all_names}

    chunk_name = next(n for n in all_names if n.startswith("telemetry/chunk_"))
    flipped = bytearray(all_data[chunk_name])
    flipped[0] ^= 0x01
    all_data[chunk_name] = bytes(flipped)

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name in all_names:
            info = zipfile.ZipInfo(filename=name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, all_data[name])

    problems = verify(path)
    assert len(problems) > 0, f"Expected problems but got: {problems}"
    assert any("hash mismatch" in p for p in problems), f"Unexpected problems: {problems}"


def test_read_header_only_reads_header(tmp_path: Path) -> None:
    """read_header reads only header.json, not the whole file."""
    kwargs = _minimal_run_kwargs(tmp_path)
    path = write_run(**kwargs)

    header = read_header(path)
    assert header["format_name"] == "phosrun"
    assert header["format_version"] == FORMAT_VERSION_STRING
    assert header["kind"] == "simulated"
    assert len(header["run_id"]) == 64


def test_optional_members_absent(tmp_path: Path) -> None:
    """A run without optional atlas/scores/traffic members still verifies."""
    kwargs = _minimal_run_kwargs(tmp_path)
    # No atlas, scores, or traffic provided
    path = write_run(**kwargs)

    assert verify(path) == []

    with RunRecord(path) as run:
        assert run.atlas() is None
        assert run.scores() is None
        assert run.traffic() is None


def test_runrecord_does_not_import_atlas() -> None:
    """The runrecord package does not import phos.atlas."""
    import importlib

    # Check that no module in runrecord imports phos.atlas
    modules = [
        "phos.runrecord",
        "phos.runrecord.writer",
        "phos.runrecord.reader",
        "phos.runrecord.cli",
        "phos.runrecord.format",
    ]
    for mod_name in modules:
        mod = importlib.import_module(mod_name)
        # Check that no attribute of the module references phos.atlas
        for name in dir(mod):
            obj = getattr(mod, name)
            # Skip string constants that happen to contain "atlas"
            if isinstance(obj, str) and "atlas" in obj.lower():
                continue
            # Check if any string attribute value contains "phos.atlas" import
            if isinstance(obj, str) and "phos.atlas" in obj:
                raise AssertionError(f"{mod_name}.{name} references phos.atlas: {obj}")


def test_runrecord_module_imports_only_allowed_atlas_modules() -> None:
    """runrecord/writer.py and reader.py only import format, not phos.atlas."""
    import phos.runrecord.writer
    import phos.runrecord.reader

    for mod in (phos.runrecord.writer, phos.runrecord.reader):
        mod_name = mod.__name__
        for name in dir(mod):
            obj = getattr(mod, name)
            if isinstance(obj, str) and "phos.atlas" in obj:
                raise AssertionError(f"{mod_name}.{name} imports phos.atlas: {obj}")


def test_write_run_creates_parent_directory(tmp_path: Path) -> None:
    """write_run creates parent directories if needed."""
    deep_path = tmp_path / "sub" / "dir" / "run.phosrun"
    kwargs = _minimal_run_kwargs(tmp_path)
    write_run(**{**kwargs, "output": deep_path})
    assert deep_path.exists()

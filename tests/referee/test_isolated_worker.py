"""`phos.referee._isolated_worker`, called directly (in process) rather than through a subprocess.

`tests/referee/test_integrity.py` already proves the subprocess boundary holds; this file checks
the worker's own logic — loading a label-free `Dataset` and running a factory-built detector —
without paying for a subprocess on every assertion.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from phos.referee import _isolated_worker
from phos.referee.corpus import strip_labels
from phos.synth.outputs import GeneratedPlant


def test_load_unlabelled_has_no_attack_or_unscored_intervals(
    small_exam_plant: GeneratedPlant, tmp_path: Path
) -> None:
    telemetry_path = strip_labels(small_exam_plant, tmp_path / "stripped")
    dataset = _isolated_worker._load_unlabelled(telemetry_path, small_exam_plant.manifest.plant_id)

    assert dataset.name == small_exam_plant.manifest.plant_id
    assert dataset.attack_intervals == []
    assert dataset.unscored_intervals == []
    assert dataset.observations


def test_load_unlabelled_observation_count_matches_the_stripped_csv(
    small_exam_plant: GeneratedPlant, tmp_path: Path
) -> None:
    import pandas

    telemetry_path = strip_labels(small_exam_plant, tmp_path / "stripped2")
    frame = pandas.read_csv(telemetry_path)
    dataset = _isolated_worker._load_unlabelled(telemetry_path, small_exam_plant.manifest.plant_id)

    value_columns = len(frame.columns) - 1  # minus the timestamp column; no label column here
    assert len(dataset.observations) == len(frame) * value_columns


def test_main_prints_a_json_array_of_detections(
    small_exam_plant: GeneratedPlant, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    telemetry_path = strip_labels(small_exam_plant, tmp_path / "stripped3")

    status = _isolated_worker.main(
        [
            "prog",
            "phos.referee.demo:threshold_detector",
            str(telemetry_path),
            small_exam_plant.manifest.plant_id,
        ]
    )

    assert status == 0
    payload = json.loads(capsys.readouterr().out)
    assert isinstance(payload, list)

"""`phos.referee.corpus`: a plant read back as a labelled `Dataset`, and label stripping."""

from __future__ import annotations

from pathlib import Path

import pandas

from phos.referee.corpus import event_records, load_plant_dataset, strip_labels
from phos.synth.events import EventKind
from phos.synth.outputs import TELEMETRY_FILE, GeneratedPlant
from phos.synth.telemetry import LABEL_COLUMN, TIMESTAMP_COLUMN


def test_event_records_matches_the_schedule(small_exam_plant: GeneratedPlant) -> None:
    """Every planned event is readable straight from the generator's own schedule."""
    records = event_records(small_exam_plant)
    kinds = {record.kind for record in records}
    assert kinds == {EventKind.ATTACK, EventKind.FAULT, EventKind.MAINTENANCE}


def test_dataset_attack_intervals_are_attack_and_fault_only(
    small_exam_plant: GeneratedPlant,
) -> None:
    """Detection targets are attack and fault windows; maintenance is sanctioned cover."""
    dataset = load_plant_dataset(small_exam_plant)
    records = event_records(small_exam_plant)

    targets = [record for record in records if record.kind in (EventKind.ATTACK, EventKind.FAULT)]
    cover = [record for record in records if record.kind is EventKind.MAINTENANCE]

    assert len(dataset.attack_intervals) == len(targets)
    assert len(dataset.unscored_intervals) == len(cover)
    for interval, record in zip(
        sorted(dataset.attack_intervals, key=lambda item: item.start),
        sorted(targets, key=lambda item: item.started_at),
        strict=True,
    ):
        assert interval.start == record.started_at
        assert interval.end == record.ended_at
        assert interval.attack_type == record.type


def test_dataset_has_one_observation_per_signal_per_sample(
    small_exam_plant: GeneratedPlant,
) -> None:
    """Observation count matches rows times signal columns in the telemetry file."""
    dataset = load_plant_dataset(small_exam_plant)
    frame = pandas.read_csv(small_exam_plant.directory / TELEMETRY_FILE)
    value_columns = [
        column for column in frame.columns if column not in (TIMESTAMP_COLUMN, LABEL_COLUMN)
    ]
    assert len(dataset.observations) == len(frame) * len(value_columns)


def test_strip_labels_drops_the_label_column(
    small_exam_plant: GeneratedPlant, tmp_path: Path
) -> None:
    """The stripped copy has no label column, and every other column survives."""
    destination = tmp_path / "stripped"
    stripped_path = strip_labels(small_exam_plant, destination)

    stripped = pandas.read_csv(stripped_path)
    original = pandas.read_csv(small_exam_plant.directory / TELEMETRY_FILE)

    assert LABEL_COLUMN not in stripped.columns
    assert set(stripped.columns) == set(original.columns) - {LABEL_COLUMN}
    assert len(stripped) == len(original)


def test_strip_labels_writes_only_telemetry(
    small_exam_plant: GeneratedPlant, tmp_path: Path
) -> None:
    """The destination holds the stripped telemetry and nothing this test did not put there."""
    destination = tmp_path / "stripped2"
    strip_labels(small_exam_plant, destination)
    assert {path.name for path in destination.iterdir()} == {TELEMETRY_FILE}

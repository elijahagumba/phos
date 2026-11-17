"""Turn a generated plant on disk into the labelled `Dataset` the referee scores against.

PART S6. Bypasses `telemetry.csv`'s own label column entirely: that column carries only D1's
generic normal/not-normal flag for `phos.eval.LabelledCsvAdapter`, while the referee needs the
richer per-event kind, type and stealth facts that only `phos.synth.events.EventRecord` carries.
Reading the schedule directly, in process, from the `GeneratedPlant` the generator just returned
is also the only way to get those facts at all: `labels.json`'s own ``attack_intervals`` keeps
only an id, a start, an end, a kind and a type, and drops ``technique``, ``physical_effect`` and
``within_normal_range`` on the way to disk.
"""

from __future__ import annotations

from pathlib import Path

import pandas

from phos.eval import Dataset, LabelledInterval
from phos.ontology import Domain, Observation
from phos.synth.events import EventKind, EventRecord
from phos.synth.outputs import TELEMETRY_FILE, GeneratedPlant
from phos.synth.telemetry import LABEL_COLUMN, TIMESTAMP_COLUMN, entity_id

__all__ = [
    "DETECTION_TARGET_KINDS",
    "SANCTIONED_COVER_KINDS",
    "CorpusError",
    "event_records",
    "load_plant_dataset",
    "strip_labels",
]

DETECTION_TARGET_KINDS: tuple[EventKind, ...] = (EventKind.ATTACK, EventKind.FAULT)
"""What `Dataset.attack_intervals` holds for an exam plant. Matches
`phos.synth.outputs.labels_document`'s own convention: attacks and faults are detection targets,
and an alert in either window is what "caught" means."""

SANCTIONED_COVER_KINDS: tuple[EventKind, ...] = (EventKind.MAINTENANCE,)
"""What `Dataset.unscored_intervals` holds. A maintenance window is neither a catch nor a false
alarm, which is exactly what `unscored_intervals` already means in `phos.eval`."""


class CorpusError(ValueError):
    """Raised when a generated plant cannot be read back as a scorable corpus."""


def event_records(plant: GeneratedPlant) -> tuple[EventRecord, ...]:
    """Return this plant's scheduled events, or an empty tuple for an events-free plant."""
    return plant.schedule.records if plant.schedule is not None else ()


def load_plant_dataset(plant: GeneratedPlant) -> Dataset:
    """Read ``telemetry.csv`` and attach ground truth from the plant's own event schedule.

    Args:
        plant: A plant `phos.synth.outputs.generate_plant` has already written.

    Returns:
        The corpus: every signal as an observation, attack and fault windows as detection
        targets, maintenance windows as sanctioned cover.

    Raises:
        CorpusError: If the telemetry file has no rows, which would score as a corpus in which
            nothing went wrong rather than as the empty, unusable run it actually is.
    """
    frame = pandas.read_csv(plant.directory / TELEMETRY_FILE)
    if frame.empty:
        raise CorpusError(f"{plant.manifest.plant_id}: telemetry.csv has no rows")
    value_columns = [
        str(column) for column in frame.columns if column not in (TIMESTAMP_COLUMN, LABEL_COLUMN)
    ]
    timestamps = [
        stamp.to_pydatetime() for stamp in pandas.to_datetime(frame[TIMESTAMP_COLUMN], utc=True)
    ]
    columns = {column: frame[column].to_numpy(dtype=float) for column in value_columns}
    entity = entity_id(plant.manifest.plant_id)

    observations: list[Observation] = []
    for row_index, timestamp in enumerate(timestamps):
        for column_index, column in enumerate(value_columns):
            observations.append(
                Observation(
                    id=f"obs_ref{row_index:08d}c{column_index:02d}",
                    entity_ids=[entity],
                    feature=column,
                    value=float(columns[column][row_index]),
                    timestamp=timestamp,
                    domain=Domain.ATLAS,
                    context={"plant": plant.manifest.plant_id},
                )
            )

    records = event_records(plant)
    attack_intervals = [
        LabelledInterval(
            start=record.started_at, end=record.ended_at, label="attack", attack_type=record.type
        )
        for record in records
        if record.kind in DETECTION_TARGET_KINDS
    ]
    unscored_intervals = [
        LabelledInterval(
            start=record.started_at, end=record.ended_at, label="unscored", attack_type=record.type
        )
        for record in records
        if record.kind in SANCTIONED_COVER_KINDS
    ]
    return Dataset(
        name=plant.manifest.plant_id,
        domain=Domain.ATLAS,
        observations=observations,
        attack_intervals=attack_intervals,
        unscored_intervals=unscored_intervals,
        source_note=(
            f"phos.synth exam plant {plant.manifest.plant_id}, family={plant.manifest.family_id}, "
            f"master_seed={plant.manifest.master_seed}"
        ),
    )


def strip_labels(plant: GeneratedPlant, destination: Path) -> Path:
    """Write a label-free copy of ``telemetry.csv`` into ``destination`` and return its path.

    Used by `phos.referee.integrity` to build the directory an isolated detector subprocess is
    allowed to see. Dropping the label column here, rather than trusting a detector not to read
    it, is what makes "the detector was given only telemetry" true of the file on disk and not
    only of the arguments it was called with.

    Args:
        plant: The plant whose telemetry is being copied.
        destination: Directory to write the stripped copy into. Created if it does not exist.

    Returns:
        The path of the stripped CSV: the timestamp and value columns, and nothing else — no
        label column, and nothing from ``labels.json``, ``manifest.json`` or any seed file,
        because those never left the directory this was copied from.
    """
    frame = pandas.read_csv(plant.directory / TELEMETRY_FILE)
    frame = frame.drop(columns=[LABEL_COLUMN], errors="ignore")
    destination.mkdir(parents=True, exist_ok=True)
    out_path = destination / TELEMETRY_FILE
    frame.to_csv(out_path, index=False)
    return out_path

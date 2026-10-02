"""Turning a plant run into the corpus Atlas already knows how to read.

The synthetic engine's telemetry output goes through `phos.eval.Dataset` and nothing else. That is
the whole design: the harness must not be able to tell a generated corpus from HAI or BATADAL, or
a false-positive rate measured on one would not mean what it means on the other.

Two routes out, and both end in the same place.

- `to_dataset` builds the `Dataset` in memory, for a caller that already has a run.
- `write_csv` writes the prepared-corpus CSV shape — a timestamp column, a label column, one
  column per signal — which `phos.eval.LabelledCsvAdapter` then loads **with no special case for
  synthetic data**. That is the stronger of the two claims and the one
  `tests/synth/test_telemetry.py` makes: the file goes in through the same door a downloaded
  corpus does.

**Every row is labelled normal, and the label column is there anyway.** D1 generates no attacks,
so `attack_intervals` is empty and every label cell is zero. The column exists because the corpus
shape has to be the one D2 will write into, and because a corpus that omitted its labels would be
indistinguishable from one whose labels were lost.

**Actuator and setpoint signals become observations too**, exactly as they do in a real historian —
HAI records valve demands beside the flows they cause. Withholding them would hide the control
action that explains half the plant's behaviour, and it is control action that D2 will manipulate.

**The caveat travels with the data.** `Dataset.source_note` carries the plant, the seed, the
sampling rate and `MODEL_NOT_REALITY_CAVEAT`, so a report generated from this corpus cannot quote
a number without also carrying the sentence that says what the number is about.
"""

import csv
import logging
from pathlib import Path
from typing import Final, Self

from pydantic import BaseModel, ConfigDict, model_validator

from phos.eval import Dataset
from phos.ontology import Domain, Observation
from phos.synth.plant import MODEL_NOT_REALITY_CAVEAT, PlantDescription, RunSpec
from phos.synth.run import PlantRun, run_plant

__all__ = [
    "LABEL_COLUMN",
    "NORMAL_LABEL",
    "TIMESTAMP_COLUMN",
    "SyntheticPlantAdapter",
    "entity_id",
    "observations",
    "source_note",
    "to_dataset",
    "write_csv",
]

logger = logging.getLogger(__name__)

TIMESTAMP_COLUMN: Final = "timestamp"
LABEL_COLUMN: Final = "label"
NORMAL_LABEL: Final = "0"
"""Every row D1 writes. Zero means normal under `phos.eval.default_attack_when`, which is the
convention every published ICS corpus PHOS reads uses."""


def entity_id(plant_id: str) -> str:
    """Return the entity id a plant's readings are attributed to.

    Args:
        plant_id: The plant's identifier.

    Returns:
        ``ent_synth-<plant_id>`` — readable rather than opaque, following the convention
        `phos.atlas.packet.commands.device_entity_id` established for devices, so a feature keyed
        to it names its plant without a lookup.
    """
    return f"ent_synth-{plant_id}"


def source_note(description: PlantDescription, spec: RunSpec) -> str:
    """Return the provenance string every dataset and report carries.

    Names the plant, the seed and the sampling rate — enough to regenerate the corpus exactly —
    and then states plainly what a plant model is and is not.
    """
    return (
        f"phos.synth: {description.label} ({description.plant_id}), seed={spec.seed}, "
        f"{spec.duration} at {spec.interval_seconds:g}s sampling, "
        f"{len(description.signals)} signals across {len(description.units)} physical units. "
        f"All rows labelled normal. {MODEL_NOT_REALITY_CAVEAT}"
    )


def observations(run: PlantRun) -> list[Observation]:
    """Return one `Observation` per signal per sample, in timestamp order.

    Args:
        run: The completed run. Its *reported* readings become observations — the true state is
            ground truth for D2 and D3 and is deliberately not published as telemetry, because a
            detector that could see it would be detecting nothing.

    Returns:
        The observations, ordered by sample and then by the plant's declared signal order.
    """
    entity = entity_id(run.description.plant_id)
    keys = run.description.signal_keys()
    return [
        Observation(
            id=f"obs_syn{step.index:08d}c{column:02d}",
            entity_ids=[entity],
            feature=key,
            value=step.report.values[key],
            timestamp=step.timestamp,
            domain=Domain.ATLAS,
            context={"plant": run.description.plant_id, "generator": "phos.synth"},
        )
        for step in run.steps
        for column, key in enumerate(keys)
    ]


def to_dataset(run: PlantRun, name: str | None = None) -> Dataset:
    """Return the run as a labelled `Dataset` the evaluation harness can score.

    Args:
        run: The completed run.
        name: Dataset name. Defaults to ``synth-<plant_id>``.

    Returns:
        The corpus, with an empty `attack_intervals` because every sample here is normal. An empty
        list is the honest statement "ground truth says nothing happened", which is exactly what
        D1 produces and exactly what D2 will fill in.
    """
    return Dataset(
        name=name or f"synth-{run.description.plant_id}",
        domain=Domain.ATLAS,
        observations=observations(run),
        attack_intervals=[],
        source_note=source_note(run.description, run.spec),
    )


def write_csv(run: PlantRun, path: Path) -> int:
    """Write the run in the prepared-corpus CSV shape and return the row count.

    The shape is the one `phos.eval.LabelledCsvAdapter` reads: a timestamp column, a label column,
    then one column per signal in the plant's declared order.

    **Values are written to five decimal places**, which is what HAI's own prepared CSV carries and
    close to what a historian storing single-precision floats can actually hold. It also makes the
    file load back exactly: a seventeen-digit repr is long enough that pandas' fast float parser
    can land one unit in the last place away from the value that was written, so writing more
    digits would buy a precision the round trip does not preserve. The run itself remains exactly
    regenerable — from the seed, which is what `phos.synth.manifest` records.

    Args:
        run: The completed run.
        path: File to write. Overwritten if it exists.

    Returns:
        Rows written, not counting the header.
    """
    keys = run.description.signal_keys()
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([TIMESTAMP_COLUMN, LABEL_COLUMN, *keys])
        for step in run.steps:
            writer.writerow(
                [
                    step.timestamp.isoformat(),
                    NORMAL_LABEL,
                    *(f"{step.report.values[key]:.5f}" for key in keys),
                ]
            )
    logger.debug("wrote %d rows to %s", len(run.steps), path)
    return len(run.steps)


class SyntheticPlantAdapter(BaseModel):
    """Generates a plant run and presents it as a `Dataset`, satisfying `phos.eval.DatasetAdapter`.

    The point of the adapter protocol is that the harness never learns which corpus it is looking
    at. This is the synthetic engine's entry into it: a plant identifier and a run spec in, a
    labelled corpus out, with no file on disk in between.

    Attributes:
        plant_id: Which plant to run. Must be one `phos.synth.run` knows.
        spec: The run to simulate.
        name: Dataset name recorded on every report the corpus produces.

    Invariants:
        The plant identifier names a known plant, checked at construction rather than at load, so
        a mis-typed corpus fails where it is configured instead of an hour into a sweep.
    """

    model_config = ConfigDict(frozen=True)

    plant_id: str
    spec: RunSpec
    name: str = ""

    @model_validator(mode="after")
    def _check_plant(self) -> Self:
        from phos.synth.run import PLANT_IDS

        if self.plant_id not in PLANT_IDS:
            raise ValueError(
                f"no plant {self.plant_id!r}; phos.synth builds {', '.join(PLANT_IDS)}"
            )
        return self

    def load(self) -> Dataset:
        """Run the plant and return the corpus. Deterministic: same spec, same corpus."""
        run = run_plant(self.plant_id, self.spec)
        return to_dataset(run, self.name or None)

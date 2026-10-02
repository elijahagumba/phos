"""Finding the three things a breaking run needs, and refusing to run on two of them.

A run needs an attacked corpus with its measured ground truth, the true-state record beside it, and
— separately — a corpus of the same plant's *normal* operation to fit a baseline on. The third is
the one that is easy to get wrong, so it is a required argument rather than a fallback: a model
fitted on the attacked corpus's own attack-free prefix would be starved, because D2 puts the first
attack four hours into a five-day run and these plants have a daily cycle. Four hours of a
twenty-four hour rhythm is not a baseline, and a breaking-point map measured against one would
describe a badly-fitted model rather than Atlas.

Everything here reads what D1 and D2 already wrote. Nothing regenerates a corpus, and nothing
writes into ``data/``.
"""

import json
import logging
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from phos.atlas import SubsystemMap, load_topology
from phos.eval import Dataset, LabelledCsvAdapter
from phos.synth.attacks import (
    MANIFEST_FILE,
    TELEMETRY_FILE,
    TRUTH_FILE,
    AttackFlavour,
    AttackManifest,
)

__all__ = [
    "TOPOLOGY_FILE",
    "AttackCorpus",
    "CorpusNotFoundError",
    "NormalCorpus",
    "discover_attack_corpora",
    "load_attack_corpus",
    "load_normal_corpus",
]

logger = logging.getLogger(__name__)

TOPOLOGY_FILE: Final = "topology.toml"
"""The declared subsystem map D1 writes beside every corpus."""

TIMESTAMP_COLUMN: Final = "timestamp"
LABEL_COLUMN: Final = "label"


class CorpusNotFoundError(FileNotFoundError):
    """A corpus a run needs is not on disk, named along with the command that produces it.

    A distinct type because the remedy is always the same and always mechanical: run the generator.
    Callers turn this into an instruction rather than a stack trace.
    """


class NormalCorpus(BaseModel):
    """A corpus of the plant behaving normally, for fitting a baseline on.

    Attributes:
        name: The dataset name, as its config declared it.
        plant_id: Which plant it is a run of.
        dataset: The observations. Attack-free by construction — D1 generates no attacks — so
            fitting on the whole of it leaks nothing.
        directory: Where it was read from.
    """

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    plant_id: str = Field(min_length=1)
    dataset: Dataset
    directory: Path


class AttackCorpus(BaseModel):
    """An attacked corpus, its measured ground truth, and the true state underneath it.

    Attributes:
        manifest: D2's record — the plant's declaration, every attack's measured ground truth, and
            the caveats that must travel with any number measured here.
        dataset: The telemetry Atlas is allowed to see, labelled with the attack windows.
        truth_path: The true-state record beside it. Read on demand rather than eagerly, because a
            robustness pass over a corrupted corpus has no use for it.
        topology_path: The declared subsystem map.
        directory: Where it was read from.

    Invariants:
        The manifest's flavour matches what the corpus can be used for — a detection corpus carries
        attacks and a hostile one carries none, which D2 guarantees and this records.
    """

    model_config = ConfigDict(frozen=True)

    manifest: AttackManifest
    dataset: Dataset
    truth_path: Path
    topology_path: Path
    directory: Path

    @property
    def name(self) -> str:
        """The dataset name."""
        return self.manifest.name

    @property
    def flavour(self) -> AttackFlavour:
        """Which of the two non-interchangeable claims this corpus can support."""
        return self.manifest.flavour

    def subsystem_map(self) -> SubsystemMap:
        """Return 5B's declared partition for this corpus's signals.

        Returns:
            The `SubsystemMap`, built against exactly the features the corpus holds.

        Note:
            Loaded against the **plant id** rather than the dataset name, because D1 writes one
            topology per plant and every corpus of that plant — normal or attacked — shares it.
        """
        return load_topology(
            self.topology_path,
            {observation.feature for observation in self.dataset.observations},
            corpus=self.manifest.plant_id,
        )


def _adapter(path: Path, name: str, note: str) -> LabelledCsvAdapter:
    """Build the adapter D1 and D2 write for, with their column names."""
    return LabelledCsvAdapter(
        path=path,
        timestamp_column=TIMESTAMP_COLUMN,
        label_column=LABEL_COLUMN,
        name=name,
        source_note=note,
    )


def _require(path: Path, what: str, command: str) -> None:
    """Raise a `CorpusNotFoundError` naming the command that would produce ``path``."""
    if not path.is_file():
        raise CorpusNotFoundError(
            f"{what} is not at {path}. The synthetic corpora are generated rather than committed; "
            f"produce it with:  {command}"
        )


def load_normal_corpus(directory: Path) -> NormalCorpus:
    """Read a D1 normal corpus from its generated directory.

    Args:
        directory: The corpus directory, e.g. ``data/synth/synth-water-treatment-train``.

    Returns:
        The corpus, loaded.

    Raises:
        CorpusNotFoundError: If the telemetry or manifest is missing, naming the generator command.
    """
    manifest_path = directory / MANIFEST_FILE
    telemetry = directory / TELEMETRY_FILE
    _require(
        manifest_path,
        f"the manifest for {directory.name}",
        "python scripts/generate_synth.py --all",
    )
    _require(
        telemetry, f"the telemetry for {directory.name}", "python scripts/generate_synth.py --all"
    )

    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    dataset = _adapter(
        telemetry,
        directory.name,
        f"{directory.name} | D1 synthetic normal operation | {telemetry}",
    ).load()
    logger.debug(
        "loaded normal corpus %s: %d observations", directory.name, len(dataset.observations)
    )
    return NormalCorpus(
        name=str(raw["name"]),
        plant_id=str(raw["plant_id"]),
        dataset=dataset,
        directory=directory,
    )


def load_attack_corpus(directory: Path) -> AttackCorpus:
    """Read a D2 attack corpus, its manifest and the paths beside it.

    Args:
        directory: The corpus directory, e.g.
            ``data/synth/attacks/synth-attack-water-treatment-graded``.

    Returns:
        The corpus, with its manifest parsed into D2's own type so a malformed one fails here
        rather than halfway through a measurement.

    Raises:
        CorpusNotFoundError: If the manifest or telemetry is missing, naming the generator command.
    """
    manifest_path = directory / MANIFEST_FILE
    telemetry = directory / TELEMETRY_FILE
    command = "python scripts/generate_attacks.py --all"
    _require(manifest_path, f"the manifest for {directory.name}", command)
    _require(telemetry, f"the telemetry for {directory.name}", command)

    manifest = AttackManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    dataset = _adapter(
        telemetry,
        manifest.name,
        f"{manifest.name} | D2 graded attack library | {telemetry}",
    ).load()
    logger.debug(
        "loaded attack corpus %s: %d observations, %d attack(s), flavour %s",
        manifest.name,
        len(dataset.observations),
        len(manifest.attacks),
        manifest.flavour.value,
    )
    return AttackCorpus(
        manifest=manifest,
        dataset=dataset,
        truth_path=directory / TRUTH_FILE,
        topology_path=directory / TOPOLOGY_FILE,
        directory=directory,
    )


def discover_attack_corpora(root: Path, names: tuple[str, ...] = ()) -> tuple[Path, ...]:
    """Return every attack-corpus directory under ``root``, in filename order.

    Args:
        root: The directory D2's generator writes into, usually ``data/synth/attacks``.
        names: Restrict to these corpus directory names. Empty means all of them.

    Returns:
        The directories holding a manifest, sorted so a run is reproducible in its ordering.
    """
    found = tuple(
        path.parent
        for path in sorted(root.glob(f"*/{MANIFEST_FILE}"))
        if not names or path.parent.name in names
    )
    logger.debug("discovered %d attack corpus/corpora under %s", len(found), root)
    return found

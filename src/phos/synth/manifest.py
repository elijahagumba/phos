"""What a generated corpus records about itself, so that it can be audited and regenerated.

Nothing the synthetic engine emits as payload is committed to git — a dataset that can be
regenerated exactly from a seed does not need to be stored, and storing it would put a large
binary in a repository whose whole claim is reproducibility. What is committed is the generator
and the config. What travels *beside* the payload is this manifest, and it has to carry enough
that someone holding only the manifest can say what the data is, check the copy they have is the
copy that was described, and produce it again.

So it records four things, and each has a reason:

- **The run** — plant, seed, start, duration, sampling rate. This is the regeneration recipe, and
  it is complete: nothing else the generator does is random.
- **The plant's whole declaration** — every signal with its span and its error model, every
  declared coupling, the topology and the control network. Embedded rather than summarised,
  because the couplings are the plant's claim about what makes its signals related, and a reviewer
  should not have to read the physics to check it.
- **The benign events** — what legitimately happened, when, and what it changed. Ground truth in
  its own right: D3 needs to know whether a detection landed on an attack or on a backwash.
- **The outputs and their digests** — so a corpus that has been regenerated can be *shown* to be
  the same corpus, not merely assumed to be.

And one thing more: `MODEL_NOT_REALITY_CAVEAT`, in the manifest itself, so a result quoted from
this corpus cannot be separated from the sentence saying what a plant model is.
"""

import hashlib
import json
import logging
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from phos.synth.plant import MODEL_NOT_REALITY_CAVEAT, BenignEvent, PlantDescription, RunSpec
from phos.synth.run import PlantRun
from phos.synth.topology import SYNTHETIC_TOPOLOGY_CAVEAT

__all__ = [
    "MANIFEST_SCHEMA_VERSION",
    "GeneratedFile",
    "SynthManifest",
    "build_manifest",
    "digest_of",
    "write_manifest",
]

logger = logging.getLogger(__name__)

MANIFEST_SCHEMA_VERSION: Final = 1
"""Bumped when the manifest layout changes incompatibly."""

_DIGEST_CHUNK: Final = 1 << 20


def digest_of(path: Path) -> tuple[str, int]:
    """Return ``(sha256 hex digest, size in bytes)`` for a generated file.

    Read in chunks so a multi-gigabyte capture does not have to fit in memory.
    """
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while chunk := handle.read(_DIGEST_CHUNK):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


class GeneratedFile(BaseModel):
    """One file a generation run produced, with what it holds and what it hashes to.

    Attributes:
        filename: Name of the file, relative to the corpus directory.
        kind: What it is — ``"telemetry-csv"``, ``"capture-pcap"`` or ``"topology-toml"``.
        records: Rows, frames or subsystems, as the kind implies.
        sha256: Digest of the bytes, so a regenerated copy can be shown identical.
        size_bytes: Size on disk.
    """

    model_config = ConfigDict(frozen=True)

    filename: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    records: int = Field(ge=0)
    sha256: str = Field(min_length=64, max_length=64)
    size_bytes: int = Field(ge=0)


class SynthManifest(BaseModel):
    """Everything about a generated corpus except the payload itself.

    Attributes:
        schema_version: Manifest format version.
        name: The dataset's name, as the config gave it.
        plant_id: Which plant was run.
        spec: The run — seed, start, duration, sampling rate. The regeneration recipe.
        samples: How many samples the run produced.
        description: The plant's full declaration: signals, units, couplings, control network.
        events: The benign operational events the run contained.
        files: The outputs, with digests.
        label_policy: What ground truth says about this corpus. D1 emits one value.
        traffic_seed: Seed for the capture's timing jitter, which is drawn separately from the
            plant's own randomness so the two outputs stay independently reproducible.
        note: Free-text note from the config.
        caveats: What must travel with any number measured on this corpus.
    """

    model_config = ConfigDict(frozen=True)

    schema_version: int = MANIFEST_SCHEMA_VERSION
    name: str = Field(min_length=1)
    plant_id: str = Field(min_length=1)
    spec: RunSpec
    samples: int = Field(ge=0)
    description: PlantDescription
    events: tuple[BenignEvent, ...] = ()
    files: tuple[GeneratedFile, ...] = ()
    label_policy: str = "Every sample is labelled normal. D1 generates no attacks."
    traffic_seed: int = 0
    note: str = ""
    caveats: tuple[str, ...] = (MODEL_NOT_REALITY_CAVEAT, SYNTHETIC_TOPOLOGY_CAVEAT)


def build_manifest(
    run: PlantRun,
    name: str,
    files: tuple[GeneratedFile, ...],
    traffic_seed: int,
    note: str = "",
) -> SynthManifest:
    """Assemble the manifest for a completed generation run.

    Args:
        run: The run that was simulated.
        name: The dataset name from the config.
        files: The outputs written, already digested.
        traffic_seed: Seed used for the capture's timing jitter.
        note: Free-text note from the config.

    Returns:
        The manifest, ready to be written beside the payload.
    """
    return SynthManifest(
        name=name,
        plant_id=run.plant_id,
        spec=run.spec,
        samples=len(run.steps),
        description=run.description,
        events=run.events,
        files=files,
        traffic_seed=traffic_seed,
        note=note,
    )


def write_manifest(manifest: SynthManifest, path: Path) -> None:
    """Write a manifest as indented JSON, overwriting ``path`` if it exists."""
    path.write_text(
        json.dumps(json.loads(manifest.model_dump_json()), indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    logger.debug("wrote manifest for %s to %s", manifest.name, path)

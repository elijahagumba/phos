"""Producing one corpus on disk: the files, their names, and what refuses to be written.

The command-line wrapper in ``scripts/generate_synth.py`` owns argument parsing and where the
repository keeps its configs. Everything that decides *what a corpus is* lives here, in the
package, so it is covered by the package's tests rather than by a script nothing imports.

A corpus is a directory holding four things, and the fourth exists because of the first three:

* ``telemetry.csv`` — the prepared-corpus shape `phos.eval.LabelledCsvAdapter` reads unchanged;
* ``topology.toml`` — which signals sit on which physical unit, in the format
  `phos.atlas.topology.load_topology` reads;
* ``capture.pcap`` — Modbus/TCP control traffic, for a plant whose real counterpart is actually
  run over Modbus. Absent otherwise, and its absence is recorded rather than explained away;
* ``manifest.json`` — the regeneration recipe, the plant's declaration and couplings, the benign
  events, and a digest of each file above.

**An empty corpus is refused rather than written.** A directory holding a header row and no data
loads without error and scores as a corpus in which nothing went wrong, which is the most
expensive kind of silence a measurement pipeline can contain.
"""

import logging
from pathlib import Path
from typing import Final

from phos.synth.catalogue import DatasetConfig
from phos.synth.manifest import (
    GeneratedFile,
    SynthManifest,
    build_manifest,
    digest_of,
    write_manifest,
)
from phos.synth.realism import RealismProfile
from phos.synth.run import PlantRun, run_plant
from phos.synth.sidecar import write_realism_sidecar
from phos.synth.telemetry import write_csv
from phos.synth.topology import write_topology
from phos.synth.traffic import TrafficPolicy, modbus_frames, write_pcap

__all__ = [
    "CAPTURE_FILE",
    "MANIFEST_FILE",
    "TELEMETRY_FILE",
    "TOPOLOGY_FILE",
    "GenerationError",
    "generate_dataset",
]

logger = logging.getLogger(__name__)

TELEMETRY_FILE: Final = "telemetry.csv"
CAPTURE_FILE: Final = "capture.pcap"
TOPOLOGY_FILE: Final = "topology.toml"
MANIFEST_FILE: Final = "manifest.json"


class GenerationError(RuntimeError):
    """Raised when a dataset cannot be produced as its config describes it."""


def generate_dataset(
    config: DatasetConfig,
    output: Path,
    *,
    with_capture: bool = True,
    realism: RealismProfile | None = None,
) -> tuple[Path, SynthManifest]:
    """Generate one corpus and return its directory and the manifest written into it.

    Args:
        config: The dataset to produce.
        output: Directory to create the corpus directory inside. Created if absent.
        with_capture: Whether to write the pcap. Off, only telemetry and topology are produced;
            the manifest then simply does not list a capture, which is the same way it records a
            plant that has no control network at all.
        realism: Ordinary trouble to apply, or ``None`` for a quiet profile. A quiet profile
            writes no ``realism.json`` sidecar, so existing quiet corpora stay byte-identical.

    Returns:
        ``(corpus directory, manifest)``.

    Raises:
        GenerationError: If the configured run holds no samples.
    """
    run = run_plant(config.plant_id, config.run_spec(), realism=realism)
    if not run.steps:
        raise GenerationError(f"{config.name}: the configured run holds no samples")

    directory = output / config.name
    directory.mkdir(parents=True, exist_ok=True)

    files = [_telemetry(run, directory), _topology(run, directory)]
    capture = _capture(run, config, directory) if with_capture else None
    if capture is not None:
        files.append(capture)
    if not run.realism_profile.is_quiet():
        files.append(write_realism_sidecar(run.realism_profile, run.realism, directory))

    manifest = build_manifest(
        run,
        name=config.name,
        files=tuple(files),
        traffic_seed=config.traffic_seed,
        note=config.note.strip(),
    )
    write_manifest(manifest, directory / MANIFEST_FILE)
    logger.debug(
        "generated %s: %d samples, %d benign event(s), %d file(s)",
        config.name,
        len(run.steps),
        len(run.events),
        len(files),
    )
    return directory, manifest


def _telemetry(run: PlantRun, directory: Path) -> GeneratedFile:
    """Write the prepared-corpus CSV and describe it for the manifest."""
    path = directory / TELEMETRY_FILE
    rows = write_csv(run, path)
    sha256, size = digest_of(path)
    return GeneratedFile(
        filename=TELEMETRY_FILE, kind="telemetry-csv", records=rows, sha256=sha256, size_bytes=size
    )


def _topology(run: PlantRun, directory: Path) -> GeneratedFile:
    """Write the topology declaration and describe it for the manifest."""
    path = directory / TOPOLOGY_FILE
    write_topology(run.description, path)
    sha256, size = digest_of(path)
    return GeneratedFile(
        filename=TOPOLOGY_FILE,
        kind="topology-toml",
        records=len(run.description.units),
        sha256=sha256,
        size_bytes=size,
    )


def _capture(run: PlantRun, config: DatasetConfig, directory: Path) -> GeneratedFile | None:
    """Write the Modbus capture, or return ``None`` for a plant with no control network."""
    frames = modbus_frames(
        run.description,
        run.steps,
        TrafficPolicy(seed=config.traffic_seed),
        dropouts=run.realism.dropouts,
    )
    if not frames:
        logger.debug("%s has no control network, so no capture", config.plant_id)
        return None
    path = directory / CAPTURE_FILE
    written = write_pcap(frames, path)
    sha256, size = digest_of(path)
    return GeneratedFile(
        filename=CAPTURE_FILE, kind="capture-pcap", records=written, sha256=sha256, size_bytes=size
    )

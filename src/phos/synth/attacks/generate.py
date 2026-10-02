"""Producing one attack corpus on disk: the files, and the one that is not for the detector.

A detection corpus is a directory holding five things, and the fifth is the reason the other four
can be trusted:

* ``telemetry.csv`` — the prepared-corpus shape `phos.eval.LabelledCsvAdapter` reads unchanged,
  with the label column now carrying ones inside the attack windows;
* ``truth.csv`` — **what the plant was actually doing**, sample by sample. Never fed to a detector,
  because a detector that could read it would be detecting nothing. It exists so a liar attack can
  be labelled honestly: where the telemetry says the clearwell was calm, this says how full it
  really was;
* ``topology.toml`` — unchanged from D1, because an attack does not move a signal onto a different
  tank;
* ``capture.pcap`` — the control traffic, now including whatever the attacker put on the wire;
* ``manifest.json`` — the regeneration recipe, the plant's declaration, the benign events, the
  measured ground truth for every attack, digests of each file, and the caveats.

An input-hostile corpus holds the same telemetry and topology, corrupted, and **no attack
intervals at all**. Its manifest records what was done to the file under a separate field, and the
label policy says in words that nothing here is a plant attack.

**Why the CSV writer is not D1's.** `phos.synth.telemetry.write_csv` hard-codes a label of zero,
which is right for a corpus with no attacks and wrong here. Rather than change it — D2 modifies no
D1 module — the row is built the same way in one place below, to the same five decimal places, so
the two shapes cannot drift. The formatting is identical on purpose: a corpus whose numbers were
formatted differently from a normal one would be separable by its formatting rather than by its
contents, which is the anti-fingerprint failure this PART exists to avoid.
"""

import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from phos.synth.attacks.battery import AttackDatasetConfig
from phos.synth.attacks.hostile import apply_hostile
from phos.synth.attacks.inject import AttackRun, attack_source_note, inject
from phos.synth.attacks.spec import (
    ATTACKS_ARE_OURS_CAVEAT,
    INPUT_HOSTILE_IS_NOT_SECURITY_CAVEAT,
    AttackFlavour,
    AttackGroundTruth,
    HostileGroundTruth,
)
from phos.synth.manifest import MANIFEST_SCHEMA_VERSION, GeneratedFile, digest_of
from phos.synth.plant import (
    MODEL_NOT_REALITY_CAVEAT,
    BenignEvent,
    PlantDescription,
    RunSpec,
)
from phos.synth.telemetry import LABEL_COLUMN, TIMESTAMP_COLUMN
from phos.synth.topology import SYNTHETIC_TOPOLOGY_CAVEAT, write_topology
from phos.synth.traffic import TrafficPolicy, modbus_frames, write_pcap

__all__ = [
    "CAPTURE_FILE",
    "MANIFEST_FILE",
    "TELEMETRY_FILE",
    "TOPOLOGY_FILE",
    "TRUTH_FILE",
    "AttackGenerationError",
    "AttackManifest",
    "generate_attack_dataset",
    "telemetry_lines",
    "truth_lines",
]

logger = logging.getLogger(__name__)

TELEMETRY_FILE: Final = "telemetry.csv"
TRUTH_FILE: Final = "truth.csv"
CAPTURE_FILE: Final = "capture.pcap"
TOPOLOGY_FILE: Final = "topology.toml"
MANIFEST_FILE: Final = "manifest.json"

_DECIMALS: Final = 5
"""Places every value is written to, matching D1 exactly. See the module docstring."""

_DETECTION_LABEL_POLICY: Final = (
    "One interval per detection attack, labelled over the manipulation window only. The recovery "
    "tail — the plant taking time to come back after the manipulation stops — is recorded in each "
    "attack's truth_departure and is deliberately NOT labelled, so a detector that fires only "
    "while the attack is running is not penalised for the plant's inertia. Every other sample is "
    "normal."
)

_HOSTILE_LABEL_POLICY: Final = (
    "No attack intervals. Nothing in this corpus is a plant attack: it is a normal run whose FILE "
    "has been corrupted, and the corruptions are recorded under `hostile` rather than as ground "
    "truth anything was supposed to detect. A detection scored against this corpus would be "
    "scoring against a claim it does not support."
)


class AttackGenerationError(RuntimeError):
    """Raised when an attack dataset cannot be produced as its config describes it."""


class AttackManifest(BaseModel):
    """Everything about a generated attack corpus except the payload itself.

    Attributes:
        schema_version: Manifest format version, shared with D1's.
        name: The dataset's name, as the config gave it.
        plant_id: Which plant was run.
        flavour: Which of the two claims this corpus can support. Derived from which list the
            config declared, and the two are mutually exclusive by construction.
        spec: The run — seed, start, duration, sampling rate. Half of the regeneration recipe.
        samples: How many samples the run produced.
        attacked_samples: How many of them ground truth marks as attacked. Zero for an
            input-hostile corpus, and that is not an omission.
        description: The plant's full declaration.
        events: The benign operational events the run contained. A detection landing here landed
            on a Tuesday morning, not on an attack.
        attacks: Measured ground truth for every detection attack. Empty for an input-hostile
            corpus.
        hostile: What was done to the file. Empty for a detection corpus.
        commands_injected: Control-network exchanges an attacker added.
        files: The outputs, with digests.
        label_policy: What ground truth says about this corpus, in words.
        traffic_seed: Seed for the capture's timing jitter.
        note: Free-text note from the config.
        caveats: What must travel with any number measured on this corpus.
    """

    model_config = ConfigDict(frozen=True)

    schema_version: int = MANIFEST_SCHEMA_VERSION
    name: str = Field(min_length=1)
    plant_id: str = Field(min_length=1)
    flavour: AttackFlavour
    spec: RunSpec
    samples: int = Field(ge=0)
    attacked_samples: int = Field(default=0, ge=0)
    description: PlantDescription
    events: tuple[BenignEvent, ...] = ()
    attacks: tuple[AttackGroundTruth, ...] = ()
    hostile: tuple[HostileGroundTruth, ...] = ()
    commands_injected: int = Field(default=0, ge=0)
    files: tuple[GeneratedFile, ...] = ()
    label_policy: str = ""
    traffic_seed: int = 0
    note: str = ""
    caveats: tuple[str, ...] = (
        MODEL_NOT_REALITY_CAVEAT,
        SYNTHETIC_TOPOLOGY_CAVEAT,
        ATTACKS_ARE_OURS_CAVEAT,
        INPUT_HOSTILE_IS_NOT_SECURITY_CAVEAT,
    )


def telemetry_lines(run: AttackRun) -> tuple[str, ...]:
    """Return the corpus as text lines: a header, then one record per sample.

    The label column carries `ATTACK_LABEL_VALUE` inside an attack window and
    `NORMAL_LABEL_VALUE` everywhere else. Values are written to five decimal places, exactly as
    D1 writes them — see the module docstring for why that matters more than it looks.
    """
    keys = run.description.signal_keys()
    header = ",".join([TIMESTAMP_COLUMN, LABEL_COLUMN, *keys])
    return (
        header,
        *(
            ",".join(
                [
                    step.timestamp.isoformat(),
                    run.label_at(step.timestamp),
                    *(f"{step.report.values[key]:.{_DECIMALS}f}" for key in keys),
                ]
            )
            for step in run.attacked.steps
        ),
    )


def truth_lines(run: AttackRun) -> tuple[str, ...]:
    """Return the true-state record as text lines, in the same shape minus the label.

    This is ground truth, not telemetry. It carries what the plant was *actually* doing at every
    sample, which under a false-data-injection attack is a different series from the one the
    corpus publishes. Nothing that scores a detector may read it.
    """
    keys = run.description.signal_keys()
    header = ",".join([TIMESTAMP_COLUMN, *keys])
    return (
        header,
        *(
            ",".join(
                [
                    step.timestamp.isoformat(),
                    *(f"{step.truth.values[key]:.{_DECIMALS}f}" for key in keys),
                ]
            )
            for step in run.attacked.steps
        ),
    )


def generate_attack_dataset(
    config: AttackDatasetConfig, output: Path, *, with_capture: bool = True
) -> tuple[Path, AttackManifest]:
    """Generate one attack corpus and return its directory and the manifest written into it.

    Args:
        config: The dataset to produce. Declares either detection attacks or input-hostile cases,
            never both.
        output: Directory to create the corpus directory inside. Created if absent.
        with_capture: Whether to write the pcap.

    Returns:
        ``(corpus directory, manifest)``.

    Raises:
        AttackGenerationError: If the configured run holds no samples.
        ValueError: If an attack cannot be staged against this plant, if two windows overlap, or
            if an attack turned out to have changed nothing.
    """
    run = inject(config.plant_id, config.run_spec(), config.attacks)
    if not run.attacked.steps:
        raise AttackGenerationError(f"{config.name}: the configured run holds no samples")

    lines = telemetry_lines(run)
    hostile: list[HostileGroundTruth] = []
    for plan in config.hostile:
        lines, record = apply_hostile(lines, plan, run.description)
        hostile.append(record)

    directory = output / config.name
    directory.mkdir(parents=True, exist_ok=True)

    files = [
        _write(directory / TELEMETRY_FILE, lines, "telemetry-csv", len(lines) - 1),
        _write(directory / TRUTH_FILE, truth_lines(run), "truth-csv", len(run.attacked.steps)),
        _topology(run, directory),
    ]
    capture = _capture(run, config, directory) if with_capture else None
    if capture is not None:
        files.append(capture)

    manifest = AttackManifest(
        name=config.name,
        plant_id=config.plant_id,
        flavour=config.flavour,
        spec=run.spec,
        samples=len(run.attacked.steps),
        attacked_samples=run.attacked_samples(),
        description=run.description,
        events=run.attacked.events,
        attacks=run.attacks,
        hostile=tuple(hostile),
        commands_injected=run.commands_injected(),
        files=tuple(files),
        label_policy=(
            _DETECTION_LABEL_POLICY
            if config.flavour is AttackFlavour.DETECTION
            else _HOSTILE_LABEL_POLICY
        ),
        traffic_seed=config.traffic_seed,
        note=f"{config.note.strip()} {attack_source_note(run)}".strip(),
    )
    (directory / MANIFEST_FILE).write_text(
        manifest.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    logger.debug(
        "generated %s: %d samples, %d attack(s), %d hostile case(s), %d file(s)",
        config.name,
        len(run.attacked.steps),
        len(run.attacks),
        len(hostile),
        len(files),
    )
    return directory, manifest


def _write(path: Path, lines: Sequence[str], kind: str, records: int) -> GeneratedFile:
    """Write text lines and describe the file for the manifest."""
    path.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8", newline="")
    sha256, size = digest_of(path)
    return GeneratedFile(
        filename=path.name, kind=kind, records=records, sha256=sha256, size_bytes=size
    )


def _topology(run: AttackRun, directory: Path) -> GeneratedFile:
    """Write the topology declaration, unchanged from D1 — an attack moves no instrument."""
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


def _capture(run: AttackRun, config: AttackDatasetConfig, directory: Path) -> GeneratedFile | None:
    """Write the control traffic, attacker's writes included, or ``None`` for a plant with none."""
    frames = modbus_frames(
        run.description,
        run.attacked.steps,
        TrafficPolicy(seed=config.traffic_seed),
        dropouts=run.attacked.realism.dropouts,
    )
    if not frames:
        logger.debug("plant %s has no control network, so no capture", config.plant_id)
        return None
    path = directory / CAPTURE_FILE
    written = write_pcap(frames, path)
    sha256, size = digest_of(path)
    return GeneratedFile(
        filename=CAPTURE_FILE, kind="capture-pcap", records=written, sha256=sha256, size_bytes=size
    )

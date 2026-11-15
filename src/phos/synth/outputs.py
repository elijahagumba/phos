"""What one generated plant writes to disk, and the manifest that says how to get it back.

PART R3. A drawn plant has existed only in memory until now. This module writes the eight files a
generated corpus is made of, into one directory per plant:

- ``telemetry.csv`` — the prepared-corpus shape, timestamp and label column included, read by
  `phos.eval.LabelledCsvAdapter` unchanged.
- ``labels.json`` — ground truth: what legitimately happened and when. PART S6's scorer.
- ``topology.toml`` — which signals sit on which physical unit, in the form
  `phos.atlas.topology.load_topology` reads.
- ``plant.json`` — the `PlantSpec` itself, for regeneration, review and PART V1's viewer.
- ``control.json`` — what the control logic *is*, in plain language. A reviewer, and PART V4.
- ``registers.json`` — the Modbus register map, per plant.
- ``capture.pcap`` — Modbus/TCP traffic, read by `phos.atlas.packet.dissect_capture` unchanged.
- ``manifest.json`` — family, seeds, rejections, parameters, digests and the caveat.

**Nothing here is committed.** A corpus regenerated exactly from a family and a seed does not
need to be stored, and storing it would put a large binary in a repository whose whole claim is
reproducibility. What is committed is the generator; what travels beside the payload is the
manifest.

**The capture and the telemetry come from one run.** `phos.synth.run.PlantRun` is simulated once
and every file is a projection of it, so the capture answers polls with the *same reported
readings* the telemetry publishes. Two outputs of one plant cannot disagree about what it said —
which matters more here than tidiness, because a detector that saw the wire and the historian
disagree on honest data would be right to distrust both.

**The register map is per plant, and it has to be.** PART R2 draws tag names and sensor layouts
per seed, so there is no longer a fixed map to document once. ``registers.json`` is rendered from
the spec's own `ControlNetwork`, which is the same declaration `phos.synth.traffic` builds the
frames from, so the document and the wire cannot drift.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Final

import numpy
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from phos.synth.events import (
    EventCatalogue,
    EventRecord,
    EventSchedule,
    assess_events,
    plan_events,
)
from phos.synth.families import PlantFamily
from phos.synth.injection import Injection
from phos.synth.manifest import GeneratedFile, digest_of
from phos.synth.plant import (
    MODEL_NOT_REALITY_CAVEAT,
    BenignEvent,
    PlantDescription,
    RunSpec,
    SignalKind,
    register_count,
)
from phos.synth.plant_spec import ControllerKind, ControllerSpec, PlantSpec
from phos.synth.run import PlantRun
from phos.synth.telemetry import write_csv
from phos.synth.templates import build_from_spec
from phos.synth.topology import SYNTHETIC_TOPOLOGY_CAVEAT, write_topology
from phos.synth.traffic import TrafficPolicy, modbus_frames, write_pcap
from phos.synth.validity import Thresholds, ValidDraw, draw_valid

__all__ = [
    "CAPTURE_FILE",
    "CONTROL_FILE",
    "LABELS_FILE",
    "MANIFEST_FILE",
    "OUTPUT_SCHEMA_VERSION",
    "PLANT_FILE",
    "REGISTERS_FILE",
    "TELEMETRY_FILE",
    "TOPOLOGY_FILE",
    "GeneratedPlant",
    "GeneratedPlantManifest",
    "OutputError",
    "control_document",
    "generate_plant",
    "labels_document",
    "register_document",
    "run_from_spec",
    "verify",
]

logger = logging.getLogger(__name__)

OUTPUT_SCHEMA_VERSION: Final = 1
"""Bumped when the set of files or the manifest layout changes incompatibly."""

TELEMETRY_FILE: Final = "telemetry.csv"
LABELS_FILE: Final = "labels.json"
TOPOLOGY_FILE: Final = "topology.toml"
PLANT_FILE: Final = "plant.json"
CONTROL_FILE: Final = "control.json"
REGISTERS_FILE: Final = "registers.json"
CAPTURE_FILE: Final = "capture.pcap"
MANIFEST_FILE: Final = "manifest.json"


class OutputError(RuntimeError):
    """Raised when a plant cannot be written as a corpus."""


def run_from_spec(
    plant_spec: PlantSpec,
    run: RunSpec,
    traffic_seed: int = 0,
    injection: Injection | None = None,
) -> PlantRun:
    """Simulate a drawn plant for a whole run and return every sample.

    The counterpart of `phos.synth.run.run_plant` for a plant that has no entry in the plant
    registry, because it was drawn rather than written. One run, every output a projection of it.

    Args:
        plant_spec: The plant to run.
        run: How long for, how often, and from what seed.
        traffic_seed: Unused here; recorded by the caller. Kept in the signature so a reader does
            not have to wonder where the capture's jitter seed went — it belongs to the capture,
            not to the run, and `phos.synth.traffic` takes it separately so changing the jitter
            cannot move a single telemetry reading.
        injection: The plant- and process-layer events to apply, or ``None`` for a normal run.
            Network-layer events are not here — they act on the capture, not the run.

    Returns:
        The completed run.
    """
    del traffic_seed
    plant = build_from_spec(plant_spec, run)
    steps = tuple(plant.step(injection) for _ in range(run.n_steps))
    return PlantRun(
        plant_id=plant_spec.plant_id,
        description=plant_spec.describe(),
        spec=run,
        steps=steps,
        events=plant.events,
    )


def labels_document(run: PlantRun, events: Sequence[EventRecord] = ()) -> dict[str, object]:
    """Return the ground truth about what happened, in the shape the scorer will read.

    **Every sample of a PART R3 corpus is normal**, so ``attack_intervals`` is empty and present
    anyway. The column exists in the telemetry and the list exists here for the same reason: a
    corpus that omitted its labels would be indistinguishable from one whose labels were lost,
    and PART R4 writes into exactly this shape.

    What is *not* empty is the benign events. An operator moved a setpoint, a demand surged, a
    feed turned cold — all legitimate, all ground truth in their own right, and all of them the
    cover a later mimic attack will hide among. A detection landing on one of these landed on a
    Tuesday morning, and the scorer can only know that because this file says so.

    **The scripted events are the ground truth a scorer grades against.** When PART R4's catalogue
    is used, ``events`` carries the attacks, faults and maintenance, each with its layer and its
    measured facts. The attack and fault intervals are the detection targets; the maintenance
    intervals are sanctioned cover, labelled so a detection on one is not counted as a catch.
    """
    targets = [record for record in events if record.kind.value in ("attack", "fault")]
    return {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "plant_id": run.plant_id,
        "label_policy": (
            "Benign events and operator actions are normal. Scripted events carry their own "
            "kind: attacks and faults are detection targets, maintenance is sanctioned cover."
            if events
            else "Every sample is labelled normal. The benign events below are legitimate "
            "operation and are ground truth, not targets."
        ),
        "attack_intervals": [
            {
                "event_id": record.event_id,
                "start": record.started_at.isoformat(),
                "end": record.ended_at.isoformat(),
                "kind": record.kind.value,
                "type": record.type,
            }
            for record in targets
        ],
        "scripted_events": [record.document() for record in events],
        "benign_events": [_event_document(event) for event in run.events],
        "caveats": [MODEL_NOT_REALITY_CAVEAT],
    }


def _event_document(event: BenignEvent) -> dict[str, object]:
    """Return one benign event as the labels file carries it."""
    return {
        "kind": event.kind,
        "label": event.label,
        "started_at": event.started_at.isoformat(),
        "ended_at": event.ended_at.isoformat(),
        "writes": list(event.writes),
        "parameters": dict(sorted(event.parameters.items())),
        "detail": event.detail,
    }


def control_document(spec: PlantSpec) -> dict[str, object]:
    """Return what this plant's control logic *is*, in a form a person can read.

    PART R3 asks for a control program export, and this is deliberately not a PLC program: these
    plants have no ladder logic and inventing some would be fake realism. What they do have is a
    set of declared loops with their tunings, a set of actuators the process drives directly, and
    a role map saying what every randomised tag name means. That is the content a reviewer needs
    in order to say whether the plant is plausible, and the content PART V4 renders as "the
    control logic in plain language".

    Args:
        spec: The plant.

    Returns:
        The document.
    """
    description = spec.describe()
    actuators = set(description.keys_of_kind(SignalKind.ACTUATOR))
    looped = {
        controller.output for controller in spec.controllers if controller.output in actuators
    }
    return {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "plant_id": spec.plant_id,
        "process": spec.process,
        "summary": spec.summary,
        "loops": [_controller_document(spec, controller) for controller in spec.controllers],
        "driven_by_the_process": [
            {
                "signal": key,
                "role": _role_name(spec, key),
                "note": (
                    "Not regulated: the process template moves this directly — a recipe step, a "
                    "phase, or a fixed position — so it has no loop and no tuning."
                ),
            }
            for key in sorted(actuators - looped)
        ],
        "roles": {
            key: {"role": role.role, "train": role.train, "stage": role.stage}
            for key, role in sorted(spec.roles.items())
        },
        "scan_period_seconds": spec.scan_period_seconds,
        "caveats": [MODEL_NOT_REALITY_CAVEAT],
    }


def _controller_document(spec: PlantSpec, controller: ControllerSpec) -> dict[str, object]:
    """Return one control loop as the control export carries it."""
    cascade = spec.cascade_slave(controller.controller_id)
    target: dict[str, object]
    if controller.setpoint is not None:
        target = {"kind": "setpoint_signal", "signal": controller.setpoint}
    elif controller.setpoint_value is not None:
        target = {"kind": "fixed", "value": controller.setpoint_value}
    else:
        target = {"kind": "cascade", "from_loop": _master_of(spec, controller.controller_id)}
    document: dict[str, object] = {
        "id": controller.controller_id,
        "kind": controller.kind.value,
        "measures": controller.measurement,
        "measures_role": _role_name(spec, controller.measurement),
        "drives": cascade if cascade is not None else controller.output,
        "drives_kind": "loop" if cascade is not None else "signal",
        "target": target,
        "description": controller.description,
    }
    if controller.kind is ControllerKind.PI:
        document["tuning"] = {
            "gain": controller.gain,
            "integral_time_seconds": controller.integral_time_seconds,
            "output_low": controller.low,
            "output_high": controller.high,
            "bias": controller.bias,
            "reverse_acting": controller.reverse_acting,
        }
    else:
        document["band"] = {"on_below": controller.on_below, "off_above": controller.off_above}
    return document


def _master_of(spec: PlantSpec, controller_id: str) -> str | None:
    """Return the loop that cascades into this one, if any."""
    for candidate in spec.controllers:
        if candidate.output == controller_id:
            return candidate.controller_id
    return None


def _role_name(spec: PlantSpec, key: str) -> str:
    """Return what a signal is, or ``""`` if the plant has not said."""
    role = spec.role_of(key)
    return role.role if role is not None else ""


def register_document(spec: PlantSpec) -> dict[str, object]:
    """Return this plant's Modbus register map, rendered from the declaration the wire uses.

    Per plant rather than once for the package, because PART R2 draws the tag names and the
    sensor layout per seed. Rendered from `PlantSpec.control_network`, which is the same object
    `phos.synth.traffic` assembles its frames from, so the document and the capture cannot drift
    apart.

    Each entry carries the span as well as the address, because an industrial device does not put
    floats on the wire: a transmitter reports a count across its calibrated span, and without the
    span a reader of the capture cannot turn a register value back into an engineering one. The
    two counts at the ends of the span are given explicitly for the same reason.

    Args:
        spec: The plant.

    Returns:
        The document. A plant with no control network returns one that says so rather than an
        empty map, because the absence is a statement about the process and not a gap.
    """
    network = spec.control_network
    if network is None:
        return {
            "schema_version": OUTPUT_SCHEMA_VERSION,
            "plant_id": spec.plant_id,
            "control_network": None,
            "note": (
                "This process declares no control network, so it produces telemetry and no "
                "capture. That is a statement about how such a plant is really run, not a "
                "missing output."
            ),
        }
    description = spec.describe()
    blocks: list[dict[str, object]] = []
    for block in network.blocks:
        entries: list[dict[str, object]] = []
        for offset, key in enumerate(block.signals):
            signal = description.signal(key)
            entries.append(
                {
                    "address": block.start_address + offset,
                    "signal": key,
                    "role": _role_name(spec, key),
                    "label": signal.label,
                    "unit": signal.unit,
                    "kind": signal.kind.value,
                    "span_low": signal.low,
                    "span_high": signal.high,
                    "count_at_low": register_count(signal, signal.low),
                    "count_at_high": register_count(signal, signal.high),
                }
            )
        blocks.append(
            {
                "node_id": block.node_id,
                "start_address": block.start_address,
                "writable": block.writable,
                "registers": entries,
            }
        )
    return {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "plant_id": spec.plant_id,
        "control_network": {
            "poller": network.poller,
            "operator": network.operator,
            "poll_interval_seconds": network.poll_interval_seconds,
            "unit_id": network.unit_id,
            "nodes": [
                {"node_id": node.node_id, "label": node.label, "ip": node.ip, "role": node.role}
                for node in network.nodes
            ],
            "blocks": blocks,
        },
        "write_authority": (
            {node: sorted(granted) for node, granted in sorted(spec.write_authority.grants.items())}
            if spec.write_authority is not None
            else None
        ),
    }


class GeneratedPlantManifest(BaseModel):
    """Everything about a generated plant except the payload, so it can be audited and regenerated.

    Attributes:
        schema_version: Manifest layout version.
        plant_id: The plant.
        family_id: The family it was drawn from.
        process: The process template it runs on.
        master_seed: The seed the whole plant came from. With the family and the code version
            this is the complete regeneration recipe.
        child_seed: The seed of the candidate that was actually accepted. Equal to the master
            seed when the first candidate passed the gate.
        rejections: How many candidates the gate refused before this one. Recorded rather than
            hidden: a high count is a finding about the family's declared ranges.
        rejection_reasons: The refused verdicts, one line each. The count says a family is wide;
            these say in what way, which is what makes it fixable rather than merely known.
        validity_hours: How long each candidate was run before being judged.
        parameters: Every free number the physics read, so a reviewer can see what was drawn
            without rerunning the draw.
        run: The run that was simulated — seed, start, duration, sampling rate.
        samples: How many samples it produced.
        events: The benign operational events the run contained.
        description: The plant's full declaration: signals, units, couplings, control network.
        files: Every output written, with its digest.
        traffic_seed: Seed for the capture's timing jitter, drawn separately from the plant's own
            randomness so the two outputs stay independently reproducible.
        git_commit: The code version, where it could be determined.
        caveats: What must travel with any number measured on this corpus.
    """

    model_config = ConfigDict(frozen=True)

    schema_version: int = OUTPUT_SCHEMA_VERSION
    plant_id: str = Field(min_length=1)
    family_id: str = Field(min_length=1)
    process: str = Field(min_length=1)
    master_seed: int
    child_seed: int
    rejections: int = Field(ge=0)
    rejection_reasons: tuple[str, ...] = ()
    validity_hours: float
    parameters: Mapping[str, float]
    run: RunSpec
    samples: int = Field(ge=0)
    events: tuple[BenignEvent, ...] = ()
    description: PlantDescription
    files: tuple[GeneratedFile, ...] = ()
    traffic_seed: int = 0
    git_commit: str | None = None
    caveats: tuple[str, ...] = (MODEL_NOT_REALITY_CAVEAT, SYNTHETIC_TOPOLOGY_CAVEAT)


@dataclass(frozen=True)
class GeneratedPlant:
    """One generated plant on disk.

    Attributes:
        directory: Where it was written.
        manifest: What it is.
        draw: The accepted draw and the record of what the gate refused on the way.
        schedule: The event schedule, or ``None`` for a normal corpus. Carried so a caller can
            report what the plant could not host, which is otherwise invisible.
    """

    directory: Path
    manifest: GeneratedPlantManifest
    draw: ValidDraw
    schedule: EventSchedule | None = None


def git_commit(start: Path | None = None) -> str | None:
    """Return the current commit, read from ``.git`` rather than asked of ``git``.

    PART R3 asks for the commit "if available", and it genuinely may not be: a corpus generated
    from an installed wheel has no repository behind it. Returning ``None`` and recording that is
    honest; inventing a version string would not be.

    **Read as files, not by running a program.** The first version of this shelled out to
    ``git rev-parse HEAD``, which put ``import subprocess`` in the simulator — and PART R4's own
    rule is that this package imports no process or socket API at all, asserted by
    ``tests/synth/test_no_network.py``. The rule exists so that attack code cannot reach a real
    device, and a generator that spawns processes is exactly the shape that rule is drawn around,
    whatever the process happens to be. Reading two small text files is also faster and cannot
    hang.

    Args:
        start: Where to begin looking for a repository, or ``None`` for this module's own
            location.

    Returns:
        The full commit hash, or ``None`` if there is no repository, no readable HEAD, or a HEAD
        whose ref resolves to nothing.
    """
    git_dir = _git_dir(start or Path(__file__).resolve())
    if git_dir is None:
        return None
    try:
        head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not head.startswith("ref:"):
        return head or None
    ref = head.removeprefix("ref:").strip()
    return _resolve_ref(git_dir, ref)


def _git_dir(start: Path) -> Path | None:
    """Return the directory holding this checkout's HEAD, or ``None`` if there is no repository.

    Handles a worktree, where ``.git`` is a *file* holding ``gitdir: <path>`` rather than a
    directory — which is how this very branch is checked out, so getting it wrong would have
    recorded ``None`` for every plant generated here and nobody would have noticed.
    """
    for directory in (start, *start.parents):
        candidate = directory / ".git"
        if candidate.is_dir():
            return candidate
        if candidate.is_file():
            try:
                pointer = candidate.read_text(encoding="utf-8").strip()
            except OSError:
                return None
            if pointer.startswith("gitdir:"):
                return Path(pointer.removeprefix("gitdir:").strip())
            return None
    return None


def _resolve_ref(git_dir: Path, ref: str) -> str | None:
    """Return the commit a ref points at, looking where git keeps it.

    A worktree's refs live in the *common* directory rather than beside its own HEAD, and a ref
    that has been packed is in ``packed-refs`` rather than in a file of its own. Both are checked,
    because missing either would make the answer depend on whether the repository had been
    garbage-collected lately.
    """
    roots = [git_dir]
    try:
        common = (git_dir / "commondir").read_text(encoding="utf-8").strip()
    except OSError:
        common = ""
    if common:
        roots.append((git_dir / common).resolve())

    for root in roots:
        loose = root / ref
        try:
            if loose.is_file():
                return loose.read_text(encoding="utf-8").strip() or None
        except OSError:
            continue
    for root in roots:
        try:
            packed = (root / "packed-refs").read_text(encoding="utf-8")
        except OSError:
            continue
        for line in packed.splitlines():
            if line.startswith(("#", "^")):
                continue
            commit, _, name = line.partition(" ")
            if name.strip() == ref:
                return commit or None
    return None


def generate_plant(
    family: PlantFamily,
    master_seed: int,
    output: Path,
    *,
    hours: float = 24.0,
    sample_interval_seconds: float | None = None,
    traffic_seed: int = 1,
    thresholds: Thresholds | None = None,
    with_capture: bool = True,
    events: EventCatalogue | None = None,
    event_seed: int = 0,
    skip_impossible_events: bool = False,
) -> GeneratedPlant:
    """Draw a valid plant, run it, and write the whole corpus to disk.

    Args:
        family: The family to draw from.
        master_seed: The seed the plant is drawn from.
        output: Directory to create the plant's own directory inside.
        hours: How long to simulate. The trial run the gate uses is separate and shorter.
        sample_interval_seconds: Sampling and integration step, or ``None`` for the plant's own
            scan period — which is the default because in this engine the sample interval is also
            the interval the controllers run at, so a corpus sampled slower than the plant's
            loops would be a corpus of a differently controlled plant.
        traffic_seed: Seeds the capture's timing jitter only.
        thresholds: What the validity gate requires, or ``None`` for its documented defaults.
        with_capture: Whether to write the pcap.
        events: A catalogue of attacks, faults and maintenance to place in the run, or ``None``
            for a normal corpus. When given, the plant is run once normally to supply the replay
            recordings and the baseline the events are measured against, then again with the
            events applied; network-layer events are then applied to the capture.
        event_seed: Seeds the event schedule, kept apart from the plant's own seed so that adding
            events cannot move a physical parameter.
        skip_impossible_events: Whether to skip an event this plant cannot host rather than refuse
            the whole corpus. See `phos.synth.events.plan_events`; what was skipped is on the
            returned schedule.

    Returns:
        The plant, its manifest and the draw record.

    Raises:
        OutputError: If the run would hold no samples. A directory holding a header row and no
            data loads without error and scores as a corpus in which nothing went wrong, which
            is the most expensive kind of silence a measurement pipeline can contain.
        ValidityError: If the family produced no valid plant. That is a finding about the family,
            and it is raised rather than worked around.
    """
    bars = thresholds or Thresholds()
    drawn = draw_valid(family, master_seed, bars)
    spec = drawn.spec

    interval = sample_interval_seconds or spec.scan_period_seconds or bars.sample_interval_seconds
    try:
        run_spec = RunSpec(
            seed=drawn.child_seed,
            start=bars.run_spec(drawn.child_seed).start,
            duration=timedelta(hours=hours),
            sample_interval=timedelta(seconds=interval),
        )
    except ValidationError as error:
        # `RunSpec` already refuses a run that holds no samples, and says so clearly. Translated
        # rather than passed through, so the command line reports it as one more thing that could
        # not be generated instead of printing a pydantic stack trace at an operator.
        raise OutputError(
            f"{spec.plant_id}: {hours}h at {interval}s is not a run — {error.errors()[0]['msg']}"
        ) from error

    normal = run_from_spec(spec, run_spec)
    if not normal.steps:
        raise OutputError(f"{spec.plant_id}: the configured run holds no samples")
    if events is None:
        run = normal
        records: tuple[EventRecord, ...] = ()
        schedule: EventSchedule | None = None
    else:
        schedule = plan_events(
            spec,
            run_spec,
            numpy.random.default_rng(event_seed),
            events,
            history=normal.steps,
            skip_impossible=skip_impossible_events,
        )
        run = run_from_spec(spec, run_spec, injection=schedule.injection())
        records = assess_events(schedule.records, normal.steps, run.steps)

    directory = output / spec.plant_id
    directory.mkdir(parents=True, exist_ok=True)

    files = [
        _telemetry(run, directory),
        _labels(run, directory, records),
        _topology(run, directory),
        _document(spec.to_json(), directory, PLANT_FILE, "plant-spec-json", len(spec.signals)),
        _json(
            control_document(spec), directory, CONTROL_FILE, "control-json", len(spec.controllers)
        ),
        _json(
            register_document(spec),
            directory,
            REGISTERS_FILE,
            "registers-json",
            0 if spec.control_network is None else len(spec.control_network.blocks),
        ),
    ]
    capture = _capture(run, directory, traffic_seed, schedule) if with_capture else None
    if capture is not None:
        files.append(capture)

    manifest = GeneratedPlantManifest(
        plant_id=spec.plant_id,
        family_id=family.family_id,
        process=spec.process,
        master_seed=master_seed,
        child_seed=drawn.child_seed,
        rejections=drawn.rejection_count,
        rejection_reasons=tuple(verdict.summary() for verdict in drawn.rejected),
        validity_hours=bars.hours,
        parameters=dict(sorted(spec.parameters.items())),
        run=run_spec,
        samples=len(run.steps),
        events=run.events,
        description=run.description,
        files=tuple(files),
        traffic_seed=traffic_seed,
        git_commit=git_commit(),
    )
    (directory / MANIFEST_FILE).write_text(
        json.dumps(json.loads(manifest.model_dump_json()), indent=2) + "\n", encoding="utf-8"
    )
    logger.debug(
        "%s: %d samples, %d benign, %d scripted event(s), %d rejection(s) -> %s",
        spec.plant_id,
        len(run.steps),
        len(run.events),
        len(records),
        drawn.rejection_count,
        directory,
    )
    return GeneratedPlant(directory=directory, manifest=manifest, draw=drawn, schedule=schedule)


def _telemetry(run: PlantRun, directory: Path) -> GeneratedFile:
    """Write the prepared-corpus CSV and describe it for the manifest."""
    path = directory / TELEMETRY_FILE
    rows = write_csv(run, path)
    sha256, size = digest_of(path)
    return GeneratedFile(
        filename=TELEMETRY_FILE, kind="telemetry-csv", records=rows, sha256=sha256, size_bytes=size
    )


def _labels(run: PlantRun, directory: Path, events: Sequence[EventRecord] = ()) -> GeneratedFile:
    """Write the ground-truth labels and describe them for the manifest."""
    return _json(
        labels_document(run, events),
        directory,
        LABELS_FILE,
        "labels-json",
        len(run.events) + len(events),
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


def _capture(
    run: PlantRun,
    directory: Path,
    traffic_seed: int,
    schedule: EventSchedule | None = None,
) -> GeneratedFile | None:
    """Write the Modbus capture, or return ``None`` for a plant with no control network.

    Network-layer events, if any, are applied to the finished frames here — the one place the
    capture exists as frames before it becomes bytes on disk, and after the plant-layer events
    have already shaped the readings those frames carry.
    """
    frames = modbus_frames(run.description, run.steps, TrafficPolicy(seed=traffic_seed))
    if not frames:
        logger.debug("%s has no control network, so no capture", run.plant_id)
        return None
    if schedule is not None:
        frames = schedule.apply_to_capture(frames)
    path = directory / CAPTURE_FILE
    written = write_pcap(frames, path)
    sha256, size = digest_of(path)
    return GeneratedFile(
        filename=CAPTURE_FILE, kind="capture-pcap", records=written, sha256=sha256, size_bytes=size
    )


def _json(
    document: Mapping[str, object], directory: Path, filename: str, kind: str, records: int
) -> GeneratedFile:
    """Write a JSON document deterministically and describe it for the manifest."""
    return _document(
        json.dumps(document, indent=2, sort_keys=True) + "\n", directory, filename, kind, records
    )


def _document(text: str, directory: Path, filename: str, kind: str, records: int) -> GeneratedFile:
    """Write a text document and describe it for the manifest."""
    path = directory / filename
    path.write_text(text, encoding="utf-8")
    sha256, size = digest_of(path)
    return GeneratedFile(
        filename=filename, kind=kind, records=records, sha256=sha256, size_bytes=size
    )


def verify(directory: Path) -> Sequence[str]:
    """Check a written plant against its own manifest.

    Args:
        directory: A plant's directory.

    Returns:
        One line per problem, in a stable order. Empty when every file is present and hashes to
        what the manifest says.

    Raises:
        OutputError: If the directory holds no manifest, which is a different problem from a
            corpus whose files have changed and should not be reported as one.
    """
    path = directory / MANIFEST_FILE
    if not path.exists():
        raise OutputError(f"{directory} holds no {MANIFEST_FILE}")
    manifest = GeneratedPlantManifest.model_validate_json(path.read_text(encoding="utf-8"))
    problems: list[str] = []
    for file in manifest.files:
        member = directory / file.filename
        if not member.exists():
            problems.append(f"{file.filename}: listed in the manifest but absent")
            continue
        sha256, size = digest_of(member)
        if sha256 != file.sha256:
            problems.append(
                f"{file.filename}: hashes to {sha256[:12]}…, manifest says {file.sha256[:12]}…"
            )
        if size != file.size_bytes:
            problems.append(f"{file.filename}: is {size} bytes, manifest says {file.size_bytes}")
    return problems

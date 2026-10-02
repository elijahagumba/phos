"""The measurement seam for command-level detection — built, tested, and deliberately unrun.

Atlas's headline claim about the packet adapter is that reading commands lets it separate a
legitimate operator action from an attacker's identical one. **That claim is not measured here, and
this module is the reason it can be honest about that.** Demonstrating it needs a capture containing
such an attack, labelled, and no such corpus exists in this project. So PART P3 builds every piece
the measurement needs, proves each on hand-built fixtures, and stops exactly at the data:

- `CommandCaptureAdapter` — the `phos.eval.DatasetAdapter` for captures. A ``.pcap`` and a declared
  set of attack windows become the same `Dataset` a labelled CSV becomes, so the PART 2 harness
  scores command detection with the numbers it already reports for the sensor path, and they mean
  the same thing.
- `CommandBehaviourDetector` and `CommandGraphDetector` — the two `phos.eval.Detector`s, one per
  stream. **Two rather than one, and that is a measurement decision rather than a stylistic one:**
  a behaviour score is a magnitude in learned spreads and a graph score is a count of commands, so
  a single ``alert_threshold`` swept across both would be swept across two unit systems and mean
  nothing at either end.
- `require_labelled_intervals` and `discover_labelled_command_corpora` — the refusals. The first
  stops a metric being computed from a corpus with no ground truth. The second is what
  ``scripts/evaluate_command_detection.py`` consults, and on this repository it returns nothing,
  which is what makes the script print `LABELLED_COMMAND_CORPUS_REQUIREMENTS` instead of a number.
  Session 5 read the licence-confirmed campaign files (ADR 0040). Data4Cyber pcapng is readable;
  its labels are 1 Hz process phases, not command-action windows. That inspection does not fill
  this list.

**What a synthetic fixture can and cannot establish.** The tests inject a rogue write from a device
that has never commanded anything, and the seam finds it. That is a statement about plumbing: the
signal was placed by the author, at a moment the author chose, with a magnitude the author chose,
and a pipeline that failed to carry it would be broken rather than merely insensitive. It says
nothing about recall on real intrusions, nothing about the false-positive rate on a real plant's
ordinary day, and nothing about whether a calibrated confidence from this path means what it says.
`phos.atlas.UNMEASURED_COMMAND_DETECTION_CAVEAT` is the sentence that must travel with any output of
this module until that changes.
"""

import json
import logging
from pathlib import Path
from typing import Final, Self

from pydantic import BaseModel, ConfigDict, model_validator

from phos.atlas.command_evidence import (
    GRAPH_FINDING_FEATURES,
    promote_command_behaviour,
    promote_graph_findings,
)
from phos.atlas.packet import (
    CommandFeaturePolicy,
    DeviceCommandGraph,
    DissectorRegistry,
    GraphComparePolicy,
    ModbusDissector,
    compare_to_graph,
    dissect_capture,
    featurise_commands,
)
from phos.eval import Dataset, Detection, LabelledInterval
from phos.models import FittedModel
from phos.ontology import Domain, Observation
from phos.reasoning import FittedCalibrator

__all__ = [
    "INSPECTED_NOT_A_LABELLED_COMMAND_CORPUS",
    "LABELLED_COMMAND_CORPUS_REQUIREMENTS",
    "CommandBehaviourDetector",
    "CommandCaptureAdapter",
    "CommandCorpus",
    "CommandGraphDetector",
    "UnlabelledCommandCorpusError",
    "default_registry",
    "discover_labelled_command_corpora",
    "render_missing_corpus",
    "require_labelled_intervals",
]

logger = logging.getLogger(__name__)

CAPTURE_MANIFEST_FORMAT: Final = "pcap"
"""Value a ``manifest.json`` must declare under ``format`` to be read as a command corpus."""

LABELLED_COMMAND_CORPUS_REQUIREMENTS: Final = (
    "A packet capture (.pcap or .pcapng) of industrial control traffic on a protocol "
    "phos.atlas.packet dissects — today that is Modbus/TCP, and adding another protocol means a "
    "ProtocolDissector plus a registry entry, not a change here.",
    "A stretch of that capture believed ATTACK-FREE, long enough to learn from: enough whole "
    "windows for a command baseline and a device-command graph. It must be a separate stretch "
    "from the one scored, or the baseline and the measurement share data.",
    "A second stretch containing at least one CONTROL ACTION BY AN ATTACKER — a command that is "
    "byte-for-byte the kind of thing an operator sends. That is the discrimination the packet "
    "adapter exists to make, and a capture of reconnaissance or scanning cannot demonstrate it.",
    "GROUND TRUTH for that stretch, as attack windows with a start and an end. Without it every "
    "metric the harness computes is a number about nothing.",
    "A LICENCE permitting research use, and provenance recorded the way data/registry.json records "
    "it for every corpus PHOS already uses.",
    "Ideally, a labelled LEGITIMATE operator action in the same capture. Without one the corpus "
    "can show that an attacker's command was flagged, but not that an operator's was not — and "
    "the second half is the claim.",
)
"""Exactly what data would let the command-detection measurement be run.

Written as a shopping list rather than as prose because it is printed to whoever runs the script,
and "no suitable corpus found" on its own tells them nothing about how to fix it.
"""

INSPECTED_NOT_A_LABELLED_COMMAND_CORPUS: Final = (
    "data4cyber (Zenodo 19965384): pcapng is readable by UniversalReader; S1 contains "
    "operator-shaped Modbus writes from 192.168.1.20. Labels are 1 Hz process phases "
    "(CSV attack_active / attack_phase, copied into IPAL). Those clocks are not command "
    "windows. 5,880 normal seconds cannot be the FP/hour ruler. See ADR 0040.",
    "s7-data-modification (Zenodo 15373938): packets_dataset.parquet is a parsed table, "
    "not a pcap. Atlas does not dissect S7comm. See ADR 0012 and ADR 0040.",
    "3W Petrobras: class labels 1-9 are faults, not cyber-attacks. See ADR 0033 and ADR 0040.",
)
"""Campaign corpora session 5 opened and refused, so the shopping list is not 'we have not looked'.

None of these may be registered with ``format="pcap"`` and ``attack_intervals`` copied from
process-phase clocks. `discover_labelled_command_corpora` stays empty until a corpus meets
`LABELLED_COMMAND_CORPUS_REQUIREMENTS`.
"""


class UnlabelledCommandCorpusError(Exception):
    """Raised when a metric is asked for from a corpus that carries no ground truth."""


def default_registry() -> DissectorRegistry:
    """Return the dissectors Atlas claims to understand: Modbus/TCP, and nothing else.

    A function rather than a module constant so that a caller gets its own registry and cannot
    mutate a shared one — though `DissectorRegistry` has no mutation API, so this is belt as well
    as braces.
    """
    return DissectorRegistry([ModbusDissector()])


class CommandCaptureAdapter(BaseModel):
    """Turns packet captures, plus declared ground truth, into a `Dataset` the harness can score.

    The whole point of a `phos.eval.DatasetAdapter` is that the harness never learns which corpus
    it is looking at, so a false-positive rate computed on a capture means what it means on a CSV
    of sensor readings. This adapter is what buys that for the packet path.

    **Labels are declared, never inferred.** A capture carries no ground truth of its own, and
    guessing which traffic was the attack from the traffic itself is exactly the circularity every
    measurement here exists to avoid. ``attack_intervals`` is therefore a field the corpus's
    manifest fills in, and an empty one produces an honestly unlabelled dataset rather than a
    conveniently clean one — see `require_labelled_intervals`.

    Attributes:
        captures: The capture files to read, in order. More than one is allowed because a corpus
            often ships a baseline file and a scored file; each observation's provenance names the
            capture it came from, so pooling them keeps frame ranges meaningful.
        attack_intervals: Ground truth, as declared by the corpus.
        graph: A device-command graph learned from a **different** capture. When given, the
            structural findings `compare_to_graph` measures are carried in the dataset alongside
            the behaviour features. When omitted, no structural finding is produced at all: a
            comparison needs something to compare against, and there is no default baseline.
        policy: How command behaviour is windowed.
        graph_policy: How the live stream is sliced against the graph.
        registry: The dissectors to read the captures with.
        name: Dataset name recorded on every report this corpus produces.
        source_note: Provenance. The capture file names are appended, because a number that cannot
            name its input is not reproducible (Constitution §3.7).
        domain: Which engine's world the corpus belongs to.

    Invariants:
        At least one capture.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    captures: tuple[Path, ...]
    attack_intervals: tuple[LabelledInterval, ...] = ()
    graph: DeviceCommandGraph | None = None
    policy: CommandFeaturePolicy = CommandFeaturePolicy()
    graph_policy: GraphComparePolicy = GraphComparePolicy()
    registry: DissectorRegistry | None = None
    name: str = "command-capture"
    source_note: str = ""
    domain: Domain = Domain.ATLAS

    @model_validator(mode="after")
    def _check_captures(self) -> Self:
        if not self.captures:
            raise ValueError("a command corpus needs at least one capture to read")
        return self

    def load(self) -> Dataset:
        """Read every capture and return the observations and labels as one `Dataset`.

        Returns:
            The corpus. Observations are sorted by timestamp, which `Dataset` requires and which
            merging two independently-ordered streams would otherwise break.

        Raises:
            CaptureError: If a file is not a readable capture. Surfaced rather than skipped: a
                corpus that silently dropped a file would report metrics over less data than it
                claimed.
        """
        registry = self.registry or default_registry()
        observations: list[Observation] = []
        for capture in self.captures:
            results = list(dissect_capture(capture, registry))
            observations.extend(featurise_commands(results, self.policy))
            if self.graph is not None:
                observations.extend(compare_to_graph(self.graph, results, self.graph_policy))

        observations.sort(key=lambda o: (o.timestamp, o.entity_ids, o.feature))
        note = self.source_note or "packet capture"
        logger.info(
            "%s: %d observation(s) from %d capture(s), %d labelled attack window(s)",
            self.name,
            len(observations),
            len(self.captures),
            len(self.attack_intervals),
        )
        return Dataset(
            name=self.name,
            domain=self.domain,
            observations=observations,
            attack_intervals=list(self.attack_intervals),
            source_note=f"{note} — {', '.join(capture.name for capture in self.captures)}",
        )


class CommandBehaviourDetector(BaseModel):
    """Scores a corpus's command-behaviour features, reporting the calibrated weight as confidence.

    A thin adapter onto `phos.atlas.command_evidence.promote_command_behaviour`, so the alerts the
    harness scores are the *same* departures the reasoning engine would receive — not a second,
    parallel scoring path that might disagree with it.

    Attributes:
        fitted: A model fitted on command behaviour believed normal, from a different capture.
        calibrator: A calibrator fitted on a held-out labelled slice.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    fitted: FittedModel
    calibrator: FittedCalibrator

    @property
    def name(self) -> str:
        """Identifies the detector in reports, naming both halves of what produced the numbers."""
        return f"command-behaviour:{self.fitted.name}+{self.calibrator.name}"

    def run(self, dataset: Dataset) -> list[Detection]:
        """Return one detection per genuine command-behaviour departure, earliest first.

        Args:
            dataset: A `CommandCaptureAdapter` corpus. Structural findings in it are ignored here;
                `CommandGraphDetector` reads those.

        Returns:
            Detections whose ``score`` is the raw magnitude — so the harness's threshold sweep is
            in the same units PART 3 and 5A report — and whose ``confidence`` is the calibrated
            probability.
        """
        behaviour = [
            observation
            for observation in dataset.observations
            if observation.feature not in GRAPH_FINDING_FEATURES
        ]
        if not behaviour:
            return []
        return [
            Detection(
                timestamp=departure.observation.timestamp,
                score=departure.deviation.magnitude,
                confidence=departure.evidence.weight,
                entity_ids=list(departure.observation.entity_ids),
                feature=departure.observation.feature,
            )
            for departure in promote_command_behaviour(behaviour, self.fitted, self.calibrator)
        ]


class CommandGraphDetector(BaseModel):
    """Scores a corpus's command-graph findings — a change in who commands whom.

    Separate from `CommandBehaviourDetector` because its ``score`` is a count of commands rather
    than a magnitude in learned spreads, and a threshold swept across both would be swept across
    two unit systems.

    Attributes:
        calibrator: A calibrator fitted on labelled graph-finding scores. See
            `phos.atlas.POOLED_GRAPH_CALIBRATION_CAVEAT` for the limit one calibrator across three
            differently-united features carries.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    calibrator: FittedCalibrator

    @property
    def name(self) -> str:
        """Identifies the detector in reports."""
        return f"command-graph:{self.calibrator.name}"

    def run(self, dataset: Dataset) -> list[Detection]:
        """Return one detection per structural change, earliest first.

        Args:
            dataset: A `CommandCaptureAdapter` corpus loaded with a learned graph. A corpus loaded
                without one holds no findings, and the honest answer is no detections rather than
                a claim that nothing changed.

        Returns:
            Detections whose ``score`` is the measured size of the change and whose ``confidence``
            is the calibrated probability.
        """
        findings = [
            observation
            for observation in dataset.observations
            if observation.feature in GRAPH_FINDING_FEATURES
        ]
        if not findings:
            return []
        return [
            Detection(
                timestamp=change.finding.timestamp,
                score=change.finding.value,
                confidence=change.evidence.weight,
                entity_ids=list(change.finding.entity_ids),
                feature=change.finding.feature,
            )
            for change in promote_graph_findings(findings, self.calibrator)
        ]


def require_labelled_intervals(dataset: Dataset) -> None:
    """Raise unless ``dataset`` carries the ground truth a metric would be computed against.

    The guard that stops a plausible-looking report being produced from a capture nobody labelled.
    Every number `phos.eval.evaluate` returns — recall, false-positive rate, latency, calibration
    error — is defined against attack windows, and with none the harness answers the question
    "how often was the detector right about nothing".

    Args:
        dataset: The corpus about to be scored.

    Raises:
        UnlabelledCommandCorpusError: If the corpus declares no attack intervals.
    """
    if not dataset.attack_intervals:
        raise UnlabelledCommandCorpusError(
            f"{dataset.name!r} carries no ground truth, so no metric may be computed from it. "
            "A capture is not a corpus until someone has said which of it was the attack; see "
            "phos.atlas.command_eval.LABELLED_COMMAND_CORPUS_REQUIREMENTS"
        )


class CommandCorpus(BaseModel):
    """A registered, labelled command corpus found on disk.

    Attributes:
        name: The corpus directory's name.
        directory: Where it lives.
        manifest: The parsed ``manifest.json``.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    directory: Path
    manifest: dict[str, object]

    def adapter(self) -> CommandCaptureAdapter:
        """Return the adapter this manifest describes, with its paths resolved.

        Raises:
            ValueError: If the manifest's captures or attack intervals cannot be read as such.
        """
        captures = tuple(
            self.directory / str(entry) for entry in _entries(self.manifest, "captures")
        )
        intervals = tuple(
            LabelledInterval.model_validate(entry)
            for entry in _entries(self.manifest, "attack_intervals")
        )
        return CommandCaptureAdapter(
            captures=captures,
            attack_intervals=intervals,
            name=self.name,
            source_note=str(self.manifest.get("source_note", "")),
        )


def _entries(manifest: dict[str, object], key: str) -> list[object]:
    """Return a manifest list field, refusing a value that is not a list."""
    value = manifest.get(key, [])
    if not isinstance(value, list):
        raise ValueError(f"manifest field {key!r} must be a list, got {type(value).__name__}")
    return value


def discover_labelled_command_corpora(data_dir: Path) -> list[CommandCorpus]:
    """Return every corpus under ``data_dir`` that is a capture corpus *and* carries labels.

    Both halves are required, and the second is the one that matters: a ``.pcap`` on disk is not a
    corpus until someone has declared which of it was the attack. A capture corpus without labels
    is skipped with a warning rather than returned, so a caller cannot accidentally score it.

    Args:
        data_dir: The ``data/`` directory, whose subdirectories each hold a ``manifest.json``.

    Returns:
        The usable corpora, ordered by name. **Empty on this repository**, which is the fact PART
        P3 stops at — see `render_missing_corpus`.
    """
    found: list[CommandCorpus] = []
    if not data_dir.is_dir():
        return found

    for manifest_path in sorted(data_dir.glob("*/manifest.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("format") != CAPTURE_MANIFEST_FORMAT:
            continue
        name = manifest_path.parent.name
        if not manifest.get("attack_intervals"):
            logger.warning(
                "%s is a capture corpus with no declared attack windows; skipping, because a "
                "metric computed from it would be a number about nothing",
                name,
            )
            continue
        missing = [
            entry
            for entry in _entries(manifest, "captures")
            if not (manifest_path.parent / str(entry)).is_file()
        ]
        if missing:
            logger.warning("%s: manifest lists %s, which is not on disk", name, missing)
            continue
        found.append(CommandCorpus(name=name, directory=manifest_path.parent, manifest=manifest))
    return found


def render_missing_corpus() -> str:
    """Return the message printed instead of a metric when no labelled capture corpus exists.

    Returns:
        A multi-line block naming every entry in `LABELLED_COMMAND_CORPUS_REQUIREMENTS`, then
        every campaign corpus session 5 inspected and refused, so that whoever runs the
        measurement learns what to go and find rather than only that it did not run.
    """
    return "\n".join(
        [
            "No labelled command corpus is registered, so NO command-level detection metric can "
            "be reported.",
            "",
            "This is not a failure of the pipeline. Every piece of the measurement exists and is "
            "tested; what is missing is data. To run it, register a corpus under data/ with a "
            'manifest.json declaring format="pcap", its captures, and its attack_intervals — '
            "and that corpus must supply:",
            "",
            *(
                f"  {index}. {text}"
                for index, text in enumerate(LABELLED_COMMAND_CORPUS_REQUIREMENTS, 1)
            ),
            "",
            "Inspected and refused (ADR 0040) — these are not a labelled command corpus:",
            "",
            *(f"  - {text}" for text in INSPECTED_NOT_A_LABELLED_COMMAND_CORPUS),
            "",
            "Until then Atlas can read commands, describe them, reason about them and be scored "
            "on them — and how well it does so is unknown.",
        ]
    )

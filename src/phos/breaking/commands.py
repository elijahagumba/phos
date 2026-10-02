"""Does reading the control network move the explanation toward the right cause?

5C recorded the asymmetry this measures. Process telemetry carries no control context, so
`unauthorised_control_activity` and `process_disturbance` weigh evidence *identically* and are told
apart only by their priors — and the attack prior is deliberately the lowest, because attacks are
rarer than equipment faults. On sensors alone, an attacker therefore loses to a process upset every
time, by construction rather than by mistake.

P3 built the path that should break the tie: a command from a device with no history of issuing it
is something a process upset cannot produce. **A real process upset moves readings; it does not make
a workstation begin commanding a PLC.** But P3 could not measure it, because measuring it needs a
capture containing a labelled control-network attack and PHOS had none.

D2 shipped exactly that. So this module answers P3's open question the only honest way available:
run the *same* corpus twice, once sensor-only and once with the capture beside it, and compare where
`unauthorised_control_activity` sits in the ordering both times. The comparison is within-corpus and
within-fold, so the only thing that differs is whether Atlas could read the commands.

**What a movement here does and does not show.** It shows that command evidence changes the
ordering in the direction the design predicted, on attacks we wrote, against a plant we simulated.
It does not show that Atlas would separate a real intruder from a real maintenance engineer on a
*known* command relationship — P3 was explicit that a commissioning engineer and an intruder can
leave behind the same new function on a learned link. A marked unknown master is the exception
that ADR 0027 records: a device that has never commanded this target is not how plant engineers
work. The batch reactor is the control case that keeps the rest honest: it declares no control
network, so no command attack can exist on it and Atlas is deaf to commands there by construction.

**Known-station writes and unknown-master writes are scored apart.** A write from the SCADA
poller is an unexpected function on a learned link (ADR 0014). A write from a declared station
that never appeared as an issuer on the baseline graph is the unknown-master shape ADR 0027
split the templates for. Pooling their lead rates would credit that split for a battery that
never exercised it (ADR 0034).
"""

import logging
from collections.abc import Sequence
from enum import Enum
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from phos.atlas import (
    compare_to_graph,
    default_registry,
    dissect_capture,
    featurise_commands,
    learn_device_command_graph,
)
from phos.atlas.command_evidence import (
    CommandEvidence,
    promote_command_behaviour,
    promote_graph_findings,
)
from phos.atlas.packet import DeviceCommandGraph, device_entity_id
from phos.eval import Dataset
from phos.models import FittedModel, GaussianBaseline
from phos.ontology import EvidenceStore, Hypothesis, Observation
from phos.reasoning import FittedCalibrator
from phos.reasoning.belief import tied_lead_ids
from phos.synth.attacks import AttackGroundTruth
from phos.synth.plant import PlantDescription

__all__ = [
    "ATTACK_TEMPLATE_ID",
    "CAPTURE_FILE",
    "CommandIssuerKind",
    "CommandPath",
    "CommandReasoningResult",
    "ExplanationRanking",
    "classify_command_issuer",
    "command_attacks",
    "rank_explanations",
    "read_command_path",
]

logger = logging.getLogger(__name__)

ATTACK_TEMPLATE_ID: Final = "unauthorised_control_activity"
"""The explanation a command attack ought to move toward. Named rather than inferred: the point of
the measurement is whether Atlas reaches *this* conclusion, so the target cannot be whichever
hypothesis happened to win."""

CAPTURE_FILE: Final = "capture.pcap"


class CommandIssuerKind(str, Enum):
    """Whether a command attack's issuer was already on the learned baseline graph.

    Attributes:
        KNOWN_STATION: The issuer commanded someone during normal operation. A new function on
            that link still supports both unauthorised control and maintenance (ADR 0014).
        UNKNOWN_MASTER: The issuer never commanded anyone in the baseline capture. That is the
            marked unknown-master finding ADR 0027 uses to contradict maintenance.
    """

    KNOWN_STATION = "known_station"
    UNKNOWN_MASTER = "unknown_master"


def classify_command_issuer(
    issuer: str, description: PlantDescription, graph: DeviceCommandGraph
) -> CommandIssuerKind:
    """Return whether ``issuer`` already commanded anyone in the learned baseline graph.

    Classification is from the observed graph, not from the attack type name. `ROGUE_COMMAND`
    from the SCADA poller is a known station; `ROGUE_COMMAND` from a silent engineering
    workstation is an unknown master.

    Args:
        issuer: The plant ``node_id`` that issued the attack.
        description: The plant declaration, for the issuer's address.
        graph: Learned from the *normal* capture the breaking harness fits on.

    Returns:
        `KNOWN_STATION` when any baseline edge was issued by this device, otherwise
        `UNKNOWN_MASTER`.

    Raises:
        ValueError: If the plant declares no control network.
        KeyError: If ``issuer`` is not a declared node.
    """
    network = description.control_network
    if network is None:
        raise ValueError(
            f"cannot classify issuer {issuer!r}: plant {description.plant_id!r} declares no "
            "control network"
        )
    entity = device_entity_id(network.node(issuer).ip)
    if any(edge.issuer == entity for edge in graph.edges):
        return CommandIssuerKind.KNOWN_STATION
    return CommandIssuerKind.UNKNOWN_MASTER


class ExplanationRanking(BaseModel):
    """Where each competing explanation sat, for one attack, in one run.

    Attributes:
        attack_id: The attack whose window this ranks.
        templates: Template ids ordered by confidence, strongest first. A lead tie keeps this
            order for reproducibility; `tied_leaders` is what says there is no unique winner.
        rank: One-based position of `ATTACK_TEMPLATE_ID`, or ``None`` when it was never raised.
        confidence: Its confidence, or ``0.0`` when it was never raised. Uncalibrated, and
            reported only as an ordering, never surfaced as a probability (Constitution §3.3).
        n_hypotheses: How many explanations were in play at all.
        tied_leaders: Template ids sharing the lead, in `template_id` order. Empty when the
            lead is unique.
    """

    model_config = ConfigDict(frozen=True)

    attack_id: str = Field(min_length=1)
    templates: tuple[str, ...] = ()
    rank: int | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    n_hypotheses: int = Field(default=0, ge=0)
    tied_leaders: tuple[str, ...] = ()

    @property
    def unique_leader(self) -> str | None:
        """The single strongest template id, or ``None`` when the lead is a tie or the set is empty.

        A non-empty `tied_leaders` means the first id in `templates` is a reproducible listing,
        not a unique winner. Constitution §3.7 requires that listing; it does not license a fake
        leader.
        """
        if self.tied_leaders:
            return None
        if self.templates:
            return self.templates[0]
        if self.rank == 1:
            return ATTACK_TEMPLATE_ID
        return None

    @property
    def leads(self) -> bool:
        """Whether the attack explanation was the unique strongest of the competing ones."""
        return self.unique_leader == ATTACK_TEMPLATE_ID


class CommandReasoningResult(BaseModel):
    """What reading the control network did to one command attack's explanation ordering.

    Attributes:
        attack_id: The command attack measured.
        subtlety: Where on the dial it ran.
        sensor_only: The ordering Atlas produced from process telemetry alone.
        with_commands: The ordering it produced with the capture beside it.
        n_command_evidence: How many pieces of evidence the command path contributed in the
            attack's window. Zero means the comparison had nothing to compare — the commands
            produced no evidence at all, and any movement would be noise.
        issuer: The plant ``node_id`` that issued the command, or empty.
        issuer_kind: Whether that issuer was already on the learned baseline graph.

    Invariants:
        Both rankings describe the same attack.
    """

    model_config = ConfigDict(frozen=True)

    attack_id: str = Field(min_length=1)
    subtlety: float = Field(ge=0.0, le=1.0)
    sensor_only: ExplanationRanking
    with_commands: ExplanationRanking
    n_command_evidence: int = Field(default=0, ge=0)
    issuer: str = ""
    issuer_kind: CommandIssuerKind = CommandIssuerKind.KNOWN_STATION

    @property
    def moved_toward_attack(self) -> bool:
        """Whether the attack explanation rose in the ordering once commands were readable.

        Rising means going from absent to present, or from a worse rank to a better one. A gain in
        confidence at an unchanged rank does **not** count: the confidence is uncalibrated, so the
        ordering is the only part of it this project is willing to read.
        """
        before, after = self.sensor_only.rank, self.with_commands.rank
        if after is None:
            return False
        return before is None or after < before

    @property
    def newly_leads(self) -> bool:
        """Whether commands made the attack explanation the strongest, when it was not before."""
        return self.with_commands.leads and not self.sensor_only.leads


def rank_explanations(
    truth: AttackGroundTruth, store: EvidenceStore, dataset: Dataset
) -> ExplanationRanking:
    """Rank the explanations Atlas raised over one attack's window.

    A hypothesis belongs to the window when any evidence supporting it is timestamped inside it.
    Supporting rather than contradictory: a hypothesis the window's evidence argues *against* is
    not an explanation of that window.

    Args:
        truth: The attack, supplying the window.
        store: The store the run wrote into.
        dataset: The corpus, for its name in the log line only.

    Returns:
        The ranking, strongest first. The listing is `(-confidence, template_id)` so two runs
        agree (Constitution §3.7). When two or more explanations share the lead, `tied_leaders`
        records the set and `leads` stays false — a tie is not a unique winner.
    """
    window = truth.interval()
    inside = {evidence.id for evidence in store.evidence() if window.contains(evidence.timestamp)}
    relevant: list[Hypothesis] = [
        hypothesis
        for hypothesis in store.hypotheses()
        if inside.intersection(hypothesis.supporting)
    ]
    relevant.sort(key=lambda item: (-item.confidence, item.template_id))
    templates = tuple(hypothesis.template_id for hypothesis in relevant)
    tied = tied_lead_ids(relevant)

    match = next(
        (item for item in relevant if item.template_id == ATTACK_TEMPLATE_ID),
        None,
    )
    logger.debug(
        "%s: %s had %d competing explanation(s) over %s",
        dataset.name,
        truth.attack_id,
        len(relevant),
        window.start,
    )
    if tied:
        logger.debug(
            "%s: %s lead is tied among %s; not naming a unique leader",
            dataset.name,
            truth.attack_id,
            ",".join(tied),
        )
    return ExplanationRanking(
        attack_id=truth.attack_id,
        templates=templates,
        rank=(templates.index(ATTACK_TEMPLATE_ID) + 1) if match is not None else None,
        confidence=match.confidence if match is not None else 0.0,
        n_hypotheses=len(relevant),
        tied_leaders=tied,
    )


class CommandPath(BaseModel):
    """The command pipeline's expensive half, done once so each fold only re-weighs it.

    Dissecting a capture, learning the device-command graph and fitting a behaviour model are all
    independent of the calibrator, and the cross-fit changes only the calibrator. Holding them here
    means a two-fold run reads each capture once rather than four times.

    Attributes:
        live_features: Command-behaviour observations from the attacked capture.
        graph_findings: Structural changes measured against the baseline capture's graph.
        graph: The baseline command graph itself, so each attack's issuer can be classified as a
            known station or an unknown master without re-reading the capture.
        fitted: The behaviour model, fitted on the baseline capture. A `GaussianBaseline`, which
            keys per ``(device, feature)`` — the shape `featurise_commands` already produces, so a
            device's polling rhythm is judged against its own history and not another device's.

    Invariants:
        None beyond its members'. Carries no labels and no verdicts.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    live_features: tuple[Observation, ...] = ()
    graph_findings: tuple[Observation, ...] = ()
    graph: DeviceCommandGraph = Field(default_factory=DeviceCommandGraph)
    fitted: FittedModel

    def promote(self, calibrator: FittedCalibrator) -> CommandEvidence:
        """Weigh both streams with ``calibrator`` and return them as evidence.

        Args:
            calibrator: Fitted on a slice the evidence being promoted does not overlap.

        Returns:
            The bundle. Empty when neither stream produced anything, which is a result.
        """
        departures = promote_command_behaviour(self.live_features, self.fitted, calibrator)
        changes = promote_graph_findings(self.graph_findings, calibrator)
        logger.info(
            "command path promoted %d behaviour departure(s) and %d graph change(s)",
            len(departures),
            len(changes),
        )
        return CommandEvidence(departures=tuple(departures), changes=tuple(changes))


def read_command_path(baseline_capture: Path, live_capture: Path) -> CommandPath:
    """Read both captures and prepare everything the command path needs bar the calibrator.

    Args:
        baseline_capture: A capture of the same plant behaving normally. Teaches Atlas who normally
            commands whom and how each device normally behaves.
        live_capture: The capture taken beside the attacked corpus.

    Returns:
        The prepared path.

    Raises:
        FileNotFoundError: If either capture is missing.
    """
    registry = default_registry()
    graph = learn_device_command_graph(dissect_capture(baseline_capture, registry))
    baseline_features = featurise_commands(dissect_capture(baseline_capture, registry))
    live_features = featurise_commands(dissect_capture(live_capture, registry))
    findings = compare_to_graph(graph, dissect_capture(live_capture, registry))

    logger.info(
        "command path read %s against %s: %d live feature(s), %d graph finding(s)",
        live_capture.name,
        baseline_capture.name,
        len(live_features),
        len(findings),
    )
    return CommandPath(
        live_features=tuple(live_features),
        graph_findings=tuple(findings),
        graph=graph,
        fitted=GaussianBaseline().fit(baseline_features),
    )


def command_attacks(truths: Sequence[AttackGroundTruth]) -> tuple[AttackGroundTruth, ...]:
    """Return only the attacks that act on the control network.

    The others are not evidence about the command path either way: an actuator manipulation puts
    nothing on the wire, so a ranking that did not move for one says nothing about whether reading
    commands helps.
    """
    return tuple(truth for truth in truths if truth.type.is_command_attack)

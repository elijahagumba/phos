"""Where a device's commanding becomes something the reasoning engine may weigh.

P2 could describe command behaviour and measure how the command graph had changed, and nothing
consumed either. This module is the join. It has one design rule, and everything below follows from
it: **command evidence must be the same object a sensor departure produces.** Same `Evidence` type,
same `EvidenceKind`, same calibrated weight, same route in — so the reasoning engine, the store, the
narratives and eventually the API cannot tell the two apart and never acquire a second case to
handle (Constitution §3.1).

That rule is why nothing here builds an `Evidence` itself. Both promoters call
`phos.reasoning.boundary`, which is the only sanctioned door and which refuses a non-event on the
way through:

- **Command behaviour** (`promote_command_behaviour`) is scored by an ordinary `FittedModel`, and
  only the readings that genuinely left their `ExpectedRange` are promoted, by
  `evidence_from_deviation`. A command feature is a scalar for one device at one instant, which is
  exactly what PART 3's baselines expect, so no adapter and no special case is involved.
- **Graph changes** (`promote_graph_findings`) go through `evidence_from_relationship_change`,
  because a relationship that has never existed has no learned band to be outside of. That door
  applies the same two refusals and produces `EvidenceKind.RELATIONSHIP_CHANGE`.

**Which of the two actually discriminates is worth saying plainly.** The graph does. A structural
change supports `unauthorised_control_activity` and contradicts `process_disturbance`, which is the
separation process telemetry could never make — a real upset moves readings and does not make a
workstation start commanding a PLC. A *marked unknown master* further contradicts
`engineering_maintenance`, because a device that has never commanded this target is not how plant
engineers work. An untyped relationship change, or a function-code change on a known link, still
supports both the attack and maintenance explanations. A command-behaviour *deviation* bears on no
OT explanation at all, because `Evidence` names a kind and some entities and never a feature, so no
pattern can ask which command behaviour departed. It is still promoted, stored and narrated: an
operator looking at a story must see the device's commanding alongside the structural change, and a
later PART with labelled data is what turns it into a template.

**What travels with every number this module produces:** `COMMAND_EVIDENCE_CAVEATS`. The first of
them is P3's central honesty guard and the reason this module ships without a headline result — the
pipeline is proved in mechanism on synthetic fixtures, and Atlas's actual ability to separate an
operator from an attacker is unmeasured until a labelled attack capture exists. See
`phos.atlas.command_eval`, which is the seam that will run it.
"""

import logging
from collections.abc import Sequence
from typing import Final

from pydantic import BaseModel, ConfigDict

from phos.atlas.packet import (
    COMMAND_BASELINE_CAVEATS,
    SILENT_COMMAND_RELATIONSHIP,
    UNEXPECTED_COMMAND_FUNCTION,
    UNKNOWN_COMMAND_RELATIONSHIP,
)
from phos.models import FittedModel
from phos.ontology import Deviation, Evidence, FacetKind, Observation
from phos.reasoning import (
    FittedCalibrator,
    calibrated_probabilities,
    evidence_from_deviation,
    evidence_from_relationship_change,
    is_out_of_band,
)

__all__ = [
    "COMMAND_BEHAVIOUR_MARKER",
    "COMMAND_EVIDENCE_CAVEATS",
    "GRAPH_FINDING_FEATURES",
    "GRAPH_FINDING_MARKER",
    "POOLED_GRAPH_CALIBRATION_CAVEAT",
    "UNGROUPED_COMMAND_EVIDENCE_CAVEAT",
    "UNMEASURED_COMMAND_DETECTION_CAVEAT",
    "CommandDeparture",
    "CommandEvidence",
    "GraphChange",
    "command_behaviour_feature_of",
    "command_behaviour_marker",
    "graph_finding_feature_of",
    "graph_finding_marker",
    "promote_command_behaviour",
    "promote_graph_findings",
]

logger = logging.getLogger(__name__)

GRAPH_FINDING_FEATURES: Final = (
    UNKNOWN_COMMAND_RELATIONSHIP,
    SILENT_COMMAND_RELATIONSHIP,
    UNEXPECTED_COMMAND_FUNCTION,
)
"""The three structural changes `phos.atlas.packet.graph` measures, and the only ones read here.

Enumerated rather than inferred from the shape of an observation, for the same reason
`phos.atlas.packet.commands.WRITE_FUNCTIONS` is: a finding this module summarises without
recognising would describe a change nobody measured.
"""

GRAPH_FINDING_MARKER: Final = "graph-finding:"
"""Declared prefix that names which of the three graph findings an `Evidence` summary carries.

`Evidence` records a kind and some entities, never a feature (Constitution §3.1), so a template
cannot ask "was this an unknown master?" unless the fact itself says so. The marker is that
statement, written into the summary at promotion — the same declared-marker idiom grouping uses
for a subsystem event. Parsing it is `graph_finding_feature_of`; forging it on unrelated evidence
would make a template match a fact nobody measured.
"""


def graph_finding_marker(feature: str) -> str:
    """Return the summary prefix that declares ``feature`` as the graph finding behind this fact."""
    return f"{GRAPH_FINDING_MARKER}{feature}:"


def graph_finding_feature_of(evidence: Evidence) -> str | None:
    """Return which graph finding this evidence declares, or ``None`` if it declares none.

    **The typed facet wins, and the summary is read only when there is no facet at all** (ADR
    0070). A fact promoted by `promote_graph_findings` carries `FacetKind.GRAPH_FINDING` and its
    feature, so no matcher depends on the wording of a sentence written for an operator. Evidence
    with no facet — a hand-built fixture, or a promoter that predates the field — still resolves
    through the marker, which is why the stamp is still written and this fallback still exists.

    ``None`` for a relationship change that declares neither (a test fixture, or a future promoter
    that has stamped nothing) and for any other facet or kind. A matcher that treated unmarked
    structure as an unknown master would silently reclassify every untyped change as an attack.
    """
    if evidence.facet_kind is not None:
        if evidence.facet_kind is not FacetKind.GRAPH_FINDING:
            return None
        return evidence.facet if evidence.facet in GRAPH_FINDING_FEATURES else None
    return _graph_finding_from_summary(evidence)


def _graph_finding_from_summary(evidence: Evidence) -> str | None:
    """Recover a graph finding from the declared summary marker. The pre-facet path."""
    if not evidence.summary.startswith(GRAPH_FINDING_MARKER):
        return None
    rest = evidence.summary[len(GRAPH_FINDING_MARKER) :]
    feature, separator, _body = rest.partition(":")
    if not separator or feature not in GRAPH_FINDING_FEATURES:
        return None
    return feature


COMMAND_BEHAVIOUR_MARKER: Final = "command-behaviour:"
"""Declared prefix that names which command-behaviour feature a deviation evidence summary carries.

Session D1: same idiom as `GRAPH_FINDING_MARKER`. Templates still have no `Evidence.feature`
field (ADR 0014). The stamp is so a later matcher *could* read it, or so a narrative can show
the finding as typed structure. Do not put known-link unexpected function on maintenance-contradict.
"""


def command_behaviour_marker(feature: str) -> str:
    """Return the summary prefix that declares ``feature`` as the behaviour fact behind this."""
    return f"{COMMAND_BEHAVIOUR_MARKER}{feature}:"


def command_behaviour_feature_of(evidence: Evidence) -> str | None:
    """Return which command-behaviour feature this evidence declares, or ``None``.

    Typed facet first, summary marker only when no facet is set — see
    `graph_finding_feature_of` for why both paths exist (ADR 0070).
    """
    if evidence.facet_kind is not None:
        if evidence.facet_kind is not FacetKind.COMMAND_BEHAVIOUR:
            return None
        return evidence.facet
    return _command_behaviour_from_summary(evidence)


def _command_behaviour_from_summary(evidence: Evidence) -> str | None:
    """Recover a command-behaviour feature from the declared marker. The pre-facet path."""
    if not evidence.summary.startswith(COMMAND_BEHAVIOUR_MARKER):
        return None
    rest = evidence.summary[len(COMMAND_BEHAVIOUR_MARKER) :]
    feature, separator, _body = rest.partition(":")
    if not separator or not feature:
        return None
    return feature


UNMEASURED_COMMAND_DETECTION_CAVEAT: Final = (
    "Unmeasured command-level detection: this pipeline has been proved in MECHANISM only. Command "
    "behaviour becomes calibrated evidence, graph changes become calibrated evidence, and the OT "
    "templates reorder competing explanations when they arrive — all demonstrated on synthetic "
    "fixtures whose rogue command was chosen by the author. Atlas's actual ability to separate a "
    "legitimate operator action from an attacker's identical command HAS NOT BEEN MEASURED, "
    "because that requires a capture containing such an attack, labelled, and no such corpus "
    "exists in this project. No recall, false-positive rate, latency or calibration figure for "
    "command-level detection may be quoted until phos.atlas.command_eval is run against real "
    "labelled attack data."
)

POOLED_GRAPH_CALIBRATION_CAVEAT: Final = (
    "Pooled graph calibration: one calibrator maps all three graph findings, whose values are in "
    "different units — a count of commands on an unknown link, a count of commands using an "
    "unfamiliar function, and an expected command VOLUME for a link that fell silent. A single "
    "monotone score-to-probability map therefore says the same thing about a score of 5 whichever "
    "feature produced it. Whether that costs anything is an empirical question no data available "
    "here can answer; a per-feature calibrator is the fix, and fitting one needs the same labelled "
    "corpus this whole path is waiting on."
)

UNGROUPED_COMMAND_EVIDENCE_CAVEAT: Final = (
    "Command-evidence reachability: graph findings attach to a window's story by entity "
    "reachability from in-window command activity (unknown_command_relationship or "
    "unexpected_command_function), or as the unknown-master finding itself. Those identities "
    "are declared on the finding — the same entity ids the command graph already recorded — "
    "not inferred from co-movement, which phos.atlas.topology exists to refuse. Command "
    "evidence is still NOT collapsed the way 5B's subsystem map collapses sensor evidence: a "
    "device whose commanding changes in several ways at once still contributes one piece of "
    "evidence per feature for what may be one act. The counting inflation that leaves is "
    "real. What is gone is the claim that there was nothing declared to attach by."
)

COMMAND_EVIDENCE_CAVEATS: Final = (
    UNMEASURED_COMMAND_DETECTION_CAVEAT,
    POOLED_GRAPH_CALIBRATION_CAVEAT,
    UNGROUPED_COMMAND_EVIDENCE_CAVEAT,
    *COMMAND_BASELINE_CAVEATS,
)
"""Everything that must travel with a number computed from command evidence.

The last two are P2's, carried forward unchanged: a command baseline describes the capture it was
learned from rather than the plant, and it does not fail loudly when that capture is short or covers
one operating mode. They are as true of an `Evidence` weight as they were of the feature underneath
it, so they travel with it.
"""


class CommandDeparture(BaseModel):
    """One command-behaviour reading that left its learned band, with its whole traceability chain.

    The three objects are kept together because storing evidence without the deviation and the
    observation behind it would leave a `source_id` pointing at nothing an operator could open
    (Constitution §3.2). `phos.atlas.AtlasEngine` writes all three.

    Attributes:
        observation: The measured feature — a `featurise_commands` output, whose ``context`` names
            the capture and frame range it was computed from.
        deviation: The scored departure, carrying the `ExpectedRange` it was judged against.
        evidence: The promoted fact, of kind `EvidenceKind.DEVIATION`.
    """

    model_config = ConfigDict(frozen=True)

    observation: Observation
    deviation: Deviation
    evidence: Evidence


class GraphChange(BaseModel):
    """One measured change in the command graph, promoted into evidence.

    Attributes:
        finding: The measurement `compare_to_graph` emitted. Its value quantifies the change and
            its ``context`` names the frames — or, for a link that fell silent, the frames the
            expectation was learned from, because there are no live frames and that absence *is*
            the finding.
        evidence: The promoted fact, of kind `EvidenceKind.RELATIONSHIP_CHANGE`.
    """

    model_config = ConfigDict(frozen=True)

    finding: Observation
    evidence: Evidence


class CommandEvidence(BaseModel):
    """Everything the command path produced for one run, ready to store and to reason over.

    A value rather than a bag of loose lists, so a caller cannot hand the engine the evidence while
    forgetting the deviations and observations that make it traceable.

    Attributes:
        departures: Command-behaviour readings that left their learned band.
        changes: Structural changes measured against the learned command graph.
    """

    model_config = ConfigDict(frozen=True)

    departures: tuple[CommandDeparture, ...] = ()
    changes: tuple[GraphChange, ...] = ()

    def evidence(self) -> tuple[Evidence, ...]:
        """Return both streams merged into one, earliest first.

        Returns:
            The evidence in time order, ties broken by kind and then by summary so two runs over
            one capture agree (Constitution §3.7). Order matters to `ReasoningEngine.ingest`: it
            decides which hypotheses spawn, and interleaving the streams by time is what lets a
            structural change and the command behaviour around it land in one story.
        """
        merged = [departure.evidence for departure in self.departures]
        merged.extend(change.evidence for change in self.changes)
        merged.sort(key=lambda item: (item.timestamp, item.kind.value, item.summary))
        return tuple(merged)


def promote_command_behaviour(
    observations: Sequence[Observation],
    fitted: FittedModel,
    calibrator: FittedCalibrator,
) -> list[CommandDeparture]:
    """Score command-behaviour observations and promote the genuine departures into `Evidence`.

    The sensor path's five steps, unchanged and in the same order: score, pair each deviation with
    its measurement, keep only the readings that actually left their `ExpectedRange`, calibrate the
    magnitudes in one batch, and promote through 4A's boundary.

    Args:
        observations: `phos.atlas.featurise_commands` output — one scalar per device per window per
            feature. Should be a slice the model was **not** fitted on.
        fitted: A model fitted on command behaviour believed normal. Any `FittedModel` works;
            `PerKeyBehaviouralModel` keys on ``(device, feature)``, which is what these
            observations already are.
        calibrator: A calibrator fitted on a held-out, **labelled** calibration slice. Supplies
            each piece of evidence's weight, which Constitution §3.3 requires to be a calibrated
            probability. Nothing here can check that it was fitted honestly — see
            `phos.reasoning.splits` and `UNMEASURED_COMMAND_DETECTION_CAVEAT`.

    Returns:
        One `CommandDeparture` per genuine departure, earliest first with ties broken by feature,
        so the result is a function of the input and not of its order.

    Raises:
        ValueError: If any observation is a command-graph finding, because the two streams answer
            different questions — a finding names two entities and has no learned band, and scoring
            it as behaviour would attribute a relationship to its issuer alone and judge it against
            whatever baseline that key happened to hold. Or, propagated from the boundary, if the
            calibrator returns something that is not a probability.
    """
    _refuse_graph_findings(observations)

    by_id = {observation.id: observation for observation in observations}
    departures: list[tuple[Deviation, Observation]] = []
    for deviation in fitted.score(observations):
        observation = by_id.get(deviation.observation_id)
        if observation is None:
            raise ValueError(
                f"{fitted.name} produced a deviation for unknown observation "
                f"{deviation.observation_id!r}, which cannot be traced back to a measurement"
            )
        if is_out_of_band(deviation, observation):
            departures.append((deviation, observation))

    departures.sort(key=lambda pair: (pair[1].timestamp, pair[1].feature, pair[1].id))
    weights = calibrated_probabilities(
        calibrator, [deviation.magnitude for deviation, _ in departures]
    )

    promoted = [
        CommandDeparture(
            observation=observation,
            deviation=deviation,
            evidence=evidence_from_deviation(
                deviation,
                observation,
                weight,
                summary=_describe_departure(deviation, observation),
                facet=(FacetKind.COMMAND_BEHAVIOUR, observation.feature),
            ),
        )
        for (deviation, observation), weight in zip(departures, weights, strict=True)
    ]
    logger.info(
        "promoted %d of %d command-behaviour observation(s) into evidence",
        len(promoted),
        len(observations),
    )
    return promoted


def promote_graph_findings(
    findings: Sequence[Observation], calibrator: FittedCalibrator
) -> list[GraphChange]:
    """Promote measured command-graph changes into `Evidence`.

    Args:
        findings: `phos.atlas.compare_to_graph` output. Every one must name a feature in
            `GRAPH_FINDING_FEATURES`.
        calibrator: A calibrator fitted on labelled graph-finding scores. The score is the
            finding's own value, which is why it is defined so that a larger number always means a
            larger departure. See `POOLED_GRAPH_CALIBRATION_CAVEAT` for the limit this carries.

    Returns:
        One `GraphChange` per finding, earliest first with ties broken by the relationship and then
        the feature.

    Raises:
        ValueError: If a finding names a feature this module does not recognise, because
            summarising it would put an operator-facing sentence on a change nothing measured. Or,
            propagated from the boundary, if a finding measures a change of zero, names fewer than
            two entities, or the calibrator returns something that is not a probability.
    """
    unknown = sorted({f.feature for f in findings} - set(GRAPH_FINDING_FEATURES))
    if unknown:
        raise ValueError(
            f"{', '.join(unknown)} is not a command-graph finding; this module reads only "
            f"{', '.join(GRAPH_FINDING_FEATURES)}, and describing an unrecognised feature would "
            "put a sentence an operator acts on in front of a change nothing here measured"
        )

    ordered = sorted(findings, key=lambda f: (f.timestamp, f.entity_ids, f.feature))
    weights = calibrated_probabilities(calibrator, [finding.value for finding in ordered])

    promoted = [
        GraphChange(
            finding=finding,
            evidence=evidence_from_relationship_change(
                finding,
                weight,
                summary=_describe_change(finding),
                facet=(FacetKind.GRAPH_FINDING, finding.feature),
            ),
        )
        for finding, weight in zip(ordered, weights, strict=True)
    ]
    logger.info("promoted %d command-graph finding(s) into evidence", len(promoted))
    return promoted


def _refuse_graph_findings(observations: Sequence[Observation]) -> None:
    """Raise if a relationship finding has been passed to the behaviour promoter."""
    crossed = sorted({o.feature for o in observations} & set(GRAPH_FINDING_FEATURES))
    if crossed:
        raise ValueError(
            f"{', '.join(crossed)} describes a relationship between two devices, not one device's "
            "behaviour; promote it with promote_graph_findings, which routes it through the "
            "relationship-change boundary instead of scoring it against a baseline it has none of"
        )


def _describe_departure(deviation: Deviation, observation: Observation) -> str:
    """Render one command-behaviour departure as a sentence an operator can act on.

    Names the device rather than only the feature, because the whole point of keying command
    behaviour on ``(device, feature)`` is that the answer to "which box do I go and look at" is
    already in the measurement.
    """
    expected = deviation.expected
    device = observation.context.get("device_ip", observation.entity_ids[0])
    return (
        f"{command_behaviour_marker(observation.feature)}{device} {observation.feature} was "
        f"{observation.value:.6g}; this device normally runs "
        f"{expected.low:.6g} to {expected.high:.6g} (mean {expected.mean:.6g}), "
        f"{deviation.magnitude:.2f} spreads out"
    )


def _describe_change(finding: Observation) -> str:
    """Render one command-graph change as a sentence an operator can act on.

    The sentence is prefixed with `graph_finding_marker` so a template can tell an unknown master
    from a function-code change on a known link without `Evidence` growing a feature field.
    """
    issuer = finding.context.get("issuer_ip", finding.entity_ids[0])
    target = finding.context.get("target_ip", finding.entity_ids[1])

    if finding.feature == UNKNOWN_COMMAND_RELATIONSHIP:
        codes = finding.context.get("function_codes", "unrecorded")
        body = (
            f"{issuer} issued {finding.value:.6g} command(s) to {target} over a relationship that "
            f"is absent from the learned command graph (function code(s) {codes})"
        )
    elif finding.feature == SILENT_COMMAND_RELATIONSHIP:
        learned = finding.context.get("learned_command_count", "an unrecorded number of")
        learned_s = finding.context.get("learned_span_seconds")
        live_s = finding.context.get("live_span_seconds")
        span_note = ""
        if learned_s is not None and live_s is not None:
            span_note = f" (learned {learned_s}s vs live {live_s}s)"
        body = (
            f"{issuer} sent {target} nothing, on a link that carried {learned} command(s) while "
            f"the graph was learned — a comparable stretch implying {finding.value:.6g} in this "
            f"window{span_note}"
        )
    else:
        code = finding.context.get("function_code", "unrecorded")
        name = finding.context.get("function_name", "unnamed")
        body = (
            f"{issuer} used function {code} ({name}) on {target} {finding.value:.6g} time(s); that "
            f"function code was never seen on this link while the graph was learned"
        )
    return f"{graph_finding_marker(finding.feature)} {body}"

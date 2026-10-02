"""U5 case fixtures: six Atlas incidents and one Sentiel limitation case. Atlas never reads gold."""

from __future__ import annotations

from datetime import UTC, datetime

from phos.atlas.command_evidence import graph_finding_marker
from phos.atlas.packet.graph import UNEXPECTED_COMMAND_FUNCTION, UNKNOWN_COMMAND_RELATIONSHIP
from phos.atlas.templates import (
    ENGINEERING_MAINTENANCE_TEMPLATE_ID,
    UNAUTHORISED_CONTROL_TEMPLATE_ID,
    atlas_library,
)
from phos.atlas.work_orders import work_order_marker
from phos.eval.decision_study import (
    Case,
    Conclusion,
    Gold,
    raw_telemetry_stimulus,
    stimulus_banner,
    threshold_alert_stimulus,
    threshold_quiet_stimulus,
)
from phos.ontology import (
    Domain,
    Entity,
    EntityType,
    Evidence,
    EvidenceKind,
    FacetKind,
    Hypothesis,
    HypothesisStatus,
    InMemoryEvidenceStore,
    Narrative,
)
from phos.reasoning.belief import CONFIDENCE_CEILING, LEAD_TIE_EPSILON
from phos.reasoning.templates import (
    INSUFFICIENT_EVIDENCE_TEMPLATE_ID,
    insufficient_evidence_template,
)
from phos.sentiel.templates import sentiel_library
from phos.synth.diagnostic_scenarios import DiagnosticKind

__all__ = [
    "ATLAS_CASE_IDS",
    "SENTIEL_CASE_ID",
    "Case",
    "atlas_cases",
    "case_pack",
    "sentiel_cases",
]

T0 = datetime(2026, 3, 1, 2, 0, tzinfo=UTC)
ATLAS_CASE_IDS: tuple[str, ...] = (
    "ordinary-quiet",
    "maintenance-covered",
    "known-station-write",
    "unknown-master-write",
    "attacker-during-maintenance",
    "incomplete-observations",
)
SENTIEL_CASE_ID: str = "sentiel-tied-rivals"


def case_pack() -> tuple[Case, ...]:
    """Return the seven fixtures in declared order."""
    return atlas_cases() + sentiel_cases()


def atlas_cases() -> tuple[Case, ...]:
    """Six Atlas incidents. Primary comparison uses only these."""
    return (
        _ordinary(),
        _maintenance_covered(),
        _known_station(),
        _unknown_master(),
        _attacker_during_maintenance(),
        _incomplete(),
    )


def sentiel_cases() -> tuple[Case, ...]:
    """One Sentiel case whose settling ask cannot be a behaviour fact the templates declare."""
    return (_sentiel_tied(),)


def _atlas_case(
    case_id: str,
    kind: DiagnosticKind,
    gold: Gold,
    *,
    raw: str,
    threshold: str,
    narrative: Narrative,
    parts: tuple[Entity | Evidence | Hypothesis | Narrative, ...],
) -> Case:
    return Case(
        case_id=case_id,
        domain=Domain.ATLAS,
        kind=kind.value,
        gold=gold,
        in_primary_comparison=True,
        raw_stimulus=raw,
        threshold_stimulus=threshold,
        store=_store(*parts),
        narrative=narrative,
        library=atlas_library(),
    )


def _ordinary() -> Case:
    residual = _residual(Domain.ATLAS, "hyp_ordinary_residual")
    narrative = Narrative(
        id="nar_ordinary",
        title="Intake levels on the quiet hour",
        domain=Domain.ATLAS,
        hypothesis_ids=[residual.id],
        evidence_ids=[],
    )
    return _atlas_case(
        "ordinary-quiet",
        DiagnosticKind.ORDINARY_OPERATION,
        Gold(
            conclusion=Conclusion.ORDINARY_OPERATION,
            should_escalate=False,
            uncertainty_important=False,
        ),
        raw=raw_telemetry_stimulus(
            "Intake, dosing and filtration sit inside the declared band. No write on the bus."
        ),
        threshold=threshold_quiet_stimulus(),
        narrative=narrative,
        parts=(_plc(), residual, narrative),
    )


def _maintenance_covered() -> Case:
    order = _rel(
        "ev_wo_covered", FacetKind.WORK_ORDER, "covering", "WO-441 covering dosing pump service"
    )
    residual = _residual(Domain.ATLAS, "hyp_maint_residual")
    maintenance = _hypothesis(
        "hyp_maint_lead",
        ENGINEERING_MAINTENANCE_TEMPLATE_ID,
        "A planned engineering or maintenance change",
        confidence=0.71,
        supporting=[order.id],
    )
    attack = _hypothesis(
        "hyp_maint_attack",
        UNAUTHORISED_CONTROL_TEMPLATE_ID,
        "Unauthorised control activity on this unit",
        confidence=0.12,
        contradictory=[order.id],
    )
    narrative = Narrative(
        id="nar_maint",
        title="Sanctioned work on dosing",
        domain=Domain.ATLAS,
        hypothesis_ids=[maintenance.id, attack.id, residual.id],
        evidence_ids=[order.id],
    )
    return _atlas_case(
        "maintenance-covered",
        DiagnosticKind.MAINTENANCE,
        Gold(
            conclusion=Conclusion.ENGINEERING_MAINTENANCE,
            should_escalate=False,
            uncertainty_important=False,
        ),
        raw=raw_telemetry_stimulus(
            "Dosing setpoint stepped at 02:00. CMMS row WO-441 names this asset and this window."
        ),
        threshold=threshold_alert_stimulus("dosing_setpoint", "1.40", "1.00"),
        narrative=narrative,
        parts=(_plc(), order, residual, maintenance, attack, narrative),
    )


def _known_station() -> Case:
    finding = _rel(
        "ev_known_link",
        FacetKind.GRAPH_FINDING,
        UNEXPECTED_COMMAND_FUNCTION,
        "Unexpected function code on a learned SCADA to PLC link",
    )
    residual = _residual(Domain.ATLAS, "hyp_known_residual")
    attack = _hypothesis(
        "hyp_known_attack",
        UNAUTHORISED_CONTROL_TEMPLATE_ID,
        "Unauthorised control activity on this unit",
        confidence=CONFIDENCE_CEILING,
        supporting=[finding.id],
    )
    maintenance = _hypothesis(
        "hyp_known_maint",
        ENGINEERING_MAINTENANCE_TEMPLATE_ID,
        "A planned engineering or maintenance change",
        confidence=CONFIDENCE_CEILING - (LEAD_TIE_EPSILON / 2),
        supporting=[finding.id],
    )
    narrative = Narrative(
        id="nar_known",
        title="Command activity on PLC-1",
        domain=Domain.ATLAS,
        hypothesis_ids=[residual.id, attack.id, maintenance.id],
        evidence_ids=[finding.id],
    )
    return _atlas_case(
        "known-station-write",
        DiagnosticKind.UNAUTHORISED_COMMANDS,
        Gold(
            conclusion=Conclusion.UNRESOLVED,
            should_escalate=False,
            uncertainty_important=True,
        ),
        raw=raw_telemetry_stimulus(
            "SCADA wrote an unexpected function to PLC-1. No work-order column on this capture."
        ),
        threshold=threshold_alert_stimulus("scada_write_rate", "4.10", "3.00"),
        narrative=narrative,
        parts=(_plc(), finding, residual, attack, maintenance, narrative),
    )


def _unknown_master() -> Case:
    finding = _rel(
        "ev_unknown",
        FacetKind.GRAPH_FINDING,
        UNKNOWN_COMMAND_RELATIONSHIP,
        "A write from a device that has never commanded this target",
    )
    residual = _residual(Domain.ATLAS, "hyp_unknown_residual")
    attack = _hypothesis(
        "hyp_unknown_attack",
        UNAUTHORISED_CONTROL_TEMPLATE_ID,
        "Unauthorised control activity on this unit",
        confidence=0.82,
        supporting=[finding.id],
    )
    maintenance = _hypothesis(
        "hyp_unknown_maint",
        ENGINEERING_MAINTENANCE_TEMPLATE_ID,
        "A planned engineering or maintenance change",
        confidence=0.11,
        contradictory=[finding.id],
    )
    narrative = Narrative(
        id="nar_unknown",
        title="Write from an unseen master",
        domain=Domain.ATLAS,
        hypothesis_ids=[attack.id, residual.id, maintenance.id],
        evidence_ids=[finding.id],
    )
    return _atlas_case(
        "unknown-master-write",
        DiagnosticKind.ATTACKER_ACTIVITY,
        Gold(
            conclusion=Conclusion.UNAUTHORISED_CONTROL,
            should_escalate=True,
            uncertainty_important=False,
        ),
        raw=raw_telemetry_stimulus(
            "Address 10.0.0.99 wrote holding registers on PLC-1. Absent from the learned graph."
        ),
        threshold=threshold_alert_stimulus("unknown_master_writes", "1", "0"),
        narrative=narrative,
        parts=(_plc(), finding, residual, attack, maintenance, narrative),
    )


def _attacker_during_maintenance() -> Case:
    order = _rel(
        "ev_wo_window", FacetKind.WORK_ORDER, "covering", "WO-880 covering filtration this hour"
    )
    finding = _rel(
        "ev_in_window",
        FacetKind.GRAPH_FINDING,
        UNEXPECTED_COMMAND_FUNCTION,
        "Unexpected function code on a learned SCADA to PLC link inside the sanctioned window",
    )
    residual = _residual(Domain.ATLAS, "hyp_overlap_residual")
    maintenance = _hypothesis(
        "hyp_overlap_maint",
        ENGINEERING_MAINTENANCE_TEMPLATE_ID,
        "A planned engineering or maintenance change",
        confidence=0.74,
        supporting=[order.id, finding.id],
    )
    attack = _hypothesis(
        "hyp_overlap_attack",
        UNAUTHORISED_CONTROL_TEMPLATE_ID,
        "Unauthorised control activity on this unit",
        confidence=0.18,
        supporting=[finding.id],
        contradictory=[order.id],
    )
    narrative = Narrative(
        id="nar_overlap",
        title="Write inside a sanctioned window",
        domain=Domain.ATLAS,
        hypothesis_ids=[maintenance.id, attack.id, residual.id],
        evidence_ids=[order.id, finding.id],
    )
    return _atlas_case(
        "attacker-during-maintenance",
        DiagnosticKind.ATTACKER_DURING_MAINTENANCE,
        Gold(
            conclusion=Conclusion.UNRESOLVED,
            should_escalate=False,
            uncertainty_important=True,
        ),
        raw=raw_telemetry_stimulus(
            "SCADA wrote during WO-880. The order names the unit, not this function code."
        ),
        threshold=threshold_alert_stimulus("filtration_write", "2.20", "1.00"),
        narrative=narrative,
        parts=(_plc(), order, finding, residual, maintenance, attack, narrative),
    )


def _incomplete() -> Case:
    residual = _residual(Domain.ATLAS, "hyp_incomplete_residual")
    narrative = Narrative(
        id="nar_incomplete",
        title="Telemetry without a capture",
        domain=Domain.ATLAS,
        hypothesis_ids=[residual.id],
        evidence_ids=[],
    )
    return _atlas_case(
        "incomplete-observations",
        DiagnosticKind.INCOMPLETE_OBSERVATIONS,
        Gold(
            conclusion=Conclusion.UNRESOLVED,
            should_escalate=False,
            uncertainty_important=True,
        ),
        raw=raw_telemetry_stimulus(
            "Process values only. The live capture was withheld. Command facts are absent."
        ),
        threshold=threshold_quiet_stimulus(),
        narrative=narrative,
        parts=(_plc(), residual, narrative),
    )


def _sentiel_tied() -> Case:
    user = Entity(
        id="ent_cch0959",
        type=EntityType.USER,
        domain=Domain.SENTIEL,
        name="CCH0959",
    )
    evidence = Evidence(
        id="ev_sentiel_day",
        kind=EvidenceKind.DEVIATION,
        source_id="src_sentiel_day",
        entity_ids=[user.id],
        timestamp=T0,
        domain=Domain.SENTIEL,
        summary="Data-handling departure on CCH0959",
    )
    residual = _residual(Domain.SENTIEL, "hyp_sentiel_residual")
    left = _hypothesis(
        "hyp_sentiel_insider",
        "insider_misuse",
        "This person is deliberately misusing their access",
        confidence=CONFIDENCE_CEILING,
        domain=Domain.SENTIEL,
        supporting=[evidence.id],
    )
    right = _hypothesis(
        "hyp_sentiel_benign",
        "benign_role_change",
        "A sanctioned change in this person's role or work",
        confidence=CONFIDENCE_CEILING,
        domain=Domain.SENTIEL,
        supporting=[evidence.id],
    )
    narrative = Narrative(
        id="nar_sentiel",
        title="Behavioural departure for CCH0959",
        domain=Domain.SENTIEL,
        hypothesis_ids=[residual.id, left.id, right.id],
        evidence_ids=[evidence.id],
    )
    return Case(
        case_id=SENTIEL_CASE_ID,
        domain=Domain.SENTIEL,
        kind="sentiel_tied_rivals",
        gold=Gold(
            conclusion=Conclusion.UNRESOLVED,
            should_escalate=False,
            uncertainty_important=True,
        ),
        in_primary_comparison=False,
        raw_stimulus=(
            f"{stimulus_banner()}\n\n"
            "Entity-day feature vector for CCH0959. Volume and novelty counts only. "
            "No sanction record is attached."
        ),
        threshold_stimulus=threshold_alert_stimulus("entity_day_score", "4.50", "13.70"),
        store=_store(user, evidence, residual, left, right, narrative),
        narrative=narrative,
        library=sentiel_library(),
        sentiel_settling_is_weak=True,
    )


def _plc() -> Entity:
    return Entity(id="ent_plc1", type=EntityType.PLC, domain=Domain.ATLAS, name="PLC-1")


def _residual(domain: Domain, hypothesis_id: str) -> Hypothesis:
    template = insufficient_evidence_template(domain)
    return Hypothesis(
        id=hypothesis_id,
        label=template.label,
        template_id=INSUFFICIENT_EVIDENCE_TEMPLATE_ID,
        domain=domain,
        prior=template.prior,
        confidence=template.prior,
        status=HypothesisStatus.ACTIVE,
    )


def _hypothesis(
    hypothesis_id: str,
    template_id: str,
    label: str,
    *,
    confidence: float,
    domain: Domain = Domain.ATLAS,
    supporting: list[str] | None = None,
    contradictory: list[str] | None = None,
) -> Hypothesis:
    return Hypothesis(
        id=hypothesis_id,
        label=label,
        template_id=template_id,
        domain=domain,
        prior=0.2,
        confidence=confidence,
        status=HypothesisStatus.ACTIVE,
        supporting=supporting or [],
        contradictory=contradictory or [],
    )


def _rel(evidence_id: str, facet_kind: FacetKind, facet: str, prose: str) -> Evidence:
    marker = (
        work_order_marker(facet)
        if facet_kind is FacetKind.WORK_ORDER
        else graph_finding_marker(facet)
    )
    return Evidence(
        id=evidence_id,
        kind=EvidenceKind.RELATIONSHIP_CHANGE,
        source_id=f"src_{evidence_id}",
        entity_ids=["ent_plc1"],
        timestamp=T0,
        domain=Domain.ATLAS,
        summary=f"{marker} {prose}",
        facet_kind=facet_kind,
        facet=facet,
    )


def _store(*objects: Entity | Evidence | Hypothesis | Narrative) -> InMemoryEvidenceStore:
    store = InMemoryEvidenceStore()
    for obj in objects:
        if isinstance(obj, Entity):
            store.add_entity(obj)
        elif isinstance(obj, Evidence):
            store.add_evidence(obj)
        elif isinstance(obj, Hypothesis):
            store.add_hypothesis(obj)
        else:
            store.add_narrative(obj)
    return store

"""Tests for `phos.reasoning.analyst` — Usefulness Phase U4 plain-English narrative renderer.

Pins the four properties the usefulness roadmap requires, the Gate 2 depth-blind ceiling on
Sentiel output, and the rule that no probability is required to act.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

import pytest

from phos.atlas.templates import (
    ENGINEERING_MAINTENANCE_TEMPLATE_ID,
    UNAUTHORISED_CONTROL_TEMPLATE_ID,
    atlas_library,
)
from phos.atlas.work_orders import work_order_marker
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
from phos.reasoning.analyst import (
    Assessment,
    assess_narrative,
    describe_pattern,
    render_narrative_markdown,
    settling_fact,
)
from phos.reasoning.belief import CONFIDENCE_CEILING, LEAD_TIE_EPSILON
from phos.reasoning.templates import (
    EvidencePattern,
    generic_library,
    insufficient_evidence_template,
)
from phos.sentiel.failure import (
    CCH0959_MALICIOUS_ENTITY_DAYS,
    CCH0959_STRUCTURALLY_UNALERTABLE_DAYS,
    PART_6B_ALERT_BUDGET,
    PART_6B_ALERT_THRESHOLD,
    features_required,
)
from phos.sentiel.featurise import PEER_FEATURES
from phos.sentiel.templates import sentiel_library

T0 = datetime(2026, 9, 16, 10, 0, tzinfo=UTC)
REPO = Path(__file__).resolve().parents[2]
FAILURE_JSON = REPO / "eval_runs" / "sentiel" / "cert-failure-classification.json"


def _entity(entity_id: str = "ent_plc") -> Entity:
    return Entity(
        id=entity_id,
        type=EntityType.PLC,
        domain=Domain.ATLAS,
        name="PLC-1",
    )


def _evidence(
    evidence_id: str,
    *,
    summary: str,
    domain: Domain = Domain.ATLAS,
    kind: EvidenceKind = EvidenceKind.RELATIONSHIP_CHANGE,
    facet: tuple[FacetKind, str] | None = None,
) -> Evidence:
    kwargs: dict[str, object] = {
        "id": evidence_id,
        "kind": kind,
        "source_id": f"src_{evidence_id}",
        "entity_ids": ["ent_plc"],
        "timestamp": T0,
        "domain": domain,
        "summary": summary,
    }
    if facet is not None:
        kwargs["facet_kind"] = facet[0]
        kwargs["facet"] = facet[1]
    return Evidence(**kwargs)  # type: ignore[arg-type]


def _hypothesis(
    template_id: str,
    label: str,
    *,
    confidence: float,
    domain: Domain = Domain.ATLAS,
    supporting: list[str] | None = None,
    contradictory: list[str] | None = None,
) -> Hypothesis:
    return Hypothesis(
        label=label,
        template_id=template_id,
        domain=domain,
        prior=0.2,
        confidence=confidence,
        status=HypothesisStatus.ACTIVE,
        supporting=supporting or [],
        contradictory=contradictory or [],
    )


def _store_with(
    *objects: Entity | Evidence | Hypothesis | Narrative,
) -> InMemoryEvidenceStore:
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


def test_unresolved_when_attack_and_maintenance_share_the_ceiling() -> None:
    """Known-link indistinguishability: unresolved is first-class, not a failure."""
    evidence = _evidence(
        "ev_known_link",
        summary="Unexpected function code on a learned SCADA→PLC link",
        facet=(FacetKind.GRAPH_FINDING, "unexpected_command_function"),
    )
    attack = _hypothesis(
        UNAUTHORISED_CONTROL_TEMPLATE_ID,
        "Unauthorised control activity on this unit",
        confidence=CONFIDENCE_CEILING,
        supporting=[evidence.id],
    )
    maintenance = _hypothesis(
        ENGINEERING_MAINTENANCE_TEMPLATE_ID,
        "A planned engineering or maintenance change",
        confidence=CONFIDENCE_CEILING - (LEAD_TIE_EPSILON / 2),
        supporting=[evidence.id],
    )
    residual = insufficient_evidence_template(Domain.ATLAS).instantiate()
    # rank_hypotheses would raise residual first; mirror that order on the narrative.
    narrative = Narrative(
        title="Command activity on PLC-1",
        domain=Domain.ATLAS,
        hypothesis_ids=[residual.id, attack.id, maintenance.id],
        evidence_ids=[evidence.id],
    )
    store = _store_with(_entity(), evidence, residual, attack, maintenance, narrative)
    brief = assess_narrative(narrative, store, atlas_library())

    assert brief.assessment is Assessment.UNRESOLVED
    assert "unresolved" in brief.assessment_line.lower()
    assert "Unauthorised" in brief.assessment_line or "maintenance" in brief.assessment_line.lower()
    rendered = render_narrative_markdown(brief)
    assert "unresolved" in rendered.lower()
    assert re.search(r"0\.\d+|confidence|prior", rendered, flags=re.IGNORECASE) is None or (
        "uncalibrated" in rendered.lower() and "not shown" in rendered.lower()
    )


def test_next_evidence_names_a_covering_work_order_for_atlas_rivals() -> None:
    """The settling ask is a specific fact the templates already declare, not a vague request."""
    evidence = _evidence(
        "ev_known_link",
        summary="Unexpected function code on a learned link",
        facet=(FacetKind.GRAPH_FINDING, "unexpected_command_function"),
    )
    attack = _hypothesis(
        UNAUTHORISED_CONTROL_TEMPLATE_ID,
        "Unauthorised control activity on this unit",
        confidence=CONFIDENCE_CEILING,
        supporting=[evidence.id],
    )
    maintenance = _hypothesis(
        ENGINEERING_MAINTENANCE_TEMPLATE_ID,
        "A planned engineering or maintenance change",
        confidence=CONFIDENCE_CEILING,
        supporting=[evidence.id],
    )
    residual = insufficient_evidence_template(Domain.ATLAS).instantiate()
    narrative = Narrative(
        title="Command activity on PLC-1",
        domain=Domain.ATLAS,
        hypothesis_ids=[residual.id, attack.id, maintenance.id],
        evidence_ids=[evidence.id],
    )
    store = _store_with(_entity(), evidence, residual, attack, maintenance, narrative)
    brief = assess_narrative(narrative, store, atlas_library())

    next_lower = brief.next_evidence.lower()
    assert "work order" in next_lower or "never commanded" in next_lower
    assert "vague" not in next_lower
    assert brief.ranking_limit is None


def test_resolved_assessment_names_the_leader_without_a_probability() -> None:
    evidence = _evidence(
        "ev_order",
        summary=work_order_marker("WO-1"),
        facet=(FacetKind.WORK_ORDER, "covering"),
    )
    maintenance = _hypothesis(
        ENGINEERING_MAINTENANCE_TEMPLATE_ID,
        "A planned engineering or maintenance change",
        confidence=0.71,
        supporting=[evidence.id],
    )
    attack = _hypothesis(
        UNAUTHORISED_CONTROL_TEMPLATE_ID,
        "Unauthorised control activity on this unit",
        confidence=0.12,
        contradictory=[evidence.id],
    )
    residual = insufficient_evidence_template(Domain.ATLAS).instantiate()
    narrative = Narrative(
        title="Sanctioned work on PLC-1",
        domain=Domain.ATLAS,
        hypothesis_ids=[maintenance.id, attack.id, residual.id],
        evidence_ids=[evidence.id],
    )
    store = _store_with(_entity(), evidence, residual, attack, maintenance, narrative)
    brief = assess_narrative(narrative, store, atlas_library())

    assert brief.assessment is Assessment.RESOLVED
    assert "planned engineering or maintenance" in brief.assessment_line.lower()
    assert "0.71" not in render_narrative_markdown(brief)
    assert "0.12" not in render_narrative_markdown(brief)


def test_sentiel_render_documents_the_depth_blind_ceiling() -> None:
    """Gate 2: the ceiling appears in the rendered output itself, not only in an ADR."""
    user = Entity(
        id="ent_user",
        type=EntityType.USER,
        domain=Domain.SENTIEL,
        name="CCH0959",
    )
    evidence = _evidence(
        "ev_day",
        summary="Data-handling departure on CCH0959",
        domain=Domain.SENTIEL,
        kind=EvidenceKind.DEVIATION,
    )
    insider = _hypothesis(
        "insider_misuse",
        "This person is deliberately misusing their access",
        confidence=0.4,
        domain=Domain.SENTIEL,
        supporting=[evidence.id],
    )
    benign = _hypothesis(
        "benign_role_change",
        "A sanctioned change in this person's role or work",
        confidence=0.4,
        domain=Domain.SENTIEL,
        supporting=[evidence.id],
    )
    residual = insufficient_evidence_template(Domain.SENTIEL).instantiate()
    narrative = Narrative(
        title="Behavioural departure for CCH0959",
        domain=Domain.SENTIEL,
        hypothesis_ids=[residual.id, insider.id, benign.id],
        evidence_ids=[evidence.id],
    )
    store = _store_with(user, evidence, residual, insider, benign, narrative)
    brief = assess_narrative(narrative, store, sentiel_library())
    rendered = render_narrative_markdown(brief)

    assert brief.ranking_limit is not None
    assert "Known limit of this ranking" in rendered
    required = features_required(PART_6B_ALERT_THRESHOLD)
    n_features = len(PEER_FEATURES)
    assert str(required) in rendered
    assert str(n_features) in rendered
    assert str(PART_6B_ALERT_BUDGET) in rendered
    assert str(CCH0959_STRUCTURALLY_UNALERTABLE_DAYS) in rendered
    assert str(CCH0959_MALICIOUS_ENTITY_DAYS) in rendered
    assert "depth-blind" in rendered.lower() or "depth-blind" in brief.ranking_limit.lower()
    assert "not a gap in the data" in rendered.lower()


def test_sentiel_unresolved_names_sanction_when_templates_have_no_contradiction() -> None:
    """Sentiel templates declare no contradictory patterns — the renderer must say so."""
    evidence = _evidence(
        "ev_day",
        summary="Access departure",
        domain=Domain.SENTIEL,
        kind=EvidenceKind.DEVIATION,
    )
    left = _hypothesis(
        "compromised_account",
        "This account is being used by someone other than its owner",
        confidence=CONFIDENCE_CEILING,
        domain=Domain.SENTIEL,
        supporting=[evidence.id],
    )
    right = _hypothesis(
        "insider_misuse",
        "This person is deliberately misusing their access",
        confidence=CONFIDENCE_CEILING,
        domain=Domain.SENTIEL,
        supporting=[evidence.id],
    )
    residual = insufficient_evidence_template(Domain.SENTIEL).instantiate()
    narrative = Narrative(
        title="Account activity",
        domain=Domain.SENTIEL,
        hypothesis_ids=[residual.id, left.id, right.id],
        evidence_ids=[evidence.id],
    )
    store = _store_with(
        Entity(id="ent_user", type=EntityType.USER, domain=Domain.SENTIEL, name="U"),
        evidence,
        residual,
        left,
        right,
        narrative,
    )
    brief = assess_narrative(narrative, store, sentiel_library())

    assert brief.assessment is Assessment.UNRESOLVED
    next_lower = brief.next_evidence.lower()
    assert "sanction" in next_lower or "change ticket" in next_lower
    assert "no behaviour fact the templates declare can settle this" in next_lower


def test_four_properties_appear_in_markdown_structure() -> None:
    evidence = _evidence("ev_1", summary="A structural change on the unit")
    hyp = _hypothesis(
        ENGINEERING_MAINTENANCE_TEMPLATE_ID,
        "A planned engineering or maintenance change",
        confidence=0.55,
        supporting=[evidence.id],
    )
    residual = insufficient_evidence_template(Domain.ATLAS).instantiate()
    narrative = Narrative(
        title="Structural change",
        domain=Domain.ATLAS,
        hypothesis_ids=[hyp.id, residual.id],
        evidence_ids=[evidence.id],
    )
    store = _store_with(_entity(), evidence, residual, hyp, narrative)
    rendered = render_narrative_markdown(assess_narrative(narrative, store, atlas_library()))

    assert "## Assessment" in rendered
    assert "## What would settle this" in rendered
    assert "## Evidence" in rendered
    assert "## Why" in rendered
    assert "A structural change on the unit" in rendered


def test_no_probability_digits_required_to_act() -> None:
    """Confidence and prior must not appear as actionable figures."""
    evidence = _evidence("ev_1", summary="Something departed")
    hyp = _hypothesis(
        "generic_anomalous_activity",
        "Anomalous activity",
        confidence=0.876543,
        domain=Domain.ATLAS,
        supporting=[evidence.id],
    )
    residual = insufficient_evidence_template(Domain.ATLAS).instantiate()
    # Use generic library so we are not testing Atlas matchers.
    narrative = Narrative(
        title="Anomaly",
        domain=Domain.ATLAS,
        hypothesis_ids=[hyp.id, residual.id],
        evidence_ids=[evidence.id],
    )
    store = _store_with(_entity(), evidence, residual, hyp, narrative)
    rendered = render_narrative_markdown(
        assess_narrative(narrative, store, generic_library(Domain.ATLAS))
    )
    assert "0.876543" not in rendered
    assert "87%" not in rendered
    assert "0.2" not in rendered  # the fixture prior


def test_describe_pattern_names_work_order_and_unknown_master() -> None:
    from phos.atlas.packet.graph import UNKNOWN_COMMAND_RELATIONSHIP
    from phos.atlas.templates import GraphFindingPattern, WorkOrderPattern

    work = WorkOrderPattern(kinds=(EvidenceKind.RELATIONSHIP_CHANGE,))
    unknown = GraphFindingPattern(
        kinds=(EvidenceKind.RELATIONSHIP_CHANGE,),
        features=(UNKNOWN_COMMAND_RELATIONSHIP,),
    )
    assert "work order" in describe_pattern(work).lower()
    assert "never commanded" in describe_pattern(unknown).lower()
    bare = describe_pattern(EvidencePattern()).lower()
    kinded = describe_pattern(EvidencePattern(kinds=(EvidenceKind.DEVIATION,))).lower()
    assert "plain English" in bare or "fact" in kinded


def test_settling_fact_with_empty_rivals() -> None:
    text = settling_fact([], atlas_library(), already_present=[], entities={})
    assert "no contentful explanation" in text.lower()


def test_frozen_ceiling_constants_match_the_failure_report() -> None:
    """No number in the renderer that the classification report does not carry."""
    assert features_required(PART_6B_ALERT_THRESHOLD) == 14
    assert len(PEER_FEATURES) == 34
    if not FAILURE_JSON.is_file():
        pytest.skip("failure classification JSON not on disk")
    import json

    payload = json.loads(FAILURE_JSON.read_text(encoding="utf-8"))
    assert payload["features_required"] == features_required(PART_6B_ALERT_THRESHOLD)
    assert abs(float(payload["threshold"]) - PART_6B_ALERT_THRESHOLD) < 1e-12
    cch = next(item for item in payload["visibility"] if item["user_id"] == "CCH0959")
    assert cch["n_malicious_days"] == CCH0959_MALICIOUS_ENTITY_DAYS
    unalertable = sum(1 for day in cch["days"] if day["verdict"] == "structurally_unalertable")
    assert unalertable == CCH0959_STRUCTURALLY_UNALERTABLE_DAYS


def test_missing_hypothesis_is_a_traceability_failure() -> None:
    narrative = Narrative(
        title="Broken",
        domain=Domain.ATLAS,
        hypothesis_ids=["hyp_missing"],
        evidence_ids=[],
    )
    store = InMemoryEvidenceStore()
    with pytest.raises(KeyError):
        assess_narrative(narrative, store, atlas_library())


def test_atlas_render_does_not_inherit_a_sentiel_ceiling() -> None:
    evidence = _evidence("ev_1", summary="A fact")
    hyp = _hypothesis(
        ENGINEERING_MAINTENANCE_TEMPLATE_ID,
        "A planned engineering or maintenance change",
        confidence=0.6,
        supporting=[evidence.id],
    )
    residual = insufficient_evidence_template(Domain.ATLAS).instantiate()
    narrative = Narrative(
        title="Atlas only",
        domain=Domain.ATLAS,
        hypothesis_ids=[hyp.id, residual.id],
        evidence_ids=[evidence.id],
    )
    store = _store_with(_entity(), evidence, residual, hyp, narrative)
    brief = assess_narrative(narrative, store, atlas_library())
    assert brief.ranking_limit is None
    assert "Known limit of this ranking" not in render_narrative_markdown(brief)

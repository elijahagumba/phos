"""Evidence-grade reports: every current incident type renders, and uncited sentences fail.

Incident types are the template ids already registered for Atlas, Sentiel, and the generic
engine placeholders. The ontology does not define a separate incident-type enum.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from phos.atlas.templates import (
    ENGINEERING_MAINTENANCE_TEMPLATE_ID,
    PROCESS_DISTURBANCE_TEMPLATE_ID,
    SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID,
    UNAUTHORISED_CONTROL_TEMPLATE_ID,
    atlas_templates,
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
from phos.reasoning.reports import (
    CitedSentence,
    EvidenceGradeReport,
    PromptStatus,
    ReportCheckError,
    ReportRefusedError,
    ReportStageId,
    StatutoryPrompt,
    build_report,
    check_rendered_report,
    check_report,
    check_sentence,
    render_report,
)
from phos.reasoning.templates import (
    GENERIC_ANOMALOUS_ACTIVITY_TEMPLATE_ID,
    GENERIC_BENIGN_CHANGE_TEMPLATE_ID,
    INSUFFICIENT_EVIDENCE_TEMPLATE_ID,
    HypothesisTemplate,
    generic_templates,
    insufficient_evidence_template,
)
from phos.sentiel.templates import (
    BENIGN_ROLE_CHANGE_TEMPLATE_ID,
    COMPROMISED_ACCOUNT_TEMPLATE_ID,
    INSIDER_MISUSE_TEMPLATE_ID,
    PEER_ANOMALY_TEMPLATE_ID,
    sentiel_templates,
)

T0 = datetime(2026, 10, 17, 8, 0, tzinfo=UTC)
CONFIDENCE = 0.137
PRIOR = 0.241
OVERALL = 0.919

_EXPECTED_INCIDENT_TYPES = frozenset(
    {
        SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID,
        ENGINEERING_MAINTENANCE_TEMPLATE_ID,
        PROCESS_DISTURBANCE_TEMPLATE_ID,
        UNAUTHORISED_CONTROL_TEMPLATE_ID,
        BENIGN_ROLE_CHANGE_TEMPLATE_ID,
        PEER_ANOMALY_TEMPLATE_ID,
        COMPROMISED_ACCOUNT_TEMPLATE_ID,
        INSIDER_MISUSE_TEMPLATE_ID,
        GENERIC_ANOMALOUS_ACTIVITY_TEMPLATE_ID,
        GENERIC_BENIGN_CHANGE_TEMPLATE_ID,
        INSUFFICIENT_EVIDENCE_TEMPLATE_ID,
    }
)


def _registered_templates() -> tuple[HypothesisTemplate, ...]:
    found: list[HypothesisTemplate] = []
    seen: set[str] = set()
    for template in (*atlas_templates(), *sentiel_templates(), *generic_templates(Domain.ATLAS)):
        if template.template_id in seen:
            continue
        seen.add(template.template_id)
        found.append(template)
    return tuple(found)


_TEMPLATES = _registered_templates()


def _entity(domain: Domain) -> Entity:
    if domain is Domain.ATLAS:
        entity_type = EntityType.PLC
    else:
        entity_type = EntityType.USER
    return Entity(id="ent_unit", type=entity_type, domain=domain, name="Unit 1")


def _evidence(
    evidence_id: str,
    *,
    domain: Domain,
    summary: str,
    source_id: str = "source_reading",
    timestamp: datetime = T0,
    facet: tuple[FacetKind, str] | None = None,
) -> Evidence:
    kwargs: dict[str, object] = {
        "id": evidence_id,
        "kind": EvidenceKind.DEVIATION,
        "source_id": source_id,
        "entity_ids": ["ent_unit"],
        "timestamp": timestamp,
        "domain": domain,
        "summary": summary,
    }
    if facet is not None:
        kwargs["facet_kind"] = facet[0]
        kwargs["facet"] = facet[1]
    return Evidence(**kwargs)  # type: ignore[arg-type]


def _hypothesis_from(
    template: HypothesisTemplate,
    *,
    supporting: list[str] | None = None,
    contradictory: list[str] | None = None,
) -> Hypothesis:
    base = template.instantiate()
    return Hypothesis(
        id=base.id,
        label=base.label,
        template_id=base.template_id,
        domain=base.domain,
        prior=PRIOR,
        confidence=CONFIDENCE,
        status=HypothesisStatus.ACTIVE,
        supporting=supporting or [],
        contradictory=contradictory or [],
    )


def _store_story(
    template: HypothesisTemplate,
    *,
    summary: str = "Pump speed left its expected range",
    extra_summary: str | None = None,
    facet: tuple[FacetKind, str] | None = None,
    causal: bool = False,
    source_id: str = "source_reading",
) -> tuple[Narrative, InMemoryEvidenceStore]:
    """Build a stored narrative whose lead template is ``template``, residual always included."""
    domain = template.domain
    primary = _evidence(
        "ev_primary",
        domain=domain,
        summary=summary,
        facet=facet,
        source_id=source_id,
    )
    evidence_items = [primary]
    contradictory: list[str] = []
    if extra_summary is not None:
        extra = _evidence(
            "ev_extra",
            domain=domain,
            summary=extra_summary,
            source_id="source_extra",
            timestamp=datetime(2026, 10, 17, 8, 5, tzinfo=UTC),
        )
        evidence_items.append(extra)
        contradictory = [extra.id]
    residual = insufficient_evidence_template(domain).instantiate()
    if template.template_id == INSUFFICIENT_EVIDENCE_TEMPLATE_ID:
        hypotheses = [residual]
    else:
        lead = _hypothesis_from(
            template,
            supporting=[primary.id],
            contradictory=contradictory,
        )
        hypotheses = [lead, residual]
    edges: list[tuple[str, str]] = []
    if causal:
        edges.append((primary.id, hypotheses[0].id))
    narrative = Narrative(
        id="nar_story",
        title="UNCITED HEADLINE",
        domain=domain,
        hypothesis_ids=[item.id for item in hypotheses],
        evidence_ids=[item.id for item in evidence_items],
        causal_edges=edges,
        overall_confidence=OVERALL,
    )
    store = InMemoryEvidenceStore()
    store.add_entity(_entity(domain))
    for item in evidence_items:
        store.add_evidence(item)
    for hypothesis in hypotheses:
        store.add_hypothesis(hypothesis)
    store.add_narrative(narrative)
    return narrative, store


def _stage_text(report: EvidenceGradeReport, stage: ReportStageId) -> str:
    match = next(item for item in report.stages if item.stage is stage)
    return "\n".join(sentence.text for sentence in match.sentences)


def test_current_incident_types_are_the_registered_templates() -> None:
    """The catalogue is the templates PHOS already names, including the residual."""
    assert {template.template_id for template in _TEMPLATES} == _EXPECTED_INCIDENT_TYPES
    assert len(_TEMPLATES) == len(_EXPECTED_INCIDENT_TYPES)


@pytest.mark.parametrize("template", _TEMPLATES, ids=[item.template_id for item in _TEMPLATES])
def test_every_current_incident_type_renders(template: HypothesisTemplate) -> None:
    """Each registered template produces four cited stages and keeps the residual visible."""
    narrative, store = _store_story(template)
    report = build_report(narrative, store)
    check_report(report, store)
    rendered = render_report(report)
    check_rendered_report(rendered, store)

    assert template.template_id in report.incident_types
    assert report.incident_types[-1] == INSUFFICIENT_EVIDENCE_TEMPLATE_ID or (
        template.template_id == INSUFFICIENT_EVIDENCE_TEMPLATE_ID
        and report.incident_types == (INSUFFICIENT_EVIDENCE_TEMPLATE_ID,)
    )
    assert report.confidence_surfaced is False
    assert report.overall_confidence == "withheld"
    assert tuple(stage.stage for stage in report.stages) == (
        ReportStageId.NIS2_EARLY_WARNING_24H,
        ReportStageId.NIS2_INCIDENT_NOTIFICATION_72H,
        ReportStageId.UK_CSR_INITIAL_24H,
        ReportStageId.UK_CSR_FULL_72H,
    )
    for stage in report.stages:
        blob = "\n".join(sentence.text for sentence in stage.sentences)
        assert "insufficient_evidence" in blob
        assert template.template_id in blob
        assert "ev_primary" in blob
    early = _stage_text(report, ReportStageId.NIS2_EARLY_WARNING_24H)
    full = _stage_text(report, ReportStageId.NIS2_INCIDENT_NOTIFICATION_72H)
    assert full.startswith(early)
    assert len(full) > len(early)
    assert _stage_text(report, ReportStageId.UK_CSR_INITIAL_24H) == early
    assert _stage_text(report, ReportStageId.UK_CSR_FULL_72H) == full
    assert "UNCITED HEADLINE" not in rendered
    assert "Unit 1" not in rendered
    assert "probability" not in rendered.lower()
    assert "%" not in rendered
    assert "0.137" not in rendered
    assert "0.241" not in rendered
    assert "0.919" not in rendered
    assert "1.0" not in rendered
    malice = next(
        status
        for prompt, status in report.stages[0].prompts
        if prompt is StatutoryPrompt.UNLAWFUL_OR_MALICIOUS
    )
    assert malice is PromptStatus.NOT_ASSERTED


def test_a_sentence_without_an_evidence_id_is_rejected() -> None:
    """The checker fails closed on prose that cites nothing."""
    narrative, store = _store_story(_TEMPLATES[0])
    with pytest.raises(ReportCheckError, match="evidence id"):
        check_sentence("The pump left its expected range.", store)
    with pytest.raises(ValidationError):
        CitedSentence(text="The pump left its expected range.", evidence_ids=())
    rendered = render_report(build_report(narrative, store))
    tampered = rendered + "The unit was attacked by a named actor.\n"
    with pytest.raises(ReportCheckError, match="evidence id"):
        check_rendered_report(tampered, store)


def test_a_sentence_citing_unknown_evidence_is_rejected() -> None:
    """An evidence-shaped token that the store does not hold is not a citation."""
    _narrative, store = _store_story(_TEMPLATES[0])
    with pytest.raises(ReportCheckError, match="unknown evidence"):
        check_sentence("Stored evidence ev_missing records the reading.", store)


def test_metadata_cannot_smuggle_an_uncited_sentence() -> None:
    """A free-text line is a sentence, even when it looks like a field."""
    narrative, store = _store_story(_TEMPLATES[0])
    rendered = render_report(build_report(narrative, store))
    smuggled = rendered.replace(
        "confidence_surfaced=false",
        "confidence_surfaced=The unit was attacked",
        1,
    )
    with pytest.raises(ReportCheckError):
        check_rendered_report(smuggled, store)


def test_checker_rejects_a_surfaced_confidence() -> None:
    """A cited sentence that adds the stored confidence is still rejected."""
    narrative, store = _store_story(_TEMPLATES[0])
    rendered = render_report(build_report(narrative, store))
    surfaced = rendered.replace(
        "records kind DEVIATION",
        "records kind DEVIATION with probability 0.137",
        1,
    )
    with pytest.raises(ReportCheckError, match="confidence"):
        check_rendered_report(surfaced, store)


def test_missing_residual_is_refused() -> None:
    """A narrative that drops insufficient_evidence is not given a report."""
    template = next(
        item for item in _TEMPLATES if item.template_id == SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID
    )
    domain = template.domain
    evidence = _evidence("ev_primary", domain=domain, summary="Pump speed left its expected range")
    lead = _hypothesis_from(template, supporting=[evidence.id])
    narrative = Narrative(
        id="nar_story",
        title="UNCITED HEADLINE",
        domain=domain,
        hypothesis_ids=[lead.id],
        evidence_ids=[evidence.id],
    )
    store = InMemoryEvidenceStore()
    store.add_evidence(evidence)
    store.add_hypothesis(lead)
    store.add_narrative(narrative)
    with pytest.raises(ReportRefusedError, match="insufficient_evidence"):
        build_report(narrative, store)


def test_narrative_without_evidence_is_refused() -> None:
    """With no evidence id to cite, the report refuses rather than writing an empty claim."""
    residual = insufficient_evidence_template(Domain.ATLAS).instantiate()
    narrative = Narrative(
        id="nar_story",
        title="UNCITED HEADLINE",
        domain=Domain.ATLAS,
        hypothesis_ids=[residual.id],
        evidence_ids=[],
    )
    store = InMemoryEvidenceStore()
    store.add_hypothesis(residual)
    store.add_narrative(narrative)
    with pytest.raises(ReportRefusedError, match="no evidence"):
        build_report(narrative, store)


def test_missing_hypothesis_is_a_traceability_failure() -> None:
    """A narrative that names a hypothesis the store lacks is not rendered as silence."""
    evidence = _evidence(
        "ev_primary",
        domain=Domain.ATLAS,
        summary="Pump speed left its expected range",
    )
    narrative = Narrative(
        id="nar_story",
        title="UNCITED HEADLINE",
        domain=Domain.ATLAS,
        hypothesis_ids=["hyp_missing"],
        evidence_ids=[evidence.id],
    )
    store = InMemoryEvidenceStore()
    store.add_evidence(evidence)
    with pytest.raises(KeyError):
        build_report(narrative, store)


def test_summary_clauses_and_decimals_stay_faithful() -> None:
    """Each stored clause is cited, and a decimal point is not treated as a second sentence."""
    template = next(
        item for item in _TEMPLATES if item.template_id == SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID
    )
    narrative, store = _store_story(
        template,
        summary="Pump speed left its expected range. It did not return",
    )
    rendered = render_report(build_report(narrative, store))
    assert "Pump speed left its expected range" in rendered
    assert "It did not return" in rendered
    assert rendered.count("ev_primary") >= 2

    decimal_narrative, decimal_store = _store_story(
        template,
        summary="Pump speed read 1.5. It stayed out",
    )
    decimal_rendered = render_report(build_report(decimal_narrative, decimal_store))
    check_rendered_report(decimal_rendered, decimal_store)
    assert "Pump speed read 1.5" in decimal_rendered
    assert "It stayed out" in decimal_rendered


def test_summary_that_smuggles_an_evidence_token_is_refused() -> None:
    """A summary that already contains an evidence token is not wrapped into a citation."""
    template = next(
        item for item in _TEMPLATES if item.template_id == SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID
    )
    narrative, store = _store_story(template, summary="see ev_other for the reading")
    with pytest.raises(ReportRefusedError, match="evidence-id token"):
        build_report(narrative, store)


def test_contradictory_evidence_and_causal_edges_are_cited() -> None:
    """Supporting, contradictory, and a stored causal edge each appear with their evidence id."""
    template = next(
        item for item in _TEMPLATES if item.template_id == UNAUTHORISED_CONTROL_TEMPLATE_ID
    )
    narrative, store = _store_story(
        template,
        extra_summary="A work order covers the same unit",
        facet=(FacetKind.GRAPH_FINDING, "unexpected_command_function"),
        causal=True,
    )
    report = build_report(narrative, store)
    early = _stage_text(report, ReportStageId.NIS2_EARLY_WARNING_24H)
    full = _stage_text(report, ReportStageId.NIS2_INCIDENT_NOTIFICATION_72H)
    assert "supporting evidence ev_primary" in early
    assert "contradictory evidence ev_extra" in early
    assert "causal edge" not in early
    assert "source_id" not in early
    assert "causal edge from evidence ev_primary" in full
    assert "source_id source_reading" in full
    assert "facet_kind GRAPH_FINDING" in full
    assert "facet unexpected_command_function" in full
    severity = next(
        status
        for prompt, status in report.stages[1].prompts
        if prompt is StatutoryPrompt.SEVERITY_AND_IMPACT
    )
    early_severity = next(
        status
        for prompt, status in report.stages[0].prompts
        if prompt is StatutoryPrompt.SEVERITY_AND_IMPACT
    )
    assert severity is PromptStatus.NOT_IN_STORE
    assert early_severity is PromptStatus.NOT_THIS_STAGE


def test_unstored_or_mutated_narrative_is_refused() -> None:
    """The report quotes the stored narrative, not a lookalike with the same ids."""
    template = next(
        item for item in _TEMPLATES if item.template_id == SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID
    )
    narrative, store = _store_story(template)
    other = Narrative(
        id="nar_other",
        title="UNCITED HEADLINE",
        domain=narrative.domain,
        hypothesis_ids=list(narrative.hypothesis_ids),
        evidence_ids=list(narrative.evidence_ids),
    )
    with pytest.raises(KeyError):
        build_report(other, store)
    changed = narrative.model_copy(update={"title": "A different headline"})
    with pytest.raises(ReportRefusedError, match="does not match"):
        build_report(changed, store)


def test_empty_source_is_quoted_as_empty() -> None:
    """An empty source id is reported as empty rather than filled in."""
    template = next(
        item for item in _TEMPLATES if item.template_id == SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID
    )
    narrative, store = _store_story(template, source_id="")
    rendered = render_report(build_report(narrative, store))
    assert "source_id empty" in rendered


def test_a_line_break_in_a_summary_is_refused() -> None:
    """A summary that is already two lines is not glued into one citation."""
    template = next(
        item for item in _TEMPLATES if item.template_id == SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID
    )
    narrative, store = _store_story(template, summary="line one\nline two")
    with pytest.raises(ReportRefusedError, match="line break"):
        build_report(narrative, store)


def test_an_evidence_id_outside_the_prefix_is_refused() -> None:
    """Citations are evidence ids. A bare word is not given a sentence."""
    evidence = _evidence(
        "primary",
        domain=Domain.ATLAS,
        summary="Pump speed left its expected range",
    )
    residual = insufficient_evidence_template(Domain.ATLAS).instantiate()
    lead = Hypothesis(
        id="hyp_lead",
        label="A sensor or device on this unit has failed",
        template_id=SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID,
        domain=Domain.ATLAS,
        prior=PRIOR,
        confidence=CONFIDENCE,
        status=HypothesisStatus.ACTIVE,
        supporting=[evidence.id],
    )
    narrative = Narrative(
        id="nar_story",
        title="UNCITED HEADLINE",
        domain=Domain.ATLAS,
        hypothesis_ids=[lead.id, residual.id],
        evidence_ids=[evidence.id],
    )
    store = InMemoryEvidenceStore()
    store.add_evidence(evidence)
    store.add_hypothesis(lead)
    store.add_hypothesis(residual)
    store.add_narrative(narrative)
    with pytest.raises(ReportRefusedError, match="not an evidence id"):
        build_report(narrative, store)


def test_checker_rejects_a_filled_statutory_prompt_and_a_blank_line() -> None:
    """Metadata cannot answer a statutory question, and a blank line is not skipped."""
    template = next(
        item for item in _TEMPLATES if item.template_id == SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID
    )
    narrative, store = _store_story(template)
    rendered = render_report(build_report(narrative, store))
    filled = rendered.replace(
        "unlawful_or_malicious_suspected=not_asserted",
        "unlawful_or_malicious_suspected=yes",
        1,
    )
    with pytest.raises(ReportCheckError, match="unlawful_or_malicious_suspected"):
        check_rendered_report(filled, store)
    with pytest.raises(ReportCheckError, match="blank line"):
        check_rendered_report(rendered.replace("\n", "\n\n", 1), store)


def test_citation_list_must_match_the_sentence() -> None:
    """The evidence ids on the sentence object are the ids the text shows."""
    with pytest.raises(ValidationError, match="citation list"):
        CitedSentence(
            text="Stored evidence ev_primary records the reading.",
            evidence_ids=("ev_other",),
        )


def test_dropping_the_residual_from_the_model_is_rejected() -> None:
    """The report object itself refuses to hide insufficient_evidence."""
    template = next(
        item for item in _TEMPLATES if item.template_id == SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID
    )
    narrative, store = _store_story(template)
    report = build_report(narrative, store)
    dumped = report.model_dump()
    dumped["incident_types"] = [SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID]
    with pytest.raises(ValidationError, match="insufficient_evidence"):
        EvidenceGradeReport.model_validate(dumped)
    broken = report.model_copy(update={"incident_types": (SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID,)})
    with pytest.raises(ReportCheckError, match="incident types"):
        check_report(broken, store)

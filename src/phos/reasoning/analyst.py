"""Plain-English rendering of an existing narrative — Usefulness Phase item U4.

This is **not** Ω3. It is not FastAPI, not React, and not ``src/phos/api/`` or ``ui/``. It takes a
`Narrative` the ontology already holds, the store that can reconstruct its evidence and hypotheses,
and the template library those hypotheses came from, and prints what an operator can act on without
reading a probability.

Four properties, from the usefulness roadmap:

1. Lead with a plain-English summary and the evidence behind it.
2. State an assessment, including **unresolved** when the evidence cannot distinguish explanations.
3. Name the single most useful next piece of evidence — a specific fact, not a vague ask.
4. Put the full competing-hypothesis reasoning behind an explicit "why".

**The operator must not have to read probabilities to act.** Hypothesis ``confidence`` and
``prior`` are used internally to decide whether the lead is unique (via `tied_lead_ids` and
`prior_only_rivals`); they never appear in the rendered text.

**Gate 2 binding condition.** When the narrative's domain is Sentiel, the rendered output itself
documents the known depth-blind ceiling via `phos.sentiel.failure.depth_blind_ceiling_notice`.

**What this module does not invent.** It does not add fields to `Narrative`. Assessment and the
next settling fact are derived at render time from the hypotheses already on the narrative and the
patterns the templates already declare (`phos.reasoning.analyst_settling`). If those patterns
cannot name a discriminating fact, the renderer says so rather than guessing.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from enum import Enum

from pydantic import BaseModel, ConfigDict

from phos.ontology import (
    Domain,
    Evidence,
    EvidenceStore,
    Hypothesis,
    Narrative,
)
from phos.reasoning.analyst_settling import describe_pattern, settling_fact
from phos.reasoning.belief import prior_only_rivals, tied_lead_ids
from phos.reasoning.templates import (
    INSUFFICIENT_EVIDENCE_TEMPLATE_ID,
    TemplateLibrary,
)

__all__ = [
    "Assessment",
    "CompetingExplanation",
    "NarrativeBrief",
    "assess_narrative",
    "describe_pattern",
    "render_narrative_markdown",
    "settling_fact",
]


class Assessment(str, Enum):
    """Whether the evidence on this narrative can settle on one contentful explanation.

    ``str``-backed so the brief serialises readably. ``UNRESOLVED`` is a first-class answer, not a
    failure state — Constitution §3 and ADR 0036 both treat silence as honourable.
    """

    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"


class CompetingExplanation(BaseModel):
    """One explanation as an operator reads it: label, and the evidence for and against it.

    No confidence, no prior. The lists are the summaries already stored on each `Evidence`.
    """

    model_config = ConfigDict(frozen=True)

    label: str
    template_id: str
    is_residual: bool = False
    supporting: tuple[str, ...] = ()
    contradictory: tuple[str, ...] = ()


class NarrativeBrief(BaseModel):
    """Everything U4 needs to print, derived from an existing narrative and nothing else.

    Attributes:
        summary: Plain-English lead: what happened, in one short paragraph.
        assessment: ``resolved`` or ``unresolved``.
        assessment_line: The assessment written so an operator can act without a probability.
        evidence: Evidence summaries in timeline order.
        explanations: The competing set, residual included, in the narrative's own order.
        next_evidence: The single most useful next fact, named specifically — or an explicit
            statement that the templates declare none.
        ranking_limit: Sentiel depth-blind ceiling prose when the domain is Sentiel; ``None``
            otherwise. Present in the brief so a reader of the structure (not only the markdown)
            sees the limit.
        domain: Which engine produced the narrative.
        narrative_id: Traceability back to the ontology object.
    """

    model_config = ConfigDict(frozen=True)

    summary: str
    assessment: Assessment
    assessment_line: str
    evidence: tuple[str, ...]
    explanations: tuple[CompetingExplanation, ...]
    next_evidence: str
    ranking_limit: str | None = None
    domain: Domain
    narrative_id: str


def assess_narrative(
    narrative: Narrative,
    store: EvidenceStore,
    library: TemplateLibrary,
    *,
    ranking_limit: str | None = None,
) -> NarrativeBrief:
    """Derive a `NarrativeBrief` from an existing narrative.

    Args:
        narrative: The story to render. Must already cite hypotheses and evidence the store holds.
        store: The ontology store. Traceability failure raises rather than skipping.
        library: The template library those hypotheses came from. Needed to name a settling fact
            from declared pattern asymmetries; without it the renderer cannot invent one.
        ranking_limit: Optional override for the Sentiel ceiling paragraph. When omitted and the
            domain is Sentiel, the paragraph is built from `depth_blind_ceiling_notice`.

    Returns:
        A brief an operator can act on. Never contains a confidence or prior figure.

    Raises:
        KeyError: If a cited hypothesis or evidence id is missing from ``store``.
        ValueError: If the narrative cites no hypotheses.
    """
    hypotheses = _hypotheses_of(narrative, store)
    if not hypotheses:
        raise ValueError(
            f"narrative {narrative.id!r} cites no hypotheses; a story with nothing to assess "
            "cannot be rendered honestly"
        )

    evidence = narrative.timeline(store)
    evidence_by_id = {item.id: item for item in evidence}
    entities = {entity.id: entity for entity in store.entities()}

    tied = tied_lead_ids(hypotheses)
    prior_only = prior_only_rivals(hypotheses)
    leader = hypotheses[0]
    residual_leads = leader.template_id == INSUFFICIENT_EVIDENCE_TEMPLATE_ID
    unresolved = residual_leads or bool(tied) or prior_only

    assessment = Assessment.UNRESOLVED if unresolved else Assessment.RESOLVED
    rivals = _rivals_for_settling(hypotheses, tied=tied, prior_only=prior_only)
    next_fact = settling_fact(
        rivals,
        library,
        already_present=evidence,
        entities=entities,
    )
    assessment_line = _assessment_line(
        assessment=assessment,
        leader=leader,
        rivals=rivals,
        tied=tied,
        prior_only=prior_only,
    )
    limit = ranking_limit
    if limit is None and narrative.domain is Domain.SENTIEL:
        from phos.sentiel.failure import depth_blind_ceiling_notice

        limit = depth_blind_ceiling_notice()

    return NarrativeBrief(
        summary=_summary(narrative, evidence, assessment=assessment, leader=leader, rivals=rivals),
        assessment=assessment,
        assessment_line=assessment_line,
        evidence=tuple(item.summary for item in evidence),
        explanations=tuple(_explanation(item, evidence_by_id) for item in hypotheses),
        next_evidence=next_fact,
        ranking_limit=limit,
        domain=narrative.domain,
        narrative_id=narrative.id,
    )


def render_narrative_markdown(brief: NarrativeBrief) -> str:
    """Render a `NarrativeBrief` as crude, functional markdown.

    The lead is the summary. Assessment and next evidence follow immediately. The competing set
    sits under an explicit "Why" heading. Sentiel's depth-blind ceiling, when present, is its own
    section so a reader cannot miss what the ranking cannot see.
    """
    lines = [
        f"# {brief.summary.splitlines()[0]}",
        "",
        brief.summary,
        "",
        "## Assessment",
        "",
        brief.assessment_line,
        "",
        "## What would settle this",
        "",
        brief.next_evidence,
        "",
        "## Evidence",
        "",
    ]
    if brief.evidence:
        for index, summary in enumerate(brief.evidence, start=1):
            lines.append(f"{index}. {summary}")
    else:
        lines.append("None on this narrative.")
    lines.extend(["", "## Why", ""])
    for explanation in brief.explanations:
        tag = " (residual)" if explanation.is_residual else ""
        lines.append(f"### {explanation.label}{tag}")
        lines.append("")
        if explanation.supporting:
            lines.append("Supports this explanation:")
            for summary in explanation.supporting:
                lines.append(f"- {summary}")
        else:
            lines.append("No supporting evidence attached.")
        lines.append("")
        if explanation.contradictory:
            lines.append("Argues against this explanation:")
            for summary in explanation.contradictory:
                lines.append(f"- {summary}")
        else:
            lines.append("No contradictory evidence attached.")
        lines.append("")
    if brief.ranking_limit is not None:
        lines.extend(
            [
                "## Known limit of this ranking",
                "",
                brief.ranking_limit,
                "",
            ]
        )
    lines.extend(
        [
            "---",
            "",
            f"Narrative `{brief.narrative_id}` · domain `{brief.domain.value}` · "
            f"assessment `{brief.assessment.value}`.",
            "Hypothesis confidence is uncalibrated and is not shown (Constitution §3.3).",
            "",
        ]
    )
    return "\n".join(lines)


def _hypotheses_of(narrative: Narrative, store: EvidenceStore) -> list[Hypothesis]:
    """Resolve every hypothesis the narrative cites, preserving its order."""
    resolved: list[Hypothesis] = []
    for hypothesis_id in narrative.hypothesis_ids:
        hypothesis = store.get_hypothesis(hypothesis_id)
        if hypothesis is None:
            raise KeyError(hypothesis_id)
        resolved.append(hypothesis)
    return resolved


def _explanation(
    hypothesis: Hypothesis, evidence_by_id: Mapping[str, Evidence]
) -> CompetingExplanation:
    """Project one hypothesis into operator-facing lists of evidence summaries."""
    supporting = tuple(
        evidence_by_id[evidence_id].summary
        for evidence_id in hypothesis.supporting
        if evidence_id in evidence_by_id
    )
    contradictory = tuple(
        evidence_by_id[evidence_id].summary
        for evidence_id in hypothesis.contradictory
        if evidence_id in evidence_by_id
    )
    missing_support = tuple(
        f"(evidence {evidence_id} cited but not on this narrative)"
        for evidence_id in hypothesis.supporting
        if evidence_id not in evidence_by_id
    )
    missing_contradict = tuple(
        f"(evidence {evidence_id} cited but not on this narrative)"
        for evidence_id in hypothesis.contradictory
        if evidence_id not in evidence_by_id
    )
    return CompetingExplanation(
        label=hypothesis.label,
        template_id=hypothesis.template_id,
        is_residual=hypothesis.template_id == INSUFFICIENT_EVIDENCE_TEMPLATE_ID,
        supporting=supporting + missing_support,
        contradictory=contradictory + missing_contradict,
    )


def _rivals_for_settling(
    hypotheses: Sequence[Hypothesis],
    *,
    tied: tuple[str, ...],
    prior_only: bool,
) -> list[Hypothesis]:
    """Return the contentful explanations the next fact must split."""
    contentful = [
        item for item in hypotheses if item.template_id != INSUFFICIENT_EVIDENCE_TEMPLATE_ID
    ]
    if tied:
        tied_set = set(tied)
        return [item for item in contentful if item.template_id in tied_set]
    if prior_only and len(contentful) >= 2:
        from phos.reasoning.belief import evidence_fingerprint

        ordered = sorted(contentful, key=lambda item: (-item.confidence, item.template_id))
        leader = ordered[0]
        fingerprint = evidence_fingerprint(leader)
        return [item for item in ordered if evidence_fingerprint(item) == fingerprint]
    if (
        hypotheses
        and hypotheses[0].template_id == INSUFFICIENT_EVIDENCE_TEMPLATE_ID
        and len(contentful) >= 2
    ):
        return list(contentful[:2])
    if contentful:
        return [contentful[0]]
    return []


def _assessment_line(
    *,
    assessment: Assessment,
    leader: Hypothesis,
    rivals: Sequence[Hypothesis],
    tied: tuple[str, ...],
    prior_only: bool,
) -> str:
    """Write the assessment so an operator can act without a probability."""
    if assessment is Assessment.RESOLVED:
        return f"Assessment: {leader.label}."
    if prior_only:
        labels = " / ".join(item.label for item in rivals) or leader.label
        return (
            f"Assessment: unresolved. The explanations “{labels}” carry the same evidence; "
            "only their written priors would separate them, and a prior is not knowledge."
        )
    if tied or len(rivals) >= 2:
        labels = " / ".join(item.label for item in rivals)
        return f"Assessment: unresolved. The evidence cannot distinguish: {labels}."
    if leader.template_id == INSUFFICIENT_EVIDENCE_TEMPLATE_ID:
        return (
            "Assessment: unresolved. The residual leads — the evidence on this narrative does "
            "not yet support a contentful explanation over silence."
        )
    return "Assessment: unresolved."


def _summary(
    narrative: Narrative,
    evidence: Sequence[Evidence],
    *,
    assessment: Assessment,
    leader: Hypothesis,
    rivals: Sequence[Hypothesis],
) -> str:
    """Build the plain-English lead paragraph from the narrative's own parts."""
    if evidence:
        lead_fact = evidence[0].summary
        if len(evidence) == 1:
            what = f"One fact is on the table: {lead_fact}."
        else:
            what = f"{len(evidence)} facts are on the table, beginning with: {lead_fact}."
    else:
        what = "No evidence is on this narrative yet."

    if assessment is Assessment.RESOLVED:
        stance = f"The assessment is: {leader.label}."
    elif len(rivals) >= 2:
        labels = " / ".join(item.label for item in rivals)
        stance = f"The assessment is unresolved between: {labels}."
    else:
        stance = "The assessment is unresolved."

    title = narrative.title.strip()
    if title and not title.lower().startswith("insufficient"):
        return f"{title}. {what} {stance}"
    return f"{what} {stance}"

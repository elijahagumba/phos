"""Evidence-grade incident reports rendered only from stored narratives.

This is not open-ended writing and not a regulatory filing. A `Narrative` already holds
evidence ids, hypothesis template ids, and the labels those templates stored. This module
copies those fields into sentences for two clocks:

- NIS2 early warning (24 hours) and incident notification (72 hours), Directive (EU)
  2022/2555 Article 23(4)(a) and (b).
- The UK Cyber Security and Resilience Bill's announced initial notification (24 hours)
  and fuller report (72 hours). The November 2025 announcement named the clocks. This
  module does not invent a content schedule the ontology does not hold.

An incident type is the ``template_id`` already stored on a hypothesis. The ontology has
no incident-type enum. ``insufficient_evidence`` stays in the competing set. Hypothesis
``confidence``, ``prior``, and `Narrative.overall_confidence` are not rendered: they are
not calibrated probabilities (Constitution §3.3).

The checker fails closed. A sentence is one line with a single terminating period. It must
cite an evidence id the store holds for this narrative. Metadata lines are a fixed
allowlist, so a free-text claim cannot hide in a header.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import UTC
from enum import Enum
from typing import Literal, NamedTuple, Self, assert_never

from pydantic import BaseModel, ConfigDict, Field, model_validator

from phos.ontology import Domain, Evidence, EvidenceStore, Hypothesis, Narrative
from phos.reasoning.templates import INSUFFICIENT_EVIDENCE_TEMPLATE_ID

__all__ = [
    "CitedSentence",
    "EvidenceGradeReport",
    "PromptStatus",
    "ReportCheckError",
    "ReportRefusedError",
    "ReportStage",
    "ReportStageId",
    "StatutoryPrompt",
    "build_report",
    "check_rendered_report",
    "check_report",
    "check_sentence",
    "render_report",
]

_EVIDENCE_TOKEN = re.compile(r"(?<![A-Za-z0-9_])ev_[0-9A-Za-z]+")
_DECIMAL_POINT = re.compile(r"(?<=\d)\.(?=\d)")
_TOKEN = re.compile(r"[A-Za-z0-9_\-]+")
_META_LINE = re.compile(r"^[a-z0-9_]+=[A-Za-z0-9_,\-]+$")
_TEMPLATE_TOKEN = re.compile(r"(?<![A-Za-z0-9_]){token}(?![A-Za-z0-9_])")


class ReportStageId(str, Enum):
    """Which notification clock a block of cited sentences is for.

    NIS2 names are Article 23(4)(a) and (b). The UK names are the two clocks announced
    with the Cyber Security and Resilience Bill in November 2025. They are document
    structure, not a claim that an enacted instrument was read in this session.
    """

    NIS2_EARLY_WARNING_24H = "nis2_early_warning_24h"
    NIS2_INCIDENT_NOTIFICATION_72H = "nis2_incident_notification_72h"
    UK_CSR_INITIAL_24H = "uk_csr_initial_24h"
    UK_CSR_FULL_72H = "uk_csr_full_72h"


class StatutoryPrompt(str, Enum):
    """A question a notification stage asks, answered only with a stored status."""

    UNLAWFUL_OR_MALICIOUS = "unlawful_or_malicious_suspected"
    CROSS_BORDER_IMPACT = "cross_border_impact"
    SEVERITY_AND_IMPACT = "severity_and_impact"
    INDICATORS_OF_COMPROMISE = "indicators_of_compromise"


class PromptStatus(str, Enum):
    """The only answers this module will give to a statutory prompt.

    ``NOT_ASSERTED`` is a suspicion PHOS will not draw from an uncalibrated hypothesis.
    ``NOT_IN_STORE`` means the ontology has no such fact. ``NOT_THIS_STAGE`` means this
    clock does not ask the question.
    """

    NOT_ASSERTED = "not_asserted"
    NOT_IN_STORE = "not_in_store"
    NOT_THIS_STAGE = "not_this_stage"


STAGE_ORDER: tuple[ReportStageId, ...] = (
    ReportStageId.NIS2_EARLY_WARNING_24H,
    ReportStageId.NIS2_INCIDENT_NOTIFICATION_72H,
    ReportStageId.UK_CSR_INITIAL_24H,
    ReportStageId.UK_CSR_FULL_72H,
)
"""The four stages, in the order a rendered report must carry them."""


class ReportRefusedError(ValueError):
    """The narrative cannot be reported without inventing a fact or hiding the residual."""


class ReportCheckError(ValueError):
    """A sentence lacks an evidence id, cites unknown evidence, or surfaces a confidence."""


def deadline_for(stage: ReportStageId) -> Literal[24, 72]:
    """Return the clock, in hours, that ``stage`` is named for.

    Args:
        stage: A notification stage.

    Returns:
        24 for an early or initial notification, 72 for the follow-up notification.
    """
    if stage is ReportStageId.NIS2_EARLY_WARNING_24H or stage is ReportStageId.UK_CSR_INITIAL_24H:
        return 24
    if (
        stage is ReportStageId.NIS2_INCIDENT_NOTIFICATION_72H
        or stage is ReportStageId.UK_CSR_FULL_72H
    ):
        return 72
    assert_never(stage)


def prompts_for(stage: ReportStageId) -> tuple[tuple[StatutoryPrompt, PromptStatus], ...]:
    """Return the statutory prompts for ``stage`` and the only status each may carry.

    The 24-hour clocks ask whether unlawful or malicious acts are suspected and whether
    cross-border impact is known. The 72-hour clocks add severity, impact, and indicators
    of compromise. Malice is never asserted from hypothesis confidence. Anything the store
    does not hold stays ``not_in_store``. The UK stage on the same clock uses the same
    prompts, because the ontology has no UK-only fact and this module will not invent one.

    Args:
        stage: A notification stage.

    Returns:
        Prompt and status pairs in render order.
    """
    early: tuple[tuple[StatutoryPrompt, PromptStatus], ...] = (
        (StatutoryPrompt.UNLAWFUL_OR_MALICIOUS, PromptStatus.NOT_ASSERTED),
        (StatutoryPrompt.CROSS_BORDER_IMPACT, PromptStatus.NOT_IN_STORE),
        (StatutoryPrompt.SEVERITY_AND_IMPACT, PromptStatus.NOT_THIS_STAGE),
        (StatutoryPrompt.INDICATORS_OF_COMPROMISE, PromptStatus.NOT_THIS_STAGE),
    )
    full: tuple[tuple[StatutoryPrompt, PromptStatus], ...] = (
        (StatutoryPrompt.UNLAWFUL_OR_MALICIOUS, PromptStatus.NOT_ASSERTED),
        (StatutoryPrompt.CROSS_BORDER_IMPACT, PromptStatus.NOT_IN_STORE),
        (StatutoryPrompt.SEVERITY_AND_IMPACT, PromptStatus.NOT_IN_STORE),
        (StatutoryPrompt.INDICATORS_OF_COMPROMISE, PromptStatus.NOT_IN_STORE),
    )
    if stage is ReportStageId.NIS2_EARLY_WARNING_24H or stage is ReportStageId.UK_CSR_INITIAL_24H:
        return early
    if (
        stage is ReportStageId.NIS2_INCIDENT_NOTIFICATION_72H
        or stage is ReportStageId.UK_CSR_FULL_72H
    ):
        return full
    assert_never(stage)


def _evidence_tokens(text: str) -> tuple[str, ...]:
    """Return evidence ids in ``text``, in the order they appear."""
    return tuple(_EVIDENCE_TOKEN.findall(text))


def _mask_decimals(text: str) -> str:
    """Replace decimal points so a later split does not treat ``1.5`` as two sentences."""
    return _DECIMAL_POINT.sub("\x00", text)


def _unmask_decimals(text: str) -> str:
    """Restore decimal points hidden by `_mask_decimals`."""
    return text.replace("\x00", ".")


def _is_one_sentence(text: str) -> bool:
    """Return whether ``text`` is one sentence ending in a single period.

    A period between digits is a decimal point, not a second sentence. The terminating
    period still counts when the sentence ends on a number, as in ``read 1.5.``.
    """
    if not text or any(mark in text for mark in "\n\r!?"):
        return False
    if not text.endswith("."):
        return False
    return "." not in _mask_decimals(text[:-1])


def _require_token(value: str, what: str) -> str:
    """Return ``value`` when it cannot break a sentence or a metadata line.

    Args:
        value: The stored string to interpolate.
        what: Name of the field, used in the refusal.

    Returns:
        ``value`` unchanged.

    Raises:
        ReportRefusedError: If ``value`` contains whitespace or punctuation.
    """
    if _TOKEN.fullmatch(value) is None:
        raise ReportRefusedError(f"{what} is not a single token: {value!r}")
    return value


def _require_evidence_id(value: str, what: str) -> str:
    """Return ``value`` when it is an evidence id token.

    Args:
        value: A stored evidence id.
        what: Name of the field, used in the refusal.

    Returns:
        ``value`` unchanged.

    Raises:
        ReportRefusedError: If ``value`` is not an ``ev_`` token.
    """
    _require_token(value, what)
    if _EVIDENCE_TOKEN.fullmatch(value) is None:
        raise ReportRefusedError(f"{what} is not an evidence id: {value!r}")
    return value


def _clauses(text: str, what: str) -> tuple[str, ...]:
    """Split stored prose into clauses a single cited sentence can quote.

    A period between digits stays inside the clause, so ``1.5`` is not two sentences.
    Any other period, exclamation mark, or question mark is a break. Each clause is
    later cited with the same evidence id. A clause is never rewritten.

    Args:
        text: Stored prose, such as an evidence summary or a hypothesis label.
        what: Name of the field, used in the refusal.

    Returns:
        The clauses, in order, with surrounding whitespace removed.

    Raises:
        ReportRefusedError: If ``text`` contains a line break, already contains an evidence
            id, or has no citable text.
    """
    if "\n" in text or "\r" in text or "\x00" in text:
        raise ReportRefusedError(f"{what} contains a line break")
    if _EVIDENCE_TOKEN.search(text):
        raise ReportRefusedError(f"{what} contains an evidence-id token")
    parts = re.split(r"[.!?]+", _mask_decimals(text))
    clauses = tuple(_unmask_decimals(part).strip() for part in parts if part.strip())
    if not clauses:
        raise ReportRefusedError(f"{what} has no citable text")
    return clauses


class CitedSentence(BaseModel):
    """One sentence whose citation list is exactly the evidence ids in the text.

    Attributes:
        text: The sentence, including its terminating period.
        evidence_ids: Evidence ids the sentence cites, each of which appears in ``text``.
    """

    model_config = ConfigDict(frozen=True)

    text: str = Field(min_length=1)
    evidence_ids: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _citation_list_matches_the_text(self) -> Self:
        """Refuse a sentence whose citation list is not the evidence ids it shows."""
        if not _is_one_sentence(self.text):
            raise ValueError("a cited sentence has exactly one period, at the end")
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("duplicate evidence ids on one sentence")
        if set(_evidence_tokens(self.text)) != set(self.evidence_ids):
            raise ValueError("evidence ids in the text and the citation list differ")
        return self


class ReportStage(BaseModel):
    """One notification stage: its clock, its prompts, and its cited sentences.

    Attributes:
        stage: Which clock this block is.
        deadline_hours: 24 or 72, matching ``stage``.
        prompts: Statutory questions and the only statuses this module allows.
        sentences: The cited sentences for this stage. The 72-hour stages repeat the
            24-hour sentences and then add source, facet, and causal-edge sentences.
    """

    model_config = ConfigDict(frozen=True)

    stage: ReportStageId
    deadline_hours: Literal[24, 72]
    prompts: tuple[tuple[StatutoryPrompt, PromptStatus], ...]
    sentences: tuple[CitedSentence, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _matches_the_stage_contract(self) -> Self:
        """Refuse a stage whose clock or prompts disagree with the closed map."""
        if self.deadline_hours != deadline_for(self.stage):
            expected = deadline_for(self.stage)
            raise ValueError(
                f"{self.stage.value} has deadline {self.deadline_hours}, not {expected}"
            )
        if self.prompts != prompts_for(self.stage):
            raise ValueError(f"{self.stage.value} prompts are not the closed map")
        return self


class EvidenceGradeReport(BaseModel):
    """A narrative rendered for the four notification stages.

    Attributes:
        narrative_id: The stored narrative this report quotes.
        domain: The narrative's domain.
        incident_types: Template ids of the stored hypotheses, in narrative order, with
            duplicates removed. ``insufficient_evidence`` is required.
        confidence_surfaced: Always false. The field exists so a reader of the object
            sees that confidence was withheld.
        overall_confidence: Always ``withheld``. `Narrative.overall_confidence` is not
            copied, even when a caller has set it.
        stages: The four stages, in `STAGE_ORDER`.
    """

    model_config = ConfigDict(frozen=True)

    narrative_id: str
    domain: Domain
    incident_types: tuple[str, ...] = Field(min_length=1)
    confidence_surfaced: Literal[False] = False
    overall_confidence: Literal["withheld"] = "withheld"
    stages: tuple[ReportStage, ...]

    @model_validator(mode="after")
    def _residual_stays_visible(self) -> Self:
        """Refuse a report that drops the residual or a stage."""
        if INSUFFICIENT_EVIDENCE_TEMPLATE_ID not in self.incident_types:
            raise ValueError("insufficient_evidence must stay visible on the report")
        if len(set(self.incident_types)) != len(self.incident_types):
            raise ValueError("duplicate incident types")
        stages = tuple(stage.stage for stage in self.stages)
        if stages != STAGE_ORDER:
            raise ValueError("stages must be the four notification clocks, in order")
        return self


def _cite(body: str, evidence_ids: tuple[str, ...]) -> CitedSentence:
    """Return one cited sentence whose body has no sentence break of its own.

    Args:
        body: The sentence without its terminating period.
        evidence_ids: Evidence ids that already appear in ``body``.

    Returns:
        A `CitedSentence`.

    Raises:
        ReportRefusedError: If ``body`` already contains a sentence break.
    """
    masked = _mask_decimals(body)
    if any(mark in masked for mark in ".!?\n\r"):
        raise ReportRefusedError(f"citation body is not a single clause: {body!r}")
    return CitedSentence(text=f"{body}.", evidence_ids=evidence_ids)


def _ids_or_none(evidence_ids: Sequence[str]) -> str:
    """Return a space-separated id list, or ``none`` when the list is empty."""
    if not evidence_ids:
        return "none"
    return " ".join(evidence_ids)


def _stamp(evidence: Evidence) -> str:
    """Return an evidence timestamp as UTC text with no decimal point."""
    return evidence.timestamp.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _evidence_sentences(evidence: Evidence) -> tuple[CitedSentence, ...]:
    """Return the identity sentence and one sentence per summary clause.

    Args:
        evidence: A stored fact.

    Returns:
        Cited sentences that quote ``evidence`` and nothing else.
    """
    evidence_id = _require_evidence_id(evidence.id, "evidence id")
    for entity_id in evidence.entity_ids:
        _require_token(entity_id, "entity id")
    entities = ",".join(evidence.entity_ids)
    head = (
        f"Stored evidence {evidence_id} at {_stamp(evidence)} records kind "
        f"{evidence.kind.value} on entities {entities}"
    )
    sentences = [_cite(head, (evidence_id,))]
    for clause in _clauses(evidence.summary, f"evidence {evidence_id} summary"):
        sentences.append(
            _cite(f"Stored evidence {evidence_id} summary states {clause}", (evidence_id,))
        )
    return tuple(sentences)


def _detail_sentence(evidence: Evidence) -> CitedSentence:
    """Return the 72-hour sentence for source, domain, and facet.

    Args:
        evidence: A stored fact whose id has already been checked.

    Returns:
        A cited sentence. An absent facet is the word ``none``, which is what the model stores.
    """
    evidence_id = _require_evidence_id(evidence.id, "evidence id")
    source = (
        "empty" if evidence.source_id == "" else _require_token(evidence.source_id, "source_id")
    )
    if evidence.facet_kind is None:
        facet_kind = "none"
    else:
        facet_kind = _require_token(evidence.facet_kind.value, "facet_kind")
    facet = "none" if evidence.facet is None else _require_token(evidence.facet, "facet")
    body = (
        f"Stored evidence {evidence_id} cites source_id {source} in domain "
        f"{evidence.domain.value} with facet_kind {facet_kind} and facet {facet}"
    )
    return _cite(body, (evidence_id,))


def _hypothesis_sentences(
    hypothesis: Hypothesis,
    narrative_evidence_ids: tuple[str, ...],
) -> tuple[CitedSentence, ...]:
    """Return cited sentences for one stored hypothesis.

    A hypothesis that lists evidence cites those ids. The residual lists none, so its
    sentence cites the narrative's evidence as facts it sits beside, not as support.

    Args:
        hypothesis: A stored explanation, residual included.
        narrative_evidence_ids: Evidence ids on the narrative, in timeline order.

    Returns:
        One sentence per label clause.

    Raises:
        ReportRefusedError: If a hypothesis with empty evidence lists has nothing on the
            narrative to cite.
    """
    _require_token(hypothesis.id, "hypothesis id")
    _require_token(hypothesis.template_id, "template id")
    clauses = _clauses(hypothesis.label, f"hypothesis {hypothesis.id} label")
    supporting = tuple(
        _require_evidence_id(item, "supporting evidence") for item in hypothesis.supporting
    )
    contradictory = tuple(
        _require_evidence_id(item, "contradictory evidence") for item in hypothesis.contradictory
    )
    if supporting or contradictory:
        cited = supporting + contradictory
        listing = (
            f"lists supporting evidence {_ids_or_none(supporting)} "
            f"and contradictory evidence {_ids_or_none(contradictory)}"
        )
    else:
        if not narrative_evidence_ids:
            raise ReportRefusedError(
                f"hypothesis {hypothesis.id} lists no evidence and the narrative cites no evidence"
            )
        cited = narrative_evidence_ids
        listing = (
            "lists supporting evidence none and contradictory evidence none "
            f"beside narrative evidence {_ids_or_none(narrative_evidence_ids)}"
        )
    sentences: list[CitedSentence] = []
    for index, clause in enumerate(clauses):
        if index == 0:
            body = (
                f"Stored hypothesis {hypothesis.id} uses template {hypothesis.template_id} "
                f"with label {clause} and {listing}"
            )
        else:
            body = (
                f"Stored hypothesis {hypothesis.id} label continues {clause} "
                f"citing evidence {_ids_or_none(cited)}"
            )
        sentences.append(_cite(body, cited))
    return tuple(sentences)


def _causal_sentences(
    narrative: Narrative,
    hypotheses: Sequence[Hypothesis],
) -> tuple[CitedSentence, ...]:
    """Return one cited sentence per stored causal edge.

    Args:
        narrative: The story whose edges are quoted.
        hypotheses: The hypotheses the narrative lists.

    Returns:
        Sentences in the narrative's edge order. Each cites the evidence end of the edge.

    Raises:
        ReportRefusedError: If an edge names an id the narrative does not list. The store
            already rejects that on write; the check is repeated so a report never skips
            a broken edge in silence.
    """
    _require_token(narrative.id, "narrative id")
    hypothesis_ids = {item.id for item in hypotheses}
    evidence_ids = set(narrative.evidence_ids)
    sentences: list[CitedSentence] = []
    for source, target in narrative.causal_edges:
        if source not in evidence_ids:
            raise ReportRefusedError(
                f"narrative {narrative.id} causal edge cites evidence {source} not on the narrative"
            )
        if target not in hypothesis_ids:
            raise ReportRefusedError(
                f"narrative {narrative.id} causal edge cites hypothesis {target} "
                "not on the narrative"
            )
        source_id = _require_evidence_id(source, "causal edge evidence")
        _require_token(target, "causal edge hypothesis")
        body = (
            f"Stored narrative {narrative.id} records a causal edge from evidence "
            f"{source_id} to hypothesis {target}"
        )
        sentences.append(_cite(body, (source_id,)))
    return tuple(sentences)


def _hypotheses(narrative: Narrative, store: EvidenceStore) -> tuple[Hypothesis, ...]:
    """Resolve the narrative's hypotheses in stored order.

    Args:
        narrative: The story whose hypothesis ids are resolved.
        store: The store that must hold each id.

    Returns:
        The stored hypotheses.

    Raises:
        KeyError: If an id is missing. A missing explanation is a traceability failure.
    """
    resolved: list[Hypothesis] = []
    for hypothesis_id in narrative.hypothesis_ids:
        hypothesis = store.get_hypothesis(hypothesis_id)
        if hypothesis is None:
            raise KeyError(hypothesis_id)
        resolved.append(hypothesis)
    return tuple(resolved)


def _collect_evidence(
    narrative: Narrative,
    hypotheses: Sequence[Hypothesis],
    store: EvidenceStore,
) -> tuple[Evidence, ...]:
    """Return the story's evidence, timeline first, then hypothesis-only ids.

    Args:
        narrative: The story.
        hypotheses: Its hypotheses, already resolved.
        store: The store `Narrative.timeline` reads.

    Returns:
        Each evidence id once, in first-seen order.

    Raises:
        KeyError: If a cited evidence id is missing.
    """
    ordered: list[Evidence] = []
    seen: set[str] = set()
    for item in narrative.timeline(store):
        if item.id in seen:
            continue
        seen.add(item.id)
        ordered.append(item)
    for hypothesis in hypotheses:
        for evidence_id in (*hypothesis.supporting, *hypothesis.contradictory):
            if evidence_id in seen:
                continue
            extra = store.get_evidence(evidence_id)
            if extra is None:
                raise KeyError(evidence_id)
            seen.add(evidence_id)
            ordered.append(extra)
    return tuple(ordered)


def _incident_types_of(hypotheses: Sequence[Hypothesis]) -> tuple[str, ...]:
    """Return template ids in hypothesis order, keeping the first copy of each."""
    seen: list[str] = []
    for hypothesis in hypotheses:
        if hypothesis.template_id not in seen:
            seen.append(hypothesis.template_id)
    return tuple(seen)


def _stage(stage: ReportStageId, sentences: tuple[CitedSentence, ...]) -> ReportStage:
    """Build one stage from the closed deadline and prompt maps."""
    return ReportStage(
        stage=stage,
        deadline_hours=deadline_for(stage),
        prompts=prompts_for(stage),
        sentences=sentences,
    )


def build_report(narrative: Narrative, store: EvidenceStore) -> EvidenceGradeReport:
    """Build an evidence-grade report from a stored narrative.

    The narrative must be the object ``store`` holds. Sentences quote evidence summaries,
    hypothesis labels, template ids, and stored roles. They do not add an attacker, an
    impact, or a probability. ``insufficient_evidence`` must already be one of the
    hypotheses. The returned report has passed `check_report`.

    Args:
        narrative: The incident story.
        store: The ontology store. Missing ids raise ``KeyError``.

    Returns:
        A report for the NIS2 and UK notification stages.

    Raises:
        KeyError: If the narrative, a hypothesis, or an evidence id is not in ``store``.
        ReportRefusedError: If the narrative has no evidence, hides ``insufficient_evidence``,
            does not match the stored object, or a stored string cannot be cited as one
            sentence without changing it.
        ReportCheckError: If the report just built fails its own checker.
    """
    hypotheses = _hypotheses(narrative, store)
    evidence = _collect_evidence(narrative, hypotheses, store)
    stored = store.get_narrative(narrative.id)
    if stored is None:
        raise KeyError(narrative.id)
    if stored != narrative:
        raise ReportRefusedError(f"narrative {narrative.id} does not match the stored record")
    if not any(
        hypothesis.template_id == INSUFFICIENT_EVIDENCE_TEMPLATE_ID for hypothesis in hypotheses
    ):
        raise ReportRefusedError(
            f"narrative {narrative.id} has no {INSUFFICIENT_EVIDENCE_TEMPLATE_ID} hypothesis"
        )
    if not narrative.evidence_ids or not evidence:
        raise ReportRefusedError(f"narrative {narrative.id} cites no evidence")

    on_narrative = set(narrative.evidence_ids)
    narrative_evidence_ids = tuple(item.id for item in evidence if item.id in on_narrative)
    core: list[CitedSentence] = []
    detail: list[CitedSentence] = []
    for item in evidence:
        core.extend(_evidence_sentences(item))
        detail.append(_detail_sentence(item))
    for hypothesis in hypotheses:
        core.extend(_hypothesis_sentences(hypothesis, narrative_evidence_ids))
    detail.extend(_causal_sentences(narrative, hypotheses))
    early = tuple(core)
    full = tuple(core + detail)
    report = EvidenceGradeReport(
        narrative_id=_require_token(narrative.id, "narrative id"),
        domain=narrative.domain,
        incident_types=_incident_types_of(hypotheses),
        stages=(
            _stage(ReportStageId.NIS2_EARLY_WARNING_24H, early),
            _stage(ReportStageId.NIS2_INCIDENT_NOTIFICATION_72H, full),
            _stage(ReportStageId.UK_CSR_INITIAL_24H, early),
            _stage(ReportStageId.UK_CSR_FULL_72H, full),
        ),
    )
    check_report(report, store)
    return report


def render_report(report: EvidenceGradeReport) -> str:
    """Render a report as metadata lines and one cited sentence per line.

    Metadata values are a closed set. Free text lives only in the sentences, which
    already carry evidence ids. The narrative title is omitted: it is not an evidence id.

    Args:
        report: A report, normally from `build_report`.

    Returns:
        The rendered report, ending in a newline.
    """
    lines = [
        f"narrative_id={report.narrative_id}",
        f"domain={report.domain.value}",
        f"incident_types={','.join(report.incident_types)}",
        "confidence_surfaced=false",
        "overall_confidence=withheld",
    ]
    for stage in report.stages:
        lines.append(f"stage={stage.stage.value}")
        lines.append(f"deadline_hours={stage.deadline_hours}")
        for prompt, status in stage.prompts:
            lines.append(f"{prompt.value}={status.value}")
        for sentence in stage.sentences:
            lines.append(sentence.text)
    return "\n".join(lines) + "\n"


class _ParsedStage(NamedTuple):
    """One stage as read back from rendered text."""

    stage: ReportStageId
    deadline_hours: int
    prompts: tuple[tuple[StatutoryPrompt, PromptStatus], ...]
    sentences: tuple[str, ...]


class _ParsedReport(NamedTuple):
    """A rendered report, split into the header and the four stages."""

    narrative_id: str
    domain: str
    incident_types: tuple[str, ...]
    stages: tuple[_ParsedStage, ...]


def _rendered_lines(text: str) -> list[str]:
    """Return the rendered lines, refusing blanks and a missing trailing newline."""
    if not text.endswith("\n"):
        raise ReportCheckError("rendered report does not end with a newline")
    lines = text.splitlines()
    if not lines:
        raise ReportCheckError("rendered report is empty")
    if any(line == "" for line in lines):
        raise ReportCheckError("blank line")
    return lines


def _take_meta(lines: Sequence[str], index: int, key: str) -> tuple[str, int]:
    """Return the value of the metadata line ``key`` at ``index``.

    Args:
        lines: Rendered lines.
        index: The line that must be ``key``.
        key: The required metadata key.

    Returns:
        The value and the index of the following line.

    Raises:
        ReportCheckError: If the line is missing, not metadata, or a different key.
    """
    if index >= len(lines):
        raise ReportCheckError(f"missing {key}")
    line = lines[index]
    if _META_LINE.fullmatch(line) is None:
        raise ReportCheckError(f"expected {key}, found a sentence or malformed line")
    found, value = line.split("=", 1)
    if found != key:
        raise ReportCheckError(f"expected {key}, found {found}")
    return value, index + 1


def _number_appears(text: str, value: float) -> bool:
    """Return whether ``value`` appears in ``text`` as a bounded decimal."""
    forms = {
        format(value, ".12g"),
        f"{value:.1f}",
        f"{value:.2f}",
        f"{value:.3f}",
        f"{value:.4f}",
        f"{value:.6f}",
        f"{value:.8f}",
    }
    return any(
        re.search(rf"(?<![0-9]){re.escape(form)}(?![0-9])", text) is not None for form in forms
    )


def _reject_surfaced_scores(
    text: str,
    hypotheses: Sequence[Hypothesis],
    overall: float | None,
) -> None:
    """Refuse text that contains a stored confidence, prior, or overall confidence.

    Args:
        text: A sentence or a whole report.
        hypotheses: The narrative's hypotheses, whose scores must stay off the page.
        overall: `Narrative.overall_confidence`, when set.

    Raises:
        ReportCheckError: If any of those numbers appears.
    """
    for hypothesis in hypotheses:
        for value in (hypothesis.confidence, hypothesis.prior):
            if _number_appears(text, value):
                raise ReportCheckError("uncalibrated confidence or prior was surfaced as a number")
    if overall is not None and _number_appears(text, overall):
        raise ReportCheckError("uncalibrated confidence or prior was surfaced as a number")


def check_sentence(text: str, store: EvidenceStore) -> None:
    """Reject one sentence that lacks a stored evidence id.

    Args:
        text: One sentence, including its terminating period.
        store: The store the citation must resolve in.

    Raises:
        ReportCheckError: If ``text`` is not a single sentence, contains no evidence id,
            or cites an id the store does not hold.
    """
    if not _is_one_sentence(text):
        raise ReportCheckError(f"not one cited sentence: {text!r}")
    evidence_ids = _evidence_tokens(text)
    if not evidence_ids:
        raise ReportCheckError(f"sentence has no evidence id: {text!r}")
    for evidence_id in evidence_ids:
        if store.get_evidence(evidence_id) is None:
            raise ReportCheckError(f"sentence cites unknown evidence {evidence_id}")


def _check_story_sentence(
    text: str,
    store: EvidenceStore,
    story_ids: set[str],
    hypotheses: Sequence[Hypothesis],
    overall: float | None,
) -> None:
    """Reject a sentence that is uncited, off-story, or carrying a confidence number."""
    check_sentence(text, store)
    for evidence_id in _evidence_tokens(text):
        if evidence_id not in story_ids:
            raise ReportCheckError(f"sentence cites evidence {evidence_id} outside this narrative")
    _reject_surfaced_scores(text, hypotheses, overall)


def _visible(template_id: str, text: str) -> bool:
    """Return whether ``template_id`` appears as its own token in ``text``."""
    pattern = _TEMPLATE_TOKEN.pattern.format(token=re.escape(template_id))
    return re.search(pattern, text) is not None


def _parse_and_check(text: str, store: EvidenceStore) -> _ParsedReport:
    """Parse rendered text and fail unless every sentence cites this narrative's evidence.

    Args:
        text: A rendered report.
        store: The store the narrative and its evidence must live in.

    Returns:
        The parsed header and stages.

    Raises:
        ReportCheckError: If a sentence lacks an evidence id, a prompt is filled in, the
            residual is hidden, or a confidence number appears.
    """
    lines = _rendered_lines(text)
    index = 0
    narrative_id, index = _take_meta(lines, index, "narrative_id")
    domain, index = _take_meta(lines, index, "domain")
    incident_types_raw, index = _take_meta(lines, index, "incident_types")
    confidence_surfaced, index = _take_meta(lines, index, "confidence_surfaced")
    overall_confidence, index = _take_meta(lines, index, "overall_confidence")
    if confidence_surfaced != "false":
        raise ReportCheckError("confidence_surfaced must be false")
    if overall_confidence != "withheld":
        raise ReportCheckError("overall_confidence must be withheld")

    narrative = store.get_narrative(narrative_id)
    if narrative is None:
        raise ReportCheckError(f"unknown narrative {narrative_id}")
    if domain != narrative.domain.value:
        raise ReportCheckError("domain does not match the stored narrative")

    hypotheses: list[Hypothesis] = []
    for hypothesis_id in narrative.hypothesis_ids:
        hypothesis = store.get_hypothesis(hypothesis_id)
        if hypothesis is None:
            raise ReportCheckError(f"narrative cites unknown hypothesis {hypothesis_id}")
        hypotheses.append(hypothesis)

    incident_types = tuple(incident_types_raw.split(",")) if incident_types_raw else ()
    if any(_TOKEN.fullmatch(item) is None for item in incident_types):
        raise ReportCheckError("incident type is not a token")
    if incident_types != _incident_types_of(hypotheses):
        raise ReportCheckError("incident types do not match the stored hypotheses")
    if INSUFFICIENT_EVIDENCE_TEMPLATE_ID not in incident_types:
        raise ReportCheckError("insufficient_evidence is not visible")

    story_ids = set(narrative.evidence_ids)
    for hypothesis in hypotheses:
        story_ids.update(hypothesis.supporting)
        story_ids.update(hypothesis.contradictory)

    parsed_stages: list[_ParsedStage] = []
    for expected in STAGE_ORDER:
        stage_raw, index = _take_meta(lines, index, "stage")
        if stage_raw != expected.value:
            raise ReportCheckError(f"expected stage {expected.value}, found {stage_raw}")
        deadline_raw, index = _take_meta(lines, index, "deadline_hours")
        if deadline_raw != str(deadline_for(expected)):
            raise ReportCheckError(f"deadline does not match {expected.value}")
        prompts: list[tuple[StatutoryPrompt, PromptStatus]] = []
        for prompt, status in prompts_for(expected):
            raw, index = _take_meta(lines, index, prompt.value)
            if raw != status.value:
                raise ReportCheckError(f"prompt {prompt.value} must be {status.value}")
            prompts.append((prompt, status))
        sentences: list[str] = []
        while index < len(lines) and not lines[index].startswith("stage="):
            sentence = lines[index]
            index += 1
            _check_story_sentence(
                sentence,
                store,
                story_ids,
                hypotheses,
                narrative.overall_confidence,
            )
            sentences.append(sentence)
        if not sentences:
            raise ReportCheckError(f"{expected.value} has no cited sentence")
        blob = "\n".join(sentences)
        for template_id in incident_types:
            if not _visible(template_id, blob):
                raise ReportCheckError(f"{template_id} is not visible in {expected.value}")
        parsed_stages.append(
            _ParsedStage(
                stage=expected,
                deadline_hours=deadline_for(expected),
                prompts=tuple(prompts),
                sentences=tuple(sentences),
            )
        )
    if index != len(lines):
        raise ReportCheckError("trailing lines after the last stage")

    early, full, uk_early, uk_full = parsed_stages
    if early.sentences != uk_early.sentences or early.prompts != uk_early.prompts:
        raise ReportCheckError("24-hour stages disagree")
    if full.sentences != uk_full.sentences or full.prompts != uk_full.prompts:
        raise ReportCheckError("72-hour stages disagree")
    if full.sentences[: len(early.sentences)] != early.sentences:
        raise ReportCheckError("72-hour notification does not extend the 24-hour warning")
    if len(full.sentences) <= len(early.sentences):
        raise ReportCheckError("72-hour notification adds no cited sentence")
    return _ParsedReport(
        narrative_id=narrative_id,
        domain=domain,
        incident_types=incident_types,
        stages=tuple(parsed_stages),
    )


def check_rendered_report(text: str, store: EvidenceStore) -> None:
    """Fail if any sentence in ``text`` lacks a stored evidence id.

    The rendered form is metadata from a fixed allowlist, then one sentence per line.
    A line that is not on the allowlist is a sentence and must cite evidence this
    narrative stores. ``insufficient_evidence`` must appear in every stage. A stored
    confidence, prior, or overall confidence must not appear as a number.

    Args:
        text: The output of `render_report`, or any text claimed to be a report.
        store: The store the narrative and its evidence must live in.

    Raises:
        ReportCheckError: If the checker cannot bind every sentence to stored evidence.
    """
    _parse_and_check(text, store)


def check_report(report: EvidenceGradeReport, store: EvidenceStore) -> None:
    """Fail if ``report`` and its rendering disagree with the store.

    Args:
        report: The report to check.
        store: The store that holds the narrative.

    Raises:
        ReportCheckError: If a sentence lacks an evidence id, the rendering drifts from
            the report object, or a confidence number is present.
    """
    parsed = _parse_and_check(render_report(report), store)
    if parsed.narrative_id != report.narrative_id:
        raise ReportCheckError("rendered narrative id does not match the report")
    if parsed.domain != report.domain.value:
        raise ReportCheckError("rendered domain does not match the report")
    if parsed.incident_types != report.incident_types:
        raise ReportCheckError("rendered incident types do not match the report")
    if len(parsed.stages) != len(report.stages):
        raise ReportCheckError("rendered stages do not match the report")
    for stage, parsed_stage in zip(report.stages, parsed.stages, strict=True):
        if stage.stage is not parsed_stage.stage:
            raise ReportCheckError("rendered stage order does not match the report")
        if stage.deadline_hours != parsed_stage.deadline_hours:
            raise ReportCheckError("rendered deadline does not match the report")
        if stage.prompts != parsed_stage.prompts:
            raise ReportCheckError("rendered prompts do not match the report")
        texts = tuple(sentence.text for sentence in stage.sentences)
        if texts != parsed_stage.sentences:
            raise ReportCheckError("rendered sentences do not match the report")

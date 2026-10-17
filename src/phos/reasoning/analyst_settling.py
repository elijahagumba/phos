"""Name the next fact that would settle competing explanations — Usefulness Phase U4.

Companion to `phos.reasoning.analyst`. Split out so neither module exceeds the repository's
500-line rule (U2's split of `failure.py` / `episode_null.py` is the precedent).

The settling ask is derived from template pattern asymmetries already declared by Atlas and
Sentiel. Nothing here invents a discriminant the templates do not carry. When the templates
declare no contradiction at all (Sentiel's finding), the answer says so and names the class of
fact that would create one.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final

from phos.ontology import Evidence, EvidenceKind, Hypothesis
from phos.reasoning.templates import (
    EvidencePattern,
    HypothesisTemplate,
    TemplateLibrary,
)

__all__ = [
    "describe_pattern",
    "settling_fact",
]


_SETTLING_WORK_ORDER: Final = "work_order"
_SETTLING_UNKNOWN_MASTER: Final = "unknown_master"
_SETTLING_OTHER: Final = "other"


def settling_fact(
    rivals: Sequence[Hypothesis],
    library: TemplateLibrary,
    *,
    already_present: Sequence[Evidence],
    entities: Mapping[str, object],
) -> str:
    """Name the single most useful next fact that would split ``rivals``.

    Derives the ask from template pattern asymmetries: a pattern that supports one rival and
    contradicts the other. Facts already on the narrative are skipped. When the templates declare
    no such asymmetry (Sentiel's finding: no contradictory patterns at all), the answer says so
    and names the class of fact that would create one — a declared sanction record — rather than
    inventing a behaviour that cannot discriminate.

    Args:
        rivals: The contentful explanations that currently cannot be split, or the unique leader
            alone when the assessment is resolved.
        library: The template library those explanations came from.
        already_present: Evidence already on the narrative; a settling fact already held is not
            "next".
        entities: Entity lookup for pattern matching (unused for naming, used if a future check
            needs to ask whether a pattern already matched).

    Returns:
        One plain-English sentence naming the fact, or an explicit statement that none is declared.
    """
    del entities  # reserved for a future "already matched" check; naming does not need it
    if not rivals:
        return (
            "No contentful explanation is on the table. More observations of the same kind are "
            "required before any assessment can be made."
        )

    templates = [_template_of(item, library) for item in rivals]
    if len(templates) == 1:
        overturning = _facts_that_would_overturn(templates[0])
        if overturning:
            return (
                "Nothing further is required to act on the assessment above. To overturn it "
                f"would take: {overturning[0]}."
            )
        return "Nothing further is required to act on the assessment above."

    candidates = _discriminating_prompts(templates[0], templates[1])
    present_kinds = _present_settling_kinds(already_present)
    for prompt, kind in candidates:
        if kind not in present_kinds:
            left = templates[0].label
            right = templates[1].label
            return (
                f"{prompt} — that fact would support one of "
                f"“{left}” and “{right}” while arguing against the other."
            )

    if not candidates:
        return (
            "No behaviour fact the templates declare can settle this. A declared sanction "
            "record (an HR change, a project assignment, or a change ticket) would — and no "
            "corpus PHOS reads carries one."
        )

    return (
        "The discriminating facts the templates declare are already on this narrative, and the "
        "explanations still cannot be split. A further fact outside those patterns is required, "
        "and the templates do not name one."
    )


def describe_pattern(pattern: EvidencePattern) -> str:
    """Return a plain-English name for a declared evidence pattern.

    Atlas and Sentiel pattern subclasses are recognised by type. An unrecognised pattern is named
    from its kind constraints rather than invented — if even that fails, the description says the
    pattern is undeclared in prose so the renderer cannot paper the gap.
    """
    from phos.atlas.packet.graph import (
        SILENT_COMMAND_RELATIONSHIP,
        UNEXPECTED_COMMAND_FUNCTION,
        UNKNOWN_COMMAND_RELATIONSHIP,
    )
    from phos.atlas.templates import (
        CommandBehaviourPattern,
        CommandResponsePattern,
        CommandStructurePattern,
        GraphFindingPattern,
        SubsystemBreadthPattern,
        UntypedStructurePattern,
        WorkOrderPattern,
    )
    from phos.sentiel.templates import BehaviourFamilyPattern

    if isinstance(pattern, WorkOrderPattern):
        return "a covering work order or change window that names this activity"
    if isinstance(pattern, GraphFindingPattern):
        features = set(pattern.features)
        if features == {UNKNOWN_COMMAND_RELATIONSHIP}:
            return "a write from a device that has never commanded this target"
        if features <= {SILENT_COMMAND_RELATIONSHIP, UNEXPECTED_COMMAND_FUNCTION} and features:
            return (
                "a change of function or an unexpected silence on a command link that was already "
                "learned"
            )
        if not features:
            return "a declared change in who commands whom"
        return f"a declared command-graph finding ({', '.join(sorted(features))})"
    if isinstance(pattern, UntypedStructurePattern):
        return "a structural change whose finding type was not declared"
    if isinstance(pattern, CommandStructurePattern):
        return "a change in who commands whom (not a work-order stamp)"
    if isinstance(pattern, CommandBehaviourPattern):
        return "a change in how a known device commands (rate, register mix, or function share)"
    if isinstance(pattern, CommandResponsePattern):
        return "a declared command whose actuator did not move"
    if isinstance(pattern, SubsystemBreadthPattern):
        if pattern.max_signals is not None:
            return f"a departure confined to at most {pattern.max_signals} signals on the same unit"
        if pattern.min_signals > 1:
            return f"a departure spanning at least {pattern.min_signals} signals on the same unit"
        return "a departure across a declared breadth of signals on the same unit"
    if isinstance(pattern, BehaviourFamilyPattern):
        if not pattern.families:
            return "a departure in any behaviour family"
        names = ", ".join(family.value.replace("_", " ") for family in pattern.families)
        return f"a departure in the {names} behaviour family"
    if pattern.kinds:
        kind_names = ", ".join(kind.value.replace("_", " ") for kind in pattern.kinds)
        return f"a {kind_names} fact"
    return (
        "a fact matching a declared pattern that this repository has not yet named in plain English"
    )


def _template_of(hypothesis: Hypothesis, library: TemplateLibrary) -> HypothesisTemplate:
    """Look up the template a hypothesis was minted from."""
    for template in library.for_domain(hypothesis.domain):
        if template.template_id == hypothesis.template_id:
            return template
    raise KeyError(
        f"template {hypothesis.template_id!r} is not in the library for domain "
        f"{hypothesis.domain.value}; the settling fact cannot be derived without it"
    )


def _discriminating_prompts(
    left: HypothesisTemplate, right: HypothesisTemplate
) -> list[tuple[str, str]]:
    """Return ``(prompt, settling_kind)`` pairs that support one rival and contradict the other.

    When a broad support pattern overlaps a more specific contradiction (or the reverse), the
    more specific pattern is the one named — so an unknown-master write is asked for by name
    rather than as a generic "change in who commands whom".
    """
    prompts: list[tuple[str, str]] = []
    seen: set[str] = set()

    def _add(support: EvidencePattern, contradict: EvidencePattern) -> None:
        chosen = _more_specific(support, contradict)
        prompt = describe_pattern(chosen)
        if prompt in seen:
            return
        seen.add(prompt)
        prompts.append((prompt, _settling_kind(chosen)))

    for support in left.supported_by:
        for contradict in right.contradicted_by:
            if support.overlaps(contradict):
                _add(support, contradict)
    for support in right.supported_by:
        for contradict in left.contradicted_by:
            if support.overlaps(contradict):
                _add(support, contradict)
    return prompts


def _more_specific(left: EvidencePattern, right: EvidencePattern) -> EvidencePattern:
    """Prefer a graph-finding or work-order pattern over a plain structure/kind constraint."""
    from phos.atlas.templates import GraphFindingPattern, WorkOrderPattern

    def score(pattern: EvidencePattern) -> int:
        if isinstance(pattern, WorkOrderPattern):
            return 3
        if isinstance(pattern, GraphFindingPattern) and pattern.features:
            return 3
        if isinstance(pattern, GraphFindingPattern):
            return 2
        return 1

    return left if score(left) >= score(right) else right


def _facts_that_would_overturn(leader: HypothesisTemplate) -> list[str]:
    """Return prompts for facts that contradict the unique leader."""
    return [describe_pattern(pattern) for pattern in leader.contradicted_by]


def _settling_kind(pattern: EvidencePattern) -> str:
    """Classify a pattern for presence filtering without comparing free text."""
    from phos.atlas.packet.graph import UNKNOWN_COMMAND_RELATIONSHIP
    from phos.atlas.templates import GraphFindingPattern, WorkOrderPattern

    if isinstance(pattern, WorkOrderPattern):
        return _SETTLING_WORK_ORDER
    if isinstance(pattern, GraphFindingPattern) and UNKNOWN_COMMAND_RELATIONSHIP in set(
        pattern.features
    ):
        return _SETTLING_UNKNOWN_MASTER
    return _SETTLING_OTHER


def _present_settling_kinds(evidence: Sequence[Evidence]) -> set[str]:
    """Return which settling kinds are already represented on the narrative."""
    from phos.atlas.command_evidence import graph_finding_feature_of
    from phos.atlas.packet.graph import UNKNOWN_COMMAND_RELATIONSHIP
    from phos.atlas.work_orders import work_order_feature_of

    present: set[str] = set()
    for item in evidence:
        if work_order_feature_of(item) is not None:
            present.add(_SETTLING_WORK_ORDER)
        feature = graph_finding_feature_of(item)
        if feature == UNKNOWN_COMMAND_RELATIONSHIP:
            present.add(_SETTLING_UNKNOWN_MASTER)
        if item.kind not in (EvidenceKind.RELATIONSHIP_CHANGE, EvidenceKind.DEVIATION):
            present.add(_SETTLING_OTHER)
    return present

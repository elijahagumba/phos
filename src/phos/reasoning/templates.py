"""Curated hypothesis templates — the only route by which an explanation enters PHOS.

**This is not open-ended reasoning, and the code says so** (Constitution §3.6). PHOS does not
invent explanations. A human author writes a `HypothesisTemplate`: a label, a prior, and a
declarative statement of which evidence patterns argue *for* it and which argue *against* it. The
engine's entire creative act is to notice that a piece of evidence matches a pattern and to
instantiate the template that pattern belongs to. Nothing here infers, generalises, or discovers a
new kind of explanation, and none of it should be described as though it did.

The pattern language is deliberately tiny — two optional constraints, `EvidenceKind` and
`EntityType`, combined with AND. Small enough that "could these two patterns both match the same
evidence?" is *decidable*, which is what lets `HypothesisTemplate` refuse, at construction time, to
call one fact both supporting and contradictory. A richer matcher (predicates, regexes) would buy
expressiveness at the cost of that guarantee, and the guarantee is what makes a confidence
reconstructable from the evidence lists.

Co-occurrence in time is the one thing a pattern does *not* express. It is a property of a set of
facts rather than of one, so it lives in `phos.reasoning.engine`, which holds the correlation
window and decides which evidence belongs to the same story.

**4B ships three templates and no more.** A generic "anomalous activity", a generic "benign
change", and the always-present "insufficient evidence" residual. They exist to exercise the
engine, they are named ``generic_*`` so no reader mistakes them for domain knowledge, and their
priors are placeholders rather than measured base rates. Atlas (PART 5) and Sentiel (PART 6)
register the templates that actually know something about industrial and enterprise behaviour.
"""

import logging
from collections.abc import Hashable, Iterable, Mapping, Sequence
from typing import Self, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from phos.ontology import (
    Domain,
    Entity,
    EntityId,
    EntityType,
    Evidence,
    EvidenceKind,
    EvidenceRole,
    Hypothesis,
    HypothesisStatus,
)

__all__ = [
    "GENERIC_ANOMALOUS_ACTIVITY_TEMPLATE_ID",
    "GENERIC_BENIGN_CHANGE_TEMPLATE_ID",
    "INSUFFICIENT_EVIDENCE_TEMPLATE_ID",
    "EvidencePattern",
    "HypothesisTemplate",
    "TemplateLibrary",
    "TemplateMatch",
    "generic_library",
    "generic_templates",
    "insufficient_evidence_template",
]

logger = logging.getLogger(__name__)

INSUFFICIENT_EVIDENCE_TEMPLATE_ID = "insufficient_evidence"
"""The residual explanation, present in every competing set: "we do not yet know"."""

GENERIC_ANOMALOUS_ACTIVITY_TEMPLATE_ID = "generic_anomalous_activity"
GENERIC_BENIGN_CHANGE_TEMPLATE_ID = "generic_benign_change"


_Constraint = TypeVar("_Constraint", EvidenceKind, EntityType)
"""The two closed vocabularies a pattern can constrain on. Both are ``str``-backed enums."""


def _constraints_overlap(left: Sequence[Hashable], right: Sequence[Hashable]) -> bool:
    """Return whether two constraint sets can hold at once; an empty set means "no constraint"."""
    if not left or not right:
        return True
    return bool(set(left) & set(right))


class EvidencePattern(BaseModel):
    """A declarative test over one piece of `Evidence`.

    Both constraints are optional and are combined with AND. An empty tuple means "no constraint on
    this dimension", so `EvidencePattern()` matches any evidence at all — a legitimate declaration
    for a template that any departure from normal bears on.

    Attributes:
        kinds: Which `EvidenceKind` values match. Empty matches every kind.
        entity_types: Which `EntityType` values match. Evidence matches if **any** of the entities
            it names is of one of these types, because evidence describing a relationship names
            more than one entity. Empty matches every type.

    Invariants:
        Constraints are stored sorted and de-duplicated, so two spellings of the same pattern are
        equal objects and serialise identically.
    """

    model_config = ConfigDict(frozen=True)

    kinds: tuple[EvidenceKind, ...] = ()
    entity_types: tuple[EntityType, ...] = ()

    @field_validator("kinds", "entity_types")
    @classmethod
    def _normalise_constraint(cls, value: tuple[_Constraint, ...]) -> tuple[_Constraint, ...]:
        """Sort and de-duplicate, so order and repetition cannot masquerade as meaning."""
        return tuple(sorted(set(value), key=lambda member: member.value))

    def matches(self, evidence: Evidence, entities: Mapping[EntityId, Entity]) -> bool:
        """Return whether ``evidence`` satisfies every constraint in this pattern.

        Args:
            evidence: The fact to test.
            entities: Entity lookup, normally built from an `EvidenceStore`. Needed only to resolve
                ``entity_types``; an entity this mapping does not hold cannot satisfy that
                constraint, because guessing its type would fabricate a match. The miss is logged.

        Returns:
            ``True`` if the evidence matches.
        """
        if self.kinds and evidence.kind not in self.kinds:
            return False
        if not self.entity_types:
            return True
        for entity_id in evidence.entity_ids:
            entity = entities.get(entity_id)
            if entity is None:
                logger.debug(
                    "evidence %s names unknown entity %s; it cannot satisfy an entity-type "
                    "constraint",
                    evidence.id,
                    entity_id,
                )
                continue
            if entity.type in self.entity_types:
                return True
        return False

    def overlaps(self, other: "EvidencePattern") -> bool:
        """Return whether some piece of evidence could satisfy both patterns.

        Exact rather than approximate: the pattern language is two finite enumerations combined
        with AND, so two patterns overlap exactly when both dimensions do. `HypothesisTemplate`
        relies on that exactness to reject an ambiguous template rather than discovering the
        ambiguity at match time.
        """
        return _constraints_overlap(self.kinds, other.kinds) and _constraints_overlap(
            self.entity_types, other.entity_types
        )


class HypothesisTemplate(BaseModel):
    """One curated, human-authored explanation, and the evidence patterns that bear on it.

    A template is a *description* of an explanation; a `Hypothesis` is an instance of it accumulated
    against a particular run of evidence. One template therefore produces many hypotheses over time,
    each recording ``template_id`` so its provenance stays inspectable.

    Attributes:
        template_id: Stable author-chosen identifier, unique within a domain.
        label: What an operator reads, e.g. ``"Unauthorised control activity"``.
        domain: Which engine's world this explanation belongs to. Evidence from another domain
            never bears on it — crossing that line is PART 7's job, not a template's.
        prior: Probability before any evidence, strictly inside ``(0, 1)``. Exactly 0 or 1 would be
            certainty before looking, which no evidence could ever move: both are infinite
            log-odds, and `phos.reasoning.belief` adds finite amounts to them.
        supported_by: Patterns whose matching evidence raises this explanation's confidence.
        contradicted_by: Patterns whose matching evidence lowers it.

    Invariants:
        No supporting pattern overlaps a contradicting one, so `role_for` is single-valued. The
        residual template carries no patterns at all.
    """

    model_config = ConfigDict(frozen=True)

    template_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    domain: Domain
    prior: float = Field(gt=0.0, lt=1.0)
    supported_by: tuple[EvidencePattern, ...] = ()
    contradicted_by: tuple[EvidencePattern, ...] = ()

    @model_validator(mode="after")
    def _check_patterns_are_unambiguous(self) -> Self:
        for supporting in self.supported_by:
            for contradicting in self.contradicted_by:
                if supporting.overlaps(contradicting):
                    raise ValueError(
                        f"template {self.template_id!r} declares evidence that could both support "
                        f"and contradict it: {supporting!r} overlaps {contradicting!r}. A role "
                        "must "
                        "be single-valued, or the confidence it produces cannot be reconstructed "
                        "from the evidence lists"
                    )
        return self

    @model_validator(mode="after")
    def _check_the_residual_stays_residual(self) -> Self:
        if self.template_id == INSUFFICIENT_EVIDENCE_TEMPLATE_ID and (
            self.supported_by or self.contradicted_by
        ):
            raise ValueError(
                f"the {INSUFFICIENT_EVIDENCE_TEMPLATE_ID!r} template must declare no evidence "
                "patterns: it is the residual explanation precisely because no evidence bears on "
                "it, and it stands for what the other explanations fail to account for"
            )
        return self

    def role_for(
        self, evidence: Evidence, entities: Mapping[EntityId, Entity]
    ) -> EvidenceRole | None:
        """Return how ``evidence`` bears on this explanation, or ``None`` if it does not.

        Args:
            evidence: The fact to weigh.
            entities: Entity lookup for resolving entity-type constraints.

        Returns:
            `EvidenceRole.SUPPORTING`, `EvidenceRole.CONTRADICTORY`, or ``None`` for evidence this
            template says nothing about — including any evidence from another domain.
        """
        if evidence.domain is not self.domain:
            logger.debug(
                "template %s (%s) ignores %s evidence %s",
                self.template_id,
                self.domain.value,
                evidence.domain.value,
                evidence.id,
            )
            return None
        if any(pattern.matches(evidence, entities) for pattern in self.supported_by):
            return EvidenceRole.SUPPORTING
        if any(pattern.matches(evidence, entities) for pattern in self.contradicted_by):
            return EvidenceRole.CONTRADICTORY
        return None

    def instantiate(self) -> Hypothesis:
        """Return a fresh `Hypothesis` seeded at this template's prior, holding no evidence.

        Returns:
            An `ACTIVE` hypothesis whose ``confidence`` equals its ``prior``. Each call mints a new
            identity: two incidents explained by the same template are two hypotheses, so that each
            accumulates only its own evidence.
        """
        return Hypothesis(
            label=self.label,
            template_id=self.template_id,
            domain=self.domain,
            prior=self.prior,
            confidence=self.prior,
            status=HypothesisStatus.ACTIVE,
        )


class TemplateMatch(BaseModel):
    """One template a piece of evidence bears on, and the role it plays for it.

    Attributes:
        template: The matched template.
        role: Whether the evidence supports or contradicts it.
    """

    model_config = ConfigDict(frozen=True)

    template: HypothesisTemplate
    role: EvidenceRole


class TemplateLibrary(BaseModel):
    """The registry of curated templates the engine may draw explanations from.

    A library is an immutable value, not shared mutable state: `with_template` returns a new
    library, so PART 5 and PART 6 register their domain templates by building one up rather than by
    mutating a global registry (Constitution §6).

    Attributes:
        templates: The registered templates, in registration order. That order is what makes
            matching — and therefore the order hypotheses spawn in — deterministic.

    Invariants:
        ``(domain, template_id)`` is unique. The pair rather than the id alone, so the same generic
        explanation can be registered once per engine while `Hypothesis` records both.
    """

    model_config = ConfigDict(frozen=True)

    templates: tuple[HypothesisTemplate, ...] = ()

    @model_validator(mode="after")
    def _check_identities_are_unique(self) -> Self:
        seen: set[tuple[Domain, str]] = set()
        for template in self.templates:
            identity = (template.domain, template.template_id)
            if identity in seen:
                raise ValueError(
                    f"template {template.template_id!r} is already registered for domain "
                    f"{template.domain.value}"
                )
            seen.add(identity)
        return self

    def with_template(self, template: HypothesisTemplate) -> "TemplateLibrary":
        """Return a new library with ``template`` registered.

        Raises:
            pydantic.ValidationError: If the domain already has a template with that id.
        """
        return TemplateLibrary(templates=(*self.templates, template))

    def with_templates(self, templates: Iterable[HypothesisTemplate]) -> "TemplateLibrary":
        """Return a new library with all of ``templates`` registered, in the order given.

        Raises:
            pydantic.ValidationError: If any id is already registered for its domain.
        """
        return TemplateLibrary(templates=(*self.templates, *templates))

    def for_domain(self, domain: Domain) -> tuple[HypothesisTemplate, ...]:
        """Return the templates registered for ``domain``, in registration order."""
        return tuple(template for template in self.templates if template.domain is domain)

    def get(self, template_id: str, domain: Domain) -> HypothesisTemplate | None:
        """Return the template with this id in this domain, or ``None``."""
        for template in self.templates:
            if template.template_id == template_id and template.domain is domain:
                return template
        return None

    def matches(
        self, evidence: Evidence, entities: Mapping[EntityId, Entity]
    ) -> tuple[TemplateMatch, ...]:
        """Return every template ``evidence`` bears on, with the role it plays for each.

        Args:
            evidence: The fact to match.
            entities: Entity lookup for resolving entity-type constraints.

        Returns:
            Matches in registration order — possibly empty, which is the case the residual
            explanation exists for. One piece of evidence routinely supports one template while
            contradicting another; that is the point of the role living on the link.
        """
        matches: list[TemplateMatch] = []
        for template in self.templates:
            role = template.role_for(evidence, entities)
            if role is not None:
                matches.append(TemplateMatch(template=template, role=role))
        return tuple(matches)

    def residual_for(self, domain: Domain) -> HypothesisTemplate:
        """Return this domain's "insufficient evidence" template, registered or canonical.

        The engine keeps this explanation in every competing set, so it may never be missing. A
        domain that registers its own — to reword it, or to set a domain-specific prior — gets that
        one; a domain that does not gets `insufficient_evidence_template`. Neither can remove it.
        """
        registered = self.get(INSUFFICIENT_EVIDENCE_TEMPLATE_ID, domain)
        if registered is not None:
            return registered
        return insufficient_evidence_template(domain)


def insufficient_evidence_template(domain: Domain) -> HypothesisTemplate:
    """Return the canonical residual explanation for ``domain``.

    "We do not yet know" is a first-class answer in PHOS, not the absence of one, so it is a real
    hypothesis with a real prior that competes with the others. No evidence ever attaches to it: it
    holds the share of belief the explanations on offer have failed to account for, and it is what
    stops a weakly-supported explanation from looking like a verdict.
    """
    return HypothesisTemplate(
        template_id=INSUFFICIENT_EVIDENCE_TEMPLATE_ID,
        label="Insufficient evidence to explain this behaviour",
        domain=domain,
        prior=0.30,
    )


def generic_templates(domain: Domain) -> tuple[HypothesisTemplate, ...]:
    """Return the three deliberately generic templates PART 4B ships for ``domain``.

    These are **placeholders that exercise the engine**, not domain knowledge. They divide the
    world crudely: behaviour that keeps failing to match expectation (deviations, forecast misses,
    sequence anomalies) argues for something being wrong, while a change in the environment's
    structure (a relationship change) argues that the new behaviour has a mundane explanation. Real
    OT and enterprise environments do not divide that cleanly — which is exactly why Atlas (PART 5)
    and Sentiel (PART 6) replace these with templates built on domain evidence.

    The priors are placeholders too, chosen only to be ordered sensibly: a benign change is a more
    common explanation for something unusual than an attack is, and "we do not know" starts ahead of
    both. They are **not measured base rates**, and no hypothesis confidence built on them should be
    shown to a user until a later PART measures them — see `phos.reasoning.belief`.

    Args:
        domain: The engine the templates are registered for.

    Returns:
        ``(generic anomalous activity, generic benign change, insufficient evidence)``.
    """
    return (
        HypothesisTemplate(
            template_id=GENERIC_ANOMALOUS_ACTIVITY_TEMPLATE_ID,
            label="Anomalous activity of unknown cause (generic)",
            domain=domain,
            prior=0.10,
            supported_by=(
                EvidencePattern(
                    kinds=(
                        EvidenceKind.DEVIATION,
                        EvidenceKind.FORECAST_MISS,
                        EvidenceKind.SEQUENCE_ANOMALY,
                    )
                ),
            ),
            contradicted_by=(EvidencePattern(kinds=(EvidenceKind.RELATIONSHIP_CHANGE,)),),
        ),
        HypothesisTemplate(
            template_id=GENERIC_BENIGN_CHANGE_TEMPLATE_ID,
            label="Benign change to the environment (generic)",
            domain=domain,
            prior=0.25,
            supported_by=(EvidencePattern(kinds=(EvidenceKind.RELATIONSHIP_CHANGE,)),),
            contradicted_by=(
                EvidencePattern(
                    kinds=(EvidenceKind.DEVIATION, EvidenceKind.SEQUENCE_ANOMALY),
                ),
            ),
        ),
        insufficient_evidence_template(domain),
    )


def generic_library(domain: Domain) -> TemplateLibrary:
    """Return a `TemplateLibrary` holding only `generic_templates` for ``domain``."""
    return TemplateLibrary(templates=generic_templates(domain))

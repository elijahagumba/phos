"""Tests for the hypothesis-template mechanism.

Two of these carry most of the weight. `test_one_piece_of_evidence_can_support_one_and_contradict
_another` is the whole reason evidence does not record its own role — the role belongs to the link,
and the same fact means opposite things to two explanations. And
`test_a_template_refuses_patterns_that_could_both_match` is what makes the role single-valued: if a
template could call one piece of evidence both supporting and contradictory, every confidence built
from it would depend on which list happened to be checked first.
"""

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from phos.ontology import (
    Domain,
    Entity,
    EntityId,
    EntityType,
    Evidence,
    EvidenceKind,
    EvidenceRole,
    HypothesisStatus,
)
from phos.reasoning.templates import (
    GENERIC_ANOMALOUS_ACTIVITY_TEMPLATE_ID,
    GENERIC_BENIGN_CHANGE_TEMPLATE_ID,
    INSUFFICIENT_EVIDENCE_TEMPLATE_ID,
    EvidencePattern,
    HypothesisTemplate,
    TemplateLibrary,
    generic_library,
    generic_templates,
    insufficient_evidence_template,
)

T0 = datetime(2026, 7, 30, 9, 0, tzinfo=UTC)
PLC = "ent_000000000001"
WORKSTATION = "ent_000000000002"
UNKNOWN = "ent_0000000000ff"

ENTITIES: Mapping[EntityId, Entity] = {
    PLC: Entity(id=PLC, type=EntityType.PLC, domain=Domain.ATLAS, name="PLC-4"),
    WORKSTATION: Entity(
        id=WORKSTATION,
        type=EntityType.ENGINEERING_WORKSTATION,
        domain=Domain.ATLAS,
        name="EWS-1",
    ),
}


def evidence(
    kind: EvidenceKind = EvidenceKind.DEVIATION,
    *,
    entity_ids: Sequence[EntityId] = (PLC,),
    domain: Domain = Domain.ATLAS,
    weight: float = 0.8,
) -> Evidence:
    return Evidence(
        kind=kind,
        source_id="dev_000000000001",
        entity_ids=list(entity_ids),
        timestamp=T0,
        domain=domain,
        weight=weight,
        summary="a fact",
    )


# ------------------------------------------------------------------------------------------------
# EvidencePattern
# ------------------------------------------------------------------------------------------------


def test_an_empty_pattern_matches_any_evidence() -> None:
    """No constraints means no filtering — "any evidence at all" is a legitimate declaration."""
    pattern = EvidencePattern()

    for kind in EvidenceKind:
        assert pattern.matches(evidence(kind), ENTITIES) is True


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        (EvidenceKind.DEVIATION, True),
        (EvidenceKind.FORECAST_MISS, True),
        (EvidenceKind.RELATIONSHIP_CHANGE, False),
        (EvidenceKind.SEQUENCE_ANOMALY, False),
    ],
)
def test_a_pattern_filters_on_kind(kind: EvidenceKind, expected: bool) -> None:
    pattern = EvidencePattern(kinds=(EvidenceKind.DEVIATION, EvidenceKind.FORECAST_MISS))

    assert pattern.matches(evidence(kind), ENTITIES) is expected


def test_a_pattern_filters_on_the_entity_types_involved() -> None:
    """One matching entity is enough: evidence about a relationship names more than one entity."""
    pattern = EvidencePattern(entity_types=(EntityType.PLC,))

    assert pattern.matches(evidence(entity_ids=[PLC]), ENTITIES) is True
    assert pattern.matches(evidence(entity_ids=[WORKSTATION, PLC]), ENTITIES) is True
    assert pattern.matches(evidence(entity_ids=[WORKSTATION]), ENTITIES) is False


def test_a_pattern_cannot_match_an_entity_the_store_does_not_hold() -> None:
    """An unresolvable entity fails the constraint rather than raising.

    `EvidenceStore.add_evidence` does not check that ``entity_ids`` resolve, so an engine can be
    handed evidence about an entity it has never been told about. Guessing the type would fabricate
    a match; raising would let one unknown id stop all reasoning. Not matching is the honest answer,
    and the miss is logged.
    """
    pattern = EvidencePattern(entity_types=(EntityType.PLC,))

    assert pattern.matches(evidence(entity_ids=[UNKNOWN]), ENTITIES) is False


def test_pattern_constraints_are_combined_with_and() -> None:
    pattern = EvidencePattern(
        kinds=(EvidenceKind.DEVIATION,), entity_types=(EntityType.ENGINEERING_WORKSTATION,)
    )

    assert pattern.matches(evidence(EvidenceKind.DEVIATION, entity_ids=[WORKSTATION]), ENTITIES)
    assert not pattern.matches(evidence(EvidenceKind.DEVIATION, entity_ids=[PLC]), ENTITIES)
    assert not pattern.matches(
        evidence(EvidenceKind.SEQUENCE_ANOMALY, entity_ids=[WORKSTATION]), ENTITIES
    )


def test_a_pattern_normalises_its_constraints() -> None:
    """Order and repetition are not meaning, so two spellings of one pattern compare equal."""
    one = EvidencePattern(kinds=(EvidenceKind.SEQUENCE_ANOMALY, EvidenceKind.DEVIATION))
    other = EvidencePattern(
        kinds=(EvidenceKind.DEVIATION, EvidenceKind.SEQUENCE_ANOMALY, EvidenceKind.DEVIATION)
    )

    assert one == other
    assert one.model_dump_json() == other.model_dump_json()


@pytest.mark.parametrize(
    ("left", "right", "overlaps"),
    [
        (EvidencePattern(), EvidencePattern(kinds=(EvidenceKind.DEVIATION,)), True),
        (
            EvidencePattern(kinds=(EvidenceKind.DEVIATION,)),
            EvidencePattern(kinds=(EvidenceKind.DEVIATION, EvidenceKind.FORECAST_MISS)),
            True,
        ),
        (
            EvidencePattern(kinds=(EvidenceKind.DEVIATION,)),
            EvidencePattern(kinds=(EvidenceKind.FORECAST_MISS,)),
            False,
        ),
        (
            EvidencePattern(kinds=(EvidenceKind.DEVIATION,), entity_types=(EntityType.PLC,)),
            EvidencePattern(kinds=(EvidenceKind.DEVIATION,), entity_types=(EntityType.HMI,)),
            False,
        ),
    ],
)
def test_overlap_is_exact_because_the_pattern_language_is_finite(
    left: EvidencePattern, right: EvidencePattern, overlaps: bool
) -> None:
    """Two patterns overlap when some evidence could satisfy both; an empty set means "all"."""
    assert left.overlaps(right) is overlaps
    assert right.overlaps(left) is overlaps


# ------------------------------------------------------------------------------------------------
# HypothesisTemplate
# ------------------------------------------------------------------------------------------------


def anomalous() -> HypothesisTemplate:
    return HypothesisTemplate(
        template_id="test_anomalous",
        label="Anomalous activity",
        domain=Domain.ATLAS,
        prior=0.1,
        supported_by=(EvidencePattern(kinds=(EvidenceKind.DEVIATION,)),),
        contradicted_by=(EvidencePattern(kinds=(EvidenceKind.RELATIONSHIP_CHANGE,)),),
    )


def benign() -> HypothesisTemplate:
    return HypothesisTemplate(
        template_id="test_benign",
        label="Benign change",
        domain=Domain.ATLAS,
        prior=0.25,
        supported_by=(EvidencePattern(kinds=(EvidenceKind.RELATIONSHIP_CHANGE,)),),
        contradicted_by=(EvidencePattern(kinds=(EvidenceKind.DEVIATION,)),),
    )


def test_a_template_reports_the_role_a_piece_of_evidence_plays() -> None:
    template = anomalous()

    assert template.role_for(evidence(EvidenceKind.DEVIATION), ENTITIES) is EvidenceRole.SUPPORTING
    assert (
        template.role_for(evidence(EvidenceKind.RELATIONSHIP_CHANGE), ENTITIES)
        is EvidenceRole.CONTRADICTORY
    )
    assert template.role_for(evidence(EvidenceKind.SEQUENCE_ANOMALY), ENTITIES) is None


def test_a_template_ignores_evidence_from_another_domain() -> None:
    """Atlas evidence must not bear on a Sentiel explanation; PART 7 owns crossing that line."""
    template = anomalous()

    assert template.role_for(evidence(domain=Domain.SENTIEL), ENTITIES) is None


def test_a_template_refuses_patterns_that_could_both_match() -> None:
    """A template that could call one fact both supporting and contradictory is unusable.

    The role would then depend on which list the implementation happened to check first, and the
    resulting confidence would not be reconstructable from the evidence lists. The pattern language
    is finite, so this is decidable at construction time rather than a runtime surprise.
    """
    with pytest.raises(ValidationError, match="both support and contradict"):
        HypothesisTemplate(
            template_id="ambiguous",
            label="Ambiguous",
            domain=Domain.ATLAS,
            prior=0.1,
            supported_by=(EvidencePattern(kinds=(EvidenceKind.DEVIATION,)),),
            contradicted_by=(EvidencePattern(entity_types=(EntityType.PLC,)),),
        )


@pytest.mark.parametrize("prior", [0.0, 1.0, -0.1, 1.5])
def test_a_template_prior_is_never_certain(prior: float) -> None:
    """A prior of 0 or 1 is a claim no evidence could move — certainty before looking."""
    with pytest.raises(ValidationError):
        HypothesisTemplate(template_id="certain", label="Certain", domain=Domain.ATLAS, prior=prior)


def test_the_residual_template_may_not_carry_patterns() -> None:
    """It is the residual precisely because no evidence bears on it."""
    with pytest.raises(ValidationError, match="no evidence patterns"):
        HypothesisTemplate(
            template_id=INSUFFICIENT_EVIDENCE_TEMPLATE_ID,
            label="Not really the residual",
            domain=Domain.ATLAS,
            prior=0.3,
            supported_by=(EvidencePattern(),),
        )


def test_a_template_instantiates_a_hypothesis_seeded_at_its_prior() -> None:
    template = anomalous()

    hypothesis = template.instantiate()

    assert hypothesis.template_id == template.template_id
    assert hypothesis.label == template.label
    assert hypothesis.domain is template.domain
    assert hypothesis.prior == template.prior
    assert hypothesis.confidence == template.prior
    assert hypothesis.status is HypothesisStatus.ACTIVE
    assert hypothesis.supporting == []
    assert hypothesis.contradictory == []


def test_two_instances_of_one_template_are_distinct_objects() -> None:
    """Two incidents explained by the same template are two hypotheses, not one shared one."""
    template = anomalous()

    assert template.instantiate().id != template.instantiate().id


# ------------------------------------------------------------------------------------------------
# TemplateLibrary
# ------------------------------------------------------------------------------------------------


def test_the_library_matches_evidence_against_every_template_it_bears_on() -> None:
    library = TemplateLibrary(templates=(anomalous(), benign()))

    matches = library.matches(evidence(EvidenceKind.DEVIATION), ENTITIES)

    assert [(m.template.template_id, m.role) for m in matches] == [
        ("test_anomalous", EvidenceRole.SUPPORTING),
        ("test_benign", EvidenceRole.CONTRADICTORY),
    ]


def test_one_piece_of_evidence_can_support_one_and_contradict_another() -> None:
    """The spec's own example, and why the role lives on the link.

    A scheduled change explains the behaviour *and* argues against foul play, so the same fact
    supports one explanation while contradicting another.
    """
    library = TemplateLibrary(templates=(anomalous(), benign()))

    matches = library.matches(evidence(EvidenceKind.RELATIONSHIP_CHANGE), ENTITIES)
    roles = {m.template.template_id: m.role for m in matches}

    assert roles == {
        "test_anomalous": EvidenceRole.CONTRADICTORY,
        "test_benign": EvidenceRole.SUPPORTING,
    }


def test_the_library_returns_nothing_for_evidence_no_template_explains() -> None:
    """The case the residual exists for."""
    library = TemplateLibrary(templates=(anomalous(), benign()))

    assert library.matches(evidence(EvidenceKind.FORECAST_MISS), ENTITIES) == ()


def test_the_library_matches_in_registration_order() -> None:
    """Determinism: the order hypotheses spawn in must not depend on set iteration."""
    forwards = TemplateLibrary(templates=(anomalous(), benign()))
    backwards = TemplateLibrary(templates=(benign(), anomalous()))
    item = evidence(EvidenceKind.DEVIATION)

    assert [m.template.template_id for m in forwards.matches(item, ENTITIES)] == [
        "test_anomalous",
        "test_benign",
    ]
    assert [m.template.template_id for m in backwards.matches(item, ENTITIES)] == [
        "test_benign",
        "test_anomalous",
    ]


def test_the_library_rejects_a_duplicate_template_id_within_a_domain() -> None:
    with pytest.raises(ValidationError, match="already registered"):
        TemplateLibrary(templates=(anomalous(), anomalous()))


def test_one_template_id_may_serve_two_domains() -> None:
    """Identity is the pair: the same generic explanation is registered per engine."""
    library = generic_library(Domain.ATLAS).with_templates(generic_templates(Domain.SENTIEL))

    atlas = library.get(GENERIC_ANOMALOUS_ACTIVITY_TEMPLATE_ID, Domain.ATLAS)
    sentiel = library.get(GENERIC_ANOMALOUS_ACTIVITY_TEMPLATE_ID, Domain.SENTIEL)

    assert atlas is not None
    assert sentiel is not None
    assert atlas.domain is Domain.ATLAS
    assert sentiel.domain is Domain.SENTIEL


def test_registering_a_template_leaves_the_original_library_alone() -> None:
    """Libraries are values. PARTs 5 and 6 register into a copy, not into shared mutable state."""
    original = TemplateLibrary(templates=(anomalous(),))

    extended = original.with_template(benign())

    assert len(original.templates) == 1
    assert len(extended.templates) == 2


def test_the_library_filters_by_domain() -> None:
    library = generic_library(Domain.ATLAS).with_templates(generic_templates(Domain.SENTIEL))

    assert {t.domain for t in library.for_domain(Domain.ATLAS)} == {Domain.ATLAS}
    assert library.get("test_anomalous", Domain.ATLAS) is None


def test_the_library_supplies_the_residual_even_when_none_was_registered() -> None:
    """Not knowing is always on the table, whatever a domain's authors remembered to register."""
    residual = TemplateLibrary().residual_for(Domain.SENTIEL)

    assert residual.template_id == INSUFFICIENT_EVIDENCE_TEMPLATE_ID
    assert residual.domain is Domain.SENTIEL
    assert residual.supported_by == ()
    assert residual.contradicted_by == ()


def test_a_registered_residual_overrides_the_canonical_one() -> None:
    """PARTs 5 and 6 may reword it or set a domain-specific prior; they may not remove it."""
    mine = HypothesisTemplate(
        template_id=INSUFFICIENT_EVIDENCE_TEMPLATE_ID,
        label="No OT explanation fits yet",
        domain=Domain.ATLAS,
        prior=0.4,
    )
    library = TemplateLibrary(templates=(mine,))

    assert library.residual_for(Domain.ATLAS) == mine
    assert library.residual_for(Domain.SENTIEL) == insufficient_evidence_template(Domain.SENTIEL)


# ------------------------------------------------------------------------------------------------
# The shipped generic set
# ------------------------------------------------------------------------------------------------


def test_the_generic_library_ships_exactly_three_clearly_generic_templates() -> None:
    """4B ships enough to exercise the engine and no more. Domain templates are PARTs 5 and 6."""
    library = generic_library(Domain.ATLAS)

    assert [t.template_id for t in library.templates] == [
        GENERIC_ANOMALOUS_ACTIVITY_TEMPLATE_ID,
        GENERIC_BENIGN_CHANGE_TEMPLATE_ID,
        INSUFFICIENT_EVIDENCE_TEMPLATE_ID,
    ]
    assert all(t.domain is Domain.ATLAS for t in library.templates)


def test_the_generic_templates_disagree_about_the_same_evidence() -> None:
    """The pair is only useful to the engine because they compete over the same facts."""
    library = generic_library(Domain.ATLAS)

    deviation_roles = {
        m.template.template_id: m.role
        for m in library.matches(evidence(EvidenceKind.DEVIATION), ENTITIES)
    }
    change_roles = {
        m.template.template_id: m.role
        for m in library.matches(evidence(EvidenceKind.RELATIONSHIP_CHANGE), ENTITIES)
    }

    assert deviation_roles[GENERIC_ANOMALOUS_ACTIVITY_TEMPLATE_ID] is EvidenceRole.SUPPORTING
    assert change_roles[GENERIC_ANOMALOUS_ACTIVITY_TEMPLATE_ID] is EvidenceRole.CONTRADICTORY
    assert change_roles[GENERIC_BENIGN_CHANGE_TEMPLATE_ID] is EvidenceRole.SUPPORTING


def test_the_generic_templates_say_in_their_own_labels_that_they_are_generic() -> None:
    """Constitution §3.6: the code must not imply this is domain knowledge it does not have."""
    for template in generic_library(Domain.ATLAS).templates:
        if template.template_id == INSUFFICIENT_EVIDENCE_TEMPLATE_ID:
            continue
        assert template.template_id.startswith("generic_")


def test_no_generic_template_is_certain_before_evidence() -> None:
    library = generic_library(Domain.ATLAS)

    assert all(0.0 < t.prior < 1.0 for t in library.templates)


def test_a_library_round_trips_as_json() -> None:
    library = generic_library(Domain.ATLAS)

    assert TemplateLibrary.model_validate_json(library.model_dump_json()) == library

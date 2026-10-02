"""The OT explanations Atlas may draw on, and the base rates behind their priors.

Two things are under test, and they are different in kind.

**The priors are derived, not felt.** Constitution §3.6 says hypothesis generation is template-based
and the code must say so; PART 5C adds that the priors must come from base rates rather than from
round numbers chosen by feel. The ladder here falls out of two anchors — the engine's own pruning
threshold and the size of one piece of fully-trusted evidence — and the tests below pin both
anchors and the ordering they produce. If either anchor moves elsewhere in PHOS, a test here fails
rather than the priors quietly drifting away from the argument that justified them.

**The matchers are honest about HAI.** Process telemetry cannot tell an operator's legitimate
control action from an attacker's, and it carries no maintenance context at all. The tests assert
those limits directly — that the malicious explanation and the process-upset explanation match
*identically* and are separated only by their prior, and that the maintenance explanation says
nothing whatsoever about a deviation — because a limit asserted by a test cannot be quietly lost.
"""

import math
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from phos.atlas import (
    ENGINEERING_MAINTENANCE_TEMPLATE_ID,
    ONE_DEVICE_MAX_SIGNALS,
    PROCESS_DISTURBANCE_TEMPLATE_ID,
    RANK_ODDS_FACTOR,
    SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID,
    UNAUTHORISED_CONTROL_TEMPLATE_ID,
    CommandBehaviourPattern,
    GraphFindingPattern,
    SubsystemBreadthPattern,
    UntypedStructurePattern,
    atlas_library,
    atlas_templates,
    graph_finding_marker,
    prior_at_rank,
)
from phos.atlas.packet import (
    SILENT_COMMAND_RELATIONSHIP,
    UNEXPECTED_COMMAND_FUNCTION,
    UNKNOWN_COMMAND_RELATIONSHIP,
)
from phos.ontology import Domain, Evidence, EvidenceKind, EvidenceRole
from phos.reasoning import (
    EVIDENCE_STRENGTH,
    INSUFFICIENT_EVIDENCE_TEMPLATE_ID,
    EvidencePattern,
    ReasoningConfig,
)

LIBRARY = atlas_library()
EPOCH = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


def event(
    *signals: str,
    kind: EvidenceKind = EvidenceKind.DEVIATION,
    domain: Domain = Domain.ATLAS,
) -> Evidence:
    """Build an evidence shaped like a subsystem event spanning ``signals``."""
    return Evidence(
        kind=kind,
        source_id="subsystem-event:ev_000000000001",
        entity_ids=list(signals),
        timestamp=EPOCH,
        domain=domain,
        weight=0.8,
        summary="a unit departed",
    )


def roles(evidence: Evidence) -> dict[str, EvidenceRole]:
    """Return ``{template_id: role}`` for every Atlas template this evidence bears on."""
    return {match.template.template_id: match.role for match in LIBRARY.matches(evidence, {})}


def prior_of(template_id: str) -> float:
    """Return the registered prior of one Atlas template."""
    template = LIBRARY.get(template_id, Domain.ATLAS)
    assert template is not None
    return template.prior


# ------------------------------------------------------------------------------------------------
# Registration
# ------------------------------------------------------------------------------------------------


def test_the_library_holds_exactly_the_five_explanations_this_part_authorises() -> None:
    """§11 forbids inventing extra explanations to look thorough, so the set is pinned."""
    assert [template.template_id for template in LIBRARY.for_domain(Domain.ATLAS)] == [
        SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID,
        ENGINEERING_MAINTENANCE_TEMPLATE_ID,
        PROCESS_DISTURBANCE_TEMPLATE_ID,
        UNAUTHORISED_CONTROL_TEMPLATE_ID,
        INSUFFICIENT_EVIDENCE_TEMPLATE_ID,
    ]


def test_every_template_belongs_to_atlas() -> None:
    assert {template.domain for template in atlas_templates()} == {Domain.ATLAS}


def test_the_residual_is_registered_rather_than_merely_available() -> None:
    """Every competing set keeps "we do not know", so it is in the library, not bolted on later."""
    assert LIBRARY.get(INSUFFICIENT_EVIDENCE_TEMPLATE_ID, Domain.ATLAS) is not None
    assert LIBRARY.residual_for(Domain.ATLAS).template_id == INSUFFICIENT_EVIDENCE_TEMPLATE_ID


def test_no_template_can_call_one_fact_both_supporting_and_contradictory() -> None:
    """`HypothesisTemplate` refuses an ambiguous template; this asserts none of ours is one."""
    for template in atlas_templates():
        for supporting in template.supported_by:
            for contradicting in template.contradicted_by:
                assert not supporting.overlaps(contradicting)


# ------------------------------------------------------------------------------------------------
# The priors and the base rates behind them
# ------------------------------------------------------------------------------------------------


def test_the_priors_are_ordered_the_way_the_base_rates_are() -> None:
    """Faults are the modal cause of an industrial anomaly; a cyber attack is the rarest."""
    assert prior_of(SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID) >= prior_of(
        ENGINEERING_MAINTENANCE_TEMPLATE_ID
    )
    assert prior_of(SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID) >= prior_of(PROCESS_DISTURBANCE_TEMPLATE_ID)
    assert prior_of(ENGINEERING_MAINTENANCE_TEMPLATE_ID) > prior_of(
        UNAUTHORISED_CONTROL_TEMPLATE_ID
    )
    assert prior_of(PROCESS_DISTURBANCE_TEMPLATE_ID) > prior_of(UNAUTHORISED_CONTROL_TEMPLATE_ID)


def test_no_explanation_starts_ahead_of_we_do_not_know() -> None:
    """Before any evidence the only thing on the table must be that nobody knows yet.

    This is the ceiling half of the derivation. An explanation whose prior exceeded the residual
    would let PHOS open with a verdict, which is the collapse the reasoning engine exists to refuse.
    """
    residual = prior_of(INSUFFICIENT_EVIDENCE_TEMPLATE_ID)

    for template in atlas_templates():
        if template.template_id == INSUFFICIENT_EVIDENCE_TEMPLATE_ID:
            continue
        assert template.prior < residual, template.template_id


def test_the_lowest_prior_is_the_engines_own_pruning_threshold() -> None:
    """The floor half of the derivation, and the reason it is not a number picked by feel.

    Below the pruning threshold a hypothesis is born marked implausible, which is a judgement made
    before looking. The malicious explanation therefore starts at exactly that threshold: the
    lowest prior the engine can carry without pre-judging it.
    """
    assert prior_of(UNAUTHORISED_CONTROL_TEMPLATE_ID) == pytest.approx(
        ReasoningConfig().pruning_threshold
    )


def test_one_rank_of_base_rate_is_one_piece_of_fully_trusted_evidence() -> None:
    """The step size, tied to `EVIDENCE_STRENGTH` so the ladder means something operational.

    Each rank multiplies the odds by exactly what one fully-trusted observation multiplies them by,
    so "maintenance starts one observation above an attack, an equipment fault two" is a sentence
    about the engine's own arithmetic rather than about a preference.
    """
    assert RANK_ODDS_FACTOR == pytest.approx(math.exp(EVIDENCE_STRENGTH))

    def odds(probability: float) -> float:
        return probability / (1.0 - probability)

    assert odds(prior_at_rank(1)) == pytest.approx(odds(prior_at_rank(0)) * RANK_ODDS_FACTOR)
    assert odds(prior_at_rank(2)) == pytest.approx(odds(prior_at_rank(1)) * RANK_ODDS_FACTOR)


def test_the_registered_priors_are_the_ones_the_ladder_produces() -> None:
    """No template may hold a prior that was typed in rather than derived."""
    assert prior_of(UNAUTHORISED_CONTROL_TEMPLATE_ID) == pytest.approx(prior_at_rank(0))
    assert prior_of(ENGINEERING_MAINTENANCE_TEMPLATE_ID) == pytest.approx(prior_at_rank(1))
    assert prior_of(PROCESS_DISTURBANCE_TEMPLATE_ID) == pytest.approx(prior_at_rank(1))
    assert prior_of(SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID) == pytest.approx(prior_at_rank(2))


def test_a_negative_rank_raises() -> None:
    with pytest.raises(ValueError, match="rank must be"):
        prior_at_rank(-1)


# ------------------------------------------------------------------------------------------------
# What the matchers can and cannot see
# ------------------------------------------------------------------------------------------------


def test_a_localised_event_argues_for_a_faulty_device_and_against_an_upset() -> None:
    """One device's worth of instrumentation departing is an instrument, not the process."""
    matched = roles(event("P1_FT01", "P1_FT01Z"))

    assert matched[SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID] is EvidenceRole.SUPPORTING
    assert matched[PROCESS_DISTURBANCE_TEMPLATE_ID] is EvidenceRole.CONTRADICTORY
    assert matched[UNAUTHORISED_CONTROL_TEMPLATE_ID] is EvidenceRole.CONTRADICTORY


def test_a_broad_event_argues_for_an_upset_and_against_a_faulty_device() -> None:
    matched = roles(event("P1_FT01", "P1_FT01Z", "P1_LIT01", "P1_PIT01"))

    assert matched[PROCESS_DISTURBANCE_TEMPLATE_ID] is EvidenceRole.SUPPORTING
    assert matched[UNAUTHORISED_CONTROL_TEMPLATE_ID] is EvidenceRole.SUPPORTING
    assert matched[SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID] is EvidenceRole.CONTRADICTORY


def test_the_boundary_between_one_device_and_more_than_one_is_where_the_roles_swap() -> None:
    """The localised/broad boundary is a fact about HAI, not a tuned threshold.

    HAI instruments a device as at most a command channel and its feedback, so two signals is one
    device and three is more than one. That is where the roles have to swap.
    """
    signals = [f"S{index}" for index in range(ONE_DEVICE_MAX_SIGNALS + 1)]

    at_boundary = roles(event(*signals[:ONE_DEVICE_MAX_SIGNALS]))
    past_boundary = roles(event(*signals))

    assert at_boundary[SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID] is EvidenceRole.SUPPORTING
    assert past_boundary[SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID] is EvidenceRole.CONTRADICTORY


def test_the_malicious_and_the_benign_upset_differ_only_where_commands_reach() -> None:
    """The limit PART P3 lifted, and the half of it that survives.

    5C asserted that these two explanations weighed *every* piece of evidence identically, and said
    that if a later PART found evidence that could separate them, this test is what would fail. The
    packet adapter is that PART. What separates them is the command graph and nothing else: on the
    process telemetry both corpora carry — a departure of some breadth on a unit — they still agree
    exactly, and only the prior tells them apart.

    **Asserted over evidence rather than over pattern tuples, since ADR 0071.** The claim has
    always been about process telemetry, and `EvidenceKind` stopped being a proxy for that the
    moment a second kind of `DEVIATION` existed. `CommandBehaviourPattern` is scoped to a declared
    command-behaviour facet and refuses a grouped subsystem event, so it cannot match a sensor
    departure — but it *is* a `DEVIATION` pattern, and a tuple comparison filtered by kind alone
    now reads it as one. This is ADR 0014 Decision 3's observation in a new place: "how many
    entities does this fact name" and "how much of a unit departed" came apart, and so did "what
    kind is this fact" and "is this process telemetry". Comparing the roles two real telemetry
    facts earn says what the prose above says, and says it more strictly.
    """
    upset = LIBRARY.get(PROCESS_DISTURBANCE_TEMPLATE_ID, Domain.ATLAS)
    malicious = LIBRARY.get(UNAUTHORISED_CONTROL_TEMPLATE_ID, Domain.ATLAS)
    assert upset is not None and malicious is not None

    broad = event(*[f"P1_S{index}" for index in range(ONE_DEVICE_MAX_SIGNALS + 1)])
    for telemetry in (event("P1_FT01"), broad):
        table = roles(telemetry)
        assert table[PROCESS_DISTURBANCE_TEMPLATE_ID] is table[UNAUTHORISED_CONTROL_TEMPLATE_ID]

    assert _telemetry_patterns(upset.supported_by) == _telemetry_patterns(malicious.supported_by)
    assert _telemetry_patterns(upset.contradicted_by) == _telemetry_patterns(
        malicious.contradicted_by
    )
    assert malicious.prior < upset.prior

    structural = EvidenceKind.RELATIONSHIP_CHANGE
    assert _patterns_over(upset.contradicted_by, structural)
    assert _patterns_over(malicious.supported_by, structural)


def _patterns_over(
    patterns: tuple[EvidencePattern, ...], kind: EvidenceKind
) -> tuple[EvidencePattern, ...]:
    """Return the patterns that constrain ``kind``, so the two halves can be compared separately."""
    return tuple(pattern for pattern in patterns if kind in pattern.kinds)


def _telemetry_patterns(patterns: tuple[EvidencePattern, ...]) -> tuple[EvidencePattern, ...]:
    """Return the patterns that read *process telemetry*, which is narrower than a `DEVIATION`.

    `CommandBehaviourPattern` is excluded by type rather than by a property of its constraints,
    because that is the honest statement: it reads a device's commanding, which is a `DEVIATION`
    for the deliberate reason ADR 0014 gives — Constitution §3.1 forbids a second evidence format —
    and is not a reading off the plant. Excluding it here is what keeps this test about the
    question 5C asked.
    """
    return tuple(
        pattern
        for pattern in _patterns_over(patterns, EvidenceKind.DEVIATION)
        if not isinstance(pattern, CommandBehaviourPattern)
    )


def test_maintenance_says_nothing_at_all_about_a_deviation() -> None:
    """HAI carries no maintenance window and no engineering workstation, so this matcher is weak.

    Weak on purpose rather than by omission: the only thing that genuinely argues for a planned
    change is a change in the environment's structure. On a process-telemetry corpus the
    explanation therefore sits at its prior and never moves — which is still true after P3, because
    a CSV of readings contains no command graph to change. What P3 alters is that Atlas can now
    produce that evidence *when it is given a capture*; see the structural tests below.
    """
    assert ENGINEERING_MAINTENANCE_TEMPLATE_ID not in roles(event("P1_FT01"))
    assert ENGINEERING_MAINTENANCE_TEMPLATE_ID not in roles(
        event("P1_FT01", "P1_FT01Z", "P1_LIT01")
    )


def test_maintenance_is_argued_for_by_a_change_in_the_environments_structure() -> None:
    matched = roles(event("P1_FT01", kind=EvidenceKind.RELATIONSHIP_CHANGE))

    assert matched[ENGINEERING_MAINTENANCE_TEMPLATE_ID] is EvidenceRole.SUPPORTING


def test_another_engines_evidence_bears_on_no_ot_explanation() -> None:
    assert roles(event("P1_FT01", domain=Domain.SENTIEL)) == {}


# ------------------------------------------------------------------------------------------------
# The breadth pattern itself
# ------------------------------------------------------------------------------------------------


def test_the_breadth_pattern_matches_only_inside_its_band() -> None:
    pattern = SubsystemBreadthPattern(min_signals=2, max_signals=3)

    assert not pattern.matches(event("A"), {})
    assert pattern.matches(event("A", "B"), {})
    assert pattern.matches(event("A", "B", "C"), {})
    assert not pattern.matches(event("A", "B", "C", "D"), {})


def test_the_breadth_pattern_still_honours_the_constraints_it_inherits() -> None:
    pattern = SubsystemBreadthPattern(kinds=(EvidenceKind.DEVIATION,), min_signals=1)

    assert pattern.matches(event("A"), {})
    assert not pattern.matches(event("A", kind=EvidenceKind.FORECAST_MISS), {})


def test_an_unbounded_band_matches_any_breadth() -> None:
    pattern = SubsystemBreadthPattern()

    assert pattern.matches(event("A"), {})
    assert pattern.matches(event(*[f"S{index}" for index in range(40)]), {})


def test_two_breadth_patterns_overlap_exactly_when_their_bands_do() -> None:
    """Exactness is what lets `HypothesisTemplate` refuse an ambiguous template at construction."""
    low = SubsystemBreadthPattern(max_signals=2)
    high = SubsystemBreadthPattern(min_signals=3)
    wide = SubsystemBreadthPattern(min_signals=2, max_signals=4)

    assert not low.overlaps(high)
    assert not high.overlaps(low)
    assert low.overlaps(wide)
    assert wide.overlaps(high)


def test_a_breadth_pattern_and_a_plain_one_overlap_because_a_plain_one_is_unbounded() -> None:
    """A plain pattern constrains no breadth, so it can always be satisfied by some event.

    The reverse direction runs `EvidencePattern.overlaps`, which cannot see a band and therefore
    answers conservatively — it reports an overlap that may not exist. Conservative is the safe
    direction: it can only make `HypothesisTemplate` refuse a template it need not have refused.
    """
    banded = SubsystemBreadthPattern(kinds=(EvidenceKind.DEVIATION,), min_signals=3)
    plain = EvidencePattern(kinds=(EvidenceKind.DEVIATION,))

    assert banded.overlaps(plain)
    assert plain.overlaps(banded)
    assert not banded.overlaps(EvidencePattern(kinds=(EvidenceKind.FORECAST_MISS,)))


def test_an_inverted_band_raises() -> None:
    with pytest.raises(ValidationError, match="min_signals"):
        SubsystemBreadthPattern(min_signals=4, max_signals=2)


# ------------------------------------------------------------------------------------------------
# PART P3: what command evidence lets these explanations say
# ------------------------------------------------------------------------------------------------
#
# Before P3, `unauthorised_control_activity` and `process_disturbance` weighed evidence identically
# and were separated only by their priors, because process telemetry carries no control context.
# A structural change in the command graph is the first evidence that tells them apart, and these
# tests pin both the new discrimination and the ones that are still impossible.


def relationship_change(*entities: str, domain: Domain = Domain.ATLAS) -> Evidence:
    """Build unmarked structural evidence — the P3 fixture shape, with no graph-finding marker."""
    return Evidence(
        kind=EvidenceKind.RELATIONSHIP_CHANGE,
        source_id="obs_00000000000f",
        entity_ids=list(entities),
        timestamp=EPOCH,
        domain=domain,
        weight=0.8,
        summary="a command relationship changed",
    )


def marked_relationship(feature: str, *entities: str) -> Evidence:
    """Build a relationship change that declares which graph finding it is."""
    named = list(entities) or ["ent_10.0.0.9", "ent_10.0.0.20"]
    return Evidence(
        kind=EvidenceKind.RELATIONSHIP_CHANGE,
        source_id="obs_00000000000f",
        entity_ids=named,
        timestamp=EPOCH,
        domain=Domain.ATLAS,
        weight=0.8,
        summary=f"{graph_finding_marker(feature)} {named[0]} commanded {named[1]}",
    )


def command_departure(device: str = "ent_10.0.0.9") -> Evidence:
    """Build per-device command-behaviour evidence: a DEVIATION that is not a subsystem event."""
    return Evidence(
        kind=EvidenceKind.DEVIATION,
        source_id="dev_00000000000a",
        entity_ids=[device],
        timestamp=EPOCH,
        domain=Domain.ATLAS,
        weight=0.8,
        summary="a device's commanding departed",
    )


def test_a_command_relationship_change_separates_an_attacker_from_a_process_upset() -> None:
    """The discrimination the packet adapter exists for, asserted as a role table."""
    assert roles(relationship_change("ent_10.0.0.9", "ent_10.0.0.20")) == {
        ENGINEERING_MAINTENANCE_TEMPLATE_ID: EvidenceRole.SUPPORTING,
        PROCESS_DISTURBANCE_TEMPLATE_ID: EvidenceRole.CONTRADICTORY,
        UNAUTHORISED_CONTROL_TEMPLATE_ID: EvidenceRole.SUPPORTING,
    }


def test_sensor_breadth_alone_still_cannot_separate_them() -> None:
    """The limit P3 lifts, restated: on a deviation the two explanations are still identical."""
    broad = roles(event(*[f"P1_S{index}" for index in range(ONE_DEVICE_MAX_SIGNALS + 1)]))

    assert broad[PROCESS_DISTURBANCE_TEMPLATE_ID] is broad[UNAUTHORISED_CONTROL_TEMPLATE_ID]


def test_a_structural_change_is_the_maintenance_explanations_first_real_matcher() -> None:
    """5C left `engineering_maintenance` with nothing to match. The command graph supplies it."""
    assert roles(event("P1_FT01")).get(ENGINEERING_MAINTENANCE_TEMPLATE_ID) is None
    assert (
        roles(relationship_change("ent_10.0.0.9", "ent_10.0.0.20"))[
            ENGINEERING_MAINTENANCE_TEMPLATE_ID
        ]
        is EvidenceRole.SUPPORTING
    )


def test_maintenance_and_an_attacker_remain_indistinguishable_to_the_evidence() -> None:
    """An untyped structural change still supports both; only their priors separate them.

    This is ADR 0014's remaining limit, stated as a test so it cannot be quietly lost. A
    relationship change that does not declare which graph finding it is is exactly what a
    commissioning engineer and an intruder can both leave behind.
    """
    table = roles(relationship_change("ent_10.0.0.9", "ent_10.0.0.20"))

    assert table[ENGINEERING_MAINTENANCE_TEMPLATE_ID] is table[UNAUTHORISED_CONTROL_TEMPLATE_ID]
    assert prior_of(ENGINEERING_MAINTENANCE_TEMPLATE_ID) > prior_of(
        UNAUTHORISED_CONTROL_TEMPLATE_ID
    )


def test_an_unknown_master_contradicts_maintenance_and_supports_an_attacker() -> None:
    """A device that has never commanded this target is not how plant engineers work."""
    table = roles(marked_relationship(UNKNOWN_COMMAND_RELATIONSHIP))

    assert table[UNAUTHORISED_CONTROL_TEMPLATE_ID] is EvidenceRole.SUPPORTING
    assert table[ENGINEERING_MAINTENANCE_TEMPLATE_ID] is EvidenceRole.CONTRADICTORY
    assert table[PROCESS_DISTURBANCE_TEMPLATE_ID] is EvidenceRole.CONTRADICTORY


def test_a_function_change_on_a_known_link_still_supports_both() -> None:
    """ADR 0014 Decision 4, kept for known-link findings: the issuer is already a commander."""
    table = roles(marked_relationship(UNEXPECTED_COMMAND_FUNCTION))

    assert table[ENGINEERING_MAINTENANCE_TEMPLATE_ID] is EvidenceRole.SUPPORTING
    assert table[UNAUTHORISED_CONTROL_TEMPLATE_ID] is EvidenceRole.SUPPORTING


def test_a_silent_known_link_still_supports_both() -> None:
    table = roles(marked_relationship(SILENT_COMMAND_RELATIONSHIP))

    assert table[ENGINEERING_MAINTENANCE_TEMPLATE_ID] is EvidenceRole.SUPPORTING
    assert table[UNAUTHORISED_CONTROL_TEMPLATE_ID] is EvidenceRole.SUPPORTING


def test_a_marked_finding_and_untyped_structure_are_disjoint_patterns() -> None:
    """The split that lets one template contradict unknown masters without overlapping support."""
    marked = GraphFindingPattern(
        kinds=(EvidenceKind.RELATIONSHIP_CHANGE,), features=(UNKNOWN_COMMAND_RELATIONSHIP,)
    )
    untyped = UntypedStructurePattern(kinds=(EvidenceKind.RELATIONSHIP_CHANGE,))

    assert not marked.overlaps(untyped)
    assert not untyped.overlaps(marked)
    assert marked.matches(marked_relationship(UNKNOWN_COMMAND_RELATIONSHIP), {})
    assert not marked.matches(relationship_change("ent_10.0.0.9", "ent_10.0.0.20"), {})
    assert untyped.matches(relationship_change("ent_10.0.0.9", "ent_10.0.0.20"), {})
    assert not untyped.matches(marked_relationship(UNKNOWN_COMMAND_RELATIONSHIP), {})


def test_an_undeclared_command_departure_bears_on_no_ot_explanation() -> None:
    """Breadth is a property of a plant unit, and a device's commanding is not one.

    Without the guard this evidence would match `_LOCALISED` and so argue *against* unauthorised
    control — the exact opposite of what reading commands is for. That half is unchanged.

    **What this pins is now narrower (ADR 0071).** The fixture declares neither facet nor summary
    marker, and it is the *declaration* rather than the pattern language that decides: a departure
    that says which feature departed reaches two explanations, and one that says nothing reaches
    none. `CommandBehaviourPattern` refuses an undeclared deviation deliberately, because a
    matcher that read one as command behaviour would put every sensor reading on both control
    explanations. A declared departure's routing is asserted in
    `tests/atlas/test_command_behaviour_pattern.py`.
    """
    assert roles(command_departure()) == {}


def test_breadth_patterns_only_read_grouped_subsystem_events() -> None:
    pattern = SubsystemBreadthPattern(kinds=(EvidenceKind.DEVIATION,), max_signals=2)

    assert pattern.matches(event("P1_FT01"), {})
    assert not pattern.matches(command_departure(), {})


def test_a_breadth_pattern_can_be_declared_for_ungrouped_evidence() -> None:
    pattern = SubsystemBreadthPattern(
        kinds=(EvidenceKind.DEVIATION,), max_signals=2, subsystem_events_only=False
    )

    assert pattern.matches(command_departure(), {})
    assert not pattern.matches(event("P1_FT01"), {})


def test_patterns_scoped_to_different_evidence_can_never_both_match() -> None:
    """Exactness again: `HypothesisTemplate` refuses ambiguity at construction using `overlaps`."""
    grouped = SubsystemBreadthPattern(subsystem_events_only=True)
    ungrouped = SubsystemBreadthPattern(subsystem_events_only=False)

    assert not grouped.overlaps(ungrouped)
    assert not ungrouped.overlaps(grouped)
    assert grouped.overlaps(SubsystemBreadthPattern(subsystem_events_only=True))


def test_a_relationship_change_from_another_engine_bears_on_no_ot_explanation() -> None:
    assert roles(relationship_change("ent_a", "ent_b", domain=Domain.SENTIEL)) == {}

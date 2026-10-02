"""ADR 0071: command-behaviour evidence reaches a template, and nothing else moves.

Four claims, and they are different in kind.

**Routing.** A declared command-behaviour departure reaches `CommandBehaviourPattern` and earns
`SUPPORTING` on exactly two explanations — the two that involve somebody operating a device. That
is the evidence Atlas has been stamping since Session D1 and discarding at the reasoning boundary.

**Refusal.** `process_disturbance` and `sensor_or_device_fault` get no relation at all, and that
is asserted rather than left to fall out. A controller answers a real upset by commanding
differently, so calling this evidence *against* an upset would be false; calling it *for* one
would be a claim about closed-loop dynamics nothing in Atlas has measured.

**Containment.** A departure that declares no facet, a sensor subsystem event, a graph finding and
a work order all reach exactly what they reached before. The existing four patterns are untouched.

**Invariants.** The competing set never collapses, `insufficient_evidence` is always in it,
confidence stays strictly below certainty, and the five priors are the ones the base-rate ladder
produced. None of this is a detection claim: see `test_this_is_readiness_and_not_a_result`.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from tests.atlas.test_command_evidence import (
    CERTAIN,
    finding,
    fitted_on_normal,
    steady_then_spike,
)

from phos.atlas import (
    ENGINEERING_MAINTENANCE_TEMPLATE_ID,
    ONE_DEVICE_MAX_SIGNALS,
    PROCESS_DISTURBANCE_TEMPLATE_ID,
    SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID,
    UNAUTHORISED_CONTROL_TEMPLATE_ID,
    CommandBehaviourPattern,
    GraphFindingPattern,
    SubsystemBreadthPattern,
    UntypedStructurePattern,
    atlas_library,
    atlas_templates,
    command_behaviour_marker,
    promote_command_behaviour,
    promote_graph_findings,
)
from phos.atlas.command_eval import discover_labelled_command_corpora
from phos.atlas.packet import COMMAND_COUNT, COMMAND_INTERVAL_CV, UNKNOWN_COMMAND_RELATIONSHIP
from phos.atlas.templates import CommandStructurePattern, WorkOrderPattern
from phos.atlas.work_orders import WORK_ORDER_FEATURE, promote_work_orders
from phos.ontology import (
    Domain,
    Evidence,
    EvidenceKind,
    EvidenceRole,
    FacetKind,
    InMemoryEvidenceStore,
)
from phos.reasoning import (
    INSUFFICIENT_EVIDENCE_TEMPLATE_ID,
    EvidencePattern,
    ReasoningConfig,
    ReasoningEngine,
)

LIBRARY = atlas_library()
EPOCH = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
DEVICE = "ent_10.0.0.9"

_CONTROL_EXPLANATIONS = (ENGINEERING_MAINTENANCE_TEMPLATE_ID, UNAUTHORISED_CONTROL_TEMPLATE_ID)
_PROCESS_EXPLANATIONS = (PROCESS_DISTURBANCE_TEMPLATE_ID, SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID)


# ------------------------------------------------------------------------------------------------
# Hand-built fixtures
# ------------------------------------------------------------------------------------------------


def departure(
    feature: str = COMMAND_COUNT,
    *,
    device: str = DEVICE,
    facet: bool = True,
    marker: bool = True,
    source_id: str = "dev_00000000000a",
) -> Evidence:
    """Build a per-device command-behaviour departure, with either channel independently set.

    ``facet`` and ``marker`` are separate so a test can force the two apart. While they agree no
    test can observe which one the matcher read, which is the same argument ADR 0070 made.
    """
    body = f"{device} {feature} collapsed to a sixth of what this device normally runs"
    return Evidence(
        kind=EvidenceKind.DEVIATION,
        source_id=source_id,
        entity_ids=[device],
        timestamp=EPOCH,
        domain=Domain.ATLAS,
        weight=0.8,
        summary=f"{command_behaviour_marker(feature)}{body}" if marker else body,
        facet_kind=FacetKind.COMMAND_BEHAVIOUR if facet else None,
        facet=feature if facet else None,
    )


def subsystem_event(*signals: str) -> Evidence:
    """Build the grouped sensor evidence 5C produces: signals departing together on one unit."""
    named = list(signals) or ["P1_FT01", "P1_LIT01", "P1_PIT01"]
    return Evidence(
        kind=EvidenceKind.DEVIATION,
        source_id="subsystem-event:ev_000000000001,ev_000000000002",
        entity_ids=named,
        timestamp=EPOCH,
        domain=Domain.ATLAS,
        weight=0.8,
        summary=f"P1: {len(named)} signals departed together",
    )


def roles(evidence: Evidence) -> dict[str, EvidenceRole]:
    """Return ``{template_id: role}`` for every Atlas template this evidence bears on."""
    return {match.template.template_id: match.role for match in LIBRARY.matches(evidence, {})}


def promoted_departure() -> Evidence:
    """Return a departure built by the real promoter, facet and marker both set by it."""
    training, live = steady_then_spike()
    return promote_command_behaviour(live, fitted_on_normal().fit(training), CERTAIN)[0].evidence


# ------------------------------------------------------------------------------------------------
# Routing: the evidence reaches the hypotheses it should, with the roles it should
# ------------------------------------------------------------------------------------------------


def test_a_command_behaviour_departure_reaches_both_control_explanations() -> None:
    """The gap this record closes: the stamp now routes instead of being discarded."""
    assert roles(departure()) == {
        ENGINEERING_MAINTENANCE_TEMPLATE_ID: EvidenceRole.SUPPORTING,
        UNAUTHORISED_CONTROL_TEMPLATE_ID: EvidenceRole.SUPPORTING,
    }


def test_the_promoted_departure_routes_the_same_way_the_hand_built_one_does() -> None:
    """The fixture is not a special case: what Atlas actually promotes lands identically."""
    assert roles(promoted_departure()) == roles(departure())


def test_every_command_behaviour_feature_routes_the_same_way() -> None:
    """No feature is privileged. Sub-selecting one would be tuning toward a corpus (ADR 0040)."""
    for feature in (COMMAND_COUNT, COMMAND_INTERVAL_CV, "write_command_share"):
        assert roles(departure(feature)) == roles(departure(COMMAND_COUNT))


def test_the_tie_between_an_engineer_and_an_attacker_is_not_resolved() -> None:
    """ADR 0014 Decision 4's tie, reached again and deliberately left standing.

    Both explanations involve somebody operating a device, and no command feature carries intent.
    Only the priors separate them, and the priors are base rates rather than a tuning choice.
    """
    table = roles(departure())

    assert table[ENGINEERING_MAINTENANCE_TEMPLATE_ID] is table[UNAUTHORISED_CONTROL_TEMPLATE_ID]
    priors = {t.template_id: t.prior for t in atlas_templates()}
    assert priors[ENGINEERING_MAINTENANCE_TEMPLATE_ID] > priors[UNAUTHORISED_CONTROL_TEMPLATE_ID]


def test_the_two_process_explanations_get_no_relation_at_all() -> None:
    """The refusal, asserted. A controller answers a real upset by commanding differently."""
    table = roles(departure())

    for template_id in _PROCESS_EXPLANATIONS:
        assert template_id not in table


def test_the_residual_never_takes_evidence() -> None:
    """`insufficient_evidence` holds unexplained belief; nothing may attach to it."""
    assert INSUFFICIENT_EVIDENCE_TEMPLATE_ID not in roles(departure())


# ------------------------------------------------------------------------------------------------
# Resolution is typed: the facet decides, the summary does not
# ------------------------------------------------------------------------------------------------


def test_the_facet_routes_the_departure_when_the_summary_says_nothing() -> None:
    """A promoter that stamps only the typed field still reaches the templates."""
    assert roles(departure(facet=True, marker=False)) == roles(departure())


def test_the_facet_is_authoritative_over_a_disagreeing_summary() -> None:
    """ADR 0070 Decision 8, exercised through the new pattern.

    A fact carrying a graph-finding facet and a forged command-behaviour marker must route as a
    graph finding. That is the only property a test can observe about which channel was read.
    """
    forged = Evidence(
        kind=EvidenceKind.DEVIATION,
        source_id="dev_00000000000b",
        entity_ids=[DEVICE],
        timestamp=EPOCH,
        domain=Domain.ATLAS,
        weight=0.8,
        summary=f"{command_behaviour_marker(COMMAND_COUNT)}forged",
        facet_kind=FacetKind.GRAPH_FINDING,
        facet=UNKNOWN_COMMAND_RELATIONSHIP,
    )

    assert roles(forged) == {}


def test_an_undeclared_departure_still_bears_on_nothing() -> None:
    """Containment: no facet and no marker resolves to nothing, exactly as before this record."""
    assert roles(departure(facet=False, marker=False)) == {}


# ------------------------------------------------------------------------------------------------
# Containment: nothing that is not a command-behaviour departure moves
# ------------------------------------------------------------------------------------------------


def test_a_sensor_subsystem_event_is_unaffected() -> None:
    """The broad and localised verdicts P3 recorded, unchanged by this record."""
    broad = roles(subsystem_event(*[f"P1_S{i}" for i in range(ONE_DEVICE_MAX_SIGNALS + 1)]))
    localised = roles(subsystem_event("P1_FT01"))

    assert broad == {
        PROCESS_DISTURBANCE_TEMPLATE_ID: EvidenceRole.SUPPORTING,
        SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID: EvidenceRole.CONTRADICTORY,
        UNAUTHORISED_CONTROL_TEMPLATE_ID: EvidenceRole.SUPPORTING,
    }
    assert localised == {
        PROCESS_DISTURBANCE_TEMPLATE_ID: EvidenceRole.CONTRADICTORY,
        SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID: EvidenceRole.SUPPORTING,
        UNAUTHORISED_CONTROL_TEMPLATE_ID: EvidenceRole.CONTRADICTORY,
    }


def test_a_grouped_event_carrying_a_command_facet_is_still_read_as_breadth() -> None:
    """The guard ADR 0014 Decision 3 made explicit, held from the other side.

    Nothing promotes this fact. The point is that the disjointness `overlaps` claims is checked
    against a declared marker rather than assumed from what the promoters happen to build.
    """
    grouped = subsystem_event("P1_FT01").model_copy(
        update={"facet_kind": FacetKind.COMMAND_BEHAVIOUR, "facet": COMMAND_COUNT}
    )

    assert not CommandBehaviourPattern(kinds=(EvidenceKind.DEVIATION,)).matches(grouped, {})
    assert roles(grouped) == roles(subsystem_event("P1_FT01"))


def test_the_graph_finding_verdicts_are_unchanged() -> None:
    """An unknown master still supports the attack and contradicts maintenance (ADR 0027)."""
    change = promote_graph_findings(
        [finding(UNKNOWN_COMMAND_RELATIONSHIP, 5.0, extra={"function_codes": "6"})], CERTAIN
    )[0]

    assert roles(change.evidence) == {
        ENGINEERING_MAINTENANCE_TEMPLATE_ID: EvidenceRole.CONTRADICTORY,
        PROCESS_DISTURBANCE_TEMPLATE_ID: EvidenceRole.CONTRADICTORY,
        UNAUTHORISED_CONTROL_TEMPLATE_ID: EvidenceRole.SUPPORTING,
    }


def test_the_work_order_verdicts_are_unchanged() -> None:
    """A work order still supports maintenance and contradicts the attack (ADR 0059)."""
    order = promote_work_orders([finding(WORK_ORDER_FEATURE, 1.0)], CERTAIN)[0]

    assert roles(order.evidence) == {
        ENGINEERING_MAINTENANCE_TEMPLATE_ID: EvidenceRole.SUPPORTING,
        UNAUTHORISED_CONTROL_TEMPLATE_ID: EvidenceRole.CONTRADICTORY,
    }


def test_a_departure_from_another_engine_bears_on_no_ot_explanation() -> None:
    """Sentiel sets no facet and reads none; a domain crossing is PART 7's job, not a pattern's."""
    foreign = departure().model_copy(update={"domain": Domain.SENTIEL})

    assert roles(foreign) == {}


# ------------------------------------------------------------------------------------------------
# Pattern algebra: the disjointness `HypothesisTemplate` relies on
# ------------------------------------------------------------------------------------------------


def test_the_pattern_is_disjoint_from_every_grouped_breadth_band() -> None:
    """Why `_COMMAND_BEHAVIOUR` may support the attack while `_LOCALISED` contradicts it."""
    pattern = CommandBehaviourPattern(kinds=(EvidenceKind.DEVIATION,))
    localised = SubsystemBreadthPattern(
        kinds=(EvidenceKind.DEVIATION,), max_signals=ONE_DEVICE_MAX_SIGNALS
    )

    assert not pattern.overlaps(localised)
    assert pattern.matches(departure(), {})
    assert not localised.matches(departure(), {})
    assert not pattern.matches(subsystem_event("P1_FT01"), {})
    assert localised.matches(subsystem_event("P1_FT01"), {})


def test_the_pattern_is_disjoint_from_the_three_relationship_patterns() -> None:
    """Exact rather than declared: a deviation is not a relationship change."""
    pattern = CommandBehaviourPattern(kinds=(EvidenceKind.DEVIATION,))
    rivals: tuple[EvidencePattern, ...] = (
        GraphFindingPattern(kinds=(EvidenceKind.RELATIONSHIP_CHANGE,)),
        UntypedStructurePattern(kinds=(EvidenceKind.RELATIONSHIP_CHANGE,)),
        WorkOrderPattern(kinds=(EvidenceKind.RELATIONSHIP_CHANGE,)),
        CommandStructurePattern(kinds=(EvidenceKind.RELATIONSHIP_CHANGE,)),
    )

    for rival in rivals:
        assert not pattern.overlaps(rival)


def test_the_pattern_still_overlaps_an_ungrouped_band_that_could_match_the_same_fact() -> None:
    """`overlaps` is not a blanket "no". A band scoped to ungrouped evidence genuinely can."""
    pattern = CommandBehaviourPattern(kinds=(EvidenceKind.DEVIATION,))
    ungrouped = SubsystemBreadthPattern(
        kinds=(EvidenceKind.DEVIATION,), subsystem_events_only=False
    )

    assert pattern.overlaps(ungrouped)
    assert pattern.matches(departure(), {})
    assert ungrouped.matches(departure(), {})


def test_every_template_still_refuses_an_ambiguous_role() -> None:
    """`HypothesisTemplate` validates at construction; rebuilding the library re-runs that."""
    for template in atlas_templates():
        for supporting in template.supported_by:
            for contradicting in template.contradicted_by:
                assert not supporting.overlaps(contradicting)


# ------------------------------------------------------------------------------------------------
# Reasoning invariants: what this record must not have moved
# ------------------------------------------------------------------------------------------------


def competing(*stream: Evidence) -> dict[str, float]:
    """Ingest evidence into a fresh Atlas engine and return the competing confidences."""
    engine = ReasoningEngine(
        atlas_library(),
        InMemoryEvidenceStore(),
        ReasoningConfig(correlation_window=timedelta(hours=2)),
    )
    engine.ingest(list(stream))
    return {h.template_id: h.confidence for h in engine.competing(Domain.ATLAS)}


def test_the_competing_set_never_collapses() -> None:
    """Both control explanations survive together, and the residual with them.

    `ReasoningEngine.competing` instantiates a hypothesis per template the evidence bears on plus
    the residual, which is pre-existing behaviour rather than anything this record introduced — a
    grouped sensor event likewise yields four of the five, `engineering_maintenance` absent. The
    invariant that matters is that a single fact never leaves one explanation standing alone.
    """
    confidences = competing(departure())

    assert set(confidences) == {
        ENGINEERING_MAINTENANCE_TEMPLATE_ID,
        UNAUTHORISED_CONTROL_TEMPLATE_ID,
        INSUFFICIENT_EVIDENCE_TEMPLATE_ID,
    }
    assert len(confidences) > 1


def test_a_sensor_event_still_instantiates_the_set_it_always_did() -> None:
    """The comparison that shows the shape above is the engine's, not this record's."""
    assert set(competing(subsystem_event("P1_FT01"))) == {
        SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID,
        PROCESS_DISTURBANCE_TEMPLATE_ID,
        UNAUTHORISED_CONTROL_TEMPLATE_ID,
        INSUFFICIENT_EVIDENCE_TEMPLATE_ID,
    }


def test_insufficient_evidence_is_always_in_the_competing_set() -> None:
    """The residual is a first-class answer, not the absence of one."""
    assert INSUFFICIENT_EVIDENCE_TEMPLATE_ID in competing(departure())
    two = competing(departure(), departure(COMMAND_INTERVAL_CV))
    assert INSUFFICIENT_EVIDENCE_TEMPLATE_ID in two


def test_no_confidence_reaches_certainty() -> None:
    """Belief is log-odds plus finite amounts, so a run of evidence cannot reach 1.0."""
    many = [departure(COMMAND_COUNT), departure(COMMAND_INTERVAL_CV), promoted_departure()]

    for confidence in competing(*many).values():
        assert 0.0 < confidence < 1.0


def test_the_base_rate_priors_are_untouched() -> None:
    """Pinned to twelve decimals, the same figures `TestReuseNotFork` holds."""
    assert [(t.template_id, round(t.prior, 12)) for t in atlas_templates()] == [
        ("sensor_or_device_fault", 0.155172413793),
        ("engineering_maintenance", 0.057692307692),
        ("process_disturbance", 0.057692307692),
        ("unauthorised_control_activity", 0.02),
        ("insufficient_evidence", 0.3),
    ]


def test_the_departure_is_reachable_from_the_hypothesis_it_moved() -> None:
    """Constitution §3.2: the role a fact played is on the hypothesis, not inferred."""
    engine = ReasoningEngine(
        atlas_library(),
        InMemoryEvidenceStore(),
        ReasoningConfig(correlation_window=timedelta(hours=2)),
    )
    fact = promoted_departure()
    engine.ingest([fact])

    carried = {
        h.template_id for h in engine.hypotheses() if fact.id in {*h.supporting, *h.contradictory}
    }

    assert carried == set(_CONTROL_EXPLANATIONS)


def test_this_is_readiness_and_not_a_result() -> None:
    """The honesty guard, executable. Nothing here is a detection number.

    Every fixture above is hand-built or promoted from hand-built observations. The value of this
    routing is gated on a labelled command corpus, which ADR 0040 and the TU Wien assessment
    confirm does not exist, so `discover_labelled_command_corpora` must still find nothing.
    """
    assert discover_labelled_command_corpora(Path("data")) == []

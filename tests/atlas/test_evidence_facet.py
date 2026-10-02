"""ADR 0070: the typed facet replaces summary-string parsing, and nothing else moves.

Three claims, and they are different in kind.

**Equivalence.** Every fact the three promoters build must resolve to the same feature through the
typed facet as it did through the summary marker. That is what makes this a refactor rather than a
change: the old path is still present and still reachable, so the test can run both and compare.

**Authority.** The typed facet decides, and the summary no longer does. The proof has to be a fact
whose two channels disagree — a forged marker on a correctly-facetted piece of evidence — because
while they agree, no test can tell which one a matcher read.

**Containment.** Evidence that declares no facet resolves exactly as it did before, through the
marker, so no fixture and no earlier promoter changes behaviour.
"""

import pytest
from tests.atlas.test_command_evidence import (
    CERTAIN,
    finding,
    fitted_on_normal,
    steady_then_spike,
)

from phos.atlas.command_evidence import (
    COMMAND_BEHAVIOUR_MARKER,
    GRAPH_FINDING_MARKER,
    _command_behaviour_from_summary,
    _graph_finding_from_summary,
    command_behaviour_feature_of,
    graph_finding_feature_of,
    promote_command_behaviour,
    promote_graph_findings,
)
from phos.atlas.packet import (
    SILENT_COMMAND_RELATIONSHIP,
    UNEXPECTED_COMMAND_FUNCTION,
    UNKNOWN_COMMAND_RELATIONSHIP,
)
from phos.atlas.templates import (
    ENGINEERING_MAINTENANCE_TEMPLATE_ID,
    UNAUTHORISED_CONTROL_TEMPLATE_ID,
    atlas_library,
)
from phos.atlas.work_orders import (
    WORK_ORDER_FEATURE,
    WORK_ORDER_MARKER,
    _work_order_from_summary,
    promote_work_orders,
    work_order_feature_of,
)
from phos.ontology import Evidence, EvidenceRole, FacetKind

GRAPH_FEATURES = (
    UNKNOWN_COMMAND_RELATIONSHIP,
    SILENT_COMMAND_RELATIONSHIP,
    UNEXPECTED_COMMAND_FUNCTION,
)


def promoted_graph_changes() -> list[Evidence]:
    """Every graph finding the promoter recognises, promoted."""
    findings = [
        finding(UNKNOWN_COMMAND_RELATIONSHIP, 5.0, index=0),
        finding(SILENT_COMMAND_RELATIONSHIP, 3.0, index=1),
        finding(UNEXPECTED_COMMAND_FUNCTION, 2.0, index=2, extra={"function_code": "6"}),
    ]
    return [change.evidence for change in promote_graph_findings(findings, CERTAIN)]


def promoted_behaviour_departures() -> list[Evidence]:
    """Command-behaviour departures, promoted."""
    training, live = steady_then_spike()
    fitted = fitted_on_normal().fit(training)
    return [d.evidence for d in promote_command_behaviour(live, fitted, CERTAIN)]


def promoted_work_orders() -> list[Evidence]:
    """Work-order facts, promoted."""
    order = finding(WORK_ORDER_FEATURE, 1.0, index=0)
    return [fact.evidence for fact in promote_work_orders([order], CERTAIN)]


# ------------------------------------------------------------------------------------------------
# Equivalence: the typed facet resolves to what the string parse resolved to
# ------------------------------------------------------------------------------------------------


def test_every_promoted_graph_finding_agrees_between_facet_and_summary() -> None:
    promoted = promoted_graph_changes()
    assert len(promoted) == len(GRAPH_FEATURES)
    for evidence in promoted:
        assert evidence.facet_kind is FacetKind.GRAPH_FINDING
        assert evidence.facet in GRAPH_FEATURES
        assert graph_finding_feature_of(evidence) == _graph_finding_from_summary(evidence)
        assert graph_finding_feature_of(evidence) == evidence.facet


def test_every_promoted_behaviour_departure_agrees_between_facet_and_summary() -> None:
    promoted = promoted_behaviour_departures()
    assert promoted
    for evidence in promoted:
        assert evidence.facet_kind is FacetKind.COMMAND_BEHAVIOUR
        assert command_behaviour_feature_of(evidence) == _command_behaviour_from_summary(evidence)
        assert command_behaviour_feature_of(evidence) == evidence.facet


def test_every_promoted_work_order_agrees_between_facet_and_summary() -> None:
    promoted = promoted_work_orders()
    assert promoted
    for evidence in promoted:
        assert evidence.facet_kind is FacetKind.WORK_ORDER
        assert work_order_feature_of(evidence) == _work_order_from_summary(evidence)
        assert work_order_feature_of(evidence) == evidence.facet


def test_the_summary_markers_are_still_written_unchanged() -> None:
    """The human-readable half does not move, so nothing a reader sees changes."""
    for evidence in promoted_graph_changes():
        assert evidence.summary.startswith(GRAPH_FINDING_MARKER)
    for evidence in promoted_behaviour_departures():
        assert evidence.summary.startswith(COMMAND_BEHAVIOUR_MARKER)
    for evidence in promoted_work_orders():
        assert evidence.summary.startswith(WORK_ORDER_MARKER)


def test_each_resolver_declines_the_other_two_facets() -> None:
    """A work order is not a graph finding, and the typed path must say so as the marker did."""
    graph = promoted_graph_changes()[0]
    behaviour = promoted_behaviour_departures()[0]
    order = promoted_work_orders()[0]

    assert work_order_feature_of(graph) is None
    assert command_behaviour_feature_of(graph) is None
    assert graph_finding_feature_of(order) is None
    assert command_behaviour_feature_of(order) is None
    assert graph_finding_feature_of(behaviour) is None
    assert work_order_feature_of(behaviour) is None


# ------------------------------------------------------------------------------------------------
# Template matching: identical verdicts, now reached through the typed field
# ------------------------------------------------------------------------------------------------


def test_templates_reach_the_same_verdict_on_every_promoted_fact() -> None:
    """The four patterns that read a facet must match exactly what they matched before.

    Compared against the same evidence with its facet stripped, which forces the old
    summary-parsing path — so this is the before/after comparison, run in one process.
    """
    library = atlas_library()
    promoted = [
        *promoted_graph_changes(),
        *promoted_behaviour_departures(),
        *promoted_work_orders(),
    ]
    assert promoted

    def verdict(evidence: Evidence) -> set[tuple[str, str]]:
        """Return every ``(template, role)`` this fact earns.

        Role is included deliberately: a facet that flipped a supporting link to a contradictory
        one would be a moved reasoning outcome, not merely a different match.
        """
        return {
            (match.template.template_id, match.role.value)
            for match in library.matches(evidence, {})
        }

    for evidence in promoted:
        stripped = evidence.model_copy(update={"facet_kind": None, "facet": None})
        typed = verdict(evidence)
        parsed = verdict(stripped)
        assert typed == parsed, f"{evidence.facet_kind} verdict moved: {typed} != {parsed}"


def test_a_stamped_behaviour_departure_routes_through_the_typed_facet() -> None:
    """What the facet was for, now that it has a consumer (ADR 0071).

    ADR 0070 typed the stamp and deliberately wired no matcher, and this test pinned that. The
    matcher exists now, so what it pins is the property the refactor actually bought: the routing
    is reached through `facet_kind` / `facet`, not through the operator sentence. Stripping the
    facet leaves the marker, which still resolves — so the assertion that says which channel was
    read is `test_the_facet_is_authoritative_over_a_disagreeing_summary` in
    `tests/atlas/test_command_behaviour_pattern.py`, not this one.
    """
    library = atlas_library()
    for evidence in promoted_behaviour_departures():
        roles = {m.template.template_id: m.role for m in library.matches(evidence, {})}
        assert roles == {
            ENGINEERING_MAINTENANCE_TEMPLATE_ID: EvidenceRole.SUPPORTING,
            UNAUTHORISED_CONTROL_TEMPLATE_ID: EvidenceRole.SUPPORTING,
        }


def test_the_graph_finding_verdicts_are_the_ones_p3_recorded() -> None:
    """The equivalence test compares two paths; this one pins what they must both say.

    An unknown master supports unauthorised control and contradicts maintenance (ADR 0027); a
    known-link change supports both. Named here so a future edit to either path has to move a
    verdict this test spells out, rather than moving both paths together unnoticed.
    """
    library = atlas_library()
    by_feature = {e.facet: e for e in promoted_graph_changes()}

    unknown = library.matches(by_feature[UNKNOWN_COMMAND_RELATIONSHIP], {})
    roles = {m.template.template_id: m.role for m in unknown}
    assert roles[UNAUTHORISED_CONTROL_TEMPLATE_ID] is EvidenceRole.SUPPORTING
    assert roles[ENGINEERING_MAINTENANCE_TEMPLATE_ID] is EvidenceRole.CONTRADICTORY

    known = library.matches(by_feature[UNEXPECTED_COMMAND_FUNCTION], {})
    known_roles = {m.template.template_id: m.role for m in known}
    assert known_roles[UNAUTHORISED_CONTROL_TEMPLATE_ID] is EvidenceRole.SUPPORTING
    assert known_roles[ENGINEERING_MAINTENANCE_TEMPLATE_ID] is EvidenceRole.SUPPORTING


# ------------------------------------------------------------------------------------------------
# Authority: the facet decides, the summary does not
# ------------------------------------------------------------------------------------------------


def test_the_facet_wins_when_the_summary_marker_contradicts_it() -> None:
    """The robustness the refactor buys, and the only test that can see which channel was read.

    No promoter builds this: the two channels agree everywhere in the pipeline. It exists because
    a forged or reworded summary must no longer be able to move a reasoning outcome.
    """
    order = promoted_work_orders()[0]
    forged = order.model_copy(
        update={"summary": f"{GRAPH_FINDING_MARKER}{UNKNOWN_COMMAND_RELATIONSHIP}: forged"}
    )

    assert work_order_feature_of(forged) == WORK_ORDER_FEATURE
    assert graph_finding_feature_of(forged) is None
    assert _graph_finding_from_summary(forged) == UNKNOWN_COMMAND_RELATIONSHIP


def test_an_unrecognised_graph_facet_resolves_to_nothing() -> None:
    """A closed vocabulary stays closed: the typed path checks membership as the parse did."""
    graph = promoted_graph_changes()[0]
    invented = graph.model_copy(update={"facet": "invented_finding"})
    assert graph_finding_feature_of(invented) is None


# ------------------------------------------------------------------------------------------------
# Containment: no facet resolves exactly as before
# ------------------------------------------------------------------------------------------------


def test_evidence_with_no_facet_still_resolves_through_the_marker() -> None:
    """Hand-built fixtures predate the field and must not change behaviour."""
    for evidence in promoted_graph_changes():
        stripped = evidence.model_copy(update={"facet_kind": None, "facet": None})
        assert stripped.facet_kind is None
        assert graph_finding_feature_of(stripped) == evidence.facet


def test_a_malformed_marker_declares_nothing_on_the_fallback_path() -> None:
    """The pre-facet parse refused a marker it could not read, and still must.

    A prefix with no separator after the feature, and a graph prefix naming a feature outside the
    closed vocabulary. Both reach the fallback only when no facet is set, which is the shape a
    hand-built fixture has.
    """
    order = promoted_work_orders()[0]

    def bare(summary: str) -> Evidence:
        return order.model_copy(update={"facet_kind": None, "facet": None, "summary": summary})

    assert graph_finding_feature_of(bare(f"{GRAPH_FINDING_MARKER}no-separator")) is None
    assert graph_finding_feature_of(bare(f"{GRAPH_FINDING_MARKER}not_a_finding: body")) is None
    assert command_behaviour_feature_of(bare(f"{COMMAND_BEHAVIOUR_MARKER}no-separator")) is None
    assert command_behaviour_feature_of(bare(f"{COMMAND_BEHAVIOUR_MARKER}:empty")) is None
    assert work_order_feature_of(bare(f"{WORK_ORDER_MARKER}no-separator")) is None
    assert work_order_feature_of(bare(f"{WORK_ORDER_MARKER}:empty")) is None


def test_evidence_carrying_neither_channel_declares_nothing() -> None:
    order = promoted_work_orders()[0]
    bare = order.model_copy(
        update={"facet_kind": None, "facet": None, "summary": "a sentence with no marker"}
    )
    assert graph_finding_feature_of(bare) is None
    assert command_behaviour_feature_of(bare) is None
    assert work_order_feature_of(bare) is None


# ------------------------------------------------------------------------------------------------
# The field's own invariant
# ------------------------------------------------------------------------------------------------


def test_half_a_facet_is_refused() -> None:
    """A kind with no feature names nothing; a feature with no kind cannot be checked."""
    order = promoted_work_orders()[0]
    fields = order.model_dump()

    for update in ({"facet": None}, {"facet_kind": None}):
        with pytest.raises(ValueError, match="must be set together"):
            Evidence(**{**fields, **update})


def test_an_unnamed_feature_declares_no_facet_rather_than_raising() -> None:
    """`Observation.feature` has no length constraint, so an empty one always promoted.

    Before the facet existed it produced a marker like ``work-order::`` that the parser read back
    as ``None`` — the fact declared nothing. Adding the field must not turn that into a refusal.
    """
    unnamed = finding(WORK_ORDER_FEATURE, 1.0, index=0).model_copy(update={"feature": ""})
    promoted = promote_work_orders([unnamed], CERTAIN)[0].evidence

    assert promoted.facet_kind is None
    assert promoted.facet is None
    assert work_order_feature_of(promoted) is None
    assert _work_order_from_summary(promoted) is None


def test_a_fact_may_declare_no_facet_at_all() -> None:
    """``None`` means "declares no sub-kind", and must stay constructible."""
    order = promoted_work_orders()[0]
    fields = order.model_dump()
    bare = Evidence(**{**fields, "facet_kind": None, "facet": None})
    assert bare.facet_kind is None
    assert bare.facet is None

"""Session D2: command-bearing hypotheses reconstruct to a finding or stamped fact."""

from datetime import timedelta

from tests.atlas.test_command_evidence import (
    CERTAIN,
    DEVICE,
    finding,
    fitted_on_normal,
    steady_then_spike,
)

from phos.atlas import (
    UNKNOWN_COMMAND_RELATIONSHIP,
    command_behaviour_feature_of,
    graph_finding_feature_of,
    promote_command_behaviour,
    promote_graph_findings,
)
from phos.atlas.packet import UNEXPECTED_COMMAND_FUNCTION
from phos.atlas.reconstructability import walk_evidence_to_observation
from phos.atlas.templates import (
    ENGINEERING_MAINTENANCE_TEMPLATE_ID,
    UNAUTHORISED_CONTROL_TEMPLATE_ID,
    atlas_library,
)
from phos.ontology import InMemoryEvidenceStore
from phos.reasoning import ReasoningConfig, ReasoningEngine


def test_command_hypotheses_reconstruct_to_a_graph_finding_or_stamped_behaviour() -> None:
    training, live = steady_then_spike()
    departure = promote_command_behaviour(live, fitted_on_normal().fit(training), CERTAIN)[0]
    change = promote_graph_findings(
        [finding(UNKNOWN_COMMAND_RELATIONSHIP, 5.0, extra={"function_codes": "6"})], CERTAIN
    )[0]
    store = InMemoryEvidenceStore()
    store.add_observation(departure.observation)
    store.add_deviation(departure.deviation)
    store.add_observation(change.finding)
    store.add_evidence(departure.evidence)
    store.add_evidence(change.evidence)
    engine = ReasoningEngine(
        atlas_library(), store, ReasoningConfig(correlation_window=timedelta(hours=2))
    )
    engine.ingest([departure.evidence, change.evidence])

    walked = 0
    for hypothesis in engine.hypotheses():
        if hypothesis.template_id not in {
            UNAUTHORISED_CONTROL_TEMPLATE_ID,
            ENGINEERING_MAINTENANCE_TEMPLATE_ID,
        }:
            continue
        for evidence_id in (*hypothesis.supporting, *hypothesis.contradictory):
            evidence = store.get_evidence(evidence_id)
            assert evidence is not None
            stamped = graph_finding_feature_of(evidence) or command_behaviour_feature_of(evidence)
            assert stamped is not None or evidence_id == departure.evidence.id
            observations = walk_evidence_to_observation(evidence, store)
            assert observations
            walked += 1
    assert walked


def test_a_known_link_finding_still_reconstructs_to_the_observation() -> None:
    change = promote_graph_findings(
        [finding(UNEXPECTED_COMMAND_FUNCTION, 2.0, extra={"function_code": "6"})], CERTAIN
    )[0]
    store = InMemoryEvidenceStore()
    store.add_observation(change.finding)
    store.add_evidence(change.evidence)
    [observation] = walk_evidence_to_observation(change.evidence, store)
    assert observation.id == change.finding.id
    assert DEVICE in observation.entity_ids or observation.entity_ids

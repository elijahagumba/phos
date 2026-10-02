"""Tests for the reasoning engine, and for the whole PHOS reasoning loop end to end.

The acceptance criteria this file exists to hold are the ones that distinguish PHOS from an anomaly
detector: `test_a_well_supported_explanation_does_not_silence_the_alternatives` (the engine reports
competing explanations, it does not decide), `test_contradictory_evidence_moves_belief_between_two
_explanations` (belief moves both ways as observations accumulate), and
`test_the_whole_reasoning_loop_runs_on_synthetic_telemetry`, which drives the full chain — model,
deviation, out-of-band filter, calibrated evidence, competing hypotheses, narrative — and then
walks a displayed number back to the measurement it came from.
"""

import math
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import numpy
import pytest
from pydantic import ValidationError

from phos.models import GaussianBaseline
from phos.ontology import (
    Deviation,
    Domain,
    Entity,
    EntityId,
    EntityType,
    Evidence,
    EvidenceKind,
    ExpectedRange,
    Hypothesis,
    HypothesisStatus,
    InMemoryEvidenceStore,
    Observation,
)
from phos.reasoning.belief import reconstruct_confidence
from phos.reasoning.boundary import evidence_from_deviation, is_out_of_band
from phos.reasoning.calibration import IsotonicCalibrator
from phos.reasoning.engine import ReasoningConfig, ReasoningEngine
from phos.reasoning.templates import (
    GENERIC_ANOMALOUS_ACTIVITY_TEMPLATE_ID,
    GENERIC_BENIGN_CHANGE_TEMPLATE_ID,
    INSUFFICIENT_EVIDENCE_TEMPLATE_ID,
    EvidencePattern,
    HypothesisTemplate,
    TemplateLibrary,
    generic_library,
    generic_templates,
)

T0 = datetime(2026, 7, 30, 9, 0, tzinfo=UTC)
PLC = "ent_000000000001"
HMI = "ent_000000000002"
FEATURE = "flow_rate"

ANOMALOUS = GENERIC_ANOMALOUS_ACTIVITY_TEMPLATE_ID
BENIGN = GENERIC_BENIGN_CHANGE_TEMPLATE_ID
RESIDUAL = INSUFFICIENT_EVIDENCE_TEMPLATE_ID


def store_with_entities() -> InMemoryEvidenceStore:
    store = InMemoryEvidenceStore()
    store.add_entity(Entity(id=PLC, type=EntityType.PLC, domain=Domain.ATLAS, name="PLC-4"))
    store.add_entity(Entity(id=HMI, type=EntityType.HMI, domain=Domain.ATLAS, name="HMI-1"))
    return store


def engine(
    *,
    library: TemplateLibrary | None = None,
    config: ReasoningConfig | None = None,
    store: InMemoryEvidenceStore | None = None,
) -> ReasoningEngine:
    return ReasoningEngine(
        library=generic_library(Domain.ATLAS) if library is None else library,
        store=store_with_entities() if store is None else store,
        config=config,
    )


def evidence(
    kind: EvidenceKind = EvidenceKind.DEVIATION,
    *,
    weight: float = 0.8,
    at: datetime = T0,
    entity_ids: Sequence[EntityId] = (PLC,),
    domain: Domain = Domain.ATLAS,
) -> Evidence:
    return Evidence(
        kind=kind,
        source_id="dev_000000000001",
        entity_ids=list(entity_ids),
        timestamp=at,
        domain=domain,
        weight=weight,
        summary=f"{kind.value.lower()} on {entity_ids[0]}",
    )


def by_template(hypotheses: Sequence[Hypothesis]) -> dict[str, Hypothesis]:
    return {hypothesis.template_id: hypothesis for hypothesis in hypotheses}


# ------------------------------------------------------------------------------------------------
# Spawning and accumulation
# ------------------------------------------------------------------------------------------------


def test_before_any_observation_the_only_explanation_is_that_we_do_not_know() -> None:
    competing = engine().competing(Domain.ATLAS)

    assert [h.template_id for h in competing] == [RESIDUAL]
    assert competing[0].confidence == 0.30


def test_evidence_spawns_every_hypothesis_it_bears_on() -> None:
    reasoning = engine()

    reasoning.ingest([evidence(EvidenceKind.DEVIATION)])

    assert set(by_template(reasoning.competing(Domain.ATLAS))) == {ANOMALOUS, BENIGN, RESIDUAL}


def test_evidence_is_attached_in_the_role_the_template_gave_it() -> None:
    reasoning = engine()
    fact = evidence(EvidenceKind.DEVIATION)

    reasoning.ingest([fact])
    competing = by_template(reasoning.competing(Domain.ATLAS))

    assert competing[ANOMALOUS].supporting == [fact.id]
    assert competing[ANOMALOUS].contradictory == []
    assert competing[BENIGN].contradictory == [fact.id]
    assert competing[BENIGN].supporting == []
    assert competing[RESIDUAL].supporting == []
    assert competing[RESIDUAL].contradictory == []


def test_confidence_evolves_as_evidence_accumulates() -> None:
    reasoning = engine()
    history = []

    for index in range(4):
        reasoning.ingest([evidence(at=T0 + timedelta(minutes=index))])
        history.append(by_template(reasoning.competing(Domain.ATLAS))[ANOMALOUS].confidence)

    assert history == sorted(history)
    assert history[0] > 0.10  # its prior
    assert history[-1] > history[0]


def test_the_same_fact_delivered_twice_is_weighed_once() -> None:
    """A redelivered id is the same fact, and counting it twice would invent support."""
    reasoning = engine()
    fact = evidence()

    reasoning.ingest([fact])
    once = by_template(reasoning.competing(Domain.ATLAS))[ANOMALOUS]
    reasoning.ingest([fact])
    twice = by_template(reasoning.competing(Domain.ATLAS))[ANOMALOUS]

    assert twice.confidence == once.confidence
    assert twice.supporting == [fact.id]


def test_evidence_no_template_explains_leaves_the_residual_alone_in_the_set() -> None:
    """Nothing on offer accounts for this — which is a real answer, not an empty one."""
    library = TemplateLibrary(
        templates=(
            HypothesisTemplate(
                template_id="only_relationship_changes",
                label="Only relationship changes",
                domain=Domain.ATLAS,
                prior=0.2,
                supported_by=(EvidencePattern(kinds=(EvidenceKind.RELATIONSHIP_CHANGE,)),),
            ),
        )
    )
    reasoning = engine(library=library)

    reasoning.ingest([evidence(EvidenceKind.DEVIATION)])
    competing = reasoning.competing(Domain.ATLAS)

    assert [h.template_id for h in competing] == [RESIDUAL]


def test_the_engine_refuses_anything_that_is_not_evidence() -> None:
    """4A guarantees this upstream; the engine's door is where an untyped caller meets it.

    The API (PART 8) will hand this engine objects rebuilt from JSON, so the type that carries the
    evidence boundary has to be checked at runtime and not only by mypy.
    """
    candidate = Deviation(
        observation_id="obs_000000000001",
        expected=ExpectedRange(
            feature=FEATURE,
            entity_id=PLC,
            low=4.0,
            high=16.0,
            mean=10.0,
            stddev=2.0,
            learned_from_window=(T0 - timedelta(hours=1), T0),
        ),
        magnitude=5.0,
        timestamp=T0,
    )

    with pytest.raises(TypeError, match="only Evidence"):
        engine().ingest([candidate])  # type: ignore[list-item]


# ------------------------------------------------------------------------------------------------
# Competing explanations never collapse — the criterion PHOS exists for
# ------------------------------------------------------------------------------------------------


def test_a_well_supported_explanation_does_not_silence_the_alternatives() -> None:
    """The engine reports; it does not decide.

    After three strong, agreeing observations one explanation clearly leads — and the other two are
    still on the table with their own confidences, including "we do not know". A system that
    collapsed to the winner here would be an alerting tool with extra steps.
    """
    reasoning = engine()

    reasoning.ingest([evidence(weight=0.8, at=T0 + timedelta(minutes=index)) for index in range(3)])
    competing = reasoning.competing(Domain.ATLAS)

    assert [h.template_id for h in competing] == [ANOMALOUS, RESIDUAL, BENIGN]
    assert competing[0].confidence > competing[1].confidence > competing[2].confidence
    assert all(0.0 < h.confidence < 1.0 for h in competing)


def test_the_residual_is_in_every_competing_set() -> None:
    reasoning = engine()

    for index in range(10):
        reasoning.ingest([evidence(weight=1.0, at=T0 + timedelta(minutes=index))])

    competing = reasoning.competing(Domain.ATLAS)
    assert RESIDUAL in by_template(competing)
    assert competing[0].template_id == ANOMALOUS
    assert competing[0].confidence < 1.0


def _saturating_rivals() -> TemplateLibrary:
    """Two explanations that match the same evidence and differ only by prior.

    Enough fully-trusted observations pin both at the log-odds ceiling. Alphabetical order
    would then name `engineering_maintenance` the unique leader; the engine must refuse.
    """
    return TemplateLibrary(
        templates=(
            HypothesisTemplate(
                template_id="engineering_maintenance",
                label="Engineering maintenance",
                domain=Domain.ATLAS,
                prior=0.20,
                supported_by=(EvidencePattern(kinds=(EvidenceKind.DEVIATION,)),),
            ),
            HypothesisTemplate(
                template_id="unauthorised_control_activity",
                label="Unauthorised control activity",
                domain=Domain.ATLAS,
                prior=0.10,
                supported_by=(EvidencePattern(kinds=(EvidenceKind.DEVIATION,)),),
            ),
        )
    )


def test_saturated_rivals_raise_insufficient_evidence_rather_than_an_alphabetical_winner() -> None:
    """The product sells the right to remain silent when the ceiling is shared."""
    reasoning = engine(library=_saturating_rivals())
    reasoning.ingest([evidence(weight=1.0, at=T0) for _ in range(40)])

    competing = reasoning.competing(Domain.ATLAS)
    ids = [hypothesis.template_id for hypothesis in competing]

    assert ids[0] == RESIDUAL
    assert "engineering_maintenance" in ids
    assert "unauthorised_control_activity" in ids
    assert ids.index("engineering_maintenance") < ids.index("unauthorised_control_activity")
    assert competing[0].confidence < competing[ids.index("engineering_maintenance")].confidence
    assert math.isclose(
        competing[ids.index("engineering_maintenance")].confidence,
        competing[ids.index("unauthorised_control_activity")].confidence,
        abs_tol=1e-9,
    )


def test_a_tied_narrative_is_led_by_the_residual() -> None:
    reasoning = engine(library=_saturating_rivals())
    reasoning.ingest([evidence(weight=1.0, at=T0) for _ in range(40)])

    story = reasoning.narratives()[0]
    residual = by_template(reasoning.competing(Domain.ATLAS))[RESIDUAL]

    assert story.hypothesis_ids[0] == residual.id
    assert story.overall_confidence is None
    assert "insufficient" in story.title.lower()


def test_tied_ranking_is_deterministic_across_calls() -> None:
    reasoning = engine(library=_saturating_rivals())
    reasoning.ingest([evidence(weight=1.0, at=T0) for _ in range(40)])

    first = [hypothesis.template_id for hypothesis in reasoning.competing(Domain.ATLAS)]
    second = [hypothesis.template_id for hypothesis in reasoning.competing(Domain.ATLAS)]

    assert first == second
    assert first[0] == RESIDUAL


def test_contradictory_evidence_moves_belief_between_two_explanations() -> None:
    """Evidence that argues the other way pulls belief back, and both explanations survive it."""
    reasoning = engine()

    reasoning.ingest([evidence(weight=0.9, at=T0 + timedelta(minutes=index)) for index in range(2)])
    before = by_template(reasoning.competing(Domain.ATLAS))

    change = evidence(EvidenceKind.RELATIONSHIP_CHANGE, weight=0.9, at=T0 + timedelta(minutes=3))
    reasoning.ingest([change])
    after = by_template(reasoning.competing(Domain.ATLAS))

    assert after[ANOMALOUS].confidence < before[ANOMALOUS].confidence
    assert after[BENIGN].confidence > before[BENIGN].confidence
    assert after[ANOMALOUS].contradictory == [change.id]
    assert after[BENIGN].supporting == [change.id]
    assert len(after[ANOMALOUS].supporting) == 2
    assert len(after[BENIGN].contradictory) == 2


# ------------------------------------------------------------------------------------------------
# Pruning and the sliding window
# ------------------------------------------------------------------------------------------------


def test_an_implausible_explanation_is_marked_rather_than_removed() -> None:
    """Pruning is a judgement, not a deletion: "considered and does not fit" is worth showing."""
    reasoning = engine()

    reasoning.ingest([evidence(weight=1.0, at=T0 + timedelta(minutes=index)) for index in range(4)])
    competing = by_template(reasoning.competing(Domain.ATLAS))

    assert competing[BENIGN].status is HypothesisStatus.PRUNED
    assert competing[BENIGN].confidence < 0.02
    assert competing[BENIGN].contradictory != []
    assert competing[ANOMALOUS].status is HypothesisStatus.ACTIVE


def test_a_pruned_explanation_can_be_revived_by_later_evidence() -> None:
    """The status is a current reading of the evidence, not a tombstone."""
    reasoning = engine()
    reasoning.ingest([evidence(weight=1.0, at=T0 + timedelta(minutes=index)) for index in range(4)])
    assert by_template(reasoning.competing(Domain.ATLAS))[BENIGN].status is HypothesisStatus.PRUNED

    reasoning.ingest(
        [
            evidence(EvidenceKind.RELATIONSHIP_CHANGE, weight=1.0, at=T0 + timedelta(minutes=5)),
            evidence(EvidenceKind.RELATIONSHIP_CHANGE, weight=1.0, at=T0 + timedelta(minutes=6)),
            evidence(EvidenceKind.RELATIONSHIP_CHANGE, weight=1.0, at=T0 + timedelta(minutes=7)),
        ]
    )

    assert by_template(reasoning.competing(Domain.ATLAS))[BENIGN].status is HypothesisStatus.ACTIVE


def test_evidence_from_another_time_starts_a_fresh_hypothesis() -> None:
    """Confidence must not accumulate across unrelated hours.

    Two bursts a day apart are two incidents. Letting the second continue the first's hypothesis
    would report a confidence built from evidence no operator would call the same story.
    """
    reasoning = engine(config=ReasoningConfig(correlation_window=timedelta(minutes=30)))

    reasoning.ingest([evidence(weight=0.9, at=T0)])
    first = by_template(reasoning.competing(Domain.ATLAS))[ANOMALOUS]
    reasoning.ingest([evidence(weight=0.9, at=T0 + timedelta(days=1))])
    second = by_template(reasoning.competing(Domain.ATLAS))[ANOMALOUS]

    assert second.id != first.id
    assert second.confidence == pytest.approx(first.confidence)
    assert len(second.supporting) == 1
    assert [h.id for h in reasoning.hypotheses(Domain.ATLAS)].count(first.id) == 1


def test_an_explanation_whose_evidence_went_quiet_leaves_the_current_set() -> None:
    """It stays in history; it stops being something the operator is asked to weigh right now."""
    library = TemplateLibrary(
        templates=(
            HypothesisTemplate(
                template_id="misses_only",
                label="Forecast misses",
                domain=Domain.ATLAS,
                prior=0.2,
                supported_by=(EvidencePattern(kinds=(EvidenceKind.FORECAST_MISS,)),),
            ),
            HypothesisTemplate(
                template_id="changes_only",
                label="Relationship changes",
                domain=Domain.ATLAS,
                prior=0.2,
                supported_by=(EvidencePattern(kinds=(EvidenceKind.RELATIONSHIP_CHANGE,)),),
            ),
        )
    )
    reasoning = engine(library=library)

    reasoning.ingest([evidence(EvidenceKind.FORECAST_MISS, at=T0)])
    reasoning.ingest([evidence(EvidenceKind.RELATIONSHIP_CHANGE, at=T0 + timedelta(days=1))])

    assert set(by_template(reasoning.competing(Domain.ATLAS))) == {"changes_only", RESIDUAL}
    assert set(by_template(reasoning.hypotheses(Domain.ATLAS))) == {
        "misses_only",
        "changes_only",
        RESIDUAL,
    }


def test_the_engine_rejects_a_window_that_would_isolate_every_fact() -> None:
    with pytest.raises(ValidationError, match="positive duration"):
        ReasoningConfig(correlation_window=timedelta(0))


def test_two_domains_never_share_a_competing_set_or_a_story() -> None:
    """4B narratives are single-domain. Correlating Atlas with Sentiel is PART 7's job.

    Both facts name the same entity id and arrive a minute apart, so only the domain keeps them
    apart — which is the check worth having, since everything else about them co-occurs.
    """
    library = generic_library(Domain.ATLAS).with_templates(generic_templates(Domain.SENTIEL))
    reasoning = engine(library=library)

    reasoning.ingest(
        [
            evidence(weight=0.9, at=T0, domain=Domain.ATLAS),
            evidence(weight=0.9, at=T0 + timedelta(minutes=1), domain=Domain.SENTIEL),
        ]
    )

    atlas = reasoning.competing(Domain.ATLAS)
    sentiel = reasoning.competing(Domain.SENTIEL)
    assert {h.domain for h in atlas} == {Domain.ATLAS}
    assert {h.domain for h in sentiel} == {Domain.SENTIEL}
    assert not {h.id for h in atlas} & {h.id for h in sentiel}

    narratives = reasoning.narratives()
    assert [story.domain for story in narratives] == [Domain.ATLAS, Domain.SENTIEL]
    assert all(len(story.evidence_ids) == 1 for story in narratives)


def test_history_outlives_the_window() -> None:
    reasoning = engine(config=ReasoningConfig(correlation_window=timedelta(minutes=30)))

    reasoning.ingest([evidence(at=T0), evidence(at=T0 + timedelta(days=1))])

    competing = reasoning.competing(Domain.ATLAS)
    everything = reasoning.hypotheses(Domain.ATLAS)
    assert len(competing) == 3
    assert len(everything) == 5  # the residual, plus two hypotheses per burst


# ------------------------------------------------------------------------------------------------
# Traceability and determinism
# ------------------------------------------------------------------------------------------------


def test_every_confidence_the_engine_reports_can_be_rebuilt_from_its_evidence() -> None:
    """Constitution §3.2, enforced over everything the engine produced rather than one case."""
    reasoning = engine()
    facts = [
        evidence(EvidenceKind.DEVIATION, weight=0.7, at=T0),
        evidence(EvidenceKind.SEQUENCE_ANOMALY, weight=0.5, at=T0 + timedelta(minutes=2)),
        evidence(EvidenceKind.RELATIONSHIP_CHANGE, weight=0.9, at=T0 + timedelta(minutes=4)),
    ]
    reasoning.ingest(facts)
    lookup = {fact.id: fact for fact in facts}

    for hypothesis in reasoning.hypotheses(Domain.ATLAS):
        assert math.isclose(reconstruct_confidence(hypothesis, lookup), hypothesis.confidence), (
            f"{hypothesis.template_id} reports a confidence its evidence does not explain"
        )


def test_the_same_evidence_in_the_same_order_gives_the_same_answers() -> None:
    """Determinism: nothing here may depend on identity, hashing or wall-clock."""
    facts = [
        evidence(EvidenceKind.DEVIATION, weight=0.7, at=T0),
        evidence(EvidenceKind.RELATIONSHIP_CHANGE, weight=0.4, at=T0 + timedelta(minutes=1)),
        evidence(EvidenceKind.FORECAST_MISS, weight=0.6, at=T0 + timedelta(minutes=2)),
    ]

    def run() -> list[tuple[str, float, HypothesisStatus, int, int]]:
        reasoning = engine()
        reasoning.ingest(facts)
        return [
            (h.template_id, h.confidence, h.status, len(h.supporting), len(h.contradictory))
            for h in reasoning.competing(Domain.ATLAS)
        ]

    assert run() == run()


def test_hypotheses_serialise() -> None:
    reasoning = engine()
    reasoning.ingest([evidence()])

    for hypothesis in reasoning.hypotheses():
        assert Hypothesis.model_validate_json(hypothesis.model_dump_json()) == hypothesis


# ------------------------------------------------------------------------------------------------
# Narratives
# ------------------------------------------------------------------------------------------------


def test_related_evidence_becomes_one_narrative() -> None:
    reasoning = engine()
    facts = [evidence(weight=0.8, at=T0 + timedelta(minutes=index)) for index in range(3)]
    reasoning.ingest(facts)

    narratives = reasoning.narratives()

    assert len(narratives) == 1
    story = narratives[0]
    assert story.domain is Domain.ATLAS
    assert story.evidence_ids == [fact.id for fact in facts]
    told = [h for h in reasoning.hypotheses() if h.id in story.hypothesis_ids]
    assert set(by_template(told)) == {ANOMALOUS, BENIGN, RESIDUAL}


def test_a_narrative_leads_with_its_strongest_explanation_and_keeps_the_rest() -> None:
    reasoning = engine()
    reasoning.ingest([evidence(weight=0.8, at=T0 + timedelta(minutes=index)) for index in range(3)])

    story = reasoning.narratives()[0]
    leading = by_template(reasoning.competing(Domain.ATLAS))[ANOMALOUS]

    assert story.overall_confidence is None
    assert leading.label in story.title
    assert len(story.hypothesis_ids) == 3


def test_causal_edges_run_from_evidence_to_explanation_in_time_order() -> None:
    reasoning = engine()
    early = evidence(weight=0.8, at=T0)
    late = evidence(weight=0.8, at=T0 + timedelta(minutes=5))
    reasoning.ingest([late, early])  # out of order on purpose

    story = reasoning.narratives()[0]
    sources = [source for source, _ in story.causal_edges]

    assert sources.index(early.id) < sources.index(late.id)
    assert all(target in story.hypothesis_ids for _, target in story.causal_edges)
    assert {source for source, _ in story.causal_edges} == {early.id, late.id}


def test_causal_edges_are_reconstructable_from_stored_evidence_lists() -> None:
    """Constitution §3.2: every edge is a bearing already recorded on a stored hypothesis."""
    reasoning = engine()
    facts = [evidence(weight=0.8, at=T0), evidence(weight=0.8, at=T0 + timedelta(minutes=5))]
    reasoning.ingest(facts)

    story = reasoning.narratives()[0]
    by_id = {hypothesis.id: hypothesis for hypothesis in reasoning.hypotheses()}

    assert story.causal_edges
    for source, target in story.causal_edges:
        assert source in story.evidence_ids
        assert target in story.hypothesis_ids
        hypothesis = by_id[target]
        assert source in {*hypothesis.supporting, *hypothesis.contradictory}


def test_unrelated_incidents_are_separate_stories() -> None:
    """Different equipment, different day: two narratives, not one long one."""
    reasoning = engine(config=ReasoningConfig(correlation_window=timedelta(minutes=30)))

    reasoning.ingest(
        [
            evidence(weight=0.8, at=T0, entity_ids=[PLC]),
            evidence(weight=0.8, at=T0 + timedelta(days=1), entity_ids=[HMI]),
        ]
    )

    narratives = reasoning.narratives()
    assert len(narratives) == 2
    assert [len(story.evidence_ids) for story in narratives] == [1, 1]


def test_a_narrative_holds_all_the_evidence_its_explanations_rest_on() -> None:
    """Otherwise a displayed confidence could not be rebuilt from the story shown beside it.

    These two facts share no entity, so co-occurrence alone would split them — but one hypothesis
    accumulated both, so the story that shows that hypothesis's confidence must show both.
    """
    reasoning = engine()
    reasoning.ingest(
        [
            evidence(weight=0.8, at=T0, entity_ids=[PLC]),
            evidence(weight=0.8, at=T0 + timedelta(minutes=1), entity_ids=[HMI]),
        ]
    )

    narratives = reasoning.narratives()

    assert len(narratives) == 1
    assert len(narratives[0].evidence_ids) == 2


def test_a_story_nothing_explains_well_is_led_by_the_residual() -> None:
    """One observation is not an incident, and the engine says so rather than picking a favourite.

    A single piece of evidence lifts "anomalous activity" above its prior but nowhere near the
    residual, so the story an operator reads is led by "we do not know yet" — with the two
    explanations listed underneath it. This also exercises a domain other than Atlas.
    """
    reasoning = engine(library=TemplateLibrary(templates=generic_templates(Domain.SENTIEL)))

    reasoning.ingest([evidence(EvidenceKind.DEVIATION, weight=0.8, domain=Domain.SENTIEL)])
    story = reasoning.narratives()[0]
    leading = by_template(reasoning.competing(Domain.SENTIEL))[RESIDUAL]

    assert story.domain is Domain.SENTIEL
    assert story.hypothesis_ids[0] == leading.id
    assert story.overall_confidence is None
    assert RESIDUAL in story.title.lower() or "insufficient" in story.title.lower()
    assert len(story.hypothesis_ids) == 3
    assert story.causal_edges != []


def test_narratives_resolve_through_the_store_and_serialise() -> None:
    store = store_with_entities()
    reasoning = engine(store=store)
    facts = [evidence(weight=0.8, at=T0 + timedelta(minutes=index)) for index in range(2)]
    reasoning.ingest(facts)
    for fact in facts:
        store.add_evidence(fact)
    for hypothesis in reasoning.hypotheses():
        store.add_hypothesis(hypothesis)

    story = reasoning.narratives()[0]
    store.add_narrative(story)

    assert [item.id for item in story.timeline(store)] == [fact.id for fact in facts]
    assert store.get_narrative(story.id) == story


def test_an_engine_that_has_seen_nothing_tells_no_stories() -> None:
    assert engine().narratives() == []


# ------------------------------------------------------------------------------------------------
# The whole loop, on telemetry a model actually scored
# ------------------------------------------------------------------------------------------------


def observation(value: float, at: datetime, entity: EntityId = PLC) -> Observation:
    return Observation(
        entity_ids=[entity],
        feature=FEATURE,
        value=value,
        timestamp=at,
        domain=Domain.ATLAS,
    )


def test_the_whole_reasoning_loop_runs_on_synthetic_telemetry() -> None:
    """Measurement to narrative, with every link in the chain the real one.

    PART 3 learns normal and emits candidates; 4A refuses the candidates that never left their
    expected range and calibrates the survivors' weights against labels; 4B turns those into
    competing explanations and one story. Then the last assertions walk a displayed number
    backwards — narrative to evidence to deviation to the observation that produced it — which is
    the chain Constitution §3.2 demands and the reason none of these layers may be skipped.
    """
    store = store_with_entities()
    normal = [
        observation(10.0 + 0.1 * ((index % 7) - 3), T0 + timedelta(minutes=index))
        for index in range(60)
    ]
    disturbed = [
        observation(30.0 + index, T0 + timedelta(minutes=60 + index)) for index in range(3)
    ]
    for measurement in (*normal, *disturbed):
        store.add_observation(measurement)

    fitted = GaussianBaseline().fit(normal)
    candidates = fitted.score([*normal, *disturbed])
    for candidate in candidates:
        store.add_deviation(candidate)
    observations = {measurement.id: measurement for measurement in (*normal, *disturbed)}
    attacks = {measurement.id for measurement in disturbed}

    # 4A: labels come from the corpus, weights come from a calibrator fitted on them.
    scores = numpy.array([candidate.magnitude for candidate in candidates])
    labels = numpy.array([float(candidate.observation_id in attacks) for candidate in candidates])
    weights = IsotonicCalibrator().fit(scores, labels).calibrate(scores)

    facts = [
        evidence_from_deviation(
            candidate,
            observations[candidate.observation_id],
            float(weight),
            summary=f"{FEATURE} outside its learned range",
        )
        for candidate, weight in zip(candidates, weights, strict=True)
        if is_out_of_band(candidate, observations[candidate.observation_id])
    ]
    for fact in facts:
        store.add_evidence(fact)

    assert len(facts) == len(disturbed), "only the genuine departures should become evidence"
    assert all(0.0 <= fact.weight <= 1.0 for fact in facts)

    # 4B: competing explanations and one story.
    reasoning = ReasoningEngine(library=generic_library(Domain.ATLAS), store=store)
    reasoning.ingest(facts)

    competing = reasoning.competing(Domain.ATLAS)
    assert competing[0].template_id == ANOMALOUS
    assert set(by_template(competing)) == {ANOMALOUS, BENIGN, RESIDUAL}
    assert competing[0].confidence > competing[0].prior
    assert competing[0].confidence < 1.0

    narratives = reasoning.narratives()
    assert len(narratives) == 1
    story = narratives[0]
    assert story.overall_confidence is None

    for hypothesis in reasoning.hypotheses():
        store.add_hypothesis(hypothesis)
    store.add_narrative(story)

    # The walk back: story -> evidence -> deviation -> observation -> outside its learned range.
    timeline = story.timeline(store)
    assert [fact.id for fact in timeline] == [fact.id for fact in facts]
    for fact in timeline:
        source = store.get_deviation(fact.source_id)
        assert source is not None
        origin = store.get_observation(source.observation_id)
        assert origin is not None
        assert not source.expected.contains(origin.value)

    leading = store.get_hypothesis(story.hypothesis_ids[0])
    assert leading is not None
    assert story.overall_confidence is None
    supporting, _ = store.evidence_for(leading.id)
    assert math.isclose(
        reconstruct_confidence(leading, {fact.id: fact for fact in supporting}),
        leading.confidence,
    )

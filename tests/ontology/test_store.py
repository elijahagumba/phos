"""Tests for the EvidenceStore protocol and its in-memory implementation.

The final test in this module is the PART 1 end-to-end acceptance fixture: it hand-builds the
Atlas worked example (no detection logic anywhere) to prove the ontology can represent real
product output before any engine exists.
"""

from datetime import UTC, datetime

import pytest

from phos.ontology import (
    Deviation,
    Domain,
    Entity,
    EntityType,
    Evidence,
    EvidenceKind,
    EvidenceRole,
    EvidenceStore,
    ExpectedRange,
    Hypothesis,
    HypothesisStatus,
    InMemoryEvidenceStore,
    Narrative,
    Observation,
)

T0 = datetime(2026, 1, 15, 9, 0, tzinfo=UTC)
T1 = datetime(2026, 1, 15, 10, 0, tzinfo=UTC)
T2 = datetime(2026, 1, 15, 11, 0, tzinfo=UTC)


def make_entity(entity_id: str, domain: Domain = Domain.ATLAS) -> Entity:
    entity_type = EntityType.PLC if domain is Domain.ATLAS else EntityType.USER
    return Entity(id=entity_id, type=entity_type, domain=domain, name=entity_id, created_at=T0)


def make_observation(observation_id: str, domain: Domain = Domain.ATLAS) -> Observation:
    return Observation(
        id=observation_id,
        entity_ids=["ent_1"],
        feature="interpacket_interval_ms",
        value=48.0,
        timestamp=T0,
        domain=domain,
    )


def make_expected_range() -> ExpectedRange:
    return ExpectedRange(
        feature="interpacket_interval_ms",
        entity_id="ent_1",
        low=95.0,
        high=105.0,
        mean=100.0,
        stddev=2.0,
        learned_from_window=(T0, T1),
    )


def make_deviation(deviation_id: str, observation_id: str) -> Deviation:
    return Deviation(
        id=deviation_id,
        observation_id=observation_id,
        expected=make_expected_range(),
        magnitude=26.0,
        timestamp=T0,
    )


def make_evidence(
    evidence_id: str,
    source_id: str = "dev_1",
    domain: Domain = Domain.ATLAS,
    timestamp: datetime = T0,
) -> Evidence:
    return Evidence(
        id=evidence_id,
        kind=EvidenceKind.DEVIATION,
        source_id=source_id,
        entity_ids=["ent_1"],
        timestamp=timestamp,
        domain=domain,
        summary=f"summary for {evidence_id}",
    )


def make_hypothesis(
    hypothesis_id: str,
    supporting: list[str] | None = None,
    contradictory: list[str] | None = None,
    domain: Domain = Domain.ATLAS,
) -> Hypothesis:
    return Hypothesis(
        id=hypothesis_id,
        label=f"label for {hypothesis_id}",
        template_id="atlas.template",
        domain=domain,
        prior=0.2,
        confidence=0.2,
        status=HypothesisStatus.ACTIVE,
        supporting=supporting or [],
        contradictory=contradictory or [],
        created_at=T0,
        updated_at=T0,
    )


def make_narrative(
    narrative_id: str,
    hypothesis_ids: list[str] | None = None,
    evidence_ids: list[str] | None = None,
    domain: Domain = Domain.INTELLIGENCE,
) -> Narrative:
    return Narrative(
        id=narrative_id,
        title=f"title for {narrative_id}",
        domain=domain,
        hypothesis_ids=hypothesis_ids or [],
        evidence_ids=evidence_ids or [],
        overall_confidence=0.5,
        created_at=T0,
        updated_at=T0,
    )


def test_in_memory_store_satisfies_the_protocol() -> None:
    store: EvidenceStore = InMemoryEvidenceStore()
    assert isinstance(store, EvidenceStore)


class TestAddAndGet:
    def test_round_trips_every_object_type(self) -> None:
        store = InMemoryEvidenceStore()
        entity = make_entity("ent_1")
        observation = make_observation("obs_1")
        deviation = make_deviation("dev_1", "obs_1")
        evidence = make_evidence("ev_1")
        hypothesis = make_hypothesis("hyp_1", supporting=["ev_1"])
        narrative = make_narrative("nar_1", hypothesis_ids=["hyp_1"], evidence_ids=["ev_1"])

        store.add_entity(entity)
        store.add_observation(observation)
        store.add_deviation(deviation)
        store.add_evidence(evidence)
        store.add_hypothesis(hypothesis)
        store.add_narrative(narrative)

        assert store.get_entity("ent_1") == entity
        assert store.get_observation("obs_1") == observation
        assert store.get_deviation("dev_1") == deviation
        assert store.get_evidence("ev_1") == evidence
        assert store.get_hypothesis("hyp_1") == hypothesis
        assert store.get_narrative("nar_1") == narrative

    def test_get_returns_none_for_unknown_ids(self) -> None:
        store = InMemoryEvidenceStore()
        assert store.get_entity("ent_missing") is None
        assert store.get_observation("obs_missing") is None
        assert store.get_deviation("dev_missing") is None
        assert store.get_evidence("ev_missing") is None
        assert store.get_hypothesis("hyp_missing") is None
        assert store.get_narrative("nar_missing") is None

    def test_rejects_duplicate_ids(self) -> None:
        store = InMemoryEvidenceStore()
        store.add_entity(make_entity("ent_1"))
        with pytest.raises(ValueError, match="ent_1"):
            store.add_entity(make_entity("ent_1"))


class TestReferentialIntegrity:
    def test_deviation_with_unknown_observation_raises(self) -> None:
        store = InMemoryEvidenceStore()
        with pytest.raises(ValueError, match="obs_missing"):
            store.add_deviation(make_deviation("dev_1", "obs_missing"))
        assert store.get_deviation("dev_1") is None

    def test_deviation_in_correct_order_succeeds(self) -> None:
        store = InMemoryEvidenceStore()
        store.add_observation(make_observation("obs_1"))
        store.add_deviation(make_deviation("dev_1", "obs_1"))
        assert store.get_deviation("dev_1") is not None

    def test_hypothesis_with_unknown_supporting_evidence_raises(self) -> None:
        store = InMemoryEvidenceStore()
        with pytest.raises(ValueError, match="ev_missing"):
            store.add_hypothesis(make_hypothesis("hyp_1", supporting=["ev_missing"]))

    def test_hypothesis_with_unknown_contradictory_evidence_raises(self) -> None:
        store = InMemoryEvidenceStore()
        store.add_evidence(make_evidence("ev_1"))
        with pytest.raises(ValueError, match="ev_missing"):
            store.add_hypothesis(
                make_hypothesis("hyp_1", supporting=["ev_1"], contradictory=["ev_missing"])
            )

    def test_hypothesis_in_correct_order_succeeds(self) -> None:
        store = InMemoryEvidenceStore()
        store.add_evidence(make_evidence("ev_1"))
        store.add_evidence(make_evidence("ev_2"))
        store.add_hypothesis(make_hypothesis("hyp_1", supporting=["ev_1"], contradictory=["ev_2"]))
        assert store.get_hypothesis("hyp_1") is not None

    def test_narrative_with_unknown_references_raises(self) -> None:
        store = InMemoryEvidenceStore()
        store.add_evidence(make_evidence("ev_1"))
        with pytest.raises(ValueError, match="hyp_missing"):
            store.add_narrative(make_narrative("nar_1", hypothesis_ids=["hyp_missing"]))
        with pytest.raises(ValueError, match="ev_missing"):
            store.add_narrative(make_narrative("nar_1", evidence_ids=["ev_missing"]))

    def test_narrative_with_causal_edge_outside_its_story_raises(self) -> None:
        """Causal edges must resolve from the narrative's own stored evidence and hypotheses."""
        store = InMemoryEvidenceStore()
        store.add_evidence(make_evidence("ev_1"))
        store.add_evidence(make_evidence("ev_other"))
        store.add_hypothesis(make_hypothesis("hyp_1", supporting=["ev_1"]))
        stray = Narrative(
            id="nar_1",
            title="stray edge",
            domain=Domain.ATLAS,
            hypothesis_ids=["hyp_1"],
            evidence_ids=["ev_1"],
            overall_confidence=0.5,
            causal_edges=[("ev_other", "hyp_1")],
            created_at=T0,
            updated_at=T0,
        )
        with pytest.raises(ValueError, match="ev_other"):
            store.add_narrative(stray)


class TestQueries:
    def test_entities_filter_by_domain_and_preserve_insertion_order(self) -> None:
        store = InMemoryEvidenceStore()
        for entity_id, domain in (
            ("ent_3", Domain.ATLAS),
            ("ent_1", Domain.SENTIEL),
            ("ent_2", Domain.ATLAS),
        ):
            store.add_entity(make_entity(entity_id, domain))

        assert [e.id for e in store.entities()] == ["ent_3", "ent_1", "ent_2"]
        assert [e.id for e in store.entities(Domain.ATLAS)] == ["ent_3", "ent_2"]
        assert [e.id for e in store.entities(Domain.SENTIEL)] == ["ent_1"]
        assert store.entities(Domain.INTELLIGENCE) == []

    def test_observations_filter_by_domain(self) -> None:
        store = InMemoryEvidenceStore()
        store.add_observation(make_observation("obs_1", Domain.ATLAS))
        store.add_observation(make_observation("obs_2", Domain.SENTIEL))
        assert [o.id for o in store.observations(Domain.SENTIEL)] == ["obs_2"]
        assert len(store.observations()) == 2

    def test_deviations_preserve_insertion_order(self) -> None:
        store = InMemoryEvidenceStore()
        store.add_observation(make_observation("obs_1"))
        store.add_deviation(make_deviation("dev_2", "obs_1"))
        store.add_deviation(make_deviation("dev_1", "obs_1"))
        assert [d.id for d in store.deviations()] == ["dev_2", "dev_1"]

    def test_evidence_filters_by_domain(self) -> None:
        store = InMemoryEvidenceStore()
        store.add_evidence(make_evidence("ev_1", domain=Domain.ATLAS))
        store.add_evidence(make_evidence("ev_2", domain=Domain.SENTIEL))
        assert [e.id for e in store.evidence(Domain.ATLAS)] == ["ev_1"]
        assert [e.id for e in store.evidence()] == ["ev_1", "ev_2"]

    def test_hypotheses_and_narratives_filter_by_domain(self) -> None:
        store = InMemoryEvidenceStore()
        store.add_hypothesis(make_hypothesis("hyp_1", domain=Domain.ATLAS))
        store.add_hypothesis(make_hypothesis("hyp_2", domain=Domain.SENTIEL))
        store.add_narrative(make_narrative("nar_1", domain=Domain.INTELLIGENCE))
        store.add_narrative(make_narrative("nar_2", domain=Domain.ATLAS))

        assert [h.id for h in store.hypotheses(Domain.SENTIEL)] == ["hyp_2"]
        assert [h.id for h in store.hypotheses()] == ["hyp_1", "hyp_2"]
        assert [n.id for n in store.narratives(Domain.INTELLIGENCE)] == ["nar_1"]
        assert [n.id for n in store.narratives()] == ["nar_1", "nar_2"]

    def test_query_results_are_copies(self) -> None:
        store = InMemoryEvidenceStore()
        store.add_entity(make_entity("ent_1"))
        store.entities().clear()
        assert len(store.entities()) == 1


class TestEvidenceFor:
    def test_resolves_both_lists_in_order(self) -> None:
        store = InMemoryEvidenceStore()
        for evidence_id in ("ev_1", "ev_2", "ev_3"):
            store.add_evidence(make_evidence(evidence_id))
        store.add_hypothesis(
            make_hypothesis("hyp_1", supporting=["ev_3", "ev_1"], contradictory=["ev_2"])
        )

        supporting, contradictory = store.evidence_for("hyp_1")

        assert [e.id for e in supporting] == ["ev_3", "ev_1"]
        assert [e.id for e in contradictory] == ["ev_2"]

    def test_empty_lists_for_a_hypothesis_without_evidence(self) -> None:
        store = InMemoryEvidenceStore()
        store.add_hypothesis(make_hypothesis("hyp_1"))
        assert store.evidence_for("hyp_1") == ([], [])

    def test_raises_for_an_unknown_hypothesis(self) -> None:
        store = InMemoryEvidenceStore()
        with pytest.raises(KeyError, match="hyp_missing"):
            store.evidence_for("hyp_missing")


def test_end_to_end_atlas_worked_example() -> None:
    """Acceptance criterion 8: hand-build the Atlas example and read it back.

    An unexpected Modbus write to PLC-4 produces one Observation, one Deviation, one Evidence,
    three competing Hypotheses, and a Narrative tying them together. No detection logic is
    involved — this proves only that the ontology can carry real product output.
    """
    store = InMemoryEvidenceStore()

    plc = Entity(
        id="ent_plc4",
        type=EntityType.PLC,
        domain=Domain.ATLAS,
        name="PLC-4",
        attributes={"cell": "assembly-2"},
        created_at=T0,
    )
    workstation = Entity(
        id="ent_ews1",
        type=EntityType.ENGINEERING_WORKSTATION,
        domain=Domain.ATLAS,
        name="EWS-1",
        created_at=T0,
    )
    store.add_entity(plc)
    store.add_entity(workstation)

    observation = Observation(
        id="obs_write",
        entity_ids=["ent_ews1", "ent_plc4"],
        feature="modbus_write_rate_per_min",
        value=12.0,
        timestamp=T1,
        domain=Domain.ATLAS,
        context={"function_code": "16", "register": "40001"},
    )
    store.add_observation(observation)

    expected = ExpectedRange(
        feature="modbus_write_rate_per_min",
        entity_id="ent_plc4",
        low=0.0,
        high=0.0,
        mean=0.0,
        stddev=0.0,
        learned_from_window=(T0, T1),
    )
    deviation = Deviation(
        id="dev_write",
        observation_id="obs_write",
        expected=expected,
        magnitude=12.0,
        timestamp=T1,
    )
    store.add_deviation(deviation)
    assert expected.contains(observation.value) is False

    evidence = Evidence(
        id="ev_write",
        kind=EvidenceKind.DEVIATION,
        source_id="dev_write",
        entity_ids=["ent_ews1", "ent_plc4"],
        timestamp=T1,
        domain=Domain.ATLAS,
        summary="Unexpected Modbus write to PLC-4",
    )
    out_of_hours = Evidence(
        id="ev_hours",
        kind=EvidenceKind.SEQUENCE_ANOMALY,
        source_id="dev_write",
        entity_ids=["ent_ews1"],
        timestamp=T2,
        domain=Domain.ATLAS,
        summary="Write occurred outside the maintenance window",
    )
    store.add_evidence(evidence)
    store.add_evidence(out_of_hours)

    unauthorised = (
        Hypothesis(
            id="hyp_unauth",
            label="Unauthorised control activity",
            template_id="atlas.unauthorised_control_activity",
            domain=Domain.ATLAS,
            prior=0.15,
            confidence=0.15,
            status=HypothesisStatus.ACTIVE,
            created_at=T1,
            updated_at=T1,
        )
        .with_evidence("ev_write", EvidenceRole.SUPPORTING)
        .with_evidence("ev_hours", EvidenceRole.SUPPORTING)
    )
    maintenance = Hypothesis(
        id="hyp_maint",
        label="Engineering maintenance",
        template_id="atlas.engineering_maintenance",
        domain=Domain.ATLAS,
        prior=0.60,
        confidence=0.60,
        status=HypothesisStatus.ACTIVE,
        created_at=T1,
        updated_at=T1,
    ).with_evidence("ev_hours", EvidenceRole.CONTRADICTORY)
    malfunction = Hypothesis(
        id="hyp_malf",
        label="Device malfunction",
        template_id="atlas.device_malfunction",
        domain=Domain.ATLAS,
        prior=0.25,
        confidence=0.25,
        status=HypothesisStatus.ACTIVE,
        created_at=T1,
        updated_at=T1,
    ).with_evidence("ev_write", EvidenceRole.SUPPORTING)
    for hypothesis in (unauthorised, maintenance, malfunction):
        store.add_hypothesis(hypothesis)

    narrative = Narrative(
        id="nar_plc4",
        title="Unexplained control writes to PLC-4",
        domain=Domain.ATLAS,
        hypothesis_ids=["hyp_unauth", "hyp_maint", "hyp_malf"],
        evidence_ids=["ev_hours", "ev_write"],
        overall_confidence=0.62,
        causal_edges=[("ev_write", "hyp_unauth"), ("ev_hours", "hyp_unauth")],
        created_at=T2,
        updated_at=T2,
    )
    store.add_narrative(narrative)

    # The narrative reads back as a time-ordered story regardless of reference order.
    stored_narrative = store.get_narrative("nar_plc4")
    assert stored_narrative is not None
    assert [e.summary for e in stored_narrative.timeline(store)] == [
        "Unexpected Modbus write to PLC-4",
        "Write occurred outside the maintenance window",
    ]

    # The same evidence supports one hypothesis and contradicts another.
    unauth_supporting, unauth_contradictory = store.evidence_for("hyp_unauth")
    maint_supporting, maint_contradictory = store.evidence_for("hyp_maint")
    assert [e.id for e in unauth_supporting] == ["ev_write", "ev_hours"]
    assert unauth_contradictory == []
    assert maint_supporting == []
    assert [e.id for e in maint_contradictory] == ["ev_hours"]

    # Every hypothesis in the narrative is retrievable and carries its template provenance.
    assert [store.get_hypothesis(h) is not None for h in stored_narrative.hypothesis_ids] == [
        True,
        True,
        True,
    ]
    assert {h.template_id for h in store.hypotheses(Domain.ATLAS)} == {
        "atlas.unauthorised_control_activity",
        "atlas.engineering_maintenance",
        "atlas.device_malfunction",
    }

    # Every displayed conclusion traces back to a stored Deviation and its Observation.
    root_evidence = store.get_evidence("ev_write")
    assert root_evidence is not None
    traced_deviation = store.get_deviation(root_evidence.source_id)
    assert traced_deviation is not None
    assert store.get_observation(traced_deviation.observation_id) == observation

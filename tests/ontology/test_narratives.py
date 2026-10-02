"""Tests for the Narrative model."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from phos.ontology.enums import Domain, EvidenceKind
from phos.ontology.evidence import Evidence
from phos.ontology.narratives import Narrative
from phos.ontology.store import InMemoryEvidenceStore

T0 = datetime(2026, 1, 15, 9, 0, tzinfo=UTC)
T1 = datetime(2026, 1, 15, 10, 0, tzinfo=UTC)
T2 = datetime(2026, 1, 15, 11, 0, tzinfo=UTC)


def make_evidence(evidence_id: str, timestamp: datetime) -> Evidence:
    return Evidence(
        id=evidence_id,
        kind=EvidenceKind.DEVIATION,
        source_id="dev_000000000001",
        entity_ids=["ent_000000000001"],
        timestamp=timestamp,
        domain=Domain.ATLAS,
        summary=f"evidence at {timestamp.isoformat()}",
    )


def make_narrative(evidence_ids: list[str] | None = None) -> Narrative:
    return Narrative(
        id="nar_000000000001",
        title="Unauthorised control activity on PLC-4",
        domain=Domain.INTELLIGENCE,
        hypothesis_ids=["hyp_000000000001"],
        evidence_ids=evidence_ids if evidence_ids is not None else ["ev_1"],
        overall_confidence=0.74,
        causal_edges=[("ev_1", "hyp_000000000001")],
        created_at=T0,
        updated_at=T0,
    )


def test_constructs_and_defaults() -> None:
    narrative = make_narrative()
    assert narrative.title == "Unauthorised control activity on PLC-4"
    assert narrative.domain is Domain.INTELLIGENCE
    assert narrative.causal_edges == [("ev_1", "hyp_000000000001")]
    assert (
        Narrative(
            title="x",
            domain=Domain.ATLAS,
            hypothesis_ids=[],
            evidence_ids=[],
            overall_confidence=0.0,
        ).causal_edges
        == []
    )


def test_causal_edges_name_evidence_and_hypothesis_ids_already_on_the_narrative() -> None:
    """The graph is reconstructable from the narrative's own stored lists, not a second score."""
    narrative = make_narrative()
    evidence_ids = set(narrative.evidence_ids)
    hypothesis_ids = set(narrative.hypothesis_ids)
    for source, target in narrative.causal_edges:
        assert source in evidence_ids
        assert target in hypothesis_ids


def test_overall_confidence_defaults_to_none() -> None:
    """Uncalibrated hypothesis confidence is not copied onto the narrative (Constitution §3.3)."""
    narrative = Narrative(
        title="x",
        domain=Domain.ATLAS,
        hypothesis_ids=[],
        evidence_ids=[],
    )
    assert narrative.overall_confidence is None


def test_is_frozen() -> None:
    with pytest.raises(ValidationError):
        make_narrative().title = "other"  # type: ignore[misc]


@pytest.mark.parametrize("value", [-0.01, 1.01])
def test_rejects_out_of_bounds_confidence(value: float) -> None:
    with pytest.raises(ValidationError):
        Narrative(
            title="x",
            domain=Domain.ATLAS,
            hypothesis_ids=[],
            evidence_ids=[],
            overall_confidence=value,
        )


def test_timeline_returns_referenced_evidence_sorted_by_time() -> None:
    store = InMemoryEvidenceStore()
    # Added out of chronological order on purpose.
    for evidence_id, timestamp in (("ev_1", T2), ("ev_2", T0), ("ev_3", T1)):
        store.add_evidence(make_evidence(evidence_id, timestamp))
    narrative = make_narrative(evidence_ids=["ev_1", "ev_2", "ev_3"])

    timeline = narrative.timeline(store)

    assert [e.id for e in timeline] == ["ev_2", "ev_3", "ev_1"]
    assert [e.timestamp for e in timeline] == [T0, T1, T2]


def test_timeline_ignores_evidence_the_narrative_does_not_reference() -> None:
    store = InMemoryEvidenceStore()
    store.add_evidence(make_evidence("ev_1", T0))
    store.add_evidence(make_evidence("ev_other", T1))
    narrative = make_narrative(evidence_ids=["ev_1"])

    assert [e.id for e in narrative.timeline(store)] == ["ev_1"]


def test_timeline_is_stable_for_equal_timestamps() -> None:
    store = InMemoryEvidenceStore()
    for evidence_id in ("ev_1", "ev_2"):
        store.add_evidence(make_evidence(evidence_id, T0))
    narrative = make_narrative(evidence_ids=["ev_2", "ev_1"])

    assert [e.id for e in narrative.timeline(store)] == ["ev_2", "ev_1"]


def test_timeline_raises_on_an_unknown_evidence_id() -> None:
    store = InMemoryEvidenceStore()
    narrative = make_narrative(evidence_ids=["ev_missing"])
    with pytest.raises(KeyError, match="ev_missing"):
        narrative.timeline(store)


def test_json_round_trip() -> None:
    narrative = make_narrative()
    assert Narrative.model_validate_json(narrative.model_dump_json()) == narrative

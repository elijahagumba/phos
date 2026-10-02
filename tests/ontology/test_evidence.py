"""Tests for the Evidence model."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from phos.ontology.enums import Domain, EvidenceKind
from phos.ontology.evidence import Evidence

T0 = datetime(2026, 7, 28, 9, 0, tzinfo=UTC)


def make_evidence() -> Evidence:
    return Evidence(
        id="ev_000000000001",
        kind=EvidenceKind.DEVIATION,
        source_id="dev_000000000001",
        entity_ids=["ent_000000000001"],
        timestamp=T0,
        domain=Domain.ATLAS,
        weight=1.0,
        summary="Unexpected Modbus write to PLC-4",
    )


def test_constructs_from_valid_data() -> None:
    evidence = make_evidence()
    assert evidence.kind is EvidenceKind.DEVIATION
    assert evidence.source_id == "dev_000000000001"
    assert evidence.summary == "Unexpected Modbus write to PLC-4"


def test_weight_defaults_to_one() -> None:
    evidence = Evidence(
        kind=EvidenceKind.SEQUENCE_ANOMALY,
        source_id="dev_1",
        entity_ids=["ent_1"],
        timestamp=T0,
        domain=Domain.SENTIEL,
        summary="Unusual login sequence",
    )
    assert evidence.weight == 1.0
    assert evidence.id.startswith("ev_")


def test_is_frozen() -> None:
    with pytest.raises(ValidationError):
        make_evidence().weight = 2.0  # type: ignore[misc]


def test_rejects_negative_weight() -> None:
    with pytest.raises(ValidationError):
        Evidence(
            kind=EvidenceKind.DEVIATION,
            source_id="dev_1",
            entity_ids=["ent_1"],
            timestamp=T0,
            domain=Domain.ATLAS,
            weight=-0.5,
            summary="x",
        )


def test_weight_is_unbounded_above() -> None:
    evidence = Evidence(
        kind=EvidenceKind.DEVIATION,
        source_id="dev_1",
        entity_ids=["ent_1"],
        timestamp=T0,
        domain=Domain.ATLAS,
        weight=7.5,
        summary="x",
    )
    assert evidence.weight == 7.5


def test_requires_at_least_one_entity() -> None:
    with pytest.raises(ValidationError):
        Evidence(
            kind=EvidenceKind.DEVIATION,
            source_id="dev_1",
            entity_ids=[],
            timestamp=T0,
            domain=Domain.ATLAS,
            summary="x",
        )


def test_json_round_trip() -> None:
    evidence = make_evidence()
    assert Evidence.model_validate_json(evidence.model_dump_json()) == evidence

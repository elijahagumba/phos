"""Tests for the ontology enumerations."""

import json

from phos.ontology.enums import (
    Domain,
    EntityType,
    EvidenceKind,
    EvidenceRole,
    HypothesisStatus,
)


def test_domain_members() -> None:
    assert [d.value for d in Domain] == ["ATLAS", "SENTIEL", "INTELLIGENCE"]


def test_entity_type_members() -> None:
    assert [e.value for e in EntityType] == [
        # OT set
        "PLC",
        "RTU",
        "HMI",
        "SCADA_SERVER",
        "ENGINEERING_WORKSTATION",
        "INDUSTRIAL_SWITCH",
        # enterprise set
        "USER",
        "DEVICE",
        "SERVER",
        "APPLICATION",
        "DATABASE",
        "CLOUD_SERVICE",
        "EXTERNAL_CONNECTION",
    ]


def test_evidence_kind_members() -> None:
    assert [k.value for k in EvidenceKind] == [
        "DEVIATION",
        "FORECAST_MISS",
        "RELATIONSHIP_CHANGE",
        "SEQUENCE_ANOMALY",
    ]


def test_evidence_role_members() -> None:
    assert [r.value for r in EvidenceRole] == ["SUPPORTING", "CONTRADICTORY"]


def test_hypothesis_status_members() -> None:
    assert [s.value for s in HypothesisStatus] == ["ACTIVE", "PRUNED", "CONFIRMED", "DISMISSED"]


def test_enums_are_str_backed_for_json() -> None:
    assert Domain("ATLAS") is Domain.ATLAS
    assert json.dumps({"domain": Domain.ATLAS, "role": EvidenceRole.SUPPORTING}) == (
        '{"domain": "ATLAS", "role": "SUPPORTING"}'
    )
    assert HypothesisStatus.ACTIVE.value.lower() == "active"

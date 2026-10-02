"""Tests for the Entity model."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from phos.ontology.entities import Entity
from phos.ontology.enums import Domain, EntityType

T0 = datetime(2026, 7, 28, 9, 0, tzinfo=UTC)


def make_entity() -> Entity:
    return Entity(
        id="ent_000000000001",
        type=EntityType.PLC,
        domain=Domain.ATLAS,
        name="PLC-4",
        attributes={"vendor": "Siemens", "cell": "assembly-2"},
        created_at=T0,
    )


def test_constructs_from_valid_data() -> None:
    entity = make_entity()
    assert entity.name == "PLC-4"
    assert entity.type is EntityType.PLC
    assert entity.domain is Domain.ATLAS
    assert entity.attributes["vendor"] == "Siemens"
    assert entity.created_at == T0


def test_defaults() -> None:
    entity = Entity(type=EntityType.USER, domain=Domain.SENTIEL, name="alice")
    assert entity.id.startswith("ent_")
    assert entity.attributes == {}
    assert entity.created_at.tzinfo is UTC


def test_is_frozen() -> None:
    entity = make_entity()
    with pytest.raises(ValidationError):
        entity.name = "PLC-5"  # type: ignore[misc]


def test_matches() -> None:
    entity = make_entity()
    assert entity.matches(EntityType.PLC) is True
    assert entity.matches(EntityType.HMI) is False


def test_rejects_unknown_entity_type() -> None:
    with pytest.raises(ValidationError):
        Entity(type="TOASTER", domain=Domain.ATLAS, name="x")  # type: ignore[arg-type]


def test_json_round_trip() -> None:
    entity = make_entity()
    assert Entity.model_validate_json(entity.model_dump_json()) == entity

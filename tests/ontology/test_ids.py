"""Tests for typed ID helpers."""

import re
from datetime import UTC, datetime

import pytest
from pydantic import BaseModel, ValidationError

from phos.ontology.ids import (
    DEVIATION_PREFIX,
    ENTITY_PREFIX,
    EVIDENCE_PREFIX,
    FORECAST_PREFIX,
    HYPOTHESIS_PREFIX,
    NARRATIVE_PREFIX,
    OBSERVATION_PREFIX,
    UtcDatetime,
    new_id,
)

ALL_PREFIXES = [
    ENTITY_PREFIX,
    OBSERVATION_PREFIX,
    DEVIATION_PREFIX,
    FORECAST_PREFIX,
    EVIDENCE_PREFIX,
    HYPOTHESIS_PREFIX,
    NARRATIVE_PREFIX,
]


def test_prefixes_are_the_spec_values() -> None:
    assert ALL_PREFIXES == ["ent", "obs", "dev", "fc", "ev", "hyp", "nar"]


@pytest.mark.parametrize("prefix", ALL_PREFIXES)
def test_new_id_shape(prefix: str) -> None:
    value = new_id(prefix)
    assert re.fullmatch(rf"{prefix}_[0-9a-f]{{12}}", value)


def test_new_id_is_unique() -> None:
    assert len({new_id(ENTITY_PREFIX) for _ in range(1000)}) == 1000


def test_new_id_rejects_empty_prefix() -> None:
    with pytest.raises(ValueError, match="prefix"):
        new_id("")


def test_new_id_rejects_a_prefix_containing_an_underscore() -> None:
    with pytest.raises(ValueError, match="must not contain"):
        new_id("ent_x")


class _Stamped(BaseModel):
    at: UtcDatetime


def test_utc_datetime_normalises_offsets_to_utc() -> None:
    parsed = _Stamped(at=datetime.fromisoformat("2026-07-28T13:00:00+01:00")).at
    assert parsed == datetime(2026, 7, 28, 12, 0, tzinfo=UTC)
    assert parsed.tzinfo is UTC


def test_utc_datetime_rejects_naive_datetimes() -> None:
    with pytest.raises(ValidationError):
        _Stamped(at=datetime(2026, 7, 28, 12, 0))  # deliberately naive

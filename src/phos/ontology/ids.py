"""Typed identifier helpers and shared scalar aliases for the ontology.

Identifiers are opaque strings of the form ``{prefix}_{12 hex chars}``. They are plain ``str``
subtypes (aliases) rather than wrapper classes so that every ontology object stays trivially
JSON-serialisable and cross-references remain readable in stored documents and API payloads.

This module also hosts :data:`UtcDatetime`, the timestamp type every ontology object uses, so
that "timestamps are timezone-aware UTC" is enforced in exactly one place.
"""

from datetime import UTC, datetime
from typing import Annotated
from uuid import uuid4

from pydantic import AwareDatetime, PlainSerializer, WrapValidator
from pydantic_core.core_schema import ValidatorFunctionWrapHandler

__all__ = [
    "DEVIATION_PREFIX",
    "ENTITY_PREFIX",
    "EVIDENCE_PREFIX",
    "FORECAST_PREFIX",
    "HYPOTHESIS_PREFIX",
    "NARRATIVE_PREFIX",
    "OBSERVATION_PREFIX",
    "DeviationId",
    "EntityId",
    "EvidenceId",
    "ForecastId",
    "HypothesisId",
    "NarrativeId",
    "ObservationId",
    "UtcDatetime",
    "new_id",
    "utc_now",
]

# Readability aliases. They document intent at call sites; they are not runtime-distinct types.
EntityId = str
ObservationId = str
DeviationId = str
ForecastId = str
EvidenceId = str
HypothesisId = str
NarrativeId = str

ENTITY_PREFIX = "ent"
OBSERVATION_PREFIX = "obs"
DEVIATION_PREFIX = "dev"
FORECAST_PREFIX = "fc"
EVIDENCE_PREFIX = "ev"
HYPOTHESIS_PREFIX = "hyp"
NARRATIVE_PREFIX = "nar"

_ID_HEX_LENGTH = 12


def new_id(prefix: str) -> str:
    """Mint a new opaque identifier.

    Args:
        prefix: Short type marker, e.g. ``"ent"``. Use one of the ``*_PREFIX`` constants.

    Returns:
        An identifier of the form ``{prefix}_{12 hex chars}``.

    Raises:
        ValueError: If ``prefix`` is empty or contains an underscore, either of which would make
            the identifier ambiguous to read.
    """
    if not prefix:
        raise ValueError("prefix must be a non-empty string")
    if "_" in prefix:
        raise ValueError(f"prefix must not contain '_': {prefix!r}")
    return f"{prefix}_{uuid4().hex[:_ID_HEX_LENGTH]}"


def utc_now() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""
    return datetime.now(UTC)


def _to_utc(value: object, handler: ValidatorFunctionWrapHandler) -> datetime:
    """Validate a timezone-aware datetime and normalise it to UTC.

    Normalising on the way in means two objects describing the same instant compare equal
    regardless of the offset they were expressed in, and JSON round-trips are byte-stable.
    """
    validated: datetime = handler(value)
    return validated.astimezone(UTC)


UtcDatetime = Annotated[
    AwareDatetime,
    WrapValidator(_to_utc),
    PlainSerializer(lambda value: value.isoformat(), return_type=str, when_used="json"),
]
"""A timezone-aware datetime, normalised to UTC on validation. Naive datetimes are rejected."""

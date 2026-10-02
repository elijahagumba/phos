"""Tests for the normalised enterprise event and its two normalisation helpers."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from phos.sentiel import (
    DETAIL_PC,
    DETAIL_URL,
    EnterpriseEvent,
    EventKind,
    domain_of,
    host_of,
)


def _event(**overrides: object) -> EnterpriseEvent:
    fields: dict[str, object] = {
        "timestamp": datetime(2010, 7, 1, 1, 24, 58, tzinfo=UTC),
        "user_id": "CSF0929",
        "event_kind": EventKind.LOGON,
        "details": {DETAIL_PC: "PC-4442"},
    }
    fields.update(overrides)
    return EnterpriseEvent.model_validate(fields)


def test_event_carries_kind_specific_fields_in_details() -> None:
    event = _event(
        event_kind=EventKind.HTTP_REQUEST,
        details={DETAIL_PC: "PC-4442", DETAIL_URL: "http://wikileaks.org/leak"},
    )

    assert event.event_kind is EventKind.HTTP_REQUEST
    assert event.details[DETAIL_URL] == "http://wikileaks.org/leak"
    assert event.details[DETAIL_PC] == "PC-4442"


def test_event_is_frozen() -> None:
    event = _event()
    with pytest.raises(ValidationError):
        event.user_id = "OTHER"  # type: ignore[misc]


def test_event_rejects_a_naive_timestamp() -> None:
    """Every ontology object is timezone-aware UTC; an event is no exception."""
    with pytest.raises(ValidationError):
        _event(timestamp=datetime(2010, 7, 1, 1, 24, 58))


def test_event_round_trips_through_json() -> None:
    event = _event(event_kind=EventKind.EMAIL_SEND, details={"recipients": "a@b.com"})
    assert EnterpriseEvent.model_validate_json(event.model_dump_json()) == event


def test_event_normalises_the_timestamp_to_utc() -> None:
    from datetime import timedelta, timezone

    event = _event(timestamp=datetime(2010, 7, 1, 3, 24, 58, tzinfo=timezone(timedelta(hours=2))))
    assert event.timestamp == datetime(2010, 7, 1, 1, 24, 58, tzinfo=UTC)


def test_every_event_kind_is_str_backed() -> None:
    """Kinds serialise as readable JSON, matching the ontology's enum convention."""
    assert EventKind.DEVICE_CONNECT.value == "DEVICE_CONNECT"
    assert {kind.value for kind in EventKind} == {
        "LOGON",
        "LOGOFF",
        "DEVICE_CONNECT",
        "DEVICE_DISCONNECT",
        "FILE_ACCESS",
        "EMAIL_SEND",
        "HTTP_REQUEST",
    }


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("http://wikileaks.org/leak", "wikileaks.org"),
        ("https://www.dropbox.com/upload?x=1", "www.dropbox.com"),
        ("http://JOB-HUNT.COM/Listing", "job-hunt.com"),
        ("http://host.example.com:8080/path", "host.example.com"),
        ("wikileaks.org/no-scheme", "wikileaks.org"),
        ("", ""),
        ("   ", ""),
    ],
)
def test_host_of_extracts_and_lowercases_the_host(url: str, expected: str) -> None:
    assert host_of(url) == expected


@pytest.mark.parametrize(
    ("address", "expected"),
    [
        ("Nathan.O.Sanders@dtaa.com", "dtaa.com"),
        ("someone@GMAIL.com", "gmail.com"),
        ("  spaced@dtaa.com  ", "dtaa.com"),
        ("not-an-address", ""),
        ("", ""),
    ],
)
def test_domain_of_extracts_and_lowercases_the_domain(address: str, expected: str) -> None:
    assert domain_of(address) == expected

"""Tests for the CERT release reader: header introspection, ordering, and email attribution."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from phos.sentiel import (
    DETAIL_ACTIVITY,
    DETAIL_FILENAME,
    DETAIL_PC,
    DETAIL_RECIPIENT_DOMAINS,
    DETAIL_SENDER,
    DETAIL_URL_HOST,
    CertFormatError,
    CertReader,
    CertRelease,
    EventKind,
)


def _reader(release_dir: Path) -> CertReader:
    return CertReader.for_release(CertRelease.discover(release_dir))


def test_discover_finds_a_release_directly(release_dir: Path) -> None:
    release = CertRelease.discover(release_dir)
    assert release.root == release_dir
    assert release.name == "r3.1"


def test_discover_descends_one_level(release_dir: Path) -> None:
    """`tar -xjf r3.1.tar.bz2` makes `r3.1/`, so the parent must work as well as the release."""
    release = CertRelease.discover(release_dir.parent)
    assert release.root == release_dir


def test_discover_refuses_a_directory_that_is_not_a_release(tmp_path: Path) -> None:
    with pytest.raises(CertFormatError, match="no CERT release found"):
        CertRelease.discover(tmp_path)


def test_discover_refuses_a_missing_directory(tmp_path: Path) -> None:
    with pytest.raises(CertFormatError, match="not found"):
        CertRelease.discover(tmp_path / "nope")


def test_events_are_time_ordered_across_every_log(release_dir: Path) -> None:
    events = list(_reader(release_dir).events())
    stamps = [event.timestamp for event in events]
    assert stamps == sorted(stamps)
    assert all(stamp.tzinfo is not None for stamp in stamps)


def test_events_cover_every_log_type(release_dir: Path) -> None:
    kinds = {event.event_kind for event in _reader(release_dir).events()}
    assert kinds == {
        EventKind.LOGON,
        EventKind.LOGOFF,
        EventKind.DEVICE_CONNECT,
        EventKind.DEVICE_DISCONNECT,
        EventKind.FILE_ACCESS,
        EventKind.EMAIL_SEND,
        EventKind.HTTP_REQUEST,
    }


def test_logon_row_is_normalised(release_dir: Path) -> None:
    first = next(iter(_reader(release_dir).events()))
    assert first.event_kind is EventKind.LOGON
    assert first.user_id == "ALICE001"
    assert first.timestamp == datetime(2010, 1, 4, 9, 0, tzinfo=UTC)
    assert first.details[DETAIL_PC] == "PC-1"
    assert first.details[DETAIL_ACTIVITY] == "Logon"


def test_http_host_is_normalised_once_at_the_boundary(release_dir: Path) -> None:
    hosts = {
        event.details[DETAIL_URL_HOST]
        for event in _reader(release_dir).events()
        if event.event_kind is EventKind.HTTP_REQUEST
    }
    assert hosts == {"wikileaks.org", "www.dropbox.com", "intranet.dtaa.com"}


def test_file_row_carries_its_filename(release_dir: Path) -> None:
    names = [
        event.details[DETAIL_FILENAME]
        for event in _reader(release_dir).events()
        if event.event_kind is EventKind.FILE_ACCESS
    ]
    assert names == ["secret.doc", "secret.doc", "other.doc"]


def test_email_actor_is_resolved_from_the_from_address(release_dir: Path) -> None:
    """r3.1's email log has no `user` column; the actor comes from LDAP via `from`."""
    emails = [
        event for event in _reader(release_dir).events() if event.event_kind is EventKind.EMAIL_SEND
    ]

    assert [event.user_id for event in emails] == ["MALLORY9", "ALICE001"]
    assert emails[0].details[DETAIL_SENDER] == "mallory.m.nine@dtaa.com"
    assert emails[0].details[DETAIL_RECIPIENT_DOMAINS] == "dtaa.com;gmail.com"


def test_email_from_a_non_employee_is_skipped_and_counted(
    release_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Inbound mail is not an action by a monitored user — but it is never dropped in silence."""
    with caplog.at_level("WARNING", logger="phos.sentiel.cert"):
        senders = [
            event.details[DETAIL_SENDER]
            for event in _reader(release_dir).events()
            if event.event_kind is EventKind.EMAIL_SEND
        ]

    assert "outsider@elsewhere.com" not in senders
    assert any("skipped 1 row(s)" in record.getMessage() for record in caplog.records)


def test_an_unresolvable_email_index_skips_every_message(release_dir: Path) -> None:
    """A reader built without the directory cannot attribute email, and says so by emitting none."""
    bare = CertReader(release=CertRelease.discover(release_dir))
    assert not [event for event in bare.events() if event.event_kind is EventKind.EMAIL_SEND]


def test_a_missing_required_column_raises_naming_what_was_found(release_dir: Path) -> None:
    (release_dir / "logon.csv").write_text(
        "id,date,user,pc\n{L1},01/04/2010 09:00:00,ALICE001,PC-1\n", encoding="utf-8"
    )
    with pytest.raises(CertFormatError, match="missing required column"):
        list(_reader(release_dir).events())


def test_an_unrecognised_column_raises_rather_than_being_dropped(release_dir: Path) -> None:
    """A release with a schema this reader has not been taught must be loud, not lossy."""
    (release_dir / "device.csv").write_text(
        "id,date,user,pc,activity,file_tree\n{D1},01/04/2010 22:35:00,MALLORY9,PC-2,Connect,C:\\\n",
        encoding="utf-8",
    )
    with pytest.raises(CertFormatError, match="unrecognised column"):
        list(_reader(release_dir).events())


def test_an_unsorted_log_raises_rather_than_corrupting_the_merge(release_dir: Path) -> None:
    (release_dir / "device.csv").write_text(
        "id,date,user,pc,activity\n"
        "{D1},01/05/2010 10:00:00,ALICE001,PC-1,Connect\n"
        "{D2},01/04/2010 22:35:00,MALLORY9,PC-2,Connect\n",
        encoding="utf-8",
    )
    with pytest.raises(CertFormatError, match="not time-ordered"):
        list(_reader(release_dir).events())


def test_an_unparseable_timestamp_raises(release_dir: Path) -> None:
    (release_dir / "logon.csv").write_text(
        "id,date,user,pc,activity\n{L1},2010-01-04 09:00:00,ALICE001,PC-1,Logon\n",
        encoding="utf-8",
    )
    with pytest.raises(CertFormatError, match="does not match"):
        list(_reader(release_dir).events())


def test_an_unknown_activity_word_raises(release_dir: Path) -> None:
    (release_dir / "device.csv").write_text(
        "id,date,user,pc,activity\n{D1},01/04/2010 22:35:00,MALLORY9,PC-2,Teleport\n",
        encoding="utf-8",
    )
    with pytest.raises(CertFormatError, match="unrecognised activity"):
        list(_reader(release_dir).events())


def test_a_missing_log_raises(release_dir: Path) -> None:
    release = CertRelease.discover(release_dir)
    reader = CertReader.for_release(release)
    (release_dir / "file.csv").unlink()
    with pytest.raises(CertFormatError, match="activity log not found"):
        list(reader.events())


def test_the_reader_may_be_iterated_twice(release_dir: Path) -> None:
    reader = _reader(release_dir)
    assert list(reader.events()) == list(reader.events())


def test_an_empty_file_raises(release_dir: Path) -> None:
    (release_dir / "logon.csv").write_text("", encoding="utf-8")
    with pytest.raises(CertFormatError, match="file is empty"):
        list(_reader(release_dir).events())


def test_a_short_row_raises_rather_than_being_read_positionally(release_dir: Path) -> None:
    """Positional reading is only safe while the row is long enough to hold its own columns."""
    (release_dir / "logon.csv").write_text(
        "id,date,user,pc,activity\n{L1},01/04/2010 09:00:00,ALICE001\n", encoding="utf-8"
    )
    with pytest.raises(CertFormatError, match="too few"):
        list(_reader(release_dir).events())


def test_an_empty_date_cell_raises(release_dir: Path) -> None:
    (release_dir / "logon.csv").write_text(
        "id,date,user,pc,activity\n{L1},,ALICE001,PC-1,Logon\n", encoding="utf-8"
    )
    with pytest.raises(CertFormatError, match="empty date cell"):
        list(_reader(release_dir).events())


def test_an_unknown_logon_activity_raises(release_dir: Path) -> None:
    (release_dir / "logon.csv").write_text(
        "id,date,user,pc,activity\n{L1},01/04/2010 09:00:00,ALICE001,PC-1,Hibernate\n",
        encoding="utf-8",
    )
    with pytest.raises(CertFormatError, match="unrecognised activity"):
        list(_reader(release_dir).events())


def test_progress_is_logged_while_streaming_a_large_release(
    release_dir: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A 13 GB read that prints nothing for twenty minutes is indistinguishable from a hang."""
    monkeypatch.setattr("phos.sentiel.cert._PROGRESS_EVERY", 1)
    with caplog.at_level("INFO", logger="phos.sentiel.cert"):
        list(_reader(release_dir).events())
    assert any("read 1 events" in record.getMessage() for record in caplog.records)

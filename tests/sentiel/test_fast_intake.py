"""The fast reader is only allowed to exist because it is proved equal to the authority."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from phos.sentiel.cert import CertFormatError, CertReader, CertRelease
from phos.sentiel.fast_intake import (
    MERGE_ORDER,
    _DateFacts,
    fast_trace_stream,
    parse_stamp,
    traces_agree,
)
from phos.sentiel.featurise import WorkingHours
from phos.sentiel.traces import trace_stream

ORG = frozenset({"dtaa.com"})


class TestEquivalenceWithTheAuthority:
    def test_the_fast_reader_and_certreader_produce_identical_traces(
        self, release_dir: Path
    ) -> None:
        """A cache that is nearly the featuriser's input is worse than no cache at all."""
        release = CertRelease.discover(release_dir)
        reader = CertReader.for_release(release)

        fast = list(fast_trace_stream(release, reader.email_senders, WorkingHours(), ORG))
        authority = list(trace_stream(reader.events(), WorkingHours(), ORG))

        agree, reason = traces_agree(fast, authority)
        assert agree, reason
        assert fast, "the fixture release must produce traces for this to mean anything"

    def test_a_disagreement_is_reported_with_the_field_that_differs(
        self, release_dir: Path
    ) -> None:
        release = CertRelease.discover(release_dir)
        reader = CertReader.for_release(release)
        authority = list(trace_stream(reader.events(), WorkingHours(), ORG))
        tampered = [authority[0].model_copy(update={"logons": 99}), *authority[1:]]

        agree, reason = traces_agree(tampered, authority)
        assert not agree
        assert "logons" in reason

    def test_a_count_mismatch_is_reported(self, release_dir: Path) -> None:
        release = CertRelease.discover(release_dir)
        reader = CertReader.for_release(release)
        authority = list(trace_stream(reader.events(), WorkingHours(), ORG))
        agree, reason = traces_agree(authority[:-1], authority)
        assert not agree
        assert "count differs" in reason

    def test_inbound_mail_is_skipped_by_both_readers(self, release_dir: Path) -> None:
        """The fixture's outsider sends one message in; neither reader may attribute it."""
        release = CertRelease.discover(release_dir)
        reader = CertReader.for_release(release)
        fast = list(fast_trace_stream(release, reader.email_senders, WorkingHours(), ORG))
        assert {trace.user_id for trace in fast} == {"ALICE001", "MALLORY9"}


class TestTheMergeOrderIsPinned:
    def test_it_names_the_same_logs_as_the_authority(self) -> None:
        from phos.sentiel.cert import ALL_SPECS

        assert {spec.filename for spec in MERGE_ORDER} == {spec.filename for spec in ALL_SPECS}

    def test_it_is_the_order_certreader_builds_its_streams_in(self) -> None:
        """`heapq.merge` is stable, so ties resolve by stream position — visible in the sequence."""
        assert [spec.filename for spec in MERGE_ORDER] == [
            "logon.csv",
            "device.csv",
            "http.csv",
            "email.csv",
            "file.csv",
        ]


class TestTheTimestampParser:
    @pytest.mark.parametrize("hour", [0, 7, 8, 12, 17, 18, 23])
    @pytest.mark.parametrize("day", ["01/04/2010", "07/16/2010", "12/31/2011"])
    def test_it_agrees_with_strptime(self, day: str, hour: int) -> None:
        """A hand-rolled parser is only allowed if it is checked against the real one."""
        text = f"{day} {hour:02d}:34:56"
        key, midnight, off_hours = parse_stamp(text, {}, WorkingHours())
        expected = datetime.strptime(text, "%m/%d/%Y %H:%M:%S").replace(tzinfo=UTC)
        assert midnight == datetime(expected.year, expected.month, expected.day, tzinfo=UTC)
        assert key == (expected.toordinal(), expected.hour, expected.minute, expected.second)
        assert off_hours == (not WorkingHours().contains(expected))

    def test_the_date_cache_does_not_change_the_answer(self) -> None:
        cache: dict[str, _DateFacts] = {}
        first = parse_stamp("01/04/2010 09:00:00", cache, WorkingHours())
        second = parse_stamp("01/04/2010 22:00:00", cache, WorkingHours())
        assert first[1] == second[1]
        assert first[2] is False
        assert second[2] is True

    @pytest.mark.parametrize(
        "text",
        [
            "",
            "2010-01-04 09:00:00",
            "01/04/2010 09:00",
            "13/45/2010 09:00:00",
            "01/04/2010 25:00:00",
        ],
    )
    def test_a_stamp_it_cannot_read_is_refused_rather_than_guessed(self, text: str) -> None:
        with pytest.raises(CertFormatError):
            parse_stamp(text, {}, WorkingHours())

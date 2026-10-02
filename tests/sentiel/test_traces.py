"""The trace cache must be a materialisation of the featuriser, not a second implementation.

The whole episode cycle rests on one claim: a run scored from cached traces and a run scored from
the corpus are the *same run*. `TestReplayIsExact` is that claim, asserted observation by
observation against `Featuriser.stream` on the CERT-shaped fixture release — the one place the
claim can be checked without reading 27 million rows.
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from phos.sentiel.cert import CertReader, CertRelease
from phos.sentiel.entities import EntityCatalogue
from phos.sentiel.featurise import FeatureSet, Featuriser, WorkingHours
from phos.sentiel.peers import PeerGroups, PeerPolicy
from phos.sentiel.traces import (
    CACHE_FORMAT_VERSION,
    DeclaredToken,
    EntityDayTrace,
    read_traces,
    replay_observations,
    token_for,
    trace_stream,
    write_traces,
)

ORG = frozenset({"dtaa.com"})


def _reader(release_dir: Path) -> CertReader:
    return CertReader.for_release(CertRelease.discover(release_dir))


def _featuriser(release_dir: Path, feature_set: FeatureSet) -> Featuriser:
    catalogue = EntityCatalogue.from_ldap_directory(release_dir / "LDAP")
    groups = (
        PeerGroups.from_catalogue(catalogue, PeerPolicy(min_group_size=2))
        if feature_set.needs_peers
        else None
    )
    return Featuriser(org_domains=ORG, feature_set=feature_set, peer_groups=groups)


class TestReplayIsExact:
    """A cache that is nearly the featuriser's input is worse than no cache at all."""

    @pytest.mark.parametrize(
        "feature_set", [FeatureSet.STARTER, FeatureSet.ENRICHED, FeatureSet.PEER]
    )
    def test_replayed_observations_match_the_featuriser_field_for_field(
        self, release_dir: Path, feature_set: FeatureSet
    ) -> None:
        """Same ids, features, values, timestamps and context — for every feature set."""
        featuriser = _featuriser(release_dir, feature_set)
        direct = list(featuriser.stream(_reader(release_dir).events()))
        traces = list(trace_stream(_reader(release_dir).events(), WorkingHours(), ORG))
        replayed = list(replay_observations(traces, featuriser))

        assert [
            (o.id, o.feature, o.value, o.timestamp, o.entity_ids, o.context) for o in replayed
        ] == [(o.id, o.feature, o.value, o.timestamp, o.entity_ids, o.context) for o in direct]
        assert direct, "the fixture release must produce observations for this to mean anything"

    def test_a_trace_restores_the_featurisers_own_accumulator(self, release_dir: Path) -> None:
        """The cache stores accumulator state, so the featuriser's own methods do the arithmetic."""
        traces = list(trace_stream(_reader(release_dir).events(), WorkingHours(), ORG))
        mallory = next(trace for trace in traces if trace.user_id == "MALLORY9")
        accumulator = mallory.as_accumulator()
        assert accumulator.values() == (
            2.0,  # logons
            2.0,  # distinct pcs
            2.0,  # off-hours logons
            1.0,  # removable connects
            3.0,  # file accesses
            2.0,  # distinct files
            1.0,  # external emails
            2.0,  # distinct hosts
        )


class TestTheSequenceIsDeclaredAndCollapsed:
    def test_consecutive_identical_tokens_collapse(self, release_dir: Path) -> None:
        """Volume is the counts' job; the sequence carries order only."""
        traces = list(trace_stream(_reader(release_dir).events(), WorkingHours(), ORG))
        mallory = next(trace for trace in traces if trace.user_id == "MALLORY9")
        assert mallory.file_accesses == 3
        assert mallory.sequence.count(DeclaredToken.FILE_ACCESS) == 1

    def test_off_hours_logons_take_a_different_token_from_in_hours_ones(
        self, release_dir: Path
    ) -> None:
        """The refinement comes from the declared working pattern, not from anyone's history."""
        traces = list(trace_stream(_reader(release_dir).events(), WorkingHours(), ORG))
        alice = next(trace for trace in traces if trace.user_id == "ALICE001")
        mallory = next(trace for trace in traces if trace.user_id == "MALLORY9")
        assert DeclaredToken.LOGON in alice.sequence
        assert DeclaredToken.LOGON_OFF_HOURS in mallory.sequence

    def test_external_and_internal_mail_take_different_tokens(self, release_dir: Path) -> None:
        """The refinement comes from the directory's own domain, not from a constant."""
        events = list(_reader(release_dir).events())
        sends = [event for event in events if event.event_kind.value == "EMAIL_SEND"]
        tokens = {token_for(event, WorkingHours(), ORG) for event in sends}
        assert DeclaredToken.EMAIL_EXTERNAL in tokens
        assert DeclaredToken.EMAIL_INTERNAL in tokens


class TestOrderingIsTheCausalityGuarantee:
    def test_out_of_order_days_are_refused(self) -> None:
        """Reversing the day order would corrupt both histories without raising anywhere else."""
        featuriser = Featuriser(org_domains=ORG, feature_set=FeatureSet.STARTER)
        traces = [
            EntityDayTrace(user_id="A", day=datetime(2010, 1, 5, tzinfo=UTC), logons=1),
            EntityDayTrace(user_id="A", day=datetime(2010, 1, 4, tzinfo=UTC), logons=1),
        ]
        with pytest.raises(ValueError, match="day-ascending"):
            list(replay_observations(traces, featuriser))

    def test_out_of_order_users_within_a_day_are_refused(self) -> None:
        """The peer pool is advanced per window, so user order inside one is load-bearing."""
        featuriser = Featuriser(org_domains=ORG, feature_set=FeatureSet.STARTER)
        day = datetime(2010, 1, 4, tzinfo=UTC)
        traces = [
            EntityDayTrace(user_id="B", day=day, logons=1),
            EntityDayTrace(user_id="A", day=day, logons=1),
        ]
        with pytest.raises(ValueError, match="user-ascending"):
            list(replay_observations(traces, featuriser))


class TestTheCacheFile:
    def test_round_trips(self, release_dir: Path, tmp_path: Path) -> None:
        """What is written is what is read, field for field."""
        traces = list(trace_stream(_reader(release_dir).events(), WorkingHours(), ORG))
        path = tmp_path / "traces.jsonl.gz"
        assert write_traces(traces, path) == len(traces)
        assert list(read_traces(path)) == traces

    def test_a_stale_format_is_refused_rather_than_reinterpreted(self, tmp_path: Path) -> None:
        """Fields that may have changed meaning must not be read as if they had not."""
        import gzip
        import json

        path = tmp_path / "stale.jsonl.gz"
        with gzip.open(path, "wt", encoding="utf-8") as handle:
            handle.write(json.dumps({"format": CACHE_FORMAT_VERSION + 1}) + "\n")
        with pytest.raises(ValueError, match="cache format"):
            list(read_traces(path))

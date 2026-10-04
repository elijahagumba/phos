"""Tests for both feature sets, computed against hand-counted answers.

Every expected number below was counted or derived by hand, which is the point: a featuriser whose
answers are only checked against itself checks nothing. The starter-set expectations are counted off
`conftest.py`'s CERT-shaped release; the enriched-set expectations are counted off event streams
built in this file, because the enrichments need weeks of history and the release fixture is two
days long.
"""

import json
import math
import subprocess
from collections import defaultdict
from collections.abc import Callable, Iterator, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import ClassVar

import pytest
from pydantic import ValidationError
from scripts.evaluate_sentiel_baseline import (
    BASELINE_6A,
    BASELINE_6D,
    ENRICHED_SUBSET,
    PEER_SUBSET,
    BaselineError,
    check_the_attack_bound_the_split,
    evaluation_remainder,
    run,
    run_aggregated,
    side_by_side,
    training_prefix,
)

from phos.eval import Dataset, EvalConfig, EvaluationReport, LatencySummary
from phos.models import GaussianBaseline, SplitPolicy, train_test_split
from phos.ontology import Domain, Observation
from phos.sentiel import (
    BASELINE_RELATIVE_FEATURES,
    ENRICHED_CAVEATS,
    ENRICHED_FEATURES,
    NEUTRAL_VALUE,
    ONSET_SIGNALS,
    PEER_CAVEATS,
    PEER_FEATURES,
    PEER_RELATIVE_FEATURES,
    RELATIONSHIP_FEATURES,
    SENTIEL_CAVEATS,
    STARTER_FEATURES,
    SUPERSEDED_CAVEAT_MARKER,
    SUPERSEDED_ENRICHED_MARKERS,
    TEMPORAL_FEATURES,
    AggregatedDetector,
    AggregationPolicy,
    CertReader,
    CertRelease,
    EnterpriseEvent,
    EntityCatalogue,
    EntityLabelledInterval,
    EventKind,
    FeatureSet,
    Featuriser,
    HistoryPolicy,
    PeerGroups,
    PeerPolicy,
    PrecomputedDetector,
    ScoringSummary,
    TrailingHistory,
    WorkingHours,
    enriched_source_note,
    evaluate_entity_aware,
    featurise,
    peer_source_note,
    static_range_model,
)
from phos.sentiel.events import (
    DETAIL_FILENAME,
    DETAIL_PC,
    DETAIL_RECIPIENT_DOMAINS,
    DETAIL_RECIPIENTS,
    DETAIL_URL_HOST,
)

MONDAY_4TH = datetime(2010, 1, 4, tzinfo=UTC)
TUESDAY_5TH = datetime(2010, 1, 5, tzinfo=UTC)

# Counted by hand from conftest.py.
EXPECTED: dict[tuple[str, datetime], dict[str, float]] = {
    ("MALLORY9", MONDAY_4TH): {
        "logon_count": 2.0,
        "distinct_pcs": 2.0,
        "off_hours_logon_count": 2.0,
        "removable_device_connects": 1.0,
        "file_access_count": 3.0,
        "distinct_files": 2.0,
        "external_email_count": 1.0,
        "distinct_http_hosts": 2.0,
    },
    ("ALICE001", MONDAY_4TH): {
        "logon_count": 1.0,
        "distinct_pcs": 1.0,
        "off_hours_logon_count": 0.0,
        "removable_device_connects": 0.0,
        "file_access_count": 0.0,
        "distinct_files": 0.0,
        "external_email_count": 0.0,
        "distinct_http_hosts": 0.0,
    },
    ("ALICE001", TUESDAY_5TH): {
        "logon_count": 1.0,
        "distinct_pcs": 1.0,
        "off_hours_logon_count": 0.0,
        "removable_device_connects": 1.0,
        "file_access_count": 0.0,
        "distinct_files": 0.0,
        "external_email_count": 0.0,
        "distinct_http_hosts": 1.0,
    },
}


def _observations(release_dir: Path) -> list[Observation]:
    reader = CertReader.for_release(CertRelease.discover(release_dir))
    return Featuriser().observations(reader.events())


def _lookup(observations: list[Observation]) -> dict[tuple[str, datetime, str], float]:
    return {
        (observation.context["user_id"], observation.timestamp, observation.feature): (
            observation.value
        )
        for observation in observations
    }


@pytest.mark.parametrize(("key", "expected"), list(EXPECTED.items()), ids=lambda k: str(k))
def test_starter_features_match_hand_counted_answers(
    release_dir: Path, key: object, expected: object
) -> None:
    if not isinstance(key, tuple) or not isinstance(expected, dict):
        pytest.fail("bad parametrisation")
    user_id, window = key
    values = _lookup(_observations(release_dir))
    assert {feature: values[(user_id, window, feature)] for feature in expected} == expected


def test_a_user_day_emits_every_feature_including_the_zeros(release_dir: Path) -> None:
    """An absent zero would narrow a quiet feature's learned band to only the days it fired."""
    observations = _observations(release_dir)
    by_window: dict[tuple[str, datetime], set[str]] = {}
    for observation in observations:
        by_window.setdefault((observation.context["user_id"], observation.timestamp), set()).add(
            observation.feature
        )
    assert all(features == set(STARTER_FEATURES) for features in by_window.values())
    assert len(observations) == 3 * len(STARTER_FEATURES)


def test_a_user_day_with_no_activity_produces_nothing(release_dir: Path) -> None:
    """Mallory does nothing on the 5th, so the 5th is not observed for Mallory."""
    values = _lookup(_observations(release_dir))
    assert not [key for key in values if key[0] == "MALLORY9" and key[1] == TUESDAY_5TH]


def test_observations_are_ontology_objects_in_the_sentiel_domain(release_dir: Path) -> None:
    for observation in _observations(release_dir):
        assert observation.domain is Domain.SENTIEL
        assert observation.entity_ids == [f"ent_{observation.context['user_id']}"]
        assert observation.feature in STARTER_FEATURES
        assert observation.context["window_seconds"] == "86400"
        assert observation.context["feature_set"] == "sentiel-starter-v1"


def test_observations_are_time_ordered(release_dir: Path) -> None:
    stamps = [observation.timestamp for observation in _observations(release_dir)]
    assert stamps == sorted(stamps)


def test_observation_ids_are_deterministic(release_dir: Path) -> None:
    """Two runs over one corpus produce identical ids (§3.7)."""
    first = [observation.id for observation in _observations(release_dir)]
    second = [observation.id for observation in _observations(release_dir)]
    assert first == second
    assert "obs_MALLORY9_20100104_00" in first


def test_windows_are_aligned_to_midnight(release_dir: Path) -> None:
    for observation in _observations(release_dir):
        assert observation.timestamp.time() == datetime.min.time()


def test_out_of_order_events_raise_rather_than_being_lost(release_dir: Path) -> None:
    events = [
        EnterpriseEvent(
            timestamp=datetime(2010, 1, 5, 9, 0, tzinfo=UTC),
            user_id="A",
            event_kind=EventKind.LOGON,
        ),
        EnterpriseEvent(
            timestamp=datetime(2010, 1, 4, 9, 0, tzinfo=UTC),
            user_id="A",
            event_kind=EventKind.LOGON,
        ),
    ]
    with pytest.raises(ValueError, match="time-ordered"):
        Featuriser().observations(events)


def test_no_events_produce_no_observations() -> None:
    assert Featuriser().observations([]) == []


def test_org_domains_decide_what_external_means(release_dir: Path) -> None:
    """Treat gmail as internal and Mallory's leak stops counting — the knob is data, not a guess."""
    reader = CertReader.for_release(CertRelease.discover(release_dir))
    featuriser = Featuriser(org_domains=frozenset({"dtaa.com", "gmail.com"}))
    values = _lookup(featuriser.observations(reader.events()))
    assert values[("MALLORY9", MONDAY_4TH, "external_email_count")] == 0.0


class TestWorkingHours:
    def test_a_weekday_inside_the_span_is_working(self) -> None:
        assert WorkingHours().contains(datetime(2010, 1, 4, 9, 0, tzinfo=UTC))

    def test_the_start_hour_is_inclusive(self) -> None:
        assert WorkingHours().contains(datetime(2010, 1, 4, 8, 0, tzinfo=UTC))

    def test_the_end_hour_is_exclusive(self) -> None:
        assert WorkingHours().contains(datetime(2010, 1, 4, 17, 59, tzinfo=UTC))
        assert not WorkingHours().contains(datetime(2010, 1, 4, 18, 0, tzinfo=UTC))

    def test_before_the_start_hour_is_off_hours(self) -> None:
        assert not WorkingHours().contains(datetime(2010, 1, 4, 7, 59, tzinfo=UTC))

    def test_the_whole_weekend_is_off_hours(self) -> None:
        saturday = datetime(2010, 1, 9, 12, 0, tzinfo=UTC)
        sunday = datetime(2010, 1, 10, 12, 0, tzinfo=UTC)
        assert not WorkingHours().contains(saturday)
        assert not WorkingHours().contains(sunday)

    def test_the_pattern_is_configurable(self) -> None:
        weekend_shift = WorkingHours(start_hour=0, end_hour=24, workdays=frozenset({5, 6}))
        assert weekend_shift.contains(datetime(2010, 1, 9, 3, 0, tzinfo=UTC))
        assert not weekend_shift.contains(datetime(2010, 1, 4, 9, 0, tzinfo=UTC))


def test_a_sub_day_window_splits_the_day() -> None:
    """The window is configurable; the default is a day and nothing in this PART changes it."""
    events = [
        EnterpriseEvent(
            timestamp=datetime(2010, 1, 4, hour, 0, tzinfo=UTC),
            user_id="A",
            event_kind=EventKind.LOGON,
        )
        for hour in (1, 2, 13)
    ]
    observations = Featuriser(window=timedelta(hours=12)).observations(events)
    windows = sorted({observation.timestamp for observation in observations})
    assert windows == [
        datetime(2010, 1, 4, 0, 0, tzinfo=UTC),
        datetime(2010, 1, 4, 12, 0, tzinfo=UTC),
    ]


def test_a_file_event_with_no_filename_still_counts_as_an_access() -> None:
    """The count and the distinct set answer different questions and must not be conflated."""
    events = [
        EnterpriseEvent(
            timestamp=MONDAY_4TH,
            user_id="A",
            event_kind=EventKind.FILE_ACCESS,
            details={},
        )
    ]
    values = _lookup(Featuriser().observations(events))
    assert values[("A", MONDAY_4TH, "file_access_count")] == 1.0
    assert values[("A", MONDAY_4TH, "distinct_files")] == 0.0


def test_an_http_event_with_no_resolvable_host_adds_no_host() -> None:
    events = [
        EnterpriseEvent(
            timestamp=MONDAY_4TH,
            user_id="A",
            event_kind=EventKind.HTTP_REQUEST,
            details={},
        )
    ]
    values = _lookup(Featuriser().observations(events))
    assert values[("A", MONDAY_4TH, "distinct_http_hosts")] == 0.0


# ================================================================================================
# PART 6A — the enriched feature set
# ================================================================================================

ALICE = "ALICE001"
BOB = "BOB00002"

# Daily counts with mean 5 and population standard deviation exactly 2, so every expected z-score
# below is a whole number. The ninth day is the one under test.
DAILY = (2, 4, 4, 4, 5, 5, 7, 9)
NINTH_DAY = 8


def _day(index: int) -> datetime:
    """Return midnight on the ``index``-th day of the fixture, counting from Monday 4 January."""
    return MONDAY_4TH + timedelta(days=index)


def _logons(user: str, index: int, count: int, pc: str = "PC-1") -> list[EnterpriseEvent]:
    return [
        EnterpriseEvent(
            timestamp=_day(index) + timedelta(hours=9, minutes=minute),
            user_id=user,
            event_kind=EventKind.LOGON,
            details={DETAIL_PC: pc},
        )
        for minute in range(count)
    ]


def _file_accesses(user: str, index: int, count: int) -> list[EnterpriseEvent]:
    return [
        EnterpriseEvent(
            timestamp=_day(index) + timedelta(hours=10, minutes=minute),
            user_id=user,
            event_kind=EventKind.FILE_ACCESS,
            details={DETAIL_PC: "PC-1", DETAIL_FILENAME: f"doc-{minute}.doc"},
        )
        for minute in range(count)
    ]


def _visits(user: str, index: int, *hosts: str) -> list[EnterpriseEvent]:
    return [
        EnterpriseEvent(
            timestamp=_day(index) + timedelta(hours=11, minutes=minute),
            user_id=user,
            event_kind=EventKind.HTTP_REQUEST,
            details={DETAIL_PC: "PC-1", DETAIL_URL_HOST: host},
        )
        for minute, host in enumerate(hosts)
    ]


def _mails(user: str, index: int, *recipients: str) -> list[EnterpriseEvent]:
    """One send per recipient, so ``external_email_ratio`` has a hand-countable denominator."""
    return [
        EnterpriseEvent(
            timestamp=_day(index) + timedelta(hours=12, minutes=minute),
            user_id=user,
            event_kind=EventKind.EMAIL_SEND,
            details={
                DETAIL_RECIPIENTS: recipient,
                DETAIL_RECIPIENT_DOMAINS: recipient.rpartition("@")[2],
            },
        )
        for minute, recipient in enumerate(recipients)
    ]


def _enriched(events: list[EnterpriseEvent]) -> list[Observation]:
    """Featurise a hand-built stream with the enriched set, time-ordering it first."""
    ordered = sorted(events, key=lambda event: event.timestamp)
    return Featuriser(feature_set=FeatureSet.ENRICHED).observations(ordered)


def _steady(user: str, count: int, days: int = 8, pc: str = "PC-1") -> list[EnterpriseEvent]:
    """``days`` identical windows of ``count`` logons, which is a history with no variance."""
    return [event for index in range(days) for event in _logons(user, index, count, pc)]


def _graded(user: str, counts: tuple[int, ...] = DAILY) -> list[EnterpriseEvent]:
    """One window per entry, logons and file accesses both following ``counts``."""
    return [
        event
        for index, count in enumerate(counts)
        for event in (*_logons(user, index, count), *_file_accesses(user, index, count))
    ]


# ------------------------------------------------------------------------------------------------
# The feature set itself
# ------------------------------------------------------------------------------------------------


class TestTheEnrichedFeatureSet:
    def test_it_is_a_strict_superset_of_the_starter_set(self) -> None:
        """So any change in the measured numbers is attributable to what was added."""
        assert ENRICHED_FEATURES[: len(STARTER_FEATURES)] == STARTER_FEATURES
        assert set(STARTER_FEATURES) < set(ENRICHED_FEATURES)

    def test_it_is_the_three_families_and_nothing_else(self) -> None:
        assert set(ENRICHED_FEATURES) == set(STARTER_FEATURES) | set(RELATIONSHIP_FEATURES) | set(
            BASELINE_RELATIVE_FEATURES
        ) | set(TEMPORAL_FEATURES)

    def test_every_feature_name_is_unique(self) -> None:
        assert len(set(ENRICHED_FEATURES)) == len(ENRICHED_FEATURES)

    def test_every_starter_count_has_a_baseline_relative_companion(self) -> None:
        """PART 6A §5.2: the mandate is every starter count, not a chosen few."""
        assert BASELINE_RELATIVE_FEATURES == tuple(f"{name}_dev" for name in STARTER_FEATURES)

    def test_the_temporal_family_covers_the_onset_signals_with_both_operators(self) -> None:
        for signal in ONSET_SIGNALS:
            assert f"{signal}_diff" in TEMPORAL_FEATURES
            assert f"{signal}_trend" in TEMPORAL_FEATURES
        assert set(ONSET_SIGNALS) < set(STARTER_FEATURES)

    def test_the_starter_set_is_still_the_default(self) -> None:
        """PART 6·D's baseline must stay reproducible from this same code."""
        assert Featuriser().feature_set is FeatureSet.STARTER
        assert Featuriser().feature_names == STARTER_FEATURES

    def test_asking_for_the_enriched_set_gets_every_enriched_feature(self) -> None:
        featuriser = Featuriser(feature_set=FeatureSet.ENRICHED)
        assert featuriser.feature_names == ENRICHED_FEATURES


# ------------------------------------------------------------------------------------------------
# Causality — PART 6A acceptance criterion 1
# ------------------------------------------------------------------------------------------------


class TestCausality:
    def test_the_current_window_is_absent_from_its_own_baseline(self) -> None:
        """The test that fails if today leaks into the history it is judged against.

        Eight windows of ten logons give a trailing mean of 10 and a trailing standard deviation of
        0, so a hundred logons is a departure reported at the cap. Had the hundred been folded in
        first, the mean would be 20 and the standard deviation 30, giving about 2.67 instead.
        """
        events = _steady(ALICE, 10) + _logons(ALICE, NINTH_DAY, 100)
        values = _lookup(_enriched(events))
        assert values[(ALICE, _day(NINTH_DAY), "logon_count")] == 100.0
        assert values[(ALICE, _day(NINTH_DAY), "logon_count_dev")] == 10.0

    def test_a_later_window_cannot_change_an_earlier_windows_features(self) -> None:
        """The strongest statement of "reads only days < t" the featuriser can make."""
        history = _graded(ALICE)
        before = _lookup(_enriched(history + _logons(ALICE, NINTH_DAY, 11)))
        after = _lookup(_enriched(history + _logons(ALICE, NINTH_DAY, 11) + _logons(ALICE, 9, 900)))
        earlier = {key: value for key, value in after.items() if key[1] <= _day(NINTH_DAY)}
        assert earlier == before

    def test_the_first_window_of_all_has_no_history_to_read(self) -> None:
        values = _lookup(_enriched(_logons(ALICE, 0, 5)))
        for feature in (*BASELINE_RELATIVE_FEATURES, *TEMPORAL_FEATURES, "new_pcs"):
            assert values[(ALICE, _day(0), feature)] == NEUTRAL_VALUE


# ------------------------------------------------------------------------------------------------
# Baseline-relative features — PART 6A acceptance criterion 3
# ------------------------------------------------------------------------------------------------


class TestBaselineRelativeFeatures:
    @pytest.mark.parametrize(("count", "expected"), [(11, 3.0), (9, 2.0), (5, 0.0), (1, -2.0)])
    def test_a_deviation_is_a_signed_z_score_against_the_users_own_history(
        self, count: int, expected: float
    ) -> None:
        """Trailing mean 5, trailing population standard deviation 2, so (count - 5) / 2."""
        values = _lookup(_enriched(_graded(ALICE) + _logons(ALICE, NINTH_DAY, count)))
        assert values[(ALICE, _day(NINTH_DAY), "logon_count_dev")] == expected

    def test_the_level_is_still_emitted_beside_the_deviation(self) -> None:
        values = _lookup(_enriched(_graded(ALICE) + _logons(ALICE, NINTH_DAY, 11)))
        assert values[(ALICE, _day(NINTH_DAY), "logon_count")] == 11.0

    def test_a_user_who_never_varied_gets_the_capped_value_not_an_infinity(self) -> None:
        """The divide-by-zero policy, end to end through the featuriser."""
        values = _lookup(_enriched(_steady(ALICE, 4) + _logons(ALICE, NINTH_DAY, 5)))
        assert values[(ALICE, _day(NINTH_DAY), "logon_count_dev")] == 10.0

    def test_a_user_who_never_varied_and_did_not_change_reports_zero(self) -> None:
        values = _lookup(_enriched(_steady(ALICE, 4) + _logons(ALICE, NINTH_DAY, 4)))
        assert values[(ALICE, _day(NINTH_DAY), "logon_count_dev")] == 0.0

    def test_before_enough_history_every_deviation_is_the_documented_neutral(self) -> None:
        """Seven windows is one short of the default eight, so nothing may be claimed yet."""
        events = _steady(ALICE, 10, days=7) + _logons(ALICE, 7, 900)
        values = _lookup(_enriched(events))
        for feature in BASELINE_RELATIVE_FEATURES:
            assert values[(ALICE, _day(7), feature)] == NEUTRAL_VALUE

    def test_the_history_policy_is_configurable(self) -> None:
        featuriser = Featuriser(
            feature_set=FeatureSet.ENRICHED,
            history_policy=HistoryPolicy(min_history_windows=3, trend_windows=3),
        )
        events = sorted(
            _steady(ALICE, 10, days=3) + _logons(ALICE, 3, 900),
            key=lambda event: event.timestamp,
        )
        values = _lookup(featuriser.observations(events))
        assert values[(ALICE, _day(3), "logon_count_dev")] == 10.0


# ------------------------------------------------------------------------------------------------
# Temporal features — PART 6A acceptance criterion 3
# ------------------------------------------------------------------------------------------------


class TestTemporalFeatures:
    def test_a_first_difference_is_today_minus_the_prior_populated_window(self) -> None:
        """File accesses run ... 7, 9 and then 11, so the last step is +2."""
        values = _lookup(_enriched(_graded(ALICE) + _file_accesses(ALICE, NINTH_DAY, 11)))
        assert values[(ALICE, _day(NINTH_DAY), "file_access_count_diff")] == 2.0

    def test_a_first_difference_is_signed(self) -> None:
        values = _lookup(_enriched(_graded(ALICE) + _file_accesses(ALICE, NINTH_DAY, 4)))
        assert values[(ALICE, _day(NINTH_DAY), "file_access_count_diff")] == -5.0

    def test_a_trend_is_the_least_squares_slope_over_the_trailing_week(self) -> None:
        """Series [4, 4, 5, 5, 7, 9, 11] over x = 0..6: slope = 33 / 28 by hand."""
        values = _lookup(_enriched(_graded(ALICE) + _file_accesses(ALICE, NINTH_DAY, 11)))
        assert values[(ALICE, _day(NINTH_DAY), "file_access_count_trend")] == pytest.approx(
            33.0 / 28.0
        )

    def test_a_flat_user_has_no_trend_and_no_step(self) -> None:
        events = _graded(ALICE, (3,) * 8) + _file_accesses(ALICE, NINTH_DAY, 3)
        values = _lookup(_enriched(events))
        assert values[(ALICE, _day(NINTH_DAY), "file_access_count_diff")] == 0.0
        assert values[(ALICE, _day(NINTH_DAY), "file_access_count_trend")] == 0.0

    def test_a_weekend_moves_off_hours_logons_and_the_temporal_terms_say_so(self) -> None:
        """Not a defect: by the configured working pattern all weekend activity *is* off-hours.

        The fixture runs from Monday 4 January, so windows 5 and 6 are the Saturday and Sunday. A
        user logging on identically every day therefore has a twice-weekly step in
        ``off_hours_logon_count``, and the temporal terms report it. Any real deployment must set
        `WorkingHours` to the pattern the organisation actually keeps, or read a weekly rhythm as
        an escalation.
        """
        values = _lookup(_enriched(_steady(ALICE, 3) + _logons(ALICE, NINTH_DAY, 3)))
        assert values[(ALICE, _day(5), "off_hours_logon_count")] == 3.0
        assert values[(ALICE, _day(7), "off_hours_logon_count")] == 0.0
        assert values[(ALICE, _day(NINTH_DAY), "off_hours_logon_count_trend")] != 0.0

    def test_a_prior_window_is_the_prior_populated_one_not_the_prior_calendar_day(self) -> None:
        """A user idle for a fortnight steps from what they last did, not from an implied zero."""
        events = _file_accesses(ALICE, 0, 3) + _file_accesses(ALICE, 14, 10)
        values = _lookup(_enriched(events))
        assert values[(ALICE, _day(14), "file_access_count_diff")] == 7.0


# ------------------------------------------------------------------------------------------------
# Relationship features — PART 6A acceptance criteria 3 and 4
# ------------------------------------------------------------------------------------------------


class TestRelationshipFeatures:
    def test_distinct_email_recipients_counts_addresses_not_messages(self) -> None:
        events = _mails(ALICE, 0, "bob@dtaa.com", "bob@dtaa.com", "carol@dtaa.com")
        values = _lookup(_enriched(events))
        assert values[(ALICE, _day(0), "distinct_email_recipients")] == 2.0

    def test_a_recipient_is_one_counterparty_however_it_is_capitalised(self) -> None:
        events = _mails(ALICE, 0, "Bob@DTAA.com", "bob@dtaa.com")
        values = _lookup(_enriched(events))
        assert values[(ALICE, _day(0), "distinct_email_recipients")] == 1.0

    def test_the_external_ratio_is_external_sends_over_all_sends(self) -> None:
        """One of two messages left the organisation, so 0.5 by hand."""
        events = _mails(ALICE, 0, "bob@dtaa.com", "friend@gmail.com")
        values = _lookup(_enriched(events))
        assert values[(ALICE, _day(0), "external_email_ratio")] == 0.5
        assert values[(ALICE, _day(0), "external_email_count")] == 1.0

    def test_a_day_with_no_mail_at_all_has_a_ratio_of_zero(self) -> None:
        values = _lookup(_enriched(_logons(ALICE, 0, 1)))
        assert values[(ALICE, _day(0), "external_email_ratio")] == 0.0

    def test_new_pcs_counts_machines_this_user_has_not_used_recently(self) -> None:
        events = _steady(ALICE, 2) + _logons(ALICE, NINTH_DAY, 2, pc="PC-1")
        events += _logons(ALICE, NINTH_DAY, 1, pc="PC-9")
        values = _lookup(_enriched(events))
        assert values[(ALICE, _day(NINTH_DAY), "distinct_pcs")] == 2.0
        assert values[(ALICE, _day(NINTH_DAY), "new_pcs")] == 1.0

    def test_a_machine_the_user_already_uses_is_not_new(self) -> None:
        events = _steady(ALICE, 2) + _logons(ALICE, NINTH_DAY, 2, pc="PC-1")
        values = _lookup(_enriched(events))
        assert values[(ALICE, _day(NINTH_DAY), "new_pcs")] == 0.0

    def test_new_counterparties_counts_hosts_and_recipients_the_user_has_not_reached(self) -> None:
        events = [
            event
            for index in range(8)
            for event in (
                *_visits(ALICE, index, "intranet.dtaa.com"),
                *_mails(ALICE, index, "bob@dtaa.com"),
            )
        ]
        events += _visits(ALICE, NINTH_DAY, "intranet.dtaa.com", "wikileaks.org")
        events += _mails(ALICE, NINTH_DAY, "bob@dtaa.com", "self@gmail.com")
        values = _lookup(_enriched(events))
        assert values[(ALICE, _day(NINTH_DAY), "new_counterparties")] == 2.0

    def test_new_means_new_for_this_user_not_new_to_the_organisation(self) -> None:
        """The whole point of the family: Bob's daily host is still new to Alice."""
        alice = [
            event for index in range(8) for event in _visits(ALICE, index, "intranet.dtaa.com")
        ]
        alice += _visits(ALICE, NINTH_DAY, "dropbox.com")
        bob = [
            event for index in range(NINTH_DAY + 1) for event in _visits(BOB, index, "dropbox.com")
        ]
        values = _lookup(_enriched(alice + bob))
        assert values[(ALICE, _day(NINTH_DAY), "new_counterparties")] == 1.0

    def test_before_enough_history_the_new_counterparty_counts_are_neutral(self) -> None:
        """Everything is new to someone with no past; counting it would measure the start date."""
        events = [event for index in range(7) for event in _visits(ALICE, index, f"host-{index}")]
        values = _lookup(_enriched(events))
        assert values[(ALICE, _day(6), "new_counterparties")] == NEUTRAL_VALUE
        assert values[(ALICE, _day(6), "new_pcs")] == NEUTRAL_VALUE


class TestTheRelationshipFeaturesAreStrictlyPerEntity:
    """PART 6A acceptance criterion 4, and the boundary 6B is on the far side of."""

    def _alice(self) -> list[EnterpriseEvent]:
        return _graded(ALICE) + _logons(ALICE, NINTH_DAY, 11) + _visits(ALICE, NINTH_DAY, "a.com")

    def test_another_users_events_do_not_change_this_users_features(self) -> None:
        alone = _lookup(_enriched(self._alice()))
        noisy = [
            event
            for index in range(NINTH_DAY + 1)
            for event in (
                *_logons(BOB, index, 400, pc="PC-77"),
                *_visits(BOB, index, "a.com", "b.com"),
                *_mails(BOB, index, "someone@elsewhere.com"),
            )
        ]
        together = _lookup(_enriched(self._alice() + noisy))
        assert {key: value for key, value in together.items() if key[0] == ALICE} == alone

    def test_a_user_alone_in_the_corpus_gets_the_same_answers(self) -> None:
        """The converse: removing everyone else changes nothing either."""
        together = _lookup(_enriched(self._alice() + _steady(BOB, 99, days=NINTH_DAY + 1)))
        assert {key: value for key, value in together.items() if key[0] == ALICE} == _lookup(
            _enriched(self._alice())
        )


# ------------------------------------------------------------------------------------------------
# Ontology cleanliness — PART 6A acceptance criteria 2 and 5
# ------------------------------------------------------------------------------------------------


class TestOntologyCleanliness:
    def _mixed(self) -> list[Observation]:
        events = _graded(ALICE) + _logons(ALICE, NINTH_DAY, 11)
        events += _visits(ALICE, NINTH_DAY, "wikileaks.org")
        events += _mails(ALICE, NINTH_DAY, "self@gmail.com", "bob@dtaa.com")
        events += _steady(BOB, 1, days=NINTH_DAY + 1)
        return _enriched(events)

    def test_every_window_emits_every_enriched_feature_exactly_once(self) -> None:
        by_window: dict[tuple[str, datetime], list[str]] = {}
        for observation in self._mixed():
            key = (observation.context["user_id"], observation.timestamp)
            by_window.setdefault(key, []).append(observation.feature)
        assert by_window
        for features in by_window.values():
            assert features == list(ENRICHED_FEATURES)

    def test_every_observation_is_a_well_formed_sentiel_observation(self) -> None:
        for observation in self._mixed():
            assert observation.domain is Domain.SENTIEL
            assert observation.entity_ids == [f"ent_{observation.context['user_id']}"]
            assert observation.feature in ENRICHED_FEATURES
            assert isinstance(observation.value, float)
            assert observation.timestamp.time() == datetime.min.time()
            assert observation.context["window_seconds"] == "86400"
            assert observation.context["feature_set"] == "sentiel-enriched-v1"

    def test_no_value_is_ever_nan_or_infinite(self) -> None:
        """A NaN would poison a learned mean; an infinity would not even serialise."""
        for observation in self._mixed():
            assert math.isfinite(observation.value)

    def test_observations_stay_time_ordered(self) -> None:
        stamps = [observation.timestamp for observation in self._mixed()]
        assert stamps == sorted(stamps)

    def test_the_enriched_run_is_deterministic(self) -> None:
        first = [(o.id, o.feature, o.value) for o in self._mixed()]
        second = [(o.id, o.feature, o.value) for o in self._mixed()]
        assert first == second

    def test_observation_ids_stay_unique_across_the_wider_feature_set(self) -> None:
        ids = [observation.id for observation in self._mixed()]
        assert len(set(ids)) == len(ids)

    def test_an_enriched_set_without_a_history_is_refused_rather_than_faked(self) -> None:
        """Emitting neutral values for every enrichment would report them as measurements."""
        from phos.sentiel.featurise import _Accumulator

        with pytest.raises(ValueError, match="trailing history"):
            list(
                _Accumulator().observations(
                    ALICE, _day(0), timedelta(days=1), FeatureSet.ENRICHED, None
                )
            )


# ------------------------------------------------------------------------------------------------
# The caveats that must travel with an enriched number — PART 6A §6
# ------------------------------------------------------------------------------------------------


class TestTheEnrichedSourceNote:
    def test_it_carries_every_part_6a_caveat(self) -> None:
        note = enriched_source_note("CERT r3.1", base_rate="53 malicious of 340171 user-windows")
        assert note.startswith("CERT r3.1")
        assert "53 malicious of 340171 user-windows" in note
        for caveat in ENRICHED_CAVEATS:
            assert caveat in note

    def test_it_names_the_four_things_part_6a_requires(self) -> None:
        joined = " ".join(ENRICHED_CAVEATS)
        assert "ENRICHED" in joined
        assert "NO PEER CONTEXT" in joined
        assert "OVERFIT A SHORT HISTORY" in joined
        assert "ONLY 2 USERS" in joined

    def test_it_still_carries_the_part_6d_caveats_that_remain_true(self) -> None:
        note = enriched_source_note("CERT r3.1")
        still_true = [c for c in SENTIEL_CAVEATS if SUPERSEDED_CAVEAT_MARKER not in c]
        assert len(still_true) == 2
        for caveat in still_true:
            assert caveat in note
        assert "SYNTHETIC" in note
        assert "ENTITY-SCOPED" in note

    def test_it_drops_the_one_part_6d_caveat_this_feature_set_outdates(self) -> None:
        note = enriched_source_note("CERT r3.1")
        superseded = [c for c in SENTIEL_CAVEATS if SUPERSEDED_CAVEAT_MARKER in c]
        assert len(superseded) == 1, "the marker must identify exactly one caveat"
        assert superseded[0] not in note

    def test_the_marker_still_matches_a_part_6d_caveat(self) -> None:
        """If 6B rewrites that caveat, this fails loudly rather than stamping a stale claim."""
        assert sum(SUPERSEDED_CAVEAT_MARKER in c for c in SENTIEL_CAVEATS) == 1

    def test_the_part_6d_caveats_themselves_are_untouched(self) -> None:
        """PART 6A must not edit the entity-aware evaluation, only decline to quote one line."""
        assert len(SENTIEL_CAVEATS) == 3
        assert "STARTER" in " ".join(SENTIEL_CAVEATS)


# ------------------------------------------------------------------------------------------------
# The layers below are reused, not modified — PART 6A acceptance criterion 5
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("package", ["src/phos/eval", "src/phos/models"])
def test_the_reused_packages_are_unmodified_in_git(package: str) -> None:
    """The strongest available statement of "the model and the harness were reused as they were"."""
    repo = Path(__file__).resolve().parents[2]
    try:
        completed = subprocess.run(
            ["git", "diff", "HEAD", "--name-only", "--", package],
            capture_output=True,
            text=True,
            check=False,
            cwd=repo,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as error:  # pragma: no cover - env dependent
        pytest.skip(f"git unavailable: {error}")
    if completed.returncode != 0:  # pragma: no cover - env dependent
        pytest.skip(f"not a git checkout: {completed.stderr.strip()}")
    # ADR 0086 adds the empirical baseline beside the frozen Gaussian module. The rest of
    # src/phos/models, including gaussian.py, stays out of this list.
    opened_after = {
        "src/phos/models/empirical.py",
        "src/phos/models/__init__.py",
    }
    leftover = [line for line in completed.stdout.splitlines() if line and line not in opened_after]
    assert leftover == [], (
        f"PART 6A must reuse {package} unchanged, but git reports:\n{completed.stdout}"
    )


def test_the_entity_aware_evaluation_is_unmodified_in_git() -> None:
    """6A adds a source note beside `SENTIEL_CAVEATS`; it does not edit the evaluation."""
    repo = Path(__file__).resolve().parents[2]
    try:
        completed = subprocess.run(
            ["git", "diff", "HEAD", "--name-only", "--", "src/phos/sentiel/evaluation.py"],
            capture_output=True,
            text=True,
            check=False,
            cwd=repo,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as error:  # pragma: no cover - env dependent
        pytest.skip(f"git unavailable: {error}")
    if completed.returncode != 0:  # pragma: no cover - env dependent
        pytest.skip(f"not a git checkout: {completed.stderr.strip()}")
    assert completed.stdout.strip() == "", (
        f"PART 6A must not modify the entity-aware evaluation:\n{completed.stdout}"
    )


# ================================================================================================
# The end-to-end enriched baseline — PART 6A acceptance criterion 6
#
# `scripts/` is on pytest's path (see pyproject), so the measurement script itself is testable, and
# the streamed two-pass split it uses to fit the enriched corpus into memory is checked against
# PART 3's list-based `train_test_split` rather than trusted to agree with it.
# ================================================================================================

CORPUS_DAYS = 30
ATTACK_DAY = 12


def _corpus_events() -> list[EnterpriseEvent]:
    """Three users over thirty days: two ordinary, one who escalates from the attack day.

    The attack starts 41% of the way through, as r3.1's does, so the earliest attack — not the
    ``train_fraction`` ceiling — is what binds the split. That is the case the streamed two-pass
    split reproduces, and `check_the_attack_bound_the_split` is what refuses the other one.
    """
    events: list[EnterpriseEvent] = []
    for index in range(CORPUS_DAYS):
        events += _logons(ALICE, index, 2)
        events += _file_accesses(ALICE, index, 3)
        events += _visits(ALICE, index, "intranet.dtaa.com")
        events += _logons(BOB, index, 3)
        events += _mails(BOB, index, "alice@dtaa.com")
        events += _logons(MALLORY, index, 2, pc="PC-3")
        events += _file_accesses(MALLORY, index, 2 if index < ATTACK_DAY else 60)
        if index >= ATTACK_DAY:
            events += _visits(MALLORY, index, "wikileaks.org", "dropbox.com")
            events += _mails(MALLORY, index, "self@gmail.com")
            events += _logons(MALLORY, index, 8, pc="PC-99")
    return sorted(events, key=lambda event: event.timestamp)


MALLORY = "MALLORY9"
LABELS = [
    EntityLabelledInterval(
        user_id=MALLORY,
        start=MONDAY_4TH + timedelta(days=ATTACK_DAY, hours=1),
        end=MONDAY_4TH + timedelta(days=CORPUS_DAYS),
        scenario="1",
        release="3.1",
    )
]


CORPUS_GROUPS = PeerGroups(
    group_attribute="role",
    min_group_size=2,
    membership={ALICE: "Salesman", BOB: "Salesman", MALLORY: "Salesman"},
    declared_sizes={"Salesman": 3},
)
"""All three fixture users in one declared group, so the peer features actually fire here.

``min_group_size`` is 2 rather than the production default of 5 because the fixture has three
people; the boundary itself is tested where it belongs, in ``tests/sentiel/test_peers.py``.
"""


def _stream_factory(
    feature_set: FeatureSet = FeatureSet.ENRICHED,
) -> tuple[Featuriser, Callable[[], Iterator[Observation]]]:
    """Return a featuriser and something that yields a fresh stream over the fixture each call."""
    featuriser = Featuriser(
        feature_set=feature_set,
        peer_groups=CORPUS_GROUPS if feature_set.needs_peers else None,
    )
    events = _corpus_events()
    return featuriser, (lambda: featuriser.stream(iter(events)))


class TestTheStreamedSplitMatchesPart3s:
    """The safety net under reading the corpus twice instead of holding it once."""

    def _both(self, feature_set: FeatureSet) -> tuple[list[Observation], list[Observation]]:
        _, factory = _stream_factory(feature_set)
        first_attack = LABELS[0].start
        return (
            training_prefix(factory(), first_attack),
            evaluation_remainder(factory(), first_attack),
        )

    def _list_based(self, feature_set: FeatureSet) -> tuple[Dataset, Dataset]:
        _, factory = _stream_factory(feature_set)
        dataset = Dataset(
            name="fixture",
            domain=Domain.SENTIEL,
            observations=list(factory()),
            attack_intervals=[label.as_labelled_interval() for label in LABELS],
        )
        return train_test_split(dataset, SplitPolicy(train_fraction=0.5))

    @pytest.mark.parametrize("feature_set", list(FeatureSet))
    def test_it_reproduces_train_test_splits_partition_exactly(
        self, feature_set: FeatureSet
    ) -> None:
        streamed_train, streamed_test = self._both(feature_set)
        listed_train, listed_test = self._list_based(feature_set)
        assert [o.id for o in streamed_train] == [o.id for o in listed_train.observations]
        assert [o.id for o in streamed_test] == [o.id for o in listed_test.observations]

    def test_it_reproduces_the_values_and_not_merely_the_partition(self) -> None:
        """Reading the corpus twice must give the same features both times."""
        streamed_train, streamed_test = self._both(FeatureSet.ENRICHED)
        listed_train, listed_test = self._list_based(FeatureSet.ENRICHED)
        assert [o.value for o in streamed_train] == [o.value for o in listed_train.observations]
        assert [o.value for o in streamed_test] == [o.value for o in listed_test.observations]

    def test_the_two_halves_partition_the_corpus_with_nothing_lost_or_shared(self) -> None:
        train, test = self._both(FeatureSet.ENRICHED)
        assert train and test
        assert not {o.id for o in train} & {o.id for o in test}
        _, factory = _stream_factory()
        assert len(train) + len(test) == len(list(factory()))

    def test_no_training_observation_is_stamped_at_or_after_the_first_attack(self) -> None:
        train, _ = self._both(FeatureSet.ENRICHED)
        assert max(o.timestamp for o in train) < LABELS[0].start


class TestTheSplitCeilingIsChecked:
    def test_an_attack_bound_split_passes(self) -> None:
        check_the_attack_bound_the_split(
            _day(0), _day(CORPUS_DAYS), LABELS[0].start, train_fraction=0.5
        )

    def test_a_fraction_bound_split_is_refused_rather_than_silently_leaking(self) -> None:
        """At a low fraction PART 3 would cut earlier, so the streamed prefix would over-train."""
        with pytest.raises(BaselineError, match="train-fraction"):
            check_the_attack_bound_the_split(
                _day(0), _day(CORPUS_DAYS), LABELS[0].start, train_fraction=0.1
            )


class TestTheSideBySideComparison:
    def _report(self, precision: float) -> EvaluationReport:
        return EvaluationReport(
            detector_name="model:gaussian",
            dataset_name="fixture",
            domain=Domain.SENTIEL,
            seed=7,
            alert_threshold=3.0,
            match_tolerance_seconds=0.0,
            calibration_bins=10,
            n_observations=100,
            n_detections=10,
            n_alerts=10,
            n_attack_intervals=1,
            normal_hours=100.0,
            window_recall=1.0,
            false_positives=1,
            false_positive_rate=0.01,
            precision=precision,
            recall_sample=0.5,
            f1=0.5,
            latency=LatencySummary.from_latencies([]),
            expected_calibration_error=0.5,
            brier_score=0.5,
        )

    COUNTS: ClassVar[dict[str, int]] = {
        "malicious_user_windows": 53,
        "benign_user_windows": 210_761,
    }

    def test_the_reference_multiple_is_the_one_part_6d_reported(self) -> None:
        """PART 6·D read its 0.004061 precision as about 16x the alert-on-everything floor."""
        assert BASELINE_6D.multiple_over_trivial == pytest.approx(16.15, abs=0.05)
        assert BASELINE_6D.trivial_precision == pytest.approx(2.514e-4, rel=1e-3)

    @pytest.mark.parametrize(
        ("precision", "verdict"),
        [(0.0040609137055837565, "NO CHANGE"), (0.02, "BETTER"), (0.0005, "WORSE")],
    )
    def test_the_verdict_follows_the_multiple_over_the_trivial_floor(
        self, precision: float, verdict: str
    ) -> None:
        note = side_by_side(self._report(precision), self.COUNTS, 26, BASELINE_6D)
        assert f"VERDICT: {verdict}" in note

    def test_it_names_both_runs_and_refuses_to_quote_recall(self) -> None:
        note = side_by_side(self._report(0.01), self.COUNTS, 26, BASELINE_6D)
        assert "PART 6·D" in note
        assert "8 features" in note
        assert "26 features" in note
        assert "not quotable at 2 insiders" in note

    def test_a_run_with_no_windows_at_all_does_not_divide_by_zero(self) -> None:
        empty = {"malicious_user_windows": 0, "benign_user_windows": 0}
        assert "VERDICT: WORSE" in side_by_side(self._report(0.01), empty, 26, BASELINE_6D)

    def test_the_reference_run_is_frozen(self) -> None:
        with pytest.raises(ValidationError):
            BASELINE_6D.precision = 0.5  # type: ignore[misc]


class TestTheEnrichedBaselineRunsEndToEnd:
    def _run(self, feature_set: FeatureSet = FeatureSet.ENRICHED) -> EvaluationReport:
        featuriser, factory = _stream_factory(feature_set)
        reports, _ = run(
            stream_factory=factory,
            labels=LABELS,
            featuriser=featuriser,
            dataset_name="fixture-user-day",
            provenance="hand-built fixture",
            train_fraction=0.5,
            min_samples=8,
            config=EvalConfig(alert_threshold=3.0, match_tolerance=timedelta(0), seed=7),
        )
        assert len(reports) == 1
        return reports[0]

    def test_it_produces_a_report_with_in_range_values(self) -> None:
        report = self._run()
        assert 0.0 <= report.precision <= 1.0
        assert 0.0 <= report.window_recall <= 1.0
        assert 0.0 <= report.recall_sample <= 1.0
        assert 0.0 <= report.expected_calibration_error <= 1.0
        assert 0.0 <= report.brier_score <= 1.0
        assert report.n_alerts <= report.n_detections
        assert report.n_attack_intervals == 1
        assert report.domain is Domain.SENTIEL

    def test_the_enriched_corpus_is_the_one_that_was_scored(self) -> None:
        report = self._run()
        assert report.n_observations % len(ENRICHED_FEATURES) == 0
        assert report.dataset_name == "fixture-user-day-test"

    def test_every_part_6a_caveat_travels_on_the_report(self) -> None:
        note = self._run().source_note
        for caveat in ENRICHED_CAVEATS:
            assert caveat in note

    def test_the_part_6d_caveats_that_still_hold_travel_too(self) -> None:
        note = self._run().source_note
        for caveat in SENTIEL_CAVEATS:
            if SUPERSEDED_CAVEAT_MARKER not in caveat:
                assert caveat in note

    def test_the_side_by_side_comparison_travels_on_the_report(self) -> None:
        """PART 6A acceptance criterion 6: the comparison field, not just the caveats."""
        note = self._run().source_note
        assert "SIDE-BY-SIDE vs PART 6·D" in note
        assert "VERDICT:" in note
        assert BASELINE_6D.commit in note

    def test_the_base_rate_travels_too(self) -> None:
        assert "base rate" in self._run().source_note

    def test_a_starter_run_carries_the_part_6d_caveats_unchanged(self) -> None:
        """The reproduction path must not quietly acquire PART 6A's note."""
        note = self._run(FeatureSet.STARTER).source_note
        for caveat in SENTIEL_CAVEATS:
            assert caveat in note

    def test_the_run_is_deterministic(self) -> None:
        first, second = self._run(), self._run()
        assert first.precision == second.precision
        assert first.n_alerts == second.n_alerts
        assert first.source_note == second.source_note

    def test_extra_thresholds_produce_one_report_each_from_one_read_of_the_corpus(self) -> None:
        """The matched-alert-budget comparison: same fit, same corpus, several alert budgets."""
        featuriser, factory = _stream_factory()
        reports, _ = run(
            stream_factory=factory,
            labels=LABELS,
            featuriser=featuriser,
            dataset_name="fixture-user-day",
            provenance="hand-built fixture",
            train_fraction=0.5,
            min_samples=8,
            config=EvalConfig(alert_threshold=3.0, match_tolerance=timedelta(0), seed=7),
            extra_thresholds=[6.0, 9.0],
        )
        assert [report.alert_threshold for report in reports] == [3.0, 6.0, 9.0]
        assert [report.n_observations for report in reports] == [reports[0].n_observations] * 3
        # A higher bar cannot admit more alerts.
        assert reports[0].n_alerts >= reports[1].n_alerts >= reports[2].n_alerts
        for report in reports:
            assert "SIDE-BY-SIDE vs PART 6·D" in report.source_note

    def test_a_corpus_under_attack_from_its_first_window_has_no_training_half(self) -> None:
        featuriser, factory = _stream_factory()
        with pytest.raises(BaselineError, match="no attack-free history"):
            run(
                stream_factory=factory,
                labels=[LABELS[0].model_copy(update={"start": _day(0)})],
                featuriser=featuriser,
                dataset_name="fixture-user-day",
                provenance="hand-built fixture",
                train_fraction=0.5,
                min_samples=8,
                config=EvalConfig(),
            )

    def test_the_model_and_the_harness_needed_no_changes_to_consume_the_enriched_set(self) -> None:
        """Criterion 5, stated as behaviour: the layers below ran on 26 features as they were.

        The git assertions above say the packages are untouched; this says the untouched packages
        actually work on the wider set — that the enrichment stayed inside the featurisation layer.
        """
        report = self._run()
        assert report.detector_name == "model:gaussian"
        assert report.n_detections > 0


# ================================================================================================
# The PART 6B peer feature set — acceptance criteria 2, 3 and 5
#
# The peer *mechanism* is tested in `tests/sentiel/test_peers.py`. What is tested here is the
# featurisation: that the peer companions are well-formed ontology objects, that they are emitted
# for exactly the users who have a group and nobody else, that the 26 features beside them are
# unchanged by their presence, and that the causal boundary survives the trip through `_flush`.
# ================================================================================================

PEER_TEAM = "Salesman"


def _peer_groups(*user_ids: str, minimum: int = 2) -> PeerGroups:
    """Return declared groups putting every named user into one group, minimum size applied."""
    big_enough = len(user_ids) >= minimum
    return PeerGroups(
        group_attribute="role",
        min_group_size=minimum,
        membership=dict.fromkeys(user_ids, PEER_TEAM) if big_enough else {},
        declared_sizes={PEER_TEAM: len(user_ids)},
        ungrouped=0 if big_enough else len(user_ids),
    )


class TestThePeerFeatureSetIsAStrictSuperset:
    """Anything that changes in the numbers is attributable to what was added."""

    def test_it_opens_with_the_whole_enriched_set_in_order(self) -> None:
        assert PEER_FEATURES[: len(ENRICHED_FEATURES)] == ENRICHED_FEATURES

    def test_it_adds_one_peer_companion_per_starter_count(self) -> None:
        assert PEER_RELATIVE_FEATURES == tuple(f"{name}_peer" for name in STARTER_FEATURES)
        assert len(PEER_FEATURES) == len(ENRICHED_FEATURES) + len(STARTER_FEATURES) == 34

    def test_the_enrichments_get_no_peer_companion(self) -> None:
        """A ``_dev`` is already a difference; comparing differences is a second-order question."""
        suffixes = ("_dev_peer", "_diff_peer", "_trend_peer")
        assert not any(name.endswith(suffixes) for name in PEER_FEATURES)

    def test_every_feature_name_is_unique(self) -> None:
        assert len(set(PEER_FEATURES)) == len(PEER_FEATURES)

    def test_the_feature_set_reports_what_it_needs(self) -> None:
        assert FeatureSet.PEER.needs_history and FeatureSet.PEER.needs_peers
        assert FeatureSet.ENRICHED.needs_history and not FeatureSet.ENRICHED.needs_peers
        assert not FeatureSet.STARTER.needs_history and not FeatureSet.STARTER.needs_peers


class TestPeerObservationsAreOntologyClean:
    """A peer feature is an ordinary `Observation` and nothing downstream needs to know better."""

    def _observations(self, minimum: int = 2) -> list[Observation]:
        events = _corpus_events()
        featuriser = Featuriser(
            feature_set=FeatureSet.PEER,
            peer_groups=_peer_groups(ALICE, BOB, MALLORY, minimum=minimum),
        )
        return featuriser.observations(events)

    def test_a_grouped_user_gets_every_feature_and_they_are_all_well_formed(self) -> None:
        peers = [o for o in self._observations() if o.feature in PEER_RELATIVE_FEATURES]
        assert peers
        for observation in peers:
            assert observation.domain is Domain.SENTIEL
            assert len(observation.entity_ids) == 1
            assert observation.entity_ids[0].startswith("ent_")
            assert math.isfinite(observation.value)
            assert observation.context["feature_set"] == "sentiel-peer-v1"

    def test_a_grouped_user_emits_all_thirty_four_features_per_window(self) -> None:
        by_window: dict[tuple[str, datetime], set[str]] = defaultdict(set)
        for observation in self._observations():
            by_window[(observation.context["user_id"], observation.timestamp)].add(
                observation.feature
            )
        assert by_window
        for features in by_window.values():
            assert features == set(PEER_FEATURES)

    def test_an_ungrouped_user_emits_the_twenty_six_and_not_one_peer_feature(self) -> None:
        """No group is not a cold start: there is no peer feature for this person, ever."""
        events = _corpus_events()
        featuriser = Featuriser(
            feature_set=FeatureSet.PEER, peer_groups=_peer_groups(ALICE, BOB, minimum=2)
        )
        emitted = defaultdict(set)
        for observation in featuriser.observations(events):
            emitted[observation.context["user_id"]].add(observation.feature)
        assert emitted[ALICE] == set(PEER_FEATURES)
        assert emitted[MALLORY] == set(ENRICHED_FEATURES)

    def test_a_group_below_the_minimum_emits_nothing_for_anybody(self) -> None:
        emitted = {o.feature for o in self._observations(minimum=99)}
        assert emitted == set(ENRICHED_FEATURES)

    def test_observation_ids_stay_unique_and_tied_to_their_feature_position(self) -> None:
        """A skipped feature must not shift its neighbours' ids; an id must stay traceable."""
        observations = self._observations()
        assert len({o.id for o in observations}) == len(observations)
        for observation in observations:
            index = int(observation.id.rpartition("_")[2])
            assert PEER_FEATURES[index] == observation.feature

    def test_the_twenty_six_enriched_features_are_byte_identical_with_and_without_peers(
        self,
    ) -> None:
        """The peer family adds; it does not disturb. 6A's numbers stay 6A's numbers."""
        events = _corpus_events()
        enriched = Featuriser(feature_set=FeatureSet.ENRICHED).observations(events)
        with_peers = [
            observation
            for observation in Featuriser(
                feature_set=FeatureSet.PEER, peer_groups=_peer_groups(ALICE, BOB, MALLORY)
            ).observations(events)
            if observation.feature in ENRICHED_FEATURES
        ]
        assert [(o.id, o.feature, o.value) for o in with_peers] == [
            (o.id, o.feature, o.value) for o in enriched
        ]


class TestPeerCausalityThroughTheFeaturiser:
    """The `_flush` ordering: every user in a window is emitted before the window is pooled."""

    def _peer_values(
        self, feature: str, events: list[EnterpriseEvent]
    ) -> dict[tuple[str, int], float]:
        featuriser = Featuriser(
            feature_set=FeatureSet.PEER,
            peer_groups=_peer_groups(ALICE, BOB, MALLORY),
            history_policy=HistoryPolicy(min_history_windows=4),
        )
        return {
            (o.context["user_id"], (o.timestamp - MONDAY_4TH).days): o.value
            for o in featuriser.observations(events)
            if o.feature == feature
        }

    def test_a_cohort_spiking_together_does_not_inflate_its_own_days_peer_baseline(self) -> None:
        """Two users spike on the same day; neither may appear in the other's baseline that day.

        Advancing the peer pool per user rather than per window is a leak that raises no error and
        produces no absurd number — it just drags the peer mean toward the cohort being judged. The
        third user's peer feature is where it would show: flat on the day of the spike, and moved
        the day after.
        """
        events: list[EnterpriseEvent] = []
        for day in range(12):
            for user in (ALICE, BOB, MALLORY):
                spiking = user in (ALICE, BOB) and day == 9
                events += _logons(user, day, 40 if spiking else 4)
        events.sort(key=lambda event: event.timestamp)

        values = self._peer_values("logon_count_peer", events)
        assert values[(MALLORY, 9)] == 0.0, "the spike is not yet in the pool that judges day 9"
        assert values[(MALLORY, 10)] < 0.0, "and is in the pool that judges day 10"

    def test_a_user_is_not_in_their_own_peer_baseline(self) -> None:
        events: list[EnterpriseEvent] = []
        for day in range(12):
            events += _logons(ALICE, day, 4)
            events += _logons(BOB, day, 4)
            events += _logons(MALLORY, day, 40)
        events.sort(key=lambda event: event.timestamp)

        values = self._peer_values("logon_count_peer", events)
        assert values[(MALLORY, 11)] == 10.0, "peers never varied from 4, so 40 is at the cap"


class TestThePeerFeaturiserRefusesTheUnanswerable:
    def test_a_peer_set_without_groups_is_refused_at_construction(self) -> None:
        with pytest.raises(ValidationError, match="needs peer_groups"):
            Featuriser(feature_set=FeatureSet.PEER)

    def test_the_accumulator_refuses_a_peer_set_with_no_peer_history(self) -> None:
        """Emitting neutral values for every peer feature and reporting them as measurements."""
        accumulator = featurise._Accumulator()
        with pytest.raises(ValueError, match="needs a peer history"):
            list(
                accumulator.observations(
                    ALICE,
                    MONDAY_4TH,
                    timedelta(days=1),
                    FeatureSet.PEER,
                    TrailingHistory(),
                    None,
                )
            )


class TestThePeerSourceNote:
    """A peer number that does not carry its grouping is a number nobody can check."""

    def _note(self) -> str:
        groups = _peer_groups(ALICE, BOB, MALLORY)
        return peer_source_note("cert-r3.1", "base rate 1 of 100", groups.summary())

    def test_it_carries_every_peer_caveat(self) -> None:
        note = self._note()
        for caveat in PEER_CAVEATS:
            assert caveat in note

    def test_it_carries_the_grouping_so_the_reader_can_judge_it(self) -> None:
        assert "peer groups by role" in self._note()

    def test_it_keeps_the_caveats_that_are_still_true(self) -> None:
        note = self._note()
        assert "CERT is SYNTHETIC" in note
        assert "ONLY 2 USERS" in note
        assert "OVERFIT A SHORT HISTORY" in note

    def test_it_drops_the_two_claims_this_feature_set_outdates(self) -> None:
        note = self._note()
        assert "Still NO PEER CONTEXT" not in note
        assert "PART 6A ENRICHED per-entity set" not in note
        assert "per-entity STARTER set" not in note

    @pytest.mark.parametrize("marker", SUPERSEDED_ENRICHED_MARKERS)
    def test_each_marker_still_matches_exactly_one_enriched_caveat(self, marker: str) -> None:
        """If a later PART rewrites them, this fails loudly rather than stamping a stale claim."""
        assert sum(marker in caveat for caveat in ENRICHED_CAVEATS) == 1

    def test_the_part_6a_caveats_themselves_are_untouched(self) -> None:
        assert len(ENRICHED_CAVEATS) == 4


# ================================================================================================
# The end-to-end PART 6B run — acceptance criterion 6
# ================================================================================================


class TestThePeerBaselineRunsEndToEnd:
    """`run_aggregated` on the fixture: one alert per entity-window, three numbers side by side."""

    def _reports(
        self, budgets: Sequence[int] = (5, 20)
    ) -> tuple[list[EvaluationReport], dict[str, ScoringSummary]]:
        featuriser, factory = _stream_factory(FeatureSet.PEER)
        groups = _peer_groups(ALICE, BOB, MALLORY)
        reports, _, summaries = run_aggregated(
            stream_factory=factory,
            labels=LABELS,
            featuriser=featuriser,
            dataset_name="fixture-user-day-peer",
            provenance="hand-built fixture",
            train_fraction=0.5,
            min_samples=8,
            config=EvalConfig(alert_threshold=1.0, match_tolerance=timedelta(0), seed=7),
            grouping=groups.summary(),
            budgets=budgets,
            policy=AggregationPolicy(),
        )
        return reports, summaries

    def test_it_scores_both_the_peer_set_and_the_enriched_control(self) -> None:
        """One corpus read, two subsets, one model — so peer is the only difference between them."""
        reports, summaries = self._reports()
        subsets = {report.detector_name for report in reports}
        assert subsets == {
            "aggregate:gaussian:peer set (34 features)",
            "aggregate:gaussian:enriched control (26 features)",
        }
        assert set(summaries) == {PEER_SUBSET, ENRICHED_SUBSET}

    def test_the_alert_unit_is_a_user_window(self) -> None:
        reports, _ = self._reports()
        for report in reports:
            assert report.n_detections == report.n_observations

    def test_the_three_way_comparison_names_all_three_runs(self) -> None:
        note = self._reports()[0][0].source_note
        assert "THREE-WAY AT A MATCHED ALERT BUDGET" in note
        assert f"PART {BASELINE_6D.part}" in note
        assert f"PART {BASELINE_6A.part}" in note
        assert "COULD NOT REACH THIS BUDGET AT ALL" in note, (
            "6A's absence at a SOC-sized budget is the comparison, not a gap in it"
        )
        assert f"{BASELINE_6A.alert_floor:,}" in note

    def test_every_caveat_travels_with_the_number(self) -> None:
        note = self._reports()[0][0].source_note
        for caveat in PEER_CAVEATS:
            assert caveat in note
        assert "CERT is SYNTHETIC" in note
        assert "ONLY 2 USERS" in note

    def test_the_grouping_and_the_unmeasured_part_travel_too(self) -> None:
        """A peer number without its grouping, or its unmeasured share, is uncheckable."""
        note = self._reports()[0][0].source_note
        assert "peer groups by role" in note
        assert "AGGREGATED SCORING" in note
        assert "UNMEASURED" in note

    def test_it_says_what_n_observations_counts(self) -> None:
        note = self._reports()[0][0].source_note
        assert "counts USER-WINDOWS, not feature observations" in note

    def test_a_budget_produces_a_report_at_the_threshold_that_yields_it(self) -> None:
        reports, _ = self._reports(budgets=(5,))
        for_peers = [r for r in reports if r.detector_name.endswith("(34 features)")]
        assert len(for_peers) == 2, "the default threshold, and one per budget"
        assert for_peers[1].n_alerts >= 5

    def test_the_run_is_deterministic(self) -> None:
        first, _ = self._reports()
        second, _ = self._reports()
        assert [(r.precision, r.n_alerts, r.source_note) for r in first] == [
            (r.precision, r.n_alerts, r.source_note) for r in second
        ]

    def test_the_layers_below_needed_no_changes_to_consume_the_aggregated_shape(self) -> None:
        """Criterion 5 as behaviour: PART 2's metrics scored a per-window detector unchanged."""
        reports, _ = self._reports()
        for report in reports:
            assert 0.0 <= report.precision <= 1.0
            assert report.normal_hours > 0.0


class TestAWindowLevelDatasetScoresTheSameAsAFullOne:
    """The one place the aggregated path departs from the enriched one, checked rather than assumed.

    A corpus of 34 features does not fit in memory, so the aggregated run hands the evaluation a
    `Dataset` of one representative observation per user-window instead of one per feature. That
    changes `EvaluationReport.n_observations` — which the source note says — and it must change
    nothing else, because every matching decision is about detections and intervals and the
    normal-hours denominator comes from each user's first and last window.
    """

    def _both(self) -> tuple[EvaluationReport, EvaluationReport]:
        _, factory = _stream_factory(FeatureSet.PEER)
        observations = list(factory())
        first_attack = LABELS[0].start
        fitted = static_range_model(
            GaussianBaseline(min_samples=8).fit(
                [o for o in observations if o.timestamp < first_attack]
            )
        )
        remainder = [o for o in observations if o.timestamp >= first_attack]

        seen: set[tuple[str, datetime]] = set()
        windows: list[Observation] = []
        for observation in remainder:
            key = (observation.entity_ids[0], observation.timestamp)
            if key not in seen:
                seen.add(key)
                windows.append(observation)

        # One alert set, scored once from the whole feature stream, then evaluated against both
        # dataset shapes. That is what the script does: the detections never come from the
        # window-level dataset, which exists only to give the evaluation its windows and its truth.
        detections = AggregatedDetector(fitted=fitted).run(
            Dataset(
                name="fixture", domain=Domain.SENTIEL, observations=remainder, attack_intervals=[]
            )
        )
        detector = PrecomputedDetector(name="aggregate:gaussian", detections=detections)
        config = EvalConfig(alert_threshold=1.0, match_tolerance=timedelta(0), seed=7)
        full, windowed = (
            evaluate_entity_aware(
                detector,
                Dataset(
                    name="fixture", domain=Domain.SENTIEL, observations=rows, attack_intervals=[]
                ),
                LABELS,
                config,
            )
            for rows in (remainder, windows)
        )
        return full, windowed

    def test_precision_recall_and_false_positives_are_identical(self) -> None:
        full, windowed = self._both()
        assert full.precision == windowed.precision
        assert full.window_recall == windowed.window_recall
        assert full.false_positives == windowed.false_positives
        assert full.n_alerts == windowed.n_alerts
        assert full.false_positive_rate == pytest.approx(windowed.false_positive_rate)

    def test_only_the_observation_count_differs(self) -> None:
        full, windowed = self._both()
        assert full.n_observations > windowed.n_observations
        assert full.n_detections == windowed.n_detections
        assert windowed.n_observations == windowed.n_detections, "one row per scored window"


_CERT_RELEASE = Path(__file__).resolve().parents[2] / "data" / "cert-insider-threat"
_CERT_LDAP = _CERT_RELEASE / "r3.1" / "LDAP"


@pytest.mark.skipif(
    not _CERT_LDAP.is_dir(),
    reason="the real CERT release is git-ignored; fetch it with scripts/fetch_datasets.py",
)
class TestTheRealReleaseCanBePeerGrouped:
    """Guarded: the grouping this PART chose, applied to the corpus it was chosen for."""

    def _catalogue(self) -> EntityCatalogue:
        data = _CERT_RELEASE
        manifest = json.loads((data / "sentiel-manifest.json").read_text(encoding="utf-8"))
        return EntityCatalogue.from_ldap_directory(
            data.parent / str(manifest["release_dir"]) / "LDAP"
        )

    def test_role_gives_most_of_the_population_a_usable_group(self) -> None:
        groups = PeerGroups.from_catalogue(self._catalogue(), PeerPolicy())
        assert groups.usable_groups > 1
        assert len(groups.membership) > 0.8 * len(self._catalogue().entities)

    def test_business_unit_is_the_degenerate_case_this_grouping_avoids(self) -> None:
        """One value for the whole company is a population baseline, not a peer baseline."""
        groups = PeerGroups.from_catalogue(
            self._catalogue(), PeerPolicy(group_attribute="business_unit", min_group_size=5)
        )
        assert groups.usable_groups == 1, "everybody in one group — no peer structure at all"

"""Identity features name declared counterparties, and the existing 34 stay symmetric.

The 34 count how many. These tests pin three facts: renaming every host, machine and
recipient leaves the 34 unchanged; the same rename changes the identity counts only
when a name crosses the declared register; and no weight distinguishes one of the 34
from another.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

import pytest

from phos.ontology import Domain, Observation
from phos.sentiel.candidates import DECLARED_CANDIDATES, FormulaTerm, score_candidate
from phos.sentiel.events import (
    DETAIL_PC,
    DETAIL_RECIPIENT_DOMAINS,
    DETAIL_RECIPIENTS,
    DETAIL_URL,
    DETAIL_URL_HOST,
    EnterpriseEvent,
    EventKind,
)
from phos.sentiel.featurise import PEER_FEATURES, FeatureSet, Featuriser
from phos.sentiel.history import HistoryPolicy
from phos.sentiel.named_counterparties import (
    IDENTITY_FEATURE_SET,
    IDENTITY_FEATURES,
    MATCHED_IDENTITIES,
    NEW_STATUS,
    NEW_STATUS_INSUFFICIENT,
    NEW_STATUS_MEASURED,
    REGISTER_SHA256,
    DeclaredIdentities,
    IdentityFeaturiser,
    register_sha256,
)
from phos.sentiel.peers import PeerGroups
from phos.sentiel.scoring import AggregationPolicy
from phos.sentiel.templates import family_of

DAY_1 = datetime(2010, 1, 4, tzinfo=UTC)
DAY_2 = datetime(2010, 1, 5, tzinfo=UTC)
SHORT_HISTORY = HistoryPolicy(trailing_windows=4, min_history_windows=1, trend_windows=2)
GROUPS = PeerGroups(
    group_attribute="role",
    min_group_size=2,
    membership={"A": "staff", "B": "staff"},
    declared_sizes={"staff": 2},
)

_ALPHA = "alpha.test"
_GAMMA = "gamma.test"
_OTHER = "other.test"
_PC_A = "pc-a"
_PC_B = "pc-b"
_MAIL_A = "a@out.test"
_MAIL_B = "b@out.test"
_RENAME = {
    _ALPHA: "beta.test",
    _GAMMA: "delta.test",
    _OTHER: "other2.test",
    _PC_A: "pc-1",
    _PC_B: "pc-2",
    _MAIL_A: "a@away.test",
    _MAIL_B: "b@away.test",
}


def _at(day: datetime, hour: int, minute: int) -> datetime:
    return day.replace(hour=hour, minute=minute)


def _logon(user: str, when: datetime, pc: str) -> EnterpriseEvent:
    return EnterpriseEvent(
        timestamp=when,
        user_id=user,
        event_kind=EventKind.LOGON,
        details={DETAIL_PC: pc},
    )


def _visit(user: str, when: datetime, host: str, pc: str = "pc-1") -> EnterpriseEvent:
    return EnterpriseEvent(
        timestamp=when,
        user_id=user,
        event_kind=EventKind.HTTP_REQUEST,
        details={DETAIL_PC: pc, DETAIL_URL_HOST: host, DETAIL_URL: f"http://{host}/"},
    )


def _mail(user: str, when: datetime, recipient: str, pc: str = "pc-1") -> EnterpriseEvent:
    domain = recipient.split("@", 1)[1]
    return EnterpriseEvent(
        timestamp=when,
        user_id=user,
        event_kind=EventKind.EMAIL_SEND,
        details={
            DETAIL_PC: pc,
            DETAIL_RECIPIENTS: recipient,
            DETAIL_RECIPIENT_DOMAINS: domain,
        },
    )


def _ordered(events: list[EnterpriseEvent]) -> list[EnterpriseEvent]:
    return sorted(events, key=lambda event: event.timestamp)


def _world(rename: dict[str, str]) -> list[EnterpriseEvent]:
    """Two people, two days. ``rename`` is applied to every name."""

    def name(value: str) -> str:
        return rename.get(value, value)

    events: list[EnterpriseEvent] = []
    for day in (DAY_1, DAY_2):
        events.append(_logon("A", _at(day, 9, 0), name(_PC_A)))
        events.append(_visit("A", _at(day, 11, 0), name(_ALPHA), name(_PC_A)))
        if day == DAY_2:
            events.append(_visit("A", _at(day, 11, 1), name(_GAMMA), name(_PC_A)))
        events.append(_mail("A", _at(day, 12, 0), name(_MAIL_A), name(_PC_A)))
        events.append(_logon("B", _at(day, 9, 2), name(_PC_B)))
        events.append(_visit("B", _at(day, 11, 2), name(_OTHER), name(_PC_B)))
        events.append(_mail("B", _at(day, 12, 2), name(_MAIL_B), name(_PC_B)))
    return _ordered(events)


def _peer_map(events: list[EnterpriseEvent]) -> dict[tuple[str, str, str], float]:
    featuriser = Featuriser(
        feature_set=FeatureSet.PEER,
        peer_groups=GROUPS,
        history_policy=SHORT_HISTORY,
    )
    return {
        (obs.context["user_id"], obs.timestamp.date().isoformat(), obs.feature): obs.value
        for obs in featuriser.observations(events)
    }


def _identity(
    events: list[EnterpriseEvent],
    register: DeclaredIdentities,
    policy: HistoryPolicy | None = None,
) -> list[Observation]:
    return IdentityFeaturiser(
        identities=register,
        history_policy=policy or HistoryPolicy(),
    ).observations(_ordered(events))


def _one(observations: list[Observation], user: str, feature: str, day: datetime) -> Observation:
    found = [
        obs
        for obs in observations
        if obs.context["user_id"] == user and obs.feature == feature and obs.timestamp == day
    ]
    assert len(found) == 1
    return found[0]


def test_the_six_identity_features_are_pinned_and_outside_the_thirty_four() -> None:
    assert IDENTITY_FEATURES == (
        "declared_host_count",
        "declared_new_host_count",
        "declared_destination_count",
        "declared_new_destination_count",
        "declared_pc_count",
        "declared_new_pc_count",
    )
    assert len(PEER_FEATURES) == 34
    assert set(IDENTITY_FEATURES).isdisjoint(PEER_FEATURES)


def test_frozen_policy_gives_every_existing_feature_the_same_weight() -> None:
    """Symmetry of the 34 is an empty weight table, on the frozen policy and on Bet 001."""
    policy = AggregationPolicy()
    assert policy.feature_weights == {}
    assert policy.stem_weights == {}
    for feature in PEER_FEATURES:
        assert policy.weight_for(feature) == 1.0
        assert family_of(feature) is not None
    for feature in IDENTITY_FEATURES:
        assert family_of(feature) is None
    for candidate in DECLARED_CANDIDATES:
        assert candidate.feature_weights == {}
        assert candidate.stem_weights == {}


def test_equal_magnitudes_score_equally_across_the_thirty_four() -> None:
    terms = [FormulaTerm(feature=name, magnitude=2.5) for name in PEER_FEATURES]
    for candidate_id in ("linear-excess", "gaussian-tail"):
        scored = score_candidate(candidate_id, terms)
        shares = [share.contribution for share in scored.shares]
        assert len(shares) == 34
        assert shares[0] > 0.0
        assert all(share == shares[0] for share in shares)
    forward = score_candidate("family-max", terms)
    backward = score_candidate("family-max", list(reversed(terms)))
    assert forward.score == backward.score
    assert forward.score > 0.0


def test_renaming_identities_leaves_the_thirty_four_unchanged() -> None:
    original = _peer_map(_world({}))
    renamed = _peer_map(_world(_RENAME))
    assert original == renamed
    assert sum(1 for user, day, _feature in original if user == "A" and day == "2010-01-04") == 34
    assert sum(1 for user, day, _feature in original if user == "B" and day == "2010-01-05") == 34


def test_identity_counts_follow_a_renamed_register_and_the_peer_vector_does_not_move() -> None:
    original_events = _world({})
    renamed_events = _world(_RENAME)
    before = _peer_map(original_events)
    original = _identity(
        original_events,
        DeclaredIdentities(hosts=frozenset({_ALPHA, _GAMMA})),
        SHORT_HISTORY,
    )
    renamed = _identity(
        renamed_events,
        DeclaredIdentities(hosts=frozenset({_RENAME[_ALPHA], _RENAME[_GAMMA]})),
        SHORT_HISTORY,
    )
    after = _peer_map(original_events)
    assert before == after

    original_count = _one(original, "A", "declared_host_count", DAY_2)
    renamed_count = _one(renamed, "A", "declared_host_count", DAY_2)
    assert original_count.value == renamed_count.value == 2.0
    assert original_count.context[MATCHED_IDENTITIES] == "alpha.test;gamma.test"
    assert renamed_count.context[MATCHED_IDENTITIES] == "beta.test;delta.test"

    original_new = _one(original, "A", "declared_new_host_count", DAY_2)
    renamed_new = _one(renamed, "A", "declared_new_host_count", DAY_2)
    assert original_new.value == renamed_new.value == 1.0
    assert original_new.context[NEW_STATUS] == NEW_STATUS_MEASURED
    assert original_new.context[MATCHED_IDENTITIES] == "gamma.test"
    assert renamed_new.context[MATCHED_IDENTITIES] == "delta.test"


def test_a_register_that_is_not_renamed_with_the_world_changes_the_identity_count() -> None:
    """The 34 ignore which name it was. The identity count does not."""
    register = DeclaredIdentities(hosts=frozenset({_ALPHA}))
    named = _identity(_world({}), register, SHORT_HISTORY)
    swapped = _identity(_world(_RENAME), register, SHORT_HISTORY)
    assert _one(named, "A", "declared_host_count", DAY_1).value == 1.0
    assert _one(swapped, "A", "declared_host_count", DAY_1).value == 0.0
    assert _peer_map(_world({})) == _peer_map(_world(_RENAME))


def test_swapping_two_declared_hosts_keeps_the_count_and_changes_the_name() -> None:
    register = DeclaredIdentities(hosts=frozenset({"alpha.test", "beta.test"}))
    alpha = _identity([_visit("A", _at(DAY_1, 11, 0), "alpha.test")], register)
    beta = _identity([_visit("A", _at(DAY_1, 11, 0), "beta.test")], register)
    alpha_count = _one(alpha, "A", "declared_host_count", DAY_1)
    beta_count = _one(beta, "A", "declared_host_count", DAY_1)
    assert alpha_count.value == beta_count.value == 1.0
    assert alpha_count.context[MATCHED_IDENTITIES] == "alpha.test"
    assert beta_count.context[MATCHED_IDENTITIES] == "beta.test"
    assert alpha_count.context["feature_set"] == IDENTITY_FEATURE_SET
    assert alpha_count.domain is Domain.SENTIEL
    assert alpha_count.entity_ids == ["ent_A"]


def test_an_empty_register_emits_zeros_and_a_stable_fingerprint() -> None:
    observations = _identity([_visit("A", _at(DAY_1, 11, 0), "alpha.test")], DeclaredIdentities())
    assert len(observations) == 6
    assert all(obs.value == 0.0 for obs in observations)
    assert all(obs.context[MATCHED_IDENTITIES] == "" for obs in observations)
    payload = "destinations=\nhosts=\npcs="
    expected = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    assert register_sha256(DeclaredIdentities()) == expected
    assert observations[0].context[REGISTER_SHA256] == expected


def test_register_order_and_case_do_not_change_the_fingerprint() -> None:
    left = DeclaredIdentities.model_validate(
        {"hosts": ["Beta.TEST", "alpha.test"], "pcs": ["PC-1"]}
    )
    right = DeclaredIdentities.model_validate(
        {"hosts": ["alpha.test", "beta.test"], "pcs": ["pc-1"]}
    )
    assert left.hosts == right.hosts == frozenset({"alpha.test", "beta.test"})
    assert register_sha256(left) == register_sha256(right)


def test_host_match_is_exact_and_case_folded() -> None:
    register = DeclaredIdentities(hosts=frozenset({"Example.TEST"}))
    hit = _identity([_visit("A", _at(DAY_1, 11, 0), "example.test")], register)
    assert _one(hit, "A", "declared_host_count", DAY_1).value == 1.0
    for host in ("example.test.evil", "www.example.test", "test", "notexample.test"):
        missed = _identity([_visit("A", _at(DAY_1, 11, 0), host)], register)
        assert _one(missed, "A", "declared_host_count", DAY_1).value == 0.0


def test_url_host_wins_and_a_bare_url_is_read_when_the_host_field_is_absent() -> None:
    register = DeclaredIdentities(hosts=frozenset({"alpha.test", "beta.test"}))
    conflict = EnterpriseEvent(
        timestamp=_at(DAY_1, 11, 0),
        user_id="A",
        event_kind=EventKind.HTTP_REQUEST,
        details={DETAIL_URL_HOST: "alpha.test", DETAIL_URL: "http://beta.test/x"},
    )
    from_url = EnterpriseEvent(
        timestamp=_at(DAY_1, 11, 1),
        user_id="A",
        event_kind=EventKind.HTTP_REQUEST,
        details={DETAIL_URL: "http://beta.test/y"},
    )
    observations = _identity([conflict, from_url], register)
    assert _one(observations, "A", "declared_host_count", DAY_1).context[MATCHED_IDENTITIES] == (
        "alpha.test;beta.test"
    )


def test_a_declared_domain_lists_the_address_and_not_a_different_mailbox() -> None:
    by_domain = _identity(
        [_mail("A", _at(DAY_1, 12, 0), "Bob@Other.test")],
        DeclaredIdentities(destinations=frozenset({"other.test"})),
    )
    listed = _one(by_domain, "A", "declared_destination_count", DAY_1)
    assert listed.value == 1.0
    assert listed.context[MATCHED_IDENTITIES] == "bob@other.test"

    both = _identity(
        [
            EnterpriseEvent(
                timestamp=_at(DAY_1, 12, 1),
                user_id="A",
                event_kind=EventKind.EMAIL_SEND,
                details={
                    DETAIL_RECIPIENTS: "ann@other.test;bob@other.test",
                    DETAIL_RECIPIENT_DOMAINS: "other.test",
                },
            )
        ],
        DeclaredIdentities(destinations=frozenset({"other.test"})),
    )
    assert _one(both, "A", "declared_destination_count", DAY_1).context[MATCHED_IDENTITIES] == (
        "ann@other.test;bob@other.test"
    )

    one_mailbox = _identity(
        [_mail("A", _at(DAY_1, 12, 2), "bob@other.test")],
        DeclaredIdentities(destinations=frozenset({"ann@other.test"})),
    )
    assert _one(one_mailbox, "A", "declared_destination_count", DAY_1).value == 0.0


def test_pc_case_folding_does_not_change_the_starter_distinct_count() -> None:
    events = [
        _logon("A", _at(DAY_1, 9, 0), "PC-1"),
        _logon("A", _at(DAY_1, 9, 1), "pc-1"),
    ]
    starter = {obs.feature: obs.value for obs in Featuriser().observations(_ordered(events))}
    assert starter["distinct_pcs"] == 2.0
    identity = _identity(events, DeclaredIdentities(pcs=frozenset({"pc-1"})))
    assert _one(identity, "A", "declared_pc_count", DAY_1).value == 1.0
    assert _one(identity, "A", "declared_pc_count", DAY_1).context[MATCHED_IDENTITIES] == "pc-1"
    assert "declared_pc_count" not in starter


def test_a_logon_with_nothing_declared_still_emits_six_zeros() -> None:
    observations = _identity([_logon("A", _at(DAY_1, 9, 0), "pc-9")], DeclaredIdentities())
    assert [obs.feature for obs in observations] == list(IDENTITY_FEATURES)
    assert all(obs.value == 0.0 for obs in observations)
    new_host = _one(observations, "A", "declared_new_host_count", DAY_1)
    assert new_host.context[NEW_STATUS] == NEW_STATUS_INSUFFICIENT


def test_no_events_produce_no_observations() -> None:
    assert IdentityFeaturiser().observations([]) == []


def test_ids_are_deterministic_and_users_emit_in_sorted_order() -> None:
    events = [
        _visit("B", _at(DAY_1, 11, 1), "beta.test"),
        _visit("A", _at(DAY_1, 11, 0), "alpha.test"),
    ]
    register = DeclaredIdentities(hosts=frozenset({"alpha.test", "beta.test"}))
    first = _identity(events, register)
    second = _identity(events, register)
    assert [obs.id for obs in first] == [obs.id for obs in second]
    assert first[0].id == "idn_A_20100104_00"
    assert [obs.context["user_id"] for obs in first[:6]] == ["A"] * 6
    assert [obs.context["user_id"] for obs in first[6:]] == ["B"] * 6


def test_out_of_order_events_raise() -> None:
    events = [
        _visit("A", _at(DAY_2, 11, 0), "alpha.test"),
        _visit("A", _at(DAY_1, 11, 0), "alpha.test"),
    ]
    with pytest.raises(ValueError, match="time-ordered"):
        IdentityFeaturiser().observations(events)


def test_a_blank_or_ambiguous_register_name_is_refused() -> None:
    with pytest.raises(ValueError, match="collection of names"):
        DeclaredIdentities.model_validate({"hosts": "alpha.test"})
    with pytest.raises(ValueError, match="blank"):
        DeclaredIdentities.model_validate({"hosts": [""]})
    with pytest.raises(ValueError, match="joined"):
        DeclaredIdentities.model_validate({"destinations": ["a;b@other.test"]})
    with pytest.raises(ValueError, match="string"):
        DeclaredIdentities.model_validate({"pcs": ["pc-1", 3]})


def test_the_current_window_is_not_already_known() -> None:
    register = DeclaredIdentities(hosts=frozenset({"alpha.test", "beta.test"}))
    events = [
        _visit("A", _at(DAY_1, 11, 0), "alpha.test"),
        _visit("A", _at(DAY_2, 11, 0), "beta.test"),
    ]
    observations = _identity(events, register, SHORT_HISTORY)
    first = _one(observations, "A", "declared_new_host_count", DAY_1)
    second = _one(observations, "A", "declared_new_host_count", DAY_2)
    assert first.context[NEW_STATUS] == NEW_STATUS_INSUFFICIENT
    assert first.value == 0.0
    assert _one(observations, "A", "declared_host_count", DAY_1).value == 1.0
    assert second.context[NEW_STATUS] == NEW_STATUS_MEASURED
    assert second.value == 1.0
    assert second.context[MATCHED_IDENTITIES] == "beta.test"


def test_a_name_ages_out_of_the_rolling_memory() -> None:
    policy = HistoryPolicy(trailing_windows=1, min_history_windows=1, trend_windows=2)
    register = DeclaredIdentities(hosts=frozenset({"alpha.test", "beta.test"}))
    events = [
        _visit("A", _at(DAY_1, 11, 0), "alpha.test"),
        _visit("A", _at(DAY_2, 11, 0), "beta.test"),
        _visit("A", datetime(2010, 1, 6, 11, 0, tzinfo=UTC), "alpha.test"),
    ]
    observations = _identity(events, register, policy)
    day_3 = datetime(2010, 1, 6, tzinfo=UTC)
    assert (
        _one(observations, "A", "declared_new_host_count", DAY_2).context[MATCHED_IDENTITIES]
        == "beta.test"
    )
    assert (
        _one(observations, "A", "declared_new_host_count", day_3).context[MATCHED_IDENTITIES]
        == "alpha.test"
    )


def test_two_users_do_not_share_a_memory() -> None:
    register = DeclaredIdentities(hosts=frozenset({"alpha.test", "beta.test"}))
    events = [
        _visit("A", _at(DAY_1, 11, 0), "alpha.test"),
        _visit("B", _at(DAY_1, 11, 1), "alpha.test"),
        _visit("A", _at(DAY_2, 11, 0), "beta.test"),
        _visit("B", _at(DAY_2, 11, 1), "alpha.test"),
    ]
    observations = _identity(events, register, SHORT_HISTORY)
    assert (
        _one(observations, "A", "declared_new_host_count", DAY_2).context[MATCHED_IDENTITIES]
        == "beta.test"
    )
    bob = _one(observations, "B", "declared_new_host_count", DAY_2)
    assert bob.context[NEW_STATUS] == NEW_STATUS_MEASURED
    assert bob.value == 0.0
    assert bob.context[MATCHED_IDENTITIES] == ""


def test_default_history_stays_silent_for_eight_windows() -> None:
    """The bar is HistoryPolicy's own eight windows, not a number chosen here."""
    register = DeclaredIdentities(hosts=frozenset({"alpha.test", "beta.test"}))
    events: list[EnterpriseEvent] = []
    for offset in range(8):
        day = DAY_1 + timedelta(days=offset)
        events.append(_logon("A", _at(day, 9, 0), "pc-1"))
    ninth = DAY_1 + timedelta(days=8)
    events.append(_visit("A", _at(ninth, 11, 0), "beta.test"))
    observations = _identity(events, register)
    eighth = DAY_1 + timedelta(days=7)
    assert (
        _one(observations, "A", "declared_new_host_count", eighth).context[NEW_STATUS]
        == NEW_STATUS_INSUFFICIENT
    )
    spoken = _one(observations, "A", "declared_new_host_count", ninth)
    assert spoken.context[NEW_STATUS] == NEW_STATUS_MEASURED
    assert spoken.value == 1.0
    assert spoken.context[MATCHED_IDENTITIES] == "beta.test"


def test_a_sub_day_window_splits_the_day() -> None:
    events = [
        _logon("A", _at(DAY_1, 1, 0), "pc-1"),
        _logon("A", _at(DAY_1, 13, 0), "pc-1"),
    ]
    observations = IdentityFeaturiser(window=timedelta(hours=12)).observations(events)
    stamps = sorted({obs.timestamp for obs in observations})
    assert stamps == [_at(DAY_1, 0, 0), _at(DAY_1, 12, 0)]
    assert len(observations) == 12

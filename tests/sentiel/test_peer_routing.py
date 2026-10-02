"""Session S1: peer features emit only when the group is a real peer group."""

from tests.sentiel.test_peers import _groups, _team

from phos.sentiel import (
    CERT_R31_ROLE_COHORT_SIZE,
    PeerPolicy,
    cert_r31_role_is_not_a_peer_group,
    peer_features_allowed,
)


def test_default_policy_does_not_apply_the_r31_ceiling() -> None:
    """Public 6B stays on PeerPolicy(); the 180-person refuse is a named S1 condition."""
    assert PeerPolicy().min_group_size == 5
    assert peer_features_allowed(CERT_R31_ROLE_COHORT_SIZE) is True


def test_r31_role_of_180_is_not_a_peer_group() -> None:
    assert CERT_R31_ROLE_COHORT_SIZE == 180
    assert cert_r31_role_is_not_a_peer_group(180) is True
    assert cert_r31_role_is_not_a_peer_group(8) is False


def test_below_min_group_size_emits_no_peer_features() -> None:
    assert peer_features_allowed(4, PeerPolicy(min_group_size=5)) is False
    groups = _groups(size=5, **_team("ITAdmin", 8))
    assert groups.group_of("ITAdmin00") == "ITAdmin"
    assert peer_features_allowed(8, PeerPolicy(min_group_size=5)) is True

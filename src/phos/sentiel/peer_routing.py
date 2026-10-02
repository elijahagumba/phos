"""When self-history is more informative than peer comparison (Session S1).

Peer features may emit only when a declared group exists, the size is at least
`PeerPolicy.min_group_size`, and — when a caller names a ceiling — the group is below that
ceiling. Causality of the pool remains `PeerHistory.observe` taking a completed window.

r3.1's modal ``role`` cohort is 180 people: a department-shaped population, not a peer group.
That condition is `cert_r31_role_is_not_a_peer_group`. Default `PeerPolicy` is unchanged, so
the public 6B row is not rewritten. The peer-advantage claim stays retired (ADR 0022/0023).
"""

from __future__ import annotations

from typing import Final

from phos.sentiel.peers import PeerPolicy

__all__ = [
    "CERT_R31_ROLE_COHORT_SIZE",
    "cert_r31_role_is_not_a_peer_group",
    "peer_features_allowed",
]

CERT_R31_ROLE_COHORT_SIZE: Final = 180
"""r3.1's published role cohort size. Not a peer group (ADR 0022 / Session S1)."""


def peer_features_allowed(
    declared_size: int,
    policy: PeerPolicy | None = None,
    *,
    max_group_size: int | None = None,
) -> bool:
    """Return whether a declared group size may emit peer features.

    Args:
        declared_size: How many directory members the group has.
        policy: Size floor. Defaults to `PeerPolicy` (min_group_size=5, no ceiling).
        max_group_size: Optional population ceiling. Independent of `PeerPolicy` so
            `src/phos/sentiel/peers.py` can stay frozen at the 6B spine.
    """
    settings = policy or PeerPolicy()
    if declared_size < settings.min_group_size:
        return False
    ceiling = max_group_size
    if ceiling is not None and declared_size >= ceiling:
        return False
    return True


def cert_r31_role_is_not_a_peer_group(size: int = CERT_R31_ROLE_COHORT_SIZE) -> bool:
    """Return whether a cohort of ``size`` is the r3.1 department-shaped failure.

    Session S1: this condition **must fire** on 180. It does not revive the peer-advantage
    claim.
    """
    return not peer_features_allowed(
        size, PeerPolicy(min_group_size=5), max_group_size=CERT_R31_ROLE_COHORT_SIZE
    )

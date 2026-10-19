"""Rare new user-machine-site links among declared role peers (ADR 0193).

This module does not add edges to ``DeclaredGraph``. It scores observed hosts,
recipients and machines against the attack-free prefix of people who share
the LDAP role. File names are not a fourth kind.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict

from phos.sentiel.day_facts import DayFacts

__all__ = ["PeerLinkRarity"]

_UNKNOWN_ROLE = "unknown"
_KINDS: tuple[str, ...] = ("hosts", "recipients", "pcs")


class PeerLinkRarity(BaseModel):
    """Training-prefix sets of hosts, recipients and machines, by user and role.

    Attributes:
        by_user: ``user_id -> kind -> frozenset of names``.
        who: ``kind -> name -> frozenset of user ids`` who touched it in training.
        role_of: ``user_id -> role``.
        peers: ``role -> frozenset of user ids``.
    """

    model_config = ConfigDict(frozen=True)

    by_user: dict[str, dict[str, frozenset[str]]]
    who: dict[str, dict[str, frozenset[str]]]
    role_of: dict[str, str]
    peers: dict[str, frozenset[str]]

    @classmethod
    def fit(cls, train: Sequence[DayFacts]) -> PeerLinkRarity:
        """Collect each user's training-prefix identity sets."""
        collected: dict[str, dict[str, set[str]]] = defaultdict(
            lambda: {kind: set() for kind in _KINDS}
        )
        who_sets: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
        role_of: dict[str, str] = {}
        peers: dict[str, set[str]] = defaultdict(set)
        for day in train:
            role_of[day.user_id] = day.role
            if day.role != _UNKNOWN_ROLE:
                peers[day.role].add(day.user_id)
            for kind in _KINDS:
                for name in getattr(day, kind):
                    collected[day.user_id][kind].add(str(name))
                    who_sets[kind][str(name)].add(day.user_id)
        return cls(
            by_user={
                user: {kind: frozenset(names) for kind, names in kinds.items()}
                for user, kinds in collected.items()
            },
            who={
                kind: {name: frozenset(users) for name, users in names.items()}
                for kind, names in who_sets.items()
            },
            role_of=role_of,
            peers={role: frozenset(users) for role, users in peers.items()},
        )

    def score(self, day: DayFacts) -> float:
        """Return summed surprise of names that are new for this user and rare among peers."""
        if day.role == _UNKNOWN_ROLE:
            return 0.0
        cohort = self.peers.get(day.role, frozenset()) - {day.user_id}
        if not cohort:
            return 0.0
        known = self.by_user.get(day.user_id, {kind: frozenset() for kind in _KINDS})
        total = 0.0
        n_peers = len(cohort)
        for kind in _KINDS:
            seen_self = known.get(kind, frozenset())
            by_name = self.who.get(kind, {})
            for name in getattr(day, kind):
                if name in seen_self:
                    continue
                peer_count = len(by_name.get(str(name), frozenset()) & cohort)
                total += -math.log((peer_count + 1) / (n_peers + 1))
        return total

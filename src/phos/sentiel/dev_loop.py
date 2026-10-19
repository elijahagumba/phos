"""Combine lane-A development streams and apply ADR 0149's keep rule.

Development scorers are named ``lane-a-dev:<id>``. They rank with the same
key ADR 0148 fixed. This module does not read CERT and does not touch 6B.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final

from pydantic import BaseModel, ConfigDict

from phos.sentiel.behaviour_chains import ChainSurprise
from phos.sentiel.bet001 import (
    BUDGET,
    DayScore,
    chance_malicious_days,
    insiders_in_budget,
    rank_days,
)
from phos.sentiel.day_facts import DayFacts
from phos.sentiel.depth import CountDepth
from phos.sentiel.peer_links import PeerLinkRarity
from phos.sentiel.role_hours import RoleHourPeers

__all__ = [
    "STREAMS",
    "FittedStreams",
    "LoopSnapshot",
    "decide_keep",
    "score_days",
    "snapshot",
]

STREAMS: Final[tuple[str, ...]] = ("depth", "chains", "role_hours", "peer_links")
MUST_KEEP: Final = "CSF0929"
TARGET: Final = "CCH0959"


class FittedStreams(BaseModel):
    """The four streams fitted on one attack-free prefix."""

    model_config = ConfigDict(frozen=True)

    depth: CountDepth
    chains: ChainSurprise
    role_hours: RoleHourPeers
    peer_links: PeerLinkRarity

    @classmethod
    def fit(cls, train: Sequence[DayFacts]) -> FittedStreams:
        """Fit every stream from the same training days."""
        return cls(
            depth=CountDepth.fit(train),
            chains=ChainSurprise.fit(train),
            role_hours=RoleHourPeers.fit(train),
            peer_links=PeerLinkRarity.fit(train),
        )

    def score(self, day: DayFacts, streams: Sequence[str]) -> float:
        """Return the sum of the named streams on ``day``.

        Raises:
            ValueError: If a name is not one of `STREAMS`.
        """
        total = 0.0
        for name in streams:
            if name == "depth":
                total += self.depth.score(day)
            elif name == "chains":
                total += self.chains.score(day)
            elif name == "role_hours":
                total += self.role_hours.score(day)
            elif name == "peer_links":
                total += self.peer_links.score(day)
            else:
                raise ValueError(f"unknown stream {name!r}")
        return total


class LoopSnapshot(BaseModel):
    """One named scorer's numbers at budget 48."""

    model_config = ConfigDict(frozen=True)

    name: str
    found: tuple[str, ...]
    both_found: bool
    precision_at_48: float
    chance_malicious_days_in_48: float
    per_insider: dict[str, dict[str, int | None]]
    n_days: int
    n_malicious: int


def score_days(
    model: FittedStreams,
    days: Sequence[DayFacts],
    streams: Sequence[str],
    malicious: Mapping[tuple[str, object], bool],
) -> tuple[DayScore, ...]:
    """Return one `DayScore` per day, labels attached after the score is known."""
    rows: list[DayScore] = []
    for day in days:
        rows.append(
            DayScore(
                user_id=day.user_id,
                day=day.day,
                score=model.score(day, streams),
                malicious=bool(malicious.get((day.user_id, day.day.date()), False)),
            )
        )
    return tuple(rows)


def snapshot(
    name: str,
    days: Sequence[DayScore],
    insider_ids: Sequence[str],
) -> LoopSnapshot:
    """Rank ``days`` and report who is inside the budget."""
    ranked = rank_days(days)
    rank_of = {(item.user_id, item.day): index + 1 for index, item in enumerate(ranked)}
    top = ranked[:BUDGET]
    found = tuple(sorted(insiders_in_budget(days, BUDGET)))
    n_malicious = sum(1 for item in days if item.malicious)
    per_insider: dict[str, dict[str, int | None]] = {}
    for user in insider_ids:
        mine = [item for item in days if item.user_id == user and item.malicious]
        best = min((rank_of[(item.user_id, item.day)] for item in mine), default=None)
        per_insider[user] = {
            "malicious_days": len(mine),
            "in_top_48": sum(1 for item in top if item.user_id == user and item.malicious),
            "best_rank": best,
        }
    true_days = sum(1 for item in top if item.malicious)
    return LoopSnapshot(
        name=name,
        found=found,
        both_found=set(found) == set(insider_ids),
        precision_at_48=true_days / BUDGET if days else 0.0,
        chance_malicious_days_in_48=(
            chance_malicious_days(len(days), n_malicious, min(BUDGET, len(days))) if days else 0.0
        ),
        per_insider=per_insider,
        n_days=len(days),
        n_malicious=n_malicious,
    )


def decide_keep(current: LoopSnapshot, candidate: LoopSnapshot) -> str:
    """Return ``keep`` or ``revert`` under ADR 0149.

    Losing the insider 6B already finds is always a revert. Finding the
    second insider is a keep even if precision falls. A rank improvement on
    the missed insider, without finding them, is kept only when precision
    does not fall.
    """
    current_found = set(current.found)
    candidate_found = set(candidate.found)
    if MUST_KEEP in current_found and MUST_KEEP not in candidate_found:
        return "revert"
    if len(candidate_found) > len(current_found):
        return "keep"
    if len(candidate_found) < len(current_found):
        return "revert"
    current_rank = current.per_insider.get(TARGET, {}).get("best_rank")
    candidate_rank = candidate.per_insider.get(TARGET, {}).get("best_rank")
    if (
        current_rank is not None
        and candidate_rank is not None
        and candidate_rank < current_rank
        and candidate.precision_at_48 + 1e-12 >= current.precision_at_48
    ):
        return "keep"
    return "revert"

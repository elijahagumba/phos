"""Reorder a champion queue. Alerts are not added or removed (ADR 0231).

Each variant is a 0/1 priority written down before any score. The champion
tiebreak stays: higher score, then earlier timestamp, then earlier input order.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Final

from phos.eval.budget import OPERATOR_SHIFT
from phos.eval.datasets import LabelledInterval
from phos.eval.queue_rank import AttackSpan, QueueAlert, rank_attacks

__all__ = [
    "ALERTS_PER_SHIFT",
    "FROZEN_VARIANT",
    "VARIANTS",
    "QueueItem",
    "Variant",
    "a3_passes",
    "champion_scores",
    "ordered",
    "recall_caught",
    "refuse_existing",
    "reject_for_recall",
    "select_variant",
    "variant_scores",
]

ALERTS_PER_SHIFT: Final = 8

#: Frozen after development, before the held-back run (ADR 0232). Held-back refuses any
#: value that is not one of the six declared variants.
FROZEN_VARIANT: Final[str] = "familiarity"


class Variant(StrEnum):
    """One declared reordering. The value is the result-name suffix."""

    FAMILIARITY = "familiarity"
    INNOCENT = "innocent"
    CROSS_PATH = "cross-path"
    FAMILIARITY_CROSS = "familiarity-cross"
    CROSS_INNOCENT = "cross-innocent"
    ALL_THREE = "all-three"


VARIANTS: Final[tuple[Variant, ...]] = (
    Variant.FAMILIARITY,
    Variant.INNOCENT,
    Variant.CROSS_PATH,
    Variant.FAMILIARITY_CROSS,
    Variant.CROSS_INNOCENT,
    Variant.ALL_THREE,
)
"""Declaration order. A tie in the freeze rule breaks toward the earlier row."""


@dataclass(frozen=True)
class QueueItem:
    """One champion alert, with the three declared facts a ranker may read.

    Attributes:
        identity: Stable id. Unique inside one queue.
        timestamp: When the alert is shown.
        champion_score: The champion's own score. Higher ranked earlier on a tie.
        input_order: Position in the champion's output.
        familiar: The member-column set appeared on a training-normal event.
        witness: The onset reading disagrees with the rest of the plant.
        strong_innocent: An innocent explanation is supported and not contradicted.
    """

    identity: str
    timestamp: datetime
    champion_score: float
    input_order: int
    familiar: bool
    witness: bool
    strong_innocent: bool


def ordered(items: Sequence[QueueItem], variant: Variant) -> tuple[QueueItem, ...]:
    """Return ``items`` in ``variant``'s order. The set of alerts is unchanged.

    Raises:
        ValueError: If two alerts share an identity, or ``variant`` is not declared.
    """
    _require_unique(items)
    if variant not in VARIANTS:
        raise ValueError(f"{variant!r} is not one of the six declared reorderings")
    return tuple(sorted(items, key=lambda item: _key(item, variant)))


def a3_passes(
    items: Sequence[QueueItem],
    spans: Sequence[AttackSpan],
    origin: datetime,
    scores: Mapping[str, float],
) -> int:
    """Return how many attacks pass ADR 0212 under ``scores``.

    ``scores`` maps an alert identity to the number the queue is sorted by.
    Higher is earlier. The champion tiebreak still applies inside a tied score.
    """
    alerts = [
        QueueAlert(item.timestamp, float(scores[item.identity]), item.input_order) for item in items
    ]
    return sum(1 for rank in rank_attacks(alerts, spans, origin=origin) if rank.passed)


def recall_caught(
    items: Sequence[QueueItem],
    intervals: Sequence[LabelledInterval],
    origin: datetime,
    scores: Mapping[str, float],
    *,
    alerts_per_shift: int = ALERTS_PER_SHIFT,
) -> int:
    """Return how many attack windows contain a top-``alerts_per_shift`` alert.

    The keep matches ``recall_within_budget``: higher score, then earlier
    timestamp, then earlier input order, inside each 8-hour shift.
    """
    grouped: dict[int, list[QueueItem]] = {}
    for item in items:
        grouped.setdefault((item.timestamp - origin) // OPERATOR_SHIFT, []).append(item)
    kept: list[QueueItem] = []
    for group in grouped.values():
        group.sort(key=lambda item: (-scores[item.identity], item.timestamp, item.input_order))
        kept.extend(group[:alerts_per_shift])
    return sum(
        1
        for interval in intervals
        if any(interval.start <= item.timestamp <= interval.end for item in kept)
    )


def champion_scores(items: Sequence[QueueItem]) -> dict[str, float]:
    """Return the champion's own scores, keyed by identity."""
    return {item.identity: item.champion_score for item in items}


def variant_scores(items: Sequence[QueueItem], variant: Variant) -> dict[str, float]:
    """Return strictly decreasing scores that impose ``variant``'s order.

    Strictly decreasing so a later tiebreak cannot undo the declared priority.
    """
    sequence = ordered(items, variant)
    count = len(sequence)
    return {item.identity: float(count - position) for position, item in enumerate(sequence)}


def refuse_existing(path: Path) -> None:
    """Refuse a one-shot score whose output is already on disk.

    Raises:
        FileExistsError: If ``path`` exists. The caller must not overwrite it.
    """
    if path.exists():
        raise FileExistsError(f"{path} already exists; this run is once")


def reject_for_recall(caught: int, champion_caught: int) -> bool:
    """Return whether ``caught`` is lower than the champion's caught count.

    Equal is not a rejection. The two counts must be attacks from the same batch.
    """
    return caught < champion_caught


def select_variant(
    seed_passes: Mapping[Variant, int],
    hai_passes: Mapping[Variant, int],
    rejected: Sequence[Variant],
) -> Variant | None:
    """Return the frozen variant under ADR 0231, or ``None`` when all are rejected.

    Greatest development-seed A3, then greatest HAI A3, then earlier declaration
    order. A rejected variant is not eligible.
    """
    banned = set(rejected)
    eligible = [variant for variant in VARIANTS if variant not in banned]
    if not eligible:
        return None
    return min(
        eligible,
        key=lambda variant: (
            -seed_passes[variant],
            -hai_passes[variant],
            VARIANTS.index(variant),
        ),
    )


def _key(item: QueueItem, variant: Variant) -> tuple[object, ...]:
    parts: list[object] = []
    if variant in {Variant.FAMILIARITY, Variant.FAMILIARITY_CROSS, Variant.ALL_THREE}:
        parts.append(1 if item.familiar else 0)
    if variant in {
        Variant.CROSS_PATH,
        Variant.FAMILIARITY_CROSS,
        Variant.CROSS_INNOCENT,
        Variant.ALL_THREE,
    }:
        parts.append(0 if item.witness else 1)
    if variant in {Variant.INNOCENT, Variant.CROSS_INNOCENT, Variant.ALL_THREE}:
        parts.append(1 if item.strong_innocent else 0)
    parts.extend((-item.champion_score, item.timestamp, item.input_order))
    return tuple(parts)


def _require_unique(items: Sequence[QueueItem]) -> None:
    seen: set[str] = set()
    for item in items:
        if item.identity in seen:
            raise ValueError(f"two alerts share identity {item.identity!r}")
        seen.add(item.identity)

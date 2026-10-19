"""ADR 0231: a ranker permutes the champion's alerts and nothing else."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from phos.eval.datasets import LabelledInterval
from phos.eval.queue_rank import AttackSpan
from phos.eval.queue_reorder import (
    FROZEN_VARIANT,
    VARIANTS,
    QueueItem,
    Variant,
    a3_passes,
    champion_scores,
    ordered,
    recall_caught,
    refuse_existing,
    reject_for_recall,
    select_variant,
    variant_scores,
)

_START = datetime(2026, 10, 1, tzinfo=UTC)


def _item(
    identity: str,
    score: float,
    order: int,
    *,
    familiar: bool = False,
    witness: bool = False,
    strong: bool = False,
    minute: int = 0,
) -> QueueItem:
    return QueueItem(
        identity,
        _START + timedelta(minutes=minute),
        score,
        order,
        familiar,
        witness,
        strong,
    )


def test_the_frozen_variant_is_familiarity() -> None:
    assert FROZEN_VARIANT == Variant.FAMILIARITY
    assert FROZEN_VARIANT in VARIANTS


def test_every_variant_is_a_permutation() -> None:
    items = (
        _item("a", 3.0, 0, familiar=True),
        _item("b", 2.0, 1, witness=True),
        _item("c", 1.0, 2, strong=True, minute=1),
    )
    identities = {item.identity for item in items}
    for variant in VARIANTS:
        result = ordered(items, variant)
        assert {item.identity for item in result} == identities
        assert len(result) == len(items)


def test_familiarity_demotes_a_louder_familiar_alert() -> None:
    items = (
        _item("loud-familiar", 9.0, 0, familiar=True),
        _item("quiet-new", 1.0, 1, minute=1),
    )
    assert [item.identity for item in ordered(items, Variant.FAMILIARITY)] == [
        "quiet-new",
        "loud-familiar",
    ]


def test_cross_path_promotes_a_quieter_witness() -> None:
    items = (
        _item("loud-together", 9.0, 0),
        _item("quiet-witness", 1.0, 1, witness=True, minute=1),
    )
    assert ordered(items, Variant.CROSS_PATH)[0].identity == "quiet-witness"


def test_innocent_demotes_a_strong_innocent_member() -> None:
    items = (
        _item("loud-innocent", 9.0, 0, strong=True),
        _item("quiet-bare", 1.0, 1, minute=1),
    )
    assert ordered(items, Variant.INNOCENT)[0].identity == "quiet-bare"


def test_all_three_uses_the_declared_priority() -> None:
    items = (
        _item("familiar-witness", 5.0, 0, familiar=True, witness=True),
        _item("new-together", 9.0, 1, minute=1),
        _item("new-witness-bare", 1.0, 2, witness=True, minute=2),
    )
    assert [item.identity for item in ordered(items, Variant.ALL_THREE)] == [
        "new-witness-bare",
        "new-together",
        "familiar-witness",
    ]


def test_champion_tiebreak_keeps_the_higher_score() -> None:
    items = (_item("quiet", 1.0, 0), _item("loud", 4.0, 1, minute=1))
    assert ordered(items, Variant.FAMILIARITY)[0].identity == "loud"


def test_duplicate_identity_is_refused() -> None:
    items = (_item("a", 1.0, 0), _item("a", 2.0, 1, minute=1))
    with pytest.raises(ValueError, match="identity"):
        ordered(items, Variant.FAMILIARITY)


def test_variant_scores_impose_the_order_on_a3() -> None:
    items = (
        _item("benign", 9.0, 0, familiar=True),
        _item("attack", 1.0, 1, minute=30),
    )
    span = AttackSpan("only", items[1].timestamp, items[1].timestamp)
    assert a3_passes(items, (span,), _START, champion_scores(items)) == 0
    assert a3_passes(items, (span,), _START, variant_scores(items, Variant.FAMILIARITY)) == 1


def test_recall_within_eight_follows_the_reordering() -> None:
    benign = tuple(_item(f"b{index}", 10.0 - index, index, familiar=True) for index in range(8))
    attack = _item("attack", 0.1, 8, minute=30)
    items = (*benign, attack)
    interval = LabelledInterval(start=attack.timestamp, end=attack.timestamp, label="attack")
    assert recall_caught(items, (interval,), _START, champion_scores(items)) == 0
    promoted = variant_scores(items, Variant.FAMILIARITY)
    assert recall_caught(items, (interval,), _START, promoted) == 1


def test_reject_for_recall_allows_an_equal_count() -> None:
    assert reject_for_recall(37, 37) is False
    assert reject_for_recall(36, 37) is True


def test_refuse_existing_stops_a_second_write(tmp_path: Path) -> None:
    path = tmp_path / "held-back.json"
    refuse_existing(path)
    path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(FileExistsError, match="once"):
        refuse_existing(path)


def test_select_variant_skips_a_rejection_and_breaks_ties_by_declaration_order() -> None:
    seed = dict.fromkeys(VARIANTS, 4)
    hai = dict.fromkeys(VARIANTS, 19)
    seed[Variant.CROSS_PATH] = 6
    seed[Variant.ALL_THREE] = 6
    hai[Variant.ALL_THREE] = 21
    hai[Variant.CROSS_PATH] = 20
    assert select_variant(seed, hai, rejected=(Variant.CROSS_PATH,)) is Variant.ALL_THREE
    assert select_variant(seed, hai, rejected=VARIANTS) is None
    tied = dict.fromkeys(VARIANTS, 5)
    assert select_variant(tied, tied, rejected=()) is Variant.FAMILIARITY

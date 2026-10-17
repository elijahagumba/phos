"""The liar slice of the arena (ADR 0120): its declared seeds and its regression rule."""

from __future__ import annotations

from pathlib import Path

import pytest

from phos.breaking.liar_arena import (
    ARENA_LIAR_SEEDS,
    CONFIRM_SEEDS,
    CONFIRM_SEEDS_2,
    CONFIRM_SEEDS_3,
    RED_TEAM_SEEDS,
    LiarScorecard,
    regressions,
    score_windows,
    within_churn,
)
from phos.eval.liar_declaration import LIAR_HELD_OUT_SEEDS
from phos.library.ot import SEEDS


def test_arena_and_red_team_seeds_are_disjoint_from_held_out_and_calibration_seeds() -> None:
    arena, red = set(ARENA_LIAR_SEEDS), set(RED_TEAM_SEEDS)
    assert not arena & red
    assert not (arena | red) & set(LIAR_HELD_OUT_SEEDS)
    assert not (arena | red) & set(SEEDS)


def test_the_red_team_has_ten_seeds_the_arena_never_scores() -> None:
    assert len(RED_TEAM_SEEDS) == 10


def test_the_confirmation_seeds_are_disjoint_from_every_other_set() -> None:
    confirm = set(CONFIRM_SEEDS)
    assert len(confirm) == 10
    assert not confirm & (set(ARENA_LIAR_SEEDS) | set(RED_TEAM_SEEDS))
    assert not confirm & (set(LIAR_HELD_OUT_SEEDS) | set(SEEDS))
    second = set(CONFIRM_SEEDS_2)
    assert len(second) == 10
    assert not second & (confirm | set(ARENA_LIAR_SEEDS) | set(RED_TEAM_SEEDS))
    assert not second & (set(LIAR_HELD_OUT_SEEDS) | set(SEEDS))


def test_a_held_out_seed_is_refused_before_anything_is_generated(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="held out"):
        score_windows(None, [4242, LIAR_HELD_OUT_SEEDS[0]], tmp_path)
    assert list(tmp_path.iterdir()) == []


def card(seeds: tuple[int, ...], passing: set[tuple[str, int, float]]) -> LiarScorecard:
    return LiarScorecard(seeds, frozenset(passing), {}, 18, 0.0)


def test_a_lost_pass_is_a_regression() -> None:
    champion = card((4242,), {("power-generation", 4242, 0.0), ("batch-reactor", 4242, 0.4)})
    candidate = card((4242,), {("power-generation", 4242, 0.0), ("water-treatment", 4242, 0.2)})
    assert regressions(champion, candidate) == [("batch-reactor", 4242, 0.4)]


def test_seeds_only_the_champion_scored_are_not_counted() -> None:
    champion = card((4242, 95001), {("power-generation", 95001, 0.0)})
    assert regressions(champion, card((4242,), set())) == []


def test_passes_by_plant_lists_every_plant() -> None:
    counts = card((4242,), {("water-treatment", 4242, 0.2)}).passes_by_plant()
    assert counts == {"water-treatment": 1, "power-generation": 0, "batch-reactor": 0}


def test_the_fourth_set_is_disjoint_from_every_other() -> None:
    third = set(CONFIRM_SEEDS_3)
    others = set(ARENA_LIAR_SEEDS) | set(RED_TEAM_SEEDS) | set(CONFIRM_SEEDS) | set(CONFIRM_SEEDS_2)
    assert len(third) == 10 and not third & others
    assert not third & (set(LIAR_HELD_OUT_SEEDS) | set(SEEDS))


SEEDS52 = tuple(range(52))


def test_the_forward_rule_allows_losses_only_within_the_champion_s_churn() -> None:
    champion = card(SEEDS52, {("water-treatment", s, 0.0) for s in range(52)})  # allowance 3
    keeps_all = card(
        SEEDS52, set(champion.passing) | {("power-generation", s, 0.0) for s in range(4)}
    )
    assert within_churn(champion, keeps_all)
    loses_three = card(
        SEEDS52,
        (set(champion.passing) - {("water-treatment", s, 0.0) for s in range(3)})
        | {("power-generation", s, 0.0) for s in range(10)},
    )
    assert within_churn(champion, loses_three)
    loses_four = card(
        SEEDS52,
        (set(champion.passing) - {("water-treatment", s, 0.0) for s in range(4)})
        | {("power-generation", s, 0.0) for s in range(40)},
    )
    assert not within_churn(champion, loses_four)
    barely_more = card(
        SEEDS52, set(champion.passing) | {("power-generation", s, 0.0) for s in range(3)}
    )
    assert not within_churn(champion, barely_more)

"""The untargeted control arm's declared candidates (ADR 0121)."""

from __future__ import annotations

from pathlib import Path

from scripts.arena import windows_from
from scripts.arena_control import ROOT, RUNS, candidates, main
from tests.lab_only import skip_if_absent

from phos.atlas.consistency_windows import FROZEN_WINDOWS


def test_the_arm_draws_the_targeted_budget_deterministically() -> None:
    first, second = candidates(), candidates()
    assert first == second
    assert len(first) == RUNS == 18


def test_every_candidate_is_a_valid_window_set_that_changes_something() -> None:
    for candidate in candidates():
        assert 1 <= len(candidate) <= 2
        assert windows_from(candidate) != FROZEN_WINDOWS


def test_a_declaration_is_never_overwritten(tmp_path: Path) -> None:
    skip_if_absent(ROOT / "experiments" / "arena" / "water-liar" / "task.json")
    assert main([str(tmp_path / "control")]) == 0
    assert main([str(tmp_path / "control")]) == 2

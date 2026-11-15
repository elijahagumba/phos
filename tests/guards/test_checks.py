"""Each guard's decision, as a function, with the behaviour the hooks used to hold."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from tests.guards.conftest import TIER_RULE

from phos.guards import run_all
from phos.guards.checks import (
    declared_before_harness,
    file_scope,
    frozen_log,
    in_scope,
    public_record,
)
from phos.guards.subject import Subject
from phos.guards.tiers import check as red_tier
from phos.guards.tiers import parse

Stage = Callable[[str], None]


def shell(root: Path, command: str, role: str = "") -> Subject:
    return Subject(tool="Shell", paths=(), commands=(command,), role=role, root=root, editor="test")


def write(root: Path, path: str, role: str = "", tool: str = "Write") -> Subject:
    return Subject(tool=tool, paths=(path,), commands=(), role=role, root=root, editor="test")


class TestTierParsing:
    def test_the_four_tiers_come_out_of_the_rule(self) -> None:
        tiers = parse(TIER_RULE)
        assert "hai-23.05" in tiers.red
        assert "hai-20.07" in tiers.green
        assert "phos-icssim-heldout" in tiers.amber
        assert (94001, 94020) in tiers.seed_ranges

    def test_an_unreadable_rule_names_nothing_red(self) -> None:
        assert parse("").red == frozenset()


class TestRedTier:
    def test_a_validation_corpus_is_refused(self, checkout: Path) -> None:
        verdict = red_tier(write(checkout, "data/hai-23.05/x.csv", tool="Read"))
        assert verdict is not None
        assert "`hai-23.05` is red tier" in verdict.detail

    def test_the_longest_name_wins_so_the_development_corpus_passes(self, checkout: Path) -> None:
        # hai-20.07 contains "hai", which is red. A plain substring test would refuse it.
        assert red_tier(write(checkout, "data/hai-20.07/x.csv", tool="Read")) is None

    def test_a_held_out_seed_is_refused(self, checkout: Path) -> None:
        verdict = red_tier(shell(checkout, "uv run python x.py --seed 94005"))
        assert verdict is not None
        assert any("94005" in line for line in verdict.detail)

    def test_a_seed_outside_the_range_passes(self, checkout: Path) -> None:
        assert red_tier(shell(checkout, "uv run python x.py --seed 93999")) is None

    def test_an_ordinary_path_passes(self, checkout: Path) -> None:
        assert red_tier(write(checkout, "src/phos/atlas/engine.py")) is None

    def test_without_the_rule_file_the_guard_says_nothing(self, tmp_path: Path) -> None:
        assert red_tier(write(tmp_path, "data/hai-23.05/x.csv", tool="Read")) is None


class TestFrozenLog:
    def test_a_write_tool_on_the_log_is_refused(self, checkout: Path) -> None:
        verdict = frozen_log(write(checkout, "eval_runs/log.jsonl"))
        assert verdict is not None
        assert verdict.guard == "frozen_log"

    @pytest.mark.parametrize(
        "command",
        [
            "echo x >> eval_runs/log.jsonl",
            "cat x | tee eval_runs/log.jsonl",
            "sed -i s/a/b/ eval_runs/log.jsonl",
            "rm eval_runs/log.jsonl",
        ],
    )
    def test_shell_shapes_that_write_are_refused(self, checkout: Path, command: str) -> None:
        assert frozen_log(shell(checkout, command)) is not None

    def test_reading_the_log_is_fine(self, checkout: Path) -> None:
        assert frozen_log(shell(checkout, "tail -5 eval_runs/log.jsonl")) is None
        assert frozen_log(write(checkout, "eval_runs/log.jsonl", tool="Read")) is None

    def test_the_rule_sentence_is_quoted_from_the_file(self, checkout: Path) -> None:
        verdict = frozen_log(write(checkout, "eval_runs/log.jsonl"))
        assert verdict is not None
        assert "log.jsonl" in verdict.rule


class TestFileScope:
    def test_an_unset_role_is_not_an_out_of_scope_role(self, checkout: Path) -> None:
        assert file_scope(write(checkout, str(checkout / "PROGRESS.md"))) is None

    def test_an_edit_inside_the_scope_passes(self, checkout: Path) -> None:
        subject = write(checkout, str(checkout / "PROGRESS.md"), role="writer")
        assert file_scope(subject) is None

    def test_an_edit_outside_the_scope_is_refused(self, checkout: Path) -> None:
        subject = write(checkout, str(checkout / "src" / "phos" / "atlas" / "x.py"), role="writer")
        verdict = file_scope(subject)
        assert verdict is not None
        assert "outside writer's file scope" in verdict.headline

    def test_a_role_no_roster_entry_matches_is_reported(self, checkout: Path) -> None:
        subject = write(checkout, str(checkout / "PROGRESS.md"), role="nobody")
        verdict = file_scope(subject)
        assert verdict is not None
        assert "no swarm role matches" in verdict.headline

    def test_a_role_with_an_empty_scope_constrains_nothing(self, checkout: Path) -> None:
        subject = write(checkout, str(checkout / "anything.py"), role="scopeless")
        assert file_scope(subject) is None

    @pytest.mark.parametrize(
        ("relative", "scope", "inside"),
        [
            ("encyclopedia/02.md", ["encyclopedia/"], True),
            ("encyclopediaX/02.md", ["encyclopedia/"], False),
            ("docs/adr/0001-x.md", ["docs/adr/**"], True),
            ("PROGRESS.md", ["PROGRESS.md"], True),
            ("src/x.py", ["PROGRESS.md"], False),
        ],
    )
    def test_a_trailing_slash_means_the_tree(
        self, relative: str, scope: list[str], inside: bool
    ) -> None:
        assert in_scope(relative, scope) is inside


class TestPublicRecord:
    def test_a_commit_advancing_without_the_surfaces_is_reported(
        self, checkout: Path, stage: Stage
    ) -> None:
        stage("src/phos/atlas/new.py")
        verdict = public_record(shell(checkout, "git commit -m 'feat: x'"))
        assert verdict is not None
        assert "encyclopedia/" in verdict.detail[1]

    def test_a_commit_carrying_all_three_passes(self, checkout: Path, stage: Stage) -> None:
        stage("src/phos/atlas/new.py")
        stage("encyclopedia/02-x.md")
        stage("easy to reads/1-x.md")
        stage("README.md")
        assert public_record(shell(checkout, "git commit -m 'feat: x'")) is None

    def test_a_commit_advancing_nothing_passes(self, checkout: Path, stage: Stage) -> None:
        stage("notes.txt")
        assert public_record(shell(checkout, "git commit -m 'chore: x'")) is None

    def test_a_command_that_is_not_a_commit_passes(self, checkout: Path, stage: Stage) -> None:
        stage("src/phos/atlas/new.py")
        assert public_record(shell(checkout, "git status")) is None

    def test_on_main_the_message_says_so(self, checkout: Path, stage: Stage) -> None:
        stage("src/phos/atlas/new.py")
        verdict = public_record(shell(checkout, "git commit -m 'feat: x'"))
        assert verdict is not None
        assert "on main without its public record" in verdict.headline


class TestDeclaredBeforeHarness:
    def test_a_harness_run_with_nothing_declared_is_reported(self, checkout: Path) -> None:
        verdict = declared_before_harness(shell(checkout, "uv run python scripts/measure_thing.py"))
        assert verdict is not None
        assert "scripts/measure_thing.py" in verdict.detail[0]

    def test_an_ordinary_command_passes(self, checkout: Path) -> None:
        assert declared_before_harness(shell(checkout, "uv run pytest -q")) is None


class TestRunAll:
    def test_a_clean_call_draws_no_objection(self, checkout: Path) -> None:
        assert run_all(write(checkout, "src/phos/atlas/engine.py")) == []

    def test_one_call_can_draw_several(self, checkout: Path) -> None:
        # A shell command that both names a red-tier corpus and appends the frozen log.
        subject = shell(checkout, "python x.py --corpus data/hai-23.05 >> eval_runs/log.jsonl")
        guards = {verdict.guard for verdict in run_all(subject)}
        assert {"red_tier", "frozen_log"} <= guards

    def test_the_data_tier_guard_speaks_first(self, checkout: Path) -> None:
        subject = shell(checkout, "python x.py --corpus data/hai-23.05 >> eval_runs/log.jsonl")
        assert run_all(subject)[0].guard == "red_tier"

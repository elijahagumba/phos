"""The two editors reach the same verdict, and the hooks are tested at all.

Before this module no hook in this repository had a test. The six under `.claude/hooks/` are
untested code that only ever runs inside one editor, and CI runs nothing editor-specific, so a
broken guard would stay broken silently. These tests exercise the decision both hosts share, then
drive each host's shim with that host's own documented payload and assert the pair agrees.

Mandate §14.4 asks that both environments enforce identical execution gates. That is a property of
the pair, so a test of one proves nothing.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from tests.genesis.conftest import COMMAND, EXPERIMENT, MEASUREMENT, QUESTION

from phos.genesis.gatehost import _SEVERITY as _SEVERITY_RANKS
from phos.genesis.gatehost import decide, is_harness, repo_root_from
from phos.genesis.records import Experiment
from phos.genesis.store import Store
from phos.genesis.tiercheck import DECLARED_TIERS

#: The repository root, so the tests can drive the real hook scripts.
REPO = Path(__file__).resolve().parents[2]


def _committed(_path: Path, _root: Path) -> tuple[bool, bool]:
    """Stand in for git: the declaration is committed and untouched."""
    return (True, True)


def _uncommitted(_path: Path, _root: Path) -> tuple[bool, bool]:
    """Stand in for git: the declaration has never been committed."""
    return (False, False)


def _tampered(_path: Path, _root: Path) -> tuple[bool, bool]:
    """Stand in for git: committed, then edited."""
    return (True, False)


#: What the `commit` fixture hands back.
Commit = Callable[[str], None]

#: Named so the four gate states can be posed without a repository.
COMMITTED: Callable[[Path, Path], tuple[bool, bool]] = _committed
UNCOMMITTED: Callable[[Path, Path], tuple[bool, bool]] = _uncommitted
TAMPERED: Callable[[Path, Path], tuple[bool, bool]] = _tampered


def seeded(root: Path, *, phase: str = "declared") -> Store:
    """Return a store holding the sample question and an experiment in ``phase``.

    The rule file and registry are copied in as well: a declaration's tier is resolved against
    them rather than read from the payload, so a checkout without them refuses every run it
    declares (ADR 0416) and every gate test here would be exercising that refusal instead of the
    state it names.
    """
    store = Store(root)
    from phos.genesis.records import Question

    (root / "docs" / "rules").mkdir(parents=True, exist_ok=True)
    for name in ("data-tiers.md", "docs-on-main.md"):
        (root / "docs" / "rules" / name).write_bytes((REPO / "docs" / "rules" / name).read_bytes())
    (root / "data").mkdir(exist_ok=True)
    (root / "data" / "registry.json").write_bytes((REPO / "data" / "registry.json").read_bytes())

    store.write(Question.model_validate({**QUESTION, "id": "Q-0001"}))
    record: dict[str, Any] = {**EXPERIMENT, "id": "E-0001", "phase": phase}
    if phase in ("measured", "judged"):
        record["measured"] = MEASUREMENT
    if phase == "judged":
        record["verdict"] = {"outcome": "refused", "per_bar": {"b1": False}}
    store.write(Experiment.model_validate(record))
    return store


class TestIsHarness:
    @pytest.mark.parametrize(
        "command",
        [
            "uv run python scripts/lane_inlet.py --corpus data/x",
            "python scripts/measure_baseline_table.py",
            "scripts/evaluate_thing.py",
            "uv run python scripts/gate.py",
        ],
    )
    def test_a_harness_command_is_recognised(self, command: str) -> None:
        assert is_harness(command) is True

    @pytest.mark.parametrize(
        "command", ["git status", "ls scripts/", "uv run pytest -q", "cat scripts/genesis.py"]
    )
    def test_an_ordinary_command_is_not_the_gates_business(self, command: str) -> None:
        assert is_harness(command) is False

    def test_a_non_harness_command_gets_no_opinion(self, tmp_path: Path) -> None:
        assert decide("git status", Store(tmp_path)) is None


class TestDecide:
    def test_nothing_declared_is_softenable(self, tmp_path: Path) -> None:
        decision = decide(COMMAND, Store(tmp_path), committed=COMMITTED)
        assert decision is not None
        assert decision.verdict == "silent"
        assert decision.softenable is True
        assert decision.allowed is False

    def test_declared_and_committed_is_allowed(self, tmp_path: Path) -> None:
        decision = decide(COMMAND, seeded(tmp_path), committed=COMMITTED)
        assert decision is not None
        assert decision.allowed is True
        assert decision.experiment == "E-0001"

    def test_declared_but_uncommitted_is_refused_and_not_softenable(self, tmp_path: Path) -> None:
        decision = decide(COMMAND, seeded(tmp_path), committed=UNCOMMITTED)
        assert decision is not None
        assert decision.verdict == "uncommitted"
        assert decision.softenable is False

    def test_edited_after_the_commit_is_refused(self, tmp_path: Path) -> None:
        decision = decide(COMMAND, seeded(tmp_path), committed=TAMPERED)
        assert decision is not None
        assert decision.verdict == "tampered"
        assert decision.softenable is False

    def test_a_spent_score_is_refused(self, tmp_path: Path) -> None:
        decision = decide(COMMAND, seeded(tmp_path, phase="judged"), committed=COMMITTED)
        assert decision is not None
        assert decision.verdict == "spent"
        assert decision.softenable is False

    def test_only_silence_may_ever_be_softened(self, tmp_path: Path) -> None:
        for committed, phase in (
            (UNCOMMITTED, "declared"),
            (TAMPERED, "declared"),
            (COMMITTED, "judged"),
        ):
            decision = decide(COMMAND, seeded(tmp_path, phase=phase), committed=committed)
            assert decision is not None and decision.softenable is False

    def test_the_reason_is_data_rather_than_english_a_host_must_parse(self, tmp_path: Path) -> None:
        # The first Cursor adapter sniffed stderr for "already judged". A reworded message would
        # have silently started allowing a spent score.
        decision = decide(COMMAND, seeded(tmp_path, phase="judged"), committed=COMMITTED)
        assert decision is not None
        assert decision.verdict == "spent"


class TestTierCrossCheck:
    """``gate`` refuses when the resolved tier and the declared tier disagree (ADR 0416)."""

    def _declaring(self, root: Path, corpus: str, tier: str) -> Store:
        # `seeded` puts the rule and registry in place; this then writes over the sample record
        # with the corpus and tier the test is about.
        store = seeded(root)
        record = json.loads(json.dumps(EXPERIMENT))
        record["declared"]["corpus"] = corpus
        record["declared"]["tier"] = tier
        store.write(Experiment.model_validate({**record, "id": "E-0001", "phase": "declared"}))
        return store

    def test_a_tier_that_contradicts_the_rule_is_refused(self, tmp_path: Path) -> None:
        store = self._declaring(tmp_path, "phos-icssim-heldout", "iterate")
        decision = decide(COMMAND, store, committed=COMMITTED)
        assert decision is not None
        assert decision.verdict == "tier"
        assert decision.allowed is False

    def test_the_tier_refusal_is_never_softenable(self, tmp_path: Path) -> None:
        store = self._declaring(tmp_path, "phos-icssim-heldout", "iterate")
        decision = decide(COMMAND, store, committed=COMMITTED)
        assert decision is not None
        assert decision.softenable is False

    def test_a_never_read_corpus_is_refused_whatever_tier_the_record_can_carry(
        self, tmp_path: Path
    ) -> None:
        # `tier: "never"` is not in this table because the model refuses that record before it can
        # be written at all, so that combination cannot reach the gate: a check for it would be a
        # check that cannot fire. What is reachable is a record labelled `iterate` or `once` on a
        # corpus the rule forbids, and that is the audit's hole exactly (ADR 0416).
        reachable = [tier for tier in DECLARED_TIERS if tier != "never"]
        assert reachable == ["iterate", "once"]
        for tier in reachable:
            store = self._declaring(tmp_path, "hai-21.03", tier)
            decision = decide(COMMAND, store, committed=COMMITTED)
            assert decision is not None, tier
            assert decision.verdict == "tier", tier

    def test_a_tier_the_rule_agrees_with_does_not_object(self, tmp_path: Path) -> None:
        store = self._declaring(tmp_path, "phos-icssim-heldout", "once")
        decision = decide(COMMAND, store, committed=COMMITTED)
        assert decision is not None
        assert decision.allowed is True

    def test_an_unknown_corpus_is_refused_at_the_gate_too(self, tmp_path: Path) -> None:
        store = self._declaring(tmp_path, "a-corpus-nobody-registered", "iterate")
        decision = decide(COMMAND, store, committed=COMMITTED)
        assert decision is not None
        assert decision.verdict == "tier"

    def test_the_refusal_names_both_tiers_and_the_rule(self, tmp_path: Path) -> None:
        store = self._declaring(tmp_path, "phos-icssim-heldout", "iterate")
        decision = decide(COMMAND, store, committed=COMMITTED)
        assert decision is not None
        assert "docs/rules/data-tiers.md" in decision.detail
        assert "iterate" in decision.detail
        assert "once" in decision.detail

    def test_the_tier_check_comes_before_an_allow_but_after_a_spent_score(
        self, tmp_path: Path
    ) -> None:
        # A spent score is the more serious finding, so it leads. The tier check still stops a
        # run that a spent record would otherwise have allowed through.
        store = self._declaring(tmp_path, "hai-21.03", "iterate")
        decision = decide(COMMAND, store, committed=COMMITTED)
        assert decision is not None
        assert decision.verdict == "tier"
        assert _SEVERITY_RANKS["spent"] < _SEVERITY_RANKS["tier"] < _SEVERITY_RANKS["allow"]

    def test_a_tier_refusal_and_an_uncommitted_one_are_both_reported(self, tmp_path: Path) -> None:
        # Two declarations matching one command: one on a never-read corpus and committed, one
        # merely uncommitted. Both are collected and the more serious leads, so neither is hidden
        # behind the other. This is the multi-reason path the `tier` verdict newly participates in.
        store = self._declaring(tmp_path, "hai-21.03", "iterate")
        second = json.loads(json.dumps(EXPERIMENT))
        second["declared"]["command"] = COMMAND
        store.write(Experiment.model_validate({**second, "id": "E-0002", "phase": "declared"}))

        def committed(path: Path, _root: Path) -> tuple[bool, bool]:
            return (False, False) if path.name.startswith("E-0002") else (True, True)

        decision = decide(COMMAND, store, committed=committed)
        assert decision is not None
        assert decision.verdict == "tier", "the tier refusal outranks an uncommitted declaration"
        assert "E-0002" in decision.detail, "the other refusal is still reported"
        assert "E-0001" in decision.detail


class TestRepoRoot:
    def test_the_root_is_the_directory_holding_dot_git(self, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        nested = tmp_path / "a" / "b"
        nested.mkdir(parents=True)
        assert repo_root_from(nested) == tmp_path

    def test_without_a_git_entry_the_path_is_returned_unchanged(self, tmp_path: Path) -> None:
        assert repo_root_from(tmp_path) == tmp_path


def _seed_corpus(root: Path, corpus: str, tier: str) -> Store:
    """Write the sample question and a declared experiment on ``corpus`` at ``tier``."""
    store = seeded(root)
    record = json.loads(json.dumps(EXPERIMENT))
    record["declared"]["corpus"] = corpus
    record["declared"]["tier"] = tier
    store.write(Experiment.model_validate({**record, "id": "E-0001", "phase": "declared"}))
    return store


def run_cursor_hook(repo: Path, command: str) -> dict[str, Any]:
    """Drive the real Cursor hook with Cursor's documented payload and return its answer."""
    done = subprocess.run(
        [sys.executable, str(REPO / ".cursor" / "hooks" / "genesis_gate.py")],
        input=json.dumps({"command": command, "workspace_roots": [str(repo)]}),
        capture_output=True,
        text=True,
        env={
            "PATH": "/usr/bin:/bin",
            "PYTHONPATH": str(REPO / "src"),
        },
        check=False,
    )
    assert done.returncode == 0, done.stderr
    parsed: dict[str, Any] = json.loads(done.stdout)
    return parsed


def run_claude_hook(repo: Path, command: str) -> int:
    """Drive the real Claude Code hook with Claude Code's payload and return its exit code."""
    done = subprocess.run(
        [sys.executable, str(REPO / ".claude" / "hooks" / "genesis_gate.py")],
        input=json.dumps({"tool_input": {"command": command}}),
        capture_output=True,
        text=True,
        env={
            "CLAUDE_PROJECT_DIR": str(repo),
            "PATH": "/usr/bin:/bin",
            "PYTHONPATH": str(REPO / "src"),
        },
        check=False,
    )
    return done.returncode


class TestCrossEnvironmentParity:
    """Mandate §14.4: both environments enforce identical gates. Tested as a pair."""

    def test_a_committed_declaration_is_allowed_in_both(self, repo: Path, commit: Commit) -> None:
        seeded(repo)
        commit("declare E-0001")
        assert run_cursor_hook(repo, COMMAND)["permission"] == "allow"
        assert run_claude_hook(repo, COMMAND) == 0

    def test_an_uncommitted_declaration_is_blocked_in_both(self, repo: Path) -> None:
        seeded(repo)
        assert run_cursor_hook(repo, COMMAND)["permission"] == "deny"
        assert run_claude_hook(repo, COMMAND) == 2

    def test_a_spent_score_is_blocked_in_both(self, repo: Path, commit: Commit) -> None:
        seeded(repo, phase="judged")
        commit("result E-0001")
        assert run_cursor_hook(repo, COMMAND)["permission"] == "deny"
        assert run_claude_hook(repo, COMMAND) == 2

    def test_an_ordinary_command_passes_both_untouched(self, repo: Path) -> None:
        assert run_cursor_hook(repo, "git status")["permission"] == "allow"
        assert run_claude_hook(repo, "git status") == 0

    def test_a_tier_that_contradicts_the_rule_is_blocked_in_both(
        self, repo: Path, commit: Commit
    ) -> None:
        # Both editors ask `gatehost.decide`, so the tier check is inherited rather than repeated.
        # A parity test is a property of the pair, so this asserts both rather than one.
        _seed_corpus(repo, "hai-21.03", "iterate")
        commit("declare E-0001 on a validation corpus")
        assert run_cursor_hook(repo, COMMAND)["permission"] == "deny"
        assert run_claude_hook(repo, COMMAND) == 2

    def test_the_tier_refusal_is_not_softened_to_a_question_in_cursor(
        self, repo: Path, commit: Commit
    ) -> None:
        _seed_corpus(repo, "phos-icssim-heldout", "iterate")
        commit("declare E-0001 with the wrong tier")
        answer = run_cursor_hook(repo, COMMAND)
        assert answer["permission"] == "deny", "a wrong tier is not a migration case"
        assert "tier" in answer["agent_message"]

    def test_silence_is_soft_in_both_but_cursor_asks_where_claude_only_warns(
        self, repo: Path
    ) -> None:
        # The one state where the hosts legitimately differ, because only Cursor can express it.
        # Neither blocks; Cursor puts the decision to the human instead of printing a warning.
        assert run_cursor_hook(repo, COMMAND)["permission"] == "ask"
        assert run_claude_hook(repo, COMMAND) == 0

    def test_the_cursor_hook_explains_itself_to_both_reader_and_agent(self, repo: Path) -> None:
        seeded(repo)
        answer = run_cursor_hook(repo, COMMAND)
        assert answer["permission"] == "deny"
        assert "E-0001" in answer["agent_message"]
        assert answer["user_message"]


class TestCursorHooksConfig:
    def test_the_hook_is_registered_on_the_shell_event_and_fails_closed(self) -> None:
        config = json.loads((REPO / ".cursor" / "hooks.json").read_text(encoding="utf-8"))
        assert config["version"] == 1
        entries = config["hooks"]["beforeShellExecution"]
        entry = next(e for e in entries if "genesis_gate" in e["command"])
        assert entry["failClosed"] is True, "a gate that fails open is not a gate when it breaks"
        assert "matcher" not in entry, "Cursor advises script-side filtering before a matcher"

    def test_the_registered_script_exists_and_is_executable(self) -> None:
        script = REPO / ".cursor" / "hooks" / "genesis_gate.py"
        assert script.is_file()
        assert script.stat().st_mode & 0o111, "Cursor runs it directly"


class TestTheGateFindsItsOwnRecord:
    """Where the gate looks for the record, now that no undocumented variable tells it.

    ADR 0414 recorded that `workspace_roots` replaced `CURSOR_PROJECT_DIR`, which Cursor does not
    document. That was true of `phos_guards.py` and not of this hook, which went on reading the
    variable until ADR 0419. These tests are here so the record and the code cannot part again.
    """

    def test_no_cursor_hook_reads_an_undocumented_environment_variable(self) -> None:
        for script in sorted((REPO / ".cursor" / "hooks").glob("*.py")):
            body = script.read_text(encoding="utf-8")
            assert "CURSOR_PROJECT_DIR" not in body, f"{script.name} reads an undocumented variable"

    def test_the_variable_is_ignored_even_when_something_sets_it(
        self, repo: Path, commit: Commit
    ) -> None:
        seeded(repo)
        commit("declare E-0001")
        done = subprocess.run(
            [sys.executable, str(REPO / ".cursor" / "hooks" / "genesis_gate.py")],
            input=json.dumps({"command": COMMAND, "workspace_roots": [str(repo)]}),
            capture_output=True,
            text=True,
            env={
                "CURSOR_PROJECT_DIR": "/nonexistent/decoy",
                "PATH": "/usr/bin:/bin",
                "PYTHONPATH": str(REPO / "src"),
            },
            check=False,
        )
        assert done.returncode == 0, done.stderr
        assert json.loads(done.stdout)["permission"] == "allow", (
            "the decoy was consulted instead of workspace_roots"
        )

    def test_without_a_workspace_root_it_falls_back_to_its_own_checkout(self) -> None:
        done = subprocess.run(
            [sys.executable, str(REPO / ".cursor" / "hooks" / "genesis_gate.py")],
            input=json.dumps({"command": "echo ordinary"}),
            capture_output=True,
            text=True,
            env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(REPO / "src")},
            check=False,
        )
        assert done.returncode == 0, done.stderr
        assert json.loads(done.stdout)["permission"] == "allow"

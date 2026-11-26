"""Tests for the orchestrator: gate order, refusal, abort and resume.

Each test drives the real orchestrator against a throwaway repository. Runtimes are injected as
test adapters so a test does not depend on which CLI is logged in, and the recording still names the
runtime the adapter reports, which is the property the task asks for.

``test_start_records_and_plans`` is marked ``lab_only``. Starting an operation resolves its corpus
against ``docs/rules/data-tiers.md``, and that path symlinks into ``.cursor/rules/``, which
``public/manifest.toml`` forbids, so in the public tree the start refuses for want of the rule
rather than recording and planning. It still runs here.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from phos.forge import adapters, orchestrator, worktree
from phos.forge.operation import OperationError, OperationStore
from phos.forge.orchestrator import Orchestrator, RoleOutcome
from phos.forge.protocol import AgentResult, RoleRequest


class _WritesNothing(adapters.RuntimeAdapter):
    """Answers cleanly and writes nothing."""

    runtime = "codex"
    binary = "python3"

    def probe(self) -> adapters.Probe:
        return adapters.Probe(True, "ready")

    def invoke(self, request: RoleRequest) -> AgentResult:
        return AgentResult(
            runtime=self.runtime,
            runtime_state="ready",
            status="ok",
            exit_status=0,
            stdout="I looked and wrote nothing.",
            duration_s=0.01,
        )


class _Leaks(adapters.RuntimeAdapter):
    """Prints the name of a sealed corpus, which must abort the operation."""

    runtime = "codex"
    binary = "python3"

    def probe(self) -> adapters.Probe:
        return adapters.Probe(True, "ready")

    def invoke(self, request: RoleRequest) -> AgentResult:
        return AgentResult(
            runtime=self.runtime,
            runtime_state="ready",
            status="ok",
            exit_status=0,
            stdout="I opened /Volumes/PHOSRED/hai/train.csv to check.",
            duration_s=0.01,
        )


class _WritesInside(adapters.RuntimeAdapter):
    """Writes one file inside the worktree, so scope checking has something to look at."""

    runtime = "codex"
    binary = "python3"

    relative: str = "notes.md"

    def probe(self) -> adapters.Probe:
        return adapters.Probe(True, "ready")

    def invoke(self, request: RoleRequest) -> AgentResult:
        target = request.worktree / self.relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("done\n")
        return AgentResult(
            runtime=self.runtime,
            runtime_state="ready",
            status="ok",
            exit_status=0,
            stdout="wrote a file",
            duration_s=0.01,
        )


class _NotInstalled(adapters.RuntimeAdapter):
    """A runtime that is present but cannot authenticate."""

    runtime = "claude"
    binary = "python3"

    def probe(self) -> adapters.Probe:
        return adapters.Probe(False, "OAuth session expired")

    def invoke(self, request: RoleRequest) -> AgentResult:  # pragma: no cover - refused first
        raise AssertionError("must not run")


@pytest.fixture()
def injected(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace the adapter registry with the test adapters.

    Args:
        monkeypatch: pytest's patcher.
    """
    monkeypatch.setitem(adapters.ADAPTERS, "codex", _WritesNothing)
    monkeypatch.setitem(adapters.ADAPTERS, "claude", _NotInstalled)


@pytest.fixture()
def worktree_parent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Put worktrees under the test's temporary directory rather than beside the repository.

    Args:
        tmp_path: pytest's temporary directory.
        monkeypatch: pytest's patcher.

    Returns:
        The directory worktrees go under.
    """

    def _default(root: Path, operation: str, role: str) -> Path:
        return (tmp_path / "worktrees" / operation / role).resolve()

    monkeypatch.setattr(worktree, "default_path", _default)
    return tmp_path / "worktrees"


def test_start_refuses_a_never_tier_corpus(repo: Path) -> None:
    made = Orchestrator(repo)
    with pytest.raises(ValueError, match="cannot be used"):
        made.start("op-1", idea="x", corpus="hai")


@pytest.mark.lab_only
def test_start_records_and_plans(repo: Path) -> None:
    made = Orchestrator(repo)
    made.start("op-1", idea="a thing", corpus="phos-icssim-dev4-walk")
    state = OperationStore(repo).load("op-1")
    assert state.state == "PLANNED"
    assert state.idea == "a thing"


def test_approve_without_a_declaration_is_refused(repo: Path, injected: None) -> None:
    made = Orchestrator(repo)
    made.start("op-1", idea="x")
    with pytest.raises(OperationError, match="names no declaration"):
        made.approve("op-1")
    gates = OperationStore(repo).load("op-1").gates
    assert gates[-1].gate == "a"
    assert gates[-1].passed is False


def test_approve_with_an_uncommitted_declaration_is_refused(
    declared_repo: Path, injected: None
) -> None:
    made = Orchestrator(declared_repo)
    made.start("op-1", idea="x", declaration="E-0002")
    with pytest.raises(OperationError, match="not committed at HEAD"):
        made.approve("op-1")


def test_approve_with_a_committed_declaration_reaches_approved(
    declared_repo: Path, injected: None
) -> None:
    made = Orchestrator(declared_repo)
    made.start("op-1", idea="x", declaration="E-0001")
    approved = made.approve("op-1")
    assert approved.state == "APPROVED"
    assert approved.gates[-1].gate == "a"
    assert approved.gates[-1].passed


def test_approve_goes_through_designing_so_the_history_is_honest(
    declared_repo: Path, injected: None
) -> None:
    made = Orchestrator(declared_repo)
    made.start("op-1", idea="x", declaration="E-0001")
    made.approve("op-1")
    states = [entry.to_state for entry in OperationStore(declared_repo).load("op-1").history]
    assert states == ["PROPOSED", "PLANNED", "DESIGNING", "APPROVED"]


def test_a_role_outside_a_working_state_is_refused(repo: Path, injected: None) -> None:
    made = Orchestrator(repo)
    made.start("op-1", idea="x")
    with pytest.raises(OperationError, match="nowhere else"):
        made.run_role("op-1", role="applied_scientist", task="t", runtime="codex")


def test_a_role_runs_and_is_recorded_with_its_runtime(
    declared_repo: Path, injected: None, worktree_parent: Path
) -> None:
    made = Orchestrator(declared_repo)
    made.start("op-1", idea="x", declaration="E-0001")
    made.approve("op-1")
    OperationStore(declared_repo).transition("op-1", "IMPLEMENTING", reason="build")
    outcome = made.run_role(
        "op-1", role="applied_scientist", task="write a harness", runtime="codex"
    )
    assert outcome.ran
    assert outcome.ok
    record = OperationStore(declared_repo).load("op-1")
    assert len(record.agents) == 1
    assert record.agents[0].runtime == "codex"
    assert record.agents[0].role == "applied_scientist"


def test_the_worktree_is_outside_the_checkout(
    declared_repo: Path, injected: None, worktree_parent: Path
) -> None:
    made = Orchestrator(declared_repo)
    made.start("op-1", idea="x", declaration="E-0001")
    made.approve("op-1")
    OperationStore(declared_repo).transition("op-1", "IMPLEMENTING", reason="build")
    outcome = made.run_role("op-1", role="applied_scientist", task="t", runtime="codex")
    assert outcome.ran
    agent = OperationStore(declared_repo).load("op-1").agents[0]
    assert worktree.is_outside_checkout(declared_repo, Path(agent.worktree))


def test_a_main_branch_is_refused_before_anything_runs(
    declared_repo: Path, injected: None, worktree_parent: Path
) -> None:
    made = Orchestrator(declared_repo)
    made.start("op-1", idea="x", declaration="E-0001")
    made.approve("op-1")
    OperationStore(declared_repo).transition("op-1", "IMPLEMENTING", reason="build")
    outcome = made.run_role(
        "op-1", role="applied_scientist", task="t", runtime="codex", branch="main"
    )
    assert not outcome.ran
    assert "not a place to work" in outcome.refusal
    assert OperationStore(declared_repo).load("op-1").agents == ()


def test_a_sealed_step_stops_when_the_volume_is_absent(
    declared_repo: Path,
    injected: None,
    worktree_parent: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("phos.forge.gates.SEALED_VOLUME", tmp_path / "definitely-not-mounted")
    made = Orchestrator(declared_repo)
    made.start("op-1", idea="x", declaration="E-0001")
    made.approve("op-1")
    OperationStore(declared_repo).transition("op-1", "IMPLEMENTING", reason="build")
    outcome = made.run_role(
        "op-1", role="verification_engineer", task="score", runtime="codex", sealed=True
    )
    assert not outcome.ran
    assert "is not mounted" in outcome.refusal
    gates = OperationStore(declared_repo).load("op-1").gates
    assert any(gate.gate == "b" and not gate.passed for gate in gates)


def test_an_unready_runtime_blocks_the_operation(
    declared_repo: Path, injected: None, worktree_parent: Path
) -> None:
    made = Orchestrator(declared_repo)
    made.start("op-1", idea="x", declaration="E-0001")
    made.approve("op-1")
    OperationStore(declared_repo).transition("op-1", "IMPLEMENTING", reason="build")
    outcome = made.run_role("op-1", role="applied_scientist", task="t", runtime="claude")
    assert not outcome.ran
    assert outcome.state == "BLOCKED"
    assert "OAuth session expired" in outcome.refusal


def test_a_leak_aborts_and_writes_the_inbox(
    declared_repo: Path, monkeypatch: pytest.MonkeyPatch, worktree_parent: Path
) -> None:
    monkeypatch.setitem(adapters.ADAPTERS, "codex", _Leaks)
    made = Orchestrator(declared_repo)
    made.start("op-1", idea="x", declaration="E-0001")
    made.approve("op-1")
    OperationStore(declared_repo).transition("op-1", "IMPLEMENTING", reason="build")
    outcome = made.run_role("op-1", role="applied_scientist", task="t", runtime="codex")

    assert outcome.ran
    assert not outcome.ok
    assert outcome.state == "BLOCKED"
    assert outcome.red is not None
    assert not outcome.red.clean

    inbox = declared_repo / "docs/method/INBOX.md"
    assert inbox.is_file()
    text = inbox.read_text()
    assert "hai" in text
    assert "applied_scientist" in text

    record = OperationStore(declared_repo).load("op-1")
    assert record.agents[0].status == "refused"


def test_a_role_that_stays_in_scope_is_not_reported(
    declared_repo: Path, monkeypatch: pytest.MonkeyPatch, worktree_parent: Path
) -> None:
    monkeypatch.setitem(adapters.ADAPTERS, "codex", _WritesInside)
    made = Orchestrator(declared_repo)
    made.start("op-1", idea="x", declaration="E-0001")
    made.approve("op-1")
    OperationStore(declared_repo).transition("op-1", "IMPLEMENTING", reason="build")
    outcome = made.run_role(
        "op-1",
        role="applied_scientist",
        task="t",
        runtime="codex",
        may_write=("**/*.md", "notes.md"),
    )
    assert outcome.refusal == ""
    assert outcome.ok


def test_a_role_that_writes_outside_its_scope_is_reported(
    declared_repo: Path, monkeypatch: pytest.MonkeyPatch, worktree_parent: Path
) -> None:
    monkeypatch.setitem(adapters.ADAPTERS, "codex", _WritesInside)
    made = Orchestrator(declared_repo)
    made.start("op-1", idea="x", declaration="E-0001")
    made.approve("op-1")
    OperationStore(declared_repo).transition("op-1", "IMPLEMENTING", reason="build")
    outcome = made.run_role(
        "op-1",
        role="applied_scientist",
        task="t",
        runtime="codex",
        may_write=("src/phos/atlas/**",),
    )
    assert "outside its declared scope" in outcome.refusal
    gates = OperationStore(declared_repo).load("op-1").gates
    assert any(gate.gate == "scope" and not gate.passed for gate in gates)


def test_a_blocked_operation_resumes_into_the_state_it_left(
    declared_repo: Path, injected: None, worktree_parent: Path
) -> None:
    from phos.forge.operation import resume_point

    made = Orchestrator(declared_repo)
    made.start("op-1", idea="x", declaration="E-0001")
    made.approve("op-1")
    store = OperationStore(declared_repo)
    store.transition("op-1", "BLOCKED", reason="interrupted")
    assert resume_point(store.load("op-1")) == "APPROVED"

    store.transition("op-1", "IMPLEMENTING", reason="resumed")
    outcome = made.run_role("op-1", role="applied_scientist", task="t", runtime="codex")
    assert outcome.ran


def test_the_runtime_in_the_record_is_the_one_that_ran(
    declared_repo: Path, monkeypatch: pytest.MonkeyPatch, worktree_parent: Path
) -> None:
    monkeypatch.setitem(adapters.ADAPTERS, "codex", _WritesInside)
    made = Orchestrator(declared_repo)
    made.start("op-1", idea="x", declaration="E-0001")
    made.approve("op-1")
    OperationStore(declared_repo).transition("op-1", "IMPLEMENTING", reason="build")
    outcome = made.run_role("op-1", role="applied_scientist", task="t", runtime="codex")
    assert outcome.result is not None
    recorded = OperationStore(declared_repo).load("op-1").agents[0]
    assert recorded.runtime == outcome.result.runtime


def test_a_role_outcome_is_false_when_nothing_ran() -> None:
    outcome = RoleOutcome("x", False, None, "refused", "BLOCKED")
    assert not outcome.ok


def test_the_orchestrator_names_no_model() -> None:
    source = Path(orchestrator.__file__).read_text(encoding="utf-8")
    for name in ("claude-opus", "gpt-", "sonnet", "haiku", "gemini", "grok"):
        assert name not in source


def test_an_operation_file_written_by_the_orchestrator_has_no_verdict(
    declared_repo: Path, injected: None, worktree_parent: Path
) -> None:
    made = Orchestrator(declared_repo)
    made.start("op-1", idea="x", declaration="E-0001")
    made.approve("op-1")
    OperationStore(declared_repo).transition("op-1", "IMPLEMENTING", reason="build")
    made.run_role("op-1", role="applied_scientist", task="t", runtime="codex")
    data = json.loads((declared_repo / "docs/forge/state/op-1.json").read_text())
    assert "verdict" not in data
    assert "measurement" not in data
    assert "bars" not in data

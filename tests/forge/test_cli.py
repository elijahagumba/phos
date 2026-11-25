"""End-to-end tests for the paths a FORGE operation actually takes.

These drive the command line rather than the library, because the exit codes are the contract a
script or a human reads: 0 done, 2 refused, 3 blocked. A refusal that returned 0 would be a gate
nobody notices.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _forge(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run one FORGE subcommand against a repository.

    Args:
        root: The repository root the command should treat as its own.
        *args: The subcommand and its flags.

    Returns:
        The completed process.
    """
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "forge.py"), *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "PYTHONPATH": f"{ROOT / 'src'}"},
    )


def test_states_prints_the_table() -> None:
    done = _forge(ROOT, "states")
    assert done.returncode == 0
    assert "PROPOSED" in done.stdout
    assert "nothing" in done.stdout


def test_tokens_prints_what_is_refused() -> None:
    done = _forge(ROOT, "tokens")
    assert done.returncode == 0
    assert "hai" in done.stdout
    assert "phosred" in done.stdout
    assert "phos-icssim-dev4-walk" not in done.stdout


def test_capability_reports_each_runtime() -> None:
    done = _forge(ROOT, "capability")
    assert done.returncode in {0, 3}
    for runtime in ("claude", "cursor", "codex"):
        assert runtime in done.stdout
    assert "sealed volume" in done.stdout


def test_status_of_a_missing_operation_is_refused() -> None:
    done = _forge(ROOT, "status", "no-such-operation-at-all")
    assert done.returncode == 2
    assert "no operation" in done.stderr


def test_start_then_status_then_transition(repo: Path) -> None:
    started = _forge(repo, "start", "op-int", "--idea", "an integration test")
    assert started.returncode == 0, started.stderr
    assert "PLANNED" in started.stdout

    status = _forge(repo, "status", "op-int")
    assert status.returncode == 0
    assert "PLANNED" in status.stdout
    assert "an integration test" in status.stdout

    moved = _forge(repo, "transition", "op-int", "DESIGNING", "--reason", "designing")
    assert moved.returncode == 0
    assert "DESIGNING" in moved.stdout


def test_an_illegal_transition_exits_refused(repo: Path) -> None:
    _forge(repo, "start", "op-illegal", "--idea", "x")
    done = _forge(repo, "transition", "op-illegal", "COMPLETED")
    assert done.returncode == 2
    assert "may not move" in done.stderr


def test_start_refuses_a_never_tier_corpus(repo: Path) -> None:
    done = _forge(repo, "start", "op-red", "--idea", "x", "--corpus", "hai")
    assert done.returncode == 2
    assert "cannot be used" in done.stderr


def test_approve_without_a_declaration_exits_refused(repo: Path) -> None:
    _forge(repo, "start", "op-nod", "--idea", "x")
    done = _forge(repo, "approve", "op-nod")
    assert done.returncode == 2
    assert "names no declaration" in done.stderr


def test_resume_reports_where_a_blocked_operation_left_off(repo: Path) -> None:
    _forge(repo, "start", "op-resume", "--idea", "x")
    _forge(repo, "transition", "op-resume", "DESIGNING")
    _forge(repo, "transition", "op-resume", "BLOCKED", "--reason", "interrupted")

    shown = _forge(repo, "resume", "op-resume")
    assert shown.returncode == 0
    assert "DESIGNING" in shown.stdout

    moved = _forge(repo, "resume", "op-resume", "--move")
    assert moved.returncode == 0
    status = _forge(repo, "status", "op-resume")
    assert "DESIGNING" in status.stdout


def test_resume_refuses_a_finished_operation(repo: Path) -> None:
    _forge(repo, "start", "op-done", "--idea", "x")
    _forge(repo, "transition", "op-done", "REJECTED", "--reason", "not worth it")
    done = _forge(repo, "resume", "op-done")
    assert done.returncode == 2
    assert "does not restart" in done.stdout + done.stderr


def test_claim_refuses_an_overlap(repo: Path) -> None:
    _forge(repo, "start", "op-claim", "--idea", "x")
    first = _forge(repo, "claim", "op-claim", "builder_a", "src/phos/atlas/**")
    assert first.returncode == 0, first.stderr
    second = _forge(repo, "claim", "op-claim", "builder_b", "src/phos/atlas/engine.py")
    assert second.returncode == 2
    assert "overlaps" in second.stderr


def test_claim_refuses_the_state_file(repo: Path) -> None:
    _forge(repo, "start", "op-state", "--idea", "x")
    done = _forge(repo, "claim", "op-state", "builder_a", "docs/forge/state/**")
    assert done.returncode == 2


def test_an_agent_on_an_operation_that_is_not_working_is_refused(repo: Path) -> None:
    _forge(repo, "start", "op-early", "--idea", "x")
    done = _forge(
        repo, "agent", "op-early", "applied_scientist", "--task", "t", "--runtime", "codex"
    )
    assert done.returncode == 2
    assert "nowhere else" in done.stderr


def test_the_operation_file_is_readable_json(repo: Path) -> None:
    import json

    _forge(repo, "start", "op-json", "--idea", "a readable record")
    path = repo / "docs/forge/state/op-json.json"
    assert path.is_file()
    data = json.loads(path.read_text())
    assert data["state"] == "PLANNED"
    assert data["protocol"] == "forge-1"
    assert "verdict" not in data

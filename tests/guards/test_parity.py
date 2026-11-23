"""Both editors' real hook scripts reach the same verdict on the same tool call.

Mandate §14.4 asks that both environments enforce identical gates. Parity is a property of the
pair, so each test drives Claude Code's script with Claude Code's payload and Cursor's script with
Cursor's payload, then compares. Before ADR 0413 no hook in this repository had any test at all.

The scripts are run as subprocesses, which is how the editors run them: that exercises the
sys.path handling, the shebang-adjacent import of the shared package, and the response encoding,
none of which an in-process call would touch.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from tests.lab_only import CURSOR_HOOKS_ABSENT_REASON, skip_if_absent

#: This repository, where the real hook scripts live.
REPO = Path(__file__).resolve().parents[2]

Stage = Callable[[str], None]


def claude_hook(
    name: str, checkout: Path, payload: dict[str, Any], role: str = ""
) -> tuple[int, str]:
    """Run one Claude Code guard with Claude Code's payload; return its exit code and message."""
    env = {
        "CLAUDE_PROJECT_DIR": str(checkout),
        "PATH": "/usr/bin:/bin",
        "PYTHONPATH": str(REPO / "src"),
    }
    if role:
        env["PHOS_SWARM_ROLE"] = role
    done = subprocess.run(
        [sys.executable, str(REPO / ".claude" / "hooks" / f"{name}.py")],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    return done.returncode, done.stderr + done.stdout


def cursor_hook(checkout: Path, payload: dict[str, Any], role: str = "") -> dict[str, Any]:
    """Run the Cursor guards shim with Cursor's payload; return its parsed answer."""
    skip_if_absent(REPO / ".cursor" / "hooks" / "phos_guards.py", CURSOR_HOOKS_ABSENT_REASON)
    env = {"PATH": "/usr/bin:/bin", "PYTHONPATH": str(REPO / "src")}
    if role:
        env["PHOS_SWARM_ROLE"] = role
    done = subprocess.run(
        [sys.executable, str(REPO / ".cursor" / "hooks" / "phos_guards.py")],
        input=json.dumps({**payload, "workspace_roots": [str(checkout)]}),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    parsed: dict[str, Any] = json.loads(done.stdout)
    return parsed


def spoke(answer: dict[str, Any]) -> bool:
    """Return whether the Cursor shim reported an objection."""
    return bool(answer.get("user_message"))


class TestRedTierParity:
    def test_a_validation_corpus_is_reported_by_both(self, checkout: Path) -> None:
        code, message = claude_hook(
            "red_tier",
            checkout,
            {"tool_name": "Read", "tool_input": {"file_path": "data/hai-23.05/x.csv"}},
        )
        answer = cursor_hook(
            checkout, {"hook_event_name": "beforeReadFile", "file_path": "data/hai-23.05/x.csv"}
        )
        assert code == 0, "advisory in Claude Code"
        assert "hai-23.05" in message
        assert spoke(answer)
        assert "hai-23.05" in answer["user_message"]

    def test_the_development_corpus_passes_both_silently(self, checkout: Path) -> None:
        code, message = claude_hook(
            "red_tier",
            checkout,
            {"tool_name": "Read", "tool_input": {"file_path": "data/hai-20.07/x.csv"}},
        )
        answer = cursor_hook(
            checkout, {"hook_event_name": "beforeReadFile", "file_path": "data/hai-20.07/x.csv"}
        )
        assert code == 0 and "red tier" not in message
        assert not spoke(answer)

    def test_a_cursor_attachment_is_scanned_where_claude_sees_a_path(self, checkout: Path) -> None:
        # The shapes differ here: Cursor can attach files to a read. The guard sees both.
        answer = cursor_hook(
            checkout,
            {
                "hook_event_name": "beforeReadFile",
                "file_path": "notes.md",
                "attachments": [{"type": "file", "file_path": "data/batadal/x.csv"}],
            },
        )
        assert spoke(answer)
        assert "batadal" in answer["user_message"]

    def test_a_held_out_seed_in_a_shell_command_is_reported_by_both(self, checkout: Path) -> None:
        command = "uv run python scripts/x.py --seed 94005"
        code, message = claude_hook(
            "red_tier", checkout, {"tool_name": "Bash", "tool_input": {"command": command}}
        )
        answer = cursor_hook(
            checkout, {"hook_event_name": "beforeShellExecution", "command": command}
        )
        assert code == 0 and "94005" in message
        assert spoke(answer) and "94005" in answer["user_message"]


class TestFrozenLogParity:
    def test_an_append_is_reported_by_both(self, checkout: Path) -> None:
        command = "echo x >> eval_runs/log.jsonl"
        code, message = claude_hook(
            "frozen_log", checkout, {"tool_name": "Bash", "tool_input": {"command": command}}
        )
        answer = cursor_hook(
            checkout, {"hook_event_name": "beforeShellExecution", "command": command}
        )
        assert code == 0 and "frozen result log" in message
        assert spoke(answer) and "frozen result log" in answer["user_message"]

    def test_a_read_passes_both(self, checkout: Path) -> None:
        command = "tail -5 eval_runs/log.jsonl"
        code, message = claude_hook(
            "frozen_log", checkout, {"tool_name": "Bash", "tool_input": {"command": command}}
        )
        answer = cursor_hook(
            checkout, {"hook_event_name": "beforeShellExecution", "command": command}
        )
        assert code == 0 and "frozen result log" not in message
        assert not spoke(answer)


class TestFileScopeParity:
    def test_an_out_of_scope_edit_is_reported_by_both(self, checkout: Path) -> None:
        target = str(checkout / "src" / "phos" / "atlas" / "x.py")
        code, message = claude_hook(
            "file_scope",
            checkout,
            {"tool_name": "Write", "tool_input": {"file_path": target}},
            role="writer",
        )
        answer = cursor_hook(
            checkout,
            {
                "hook_event_name": "preToolUse",
                "tool_name": "Write",
                "tool_input": {"file_path": target},
            },
            role="writer",
        )
        assert code == 0 and "file scope" in message
        assert spoke(answer) and "file scope" in answer["user_message"]

    def test_with_no_role_set_both_stay_silent(self, checkout: Path) -> None:
        target = str(checkout / "src" / "phos" / "atlas" / "x.py")
        code, message = claude_hook(
            "file_scope", checkout, {"tool_name": "Write", "tool_input": {"file_path": target}}
        )
        answer = cursor_hook(
            checkout,
            {
                "hook_event_name": "preToolUse",
                "tool_name": "Write",
                "tool_input": {"file_path": target},
            },
        )
        assert code == 0 and "file scope" not in message
        assert not spoke(answer)


class TestPublicRecordParity:
    def test_an_advancing_commit_is_reported_by_both(self, checkout: Path, stage: Stage) -> None:
        stage("src/phos/atlas/new.py")
        command = "git commit -m 'feat: x'"
        code, message = claude_hook(
            "public_record", checkout, {"tool_name": "Bash", "tool_input": {"command": command}}
        )
        answer = cursor_hook(
            checkout, {"hook_event_name": "beforeShellExecution", "command": command}
        )
        assert code == 0 and "public record" in message
        assert spoke(answer) and "public record" in answer["user_message"]


class TestDeclaredBeforeHarnessParity:
    def test_an_undeclared_harness_run_is_reported_by_both(self, checkout: Path) -> None:
        command = "uv run python scripts/measure_thing.py"
        code, message = claude_hook(
            "declared_before_harness",
            checkout,
            {"tool_name": "Bash", "tool_input": {"command": command}},
        )
        answer = cursor_hook(
            checkout, {"hook_event_name": "beforeShellExecution", "command": command}
        )
        assert code == 0 and "nothing declared" in message
        assert spoke(answer) and "nothing declared" in answer["user_message"]


class TestCursorResponseSchema:
    """Cursor blocks on a response that does not match the event's schema, so the shape matters."""

    def test_beforereadfile_gets_no_agent_message(self, checkout: Path) -> None:
        # beforeReadFile accepts permission and user_message only. An extra field would be
        # off-schema, and Cursor documents that as blocking — every file read, on an advisory guard.
        answer = cursor_hook(
            checkout, {"hook_event_name": "beforeReadFile", "file_path": "data/hai-23.05/x.csv"}
        )
        assert spoke(answer)
        assert "agent_message" not in answer
        assert set(answer) <= {"permission", "user_message"}

    def test_pretooluse_may_carry_an_agent_message(self, checkout: Path) -> None:
        answer = cursor_hook(
            checkout,
            {
                "hook_event_name": "preToolUse",
                "tool_name": "Write",
                "tool_input": {"file_path": "eval_runs/log.jsonl"},
            },
        )
        assert spoke(answer)
        assert answer["agent_message"]

    @pytest.mark.parametrize(
        "event", ["beforeShellExecution", "preToolUse", "beforeReadFile", "unknownEvent"]
    )
    def test_every_event_gets_a_permission_and_never_a_crash(
        self, checkout: Path, event: str
    ) -> None:
        answer = cursor_hook(
            checkout, {"hook_event_name": event, "command": "ls", "file_path": "x"}
        )
        assert answer["permission"] == "allow"

    def test_a_malformed_payload_allows_rather_than_blocking(self, checkout: Path) -> None:
        skip_if_absent(REPO / ".cursor" / "hooks" / "phos_guards.py", CURSOR_HOOKS_ABSENT_REASON)
        done = subprocess.run(
            [sys.executable, str(REPO / ".cursor" / "hooks" / "phos_guards.py")],
            input='{"broken',
            capture_output=True,
            text=True,
            env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(REPO / "src")},
            check=False,
        )
        assert done.returncode == 0
        assert json.loads(done.stdout)["permission"] == "allow"

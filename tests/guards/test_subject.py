"""Both editors' payload shapes normalise to the same subject.

The field names asserted here are the ones Cursor publishes for its hook events and the ones
`.claude/hooks/_phos_guard.py` already read. They are asserted rather than assumed because
assuming a Cursor capability is what ADR 0413 had to correct.
"""

from __future__ import annotations

from pathlib import Path

from phos.guards.subject import (
    from_claude_code,
    from_cursor_read,
    from_cursor_shell,
    from_cursor_tool,
    read_event,
    repo_root_from,
)


class TestClaudeCode:
    def test_a_write_names_its_tool_and_its_path(self, tmp_path: Path) -> None:
        subject = from_claude_code(
            {"tool_name": "Write", "tool_input": {"file_path": "/a/b.py"}}, tmp_path
        )
        assert subject.tool == "Write"
        assert subject.paths == ("/a/b.py",)
        assert subject.writes is True
        assert subject.editor == "claude-code"

    def test_a_bash_call_names_its_command(self, tmp_path: Path) -> None:
        subject = from_claude_code(
            {"tool_name": "Bash", "tool_input": {"command": "ls -l"}}, tmp_path
        )
        assert subject.commands == ("ls -l",)
        assert subject.writes is False

    def test_an_empty_payload_is_an_empty_subject(self, tmp_path: Path) -> None:
        subject = from_claude_code({}, tmp_path)
        assert subject.tool == ""
        assert subject.texts == ()


class TestCursor:
    def test_pretooluse_carries_the_same_two_fields_as_claude_code(self, tmp_path: Path) -> None:
        payload = {"tool_name": "Write", "tool_input": {"file_path": "/a/b.py"}}
        cursor = from_cursor_tool(payload, tmp_path)
        claude = from_claude_code(payload, tmp_path)
        assert cursor.tool == claude.tool
        assert cursor.paths == claude.paths
        assert cursor.editor == "cursor"

    def test_beforeshellexecution_has_the_command_at_the_top_level(self, tmp_path: Path) -> None:
        subject = from_cursor_shell({"command": "uv run pytest", "cwd": "/x"}, tmp_path)
        assert subject.tool == "Shell"
        assert subject.commands == ("uv run pytest",)

    def test_beforereadfile_has_the_path_at_the_top_level(self, tmp_path: Path) -> None:
        subject = from_cursor_read({"file_path": "/a/b.py"}, tmp_path)
        assert subject.tool == "Read"
        assert subject.paths == ("/a/b.py",)

    def test_beforereadfile_attachments_are_scanned_too(self, tmp_path: Path) -> None:
        subject = from_cursor_read(
            {
                "file_path": "/a/b.py",
                "attachments": [
                    {"type": "file", "file_path": "/data/hai-23.05/x.csv"},
                    {"type": "rule", "file_path": "/r.mdc"},
                ],
            },
            tmp_path,
        )
        assert "/data/hai-23.05/x.csv" in subject.texts
        assert "/r.mdc" in subject.texts

    def test_workspace_roots_wins_over_the_fallback(self, tmp_path: Path) -> None:
        elsewhere = tmp_path / "elsewhere"
        subject = from_cursor_shell(
            {"command": "ls", "workspace_roots": [str(elsewhere)]}, tmp_path
        )
        assert subject.root == elsewhere

    def test_a_missing_workspace_roots_falls_back(self, tmp_path: Path) -> None:
        assert from_cursor_shell({"command": "ls"}, tmp_path).root == tmp_path

    def test_an_empty_workspace_roots_falls_back(self, tmp_path: Path) -> None:
        subject = from_cursor_shell({"command": "ls", "workspace_roots": []}, tmp_path)
        assert subject.root == tmp_path


class TestReadEvent:
    def test_nothing_on_stdin_is_an_empty_mapping(self) -> None:
        assert read_event("") == {}
        assert read_event("   ") == {}

    def test_broken_json_is_an_empty_mapping_rather_than_a_crash(self) -> None:
        assert read_event('{"command": "trunc') == {}

    def test_a_json_array_is_not_an_event(self) -> None:
        assert read_event("[1, 2]") == {}

    def test_an_object_comes_back(self) -> None:
        assert read_event('{"command": "ls"}') == {"command": "ls"}


class TestRepoRoot:
    def test_the_root_is_the_directory_holding_dot_git(self, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        nested = tmp_path / "a" / "b"
        nested.mkdir(parents=True)
        assert repo_root_from(nested) == tmp_path

    def test_without_a_git_entry_the_path_comes_back(self, tmp_path: Path) -> None:
        assert repo_root_from(tmp_path) == tmp_path

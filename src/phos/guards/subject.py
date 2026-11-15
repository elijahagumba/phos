"""What a tool call is about, normalised away from the editor that reported it.

The five PHOS guards each answer a question about a tool call: does it name red-tier data, does it
write the frozen log, is this edit inside the acting role's scope, is this commit an advancement
without its public record, is this harness run declared. None of those questions is about which
editor asked.

The editors disagree only on shape. Claude Code sends ``{"tool_name": ..., "tool_input": {...}}``.
Cursor sends ``{"tool_name": ..., "tool_input": {...}}`` for ``preToolUse``, ``{"command": ...}``
for ``beforeShellExecution`` and ``{"file_path": ..., "attachments": [...]}`` for
``beforeReadFile``, and documents ``workspace_roots`` on every event. So a `Subject` is built once
per editor, and every guard reads a `Subject`.

The field names here are taken from Cursor's published hook reference and from the payloads
``.claude/hooks/_phos_guard.py`` already reads, rather than guessed: guessing a Cursor capability
is exactly what ADR 0413 had to correct.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

#: Fields that have held a path or a path-like string in either editor.
_PATH_FIELDS: Final[tuple[str, ...]] = (
    "file_path",
    "path",
    "notebook_path",
    "pattern",
    "target_file",
)

#: Fields that have held a shell command.
_COMMAND_FIELDS: Final[tuple[str, ...]] = ("command",)

#: Tool names that write rather than read, across both editors.
WRITING_TOOLS: Final[tuple[str, ...]] = (
    "Write",
    "Edit",
    "MultiEdit",
    "NotebookEdit",
    "TabWrite",
)


@dataclass(frozen=True)
class GuardVerdict:
    """One guard's objection to a tool call.

    Attributes:
        rule: The rule file and the sentence in it that objects.
        headline: One line naming the problem.
        detail: The longer explanation, one line per entry.
        guard: Which guard objected, for the message and for the tests.
    """

    rule: str
    headline: str
    detail: tuple[str, ...]
    guard: str


@dataclass(frozen=True)
class Subject:
    """A tool call, as the guards need to see it.

    Attributes:
        tool: The tool name the editor reported, or an empty string.
        paths: Every path or path-like string the call mentions.
        commands: Every shell command the call would run.
        role: The swarm role this session is acting as, from ``PHOS_SWARM_ROLE``.
        root: The repository root the call is happening in.
        editor: ``claude-code`` or ``cursor``, for the message only. No guard branches on it.
    """

    tool: str
    paths: tuple[str, ...]
    commands: tuple[str, ...]
    role: str
    root: Path
    editor: str
    attachments: tuple[str, ...] = field(default=())

    @property
    def texts(self) -> tuple[str, ...]:
        """Return every string a guard should scan: paths, commands and attachment paths."""
        return (*self.paths, *self.commands, *self.attachments)

    @property
    def writes(self) -> bool:
        """Return whether the tool itself is a writing tool."""
        return self.tool in WRITING_TOOLS


def _strings(value: object, names: tuple[str, ...]) -> list[str]:
    """Return the non-empty string values of ``names`` in ``value`` when it is a mapping."""
    if not isinstance(value, dict):
        return []
    found = []
    for name in names:
        item = value.get(name)
        if isinstance(item, str) and item.strip():
            found.append(item)
    return found


def workspace_root(payload: dict[str, Any], fallback: Path) -> Path:
    """Return the workspace root Cursor reported, else ``fallback``.

    Args:
        payload: The hook payload.
        fallback: Used when the payload names no workspace.

    Returns:
        The first entry of ``workspace_roots`` when it is a non-empty list of strings.
    """
    roots = payload.get("workspace_roots")
    if isinstance(roots, list):
        for entry in roots:
            if isinstance(entry, str) and entry.strip():
                return Path(entry)
    return fallback


def from_claude_code(payload: dict[str, Any], root: Path, role: str = "") -> Subject:
    """Return the subject of a Claude Code ``PreToolUse`` event.

    Args:
        payload: The event, as Claude Code writes it to stdin.
        root: The repository root.
        role: The acting swarm role, if any.

    Returns:
        The normalised subject.
    """
    fields = payload.get("tool_input")
    extra = _strings(fields, ("prompt",))
    return Subject(
        tool=str(payload.get("tool_name") or ""),
        paths=tuple(_strings(fields, _PATH_FIELDS)),
        commands=tuple(_strings(fields, _COMMAND_FIELDS) + extra),
        role=role,
        root=root,
        editor="claude-code",
    )


def from_cursor_tool(payload: dict[str, Any], fallback: Path, role: str = "") -> Subject:
    """Return the subject of a Cursor ``preToolUse`` event.

    Cursor's ``preToolUse`` carries ``tool_name`` and ``tool_input``, the same two fields Claude
    Code uses, which is why one normaliser serves both.

    Args:
        payload: The event, as Cursor writes it to stdin.
        fallback: The root to use when the payload names no workspace.
        role: The acting swarm role, if any.

    Returns:
        The normalised subject.
    """
    fields = payload.get("tool_input")
    return Subject(
        tool=str(payload.get("tool_name") or ""),
        paths=tuple(_strings(fields, _PATH_FIELDS)),
        commands=tuple(_strings(fields, _COMMAND_FIELDS)),
        role=role,
        root=workspace_root(payload, fallback),
        editor="cursor",
    )


def from_cursor_shell(payload: dict[str, Any], fallback: Path, role: str = "") -> Subject:
    """Return the subject of a Cursor ``beforeShellExecution`` event.

    Args:
        payload: The event. ``command`` is at the top level, not inside ``tool_input``.
        fallback: The root to use when the payload names no workspace.
        role: The acting swarm role, if any.

    Returns:
        The normalised subject, with ``tool`` set to ``Shell``.
    """
    command = payload.get("command")
    return Subject(
        tool="Shell",
        paths=(),
        commands=(command,) if isinstance(command, str) and command.strip() else (),
        role=role,
        root=workspace_root(payload, fallback),
        editor="cursor",
    )


def from_cursor_read(payload: dict[str, Any], fallback: Path, role: str = "") -> Subject:
    """Return the subject of a Cursor ``beforeReadFile`` event.

    Args:
        payload: The event. ``file_path`` is at the top level, and ``attachments`` is a list of
            objects each carrying their own ``file_path``.
        fallback: The root to use when the payload names no workspace.
        role: The acting swarm role, if any.

    Returns:
        The normalised subject, with ``tool`` set to ``Read``.
    """
    attachments: list[str] = []
    entries = payload.get("attachments")
    if isinstance(entries, list):
        for entry in entries:
            if isinstance(entry, dict):
                attachments += _strings(entry, ("file_path",))
    return Subject(
        tool="Read",
        paths=tuple(_strings(payload, _PATH_FIELDS)),
        commands=(),
        role=role,
        root=workspace_root(payload, fallback),
        editor="cursor",
        attachments=tuple(attachments),
    )


def read_event(stream: str) -> dict[str, Any]:
    """Return the hook payload parsed from ``stream``, or an empty mapping.

    Args:
        stream: The raw stdin text.

    Returns:
        The decoded object, or ``{}`` when it is absent or not an object.
    """
    text = stream.strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def repo_root_from(path: Path) -> Path:
    """Return the checkout root containing ``path``, by walking up to the ``.git`` entry.

    Args:
        path: Any path inside the checkout.

    Returns:
        The directory holding ``.git``, or ``path`` when none is found.
    """
    for candidate in (path, *path.parents):
        if (candidate / ".git").exists():
            return candidate
    return path

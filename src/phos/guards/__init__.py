"""The PHOS guards, as functions rather than as scripts inside one editor.

ADR 0413 found that the gate was enforced in Claude Code and not in Cursor, because the decision
lived inside a Claude Code hook. These five were in the same position. The decision now lives
here, typed and tested, and each editor keeps a shim that translates its own payload shape.

``run_all`` is the order the guards speak in, and it is the order the Claude Code
``.claude/settings.json`` already ran them in.
"""

from __future__ import annotations

from collections.abc import Callable

from phos.guards import checks, tiers
from phos.guards.subject import (
    GuardVerdict,
    Subject,
    from_claude_code,
    from_cursor_read,
    from_cursor_shell,
    from_cursor_tool,
    read_event,
    repo_root_from,
    workspace_root,
)

#: Every guard, in the order they are consulted. The first objection is the one reported, so the
#: order is the priority: data tiers before anything else, because a red-tier read cannot be
#: undone by a later apology.
ALL: tuple[tuple[str, Callable[[Subject], GuardVerdict | None]], ...] = (
    ("red_tier", tiers.check),
    ("frozen_log", checks.frozen_log),
    ("file_scope", checks.file_scope),
    ("public_record", checks.public_record),
    ("declared_before_harness", checks.declared_before_harness),
)

__all__ = [
    "ALL",
    "GuardVerdict",
    "Subject",
    "from_claude_code",
    "from_cursor_read",
    "from_cursor_shell",
    "from_cursor_tool",
    "read_event",
    "repo_root_from",
    "run_all",
    "workspace_root",
]


def run_all(subject: Subject) -> list[GuardVerdict]:
    """Return every guard's objection to ``subject``, in the order they are consulted.

    Args:
        subject: The normalised tool call.

    Returns:
        One verdict per objecting guard; empty when none objects.
    """
    found = []
    for _name, guard in ALL:
        verdict = guard(subject)
        if verdict is not None:
            found.append(verdict)
    return found

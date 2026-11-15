"""The other four PHOS guards, as functions of a `Subject`.

Each was a Claude Code hook script and is now a function, for the reason ADR 0413 gives: a guard
that lives inside one editor protects half the work, and a guard whose logic lives in two editors
drifts. The hooks that remain are shims.

Behaviour is lifted unchanged from ``.claude/hooks/frozen_log.py``, ``file_scope.py``,
``public_record.py`` and ``declared_before_harness.py``. Where a guard reached for git or the
environment, that reach is now an argument, which is what makes it testable.
"""

from __future__ import annotations

import fnmatch
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Final

from phos.guards.subject import GuardVerdict, Subject

LOG_PATH: Final = "eval_runs/log.jsonl"

#: Shell shapes that write the log rather than read it: a redirection, a mover, a truncation.
_WRITING_SHELL: Final = re.compile(
    r">>?\s*\S*log\.jsonl"
    r"|\b(?:tee|sed\s+-i|truncate|rm|mv|cp|dd|sponge)\b[^|;&]*log\.jsonl"
    r"|log\.jsonl[^|;&]*\b(?:>>?|\|\s*tee)\b"
)

#: The three public surfaces ADR 0044 requires an advancement to move.
SURFACES: Final = ("encyclopedia/", "easy to reads/", "README.md")
#: What counts as an advancement when it is staged.
ADVANCING: Final = ("docs/adr/", "src/", "scripts/", "eval_runs/")
_COMMIT: Final = re.compile(r"\bgit\b[^|;&]*\bcommit\b")

#: The harness entry points the cycle's phase 2 allows.
_HARNESS: Final = re.compile(r"scripts/(?:measure_|evaluate_|lane_)[\w./-]*\.py|scripts/gate\.py")
_ADR_FILE: Final = re.compile(r"^(\d{4})-(.+)\.md$")
_DECLARATION: Final = re.compile(
    r"(?:is|are)\s+declared(?:\s+(?:on|for|before|in|against)\b.*)?$"
    r"|(?<!not\s)\bdeclared$"
    r"|(?<!not\s)\bdeclarations?$",
    re.IGNORECASE,
)


def git(root: Path, *args: str) -> str:
    """Return the stripped stdout of a git command run in ``root``, or an empty string."""
    try:
        done = subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, text=True, check=False
        )
    except OSError:
        return ""
    return done.stdout.strip() if done.returncode == 0 else ""


def roadmap(root: Path) -> dict[str, Any]:
    """Return the programme tracker, or an empty mapping when it cannot be read."""
    path = root / ".phos_roadmap_state.json"
    if not path.is_file():
        return {}
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


# -- frozen result log ---------------------------------------------------------------------


def frozen_sentence(rule_text: str) -> str:
    """Return the sentence in the tier rule that freezes the log, or a pointer to the file."""
    for line in rule_text.splitlines():
        if "log.jsonl" in line:
            return line.strip().lstrip("-* ")
    return "docs/rules/data-tiers.md names eval_runs/log.jsonl as frozen"


def writes_the_log(subject: Subject) -> str:
    """Return a description of the write, or an empty string when nothing writes the log.

    Args:
        subject: The normalised tool call.

    Returns:
        What is writing, for the message.
    """
    for target in subject.paths:
        if subject.writes and target.replace("\\", "/").endswith(LOG_PATH):
            return f"{subject.tool} on {target}"
    for command in subject.commands:
        if _WRITING_SHELL.search(command):
            return f"shell command writing {LOG_PATH}"
    return ""


def frozen_log(subject: Subject) -> GuardVerdict | None:
    """Return a verdict when the frozen result log is about to be written.

    Args:
        subject: The normalised tool call.

    Returns:
        The verdict, or ``None``. Reading the log is fine; only writes are seen.
    """
    what = writes_the_log(subject)
    if not what:
        return None
    from phos.guards.tiers import read_rule

    sentence = frozen_sentence(read_rule(subject.root, "data-tiers.md"))
    return GuardVerdict(
        rule=f"docs/rules/data-tiers.md — {sentence}",
        headline=f"a write to the frozen result log ({what})",
        detail=(
            f"{LOG_PATH} is frozen: rows are never appended, and an existing row is never edited",
            "a new measurement gets a new result name and its own report under eval_runs/",
            "reading the file is fine; this guard only sees writes",
        ),
        guard="frozen_log",
    )


# -- swarm file scope ----------------------------------------------------------------------


def role_scope(root: Path, name: str) -> tuple[dict[str, Any] | None, list[str]]:
    """Return the ``swarm`` entry for ``name`` and its file scope."""
    entries = roadmap(root).get("swarm")
    if not isinstance(entries, list):
        return None, []
    for entry in entries:
        if isinstance(entry, dict) and str(entry.get("role", "")) == name:
            scope = entry.get("file_scope")
            return entry, [str(item) for item in scope] if isinstance(scope, list) else []
    return None, []


def in_scope(relative: str, scope: list[str]) -> bool:
    """Return whether ``relative`` is inside ``scope``, treating a trailing ``/`` as a tree."""
    for pattern in scope:
        if pattern.endswith("/"):
            if relative.startswith(pattern):
                return True
            continue
        if fnmatch.fnmatch(relative, pattern) or fnmatch.fnmatch(relative, f"{pattern}/*"):
            return True
    return False


def file_scope(subject: Subject) -> GuardVerdict | None:
    """Return a verdict when the acting role edits a file its scope does not name.

    Args:
        subject: The normalised tool call. With no role set the guard says nothing, because an
            unset role is not an out-of-scope role.

    Returns:
        The verdict, or ``None``.
    """
    if not subject.role or not subject.paths:
        return None
    target = subject.paths[0]
    entry, scope = role_scope(subject.root, subject.role)
    if entry is None:
        return GuardVerdict(
            rule=".phos_roadmap_state.json — swarm[].role",
            headline=f"PHOS_SWARM_ROLE is {subject.role!r}, which no swarm role matches",
            detail=("the tracker's swarm roster is the list of roles that may be dispatched",),
            guard="file_scope",
        )
    if not scope:
        return None
    try:
        relative = str(Path(target).resolve().relative_to(subject.root.resolve()))
    except ValueError:
        relative = target
    if in_scope(relative, scope):
        return None
    return GuardVerdict(
        rule=f".phos_roadmap_state.json — swarm[].file_scope for role {subject.role}",
        headline=f"an edit outside {subject.role}'s file scope",
        detail=(
            f"editing: {relative}",
            f"scope: {', '.join(scope)}",
            "two roles never share a file; take the edit to the role that owns it",
        ),
        guard="file_scope",
    )


# -- public record on main -----------------------------------------------------------------


def public_record(subject: Subject) -> GuardVerdict | None:
    """Return a verdict when an advancing commit carries none of the three surfaces.

    Args:
        subject: The normalised tool call.

    Returns:
        The verdict, or ``None`` when this is not a commit, or nothing advancing is staged, or
        all three surfaces move with it.
    """
    if not any(_COMMIT.search(command) for command in subject.commands):
        return None
    paths = [
        line.strip()
        for line in git(subject.root, "diff", "--cached", "--name-only").splitlines()
        if line.strip()
    ]
    advancing = [path for path in paths if path.startswith(ADVANCING)]
    if not advancing:
        return None
    moved = [surface for surface in SURFACES if any(path.startswith(surface) for path in paths)]
    if len(moved) == len(SURFACES):
        return None
    branch = git(subject.root, "branch", "--show-current") or "(detached)"
    on_main = branch == "main"
    missing = [surface for surface in SURFACES if surface not in moved]
    return GuardVerdict(
        rule="docs/rules/docs-on-main.md — ADR 0044, the three surfaces move with the advancement",
        headline=(
            "an advancing commit on main without its public record"
            if on_main
            else f"an advancing commit on {branch}; the public record falls due at the merge"
        ),
        detail=(
            f"staged advancement: {', '.join(advancing[:6])}",
            f"not staged: {', '.join(missing)}",
            "PROGRESS.md and docs/adr/ are required separately and do not replace the three",
            (
                "do not merge to main while any of the three is stale"
                if on_main
                else "the merge into main is where the three catch up"
            ),
        ),
        guard="public_record",
    )


# -- a harness run with nothing declared ---------------------------------------------------


def declarations_on_branch(root: Path) -> list[str]:
    """Return the declaration ADRs added on this branch and not on ``main``."""
    names = git(root, "log", "main..HEAD", "--name-only", "--pretty=format:", "--", "docs/adr")
    found: list[str] = []
    for line in names.splitlines():
        match = _ADR_FILE.match(Path(line.strip()).name) if line.strip() else None
        slug = match.group(2).replace("-", " ") if match else ""
        if match is None or not _DECLARATION.search(slug):
            continue
        found.append(f"ADR {match.group(1)} — {slug}")
    return sorted(set(found))


def declared_before_harness(subject: Subject) -> GuardVerdict | None:
    """Return a verdict when a harness is about to run with no declaration ADR committed.

    What counts as a declaration here is a heuristic and is stated as one: an ADR added on this
    branch but not on ``main`` whose title reads as a declaration. The ADRs carry no
    machine-readable kind, which is the whole reason GENESIS exists — ``genesis gate`` answers the
    same question exactly, from the record, and this guard remains as the older, looser net.

    Args:
        subject: The normalised tool call.

    Returns:
        The verdict, or ``None``.
    """
    scripts = sorted({found for text in subject.texts for found in _HARNESS.findall(text)})
    if not scripts or declarations_on_branch(subject.root):
        return None
    detail = [
        f"about to run: {', '.join(scripts)}",
        f"branch: {git(subject.root, 'branch', '--show-current') or '(detached)'}",
        "no ADR on main..HEAD whose title reads as a declaration",
    ]
    if git(subject.root, "status", "--porcelain", "--", "docs/adr"):
        detail.append("docs/adr/ has uncommitted changes — a declaration must be committed first")
    return GuardVerdict(
        rule="docs/rules/data-tiers.md — score once, only after a committed declaration",
        headline="a harness run with nothing declared",
        detail=tuple(detail),
        guard="declared_before_harness",
    )

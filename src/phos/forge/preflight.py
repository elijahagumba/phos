"""Preflight: the checks a FORGE operation must pass before the conductor will size a team.

Four checks, and every one of them is a thing that has actually gone wrong in this repository:

1. **A clean main.** The main checkout has staged and unstaged work in it right now that predates
   FORGE. A commit made with ``git add -A`` would sweep somebody else's half-finished experiment
   under a FORGE message. A dirty tree is refused rather than committed around.
2. **No clashing worktrees.** Thirteen worktrees exist, three of them under ``.claude/worktrees``.
   A goal that wants a worktree already claimed by another operation would give two agents one
   checkout, which is the one thing the worktree rule exists to prevent.
3. **Number allocation.** A declaration, a finding and a question are numbered in one sequence each,
   and two operations allocating the same number is a collision the store cannot repair later. The
   next free number is computed from the record, not guessed.
4. **Gates present.** The Genesis gate must be able to answer for this checkout, and the tier rule
   must be readable. A checkout where the gate cannot load has neither the declare-before-run rule
   nor the tier fence, and nothing FORGE does is safe there.

Each returns a :class:`Check`, and :func:`run` collects them. A single failure stops the operation
before a worktree is made, because a half-created operation is harder to reason about than one that
never started.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from phos.forge.gates import ALLOWED_REMOTE

#: Where declarations, questions and findings live.
GENESIS = Path("docs/genesis")

#: The rule files a checkout must carry for the gates to mean anything.
REQUIRED_RULES: Final[tuple[str, ...]] = (
    "docs/rules/data-tiers.md",
    "docs/rules/phos-execution-master.md",
)

#: The hook configuration Cursor and Claude Code read. A checkout without them has no guards.
REQUIRED_HOOKS: Final[tuple[str, ...]] = (
    ".claude/settings.json",
    ".cursor/hooks.json",
)

#: The prefix each record kind uses, and the directory it lives in.
_SEQUENCES: Final[dict[str, str]] = {
    "experiments": "E",
    "questions": "Q",
    "findings": "F",
}


@dataclass(frozen=True)
class Check:
    """One preflight check.

    Attributes:
        name: Which check.
        passed: Whether it passed.
        detail: Why, in a sentence a human can act on.
        blocking: Whether a failure stops the operation. Every check here is blocking; the field
            exists so a future non-blocking advisory can be added without reshaping the result.
    """

    name: str
    passed: bool
    detail: str
    blocking: bool = True


@dataclass(frozen=True)
class Preflight:
    """The whole preflight result.

    Attributes:
        checks: One entry per check, in the order they ran.
    """

    checks: tuple[Check, ...] = field(default=())

    @property
    def passed(self) -> bool:
        """Return whether every blocking check passed."""
        return all(check.passed for check in self.checks if check.blocking)

    @property
    def failures(self) -> tuple[Check, ...]:
        """Return the blocking checks that failed."""
        return tuple(check for check in self.checks if check.blocking and not check.passed)

    def summary(self) -> str:
        """Return a one-line verdict."""
        if self.passed:
            return f"preflight passed ({len(self.checks)} checks)"
        named = ", ".join(check.name for check in self.failures)
        return f"preflight REFUSED: {named}"

    def report(self) -> str:
        """Return a multi-line report for a human.

        Returns:
            One line per check, with a pass or a refusal and the reason.
        """
        lines = []
        for check in self.checks:
            state = "ok  " if check.passed else "STOP"
            lines.append(f"  [{state}] {check.name}: {check.detail}")
        lines.append(f"  {self.summary()}")
        return "\n".join(lines)


def _git(root: Path, *args: str) -> tuple[int, str, str]:
    """Run one git command in ``root``.

    Args:
        root: The repository root.
        *args: The git arguments.

    Returns:
        ``(returncode, stdout, stderr)``, stripped.
    """
    try:
        done = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as error:
        return 127, "", str(error)
    return done.returncode, done.stdout.strip(), done.stderr.strip()


def check_clean_main(root: Path) -> Check:
    """Check that the main checkout has nothing staged or unstaged.

    A staged change is worse than an unstaged one, because the next ``git commit`` will take it
    whether or not the committer meant to. Both are refused.

    Args:
        root: The repository root.

    Returns:
        The check.
    """
    code, out, err = _git(root, "status", "--porcelain")
    if code != 0:
        return Check("clean main", False, f"git status failed: {err or out}")
    if not out:
        return Check("clean main", True, "the working tree is clean")

    lines = out.splitlines()
    staged = [line for line in lines if line[:2].strip() and line[0] not in {" ", "?"}]
    untracked = [line for line in lines if line.startswith("??")]
    detail = (
        f"{len(staged)} staged and {len(untracked)} untracked paths are in the checkout. "
        "A FORGE commit uses explicit paths so it cannot sweep them up, but a preflight refuses "
        "to start from a tree whose owner has not said what is in it."
    )
    if staged:
        detail += " Staged: " + ", ".join(line[3:] for line in staged[:5])
    return Check("clean main", False, detail)


def check_no_clashing_worktrees(root: Path, wanted: tuple[str, ...] = ()) -> Check:
    """Check that no worktree this operation would want is already claimed.

    Args:
        root: The repository root.
        wanted: Operation ids or role names the goal would need worktrees for.

    Returns:
        The check.
    """
    code, out, err = _git(root, "worktree", "list", "--porcelain")
    if code != 0:
        return Check("no clashing worktrees", False, f"git worktree list failed: {err or out}")

    existing = [
        line.removeprefix("worktree ")
        for line in out.splitlines()
        if line.startswith("worktree ")
    ]
    if not wanted:
        return Check(
            "no clashing worktrees",
            True,
            f"{len(existing)} worktrees exist and none were requested by name",
        )

    clashing = [
        path
        for path in existing
        for name in wanted
        if f"/{name}/" in path or path.endswith(f"/{name}")
    ]
    if clashing:
        return Check(
            "no clashing worktrees",
            False,
            "a worktree this operation would need is already there: " + ", ".join(clashing[:5]),
        )
    return Check("no clashing worktrees", True, f"none of the {len(wanted)} wanted paths exist")


def next_numbers(root: Path) -> dict[str, int]:
    """Return the next free number for each record kind.

    The number is the highest existing id plus one, computed from the files rather than from a
    counter, because a counter can fall behind a hand-written record and a number collision cannot
    be repaired afterwards.

    Args:
        root: The repository root.

    Returns:
        Kind to the next free integer. A kind with no records starts at 1.
    """
    found: dict[str, int] = {}
    for kind, prefix in _SEQUENCES.items():
        directory = root / GENESIS / kind
        highest = 0
        if directory.is_dir():
            pattern = re.compile(rf"^{prefix}-(\d{{4}})\.json$")
            for path in directory.glob(f"{prefix}-*.json"):
                match = pattern.match(path.name)
                if match:
                    highest = max(highest, int(match.group(1)))
        found[kind] = highest + 1
    return found


def check_number_allocation(root: Path) -> Check:
    """Check that the next number for each kind is free on disk.

    Args:
        root: The repository root.

    Returns:
        The check. The detail names the next number for each kind, so a caller can print it.
    """
    numbers = next_numbers(root)
    if not numbers:
        return Check("number allocation", False, "no record kinds were found to number")
    clashes = []
    for kind, prefix in _SEQUENCES.items():
        candidate = root / GENESIS / kind / f"{prefix}-{numbers[kind]:04d}.json"
        if candidate.exists():
            clashes.append(candidate.as_posix())
    if clashes:
        return Check(
            "number allocation",
            False,
            "a next number is already taken: " + ", ".join(clashes),
        )
    named = ", ".join(f"{_SEQUENCES[kind]}-{number:04d}" for kind, number in numbers.items())
    return Check("number allocation", True, f"the next free numbers are {named}")


def check_gates_present(root: Path) -> Check:
    """Check that the gate and the tier rule can be loaded in this checkout.

    The question is not whether the files exist but whether the code that reads them works, so this
    asks the gate a harmless question and the resolver a real one. A checkout whose gate cannot
    answer has no declare-before-run rule and no tier fence, and nothing FORGE does there is safe.

    Args:
        root: The repository root.

    Returns:
        The check.
    """
    from phos.forge.genesis_api import gate, tier

    missing = [relative for relative in REQUIRED_RULES if not (root / relative).is_file()]
    if missing:
        return Check("gates present", False, "the rule files are missing: " + ", ".join(missing))

    try:
        decision = gate(root, "uv run python scripts/lane_probe.py --corpus data/synth")
    except Exception as error:  # the gate failing to load is the thing being checked
        return Check("gates present", False, f"the gate could not be asked: {error}")

    try:
        verdict = tier(root, "synth", "iterate")
    except Exception as error:  # a resolver that cannot read the rule is the same failure
        return Check("gates present", False, f"the tier resolver could not answer: {error}")

    detail = (
        "the gate answered "
        + ("with a decision" if decision is not None else "that this is not a harness command")
        + f", and the tier resolver read the rule ({verdict.tier or 'unknown'})"
    )
    return Check("gates present", True, detail)


def check_hooks_present(root: Path) -> Check:
    """Check that the editor hook configuration is in this checkout.

    This is the check behind "/forge must refuse from a checkout where the hooks are not loaded".
    ADR 0417 and ADR 0419 are the reason it is a refusal rather than a warning: Cursor reads project
    hooks from the **workspace root**, so a window opened on a parent directory loads none of them
    and nothing inside the repository can detect it. What can be detected is the case where the
    hook files are absent from the checkout entirely, and that is what this checks.

    Args:
        root: The repository root.

    Returns:
        The check.
    """
    missing = [relative for relative in REQUIRED_HOOKS if not (root / relative).is_file()]
    if missing:
        return Check(
            "hooks present",
            False,
            "the hook configuration is not in this checkout: "
            + ", ".join(missing)
            + ". Without it neither editor loads a guard, and FORGE refuses to run where its "
            "gates are the only thing standing between an agent and a red corpus.",
        )

    unreadable: list[str] = []
    for relative in REQUIRED_HOOKS:
        try:
            json.loads((root / relative).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            unreadable.append(relative)
    if unreadable:
        return Check(
            "hooks present",
            False,
            "the hook configuration will not parse: " + ", ".join(unreadable),
        )
    return Check("hooks present", True, "both editors have a hook configuration that parses")


def check_remote(root: Path) -> Check:
    """Check that a push target is the PHOS Labs remote.

    Args:
        root: The repository root.

    Returns:
        The check. A missing remote is not a refusal to work, only to land, so the detail says so.
    """
    code, out, _ = _git(root, "remote", "-v")
    if code != 0 or not out:
        return Check("remote", False, "no remote is configured, so nothing could be pushed")
    urls = {line.split()[1] for line in out.splitlines() if len(line.split()) > 1}
    allowed = [url for url in urls if ALLOWED_REMOTE in url]
    if not allowed:
        return Check(
            "remote",
            False,
            f"no remote points at {ALLOWED_REMOTE}. Configured: " + ", ".join(sorted(urls)),
        )
    return Check("remote", True, f"{allowed[0]} is the PHOS Labs remote")


def run(root: Path, wanted: tuple[str, ...] = ()) -> Preflight:
    """Run every check, in the order the specification lists them.

    Args:
        root: The repository root.
        wanted: Operation ids or role names the goal's worktrees would need.

    Returns:
        The preflight result. It carries every check, not only the first failure, so a human sees
        all of what is wrong rather than fixing one thing at a time.
    """
    return Preflight(
        checks=(
            check_clean_main(root),
            check_no_clashing_worktrees(root, wanted),
            check_number_allocation(root),
            check_gates_present(root),
            check_hooks_present(root),
            check_remote(root),
        )
    )

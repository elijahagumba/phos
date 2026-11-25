"""One git worktree per agent, outside the main checkout.

The isolation is the safety property, not a convenience. A role that works in the main checkout can
edit a frozen file, a rule, or another role's work without noticing. A role in its own worktree can
only reach what its branch carries, and the main checkout is untouched by anything it does.

Two rules are enforced rather than described:

* **Outside the main checkout.** A worktree inside the repository would be picked up by every tool
  that walks the tree, and ``git status`` in the main checkout would see it. The path is checked
  against the repository root and refused if it is inside.
* **Never on ``main``.** The branch is checked by :func:`phos.forge.gates.require_not_main`, so a
  worktree on ``main`` cannot be created by this module at all.

The default location is a sibling directory, ``<parent>/<repo>-forge/<operation>/<role>``, which is
where the existing PHOS worktrees already live (``../phos-witness2``, ``../phos-method-week-NN-a``).
FORGE does not use ``.claude/worktrees``: that is Claude Code's own directory, and putting FORGE
worktrees there would make two tools own one path.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from phos.forge.gates import GateOutcome, require_not_main

#: The directory FORGE puts worktrees in, beside the repository rather than inside it.
WORKTREE_PARENT: Final = "forge"


class WorktreeError(RuntimeError):
    """A worktree could not be created, or would have broken one of the two rules."""


@dataclass(frozen=True)
class Worktree:
    """One role's checkout.

    Attributes:
        path: Absolute path to the worktree.
        branch: The branch checked out in it.
        base_commit: The commit it was created from.
        role: The role that owns it.
    """

    path: Path
    branch: str
    base_commit: str
    role: str


def _git(root: Path, *args: str) -> tuple[int, str, str]:
    """Run one git command in ``root``.

    Args:
        root: The repository root.
        *args: The git arguments.

    Returns:
        ``(returncode, stdout, stderr)``, both streams stripped.
    """
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def default_path(root: Path, operation: str, role: str) -> Path:
    """Return where one role's worktree goes by default.

    Args:
        root: The repository root.
        operation: The operation id.
        role: The role name.

    Returns:
        ``<parent>/<repo>-forge/<operation>/<role>``, resolved.
    """
    root = root.resolve()
    return (root.parent / f"{root.name}-{WORKTREE_PARENT}" / operation / role).resolve()


def is_outside_checkout(root: Path, candidate: Path) -> bool:
    """Return whether ``candidate`` lies outside the repository root.

    Args:
        root: The repository root.
        candidate: The worktree path.

    Returns:
        True when the path is not inside the repository.
    """
    root = root.resolve()
    try:
        candidate.resolve().relative_to(root)
    except ValueError:
        return True
    return False


def head_commit(root: Path, ref: str = "HEAD") -> str:
    """Return the full commit a ref points at.

    Args:
        root: The repository root.
        ref: The ref, ``HEAD`` by default.

    Returns:
        The full SHA.

    Raises:
        WorktreeError: If the ref does not resolve.
    """
    code, out, err = _git(root, "rev-parse", "--verify", f"{ref}^{{commit}}")
    if code != 0:
        raise WorktreeError(f"{ref} does not resolve in {root}: {err or out}")
    return out


def branch_exists(root: Path, branch: str) -> bool:
    """Return whether a branch exists.

    Args:
        root: The repository root.
        branch: The branch name.

    Returns:
        True when the branch resolves.
    """
    code, _, _ = _git(root, "rev-parse", "--verify", f"refs/heads/{branch}")
    return code == 0


def create(
    root: Path,
    *,
    operation: str,
    role: str,
    branch: str,
    base: str = "HEAD",
    path: Path | None = None,
) -> Worktree:
    """Create one role's worktree and branch.

    Args:
        root: The repository root.
        operation: The operation id.
        role: The role name.
        branch: The branch to create. Must not be ``main`` or ``master``.
        base: The commit or ref to branch from.
        path: Where to put it. Defaults to :func:`default_path`.

    Returns:
        The worktree.

    Raises:
        WorktreeError: If the branch is protected, the path is inside the checkout, the path
            already exists, or git refuses.
    """
    guarded: GateOutcome = require_not_main(branch)
    if not guarded.passed:
        raise WorktreeError(guarded.detail)

    target = (path or default_path(root, operation, role)).resolve()
    if not is_outside_checkout(root, target):
        raise WorktreeError(
            f"{target} is inside {root}. A worktree inside the checkout is walked by every tool "
            "that walks the tree and appears in the main checkout's status, so it is refused."
        )
    if target.exists():
        raise WorktreeError(f"{target} already exists; removing it would discard work")
    if branch_exists(root, branch):
        raise WorktreeError(
            f"branch {branch} already exists. A role gets a fresh branch, so an existing one is "
            "either an interrupted operation to resume or somebody else's work."
        )

    base_commit = head_commit(root, base)
    target.parent.mkdir(parents=True, exist_ok=True)
    code, out, err = _git(root, "worktree", "add", "-b", branch, str(target), base_commit)
    if code != 0:
        raise WorktreeError(f"git worktree add failed: {err or out}")
    return Worktree(path=target, branch=branch, base_commit=base_commit, role=role)


def changed_files(worktree: Worktree, base: str | None = None) -> tuple[str, ...]:
    """Return the files a role changed, relative to the repository root.

    Both tracked modifications and untracked files count: an agent that writes a new file has
    changed the tree as much as one that edits an existing file.

    Args:
        worktree: The worktree to inspect.
        base: The commit to compare against. Defaults to the worktree's own base.

    Returns:
        The paths, sorted.
    """
    against = base or worktree.base_commit
    code, out, _ = _git(worktree.path, "diff", "--name-only", against)
    if code != 0:
        return ()
    code, untracked, _ = _git(worktree.path, "ls-files", "--others", "--exclude-standard")
    found = set(out.splitlines()) if out else set()
    if code == 0 and untracked:
        found |= set(untracked.splitlines())
    return tuple(sorted(path for path in found if path))


def detect_file_conflicts(
    worktrees: list[Worktree], base: str | None = None
) -> dict[str, tuple[str, ...]]:
    """Return the files more than one role changed.

    Two agents can hold non-overlapping declared scopes and still edit the same file. This is the
    check that catches it, after they stop rather than before they start.

    Args:
        worktrees: The worktrees to compare.
        base: The common commit. Defaults to each worktree's own base, which is right when they
            were all branched from the same place.

    Returns:
        Path to the roles that changed it, for every path changed more than once. Empty when there
        is no conflict.
    """
    seen: dict[str, list[str]] = {}
    for worktree in worktrees:
        for path in changed_files(worktree, base):
            seen.setdefault(path, []).append(worktree.role)
    return {path: tuple(roles) for path, roles in sorted(seen.items()) if len(roles) > 1}


def remove(worktree: Worktree, *, force: bool = False) -> None:
    """Remove a worktree.

    The main checkout is located from git's own answer rather than guessed. ``--git-common-dir``
    returns the shared ``.git`` directory, which is either absolute or relative to the worktree, so
    both cases are resolved before its parent is taken. An earlier draft climbed a fixed number of
    parents and failed against an absolute answer; the test that removes a real worktree is what
    caught it.

    Args:
        worktree: The worktree to remove.
        force: Whether to remove one with uncommitted changes. Default False, because the
            uncommitted changes are usually the work.

    Raises:
        WorktreeError: If git refuses. A refusal is reported with its own reason rather than
            worked around.
    """
    code, common, err = _git(worktree.path, "rev-parse", "--git-common-dir")
    if code != 0:
        raise WorktreeError(f"{worktree.path} is not a git worktree: {err}")
    common_path = Path(common)
    if not common_path.is_absolute():
        common_path = (worktree.path / common_path).resolve()
    main = common_path.parent
    args = ["worktree", "remove", str(worktree.path)]
    if force:
        args.insert(2, "--force")
    code, out, err = _git(main, *args)
    if code != 0:
        raise WorktreeError(f"git worktree remove failed: {err or out}")


def prune(root: Path) -> None:
    """Drop git's records of worktrees whose directories are gone.

    Args:
        root: The repository root.
    """
    _git(root, "worktree", "prune")


def which_git() -> str | None:
    """Return the git binary path, or None when there is none.

    Returns:
        The path, or None.
    """
    return shutil.which("git")

"""The three human approval gates, as functions rather than as sentences in a rule.

A comment saying "a human must approve this" is not a gate. Each function here returns a
:class:`GateOutcome` and the CLI refuses the thing it guards when ``passed`` is False. The three:

* **(a) The idea and the pass bar are committed before any build.** A declaration must be at
  ``HEAD``, unmodified, in phase ``declared``, and introduced by a commit that is an ancestor of
  the base the builder branches from. A declaration typed into a working tree does not pass, which
  is the distinction ``genesis.py declare`` prints when it says the gate reads HEAD.
* **(b) The sealed referee step stops unless the PHOSRED volume is mounted.** The check looks and
  stops. It never mounts the volume and never reads a password: there is no ``hdiutil``, no
  ``security`` call, no keychain lookup and no variable that could hold a passphrase anywhere in
  this module, and ``tests/forge/test_gates.py`` asserts that against the source text.
* **(c) Nothing merges to ``main``.** A working branch may not be ``main``, and a push target may
  not be ``main`` and must be the PHOS Labs remote, never the public repository.

None of these can be satisfied by an agent. That is the point of putting them here rather than in
prose an agent could reason its way past.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

#: The volume the sealed corpora live in (ADR 0464). Matched by name only; this module never
#: inspects its contents and never opens it.
SEALED_VOLUME: Final = Path("/Volumes/PHOSRED")

#: The one remote FORGE may push to. The public ``phos`` repository is not a target anywhere in
#: this package, and a test asserts the string does not appear.
ALLOWED_REMOTE: Final = "elijahagumba/phoslabs"

#: Branch names that are never a place to work.
PROTECTED_BRANCHES: Final[frozenset[str]] = frozenset({"main", "master"})

#: Where a declaration lives, relative to the repository root.
DECLARATION_DIR: Final = Path("docs/genesis/experiments")


@dataclass(frozen=True)
class GateOutcome:
    """What one gate concluded.

    Attributes:
        gate: Which gate, ``a``, ``b`` or ``c``.
        passed: Whether the guarded thing may proceed.
        detail: Why, in a sentence a human can act on.
        missing: What is absent, where the answer is a missing thing rather than a wrong one.
    """

    gate: str
    passed: bool
    detail: str
    missing: tuple[str, ...] = field(default=())

    def __bool__(self) -> bool:
        """Return whether the gate passed, so ``if gate(...)`` reads correctly."""
        return self.passed


def _git(root: Path, *args: str) -> tuple[int, str, str]:
    """Run one git command in ``root``.

    Args:
        root: The repository root.
        *args: The git arguments.

    Returns:
        ``(returncode, stdout, stderr)``, with both streams stripped.
    """
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def require_committed_declaration(
    root: Path,
    experiment_id: str,
    *,
    base_commit: str | None = None,
) -> GateOutcome:
    """Gate (a): the idea and its pass bar are committed before any build.

    Three checks, and all must hold:

    1. The declaration file is in ``HEAD``.
    2. The working copy of that file still matches ``HEAD``. An edited declaration is a bar moved
       after the fact, which is the thing the bar exists to prevent.
    3. The record's phase is ``declared``. A record already ``measured`` or ``judged`` is a result,
       not something to build against.
    4. When ``base_commit`` is given, the commit that introduced the declaration is an ancestor of
       it, so the builder's branch really does carry the bar it will be judged against.

    Args:
        root: The repository root.
        experiment_id: The GENESIS experiment id, ``E-NNNN``.
        base_commit: The commit a builder would branch from, or None to skip the ancestry check.

    Returns:
        The outcome. ``missing`` names what was absent when the answer is absence rather than a
        contradiction.
    """
    relative = (DECLARATION_DIR / f"{experiment_id}.json").as_posix()

    code, listed, _ = _git(root, "ls-tree", "--name-only", "HEAD", "--", relative)
    if code != 0:
        return GateOutcome("a", False, f"git could not read HEAD in {root}")
    if not listed:
        return GateOutcome(
            "a",
            False,
            f"{relative} is not committed at HEAD. A declaration in a working tree is not a bar: "
            "commit it before anything is built, because the gate reads HEAD.",
            missing=(relative,),
        )

    code, difference, _ = _git(root, "diff", "--name-only", "HEAD", "--", relative)
    if code != 0:
        return GateOutcome("a", False, f"git could not compare {relative} with HEAD")
    if difference:
        return GateOutcome(
            "a",
            False,
            f"{relative} differs from HEAD. A bar moved after the declaration was committed is "
            "not the bar the result will be judged against.",
        )

    path = root / DECLARATION_DIR / f"{experiment_id}.json"
    if not path.is_file():
        return GateOutcome("a", False, f"{relative} is in HEAD but not in the working tree")
    phase = _read_phase(path)
    if phase is None:
        return GateOutcome("a", False, f"{relative} does not state a phase")
    if phase != "declared":
        return GateOutcome(
            "a",
            False,
            f"{experiment_id} is in phase {phase!r}. Only a declaration in phase 'declared' "
            "may be built against; a measured or judged record is a result.",
        )

    if base_commit is not None:
        code, introducing, _ = _git(
            root, "log", "--diff-filter=A", "--format=%H", "-1", "--", relative
        )
        if code != 0 or not introducing:
            return GateOutcome("a", False, f"git could not find the commit that added {relative}")
        code, _, _ = _git(root, "merge-base", "--is-ancestor", introducing, base_commit)
        if code != 0:
            return GateOutcome(
                "a",
                False,
                f"{relative} was added in {introducing[:12]}, which is not an ancestor of "
                f"{base_commit[:12]}. The branch being built on does not carry the bar.",
            )

    return GateOutcome("a", True, f"{experiment_id} is committed at HEAD and declares a bar")


def _read_phase(path: Path) -> str | None:
    """Return the ``phase`` field of a declaration file, or None when it has none.

    Args:
        path: The declaration file.

    Returns:
        The phase string, or None.
    """
    import json

    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(parsed, dict):
        return None
    phase = parsed.get("phase")
    return phase if isinstance(phase, str) else None


def require_sealed_volume(volume: Path = SEALED_VOLUME) -> GateOutcome:
    """Gate (b): the sealed referee step stops unless the volume is already mounted.

    This function looks and stops. It does not mount, does not attach an image, does not read a
    password and does not look in the keychain. The sealed corpora are mounted by a human for a
    declared score (ADR 0464), so a machine that cannot see the volume is a machine that does not
    score.

    A refusal is a normal result. The operation ends with its development numbers and an INBOX
    note naming exactly what is missing.

    Args:
        volume: The mount point to look for. Injectable so a test does not need a real image.

    Returns:
        The outcome.
    """
    if volume.is_dir():
        return GateOutcome("b", True, f"{volume} is mounted")
    return GateOutcome(
        "b",
        False,
        f"{volume} is not mounted. The sealed referee step does not run, and FORGE does not mount "
        "it or ask for its password: a human mounts it for a declared score. The operation ends "
        "with development results only.",
        missing=(str(volume),),
    )


def require_not_main(branch: str) -> GateOutcome:
    """Gate (c), first half: a builder never works on ``main``.

    Args:
        branch: The branch the role would work on.

    Returns:
        The outcome.
    """
    if branch in PROTECTED_BRANCHES:
        return GateOutcome(
            "c",
            False,
            f"{branch} is not a place to work. Every role works on its own branch in its own "
            "worktree, and nothing merges to main from FORGE.",
        )
    if not branch:
        return GateOutcome("c", False, "no branch was named, so there is nothing to work on")
    return GateOutcome("c", True, f"{branch} is a working branch")


def require_landing_target(remote_url: str) -> GateOutcome:
    """Gate (c), second half: a push goes to PHOS Labs and never to the public repository.

    Args:
        remote_url: The URL the push would go to.

    Returns:
        The outcome.
    """
    if not remote_url:
        return GateOutcome("c", False, "no remote was named, so there is nothing to push to")
    if ALLOWED_REMOTE not in remote_url:
        return GateOutcome(
            "c",
            False,
            f"{remote_url} is not the PHOS Labs remote. FORGE pushes only to a remote pointing at "
            f"{ALLOWED_REMOTE}; the public repository is never a target.",
        )
    return GateOutcome("c", True, f"{remote_url} is the PHOS Labs remote")


def require_landing_push(remote_url: str, refspec: str) -> GateOutcome:
    """Gate (c) as one call: a push must target PHOS Labs and must not be ``main``.

    Args:
        remote_url: The URL the push would go to.
        refspec: The refspec, for example ``refs/heads/forge/v0:refs/heads/forge/v0``.

    Returns:
        The outcome.
    """
    target = require_landing_target(remote_url)
    if not target.passed:
        return target
    destination = refspec.rsplit(":", 1)[-1].removeprefix("refs/heads/")
    if destination in PROTECTED_BRANCHES:
        return GateOutcome(
            "c",
            False,
            f"the push would write {destination}. FORGE does not push to main; a human lands the "
            "work, and only after reviewing it.",
        )
    return GateOutcome("c", True, f"{refspec} to the PHOS Labs remote is permitted")

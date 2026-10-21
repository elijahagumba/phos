#!/usr/bin/env python3
"""Refuse an ADR or note number that another branch has already given to a different file.

ADR 0291 recorded the cause and left it unfixed: two sessions each take the next free number
from the tree they can see, and neither can see the other's. ADR 0292 is this check.

A change is judged only on the numbered files it adds or renames onto. The same filename on
two branches is one record. A different filename under the same number is the collision, and
the change is refused. The pair ADR 0291 already settled is not reopened, because those old
filenames are not what a later change adds.

The check sees the refs in this clone, heads and remote-tracking branches. A remote branch
that has not been fetched is invisible here, which is why the lab workflow fetches every
origin branch before it runs.

Usage::

    uv run python scripts/check_number_allocation.py --staged
    uv run python scripts/check_number_allocation.py --from <rev> --to <rev>
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

#: Decision records. The four digits are the number; the rest is which decision it is.
ADR_PATH: re.Pattern[str] = re.compile(r"^docs/adr/(\d{4})-.+\.md$")
#: Plain-English notes. The leading digits are the number.
NOTE_PATH: re.Pattern[str] = re.compile(r"^easy to reads/(\d+)-.+\.md$")


@dataclass(frozen=True)
class Collision:
    """One new file whose number already belongs to a different file."""

    kind: str
    number: str
    basename: str
    also: tuple[str, ...]

    def __str__(self) -> str:
        """The line a person refusing the change should read."""
        others = ", ".join(self.also)
        return f"{self.kind} {self.number}: {self.basename} is already used by {others}"


def identity(path: str) -> tuple[str, str, str] | None:
    """Return ``(kind, number, basename)`` for a numbered record, else ``None``.

    Args:
        path: A repository path using forward slashes, as git prints it.

    Returns:
        The kind (``adr`` or ``note``), the number, and the filename. A path that is
        not one of those two records is ``None``, including the ADR index.
    """
    name = Path(path).name
    adr = ADR_PATH.fullmatch(path)
    if adr is not None:
        return ("adr", adr.group(1), name)
    note = NOTE_PATH.fullmatch(path)
    if note is not None:
        return ("note", note.group(1), name)
    return None


def paths_from_name_status(blob: str) -> list[str]:
    """The destination paths in a ``git diff --name-status -z`` payload.

    Args:
        blob: The raw diff, NUL-separated. An add contributes its path. A rename or a
            copy contributes the new path, which is the number being taken.

    Returns:
        Destination paths, in the order git emitted them.
    """
    parts = blob.split("\0")
    found: list[str] = []
    index = 0
    while index < len(parts):
        status = parts[index]
        if status == "":
            break
        if status.startswith(("R", "C")):
            found.append(parts[index + 2])
            index += 3
            continue
        found.append(parts[index + 1])
        index += 2
    return found


def find_collisions(
    introduced: Sequence[str],
    on_refs: Mapping[tuple[str, str], set[str]],
) -> list[Collision]:
    """The introduced numbered files whose number already names a different file.

    Args:
        introduced: Paths the change adds or renames onto.
        on_refs: Filenames already stored under each ``(kind, number)`` on any ref.

    Returns:
        One collision per introduced file that is not alone under its number. Two new
        files that take the same number in this change collide with each other even
        when no ref has either yet.
    """
    incoming: dict[tuple[str, str], set[str]] = {}
    parsed: list[tuple[str, str, str]] = []
    for path in introduced:
        found = identity(path)
        if found is None:
            continue
        kind, number, basename = found
        parsed.append(found)
        incoming.setdefault((kind, number), set()).add(basename)

    collisions: list[Collision] = []
    for kind, number, basename in parsed:
        others = (on_refs.get((kind, number), set()) | incoming[(kind, number)]) - {basename}
        if others:
            collisions.append(Collision(kind, number, basename, tuple(sorted(others))))
    return collisions


def _git(repo: Path, *args: str) -> str:
    """Run git in ``repo`` and return stdout. Raise when git refuses."""
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout


def changed_paths(repo: Path, *, staged: bool, from_rev: str, to_rev: str) -> list[str]:
    """Paths a change adds or renames onto.

    Args:
        repo: The work tree to ask.
        staged: When true, read the index rather than a revision range.
        from_rev: The left side of the range. Ignored when ``staged`` is true.
        to_rev: The right side of the range. Ignored when ``staged`` is true.

    Returns:
        Destination paths.
    """
    command = ["diff", "-M", "--name-status", "--diff-filter=AR", "-z"]
    if staged:
        command.insert(1, "--cached")
    else:
        command.extend([from_rev, to_rev])
    return paths_from_name_status(_git(repo, *command))


def branch_refs(repo: Path) -> list[str]:
    """Local branch tips and remote-tracking tips, omitting ``origin/HEAD``.

    ``origin/HEAD`` is a second name for the default branch, so counting it would
    report every file twice and change nothing about a collision.
    """
    text = _git(repo, "for-each-ref", "--format=%(refname)", "refs/heads", "refs/remotes")
    return [line for line in text.splitlines() if line and not line.endswith("/HEAD")]


def names_on_refs(repo: Path, refs: Sequence[str]) -> dict[tuple[str, str], set[str]]:
    """Every numbered filename visible on ``refs``, grouped by kind and number."""
    grouped: dict[tuple[str, str], set[str]] = {}
    for ref in refs:
        listing = _git(
            repo,
            "ls-tree",
            "-r",
            "--name-only",
            ref,
            "--",
            "docs/adr",
            "easy to reads",
        )
        for path in listing.splitlines():
            found = identity(path)
            if found is None:
                continue
            kind, number, basename = found
            grouped.setdefault((kind, number), set()).add(basename)
    return grouped


def check(repo: Path, *, staged: bool, from_rev: str, to_rev: str) -> list[Collision]:
    """Collisions between a change and every branch tip this clone can see."""
    introduced = changed_paths(repo, staged=staged, from_rev=from_rev, to_rev=to_rev)
    return find_collisions(introduced, names_on_refs(repo, branch_refs(repo)))


def main(argv: Sequence[str] | None = None, repo: Path | None = None) -> int:
    """Run the check. ``0`` when the change takes no occupied number, ``1`` when it does.

    Args:
        argv: Arguments, excluding the program name. ``None`` reads the process arguments.
        repo: The work tree. ``None`` is the repository that contains this script.

    Returns:
        ``0`` when no new number is already taken, ``1`` when one is, ``2`` when the
        arguments or git cannot be used.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--staged",
        action="store_true",
        help="judge the files staged for the next commit",
    )
    parser.add_argument("--from", dest="from_rev", default="", help="left side of a revision range")
    parser.add_argument("--to", dest="to_rev", default="", help="right side of a revision range")
    arguments = parser.parse_args(argv)
    ranged = bool(arguments.from_rev or arguments.to_rev)
    if arguments.staged == ranged or (ranged and not (arguments.from_rev and arguments.to_rev)):
        print(
            "pass --staged, or both --from and --to",
            file=sys.stderr,
        )
        return 2

    root = repo if repo is not None else Path(__file__).resolve().parents[1]
    try:
        found = check(
            root,
            staged=arguments.staged,
            from_rev=arguments.from_rev,
            to_rev=arguments.to_rev,
        )
    except subprocess.CalledProcessError as error:
        message = error.stderr.strip() if error.stderr else str(error)
        print(message, file=sys.stderr)
        return 2

    if not found:
        print("no new ADR or note number is already taken on another branch")
        return 0
    print(f"{len(found)} numbered file(s) take a number another file already has:")
    for collision in found:
        print(f"  {collision}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

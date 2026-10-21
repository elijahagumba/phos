"""Compare recomputed record text to the committed file. Never writes."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path


def wants_compare(argv: Sequence[str] | None) -> bool:
    """True when the only argument is ``--compare``.

    Args:
        argv: Arguments, excluding the program name. ``None`` reads ``sys.argv``.

    Returns:
        Whether the caller asked to recompute and compare, without writing.

    Raises:
        SystemExit: Any argument other than ``--compare`` was given.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        return False
    if args == ["--compare"]:
        return True
    raise SystemExit(f"unrecognised arguments: {' '.join(args)}")


def committed_difference(path: Path, fresh: str) -> str | None:
    """Return None when ``fresh`` is the committed file.

    Args:
        path: The committed record.
        fresh: The recomputed text.

    Returns:
        None on a match. Otherwise one sentence naming the first difference.
        The file is not written.
    """
    if not path.is_file():
        return f"{path.name} is missing"
    committed = path.read_text(encoding="utf-8")
    if committed == fresh:
        return None
    return f"{path.name} differs: {_first_difference(committed, fresh)}"


def require_match(pairs: Sequence[tuple[Path, str]]) -> None:
    """Exit when any recomputed text differs. Do not write.

    Args:
        pairs: Each committed path and the text just recomputed for it.

    Raises:
        SystemExit: A file is missing or its bytes differ.
    """
    problems: list[str] = []
    for path, fresh in pairs:
        difference = committed_difference(path, fresh)
        if difference is not None:
            problems.append(difference)
    if problems:
        raise SystemExit("not written:\n" + "\n".join(problems))


def _first_difference(committed: str, fresh: str) -> str:
    left = committed.splitlines()
    right = fresh.splitlines()
    for number, (old, new) in enumerate(zip(left, right, strict=False), start=1):
        if old != new:
            return f"line {number}"
    return f"length {len(committed)} != {len(fresh)}"

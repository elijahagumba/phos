"""Compare two generated corpus trees file-by-file by SHA-256.

Prints how many files were compared, how many were byte-identical, and how many differed.
Every count in an identity-proof record must come from this script's output, not from memory.

Usage::

    uv run python scripts/compare_corpus_identity.py LEFT RIGHT
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

_CHUNK = 1 << 20


def digest_of(path: Path) -> str:
    """Return the SHA-256 hex digest of ``path``."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def files_under(root: Path) -> dict[str, Path]:
    """Return ``{relative posix path: absolute path}`` for every file under ``root``."""
    return {
        path.relative_to(root).as_posix(): path
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def compare(left_root: Path, right_root: Path) -> tuple[int, int, int, tuple[str, ...]]:
    """Compare every file under both roots.

    Returns:
        ``(compared, identical, differing, differing_relative_paths)``. A path present on only
        one side counts as differing.
    """
    left = files_under(left_root)
    right = files_under(right_root)
    names = sorted(set(left) | set(right))
    identical = 0
    differing_names: list[str] = []
    for name in names:
        if name not in left or name not in right:
            differing_names.append(name)
            continue
        if digest_of(left[name]) == digest_of(right[name]):
            identical += 1
        else:
            differing_names.append(name)
    return len(names), identical, len(differing_names), tuple(differing_names)


def main(argv: list[str] | None = None) -> int:
    """Compare two corpus trees and print the counts."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("left", type=Path)
    parser.add_argument("right", type=Path)
    args = parser.parse_args(argv)
    if not args.left.is_dir() or not args.right.is_dir():
        print("both arguments must be existing directories", file=sys.stderr)
        return 2
    compared, identical, differing, names = compare(args.left, args.right)
    print(f"compared={compared}")
    print(f"identical={identical}")
    print(f"differing={differing}")
    for name in names:
        print(f"differ: {name}")
    return 0 if differing == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

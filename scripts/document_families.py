#!/usr/bin/env python3
"""Render the plant families' declared bounds into the public documentation, and check it.

PART R2 asks for every randomised parameter and its bounds to be documented. A table written by
hand beside the code is a table that is wrong within a month, so this one is *generated* from
`phos.synth.families` and the test in ``tests/synth/test_family_docs.py`` fails when the committed
document and the registry disagree. Changing a bound therefore changes the document, or CI says so.

Only the open families are rendered. A sealed family's bounds are not published, because the
public table is read by whoever is being examined on it.

Usage::

    python scripts/document_families.py            # check the document matches the registry
    python scripts/document_families.py --write    # regenerate it
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final

REPO_ROOT: Final = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from phos.synth.families import bounds_table, list_families  # noqa: E402

__all__ = [
    "BEGIN_MARKER",
    "END_MARKER",
    "README_PATH",
    "DocumentationError",
    "current_section",
    "main",
    "rendered_section",
    "rewritten",
]

logger = logging.getLogger("phos.synth.document_families")

README_PATH: Final = REPO_ROOT / "docs" / "sim" / "README.md"
BEGIN_MARKER: Final = "<!-- BEGIN GENERATED: family bounds -->"
END_MARKER: Final = "<!-- END GENERATED: family bounds -->"


class DocumentationError(RuntimeError):
    """Raised when the document cannot be read as something this script maintains."""


def rendered_section() -> str:
    """Return the generated block, markers included, as it should appear in the document."""
    table = bounds_table(list_families())
    return f"{BEGIN_MARKER}\n\n{table}\n{END_MARKER}"


def current_section(document: str) -> str:
    """Return the generated block as the document currently holds it.

    Args:
        document: The whole file.

    Returns:
        The block, markers included.

    Raises:
        DocumentationError: If the markers are missing or out of order. The message says how to
            put them back, because a document that has lost them silently stops being checked.
    """
    begin = document.find(BEGIN_MARKER)
    end = document.find(END_MARKER)
    if begin < 0 or end < 0 or end < begin:
        raise DocumentationError(
            f"{README_PATH} has no generated block between {BEGIN_MARKER!r} and {END_MARKER!r}; "
            "add the markers back, or the bounds table stops being checked against the code"
        )
    return document[begin : end + len(END_MARKER)]


def rewritten(document: str) -> str:
    """Return the document with its generated block replaced by a freshly rendered one."""
    return document.replace(current_section(document), rendered_section())


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns a process exit code."""
    parser = argparse.ArgumentParser(
        description="Render or check the family bounds table in docs/sim/README.md."
    )
    parser.add_argument("--write", action="store_true", help="regenerate the table in place")
    arguments = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    try:
        document = README_PATH.read_text(encoding="utf-8")
        if arguments.write:
            README_PATH.write_text(rewritten(document), encoding="utf-8")
            logger.info("wrote the bounds table for %d families", len(list_families()))
            return 0
        if current_section(document) != rendered_section():
            logger.error(
                "%s is out of date: a family's bounds have changed. Regenerate it with "
                "`python scripts/document_families.py --write`.",
                README_PATH,
            )
            return 1
    except DocumentationError as error:
        logger.error("%s", error)
        return 2
    logger.info("the bounds table matches the registry")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

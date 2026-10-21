#!/usr/bin/env python3
"""Check every drafted post in `outreach/launch-posts.md` against X's character limit.

A draft that is two characters over is a draft that cannot be posted, and counting by eye does not
catch it. This reads the blockquoted posts out of the drafts file and reports the length of each.

**How X counts, and what this reproduces.** A URL counts as a fixed 23 characters whatever its real
length, so a 29-character repository link costs 23. The drafts file wraps at the repository's line
width, so a single newline inside a paragraph is markdown wrapping rather than part of the post and
is counted as the one space it becomes when pasted; a blank line stays a paragraph break.

A handle placeholder such as ``[PHOS_HANDLE]`` is left as written, because its real length is not
known here; the margin reported is what a longer handle would eat into.

Usage::

    uv run python scripts/check_post_lengths.py
    uv run python scripts/check_post_lengths.py --limit 280 --file outreach/launch-posts.md
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

ROOT: Final = Path(__file__).resolve().parents[1]

#: X's limit for an ordinary account.
LIMIT: Final = 280

#: X bills every URL at this fixed length, however long the URL really is.
URL_WEIGHT: Final = 23

#: A post header in the drafts file: ``**1/**``, ``**S/**``.
_HEADER: Final = re.compile(r"^\*\*([0-9]+|[A-Z])/\*\*\s*$")

#: A markdown section header, which ends the preceding post.
_SECTION: Final = re.compile(r"^#{1,3} ")

_URL: Final = re.compile(r"https?://\S+|\b[a-z0-9-]+(?:\.[a-z0-9-]+)+/\S*")


@dataclass(frozen=True)
class Post:
    """One drafted post, with the section it belongs to.

    Attributes:
        section: The nearest preceding markdown heading, so a report names the account.
        label: The post's own marker, for example ``1`` or ``S``.
        text: The post as it would be pasted, blockquote markers stripped.
    """

    section: str
    label: str
    text: str

    def pasted(self) -> str:
        """The post as it would actually be pasted, with markdown wrapping undone.

        The drafts file wraps at the repository's line width, so a sentence can carry a newline in
        the middle of it. That newline is an artefact of the file and not part of the post, so a
        single newline becomes a space and only a blank line stays a paragraph break.
        """
        paragraphs = [" ".join(part.split()) for part in self.text.split("\n\n")]
        return "\n\n".join(p for p in paragraphs if p)

    def billed(self) -> int:
        """The length X would charge for the pasted text, each URL counted as `URL_WEIGHT`."""
        return len(_URL.sub("U" * URL_WEIGHT, self.pasted()))


def parse(markdown: str) -> list[Post]:
    """Read the blockquoted posts out of the drafts file.

    Args:
        markdown: The whole drafts file.

    Returns:
        Every post found, in file order.
    """
    posts: list[Post] = []
    section = ""
    label: str | None = None
    body: list[str] = []

    def flush() -> None:
        if label is not None and body:
            text = "\n".join(body).strip()
            if text:
                posts.append(Post(section=section, label=label, text=text))

    for line in markdown.splitlines():
        if _SECTION.match(line):
            flush()
            label, body = None, []
            section = line.lstrip("#").strip()
            continue
        header = _HEADER.match(line)
        if header:
            flush()
            label, body = header.group(1), []
            continue
        if label is None:
            continue
        if line.startswith(">"):
            body.append(line[1:].lstrip() if line[1:2] == " " else line[1:])
        elif line.strip() == "":
            if body:
                body.append("")
        else:
            flush()
            label, body = None, []
    flush()
    return posts


def main(argv: Sequence[str] | None = None) -> int:
    """Report each post's billed length and fail if any exceeds the limit."""
    parser = argparse.ArgumentParser(description="Check drafted posts against X's limit.")
    parser.add_argument("--file", type=Path, default=ROOT / "outreach" / "launch-posts.md")
    parser.add_argument("--limit", type=int, default=LIMIT)
    arguments = parser.parse_args(argv)

    if not arguments.file.is_file():
        print(f"{arguments.file} is not a file", file=sys.stderr)
        return 2

    posts = parse(arguments.file.read_text(encoding="utf-8"))
    if not posts:
        print(f"no posts found in {arguments.file}", file=sys.stderr)
        return 2

    over = 0
    current = ""
    for post in posts:
        if post.section != current:
            current = post.section
            print(f"\n{current}")
        billed = post.billed()
        room = arguments.limit - billed
        mark = "OVER" if billed > arguments.limit else "ok  "
        if billed > arguments.limit:
            over += 1
        print(f"  {mark} {post.label + '/':>4}  {billed:>4} chars, {room:>4} to spare")

    print()
    if over:
        print(f"{over} of {len(posts)} posts exceed {arguments.limit} characters")
        return 1
    tightest = min(arguments.limit - p.billed() for p in posts)
    print(
        f"all {len(posts)} posts are within {arguments.limit} characters; "
        f"the tightest has {tightest} to spare"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

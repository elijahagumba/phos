"""Audit every commit, path, and digest the records cite.

A squash or a rebase leaves a cited short SHA pointing at nothing, and a record whose
evidence cannot be resolved is not evidence. This script reads the citations out of the
markdown records and says which ones still resolve against the current history.

It reports. It does not rewrite a record, and it never creates a tag to make an orphan
resolve: a dangling citation is re-stamped by re-running from a committed HEAD.

A citation that does not resolve can still be the honest state of the record: an unmerged
lane, another repository's layout, a tree deliberately not built. Such an item is
acknowledged where it is cited, with a reason, so the audit can tell "this does not resolve
and nobody has explained why" from "this does not resolve and the record says why":

    <!-- evidence-ack: src/phos/api/ — neither tree is built; the programme lock forbids it -->

The acknowledgement names the token and sits in the citation's own paragraph, so it covers
that citation and no other. An acknowledgement that stops matching a citation fails the gate
just as an unexplained citation does; an acknowledgement cannot go quietly stale.

    uv run python scripts/audit_evidence.py
    uv run python scripts/audit_evidence.py --paths docs/adr
    uv run python scripts/audit_evidence.py --strict     # the CI gate
"""

from __future__ import annotations

import argparse
import re
import subprocess
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

#: A backticked hex token the length of an abbreviated or full git object name.
COMMITISH = re.compile(r"`([0-9a-f]{7,40})`")
#: A full sha256, which is a frozen-bytes digest rather than a commit.
SHA256 = re.compile(r"\b([0-9a-f]{64})\b")
#: A backticked repository path. Known top-level directories only, so prose is not a path.
CITED_PATH = re.compile(r"`((?:src|tests|scripts|docs|eval_runs|data|public|configs)/[^`\s]+)`")
#: Words just before a token that make it this repository's commit.
COMMIT_CUES = (
    "commit",
    "at",
    "built on",
    "run after",
    "scored at",
    "worktree",
    "rebased",
    "squashed",
    "head",
    "merged",
    "branch",
)
#: Words just before a token that make it somebody else's identifier, not our commit.
FOREIGN_CUES = (
    "md5",
    "sha1",
    "sha256",
    "checksum",
    "digest",
    "hash",
    "blob",
    "blobs",
    "tree",
    "file",
    "files",
    "pin",
    "doi",
    "record",
    "figshare",
    "zenodo",
    "bytes",
    "version",
)
#: How much text before a token is read for a cue.
CUE_WINDOW = 48
#: Characters that make a cited path a pattern or a placeholder rather than a file.
PATH_WILDCARDS = ("*", "<", ">", "?", "{")
#: Trees that are deliberately absent. Data is never committed (ADR 0006), so a cited
#: payload path missing from a checkout is the rule working, not a dangling citation.
UNCOMMITTED_TREES = ("data/",)
#: An acknowledgement that a cited token does not resolve, written beside it in the record.
#: Matched loosely so a near miss is reported rather than ignored.
ACK_COMMENT = re.compile(r"<!--\s*evidence-ack(?P<body>.*?)-->")
#: The literal a marker must contain, used to catch a typo that ACK_COMMENT cannot match.
ACK_KEYWORD = "evidence-ack"
#: What separates the acknowledged token from the reason. An em dash, as the records use.
ACK_SEPARATOR = "\u2014"
#: A reason has to be a sentence about this citation, not a word that waves it through.
MIN_REASON_WORDS = 4
MIN_REASON_CHARS = 20
#: The shape to write, quoted back whenever a marker is rejected.
ACK_FORM = "<!-- evidence-ack: <token> \u2014 <why it does not resolve> -->"


def resolve_cited_path(value: str) -> Path | None:
    """The file a cited path points at, or ``None`` when it is not a single file.

    A record cites a test by node id (``path::test_name``), a line by ``path:line``,
    a family by glob, and a payload under ``data/`` that is never committed. None of
    those is a dangling reference, so none is resolved here.
    """
    if any(mark in value for mark in PATH_WILDCARDS):
        return None
    if value.startswith(UNCOMMITTED_TREES):
        return None
    bare = value.split("::", 1)[0]
    stem, _, suffix = bare.rpartition(":")
    if stem and suffix.isdigit():
        bare = stem
    return Path(bare)


#: Text near a citation saying the commit is from another repository. Matched against the
#: citation's own paragraph, never the whole file: "upstream" appears in ADR titles that have
#: nothing to do with the commit beside them, and a file-wide match files our own commits as
#: somebody else's.
EXTERNAL_MARKERS = ("not in this repository", "worktree commit", "upstream", "publisher's head")
DEFAULT_ROOTS = ("docs", "eval_runs")


def classify(line: str, start: int, token: str) -> str:
    """Say what the hex ``token`` at ``start`` is, from the words just before it.

    A figshare id, an MD5, and a commit are all hex in backticks. The prose around the
    token is the only thing that separates them, so that is what is read.
    """
    if token.isdigit():
        return "foreign"
    before = line[max(0, start - CUE_WINDOW) : start].lower()
    words = re.findall(r"[a-z0-9]+", before)
    tail = words[-3:]
    if any(cue in tail for cue in FOREIGN_CUES):
        return "foreign"
    if any(cue.split()[-1] in tail for cue in COMMIT_CUES):
        return "commit"
    return "unclassified"


@dataclass(frozen=True)
class Citation:
    """One cited token, and where it was cited."""

    kind: str
    value: str
    record: Path
    line: int
    block: int = -1

    @property
    def site(self) -> tuple[Path, int, str]:
        """What an acknowledgement has to name to cover this citation.

        The paragraph rather than the line, so reflowing a record does not invalidate an
        acknowledgement; the token rather than the position, so moving the citation or
        citing something else in its place does.
        """
        return (self.record, self.block, self.value)

    def __str__(self) -> str:
        """Where the citation is, then the token."""
        return f"{self.record}:{self.line}  {self.value}"


@dataclass(frozen=True)
class Acknowledgement:
    """A record saying, beside a citation, that it does not resolve and why."""

    token: str
    reason: str
    record: Path
    line: int
    block: int
    note: str = ""

    @property
    def site(self) -> tuple[Path, int, str]:
        """The citation this acknowledgement claims to cover."""
        return (self.record, self.block, self.token)

    def __str__(self) -> str:
        """Where the acknowledgement is, the token, and why it is being reported."""
        where = f"{self.record}:{self.line}  {self.token}"
        return f"{where}  \u2014 {self.note}" if self.note else where


@dataclass(frozen=True)
class Malformed:
    """A marker that was meant to be an acknowledgement and cannot be read as one."""

    text: str
    record: Path
    line: int
    problem: str

    def __str__(self) -> str:
        """Where it is, what is wrong, and what was written."""
        return f"{self.record}:{self.line}  {self.problem}\n    found: {self.text}"


@dataclass(frozen=True)
class Audit:
    """What the citations resolved to."""

    resolved: tuple[Citation, ...]
    orphans: tuple[Citation, ...]
    unreachable: tuple[Citation, ...]
    external: tuple[Citation, ...]
    missing_paths: tuple[Citation, ...]
    digests: tuple[Citation, ...]
    unclassified: tuple[Citation, ...]
    foreign: tuple[Citation, ...]
    acknowledged: tuple[Acknowledgement, ...] = ()
    unacknowledged: tuple[Citation, ...] = ()
    stale: tuple[Acknowledgement, ...] = ()
    malformed: tuple[Malformed, ...] = ()

    @property
    def clean(self) -> bool:
        """Whether every citation resolved to something in this history."""
        return not (self.orphans or self.unreachable or self.missing_paths)

    @property
    def gated(self) -> bool:
        """Whether the record accounts for every citation, which is what CI enforces.

        Weaker than ``clean`` on purpose: a citation that does not resolve for a stated
        reason is the honest state of the record, and the skill's triage says so. Not weaker
        in the way that matters, because it fails in three directions — a citation nobody
        explained, an acknowledgement that no longer names one, and a marker that cannot be
        read. Nothing is waved through by default and no category is dropped.
        """
        return not (self.unacknowledged or self.stale or self.malformed)


def blocks_of(lines: Sequence[str]) -> list[int]:
    """For each line, the index of the blank-line-delimited block it sits in; -1 when blank.

    This is the identity an acknowledgement is scoped to, so it has to come from the
    record's own blank lines and not from whatever is left after a marker is blanked out.
    """
    index = [-1] * len(lines)
    current = -1
    after_blank = True
    for position, line in enumerate(lines):
        if not line.strip():
            after_blank = True
            continue
        if after_blank:
            current += 1
            after_blank = False
        index[position] = current
    return index


def paragraph_at(lines: Sequence[str], text: Sequence[str] | None = None) -> list[str]:
    """For each line, the blank-line-delimited block it belongs to, joined and lowercased.

    A marker sentence wraps across lines, so the block is what gets searched rather than the
    line. A table is one block, which is as tight as this can be without parsing markdown.

    ``lines`` delimits the blocks and ``text`` is what gets joined, so an acknowledgement can
    be kept out of the prose without its line splitting the paragraph it was written in.
    """
    source = list(text) if text is not None else list(lines)
    index = blocks_of(lines)
    grouped: dict[int, list[str]] = {}
    for position, block in enumerate(index):
        if block >= 0:
            grouped.setdefault(block, []).append(source[position])
    return ["" if block < 0 else " ".join(grouped[block]).lower() for block in index]


def without_acknowledgements(line: str) -> str:
    """The line with every acknowledgement blanked out, column offsets preserved.

    A marker names the token it acknowledges. Left in place it would be read as one more
    citation of that token, and its reason would be read as prose around the real one.
    """
    return ACK_COMMENT.sub(lambda found: " " * len(found.group(0)), line)


def read_acknowledgement(body: str) -> tuple[str, str]:
    """The token and reason a marker's body carries.

    Raises ``ValueError`` with what is wrong. A marker that names a token and gives no reason
    is refused: acknowledging an item is stating why it does not resolve, and a bare token
    states nothing.
    """
    rest = body.strip()
    if not rest.startswith(":"):
        raise ValueError(f"no colon after {ACK_KEYWORD}; write {ACK_FORM}")
    token, separator, reason = rest[1:].partition(ACK_SEPARATOR)
    token, reason = token.strip(), reason.strip()
    if not separator:
        raise ValueError(f"no em dash before the reason; write {ACK_FORM}")
    if not token:
        raise ValueError(f"no token before the em dash; write {ACK_FORM}")
    if len(reason.split()) < MIN_REASON_WORDS or len(reason) < MIN_REASON_CHARS:
        raise ValueError(
            f"the reason must say why the citation does not resolve, in at least "
            f"{MIN_REASON_WORDS} words; got {reason!r}"
        )
    return token, reason


def acknowledgements(record: Path) -> tuple[list[Acknowledgement], list[Malformed]]:
    """Every acknowledgement in one record, and every marker that could not be read as one."""
    lines = record.read_text(encoding="utf-8").splitlines()
    index = blocks_of(lines)
    stated: list[Acknowledgement] = []
    broken: list[Malformed] = []
    for number, line in enumerate(lines, start=1):
        found = list(ACK_COMMENT.finditer(line))
        for match in found:
            try:
                token, reason = read_acknowledgement(match.group("body"))
            except ValueError as problem:
                broken.append(Malformed(match.group(0), record, number, str(problem)))
                continue
            stated.append(Acknowledgement(token, reason, record, number, index[number - 1]))
        if line.count(ACK_KEYWORD) > len(found):
            broken.append(
                Malformed(
                    line.strip(),
                    record,
                    number,
                    f"{ACK_KEYWORD} is not inside a complete comment on one line; write {ACK_FORM}",
                )
            )
    return stated, broken


def records(roots: Sequence[str]) -> Iterator[Path]:
    """Every markdown record under the given roots, in a stable order."""
    for root in roots:
        base = Path(root)
        if base.is_file():
            yield base
            continue
        yield from sorted(base.rglob("*.md"))


def citations(record: Path) -> Iterator[Citation]:
    """Pull commit, digest, and path citations out of one record."""
    lines = record.read_text(encoding="utf-8").splitlines()
    scanned = [without_acknowledgements(line) for line in lines]
    index = blocks_of(lines)
    blocks = paragraph_at(lines, scanned)
    for number, line in enumerate(scanned, start=1):
        block = index[number - 1]
        declares_external = any(marker in blocks[number - 1] for marker in EXTERNAL_MARKERS)
        for match in SHA256.finditer(line):
            yield Citation("sha256", match.group(1), record, number, block)
        for match in COMMITISH.finditer(line):
            if SHA256.fullmatch(match.group(1)):
                continue
            kind = classify(line, match.start(1), match.group(1))
            if kind == "commit" and declares_external:
                kind = "external"
            yield Citation(kind, match.group(1), record, number, block)
        for match in CITED_PATH.finditer(line):
            yield Citation("path", match.group(1), record, number, block)


def is_commit(value: str) -> bool:
    """Whether the object exists in this repository and is a commit."""
    found = subprocess.run(
        ["git", "cat-file", "-t", value],
        capture_output=True,
        text=True,
        check=False,
    )
    return found.returncode == 0 and found.stdout.strip() == "commit"


def is_ancestor(value: str, ref: str) -> bool:
    """Whether the commit is reachable from ``ref``."""
    return (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", value, ref],
            capture_output=True,
            check=False,
        ).returncode
        == 0
    )


def audit(roots: Sequence[str], ref: str) -> Audit:
    """Resolve every citation under ``roots`` against ``ref``."""
    resolved: list[Citation] = []
    orphans: list[Citation] = []
    unreachable: list[Citation] = []
    external: list[Citation] = []
    missing: list[Citation] = []
    digests: list[Citation] = []
    unclassified: list[Citation] = []
    foreign: list[Citation] = []
    stated: list[Acknowledgement] = []
    broken: list[Malformed] = []
    seen: dict[str, bool] = {}

    for record in records(roots):
        record_acks, record_broken = acknowledgements(record)
        stated.extend(record_acks)
        broken.extend(record_broken)
        for cited in citations(record):
            if cited.kind == "sha256":
                digests.append(cited)
            elif cited.kind == "path":
                target = resolve_cited_path(cited.value)
                if target is None:
                    continue
                (resolved if target.exists() else missing).append(cited)
            elif cited.kind == "foreign":
                foreign.append(cited)
            elif cited.kind == "unclassified":
                unclassified.append(cited)
            elif cited.kind == "external":
                external.append(cited)
            else:
                if cited.value not in seen:
                    seen[cited.value] = is_commit(cited.value)
                if not seen[cited.value]:
                    orphans.append(cited)
                elif not is_ancestor(cited.value, ref):
                    unreachable.append(cited)
                else:
                    resolved.append(cited)

    acknowledged, unacknowledged, stale = reconcile(
        orphans + unreachable + missing,
        stated,
    )

    return Audit(
        tuple(resolved),
        tuple(orphans),
        tuple(unreachable),
        tuple(external),
        tuple(missing),
        tuple(digests),
        tuple(unclassified),
        tuple(foreign),
        tuple(acknowledged),
        tuple(unacknowledged),
        tuple(stale),
        tuple(broken),
    )


def reconcile(
    failing: Sequence[Citation],
    stated: Sequence[Acknowledgement],
) -> tuple[list[Acknowledgement], list[Citation], list[Acknowledgement]]:
    """Match acknowledgements to the citations that do not resolve, both ways.

    Returns the acknowledgements that landed, the citations nobody accounted for, and the
    acknowledgements that no longer name such a citation. The second direction is the point:
    an acknowledgement whose citation was edited, repointed, or fixed stops matching and is
    reported, so it can never drift onto a different citation later and pass in silence.
    """
    by_site: dict[tuple[Path, int, str], list[Citation]] = {}
    for cited in failing:
        by_site.setdefault(cited.site, []).append(cited)

    acknowledged: list[Acknowledgement] = []
    stale: list[Acknowledgement] = []
    claimed: set[tuple[Path, int, str]] = set()
    for ack in stated:
        if ack.site not in by_site:
            stale.append(
                replace(
                    ack,
                    note="no citation in this paragraph fails to resolve under that token",
                )
            )
        elif ack.site in claimed:
            stale.append(replace(ack, note="that citation is already acknowledged here"))
        else:
            claimed.add(ack.site)
            acknowledged.append(ack)

    unacknowledged = [
        cited for site, items in by_site.items() if site not in claimed for cited in items
    ]
    return acknowledged, unacknowledged, stale


def _section(title: str, items: Iterable[object], note: str = "") -> list[str]:
    listed = list(items)
    if not listed:
        return []
    lines = [f"## {title} ({len(listed)})", ""]
    if note:
        lines.extend([note, ""])
    lines.extend(f"- {cited}" for cited in listed)
    lines.append("")
    return lines


def render(result: Audit, ref: str, show_foreign: bool = False) -> str:
    """The audit as markdown."""
    lines = [
        "# Cited evidence audit",
        "",
        f"Resolved against `{ref}`. "
        f"{len(result.resolved)} citations resolve. "
        f"{len(result.orphans)} do not exist. "
        f"{len(result.unreachable)} exist but are not reachable. "
        f"{len(result.missing_paths)} cited paths are absent. "
        f"{len(result.foreign)} hex tokens were read as somebody else's identifier and "
        f"not resolved (use --show-foreign to list them). "
        f"{len(result.acknowledged)} of the citations that do not resolve are acknowledged "
        f"with a reason where they are cited; "
        f"{len(result.unacknowledged)} are not.",
        "",
    ]
    lines += _section(
        "Citations that do not resolve and nobody has explained",
        result.unacknowledged,
        "The gate fails on these. Either fix the citation — re-stamp the commit, repoint "
        "the path — or, if not resolving is the honest state of the record, say so beside "
        f"the citation in its own paragraph: {ACK_FORM}",
    )
    lines += _section(
        "Acknowledgements that no longer match their citation",
        result.stale,
        "The gate fails on these too. The record moved and the acknowledgement did not, so "
        "it now vouches for nothing. Read what the paragraph cites now and either retarget "
        "the acknowledgement or delete it.",
    )
    lines += _section(
        "Markers that cannot be read as an acknowledgement",
        result.malformed,
        "A marker that cannot be parsed is reported rather than ignored, so a typo never "
        "silently stops acknowledging the thing it was written for.",
    )
    lines += _section(
        "Orphaned commits",
        result.orphans,
        "These SHAs are in no object in this repository. A squash or a rebase dropped them. "
        "Re-stamp the record from a committed HEAD. Do not create a tag to make one resolve.",
    )
    lines += _section(
        "Commits not reachable from the ref",
        result.unreachable,
        "These exist but are not ancestors — an unmerged lane, or another branch. "
        "Fine while the lane is open; not fine in a record that claims to be landed.",
    )
    lines += _section(
        "Cited paths that do not exist",
        result.missing_paths,
        "A report or source file a record points at is gone or was renamed.",
    )
    lines += _section(
        "External commits, by declaration",
        result.external,
        "Records that say in their own text that the commit is from elsewhere. Not orphans.",
    )
    lines += _section(
        "Set aside as somebody else's identifier",
        result.foreign if show_foreign else (),
        "A checksum, a record id, or another repository's object. Listed so a citation is "
        "never dropped without you being able to see it.",
    )
    lines += _section(
        "Hex tokens with no cue either way",
        result.unclassified,
        "Neither a commit word nor a checksum word sits before these. Read each one and "
        "either name what it is in the prose, or treat it as a commit and re-stamp it.",
    )
    if result.digests:
        lines.extend(
            [
                f"## Frozen digests ({len(result.digests)})",
                "",
                "Recompute each with the lane's own `challenger_sha256()`. "
                "This script does not know which file set a digest covers.",
                "",
            ]
        )
        lines.extend(f"- {cited}" for cited in result.digests)
        lines.append("")
    lines += _section(
        "Acknowledged where they are cited",
        result.acknowledged,
        "Each of these is reported above as well — acknowledging an item does not hide it. "
        "The reason is in the record, beside the citation.",
    )
    if result.clean:
        lines.extend(["Every citation resolves.", ""])
    lines.extend(
        [
            "The gate passes: every citation that does not resolve is acknowledged with a "
            "reason in the record that cites it."
            if result.gated
            else "The gate fails. See the sections above.",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    """Audit the records and print the result."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paths", nargs="*", default=list(DEFAULT_ROOTS))
    parser.add_argument("--ref", default="HEAD")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit 1 when a citation does not resolve and the record does not say why, "
        "when an acknowledgement no longer matches its citation, or when a marker is "
        "malformed. This is the CI gate.",
    )
    parser.add_argument(
        "--show-foreign", action="store_true", help="list the tokens read as foreign ids"
    )
    args = parser.parse_args(argv)

    result = audit(args.paths, args.ref)
    print(render(result, args.ref, show_foreign=args.show_foreign))
    return 1 if args.strict and not result.gated else 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Abort on any output that names a red or sealed path.

The token list is **derived from the resolver that decides the same question**, not written by hand
and not scraped from prose. Every corpus in ``data/registry.json`` is put through
``phos.genesis.tiercheck.resolve``, and the ones it refuses, or resolves to ``once``, become tokens.
The sealed manifest supplies the held-back halves the registry does not list, and the volume name
supplies the vault.

That derivation is the point. A corpus added to the registry and marked never-read is caught without
a change here; a list written by hand would be the fourth place the same fact lives and the first to
go stale. It is also why the first draft of this module was wrong: it read backticked names out of
the tier rule's text and swept in iterate-tier corpora like ``phos-icssim-dev4`` and non-corpora
like ``roles.toml``, which would have aborted harmless output. Asking the resolver is exact, because
the resolver is what gate (a) and ``genesis.py declare`` already ask.

A hit **aborts**. An agent that has printed the name of a sealed corpus has already been told that
corpus exists. On a hit, :func:`write_inbox` writes ``docs/method/INBOX.md`` naming the operation,
the role, the token and the line.

Two honest limits, stated rather than hidden: a corpus absent from both the registry and the
manifest is not a token, and matching prose can refuse a harmless mention ("the sealed batch is not
available"). It guards against the common accident; it is not a proof.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from phos.genesis.tiercheck import read_registry, resolve

#: The volume the sealed corpora live in (ADR 0464). Its name is a token even though it is not a
#: corpus: an agent that prints it has located the vault.
VOLUME_TOKEN: Final = "PHOSRED"

#: Where a hit is reported.
INBOX: Final = Path("docs/method/INBOX.md")

#: The manifest of sealed files (ADR 0464). Its first path component is a corpus name.
MANIFEST: Final = Path("docs/method/red-sealed-manifest.txt")

#: The phrase in the tier rule that introduces a paragraph of score-once corpora. Everything
#: backticked in such a paragraph is a corpus name, which is how the rule itself is written.
_SCORE_ONCE_MARKER: Final = "score once"

#: A backticked token in the tier rule. Narrow on purpose: a broad pattern over the rule's prose
#: matches English words, which is how the first draft of this module swept in `roles.toml` and
#: the iterate-tier development corpora.
_BACKTICKED_CORPUS: Final = re.compile(r"^`([a-z0-9][a-z0-9._-]*[a-z0-9])`$")


@dataclass(frozen=True)
class RedHit:
    """One token found in one line of one output.

    Attributes:
        token: The corpus name or volume name that matched.
        line: The line it appeared on, truncated for the report.
    """

    token: str
    line: str


@dataclass(frozen=True)
class RedCheck:
    """The result of scanning one output.

    Attributes:
        hits: Every match, in the order they appeared.
        tokens: The tokens searched for, so a clean result can be read as "nothing found among
            these" rather than "nothing was looked for".
        sources: The files and functions the token list came from.
    """

    hits: tuple[RedHit, ...]
    tokens: tuple[str, ...]
    sources: tuple[str, ...]

    @property
    def clean(self) -> bool:
        """Return whether the output named nothing that must not be named."""
        return not self.hits

    def summary(self) -> str:
        """Return a one-line description for a gate record."""
        if self.clean:
            return f"no red or sealed token in the output ({len(self.tokens)} tokens searched)"
        named = ", ".join(sorted({hit.token for hit in self.hits}))
        return f"ABORTED: the output names {named}"


def _manifest_corpora(manifest_text: str) -> set[str]:
    """Return the top-level directory names in the sealed manifest.

    Each manifest line is ``<sha256>  <relative path>``. The first path component is the corpus.

    Args:
        manifest_text: The text of the manifest.

    Returns:
        The directory names, lowercased for matching.
    """
    names: set[str] = set()
    for line in manifest_text.splitlines():
        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            continue
        first = parts[1].strip().replace("\\", "/").split("/")[0]
        if first and first not in {".", ".."}:
            names.add(first.lower())
    return names


def _rule_only_corpora(rule_text: str, known: frozenset[str]) -> set[str]:
    """Return score-once corpora the tier rule names but the registry does not list.

    The tier rule and ``data/registry.json`` are two lists of the same fact and they do not agree:
    ``phos-icssim-heldout2`` through ``heldout5`` are score-once in the rule and absent from the
    registry. The rule wins, because ``docs/rules/data-tiers.md`` is the lock and the registry is a
    description of where a corpus came from. So this reads the rule's score-once bullet and takes
    the corpus-shaped names in it, and the resolver stays the authority for everything the registry
    does list.

    The split is on **bullets**, not blank lines. The rule is a bullet list in which every bullet
    sits on consecutive lines, so a blank-line split puts "score once" and "iterate freely on" in
    one paragraph and sweeps the development corpora in with the sealed ones. That mistake was made
    here first and caught by a test: a false positive on ``phos-icssim-dev4-walk`` would abort the
    very corpus the ADR 0418 baseline is declared on.

    Args:
        rule_text: The text of ``docs/rules/data-tiers.md``.
        known: The names the registry already lists, so they are not counted twice.

    Returns:
        The additional names, lowercased.
    """
    found: set[str] = set()
    bullet = ""
    for line in rule_text.splitlines():
        if line.lstrip().startswith(("- ", "* ")):
            _collect_score_once(bullet, known, found)
            bullet = line
        else:
            bullet += f"\n{line}"
    _collect_score_once(bullet, known, found)
    return found


def _collect_score_once(bullet: str, known: frozenset[str], found: set[str]) -> None:
    """Add the corpus-shaped names in one bullet, if the bullet is about scoring once.

    Args:
        bullet: One bullet's text.
        known: The names the registry already lists.
        found: The set to add to, modified in place.
    """
    if _SCORE_ONCE_MARKER not in bullet.lower():
        return
    for raw in re.findall(r"`[^`]+`", bullet):
        match = _BACKTICKED_CORPUS.match(raw.strip())
        if match is None:
            continue
        name = match.group(1)
        # Prose backticks in the rule also wrap commands and vocabulary. A corpus name holds a
        # dash or a digit and is not a bare English word, which is enough to tell them apart.
        if ("-" in name or any(character.isdigit() for character in name)) and name not in known:
            found.add(name)


def red_tokens(root: Path) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return the tokens to refuse, and where they came from.

    Args:
        root: The repository root.

    Returns:
        ``(tokens, sources)``. ``tokens`` is sorted and lowercased, and holds every corpus the
        resolver refuses or places in the once tier, every sealed manifest directory, and the
        volume name.
    """
    tokens: set[str] = {VOLUME_TOKEN.lower()}
    sources: list[str] = ["phos.genesis.tiercheck.resolve"]

    registry = read_registry(root)
    for name in registry.names:
        verdict = resolve(root, name, "iterate")
        if verdict.refused or verdict.expected_tier == "once":
            tokens.add(name.lower())

    rule = root / "docs" / "rules" / "data-tiers.md"
    if rule.is_file():
        tokens |= _rule_only_corpora(rule.read_text(encoding="utf-8"), registry.names)
        sources.append("docs/rules/data-tiers.md (score-once paragraph)")

    manifest = root / MANIFEST
    if manifest.is_file():
        tokens |= _manifest_corpora(manifest.read_text(encoding="utf-8"))
        sources.append(MANIFEST.as_posix())

    # A one- or two-character token would match inside ordinary words. Every real corpus name is
    # longer, and dropping the short ones is the difference between a guard and a nuisance.
    return tuple(sorted(token for token in tokens if len(token) >= 3)), tuple(sources)


def _contains(text: str, token: str) -> bool:
    """Return whether ``text`` names ``token`` as a whole word.

    A plain substring match would refuse ``hai`` inside ``chair``. The boundary is a non-word
    character on each side, which allows ``/Volumes/PHOSRED/hai/`` and ``data/hai`` and refuses
    ``chair``.

    Args:
        text: The line.
        token: The token, lowercased.

    Returns:
        True when the line names the token.
    """
    pattern = rf"(?<![A-Za-z0-9_]){re.escape(token)}(?![A-Za-z0-9_])"
    return re.search(pattern, text.lower()) is not None


def scan(output: str, tokens: tuple[str, ...], sources: tuple[str, ...] = ()) -> RedCheck:
    """Scan one output for every token.

    Args:
        output: The agent's combined stdout and stderr.
        tokens: The tokens to refuse.
        sources: Where the tokens came from, recorded for the report.

    Returns:
        The check. ``hits`` is empty when the output is clean.
    """
    hits: list[RedHit] = []
    for raw in output.splitlines():
        line = raw.strip()
        if not line:
            continue
        for token in tokens:
            if _contains(line, token):
                hits.append(RedHit(token=token, line=line[:300]))
    return RedCheck(hits=tuple(hits), tokens=tokens, sources=sources)


def check_output(root: Path, output: str) -> RedCheck:
    """Scan ``output`` against the tokens this repository's rules define.

    Args:
        root: The repository root.
        output: The combined stdout and stderr of one agent turn.

    Returns:
        The check.
    """
    tokens, sources = red_tokens(root)
    return scan(output, tokens, sources)


def write_inbox(
    root: Path,
    *,
    operation: str,
    role: str,
    check: RedCheck,
    runtime: str = "unknown",
) -> Path:
    """Write ``docs/method/INBOX.md`` naming what tripped the abort.

    The file is written whole rather than appended to. An INBOX that accumulates every abort from
    every operation becomes a log nobody reads, and the instruction is that a human sees exactly
    what is missing now. If a file is already there and was not written by FORGE, it is kept below
    a separator rather than silently destroyed.

    Args:
        root: The repository root.
        operation: The operation id.
        role: The role whose output tripped it.
        check: The failed check.
        runtime: The runtime that produced the output.

    Returns:
        The path written.
    """
    path = root / INBOX
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).isoformat(timespec="seconds")
    named = ", ".join(sorted({hit.token for hit in check.hits})) or "nothing"

    lines = [
        "# INBOX",
        "",
        "Written by FORGE. A human needs to read this.",
        "",
        f"- When: {stamp}",
        f"- Operation: {operation}",
        f"- Role: {role}",
        f"- Runtime: {runtime}",
        f"- What happened: the output named {named}, which no agent output may name.",
        "- What FORGE did: stopped the operation. Nothing was recorded as a result.",
        "",
        "## The lines that matched",
        "",
    ]
    lines.extend(f"- `{hit.token}` in: {hit.line}" for hit in check.hits)
    lines.append("")

    previous = ""
    if path.is_file():
        existing = path.read_text(encoding="utf-8")
        if not existing.lstrip().startswith("# INBOX"):
            previous = f"\n---\n\n## Previous contents\n\n{existing}"
    path.write_text("\n".join(lines) + previous, encoding="utf-8")
    return path

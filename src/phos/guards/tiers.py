"""The data-tier guard: does this tool call name a corpus, path or seed it may not touch?

``docs/rules/data-tiers.md`` sets the tiers and this module parses that file. It invents no names,
so a corpus added to the rule is guarded from the moment the sentence lands, and a corpus removed
stops being guarded without anyone editing code.

The subtlety worth keeping is the longest-match rule. ``hai-20.07`` contains ``hai``, and ``hai``
is red while ``hai-20.07`` is green, so a plain substring test would refuse the development corpus.
The longest matching name wins, which is what makes ``hai-20.07`` read as development and
``hai-23.05`` read as validation.

Lifted from ``.claude/hooks/red_tier.py`` without a change of behaviour, so that the Cursor hook
and the Claude Code hook ask the same function (ADR 0414).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from phos.guards.subject import GuardVerdict, Subject

_BULLET: Final = re.compile(r"^- \*\*(.+?)\*\*(.*?)(?=^- \*\*|\Z)", re.MULTILINE | re.DOTALL)
_TOKEN: Final = re.compile(r"`([^`]+)`")
_SEED_RANGE: Final = re.compile("(\\d{5})\\s*[\u2013-]\\s*(\\d{5})")
_SEED: Final = re.compile(r"\b(\d{5})\b")

#: How each tier's bullet begins in the rule file.
RED_LEADS: Final = ("never read", "never touch")
AMBER_LEADS: Final = ("score once",)
GREEN_LEADS: Final = ("iterate freely",)


@dataclass(frozen=True)
class Tiers:
    """The tier names and held-out seed ranges parsed from the rule.

    Attributes:
        red: Names that may never be read, scored or iterated on.
        amber: Names that may be scored once after a committed declaration.
        green: Names that may be iterated on freely.
        seed_ranges: Inclusive held-out seed ranges, as ``(low, high)``.
        sentences: The rule's own sentence naming each tier, by name, so a message can quote the
            text that refused rather than paraphrasing it.
    """

    red: frozenset[str]
    amber: frozenset[str]
    green: frozenset[str]
    seed_ranges: tuple[tuple[int, int], ...]
    sentences: Mapping[str, str] = field(default_factory=dict)

    def tier_of(self, name: str) -> str | None:
        """Return ``red``, ``amber`` or ``green`` for an exact name, or ``None`` if unnamed.

        Matching is exact and case-insensitive. A corpus the rule does not name has no tier, and
        returning ``None`` rather than a default is what lets the caller refuse it: a tier the
        rule did not assign cannot be asserted by a declaration.

        Args:
            name: The corpus name as the declaration names it.

        Returns:
            The tier, or ``None`` when the rule does not name this corpus.
        """
        wanted = name.strip().lower()
        for tier, names in (("red", self.red), ("amber", self.amber), ("green", self.green)):
            if any(other.lower() == wanted for other in names):
                return tier
        return None


def parse(rule_text: str) -> Tiers:
    """Return the tiers named by the data-tier rule.

    Args:
        rule_text: The contents of ``docs/rules/data-tiers.md``.

    Returns:
        The parsed tiers. Every set is empty when the rule cannot be read, and the caller treats
        that as "say nothing" rather than as "nothing is red".
    """
    names: dict[str, set[str]] = {"red": set(), "amber": set(), "green": set()}
    ranges: list[tuple[int, int]] = []
    sentences: dict[str, str] = {}
    for lead, body in _BULLET.findall(rule_text):
        lowered = lead.lower()
        tier = next(
            (
                key
                for key, leads in (
                    ("red", RED_LEADS),
                    ("amber", AMBER_LEADS),
                    ("green", GREEN_LEADS),
                )
                if any(lowered.startswith(start) for start in leads)
            ),
            "",
        )
        if not tier:
            continue
        named = {token.strip() for token in _TOKEN.findall(body) if token.strip()}
        names[tier] |= named
        if tier == "red":
            ranges += [(int(low), int(high)) for low, high in _SEED_RANGE.findall(body)]
        for name in named:
            sentences.setdefault(name, bullet_sentence(lead, body))
    return Tiers(
        red=frozenset(names["red"]),
        amber=frozenset(names["amber"]),
        green=frozenset(names["green"]),
        seed_ranges=tuple(ranges),
        sentences=sentences,
    )


def bullet_sentence(lead: str, body: str) -> str:
    """Return one tier bullet as a single quotable line: its bold lead and its first sentence.

    A tier bullet carries exceptions in its later sentences ("Three exceptions, each scored once
    …"), and a message that quoted the whole bullet would bury the rule in its own caveats. The
    lead and the first sentence are what name the prohibition.

    Args:
        lead: The bold lead text, without the asterisks.
        body: The rest of the bullet.

    Returns:
        The lead and the bullet's first sentence, on one line.
    """
    first = re.split(r"(?<=\.)\s+(?=[A-Z])", " ".join(body.split()), maxsplit=1)[0]
    return f"{' '.join(lead.split())} {first}".strip()


def reasons_for(text: str, tiers: Tiers) -> list[str]:
    """Return why ``text`` is red tier, longest name first and a longer green name winning.

    Args:
        text: A path, command or other string from the tool call.
        tiers: The parsed tiers.

    Returns:
        One reason per red name or held-out seed found, sorted and deduplicated.
    """
    lowered = text.lower()
    hits = sorted((name for name in tiers.red if name.lower() in lowered), key=len, reverse=True)
    found: list[str] = []
    for name in hits:
        longer = [
            other
            for other in tiers.green | tiers.amber
            if other.lower() in lowered and len(other) > len(name)
        ]
        if longer:
            continue
        found.append(f"`{name}` is red tier")
    for seed in (int(match) for match in _SEED.findall(text)):
        for low, high in tiers.seed_ranges:
            if low <= seed <= high:
                found.append(f"seed {seed} is inside the held-out range {low}-{high}")
    return sorted(set(found))


def read_rule(root: Path, name: str) -> str:
    """Return the text of one rule file under ``docs/rules/``, or an empty string.

    Args:
        root: The repository root.
        name: The rule's file name, for example ``data-tiers.md``.

    Returns:
        The file's text, or ``""`` when it is absent. An absent rule silences the guard that
        reads it rather than inventing a prohibition.
    """
    path = root / "docs" / "rules" / name
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def check(subject: Subject) -> GuardVerdict | None:
    """Return a verdict when the tool call names red-tier data.

    Args:
        subject: The normalised tool call.

    Returns:
        The verdict, or ``None`` when nothing in the call is red tier.
    """
    tiers = parse(read_rule(subject.root, "data-tiers.md"))
    if not tiers.red:
        return None
    found = sorted({reason for text in subject.texts for reason in reasons_for(text, tiers)})
    if not found:
        return None
    return GuardVerdict(
        rule="docs/rules/data-tiers.md — never read, score or iterate on the validation corpora",
        headline="a tool call naming red-tier data",
        detail=(
            *found,
            "ADR 0117's gate look 1 is spent (ADR 0143); a new look needs Elijah to authorise it",
            f"tool: {subject.tool or '?'}",
        ),
        guard="red_tier",
    )

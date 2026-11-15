"""Which tier a declared corpus is in, resolved from the rule file rather than from the payload.

ADR 0412 said a ``never``-tier corpus stays unread because "the record refuses to declare one". It
did not. The audit declared a run on ``hai-21.03`` — named in ``docs/rules/data-tiers.md`` under
"**Never read, score or iterate on**" — by writing ``"tier": "iterate"`` in the payload, and GENESIS
accepted it. The model refused the *string* ``never``; nothing looked at the *corpus*.

This module closes that. ``resolve`` reads the corpus name out of a declaration and asks the rule
file what it is, using the parser the ``red_tier`` guard already uses (``phos.guards.tiers``), so
there is one reading of the rule and not two. Three answers refuse:

* the rule names the corpus never-read, whatever the declaration says its tier is;
* the rule names no tier and ``data/registry.json`` does not list the corpus — an unknown corpus is
  a refusal, not a default (ADR 0412, decision 8);
* the rule cannot be read at all, because then every corpus is unknown.

A corpus the rule does not name but the registry does is the rule's own catch-all: "any newly
registered unseen corpus" is scored **once**, so its tier is ``once`` and its declaration must say
so. Nothing here infers a tier from a registry ``role`` field — that would be the registry
overruling the rule, and the rule wins.

The difference between this and ``guards.tiers.check`` is the direction of the safe answer, and it
is deliberate. That guard is advisory and warns about a tool call, so a missing rule silences it —
it must not block every tool call the day a file is renamed. This is a declaration, where a corpus
nobody can classify has not been classified as safe, so it is refused.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, get_args

from phos.genesis.records import Tier
from phos.guards import tiers

#: The rule this resolves against, relative to the checkout root.
RULE_FILE: Final = "data-tiers.md"

#: The registry of corpora, relative to the checkout root.
REGISTRY: Final = Path("data") / "registry.json"

#: The phrase in the rule that puts every registered corpus it does not name in the ``score once``
#: tier. Quoted rather than paraphrased, and asserted against the real file by the tests, so the
#: catch-all cannot quietly disappear from the rule while this module still claims it.
NEWLY_REGISTERED: Final = "any newly registered unseen corpus"

#: The declaration's tier vocabulary, mapped onto the rule's. Both are needed: a record stores
#: ``iterate``/``once``/``never`` and the rule file says green/amber/red, and the mapping is the
#: only place the two meet. ``Tier`` is the record's own ``Literal``, so a tier added to the model
#: without a rule name here is a test failure rather than a silent hole.
DECLARED_TIERS: Final[dict[str, str]] = {
    "iterate": "green",
    "once": "amber",
    "never": "red",
}

#: The rule's tier names, and whether a declaration may be made on one at all.
_DECLARABLE: Final[dict[str, bool]] = {"green": True, "amber": True, "red": False}


@dataclass(frozen=True)
class Registry:
    """The corpus names ``data/registry.json`` lists.

    Attributes:
        names: Every ``datasets[].name``.
        problem: Why the registry could not be read, or ``""`` when it could. A problem is kept
            rather than raised because an unreadable registry is not the corpus's fault, and the
            rule file may still name the corpus.
    """

    names: frozenset[str]
    problem: str = ""


@dataclass(frozen=True)
class TierVerdict:
    """What the rule says about one declared corpus.

    Attributes:
        corpus: The name as the declaration gave it.
        tier: ``red``, ``amber`` or ``green``; ``None`` when the rule does not name the corpus.
        expected_tier: That tier in the declaration's vocabulary (``never``/``once``/``iterate``),
            or ``None`` when there is no tier to expect.
        declared: The tier the declaration asserted, or ``None`` when it was not consulted.
        sentence: The rule's own words that decide this, quoted.
        reasons: Why this corpus may not be declared. Empty means it may.
        detail: The full message, one line per entry, naming the rule and the sentence.
    """

    corpus: str
    tier: str | None
    expected_tier: str | None
    declared: str | None
    sentence: str
    reasons: tuple[str, ...] = ()
    detail: tuple[str, ...] = field(default=())

    @property
    def refused(self) -> bool:
        """Return whether the corpus may not be declared at all."""
        return bool(self.reasons)

    @property
    def disagrees(self) -> bool:
        """Return whether the declared tier contradicts the tier the rule resolves.

        This is the gate's question rather than ``declare``'s: a declaration naming the wrong tier
        is still a declaration, but it must not be allowed to run. A refusal always dominates, so
        a corpus that may not be declared does not also report a disagreement.
        """
        if self.refused or self.declared is None or self.expected_tier is None:
            return False
        return self.declared != self.expected_tier


def read_registry(root: Path) -> Registry:
    """Return the corpus names ``data/registry.json`` lists under ``root``.

    Args:
        root: The checkout root.

    Returns:
        The names and, when the file is absent or unreadable, why.
    """
    path = root / REGISTRY
    if not path.is_file():
        return Registry(frozenset(), f"`{REGISTRY.as_posix()}` cannot be read: no such file")
    try:
        loaded: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return Registry(frozenset(), f"`{REGISTRY.as_posix()}` will not parse as JSON")
    entries = loaded.get("datasets") if isinstance(loaded, dict) else None
    if not isinstance(entries, list):
        return Registry(frozenset(), f"`{REGISTRY.as_posix()}` has no `datasets` array")
    names = {
        str(entry["name"]).strip()
        for entry in entries
        if isinstance(entry, dict) and str(entry.get("name", "")).strip()
    }
    return Registry(frozenset(names))


def _unknown(root: Path, corpus: str, registry: Registry, declared: str | None) -> TierVerdict:
    """Return the verdict for a corpus neither the rule nor the registry names."""
    sentence = f"`{corpus}` is named in no tier of {RULE_FILE}, and no registry entry lists it"
    detail = [
        f"docs/rules/{RULE_FILE} — {sentence}",
        "an unknown corpus is a refusal, not a default (ADR 0412, decision 8): a tier the rule "
        "did not assign cannot be asserted by a declaration",
    ]
    if registry.problem:
        detail.append(registry.problem)
    else:
        detail.append(
            f"`{REGISTRY.as_posix()}` is readable and lists {len(registry.names)} corpora, "
            f"none of them {corpus!r}"
        )
    detail.append(
        "name the corpus in docs/rules/data-tiers.md, or register it, before declaring a run on it"
    )
    return TierVerdict(
        corpus=corpus,
        tier=None,
        expected_tier=None,
        declared=declared,
        sentence=sentence,
        reasons=(f"`{corpus}` is not a corpus this repository knows",),
        detail=tuple(detail),
    )


def resolve(root: Path, corpus: str, declared: str | None = None) -> TierVerdict:
    """Return what the data-tier rule says about declaring a run on ``corpus``.

    Args:
        root: The checkout root, holding ``docs/rules/data-tiers.md`` and ``data/registry.json``.
        corpus: The corpus name as the declaration gives it.
        declared: The tier the declaration asserts, or ``None`` to ask only what the rule says.

    Returns:
        The verdict. ``refused`` is true when the rule names the corpus never-read, when nothing
        can classify it, or when the rule cannot be read. ``disagrees`` is true when a declared
        tier was supplied and it is not the one the rule resolves.
    """
    rule_text = tiers.read_rule(root, RULE_FILE)
    if not rule_text:
        sentence = f"`docs/rules/{RULE_FILE}` cannot be read, so no corpus has a tier"
        return TierVerdict(
            corpus=corpus,
            tier=None,
            expected_tier=None,
            declared=declared,
            sentence=sentence,
            reasons=("the data-tier rule cannot be read, so this corpus cannot be classified",),
            detail=(
                f"docs/rules/{RULE_FILE} — {sentence}",
                "a corpus nobody can classify has not been classified as safe",
                "restore the rule file; a declaration cannot substitute for it",
            ),
        )

    parsed = tiers.parse(rule_text)
    sentence = parsed.sentences.get(corpus, "")
    tier = parsed.tier_of(corpus)

    if tier is not None:
        expected = next(
            (name for name, rule_name in DECLARED_TIERS.items() if rule_name == tier), None
        )
        if _DECLARABLE.get(tier, False):
            return TierVerdict(
                corpus=corpus,
                tier=tier,
                expected_tier=expected,
                declared=declared,
                sentence=sentence,
                detail=(f"docs/rules/{RULE_FILE} — {sentence}",),
            )
        return TierVerdict(
            corpus=corpus,
            tier=tier,
            expected_tier=expected,
            declared=declared,
            sentence=sentence,
            reasons=(f"`{corpus}` is never-read in docs/rules/{RULE_FILE}",),
            detail=(
                f"docs/rules/{RULE_FILE} — {sentence}",
                f"the rule names {corpus!r} in the never-read tier; the declaration's own "
                f"`tier` field cannot overrule it, and said {declared!r}"
                if declared
                else f"the rule names {corpus!r} in the never-read tier",
                "a run on it cannot be declared; ADR 0117's gate look 1 is spent (ADR 0143) and a "
                "new look needs Elijah to authorise it",
            ),
        )

    registry = read_registry(root)
    if corpus.strip() in registry.names:
        once_sentence = _catch_all_sentence(parsed)
        return TierVerdict(
            corpus=corpus,
            tier="amber",
            expected_tier="once",
            declared=declared,
            sentence=once_sentence,
            detail=(
                f"docs/rules/{RULE_FILE} — {once_sentence}",
                f"`{corpus}` is registered in `{REGISTRY.as_posix()}` and named in no tier, so "
                "the rule's catch-all puts it in the score-once tier",
                "declare it as `once`: scored once after a committed declaration, and a second "
                "look is not available",
            ),
        )

    return _unknown(root, corpus, registry, declared)


def disagreement(verdict: TierVerdict) -> str:
    """Return the line naming what the declaration claimed against what the rule resolves.

    A refusal that says only what the rule says leaves a reader guessing which of the two was
    believed. This is the sentence the gate shows, and it is separate from ``detail`` so that a
    caller may show it alone.

    Args:
        verdict: The resolved verdict, which must carry both tiers.

    Returns:
        One line, or ``""`` when there is no declared tier to compare.
    """
    if verdict.declared is None or verdict.expected_tier is None:
        return ""
    if not verdict.disagrees:
        return f"the declaration says {verdict.declared!r}, which the rule agrees with"
    return (
        f"the declaration says `tier: {verdict.declared}`, the rule resolves "
        f"`{verdict.expected_tier}` from the corpus name"
    )


def _catch_all_sentence(parsed: tiers.Tiers) -> str:
    """Return the rule's own sentence carrying the newly-registered catch-all.

    Args:
        parsed: The parsed rule.

    Returns:
        The sentence that contains ``NEWLY_REGISTERED``, or the phrase itself when the sentence
        cannot be found, so a message always quotes something the reader can search for.
    """
    for sentence in parsed.sentences.values():
        if NEWLY_REGISTERED in sentence:
            return sentence
    return NEWLY_REGISTERED


def tier_vocabulary_is_mapped() -> tuple[str, ...]:
    """Return the record's tier values that ``DECLARED_TIERS`` does not map.

    Returns:
        The unmapped values. An empty tuple means the model and this module agree, which is what
        ``tests/genesis/test_tiercheck.py`` asserts so that a tier added to ``Tier`` cannot become
        a corpus this module silently refuses to classify.
    """
    return tuple(value for value in get_args(Tier) if value not in DECLARED_TIERS)

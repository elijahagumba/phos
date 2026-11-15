"""The corpus is resolved against the rule file, and the rule file is what refuses.

ADR 0412 claimed a `never`-tier corpus could not be declared. It could, and the audit proved it by
declaring a run on `hai-21.03` with `"tier": "iterate"`: the model refused the *string* `never` and
never looked at the *corpus*. The test whose absence that was is `TestTheRuleRefusesItsOwnNames`
below, which reads `docs/rules/data-tiers.md` and asserts every corpus it names as never-read is
refused at declaration however the `tier` field is filled in.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import get_args

import pytest
from tests.lab_only import RULES_ABSENT_REASON

from phos.genesis.records import Tier
from phos.genesis.tiercheck import (
    DECLARED_TIERS,
    NEWLY_REGISTERED,
    REGISTRY,
    RULE_FILE,
    _catch_all_sentence,
    read_registry,
    resolve,
    tier_vocabulary_is_mapped,
)
from phos.guards import tiers

#: The real repository root, so the table below reads the rule this project actually ships.
REPO = Path(__file__).resolve().parents[2]

# A `lab_only` marker cannot carry this module, and the reason is worth stating. The parametrised
# tables below call `named_in()` inside their `@pytest.mark.parametrize` decorators, so the rule
# file is read while the module is being **imported** — before `pytest_collection_modifyitems` runs
# and before any marker exists to be honoured. In the public tree, where `docs/rules/` is a
# forbidden path, that import raises and takes the whole collection down with it: the public suite
# reported one collection error and two cascading failures in `tests/eval/test_slow_marker.py`,
# which shells out to `pytest --collect-only` and asserts a clean exit (ADR 0440). A module-level
# skip is the only thing that runs early enough. It is the same condition the marker expresses.
if not (REPO / "docs" / "rules" / RULE_FILE).is_file():  # pragma: no cover - public tree only
    pytest.skip(
        f"docs/rules/{RULE_FILE} is absent. {RULES_ABSENT_REASON}",
        allow_module_level=True,
    )


def the_rule_text() -> str:
    """Return the shipped data-tier rule, read from the repository rather than restated here."""
    return (REPO / "docs" / "rules" / RULE_FILE).read_text(encoding="utf-8")


def named_in(tier: str) -> list[str]:
    """Return every name the shipped rule puts in ``tier``, sorted for a stable table."""
    return sorted(getattr(tiers.parse(the_rule_text()), tier))


def a_checkout(tmp_path: Path, rule: str | None = None, registry: object = None) -> Path:
    """Return a directory holding a rule file and a registry, as a checkout would."""
    (tmp_path / "docs" / "rules").mkdir(parents=True)
    (tmp_path / "docs" / "rules" / RULE_FILE).write_text(
        the_rule_text() if rule is None else rule, encoding="utf-8"
    )
    if registry is not False:
        (tmp_path / "data").mkdir(parents=True, exist_ok=True)
        (tmp_path / "data" / "registry.json").write_text(
            json.dumps({"datasets": []} if registry is None else registry), encoding="utf-8"
        )
    return tmp_path


class TestTheRuleRefusesItsOwnNames:
    """The table this phase exists for: the rule's never-read names are refused at declaration."""

    def test_the_rule_names_at_least_one_never_read_corpus(self) -> None:
        # A table over an empty set would pass while proving nothing.
        assert named_in("red") != []
        assert named_in("green") != []

    @pytest.mark.parametrize("corpus", named_in("red"))
    def test_every_never_read_name_is_refused(self, tmp_path: Path, corpus: str) -> None:
        verdict = resolve(a_checkout(tmp_path), corpus)
        assert verdict.refused, f"{corpus} is named never-read and was not refused"

    @pytest.mark.parametrize("declared", sorted(DECLARED_TIERS.values()))
    @pytest.mark.parametrize("corpus", named_in("red"))
    def test_the_tier_field_cannot_rescue_a_never_read_name(
        self, tmp_path: Path, corpus: str, declared: str
    ) -> None:
        # This is the audit's hole exactly: the payload says "iterate", the rule says never.
        assert resolve(a_checkout(tmp_path), corpus, declared=declared).refused

    @pytest.mark.parametrize("corpus", named_in("amber"))
    def test_every_score_once_name_resolves_to_once(self, tmp_path: Path, corpus: str) -> None:
        verdict = resolve(a_checkout(tmp_path), corpus)
        assert verdict.tier == "amber"
        assert verdict.expected_tier == "once"
        assert not verdict.refused

    @pytest.mark.parametrize("corpus", named_in("green"))
    def test_every_iterate_name_resolves_to_iterate(self, tmp_path: Path, corpus: str) -> None:
        verdict = resolve(a_checkout(tmp_path), corpus)
        assert verdict.tier == "green"
        assert verdict.expected_tier == "iterate"
        assert not verdict.refused

    def test_no_name_is_in_two_tiers(self) -> None:
        parsed = tiers.parse(the_rule_text())
        assert not (parsed.red & parsed.amber)
        assert not (parsed.red & parsed.green)
        assert not (parsed.amber & parsed.green)


class TestLongestMatchIsNotUsedForACorpus:
    """A declaration names one corpus exactly; only a tool-call path needs longest-match."""

    def test_the_development_hai_corpus_is_not_refused_by_the_validation_one(
        self, tmp_path: Path
    ) -> None:
        # `hai` is red and `hai-20.07` is green. A substring test would refuse the second.
        assert resolve(a_checkout(tmp_path), "hai-20.07").tier == "green"

    def test_a_partial_name_is_not_a_name(self, tmp_path: Path) -> None:
        assert resolve(a_checkout(tmp_path), "hai-20").tier is None

    def test_matching_is_case_insensitive(self, tmp_path: Path) -> None:
        assert resolve(a_checkout(tmp_path), "HAI-21.03").refused


class TestAnUnknownCorpusIsARefusal:
    def test_a_corpus_named_nowhere_is_refused(self, tmp_path: Path) -> None:
        verdict = resolve(a_checkout(tmp_path), "corpus-that-does-not-exist")
        assert verdict.refused
        assert verdict.tier is None

    def test_the_refusal_names_the_rule_file_and_says_what_is_missing(self, tmp_path: Path) -> None:
        verdict = resolve(a_checkout(tmp_path), "corpus-that-does-not-exist")
        assert any(RULE_FILE in line for line in verdict.detail)
        assert any("registry.json" in line for line in verdict.detail)

    def test_an_unregistered_corpus_the_rule_never_names_is_refused(self, tmp_path: Path) -> None:
        # Registered is what makes the catch-all apply; unregistered is nothing at all.
        registry = {"datasets": [{"name": "some-other-corpus"}]}
        checkout = a_checkout(tmp_path, registry=registry)
        assert resolve(checkout, "corpus-that-does-not-exist").refused

    def test_the_rule_settles_it_before_the_registry_is_consulted(self, tmp_path: Path) -> None:
        registry = {"datasets": [{"name": "hai-21.03", "role": "development"}]}
        assert resolve(a_checkout(tmp_path, registry=registry), "hai-21.03").refused

    def test_a_missing_registry_still_lets_the_rule_name_its_corpora(self, tmp_path: Path) -> None:
        checkout = a_checkout(tmp_path, registry=False)
        assert resolve(checkout, "phos-icssim-dev4").tier == "green"
        assert resolve(checkout, "corpus-that-does-not-exist").refused


class TestARegisteredCorpusTheRuleDoesNotName:
    """The rule's own catch-all: "any newly registered unseen corpus" is scored once."""

    def test_a_registered_unnamed_corpus_resolves_to_once(self, tmp_path: Path) -> None:
        registry = {"datasets": [{"name": "kelmarsh"}]}
        verdict = resolve(a_checkout(tmp_path, registry=registry), "kelmarsh")
        assert verdict.tier == "amber"
        assert verdict.expected_tier == "once"
        assert not verdict.refused

    def test_the_catch_all_sentence_is_quoted_rather_than_paraphrased(self, tmp_path: Path) -> None:
        registry = {"datasets": [{"name": "kelmarsh"}]}
        verdict = resolve(a_checkout(tmp_path, registry=registry), "kelmarsh")
        assert NEWLY_REGISTERED in verdict.sentence
        assert NEWLY_REGISTERED in the_rule_text()

    def test_a_registry_role_cannot_promote_a_corpus_to_iterate(self, tmp_path: Path) -> None:
        # Inferring a tier from `role` would let the registry overrule the rule file.
        registry = {"datasets": [{"name": "kelmarsh", "role": "development"}]}
        assert resolve(a_checkout(tmp_path, registry=registry), "kelmarsh").expected_tier == "once"

    def test_a_declaration_of_iterate_on_it_is_a_disagreement(self, tmp_path: Path) -> None:
        registry = {"datasets": [{"name": "kelmarsh", "role": "development"}]}
        verdict = resolve(a_checkout(tmp_path, registry=registry), "kelmarsh", declared="iterate")
        assert not verdict.refused, "declare does not police the tier; the gate does"
        assert verdict.disagrees


class TestDeclaredTierDisagreement:
    @pytest.mark.parametrize(
        ("corpus", "declared", "agrees"),
        [
            ("phos-icssim-dev4", "iterate", True),
            ("phos-icssim-dev4", "once", False),
            ("phos-icssim-heldout", "once", True),
            ("phos-icssim-heldout", "iterate", False),
        ],
    )
    def test_the_gate_s_question_is_answered_here(
        self, tmp_path: Path, corpus: str, declared: str, agrees: bool
    ) -> None:
        verdict = resolve(a_checkout(tmp_path), corpus, declared=declared)
        assert verdict.disagrees is not agrees

    def test_with_no_declared_tier_there_is_nothing_to_disagree_with(self, tmp_path: Path) -> None:
        assert not resolve(a_checkout(tmp_path), "phos-icssim-dev4").disagrees


class TestTheRuleCannotBeRead:
    def test_a_missing_rule_resolves_nothing_and_refuses(self, tmp_path: Path) -> None:
        verdict = resolve(tmp_path, "phos-icssim-dev4")
        assert verdict.refused
        assert verdict.tier is None
        assert any("cannot be read" in line for line in verdict.detail)

    def test_a_rule_naming_nothing_refuses_everything(self, tmp_path: Path) -> None:
        verdict = resolve(a_checkout(tmp_path, rule="# Data tiers\n"), "phos-icssim-dev4")
        assert verdict.refused


class TestRegistry:
    def test_the_names_come_out_of_the_datasets_array(self, tmp_path: Path) -> None:
        registry = read_registry(a_checkout(tmp_path, registry={"datasets": [{"name": "a"}]}))
        assert registry.names == frozenset({"a"})
        assert registry.problem == ""

    def test_a_missing_registry_is_reported_rather_than_treated_as_empty_evidence(
        self, tmp_path: Path
    ) -> None:
        registry = read_registry(tmp_path)
        assert registry.names == frozenset()
        assert "cannot be read" in registry.problem

    def test_a_malformed_registry_is_reported(self, tmp_path: Path) -> None:
        (tmp_path / "data").mkdir(parents=True)
        (tmp_path / "data" / "registry.json").write_text("{not json", encoding="utf-8")
        registry = read_registry(tmp_path)
        assert registry.names == frozenset()
        assert "will not parse" in registry.problem

    def test_the_entries_without_a_name_are_skipped(self, tmp_path: Path) -> None:
        registry = read_registry(
            a_checkout(tmp_path, registry={"datasets": [{"name": "a"}, {"role": "x"}, "junk"]})
        )
        assert registry.names == frozenset({"a"})

    def test_a_registry_that_is_not_an_object_is_reported(self, tmp_path: Path) -> None:
        assert "no `datasets` array" in read_registry(a_checkout(tmp_path, registry=[])).problem

    def test_a_registry_without_a_datasets_array_is_reported(self, tmp_path: Path) -> None:
        assert "no `datasets` array" in read_registry(a_checkout(tmp_path, registry={})).problem

    def test_it_reads_the_shipped_registry(self) -> None:
        assert "batadal" in read_registry(REPO).names

    def test_the_rule_file_path_is_the_one_the_guard_reads(self) -> None:
        assert (REPO / "docs" / "rules" / RULE_FILE).is_file()
        assert REGISTRY == Path("data") / "registry.json"


class TestTheVocabularyCannotDrift:
    """A tier the record can carry must map to a rule tier, not become an unclassified hole."""

    def test_every_declared_tier_is_mapped_to_a_rule_tier(self) -> None:
        assert tier_vocabulary_is_mapped() == (), (
            "records can carry a tier this module does not map, so a corpus could be declared "
            "on a vocabulary word the rule never names"
        )

    def test_the_mapping_covers_exactly_the_record_s_vocabulary(self) -> None:
        assert set(DECLARED_TIERS) == set(get_args(Tier))

    def test_the_sets_in_the_file_are_the_ones_the_mapping_names(self) -> None:
        parsed = tiers.parse(the_rule_text())
        assert set(DECLARED_TIERS.values()) == {
            "red",
            "amber",
            "green",
        }, "the mapping names a tier the rule file does not have"
        assert parsed.red and parsed.amber and parsed.green

    def test_the_catch_all_can_be_found_in_the_shipped_rule(self) -> None:
        # `_catch_all_sentence` falls back to the bare phrase when the sentence is missing, which
        # would still read sensibly while quoting no rule at all. This asserts the real lookup.
        parsed = tiers.parse(the_rule_text())
        found = _catch_all_sentence(parsed)
        assert NEWLY_REGISTERED in found
        assert found != NEWLY_REGISTERED, "the phrase was quoted without the sentence around it"

    def test_the_fallback_still_names_the_phrase(self) -> None:
        empty = tiers.parse("- **Iterate freely on** `x`.\n")
        assert _catch_all_sentence(empty) == NEWLY_REGISTERED

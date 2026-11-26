"""Tests for the red and sealed path abort.

The interesting cases are the two failure modes of any such guard: a token list so broad it refuses
honest work, and a token list so narrow it misses the batch it exists to protect. Both are tested
against the real rule files, because that is where the tokens come from.

That is also why two of them are marked ``lab_only``: the tokens they check for exist only in
``docs/rules/data-tiers.md``, which symlinks into the ``.cursor/rules/`` that
``public/manifest.toml`` forbids. In the public tree the rule is absent, so those tokens are
genuinely not in the list and the test would be reporting the export split rather than a hole in
the guard. The rest of the file does not need the rule and runs everywhere.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from phos.forge import redline
from phos.forge.redline import RedCheck, RedHit, check_output, red_tokens, scan, write_inbox


def test_the_corpus_the_baseline_uses_is_not_a_token(repo: Path) -> None:
    """ADR 0418's corpus is iterate tier, so its name must not trip the guard.

    An earlier draft derived tokens from backticked names in the tier rule and did refuse this,
    which would have aborted the one backtest Step 5 depends on.
    """
    tokens, _ = red_tokens(repo)
    assert "phos-icssim-dev4-walk" not in tokens


def test_a_sealed_corpus_is_a_token(repo: Path) -> None:
    tokens, _ = red_tokens(repo)
    assert "hai" in tokens
    assert "batadal" in tokens


@pytest.mark.lab_only
def test_a_score_once_corpus_named_only_in_the_rule_is_a_token(repo: Path) -> None:
    """``phos-icssim-heldout2`` is in the tier rule and not in the registry.

    The rule is the lock, so it wins, and the guard must catch what the rule names.
    """
    tokens, _ = red_tokens(repo)
    assert "phos-icssim-heldout2" in tokens
    assert "phos-icssim-heldout5" in tokens


def test_the_volume_name_is_a_token(repo: Path) -> None:
    tokens, _ = red_tokens(repo)
    assert "phosred" in tokens


def test_the_sources_are_recorded(repo: Path) -> None:
    _, sources = red_tokens(repo)
    assert any("tiercheck" in source for source in sources)


def test_clean_output_passes(repo: Path) -> None:
    check = check_output(repo, "the sequential column missed no walk")
    assert check.clean
    assert check.hits == ()
    assert check.tokens, "a clean result must still say what was searched for"


def test_naming_a_sealed_path_aborts(repo: Path) -> None:
    check = check_output(repo, "reading /Volumes/PHOSRED/hai/train.csv")
    assert not check.clean
    named = {hit.token for hit in check.hits}
    assert "hai" in named
    assert "phosred" in named


def test_a_word_containing_a_token_does_not_match(repo: Path) -> None:
    """``chair`` contains ``hai`` and must not trip the guard."""
    check = check_output(repo, "please take a chair")
    assert check.clean


def test_a_sealed_name_as_a_whole_word_matches(repo: Path) -> None:
    check = check_output(repo, "we opened data/batadal and looked")
    assert not check.clean


def test_a_path_segment_matches(repo: Path) -> None:
    check = check_output(repo, "ls /Volumes/PHOSRED/daypsci-v1-heldout/")
    assert not check.clean


def test_the_summary_names_what_matched(repo: Path) -> None:
    check = check_output(repo, "batadal again")
    assert "batadal" in check.summary()


def test_a_clean_summary_says_how_many_tokens_were_searched(repo: Path) -> None:
    check = check_output(repo, "nothing to see")
    assert "tokens searched" in check.summary()


def test_scan_records_the_line(repo: Path) -> None:
    check = check_output(repo, "first line\nsecond line with batadal\nthird")
    assert len(check.hits) == 1
    assert "batadal" in check.hits[0].line
    assert check.hits[0].line != "first line"


def test_scan_handles_empty_output() -> None:
    assert scan("", ("hai",)).clean


def test_a_token_that_is_too_short_is_dropped(repo: Path) -> None:
    """A two-character token would match inside ordinary words."""
    tokens, _ = red_tokens(repo)
    assert all(len(token) >= 3 for token in tokens)


def test_write_inbox_names_the_operation_role_and_token(repo: Path) -> None:
    check = check_output(repo, "I read hai by mistake")
    path = write_inbox(
        repo, operation="op-1", role="applied_scientist", check=check, runtime="codex"
    )
    text = path.read_text()
    assert path == repo / "docs/method/INBOX.md"
    assert "op-1" in text
    assert "applied_scientist" in text
    assert "codex" in text
    assert "hai" in text
    assert "Nothing was recorded as a result" in text


def test_write_inbox_keeps_a_foreign_inbox(repo: Path) -> None:
    path = repo / "docs/method/INBOX.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("a note a human wrote\n")
    check = check_output(repo, "batadal")
    write_inbox(repo, operation="op-1", role="x", check=check)
    text = path.read_text()
    assert "a note a human wrote" in text
    assert "Previous contents" in text


def test_write_inbox_replaces_its_own_previous_entry(repo: Path) -> None:
    """The INBOX says what is missing now, not every abort ever. Otherwise nobody reads it."""
    check = check_output(repo, "hai")
    write_inbox(repo, operation="op-1", role="x", check=check)
    write_inbox(repo, operation="op-2", role="y", check=check)
    text = (repo / "docs/method/INBOX.md").read_text()
    assert "op-2" in text
    assert "op-1" not in text


def test_a_check_is_false_when_it_found_something() -> None:
    check = RedCheck(hits=(RedHit("hai", "a line"),), tokens=("hai",), sources=())
    assert not check.clean


def test_the_inbox_path_is_where_the_task_says(repo: Path) -> None:
    assert redline.INBOX == Path("docs/method/INBOX.md")


@pytest.mark.lab_only
@pytest.mark.parametrize(
    "line",
    [
        "data/hai/train.csv",
        "/Volumes/PHOSRED",
        "hai-21.03",
        "hai-22.04",
        "batadal",
        "phos-icssim-heldout4",
        "daypsci-v1-heldout",
    ],
)
def test_every_shape_of_sealed_reference_is_caught(repo: Path, line: str) -> None:
    assert not check_output(repo, line).clean

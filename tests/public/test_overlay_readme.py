"""The public record states the ceiling and the refusal the code enforces (ADR 0381).

The front page tells a reader the page holds at most eight lines. The contract page states the
same ceiling as a formula, names the five words that refuse a sentence, and names how many of
them there are. All of it is code constants -- ``OPERATOR_PAGE_CEILING`` and ``_SCORE_WORDS`` in
``phos.atlas.declared_law`` -- and this module fails when either public file and the code drift
apart in either direction.

The four display equations were on the front page until the page was shortened; they are now in
``docs/whitepaper/eight-alert-non-admission.md``, which is the paper about what the page refuses,
and the pins follow them there. Moving a statement does not loosen its pin: the ceiling is still
checked on the page a reader meets first, and the formula, the word set and the count are still
checked character for character against the code.

Both files are exported, so this module runs in the public repository too. The overlay lands
there as the root README, so the front page is looked for in both places; the contract page keeps
its path. The refused words themselves are welcome in prose that explains the refusal; what is
pinned is that the set the contract states, the count it names, and every ceiling the front page
quotes are the code's.
"""

import re
from pathlib import Path
from typing import Final

from phos.atlas.declared_law import _SCORE_WORDS, OPERATOR_PAGE_CEILING

_ROOT: Final = Path(__file__).resolve().parents[2]
_README: Final = (
    _ROOT / "public" / "overlay" / "README.md"
    if (_ROOT / "public" / "overlay" / "README.md").is_file()
    else _ROOT / "README.md"
)
_CONTRACT: Final = _ROOT / "docs" / "whitepaper" / "eight-alert-non-admission.md"

_NUMBER_WORDS: Final = (
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
)
_NUM: Final = r"\d+|" + "|".join(_NUMBER_WORDS)
_CEILING_PHRASES: Final = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        rf"at most\s+(?P<num>{_NUM})\b",
        rf"cut at\s+(?P<num>{_NUM})\b",
        rf"\b(?P<num>{_NUM})\s+alerts?\s+an operator can read in a shift\b",
        rf"\b(?P<num>{_NUM})\s+alerts?\s+a shift\b",
    )
)
_TEXTSF: Final = re.compile(r"\\textsf\{([^}]+)\}")


def _text() -> str:
    return _README.read_text(encoding="utf-8")


def _contract() -> str:
    return _CONTRACT.read_text(encoding="utf-8")


def _as_int(value: str) -> int:
    if value.isdigit():
        return int(value)
    return _NUMBER_WORDS.index(value.casefold()) + 1


def test_the_contract_page_is_where_the_pins_point() -> None:
    # A rename or a move that leaves the pins dangling would otherwise pass four tests by
    # reading an empty string, so the file's presence is its own assertion.
    assert _CONTRACT.is_file(), f"the contract page is not at {_CONTRACT}"


def test_every_ceiling_the_page_states_is_the_code_ceiling() -> None:
    stated = {
        _as_int(match.group("num"))
        for pattern in _CEILING_PHRASES
        for match in pattern.finditer(_text())
    }
    assert stated == {OPERATOR_PAGE_CEILING}


def test_the_front_page_still_points_at_the_contract() -> None:
    assert "whitepaper/eight-alert-non-admission.md" in _text(), (
        "the front page no longer links the contract the equations moved to"
    )


def test_the_contract_formula_cuts_at_the_code_ceiling() -> None:
    (line,) = [ln for ln in _contract().splitlines() if ln.startswith("$$\\mathrm{page}")]
    assert str(OPERATOR_PAGE_CEILING) in line


def test_the_refused_set_the_contract_states_is_the_code_set() -> None:
    (line,) = [ln for ln in _contract().splitlines() if ln.startswith("$$W")]
    assert tuple(_TEXTSF.findall(line)) == _SCORE_WORDS


def test_the_refused_count_the_contract_names_is_the_code_count() -> None:
    match = re.search(r"none of the ([a-z]+) words in any case", _contract(), re.IGNORECASE)
    assert match is not None, "the contract no longer names the count of refused words"
    assert match.group(1).casefold() == _NUMBER_WORDS[len(_SCORE_WORDS) - 1]


def test_the_math_uses_no_macro_the_renderer_refuses() -> None:
    # GitHub's math renderer refused `\operatorname` on 29 October 2026 and showed the block's
    # raw source on the public front page. The blocks use `\mathrm` where a word is set roman.
    assert "\\operatorname" not in _text()
    assert "\\operatorname" not in _contract()

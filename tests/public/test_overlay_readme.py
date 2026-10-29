"""The public front page states the ceiling and the refusal the code enforces (ADR 0381).

The overlay README tells a reader the page holds at most eight lines, cuts its sorted breaks at
that ceiling, and names the five words that refuse a sentence. All three are code constants —
``OPERATOR_PAGE_CEILING`` and ``_SCORE_WORDS`` in ``phos.atlas.declared_law`` — and this module
fails when the page and the code drift apart in either direction. It runs in the public
repository too: the overlay lands there as the root README, so the file is looked for in both
places. The words themselves are welcome in prose that explains the refusal; what is pinned is
that the set the page states, the count it names, and every ceiling it quotes are the code's.
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


def _as_int(value: str) -> int:
    if value.isdigit():
        return int(value)
    return _NUMBER_WORDS.index(value.casefold()) + 1


def test_every_ceiling_the_page_states_is_the_code_ceiling() -> None:
    stated = {
        _as_int(match.group("num"))
        for pattern in _CEILING_PHRASES
        for match in pattern.finditer(_text())
    }
    assert stated == {OPERATOR_PAGE_CEILING}


def test_the_page_formula_cuts_at_the_code_ceiling() -> None:
    (line,) = [ln for ln in _text().splitlines() if ln.startswith("$$\\mathrm{page}")]
    assert str(OPERATOR_PAGE_CEILING) in line


def test_the_refused_set_the_page_states_is_the_code_set() -> None:
    (line,) = [ln for ln in _text().splitlines() if ln.startswith("$$W")]
    assert tuple(_TEXTSF.findall(line)) == _SCORE_WORDS


def test_the_refused_count_the_page_names_is_the_code_count() -> None:
    match = re.search(r"none of the ([a-z]+) words in any case", _text(), re.IGNORECASE)
    assert match is not None, "the page no longer names the count of refused words"
    assert match.group(1).casefold() == _NUMBER_WORDS[len(_SCORE_WORDS) - 1]

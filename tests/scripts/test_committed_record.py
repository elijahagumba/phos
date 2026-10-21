"""A recompute that differs from the committed file is not written."""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.committed_record import committed_difference, require_match, wants_compare


def test_a_match_is_silent_and_a_difference_names_the_line(tmp_path: Path) -> None:
    path = tmp_path / "row.json"
    path.write_text('{"caught": 5}\n', encoding="utf-8")
    assert committed_difference(path, '{"caught": 5}\n') is None
    difference = committed_difference(path, '{"caught": 4}\n')
    assert difference is not None
    assert "line 1" in difference
    assert path.read_text(encoding="utf-8") == '{"caught": 5}\n'


def test_a_missing_record_is_a_difference(tmp_path: Path) -> None:
    difference = committed_difference(tmp_path / "missing.json", "{}\n")
    assert difference is not None
    assert "missing" in difference


def test_require_match_exits_without_writing(tmp_path: Path) -> None:
    path = tmp_path / "row.json"
    path.write_text("a\n", encoding="utf-8")
    require_match(((path, "a\n"),))
    with pytest.raises(SystemExit, match="not written"):
        require_match(((path, "b\n"),))
    assert path.read_text(encoding="utf-8") == "a\n"


def test_compare_is_the_only_accepted_flag() -> None:
    assert wants_compare([]) is False
    assert wants_compare(["--compare"]) is True
    with pytest.raises(SystemExit, match="unrecognised"):
        wants_compare(["--write"])

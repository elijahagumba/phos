"""An absent experiment pin skips. A present file does not."""

from __future__ import annotations

from pathlib import Path

import pytest
from tests.lab_only import skip_if_absent


def test_a_present_file_is_not_skipped(tmp_path: Path) -> None:
    path = tmp_path / "candidate.py"
    path.write_text("x = 1\n", encoding="utf-8")
    skip_if_absent(path)


def test_an_absent_file_skips_with_the_export_reason(tmp_path: Path) -> None:
    path = tmp_path / "experiments" / "candidate.py"
    with pytest.raises(pytest.skip.Exception, match="not an include pattern"):
        skip_if_absent(path)

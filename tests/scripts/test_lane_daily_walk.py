"""The walk-column command refuses a held-out path before any file is opened."""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.lane_daily_walk import main


def test_a_held_out_path_is_refused(tmp_path: Path) -> None:
    held = tmp_path / "phos-icssim-heldout4-walk"
    held.mkdir()
    with pytest.raises(SystemExit, match="held-out"):
        main(["--corpus", str(held)])

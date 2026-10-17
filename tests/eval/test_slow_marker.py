"""Default pytest omits real-corpus runs (ADR 0092).

The marker expression on the command line replaces the one in ``addopts``. ``-m "slow or not
slow"`` is the full suite.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _collect(*extra: str) -> str:
    """Return the quiet collection listing for this repo."""
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
            *extra,
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stderr
    return completed.stdout


def test_the_default_suite_omits_a_real_corpus_score() -> None:
    listing = _collect()
    assert "test_real_dataset_scores_end_to_end" not in listing


def test_the_full_marker_expression_puts_that_score_back() -> None:
    listing = _collect("-m", "slow or not slow")
    assert "test_real_dataset_scores_end_to_end" in listing

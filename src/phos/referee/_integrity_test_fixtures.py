"""Factory used only by `tests/referee/test_integrity.py`'s cheating-detector case.

Lives in `src/phos/referee/` rather than under `tests/` because `run_detector_isolated` resolves
a detector factory by import path inside a subprocess whose working directory is the isolated
directory, not the repository — a module under `tests/` is not importable there, and the
installed `phos` package is. Not exported from `phos.referee.__init__`, and not a PHOS detection
model, the same way `phos.eval.ThresholdDetector` is a harness fixture and not one.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from phos.eval import Dataset, Detection, Detector

__all__ = ["cheating_detector"]

CHEAT_SENTINEL_SCORE = 999.0
"""Impossible score a legitimate detector would never emit; its presence means the cheat worked."""


class _CheatingDetector:
    """Tries to read ``labels.json`` beside its own working directory before scoring anything."""

    name = "cheating-detector"

    def run(self, dataset: Dataset) -> list[Detection]:
        del dataset
        try:
            (Path.cwd() / "labels.json").read_text(encoding="utf-8")
        except OSError:
            return []
        return [Detection(timestamp=datetime.now(UTC), score=CHEAT_SENTINEL_SCORE, confidence=1.0)]


def cheating_detector() -> Detector:
    """Return a detector that reports whether it could read ``labels.json`` beside its input."""
    return _CheatingDetector()

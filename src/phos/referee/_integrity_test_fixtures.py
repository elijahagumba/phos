"""Factories used only by `tests/referee/test_integrity.py`'s cheating-detector cases.

Lives in `src/phos/referee/` rather than under `tests/` because `run_detector_isolated` resolves
a detector factory by import path inside a subprocess whose working directory is the isolated
directory, not the repository — a module under `tests/` is not importable there, and the
installed `phos` package is. Not exported from `phos.referee.__init__`, and not a PHOS detection
model, the same way `phos.eval.ThresholdDetector` is a harness fixture and not one.

Two cheats are modelled, because there are two doors. `cheating_detector` looks for ground truth
*beside* its input, which is the accidental-overfitting shape. `name_reading_detector` looks for
it *through* its input: a generated plant's real id carries its family and master seed, so a
detector handed that id could regenerate the plant or look up which family it came from without
opening any file. It reports a hit if the dataset's name still contains a seed-shaped number.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

from phos.eval import Dataset, Detection, Detector

__all__ = ["cheating_detector", "name_reading_detector"]

CHEAT_SENTINEL_SCORE = 999.0
"""Impossible score a legitimate detector would never emit; its presence means the cheat worked."""

#: What a family-and-seed id looks like: a run of five or more digits, as in ``level-flow-96011``.
_SEED_SHAPED: re.Pattern[str] = re.compile(r"\d{5,}")


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


class _NameReadingDetector:
    """Reports whether the dataset it was given names a family and a seed-shaped number."""

    name = "name-reading-detector"

    def run(self, dataset: Dataset) -> list[Detection]:
        entity_names = {
            entity for observation in dataset.observations for entity in observation.entity_ids
        }
        hit = bool(_SEED_SHAPED.search(dataset.name)) or any(
            _SEED_SHAPED.search(name) for name in entity_names
        )
        if not hit:
            return []
        return [Detection(timestamp=datetime.now(UTC), score=CHEAT_SENTINEL_SCORE, confidence=1.0)]


def cheating_detector() -> Detector:
    """Return a detector that reports whether it could read ``labels.json`` beside its input."""
    return _CheatingDetector()


def name_reading_detector() -> Detector:
    """Return a detector that reports whether its input carries a family and a seed."""
    return _NameReadingDetector()

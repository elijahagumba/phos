"""One more look at HAI 22.04 and 23.05, declared before it is scored.

The sandbox candidate is the file named by the sandbox README as worktree commit
``6e7c665``. That commit is not in this repository. The bytes here are locked by
sha256. Grouped Atlas and grouped MinMax are the published ADR 0102 counts and are
not scored again.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy
from numpy.typing import NDArray

from phos.eval.baseline_table import SeriesGrid

CANDIDATE_RELATIVE = Path("experiments/2026-10-04-sandbox/candidate.py")
CANDIDATE_SHA256 = "7d485b7298282b6b369d55675804d3017e9f952d1353b5e673c84734720433d4"
CANDIDATE_WORKTREE = "6e7c665"
CLEAN_CORPORA: tuple[str, ...] = ("hai-22.04", "hai-23.05")
OWN_GROUPING = "sandbox-candidate:own-grouping"
SHARED_WRAPPER = "sandbox-candidate:shared-wrapper"
GROUPED_ATLAS = "g1-grouped:atlas-mahalanobis"
GROUPED_MINMAX = "g1-grouped:simple-minmax"
LOOK_JSON_NAME = "g1-candidate-look.json"
# Published headline catches from ADR 0102. Not a new measurement.
PUBLISHED_CAUGHT: Mapping[str, Mapping[str, tuple[int, int]]] = {
    "hai-22.04": {GROUPED_ATLAS: (5, 58), GROUPED_MINMAX: (10, 58)},
    "hai-23.05": {GROUPED_ATLAS: (5, 52), GROUPED_MINMAX: (6, 52)},
}


def sha256_bytes(payload: bytes) -> str:
    """sha256 hex digest of a file's bytes."""
    return hashlib.sha256(payload).hexdigest()


def assert_candidate_bytes(payload: bytes) -> None:
    """Raise when the candidate file is not the frozen bytes."""
    digest = sha256_bytes(payload)
    if digest != CANDIDATE_SHA256:
        raise ValueError(f"candidate.py sha256 {digest} is not {CANDIDATE_SHA256}")


def beyond_grouped_minmax(candidate_caught: int, minmax_caught: int) -> int:
    """Candidate attacks caught, minus published grouped MinMax attacks caught."""
    return candidate_caught - minmax_caught


def attacks_only_candidate(candidate: Sequence[str], minmax: Sequence[str]) -> tuple[str, ...]:
    """Attack ids the candidate caught and grouped MinMax did not."""
    return tuple(sorted(set(candidate) - set(minmax)))


def cells_above(
    scores: NDArray[numpy.float64], features: Sequence[str], threshold: float
) -> tuple[tuple[int, str, float], ...]:
    """Rows where a feature score is strictly above ``threshold``.

    The comparison is the frozen candidate's ``score > THRESHOLD``.
    """
    if scores.ndim != 2 or scores.shape[1] != len(features):
        raise ValueError("scores must have one column per feature")
    rows, columns = numpy.nonzero(scores > threshold)
    return tuple(
        (int(row), features[int(column)], float(scores[int(row), int(column)]))
        for row, column in zip(rows.tolist(), columns.tolist(), strict=True)
    )


def train_record(grid: SeriesGrid) -> dict[str, object]:
    """The frozen train dict. Attack flags are allowed, for the fit only."""
    return {
        "time": _unix(grid),
        "values": grid.values,
        "attack": numpy.asarray(grid.attack, dtype=numpy.bool_),
        "features": grid.features,
    }


def label_free_record(grid: SeriesGrid) -> dict[str, object]:
    """The frozen test dict. Test labels are not included."""
    return {"time": _unix(grid), "values": grid.values, "features": grid.features}


def published_caught(corpus: str, detector: str) -> tuple[int, int]:
    """The ADR 0102 catch count for one published grouped detector."""
    try:
        return PUBLISHED_CAUGHT[corpus][detector]
    except KeyError as error:
        raise ValueError(f"{corpus} {detector} is not a published comparison row") from error


@dataclass(frozen=True)
class LookRow:
    """One comparison row. A blank beyond-count is a published row, not a new score."""

    corpus: str
    detector: str
    caught: int
    attacks: int
    point_adjusted_f1: float | None
    beyond_grouped_minmax: int | None
    attacks_only_candidate: tuple[str, ...]

    @property
    def recall_within_budget(self) -> float:
        """Headline: attacks caught over attacks."""
        if self.attacks == 0:
            return 0.0
        return self.caught / self.attacks


def render_look(rows: Sequence[LookRow]) -> str:
    """Markdown for the one candidate look. Recall is the first numeric column."""
    lines = [
        "# Sandbox candidate on the clean HAI editions",
        "",
        "Recall within budget is the headline. Point-adjusted F1 is reported and is not.",
        "Grouped Atlas and grouped MinMax are the published ADR 0102 counts.",
        "Beyond grouped MinMax is the candidate's catches minus grouped MinMax's catches.",
        "",
        "| Corpus | Detector | Caught | Attacks | Recall within budget | "
        "Point-adjusted F1 (reported, not the headline) | Beyond grouped MinMax |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        adjusted = "published" if row.point_adjusted_f1 is None else f"{row.point_adjusted_f1:.6f}"
        beyond = "" if row.beyond_grouped_minmax is None else str(row.beyond_grouped_minmax)
        lines.append(
            f"| {row.corpus} | {row.detector} | {row.caught} | {row.attacks} | "
            f"{row.recall_within_budget:.6f} | {adjusted} | {beyond} |"
        )
    lines.extend(["", "## Attacks only the candidate catches", ""])
    for row in rows:
        if row.beyond_grouped_minmax is None:
            continue
        listed = ", ".join(row.attacks_only_candidate) or "none"
        lines.append(f"{row.corpus} {row.detector}: {listed}.")
    lines.append("")
    return "\n".join(lines)


def _unix(grid: SeriesGrid) -> NDArray[numpy.float64]:
    return numpy.asarray([stamp.timestamp() for stamp in grid.timestamps], dtype=numpy.float64)

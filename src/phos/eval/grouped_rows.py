"""Grouped G1 rows. The published ungrouped scores are not recomputed here."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

import numpy
from numpy.typing import NDArray

from phos.eval.baseline_alerts import (
    _atlas_cells,
    _attack_intervals,
    _histogram_cells,
    _keep_top,
    _minmax_cells,
    _steady_cells,
)
from phos.eval.baseline_table import (
    ATLAS_DETECTOR,
    HISTOGRAM_DETECTOR,
    MINMAX_DETECTOR,
    STEADY_DETECTOR,
    DetectorScore,
    FitFacts,
    SeriesGrid,
    _fit_atlas,
    _fit_opponents,
    _score_detector,
)
from phos.eval.grouping import group_published_alerts

GROUPED_CORPORA: tuple[str, ...] = (
    "hai-20.07",
    "hai-21.03",
    "batadal",
    "batch-distillation",
    "data4cyber",
)
SEEN_CORPORA = frozenset({"hai-20.07", "hai-21.03"})
GROUPED_ATLAS = "g1-grouped:atlas-mahalanobis"
GROUPED_MINMAX = "g1-grouped:simple-minmax"
GROUPED_STEADY = "g1-grouped:simple-steadytime"
GROUPED_HISTOGRAM = "g1-grouped:simple-histogram"
GROUPED_OPPONENTS = frozenset({GROUPED_MINMAX, GROUPED_STEADY, GROUPED_HISTOGRAM})
_RENAME = {
    ATLAS_DETECTOR: GROUPED_ATLAS,
    MINMAX_DETECTOR: GROUPED_MINMAX,
    STEADY_DETECTOR: GROUPED_STEADY,
    HISTOGRAM_DETECTOR: GROUPED_HISTOGRAM,
}


def exposure_of(corpus: str) -> str | None:
    """``seen`` when the grouping constants were chosen or held out on this corpus."""
    if corpus in SEEN_CORPORA:
        return "seen"
    return None


def beyond_grouping(atlas_caught: int, opponent_caught: Sequence[int]) -> int:
    """Grouped Atlas caught, minus the best grouped checked opponent caught."""
    if not opponent_caught:
        raise ValueError("beyond grouping needs at least one checked opponent")
    return atlas_caught - max(opponent_caught)


def attacks_only_grouped_atlas(
    atlas: Sequence[str], opponents: Sequence[Sequence[str]]
) -> tuple[str, ...]:
    """Attack ids grouped Atlas caught and no grouped checked opponent caught."""
    others: set[str] = set()
    for group in opponents:
        others.update(group)
    return tuple(sorted(set(atlas) - others))


def score_grouped_cells(
    grid: SeriesGrid,
    file_name: str,
    cells: Mapping[str, Sequence[tuple[int, str, float]]],
) -> tuple[tuple[DetectorScore, ...], dict[str, tuple[str, ...]]]:
    """Group each detector's published cells, then score those alerts.

    ``cells`` is keyed by the ungrouped ``g1-baseline:`` name. The returned scores
    use ``g1-grouped:`` names. Caught ids are ``file#index`` of attack windows that
    contain a kept grouped alert.
    """
    scores: list[DetectorScore] = []
    caught: dict[str, tuple[str, ...]] = {}
    for baseline_name, published in cells.items():
        grouped_name = _RENAME[baseline_name]
        grouped = group_published_alerts(grid.timestamps, published)
        scores.append(_score_detector(grouped_name, grouped, grid))
        caught[grouped_name] = _caught_ids(grouped, grid, file_name)
    return tuple(scores), caught


def score_grouped_splits(
    features: Sequence[str],
    train: NDArray[numpy.float64],
    train_window: tuple[datetime, datetime],
    tests: Sequence[tuple[str, SeriesGrid]],
) -> tuple[FitFacts, tuple[tuple[str, tuple[DetectorScore, ...], dict[str, tuple[str, ...]]], ...]]:
    """Fit the G1 configuration once and score grouped alerts on each test file."""
    feature_names = tuple(features)
    atlas, facts = _fit_atlas(feature_names, train, train_window)
    minmax, steady, histogram = _fit_opponents(feature_names, train)
    files = []
    for name, grid in tests:
        cells = {
            ATLAS_DETECTOR: _atlas_cells(atlas, feature_names, grid),
            MINMAX_DETECTOR: _minmax_cells(minmax, grid),
            STEADY_DETECTOR: _steady_cells(steady, grid),
            HISTOGRAM_DETECTOR: _histogram_cells(histogram, grid),
        }
        scores, caught = score_grouped_cells(grid, name, cells)
        files.append((name, scores, caught))
    return facts, tuple(files)


def _caught_ids(
    cells: Sequence[tuple[int, str, float]], grid: SeriesGrid, file_name: str
) -> tuple[str, ...]:
    kept = _keep_top(cells, grid.timestamps)
    intervals = _attack_intervals(grid)
    return tuple(
        f"{file_name}#{index}"
        for index, interval in enumerate(intervals)
        if any(interval.start <= detection.timestamp <= interval.end for detection in kept)
    )


@dataclass(frozen=True)
class GroupedRow:
    """One corpus after the shared wrapper. Not a replacement of the published row."""

    corpus: str
    exposure: str | None
    scores: tuple[DetectorScore, ...]
    beyond_grouping: int
    attacks_only_grouped_atlas: tuple[str, ...]
    note: str


def render_grouped_section(rows: Sequence[GroupedRow]) -> str:
    """Markdown appended to the G1 table. It does not repeat the published fractions."""
    lines = [
        "## Grouped rows",
        "",
        "Same Atlas configuration and the same three opponents, each through",
        "`group_published_alerts` (ADR 0099). These rows do not replace the rows above.",
        "HAI 22.04 and 23.05 are not scored here.",
        "Beyond grouping is grouped Atlas caught minus the best grouped checked opponent caught.",
        "",
        "| Corpus | Exposure | Detector | Caught | Attacks | Recall within budget |",
        "|---|---|---|---:|---:|---:|",
    ]
    for row in rows:
        exposure = row.exposure if row.exposure is not None else ""
        for score in row.scores:
            lines.append(
                f"| {row.corpus} | {exposure} | {score.detector} | {score.caught} | "
                f"{score.attacks} | {score.recall_within_budget:.6f} |"
            )
        listed = ", ".join(row.attacks_only_grouped_atlas) or "none"
        lines.append("")
        lines.append(
            f"{row.corpus}: beyond grouping {row.beyond_grouping}. "
            f"Attacks only grouped Atlas catches: {listed}."
        )
        lines.append("")
    lines.append("## Grouped notes")
    lines.append("")
    for row in rows:
        lines.append(f"- **{row.corpus}**: {row.note}")
    lines.append("")
    return "\n".join(lines)

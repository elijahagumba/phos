"""Alert rows for the G1 table.

Atlas cells are the ungated Mahalanobis conditional departure. Opponent cells are the
published simple-detector rules. The heap keeps eight alerts per eight-hour shift, which
is the keep inside ``recall_within_budget`` and not a second budget.
"""

from __future__ import annotations

import heapq
from collections.abc import Iterable, Sequence
from datetime import datetime

import numpy
from numpy.typing import NDArray

from phos.atlas.multivariate import MahalanobisFittedModel, _departure
from phos.eval.baseline_table import (
    G1_ALERTS_PER_SHIFT,
    G1_ATLAS_THRESHOLD,
    G1_ENTITY,
    SeriesGrid,
)
from phos.eval.budget import OPERATOR_SHIFT, recall_within_budget
from phos.eval.datasets import Dataset, LabelledInterval
from phos.eval.detectors import Detection
from phos.eval.metrics import window_recall
from phos.eval.simple_iids import (
    HistogramFeature,
    RangeBound,
    SteadyFeature,
    histogram_alert_indexes,
    minmax_alert_indexes,
    steadytime_alert_indexes,
)
from phos.ontology import Domain, Observation

_Flags = NDArray[numpy.bool_]


def _atlas_cells(
    fitted: MahalanobisFittedModel, features: Sequence[str], grid: SeriesGrid
) -> list[tuple[int, str, float]]:
    if fitted.signal_space.size == 0 or grid.values.shape[0] == 0:
        return []
    index = {feature: column for column, feature in enumerate(features)}
    columns = [index[feature] for _entity, feature in fitted.signal_space.signals]
    matrix = grid.values[:, columns]
    expected = fitted._expected_values(matrix)
    magnitude = _departure(matrix, expected, fitted._signal_spread())
    allowed = fitted._moment_mask(matrix)[:, numpy.newaxis]
    rows, cols = numpy.nonzero((magnitude >= G1_ATLAS_THRESHOLD) & allowed)
    names = [feature for _entity, feature in fitted.signal_space.signals]
    return [
        (int(row), names[int(col)], float(magnitude[int(row), int(col)]))
        for row, col in zip(rows.tolist(), cols.tolist(), strict=True)
    ]


def _minmax_cells(bounds: dict[str, RangeBound], grid: SeriesGrid) -> list[tuple[int, str, float]]:
    cells: list[tuple[int, str, float]] = []
    for column, feature in enumerate(grid.features):
        bound = bounds[feature]
        values = grid.values[:, column].tolist()
        for row in minmax_alert_indexes(values, bound):
            cells.append((row, feature, _minmax_likelihood(values[row], bound)))
    cells.sort()
    return cells


def _steady_cells(
    models: dict[str, SteadyFeature], grid: SeriesGrid
) -> list[tuple[int, str, float]]:
    cells: list[tuple[int, str, float]] = []
    for column, feature in enumerate(grid.features):
        model = models.get(feature)
        if model is None:
            continue
        values = grid.values[:, column].tolist()
        for row in steadytime_alert_indexes(values, model):
            cells.append((row, feature, 1.0))
    cells.sort()
    return cells


def _histogram_cells(
    models: dict[str, HistogramFeature], grid: SeriesGrid
) -> list[tuple[int, str, float]]:
    cells: list[tuple[int, str, float]] = []
    for column, feature in enumerate(grid.features):
        model = models.get(feature)
        if model is None:
            continue
        values = grid.values[:, column].tolist()
        for row in histogram_alert_indexes(values, model):
            cells.append((row, feature, 1.0))
    cells.sort()
    return cells


def _minmax_likelihood(value: float, bound: RangeBound) -> float:
    """The public overshoot. Zero inside the raw range, uncapped outside it."""
    if bound.low <= value <= bound.high:
        return 0.0
    overshoot = abs(((bound.high + bound.low) * 0.5) - value) - (bound.high - bound.low) * 0.5
    margin = 1.0 if bound.margin == 0.0 else bound.margin
    return overshoot / margin


def _keep_top(
    cells: Sequence[tuple[int, str, float]], timestamps: Sequence[datetime]
) -> list[Detection]:
    """The alerts ``recall_within_budget`` would keep at 8 per shift.

    Heap key ``(score, -time, -order)`` puts the worst of the current eight first, so a
    ninth alert replaces it. Ties keep the earlier timestamp, then the earlier cell.
    """
    origin = timestamps[0] if timestamps else None
    heaps: dict[int, list[tuple[float, float, int, int, str]]] = {}
    for order, (row, feature, score) in enumerate(cells):
        if origin is None:
            break
        stamp = timestamps[row]
        shift = (stamp - origin) // OPERATOR_SHIFT
        heap = heaps.setdefault(shift, [])
        item = (score, -stamp.timestamp(), -order, row, feature)
        if len(heap) < G1_ALERTS_PER_SHIFT:
            heapq.heappush(heap, item)
        elif item > heap[0]:
            heapq.heapreplace(heap, item)
    kept: list[Detection] = []
    for heap in heaps.values():
        for score, _negative_time, _negative_order, row, feature in heap:
            kept.append(
                Detection(
                    timestamp=timestamps[row],
                    score=score,
                    confidence=0.0,
                    entity_ids=[G1_ENTITY],
                    feature=feature,
                )
            )
    return kept


def _attack_intervals(grid: SeriesGrid) -> list[LabelledInterval]:
    intervals: list[LabelledInterval] = []
    index = 0
    n_rows = len(grid.timestamps)
    while index < n_rows:
        if not bool(grid.attack[index]):
            index += 1
            continue
        end = index + 1
        while end < n_rows and bool(grid.attack[end]):
            end += 1
        intervals.append(
            LabelledInterval(
                start=grid.timestamps[index],
                end=grid.timestamps[end - 1],
                label="attack",
            )
        )
        index = end
    return intervals


def _clock(origin: datetime, intervals: list[LabelledInterval]) -> Dataset:
    observation = Observation(
        id="obs_g1clock0001",
        entity_ids=[G1_ENTITY],
        feature="clock",
        value=0.0,
        timestamp=origin,
        domain=Domain.ATLAS,
    )
    return Dataset(
        name="g1-clock",
        domain=Domain.ATLAS,
        observations=[observation],
        attack_intervals=intervals,
    )


def _clock_empty() -> Dataset:
    return Dataset(name="g1-clock", domain=Domain.ATLAS, observations=[])


def _caught(detections: Sequence[Detection], intervals: Sequence[LabelledInterval]) -> int:
    if not intervals:
        return 0
    return sum(
        1
        for interval in intervals
        if any(interval.start <= detection.timestamp <= interval.end for detection in detections)
    )


def _point_flags(
    cells: Sequence[tuple[int, str, float]], grid: SeriesGrid
) -> tuple[numpy.ndarray, numpy.ndarray]:
    """Scored rows only. Unscored rows leave the index; one alert marks the timestamp."""
    scored = numpy.flatnonzero(~grid.unscored)
    truth = grid.attack[scored]
    predicted = numpy.zeros(scored.shape[0], dtype=numpy.bool_)
    if scored.size == 0 or not cells:
        return truth, predicted
    position = {int(row): index for index, row in enumerate(scored.tolist())}
    for row, _feature, _score in cells:
        index = position.get(row)
        if index is not None:
            predicted[index] = True
    return truth, predicted


def _ranges(flags: _Flags) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    index = 0
    n_points = int(flags.shape[0])
    while index < n_points:
        if not bool(flags[index]):
            index += 1
            continue
        end = index + 1
        while end < n_points and bool(flags[end]):
            end += 1
        ranges.append((index, end - 1))
        index = end
    return ranges


def kept_matches_full_list(cells: Sequence[tuple[int, str, float]], grid: SeriesGrid) -> bool:
    """Return whether the heap keeps the same windows as scoring the full alert list.

    Used by the test. The corpus path does not build the full list twice.
    """
    kept = _keep_top(cells, grid.timestamps)
    full = [
        Detection(
            timestamp=grid.timestamps[row],
            score=score,
            confidence=0.0,
            entity_ids=[G1_ENTITY],
            feature=feature,
        )
        for row, feature, score in cells
    ]
    intervals = _attack_intervals(grid)
    dataset = _clock(grid.timestamps[0], intervals)
    budget_kept = list(_budget_kept(full, dataset))
    same_windows = window_recall(kept, intervals) == window_recall(budget_kept, intervals)
    same_recall = recall_within_budget(full, dataset, G1_ALERTS_PER_SHIFT) == recall_within_budget(
        kept, dataset, G1_ALERTS_PER_SHIFT
    )
    return same_windows and same_recall


def _budget_kept(detections: Sequence[Detection], dataset: Dataset) -> Iterable[Detection]:
    """The same keep as ``recall_within_budget``, so the heap can be checked against it."""
    origin = dataset.observations[0].timestamp
    grouped: dict[int, list[tuple[int, Detection]]] = {}
    for index, detection in enumerate(detections):
        shift = (detection.timestamp - origin) // OPERATOR_SHIFT
        grouped.setdefault(shift, []).append((index, detection))
    for group in grouped.values():
        group.sort(key=lambda item: (-item[1].score, item[1].timestamp, item[0]))
        for _index, detection in group[:G1_ALERTS_PER_SHIFT]:
            yield detection

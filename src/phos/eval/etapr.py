"""Enhanced time-series aware precision and recall (eTaPR).

This is the metric in Hwang, Yun, Kim and Min, "Do You Know Existing Accuracy Metrics
Overrate Time-Series Anomaly Detections?", SAC 2022. The arithmetic follows the reference
package eTaPR 22.6.1 (``evaluate_w_ranges``), including the places that package is sharp:
an ambiguous tail is a ratio of the anomaly's span, a one-point tail is ignored, and a
prediction whose overlap is exactly zero is not pruned.

Ranges are inclusive integer indexes, the unit the reference uses. A caller who has
timestamps converts them before calling. ``theta_p`` and ``theta_r`` are required arguments.
HAICon's published settings are not a default here, and the draft pass criteria in the v1
roadmap are not applied.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["EtaPrResult", "etapr"]

_Range = tuple[int, int]


class EtaPrResult(BaseModel):
    """eTaPR for one anomaly set and one prediction set.

    Attributes:
        etar: Enhanced time-series aware recall. The reference key ``eTaR``.
        etap: Enhanced time-series aware precision. The reference key ``eTaP``.
        f1: Harmonic mean of ``etar`` and ``etap``. Zero when both are zero.
        etar_detection: Fraction of anomalies kept after pruning. Reference ``eTaRd``.
        etar_portion: Mean capped overlap of anomalies after pruning. Reference ``eTaRp``.
        etap_detection: Length-weighted fraction of predictions kept. Reference ``eTaPd``.
        etap_portion: Length-weighted overlap of predictions after pruning. Reference ``eTaPp``.
    """

    model_config = ConfigDict(frozen=True)

    etar: float = Field(ge=0.0)
    etap: float = Field(ge=0.0)
    f1: float = Field(ge=0.0)
    etar_detection: float = Field(ge=0.0)
    etar_portion: float = Field(ge=0.0)
    etap_detection: float = Field(ge=0.0)
    etap_portion: float = Field(ge=0.0)


def etapr(
    anomalies: Sequence[tuple[int, int]],
    predictions: Sequence[tuple[int, int]],
    *,
    theta_p: float,
    theta_r: float,
    delta: float = 0.0,
) -> EtaPrResult:
    """Return eTaPR for inclusive integer ranges.

    Args:
        anomalies: Ground-truth ranges, ``(start, end)`` inclusive. Sorted by start before
            the ambiguous tail is attached, because that tail stops at the next anomaly.
        predictions: Predicted ranges, same shape. Order does not change the score.
        theta_p: Minimum overlap before a prediction survives pruning. In ``[0, 1]``.
        theta_r: Minimum overlap before an anomaly survives pruning. In ``[0, 1]``.
        delta: Ambiguous tail after each anomaly, as a fraction of ``end - start`` (not of
            the inclusive length). In ``[0, 1]``. This is the ratio in eTaPR 22.6.1. It is
            not the integer ``delta`` of the earlier TaPR package, and it is not HAICon's
            180.

    Returns:
        Detection score, portion score and their combination, for recall and for precision.

    Raises:
        ValueError: If a parameter is outside its interval, or a range is inverted.
    """
    _check_unit_interval("theta_p", theta_p)
    _check_unit_interval("theta_r", theta_r)
    _check_unit_interval("delta", delta)
    anomaly_ranges = _sorted_ranges("anomaly", anomalies)
    prediction_ranges = _checked_ranges("prediction", predictions)
    if not anomaly_ranges or not prediction_ranges:
        return EtaPrResult(
            etar=0.0,
            etap=0.0,
            f1=0.0,
            etar_detection=0.0,
            etar_portion=0.0,
            etap_detection=0.0,
            etap_portion=0.0,
        )

    ambiguous = _ambiguous_tails(anomaly_ranges, delta)
    anomaly_lengths = [end - start + 1 for start, end in anomaly_ranges]
    prediction_lengths = [end - start + 1 for start, end in prediction_ranges]
    weights = [math.sqrt(length) for length in prediction_lengths]
    weight_total = sum(weights)
    overlap = [
        [
            _pair_score(anomaly_ranges[i], ambiguous[i], prediction_ranges[j])
            for j in range(len(prediction_ranges))
        ]
        for i in range(len(anomaly_ranges))
    ]
    pruned = _prune(overlap, anomaly_lengths, prediction_lengths, theta_p, theta_r)

    anomaly_scores = [sum(row) / anomaly_lengths[i] for i, row in enumerate(pruned)]
    prediction_scores = [
        sum(pruned[i][j] for i in range(len(pruned))) / prediction_lengths[j]
        for j in range(len(prediction_lengths))
    ]
    detection_recall = [1.0 if score >= theta_r else 0.0 for score in anomaly_scores]
    portion_recall = [min(1.0, score) for score in anomaly_scores]
    detection_precision = [1.0 if score >= theta_p else 0.0 for score in prediction_scores]
    etar_detection = sum(detection_recall) / len(detection_recall)
    etar_portion = sum(portion_recall) / len(portion_recall)
    etar = sum(
        (detected + detected * portion) / 2.0
        for detected, portion in zip(detection_recall, portion_recall, strict=True)
    ) / len(detection_recall)
    etap_detection = (
        sum(weights[j] * detection_precision[j] for j in range(len(weights))) / weight_total
    )
    etap_portion = (
        sum(weights[j] * prediction_scores[j] for j in range(len(weights))) / weight_total
    )
    etap = (
        sum(
            weights[j]
            * (detection_precision[j] + detection_precision[j] * prediction_scores[j])
            / 2.0
            for j in range(len(weights))
        )
        / weight_total
    )
    return EtaPrResult(
        etar=etar,
        etap=etap,
        f1=_f1(etap, etar),
        etar_detection=etar_detection,
        etar_portion=etar_portion,
        etap_detection=etap_detection,
        etap_portion=etap_portion,
    )


def _f1(precision_value: float, recall_value: float) -> float:
    """Harmonic mean, matching the reference: zero when both inputs are zero."""
    total = precision_value + recall_value
    if total == 0.0:
        return 0.0
    return 2.0 * precision_value * recall_value / total


def _check_unit_interval(name: str, value: float) -> None:
    """Raise unless ``value`` is inside ``[0, 1]``, the interval the reference asserts."""
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be in [0, 1], got {value}")


def _checked_ranges(kind: str, ranges: Sequence[tuple[int, int]]) -> list[_Range]:
    """Return the ranges, rejecting an inverted pair."""
    checked: list[_Range] = []
    for start, end in ranges:
        if end < start:
            raise ValueError(f"{kind} range is inverted: {(start, end)}")
        checked.append((start, end))
    return checked


def _sorted_ranges(kind: str, ranges: Sequence[tuple[int, int]]) -> list[_Range]:
    """Return ranges ordered by start, then end."""
    return sorted(_checked_ranges(kind, ranges), key=lambda item: (item[0], item[1]))


def _ambiguous_tails(anomalies: Sequence[_Range], delta: float) -> list[_Range]:
    """Return the tail after each anomaly.

    The tail length is ``int(delta * (end - start))``, which drops the inclusive ``+ 1``.
    A tail whose start is not strictly before its end contributes nothing later. Both
    choices are the reference package's.
    """
    tails: list[_Range] = []
    for index, (_, end) in enumerate(anomalies):
        start_id = end + 1
        end_id = start_id + int(delta * (end - anomalies[index][0]))
        if index + 1 < len(anomalies) and end_id > anomalies[index + 1][0]:
            end_id = anomalies[index + 1][0] - 1
        if start_id > end_id:
            start_id, end_id = -2, -1
        tails.append((start_id, end_id))
    return tails


def _covered(left: _Range, right: _Range) -> int:
    """Return the inclusive overlap length, or zero when the ranges miss."""
    start = max(left[0], right[0])
    end = min(left[1], right[1])
    if end < start:
        return 0
    return end - start + 1


def _decay_sum(start: int, end: int, org_start: int, org_end: int) -> float:
    """Sum the logistic decay across an ambiguous overlap.

    Each index is mapped from the ambiguous window onto ``[-6, 6]``, then scored
    ``1 / (1 + exp(x))``. That is ``_decaying_func`` in the reference.
    """
    if start > end:
        return 0.0
    total = 0.0
    span = org_end - org_start
    for timestamp in range(start, end + 1):
        if span == 0:
            normalised = -6.0
        else:
            normalised = -6.0 + (timestamp - org_start) * 12.0 / span
        total += 1.0 / (1.0 + math.exp(normalised))
    return total


def _pair_score(anomaly: _Range, ambiguous: _Range, prediction: _Range) -> float:
    """Overlap inside the anomaly, plus the decayed overlap in a tail that has width."""
    score = float(_covered(anomaly, prediction))
    if ambiguous[0] < ambiguous[1]:
        start = max(ambiguous[0], prediction[0])
        end = min(ambiguous[1], prediction[1])
        score += _decay_sum(start, end, ambiguous[0], ambiguous[1])
    return score


def _prune(
    overlap: list[list[float]],
    anomaly_lengths: Sequence[int],
    prediction_lengths: Sequence[int],
    theta_p: float,
    theta_r: float,
) -> list[list[float]]:
    """Zero anomaly rows and prediction columns that fall below their thresholds.

    A row or column whose overlap is exactly zero is left alone, which is the reference's
    ``where(score < theta) - where(score == 0)``. The loop repeats until a pass removes
    nothing, because removing one side can push the other side under its threshold.
    """
    matrix = [row[:] for row in overlap]
    n_anomalies = len(matrix)
    n_predictions = len(matrix[0]) if matrix else 0
    while True:
        removed_anomaly = False
        for index, row in enumerate(matrix):
            ratio = sum(row) / anomaly_lengths[index]
            if 0.0 < ratio < theta_r:
                matrix[index] = [0.0] * n_predictions
                removed_anomaly = True
        removed_prediction = False
        for column in range(n_predictions):
            ratio = (
                sum(matrix[anomaly_index][column] for anomaly_index in range(n_anomalies))
                / prediction_lengths[column]
            )
            if 0.0 < ratio < theta_p:
                for anomaly_index in range(n_anomalies):
                    matrix[anomaly_index][column] = 0.0
                removed_prediction = True
        if not removed_anomaly and not removed_prediction:
            return matrix

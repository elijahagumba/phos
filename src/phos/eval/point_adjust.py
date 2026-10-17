"""Point-adjusted F1, reported beside eTaPR and never used as a headline.

The segment rule is the usual one: if any point inside a contiguous true-attack segment is
predicted, the whole segment is marked predicted, and precision, recall and F1 are then the
ordinary point counts on that adjusted prediction. Unscored points are the caller's job to
leave out of both arrays. This module does not rank detectors and does not read a corpus.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["PointAdjustResult", "point_adjusted_f1"]


class PointAdjustResult(BaseModel):
    """Point precision, recall and F1 after the segment adjustment.

    Attributes:
        precision: True positives over predicted points, after adjustment. Zero when nothing
            is predicted.
        recall: True positives over attack points, after adjustment. Zero when there is no
            attack point.
        f1: Harmonic mean. Zero when precision and recall are both zero.
    """

    model_config = ConfigDict(frozen=True)

    precision: float = Field(ge=0.0)
    recall: float = Field(ge=0.0)
    f1: float = Field(ge=0.0)


def point_adjusted_f1(
    truth: Sequence[bool],
    predicted: Sequence[bool],
) -> PointAdjustResult:
    """Return point-adjusted precision, recall and F1.

    Args:
        truth: One flag per scored point. True is an attack point.
        predicted: One flag per scored point, same length. True is an alert at that point.

    Returns:
        The three rates. An empty series is zero, not a vacuous one.

    Raises:
        ValueError: If the two sequences differ in length.
    """
    if len(truth) != len(predicted):
        raise ValueError(
            f"point-adjusted F1 needs equal lengths, got {len(truth)} and {len(predicted)}"
        )
    if not truth:
        return PointAdjustResult(precision=0.0, recall=0.0, f1=0.0)

    adjusted = list(predicted)
    index = 0
    n_points = len(truth)
    while index < n_points:
        if not truth[index]:
            index += 1
            continue
        end = index + 1
        while end < n_points and truth[end]:
            end += 1
        if any(predicted[index:end]):
            for point in range(index, end):
                adjusted[point] = True
        index = end

    true_positive = 0
    false_positive = 0
    false_negative = 0
    for attack, alert in zip(truth, adjusted, strict=True):
        if attack and alert:
            true_positive += 1
        elif alert:
            false_positive += 1
        elif attack:
            false_negative += 1
    precision = _rate(true_positive, true_positive + false_positive)
    recall = _rate(true_positive, true_positive + false_negative)
    return PointAdjustResult(precision=precision, recall=recall, f1=_f1(precision, recall))


def _rate(numerator: int, denominator: int) -> float:
    """A count ratio, or zero when the denominator is empty."""
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _f1(precision: float, recall: float) -> float:
    """Harmonic mean, zero when both inputs are zero."""
    total = precision + recall
    if total == 0.0:
        return 0.0
    return 2.0 * precision * recall / total

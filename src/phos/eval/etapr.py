"""Enhanced time-series aware precision and recall (eTaPR).

This is the metric in Hwang, Yun, Kim and Min, "Do You Know Existing Accuracy Metrics
Overrate Time-Series Anomaly Detections?", SAC 2022. The arithmetic follows the reference
package eTaPR 22.6.1 (``evaluate_w_ranges``), including the places that package is sharp:
an ambiguous tail is a ratio of the anomaly's span, a one-point tail is ignored, and a
prediction whose overlap is exactly zero is not pruned.

Ranges are inclusive integer indexes, the unit the reference uses. A caller who has
timestamps converts them before calling. ``theta_p`` and ``theta_r`` are required arguments.
``REFERENCE_ETAPR`` is the reference CLI default. ``HAICON_2020`` records the four HAICon
2020 parameters (ADR 0091). Their δ of 180 samples is not :func:`etapr`'s ``delta``.
:func:`etapr_sample_tail` is the integer tail. It still has no ``alpha`` argument.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "HAICON_2020",
    "REFERENCE_ETAPR",
    "EtaPrResult",
    "EtaprSetting",
    "Haicon2020Parameters",
    "etapr",
    "etapr_at",
    "etapr_sample_tail",
]

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


class EtaprSetting(BaseModel):
    """Arguments :func:`etapr` accepts, named so a later score can say which one it used.

    Attributes:
        name: Stable name. ``reference-22.6.1`` is the reference command-line default.
        theta_p: Precision pruning threshold. In ``[0, 1]``.
        theta_r: Recall pruning threshold. In ``[0, 1]``.
        delta: Ambiguous tail as a fraction of ``end - start``. In ``[0, 1]``.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    theta_p: float = Field(ge=0.0, le=1.0)
    theta_r: float = Field(ge=0.0, le=1.0)
    delta: float = Field(ge=0.0, le=1.0)


REFERENCE_ETAPR = EtaprSetting(
    name="reference-22.6.1",
    theta_p=0.5,
    theta_r=0.1,
    delta=0.0,
)


class Haicon2020Parameters(BaseModel):
    """The four values Shin, Lee, Yun and Min set for HAICon 2020.

    CSET 2021, §4.1.2 sets alpha = 0.5, rho = 0.1, pi = 0.7, and delta = 180, and those
    values are not allowed to change. ``theta_p`` is pi. ``theta_r`` is rho. ``alpha`` is
    alpha. ``ambiguous_samples`` is delta.

    :func:`etapr` accepts ``theta_p`` and ``theta_r``. It has no ``alpha`` argument: wheel
    22.6.1 mixes detection and portion as ``(detection + detection * portion) / 2``.
    ``ambiguous_samples`` is an integer sample count on the older TaPR ``compute`` shipped
    in that same wheel. :func:`etapr`'s ``delta`` is a fraction in ``[0, 1]``, and 180 is
    rejected. Calling :func:`etapr` at ``delta=0`` with these thresholds is not the HAICon
    score.

    Attributes:
        name: ``haicon-2020``.
        theta_p: Their pi, 0.7.
        theta_r: Their rho, 0.1.
        alpha: Their alpha, 0.5. Not an :func:`etapr` argument.
        ambiguous_samples: Their δ, 180 samples. Not a fractional ``delta``.
    """

    model_config = ConfigDict(frozen=True)

    name: str = "haicon-2020"
    theta_p: float = Field(default=0.7, ge=0.0, le=1.0)
    theta_r: float = Field(default=0.1, ge=0.0, le=1.0)
    alpha: float = Field(default=0.5, ge=0.0, le=1.0)
    ambiguous_samples: int = Field(default=180, ge=0)


HAICON_2020 = Haicon2020Parameters()


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
        return _zeros()
    return _combine(
        anomaly_ranges,
        prediction_ranges,
        _ambiguous_tails(anomaly_ranges, delta),
        theta_p,
        theta_r,
    )


def etapr_at(
    anomalies: Sequence[tuple[int, int]],
    predictions: Sequence[tuple[int, int]],
    setting: EtaprSetting,
) -> EtaPrResult:
    """Score ranges with a named :class:`EtaprSetting`.

    ``HAICON_2020`` is not an :class:`EtaprSetting`. Its sample count does not fit ``delta``.

    Args:
        anomalies: Ground-truth ranges, as for :func:`etapr`.
        predictions: Predicted ranges, as for :func:`etapr`.
        setting: Named ``theta_p``, ``theta_r`` and fractional ``delta``.

    Returns:
        The same result as calling :func:`etapr` with that setting's three numbers.
    """
    return etapr(
        anomalies,
        predictions,
        theta_p=setting.theta_p,
        theta_r=setting.theta_r,
        delta=setting.delta,
    )


def etapr_sample_tail(
    anomalies: Sequence[tuple[int, int]],
    predictions: Sequence[tuple[int, int]],
    *,
    theta_p: float,
    theta_r: float,
    ambiguous_samples: int,
) -> EtaPrResult:
    """Score ranges with an integer ambiguous tail, in samples.

    The body is eTaPR 22.6.1. The tail is not that package's fractional ``delta``. After
    each anomaly it covers ``ambiguous_samples`` indexes, inclusive, from ``end + 1``
    through ``end + ambiguous_samples``, and it stops one index before the next anomaly.
    A tail whose start is not strictly before its end scores nothing, the same edge as
    :func:`etapr`. ``HAICON_2020.alpha`` is not an argument: the mix stays
    ``(detection + detection * portion) / 2``.

    Args:
        anomalies: Ground-truth ranges, as for :func:`etapr`.
        predictions: Predicted ranges, as for :func:`etapr`.
        theta_p: Precision pruning threshold. HAICon's pi is 0.7.
        theta_r: Recall pruning threshold. HAICon's rho is 0.1.
        ambiguous_samples: Tail length in samples. HAICon's delta is 180. Not a fraction,
            and not rescaled into seconds.

    Returns:
        The same fields as :func:`etapr`.

    Raises:
        ValueError: If a threshold is outside ``[0, 1]``, ``ambiguous_samples`` is
            negative, or a range is inverted.
    """
    _check_unit_interval("theta_p", theta_p)
    _check_unit_interval("theta_r", theta_r)
    if ambiguous_samples < 0:
        raise ValueError(f"ambiguous_samples must be >= 0, got {ambiguous_samples}")
    anomaly_ranges = _sorted_ranges("anomaly", anomalies)
    prediction_ranges = _checked_ranges("prediction", predictions)
    if not anomaly_ranges or not prediction_ranges:
        return _zeros()
    return _combine(
        anomaly_ranges,
        prediction_ranges,
        _sample_tails(anomaly_ranges, ambiguous_samples),
        theta_p,
        theta_r,
    )


def _zeros() -> EtaPrResult:
    """An empty side scores zero. The reference wheel returns NaN or raises."""
    return EtaPrResult(
        etar=0.0,
        etap=0.0,
        f1=0.0,
        etar_detection=0.0,
        etar_portion=0.0,
        etap_detection=0.0,
        etap_portion=0.0,
    )


def _combine(
    anomaly_ranges: Sequence[_Range],
    prediction_ranges: Sequence[_Range],
    ambiguous: Sequence[_Range],
    theta_p: float,
    theta_r: float,
) -> EtaPrResult:
    """Assemble detection and portion scores the way eTaPR 22.6.1 does."""
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


def _sample_tails(anomalies: Sequence[_Range], samples: int) -> list[_Range]:
    """Return an integer tail of ``samples`` indexes after each anomaly.

    Inclusive, so 180 samples run from ``end + 1`` through ``end + 180``. The tail is
    clipped to stop before the next anomaly. A one-sample tail has equal ends and
    :func:`_pair_score` ignores it, matching the fractional scorer.
    """
    tails: list[_Range] = []
    for index, (_, end) in enumerate(anomalies):
        if samples <= 0:
            tails.append((-2, -1))
            continue
        start_id = end + 1
        end_id = start_id + samples - 1
        if index + 1 < len(anomalies) and end_id >= anomalies[index + 1][0]:
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

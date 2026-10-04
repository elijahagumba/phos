"""Recall inside an operator's shift budget.

Published detection papers usually report F1 or eTaPR. This metric asks a different question:
if each shift the operator can read only ``alerts_per_shift`` alerts, what fraction of the
attack windows still contain one of the alerts that were kept.

The shift length defaults to eight hours because that is the unit the question is asked in.
The count of alerts is an argument. It is not a default, and it is not the draft pass mark
in the v1 roadmap. Nothing here retunes a detector.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime, timedelta

from phos.eval.datasets import Dataset
from phos.eval.detectors import Detection

__all__ = ["OPERATOR_SHIFT", "recall_within_budget"]

#: The shift the question is asked in. Not a searched budget.
OPERATOR_SHIFT = timedelta(hours=8)


def recall_within_budget(
    detections: Sequence[Detection],
    dataset: Dataset,
    alerts_per_shift: int,
    *,
    shift: timedelta = OPERATOR_SHIFT,
    tolerance: timedelta = timedelta(0),
) -> float:
    """Return window recall after keeping the top alerts in each shift.

    Alerts are assigned to half-open shifts ``[origin + k * shift, origin + (k + 1) * shift)``.
    The origin is the first observation, or the earliest alert when the corpus has no
    observations. An alert exactly on a boundary belongs to the later shift.

    Within a shift the kept alerts are the highest scores. Ties break toward the earlier
    timestamp, then toward the earlier position in ``detections``, so the result does not
    depend on dict order. Every alert consumes a slot, including one that falls in unscored
    time: the operator read it. Window recall then uses the same tolerance as the rest of
    the harness.

    Args:
        detections: Candidate alerts. Scores may be uncalibrated; this function ranks them
            and does not report the scores.
        dataset: Supplies the attack windows and the origin of the shift clock.
        alerts_per_shift: How many alerts are kept in each shift. A positive integer.
        shift: Length of one shift. Defaults to eight hours.
        tolerance: Slack passed through to window recall.

    Returns:
        Window-level recall of the kept alerts, in ``[0, 1]``.

    Raises:
        ValueError: If ``alerts_per_shift`` is not positive or ``shift`` is not a positive
            duration.
    """
    if alerts_per_shift <= 0:
        raise ValueError(
            f"recall_within_budget needs a positive alert budget, got {alerts_per_shift}"
        )
    if shift <= timedelta(0):
        raise ValueError(f"a shift must be a positive duration, got {shift}")

    # Imported here so metrics.py can re-export this function without a cycle.
    from phos.eval.metrics import window_recall

    origin = _origin(detections, dataset)
    if origin is None:
        return window_recall([], dataset.attack_intervals, tolerance)

    grouped: dict[int, list[tuple[int, Detection]]] = defaultdict(list)
    for index, detection in enumerate(detections):
        grouped[_shift_index(detection.timestamp, origin, shift)].append((index, detection))

    kept: list[Detection] = []
    for group in grouped.values():
        group.sort(key=lambda item: (-item[1].score, item[1].timestamp, item[0]))
        kept.extend(detection for _, detection in group[:alerts_per_shift])
    return window_recall(kept, dataset.attack_intervals, tolerance)


def _origin(detections: Sequence[Detection], dataset: Dataset) -> datetime | None:
    """Return the shift clock's zero, or ``None`` when nothing is timed."""
    if dataset.observations:
        return dataset.observations[0].timestamp
    if not detections:
        return None
    return min(detection.timestamp for detection in detections)


def _shift_index(stamp: datetime, origin: datetime, shift: timedelta) -> int:
    """Return the half-open shift index of ``stamp`` relative to ``origin``."""
    return (stamp - origin) // shift

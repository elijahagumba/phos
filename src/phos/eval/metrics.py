"""The metrics that define "powerful" for a PHOS detector. Pure functions: values in, numbers out.

Nothing here touches disk, holds state, or knows what a detector is. That is deliberate — these
are the definitions the whole project is judged against, so they have to be small enough to
verify by hand.

Two definitional choices shape everything downstream, and both are chosen to match how a SOC
actually judges a detector rather than what scores best on paper:

**Recall is window-level.** An attack is caught if *any* alert lands in its labelled window. A
detector that fires once on a thirty-minute intrusion has caught it; per-sample recall would
score that same detector at a few percent and throw away a working detector.
:func:`recall_sample` is still provided, because the gap between the two numbers says how noisy
a detector is inside an incident — but window recall is the headline.

**False positives are per hour of normal operation.** Not per sample, not per alert. An analyst
lives in wall-clock time, and "three false alarms a shift" is the number that decides whether a
system stays switched on. The denominator is :meth:`Dataset.normal_duration`, which excludes
labelled attack time so a corpus that is mostly attack cannot flatter a noisy detector.

Both are exposed together by :func:`threshold_sweep`, which yields the number that actually
decides adoption: false positives at a fixed recall.

``tolerance`` appears throughout because labelled window boundaries are imprecise. It is applied
**consistently**: an alert forgiven into an attack window by tolerance counts as a true positive
*and* is not counted as a false positive, so no alert is ever rewarded and punished at once.

**Unscored time is neither.** A corpus may declare :attr:`Dataset.unscored_intervals`, stretches
ground truth calls neither attack nor normal (ADR 0082). An alert inside one that is not already a
true positive is dropped from every count here: it is not a false positive, it does not enter
precision or calibration, and the time itself is outside the normal-hour denominator. Unscored
bounds are not widened by ``tolerance``, because forgiving more alerts would only flatter the
false-positive rate.
"""

import bisect
import math
from collections.abc import Sequence
from datetime import datetime, timedelta

from pydantic import BaseModel, ConfigDict, Field

from phos.eval.datasets import Dataset, LabelledInterval
from phos.eval.detectors import Detection

__all__ = [
    "OperatingPoint",
    "ReliabilityBin",
    "brier_score",
    "detection_latency",
    "expected_calibration_error",
    "f1",
    "false_positive_rate",
    "false_positives",
    "false_positives_per_day",
    "precision",
    "precision_at_budget",
    "recall_sample",
    "reliability_table",
    "threshold_sweep",
    "unscored_alerts",
    "window_recall",
]

_SECONDS_PER_HOUR = 3600.0
_HOURS_PER_DAY = 24.0


class OperatingPoint(BaseModel):
    """What a detector achieves at one alerting threshold.

    Attributes:
        threshold: The score at or above which a detection was treated as an alert.
        recall: Window-level recall at this threshold.
        fp_rate: False positives per hour of normal operation at this threshold.
        precision: Fraction of alerts that landed in an attack window.
    """

    model_config = ConfigDict(frozen=True)

    threshold: float
    recall: float = Field(ge=0.0, le=1.0)
    fp_rate: float = Field(ge=0.0)
    precision: float = Field(ge=0.0, le=1.0)


class ReliabilityBin(BaseModel):
    """One row of a reliability table: what was promised versus what happened.

    Attributes:
        lower: Inclusive lower edge of the confidence bin.
        upper: Upper edge of the confidence bin.
        count: Alerts falling in this bin. Zero for an unpopulated bin, whose other statistics
            are reported as zero and excluded from the calibration error.
        mean_confidence: Mean confidence the detector claimed in this bin.
        empirical_rate: Fraction of this bin's alerts that were genuinely attacks.
    """

    model_config = ConfigDict(frozen=True)

    lower: float = Field(ge=0.0, le=1.0)
    upper: float = Field(ge=0.0, le=1.0)
    count: int = Field(ge=0)
    mean_confidence: float = Field(ge=0.0, le=1.0)
    empirical_rate: float = Field(ge=0.0, le=1.0)


def _matches(timestamp: datetime, interval: LabelledInterval, tolerance: timedelta) -> bool:
    """Return whether ``timestamp`` falls in ``interval``, widened by ``tolerance`` each side."""
    return interval.start - tolerance <= timestamp <= interval.end + tolerance


def _is_true_positive(
    timestamp: datetime,
    intervals: Sequence[LabelledInterval],
    tolerance: timedelta,
) -> bool:
    """Return whether an alert at ``timestamp`` lands in any attack window.

    The single definition of "this alert was right", shared by every metric here so that the
    true-positive and false-positive counts can never disagree.
    """
    return any(_matches(timestamp, interval, tolerance) for interval in intervals)


def _scored_outcomes(
    detections: Sequence[Detection],
    dataset: Dataset,
    tolerance: timedelta,
) -> list[tuple[Detection, bool]]:
    """Return ``(alert, is_true_positive)`` for every alert that ground truth scores.

    An alert that is not a true positive and falls inside an unscored interval is left out, so
    it can be neither rewarded nor punished. This is the single place that decision is made.
    """
    outcomes: list[tuple[Detection, bool]] = []
    for detection in detections:
        hit = _is_true_positive(detection.timestamp, dataset.attack_intervals, tolerance)
        if hit or not dataset.is_unscored(detection.timestamp):
            outcomes.append((detection, hit))
    return outcomes


def unscored_alerts(
    detections: Sequence[Detection],
    dataset: Dataset,
    tolerance: timedelta = timedelta(0),
) -> int:
    """Return how many alerts fell in unscored time and were therefore set aside.

    Every alert is exactly one of: a true positive, a false positive, or unscored. Reporting this
    count keeps the three adding up to the alert total, so an excluded alert is visible rather than
    silently missing.
    """
    return len(detections) - len(_scored_outcomes(detections, dataset, tolerance))


def window_recall(
    detections: Sequence[Detection],
    intervals: Sequence[LabelledInterval],
    tolerance: timedelta = timedelta(0),
) -> float:
    """Return the fraction of attack windows containing at least one alert.

    Args:
        detections: The alert set (already thresholded).
        intervals: Ground-truth attack windows.
        tolerance: Slack applied to each window's bounds.

    Returns:
        Detected windows divided by total windows, in ``[0, 1]``. A corpus with no attack
        windows returns ``0.0`` rather than a vacuous ``1.0``, so a detector cannot claim
        perfect recall on a corpus that never tested it.
    """
    if not intervals:
        return 0.0
    detected = sum(
        1
        for interval in intervals
        if any(_matches(detection.timestamp, interval, tolerance) for detection in detections)
    )
    return detected / len(intervals)


def false_positives(
    detections: Sequence[Detection],
    dataset: Dataset,
    tolerance: timedelta = timedelta(0),
) -> int:
    """Return the number of alerts that fall in no attack window and no unscored window."""
    return sum(1 for _, hit in _scored_outcomes(detections, dataset, tolerance) if not hit)


def false_positive_rate(
    detections: Sequence[Detection],
    dataset: Dataset,
    tolerance: timedelta = timedelta(0),
) -> float:
    """Return false positives per hour of normal operation.

    Returns:
        The rate. A corpus with no normal time yields ``0.0`` when there were no false positives
        and ``inf`` when there were — there is no normal time to amortise them over, and saying
        so is more honest than inventing a denominator.
    """
    count = false_positives(detections, dataset, tolerance)
    hours = dataset.normal_duration().total_seconds() / _SECONDS_PER_HOUR
    if hours <= 0.0:
        return 0.0 if count == 0 else math.inf
    return count / hours


def false_positives_per_day(fp_per_hour: float) -> float:
    """Convert a frozen per-hour false-positive rate into a per-day rate.

    This is arithmetic on an already-measured rate. It does not retune a detector and it
    does not overwrite a public log name. Distillation 18.72 FP/hour becomes 449.28 FP/day,
    which is why 2-3/day stays refused.
    """
    return fp_per_hour * _HOURS_PER_DAY


def detection_latency(
    detections: Sequence[Detection],
    intervals: Sequence[LabelledInterval],
) -> list[timedelta]:
    """Return, for each detected window, the delay from its start to the first alert inside it.

    Only alerts strictly inside a window count, so a latency is never negative. An alert that
    only matched a window because of ``tolerance`` therefore contributes no latency: there is no
    meaningful "time to detect" for an alert that preceded the attack.

    Returns:
        One entry per *detected* window, in the order the windows were given. Undetected windows
        contribute nothing, so the list is shorter than ``intervals`` whenever recall is < 1.
    """
    latencies: list[timedelta] = []
    for interval in intervals:
        inside = [d.timestamp for d in detections if interval.contains(d.timestamp)]
        if inside:
            latencies.append(min(inside) - interval.start)
    return latencies


def precision(
    detections: Sequence[Detection],
    dataset: Dataset,
    tolerance: timedelta = timedelta(0),
) -> float:
    """Return the fraction of scored alerts that landed in an attack window.

    Alerts in unscored time are not in the denominator. An empty scored alert set returns
    ``0.0``: firing nothing is not perfect precision.
    """
    outcomes = _scored_outcomes(detections, dataset, tolerance)
    if not outcomes:
        return 0.0
    return sum(1 for _, hit in outcomes if hit) / len(outcomes)


def precision_at_budget(ranked_is_true_positive: Sequence[bool], budget: int) -> float:
    """Return precision among the first ``budget`` ranked alerts.

    CERT 6B at 48 is 5 true positives in 48 alerts: ``5 / 48``. An empty ranking or a
    non-positive budget is not a CERT row — budget must be a positive operator volume.
    """
    if budget <= 0:
        raise ValueError(f"precision_at_budget needs a positive alert budget, got {budget}")
    taken = list(ranked_is_true_positive)[:budget]
    if not taken:
        return 0.0
    return sum(1.0 for hit in taken if hit) / float(budget)


def recall_sample(
    detections: Sequence[Detection],
    dataset: Dataset,
    tolerance: timedelta = timedelta(0),
) -> float:
    """Return the fraction of attack-labelled observations that had an alert at their instant.

    This is the pessimistic counterpart to :func:`window_recall`: it asks whether *every* moment
    of an attack was flagged, not merely whether the attack was noticed. Reported alongside
    window recall, the gap between them describes how continuously a detector fires inside an
    incident.

    Returns:
        Covered attack samples over total attack samples. A corpus with no attack-labelled
        observations returns ``0.0``.
    """
    attack_stamps = [
        observation.timestamp
        for observation in dataset.observations
        if dataset.is_attack(observation.timestamp)
    ]
    if not attack_stamps:
        return 0.0

    alert_stamps = sorted(detection.timestamp for detection in detections)
    covered = sum(1 for stamp in attack_stamps if _has_alert_near(alert_stamps, stamp, tolerance))
    return covered / len(attack_stamps)


def _has_alert_near(
    alert_stamps: Sequence[datetime], stamp: datetime, tolerance: timedelta
) -> bool:
    """Return whether a sorted alert list contains an alert within ``tolerance`` of ``stamp``."""
    index = bisect.bisect_left(alert_stamps, stamp - tolerance)
    return index < len(alert_stamps) and alert_stamps[index] <= stamp + tolerance


def f1(precision_value: float, recall_value: float) -> float:
    """Return the harmonic mean of precision and recall, or ``0.0`` if both are zero."""
    total = precision_value + recall_value
    if total == 0.0:
        return 0.0
    return 2.0 * precision_value * recall_value / total


def threshold_sweep(
    detections: Sequence[Detection],
    dataset: Dataset,
    thresholds: Sequence[float],
    tolerance: timedelta = timedelta(0),
) -> list[OperatingPoint]:
    """Return the recall / FP-rate / precision achieved at each alerting threshold.

    This is the curve that answers the adoption question — *how many false alarms per hour does
    it take to catch 90% of incidents?* — which a single operating point cannot.

    Args:
        detections: All scored detections, not just the ones above some threshold.
        dataset: The corpus, supplying both ground truth and the normal-time denominator.
        thresholds: Scores to evaluate at. Returned in the order given.
        tolerance: Slack applied to attack-window bounds.

    Returns:
        One `OperatingPoint` per threshold. Recall and FP rate are non-increasing as the
        threshold rises, because raising it can only shrink the alert set. Precision is not
        monotone and is not expected to be.
    """
    points: list[OperatingPoint] = []
    for threshold in thresholds:
        alerts = [detection for detection in detections if detection.score >= threshold]
        points.append(
            OperatingPoint(
                threshold=threshold,
                recall=window_recall(alerts, dataset.attack_intervals, tolerance),
                fp_rate=false_positive_rate(alerts, dataset, tolerance),
                precision=precision(alerts, dataset, tolerance),
            )
        )
    return points


def reliability_table(
    detections: Sequence[Detection],
    dataset: Dataset,
    n_bins: int = 10,
    tolerance: timedelta = timedelta(0),
) -> list[ReliabilityBin]:
    """Bin alerts by claimed confidence and report how often each bin was actually right.

    This is what makes Constitution §3.3 measurable: a detector claiming 90% should be right
    about 90% of the time in the ``[0.9, 1.0]`` bin. PART 4 fits calibrators against it; this
    PART only measures.

    Args:
        detections: The alert set.
        dataset: Supplies ground truth for each alert.
        n_bins: Number of equal-width bins spanning ``[0, 1]``.
        tolerance: Slack applied to attack-window bounds.

    Returns:
        Exactly ``n_bins`` rows in ascending confidence order, including unpopulated ones so the
        table can be plotted directly. Confidence of exactly 1.0 falls in the last bin.

    Raises:
        ValueError: If ``n_bins`` is not positive.
    """
    if n_bins < 1:
        raise ValueError(f"a reliability table needs at least one bin, got {n_bins}")

    buckets: list[list[tuple[float, int]]] = [[] for _ in range(n_bins)]
    for detection, hit in _scored_outcomes(detections, dataset, tolerance):
        index = min(int(detection.confidence * n_bins), n_bins - 1)
        buckets[index].append((detection.confidence, int(hit)))

    table: list[ReliabilityBin] = []
    for index, bucket in enumerate(buckets):
        count = len(bucket)
        table.append(
            ReliabilityBin(
                lower=index / n_bins,
                upper=(index + 1) / n_bins,
                count=count,
                mean_confidence=(
                    sum(confidence for confidence, _ in bucket) / count if count else 0.0
                ),
                empirical_rate=(sum(outcome for _, outcome in bucket) / count if count else 0.0),
            )
        )
    return table


def expected_calibration_error(
    detections: Sequence[Detection],
    dataset: Dataset,
    n_bins: int = 10,
    tolerance: timedelta = timedelta(0),
) -> float:
    """Return the population-weighted mean gap between claimed and empirical attack rates.

    Zero means every confidence bin was right as often as it said it would be. Bins are weighted
    by how many alerts they hold, so one wild claim made once cannot dominate the score.
    Unpopulated bins contribute nothing. No detections means nothing was claimed, so ``0.0``.
    """
    table = reliability_table(detections, dataset, n_bins, tolerance)
    total = sum(row.count for row in table)
    if total == 0:
        return 0.0
    return sum((row.count / total) * abs(row.mean_confidence - row.empirical_rate) for row in table)


def brier_score(
    detections: Sequence[Detection],
    dataset: Dataset,
    tolerance: timedelta = timedelta(0),
) -> float:
    """Return the mean squared error between claimed confidence and the actual outcome.

    Unlike the calibration error this punishes hedging as well as miscalibration: a detector
    that answers 0.5 to everything is perfectly calibrated on a balanced corpus but scores a
    mediocre Brier. Lower is better; ``0.0`` for an empty alert set.
    """
    outcomes = _scored_outcomes(detections, dataset, tolerance)
    if not outcomes:
        return 0.0
    total = 0.0
    for detection, hit in outcomes:
        total += (detection.confidence - float(hit)) ** 2
    return total / len(outcomes)

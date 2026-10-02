"""The harness: run a detector over a labelled corpus and score it.

This is the ruler. Per Constitution §3.5 nothing in PHOS is trusted until it has been measured
here, and every engine built later — Atlas, Sentiel, Intelligence — is scored by this same
function so their numbers stay comparable.

:func:`evaluate` is deterministic: the same detector, corpus and config always produce the same
report, save for the wall-clock ``created_at`` stamp. It performs no I/O; writing a report to
the experiment log is a separate, explicit step (`phos.eval.report.append_to_experiment_log`).
"""

import logging
from datetime import timedelta

import numpy
from pydantic import BaseModel, ConfigDict, Field

from phos.eval.datasets import Dataset
from phos.eval.detectors import Detection, Detector
from phos.eval.metrics import (
    brier_score,
    detection_latency,
    expected_calibration_error,
    f1,
    false_positive_rate,
    false_positives,
    precision,
    recall_sample,
    reliability_table,
    threshold_sweep,
    unscored_alerts,
    window_recall,
)
from phos.eval.report import EvaluationReport, LatencySummary

__all__ = ["EvalConfig", "evaluate", "sweep_thresholds"]

logger = logging.getLogger(__name__)

_SECONDS_PER_HOUR = 3600.0
_SWEEP_POINTS = 11


class EvalConfig(BaseModel):
    """The knobs that decide what a run of the harness means.

    Every one of these is recorded on the resulting report, because a metric without the
    settings that produced it cannot be compared against another metric.

    Attributes:
        alert_threshold: Detections scoring at or above this are treated as alerts. Detections
            below it are still used for the threshold sweep.
        match_tolerance: Slack applied to attack-window bounds, absorbing imprecision in the
            corpus's labels. Applied consistently to true-positive and false-positive accounting
            alike, so an alert forgiven into a window is never also charged as a false alarm.
        calibration_bins: Number of confidence bins in the reliability table.
        seed: Seeds any randomness in a run. Nothing in this PART is stochastic; the field
            exists so the number is on the record from the start and later PARTs inherit it.
    """

    model_config = ConfigDict(frozen=True)

    alert_threshold: float = 0.0
    match_tolerance: timedelta = Field(default=timedelta(0), ge=timedelta(0))
    calibration_bins: int = Field(default=10, ge=1)
    seed: int = 7


def evaluate(detector: Detector, dataset: Dataset, config: EvalConfig) -> EvaluationReport:
    """Score ``detector`` against ``dataset`` and return the full report.

    Args:
        detector: Anything satisfying the `Detector` protocol.
        dataset: A labelled corpus from any `DatasetAdapter`.
        config: Threshold, tolerance, calibration bins and seed.

    Returns:
        An `EvaluationReport` carrying every metric plus the settings that produced it.

    Note:
        Deterministic. Two calls with equal arguments produce reports that differ only in
        ``created_at``. Session C2: this function never applies a saturation policy. A loud
        corpus stays ``MEASURED`` unless a caller opts into `apply_saturation_policy`. Public
        distillation 18.72 and Data4Cyber Track A names stay comparable because they omit
        that call.
    """
    tolerance = config.match_tolerance
    detections = detector.run(dataset)
    alerts = [detection for detection in detections if detection.score >= config.alert_threshold]
    logger.info(
        "evaluating %s on %s: %d detections, %d alerts at threshold %s",
        detector.name,
        dataset.name,
        len(detections),
        len(alerts),
        config.alert_threshold,
    )

    alert_precision = precision(alerts, dataset, tolerance)
    sample_recall = recall_sample(alerts, dataset, tolerance)

    return EvaluationReport(
        detector_name=detector.name,
        dataset_name=dataset.name,
        domain=dataset.domain,
        seed=config.seed,
        source_note=dataset.source_note,
        alert_threshold=config.alert_threshold,
        match_tolerance_seconds=tolerance.total_seconds(),
        calibration_bins=config.calibration_bins,
        n_observations=len(dataset.observations),
        n_detections=len(detections),
        n_alerts=len(alerts),
        n_attack_intervals=len(dataset.attack_intervals),
        n_unscored_intervals=len(dataset.unscored_intervals),
        n_unscored_alerts=unscored_alerts(alerts, dataset, tolerance),
        normal_hours=dataset.normal_duration().total_seconds() / _SECONDS_PER_HOUR,
        window_recall=window_recall(alerts, dataset.attack_intervals, tolerance),
        false_positives=false_positives(alerts, dataset, tolerance),
        false_positive_rate=false_positive_rate(alerts, dataset, tolerance),
        precision=alert_precision,
        recall_sample=sample_recall,
        f1=f1(alert_precision, sample_recall),
        latency=LatencySummary.from_latencies(detection_latency(alerts, dataset.attack_intervals)),
        operating_points=threshold_sweep(
            detections, dataset, sweep_thresholds(detections), tolerance
        ),
        expected_calibration_error=expected_calibration_error(
            alerts, dataset, config.calibration_bins, tolerance
        ),
        brier_score=brier_score(alerts, dataset, tolerance),
        reliability=reliability_table(alerts, dataset, config.calibration_bins, tolerance),
    )


def sweep_thresholds(detections: list[Detection], count: int = _SWEEP_POINTS) -> list[float]:
    """Pick thresholds for the operating-point curve from the score distribution.

    Quantiles rather than an even split of the score range, so the curve spends its points where
    the scores actually are — an even split is mostly empty when scores are heavily skewed,
    which anomaly scores always are. Duplicate quantiles are collapsed, so a detector emitting
    one distinct score yields one operating point rather than eleven identical ones.

    Returns:
        Distinct thresholds in ascending order; empty when there are no detections.
    """
    if not detections:
        return []
    scores = numpy.asarray([detection.score for detection in detections], dtype=float)
    quantiles = numpy.quantile(scores, numpy.linspace(0.0, 1.0, count))
    return sorted({float(quantile) for quantile in quantiles})

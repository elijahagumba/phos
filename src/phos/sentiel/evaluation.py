"""Scoring a detector when the malicious thing is a *person*, not a moment.

PART 2's harness matches an alert to ground truth by time alone. For Atlas that is right: an
attacker manipulating a pump is attacking the plant, and every alert inside the window concerns the
same event. For Sentiel it is wrong, and wrong in a way that flatters a broken detector — see
`phos.sentiel.labels` for the arithmetic (r3.1 labels 2 users out of 1000; a detector alerting on
everyone every day would score perfect time-only recall).

This module fixes the matching without touching PART 2, and reuses PART 2's metric math rather than
restating it. The mechanism is a **partition**:

    Within one user's slice of the corpus, time-only matching and entity-scoped matching agree
    exactly.

So the corpus is split per user; each slice becomes an ordinary PART 2 `Dataset` carrying only that
user's windows and only that user's alerts; PART 2's own `window_recall`, `false_positives`,
`detection_latency`, `reliability_table`, `expected_calibration_error` and `brier_score` are called
on the slices; and the results are pooled by count. Every matching decision — including how
``match_tolerance`` widens a window — is therefore made by PART 2, and a change there changes
Sentiel's numbers too, which is what "one ruler" is supposed to mean.

Two consequences are recorded rather than hidden:

- **A user with no labels contributes every one of their alerts as a false positive**, which is the
  correct and expensive answer, and is where a peer-blind detector will lose most of its precision.
- **The false-positive denominator is normal *user*-hours**, summed across the population, not
  wall-clock hours. An organisation of a thousand people generates a thousand hours of behaviour
  per hour, and an analyst's alert budget scales with the population, not the clock. The field is
  `EvaluationReport.normal_hours` because the report is shared with Atlas; the unit difference is
  stated in `source_note` on every Sentiel run so no one compares the two numbers by accident.

The output is a PART 2 `EvaluationReport` — deliberately, so Sentiel runs land in the same
experiment log, through the same `append_to_experiment_log`, with no new report type to reconcile.
"""

import logging
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import timedelta
from typing import Final

from phos.eval import (
    Dataset,
    Detection,
    Detector,
    EvalConfig,
    EvaluationReport,
    LabelledInterval,
    LatencySummary,
    OperatingPoint,
    ReliabilityBin,
    brier_score,
    detection_latency,
    expected_calibration_error,
    f1,
    false_positives,
    recall_sample,
    reliability_table,
    sweep_thresholds,
    window_recall,
)
from phos.ontology import Domain
from phos.sentiel.entities import user_id_of
from phos.sentiel.labels import EntityLabelledInterval

__all__ = [
    "SENTIEL_CAVEATS",
    "base_rate",
    "entity_aware_detections",
    "evaluate_entity_aware",
    "sentiel_source_note",
]

logger = logging.getLogger(__name__)

_SECONDS_PER_HOUR: Final = 3600.0

SENTIEL_CAVEATS: Final[tuple[str, ...]] = (
    "CERT is SYNTHETIC: simulated users and simulated attackers, not observed enterprise "
    "activity. A good number here demonstrates the machinery works; it does not demonstrate "
    "real-world capability, and simulated insiders may be cleaner and more obvious than real ones.",
    "The featurisation is a per-entity STARTER set (8 count features over a one-day window). "
    "There is no relationship context (PART 6A) and no peer-group baselining (PART 6B), so this "
    "baseline is expected to miss the insider whose own history looks unremarkable and whose "
    "peers' does not — which is the class 6B exists to catch.",
    "Ground truth is ENTITY-SCOPED: a detection counts only when it names the labelled malicious "
    "user inside their labelled window. The false-positive denominator is normal USER-hours summed "
    "across the population, not wall-clock hours, and is not comparable to an Atlas FP rate.",
)
"""The three things that must travel with every Sentiel number (PART 6·D §6).

Exported as data rather than prose in a docstring so `sentiel_source_note` can stamp them onto
every report and a test can assert they are present.
"""


def sentiel_source_note(prefix: str, base_rate: str = "") -> str:
    """Return a `Dataset.source_note` carrying the mandatory caveats.

    Args:
        prefix: Provenance for this particular corpus — release, files, split.
        base_rate: How many user-windows are malicious versus benign, when known.

    Returns:
        One string, caveats appended, suitable for `Dataset.source_note` and therefore copied onto
        every `EvaluationReport` the corpus produces.
    """
    parts = [prefix, *([base_rate] if base_rate else []), *SENTIEL_CAVEATS]
    return " | ".join(part.strip() for part in parts if part.strip())


def _user_of(detection: Detection) -> str:
    """Return the user a detection concerns.

    Raises:
        ValueError: If the detection names no entity. Sentiel scores by user, so a detection that
            does not say who it is about cannot be scored at all — and guessing would silently
            attribute it to somebody.
    """
    if not detection.entity_ids:
        raise ValueError(
            "a Sentiel detection must name the entity it concerns; this one names none, so it "
            "cannot be matched against entity-scoped ground truth"
        )
    return user_id_of(detection.entity_ids[0])


def _labels_by_user(
    labels: Sequence[EntityLabelledInterval],
) -> dict[str, list[LabelledInterval]]:
    """Group labels by user, projected to PART 2 intervals.

    The projection drops the user id, which is only sound because each list is thereafter matched
    against that same user's detections and nothing else. See
    `EntityLabelledInterval.as_labelled_interval`.
    """
    grouped: dict[str, list[LabelledInterval]] = defaultdict(list)
    for label in labels:
        grouped[label.user_id].append(label.as_labelled_interval())
    return dict(grouped)


def _shell(user_id: str, intervals: Sequence[LabelledInterval]) -> Dataset:
    """Return an observation-free `Dataset` carrying one user's windows.

    Used only to hand PART 2's `false_positives` the ground truth it expects, so that the decision
    "did this alert land in a window" — tolerance included — is made by PART 2 rather than restated
    here.
    """
    return Dataset(
        name=f"sentiel-user-{user_id}",
        domain=Domain.SENTIEL,
        observations=[],
        attack_intervals=list(intervals),
    )


def entity_aware_detections(
    detections: Sequence[Detection],
    labels: Sequence[EntityLabelledInterval],
    tolerance: timedelta = timedelta(0),
) -> tuple[list[Detection], list[Detection]]:
    """Split detections into those that named the right user in the right window, and the rest.

    This is the one primitive PART 2 cannot supply, and everything else in this module is built on
    it. A detection about user V inside user U's malicious window is a **false positive**: it names
    an innocent person.

    Args:
        detections: The alert set.
        labels: Entity-scoped ground truth.
        tolerance: Slack applied to each window's bounds, with PART 2's semantics.

    Returns:
        ``(true_positives, false_positives)``, each in the input order.

    Raises:
        ValueError: If a detection names no entity.
    """
    by_user = _labels_by_user(labels)
    shells = {user_id: _shell(user_id, intervals) for user_id, intervals in by_user.items()}

    hits: list[Detection] = []
    misses: list[Detection] = []
    for detection in detections:
        shell = shells.get(_user_of(detection))
        # No labels for this user means nothing about them can be a true positive — the common
        # case, and the one that makes precision expensive.
        if shell is not None and false_positives([detection], shell, tolerance) == 0:
            hits.append(detection)
        else:
            misses.append(detection)
    return hits, misses


class _Slice:
    """One user's corpus, alerts and ground truth — an ordinary PART 2 problem."""

    __slots__ = ("alerts", "dataset", "intervals", "user_id")

    def __init__(
        self,
        user_id: str,
        dataset: Dataset,
        alerts: list[Detection],
        intervals: list[LabelledInterval],
    ) -> None:
        self.user_id = user_id
        self.dataset = dataset
        self.alerts = alerts
        self.intervals = intervals

    def attack_samples(self) -> int:
        """Return how many of this user's observations ground truth calls malicious."""
        return sum(
            1
            for observation in self.dataset.observations
            if self.dataset.is_attack(observation.timestamp)
        )


def _slices(
    dataset: Dataset,
    alerts: Sequence[Detection],
    labels: Sequence[EntityLabelledInterval],
) -> list[_Slice]:
    """Partition the corpus, the alerts and the truth by user.

    Every user appearing in the corpus gets a slice, including the overwhelming majority with no
    labels — their alerts are exactly the false positives that make the number honest.
    """
    by_user = _labels_by_user(labels)
    observations: dict[str, list] = defaultdict(list)  # type: ignore[type-arg]
    for observation in dataset.observations:
        observations[user_id_of(observation.entity_ids[0])].append(observation)

    grouped_alerts: dict[str, list[Detection]] = defaultdict(list)
    for detection in alerts:
        grouped_alerts[_user_of(detection)].append(detection)

    user_ids = sorted(observations.keys() | grouped_alerts.keys() | by_user.keys())
    return [
        _Slice(
            user_id=user_id,
            dataset=Dataset(
                name=f"{dataset.name}-{user_id}",
                domain=dataset.domain,
                observations=observations.get(user_id, []),
                attack_intervals=by_user.get(user_id, []),
                source_note=dataset.source_note,
            ),
            alerts=grouped_alerts.get(user_id, []),
            intervals=by_user.get(user_id, []),
        )
        for user_id in user_ids
    ]


def _pooled_recall(slices: Sequence[_Slice], tolerance: timedelta) -> tuple[int, int]:
    """Return ``(windows detected, windows total)`` across every user.

    Each window is asked about on its own, through PART 2's `window_recall`, against only its own
    user's alerts — so the answer is 1.0 or 0.0 per window and pooling is an exact integer count
    rather than an average of averages.
    """
    detected = 0
    total = 0
    for user_slice in slices:
        for interval in user_slice.intervals:
            total += 1
            detected += int(window_recall(user_slice.alerts, [interval], tolerance) == 1.0)
    return detected, total


def _pooled_reliability(
    slices: Sequence[_Slice], n_bins: int, tolerance: timedelta
) -> list[ReliabilityBin]:
    """Merge each user's PART 2 reliability table into one, weighting by bin population."""
    counts = [0] * n_bins
    confidence = [0.0] * n_bins
    outcomes = [0.0] * n_bins
    for user_slice in slices:
        if not user_slice.alerts:
            continue
        for index, row in enumerate(
            reliability_table(user_slice.alerts, user_slice.dataset, n_bins, tolerance)
        ):
            counts[index] += row.count
            confidence[index] += row.mean_confidence * row.count
            outcomes[index] += row.empirical_rate * row.count
    return [
        ReliabilityBin(
            lower=index / n_bins,
            upper=(index + 1) / n_bins,
            count=counts[index],
            mean_confidence=confidence[index] / counts[index] if counts[index] else 0.0,
            empirical_rate=outcomes[index] / counts[index] if counts[index] else 0.0,
        )
        for index in range(n_bins)
    ]


def _weighted(values: Sequence[tuple[float, int]]) -> float:
    """Return a population-weighted mean of ``(value, weight)`` pairs; ``0.0`` if unpopulated."""
    total = sum(weight for _, weight in values)
    if total == 0:
        return 0.0
    return sum(value * weight for value, weight in values) / total


def _operating_point(
    slices: Sequence[_Slice],
    threshold: float,
    normal_hours: float,
    tolerance: timedelta,
) -> OperatingPoint:
    """Return the entity-aware recall / FP-rate / precision at one alerting threshold."""
    thresholded = [
        _Slice(
            user_slice.user_id,
            user_slice.dataset,
            [alert for alert in user_slice.alerts if alert.score >= threshold],
            user_slice.intervals,
        )
        for user_slice in slices
    ]
    detected, total = _pooled_recall(thresholded, tolerance)
    n_alerts = sum(len(user_slice.alerts) for user_slice in thresholded)
    n_false = sum(
        false_positives(user_slice.alerts, user_slice.dataset, tolerance)
        for user_slice in thresholded
    )
    return OperatingPoint(
        threshold=threshold,
        recall=detected / total if total else 0.0,
        fp_rate=(n_false / normal_hours) if normal_hours > 0.0 else 0.0,
        precision=((n_alerts - n_false) / n_alerts) if n_alerts else 0.0,
    )


def evaluate_entity_aware(
    detector: Detector,
    dataset: Dataset,
    labels: Sequence[EntityLabelledInterval],
    config: EvalConfig,
) -> EvaluationReport:
    """Score ``detector`` against ``dataset`` using entity-scoped ground truth.

    Args:
        detector: Anything satisfying PART 2's `Detector` protocol — Sentiel adds no detector type.
        dataset: The per-user-window corpus. Its `Dataset.attack_intervals` must be **empty**:
            Sentiel's truth is entity-scoped and arrives through ``labels``.
        labels: Entity-scoped ground truth.
        config: Threshold, tolerance, calibration bins and seed — PART 2's own config, unchanged.

    Returns:
        A PART 2 `EvaluationReport`, so a Sentiel run lands in the shared experiment log alongside
        every Atlas run. ``normal_hours`` and therefore ``false_positive_rate`` are per normal
        **user**-hour; see the module docstring.

    Raises:
        ValueError: If ``dataset`` carries time-only attack intervals, or a detection names no
            entity.

    Note:
        Deterministic. Two calls with equal arguments produce reports differing only in
        ``created_at``.
    """
    if dataset.attack_intervals:
        raise ValueError(
            f"{dataset.name} carries {len(dataset.attack_intervals)} time-only attack interval(s). "
            "Sentiel ground truth is entity-scoped and is passed separately as `labels`; a "
            "time-only window here would score a detection about the wrong user as a hit."
        )

    tolerance = config.match_tolerance
    detections = detector.run(dataset)
    alerts = [detection for detection in detections if detection.score >= config.alert_threshold]
    slices = _slices(dataset, alerts, labels)

    normal_hours = (
        sum(
            (user_slice.dataset.normal_duration() for user_slice in slices),
            timedelta(0),
        ).total_seconds()
        / _SECONDS_PER_HOUR
    )
    detected, total_windows = _pooled_recall(slices, tolerance)
    n_false = sum(
        false_positives(user_slice.alerts, user_slice.dataset, tolerance) for user_slice in slices
    )
    alert_precision = ((len(alerts) - n_false) / len(alerts)) if alerts else 0.0
    sample_recall = _weighted(
        [
            (
                recall_sample(user_slice.alerts, user_slice.dataset, tolerance),
                user_slice.attack_samples(),
            )
            for user_slice in slices
        ]
    )
    latencies = [
        latency
        for user_slice in slices
        for latency in detection_latency(user_slice.alerts, user_slice.intervals)
    ]
    logger.info(
        "entity-aware evaluation of %s on %s: %d alerts over %d users, %d/%d windows caught, "
        "%d false positives across %.1f normal user-hours",
        detector.name,
        dataset.name,
        len(alerts),
        len(slices),
        detected,
        total_windows,
        n_false,
        normal_hours,
    )

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
        n_attack_intervals=total_windows,
        normal_hours=normal_hours,
        window_recall=(detected / total_windows) if total_windows else 0.0,
        false_positives=n_false,
        false_positive_rate=(n_false / normal_hours) if normal_hours > 0.0 else 0.0,
        precision=alert_precision,
        recall_sample=sample_recall,
        f1=f1(alert_precision, sample_recall),
        latency=LatencySummary.from_latencies(latencies),
        operating_points=[
            _operating_point(slices, threshold, normal_hours, tolerance)
            for threshold in sweep_thresholds(detections)
        ],
        expected_calibration_error=_weighted(
            [
                (
                    expected_calibration_error(
                        user_slice.alerts, user_slice.dataset, config.calibration_bins, tolerance
                    ),
                    len(user_slice.alerts),
                )
                for user_slice in slices
            ]
        ),
        brier_score=_weighted(
            [
                (
                    brier_score(user_slice.alerts, user_slice.dataset, tolerance),
                    len(user_slice.alerts),
                )
                for user_slice in slices
            ]
        ),
        reliability=_pooled_reliability(slices, config.calibration_bins, tolerance),
    )


def base_rate(dataset: Dataset, labels: Sequence[EntityLabelledInterval]) -> Mapping[str, int]:
    """Return how many user-windows ground truth calls malicious, and how many it does not.

    PART 6·D §6.3 requires this on the record: if malicious windows are rare — and two users out of
    a thousand is very rare — then the evidence-weight ceiling that starved Atlas's reasoning layer
    may apply to Sentiel too, and a run should say so rather than let a reader assume otherwise.
    """
    windows = {
        (user_id_of(observation.entity_ids[0]), observation.timestamp)
        for observation in dataset.observations
    }
    malicious = sum(
        1 for user_id, stamp in windows if any(label.contains(user_id, stamp) for label in labels)
    )
    return {"malicious_user_windows": malicious, "benign_user_windows": len(windows) - malicious}

"""Score one detector against an exam: per-plant metrics, then aggregated honestly.

PART S6. Every per-plant number that `phos.eval` already defines — false alarms per normal hour,
window recall, detection delay, calibration — is computed by calling `phos.eval.evaluate`
unchanged; this module adds only what an exam needs on top: per-technique and per-fault-type
recall, stealthy-attack recall reported separately, physical-effect attacks missed, and, when the
detector is Atlas, fault-versus-attack discrimination and uncertainty honesty. Nothing here
refits, retunes or re-derives a metric `phos.eval.metrics` already owns.

**Aggregation never reports one number alone.** `Summary` carries the mean, the standard
deviation, the 5th/50th/95th percentiles, the worst plant, and a bootstrap confidence interval for
the mean, because a mean without its spread is not what §"Scoring" of the S6 brief asks a referee
to produce.
"""

from __future__ import annotations

import logging
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import timedelta

import numpy

from phos.atlas.templates import (
    ENGINEERING_MAINTENANCE_TEMPLATE_ID,
    SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID,
    UNAUTHORISED_CONTROL_TEMPLATE_ID,
)
from phos.eval import (
    Dataset,
    Detection,
    Detector,
    EvalConfig,
    EvaluationReport,
    LabelledInterval,
    evaluate,
)
from phos.eval.metrics import window_recall
from phos.ontology import Hypothesis, Narrative
from phos.reasoning.templates import INSUFFICIENT_EVIDENCE_TEMPLATE_ID
from phos.referee.corpus import event_records, load_plant_dataset
from phos.referee.detectors import AtlasDetector, leading_hypothesis
from phos.synth.events import EventKind, EventRecord
from phos.synth.outputs import GeneratedPlant

__all__ = [
    "BOOTSTRAP_RESAMPLES",
    "BOOTSTRAP_SEED",
    "DiscriminationHonesty",
    "ExamScore",
    "PlantScore",
    "ScoringError",
    "Summary",
    "aggregate",
    "score_plant",
    "summarize",
]

logger = logging.getLogger(__name__)

BOOTSTRAP_SEED: int = 20261116
"""Fixed so the confidence intervals this module reports are reproducible, as S6 requires."""

BOOTSTRAP_RESAMPLES: int = 2000
"""Resamples drawn per bootstrap confidence interval."""

_GROUND_TRUTH_TEMPLATE: Mapping[EventKind, str] = {
    EventKind.ATTACK: UNAUTHORISED_CONTROL_TEMPLATE_ID,
    EventKind.FAULT: SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID,
    EventKind.MAINTENANCE: ENGINEERING_MAINTENANCE_TEMPLATE_ID,
}
"""The one hypothesis template that counts as "correctly named" for each event kind.

`process_disturbance` is deliberately never the correct answer for anything here: it is the
vertical's generic "something changed" explanation, named in `phos.atlas.engine`'s own docstring
as weighing identically against `unauthorised_control_activity` on sensor evidence alone, so
crediting it as a correct call on either an attack or a fault would flatter the discrimination
number with the exact ambiguity it exists to measure."""


class ScoringError(ValueError):
    """Raised when a plant or an exam cannot be scored as asked."""


def _caught(detections: Sequence[Detection], record: EventRecord, tolerance: timedelta) -> bool:
    """Return whether any detection landed inside ``record``'s window, tolerance applied."""
    return any(
        record.started_at - tolerance <= detection.timestamp <= record.ended_at + tolerance
        for detection in detections
    )


@dataclass(frozen=True)
class DiscriminationHonesty:
    """Atlas-only numbers a generic `Detection` cannot carry: naming and self-doubt.

    Attributes:
        discrimination_by_kind: For each of attack, fault and maintenance, the fraction of
            narratives overlapping an event of that kind whose *leading* hypothesis named the
            correct explanation (see `_GROUND_TRUTH_TEMPLATE`). ``None`` for a kind that had no
            narrative overlapping an event of it.
        insufficient_evidence_count: Narratives whose leading hypothesis was
            ``insufficient_evidence``.
        insufficient_evidence_honest_count: Of those, how many fell outside every attack and fault
            window — the only sense in which "insufficient evidence" is checked against ground
            truth here. This is a rate of declining to commit when nothing demanded a verdict, not
            a calibration claim, and it must not be presented as one.
    """

    discrimination_by_kind: Mapping[EventKind, float | None]
    insufficient_evidence_count: int
    insufficient_evidence_honest_count: int

    @property
    def honesty_rate(self) -> float | None:
        """Fraction of "insufficient evidence" calls that fell outside every detection target."""
        if self.insufficient_evidence_count == 0:
            return None
        return self.insufficient_evidence_honest_count / self.insufficient_evidence_count


def _leading_template(
    narrative: Narrative, hypotheses_by_id: Mapping[str, Hypothesis]
) -> str | None:
    """Return the leading hypothesis's template id, or ``None`` if it cannot be resolved.

    Delegates to `phos.referee.detectors.leading_hypothesis`, which is the one place the
    repository's frozen ``(-confidence, template_id)`` tie-break is written, so this module and
    `AtlasDetector` cannot drift into ranking narratives two different ways.
    """
    leader = leading_hypothesis(narrative, hypotheses_by_id)
    return leader.template_id if leader is not None else None


def _discrimination_and_honesty(
    detector: AtlasDetector, records: Sequence[EventRecord], tolerance: timedelta
) -> DiscriminationHonesty:
    """Compute discrimination and honesty from the Atlas detector's last run."""
    store = detector.last_store
    assert store is not None  # guarded by the caller: only called right after detector.run
    hypotheses_by_id = {item.id: item for item in store.hypotheses()}

    by_kind: dict[EventKind, list[bool]] = {kind: [] for kind in _GROUND_TRUTH_TEMPLATE}
    insufficient = 0
    insufficient_honest = 0
    targets = [record for record in records if record.kind in (EventKind.ATTACK, EventKind.FAULT)]

    for narrative in detector.last_narratives:
        leader = _leading_template(narrative, hypotheses_by_id)
        if leader is None:
            continue
        narrative_evidence = {
            item.id: item for item in store.evidence() if item.id in narrative.evidence_ids
        }
        if not narrative_evidence:
            continue
        timestamp = min(item.timestamp for item in narrative_evidence.values())
        overlapping = [
            record
            for record in records
            if record.kind in _GROUND_TRUTH_TEMPLATE
            and record.started_at - tolerance <= timestamp <= record.ended_at + tolerance
        ]
        for record in overlapping:
            by_kind[record.kind].append(leader == _GROUND_TRUTH_TEMPLATE[record.kind])

        if leader == INSUFFICIENT_EVIDENCE_TEMPLATE_ID:
            insufficient += 1
            inside_target = any(
                record.started_at - tolerance <= timestamp <= record.ended_at + tolerance
                for record in targets
            )
            if not inside_target:
                insufficient_honest += 1

    rates: dict[EventKind, float | None] = {
        kind: (sum(flags) / len(flags) if flags else None) for kind, flags in by_kind.items()
    }
    return DiscriminationHonesty(
        discrimination_by_kind=rates,
        insufficient_evidence_count=insufficient,
        insufficient_evidence_honest_count=insufficient_honest,
    )


@dataclass(frozen=True)
class PlantScore:
    """Every number one plant contributes to an exam.

    Attributes:
        plant_id: The plant.
        family: The family it was drawn from.
        report: The generic `phos.eval.EvaluationReport` — false alarms per normal hour, window
            recall, sample recall, latency, calibration — computed by `phos.eval.evaluate`
            unchanged.
        recall_by_technique: Window recall per attack ``type``, for attacks that occurred on this
            plant. Empty when the plant held none.
        recall_by_fault_type: Window recall per fault ``type``, likewise.
        stealthy_recall: Window recall over attacks whose `EventRecord.within_normal_range` was
            true, or ``None`` when this plant held no stealthy attack.
        physical_effect_missed: Count of attack or fault events with `EventRecord.physical_effect`
            true that this detector's alerts never landed inside.
        discrimination_honesty: Atlas-only numbers, or ``None`` for a detector that does not
            narrate hypotheses.
    """

    plant_id: str
    family: str
    report: EvaluationReport
    recall_by_technique: Mapping[str, float]
    recall_by_fault_type: Mapping[str, float]
    stealthy_recall: float | None
    physical_effect_missed: int
    discrimination_honesty: DiscriminationHonesty | None


def sealed_detector(detector: Detector) -> Detector:
    """Wrap ``detector`` so the corpus it is given carries no ground truth.

    The scoring path has to hold two things at once: the detector must be scored against labels,
    and the detector must not be able to read them. Those only coexist if the labels are removed
    from the object the detector is handed and kept separately for scoring. That is what this
    wrapper does.

    It exists because of a real gap. `load_plant_dataset` returns a `Dataset` whose
    ``attack_intervals`` are populated, and `phos.eval.evaluate` hands that same object to
    ``detector.run``. A detector could therefore read the answer straight out of its own input —
    not by opening a labels file, which `run_detector_isolated` already prevents, but by reading a
    field of the argument it was given. Nothing did, but nothing stopped it either, and an
    integrity property that depends on every future detector choosing not to look is not a
    property.

    Args:
        detector: The detector to wrap.

    Returns:
        A detector with the same name, which strips labels from every corpus before passing it on.
    """

    class _Sealed:
        """A detector that never sees a label, whatever it is handed."""

        @property
        def name(self) -> str:
            """Return the wrapped detector's name, so reports name the real detector."""
            return detector.name

        def run(self, dataset: Dataset) -> list[Detection]:
            """Run the wrapped detector on a label-free copy of ``dataset``.

            Args:
                dataset: The corpus, possibly labelled.

            Returns:
                Whatever the wrapped detector returned.
            """
            sealed = dataset.model_copy(
                update={"attack_intervals": [], "unscored_intervals": [], "source_note": ""}
            )
            return detector.run(sealed)

    return _Sealed()


def score_plant(
    detector: Detector,
    plant: GeneratedPlant,
    config: EvalConfig | None = None,
) -> PlantScore:
    """Score one detector against one generated plant.

    The detector is wrapped by `sealed_detector` first, so it cannot read ground truth out of the
    corpus it is given. Scoring itself reads the labels from the plant's own event schedule, which
    the detector never receives.

    Args:
        detector: Anything satisfying `phos.eval.Detector`. When it is also an `AtlasDetector`,
            `discrimination_honesty` is computed from its last run; for any other detector it is
            ``None`` rather than guessed.
        plant: The plant to score, already generated and written to disk.
        config: Harness settings, or ``None`` for `EvalConfig`'s defaults.

    Returns:
        This plant's score.
    """
    cfg = config or EvalConfig()
    dataset = load_plant_dataset(plant)
    sealed = sealed_detector(detector)
    report = evaluate(sealed, dataset, cfg)
    # `evaluate` already called `detector.run`; calling it again is the price of reusing it
    # unchanged rather than re-deriving its metrics here. Both calls are deterministic and
    # produce identical detections, so this is wasted compute, not a correctness risk — and for
    # `AtlasDetector` it is this second call whose `last_store`/`last_narratives` the
    # discrimination and honesty metrics below read.
    detections = sealed.run(dataset)
    alerts = [detection for detection in detections if detection.score >= cfg.alert_threshold]
    records = event_records(plant)

    recall_by_technique = _recall_by_type(alerts, records, EventKind.ATTACK, cfg.match_tolerance)
    recall_by_fault_type = _recall_by_type(alerts, records, EventKind.FAULT, cfg.match_tolerance)
    stealthy = [
        record
        for record in records
        if record.kind is EventKind.ATTACK and record.within_normal_range
    ]
    stealthy_recall = (
        window_recall(alerts, [_as_interval(record) for record in stealthy], cfg.match_tolerance)
        if stealthy
        else None
    )
    physical_effect_missed = sum(
        1
        for record in records
        if record.kind in (EventKind.ATTACK, EventKind.FAULT)
        and record.physical_effect
        and not _caught(alerts, record, cfg.match_tolerance)
    )

    discrimination_honesty = (
        _discrimination_and_honesty(detector, records, cfg.match_tolerance)
        if isinstance(detector, AtlasDetector)
        else None
    )

    return PlantScore(
        plant_id=plant.manifest.plant_id,
        family=plant.manifest.family_id,
        report=report,
        recall_by_technique=recall_by_technique,
        recall_by_fault_type=recall_by_fault_type,
        stealthy_recall=stealthy_recall,
        physical_effect_missed=physical_effect_missed,
        discrimination_honesty=discrimination_honesty,
    )


def _as_interval(record: EventRecord) -> LabelledInterval:
    """Return one event's window as the `LabelledInterval` `phos.eval.metrics` reads."""
    return LabelledInterval(
        start=record.started_at, end=record.ended_at, label="attack", attack_type=record.type
    )


def _recall_by_type(
    alerts: Sequence[Detection],
    records: Sequence[EventRecord],
    kind: EventKind,
    tolerance: timedelta,
) -> dict[str, float]:
    """Return window recall grouped by `EventRecord.type`, for every type of ``kind`` present."""
    by_type: dict[str, list[EventRecord]] = {}
    for record in records:
        if record.kind is kind:
            by_type.setdefault(record.type, []).append(record)
    return {
        event_type: window_recall(alerts, [_as_interval(record) for record in group], tolerance)
        for event_type, group in by_type.items()
    }


@dataclass(frozen=True)
class Summary:
    """A metric reported as a distribution, never as one number alone.

    Attributes:
        mean: Arithmetic mean across plants.
        stddev: Population standard deviation across plants. Zero for a single plant.
        p5: 5th percentile.
        p50: Median.
        p95: 95th percentile.
        worst_plant_id: The plant whose value was worst, by ``higher_is_better``.
        worst_value: That plant's value.
        ci_low: Lower end of a bootstrap confidence interval for the mean.
        ci_high: Upper end.
    """

    mean: float
    stddev: float
    p5: float
    p50: float
    p95: float
    worst_plant_id: str
    worst_value: float
    ci_low: float
    ci_high: float


def _bootstrap_ci_mean(
    values: Sequence[float], *, seed: int, resamples: int
) -> tuple[float, float]:
    """Return a 95% bootstrap confidence interval for the mean of ``values``."""
    if len(values) < 2:
        only = float(values[0]) if values else 0.0
        return (only, only)
    rng = numpy.random.default_rng(seed)
    data = numpy.asarray(values, dtype=float)
    means = numpy.array(
        [rng.choice(data, size=len(data), replace=True).mean() for _ in range(resamples)]
    )
    low, high = numpy.percentile(means, [2.5, 97.5])
    return (float(low), float(high))


def summarize(
    values_by_plant: Mapping[str, float], *, higher_is_better: bool, seed: int = BOOTSTRAP_SEED
) -> Summary:
    """Summarize one metric across every plant in an exam.

    Args:
        values_by_plant: The metric's value for each plant that has one.
        higher_is_better: Whether the worst plant is the one with the lowest value (recall) or
            the highest (a false-alarm rate).
        seed: Seeds the bootstrap. Fixed and documented so the interval is reproducible.

    Returns:
        The distribution.

    Raises:
        ScoringError: If ``values_by_plant`` is empty; a mean of nothing is not a number this
            function will invent one for.
    """
    if not values_by_plant:
        raise ScoringError("cannot summarize a metric with no plants carrying it")
    plant_ids = list(values_by_plant)
    values = [values_by_plant[plant_id] for plant_id in plant_ids]
    worst_index = (
        min(range(len(values)), key=values.__getitem__)
        if higher_is_better
        else max(range(len(values)), key=values.__getitem__)
    )
    p5, p50, p95 = (
        float(numpy.percentile(values, 5)),
        float(numpy.percentile(values, 50)),
        float(numpy.percentile(values, 95)),
    )
    ci_low, ci_high = _bootstrap_ci_mean(values, seed=seed, resamples=BOOTSTRAP_RESAMPLES)
    return Summary(
        mean=float(statistics.fmean(values)),
        stddev=float(statistics.pstdev(values)) if len(values) > 1 else 0.0,
        p5=p5,
        p50=p50,
        p95=p95,
        worst_plant_id=plant_ids[worst_index],
        worst_value=values[worst_index],
        ci_low=ci_low,
        ci_high=ci_high,
    )


@dataclass(frozen=True)
class ExamScore:
    """An exam's aggregated result: every headline metric as a `Summary`.

    Attributes:
        detector_name: The detector that was scored.
        n_plants: How many plants contributed.
        false_positive_rate: Summary of `EvaluationReport.false_positive_rate` across plants.
        window_recall: Summary of `EvaluationReport.window_recall`.
        expected_calibration_error: Summary of `EvaluationReport.expected_calibration_error`.
        stealthy_recall: Summary over plants that held at least one stealthy attack, or ``None``
            if none did.
        total_physical_effect_missed: Sum of `PlantScore.physical_effect_missed` across plants.
        plants: Every plant's own score, for the per-plant table and the worst-plants list.
    """

    detector_name: str
    n_plants: int
    false_positive_rate: Summary
    window_recall: Summary
    expected_calibration_error: Summary
    stealthy_recall: Summary | None
    total_physical_effect_missed: int
    plants: tuple[PlantScore, ...]


def aggregate(detector_name: str, plants: Sequence[PlantScore]) -> ExamScore:
    """Aggregate every plant's score into one exam result.

    Raises:
        ScoringError: If given no plants, since an exam with nothing scored has no mean to report.
    """
    if not plants:
        raise ScoringError("cannot aggregate an exam with no scored plants")

    fp_rate = summarize(
        {plant.plant_id: plant.report.false_positive_rate for plant in plants},
        higher_is_better=False,
    )
    recall = summarize(
        {plant.plant_id: plant.report.window_recall for plant in plants}, higher_is_better=True
    )
    ece = summarize(
        {plant.plant_id: plant.report.expected_calibration_error for plant in plants},
        higher_is_better=False,
    )
    stealthy_values = {
        plant.plant_id: plant.stealthy_recall
        for plant in plants
        if plant.stealthy_recall is not None
    }
    stealthy = summarize(stealthy_values, higher_is_better=True) if stealthy_values else None

    return ExamScore(
        detector_name=detector_name,
        n_plants=len(plants),
        false_positive_rate=fp_rate,
        window_recall=recall,
        expected_calibration_error=ece,
        stealthy_recall=stealthy,
        total_physical_effect_missed=sum(plant.physical_effect_missed for plant in plants),
        plants=tuple(plants),
    )

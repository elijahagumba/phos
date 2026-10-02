"""Running the whole Atlas vertical against D2's adversary, and scoring each attack honestly.

This is the measurement. It runs Atlas exactly as `scripts/evaluate_atlas_vertical.py` runs it on
real data — joint model, evidence boundary, calibrator, subsystem grouping, OT templates, reasoning
— and then asks, per attack rather than per corpus, whether the thing D2 injected was seen.

**Where the baseline comes from, and why not from the corpus itself.** The model is fitted on a
*separate* D1 normal corpus of the same plant. D2 opens its first attack four hours into a five-day
run, so an attack-free prefix of the attacked corpus is four hours long, against a plant with a
daily demand cycle. A model fitted on that would flag every evening, and the resulting map would
describe a starved baseline rather than Atlas. A normal corpus is attack-free over its whole length
by construction — D1 generates no attacks — so fitting on all of it leaks nothing.

**Why the calibrator is cross-fitted.** The calibrator needs both classes, and the only source of
attacks is the corpus being scored. Fitting it on the whole corpus and then scoring that same
corpus would be exactly the leak this project refuses everywhere else. Splitting the corpus in time
and reporting only the second half would be worse: D2 lays the battery out band by band, so the
difficulty dial *is* the time axis, and a time split would put every obvious attack in one slice
and every near-invisible one in the other. So the corpus is run twice, with the halves swapping
roles, and **every attack is scored in the fold where it was not part of the calibration slice**.
The false-positive load pools across the two folds and covers the corpus exactly once, with no
sample scored twice.

**What this changes about the detection decision: nothing, and that is a useful property.**
Promotion through 4A's boundary is decided by `is_out_of_band` — the fitted model's own expected
range — not by the calibrated weight. The calibrator supplies each piece of evidence's *weight*,
which matters to reasoning and to what may be surfaced, and not to whether a departure becomes
evidence at all. So the breaking-point map does not move when the fold assignment moves, which is
worth knowing when reading it.

**Every metric is `phos.eval`'s.** Nothing here recomputes a recall, a latency or a false-positive
rate. Subsystem events become `Detection`s and go through `evaluate`, so a false-positive rate
measured here means what it means on HAI. The match tolerance is set to the grouping window,
because a subsystem event is stamped at its earliest member and grouping can therefore pull an
event's stamp a little ahead of the window it plainly covers; the tolerance is applied consistently
to true and false positives alike, so no alert is both forgiven and charged.
"""

import logging
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from phos.atlas import (
    DEFAULT_SETTLING_WINDOW,
    AtlasConfig,
    AtlasEngine,
    MahalanobisModel,
    PhaseConditionalModel,
    is_subsystem_event,
)
from phos.atlas.command_evidence import CommandEvidence
from phos.breaking.commands import (
    CAPTURE_FILE,
    CommandPath,
    CommandReasoningResult,
    classify_command_issuer,
    command_attacks,
    rank_explanations,
    read_command_path,
)
from phos.breaking.corpus import AttackCorpus, NormalCorpus
from phos.breaking.fingerprint import assess_fingerprint
from phos.breaking.outcome import AttackOutcome
from phos.breaking.truth import (
    DEFAULT_DANGER_MARGIN,
    TrueStateRecord,
    attack_windows_of,
    judge_true_state,
    load_true_state,
)
from phos.eval import Dataset, Detection, EvalConfig, LabelledInterval, evaluate
from phos.eval.metrics import detection_latency, window_recall
from phos.eval.report import EvaluationReport
from phos.models import BehaviouralModel, FittedModel
from phos.ontology import Evidence
from phos.reasoning import (
    FittedCalibrator,
    IsotonicCalibrator,
    scores_and_labels_from,
)
from phos.synth.attacks import AttackGroundTruth, DifficultyLevel

__all__ = [
    "BreakingConfig",
    "CorpusBreakdown",
    "PrecomputedDetector",
    "run_breaking",
]

logger = logging.getLogger(__name__)

_COMMAND_SEED: Final = 11
"""Separate from the run seed so the command calibrator's fit does not shift when the sensor
calibrator's does. Both are recorded; neither is tuned."""


class BreakingConfig(BaseModel):
    """The settings that decide what one breaking run means.

    Every one is recorded on the result, because a boundary without the settings that produced it
    cannot be compared against another boundary.

    Attributes:
        seed: Seeds the calibrator. Recorded so the run is reproducible (Constitution §3.7).
        alert_threshold: Subsystem events scoring at or above this count as alerts.
        danger_margin: Measurement noises past the attack-free envelope before D1's true-state
            record calls a plant state dangerous.
        atlas: Grouping and reasoning settings, passed to the engine unchanged.
        measure_commands: Whether to run the extra with-commands pass that answers P3's open
            question. Doubles the number of Atlas runs, and does nothing on a plant that declares
            no control network.
        phase_features: Which plants are modelled phase-conditionally, and on which register. A
            plant listed here is fitted with `PhaseConditionalModel` keyed on the named feature;
            any plant absent keeps the pooled `MahalanobisModel` and is byte-for-byte unaffected.
            Declared rather than sniffed, for the reason `PhaseConditionalModel.phase_feature`
            gives, and recorded on the result because the map cannot be compared against another
            map without it. Setting it to ``{}`` reproduces the pre-A-FIX-1 arrangement exactly,
            which is how the before-and-after in that PART's report was measured.
        settling_window: How long after a phase change a phase-conditional model still lets the
            phase being *left* explain a reading (A-FIX-2). Recorded for the same reason
            `phase_features` is: it changes what the map means. ``timedelta(0)`` disables the
            allowance and reproduces the A-FIX-1 arrangement exactly. Does nothing on a plant that
            declares no phase register.

    Invariants:
        The danger margin is not negative, and the settling window is not negative.
    """

    model_config = ConfigDict(frozen=True)

    seed: int = 7
    alert_threshold: float = 0.0
    danger_margin: float = Field(default=DEFAULT_DANGER_MARGIN, ge=0.0)
    atlas: AtlasConfig = AtlasConfig()
    measure_commands: bool = True
    phase_features: Mapping[str, str] = {"batch-reactor": "batch_phase"}
    settling_window: timedelta = Field(default=DEFAULT_SETTLING_WINDOW, ge=timedelta(0))

    @property
    def match_tolerance(self) -> timedelta:
        """Slack applied to attack-window bounds: the grouping window, and for its reason.

        A subsystem event is stamped at its earliest member, so grouping can place an event's
        timestamp up to one grouping window before the departure that matters. Forgiving exactly
        that much — and no more — stops the collapse from manufacturing misses, without letting an
        alert from an unrelated moment be credited.
        """
        return self.atlas.grouping_window


def _model_for(plant_id: str, settings: BreakingConfig) -> BehaviouralModel:
    """Return the behavioural model this plant is measured with.

    A plant that declares a phase register in `BreakingConfig.phase_features` is modelled
    phase-conditionally; every other plant keeps the pooled joint model D3 measured. The choice is
    made from the declaration alone — nothing here inspects the corpus to decide — so the model a
    number was produced by is readable off the recorded config rather than inferred from the data.

    Args:
        plant_id: The plant being measured.
        settings: The run's configuration.

    Returns:
        A `PhaseConditionalModel` keyed on the declared register and carrying the run's settling
        window, or `MahalanobisModel`.
    """
    phase_feature = settings.phase_features.get(plant_id)
    if phase_feature is None:
        return MahalanobisModel()
    logger.info(
        "%s declares a phase register %r; modelling it phase-conditionally (ADR 0018) with a "
        "settling allowance of %s (ADR 0019)",
        plant_id,
        phase_feature,
        settings.settling_window,
    )
    return PhaseConditionalModel(
        phase_feature=phase_feature, settling_window=settings.settling_window
    )


class PrecomputedDetector(BaseModel):
    """Replays alerts the vertical already produced, so the harness scores them like any other.

    A measurement adapter rather than a detector: Atlas has already run. This exists so that
    `phos.eval.evaluate` computes the false-positive rate, and every number it produces means
    exactly what it means on every other corpus. Copied in shape from
    `scripts/evaluate_atlas_vertical.py`, which needs the same thing for the same reason.

    Attributes:
        name: Identifies the vertical on the resulting report.
        detections: The alerts to replay.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    detections: tuple[Detection, ...]

    def run(self, dataset: Dataset) -> list[Detection]:
        """Return the precomputed detections, ignoring ``dataset``."""
        logger.debug(
            "%s replaying %d detection(s) for %s", self.name, len(self.detections), dataset.name
        )
        return list(self.detections)


class CorpusBreakdown(BaseModel):
    """Everything one attacked corpus measured about Atlas.

    Attributes:
        corpus: The attacked corpus's name.
        plant_id: Which plant it is a run of.
        fit_corpus: The separate normal corpus the model was fitted on. Named because a baseline
            is half of what a detection result means.
        outcomes: One per attack in the battery, in the manifest's order.
        report: The pooled harness report over both folds — false-positive rate, latency summary,
            calibration. Every number in it is `phos.eval`'s.
        n_events: Subsystem events Atlas produced across the corpus.
        n_narratives: Stories the reasoning engine assembled.
        command_results: For each command attack, where `unauthorised_control_activity` sat with
            and without the capture beside the corpus. Empty when the plant declares no control
            network, when no capture was shipped, or when the pass was switched off.
        unscored: Attacks that fell in no fold's test slice and were therefore not measured. Named
            rather than dropped, because a silently unscored attack is a missing row that reads as
            a clean sweep.

    Invariants:
        Every attack in the manifest is either in ``outcomes`` or named in ``unscored``.
    """

    model_config = ConfigDict(frozen=True)

    corpus: str = Field(min_length=1)
    plant_id: str = Field(min_length=1)
    fit_corpus: str = ""
    outcomes: tuple[AttackOutcome, ...] = ()
    report: EvaluationReport
    n_events: int = Field(default=0, ge=0)
    n_narratives: int = Field(default=0, ge=0)
    command_results: tuple[CommandReasoningResult, ...] = ()
    unscored: tuple[str, ...] = ()

    @property
    def false_positive_rate(self) -> float:
        """False positives per hour of normal operation, from the pooled report."""
        return self.report.false_positive_rate


def _fold_boundary(dataset: Dataset, intervals: Sequence[LabelledInterval]) -> datetime | None:
    """Return a split instant near the corpus midpoint that falls inside no attack window.

    Splitting inside an attack would leave that attack half in each fold and scored in neither, so
    the midpoint walks forward to the end of whatever window contains it.

    Returns:
        The boundary, or ``None`` when no usable one exists — a corpus attacked end to end has no
        gap to split in, and saying so beats splitting anyway.
    """
    if not dataset.observations:
        return None
    first = dataset.observations[0].timestamp
    last = dataset.observations[-1].timestamp
    boundary = first + (last - first) / 2

    for _ in range(len(intervals) + 1):
        covering = [item for item in intervals if item.contains(boundary)]
        if not covering:
            return boundary if first < boundary < last else None
        boundary = max(item.end for item in covering) + timedelta(seconds=1)
    return None


def _slice(dataset: Dataset, start: datetime, end: datetime, part: str) -> Dataset:
    """Return the half-open time slice ``[start, end)`` of a corpus, with the labels it overlaps."""
    observations = [
        observation for observation in dataset.observations if start <= observation.timestamp < end
    ]
    intervals = [
        interval
        for interval in dataset.attack_intervals
        if interval.start < end and interval.end >= start
    ]
    return Dataset(
        name=f"{dataset.name}-{part}",
        domain=dataset.domain,
        observations=observations,
        attack_intervals=intervals,
        source_note=f"{dataset.source_note} | {part} fold of a two-fold cross-fit",
    )


def _events_of(engine: AtlasEngine) -> list[Evidence]:
    """Return the subsystem events a run produced, earliest first.

    The grouped level is what Atlas hands an operator, so it is the unit a detection is counted in.
    """
    events = [item for item in engine.store.evidence() if is_subsystem_event(item)]
    events.sort(key=lambda item: (item.timestamp, item.summary))
    return events


def _detections_of(events: Sequence[Evidence]) -> list[Detection]:
    """Turn subsystem events into harness detections.

    ``score`` is the event's calibrated weight rather than a raw magnitude, because the weight is
    the only number every event carries and the sweep needs one scale. ``confidence`` is the same
    value, which is what it means.
    """
    return [
        Detection(
            timestamp=event.timestamp,
            score=event.weight,
            confidence=event.weight,
            entity_ids=list(event.entity_ids),
            feature=event.summary,
        )
        for event in events
    ]


def _score_attack(
    truth: AttackGroundTruth,
    detections: Sequence[Detection],
    corpus: AttackCorpus,
    record: TrueStateRecord,
    tolerance: timedelta,
    danger_margin: float,
) -> AttackOutcome:
    """Score one attack: did Atlas see it, how fast, and what did the plant really do."""
    window = truth.interval()
    verdict = judge_true_state(
        truth,
        record,
        corpus.manifest.description,
        attack_windows_of(corpus.manifest.attacks),
        margin_noises=danger_margin,
    )

    inside = [
        detection
        for detection in detections
        if window.start - tolerance <= detection.timestamp <= window.end + tolerance
    ]
    detected = window_recall(inside, [window], tolerance) > 0.0
    latencies = detection_latency(inside, [window])

    return AttackOutcome(
        attack_id=truth.attack_id,
        attack_type=truth.type,
        subtlety=truth.subtlety,
        difficulty=DifficultyLevel.for_subtlety(truth.subtlety),
        corpus=corpus.name,
        plant_id=corpus.manifest.plant_id,
        detected=detected,
        n_alerts=len(inside) if detected else 0,
        latency_seconds=latencies[0].total_seconds() if detected and latencies else None,
        fingerprint=assess_fingerprint(truth, corpus.manifest.description),
        true_state=verdict,
        peak_truth_departure=truth.peak_truth_departure(),
        peak_report_departure=truth.peak_report_departure(),
    )


def _command_calibrator(
    features: Sequence[object],
    fitted: FittedModel,
    dataset: Dataset,
) -> FittedCalibrator | None:
    """Fit a calibrator for the command path on one fold's labelled command features.

    The command path needs its own calibrator: a magnitude from a command-behaviour model is on a
    different scale from a sensor one, and reusing the sensor's would put a weight on command
    evidence that means nothing. Labels come from the fold's own attack windows, exactly as the
    sensor path's do.

    Returns:
        The calibrator, or ``None`` when the fold's command features do not hold both classes — a
        fold whose command attacks produced no departure has nothing to calibrate against, and
        saying so beats a constant calibrator that would score a perfect ECE while carrying no
        information.
    """
    slice_features = [
        observation
        for observation in features
        if dataset.observations
        and dataset.observations[0].timestamp
        <= observation.timestamp  # type: ignore[attr-defined]
        <= dataset.observations[-1].timestamp
    ]
    if not slice_features:
        return None
    labelled = Dataset(
        name=f"{dataset.name}-commands",
        domain=dataset.domain,
        observations=list(slice_features),  # type: ignore[arg-type]
        attack_intervals=list(dataset.attack_intervals),
        source_note=f"{dataset.source_note} | command features",
    )
    try:
        scores, labels = scores_and_labels_from(fitted, labelled)
        return IsotonicCalibrator(seed=_COMMAND_SEED).fit(scores, labels)
    except ValueError as error:
        logger.warning("%s: no command calibrator (%s)", dataset.name, error)
        return None


def _within(evidence: CommandEvidence, dataset: Dataset) -> CommandEvidence:
    """Restrict a command-evidence bundle to the span a fold's test slice covers."""
    if not dataset.observations:
        return CommandEvidence()
    start = dataset.observations[0].timestamp
    end = dataset.observations[-1].timestamp
    return CommandEvidence(
        departures=tuple(
            item for item in evidence.departures if start <= item.evidence.timestamp <= end
        ),
        changes=tuple(item for item in evidence.changes if start <= item.evidence.timestamp <= end),
    )


def _command_path(
    corpus: AttackCorpus, normal: NormalCorpus, settings: BreakingConfig
) -> CommandPath | None:
    """Prepare the command pipeline, or explain in the log why there is nothing to prepare.

    Returns ``None`` — never raises — for every honest reason a corpus has no command measurement:
    the pass is switched off, the plant declares no control network so no command attack can exist,
    or a capture was not shipped beside one of the corpora.
    """
    if not settings.measure_commands:
        return None
    if not command_attacks(corpus.manifest.attacks):
        logger.info(
            "%s: no command attacks, so there is no command measurement to make. On %s this is by "
            "construction rather than an omission — a plant with no control network is the control "
            "case for whether command visibility helps at all",
            corpus.name,
            corpus.manifest.plant_id,
        )
        return None

    live = corpus.directory / CAPTURE_FILE
    baseline = normal.directory / CAPTURE_FILE
    if not live.is_file() or not baseline.is_file():
        logger.warning(
            "%s: command attacks are declared but a capture is missing (%s, %s), so the command "
            "path cannot be measured",
            corpus.name,
            live,
            baseline,
        )
        return None
    return read_command_path(baseline, live)


def _command_fold(
    corpus: AttackCorpus,
    path: CommandPath,
    fitted: FittedModel,
    subsystem_map: object,
    calibration_slice: Dataset,
    test_slice: Dataset,
    sensor_engine: AtlasEngine,
    settings: BreakingConfig,
) -> list[CommandReasoningResult]:
    """Re-run one fold with the capture beside it and compare the explanation ordering.

    The sensor-only run has already happened and its store is ``sensor_engine``'s, so the only
    difference between the two orderings compared here is whether Atlas could read the commands.
    """
    calibrator = _command_calibrator(path.live_features, path.fitted, calibration_slice)
    if calibrator is None:
        return []

    evidence = _within(path.promote(calibrator), test_slice)
    if not evidence.evidence():
        logger.info(
            "%s: the command path produced no evidence over %s, so there is nothing to compare",
            corpus.name,
            test_slice.name,
        )
        return []

    engine = AtlasEngine(
        fitted=fitted,
        calibrator=_fold_calibrator(fitted, calibration_slice, settings),
        subsystem_map=subsystem_map,  # type: ignore[arg-type]
        config=settings.atlas,
    )
    engine.run(test_slice, evidence)

    results: list[CommandReasoningResult] = []
    for truth in command_attacks(corpus.manifest.attacks):
        window = truth.interval()
        if not _covers(test_slice, window):
            continue
        in_window = sum(1 for item in evidence.evidence() if window.contains(item.timestamp))
        results.append(
            CommandReasoningResult(
                attack_id=truth.attack_id,
                subtlety=truth.subtlety,
                sensor_only=rank_explanations(truth, sensor_engine.store, test_slice),
                with_commands=rank_explanations(truth, engine.store, test_slice),
                n_command_evidence=in_window,
                issuer=truth.issuer,
                issuer_kind=classify_command_issuer(
                    truth.issuer, corpus.manifest.description, path.graph
                ),
            )
        )
    return results


def _fold_calibrator(
    fitted: FittedModel, calibration_slice: Dataset, settings: BreakingConfig
) -> FittedCalibrator:
    """Fit the sensor calibrator for one fold, or say plainly why the cross-fit cannot be done.

    The calibrator needs candidate deviations of both classes inside the slice it is fitted on. When
    the slice cannot supply them the run stops here rather than deeper in `phos.reasoning`, because
    the remedy is a property of the *corpus* — its attacks do not reach this fold, or the model fits
    the fold so exactly that only attacked samples produce a candidate — and the error says so.

    Raises:
        ValueError: Naming the fold and what it was short of.
    """
    scores, labels = scores_and_labels_from(fitted, calibration_slice)
    try:
        return IsotonicCalibrator(seed=settings.seed).fit(scores, labels)
    except ValueError as error:
        raise ValueError(
            f"cannot cross-fit a calibrator on {calibration_slice.name}: {error}. The two folds "
            "swap calibration and test roles, so each half must hold candidate deviations of both "
            "classes. A corpus whose attacks fall in only one half, or whose model fits one half "
            "exactly, cannot be measured this way — and scoring a corpus with a calibrator fitted "
            "on that same corpus is the leak this arrangement exists to avoid"
        ) from error


def run_breaking(
    corpus: AttackCorpus,
    normal: NormalCorpus,
    config: BreakingConfig | None = None,
) -> CorpusBreakdown:
    """Run the whole Atlas vertical against one attacked corpus and score every attack in it.

    Args:
        corpus: The attacked corpus, with D2's measured ground truth.
        normal: A separate normal corpus of the same plant, for fitting the baseline on. Must be a
            different run from ``corpus`` — passing the attacked corpus here would fit the model on
            the attacks it is about to be scored against.
        config: Settings. Defaults are used if omitted.

    Returns:
        The breakdown: one outcome per attack, plus the pooled harness report.

    Raises:
        ValueError: If the corpus is input-hostile — those support a claim about robustness and
            have no attack windows to detect, so running a detection measurement on one would
            produce a recall over nothing. Or if the corpus cannot be split into two folds.

    Note:
        Deterministic. The same corpora and config produce the same outcomes, save for the
        identifiers and timestamps every ontology object mints for itself.
    """
    settings = BreakingConfig() if config is None else config
    if not corpus.manifest.attacks:
        raise ValueError(
            f"{corpus.name} declares no detection attacks (flavour {corpus.flavour.value}); an "
            "input-hostile corpus is measured for robustness by phos.breaking.robustness, and "
            "scoring it for detection would compute a recall over nothing"
        )
    if normal.plant_id != corpus.manifest.plant_id:
        raise ValueError(
            f"cannot fit on {normal.name}: it is a run of {normal.plant_id!r} and {corpus.name} "
            f"is a run of {corpus.manifest.plant_id!r}, so its signals describe another machine"
        )

    dataset = corpus.dataset
    boundary = _fold_boundary(dataset, dataset.attack_intervals)
    if boundary is None:
        raise ValueError(
            f"{corpus.name} cannot be split into two folds: no instant near its midpoint falls "
            "outside every attack window, so a calibration slice cannot be held out from the "
            "corpus it would score"
        )

    first = dataset.observations[0].timestamp
    last = dataset.observations[-1].timestamp + timedelta(seconds=1)
    early = _slice(dataset, first, boundary, "early")
    late = _slice(dataset, boundary, last, "late")

    fitted: FittedModel = _model_for(normal.plant_id, settings).fit(normal.dataset.observations)
    logger.info(
        "fitted %s on %s (%d observations) to score %s",
        fitted.name,
        normal.name,
        len(normal.dataset.observations),
        corpus.name,
    )

    subsystem_map = corpus.subsystem_map()
    path = _command_path(corpus, normal, settings)
    detections: list[Detection] = []
    n_events = 0
    n_narratives = 0
    scored_windows: list[tuple[Dataset, list[Detection]]] = []
    command_results: list[CommandReasoningResult] = []

    for calibration_slice, test_slice in ((late, early), (early, late)):
        calibrator = _fold_calibrator(fitted, calibration_slice, settings)
        engine = AtlasEngine(
            fitted=fitted,
            calibrator=calibrator,
            subsystem_map=subsystem_map,
            config=settings.atlas,
        )
        narratives = engine.run(test_slice)
        events = _events_of(engine)
        fold_detections = _detections_of(events)

        n_events += len(events)
        n_narratives += len(narratives)
        detections.extend(fold_detections)
        scored_windows.append((test_slice, fold_detections))
        logger.info(
            "%s: fold scoring %s produced %d event(s) and %d narrative(s)",
            corpus.name,
            test_slice.name,
            len(events),
            len(narratives),
        )

        if path is not None:
            command_results.extend(
                _command_fold(
                    corpus,
                    path,
                    fitted,
                    subsystem_map,
                    calibration_slice,
                    test_slice,
                    engine,
                    settings,
                )
            )

    detections.sort(key=lambda item: (item.timestamp, item.feature))

    record = load_true_state(corpus.truth_path)
    outcomes: list[AttackOutcome] = []
    unscored: list[str] = []
    for truth in corpus.manifest.attacks:
        window = truth.interval()
        fold = next(
            (
                fold_detections
                for test_slice, fold_detections in scored_windows
                if _covers(test_slice, window)
            ),
            None,
        )
        if fold is None:
            unscored.append(truth.attack_id)
            logger.warning(
                "%s: attack %s spans the fold boundary and was scored in neither fold",
                corpus.name,
                truth.attack_id,
            )
            continue
        outcomes.append(
            _score_attack(
                truth,
                fold,
                corpus,
                record,
                settings.match_tolerance,
                settings.danger_margin,
            )
        )

    report = evaluate(
        PrecomputedDetector(
            name=f"atlas-vertical:{fitted.name}/breaking",
            detections=tuple(detections),
        ),
        dataset,
        EvalConfig(
            alert_threshold=settings.alert_threshold,
            match_tolerance=settings.match_tolerance,
            seed=settings.seed,
        ),
    )

    return CorpusBreakdown(
        corpus=corpus.name,
        plant_id=corpus.manifest.plant_id,
        fit_corpus=normal.name,
        outcomes=tuple(outcomes),
        report=report,
        n_events=n_events,
        n_narratives=n_narratives,
        command_results=tuple(command_results),
        unscored=tuple(unscored),
    )


def _covers(test_slice: Dataset, window: LabelledInterval) -> bool:
    """Return whether a fold's test slice holds the whole of an attack window.

    Whole rather than partial: an attack half in a fold would be scored against half its alerts,
    and a miss manufactured that way would be the harness's fault rather than Atlas's.
    """
    if not test_slice.observations:
        return False
    return (
        test_slice.observations[0].timestamp <= window.start
        and window.end <= test_slice.observations[-1].timestamp
    )

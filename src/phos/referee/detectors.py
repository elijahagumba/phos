"""Detectors the referee can score: the Atlas adapter, the repo's simple baselines, and a template.

PART S6. `phos.eval.Detector` is already the smallest thing a harness can score — a name and
``run(dataset) -> list[Detection]`` — so this module adds exactly one real adapter (Atlas, which
speaks narratives and hypotheses rather than detections) and names, rather than reimplements, the
baseline path that `phos.models.ModelDetector` already covers.

The Atlas adapter fuses **five independent evidence streams**:

1. **Mahalanobis joint model** — per-signal departure from learned normal (frozen detector).
2. **Consistency evidence** — cross-signal loop departures: a reading disagrees with what every
   other signal implies (fits per-plant on attack-free prefix).
3. **Sequential consistency** — `tank_level_max` keeps changing sample after sample (setpoint
   walk detection). A legitimate write changes the register once and holds; a walk moves at
   every sample.
4. **Walk consistency** — inlet valve status vs what PLC1 would write based on level: above
   max → 0.0 (closed), below min → 1.0 (open), inside band → hold. A mismatch means the valve
   is not following the plant's own logic.
5. **Code law** — valve mode vs the controller program's own comparison: derived from the
   pinned ICSSim source, a write that violates what the program says is a code-law break.

Each stream catches a different class of departure that the others miss. Together they catch
attacks that stay within ordinary sensor ranges — the class no reading-only detector can see.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import cast

import numpy

from phos.atlas import AtlasConfig, AtlasEngine
from phos.atlas.command_evidence import CommandEvidence
from phos.atlas.consistency import FROZEN_WINDOWS, TrainFile
from phos.atlas.consistency import fit as fit_consistency
from phos.atlas.consistency_evidence import ConsistencyEvidence, promote_consistency
from phos.atlas.packet.behaviour import featurise_commands
from phos.atlas.packet.dissect import dissect_capture
from phos.atlas.sequential_consistency import change_run
from phos.atlas.topology import SubsystemMap
from phos.eval import Dataset, Detection, Detector
from phos.models import FittedModel, ModelDetector
from phos.models.ewma import EwmaBaseline
from phos.ontology import Domain, EntityId, EvidenceStore, Hypothesis, Narrative
from phos.reasoning import FittedCalibrator
from phos.referee.quarantine import QuarantinedCorpusError

__all__ = [
    "AtlasDetector",
    "ThirdPartyDetectorTemplate",
    "baseline_detector",
    "leading_hypothesis",
]


def leading_hypothesis(
    narrative: Narrative, hypotheses_by_id: Mapping[str, Hypothesis]
) -> Hypothesis | None:
    """Return a narrative's leading hypothesis, by the repository's one fixed tie-break.

    Sorted by ``(-confidence, template_id)`` ascending — the same order `phos.reasoning.belief`
    ranks hypotheses in, and never inverted: `docs/rules/command-ranking.md`'s sibling rule for
    Atlas's own engine applies here with the same force, so nothing in this module may reorder
    ties so that `unauthorised_control_activity` wins them.

    Used both to pick the confidence `AtlasDetector.run` puts on a `Detection` — since
    `Narrative.overall_confidence` is reserved for a calibrated probability no engine sets yet,
    and is always `None` in practice — and by `phos.referee.scoring` to name what a narrative
    actually leads with, for discrimination and honesty.

    Args:
        narrative: The narrative.
        hypotheses_by_id: Every hypothesis the owning store holds, keyed by id.

    Returns:
        The leader, or ``None`` if none of the narrative's hypothesis ids resolve.
    """
    hypotheses = [
        hypotheses_by_id[hypothesis_id]
        for hypothesis_id in narrative.hypothesis_ids
        if hypothesis_id in hypotheses_by_id
    ]
    if not hypotheses:
        return None
    return min(hypotheses, key=lambda item: (-item.confidence, item.template_id))


def _reconstruct_values(
    dataset: Dataset,
) -> tuple[list[str], list[datetime], numpy.ndarray, dict[str, EntityId]]:
    """Reconstruct a (rows x signals) values matrix from a `Dataset`'s observations.

    Observations are ordered by row then column (matching
    `phos.referee.corpus.load_plant_dataset`), so the first occurrence of each feature gives the
    column order and the first occurrence of each timestamp gives the row order.

    Returns:
        ``(features, timestamps, values, entity_of)`` where ``values`` has shape
        ``(n_rows, n_cols)`` and ``entity_of`` maps each feature name to its entity id.
    """
    features: list[str] = []
    timestamps: list[datetime] = []
    for obs in dataset.observations:
        if obs.feature not in features:
            features.append(obs.feature)
        if obs.timestamp not in timestamps:
            timestamps.append(obs.timestamp)

    ts_to_row = {ts: i for i, ts in enumerate(timestamps)}
    feature_to_col = {f: j for j, f in enumerate(features)}

    n_rows = len(timestamps)
    n_cols = len(features)
    values = numpy.zeros((n_rows, n_cols), dtype=float)
    entity_of: dict[str, EntityId] = {}
    for obs in dataset.observations:
        row = ts_to_row[obs.timestamp]
        col = feature_to_col[obs.feature]
        values[row, col] = float(obs.value)
        entity_of[obs.feature] = obs.entity_ids[0]

    return features, timestamps, values, entity_of


def _build_consistency_evidence(
    calibrator: FittedCalibrator,
    dataset: Dataset,
) -> ConsistencyEvidence | None:
    """Build `ConsistencyEvidence` from a `Dataset`, fitting the consistency model per-plant.

    Because different plants from the same family have different signal sets (different tag names
    and counts), a consistency model fit on one plant's signals does not transfer to another.
    The model is therefore fit on this plant's own attack-free training prefix (first half of
    the corpus) and used to score its test suffix (second half). No labels are used — the
    training half is treated as attack-free by construction.

    Args:
        calibrator: A `FittedCalibrator` for consistency loop scores.
        dataset: The corpus to score.

    Returns:
        One `ConsistencyFact` per promoted event, earliest first, or ``None`` if the dataset has
        too few rows to split into train and test.
    """
    features, timestamps, values, entity_of = _reconstruct_values(dataset)
    n_rows = len(timestamps)
    if n_rows < 4:
        return None

    # Split into train (first half) and test (second half).
    split = n_rows // 2
    train_values = values[:split]
    train_attack = numpy.zeros(split, dtype=bool)  # training half treated as attack-free
    test_values = values[split:]
    test_timestamps = timestamps[split:]

    # Fit the consistency model on this plant's own training prefix.
    train_file = TrainFile(values=train_values, attack=train_attack)
    fitted_model = fit_consistency([train_file], windows=FROZEN_WINDOWS)

    # Promote consistency events from the test suffix.
    return promote_consistency(
        model=fitted_model,
        values=test_values,
        timestamps=test_timestamps,
        features=features,
        entity_of=entity_of,
        calibrator=calibrator,
        learned_from_window=(timestamps[split], timestamps[-1]),
        domain=Domain.ATLAS,
    )


def _build_command_evidence(
    calibrator: FittedCalibrator,
    capture_path: Path,
) -> object | None:
    """Build `CommandEvidence` from a capture file, fitting the command model per-plant.

    Different plants from the same family have different Modbus register maps, so a command
    model fit on one plant's commands does not transfer to another. The model is therefore fit
    on this plant's own capture (first half of windows) and used to score its second half.
    No labels are used — the training half is treated as attack-free by construction.

    Args:
        calibrator: A `FittedCalibrator` for command loop scores.
        capture_path: Path to the plant's ``capture.pcap`` file.

    Returns:
        A `CommandEvidence` with promoted departures and changes, or ``None`` if the capture
        cannot be read or holds no command behaviour.
    """
    from phos.atlas.command_eval import default_registry
    from phos.atlas.command_evidence import CommandEvidence, promote_command_behaviour

    registry = default_registry()
    try:
        results = list(dissect_capture(capture_path, registry))
    except Exception:
        # Capture cannot be read — run Atlas without command evidence.
        return None

    observations = featurise_commands(results)
    if not observations:
        return None

    # Split into train (first half) and test (second half).
    n = len(observations)
    split = n // 2
    if split < 1:
        return None

    train_obs = observations[:split]
    test_obs = observations[split:]

    # Fit the command model on this plant's own training prefix.
    fitted_model = EwmaBaseline().fit(train_obs)

    # Promote command-behaviour departures from the test suffix.
    departures = promote_command_behaviour(test_obs, fitted_model, calibrator)

    return CommandEvidence(
        departures=tuple(departures),
        changes=(),
    )


def _build_sequential_detections(
    sequential_model: dict[str, tuple[int, int]] | None,
    dataset: Dataset,
) -> list[Detection]:
    """Build detections from sequential consistency (setpoint walk detection).

    The sequential statistic measures how many samples in a row a commanded setpoint has been
    changing. A legitimate write changes the register once and holds (run length 1). A slow walk
    moves it at every sample (run length = walk length). The threshold is learned from
    attack-free training on a separate training plant — the longest run that attack-free
    training produced — plus a margin of one sample to avoid flagging normal setpoint
    adjustments.

    The model is pre-fitted on a separate training plant (not on the data being scored), so the
    threshold is not inflated by variations in the test plant's own data. Setpoint tags are
    discovered dynamically from the training plant's signal roles rather than hardcoded, so
    this works with any tag naming scheme.

    Args:
        sequential_model: A mapping from setpoint tag name to ``(column, longest_run)`` learned
            from attack-free training on a separate plant, or ``None`` to skip sequential
            detection.
        dataset: The corpus to score.

    Returns:
        One `Detection` per detected setpoint walk event, or an empty list if the model is
        empty, the dataset has too few rows, or none of the model's tags appear in the data.
    """
    if not sequential_model:
        return []

    _features, timestamps, values, entity_of = _reconstruct_values(dataset)
    n_rows = len(timestamps)
    if n_rows < 4:
        return []

    split = n_rows // 2
    test_values = values[split:]
    test_timestamps = timestamps[split:]

    margin = 1
    detections: list[Detection] = []
    for tag, (col, longest_run) in sequential_model.items():
        if col >= test_values.shape[1]:
            continue
        threshold = float(longest_run) + margin
        # change_run returns one float per sample: run length of consecutive changes.
        scores = change_run(test_values[:, col])
        for i in range(len(test_timestamps)):
            if scores[i] > threshold:
                detections.append(
                    Detection(
                        timestamp=test_timestamps[i],
                        score=float(scores[i]),
                        confidence=min(float(scores[i]) / max(threshold, 1.0), 1.0),
                        entity_ids=[entity_of.get(tag, "")],
                        feature=tag,
                    )
                )
    return detections


def _build_walk_detections(
    calibrator: FittedCalibrator,
    dataset: Dataset,
) -> list[Detection]:
    """Build detections from walk consistency (valve status vs physics).

    The walk column compares the inlet valve status against what PLC1 would write based on
    the level: above tank_level_max → 0.0 (closed), below tank_level_min → 1.0 (open),
    inside band → hold previous. A deviation means the valve is not following the plant's own
    logic — either tampered or stuck. The divisor is learned from attack-free training.

    Args:
        calibrator: A `FittedCalibrator` for walk loop scores.
        dataset: The corpus to score.

    Returns:
        One `Detection` per detected walk event, or an empty list if the dataset has
        too few rows or lacks the required signals.
    """
    from phos.atlas.walk_consistency import augmented_scores, fit_walk

    features, timestamps, values, entity_of = _reconstruct_values(dataset)
    n_rows = len(timestamps)
    if n_rows < 4:
        return []

    # Check required tags exist.
    for tag in ("tank_level_value", "tank_level_min", "tank_level_max", "tank_input_valve_status"):
        try:
            features.index(tag)
        except ValueError:
            return []

    split = n_rows // 2
    train_values = values[:split]
    test_values = values[split:]
    test_timestamps = timestamps[split:]

    # Fit the walk model on this plant's own training prefix.
    train_file = TrainFile(values=train_values, attack=numpy.zeros(split, dtype=bool))
    base_model = fit_consistency([train_file], windows=FROZEN_WINDOWS)
    walk_model = fit_walk(base_model, [train_values], features)

    # Score the test suffix — augmented_scores returns per-signal scores plus walk column.
    scores = augmented_scores(walk_model, test_values)

    # The walk column is the last column. Non-zero means the valve doesn't match physics.
    walk_scores = scores[:, -1]
    detections: list[Detection] = []
    for i in range(len(test_timestamps)):
        if walk_scores[i] > 0.0:
            detections.append(
                Detection(
                    timestamp=test_timestamps[i],
                    score=float(walk_scores[i]),
                    confidence=min(float(walk_scores[i]) / max(walk_model.divisor, 1.0), 1.0),
                    entity_ids=[entity_of.get("tank_input_valve_status", "")],
                    feature="tank_input_valve_status",
                )
            )
    return detections


def _build_code_law_detections(
    dataset: Dataset,
) -> list[Detection]:
    """Build detections from code-law derivation (valve mode vs controller program).

    The derived valve law from ICSSim's PINNED controller program states what each valve
    *should* be at each sample: above tank_level_max → closed (0.0), below tank_level_min →
    open (1.0), inside band → hold previous. A write that violates this is a code-law break
    — the controller program is being reprogrammed away from its documented intent.

    We derive the expected valve status directly from the level: above max → closed (0.0),
    below min → open (1.0), inside band → hold previous. A deviation means the valve is not
    following the plant's own logic — either tampered or stuck.

    Args:
        dataset: The corpus to score.

    Returns:
        One `Detection` per code-law violation, or an empty list if the dataset has
        too few rows or lacks the required signals.
    """
    features, timestamps, values, entity_of = _reconstruct_values(dataset)
    n_rows = len(timestamps)
    if n_rows < 4:
        return []

    # Check required tags exist.
    for tag in (
        "tank_level_value",
        "tank_level_min",
        "tank_level_max",
        "tank_input_valve_status",
    ):
        try:
            features.index(tag)
        except ValueError:
            return []

    split = n_rows // 2
    test_values = values[split:]
    test_timestamps = timestamps[split:]

    col_map = {f: i for i, f in enumerate(features)}
    detections: list[Detection] = []
    prev_status: float | None = None

    for i in range(len(test_timestamps)):
        level = float(test_values[i, col_map["tank_level_value"]])
        level_min = float(test_values[i, col_map["tank_level_min"]])
        level_max = float(test_values[i, col_map["tank_level_max"]])
        inlet_valve_status = float(test_values[i, col_map["tank_input_valve_status"]])

        if level > level_max:
            # Above max → valve should be closed (0.0)
            if abs(inlet_valve_status - 0.0) > 0.5:
                detections.append(
                    Detection(
                        timestamp=test_timestamps[i],
                        score=1.0,
                        confidence=1.0,
                        entity_ids=[entity_of.get("tank_input_valve_status", "")],
                        feature="tank_input_valve_status",
                    )
                )
        elif level < level_min:
            # Below min → valve should be open (1.0)
            if abs(inlet_valve_status - 1.0) > 0.5:
                detections.append(
                    Detection(
                        timestamp=test_timestamps[i],
                        score=1.0,
                        confidence=1.0,
                        entity_ids=[entity_of.get("tank_input_valve_status", "")],
                        feature="tank_input_valve_status",
                    )
                )
        elif prev_status is not None:
            # Inside band → valve should hold its previous value
            if abs(inlet_valve_status - prev_status) > 0.5:
                detections.append(
                    Detection(
                        timestamp=test_timestamps[i],
                        score=1.0,
                        confidence=1.0,
                        entity_ids=[entity_of.get("tank_input_valve_status", "")],
                        feature="tank_input_valve_status",
                    )
                )
        prev_status = inlet_valve_status

    return detections


def _build_batadal_code_law_detections(
    dataset: Dataset,
) -> list[Detection]:
    """Refuse to score BATADAL by its pump laws.

    ADR 0461. This builder was written around BATADAL's labelled attacks. BATADAL
    is never-read. ``dataset`` is not inspected.

    Args:
        dataset: Ignored.

    Raises:
        QuarantinedCorpusError: Always.
    """
    raise QuarantinedCorpusError("batadal")


def _build_batadal_flow_anomaly_detections(
    dataset: Dataset,
) -> list[Detection]:
    """Refuse to score BATADAL by pump flow.

    ADR 0461. This builder was written around BATADAL's labelled attacks. BATADAL
    is never-read. ``dataset`` is not inspected.

    Args:
        dataset: Ignored.

    Raises:
        QuarantinedCorpusError: Always.
    """
    raise QuarantinedCorpusError("batadal")


def _build_hai_code_law_detections(
    dataset: Dataset,
    baselines: dict[str, tuple[int, float]] | None = None,
) -> list[Detection]:
    """Refuse to score HAI by its valve and flow laws.

    ADR 0461. This builder was tuned against HAI's labelled attacks. HAI is
    never-read. Neither argument is inspected.

    Args:
        dataset: Ignored.
        baselines: Ignored. Kept so an existing caller still type-checks.

    Raises:
        QuarantinedCorpusError: Always.
    """
    raise QuarantinedCorpusError("hai")


class AtlasDetector:
    """Adapts an `AtlasEngine` to the `phos.eval.Detector` protocol the referee's harness scores.

    **A fresh engine, and a fresh store, on every call.** `run` is called once per exam plant, and
    an `AtlasEngine`'s store accumulates what it is told to run; reusing one engine across plants
    would let an earlier plant's evidence leak into a later plant's narratives. Constructing a new
    `AtlasEngine` inside `run` keeps one `AtlasDetector` safe to hand the whole exam.

    **Why this adapter, and not `phos.models.ModelDetector`.** Atlas's whole claim is that it
    narrates competing explanations, not just flags; a `Detection` has no room for a hypothesis's
    label. `last_store` and `last_narratives` hold the most recent run's full output precisely so
    `phos.referee.scoring` can read it for the metrics S6 asks for that a `Detection` cannot carry
    — fault-versus-attack discrimination and uncertainty honesty both need the leading hypothesis,
    not merely a confidence number.

    **The mapping from narrative to `Detection` is one choice among several, named here.** A
    narrative's earliest evidence timestamp is its detection time. `Narrative.overall_confidence`
    is reserved for a calibrated probability no engine sets yet (its own docstring: "engines
    leave this `None` until hypothesis confidence is calibrated") and is `None` in every real run,
    so this adapter uses the *leading hypothesis's* `confidence` instead — found by
    `leading_hypothesis`, the same tie-break `phos.referee.scoring` uses to name what a narrative
    leads with. That confidence is **not** a calibrated probability either (Constitution §3.3);
    using it inside this harness to threshold and rank is measurement, not display, and nothing
    downstream may surface it to a person.

    **Five independent evidence streams are fused:** the Mahalanobis joint model, per-plant
    consistency (cross-signal loop departures), sequential consistency (setpoint walk detection),
    walk consistency (valve status vs physics), and code law (valve mode vs controller program).
    Each catches a different class of departure that the others miss. Together they catch attacks
    that stay within ordinary sensor ranges — the class no reading-only detector can see.
    """

    def __init__(
        self,
        fitted: FittedModel,
        calibrator: FittedCalibrator,
        subsystem_map: SubsystemMap,
        config: AtlasConfig | None = None,
        consistency_calibrator: FittedCalibrator | None = None,
        command_fitted: FittedModel | None = None,
        command_calibrator: FittedCalibrator | None = None,
        sequential_model: dict[str, tuple[int, int]] | None = None,
        hai_baselines: dict[str, tuple[int, float]] | None = None,
    ) -> None:
        """Assemble the fitted parts an `AtlasEngine` needs on every plant it scores.

        Args:
            fitted: The fitted joint model, e.g. `phos.atlas.MahalanobisModel` fitted on a
                training prefix.
            calibrator: A calibrator fitted on a held-out calibration slice.
            subsystem_map: The declared partition of this plant's signals.
            config: Grouping window and reasoning settings, or ``None`` for `AtlasEngine`'s
                defaults.
            consistency_calibrator: A calibrator for consistency loop scores, or ``None`` to run
                Atlas without consistency evidence (byte-identical to the run without it). The
                consistency model itself is fit per-plant inside `run` on this plant's own
                attack-free training prefix.
            command_fitted: A pre-fitted command behaviour model (e.g. `EwmaBaseline` fitted on
                a separate training plant's capture), or ``None`` to run Atlas without command
                evidence.
            command_calibrator: A calibrator for command behaviour scores, or ``None`` if no
                command model is configured.
            sequential_model: A mapping from setpoint tag name to ``(column, longest_run)``
                learned from attack-free training on a separate training plant, or ``None`` to
                run Atlas without sequential consistency evidence.
            hai_baselines: Ignored. Kept so an existing caller still constructs. The HAI
                builder this used to feed is quarantined (ADR 0461) and is not called.
        """
        self._fitted = fitted
        self._calibrator = calibrator
        self._map = subsystem_map
        self._config = config
        self._consistency_calibrator = consistency_calibrator
        self._command_fitted = command_fitted
        self._command_calibrator = command_calibrator
        self._sequential_model = sequential_model
        self._hai_baselines = hai_baselines
        self._current_capture_path: Path | None = None
        self.last_store: EvidenceStore | None = None
        self.last_narratives: tuple[Narrative, ...] = ()
        self.last_consistency: ConsistencyEvidence | None = None
        self.last_command: CommandEvidence | None = None
        self.last_sequential: dict[str, tuple[int, int]] | None = sequential_model

    @property
    def name(self) -> str:
        """Identify this detector by its fitted model and calibrator."""
        return f"atlas-referee:{self._fitted.name}+{self._calibrator.name}"

    def run(self, dataset: Dataset) -> list[Detection]:
        """Run a fresh `AtlasEngine` over ``dataset`` and return one `Detection` per narrative.

        Args:
            dataset: The corpus to score.

        Returns:
            One `Detection` per narrative that resolved to at least one piece of evidence. A
            narrative with no resolvable evidence (which should not happen; the store that
            produced it is the same store its evidence ids are read from) contributes none,
            rather than a `Detection` with a guessed timestamp.
        """
        consistency = None
        if self._consistency_calibrator is not None:
            consistency = _build_consistency_evidence(
                self._consistency_calibrator,
                dataset,
            )

        command_evidence: CommandEvidence | None = None
        if (
            self._command_fitted is not None
            and self._command_calibrator is not None
            and self._current_capture_path is not None
        ):
            command_evidence = cast(
                CommandEvidence | None,
                _build_command_evidence(
                    self._command_calibrator,
                    self._current_capture_path,
                ),
            )
            self._current_capture_path = None  # consume once

        engine = AtlasEngine(
            fitted=self._fitted,
            calibrator=self._calibrator,
            subsystem_map=self._map,
            config=self._config,
        )
        narratives = engine.run(
            dataset,
            commands=command_evidence,
            consistency=consistency,
        )
        self.last_store = engine.store
        self.last_narratives = tuple(narratives)
        self.last_consistency = consistency
        self.last_command = command_evidence

        evidence_by_id = {item.id: item for item in engine.store.evidence()}
        hypotheses_by_id = {item.id: item for item in engine.store.hypotheses()}
        detections: list[Detection] = []
        for narrative in narratives:
            items = [
                evidence_by_id[evidence_id]
                for evidence_id in narrative.evidence_ids
                if evidence_id in evidence_by_id
            ]
            leader = leading_hypothesis(narrative, hypotheses_by_id)
            if not items or leader is None:
                continue
            confidence = max(0.0, min(1.0, leader.confidence))
            detections.append(
                Detection(
                    timestamp=min(item.timestamp for item in items),
                    score=confidence,
                    confidence=confidence,
                    entity_ids=sorted({entity for item in items for entity in item.entity_ids}),
                    feature=None,
                )
            )

        # Add sequential consistency detections (setpoint walk detection)
        if self._sequential_model is not None:
            seq_detections = _build_sequential_detections(
                self._sequential_model,
                dataset,
            )
            detections.extend(seq_detections)

        # Add walk consistency detections (valve status vs physics)
        if self._consistency_calibrator is not None:
            walk_detections = _build_walk_detections(self._consistency_calibrator, dataset)
            detections.extend(walk_detections)

        # Add code-law detections (valve mode vs controller program)
        code_law_detections = _build_code_law_detections(dataset)
        detections.extend(code_law_detections)

        # The BATADAL and HAI builders are quarantined (ADR 0461). They are not
        # called. Each raises QuarantinedCorpusError before it reads a corpus.
        return detections


def baseline_detector(fitted: FittedModel, score_scale: float = 3.0) -> Detector:
    """Wrap an already-fitted baseline model as something the referee's harness can score.

    There is nothing to build: `phos.models.ModelDetector` already satisfies `phos.eval.Detector`
    for any `FittedModel`, so the per-signal Gaussian (`phos.models.GaussianBaseline`) and the
    Mahalanobis model (`phos.atlas.MahalanobisModel`) are both scorable through it unchanged. This
    function exists only so `phos.referee.scoring` has one name to call regardless of which
    baseline it is scoring, instead of constructing `ModelDetector` by hand at every call site.

    Args:
        fitted: An already-fitted model.
        score_scale: Passed through to `ModelDetector`; see its own docstring.

    Returns:
        A `Detector` ready to be scored.
    """
    return ModelDetector(fitted=fitted, score_scale=score_scale)


class ThirdPartyDetectorTemplate:
    """Documented, empty template for a third party's detector.

    Fill in `name` and `run`. The referee asks for nothing else: no base class to subclass, no
    registration call, and no import of anything referee- or Atlas-internal. Satisfying
    `phos.eval.Detector` structurally — a `name` property and a `run(dataset) -> list[Detection]`
    method — is the whole contract, and `Detector` is `@runtime_checkable` so conformance can be
    checked with ``isinstance`` and never needs this class to be a real base class.

    This template is never run and is not registered anywhere. `tests/referee/test_detectors.py`
    only asserts that a conforming subclass satisfies `Detector`, so the template stays honest if
    the protocol it documents ever changes shape, rather than pretending a stub constitutes a
    working adapter.
    """

    @property
    def name(self) -> str:
        """Return a short, stable identifier for this detector."""
        raise NotImplementedError("name a third-party detector before using this template")

    def run(self, dataset: Dataset) -> list[Detection]:
        """Return this detector's detections for ``dataset``.

        Args:
            dataset: The corpus to score. Carries observations only — never labels or seeds; see
                `phos.referee.integrity` for how that is enforced on the way in.

        Returns:
            One `Detection` per flagged instant. ``timestamp`` and ``entity_ids`` are required;
            ``score`` is this detector's own unbounded anomaly score; ``confidence`` must be in
            ``[0, 1]`` and must never be presented to a person as a calibrated probability unless
            it genuinely is one.
        """
        raise NotImplementedError("implement run() before using this template")

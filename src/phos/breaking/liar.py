"""The held-out liar measurement (T1): ADR 0094's declaration, run through the breaking harness.

One run is one plant, one held-out seed and one subtlety (ADR 0094). Each plant-and-seed pair is
one generated corpus holding that plant's library liar at all six subtleties, laid out exactly as
the library lays out a process pack, so the corpus can be split into the two folds the harness
cross-fits calibrators on. Atlas is assembled as `phos.breaking.harness.run_breaking` assembles
it: the plant's joint model fitted on a separate attack-free corpus, a sensor calibrator fitted on
the other fold, the declared subsystem map and the OT templates. The consistency inlet is added:
`phos.atlas.consistency` fitted on the same attack-free corpus, with `windows_for_period` of the
corpus's sample period (ADR 0112), and its calibrator fitted on the plant's development-seed liar
corpora (71001 to 71003), never on a held-out one (ADR 0114).

Each fold runs twice, with and without the inlet, so the comparison row ADR 0094 names ("the same
share for Atlas without that citation") comes from the same fitted parts. A run's competing set is
the precedent `phos.breaking.commands.rank_explanations` set: every hypothesis with supporting
evidence timestamped inside the attack window. The checked opponents (MinMax, Steadytime,
Histogram, fitted with the G1 defaults on the same attack-free corpus) are reported as whether any
of their alerts falls inside the window.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

import numpy
from numpy.typing import NDArray

from phos.atlas import AtlasEngine
from phos.atlas.consistency import ConsistencyModel, TrainFile, fit
from phos.atlas.consistency_evidence import ConsistencyEvidence, promote_consistency
from phos.atlas.consistency_windows import Windows, scale_windows, windows_for_period
from phos.atlas.plant_map_detector import Arm, PlantMapDetector, fit_detector
from phos.atlas.plant_map_evidence import PlantMapPromotion, promote_plant_map
from phos.atlas.plant_map_model import MapSettings
from phos.atlas.vectorise import SignalSpace, vectorise
from phos.breaking.corpus import AttackCorpus, NormalCorpus
from phos.breaking.declared_roles import description_for, plant_roles
from phos.breaking.harness import (
    BreakingConfig,
    _covers,
    _fold_boundary,
    _fold_calibrator,
    _model_for,
    _slice,
)
from phos.eval import Dataset
from phos.eval.baseline_alerts import _histogram_cells, _minmax_cells, _steady_cells
from phos.eval.baseline_table import _fit_opponents, grid_from_columns
from phos.eval.liar_declaration import LEADING_TEMPLATE_ID, liar_run_passes
from phos.library.ot import (
    PROCESS_GAP_HOURS,
    SAMPLE_INTERVAL_SECONDS,
    lay_out,
    liar_recipe,
    pack_start,
)
from phos.ontology import EntityId, EvidenceStore, Hypothesis
from phos.reasoning import FittedCalibrator, IsotonicCalibrator, PlattCalibrator, tied_lead_ids
from phos.reasoning.templates import INSUFFICIENT_EVIDENCE_TEMPLATE_ID
from phos.synth.attacks.battery import AttackDatasetConfig
from phos.synth.attacks.spec import AttackGroundTruth, AttackType

__all__ = [
    "OPPONENTS",
    "Inlet",
    "LiarRun",
    "fit_inlet",
    "inlet_calibrator",
    "liar_corpus_config",
    "promote_map",
    "run_liar_corpus",
]

logger = logging.getLogger(__name__)

#: The checked opponents, by G1 name, reported as an alert inside the window.
OPPONENTS: Final = ("simple-minmax", "simple-steadytime", "simple-histogram")


@dataclass(frozen=True)
class LiarRun:
    """One plant, one seed, one subtlety: whether each arrangement met the declared catch.

    Attributes:
        plant_id: The plant.
        seed: The held-out seed of the corpus.
        subtlety: The dial value.
        attack_id: The attack's id in the corpus.
        scored: Whether the attack lay wholly inside one fold. An unscored run does not pass.
        passes: ADR 0094's predicate with the consistency inlet: the unique contentful leader is
            `sensor_or_device_fault` and cites a consistency facet.
        leader_with_inlet: The unique contentful leader with the inlet, or ``None`` (tie or none).
        leads_without_inlet: Without the inlet, the unique contentful leader is
            `sensor_or_device_fault`. No citation is asked: none can exist without the inlet.
        leader_without_inlet: The unique contentful leader without the inlet, or ``None``.
        opponent_alert: For each opponent, whether any of its alerts falls inside the window.
    """

    plant_id: str
    seed: int
    subtlety: float
    attack_id: str
    scored: bool
    passes: bool
    leader_with_inlet: str | None
    leads_without_inlet: bool
    leader_without_inlet: str | None
    opponent_alert: tuple[bool, ...]


def liar_corpus_config(plant_id: str, seed: int) -> AttackDatasetConfig:
    """The corpus for one plant and seed: its library liar at all six subtleties.

    Laid out by the library's own process-pack layout (prefix, gap, tail, sample interval,
    traffic seed offset), with the liar as the only recipe.
    """
    plans, duration = lay_out(plant_id, "liar", (liar_recipe(plant_id),), seed, PROCESS_GAP_HOURS)
    return AttackDatasetConfig(
        name=f"t1-liar-{plant_id}-s{seed}",
        plant_id=plant_id,
        seed=seed,
        traffic_seed=seed + 17,
        start=pack_start(),
        duration_hours=duration,
        sample_interval_seconds=SAMPLE_INTERVAL_SECONDS,
        role="attack",
        note=f"T1 liar corpus for {plant_id}, held-out seed {seed} (ADR 0094, ADR 0114).",
        attacks=plans,
    )


class _Unit:
    """Weight 1 for every candidate. Used only to enumerate candidates; its weights are dropped."""

    name = "unit"

    def calibrate(self, scores: NDArray[numpy.float64]) -> NDArray[numpy.float64]:
        return numpy.ones(len(scores), dtype=numpy.float64)


@dataclass(frozen=True)
class _Matrix:
    timestamps: tuple[datetime, ...]
    values: NDArray[numpy.float64]


def _matrix(dataset: Dataset, space: SignalSpace) -> _Matrix:
    series = vectorise(dataset.observations, space)
    return _Matrix(series.timestamps, series.matrix)


def _names(space: SignalSpace) -> tuple[list[str], dict[str, EntityId]]:
    features = [feature for _entity, feature in space.signals]
    if len(set(features)) != len(features):
        raise ValueError(
            "two entities share a signal name; the consistency inlet needs unique ones"
        )
    return features, {feature: entity for entity, feature in space.signals}


@dataclass(frozen=True)
class Inlet:
    """The consistency inlet for one plant: the detector fitted on the attack-free corpus.

    ``detector`` is the plant-map challenger (ADR 0127) when the inlet was fitted with one; its
    facts then replace the champion's. ``None`` is the champion, exactly as T1 declared it.
    """

    model: ConsistencyModel
    space: SignalSpace
    learned: tuple[datetime, datetime]
    detector: PlantMapDetector | None = None


def fit_inlet(
    normal: NormalCorpus,
    base: Windows | None = None,
    plant_map: MapSettings | None = None,
    arm: Arm = Arm.EXTEND,
) -> Inlet:
    """Fit the consistency detector on a plant's attack-free corpus, windows by its period.

    ``base`` is a window set in seconds for the arena to try (ADR 0120), converted by the same
    rule; ``None``, the default, is ADR 0112's `windows_for_period`, as T1 declared it.
    ``plant_map`` fits `atlas-plant-map-v1` beside it with those settings, on the same corpus,
    with the plant's declared roles and loops (ADR 0127); ``arm`` is its replace arm, diagnosis
    only.
    """
    space = SignalSpace.from_observations(normal.dataset.observations)
    matrix = _matrix(normal.dataset, space)
    period = float(numpy.median(numpy.diff([t.timestamp() for t in matrix.timestamps])))
    windows = windows_for_period(period) if base is None else scale_windows(base, period)
    train = [
        TrainFile(values=matrix.values, attack=numpy.zeros(matrix.values.shape[0], numpy.bool_))
    ]
    model = fit(train, windows)
    detector = None
    if plant_map is not None:
        features, _entity_of = _names(space)
        roles = plant_roles(description_for(normal.plant_id))
        detector = fit_detector(train, features, roles, period, windows, plant_map, arm)
    return Inlet(model, space, (matrix.timestamps[0], matrix.timestamps[-1]), detector)


def promote_map(inlet: Inlet, dataset: Dataset, calibrator: FittedCalibrator) -> PlantMapPromotion:
    """The challenger's facts and event records for one dataset.

    Raises:
        ValueError: If the inlet was fitted without the plant map.
    """
    if inlet.detector is None:
        raise ValueError("this inlet has no plant map")
    matrix = _matrix(dataset, inlet.space)
    features, entity_of = _names(inlet.space)
    return promote_plant_map(
        inlet.detector,
        matrix.values,
        matrix.timestamps,
        features,
        entity_of,
        calibrator,
        inlet.learned,
    )


def _promote(inlet: Inlet, dataset: Dataset, calibrator: FittedCalibrator) -> ConsistencyEvidence:
    if inlet.detector is not None:
        return promote_map(inlet, dataset, calibrator).evidence
    matrix = _matrix(dataset, inlet.space)
    features, entity_of = _names(inlet.space)
    return promote_consistency(
        inlet.model,
        matrix.values,
        matrix.timestamps,
        features,
        entity_of,
        calibrator,
        inlet.learned,
    )


def inlet_calibrator(
    inlet: Inlet, development: Sequence[AttackCorpus], seed: int
) -> FittedCalibrator | None:
    """Fit the inlet's calibrator on development corpora only, never on a held-out one.

    Candidates are every loop-carried event `promote_consistency` would promote in each
    development corpus; a candidate is positive when it falls inside one of that corpus's attack
    windows. ``None`` when the candidates do not hold both classes: the plant then runs without
    the inlet, so none of its runs can cite a consistency facet.
    """
    scores: list[float] = []
    labels: list[float] = []
    for corpus in development:
        windows = corpus.dataset.attack_intervals
        for fact in _promote(inlet, corpus.dataset, _Unit()).facts:
            scores.append(fact.deviation.magnitude)
            inside = any(window.contains(fact.evidence.timestamp) for window in windows)
            labels.append(1.0 if inside else 0.0)
    platt = inlet.detector is not None and inlet.detector.plant.settings.calibrator == "platt"
    method = PlattCalibrator(seed=seed) if platt else IsotonicCalibrator(seed=seed)
    try:
        return method.fit(
            numpy.asarray(scores, dtype=numpy.float64), numpy.asarray(labels, dtype=numpy.float64)
        )
    except ValueError as error:
        logger.warning("no consistency calibrator from development corpora (%s)", error)
        return None


def _competing(truth: AttackGroundTruth, store: EvidenceStore) -> list[Hypothesis]:
    """`rank_explanations`' set: hypotheses with supporting evidence inside the window."""
    window = truth.interval()
    inside = {evidence.id for evidence in store.evidence() if window.contains(evidence.timestamp)}
    return [hypothesis for hypothesis in store.hypotheses() if inside & set(hypothesis.supporting)]


def _leader(hypotheses: Sequence[Hypothesis]) -> str | None:
    if tied_lead_ids(hypotheses):
        return None
    contentful = [h for h in hypotheses if h.template_id != INSUFFICIENT_EVIDENCE_TEMPLATE_ID]
    if not contentful:
        return None
    return min(contentful, key=lambda item: (-item.confidence, item.template_id)).template_id


def _opponent_alerts(
    normal: _Matrix, test: _Matrix, features: Sequence[str], windows: Sequence[AttackGroundTruth]
) -> dict[str, tuple[bool, ...]]:
    """For each opponent and attack, whether any alert falls inside the attack window."""
    n = test.values.shape[0]
    grid = grid_from_columns(test.timestamps, list(features), test.values, [False] * n, [False] * n)
    finite = numpy.isfinite(normal.values).all(axis=1)
    order = [list(features).index(name) for name in grid.features]
    minmax, steady, histogram = _fit_opponents(grid.features, normal.values[finite][:, order])
    cells = {
        "simple-minmax": _minmax_cells(minmax, grid),
        "simple-steadytime": _steady_cells(steady, grid),
        "simple-histogram": _histogram_cells(histogram, grid),
    }
    found: dict[str, tuple[bool, ...]] = {}
    for name in OPPONENTS:
        stamps = [grid.timestamps[row] for row, _feature, _score in cells[name]]
        found[name] = tuple(
            any(truth.interval().contains(stamp) for stamp in stamps) for truth in windows
        )
    return found


def run_liar_corpus(
    corpus: AttackCorpus,
    normal: NormalCorpus,
    inlet: Inlet,
    calibrator: FittedCalibrator | None,
    config: BreakingConfig | None = None,
) -> list[LiarRun]:
    """Score every liar in one corpus, with and without the consistency inlet.

    Args:
        corpus: A held-out liar corpus.
        normal: The plant's attack-free corpus, for the joint model and the opponents.
        inlet: `fit_inlet` of ``normal``.
        calibrator: `inlet_calibrator` from development corpora, or ``None`` for no inlet.
        config: The harness settings.

    Raises:
        ValueError: If the corpus and the normal corpus are different plants, or the corpus
            cannot be split into two folds.
    """
    settings = BreakingConfig() if config is None else config
    if normal.plant_id != corpus.manifest.plant_id:
        raise ValueError(f"{normal.name} is not a run of {corpus.manifest.plant_id!r}")
    dataset = corpus.dataset
    boundary = _fold_boundary(dataset, dataset.attack_intervals)
    if boundary is None:
        raise ValueError(f"{corpus.name} cannot be split into two folds")
    first = dataset.observations[0].timestamp
    last = dataset.observations[-1].timestamp + timedelta(seconds=1)
    early = _slice(dataset, first, boundary, "early")
    late = _slice(dataset, boundary, last, "late")

    fitted = _model_for(normal.plant_id, settings).fit(normal.dataset.observations)
    normal_matrix = _matrix(normal.dataset, inlet.space)
    subsystem_map = corpus.subsystem_map()
    liars = [truth for truth in corpus.manifest.attacks if truth.type is AttackType.LIAR]

    stores: list[tuple[Dataset, EvidenceStore, EvidenceStore]] = []
    for calibration_slice, test_slice in ((late, early), (early, late)):
        sensor = _fold_calibrator(fitted, calibration_slice, settings)
        without = AtlasEngine(fitted, sensor, subsystem_map, config=settings.atlas)
        without.run(test_slice)
        with_inlet = AtlasEngine(fitted, sensor, subsystem_map, config=settings.atlas)
        facts = None if calibrator is None else _promote(inlet, test_slice, calibrator)
        with_inlet.run(test_slice, consistency=facts)
        stores.append((test_slice, with_inlet.store, without.store))

    features, _entity_of = _names(inlet.space)
    opponents = _opponent_alerts(normal_matrix, _matrix(dataset, inlet.space), features, liars)
    runs: list[LiarRun] = []
    for index, truth in enumerate(liars):
        fold = next(
            ((w, wo) for test_slice, w, wo in stores if _covers(test_slice, truth.interval())),
            None,
        )
        opponent = tuple(opponents[name][index] for name in OPPONENTS)
        if fold is None:
            runs.append(
                LiarRun(
                    normal.plant_id,
                    corpus.manifest.spec.seed,
                    truth.subtlety,
                    truth.attack_id,
                    False,
                    False,
                    None,
                    False,
                    None,
                    opponent,
                )
            )
            continue
        with_store, without_store = fold
        competing = _competing(truth, with_store)
        facets = {evidence.id: evidence.facet for evidence in with_store.evidence()}
        leader_without = _leader(_competing(truth, without_store))
        runs.append(
            LiarRun(
                plant_id=normal.plant_id,
                seed=corpus.manifest.spec.seed,
                subtlety=truth.subtlety,
                attack_id=truth.attack_id,
                scored=True,
                passes=liar_run_passes(competing, facets),
                leader_with_inlet=_leader(competing),
                leads_without_inlet=leader_without == LEADING_TEMPLATE_ID,
                leader_without_inlet=leader_without,
                opponent_alert=opponent,
            )
        )
    return runs

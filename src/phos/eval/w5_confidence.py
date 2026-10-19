"""W5 scenarios with wrong answers, scored by ADR 0171's shape calibration (ADR 0175).

Five kinds on ``water-treatment``. The quiet train is seed 97001. Development seeds
97401-97420 may be built freely. Held-back seeds 97501-97520 are refused unless the
caller passes ``held_back_authorized``, which only the declared command does, after
the magnitudes are frozen.

The detector, the priors, and the shape rule are unchanged. ``k`` for the subtle
liar is the one development knob. The calibrated number is not surfaced.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from typing import Final

import numpy
from numpy.typing import NDArray

from phos.atlas.conformal_confidence import (
    HIGH_BOUND,
    CalibratedLead,
    ShapedOutcome,
    evidence_shape,
    leave_one_seed_out,
    summarise,
)
from phos.atlas.consistency import ConsistencyModel, TrainFile, fit
from phos.atlas.consistency_evidence import (
    CROSS_SIGNAL_MISMATCH,
    consistency_feature_of,
    promote_consistency,
)
from phos.atlas.consistency_windows import windows_for_period
from phos.atlas.explanation_calibration import BIN_EDGES, ReliabilityBin, reliability_svg
from phos.atlas.templates import (
    SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID,
    UNAUTHORISED_CONTROL_TEMPLATE_ID,
    atlas_library,
)
from phos.atlas.work_orders import promote_work_orders
from phos.eval.build_declaration import W5_DEVELOPMENT_SEEDS, W5_HELD_BACK_SEEDS
from phos.ontology import Domain, Entity, EntityType, Evidence, InMemoryEvidenceStore, Observation
from phos.reasoning import (
    INSUFFICIENT_EVIDENCE_TEMPLATE_ID,
    FittedPlattCalibrator,
    ReasoningConfig,
    ReasoningEngine,
)
from phos.synth.attacks.manipulations import ReadingBlend
from phos.synth.injection import CompositeInjection, HoldReading, TimeWindow
from phos.synth.plant import PlantDescription, RunSpec
from phos.synth.plants.water import (
    CHLORINE_RESIDUAL,
    DISTRIBUTION_PRESSURE,
    FILTER_HEADLOSS,
    LEVEL_SETPOINT,
    WATER_DESCRIPTION,
)
from phos.synth.run import PlantRun, run_plant

__all__ = [
    "KINDS",
    "K_LIAR",
    "LOW_CONFIDENCE",
    "PLANT_ID",
    "W5AuthorizationError",
    "chart_bins",
    "held_back_bar",
    "require_w5_seed",
    "score_split",
    "w5_seeds",
]

logger = logging.getLogger(__name__)

PLANT_ID: Final = "water-treatment"
KINDS: Final[tuple[str, ...]] = (
    "plain_sensor_fault",
    "fault_and_maintenance",
    "subtle_liar",
    "two_sensors",
    "mimic_with_work_order",
)
K_LIAR: Final = 3.0
"""Quiet-train standard deviations above the chlorine mean. Development may raise this."""

LOW_CONFIDENCE: Final = 0.5
"""A wrong lead at or above this is not low. The unseen-shape value sits on this line."""

_SAMPLE_SECONDS: Final = 30
_N_STEPS: Final = 160
_HALF: Final = 80
_START_YEAR: Final = 2026
_TRAIN_SEED: Final = 97001
_MIMIC_SETPOINT: Final = 4.8
_WEIGHT: Final = FittedPlattCalibrator(coefficient=0.0, intercept=0.0)
_ORDER_WEIGHT: Final = FittedPlattCalibrator(coefficient=0.0, intercept=40.0)
_WITH_ORDER: Final = frozenset({"fault_and_maintenance", "mimic_with_work_order"})


class W5AuthorizationError(RuntimeError):
    """Raised when a held-back W5 seed would be built without a declaration."""


def w5_seeds(split: str) -> tuple[int, ...]:
    """Return the seeds for ``development`` or ``held-back``.

    Raises:
        ValueError: If ``split`` is neither.
    """
    if split == "development":
        return W5_DEVELOPMENT_SEEDS
    if split == "held-back":
        return W5_HELD_BACK_SEEDS
    raise ValueError(f"split must be 'development' or 'held-back', got {split!r}")


def require_w5_seed(seed: int, split: str) -> None:
    """Refuse a seed outside the named W5 block, before a plant is built.

    Raises:
        ValueError: If ``seed`` is not in that block.
    """
    allowed = w5_seeds(split)
    if seed not in allowed:
        raise ValueError(f"seed {seed} is not in the W5 {split} block")


def score_split(split: str, *, held_back_authorized: bool = False) -> tuple[ShapedOutcome, ...]:
    """Score every kind on every seed of ``split``.

    Args:
        split: ``development`` or ``held-back``.
        held_back_authorized: Required for the held-back block. The declared command
            sets this only after the magnitudes are frozen in a committed declaration.

    Returns:
        One outcome per seed per kind.

    Raises:
        W5AuthorizationError: If the held-back block is requested without authorization.
    """
    if split == "held-back" and not held_back_authorized:
        raise W5AuthorizationError("held-back W5 seeds are not authorized")
    seeds = w5_seeds(split)
    for seed in seeds:
        require_w5_seed(seed, split)
    description = WATER_DESCRIPTION
    spec = _spec(_TRAIN_SEED)
    train = run_plant(PLANT_ID, spec)
    model_values = _matrix(train)
    fitted: ConsistencyModel = fit(
        [TrainFile(values=model_values, attack=numpy.zeros(len(train.steps), dtype=numpy.bool_))],
        windows_for_period(float(_SAMPLE_SECONDS)),
    )
    entities = _entities(description)
    entity_of = {entity.name: entity.id for entity in entities}
    chlorine_mean = float(numpy.mean(train.reported(CHLORINE_RESIDUAL)))
    found: list[ShapedOutcome] = []
    for seed in seeds:
        found.extend(
            _score_seed(
                seed,
                description,
                train,
                fitted,
                entities,
                entity_of,
                chlorine_mean,
            )
        )
    return tuple(found)


def chart_bins(leads: Sequence[CalibratedLead]) -> tuple[ReliabilityBin, ...]:
    """Bin calibrated confidence the way ADR 0162 bins raw confidence."""
    bins: list[ReliabilityBin] = []
    for low, high in pairwise(BIN_EDGES):
        members = [item for item in leads if low <= item.confidence < high]
        if not members:
            bins.append(ReliabilityBin(low, high, 0, 0, None, None))
            continue
        correct = sum(1 for item in members if item.outcome.correct)
        mean = sum(item.confidence for item in members) / len(members)
        bins.append(ReliabilityBin(low, high, len(members), correct, mean, correct / len(members)))
    return tuple(bins)


def held_back_bar(leads: Sequence[CalibratedLead]) -> dict[str, object]:
    """The two W5 checks, plus how many wrong leads sit in the high band."""
    summary = summarise(leads)
    wrong = [item for item in leads if not item.outcome.correct]
    wrong_low = sum(1 for item in wrong if item.confidence < LOW_CONFIDENCE)
    wrong_high = sum(1 for item in wrong if item.high)
    high = [item for item in leads if item.high]
    high_right_share = summary["high_right_share"]
    high_met = isinstance(high_right_share, float) and high_right_share >= HIGH_BOUND and bool(high)
    mostly_low = bool(wrong) and wrong_low / len(wrong) >= HIGH_BOUND
    return {
        **summary,
        "wrong": len(wrong),
        "wrong_low": wrong_low,
        "wrong_high": wrong_high,
        "wrong_mostly_low": mostly_low,
        "high_bar_met": high_met,
        "bar_met": high_met and mostly_low,
        "chart": reliability_svg(chart_bins(leads)),
    }


def _score_seed(
    seed: int,
    description: PlantDescription,
    train: PlantRun,
    model: ConsistencyModel,
    entities: Sequence[Entity],
    entity_of: Mapping[str, str],
    chlorine_mean: float,
) -> tuple[ShapedOutcome, ...]:
    spec = _spec(seed)
    found: list[ShapedOutcome] = []
    for kind in KINDS:
        injection = _injection(kind, spec, description, chlorine_mean)
        run = run_plant(PLANT_ID, spec, injection=injection)
        evidence = _physics(description, train, run, entity_of, model)
        if kind in _WITH_ORDER:
            evidence = evidence + _work_order(run, entity_of)
        found.append(_outcome(seed, kind, evidence, entities, entity_of))
    return tuple(found)


def _injection(
    kind: str,
    spec: RunSpec,
    description: PlantDescription,
    chlorine_mean: float,
) -> HoldReading | CompositeInjection | ReadingBlend:
    window = TimeWindow(start=spec.instant(_HALF), end=spec.instant(_N_STEPS))
    chlorine = description.signal(CHLORINE_RESIDUAL)
    pressure = description.signal(DISTRIBUTION_PRESSURE)
    setpoint = description.signal(LEVEL_SETPOINT)
    if kind in {"plain_sensor_fault", "fault_and_maintenance"}:
        return HoldReading(signal=CHLORINE_RESIDUAL, value=0.0, window=window)
    if kind == "subtle_liar":
        target = chlorine_mean + K_LIAR * chlorine.noise_stddev
        target = min(chlorine.high, max(chlorine.low, target))
        return HoldReading(signal=CHLORINE_RESIDUAL, value=target, window=window)
    if kind == "two_sensors":
        return CompositeInjection(
            parts=(
                HoldReading(signal=CHLORINE_RESIDUAL, value=0.0, window=window),
                HoldReading(signal=DISTRIBUTION_PRESSURE, value=pressure.low, window=window),
            )
        )
    if kind == "mimic_with_work_order":
        return ReadingBlend(
            signal=LEVEL_SETPOINT,
            target=_MIMIC_SETPOINT,
            strength=1.0,
            low=setpoint.low,
            high=setpoint.high,
            window=window,
            jitter=0.0,
        )
    raise ValueError(f"unknown kind {kind!r}")


def _work_order(run: PlantRun, entity_of: Mapping[str, str]) -> tuple[Evidence, ...]:
    """A filtration work order. It does not name the chlorine sensor or the setpoint."""
    stamp = run.steps[_HALF].timestamp
    observation = Observation(
        entity_ids=["wo_w5_filtration", entity_of[FILTER_HEADLOSS]],
        feature="work_order",
        value=1.0,
        timestamp=stamp,
        domain=Domain.ATLAS,
        context={"ticket": "WO-filtration", "asset": "filtration"},
    )
    facts = promote_work_orders([observation], _ORDER_WEIGHT)
    return tuple(fact.evidence for fact in facts)


def _physics(
    description: PlantDescription,
    train: PlantRun,
    run: PlantRun,
    entity_of: Mapping[str, str],
    model: ConsistencyModel,
) -> tuple[Evidence, ...]:
    bundle = promote_consistency(
        model,
        _matrix(run),
        [step.timestamp for step in run.steps],
        [spec.key for spec in description.signals],
        entity_of,
        _WEIGHT,
        (train.steps[0].timestamp, train.steps[-1].timestamp),
    )
    return tuple(
        fact.evidence
        for fact in bundle.facts
        if consistency_feature_of(fact.evidence) == CROSS_SIGNAL_MISMATCH
    )


def _outcome(
    seed: int,
    kind: str,
    evidence: Sequence[Evidence],
    entities: Sequence[Entity],
    entity_of: Mapping[str, str],
) -> ShapedOutcome:
    store = InMemoryEvidenceStore()
    for entity in entities:
        store.add_entity(entity)
    engine = ReasoningEngine(
        atlas_library(), store, ReasoningConfig(correlation_window=timedelta(hours=2))
    )
    if evidence:
        engine.ingest(evidence)
    lead = engine.competing(Domain.ATLAS)[0]
    contentful = lead.template_id != INSUFFICIENT_EVIDENCE_TEMPLATE_ID
    by_id = {item.id: item for item in evidence}
    supporting = [by_id[item] for item in lead.supporting if item in by_id]
    correct: bool | None = None
    if contentful:
        correct = _is_right(kind, lead.template_id, supporting, entity_of)
    return ShapedOutcome(
        seed=seed,
        plant_id=PLANT_ID,
        scenario=kind,
        lead=lead.template_id,
        raw_confidence=lead.confidence,
        shape=evidence_shape(supporting),
        contentful=contentful,
        correct=correct,
    )


def _is_right(
    kind: str,
    lead: str,
    supporting: Sequence[Evidence],
    entity_of: Mapping[str, str],
) -> bool:
    if kind in {"plain_sensor_fault", "fault_and_maintenance", "subtle_liar"}:
        return lead == SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID
    if kind == "two_sensors":
        named = {item_id for fact in supporting for item_id in fact.entity_ids}
        both = entity_of[CHLORINE_RESIDUAL] in named and entity_of[DISTRIBUTION_PRESSURE] in named
        return lead == SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID and both
    if kind == "mimic_with_work_order":
        return lead == UNAUTHORISED_CONTROL_TEMPLATE_ID
    raise ValueError(f"unknown kind {kind!r}")


def _spec(seed: int) -> RunSpec:
    interval = timedelta(seconds=_SAMPLE_SECONDS)
    return RunSpec(
        seed=seed,
        start=datetime(_START_YEAR, 10, 1, tzinfo=UTC),
        duration=interval * _N_STEPS,
        sample_interval=interval,
    )


def _entities(description: PlantDescription) -> tuple[Entity, ...]:
    return tuple(
        Entity(
            id=f"ent_{description.plant_id}_{spec.key}",
            type=EntityType.PLC,
            domain=Domain.ATLAS,
            name=spec.key,
        )
        for spec in description.signals
    )


def _matrix(run: PlantRun) -> NDArray[numpy.float64]:
    keys = [spec.key for spec in run.description.signals]
    rows = [[step.report.values[key] for key in keys] for step in run.steps]
    return numpy.asarray(rows, dtype=numpy.float64)


def development_report(outcomes: Sequence[ShapedOutcome]) -> dict[str, object]:
    """Out-of-fold development summary. Does not touch held-back seeds."""
    leads = leave_one_seed_out(outcomes)
    body = held_back_bar(leads)
    chart = body.pop("chart")
    return {"split": "development", "k_liar": K_LIAR, "leads": len(leads), **body, "svg": chart}

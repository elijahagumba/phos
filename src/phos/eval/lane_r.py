"""Lane R challenger: origin facts and, later, an uncovered setpoint, on the W5 scenarios.

The frozen W5 scorer is not this module. `score_split` there is unchanged. This module
reuses its plant, its kinds, and its right-rule, and adds evidence the confusion table asked for.
Development seeds 97401-97420 may be scored freely. Held-back seeds are refused here; the one
held-back look lives in the declared command.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy
from numpy.typing import NDArray

from phos.atlas.conformal_confidence import ShapedOutcome, evidence_shape
from phos.atlas.consistency import ConsistencyModel, TrainFile, fit
from phos.atlas.consistency_evidence import CROSS_SIGNAL_MISMATCH, consistency_feature_of
from phos.atlas.consistency_windows import windows_for_period
from phos.atlas.loop_explainer import LOOP_EXPLAINER_SETTINGS, roles_with_every_control_coupling
from phos.atlas.origin_evidence import member_evidence, origin_evidence
from phos.atlas.plant_map_fit import fit_map
from phos.atlas.plant_map_model import PlantMap
from phos.atlas.templates import atlas_library
from phos.atlas.uncovered_setpoint import uncovered_setpoint_evidence
from phos.eval import w5_confidence as w5
from phos.eval.build_declaration import LANE_R_HELD_BACK_SEEDS
from phos.ontology import Domain, Entity, EntityId, Evidence, InMemoryEvidenceStore
from phos.reasoning import INSUFFICIENT_EVIDENCE_TEMPLATE_ID, ReasoningConfig, ReasoningEngine
from phos.reasoning.separation import separation_count
from phos.synth.plant import PlantDescription
from phos.synth.plants.water import CHLORINE_RESIDUAL, WATER_DESCRIPTION
from phos.synth.run import PlantRun, run_plant

__all__ = [
    "DevelopmentRow",
    "development_rows",
    "score_h1",
    "score_h1b",
    "score_h2",
    "score_h2b",
    "score_seeds",
]


@dataclass(frozen=True)
class DevelopmentRow:
    """One development lead and how many facts separate it from the runner-up.

    Attributes:
        outcome: The engine's lead, before the separation refusal.
        separation: Facts that support one of the lead and the runner-up and contradict the other.
        rival: The runner-up template, or ``None`` when no contentful rival was spawned.
    """

    outcome: ShapedOutcome
    separation: int
    rival: str | None


def score_h1(split: str = "development") -> tuple[ShapedOutcome, ...]:
    """Score ``split`` with one extra cross-signal fact per unnamed root-cause origin.

    Args:
        split: ``development`` only. Held-back is refused so this function cannot be the one look.

    Raises:
        ValueError: If ``split`` is not ``development``.
    """
    return _outcomes(split, "h1")


def score_h1b(split: str = "development") -> tuple[ShapedOutcome, ...]:
    """Score ``split`` with one fact per out-of-band event member, inherited members included.

    Args:
        split: ``development`` only.

    Raises:
        ValueError: If ``split`` is not ``development``.
    """
    return _outcomes(split, "h1b")


def score_h2b(split: str = "development") -> tuple[ShapedOutcome, ...]:
    """Score H1b, and drop cross-signal facts when a widened uncovered setpoint is present.

    Args:
        split: ``development`` only.

    Raises:
        ValueError: If ``split`` is not ``development``.
    """
    return _outcomes(split, "h2b")


def score_h2(split: str = "development") -> tuple[ShapedOutcome, ...]:
    """Score ``split`` with an uncovered-setpoint fact on the frozen W5 evidence.

    H2 does not add origin or member facts. The setpoint fact is the only addition.

    Args:
        split: ``development`` only.

    Raises:
        ValueError: If ``split`` is not ``development``.
    """
    return _outcomes(split, "h2")


def development_rows(mode: str) -> tuple[DevelopmentRow, ...]:
    """Development leads for ``mode``, each with its separation count.

    The count is how many facts support the lead and contradict the runner-up, or the
    reverse. It is not a probability.
    """
    if mode not in {"h1", "h1b", "h2", "h2b"}:
        raise ValueError(f"unknown Lane R mode {mode!r}")
    return _score("development", mode)


def _outcomes(split: str, mode: str) -> tuple[ShapedOutcome, ...]:
    """The shaped leads for ``mode``, without the separation counts."""
    return tuple(item.outcome for item in _score(split, mode))


def score_seeds(
    seeds: Sequence[int], mode: str, *, held_back_authorized: bool = False
) -> tuple[DevelopmentRow, ...]:
    """Score ``seeds`` with ``mode``. The caller has already checked that the seeds are allowed.

    Development uses `development_rows`. The held-back command is the only caller for
    seeds 97701-97720, and only after its declaration.
    """
    if mode not in {"h1", "h1b", "h2", "h2b"}:
        raise ValueError(f"unknown Lane R mode {mode!r}")
    held = frozenset(LANE_R_HELD_BACK_SEEDS)
    if held.intersection(seeds) and not held_back_authorized:
        raise PermissionError(
            "seeds 97701-97720 are scored once, after the Lane R declaration, "
            "by scripts/lane_r_heldback.py"
        )
    return _run(tuple(seeds), mode)


def _score(split: str, mode: str) -> tuple[DevelopmentRow, ...]:
    """Shared development loop. ``mode`` is ``h1``, ``h1b``, ``h2``, or ``h2b``."""
    if split != "development":
        raise ValueError("Lane R development scoring refuses any other split")
    return _run(w5.w5_seeds("development"), mode)


def _run(seeds: Sequence[int], mode: str) -> tuple[DevelopmentRow, ...]:
    """Fit the quiet train once and score ``seeds``. Does not check which block they are in."""
    description = WATER_DESCRIPTION
    train_spec = w5._spec(w5._TRAIN_SEED)
    train = run_plant(w5.PLANT_ID, train_spec)
    model_values = w5._matrix(train)
    trained = TrainFile(
        values=model_values, attack=numpy.zeros(len(train.steps), dtype=numpy.bool_)
    )
    windows = windows_for_period(float(w5._SAMPLE_SECONDS))
    fitted = fit([trained], windows)
    keys = [spec.key for spec in description.signals]
    plant_map = fit_map(
        [trained],
        keys,
        roles_with_every_control_coupling(description),
        float(w5._SAMPLE_SECONDS),
        LOOP_EXPLAINER_SETTINGS,
    )
    entities = w5._entities(description)
    entity_of = {entity.name: entity.id for entity in entities}
    chlorine_mean = float(numpy.mean(train.reported(CHLORINE_RESIDUAL)))
    learned = (train.steps[0].timestamp, train.steps[-1].timestamp)
    found: list[DevelopmentRow] = []
    for seed in seeds:
        found.extend(
            _score_seed(
                seed,
                description,
                train,
                fitted,
                plant_map,
                entities,
                entity_of,
                chlorine_mean,
                learned,
                mode,
                model_values,
            )
        )
    return tuple(found)


def _score_seed(
    seed: int,
    description: PlantDescription,
    train: PlantRun,
    model: ConsistencyModel,
    plant_map: PlantMap,
    entities: Sequence[Entity],
    entity_of: Mapping[str, EntityId],
    chlorine_mean: float,
    learned: tuple[datetime, datetime],
    mode: str,
    train_values: NDArray[numpy.float64],
) -> tuple[DevelopmentRow, ...]:
    spec = w5._spec(seed)
    found: list[DevelopmentRow] = []
    for kind in w5.KINDS:
        injection = w5._injection(kind, spec, description, chlorine_mean)
        run = run_plant(w5.PLANT_ID, spec, injection=injection)
        physics = w5._physics(description, train, run, entity_of, model)
        orders: tuple[Evidence, ...] = ()
        if kind in w5._WITH_ORDER:
            orders = w5._work_order(run, entity_of)
        evidence = _assemble(
            mode,
            plant_map,
            model,
            run,
            physics,
            orders,
            entity_of,
            learned,
            description,
            train_values,
        )
        found.append(_outcome(seed, kind, evidence, entities, entity_of))
    return tuple(found)


def _assemble(
    mode: str,
    plant_map: PlantMap,
    model: ConsistencyModel,
    run: PlantRun,
    physics: tuple[Evidence, ...],
    orders: tuple[Evidence, ...],
    entity_of: Mapping[str, EntityId],
    learned: tuple[datetime, datetime],
    description: PlantDescription,
    train_values: NDArray[numpy.float64],
) -> tuple[Evidence, ...]:
    """Physics, work orders, and the facts ``mode`` adds.

    H2b drops the cross-signal facts when a widened uncovered setpoint is present. Those
    facts are the plant following a setpoint the work order does not cover.
    """
    if mode == "h2b":
        uncovered = uncovered_setpoint_evidence(
            description,
            train_values,
            run,
            entity_of,
            orders,
            learned,
            widen_by_range=True,
        )
        if uncovered:
            return orders + uncovered
        return _with_members(plant_map, model, run, physics, orders, entity_of, learned)
    if mode == "h2":
        return (
            physics
            + orders
            + uncovered_setpoint_evidence(
                description, train_values, run, entity_of, orders, learned
            )
        )
    if mode == "h1b":
        return _with_members(plant_map, model, run, physics, orders, entity_of, learned)
    if mode == "h1":
        matrix = w5._matrix(run)
        stamps = [step.timestamp for step in run.steps]
        named = _named_signals(physics, entity_of)
        return (
            physics
            + orders
            + origin_evidence(plant_map, model, matrix, stamps, entity_of, learned, named)
        )
    raise ValueError(f"unknown Lane R mode {mode!r}")


def _with_members(
    plant_map: PlantMap,
    model: ConsistencyModel,
    run: PlantRun,
    physics: tuple[Evidence, ...],
    orders: tuple[Evidence, ...],
    entity_of: Mapping[str, EntityId],
    learned: tuple[datetime, datetime],
) -> tuple[Evidence, ...]:
    matrix = w5._matrix(run)
    stamps = [step.timestamp for step in run.steps]
    named = _named_signals(physics, entity_of)
    return (
        physics
        + orders
        + member_evidence(plant_map, model, matrix, stamps, entity_of, learned, named)
    )


def _named_signals(
    evidence: Sequence[Evidence], entity_of: Mapping[str, EntityId]
) -> frozenset[str]:
    """Signal keys already cited by a cross-signal fact."""
    id_to_name = {entity_id: name for name, entity_id in entity_of.items()}
    named: set[str] = set()
    for fact in evidence:
        if consistency_feature_of(fact) != CROSS_SIGNAL_MISMATCH:
            continue
        for entity_id in fact.entity_ids:
            name = id_to_name.get(entity_id)
            if name is not None:
                named.add(name)
    return frozenset(named)


def _outcome(
    seed: int,
    kind: str,
    evidence: Sequence[Evidence],
    entities: Sequence[Entity],
    entity_of: Mapping[str, EntityId],
) -> DevelopmentRow:
    store = InMemoryEvidenceStore()
    for entity in entities:
        store.add_entity(entity)
    engine = ReasoningEngine(
        atlas_library(), store, ReasoningConfig(correlation_window=timedelta(hours=2))
    )
    if evidence:
        engine.ingest(evidence)
    competing = engine.competing(Domain.ATLAS)
    lead = competing[0]
    contentful = lead.template_id != INSUFFICIENT_EVIDENCE_TEMPLATE_ID
    by_id = {item.id: item for item in evidence}
    supporting = [by_id[item] for item in lead.supporting if item in by_id]
    correct: bool | None = None
    if contentful:
        correct = w5._is_right(kind, lead.template_id, supporting, entity_of)
    rival = next(
        (item for item in competing[1:] if item.template_id != INSUFFICIENT_EVIDENCE_TEMPLATE_ID),
        None,
    )
    separated = 0
    if contentful and rival is not None:
        separated = separation_count(
            lead.supporting, lead.contradictory, rival.supporting, rival.contradictory
        )
    outcome = ShapedOutcome(
        seed=seed,
        plant_id=w5.PLANT_ID,
        scenario=kind,
        lead=lead.template_id,
        raw_confidence=lead.confidence,
        shape=evidence_shape(supporting),
        contentful=contentful,
        correct=correct,
    )
    return DevelopmentRow(outcome, separated, None if rival is None else rival.template_id)

"""Calibrate explanation confidence by the shape of the evidence it rests on (ADR 0171).

The raw confidence on a hypothesis is the belief update from the frozen priors and
`EVIDENCE_STRENGTH`. It counts facts. In lane D's command scenarios (ADR 0162) one fact that an
actuator ignored its command and one cross-signal fact score the same as two cross-signal facts,
so right and wrong leads share one number.

This module groups each contentful lead by its *evidence shape*: the sorted set of consistency
facets among the facts that support it. It fits, on development runs only, how often a lead with
that shape was right, and reports `(right + 1) / (n + 2)`. A lead is high-confidence only when the
Wilson 95% lower bound of its shape's right share is at least 0.8. Nothing here edits a prior, a
template, the ranking or the raw confidence, and nothing here is surfaced to a user.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import timedelta
from typing import Final

from phos.atlas.command_physics import (
    N_STEPS,
    SCORED_LOOPS,
    WRITE_AT,
    _description,
    _entities,
    _mismatches,
    _physics,
    _require_seed,
    _seeds,
    _source,
    _spec,
    champion_train_seed,
)
from phos.atlas.consistency_evidence import consistency_feature_of
from phos.atlas.templates import SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID, atlas_library
from phos.ontology import Domain, Entity, Evidence, InMemoryEvidenceStore
from phos.reasoning import INSUFFICIENT_EVIDENCE_TEMPLATE_ID, ReasoningConfig, ReasoningEngine
from phos.synth.injection import HoldActuator, TimeWindow
from phos.synth.run import run_plant

__all__ = [
    "HIGH_BOUND",
    "WILSON_Z",
    "CalibratedLead",
    "ShapeCalibrator",
    "ShapedOutcome",
    "evidence_shape",
    "leave_one_seed_out",
    "score_shaped",
    "summarise",
    "wilson_lower",
]

logger = logging.getLogger(__name__)

HIGH_BOUND: Final = 0.8
"""A lead is high-confidence when its shape's Wilson lower bound reaches this."""

WILSON_Z: Final = 1.959963984540054
"""The two-sided 95% normal quantile."""

_CORRECT_LEAD: Final = SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID


@dataclass(frozen=True)
class ShapedOutcome:
    """One scenario's lead, its shape, and whether it was right.

    Attributes:
        seed: The plant seed.
        plant_id: Which synthetic plant.
        scenario: ``stuck``, ``follow`` or ``quiet``.
        lead: The template at the front of ``competing``.
        raw_confidence: The engine's number. Not a probability.
        shape: Sorted consistency facets among the lead's supporting facts.
        contentful: Whether the lead is an explanation other than the residual.
        correct: Whether a contentful lead is right. ``None`` for silence.
    """

    seed: int
    plant_id: str
    scenario: str
    lead: str
    raw_confidence: float
    shape: tuple[str, ...]
    contentful: bool
    correct: bool | None


@dataclass(frozen=True)
class CalibratedLead:
    """A contentful lead with its calibrated confidence.

    Attributes:
        outcome: The scored lead.
        confidence: ``(right + 1) / (n + 2)`` for its shape in the fitting runs.
        lower: The Wilson 95% lower bound for that shape.
        n: Fitting leads with that shape.
        high: Whether ``lower`` reaches `HIGH_BOUND`.
    """

    outcome: ShapedOutcome
    confidence: float
    lower: float
    n: int
    high: bool


def wilson_lower(right: int, n: int, z: float = WILSON_Z) -> float:
    """Return the Wilson score interval's lower bound, or 0 when ``n`` is 0.

    Raises:
        ValueError: If the counts are impossible.
    """
    if n < 0 or not 0 <= right <= n:
        raise ValueError(f"impossible counts: {right} right of {n}")
    if n == 0:
        return 0.0
    share = right / n
    z2 = z * z
    centre = share + z2 / (2 * n)
    spread = z * math.sqrt(share * (1 - share) / n + z2 / (4 * n * n))
    return max(0.0, (centre - spread) / (1 + z2 / n))


def evidence_shape(supporting: Sequence[Evidence]) -> tuple[str, ...]:
    """Return the sorted set of consistency facets among ``supporting``.

    A fact with no consistency facet is named by its evidence kind, so it is not silently dropped.
    """
    names = {consistency_feature_of(item) or item.kind.value for item in supporting}
    return tuple(sorted(names))


class ShapeCalibrator:
    """Right and total counts per evidence shape, fitted on development leads only."""

    def __init__(self, counts: Mapping[tuple[str, ...], tuple[int, int]]) -> None:
        """Store ``shape -> (right, n)``."""
        self._counts = dict(counts)

    @classmethod
    def fit(cls, outcomes: Sequence[ShapedOutcome]) -> ShapeCalibrator:
        """Count right and total contentful leads per shape. Silence is not counted."""
        counts: dict[tuple[str, ...], tuple[int, int]] = {}
        for item in outcomes:
            if not item.contentful or item.correct is None:
                continue
            right, n = counts.get(item.shape, (0, 0))
            counts[item.shape] = (right + int(item.correct), n + 1)
        return cls(counts)

    @property
    def counts(self) -> dict[tuple[str, ...], tuple[int, int]]:
        """A copy of ``shape -> (right, n)``."""
        return dict(self._counts)

    def calibrate(self, outcome: ShapedOutcome) -> CalibratedLead:
        """Return the calibrated confidence for one contentful lead."""
        right, n = self._counts.get(outcome.shape, (0, 0))
        confidence = (right + 1) / (n + 2)
        lower = wilson_lower(right, n)
        return CalibratedLead(outcome, confidence, lower, n, lower >= HIGH_BOUND)


def leave_one_seed_out(outcomes: Sequence[ShapedOutcome]) -> tuple[CalibratedLead, ...]:
    """Score each seed's contentful leads with a map fitted on every other seed."""
    seeds = sorted({item.seed for item in outcomes})
    scored: list[CalibratedLead] = []
    for seed in seeds:
        fitted = ShapeCalibrator.fit([item for item in outcomes if item.seed != seed])
        scored.extend(
            fitted.calibrate(item)
            for item in outcomes
            if item.seed == seed and item.contentful and item.correct is not None
        )
    return tuple(scored)


def summarise(leads: Sequence[CalibratedLead]) -> dict[str, object]:
    """High-confidence right share, and whether right and wrong leads share a score."""
    high = [lead for lead in leads if lead.high]
    right_scores = {round(lead.confidence, 12) for lead in leads if lead.outcome.correct}
    wrong_scores = {round(lead.confidence, 12) for lead in leads if not lead.outcome.correct}
    raw_right = {round(lead.outcome.raw_confidence, 12) for lead in leads if lead.outcome.correct}
    raw_wrong = {
        round(lead.outcome.raw_confidence, 12) for lead in leads if not lead.outcome.correct
    }
    return {
        "contentful": len(leads),
        "right": sum(1 for lead in leads if lead.outcome.correct),
        "high": len(high),
        "high_right": sum(1 for lead in high if lead.outcome.correct),
        "high_right_share": (
            None if not high else sum(1 for lead in high if lead.outcome.correct) / len(high)
        ),
        "shared_calibrated_scores": sorted(right_scores & wrong_scores),
        "shared_raw_scores": sorted(raw_right & raw_wrong),
        "right_calibrated_range": _range(right_scores),
        "wrong_calibrated_range": _range(wrong_scores),
    }


def _range(values: set[float]) -> list[float] | None:
    return None if not values else [min(values), max(values)]


def score_shaped(split: str) -> tuple[ShapedOutcome, ...]:
    """Every seed of ``split``: both scored loops, three scenarios, the lead and its shape.

    The scenarios are lane D's (ADR 0162), built the same way. A seed outside the split is
    refused before a plant is built.
    """
    found: list[ShapedOutcome] = []
    for seed in _seeds(split):
        found.extend(_score_seed(seed, split))
    return tuple(found)


def _score_seed(seed: int, split: str) -> tuple[ShapedOutcome, ...]:
    _require_seed(seed, split)
    found: list[ShapedOutcome] = []
    for loop in SCORED_LOOPS:
        description = _description(loop.plant_id)
        train = run_plant(loop.plant_id, _spec(champion_train_seed(), loop.sample_seconds))
        spec = _spec(seed, loop.sample_seconds)
        follow = run_plant(loop.plant_id, spec, commands=_source(description, loop))
        held = follow.steps[WRITE_AT - 1].report.values[loop.actuator]
        stuck = run_plant(
            loop.plant_id,
            spec,
            injection=HoldActuator(
                actuator=loop.actuator,
                value=held,
                window=TimeWindow(start=spec.instant(WRITE_AT), end=spec.instant(N_STEPS)),
            ),
            commands=_source(description, loop),
        )
        quiet = run_plant(loop.plant_id, spec)
        entities = _entities(description)
        entity_of = {entity.name: entity.id for entity in entities}
        scenarios = {
            "stuck": _physics(description, train, stuck, entity_of)
            + _mismatches(description, stuck, entity_of, train),
            "follow": _physics(description, train, follow, entity_of)
            + _mismatches(description, follow, entity_of, train),
            "quiet": _physics(description, train, quiet, entity_of),
        }
        for name, evidence in scenarios.items():
            found.append(_outcome(seed, loop.plant_id, name, evidence, entities))
    return tuple(found)


def _outcome(
    seed: int,
    plant_id: str,
    scenario: str,
    evidence: Sequence[Evidence],
    entities: Sequence[Entity],
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
        correct = scenario == "stuck" and lead.template_id == _CORRECT_LEAD
    return ShapedOutcome(
        seed=seed,
        plant_id=plant_id,
        scenario=scenario,
        lead=lead.template_id,
        raw_confidence=lead.confidence,
        shape=evidence_shape(supporting),
        contentful=contentful,
        correct=correct,
    )

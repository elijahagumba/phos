"""Whether an explanation's confidence may be shown as a probability (ADR 0162).

The number on a hypothesis is the belief update from the frozen priors and `EVIDENCE_STRENGTH`.
It is not, by itself, the chance that the explanation is right. This module scores the leads
the command-against-physics runs actually produce, draws a reliability chart, and refuses to
surface the number when that chart says it is not calibrated.

A stuck actuator should lead with ``sensor_or_device_fault``. A follow run, and a quiet run,
have nothing falsified: a contentful lead there is wrong. ``insufficient_evidence`` is silence,
not an explanation, and it is not in the chart. The rank stays ``(-confidence, template_id)``.
Nothing here retunes a matcher, a prior, or `EVIDENCE_STRENGTH`.

A Platt map is fit only as a diagnostic. If its outputs on the development pairs barely move,
it is the base rate of a mix this measurement chose, and it is not a probability to show.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta
from itertools import pairwise
from typing import Final

import numpy
from numpy.typing import NDArray

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
from phos.atlas.templates import SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID, atlas_library
from phos.eval.build_declaration import SCORECARD
from phos.ontology import Domain, Entity, Evidence, InMemoryEvidenceStore
from phos.reasoning import (
    INSUFFICIENT_EVIDENCE_TEMPLATE_ID,
    PlattCalibrator,
    ReasoningConfig,
    ReasoningEngine,
)
from phos.synth.injection import HoldActuator, TimeWindow
from phos.synth.run import run_plant

__all__ = [
    "BIN_EDGES",
    "FLAT_SPAN",
    "HIGH_CONFIDENCE",
    "CalibrationReport",
    "ExplanationOutcome",
    "ReliabilityBin",
    "expected_calibration_error",
    "map_is_flat",
    "reliability_bins",
    "reliability_svg",
    "score_calibration",
    "scorecard_numbers",
]

logger = logging.getLogger(__name__)

HIGH_CONFIDENCE: Final = 0.8
"""A probability we would call high. Raw hypothesis confidence is not this probability."""

FLAT_SPAN: Final = 0.05
"""A fitted map whose outputs move by less than this is a base rate, not a ranking."""

BIN_EDGES: Final[tuple[float, ...]] = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0000001)
"""Reliability bins on raw confidence. The last edge includes 1."""

_CORRECT_LEAD: Final = SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID


@dataclass(frozen=True)
class ExplanationOutcome:
    """One scenario's lead, and whether that lead was the right explanation.

    Attributes:
        seed: The plant seed.
        plant_id: Which synthetic plant.
        scenario: ``stuck``, ``follow``, or ``quiet``.
        lead: The template at the front of ``competing``.
        confidence: That template's confidence. Not a user-facing probability.
        contentful: Whether the lead is an explanation other than the residual.
        correct: Whether a contentful lead is the right one. ``None`` for silence.
        n_evidence: How many facts were ingested.
    """

    seed: int
    plant_id: str
    scenario: str
    lead: str
    confidence: float
    contentful: bool
    correct: bool | None
    n_evidence: int

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-ready copy."""
        return {
            "seed": self.seed,
            "plant_id": self.plant_id,
            "scenario": self.scenario,
            "lead": self.lead,
            "confidence": self.confidence,
            "contentful": self.contentful,
            "correct": self.correct,
            "n_evidence": self.n_evidence,
        }


@dataclass(frozen=True)
class ReliabilityBin:
    """One bar of the reliability chart."""

    low: float
    high: float
    count: int
    correct: int
    mean_confidence: float | None
    observed: float | None

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-ready copy."""
        return {
            "low": self.low,
            "high": self.high,
            "count": self.count,
            "correct": self.correct,
            "mean_confidence": self.mean_confidence,
            "observed": self.observed,
        }


@dataclass(frozen=True)
class CalibrationReport:
    """The chart, the refused map, and the decision not to surface a probability."""

    split: str
    outcomes: tuple[ExplanationOutcome, ...]
    bins: tuple[ReliabilityBin, ...]
    expected_calibration_error: float | None
    platt_coefficient: float | None
    platt_intercept: float | None
    platt_low: float | None
    platt_high: float | None
    map_flat: bool
    surfaced: bool
    raw_high_confidence: int
    contentful: int
    contentful_correct: int

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-ready copy. Confidences here are not for a user to read as chances."""
        return {
            "split": self.split,
            "surfaced": self.surfaced,
            "user_facing_probability": None,
            "raw_high_confidence": self.raw_high_confidence,
            "contentful": self.contentful,
            "contentful_correct": self.contentful_correct,
            "expected_calibration_error": self.expected_calibration_error,
            "platt_coefficient": self.platt_coefficient,
            "platt_intercept": self.platt_intercept,
            "platt_low": self.platt_low,
            "platt_high": self.platt_high,
            "map_flat": self.map_flat,
            "bins": [item.as_dict() for item in self.bins],
            "outcomes": [item.as_dict() for item in self.outcomes],
            "note": (
                "Hypothesis confidence is not shown as a probability. A flat Platt map repeats "
                "the base rate of this scenario mix, and that mix is one this measurement chose."
            ),
        }


def reliability_bins(
    outcomes: Sequence[ExplanationOutcome],
    edges: Sequence[float] = BIN_EDGES,
) -> tuple[ReliabilityBin, ...]:
    """Bin contentful leads by raw confidence and record how often the lead was right.

    Silence is left out. An empty bin is kept, so the chart shows where nothing landed.
    """
    contentful = [item for item in outcomes if item.contentful and item.correct is not None]
    bins: list[ReliabilityBin] = []
    for low, high in pairwise(edges):
        members = [item for item in contentful if low <= item.confidence < high]
        if not members:
            bins.append(ReliabilityBin(low, high, 0, 0, None, None))
            continue
        correct = sum(1 for item in members if item.correct)
        mean = sum(item.confidence for item in members) / len(members)
        bins.append(
            ReliabilityBin(
                low=low,
                high=high,
                count=len(members),
                correct=correct,
                mean_confidence=mean,
                observed=correct / len(members),
            )
        )
    return tuple(bins)


def expected_calibration_error(bins: Sequence[ReliabilityBin]) -> float | None:
    """Mean absolute gap between raw confidence and the observed frequency, weighted by count."""
    total = sum(item.count for item in bins)
    if total == 0:
        return None
    gap = 0.0
    for item in bins:
        if item.mean_confidence is None or item.observed is None:
            continue
        gap += item.count * abs(item.observed - item.mean_confidence)
    return gap / total


def map_is_flat(probabilities: Sequence[float], *, span: float = FLAT_SPAN) -> bool:
    """A map that barely moves is a constant, whatever the constant is.

    Raises:
        ValueError: If ``span`` is not positive.
    """
    if span <= 0.0:
        raise ValueError(f"span must be positive, got {span}")
    if not probabilities:
        return True
    return max(probabilities) - min(probabilities) < span


def reliability_svg(bins: Sequence[ReliabilityBin]) -> str:
    """A reliability diagram: raw confidence against how often that lead was right.

    The diagonal is what a calibrated probability would do. Points off it are the gap.
    """
    width, height = 640, 420
    left, right, top, bottom = 56, 600, 36, 360
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        (
            '<text x="56" y="24">'
            "Raw explanation confidence against how often the lead was right"
            "</text>"
        ),
        f'<line x1="{left}" y1="{bottom}" x2="{right}" y2="{top}" stroke="#bbbbbb"/>',
    ]
    for item in bins:
        if item.count == 0 or item.mean_confidence is None or item.observed is None:
            continue
        x = left + (right - left) * item.mean_confidence
        y = bottom - (bottom - top) * item.observed
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="#1f4e79"/>')
        parts.append(
            f'<text x="{x + 8:.1f}" y="{y:.1f}">n={item.count} observed={item.observed:.3f}</text>'
        )
    parts.append('<text x="56" y="400">Diagonal: a probability that matched the frequency.</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def score_calibration(split: str, *, fit_platt: bool = True) -> CalibrationReport:
    """Score every seed of ``split`` and decide that the confidence is not shown.

    The Platt map is fit on development pairs only. A held-back call passes ``fit_platt=False``
    so those labels do not train a map and cannot unlock surfacing.

    Raises:
        ValueError: If ``split`` is not a build split.
    """
    _seeds(split)
    outcomes: list[ExplanationOutcome] = []
    for seed in _seeds(split):
        outcomes.extend(_score_seed(seed, split))
    return _report(split, tuple(outcomes), fit_platt=fit_platt)


def scorecard_numbers(report: CalibrationReport) -> dict[str, float | None]:
    """Leave ``calibration`` unset. The confidence is not a user-facing probability."""
    numbers: dict[str, float | None] = dict.fromkeys(SCORECARD)
    if report.surfaced:
        logger.error("surfacing was requested; this lane's rule leaves calibration unset")
    return numbers


def _report(
    split: str, outcomes: tuple[ExplanationOutcome, ...], *, fit_platt: bool = True
) -> CalibrationReport:
    """Chart the outcomes and reject a flat map. ``fit_platt`` false leaves the map unset."""
    bins = reliability_bins(outcomes)
    contentful = [item for item in outcomes if item.contentful and item.correct is not None]
    if fit_platt:
        coefficient, intercept, low, high, flat = _platt(contentful)
    else:
        coefficient, intercept, low, high, flat = None, None, None, None, True
    raw_high = sum(1 for item in contentful if item.confidence >= HIGH_CONFIDENCE)
    surfaced = False
    if raw_high or not flat:
        logger.info(
            "explanation confidence stays unsurfaced: raw_high=%d map_flat=%s",
            raw_high,
            flat,
        )
    return CalibrationReport(
        split=split,
        outcomes=outcomes,
        bins=bins,
        expected_calibration_error=expected_calibration_error(bins),
        platt_coefficient=coefficient,
        platt_intercept=intercept,
        platt_low=low,
        platt_high=high,
        map_flat=flat,
        surfaced=surfaced,
        raw_high_confidence=raw_high,
        contentful=len(contentful),
        contentful_correct=sum(1 for item in contentful if item.correct),
    )


def _platt(
    contentful: Sequence[ExplanationOutcome],
) -> tuple[float | None, float | None, float | None, float | None, bool]:
    """Fit Platt on the contentful pairs. A single class, or a flat map, is rejected."""
    if not contentful:
        return None, None, None, None, True
    scores: NDArray[numpy.float64] = numpy.array(
        [item.confidence for item in contentful], dtype=numpy.float64
    )
    labels: NDArray[numpy.float64] = numpy.array(
        [1.0 if item.correct else 0.0 for item in contentful], dtype=numpy.float64
    )
    try:
        fitted = PlattCalibrator().fit(scores, labels)
    except ValueError:
        logger.info("explanation calibrator refused: the pairs are a single class")
        return None, None, None, None, True
    calibrated = fitted.calibrate(scores)
    low = float(numpy.min(calibrated))
    high = float(numpy.max(calibrated))
    return fitted.coefficient, fitted.intercept, low, high, map_is_flat((low, high))


def _score_seed(seed: int, split: str) -> tuple[ExplanationOutcome, ...]:
    """Both scored plants, three scenarios. The seed is refused before a plant is built."""
    _require_seed(seed, split)
    found: list[ExplanationOutcome] = []
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
) -> ExplanationOutcome:
    """The lead after ingesting ``evidence``, ranked by the engine's own order."""
    store = InMemoryEvidenceStore()
    for entity in entities:
        store.add_entity(entity)
    engine = ReasoningEngine(
        atlas_library(),
        store,
        ReasoningConfig(correlation_window=timedelta(hours=2)),
    )
    if evidence:
        engine.ingest(evidence)
    lead = engine.competing(Domain.ATLAS)[0]
    contentful = lead.template_id != INSUFFICIENT_EVIDENCE_TEMPLATE_ID
    correct: bool | None = None
    if contentful:
        correct = scenario == "stuck" and lead.template_id == _CORRECT_LEAD
    return ExplanationOutcome(
        seed=seed,
        plant_id=plant_id,
        scenario=scenario,
        lead=lead.template_id,
        confidence=lead.confidence,
        contentful=contentful,
        correct=correct,
        n_evidence=len(evidence),
    )

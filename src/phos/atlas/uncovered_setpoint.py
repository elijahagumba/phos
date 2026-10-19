"""A setpoint the open work order does not name (Lane R, H2).

The fact is not a graph finding. Known-link matchers are not consulted. The weight is the
same half-weight W5 uses for a cross-signal fact, not a weight chosen to force a lead.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime

import numpy
from numpy.typing import NDArray

from phos.atlas.origin_evidence import ORIGIN_WEIGHT
from phos.atlas.templates import UNCOVERED_SETPOINT
from phos.atlas.work_orders import work_order_feature_of
from phos.ontology import (
    Deviation,
    Domain,
    EntityId,
    Evidence,
    ExpectedRange,
    FacetKind,
    Observation,
)
from phos.reasoning import calibrated_probabilities, evidence_from_deviation
from phos.synth.plant import PlantDescription, SignalKind
from phos.synth.run import PlantRun

__all__ = ["uncovered_setpoint_evidence"]

_Float = NDArray[numpy.float64]


def uncovered_setpoint_evidence(
    description: PlantDescription,
    train_values: _Float,
    run: PlantRun,
    entity_of: Mapping[str, EntityId],
    work_orders: Sequence[Evidence],
    learned_from_window: tuple[datetime, datetime],
    domain: Domain = Domain.ATLAS,
    *,
    widen_by_range: bool = False,
) -> tuple[Evidence, ...]:
    """One fact per setpoint that leaves the quiet-train band while a work order is open.

    A work order covers a setpoint only when the setpoint's entity is one of the work order's
    entities. No work order means no fact: a setpoint move with no order is not this hypothesis.
    ``widen_by_range`` expands the band by its own width, so a step inside the plant's own
    variation does not count and a move beyond that variation does.

    Raises:
        ValueError: If the training matrix does not have one column per signal.
    """
    keys = [spec.key for spec in description.signals]
    if train_values.ndim != 2 or train_values.shape[1] != len(keys):
        raise ValueError(
            f"training values have shape {train_values.shape}; expected (*, {len(keys)})"
        )
    if not any(work_order_feature_of(fact) is not None for fact in work_orders):
        return ()
    covered = {
        entity_id
        for fact in work_orders
        if work_order_feature_of(fact) is not None
        for entity_id in fact.entity_ids
    }
    weight = calibrated_probabilities(ORIGIN_WEIGHT, [1.0])[0]
    found: list[Evidence] = []
    for index, spec in enumerate(description.signals):
        if spec.kind is not SignalKind.SETPOINT:
            continue
        entity = entity_of.get(spec.key)
        if entity is None or entity in covered:
            continue
        low = float(numpy.min(train_values[:, index]))
        high = float(numpy.max(train_values[:, index]))
        if widen_by_range:
            width = high - low
            low, high = low - width, high + width
        for step in run.steps:
            value = float(step.report.values[spec.key])
            if low <= value <= high:
                continue
            found.append(
                _fact(
                    spec.key,
                    entity,
                    value,
                    low,
                    high,
                    step.timestamp,
                    learned_from_window,
                    weight,
                    domain,
                )
            )
            break
    return tuple(found)


def _fact(
    signal: str,
    entity: EntityId,
    value: float,
    low: float,
    high: float,
    timestamp: datetime,
    learned_from_window: tuple[datetime, datetime],
    weight: float,
    domain: Domain,
) -> Evidence:
    observation = Observation(
        entity_ids=[entity],
        feature=signal,
        value=value,
        timestamp=timestamp,
        domain=domain,
    )
    deviation = Deviation(
        observation_id=observation.id,
        expected=ExpectedRange(
            feature=signal,
            entity_id=entity,
            low=low,
            high=high,
            mean=(low + high) / 2.0,
            stddev=0.0,
            learned_from_window=learned_from_window,
        ),
        magnitude=abs(value - (low + high) / 2.0),
        timestamp=timestamp,
    )
    return evidence_from_deviation(
        deviation,
        observation,
        weight,
        summary=(
            f"{signal} read {value:.6g}, outside the quiet-train envelope "
            f"[{low:.6g}, {high:.6g}]; the work order does not name it"
        ),
        facet=(FacetKind.UNCOVERED_SETPOINT, UNCOVERED_SETPOINT),
    )

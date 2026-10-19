"""One cross-signal fact per plant-map origin (ADR 0172), beside the facts already promoted.

`promote_consistency` keeps the loop-carried alert cell of each event. A held sensor can sit
inside that event and still not be the cell that is promoted, so the sensor-fault explanation
never names it. This module asks `rank_root_causes` which signals are origins at those cells
and adds one `cross_signal_mismatch` fact per origin signal the promoter did not already name.
It does not add, drop, or reorder the champion's alerts, and it does not edit a prior.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from datetime import datetime

import numpy
from numpy.typing import NDArray

from phos.atlas.consistency import (
    THRESHOLD,
    ConsistencyModel,
    events,
    feature_components,
    feature_scores,
)
from phos.atlas.consistency_evidence import CROSS_SIGNAL_MISMATCH
from phos.atlas.plant_map_model import Form, PlantMap, residuals
from phos.atlas.plant_map_naming import _pad
from phos.atlas.root_cause import RootCause, Tier, rank_root_causes
from phos.ontology import (
    Deviation,
    Domain,
    EntityId,
    Evidence,
    ExpectedRange,
    FacetKind,
    Observation,
)
from phos.reasoning import FittedPlattCalibrator, calibrated_probabilities, evidence_from_deviation

__all__ = [
    "ORIGIN_WEIGHT",
    "loud_member_names",
    "member_evidence",
    "origin_evidence",
    "origin_signals",
    "promoted_cells",
]

ORIGIN_WEIGHT = FittedPlattCalibrator(coefficient=0.0, intercept=0.0)
"""The W5 weight. The coefficient is zero, so every score maps to one half."""

_Float = NDArray[numpy.float64]


def loud_member_names(
    scored: Sequence[tuple[str, float]], already_named: frozenset[str]
) -> tuple[str, ...]:
    """Names whose own-model score is above 1, skipping names already cited, in given order.

    The threshold is the plant map's in-band line (`own <= 1` is in band). Inherited signals
    are kept: a joint hold makes each sensor a driver of the other, so the origin tier names
    neither.
    """
    found: list[str] = []
    for name, own in scored:
        if own > 1.0 and name not in already_named and name not in found:
            found.append(name)
    return tuple(found)


def origin_signals(ranked: Sequence[RootCause]) -> tuple[str, ...]:
    """Return origin signal names from a root-cause ranking, first occurrence, in rank order.

    Inherited and in-band candidates are omitted. A signal ranked as an origin twice is named once.
    """
    found: list[str] = []
    for item in ranked:
        if item.tier is Tier.ORIGIN and item.signal not in found:
            found.append(item.signal)
    return tuple(found)


def promoted_cells(model: ConsistencyModel, values: _Float) -> tuple[tuple[int, int], ...]:
    """Return ``(row, column)`` for each loop-carried consistency event, in onset order.

    This is the same gate `promote_consistency` uses. A cell that fails it is not an origin
    site for this module, because no alert was raised there.
    """
    loop, rng = feature_components(model, values)
    found: list[tuple[int, int]] = []
    for event in events(feature_scores(model, values), windows=model.windows):
        row, column = event.onset, event.column
        loop_score = float(loop[row, column])
        if loop_score > THRESHOLD and loop_score >= float(rng[row, column]):
            found.append((int(row), int(column)))
    return tuple(found)


def origin_evidence(
    plant_map: PlantMap,
    consistency: ConsistencyModel,
    values: _Float,
    timestamps: Sequence[datetime],
    entity_of: Mapping[str, EntityId],
    learned_from_window: tuple[datetime, datetime],
    already_named: frozenset[str],
    domain: Domain = Domain.ATLAS,
) -> tuple[Evidence, ...]:
    """One fact per origin signal that ``already_named`` does not already carry.

    Args:
        plant_map: Fitted on attack-free rows, the same signal order as ``values``.
        consistency: The detector whose loop-carried cells choose where origins are read.
        values: The scored run, rows by signals.
        timestamps: One UTC timestamp per row.
        entity_of: Entity id for each signal name.
        learned_from_window: Training window stored on each expected range.
        already_named: Signal names the existing cross-signal facts already cite.
        domain: Domain of the observations.

    Returns:
        Facts in first-seen order. Empty when every origin is already named.

    Raises:
        ValueError: If a row is missing a timestamp, or an origin signal has no entity.
    """
    if values.shape[0] != len(timestamps):
        raise ValueError(f"{values.shape[0]} rows but {len(timestamps)} timestamps")
    weight = calibrated_probabilities(ORIGIN_WEIGHT, [1.0])[0]
    chosen: list[tuple[int, int, float]] = []
    seen = set(already_named)
    for row, column in promoted_cells(consistency, values):
        for item in rank_root_causes(plant_map, values, row, column):
            if item.tier is not Tier.ORIGIN or item.signal in seen:
                continue
            seen.add(item.signal)
            chosen.append((row, item.column, item.own))
    return tuple(
        _fact(
            plant_map,
            values,
            timestamps,
            entity_of,
            learned_from_window,
            row,
            column,
            own,
            weight,
            domain,
        )
        for row, column, own in chosen
    )


def member_evidence(
    plant_map: PlantMap,
    consistency: ConsistencyModel,
    values: _Float,
    timestamps: Sequence[datetime],
    entity_of: Mapping[str, EntityId],
    learned_from_window: tuple[datetime, datetime],
    already_named: frozenset[str],
    domain: Domain = Domain.ATLAS,
) -> tuple[Evidence, ...]:
    """One fact per event member whose own-model score is above 1.

    Inherited members are included. H1's origin tier does not name both held sensors, because
    each is a driver of the other on this map. A signal already in ``already_named`` is skipped.

    Raises:
        ValueError: If the row count disagrees with ``timestamps``, or a signal has no entity.
    """
    if values.shape[0] != len(timestamps):
        raise ValueError(f"{values.shape[0]} rows but {len(timestamps)} timestamps")
    best: dict[int, tuple[float, int]] = {}
    for event in events(feature_scores(consistency, values), windows=consistency.windows):
        for member in event.members:
            peak_row, column = int(member[3]), int(member[4])
            if column not in plant_map.targets:
                continue
            ranked = rank_root_causes(plant_map, values, peak_row, column)
            own = next(item.own for item in ranked if item.column == column)
            previous = best.get(column)
            if previous is None or own > previous[0]:
                best[column] = (own, peak_row)
    scored = [(plant_map.names[column], own) for column, (own, _row) in best.items()]
    chosen = loud_member_names(scored, already_named)
    weight = calibrated_probabilities(ORIGIN_WEIGHT, [1.0])[0]
    by_name = {plant_map.names[column]: (own, row, column) for column, (own, row) in best.items()}
    return tuple(
        _fact(
            plant_map,
            values,
            timestamps,
            entity_of,
            learned_from_window,
            by_name[name][1],
            by_name[name][2],
            by_name[name][0],
            weight,
            domain,
        )
        for name in chosen
    )


def _fact(
    plant_map: PlantMap,
    values: _Float,
    timestamps: Sequence[datetime],
    entity_of: Mapping[str, EntityId],
    learned_from_window: tuple[datetime, datetime],
    row: int,
    column: int,
    own: float,
    weight: float,
    domain: Domain,
) -> Evidence:
    signal = plant_map.names[column]
    entity = entity_of.get(signal)
    if entity is None:
        raise ValueError(f"signal {signal!r} has no entity in entity_of")
    value = float(values[row, column])
    low, high, centre = _band(plant_map, values, row, column, value)
    observation = Observation(
        entity_ids=[entity],
        feature=signal,
        value=value,
        timestamp=timestamps[row],
        domain=domain,
    )
    deviation = Deviation(
        observation_id=observation.id,
        expected=ExpectedRange(
            feature=signal,
            entity_id=entity,
            low=low,
            high=high,
            mean=float(plant_map.mean[column]),
            stddev=float(plant_map.spread[column]),
            learned_from_window=learned_from_window,
        ),
        magnitude=own,
        timestamp=timestamps[row],
    )
    return evidence_from_deviation(
        deviation,
        observation,
        weight,
        summary=(
            f"{signal} is a plant-map origin (own score {own:.6g}); "
            f"the map implies about {centre:.6g}"
        ),
        facet=(FacetKind.CONSISTENCY, CROSS_SIGNAL_MISMATCH),
    )


def _band(
    plant_map: PlantMap, values: _Float, row: int, column: int, value: float
) -> tuple[float, float, float]:
    """Return ``(low, high, centre)`` that leaves ``value`` outside the band.

    A level model uses its prediction and its band, scaled back into engineering units. Any other
    form, or a band the value still touches, shifts the near edge off the value so the fact is a
    departure the boundary will accept. The magnitude stored on the deviation remains the map's
    own score.
    """
    target = plant_map.targets.get(column)
    spread = float(plant_map.spread[column])
    mean = float(plant_map.mean[column])
    if target is not None and target.form is Form.LEVEL:
        z = (values - plant_map.mean) / plant_map.spread
        start = max(0, row - _pad(plant_map))
        window = residuals(
            target.form, target.equation, z[start : row + 1], column, plant_map.horizons
        )
        residual = window[row - start]
        scaled = numpy.abs(residual) / target.equation.bands
        if numpy.any(numpy.isfinite(scaled)):
            deciding = int(numpy.nanargmax(scaled))
            residual_z = float(residual[deciding])
            if math.isfinite(residual_z):
                z_value = float(z[row, column])
                centre = mean + (z_value - residual_z) * spread
                half = abs(float(target.equation.bands[deciding])) * spread
                low, high = centre - half, centre + half
                if not low <= value <= high and low <= high:
                    return low, high, centre
    return _exclude(value, mean, spread)


def _exclude(value: float, mean: float, spread: float) -> tuple[float, float, float]:
    """A band of width ``spread`` that does not contain ``value``."""
    half = max(abs(spread), 1e-6)
    gap = max(abs(value) * 1e-9, 1e-9)
    if value >= mean:
        high = value - gap
        low = high - 2.0 * half
    else:
        low = value + gap
        high = low + 2.0 * half
    return low, high, (low + high) / 2.0

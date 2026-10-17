"""The plant-map challenger's events become evidence (ADR 0123 §5, "The fact").

`phos.atlas.consistency_evidence` promotes the champion's loop-carried events. This module does
the same for `atlas-plant-map-v1`, through the same door (`phos.reasoning.boundary`) and with the
same facet, (`CONSISTENCY`, `CROSS_SIGNAL_MISMATCH`), so the template routing does not move.

**One fact per event.** A **map-carried** event (`phos.atlas.plant_map_detector.map_carried`) is
named by `phos.atlas.plant_map_naming`:

- **A named instrument:** the observation is its reading at the alert row, and the expected range
  is its reconstruction from its own drivers, with the reconstruction's band.
- **Not separable, or unnamed:** the observation is the event's own signal, reconstructed the
  same way, and the context says no single instrument could be named.
- **Reading true, plant changed** (§5.3): not promoted, because this facet routes to an
  instrument fault and against a real upset. It is kept in the event records.

Where the map cannot reconstruct (no anchor, a band past the calibrated free run, or a reading
inside the band), the event falls back to the loop's fact if the loop carries it. An event the
map does not carry is promoted as the champion promotes it, naming no link. Every event gets a
record, promoted or not, for the development slices' naming and reconstruction measures.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

import numpy
from numpy.typing import NDArray

from phos.atlas.consistency import THRESHOLD, loop_expectation
from phos.atlas.consistency_evidence import (
    EXPECTED_VALUE_CONTEXT_KEY,
    ConsistencyEvidence,
    facts_from,
    loop_fact_parts,
)
from phos.atlas.plant_map_detector import (
    PlantMapDetector,
    detector_components,
    detector_events,
    map_carried,
)
from phos.atlas.plant_map_naming import (
    InstrumentCheck,
    Naming,
    Reconstruction,
    Verdict,
    name_instrument,
    reconstruct,
)
from phos.ontology import Deviation, Domain, EntityId, ExpectedRange, Observation
from phos.reasoning import FittedCalibrator, is_out_of_band

__all__ = [
    "BROKEN_LINK_CONTEXT_KEY",
    "INSTRUMENT_CHECKS_CONTEXT_KEY",
    "INSTRUMENT_CONTEXT_KEY",
    "RECONSTRUCTION_ANCHOR_CONTEXT_KEY",
    "MapEventRecord",
    "PlantMapPromotion",
    "promote_plant_map",
]

logger = logging.getLogger(__name__)

BROKEN_LINK_CONTEXT_KEY: Final = "broken_link"
INSTRUMENT_CONTEXT_KEY: Final = "instrument"
INSTRUMENT_CHECKS_CONTEXT_KEY: Final = "instrument_checks"
RECONSTRUCTION_ANCHOR_CONTEXT_KEY: Final = "reconstruction_anchor"

_Float = NDArray[numpy.float64]


@dataclass(frozen=True)
class MapEventRecord:
    """What happened to one challenger event.

    Attributes:
        onset: The alert row.
        column: The alert signal.
        first_onset: The row the event's first member began.
        carried_by: ``"map"``, ``"loop"`` or ``"range"``.
        promoted: ``"map"``, ``"loop"`` or ``None``.
        naming: The map's naming, for a map-carried event.
        reconstruction: The reconstruction the map fact used, if any.
    """

    onset: int
    column: int
    first_onset: int
    carried_by: str
    promoted: str | None
    naming: Naming | None
    reconstruction: Reconstruction | None


@dataclass(frozen=True)
class PlantMapPromotion:
    """The promoted facts and one record per event, in onset order."""

    evidence: ConsistencyEvidence
    records: tuple[MapEventRecord, ...]


def _carrier(loop: float, rng: float, carried: bool) -> str:
    if carried:
        return "map"
    return "loop" if loop > THRESHOLD and loop >= rng else "range"


def _checks_in_words(names: Sequence[str], check: InstrumentCheck | None) -> str:
    if check is None:
        return "no check"
    name = names[check.candidate]
    parts = [
        f"{name} {'disagrees' if check.disagrees_with_drivers else 'does not disagree'} with its "
        "drivers",
        f"its drivers are {'in band' if check.drivers_in_band else 'not all in band'}",
    ]
    if check.downstream_checked:
        parts.append(
            f"{check.downstream_agree_with_reconstruction} of {len(check.downstream)} downstream "
            "signal(s) agree with the reconstruction and not the reading"
        )
    else:
        parts.append("no downstream check was possible")
    if check.inconclusive:
        parts.append(
            "without " + ", ".join(names[d] for d in check.inconclusive) + " it could not tell"
        )
    return "; ".join(parts)


def _instrument_text(names: Sequence[str], naming: Naming) -> str:
    if naming.verdict is Verdict.NAMED and naming.instrument is not None:
        return names[naming.instrument]
    if naming.verdict is Verdict.NOT_SEPARABLE:
        passing = [names[c.candidate] for c in naming.checks if c.passes]
        return "not separable: " + ", ".join(passing)
    return "unnamed"


def _broken_text(detector: PlantMapDetector, naming: Naming) -> str:
    plant = detector.plant
    target = plant.targets[naming.column]
    links = []
    for link in target.links:
        if link.driver in naming.broken_links:
            lags = " and ".join(f"{round(lag * plant.period_seconds)} s" for lag in link.lags)
            links.append(
                f"{plant.names[link.driver]} -> {plant.names[naming.column]}, "
                f"{target.form.value} form, {lags}"
            )
    return "; ".join(links) if links else "none"


def _map_parts(
    detector: PlantMapDetector,
    values: _Float,
    timestamps: Sequence[datetime],
    entity_of: Mapping[str, EntityId],
    naming: Naming,
    rebuilt: Reconstruction,
    magnitude: float,
    learned_from_window: tuple[datetime, datetime],
    domain: Domain,
) -> tuple[Observation, Deviation] | None:
    plant = detector.plant
    row, column = naming.row, rebuilt.column
    centre = float(rebuilt.centre[-1])
    half = float(rebuilt.half_width[-1])
    if not (math.isfinite(centre) and math.isfinite(half)) or bool(rebuilt.too_uncertain[-1]):
        return None
    feature = plant.names[column]
    entity = entity_of.get(feature)
    if entity is None:
        raise ValueError(f"signal {feature!r} has no entity in entity_of")
    check = next((c for c in naming.checks if c.candidate == column), None)
    anchor = "level form" if rebuilt.anchor is None else timestamps[rebuilt.anchor].isoformat()
    observation = Observation(
        entity_ids=[entity],
        feature=feature,
        value=float(values[row, column]),
        timestamp=timestamps[row],
        domain=domain,
        context={
            EXPECTED_VALUE_CONTEXT_KEY: f"{centre:.6g}",
            BROKEN_LINK_CONTEXT_KEY: _broken_text(detector, naming),
            INSTRUMENT_CONTEXT_KEY: _instrument_text(plant.names, naming),
            INSTRUMENT_CHECKS_CONTEXT_KEY: _checks_in_words(plant.names, check),
            RECONSTRUCTION_ANCHOR_CONTEXT_KEY: anchor,
        },
    )
    deviation = Deviation(
        observation_id=observation.id,
        expected=ExpectedRange(
            feature=feature,
            entity_id=entity,
            low=centre - half,
            high=centre + half,
            mean=float(plant.mean[column]),
            stddev=float(plant.spread[column]),
            learned_from_window=learned_from_window,
        ),
        magnitude=magnitude,
        timestamp=timestamps[row],
    )
    if not is_out_of_band(deviation, observation):
        return None
    return observation, deviation


def _describe(observation: Observation, deviation: Deviation) -> str:
    """The sentence an operator reads (ADR 0123 §5)."""
    expected = deviation.expected
    centre = (expected.low + expected.high) / 2.0
    context = observation.context
    sentence = (
        f"{observation.feature} read {observation.value:.6g}; its drivers imply about "
        f"{centre:.6g} (consistent between {expected.low:.6g} and {expected.high:.6g})"
    )
    if INSTRUMENT_CONTEXT_KEY not in context:
        return sentence.replace("its drivers imply", "the rest of the plant implies")
    broken = context.get(BROKEN_LINK_CONTEXT_KEY, "none")
    if broken != "none":
        sentence += f". Broken link: {broken}"
    instrument = context[INSTRUMENT_CONTEXT_KEY]
    if instrument == observation.feature:
        sentence += f". {context[INSTRUMENT_CHECKS_CONTEXT_KEY]}"
    else:
        sentence += f". Instrument: {instrument}"
    return sentence


def promote_plant_map(
    detector: PlantMapDetector,
    values: _Float,
    timestamps: Sequence[datetime],
    features: Sequence[str],
    entity_of: Mapping[str, EntityId],
    calibrator: FittedCalibrator,
    learned_from_window: tuple[datetime, datetime],
    domain: Domain = Domain.ATLAS,
) -> PlantMapPromotion:
    """Score one file with the challenger and promote one fact per promotable event.

    Args:
        detector: A fitted challenger, fitted on data this file is not part of.
        values: The file's readings, rows by signals, in ``features`` order.
        timestamps: One UTC timestamp per row.
        features: The signal names, the map's own order.
        entity_of: The entity each signal belongs to.
        calibrator: Supplies each fact's weight from its magnitude.
        learned_from_window: ``(start, end)`` of the training data.
        domain: The domain the observations belong to.

    Raises:
        ValueError: If the shapes or names disagree, or a promoted signal has no entity.
    """
    if tuple(features) != detector.plant.names:
        raise ValueError("features must be the map's signals, in its order")
    if values.shape != (len(timestamps), len(features)):
        raise ValueError(f"values have shape {values.shape}; expected rows by features")
    parts = detector_components(detector, values)
    expectation = loop_expectation(detector.consistency, values)
    pending: list[tuple[Observation, Deviation]] = []
    records: list[MapEventRecord] = []
    for event in detector_events(detector, values):
        row, column = event.onset, event.column
        first = min(member[0] for member in event.members)
        carried = map_carried(parts, event)
        loop = float(parts.loop[row, column])
        rng = float(parts.rng[row, column])
        naming: Naming | None = None
        rebuilt: Reconstruction | None = None
        promoted: str | None = None
        fact: tuple[Observation, Deviation] | None = None
        if carried:
            naming = name_instrument(
                detector.plant,
                values,
                row=row,
                column=column,
                onset=first,
                rules=detector.plant.settings.naming_rules,
            )
            if naming.verdict is not Verdict.PLANT_CHANGED:
                subject = naming.instrument if naming.instrument is not None else column
                rebuilt = naming.reconstruction or reconstruct(
                    detector.plant, values, subject, first, row
                )
                if rebuilt is not None:
                    fact = _map_parts(
                        detector,
                        values,
                        timestamps,
                        entity_of,
                        naming,
                        rebuilt,
                        float(parts.map[row, column]),
                        learned_from_window,
                        domain,
                    )
                    promoted = "map" if fact is not None else None
        plant_changed = naming is not None and naming.verdict is Verdict.PLANT_CHANGED
        if fact is None and not plant_changed and loop > THRESHOLD and loop >= rng:
            fact = loop_fact_parts(
                detector.consistency,
                values,
                timestamps,
                features,
                entity_of,
                expectation,
                (row, column, loop),
                learned_from_window,
                domain,
            )
            promoted = "loop" if fact is not None else None
        if fact is not None:
            pending.append(fact)
        records.append(
            MapEventRecord(
                onset=row,
                column=column,
                first_onset=first,
                carried_by=_carrier(loop, rng, carried),
                promoted=promoted,
                naming=naming,
                reconstruction=rebuilt,
            )
        )
    facts = facts_from(pending, calibrator, _describe)
    logger.info("promoted %d of %d challenger event(s) into evidence", len(facts), len(records))
    return PlantMapPromotion(ConsistencyEvidence(facts=facts), tuple(records))

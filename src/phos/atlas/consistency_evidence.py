"""Where "this reading disagrees with the rest of the plant" becomes evidence Atlas can weigh.

`phos.atlas.consistency` decides *that* something departed. This module turns its strongest kind
of departure into the same object every other Atlas fact is: an `Observation`, a `Deviation`
against an `ExpectedRange`, and `Evidence` promoted through `phos.reasoning.boundary`, the only
sanctioned door into reasoning (Constitution §3.1). It builds no `Evidence` itself.

**One fact per event, and only when the loop carries it.** The detector groups departures into
events and places each event's alert at one ``(row, signal)``. That cell becomes evidence only
when its calibrated *loop* score is above `phos.atlas.consistency.THRESHOLD` and at least its range
score: the reading disagrees with what every other signal, now and over the last minute, implies.
A reading that merely left its training range is a different fact and is not promoted here.

**The facet says which fact it is.** `FacetKind.CONSISTENCY` with `CROSS_SIGNAL_MISMATCH`. Its
sibling `COMMAND_TO_RESPONSE_MISMATCH` is emitted by `phos.atlas.command_response` from a plant's
declared `CONTROL` couplings (ADR 0160). It is not inferred from co-movement: that is the
circularity `phos.atlas.topology` refuses, and this module still does not invent a pairing.

**The expected range is the plant's own account of the reading.** Its centre is the regression's
prediction — what the rest of the plant implies the value is, which for a falsified instrument is a
reconstruction of the real value — and its half-width is exactly where the calibrated loop score
reaches the threshold (`phos.atlas.consistency.loop_expectation`). So the stored `Deviation` says
both that the reading left the band and what the band was at that instant. The predicted value
also travels in the observation's ``context`` and in the summary an operator reads.

**What this fact supports is argued in `phos.atlas.templates`** (ADR 0108): an instrument or device
that has failed, and not a real process upset. A falsified reading and a failed transmitter leave
the same fact; telling them apart needs other evidence, such as who commanded what.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from typing import Final

import numpy
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict

from phos.atlas.consistency import (
    THRESHOLD,
    ConsistencyModel,
    events,
    feature_components,
    feature_scores,
    loop_expectation,
)
from phos.ontology import (
    Deviation,
    Domain,
    EntityId,
    Evidence,
    ExpectedRange,
    FacetKind,
    Observation,
)
from phos.reasoning import (
    FittedCalibrator,
    calibrated_probabilities,
    evidence_from_deviation,
    is_out_of_band,
)

__all__ = [
    "COMMAND_TO_RESPONSE_MISMATCH",
    "CONSISTENCY_FEATURES",
    "CROSS_SIGNAL_MISMATCH",
    "EXPECTED_VALUE_CONTEXT_KEY",
    "ConsistencyEvidence",
    "ConsistencyFact",
    "consistency_feature_of",
    "facts_from",
    "loop_fact_parts",
    "promote_consistency",
]

logger = logging.getLogger(__name__)

CROSS_SIGNAL_MISMATCH: Final = "cross_signal_mismatch"
"""A reading disagrees with what every other signal, now and over the last minute, implies."""

COMMAND_TO_RESPONSE_MISMATCH: Final = "command_to_response_mismatch"
"""A declared command's actuator did not move.

Emitted by `phos.atlas.command_response` (ADR 0160), not by this module.
"""

CONSISTENCY_FEATURES: Final = (CROSS_SIGNAL_MISMATCH, COMMAND_TO_RESPONSE_MISMATCH)
"""Every feature `FacetKind.CONSISTENCY` may carry."""

EXPECTED_VALUE_CONTEXT_KEY: Final = "expected_from_rest_of_plant"
"""Observation context key holding the value the rest of the plant implies, as text."""


def consistency_feature_of(evidence: Evidence) -> str | None:
    """Return which consistency feature this evidence declares, or ``None``.

    Read from the typed facet only. Consistency evidence was introduced after ADR 0070, so there is
    no summary-marker path to fall back to.
    """
    if evidence.facet_kind is not FacetKind.CONSISTENCY:
        return None
    return evidence.facet


class ConsistencyFact(BaseModel):
    """One promoted consistency departure with its full traceability chain."""

    model_config = ConfigDict(frozen=True)

    observation: Observation
    deviation: Deviation
    evidence: Evidence


class ConsistencyEvidence(BaseModel):
    """Optional inlet. Empty or omitted, Atlas is byte-identical to the run without it."""

    model_config = ConfigDict(frozen=True)

    facts: tuple[ConsistencyFact, ...] = ()

    def evidence(self) -> tuple[Evidence, ...]:
        """Return the facts' evidence in time order."""
        ordered = sorted(
            self.facts, key=lambda item: (item.evidence.timestamp, item.evidence.summary)
        )
        return tuple(item.evidence for item in ordered)


def promote_consistency(
    model: ConsistencyModel,
    values: NDArray[numpy.float64],
    timestamps: Sequence[datetime],
    features: Sequence[str],
    entity_of: Mapping[str, EntityId],
    calibrator: FittedCalibrator,
    learned_from_window: tuple[datetime, datetime],
    domain: Domain = Domain.ATLAS,
) -> ConsistencyEvidence:
    """Score one file and promote each loop-carried event into calibrated `Evidence`.

    Args:
        model: A `phos.atlas.consistency.fit` result, fitted on data this file is not part of.
        values: The file's readings, rows by signals, in ``features`` order.
        timestamps: One UTC timestamp per row.
        features: The signal names, one per column.
        entity_of: The entity each signal belongs to. Every promoted signal must be present.
        calibrator: Supplies each fact's weight from its loop score, which Constitution §3.3
            requires to be a calibrated probability. Nothing here can check it was fitted honestly.
        learned_from_window: ``(start, end)`` of the training data, recorded on each range.
        domain: The domain the observations belong to.

    Returns:
        One fact per promoted event, earliest first.

    Raises:
        ValueError: If the shapes disagree, or a promoted signal has no entity.
    """
    if values.ndim != 2 or values.shape[1] != len(features):
        raise ValueError(
            f"values have shape {values.shape}; expected one column per feature ({len(features)})"
        )
    if values.shape[0] != len(timestamps):
        raise ValueError(f"{values.shape[0]} rows but {len(timestamps)} timestamps")

    loop, rng = feature_components(model, values)
    predicted, half_width = loop_expectation(model, values)
    found = events(feature_scores(model, values), windows=model.windows)

    pending: list[tuple[Observation, Deviation]] = []
    for event in found:
        row, column = event.onset, event.column
        loop_score = float(loop[row, column])
        if not (loop_score > THRESHOLD and loop_score >= float(rng[row, column])):
            continue
        parts = loop_fact_parts(
            model,
            values,
            timestamps,
            features,
            entity_of,
            (predicted, half_width),
            (row, column, loop_score),
            learned_from_window,
            domain,
        )
        if parts is not None:
            pending.append(parts)
    facts = facts_from(pending, calibrator, _describe)
    logger.info("promoted %d of %d consistency event(s) into evidence", len(facts), len(found))
    return ConsistencyEvidence(facts=facts)


def loop_fact_parts(
    model: ConsistencyModel,
    values: NDArray[numpy.float64],
    timestamps: Sequence[datetime],
    features: Sequence[str],
    entity_of: Mapping[str, EntityId],
    expectation: tuple[NDArray[numpy.float64], NDArray[numpy.float64]],
    cell: tuple[int, int, float],
    learned_from_window: tuple[datetime, datetime],
    domain: Domain,
) -> tuple[Observation, Deviation] | None:
    """The observation and deviation of one loop-carried alert cell, or ``None`` on the band's edge.

    ``expectation`` is `phos.atlas.consistency.loop_expectation` of the file; ``cell`` is
    ``(row, column, loop score)``.

    Raises:
        ValueError: If the cell's signal has no entity.
    """
    predicted, half_width = expectation
    row, column, loop_score = cell
    centre = float(predicted[row, column])
    half = float(half_width[row, column])
    value = float(values[row, column])
    if not (math.isfinite(centre) and math.isfinite(half)):
        return None
    feature = features[column]
    entity = entity_of.get(feature)
    if entity is None:
        raise ValueError(f"signal {feature!r} has no entity in entity_of")
    observation = Observation(
        entity_ids=[entity],
        feature=feature,
        value=value,
        timestamp=timestamps[row],
        domain=domain,
        context={EXPECTED_VALUE_CONTEXT_KEY: f"{centre:.6g}"},
    )
    deviation = Deviation(
        observation_id=observation.id,
        expected=ExpectedRange(
            feature=feature,
            entity_id=entity,
            low=centre - half,
            high=centre + half,
            mean=float(model.mean[column]),
            stddev=float(model.spread[column]),
            learned_from_window=learned_from_window,
        ),
        magnitude=loop_score,
        timestamp=timestamps[row],
    )
    if not is_out_of_band(deviation, observation):
        # Only at the threshold itself, where float32 scores and a float64 band can disagree.
        logger.debug("skipped %s at row %d: on the band's edge", feature, row)
        return None
    return observation, deviation


def facts_from(
    pending: Sequence[tuple[Observation, Deviation]],
    calibrator: FittedCalibrator,
    describe: Callable[[Observation, Deviation], str],
) -> tuple[ConsistencyFact, ...]:
    """Weigh each pending fact by the calibrator and promote it through the boundary."""
    weights = calibrated_probabilities(
        calibrator, [deviation.magnitude for _observation, deviation in pending]
    )
    return tuple(
        ConsistencyFact(
            observation=observation,
            deviation=deviation,
            evidence=evidence_from_deviation(
                deviation,
                observation,
                weight,
                summary=describe(observation, deviation),
                facet=(FacetKind.CONSISTENCY, CROSS_SIGNAL_MISMATCH),
            ),
        )
        for (observation, deviation), weight in zip(pending, weights, strict=True)
    )


def _describe(observation: Observation, deviation: Deviation) -> str:
    """The sentence an operator reads: the reading, and what the rest of the plant implies."""
    expected = deviation.expected
    centre = (expected.low + expected.high) / 2.0
    return (
        f"{observation.feature} read {observation.value:.6g}; the rest of the plant implies about "
        f"{centre:.6g} (consistent between {expected.low:.6g} and {expected.high:.6g})"
    )

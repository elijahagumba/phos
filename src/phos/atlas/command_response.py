"""A declared command whose actuator did not move (ADR 0160).

A plant's ``CONTROL`` couplings already say which setpoint a loop chases and which actuator it
moves. This module reads that declaration. It does not infer a pairing from signals that happen
to move together: that is the circularity `phos.atlas.topology` refuses.

**The check.** After a wire write to the coupling's setpoint, the actuator's reported travel over
a fixed horizon is compared with a fixed share of its own span. Travel at least that large means
the actuator answered. Travel below it, when the setpoint itself moved by at least the same share
of its span, is `COMMAND_TO_RESPONSE_MISMATCH`. The observation is the travel, and the expected
range is the travel a following actuator would have shown. The fact goes through
`phos.reasoning.boundary`, like every other deviation.

The controlled measurement is recorded on the pair for the reader. It is not subtracted from the
setpoint: the two are often in different units, and inventing a conversion would be a second
model.

Travel is the actuator's reported change from the write's own sample to the sample
``horizon_steps`` later. On these plants the write lands before the controller reads the previous
report, so the actuator answers on the scans inside that window, not on the write sample itself.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from phos.atlas.consistency_evidence import (
    COMMAND_TO_RESPONSE_MISMATCH,
    ConsistencyEvidence,
    ConsistencyFact,
)
from phos.ontology import (
    Deviation,
    Domain,
    EntityId,
    ExpectedRange,
    FacetKind,
    Observation,
)
from phos.reasoning import FittedCalibrator, calibrated_probabilities, evidence_from_deviation
from phos.synth.plant import CouplingKind, PlantDescription, SignalKind, SignalSpec

__all__ = [
    "HORIZON_STEPS",
    "MIN_COMMAND_SHARE",
    "MIN_RESPONSE_SHARE",
    "CommandResponsePair",
    "declared_pairs",
    "response_mismatches",
]

logger = logging.getLogger(__name__)

MIN_COMMAND_SHARE: Final = 0.05
"""A write smaller than this share of the setpoint span is not a command the check judges."""

MIN_RESPONSE_SHARE: Final = 0.05
"""Actuator travel below this share of its span did not answer the command."""

HORIZON_STEPS: Final = 20
"""Samples after the write in which the actuator must have moved. The same count on every plant."""

_TRAVEL_FEATURE: Final = "travel_after_command"


@dataclass(frozen=True)
class CommandResponsePair:
    """One declared loop: the setpoint, the actuator it moves, and the measurement it holds.

    Attributes:
        command: The setpoint a wire write addresses.
        actuator: The coupling's driven signal, the loop's immediate response.
        response: The controlled measurement when the coupling names exactly one, else the
            actuator. Recorded so a reader can see the loop. Not compared in the setpoint's units.
    """

    command: str
    actuator: str
    response: str


def declared_pairs(description: PlantDescription) -> tuple[CommandResponsePair, ...]:
    """Return the command-response pairs a plant's ``CONTROL`` couplings declare.

    A coupling qualifies when it is ``CONTROL`` and names exactly one setpoint among its drivers.
    The actuator is the driven signal. The response is the only other driver when there is exactly
    one; otherwise it is the actuator, because choosing among several sensors would be an
    inference the coupling did not make.

    Args:
        description: The plant's declaration. Couplings and signal kinds are read; no series is.

    Returns:
        The pairs in coupling order. Empty when the plant declares no such loop.
    """
    kind_of = {spec.key: spec.kind for spec in description.signals}
    pairs: list[CommandResponsePair] = []
    for coupling in description.couplings:
        if coupling.kind is not CouplingKind.CONTROL:
            continue
        setpoints = [
            driver for driver in coupling.drivers if kind_of[driver] is SignalKind.SETPOINT
        ]
        if len(setpoints) != 1:
            continue
        others = [driver for driver in coupling.drivers if driver != setpoints[0]]
        response = others[0] if len(others) == 1 else coupling.driven
        pairs.append(CommandResponsePair(setpoints[0], coupling.driven, response))
    return tuple(pairs)


def response_mismatches(
    *,
    pairs: Sequence[CommandResponsePair],
    signals: Mapping[str, SignalSpec],
    reported: Mapping[str, Sequence[float]],
    writes: Sequence[tuple[int, str]],
    timestamps: Sequence[datetime],
    entity_of: Mapping[str, EntityId],
    calibrator: FittedCalibrator,
    learned_from_window: tuple[datetime, datetime],
    horizon_steps: int = HORIZON_STEPS,
    min_command_share: float = MIN_COMMAND_SHARE,
    min_response_share: float = MIN_RESPONSE_SHARE,
    domain: Domain = Domain.ATLAS,
) -> ConsistencyEvidence:
    """Promote each declared command whose actuator did not move.

    Args:
        pairs: From `declared_pairs`. A write to any other signal is ignored.
        signals: Signal specs keyed by name, for spans.
        reported: Reported series, one per signal, aligned with ``timestamps``.
        writes: ``(sample index, setpoint key)`` for each wire write. Authorisation is not an
            input: a write is a write.
        timestamps: One UTC timestamp per sample.
        entity_of: Entity id for each actuator that might be promoted.
        calibrator: Maps the travel shortfall onto the evidence weight.
        learned_from_window: Training window recorded on the expected range.
        horizon_steps: Samples after the write. A window that runs off the series is not a fact.
        min_command_share: Smallest setpoint step, as a share of its span, that counts.
        min_response_share: Smallest actuator travel, as a share of its span, that counts as an
            answer.
        domain: Domain of the observations.

    Returns:
        One fact per unanswered command, in write order.

    Raises:
        ValueError: If a share is not strictly between 0 and 1, the horizon is not positive, or
            a promoted actuator has no entity.
    """
    _require_share("min_command_share", min_command_share)
    _require_share("min_response_share", min_response_share)
    if horizon_steps < 1:
        raise ValueError(f"horizon_steps must be positive, got {horizon_steps}")
    by_command = {pair.command: pair for pair in pairs}
    pending: list[tuple[Observation, Deviation, float]] = []
    n_samples = len(timestamps)
    if any(len(series) != n_samples for series in reported.values()):
        raise ValueError("every reported series must have one value per timestamp")
    for index, command in writes:
        pair = by_command.get(command)
        if pair is None or index < 1 or index >= n_samples or index + horizon_steps >= n_samples:
            continue
        command_spec = signals[command]
        actuator_spec = signals[pair.actuator]
        command_span = command_spec.high - command_spec.low
        actuator_span = actuator_spec.high - actuator_spec.low
        step = abs(reported[command][index] - reported[command][index - 1])
        if step < min_command_share * command_span:
            continue
        later = reported[pair.actuator][index + horizon_steps]
        travel = abs(later - reported[pair.actuator][index])
        min_travel = min_response_share * actuator_span
        if travel >= min_travel:
            continue
        entity = entity_of.get(pair.actuator)
        if entity is None:
            raise ValueError(f"actuator {pair.actuator!r} has no entity in entity_of")
        shortfall = (min_travel - travel) / min_travel
        observation = Observation(
            entity_ids=[entity],
            feature=f"{pair.actuator}__{_TRAVEL_FEATURE}",
            value=travel,
            timestamp=timestamps[index + horizon_steps],
            domain=domain,
            context={
                "command": command,
                "actuator": pair.actuator,
                "response": pair.response,
                "setpoint_before": f"{reported[command][index - 1]:.6g}",
                "setpoint_after": f"{reported[command][index]:.6g}",
                "min_travel": f"{min_travel:.6g}",
            },
        )
        deviation = Deviation(
            observation_id=observation.id,
            timestamp=observation.timestamp,
            magnitude=(min_travel - travel) / actuator_span,
            expected=ExpectedRange(
                feature=observation.feature,
                entity_id=entity,
                low=min_travel,
                high=actuator_span,
                mean=min_travel,
                stddev=actuator_span,
                learned_from_window=learned_from_window,
            ),
        )
        pending.append((observation, deviation, shortfall))
    if not pending:
        return ConsistencyEvidence()
    weights = calibrated_probabilities(calibrator, [item[2] for item in pending])
    facts: list[ConsistencyFact] = []
    for (observation, deviation, _shortfall), weight in zip(pending, weights, strict=True):
        summary = (
            f"{observation.context['actuator']} moved {observation.value:.6g} after "
            f"{observation.context['command']} changed, under the {min_travel_text(observation)} "
            "travel a following actuator shows"
        )
        facts.append(
            ConsistencyFact(
                observation=observation,
                deviation=deviation,
                evidence=evidence_from_deviation(
                    deviation,
                    observation,
                    weight,
                    summary=summary,
                    facet=(FacetKind.CONSISTENCY, COMMAND_TO_RESPONSE_MISMATCH),
                ),
            )
        )
    logger.info("promoted %d command-to-response mismatch(es)", len(facts))
    return ConsistencyEvidence(facts=tuple(facts))


def min_travel_text(observation: Observation) -> str:
    """Return the minimum travel stored on ``observation``, for the summary."""
    return observation.context["min_travel"]


def _require_share(name: str, value: float) -> None:
    """Raise unless ``value`` is a share strictly inside (0, 1)."""
    if not 0.0 < value < 1.0:
        raise ValueError(f"{name} must be strictly between 0 and 1, got {value}")

"""What a known station's write did to the plant (ADR 0250).

Not who sent it. A known-link function change still supports both maintenance and unauthorised
control; this module does not match that finding.

H1: toward a safety limit, against the reported call, outside the operating band. A covering
work order withholds it. H2: a step larger than the operating band's width, or a write during
a manual mode. H2 is not withheld by a work order. Weight is a constant one half, not a knob.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Final, NamedTuple

from phos.atlas.command_response import (
    MIN_COMMAND_SHARE,
    MIN_RESPONSE_SHARE,
    CommandResponsePair,
    declared_pairs,
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
)
from phos.synth.plant import PlantDescription, SignalSpec

__all__ = [
    "DEADBAND_NOISE_SIGMAS",
    "HIDE_HORIZON_STEPS",
    "OUTSIDE_OPERATING_MODE",
    "SETPOINT_JUMP",
    "TOWARD_LIMIT_AGAINST_STATE",
    "WRITE_AND_HIDE",
    "OperatorWrite",
    "called_for_direction",
    "command_effect_evidence",
    "command_effect_feature_of",
    "is_setpoint_jump",
    "moves_toward_limit_against_call",
    "reading_stays_hidden",
]

logger = logging.getLogger(__name__)

TOWARD_LIMIT_AGAINST_STATE: Final = "toward_limit_against_state"
"""Setpoint moved toward a safety limit, against the direction the plant's state called for."""

SETPOINT_JUMP: Final = "setpoint_jump"
"""One write moved the setpoint by more than the declared operating band's width."""

OUTSIDE_OPERATING_MODE: Final = "outside_operating_mode"
"""A setpoint was written while a declared manual mode was in force."""

WRITE_AND_HIDE: Final = "write_and_hide"
"""The actuator moved and the controlled reading did not."""

HIDE_HORIZON_STEPS: Final = 8
"""Samples after the write used to see whether the reading followed. Not searched."""

_FEATURES: Final = frozenset(
    {
        TOWARD_LIMIT_AGAINST_STATE,
        SETPOINT_JUMP,
        OUTSIDE_OPERATING_MODE,
        WRITE_AND_HIDE,
    }
)

DEADBAND_NOISE_SIGMAS: Final = 3.0
"""Hold if the error is inside this many of the measurement's own noise standard deviations."""

_FEATURE: Final = "setpoint_after_write"


class OperatorWrite:
    """One operator write. Authorisation is not a field: the promoter does not read it."""

    __slots__ = ("applied", "index", "signal")

    def __init__(self, index: int, signal: str, applied: float) -> None:
        """Record one operator write. ``applied`` is the value the plant took."""
        self.index = index
        self.signal = signal
        self.applied = applied


def command_effect_feature_of(evidence: Evidence) -> str | None:
    """Return the command-effect feature from the typed facet, or ``None``."""
    if evidence.facet_kind is not FacetKind.COMMAND_EFFECT:
        return None
    return evidence.facet


def called_for_direction(measurement: float, setpoint: float, deadband: float) -> int:
    """Return 1 to raise, -1 to lower, or 0 to hold. ``deadband`` must be non-negative.

    The call is ``setpoint - measurement`` on the sample before the write.
    """
    if deadband < 0.0:
        raise ValueError(f"deadband must be non-negative, got {deadband}")
    error = setpoint - measurement
    if error > deadband:
        return 1
    if error < -deadband:
        return -1
    return 0


def moves_toward_limit_against_call(
    *,
    before: float,
    after: float,
    low: float,
    high: float,
    operating_low: float,
    operating_high: float,
    call: int,
    min_share: float = MIN_COMMAND_SHARE,
) -> bool:
    """Return whether ``after`` left the operating band toward ``low`` or ``high`` against ``call``.

    The closure must be at least ``min_share`` of the safety span. A hold counts. An in-band
    step does not. Raises ValueError if the span, the share, or the band is unusable.
    """
    span = high - low
    if span <= 0.0:
        raise ValueError(f"safety span must be positive, got {span}")
    if not 0.0 < min_share < 1.0:
        raise ValueError(f"min_share must be strictly between 0 and 1, got {min_share}")
    if operating_low > operating_high:
        raise ValueError(f"operating band is inverted: {operating_low} > {operating_high}")
    if operating_low <= after <= operating_high:
        return False
    closure = _limit_distance(before, low, high) - _limit_distance(after, low, high)
    if closure < min_share * span:
        return False
    delta = after - before
    if delta == 0.0:
        return False
    if call == 0:
        return True
    return (delta > 0.0 and call < 0) or (delta < 0.0 and call > 0)


def is_setpoint_jump(
    before: float, after: float, operating_low: float, operating_high: float
) -> bool:
    """Return whether ``abs(after - before)`` exceeds the operating band's width.

    Raises ValueError if that width is not positive. An empty band would call every write a jump.
    """
    width = operating_high - operating_low
    if width <= 0.0:
        raise ValueError(
            f"operating band must have positive width, got {operating_low} to {operating_high}"
        )
    return abs(after - before) > width


def reading_stays_hidden(
    *,
    actuator_before: float,
    actuator_after: float,
    reading_before: float,
    reading_after: float,
    actuator_span: float,
    reading_deadband: float,
    min_response_share: float = MIN_RESPONSE_SHARE,
) -> bool:
    """Return whether the actuator moved at least ``min_response_share`` and the reading did not.

    The reading is held when its travel is within ``reading_deadband``. Raises ValueError if
    the actuator span is not positive or the share is not inside (0, 1).
    """
    if actuator_span <= 0.0:
        raise ValueError(f"actuator span must be positive, got {actuator_span}")
    if not 0.0 < min_response_share < 1.0:
        raise ValueError(f"min_response_share must be inside (0, 1), got {min_response_share}")
    moved = abs(actuator_after - actuator_before) >= min_response_share * actuator_span
    held = abs(reading_after - reading_before) <= reading_deadband
    return moved and held


class _Pending(NamedTuple):
    """One fact waiting for its calibrated weight."""

    observation: Observation
    deviation: Deviation
    score: float
    feature: str
    summary: str


def command_effect_evidence(
    *,
    description: PlantDescription,
    reported: Mapping[str, Sequence[float]],
    timestamps: Sequence[datetime],
    writes: Sequence[OperatorWrite],
    operating_bands: Mapping[str, tuple[float, float]],
    covered: frozenset[str],
    entity_of: Mapping[str, EntityId],
    calibrator: FittedCalibrator,
    learned_from_window: tuple[datetime, datetime],
    enabled: frozenset[str] = frozenset({TOWARD_LIMIT_AGAINST_STATE}),
    active_kinds: Sequence[str | None] | None = None,
    manual_modes: frozenset[str] = frozenset(),
    horizon_steps: int = HIDE_HORIZON_STEPS,
    domain: Domain = Domain.ATLAS,
) -> tuple[Evidence, ...]:
    """Promote the enabled command-effect facts, in write order then feature order.

    ``description`` supplies couplings and spans. ``reported`` and ``timestamps`` are aligned.
    ``covered`` withholds H1 only. ``enabled`` names the features; an unknown name is refused.
    ``active_kinds`` is one kind per sample when the mode feature is enabled. ``calibrator``
    sets the weight; lane T passes a constant one half. ``entity_of`` must name every setpoint
    that qualifies.

    Raises:
        ValueError: On a length mismatch, an unknown feature, a missing mode series, or a
            setpoint with no entity.
    """
    if not enabled <= _FEATURES:
        unknown = sorted(enabled - _FEATURES)
        raise ValueError(f"unknown command-effect feature(s): {unknown}")
    if not enabled:
        return ()
    if horizon_steps < 1:
        raise ValueError(f"horizon_steps must be positive, got {horizon_steps}")
    _check_series(reported, timestamps)
    if OUTSIDE_OPERATING_MODE in enabled:
        if active_kinds is None or len(active_kinds) != len(timestamps):
            raise ValueError("outside_operating_mode needs one active kind per sample")
    signals = {spec.key: spec for spec in description.signals}
    pairs: dict[str, CommandResponsePair] = {
        pair.command: pair for pair in declared_pairs(description)
    }
    pending: list[_Pending] = []
    for write in writes:
        if TOWARD_LIMIT_AGAINST_STATE in enabled:
            built = _h1_fact(
                write=write,
                pairs=pairs,
                signals=signals,
                reported=reported,
                timestamps=timestamps,
                operating_bands=operating_bands,
                covered=covered,
                entity_of=entity_of,
                learned_from_window=learned_from_window,
                domain=domain,
            )
            if built is not None:
                observation, deviation, score = built
                pending.append(
                    _Pending(
                        observation,
                        deviation,
                        score,
                        TOWARD_LIMIT_AGAINST_STATE,
                        (
                            f"{observation.context['command']} moved to {observation.value:.6g}, "
                            "toward a safety limit and against the direction the plant called for "
                            f"({observation.context['call']})"
                        ),
                    )
                )
        pending.extend(
            _h2_facts(
                write=write,
                reported=reported,
                timestamps=timestamps,
                operating_bands=operating_bands,
                entity_of=entity_of,
                learned_from_window=learned_from_window,
                domain=domain,
                enabled=enabled,
                active_kinds=active_kinds,
                manual_modes=manual_modes,
            )
        )
        if WRITE_AND_HIDE in enabled:
            hidden = _hide_fact(
                write=write,
                pairs=pairs,
                signals=signals,
                reported=reported,
                timestamps=timestamps,
                entity_of=entity_of,
                learned_from_window=learned_from_window,
                domain=domain,
                horizon_steps=horizon_steps,
            )
            if hidden is not None:
                pending.append(hidden)
    if not pending:
        return ()
    weights = calibrated_probabilities(calibrator, [item.score for item in pending])
    facts: list[Evidence] = []
    for item, weight in zip(pending, weights, strict=True):
        facts.append(
            evidence_from_deviation(
                item.deviation,
                item.observation,
                float(weight),
                summary=item.summary,
                facet=(FacetKind.COMMAND_EFFECT, item.feature),
            )
        )
    logger.info("promoted %d command-effect fact(s)", len(facts))
    return tuple(facts)


def _h2_facts(
    *,
    write: OperatorWrite,
    reported: Mapping[str, Sequence[float]],
    timestamps: Sequence[datetime],
    operating_bands: Mapping[str, tuple[float, float]],
    entity_of: Mapping[str, EntityId],
    learned_from_window: tuple[datetime, datetime],
    domain: Domain,
    enabled: frozenset[str],
    active_kinds: Sequence[str | None] | None,
    manual_modes: frozenset[str],
) -> tuple[_Pending, ...]:
    """Return the jump fact and the mode fact when each is enabled and true."""
    index = write.index
    if index < 1 or index >= len(timestamps) or write.signal not in reported:
        return ()
    entity = entity_of.get(write.signal)
    before = reported[write.signal][index - 1]
    after = reported[write.signal][index]
    found: list[_Pending] = []
    band = operating_bands.get(write.signal)
    if SETPOINT_JUMP in enabled and band is not None and entity is not None:
        if is_setpoint_jump(before, after, band[0], band[1]):
            step = abs(after - before)
            width = band[1] - band[0]
            observation = _observation(
                entity=entity,
                signal=write.signal,
                feature="setpoint_step",
                value=step,
                timestamp=timestamps[index],
                domain=domain,
                context={
                    "command": write.signal,
                    "setpoint_before": f"{before:.6g}",
                    "setpoint_after": f"{after:.6g}",
                    "band_width": f"{width:.6g}",
                },
            )
            found.append(
                _Pending(
                    observation,
                    _deviation(
                        observation,
                        low=0.0,
                        high=width,
                        score=step / width,
                        learned_from_window=learned_from_window,
                    ),
                    step / width,
                    SETPOINT_JUMP,
                    (
                        f"{write.signal} jumped by {step:.6g}, more than the {width:.6g} "
                        "width of the declared operating band"
                    ),
                )
            )
    if (
        OUTSIDE_OPERATING_MODE in enabled
        and active_kinds is not None
        and entity is not None
        and active_kinds[index] in manual_modes
    ):
        kind = active_kinds[index] or ""
        observation = _observation(
            entity=entity,
            signal=write.signal,
            feature="manual_mode_write",
            value=1.0,
            timestamp=timestamps[index],
            domain=domain,
            context={"command": write.signal, "mode": kind},
        )
        found.append(
            _Pending(
                observation,
                _deviation(
                    observation,
                    low=0.0,
                    high=0.0,
                    score=1.0,
                    learned_from_window=learned_from_window,
                ),
                1.0,
                OUTSIDE_OPERATING_MODE,
                f"{write.signal} was written while {kind} was in force",
            )
        )
    if (SETPOINT_JUMP in enabled or OUTSIDE_OPERATING_MODE in enabled) and entity is None:
        raise ValueError(f"setpoint {write.signal!r} has no entity in entity_of")
    return tuple(found)


def _observation(
    *,
    entity: EntityId,
    signal: str,
    feature: str,
    value: float,
    timestamp: datetime,
    domain: Domain,
    context: dict[str, str],
) -> Observation:
    """Build the observation a command-effect deviation is judged from."""
    return Observation(
        entity_ids=[entity],
        feature=f"{signal}__{feature}",
        value=value,
        timestamp=timestamp,
        domain=domain,
        context=context,
    )


def _deviation(
    observation: Observation,
    *,
    low: float,
    high: float,
    score: float,
    learned_from_window: tuple[datetime, datetime],
) -> Deviation:
    """Build a deviation whose expected range is the declared ordinary band."""
    return Deviation(
        observation_id=observation.id,
        timestamp=observation.timestamp,
        magnitude=score,
        expected=ExpectedRange(
            feature=observation.feature,
            entity_id=observation.entity_ids[0],
            low=low,
            high=high,
            mean=(low + high) / 2.0,
            stddev=max((high - low) / 2.0, 0.0),
            learned_from_window=learned_from_window,
        ),
    )


def _hide_fact(
    *,
    write: OperatorWrite,
    pairs: Mapping[str, CommandResponsePair],
    signals: Mapping[str, SignalSpec],
    reported: Mapping[str, Sequence[float]],
    timestamps: Sequence[datetime],
    entity_of: Mapping[str, EntityId],
    learned_from_window: tuple[datetime, datetime],
    domain: Domain,
    horizon_steps: int,
) -> _Pending | None:
    """Return the write-and-hide fact, or ``None`` when the reading followed."""
    pair = pairs.get(write.signal)
    entity = entity_of.get(write.signal)
    end = write.index + horizon_steps
    if pair is None or entity is None or write.index < 1 or end >= len(timestamps):
        return None
    actuator = pair.actuator
    reading = pair.response
    if actuator not in reported or reading not in reported:
        return None
    sensor = signals[reading]
    actuator_spec = signals[actuator]
    before = write.index - 1
    deadband = DEADBAND_NOISE_SIGMAS * sensor.noise_stddev
    if not reading_stays_hidden(
        actuator_before=reported[actuator][before],
        actuator_after=reported[actuator][end],
        reading_before=reported[reading][before],
        reading_after=reported[reading][end],
        actuator_span=actuator_spec.high - actuator_spec.low,
        reading_deadband=deadband,
    ):
        return None
    travel = abs(reported[reading][end] - reported[reading][before])
    observation = _observation(
        entity=entity,
        signal=write.signal,
        feature="hidden_reading_travel",
        value=travel,
        timestamp=timestamps[end],
        domain=domain,
        context={
            "command": write.signal,
            "actuator": actuator,
            "measurement": reading,
        },
    )
    return _Pending(
        observation,
        _deviation(
            observation,
            low=deadband,
            high=max(sensor.high - sensor.low, deadband),
            score=1.0,
            learned_from_window=learned_from_window,
        ),
        1.0,
        WRITE_AND_HIDE,
        f"{actuator} moved after {write.signal} was written and {reading} did not",
    )


def _h1_fact(
    *,
    write: OperatorWrite,
    pairs: Mapping[str, CommandResponsePair],
    signals: Mapping[str, SignalSpec],
    reported: Mapping[str, Sequence[float]],
    timestamps: Sequence[datetime],
    operating_bands: Mapping[str, tuple[float, float]],
    covered: frozenset[str],
    entity_of: Mapping[str, EntityId],
    learned_from_window: tuple[datetime, datetime],
    domain: Domain,
) -> tuple[Observation, Deviation, float] | None:
    """Build one H1 observation, or ``None`` when the write does not qualify."""
    pair = pairs.get(write.signal)
    band = operating_bands.get(write.signal)
    if pair is None or band is None or write.signal in covered:
        return None
    index = write.index
    if index < 1 or index >= len(timestamps):
        return None
    measurement = pair.response
    if measurement not in reported or write.signal not in reported:
        return None
    spec = signals[write.signal]
    sensor = signals[measurement]
    before = reported[write.signal][index - 1]
    after = reported[write.signal][index]
    deadband = DEADBAND_NOISE_SIGMAS * sensor.noise_stddev
    call = called_for_direction(reported[measurement][index - 1], before, deadband)
    if not moves_toward_limit_against_call(
        before=before,
        after=after,
        low=spec.low,
        high=spec.high,
        operating_low=band[0],
        operating_high=band[1],
        call=call,
    ):
        return None
    entity = entity_of.get(write.signal)
    if entity is None:
        raise ValueError(f"setpoint {write.signal!r} has no entity in entity_of")
    span = spec.high - spec.low
    closure = _limit_distance(before, spec.low, spec.high) - _limit_distance(
        after, spec.low, spec.high
    )
    score = closure / span
    call_name = {1: "raise", -1: "lower", 0: "hold"}[call]
    observation = Observation(
        entity_ids=[entity],
        feature=f"{write.signal}__{_FEATURE}",
        value=after,
        timestamp=timestamps[index],
        domain=domain,
        context={
            "command": write.signal,
            "measurement": measurement,
            "setpoint_before": f"{before:.6g}",
            "call": call_name,
            "applied": f"{write.applied:.6g}",
        },
    )
    deviation = Deviation(
        observation_id=observation.id,
        timestamp=observation.timestamp,
        magnitude=score,
        expected=ExpectedRange(
            feature=observation.feature,
            entity_id=entity,
            low=band[0],
            high=band[1],
            mean=(band[0] + band[1]) / 2.0,
            stddev=max((band[1] - band[0]) / 2.0, 0.0),
            learned_from_window=learned_from_window,
        ),
    )
    return observation, deviation, score


def _limit_distance(value: float, low: float, high: float) -> float:
    """Return the distance from ``value`` to the nearer safety limit."""
    return min(value - low, high - value)


def _check_series(reported: Mapping[str, Sequence[float]], timestamps: Sequence[datetime]) -> None:
    """Raise if any series is a different length from ``timestamps``."""
    n_samples = len(timestamps)
    for key, series in reported.items():
        if len(series) != n_samples:
            raise ValueError(
                f"reported series {key!r} has {len(series)} samples, timestamps have {n_samples}"
            )

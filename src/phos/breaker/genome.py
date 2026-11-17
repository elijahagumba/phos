"""The attack genome: a structured description of a simulated attack (PART S7).

A genome is built from the S4 catalogue: event type, target tags, start time, duration,
intensity, shape (step, ramp, pulse, replay), and layer. It carries validity checks so the
breaker only ever proposes physically and protocol-consistent attacks.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class AttackTechnique(StrEnum):
    """Techniques the breaker may draw from, mirroring S4's event catalogue.

    Held-out techniques are marked separately by the loader (see `phos.breaker.round_runner`)
    and are never trained on.
    """

    LEVEL_EXCURSION = "level_excursion"
    TEMPERATURE_RAMP = "temperature_ramp"
    PRESSURE_SPIKE = "pressure_spike"
    FLOW_MANIPULATION = "flow_manipulation"
    VALVE_STUCK = "valve_stuck"
    SENSOR_DRIFT = "sensor_drift"
    REPLAY_COMMAND = "replay_command"
    SETPOINT_WALK = "setpoint_walk"


class AttackShape(StrEnum):
    """The time profile of the attack."""

    STEP = "step"
    RAMP = "ramp"
    PULSE = "pulse"
    REPLAY = "replay"


@dataclass(frozen=True)
class AttackGenome:
    """One attack candidate.

    Attributes:
        technique: What kind of event it is.
        target_tags: The tags the attack acts on (at least one).
        start_time: Seconds into the plant's run when the attack starts.
        duration: Seconds the attack runs.
        intensity: How strong the attack is, in the technique's own units.
        shape: The time profile.
        layer: Which layer of the stack the attack acts on (sensor, actuator, network).
    """

    technique: AttackTechnique
    target_tags: tuple[str, ...]
    start_time: float
    duration: float
    intensity: float
    shape: AttackShape
    layer: str

    def __post_init__(self) -> None:
        """Validate the genome's fields after construction."""
        if not self.target_tags:
            raise ValueError("genome needs at least one target tag")
        if self.start_time < 0.0:
            raise ValueError("start_time must be non-negative")
        if self.duration <= 0.0:
            raise ValueError("duration must be positive")
        if self.intensity < 0.0:
            raise ValueError("intensity must be non-negative")


def validate_genome(genome: AttackGenome) -> None:
    """Raise if the genome is not physically and protocol consistent.

    Checks are deliberately conservative: a genome that passes here is *plausible*, not
    guaranteed to produce a physical effect. The simulator makes the final call.

    Raises:
        ValueError: Naming the rule the genome breaks.
    """
    if len(genome.target_tags) > 8:
        raise ValueError(
            f"genome targets {len(genome.target_tags)} tags (max 8); an attack that touches "
            "nearly every signal is not a credible single-technique probe"
        )
    if genome.start_time > 86400.0:
        raise ValueError(
            f"start_time {genome.start_time}s exceeds a 24-hour run; nothing after the end "
            "can be observed"
        )
    if genome.duration > 86400.0:
        raise ValueError(
            f"duration {genome.duration}s exceeds a 24-hour run; an attack longer than the "
            "run is not a distinct technique"
        )
    if genome.technique is AttackTechnique.REPLAY_COMMAND and genome.layer != "network":
        raise ValueError(
            "a replay_command acts on the network layer; genomes that place it elsewhere are "
            "not protocol-consistent"
        )


__all__ = ["AttackGenome", "AttackShape", "AttackTechnique", "validate_genome"]

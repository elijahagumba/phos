"""Tests for `phos.breaker.genome`: attack genomes and validity checks (PART S7)."""

from __future__ import annotations

import pytest

from phos.breaker.genome import (
    AttackGenome,
    AttackShape,
    AttackTechnique,
    validate_genome,
)


def _genome(
    technique: AttackTechnique = AttackTechnique.LEVEL_EXCURSION,
    target_tags: tuple[str, ...] = ("tank_level",),
    start_time: float = 100.0,
    duration: float = 300.0,
    intensity: float = 5.0,
    shape: AttackShape = AttackShape.STEP,
    layer: str = "sensor",
) -> AttackGenome:
    return AttackGenome(
        technique=technique,
        target_tags=target_tags,
        start_time=start_time,
        duration=duration,
        intensity=intensity,
        shape=shape,
        layer=layer,
    )


def test_valid_genome_passes() -> None:
    validate_genome(_genome())


def test_no_target_tags_refused() -> None:
    with pytest.raises(ValueError, match="at least one target tag"):
        validate_genome(_genome(target_tags=()))


def test_negative_start_refused() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        validate_genome(_genome(start_time=-1.0))


def test_zero_duration_refused() -> None:
    with pytest.raises(ValueError, match="positive"):
        validate_genome(_genome(duration=0.0))


def test_negative_intensity_refused() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        validate_genome(_genome(intensity=-1.0))


def test_too_many_tags_refused() -> None:
    with pytest.raises(ValueError, match="max 8"):
        validate_genome(_genome(target_tags=tuple(f"tag_{i}" for i in range(9))))


def test_replay_command_wrong_layer_refused() -> None:
    with pytest.raises(ValueError, match="network layer"):
        validate_genome(_genome(technique=AttackTechnique.REPLAY_COMMAND, layer="sensor"))


def test_replay_command_network_layer_ok() -> None:
    validate_genome(_genome(technique=AttackTechnique.REPLAY_COMMAND, layer="network"))


__all__ = []

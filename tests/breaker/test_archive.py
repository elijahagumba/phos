"""Tests for `phos.breaker.archive`: diversity archive of successful attacks (PART S7)."""

from __future__ import annotations

from phos.breaker.archive import DiversityArchive
from phos.breaker.genome import (
    AttackGenome,
    AttackShape,
    AttackTechnique,
)
from phos.breaker.objective import Objective


def _genome(technique=AttackTechnique.LEVEL_EXCURSION, start_time=100.0, intensity=5.0) -> AttackGenome:
    return AttackGenome(
        technique=technique,
        target_tags=("tank_level",),
        start_time=start_time,
        duration=300.0,
        intensity=intensity,
        shape=AttackShape.STEP,
        layer="sensor",
    )


def _objective(value: float) -> Objective:
    return Objective(stealth=value, harm=value, value=value * value)


def test_add_records_new_region() -> None:
    archive = DiversityArchive()
    genome = _genome()
    added = archive.add(genome, _objective(0.8))
    assert added is True
    assert archive.regions() == 1


def test_add_same_region_keeps_best() -> None:
    archive = DiversityArchive()
    g1 = _genome(start_time=100.0)
    g2 = _genome(start_time=120.0)  # same 30-minute bin
    archive.add(g1, _objective(0.5))
    added = archive.add(g2, _objective(0.9))
    assert added is True  # better value replaces
    assert archive.regions() == 1


def test_techniques_returns_seen_techniques() -> None:
    archive = DiversityArchive()
    archive.add(_genome(technique=AttackTechnique.LEVEL_EXCURSION), _objective(0.5))
    archive.add(_genome(technique=AttackTechnique.TEMPERATURE_RAMP), _objective(0.6))
    assert archive.techniques() == {"level_excursion", "temperature_ramp"}


def test_best_returns_highest_value() -> None:
    archive = DiversityArchive()
    archive.add(_genome(intensity=1.0), _objective(0.3))
    archive.add(_genome(intensity=9.0), _objective(0.9))
    best = archive.best()
    assert best is not None
    assert best[1].value == 0.81


def test_empty_archive_best_is_none() -> None:
    archive = DiversityArchive()
    assert archive.best() is None


__all__ = []

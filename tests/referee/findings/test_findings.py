"""Tests for `phos.referee.findings`: findings registry and regression suite (PART S8)."""

from __future__ import annotations

from pathlib import Path

import pytest

from phos.breaker.genome import (
    AttackGenome,
    AttackShape,
    AttackTechnique,
)
from phos.referee.findings import (
    Finding,
    FindingRegistry,
    FindingStatus,
    Severity,
    severity_for,
)
from phos.referee.findings.regression import generate_variants


def _genome() -> AttackGenome:
    return AttackGenome(
        technique=AttackTechnique.LEVEL_EXCURSION,
        target_tags=("tank_level",),
        start_time=100.0,
        duration=300.0,
        intensity=5.0,
        shape=AttackShape.STEP,
        layer="sensor",
    )


def _finding(
    *,
    source: str = "test-round",
    plant_spec_hash: str = "plant-abc",
    seed: int = 4242,
    family: str = "level_flow",
    attack_genome: AttackGenome | None = None,
    what_happened: str = "The level was nudged up and Atlas said nothing.",
    atlas_output: str = "no alerts raised",
    why_missed: str = "The departure stayed inside the per-signal band.",
    physical_harm: bool = True,
    stealthy: bool = True,
) -> Finding:
    return Finding.create(
        source=source,
        plant_spec_hash=plant_spec_hash,
        seed=seed,
        family=family,
        attack_genome=_genome() if attack_genome is None else attack_genome,
        what_happened=what_happened,
        atlas_output=atlas_output,
        why_missed=why_missed,
        physical_harm=physical_harm,
        stealthy=stealthy,
    )


def test_finding_create_sets_open_status() -> None:
    finding = _finding()
    assert finding.status == "open"
    assert len(finding.history) == 1
    assert finding.history[0]["status"] == "open"


def test_finding_id_is_deterministic_hash() -> None:
    a = _finding(seed=4242, source="round-1")
    b = _finding(seed=4242, source="round-1")
    assert a.id == b.id


def test_finding_id_changes_with_content() -> None:
    a = _finding(seed=4242)
    b = _finding(seed=4243)
    assert a.id != b.id


def test_registry_add_and_get(tmp_path: Path) -> None:
    registry = FindingRegistry(tmp_path)
    finding = _finding()
    registry.add(finding)
    got = registry.get(finding.id)
    assert got is not None
    assert got.id == finding.id


def test_registry_refuses_duplicate(tmp_path: Path) -> None:
    registry = FindingRegistry(tmp_path)
    finding = _finding()
    registry.add(finding)
    with pytest.raises(ValueError, match="already exists"):
        registry.add(finding)


def test_registry_list_open(tmp_path: Path) -> None:
    registry = FindingRegistry(tmp_path)
    open_finding = _finding()
    fixed_finding = _finding(seed=4243)
    registry.add(open_finding)
    registry.add(fixed_finding)
    registry.change_status(
        fixed_finding.id,
        FindingStatus.FIXED,
        "fixed by commit abc123",
        fixed_commit="abc123",
        generalisation=[{"variant": "level_excursion+10%", "detected": True}],
    )
    open_list = registry.list_open()
    assert len(open_list) == 1
    assert open_list[0].id == open_finding.id


def test_change_status_appends_history(tmp_path: Path) -> None:
    registry = FindingRegistry(tmp_path)
    finding = _finding()
    registry.add(finding)
    registry.change_status(
        finding.id,
        FindingStatus.FIXED,
        "fixed by detector update",
        fixed_commit="abc123",
        generalisation=[{"variant": "level+10%", "detected": True}],
    )
    got = registry.get(finding.id)
    assert got is not None
    assert got.status == "fixed"
    assert got.fixed_commit == "abc123"
    assert got.history[-1]["status"] == "fixed"
    assert len(got.history) == 2


def test_fixed_without_generalisation_becomes_narrowly(tmp_path: Path) -> None:
    registry = FindingRegistry(tmp_path)
    finding = _finding()
    registry.add(finding)
    registry.change_status(finding.id, FindingStatus.FIXED, "fixed only on exact case")
    got = registry.get(finding.id)
    assert got is not None
    assert got.status == "fixed narrowly"


def test_severity_labels() -> None:
    assert severity_for(True, True) == Severity.HARM_STEALTHY
    assert severity_for(True, False) == Severity.HARM_NOT_STEALTHY
    assert severity_for(False, True) == Severity.NO_HARM_STEALTHY
    assert severity_for(False, False) == Severity.NO_HARM_NOT_STEALTHY


def test_generate_variants_produces_different_genomes() -> None:
    genome = _genome()
    variants = generate_variants(genome, n_variants=3, seed=7)
    assert len(variants) == 3
    assert all(v is not genome for v in variants)
    for v in variants:
        # Variants should be valid genomes.
        from phos.breaker.genome import validate_genome

        validate_genome(v)


__all__ = []

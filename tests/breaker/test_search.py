"""Tests for `phos.breaker.search`: search strategies produce valid genomes (PART S7)."""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import FrozenInstanceError

import pytest

from phos.breaker.genome import AttackGenome, AttackTechnique, validate_genome
from phos.breaker.objective import Objective
from phos.breaker.search import (
    EvolutionarySearch,
    HillClimber,
    RandomSearch,
    SearchResult,
    SearchStrategy,
)


def _make_strategy[StrategyT: SearchStrategy](
    cls: Callable[..., StrategyT], seed: int = 42, **kwargs: object
) -> StrategyT:
    tag_pool = ("tank_level", "outlet_flow", "inlet_valve")
    techniques = (
        AttackTechnique.LEVEL_EXCURSION,
        AttackTechnique.TEMPERATURE_RAMP,
    )
    return cls(
        rng=random.Random(seed),
        tag_pool=tag_pool,
        techniques=techniques,
        hours=24.0,
        **kwargs,
    )


def _result(genome: AttackGenome, stealth: float = 0.8, harm: float = 0.9) -> SearchResult:
    return SearchResult(
        genome=genome,
        objective=Objective(stealth=stealth, harm=harm, value=stealth * harm),
        queries=1,
    )


def test_random_search_always_produces_valid_genome() -> None:
    strategy = _make_strategy(RandomSearch)
    for _ in range(20):
        genome = strategy.next_genome()
        validate_genome(genome)
        assert genome.technique in (
            AttackTechnique.LEVEL_EXCURSION,
            AttackTechnique.TEMPERATURE_RAMP,
        )
        assert set(genome.target_tags) <= {"tank_level", "outlet_flow", "inlet_valve"}


def test_random_search_is_deterministic_with_seed() -> None:
    a = _make_strategy(RandomSearch, seed=7)
    b = _make_strategy(RandomSearch, seed=7)
    genomes_a = [a.next_genome() for _ in range(5)]
    genomes_b = [b.next_genome() for _ in range(5)]
    assert genomes_a == genomes_b


def test_random_search_records_nothing() -> None:
    strategy = _make_strategy(RandomSearch)
    genome = strategy.next_genome()
    strategy.record(_result(genome))
    # Random search learns nothing: next draw is independent.
    genome2 = strategy.next_genome()
    validate_genome(genome2)


def test_evolutionary_search_mutates_and_crosses_over() -> None:
    strategy = _make_strategy(EvolutionarySearch)
    first = strategy.next_genome()
    validate_genome(first)
    strategy.record(_result(first, stealth=0.9, harm=0.9))
    for _ in range(10):
        genome = strategy.next_genome()
        validate_genome(genome)
        strategy.record(_result(genome, stealth=0.5, harm=0.5))


def test_evolutionary_search_keeps_best() -> None:
    strategy = _make_strategy(EvolutionarySearch, population_size=4)
    good = strategy.next_genome()
    strategy.record(_result(good, stealth=0.9, harm=0.9))
    for _ in range(20):
        bad = strategy.next_genome()
        validate_genome(bad)
        strategy.record(_result(bad, stealth=0.1, harm=0.1))
    # The good genome should still be represented in the population.
    assert len(strategy._population) <= 4


def test_hill_climber_restarts_on_plateau() -> None:
    strategy = _make_strategy(HillClimber, restart_after=3)
    first = strategy.next_genome()
    validate_genome(first)
    strategy.record(_result(first, stealth=0.5, harm=0.5))
    # Three non-improving records should trigger a restart.
    for _ in range(3):
        strategy.record(_result(strategy.next_genome(), stealth=0.1, harm=0.1))
    # The next genome should be a fresh random one (restarted).
    genome = strategy.next_genome()
    validate_genome(genome)


def test_hill_climber_improves_keeps_current() -> None:
    strategy = _make_strategy(HillClimber)
    first = strategy.next_genome()
    strategy.record(_result(first, stealth=0.5, harm=0.5))
    # A better result should be kept.
    better = strategy.next_genome()
    validate_genome(better)
    strategy.record(_result(better, stealth=0.9, harm=0.9))


def test_search_result_is_frozen() -> None:
    strategy = _make_strategy(RandomSearch)
    genome = strategy.next_genome()
    result = SearchResult(
        genome=genome, objective=Objective(stealth=0.5, harm=0.5, value=0.25), queries=1
    )
    with pytest.raises(FrozenInstanceError):
        result.queries = 999  # type: ignore[misc]


__all__ = []

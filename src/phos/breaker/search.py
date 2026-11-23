"""Search strategies behind one interface (PART S7).

Three strategies: random search, a hand-written evolutionary search (mutation, crossover,
tournament selection), and a hill climber with restarts. All use only the standard library
and numpy.
"""

from __future__ import annotations

import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from phos.breaker.genome import (
    AttackGenome,
    AttackShape,
    AttackTechnique,
    validate_genome,
)
from phos.breaker.objective import Objective


@dataclass(frozen=True)
class SearchResult:
    """One search attempt's outcome.

    Attributes:
        genome: What was tried.
        objective: The objective value.
        queries: How many queries this attempt used.
    """

    genome: AttackGenome
    objective: Objective
    queries: int


class SearchStrategy(ABC):
    """One way to search the attack space.

    Subclasses implement :meth:`next_genome` to propose the next candidate, and
    :meth:`record` to learn from the last result.
    """

    @abstractmethod
    def next_genome(self) -> AttackGenome:
        """Propose the next genome to try."""

    @abstractmethod
    def record(self, result: SearchResult) -> None:
        """Record the outcome of the last proposed genome."""


@dataclass
class RandomSearch(SearchStrategy):
    """Draw genomes uniformly at random from the valid space.

    Parameters:
        rng: A ``random.Random`` for determinism.
        tag_pool: Tags the attacker may target.
        techniques: Techniques allowed (held-out techniques are excluded by the caller).
        hours: How long the plant run is, to bound start_time.
    """

    rng: random.Random
    tag_pool: tuple[str, ...]
    techniques: tuple[AttackTechnique, ...]
    hours: float
    _attempts: int = field(default=0, init=False)

    def next_genome(self) -> AttackGenome:
        """Draw the next genome uniformly at random from the valid space."""
        technique = self.rng.choice(self.techniques)
        tag_count = self.rng.randint(1, min(3, len(self.tag_pool)))
        targets = tuple(self.rng.sample(self.tag_pool, tag_count))
        start = self.rng.uniform(0.0, max(0.0, self.hours * 3600.0 - 3600.0))
        duration = self.rng.uniform(300.0, 3600.0)
        intensity = self.rng.uniform(0.1, 10.0)
        shape = self.rng.choice(list(AttackShape))
        layer = self.rng.choice(("sensor", "actuator", "network"))
        genome = AttackGenome(
            technique=technique,
            target_tags=targets,
            start_time=start,
            duration=duration,
            intensity=intensity,
            shape=shape,
            layer=layer,
        )
        validate_genome(genome)
        self._attempts += 1
        return genome

    def record(self, result: SearchResult) -> None:
        """Random search learns nothing: every draw is independent."""


@dataclass
class _Individual:
    genome: AttackGenome
    fitness: float


@dataclass
class EvolutionarySearch(SearchStrategy):
    """Hand-written evolutionary search: mutation, crossover, tournament selection.

    Parameters:
        rng: A ``random.Random`` for determinism.
        tag_pool: Tags the attacker may target.
        techniques: Techniques allowed.
        hours: How long the plant run is.
        population_size: How many individuals carry over between rounds.
        mutation_rate: Probability of mutating a genome component.
        crossover_rate: Probability of crossing two parents.
    """

    rng: random.Random
    tag_pool: tuple[str, ...]
    techniques: tuple[AttackTechnique, ...]
    hours: float
    population_size: int = 8
    mutation_rate: float = 0.3
    crossover_rate: float = 0.3

    _population: list[_Individual] = field(default_factory=list, init=False)
    _evaluated: int = field(default=0, init=False)

    def next_genome(self) -> AttackGenome:
        """Propose the next genome via mutation, crossover, or random draw."""
        if not self._population:
            return self._random_genome()
        if self.rng.random() < self.crossover_rate and len(self._population) >= 2:
            parent_a, parent_b = self._tournament(), self._tournament()
            return self._crossover(parent_a.genome, parent_b.genome)
        return self._mutate(self._tournament().genome)

    def record(self, result: SearchResult) -> None:
        """Record the outcome: keep the best individuals in the population."""
        self._evaluated += 1
        individual = _Individual(genome=result.genome, fitness=result.objective.value)
        if len(self._population) < self.population_size:
            self._population.append(individual)
        else:
            worst = min(self._population, key=lambda ind: ind.fitness)
            if individual.fitness > worst.fitness:
                self._population.remove(worst)
                self._population.append(individual)

    def _random_genome(self) -> AttackGenome:
        technique = self.rng.choice(self.techniques)
        tag_count = self.rng.randint(1, min(3, len(self.tag_pool)))
        targets = tuple(self.rng.sample(self.tag_pool, tag_count))
        start = self.rng.uniform(0.0, max(0.0, self.hours * 3600.0 - 3600.0))
        duration = self.rng.uniform(300.0, 3600.0)
        intensity = self.rng.uniform(0.1, 10.0)
        shape = self.rng.choice(list(AttackShape))
        layer = self.rng.choice(("sensor", "actuator", "network"))
        genome = AttackGenome(
            technique=technique,
            target_tags=targets,
            start_time=start,
            duration=duration,
            intensity=intensity,
            shape=shape,
            layer=layer,
        )
        validate_genome(genome)
        return genome

    def _tournament(self) -> _Individual:
        contenders = self.rng.sample(self._population, min(3, len(self._population)))
        return max(contenders, key=lambda ind: ind.fitness)

    def _mutate(self, genome: AttackGenome) -> AttackGenome:
        tags = list(genome.target_tags)
        if self.rng.random() < self.mutation_rate:
            if self.rng.random() < 0.5 and len(tags) < len(self.tag_pool):
                new_tag = self.rng.choice([t for t in self.tag_pool if t not in tags])
                tags.append(new_tag)
            elif len(tags) > 1:
                tags.pop(self.rng.randrange(len(tags)))
        # Always keep at least one tag.
        if not tags:
            tags = [self.rng.choice(self.tag_pool)]
        start = genome.start_time
        if self.rng.random() < self.mutation_rate:
            start = self.rng.uniform(0.0, max(0.0, self.hours * 3600.0 - 3600.0))
        duration = genome.duration
        if self.rng.random() < self.mutation_rate:
            duration = self.rng.uniform(300.0, 3600.0)
        intensity = genome.intensity
        if self.rng.random() < self.mutation_rate:
            intensity = self.rng.uniform(0.1, 10.0)
        shape = genome.shape
        if self.rng.random() < self.mutation_rate:
            shape = self.rng.choice(list(AttackShape))
        layer = genome.layer
        if self.rng.random() < self.mutation_rate:
            layer = self.rng.choice(("sensor", "actuator", "network"))
        return AttackGenome(
            technique=genome.technique,
            target_tags=tuple(tags),
            start_time=start,
            duration=duration,
            intensity=intensity,
            shape=shape,
            layer=layer,
        )

    def _crossover(self, a: AttackGenome, b: AttackGenome) -> AttackGenome:
        tags = tuple(sorted(set(a.target_tags) | set(b.target_tags))[: min(3, len(self.tag_pool))])
        return AttackGenome(
            technique=self.rng.choice((a.technique, b.technique)),
            target_tags=tags,
            start_time=self.rng.uniform(a.start_time, b.start_time)
            if a.start_time != b.start_time
            else a.start_time,
            duration=self.rng.uniform(a.duration, b.duration)
            if a.duration != b.duration
            else a.duration,
            intensity=self.rng.uniform(a.intensity, b.intensity)
            if a.intensity != b.intensity
            else a.intensity,
            shape=self.rng.choice((a.shape, b.shape)),
            layer=self.rng.choice((a.layer, b.layer)),
        )


@dataclass
class HillClimber(SearchStrategy):
    """Hill climber with restarts: start from a random point, mutate uphill, restart on plateau.

    Parameters:
        rng: A ``random.Random`` for determinism.
        tag_pool: Tags the attacker may target.
        techniques: Techniques allowed.
        hours: How long the plant run is.
        restart_after: How many non-improving steps before a restart.
    """

    rng: random.Random
    tag_pool: tuple[str, ...]
    techniques: tuple[AttackTechnique, ...]
    hours: float
    restart_after: int = 10

    _current: AttackGenome | None = field(default=None, init=False)
    _current_fitness: float = field(default=0.0, init=False)
    _steps_since_improvement: int = field(default=0, init=False)

    def next_genome(self) -> AttackGenome:
        """Propose the next genome: a mutation of the current, or a restart."""
        if self._current is None:
            self._current = self._random_genome()
            self._current_fitness = 0.0
            self._steps_since_improvement = 0
            return self._current
        if self._steps_since_improvement >= self.restart_after:
            self._current = self._random_genome()
            self._current_fitness = 0.0
            self._steps_since_improvement = 0
            return self._current
        return self._mutate(self._current)

    def record(self, result: SearchResult) -> None:
        """Record the outcome: keep the current genome if it improved."""
        if result.objective.value > self._current_fitness:
            self._current = result.genome
            self._current_fitness = result.objective.value
            self._steps_since_improvement = 0
        else:
            self._steps_since_improvement += 1

    def _random_genome(self) -> AttackGenome:
        technique = self.rng.choice(self.techniques)
        tag_count = self.rng.randint(1, min(3, len(self.tag_pool)))
        targets = tuple(self.rng.sample(self.tag_pool, tag_count))
        start = self.rng.uniform(0.0, max(0.0, self.hours * 3600.0 - 3600.0))
        duration = self.rng.uniform(300.0, 3600.0)
        intensity = self.rng.uniform(0.1, 10.0)
        shape = self.rng.choice(list(AttackShape))
        layer = self.rng.choice(("sensor", "actuator", "network"))
        return AttackGenome(
            technique=technique,
            target_tags=targets,
            start_time=start,
            duration=duration,
            intensity=intensity,
            shape=shape,
            layer=layer,
        )

    def _mutate(self, genome: AttackGenome) -> AttackGenome:
        # Small perturbations around the current point.
        tags = list(genome.target_tags)
        if self.rng.random() < 0.5:
            if self.rng.random() < 0.5 and len(tags) < len(self.tag_pool):
                new_tag = self.rng.choice([t for t in self.tag_pool if t not in tags])
                tags.append(new_tag)
            elif len(tags) > 1:
                tags.pop(self.rng.randrange(len(tags)))
        # Always keep at least one tag.
        if not tags:
            tags = [self.rng.choice(self.tag_pool)]
        start = max(0.0, genome.start_time + self.rng.uniform(-300.0, 300.0))
        duration = max(300.0, genome.duration + self.rng.uniform(-300.0, 300.0))
        intensity = max(0.1, genome.intensity + self.rng.uniform(-1.0, 1.0))
        shape = genome.shape if self.rng.random() < 0.8 else self.rng.choice(list(AttackShape))
        layer = (
            genome.layer
            if self.rng.random() < 0.8
            else self.rng.choice(("sensor", "actuator", "network"))
        )
        return AttackGenome(
            technique=genome.technique,
            target_tags=tuple(tags),
            start_time=start,
            duration=duration,
            intensity=intensity,
            shape=shape,
            layer=layer,
        )


__all__ = [
    "EvolutionarySearch",
    "HillClimber",
    "RandomSearch",
    "SearchResult",
    "SearchStrategy",
]

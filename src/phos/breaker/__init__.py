"""The breaker: adaptive attack search against Atlas as a black box (PART S7).

This package studies Atlas through the referee's ``QueryInterface`` and searches for simulated
attacks that slip past it. It never imports Atlas, the referee internals, or anything that
exposes Atlas's rules, thresholds or model parameters.

**Hard rules from PART S0, all still in force:**
- Everything is simulated and offline. Nothing touches real devices or networks.
- The breaker runs only on development seeds (``PHOS_SEEDS_DEV``).
- The breaker never sees sealed generator families.
- Determinism: a fixed seed makes every run reproducible.
"""

from __future__ import annotations

from phos.breaker.archive import DiversityArchive
from phos.breaker.genome import AttackGenome, AttackShape, AttackTechnique, validate_genome
from phos.breaker.objective import Objective, objective_version
from phos.breaker.search import (
    EvolutionarySearch,
    HillClimber,
    RandomSearch,
    SearchResult,
    SearchStrategy,
)

__all__ = [
    "AttackGenome",
    "AttackShape",
    "AttackTechnique",
    "DiversityArchive",
    "EvolutionarySearch",
    "HillClimber",
    "Objective",
    "RandomSearch",
    "SearchResult",
    "SearchStrategy",
    "objective_version",
    "validate_genome",
]

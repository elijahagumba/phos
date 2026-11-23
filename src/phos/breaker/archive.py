"""Diversity archive of successful attacks (PART S7).

Keeps distinct successful attacks, distinguished by technique and parameter region — not just
the single best. Reports coverage of the attack space.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from phos.breaker.genome import AttackGenome
from phos.breaker.objective import Objective


@dataclass
class DiversityArchive:
    """Stores successful attacks, keyed by (technique, parameter region).

    A parameter region is a coarse binning of start_time, duration and intensity so that
    attacks in the same region are treated as variants of one another.
    """

    entries: dict[tuple[str, str, str, str], list[tuple[AttackGenome, Objective]]] = field(
        default_factory=dict
    )

    def add(self, genome: AttackGenome, objective: Objective) -> bool:
        """Record a successful attack. Returns True if it added a new region."""
        key = self._region(genome)
        bucket = self.entries.setdefault(key, [])
        # Keep only the best per region; if this one is better, replace the worst.
        if not bucket or objective.value > max(o.value for _, o in bucket):
            if len(bucket) >= 5:
                bucket.pop(min(range(len(bucket)), key=lambda i: bucket[i][1].value))
            bucket.append((genome, objective))
            return True
        return False

    def regions(self) -> int:
        """How many distinct parameter regions have at least one success."""
        return len(self.entries)

    def techniques(self) -> set[str]:
        """Which techniques have at least one recorded success."""
        return {key[0] for key in self.entries}

    def best(self) -> tuple[AttackGenome, Objective] | None:
        """The single best attack across all regions, or None."""
        best: tuple[AttackGenome, Objective] | None = None
        for bucket in self.entries.values():
            for genome, objective in bucket:
                if best is None or objective.value > best[1].value:
                    best = (genome, objective)
        return best

    def _region(self, genome: AttackGenome) -> tuple[str, str, str, str]:
        start_bin = int(genome.start_time // 1800)  # 30-minute bins
        duration_bin = int(genome.duration // 600)  # 10-minute bins
        intensity_bin = int(genome.intensity)  # integer bins
        return (genome.technique.value, str(start_bin), str(duration_bin), str(intensity_bin))


__all__ = ["DiversityArchive"]

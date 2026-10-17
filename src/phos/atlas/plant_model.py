"""The graded plant model: every link carries the evidence for it (ADR 0130, ADR 0133).

The statistical map (`phos.atlas.plant_map`) learns links from co-movement and detects well, but
cannot say which links are the plant's (ADR 0129). This module grades each pair of signals by the
strongest evidence for it:

- **A, declared:** the documentation states it (a role file's loop, from a reading or a setpoint
  to the actuators it moves, or a declared coupling), and the map does not contradict it: it has
  the link the same way round, or no link the other way.
- **B, intervened:** a logged change propagated to it (`phos.atlas.interventions`).
- **C, network-observed:** a controller's own traffic shows it (`phos.atlas.network_links`).
- **D, stable:** the map learns it from each of two disjoint halves of training, at lags within
  one grid step of each other.

A to C is evidence an engineer would accept from a colleague. **The trusted map** is the map
refitted with each target allowed only its A to C drivers; naming and reconstruction run on it, and
a target with no A to C driver has no model, so Atlas says it cannot place that reading. Detection
keeps the full map. D corroborates and is reported, never used to name.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum

from phos.atlas.consistency import TrainFile
from phos.atlas.interventions import IntervenedLink
from phos.atlas.network_links import NetworkClaim
from phos.atlas.plant_map_fit import fit_map
from phos.atlas.plant_map_model import DEFAULT_SETTINGS, MapSettings, PlantMap
from phos.atlas.signal_roles import SignalRoles

__all__ = [
    "Grade",
    "GradedLink",
    "declared_pairs",
    "grade_links",
    "halves",
    "intervened_pairs",
    "learned_pairs",
    "network_pairs",
    "stable_pairs",
    "trusted_drivers",
    "trusted_map",
]

Pair = tuple[str, str]


class Grade(str, Enum):
    """How Atlas knows a link, strongest first."""

    DECLARED = "A"
    INTERVENED = "B"
    NETWORK = "C"
    STABLE = "D"


#: The grades naming and reconstruction may stand on.
TRUSTED = (Grade.DECLARED, Grade.INTERVENED, Grade.NETWORK)


@dataclass(frozen=True)
class GradedLink:
    """One learned link and every grade of evidence for it; none means rejected."""

    driver: str
    target: str
    grades: tuple[Grade, ...]

    @property
    def best(self) -> Grade | None:
        """The strongest grade, or ``None`` for a link with no evidence beyond fitting once."""
        return min(self.grades, key=lambda g: "ABCD".index(g.value)) if self.grades else None


def learned_pairs(plant: PlantMap) -> dict[Pair, tuple[int, ...]]:
    """Every (driver, target) the map learned, with its lags in samples."""
    return {
        (plant.names[link.driver], plant.names[target]): link.lags
        for target, model in plant.targets.items()
        for link in model.links
    }


def declared_pairs(roles: SignalRoles, couplings: Iterable[Pair] = ()) -> frozenset[Pair]:
    """Each declared loop's reading and setpoint to its outputs, and any declared couplings."""
    pairs = set(couplings)
    for loop in roles.loops:
        for source in (loop.reading, loop.setpoint):
            if source is not None:
                pairs.update((source, output) for output in loop.outputs)
    return frozenset(pairs)


def intervened_pairs(links: Iterable[IntervenedLink]) -> frozenset[Pair]:
    """Grade B's pairs."""
    return frozenset((link.driver, link.driven) for link in links)


def network_pairs(claims: Iterable[NetworkClaim]) -> frozenset[Pair]:
    """Grade C's pairs: the narrowed actuator where one is known, else every one in the set."""
    pairs: set[Pair] = set()
    for claim in claims:
        outputs = (claim.narrowed,) if claim.narrowed else claim.actuators
        pairs.update((claim.point, output) for output in outputs)
    return frozenset(pairs)


def halves(train: Sequence[TrainFile]) -> tuple[list[TrainFile], list[TrainFile]]:
    """Two disjoint halves: alternate files when there are several, else the one file split."""
    if len(train) >= 2:
        return list(train[0::2]), list(train[1::2])
    (only,) = train
    middle = only.values.shape[0] // 2
    return (
        [TrainFile(values=only.values[:middle], attack=only.attack[:middle])],
        [TrainFile(values=only.values[middle:], attack=only.attack[middle:])],
    )


def stable_pairs(first: PlantMap, second: PlantMap) -> frozenset[Pair]:
    """Pairs both maps learn, at lags within one step of the lag grid (ADR 0123 §9.6's test)."""
    grid = first.lags
    one, two = learned_pairs(first), learned_pairs(second)

    def steps(a: tuple[int, ...], b: tuple[int, ...]) -> int:
        return min(abs(grid.index(x) - grid.index(y)) for x in a for y in b)

    return frozenset(p for p in set(one) & set(two) if steps(one[p], two[p]) <= 1)


def trusted_drivers(
    plant: PlantMap,
    declared: frozenset[Pair],
    intervened: frozenset[Pair] = frozenset(),
    network: frozenset[Pair] = frozenset(),
) -> dict[str, frozenset[str]]:
    """Per target, its A to C drivers. A declared pair the map learned only reversed is dropped."""
    learned = set(learned_pairs(plant))
    allowed: dict[str, set[str]] = {}
    for driver, target in declared:
        contradicted = (target, driver) in learned and (driver, target) not in learned
        if not contradicted:
            allowed.setdefault(target, set()).add(driver)
    for driver, target in intervened | network:
        allowed.setdefault(target, set()).add(driver)
    return {target: frozenset(drivers) for target, drivers in allowed.items()}


def grade_links(
    plant: PlantMap,
    declared: frozenset[Pair],
    intervened: frozenset[Pair] = frozenset(),
    network: frozenset[Pair] = frozenset(),
    stable: frozenset[Pair] = frozenset(),
) -> tuple[GradedLink, ...]:
    """Every link the full map learned, with its grades, in (target, driver) order."""
    trusted = trusted_drivers(plant, declared, intervened, network)
    out: list[GradedLink] = []
    for driver, target in sorted(learned_pairs(plant), key=lambda p: (p[1], p[0])):
        pair = (driver, target)
        grades: list[Grade] = []
        if pair in declared and driver in trusted.get(target, frozenset()):
            grades.append(Grade.DECLARED)
        if pair in intervened:
            grades.append(Grade.INTERVENED)
        if pair in network:
            grades.append(Grade.NETWORK)
        if pair in stable:
            grades.append(Grade.STABLE)
        out.append(GradedLink(driver, target, tuple(grades)))
    return tuple(out)


def trusted_map(
    train: Sequence[TrainFile],
    names: Sequence[str],
    roles: SignalRoles,
    period_seconds: float,
    allowed: Mapping[str, frozenset[str]],
    settings: MapSettings = DEFAULT_SETTINGS,
) -> PlantMap:
    """The map refitted on A to C drivers only; a target with none has no model, unplaceable."""
    return fit_map(train, names, roles, period_seconds, settings, allowed=allowed)

"""Running a plant: which plants exist, and what a completed run holds.

One entry point, `run_plant`, and one result type, `PlantRun`. Everything downstream — telemetry,
capture, topology, manifest — is a projection of that result, so a run is simulated exactly once
however many outputs are taken from it. That matters beyond tidiness: the capture answers polls
with the *same reported readings* the telemetry publishes, so the two outputs of one run cannot
disagree about what the plant said.

**The registry is the seam D2 and D3 come in through.** They name a plant by identifier and hand
over a spec and, later, an injection. Adding a plant is one entry here and a module in
`phos.synth.plants`; nothing else changes.
"""

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Final, Protocol

from phos.synth.command import CommandSource
from phos.synth.injection import Injection
from phos.synth.plant import BenignEvent, Plant, PlantDescription, PlantStep, RunSpec
from phos.synth.plants import BatchReactorPlant, PowerGenerationPlant, WaterTreatmentPlant
from phos.synth.realism import RealismPlan, RealismProfile


class _PlantFactory(Protocol):
    """How every plant constructor is spelled, so the registry can name one type."""

    def __call__(
        self,
        spec: RunSpec,
        *,
        commands: CommandSource | None = ...,
        realism: RealismProfile | None = ...,
    ) -> Plant:
        """Construct the plant for ``spec``."""


__all__ = [
    "PLANT_FACTORIES",
    "PLANT_IDS",
    "PlantRun",
    "build_plant",
    "run_plant",
]

logger = logging.getLogger(__name__)

PLANT_FACTORIES: Final[Mapping[str, _PlantFactory]] = {
    "water-treatment": WaterTreatmentPlant,
    "power-generation": PowerGenerationPlant,
    "batch-reactor": BatchReactorPlant,
}
"""Every plant the synthetic engine can build, by identifier."""

PLANT_IDS: Final = tuple(sorted(PLANT_FACTORIES))
"""The known plant identifiers, sorted so error messages and listings are stable."""


@dataclass(frozen=True)
class PlantRun:
    """A completed simulation: every sample, and everything needed to describe it.

    Attributes:
        plant_id: Which plant was run.
        description: The plant's declaration — signals, units, couplings, control network.
        spec: The run that was simulated. With ``plant_id`` this is the whole of what has to be
            kept to regenerate the run exactly.
        steps: Every sample, in time order.
        events: The benign operational events the run contained, in time order. Part of the ground
            truth D2 and D3 receive: a detection landing here landed on a Tuesday morning, not on
            an attack.
        realism_profile: The profile the plant was given. Quiet by default. Not serialised into
            the manifest — a field there would have changed every existing corpus.
        realism: The planned phenomena, faults, drifts and dropouts. Empty under a quiet profile.
            Ground truth for a sidecar, never an input to Atlas.
    """

    plant_id: str
    description: PlantDescription
    spec: RunSpec
    steps: tuple[PlantStep, ...]
    events: tuple[BenignEvent, ...]
    realism_profile: RealismProfile = field(default_factory=RealismProfile)
    realism: RealismPlan = field(default_factory=lambda: RealismPlan((), (), (), (), {}))

    @property
    def timestamps(self) -> tuple[datetime, ...]:
        """The instant of every sample, in order."""
        return tuple(step.timestamp for step in self.steps)

    @property
    def command_count(self) -> int:
        """How many control-network exchanges the run generated. Zero without a network."""
        return sum(len(step.commands) for step in self.steps)

    def reported(self, key: str) -> list[float]:
        """Return one signal's reported series.

        Raises:
            KeyError: If the plant declares no such signal.
        """
        self.description.signal(key)
        return [step.report.values[key] for step in self.steps]

    def true_values(self, key: str) -> list[float]:
        """Return one signal's true series — ground truth, never published as telemetry.

        Raises:
            KeyError: If the plant declares no such signal.
        """
        self.description.signal(key)
        return [step.truth.values[key] for step in self.steps]


def build_plant(
    plant_id: str,
    spec: RunSpec,
    commands: CommandSource | None = None,
    realism: RealismProfile | None = None,
) -> Plant:
    """Construct a plant by identifier.

    Args:
        plant_id: One of `PLANT_IDS`.
        spec: The run to prepare for.
        commands: Who writes to this plant over its control network, or ``None`` for the legacy
            path where a benign event's writes are echoed onto the wire after the fact. Passing a
            source makes writes causal — see `phos.synth.plant.Plant`.
        realism: Ordinary trouble to apply, or ``None`` for a quiet profile. ``None`` and a quiet
            `RealismProfile()` are byte-identical.

    Returns:
        The constructed plant, ready to be stepped.

    Raises:
        KeyError: If no such plant exists. The message names the ones that do, because a typo
            here would otherwise surface as a missing dataset much later.
    """
    factory = PLANT_FACTORIES.get(plant_id)
    if factory is None:
        raise KeyError(f"no plant {plant_id!r}; phos.synth builds {', '.join(PLANT_IDS)}")
    return factory(spec, commands=commands, realism=realism)


def run_plant(
    plant_id: str,
    spec: RunSpec,
    injection: Injection | None = None,
    commands: CommandSource | None = None,
    realism: RealismProfile | None = None,
) -> PlantRun:
    """Simulate a plant for a whole run and return every sample.

    Args:
        plant_id: One of `PLANT_IDS`.
        spec: How long to run, how often to sample, and from what seed.
        injection: A manipulation to apply, or ``None`` for normal operation. D1 generates no
            attacks; the parameter exists because the hook has to be reachable from the same
            entry point D2 will use, and because leaving it out would mean D2 running plants
            through a different path than the one D1 tested.

        commands: Who writes over the control network, or ``None`` for the legacy echo path.
        realism: Ordinary trouble to apply, or ``None`` for a quiet profile.

    Returns:
        The completed run.

    Raises:
        KeyError: If no such plant exists, or if the injection names something the plant does not
            declare.
    """
    plant = build_plant(plant_id, spec, commands, realism)
    steps = tuple(plant.step(injection) for _ in range(spec.n_steps))
    logger.debug(
        "ran %s for %d samples from seed %d (%d events, %d commands)",
        plant_id,
        len(steps),
        spec.seed,
        len(plant.events),
        sum(len(step.commands) for step in steps),
    )
    return PlantRun(
        plant_id=plant_id,
        description=plant.description,
        spec=spec,
        steps=steps,
        events=plant.events,
        realism_profile=plant._realism_profile,
        realism=plant._realism,
    )

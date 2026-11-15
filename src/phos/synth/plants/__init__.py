"""The simulated plants: three processes, three industries, three notions of normal.

Variety here is behavioural rather than numerical. Three near-identical continuous processes with
different column names would prove nothing about an engine that learns "normal", so each plant is
chosen for a *rhythm* the others do not have:

- `water.WaterTreatmentPlant` — continuous, paced by a city's diurnal demand, with slow
  accumulating state (a filter fouling between backwashes) and a long transport delay between a
  dose and its effect.
- `power.PowerGenerationPlant` — continuous and much faster, a machine following load second by
  second, where the coupling that matters is an electrical identity rather than a mixing lag.
- `batch.BatchReactorPlant` — not continuous at all. It cycles through charge, heat, react and
  discharge, so its "normal" is a *sequence*, and the same reading is ordinary in one phase and
  impossible in another.

Every plant declares its own couplings, its own topology and its own model source. What they
share is `phos.synth.plant.Plant`, which owns the true-state record, the injection points and the
randomness discipline, so none of them can quietly do those differently.

**Two of the three speak Modbus, and the third's silence is the honest answer rather than a gap.**
Water treatment and power generation are commonly run over Modbus/TCP, so those plants emit
control traffic. A jacketed batch reactor is typically run from a DCS over a fieldbus Atlas cannot
dissect, so `batch` declares no control network and produces telemetry only. Inventing Modbus for
it would be fake realism, and the asymmetry is useful: it gives D3 a plant where Atlas is deaf to
commands by construction rather than by accident.

**PART R2 adds a second kind of module here, and the distinction matters.** `water`, `power` and
`batch` are *plants*: each is one works, and a seed never gives it a second clearwell.
`level_flow` and the modules beside it are *processes* — physics a spec sizes, shapes and tunes —
each paired with a `_family` module that turns a master seed into one plant of that kind. A
process has no canonical instance, which is why building one without a spec is refused rather
than defaulted.

Importing this package registers every process template and every open family, which is what
`phos.synth.templates` and `phos.synth.families` rely on when they are asked for one. Sealed
families are not here; they live in `phos.synth.families_sealed` and load only when the
environment allows it.
"""

from phos.synth.plants.batch import BatchReactorPlant
from phos.synth.plants.batch_mix import BatchMixPlant
from phos.synth.plants.batch_mix_family import BatchMixFamily
from phos.synth.plants.generation import GenerationPlant
from phos.synth.plants.generation_family import PowerFamily
from phos.synth.plants.heated_chain import HeatedChainPlant
from phos.synth.plants.heated_chain_family import HybridFamily
from phos.synth.plants.level_flow import LevelFlowPlant
from phos.synth.plants.level_flow_family import LevelFlowFamily
from phos.synth.plants.power import PowerGenerationPlant
from phos.synth.plants.thermal import ThermalPlant
from phos.synth.plants.thermal_family import ThermalFamily
from phos.synth.plants.water import WaterTreatmentPlant

__all__ = [
    "BatchMixFamily",
    "BatchMixPlant",
    "BatchReactorPlant",
    "GenerationPlant",
    "HeatedChainPlant",
    "HybridFamily",
    "LevelFlowFamily",
    "LevelFlowPlant",
    "PowerFamily",
    "PowerGenerationPlant",
    "ThermalFamily",
    "ThermalPlant",
    "WaterTreatmentPlant",
]

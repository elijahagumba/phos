"""Gate 1's fit-history safeguard: refuse a U3 diagnostic whose declared-normal history is short.

U1 measured the fit-length artefact as the dominant driver of Atlas alert volume on HAI. A fit
shorter than the slowest cycle a scenario's signals actually have makes every scenario read the
same, so the environment would measure the artefact instead of the scenarios. Gate 1 (2026-09-11)
bound U3 to give Atlas enough declared-normal history. This module enforces that as a property.

**Derivation, from declared periods, not from a threshold that separates scenarios.**

Every plant draws a per-instrument calibration-drift period from
`phos.synth.plant.DRIFT_PERIOD_HOURS` = (48, 120). That range's upper bound is therefore a
declared cycle of every signal on every plant.

Water treatment additionally declares:

- city demand on 24 h and 12 h cycles (`WaterTreatmentPlant._demand`);
- raw turbidity on 72 h and 24 h cycles (`WaterTreatmentPlant._raw_turbidity`).

Power generation additionally declares:

- grid demand on a 24 h cycle plus an 8 h, three-shift pattern (`PowerGenerationPlant._demand`);
- power factor and ambient temperature on 24 h cycles.

The batch reactor's declared timers (idle 900 s, a full charge at 5400 kg/h into a 4500 kg
target, a 5400 s hold, a discharge at 7200 kg/h) sum to 3.2083 h; heat-up is not a fixed
duration. Instrument drift at 120 h is slower than any of those, and slower than water's 72 h
turbidity wander, so **the required history is 120 h on every plant**, named as the instrument
calibration-drift period. The committed power-generation train is 48 h and would be refused as a
U3 fit; U3 generates its own 120 h stretch rather than reusing that corpus.

Never pick a number because it makes a scenario look different. The 120 h figure is the upper
bound of a range the plant already draws from.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from typing import Final

from phos.synth.plant import DRIFT_PERIOD_HOURS
from phos.synth.plants import batch as batch_plant
from phos.synth.run import PLANT_IDS

__all__ = [
    "DeclaredCycle",
    "FitHistoryTooShortError",
    "assert_fit_history",
    "declared_cycles",
    "required_fit_history",
]


@dataclass(frozen=True)
class DeclaredCycle:
    """One declared period a plant's signals actually have.

    Attributes:
        name: What the cycle is, for the refusal message.
        hours: Its period, in hours.
        plant_id: Which plant declares it.
    """

    name: str
    hours: float
    plant_id: str


class FitHistoryTooShortError(ValueError):
    """Raised when a U3 diagnostic would fit Atlas on less history than the slowest cycle."""


_WATER_CYCLES: Final = (
    DeclaredCycle("city demand (daily)", 24.0, "water-treatment"),
    DeclaredCycle("city demand (half-daily)", 12.0, "water-treatment"),
    DeclaredCycle("raw turbidity (slow wander)", 72.0, "water-treatment"),
    DeclaredCycle("raw turbidity (daily)", 24.0, "water-treatment"),
)
_POWER_CYCLES: Final = (
    DeclaredCycle("grid demand (daily)", 24.0, "power-generation"),
    DeclaredCycle("shift load (three-shift)", 8.0, "power-generation"),
    DeclaredCycle("power factor (daily)", 24.0, "power-generation"),
    DeclaredCycle("ambient temperature (daily)", 24.0, "power-generation"),
)

_BATCH_TIMER_HOURS: Final = (
    batch_plant._IDLE_SECONDS / 3600.0
    + batch_plant._FULL_CHARGE_KG / batch_plant._MAX_FEED_KGPH
    + batch_plant._DEFAULT_HOLD_S / 3600.0
    + batch_plant._FULL_CHARGE_KG / batch_plant._DISCHARGE_KGPH
)
_BATCH_CYCLES: Final = (
    DeclaredCycle(
        "declared batch timers (idle + charge + hold + discharge; heat-up unfixed)",
        _BATCH_TIMER_HOURS,
        "batch-reactor",
    ),
)

_BY_PLANT: Final[Mapping[str, tuple[DeclaredCycle, ...]]] = {
    "water-treatment": _WATER_CYCLES,
    "power-generation": _POWER_CYCLES,
    "batch-reactor": _BATCH_CYCLES,
}


def declared_cycles(plant_id: str) -> tuple[DeclaredCycle, ...]:
    """Return every declared cycle of ``plant_id``, including instrument calibration drift.

    Raises:
        KeyError: If ``plant_id`` is not a registered plant.
    """
    if plant_id not in PLANT_IDS:
        raise KeyError(f"no plant {plant_id!r}; phos.synth builds {', '.join(PLANT_IDS)}")
    drift = DeclaredCycle(
        "instrument calibration-drift period (range upper bound)",
        DRIFT_PERIOD_HOURS[1],
        plant_id,
    )
    return (*_BY_PLANT[plant_id], drift)


def required_fit_history(plant_id: str) -> DeclaredCycle:
    """Return the slowest declared cycle Atlas must see as declared-normal history."""
    cycles = declared_cycles(plant_id)
    return max(cycles, key=lambda cycle: cycle.hours)


def assert_fit_history(plant_id: str, history: timedelta) -> None:
    """Refuse a U3 diagnostic whose fit history is shorter than the slowest declared cycle.

    Args:
        plant_id: Which plant Atlas would be fitted on.
        history: How much declared-normal history the fit would see.

    Raises:
        FitHistoryTooShortError: If ``history`` is shorter than the slowest cycle. The message
            names that cycle.
        KeyError: If ``plant_id`` is not a registered plant.
    """
    slowest = required_fit_history(plant_id)
    hours = history.total_seconds() / 3600.0
    if hours < slowest.hours:
        raise FitHistoryTooShortError(
            f"U3 diagnostic fit history is {hours:.4f} h, shorter than the slowest declared "
            f"cycle of {plant_id}: {slowest.name} ({slowest.hours:g} h). A fit that does not "
            f"cover that cycle measures the fit-length artefact U1 named, not the scenario. "
            f"Gate 1 (2026-09-11)."
        )

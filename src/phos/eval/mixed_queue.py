"""The mixed-queue generator declared in ADR 0231. It does not run a plant.

Each scored seed is one 8-hour shift. Quiet training is seed 97001 for 24 hours.
Plants cycle water, power, batch. Windows are the plant's sample period and are
not chosen here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final

from phos.atlas.sensor_explainer import HOLD_SHARE
from phos.eval.build_declaration import (
    BUILD_DEVELOPMENT_SEEDS,
    QUEUE_DEVELOPMENT_SEEDS,
    QUEUE_HELD_BACK_SEEDS,
)
from phos.synth.injection import TimeWindow
from phos.synth.maintenance import MaintenanceKind, WorkOrder
from phos.synth.plant import RunSpec

__all__ = [
    "ATTACK_HOURS",
    "JOBS",
    "QUIET_TRAIN_HOURS",
    "QUIET_TRAIN_SEED",
    "SHIFT_HOURS",
    "SHIFT_START",
    "WORK_ORDER_HOURS",
    "PlantJob",
    "attack_window",
    "hold_value",
    "job_for_seed",
    "run_spec",
    "work_order_for",
]

SHIFT_START: Final = datetime(2026, 10, 1, tzinfo=UTC)
"""First sample of every mixed-queue run, train and test."""

SHIFT_HOURS: Final = 8
QUIET_TRAIN_HOURS: Final = 24
QUIET_TRAIN_SEED: Final = BUILD_DEVELOPMENT_SEEDS[0]
"""Seed 97001. A held-back seed is never the training seed."""

WORK_ORDER_HOURS: Final[tuple[int, int]] = (1, 5)
"""Inclusive hour-of-shift bounds of the sanctioning routine order."""

ATTACK_HOURS: Final[tuple[int, int]] = (6, 8)
"""Half-open hour-of-shift bounds of the held reading, ``[6, 8)``."""


@dataclass(frozen=True)
class PlantJob:
    """One plant in the cycle, with the sensor and unit ADR 0231 names.

    Attributes:
        plant_id: A plant ``run_plant`` already knows.
        sample_seconds: The sample period. Windows come from ``windows_for_period`` of this.
        sensor: The frozen sensor the held reading falsifies.
        asset_id: The plant's first declared unit, where the work order is filed.
    """

    plant_id: str
    sample_seconds: int
    sensor: str
    asset_id: str


JOBS: Final[tuple[PlantJob, ...]] = (
    PlantJob("water-treatment", 30, "filtered_turbidity_ntu", "intake"),
    PlantJob("power-generation", 10, "transformer_oil_temp_c", "turbine"),
    PlantJob("batch-reactor", 60, "reactor_temp_c", "reactor"),
)


def job_for_seed(seed: int) -> PlantJob:
    """Return the plant for ``seed``. Index 0 of either batch is water.

    Raises:
        ValueError: If ``seed`` is in neither declared batch.
    """
    if seed in QUEUE_DEVELOPMENT_SEEDS:
        index = QUEUE_DEVELOPMENT_SEEDS.index(seed)
    elif seed in QUEUE_HELD_BACK_SEEDS:
        index = QUEUE_HELD_BACK_SEEDS.index(seed)
    else:
        raise ValueError(f"seed {seed} is not a lane Q mixed-queue seed")
    return JOBS[index % len(JOBS)]


def run_spec(seed: int, sample_seconds: int, *, hours: int) -> RunSpec:
    """Return a run of ``hours`` from `SHIFT_START` at ``sample_seconds``."""
    return RunSpec(
        seed=seed,
        start=SHIFT_START,
        duration=timedelta(hours=hours),
        sample_interval=timedelta(seconds=sample_seconds),
    )


def hold_value(low: float, high: float) -> float:
    """Return the held reading, ``low + HOLD_SHARE * (high - low)``.

    ``HOLD_SHARE`` is the explainer's frozen 0.9. It is not a searched level.
    """
    return low + HOLD_SHARE * (high - low)


def attack_window(spec: RunSpec) -> TimeWindow:
    """Return the half-open hold window, hour 6 through hour 8 of ``spec``."""
    start, end = ATTACK_HOURS
    return TimeWindow(spec.start + timedelta(hours=start), spec.start + timedelta(hours=end))


def work_order_for(seed: int, spec: RunSpec, asset_id: str) -> WorkOrder:
    """Return the one sanctioning routine order for ``seed``.

    The window is hour 1 through hour 5, inclusive. It does not overlap
    `attack_window`. The order does not know where the hold is placed beyond
    those two fixed clocks.
    """
    start_hour, end_hour = WORK_ORDER_HOURS
    return WorkOrder(
        order_id=f"WO-{seed}",
        asset_id=asset_id,
        kind=MaintenanceKind.ROUTINE,
        start=spec.start + timedelta(hours=start_hour),
        end=spec.start + timedelta(hours=end_hour),
        sanctioning=True,
        summary=f"routine cover on {asset_id} for mixed-queue seed {seed}",
    )

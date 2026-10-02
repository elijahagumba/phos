"""One clean water-treatment run, shared by every test that needs to know what normal looked like.

Session-scoped because it is expensive and immutable: `PlantRun` and `NormalReference` are frozen
and every query on them returns a copy, so no test can leave a mark another test would read.

The run is twelve hours of the works at 30-second sampling from seed 4242. That seed is not
arbitrary — it puts a genuine ``level_setpoint_change`` at 01:00 and a ``residual_setpoint_change``
at 08:50, with two filter backwashes between them, so there is a real operator write for a mimic
to imitate and long quiet stretches for an attack to sit in without colliding with one.
"""

from datetime import UTC, datetime, timedelta

import pytest

from phos.synth import PlantRun, RunSpec, run_plant
from phos.synth.attacks.library import NormalReference

START = datetime(2026, 4, 1, tzinfo=UTC)
PLANT = "water-treatment"
SEED = 4242

# Water-treatment signal keys, spelled out rather than imported: a test that reached into the
# plant module for its own constants would keep passing if the plant renamed a column, and the
# column name is exactly what a corpus is keyed on.
INTAKE_SPEED = "intake_pump_speed_pct"
RAW_INFLOW = "raw_inflow_m3ph"
CHLORINE_DOSE = "chlorine_dose_mgpl"
CLEARWELL_LEVEL = "clearwell_level_m"
LEVEL_SETPOINT = "clearwell_level_setpoint_m"
RESIDUAL_SETPOINT = "chlorine_residual_setpoint_mgpl"
DISTRIBUTION_FLOW = "distribution_flow_m3ph"
LEVEL_SETPOINT_CHANGE = "level_setpoint_change"
BACKWASH = "filter_backwash"


def a_spec(hours: float = 12.0, seed: int = SEED) -> RunSpec:
    """Return the standard test run spec, optionally at a different length or seed."""
    return RunSpec(
        seed=seed,
        start=START,
        duration=timedelta(hours=hours),
        sample_interval=timedelta(seconds=30),
    )


@pytest.fixture(scope="session")
def clean_run() -> PlantRun:
    """Twelve hours of normal water treatment. Frozen, so sharing it is safe."""
    return run_plant(PLANT, a_spec())


@pytest.fixture(scope="session")
def reference(clean_run: PlantRun) -> NormalReference:
    """What normal looked like, as the attack library reads it."""
    return NormalReference.of(clean_run)

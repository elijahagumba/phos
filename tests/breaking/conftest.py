"""Hand-built fixtures for the breaking harness.

Deliberately tiny and deliberately **not** loaded from ``data/``. The generated corpora are
git-ignored, so a test that read one would pass on the machine that had just run the generator and
fail everywhere else. Everything here is built in memory from D1's and D2's own types, which also
means a fixture cannot drift away from the schema it claims to be an instance of.
"""

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from phos.synth import PlantDescription, SignalSpec
from phos.synth.attacks import AttackGroundTruth, AttackType
from phos.synth.plant import Coupling, CouplingKind, PhysicalUnit, SignalKind

if TYPE_CHECKING:
    from phos.breaking.truth import TrueStateRecord

RUN_START = datetime(2026, 5, 1, tzinfo=UTC)
"""First sample instant every fixture here is anchored to."""


def signal(
    key: str,
    kind: SignalKind,
    *,
    noise: float = 0.1,
    drift: float = 0.0,
    unit_id: str = "unit-a",
) -> SignalSpec:
    """Build one declared signal, defaulting to a driftless instrument."""
    return SignalSpec(
        key=key,
        label=key.replace("_", " "),
        unit="units",
        kind=kind,
        physical_unit=unit_id,
        low=0.0,
        high=100.0,
        noise_stddev=noise,
        drift_amplitude=drift,
    )


@pytest.fixture
def plant() -> PlantDescription:
    """A two-unit plant carrying one drifting sensor, one actuator and one setpoint.

    The three kinds are exactly what the fingerprint rule turns on: a falsified sensor reading is
    short of the drift a real one has, while an actuator is sensed honestly and a setpoint declares
    no drift to be missing.
    """
    return PlantDescription(
        plant_id="fixture-plant",
        label="Fixture plant",
        industry="testing",
        summary="A plant that exists to make one classification checkable by eye.",
        model_source="Hand-built for tests; models nothing real.",
        units=(
            PhysicalUnit(unit_id="unit-a", label="Unit A"),
            PhysicalUnit(unit_id="unit-b", label="Unit B"),
        ),
        signals=(
            signal("level_m", SignalKind.SENSOR, noise=0.01, drift=0.02),
            signal("steady_sensor", SignalKind.SENSOR, noise=0.01, drift=0.0),
            signal("pump_pct", SignalKind.ACTUATOR, noise=0.15, drift=0.0, unit_id="unit-b"),
            signal("level_setpoint_m", SignalKind.SETPOINT, noise=0.0, drift=0.0),
        ),
        couplings=(
            Coupling(
                driven="level_m",
                drivers=("pump_pct",),
                kind=CouplingKind.INTEGRATION,
                relation="level rises with pump speed",
            ),
        ),
    )


def ground_truth(
    attack_id: str,
    attack_type: AttackType,
    *,
    subtlety: float = 0.0,
    targets: tuple[str, ...] = ("level_m",),
    start_hours: float = 1.0,
    duration_hours: float = 2.0,
    physical_effect: bool = True,
    truth_departure: dict[str, float] | None = None,
    issuer: str = "",
) -> AttackGroundTruth:
    """Build measured ground truth for one attack, as D2's manifest would record it."""
    started = RUN_START + timedelta(hours=start_hours)
    return AttackGroundTruth(
        attack_id=attack_id,
        type=attack_type,
        subtlety=subtlety,
        started_at=started,
        ended_at=started + timedelta(hours=duration_hours),
        target_signals=targets,
        issuer=issuer,
        manipulation=f"{attack_type.value} on {', '.join(targets)}",
        physical_effect=physical_effect,
        truth_departure=truth_departure or {},
    )


def true_state_record(
    series: dict[str, list[float]],
    *,
    n: int | None = None,
    step_minutes: float = 30.0,
) -> "TrueStateRecord":
    """Build a true-state record from per-signal series, stamped from `RUN_START`."""
    from phos.breaking.truth import TrueStateRecord

    length = n if n is not None else len(next(iter(series.values())))
    stamps = tuple(RUN_START + timedelta(minutes=step_minutes * index) for index in range(length))
    return TrueStateRecord(
        timestamps=stamps,
        values={key: tuple(values) for key, values in series.items()},
        source="fixture",
    )

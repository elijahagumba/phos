"""Shared fixtures for the synthetic-engine tests.

The tank below is the same toy plant `test_plant.py` uses — one tank, one pump, one loop — and it
lives here so the command-layer tests can build on it without importing another test module.
Sharing through a conftest is the convention `tests/breaking/` already follows; importing a test
module from a test module breaks coverage collection, because the module is then loaded twice
under two names.
"""

from datetime import UTC, datetime

from phos.synth.plant import (
    ControlNetwork,
    Coupling,
    CouplingKind,
    NetworkNode,
    PhysicalUnit,
    PlantDescription,
    RegisterBlock,
    SignalKind,
    SignalSpec,
)

START = datetime(2026, 3, 1, tzinfo=UTC)
LEVEL = "level_m"
INFLOW = "inflow_m3ph"
PUMP = "pump_speed_pct"
SETPOINT = "level_setpoint_m"
TANK_AREA_M2 = 10.0

TANK_NETWORK = ControlNetwork(
    nodes=(
        NetworkNode(node_id="scada", label="SCADA server", ip="10.0.9.5", role="scada"),
        NetworkNode(node_id="plc", label="Tank PLC", ip="10.0.9.11", role="plc"),
        NetworkNode(node_id="hmi", label="Operator HMI", ip="10.0.9.20", role="hmi"),
    ),
    blocks=(
        RegisterBlock(node_id="plc", start_address=0, signals=(LEVEL, INFLOW, PUMP)),
        RegisterBlock(node_id="plc", start_address=100, signals=(SETPOINT,), writable=True),
    ),
    poller="scada",
    operator="hmi",
    poll_interval_seconds=120.0,
)

TANK_DESCRIPTION = PlantDescription(
    plant_id="tiny-tank",
    label="Tiny tank",
    industry="test fixture",
    summary="One tank, one pump, one level loop. A fixture, not a claim about any real plant.",
    model_source="Hand-built fixture for tests/synth/test_plant.py.",
    units=(
        PhysicalUnit(unit_id="tank", label="Storage tank"),
        PhysicalUnit(unit_id="pump", label="Feed pump"),
    ),
    signals=(
        SignalSpec(
            key=LEVEL,
            label="Tank level",
            unit="m",
            kind=SignalKind.SENSOR,
            physical_unit="tank",
            low=0.0,
            high=6.0,
            noise_stddev=0.01,
            drift_amplitude=0.02,
        ),
        SignalSpec(
            key=INFLOW,
            label="Feed flow",
            unit="m3/h",
            kind=SignalKind.SENSOR,
            physical_unit="pump",
            low=0.0,
            high=70.0,
            noise_stddev=0.3,
            drift_amplitude=0.2,
        ),
        SignalSpec(
            key=PUMP,
            label="Feed pump speed",
            unit="%",
            kind=SignalKind.ACTUATOR,
            physical_unit="pump",
            low=0.0,
            high=100.0,
            noise_stddev=0.05,
        ),
        SignalSpec(
            key=SETPOINT,
            label="Level setpoint",
            unit="m",
            kind=SignalKind.SETPOINT,
            physical_unit="tank",
            low=0.0,
            high=6.0,
            noise_stddev=0.0,
        ),
    ),
    couplings=(
        Coupling(
            driven=LEVEL,
            drivers=(INFLOW,),
            kind=CouplingKind.INTEGRATION,
            relation="level integrates inflow minus the demand drawn off the tank",
        ),
        Coupling(
            driven=INFLOW,
            drivers=(PUMP,),
            kind=CouplingKind.ALGEBRAIC,
            relation="flow follows the square root of pump speed",
        ),
        Coupling(
            driven=PUMP,
            drivers=(LEVEL, SETPOINT),
            kind=CouplingKind.CONTROL,
            relation="a PI loop holds level at setpoint",
        ),
    ),
    control_network=TANK_NETWORK,
)


def description_with(**overrides: object) -> PlantDescription:
    """Rebuild the fixture description with fields replaced, re-running every validator.

    `model_copy(update=...)` skips validation in Pydantic v2, so a variant built that way would
    construct happily and the test asserting it is refused would assert nothing.
    """
    return PlantDescription.model_validate({**TANK_DESCRIPTION.model_dump(), **overrides})

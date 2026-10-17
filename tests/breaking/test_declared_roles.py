"""The synthetic plants' declared roles and couplings, read from their own definitions (ADR 0123).

Nothing here is inferred from data: a role is the signal's declared `SignalKind`, and a link is a
declared `Coupling`. These are what the plant map is checked against (§8), never its input.
"""

import pytest

from phos.atlas.signal_roles import SignalRole
from phos.breaking.declared_roles import (
    DeclaredLink,
    declared_links,
    declared_loops,
    description_for,
    plant_roles,
)
from phos.synth.plant import CouplingKind, PlantDescription, SignalKind
from phos.synth.plants.batch import BATCH_DESCRIPTION
from phos.synth.plants.power import POWER_DESCRIPTION
from phos.synth.plants.water import WATER_DESCRIPTION

PLANTS = (WATER_DESCRIPTION, POWER_DESCRIPTION, BATCH_DESCRIPTION)


@pytest.mark.parametrize("description", PLANTS, ids=lambda d: d.plant_id)
def test_every_signal_has_its_declared_kind_as_its_role(description: PlantDescription) -> None:
    roles = plant_roles(description)
    assert roles.signals == description.signal_keys()
    assert roles.without_role() == ()
    expected = {
        SignalKind.SENSOR: SignalRole.SENSOR,
        SignalKind.ACTUATOR: SignalRole.ACTUATOR,
        SignalKind.SETPOINT: SignalRole.SETPOINT,
    }
    for spec in description.signals:
        assert roles.role_of(spec.key) is expected[spec.kind]
    assert description.plant_id in roles.source


@pytest.mark.parametrize("description", PLANTS, ids=lambda d: d.plant_id)
def test_links_are_one_per_declared_driver(description: PlantDescription) -> None:
    links = declared_links(description)
    expected = [
        (driver, coupling.driven, coupling.kind)
        for coupling in description.couplings
        for driver in coupling.drivers
    ]
    assert [(link.driver, link.driven, link.kind) for link in links] == expected
    assert len(set(links)) == len(links)


def test_the_water_liar_target_integrates_its_flows_and_is_held_by_a_controller() -> None:
    links = declared_links(WATER_DESCRIPTION)
    roles = plant_roles(WATER_DESCRIPTION)
    into_level = {link.driver: link.kind for link in links if link.driven == "clearwell_level_m"}
    assert into_level == {
        "raw_inflow_m3ph": CouplingKind.INTEGRATION,
        "distribution_flow_m3ph": CouplingKind.INTEGRATION,
    }
    assert (
        DeclaredLink(
            driver="clearwell_level_m", driven="intake_pump_speed_pct", kind=CouplingKind.CONTROL
        )
        in links
    )
    assert roles.role_of("clearwell_level_m") is SignalRole.SENSOR
    assert roles.role_of("clearwell_level_setpoint_m") is SignalRole.SETPOINT
    assert roles.role_of("intake_pump_speed_pct") is SignalRole.ACTUATOR


def test_the_water_level_loop_is_declared_from_its_control_coupling() -> None:
    loops = {loop.reading: loop for loop in plant_roles(WATER_DESCRIPTION).loops}
    level = loops["clearwell_level_m"]
    assert level.outputs == ("intake_pump_speed_pct",)
    assert level.setpoint == "clearwell_level_setpoint_m"
    assert set(loops) == {
        "clearwell_level_m",
        "chlorine_residual_mgpl",
        "raw_turbidity_ntu",
        "distribution_pressure_bar",
    }


@pytest.mark.parametrize("description", PLANTS, ids=lambda d: d.plant_id)
def test_every_loop_is_a_sensor_driving_a_control_coupling(description: PlantDescription) -> None:
    kind = {spec.key: spec.kind for spec in description.signals}
    control = {
        (driver, coupling.driven)
        for coupling in description.couplings
        if coupling.kind is CouplingKind.CONTROL
        for driver in coupling.drivers
        if kind[driver] is SignalKind.SENSOR
    }
    loops = declared_loops(description)
    assert {(loop.reading, loop.outputs[0]) for loop in loops} == control
    assert all(len(loop.outputs) == 1 for loop in loops)


@pytest.mark.parametrize("description", PLANTS, ids=lambda d: d.plant_id)
def test_a_plant_is_found_by_its_id(description: PlantDescription) -> None:
    assert description_for(description.plant_id) is description

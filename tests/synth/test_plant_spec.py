"""A plant said declaratively is the same plant, and the saying of it is load-bearing.

Two claims are worth more than the rest here and both are asserted on all three plants:

* `PlantSpec.describe` returns the `PlantDescription` the hand-written plant returned, field for
  field. Without that, PART R1 produced a second, similar plant rather than a re-expression of
  the existing one, and every corpus measured before it would be measuring something else.
* Changing a spec changes the plant. A declaration nothing reads is decoration, and the test that
  catches that is the one that perturbs a parameter and insists the telemetry moves.

The byte-identity of the standard corpora is asserted separately, in ``test_golden_corpora.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import BaseModel

from phos.synth.plant import RunSpec, SignalKind
from phos.synth.plant_spec import (
    SPEC_VERSION,
    Component,
    ComponentKind,
    Connection,
    ControllerKind,
    ControllerSpec,
    PlantSpec,
    SpecError,
    component_signals,
    fixed_setpoint,
    pi_controller,
    signals_of_kind,
)
from phos.synth.plants.batch import BATCH_DESCRIPTION, BATCH_SPEC, BatchParameters
from phos.synth.plants.power import POWER_DESCRIPTION, POWER_SPEC, PowerParameters
from phos.synth.plants.water import (
    CLEARWELL_LEVEL,
    WATER_DESCRIPTION,
    WATER_SPEC,
    WaterParameters,
    WaterTreatmentPlant,
)
from phos.synth.process import Hysteresis, PiController
from phos.synth.topology import subsystems, subsystems_from_components

SPECS = (WATER_SPEC, POWER_SPEC, BATCH_SPEC)
PAIRS = (
    (WATER_SPEC, WATER_DESCRIPTION),
    (POWER_SPEC, POWER_DESCRIPTION),
    (BATCH_SPEC, BATCH_DESCRIPTION),
)
RUN = RunSpec(
    seed=4242,
    start=datetime(2026, 5, 1, tzinfo=UTC),
    duration=timedelta(hours=3),
    sample_interval=timedelta(seconds=30),
)


@pytest.mark.parametrize(
    ("spec", "description"), PAIRS, ids=lambda value: getattr(value, "plant_id", "")
)
def test_a_spec_describes_the_plant_that_was_there_before(
    spec: PlantSpec, description: object
) -> None:
    assert spec.describe() == description


@pytest.mark.parametrize("spec", SPECS, ids=lambda spec: spec.plant_id)
def test_a_spec_round_trips_through_json(spec: PlantSpec) -> None:
    document = spec.to_json()
    rebuilt = PlantSpec.from_json(document)

    assert rebuilt == spec
    assert rebuilt.to_json() == document
    assert rebuilt.describe() == spec.describe()


@pytest.mark.parametrize("spec", SPECS, ids=lambda spec: spec.plant_id)
def test_the_component_graph_and_the_instruments_agree(spec: PlantSpec) -> None:
    assert subsystems_from_components(spec) == subsystems(spec.describe())


@pytest.mark.parametrize("spec", SPECS, ids=lambda spec: spec.plant_id)
def test_every_signal_is_owned_exactly_once(spec: PlantSpec) -> None:
    owned = component_signals(spec.components)

    assert sorted(owned) == sorted(spec.describe().signal_keys())
    assert len(owned) == len(set(owned))


@pytest.mark.parametrize("spec", SPECS, ids=lambda spec: spec.plant_id)
def test_every_connection_joins_declared_components(spec: PlantSpec) -> None:
    declared = {component.component_id for component in spec.components}
    for connection in spec.connections:
        assert connection.source in declared
        assert connection.target in declared


def test_the_scan_period_is_the_poll_interval_and_is_absent_without_a_network() -> None:
    assert WATER_SPEC.scan_period_seconds == 30.0
    assert BATCH_SPEC.control_network is None
    assert BATCH_SPEC.scan_period_seconds is None


def test_changing_a_parameter_changes_the_plant() -> None:
    before = _levels(WATER_SPEC)
    smaller = WATER_SPEC.model_copy(
        update={"parameters": WaterParameters(clearwell_area_m2=180.0).model_dump()}
    )

    after = _levels(PlantSpec.model_validate(smaller.model_dump()))

    assert after != before, "the spec's parameters are not reaching the physics"


def test_changing_a_controller_gain_changes_the_plant() -> None:
    before = _levels(WATER_SPEC)
    retuned = tuple(
        controller.model_copy(update={"gain": 4.0})
        if controller.controller_id == "level"
        else controller
        for controller in WATER_SPEC.controllers
    )

    after = _levels(
        PlantSpec.model_validate(
            WATER_SPEC.model_copy(update={"controllers": retuned}).model_dump()
        )
    )

    assert after != before, "the spec's controller tunings are not reaching the loops"


def _levels(spec: PlantSpec) -> list[float]:
    """Return the reported clearwell level over a short run of the works this spec describes."""
    plant = WaterTreatmentPlant(RUN, plant_spec=spec)
    return [plant.step(None).report.values[CLEARWELL_LEVEL] for _ in range(RUN.n_steps)]


def test_the_default_spec_is_the_one_the_module_declares() -> None:
    assert WaterTreatmentPlant(RUN).description == WATER_SPEC.describe()
    assert WaterTreatmentPlant(RUN, plant_spec=None).description == WATER_SPEC.describe()


@pytest.mark.parametrize(
    ("spec", "parameters"),
    ((WATER_SPEC, WaterParameters), (POWER_SPEC, PowerParameters), (BATCH_SPEC, BatchParameters)),
    ids=lambda value: getattr(value, "plant_id", getattr(value, "__name__", "")),
)
def test_the_parameter_set_is_exactly_what_the_template_reads(
    spec: PlantSpec, parameters: type[BaseModel]
) -> None:
    assert set(spec.parameters) == set(parameters.model_fields)
    assert parameters.model_validate(dict(spec.parameters)) == parameters()


def test_a_spec_from_another_version_is_refused() -> None:
    raw = WATER_SPEC.model_dump()
    raw["spec_version"] = SPEC_VERSION + 1

    with pytest.raises(ValueError, match="spec_version"):
        PlantSpec.model_validate(raw)


def test_a_signal_no_component_owns_is_refused() -> None:
    stripped = tuple(
        component.model_copy(update={"signals": ()})
        if component.component_id == "clearwell"
        else component
        for component in WATER_SPEC.components
    )

    with pytest.raises(ValueError, match="no component owns"):
        PlantSpec.model_validate(
            WATER_SPEC.model_copy(update={"components": stripped}).model_dump()
        )


def test_a_signal_owned_twice_is_refused() -> None:
    doubled = (
        *WATER_SPEC.components,
        Component(
            component_id="second_clearwell",
            kind=ComponentKind.TANK,
            label="A second claim on the same instrument",
            physical_unit="clearwell",
            signals=(CLEARWELL_LEVEL,),
        ),
    )

    with pytest.raises(ValueError, match="owned by both"):
        PlantSpec.model_validate(WATER_SPEC.model_copy(update={"components": doubled}).model_dump())


def test_a_component_owning_a_signal_from_another_unit_is_refused() -> None:
    moved = tuple(
        component.model_copy(update={"physical_unit": "intake"})
        if component.component_id == "clearwell"
        else component
        for component in WATER_SPEC.components
    )

    with pytest.raises(ValueError, match="the drawing and the instruments disagree"):
        PlantSpec.model_validate(WATER_SPEC.model_copy(update={"components": moved}).model_dump())


def test_a_component_on_an_undeclared_unit_is_refused() -> None:
    stray = (
        *WATER_SPEC.components,
        Component(
            component_id="nowhere",
            kind=ComponentKind.OTHER,
            label="On a unit the plant does not have",
            physical_unit="imaginary",
        ),
    )

    with pytest.raises(ValueError, match="undeclared unit"):
        PlantSpec.model_validate(WATER_SPEC.model_copy(update={"components": stray}).model_dump())


def test_a_connection_to_nowhere_is_refused() -> None:
    dangling = (
        *WATER_SPEC.connections,
        Connection(source="clearwell", target="not_a_component", medium="water"),
    )

    with pytest.raises(ValueError, match="not a declared component"):
        PlantSpec.model_validate(
            WATER_SPEC.model_copy(update={"connections": dangling}).model_dump()
        )


def test_a_component_connected_to_itself_is_refused() -> None:
    with pytest.raises(ValueError, match="connected to itself"):
        Connection(source="clearwell", target="clearwell", medium="water")


def test_a_loop_cannot_drive_a_measurement() -> None:
    wrong = tuple(
        controller.model_copy(update={"output": CLEARWELL_LEVEL})
        if controller.controller_id == "level"
        else controller
        for controller in WATER_SPEC.controllers
    )

    with pytest.raises(ValueError, match="must be a ACTUATOR"):
        PlantSpec.model_validate(WATER_SPEC.model_copy(update={"controllers": wrong}).model_dump())


def test_a_loop_holding_to_nothing_is_refused() -> None:
    adrift = tuple(
        controller.model_copy(update={"setpoint": None})
        if controller.controller_id == "level"
        else controller
        for controller in WATER_SPEC.controllers
    )

    with pytest.raises(ValueError, match="holds to nothing"):
        PlantSpec.model_validate(WATER_SPEC.model_copy(update={"controllers": adrift}).model_dump())


def test_a_loop_holding_to_two_things_is_refused() -> None:
    with pytest.raises(ValueError, match="two answers"):
        ControllerSpec(
            controller_id="confused",
            kind=ControllerKind.PI,
            measurement="a",
            output="b",
            setpoint="c",
            setpoint_value=11.0,
            gain=1.0,
            integral_time_seconds=10.0,
            low=0.0,
            high=100.0,
        )


def test_an_untuned_loop_is_refused() -> None:
    with pytest.raises(ValueError, match="unstated tuning"):
        ControllerSpec(
            controller_id="untuned",
            kind=ControllerKind.PI,
            measurement="a",
            output="b",
            setpoint_value=1.0,
        )


def test_a_hysteresis_element_with_a_loop_tuning_is_refused() -> None:
    with pytest.raises(ValueError, match="belongs to a hysteresis element"):
        ControllerSpec(
            controller_id="muddled",
            kind=ControllerKind.PI,
            measurement="a",
            output="b",
            setpoint_value=1.0,
            gain=1.0,
            integral_time_seconds=10.0,
            low=0.0,
            high=1.0,
            on_below=0.2,
        )

    with pytest.raises(ValueError, match="belongs to a PI loop"):
        ControllerSpec(
            controller_id="muddled",
            kind=ControllerKind.HYSTERESIS,
            measurement="a",
            output="b",
            on_below=0.2,
            off_above=0.8,
            gain=1.0,
        )


def test_a_hysteresis_element_with_a_setpoint_is_refused() -> None:
    with pytest.raises(ValueError, match="its band is its target"):
        ControllerSpec(
            controller_id="banded",
            kind=ControllerKind.HYSTERESIS,
            measurement="a",
            output="b",
            setpoint_value=1.0,
            on_below=0.2,
            off_above=0.8,
        )


def test_an_incomplete_band_is_refused() -> None:
    with pytest.raises(ValueError, match="off_above"):
        ControllerSpec(
            controller_id="half_banded",
            kind=ControllerKind.HYSTERESIS,
            measurement="a",
            output="b",
            on_below=0.2,
        )


def test_the_batch_cascade_is_declared_as_one() -> None:
    assert BATCH_SPEC.cascade_slave("reactor_temperature") == "jacket_temperature"
    assert BATCH_SPEC.cascade_slave("jacket_temperature") is None
    slave = BATCH_SPEC.controller("jacket_temperature")
    assert slave.setpoint is None and slave.setpoint_value is None


def test_a_declared_element_is_built_as_what_it_says_it_is() -> None:
    assert isinstance(pi_controller(WATER_SPEC, "level"), PiController)
    assert isinstance(
        ControllerSpec(
            controller_id="duty_pump",
            kind=ControllerKind.HYSTERESIS,
            measurement="a",
            output="b",
            on_below=1.0,
            off_above=2.0,
        ).build(),
        Hysteresis,
    )


def test_asking_for_the_wrong_kind_of_element_is_refused() -> None:
    with pytest.raises(KeyError, match="no controller"):
        pi_controller(WATER_SPEC, "not_a_loop")
    with pytest.raises(SpecError, match="not to a fixed value"):
        fixed_setpoint(WATER_SPEC, "level")
    assert fixed_setpoint(POWER_SPEC, "avr") == 11.0


def test_asking_for_an_undeclared_component_names_the_plant() -> None:
    with pytest.raises(KeyError, match="water-treatment"):
        WATER_SPEC.component("not_a_component")


def test_a_document_that_is_not_a_spec_is_refused_with_the_reason() -> None:
    with pytest.raises(SpecError, match="not readable as JSON"):
        PlantSpec.from_json("{not json")
    with pytest.raises(SpecError, match="water-treatment"):
        PlantSpec.from_json(WATER_SPEC.to_json().replace('"components"', '"nope"', 1))


def test_signals_of_kind_follows_declaration_order() -> None:
    setpoints = signals_of_kind(WATER_SPEC, SignalKind.SETPOINT)

    assert setpoints == WATER_SPEC.describe().keys_of_kind(SignalKind.SETPOINT)


def test_components_on_a_unit_are_in_declaration_order() -> None:
    on_intake = WATER_SPEC.components_on("intake")

    assert [component.component_id for component in on_intake] == [
        "river",
        "intake_pump",
        "raw_main",
    ]
    assert WATER_SPEC.components_on("no_such_unit") == ()

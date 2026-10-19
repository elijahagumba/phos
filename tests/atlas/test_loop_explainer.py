"""ADR 0170: every control coupling is a loop, and a loop bars only its outputs."""

import pytest
from tests.atlas.plant_map_fixture import INFLOW, LEVEL, NAMES, OUTFLOW, QUALITY, VALVE, roles

from phos.atlas.loop_explainer import (
    ALL_NINE,
    LOOP_EXPLAINER_RESULT_NAME,
    LOOP_EXPLAINER_SETTINGS,
    naming_totals,
    roles_with_every_control_coupling,
)
from phos.atlas.plant_map_fit import _level_exclusions
from phos.atlas.plant_map_model import DEFAULT_SETTINGS, LOOP_BARS
from phos.atlas.sensor_explainer import (
    EXPLAINER_RESULT_NAME,
    EXPLAINER_SETTINGS,
    SURVEY_SUBJECTS,
    SubjectResult,
    roles_from_plant,
    score_subject,
)
from phos.synth.plants.batch import BATCH_DESCRIPTION
from phos.synth.plants.power import POWER_DESCRIPTION
from phos.synth.plants.water import WATER_DESCRIPTION


def test_defaults_keep_adr_0126() -> None:
    assert DEFAULT_SETTINGS.loop_bar == "reach"
    assert EXPLAINER_SETTINGS.loop_bar == "reach"
    assert LOOP_EXPLAINER_SETTINGS.loop_bar == "outputs"
    assert LOOP_BARS == ("reach", "outputs")
    assert len({LOOP_EXPLAINER_RESULT_NAME, EXPLAINER_RESULT_NAME}) == 2


def test_outputs_bar_keeps_what_the_output_reaches() -> None:
    graph = {LEVEL: {INFLOW}, INFLOW: {VALVE}, VALVE: {LEVEL}, OUTFLOW: set(), QUALITY: {LEVEL}}
    modelled = [LEVEL, INFLOW, OUTFLOW, VALVE, QUALITY]
    descendants = dict.fromkeys(modelled, ())
    reach = _level_exclusions(roles(), NAMES, graph, modelled, descendants, "reach")
    outputs = _level_exclusions(roles(), NAMES, graph, modelled, descendants, "outputs")
    assert INFLOW in reach[LEVEL]
    assert outputs[LEVEL] == (VALVE,)


def test_an_unknown_bar_is_refused() -> None:
    graph: dict[int, set[int]] = {LEVEL: set()}
    with pytest.raises(ValueError, match="loop bar"):
        _level_exclusions(roles(), NAMES, graph, [LEVEL], {LEVEL: ()}, "everything")


def test_batch_gets_a_loop_for_each_control_coupling() -> None:
    assert roles_from_plant(BATCH_DESCRIPTION).loops == ()
    loops = {loop.name: loop for loop in roles_with_every_control_coupling(BATCH_DESCRIPTION).loops}
    assert set(loops) == {"jacket_valve_pct", "feed_valve_pct", "agitator_speed_rpm"}
    assert all(loop.reading is None for loop in loops.values())
    assert loops["jacket_valve_pct"].setpoint == "reactor_temp_setpoint_c"
    assert loops["feed_valve_pct"].setpoint is None


def test_lane_d_loops_are_kept_as_they_were() -> None:
    for description in (WATER_DESCRIPTION, POWER_DESCRIPTION):
        before = {loop.name: loop for loop in roles_from_plant(description).loops}
        after = {loop.name: loop for loop in roles_with_every_control_coupling(description).loops}
        for name, loop in before.items():
            assert after[name] == loop
    water = {loop.name for loop in roles_with_every_control_coupling(WATER_DESCRIPTION).loops}
    assert "coagulant_dose_mgpl" in water


def test_reactor_pressure_is_named_on_a_development_seed() -> None:
    subject = next(item for item in SURVEY_SUBJECTS if item.signal == "reactor_pressure_barg")
    before = score_subject(subject, split="development", seeds=(97001,))
    after = score_subject(
        subject,
        split="development",
        seeds=(97001,),
        settings=LOOP_EXPLAINER_SETTINGS,
        roles_for=roles_with_every_control_coupling,
    )
    assert before.caught == after.caught == 1
    assert before.named_right == 0
    assert after.named_right == 1
    assert after.named_wrong == 0
    assert after.alerts_unchanged


def test_a_held_back_seed_is_refused_before_a_plant_is_built() -> None:
    with pytest.raises(ValueError, match="not in the development split"):
        score_subject(ALL_NINE[0], split="development", seeds=(97101,))


def test_totals_add_every_subject() -> None:
    def result(caught: int, right: int, wrong: int) -> SubjectResult:
        return SubjectResult("p", "s", False, 20, caught, right, wrong, None, 0, 0, True)

    totals = naming_totals((result(20, 19, 0), result(13, 13, 1), result(0, 0, 0)))
    assert (totals.caught, totals.named_right, totals.named_wrong) == (33, 32, 1)
    assert totals.right_share == pytest.approx(32 / 33)
    assert naming_totals(()).right_share is None

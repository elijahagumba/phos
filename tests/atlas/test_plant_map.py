"""The plant map (ADR 0123): links, forms, bands, scores, naming and reconstruction.

Every test runs on the small tank in `plant_map_fixture`, at one second a sample, with short
windows so it runs in seconds. The windows are passed through the same `MapSettings` the ADR's
defaults use; only their values differ.
"""

from __future__ import annotations

import numpy
import pytest
from tests.atlas import plant_map_fixture as tank

from phos.atlas import consistency
from phos.atlas.consistency import TrainFile
from phos.atlas.consistency_windows import _samples
from phos.atlas.plant_map import (
    DEFAULT_SETTINGS,
    Form,
    MapSettings,
    PlantMap,
    fit_map,
    map_scores,
    samples_for,
)
from phos.atlas.plant_map_naming import Verdict, name_instrument, reconstruct
from phos.atlas.signal_roles import ControlLoop, SignalRole

SETTINGS = MapSettings(
    lag_seconds=(1, 2, 5, 10, 20),
    horizon_seconds=(5, 20, 60),
    form_horizon_seconds=60,
    fit_step_seconds=1,
    anchor_every_seconds=50,
    free_run_step_seconds=10,
    free_run_max_seconds=1200,
    anchor_lookback_seconds=1200,
)


@pytest.fixture(scope="module")
def train() -> tank.Run:
    return tank.simulate(12_000, seed=1)


@pytest.fixture(scope="module")
def plant(train: tank.Run) -> PlantMap:
    return _fit(train)


def _fit(
    run: tank.Run,
    unroled: frozenset[str] = frozenset(),
    loops: tuple[ControlLoop, ...] = (tank.LEVEL_LOOP,),
) -> PlantMap:
    attack = numpy.zeros(run.reported.shape[0], dtype=numpy.bool_)
    return fit_map(
        [TrainFile(values=run.reported, attack=attack)],
        tank.NAMES,
        tank.roles(unroled=unroled, loops=loops),
        period_seconds=1.0,
        settings=SETTINGS,
    )


# ---------------------------------------------------------------------------- settings


def test_seconds_convert_by_adr_0112s_rule() -> None:
    for period in (0.5, 1.0, 2.0, 30.0, 3600.0):
        for seconds in (1, 5, 15, 29, 30, 45, 60, 900, 3600):
            assert samples_for(seconds, period) == _samples(seconds, period)


def test_the_default_settings_are_the_adr_s() -> None:
    assert DEFAULT_SETTINGS.lag_seconds == (5, 15, 30, 60, 120, 300, 600, 900, 1800, 3600)
    assert DEFAULT_SETTINGS.horizon_seconds == (60, 300, 900, 3600)
    assert DEFAULT_SETTINGS.form_horizon_seconds == 900
    assert (DEFAULT_SETTINGS.max_drivers, DEFAULT_SETTINGS.max_lags_per_driver) == (6, 2)
    assert (DEFAULT_SETTINGS.folds, DEFAULT_SETTINGS.min_gain) == (5, 0.01)
    assert (DEFAULT_SETTINGS.ridge, DEFAULT_SETTINGS.band_quantile) == (1.0, 0.9999)
    assert DEFAULT_SETTINGS.free_run_quantile == 0.99
    assert DEFAULT_SETTINGS.free_run_max_seconds == 6 * 3600
    assert DEFAULT_SETTINGS.anchor_every_seconds == 600


# ---------------------------------------------------------------------------- the map


def test_the_level_is_mapped_in_increment_form_from_its_flows(plant: PlantMap) -> None:
    model = plant.targets[tank.LEVEL]
    assert model.form is Form.INCREMENT
    drivers = {link.driver for link in model.links}
    assert {tank.INFLOW, tank.OUTFLOW} <= drivers | {tank.VALVE}
    assert drivers & {tank.INFLOW, tank.VALVE}
    assert tank.OUTFLOW in drivers


def test_every_link_has_a_lag_of_at_least_one_sample_and_at_most_two_lags(
    plant: PlantMap,
) -> None:
    for model in plant.targets.values():
        assert len(model.links) <= SETTINGS.max_drivers
        for link in model.links:
            assert link.target == model.target
            assert 1 <= len(link.lags) <= SETTINGS.max_lags_per_driver
            assert min(link.lags) >= 1
            assert link.driver != link.target


def test_a_setpoint_never_drives_a_sensor(plant: PlantMap) -> None:
    for model in plant.targets.values():
        if plant.roles[model.target] is SignalRole.SENSOR:
            assert tank.TARGET not in {link.driver for link in model.links}


def test_barred_signals_never_enter_a_level_form(plant: PlantMap) -> None:
    for model in plant.targets.values():
        if model.form is Form.LEVEL:
            drivers = {link.driver for link in model.links}
            assert not drivers & set(plant.level_exclusions[model.target])


def test_a_loop_bars_its_controller_and_what_it_drives_from_its_reading(plant: PlantMap) -> None:
    assert {tank.VALVE, tank.INFLOW} <= set(plant.level_exclusions[tank.LEVEL])
    assert plant.level_exclusions[tank.INFLOW] == ()
    assert plant.level_exclusions[tank.QUALITY] == ()


def test_the_map_learns_the_tank_as_built(plant: PlantMap) -> None:
    # ADR 0126: with ADR 0123's rule the valve-inflow echo barred the inflow's only real driver.
    assert tank.VALVE in plant.drivers_of(tank.INFLOW)
    assert tank.LEVEL in plant.drivers_of(tank.QUALITY)


def test_without_declared_loops_every_descendant_is_barred(train: tank.Run) -> None:
    plant = _fit(train, loops=())
    for target, barred in plant.level_exclusions.items():
        assert barred == plant.preliminary_descendants[target]


def test_a_signal_without_a_role_has_no_model_and_drives_nothing(train: tank.Run) -> None:
    plant = _fit(train, unroled=frozenset({"outflow"}))
    assert tank.OUTFLOW not in plant.targets
    for model in plant.targets.values():
        assert tank.OUTFLOW not in {link.driver for link in model.links}


def test_the_fit_is_deterministic(train: tank.Run, plant: PlantMap) -> None:
    again = _fit(train)
    assert again.describe() == plant.describe()


def test_each_link_carries_its_own_band_and_error_share(plant: PlantMap) -> None:
    for model in plant.targets.values():
        for link in model.links:
            assert link.drop_one.bands.shape == model.equation.bands.shape
            assert numpy.all(link.drop_one.bands > 0)
            assert 0.0 <= link.error_share <= 1.0


# ---------------------------------------------------------------------------- scores


def test_normal_data_stays_mostly_in_band(plant: PlantMap) -> None:
    fresh = tank.simulate(6_000, seed=2)
    scores = map_scores(plant, fresh.reported)
    assert scores.shape == fresh.reported.shape
    for column in plant.targets:
        assert numpy.mean(scores[:, column] > 1.0) < 0.01


def test_a_falsified_level_leaves_its_band(plant: PlantMap) -> None:
    run = tank.simulate(6_000, seed=3, liar=(3_000, 5_000, 1.0))
    scores = map_scores(plant, run.reported)
    assert scores[3_000:5_000, tank.LEVEL].max() > 1.0


# ---------------------------------------------------------------------------- naming


def _first_crossing(plant: PlantMap, run: tank.Run, start: int, column: int) -> int:
    scores = map_scores(plant, run.reported)
    (hits,) = numpy.nonzero(scores[start:, column] > 1.0)
    assert hits.size, "the event never crossed"
    return start + int(hits[0])


def test_the_lying_level_is_named(plant: PlantMap) -> None:
    run = tank.simulate(6_000, seed=3, liar=(3_000, 5_000, 1.0))
    named = [
        name_instrument(plant, run.reported, row=row, column=tank.LEVEL, onset=3_000)
        for row in range(3_050, 5_000, 100)
    ]
    hits = [n for n in named if n.verdict is Verdict.NAMED and n.instrument == tank.LEVEL]
    assert len(hits) * 2 >= len(named)


def test_a_lying_inflow_meter_is_not_blamed_on_the_level(plant: PlantMap) -> None:
    run = tank.simulate(6_000, seed=5, inflow_liar=(3_000, 5_000, 30.0))
    scores = map_scores(plant, run.reported)
    rows = [r for r in range(3_050, 5_000, 100) if scores[r, tank.LEVEL] > 1.0]
    assert len(rows) >= 10, "the lie must reach the level for this test to mean anything"
    for row in rows:
        naming = name_instrument(plant, run.reported, row=row, column=tank.LEVEL, onset=3_000)
        assert naming.instrument != tank.LEVEL
        assert naming.verdict in {Verdict.NAMED, Verdict.NOT_SEPARABLE}
        if naming.verdict is Verdict.NAMED:
            assert naming.instrument == tank.INFLOW


def test_a_drop_one_with_no_driver_left_cannot_testify(plant: PlantMap) -> None:
    run = tank.simulate(6_000, seed=5, inflow_liar=(3_000, 5_000, 30.0))
    naming = name_instrument(plant, run.reported, row=3_500, column=tank.LEVEL, onset=3_000)
    (inflow,) = [check for check in naming.checks if check.candidate == tank.INFLOW]
    assert plant.drivers_of(tank.INFLOW) == (tank.VALVE,)
    assert inflow.inconclusive == (tank.VALVE,)


def test_a_naming_lists_its_inconclusive_drop_one_checks(plant: PlantMap) -> None:
    run = tank.simulate(6_000, seed=3, liar=(3_000, 5_000, 1.0))
    naming = name_instrument(plant, run.reported, row=3_500, column=tank.LEVEL, onset=3_000)
    (level,) = [check for check in naming.checks if check.candidate == tank.LEVEL]
    drivers = set(plant.drivers_of(tank.LEVEL))
    assert set(level.inconclusive) <= drivers
    assert set(level.decisively_in_band) <= drivers
    assert not set(level.inconclusive) & set(level.decisively_in_band)


def test_the_lying_level_is_reconstructed_from_its_drivers(plant: PlantMap) -> None:
    run = tank.simulate(6_000, seed=3, liar=(3_000, 5_000, 1.0))
    rebuilt = reconstruct(plant, run.reported, tank.LEVEL, onset=3_000, end=3_600)
    assert rebuilt is not None and rebuilt.form is Form.INCREMENT
    assert rebuilt.anchor is not None and rebuilt.anchor < 3_000
    truth = run.true_level[rebuilt.rows]
    error = numpy.abs(rebuilt.centre - truth)
    reported_error = numpy.abs(run.reported[rebuilt.rows, tank.LEVEL] - truth)
    assert numpy.median(error) < 0.1 * numpy.median(reported_error)
    assert numpy.mean(error <= rebuilt.half_width) > 0.9


def test_the_band_of_an_integrated_reconstruction_widens(plant: PlantMap) -> None:
    run = tank.simulate(6_000, seed=3, liar=(3_000, 5_000, 1.0))
    rebuilt = reconstruct(plant, run.reported, tank.LEVEL, onset=3_000, end=4_000)
    assert rebuilt is not None
    assert rebuilt.half_width[-1] > rebuilt.half_width[0]


def test_a_forced_valve_names_no_lying_instrument(plant: PlantMap) -> None:
    run = tank.simulate(6_000, seed=4, forced_valve=(3_000, 4_000, 90.0))
    scores = map_scores(plant, run.reported)
    window = scores[3_000:4_200]
    row = 3_000 + int(numpy.argmax(window.max(axis=1)))
    column = int(numpy.argmax(scores[row]))
    naming = name_instrument(plant, run.reported, row=row, column=column, onset=3_000)
    assert naming.verdict is not Verdict.NAMED or naming.instrument not in {
        tank.LEVEL,
        tank.QUALITY,
        tank.OUTFLOW,
    }


def test_the_frozen_detector_is_unchanged_by_the_map(train: tank.Run) -> None:
    attack = numpy.zeros(train.reported.shape[0], dtype=numpy.bool_)
    files = [TrainFile(values=train.reported, attack=attack)]
    before = consistency.feature_scores(consistency.fit(files), train.reported[:4_000])
    _fit(train)
    after = consistency.feature_scores(consistency.fit(files), train.reported[:4_000])
    assert numpy.array_equal(before, after)


# ---------------------------------------------------------------------------- ADR 0135's rules


def test_adr_0135_still_names_the_lying_level(plant: PlantMap) -> None:
    run = tank.simulate(6_000, seed=3, liar=(3_000, 5_000, 1.0))
    named = [
        name_instrument(
            plant, run.reported, row=r, column=tank.LEVEL, onset=3_000, rules="adr-0135"
        )
        for r in range(3_100, 4_200, 100)
    ]
    hits = [n for n in named if n.verdict is Verdict.NAMED and n.instrument == tank.LEVEL]
    assert len(hits) * 2 >= len(named)
    assert all(n.instrument in {None, tank.LEVEL} for n in named)


def test_adr_0135_never_blames_the_level_for_a_lying_inflow_meter(plant: PlantMap) -> None:
    run = tank.simulate(6_000, seed=5, inflow_liar=(3_000, 5_000, 30.0))
    scores = map_scores(plant, run.reported)
    for row in [r for r in range(3_050, 5_000, 100) if scores[r, tank.LEVEL] > 1.0]:
        naming = name_instrument(
            plant, run.reported, row=row, column=tank.LEVEL, onset=3_000, rules="adr-0135"
        )
        assert naming.instrument != tank.LEVEL


def test_a_candidate_whose_upstream_is_out_of_band_is_not_named(plant: PlantMap) -> None:
    # The inflow meter lies, so the inflow is out of band; under ADR 0135 the level, downstream of
    # it, may not be named even at rows where it disagrees with its own drivers.
    run = tank.simulate(6_000, seed=5, inflow_liar=(3_000, 5_000, 30.0))
    naming = name_instrument(
        plant, run.reported, row=3_450, column=tank.LEVEL, onset=3_000, rules="adr-0135"
    )
    (level,) = [c for c in naming.checks if c.candidate == tank.LEVEL]
    assert not level.passes


def test_unknown_naming_rules_are_refused(plant: PlantMap) -> None:
    run = tank.simulate(600, seed=3)
    with pytest.raises(ValueError, match="unknown naming rules"):
        name_instrument(plant, run.reported, row=500, column=tank.LEVEL, rules="mine")

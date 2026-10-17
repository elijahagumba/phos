"""The plant-map challenger (ADR 0123 §7) on the test tank: it extends the frozen detector."""

import numpy
import pytest
import tests.atlas.plant_map_fixture as tank
from tests.atlas.test_plant_map import SETTINGS

from phos.atlas import consistency
from phos.atlas.consistency import THRESHOLD, TrainFile
from phos.atlas.consistency_windows import windows_for_period
from phos.atlas.plant_map_detector import (
    RESULT_NAME,
    Arm,
    PlantMapDetector,
    detect_alerts,
    detector_components,
    detector_events,
    fit_detector,
    map_carried,
)
from phos.atlas.plant_map_naming import Verdict, name_instrument

WINDOWS = windows_for_period(1.0)


def _fit(
    run: tank.Run, arm: Arm = Arm.EXTEND, unroled: frozenset[str] = frozenset()
) -> PlantMapDetector:
    attack = numpy.zeros(run.reported.shape[0], dtype=numpy.bool_)
    return fit_detector(
        [TrainFile(values=run.reported, attack=attack)],
        tank.NAMES,
        tank.roles(unroled=unroled),
        period_seconds=1.0,
        windows=WINDOWS,
        settings=SETTINGS,
        arm=arm,
    )


@pytest.fixture(scope="module")
def train() -> tank.Run:
    return tank.simulate(12_000, seed=1)


@pytest.fixture(scope="module")
def detector(train: tank.Run) -> PlantMapDetector:
    return _fit(train)


def test_the_result_name_is_the_adr_s() -> None:
    assert RESULT_NAME == "atlas-plant-map-v1"


def test_with_no_map_the_challenger_is_the_frozen_detector(train: tank.Run) -> None:
    empty = _fit(train, unroled=frozenset(tank.NAMES))
    assert not empty.plant.targets
    attack = numpy.zeros(train.reported.shape[0], dtype=numpy.bool_)
    frozen = consistency.fit([TrainFile(values=train.reported, attack=attack)], WINDOWS)
    run = tank.simulate(6_000, seed=3, liar=(3_000, 5_000, 1.0))
    assert numpy.array_equal(empty.consistency.divisor, frozen.divisor)
    ours = [(e.onset, e.column) for e in detector_events(empty, run.reported)]
    theirs = [
        (e.onset, e.column)
        for e in consistency.events(
            consistency.feature_scores(frozen, run.reported), windows=WINDOWS
        )
    ]
    assert ours == theirs


def test_the_challenger_s_score_is_the_maximum_of_its_three(detector: PlantMapDetector) -> None:
    run = tank.simulate(6_000, seed=3, liar=(3_000, 5_000, 1.0))
    parts = detector_components(detector, run.reported)
    combined = parts.combined()
    assert numpy.array_equal(
        combined, numpy.maximum(numpy.maximum(parts.loop, parts.rng), parts.map)
    )
    assert (combined >= parts.map).all()


#: The tank without its quality signal: no independent witness of the true level, which is the
#: water liar's situation (ADR 0123 Context 3). The controller follows the lie.
NO_WITNESS = (tank.LEVEL, tank.INFLOW, tank.OUTFLOW, tank.VALVE, tank.TARGET)


def test_without_a_witness_the_map_carries_the_lie_and_names_the_level(train: tank.Run) -> None:
    names = tuple(tank.NAMES[i] for i in NO_WITNESS)
    values = train.reported[:, NO_WITNESS]
    detector = fit_detector(
        [TrainFile(values=values, attack=numpy.zeros(values.shape[0], dtype=numpy.bool_))],
        names,
        tank.roles(names=names),
        period_seconds=1.0,
        windows=WINDOWS,
        settings=SETTINGS,
    )
    run = tank.simulate(6_000, seed=3, liar=(3_000, 6_000, 1.0)).reported[:, NO_WITNESS]
    parts = detector_components(detector, run)
    assert parts.loop[3_000:, 0].max() < parts.map[3_000:, 0].max() / 4
    carried = [
        e for e in detector_events(detector, run) if e.onset >= 3_000 and map_carried(parts, e)
    ]
    assert [e.column for e in carried] == [0]
    onset = min(member[0] for member in carried[0].members)
    naming = name_instrument(detector.plant, run, row=carried[0].onset, column=0, onset=onset)
    assert naming.verdict is Verdict.NAMED
    assert naming.instrument == 0


def test_normal_operation_raises_few_alerts(detector: PlantMapDetector) -> None:
    run = tank.simulate(8_000, seed=4)
    time = numpy.arange(run.reported.shape[0], dtype=numpy.float64)
    rows, _columns, _scores = detect_alerts(detector, run.reported, time)
    assert len(rows) <= 2 * consistency.ALERTS_PER_SHIFT


def test_the_replace_arm_has_no_loop_score(train: tank.Run) -> None:
    replaced = _fit(train, arm=Arm.REPLACE)
    run = tank.simulate(6_000, seed=3, liar=(3_000, 5_000, 1.0))
    parts = detector_components(replaced, run.reported)
    assert not parts.loop.any()
    assert (parts.combined() > THRESHOLD).any()

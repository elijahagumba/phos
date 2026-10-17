"""The challenger's events become evidence (ADR 0123 §5): the tank without its quality witness."""

from datetime import UTC, datetime, timedelta

import numpy
import pytest
import tests.atlas.plant_map_fixture as tank
from tests.atlas.test_plant_map import SETTINGS
from tests.atlas.test_plant_map_detector import NO_WITNESS, WINDOWS

from phos.atlas.consistency import TrainFile
from phos.atlas.consistency_evidence import CROSS_SIGNAL_MISMATCH, EXPECTED_VALUE_CONTEXT_KEY
from phos.atlas.plant_map_detector import PlantMapDetector, fit_detector
from phos.atlas.plant_map_evidence import (
    BROKEN_LINK_CONTEXT_KEY,
    INSTRUMENT_CHECKS_CONTEXT_KEY,
    INSTRUMENT_CONTEXT_KEY,
    RECONSTRUCTION_ANCHOR_CONTEXT_KEY,
    PlantMapPromotion,
    promote_plant_map,
)
from phos.atlas.plant_map_naming import Verdict
from phos.ontology import EntityId, FacetKind
from phos.reasoning import FittedPlattCalibrator, is_out_of_band

CERTAIN = FittedPlattCalibrator(coefficient=0.0, intercept=40.0)
NAMES = tuple(tank.NAMES[i] for i in NO_WITNESS)
ENTITY = {name: EntityId(f"tank/{name}") for name in NAMES}
START = datetime(2026, 1, 1, tzinfo=UTC)


def _promote(detector: PlantMapDetector, values: numpy.ndarray) -> PlantMapPromotion:
    stamps = [START + timedelta(seconds=i) for i in range(values.shape[0])]
    return promote_plant_map(
        detector, values, stamps, NAMES, ENTITY, CERTAIN, (START, START + timedelta(hours=3))
    )


@pytest.fixture(scope="module")
def lie() -> tuple[tank.Run, PlantMapPromotion]:
    run = tank.simulate(6_000, seed=3, liar=(3_000, 6_000, 1.0))
    return run, _promote(_fitted(), run.reported[:, NO_WITNESS])


_CACHE: dict[str, PlantMapDetector] = {}


def _fitted() -> PlantMapDetector:
    if "d" not in _CACHE:
        values = tank.simulate(12_000, seed=1).reported[:, NO_WITNESS]
        _CACHE["d"] = fit_detector(
            [TrainFile(values=values, attack=numpy.zeros(values.shape[0], dtype=numpy.bool_))],
            NAMES,
            tank.roles(names=NAMES),
            period_seconds=1.0,
            windows=WINDOWS,
            settings=SETTINGS,
        )
    return _CACHE["d"]


def test_the_lie_is_promoted_as_a_map_fact_naming_the_level(
    lie: tuple[tank.Run, PlantMapPromotion],
) -> None:
    _run, promotion = lie
    (record,) = [r for r in promotion.records if r.onset >= 3_000 and r.carried_by == "map"]
    assert record.promoted == "map"
    assert record.naming is not None and record.naming.verdict is Verdict.NAMED
    (fact,) = [f for f in promotion.evidence.facts if f.observation.feature == "level"]
    context = fact.observation.context
    assert context[INSTRUMENT_CONTEXT_KEY] == "level"
    assert "inflow -> level" in context[BROKEN_LINK_CONTEXT_KEY]
    assert "disagrees with its drivers" in context[INSTRUMENT_CHECKS_CONTEXT_KEY]
    assert context[RECONSTRUCTION_ANCHOR_CONTEXT_KEY].startswith("2026-01-01T00:")
    assert fact.evidence.facet_kind is FacetKind.CONSISTENCY
    assert fact.evidence.facet == CROSS_SIGNAL_MISMATCH
    assert is_out_of_band(fact.deviation, fact.observation)
    assert "its drivers imply" in fact.evidence.summary


def test_the_expected_value_is_closer_to_the_truth_than_the_lie(
    lie: tuple[tank.Run, PlantMapPromotion],
) -> None:
    run, promotion = lie
    (fact,) = [f for f in promotion.evidence.facts if f.observation.feature == "level"]
    row = int((fact.observation.timestamp - START).total_seconds())
    expected = float(fact.observation.context[EXPECTED_VALUE_CONTEXT_KEY])
    truth = float(run.true_level[row])
    assert abs(expected - truth) < abs(fact.observation.value - truth) / 4
    assert fact.deviation.expected.low <= truth <= fact.deviation.expected.high


def test_every_event_has_a_record_and_no_fact_lacks_one(
    lie: tuple[tank.Run, PlantMapPromotion],
) -> None:
    _run, promotion = lie
    promoted = [r for r in promotion.records if r.promoted is not None]
    assert len(promoted) == len(promotion.evidence.facts)
    assert all(r.carried_by in {"map", "loop", "range"} for r in promotion.records)


def test_a_reading_the_plant_follows_is_never_promoted() -> None:
    run = tank.simulate(6_000, seed=4, forced_valve=(3_000, 4_000, 90.0))
    promotion = _promote(_fitted(), run.reported[:, NO_WITNESS])
    for record in promotion.records:
        if record.naming is not None and record.naming.verdict is Verdict.PLANT_CHANGED:
            assert record.promoted is None


def test_the_features_must_be_the_map_s() -> None:
    values = tank.simulate(600, seed=4).reported[:, NO_WITNESS]
    stamps = [START + timedelta(seconds=i) for i in range(values.shape[0])]
    with pytest.raises(ValueError, match="map's signals"):
        promote_plant_map(
            _fitted(), values, stamps, tuple(reversed(NAMES)), ENTITY, CERTAIN, (START, START)
        )

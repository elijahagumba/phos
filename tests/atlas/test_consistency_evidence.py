"""ADR 0108: a reading that disagrees with the rest of the plant becomes evidence, and routes."""

from datetime import UTC, datetime, timedelta

import numpy
import pytest
from tests.atlas.test_engine import corpus, fitted_on_clean_plant, vertical

from phos.atlas import (
    CROSS_SIGNAL_MISMATCH,
    ENGINEERING_MAINTENANCE_TEMPLATE_ID,
    EXPECTED_VALUE_CONTEXT_KEY,
    PROCESS_DISTURBANCE_TEMPLATE_ID,
    SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID,
    UNAUTHORISED_CONTROL_TEMPLATE_ID,
    AtlasEngine,
    ConsistencyEvidence,
    atlas_library,
    consistency_feature_of,
    promote_consistency,
)
from phos.atlas.consistency import TrainFile, fit
from phos.ontology import Domain, EvidenceRole, FacetKind, Narrative
from phos.reasoning import FittedPlattCalibrator, is_out_of_band

CERTAIN = FittedPlattCalibrator(coefficient=0.0, intercept=40.0)
START = datetime(2026, 3, 1, tzinfo=UTC)
FEATURES = ("command", "flow", "level", "dead", "noise")
ENTITIES = dict.fromkeys(FEATURES, "ent_plant00001")
LIAR = (4000, 4300)


def _plant(rows: int, seed: int, liar: bool = False) -> tuple[numpy.ndarray, numpy.ndarray]:
    """Return (reported, true) readings: the flow instrument freezes during the liar window."""
    rng = numpy.random.default_rng(seed)
    t = numpy.arange(rows, dtype=numpy.float64)
    command = 50.0 + 20.0 * numpy.sin(2.0 * numpy.pi * t / 600.0)
    flow = 2.0 * numpy.roll(command, 10) + rng.normal(0.0, 0.5, rows)
    level = command + flow + rng.normal(0.0, 0.5, rows)
    true = numpy.column_stack([command, flow, level, numpy.full(rows, 3.0), rng.normal(0, 1, rows)])
    reported = true.copy()
    if liar:
        start, end = LIAR
        reported[start:end, 1] = reported[start, 1]
    return reported, true


def _promoted() -> tuple[ConsistencyEvidence, numpy.ndarray, numpy.ndarray]:
    first, _ = _plant(6000, 1)
    second, _ = _plant(6000, 2)
    model = fit(
        [
            TrainFile(values=first, attack=numpy.zeros(6000, dtype=bool)),
            TrainFile(values=second, attack=numpy.zeros(6000, dtype=bool)),
        ]
    )
    reported, true = _plant(9000, 3, liar=True)
    stamps = [START + timedelta(seconds=row) for row in range(9000)]
    bundle = promote_consistency(
        model,
        reported,
        stamps,
        FEATURES,
        ENTITIES,
        CERTAIN,
        (START - timedelta(days=1), START),
    )
    return bundle, reported, true


def test_a_frozen_instrument_becomes_a_cross_signal_mismatch_on_that_instrument() -> None:
    bundle, _reported, _true = _promoted()
    start, end = LIAR
    inside = [
        fact
        for fact in bundle.facts
        if START + timedelta(seconds=start)
        <= fact.observation.timestamp
        < START + timedelta(seconds=end)
    ]
    assert inside, "the frozen flow instrument must be promoted"
    fact = inside[0]
    assert fact.observation.feature == "flow"
    assert fact.evidence.facet_kind is FacetKind.CONSISTENCY
    assert consistency_feature_of(fact.evidence) == CROSS_SIGNAL_MISMATCH
    assert fact.evidence.source_id == fact.deviation.id
    assert is_out_of_band(fact.deviation, fact.observation)


def test_the_expected_value_is_closer_to_the_truth_than_the_lying_reading() -> None:
    bundle, reported, true = _promoted()
    start, end = LIAR
    for fact in bundle.facts:
        row = int((fact.observation.timestamp - START).total_seconds())
        if not start <= row < end or fact.observation.feature != "flow":
            continue
        expected = float(fact.observation.context[EXPECTED_VALUE_CONTEXT_KEY])
        assert abs(expected - true[row, 1]) < abs(reported[row, 1] - true[row, 1])
        assert "the rest of the plant implies about" in fact.evidence.summary
        return
    pytest.fail("no promoted flow fact inside the liar window")


def test_every_fact_carries_a_calibrated_weight() -> None:
    bundle, _reported, _true = _promoted()
    assert bundle.facts
    assert all(0.0 <= fact.evidence.weight <= 1.0 for fact in bundle.facts)
    assert all(fact.evidence.weight > 0.99 for fact in bundle.facts)  # CERTAIN


def test_the_fact_supports_an_instrument_fault_and_contradicts_a_process_upset() -> None:
    bundle, _reported, _true = _promoted()
    evidence = bundle.facts[0].evidence
    matches = atlas_library().matches(evidence, {})
    table = {match.template.template_id: match.role for match in matches}
    assert table[SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID] is EvidenceRole.SUPPORTING
    assert table[PROCESS_DISTURBANCE_TEMPLATE_ID] is EvidenceRole.CONTRADICTORY
    assert ENGINEERING_MAINTENANCE_TEMPLATE_ID not in table
    assert UNAUTHORISED_CONTROL_TEMPLATE_ID not in table


def test_a_signal_without_an_entity_is_refused() -> None:
    first, _ = _plant(6000, 1)
    model = fit([TrainFile(values=first, attack=numpy.zeros(6000, dtype=bool))])
    reported, _ = _plant(9000, 3, liar=True)
    stamps = [START + timedelta(seconds=row) for row in range(9000)]
    with pytest.raises(ValueError, match="has no entity"):
        promote_consistency(model, reported, stamps, FEATURES, {}, CERTAIN, (START, START))


def test_shapes_that_disagree_are_refused() -> None:
    first, _ = _plant(6000, 1)
    model = fit([TrainFile(values=first, attack=numpy.zeros(6000, dtype=bool))])
    reported, _ = _plant(100, 3)
    with pytest.raises(ValueError, match="timestamps"):
        promote_consistency(model, reported, [START], FEATURES, ENTITIES, CERTAIN, (START, START))


def _rank(engine: AtlasEngine, narratives: list[Narrative]) -> list[str]:
    by_id = {hypothesis.id: hypothesis.template_id for hypothesis in engine.store.hypotheses()}
    return [by_id[item] for item in narratives[0].hypothesis_ids]


def test_omitted_and_empty_consistency_produce_the_same_ranking() -> None:
    data = corpus(60, surge={"FT01": 40.0, "FT01Z": 20.0}, surge_rows=range(40, 46))
    omitted = vertical(fitted_on_clean_plant())
    empty = vertical(fitted_on_clean_plant())
    left = omitted.run(data)
    right = empty.run(data, consistency=ConsistencyEvidence())
    assert left and right
    assert _rank(omitted, left) == _rank(empty, right)


def test_the_engine_stores_the_chain_and_reasons_over_the_fact() -> None:
    bundle, _reported, _true = _promoted()
    engine = vertical(fitted_on_clean_plant())
    narratives = engine.run(corpus(60), consistency=bundle)
    assert narratives
    fact = bundle.facts[0]
    assert engine.store.get_observation(fact.observation.id) is not None
    assert engine.store.get_deviation(fact.deviation.id) is not None
    supporting = {
        evidence_id
        for hypothesis in engine.store.hypotheses()
        if hypothesis.template_id == SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID
        for evidence_id in hypothesis.supporting
    }
    assert fact.evidence.id in supporting
    assert fact.evidence.domain is Domain.ATLAS

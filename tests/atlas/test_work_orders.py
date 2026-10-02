"""Session E3: work-order inlet. Empty is a no-op; present supports maintenance."""

from datetime import UTC, datetime

from tests.atlas.test_engine import corpus, fitted_on_clean_plant, vertical

from phos.atlas import (
    ENGINEERING_MAINTENANCE_TEMPLATE_ID,
    UNAUTHORISED_CONTROL_TEMPLATE_ID,
    WORK_ORDER_MARKER,
    AtlasEngine,
    WorkOrderEvidence,
    atlas_library,
    promote_work_orders,
    work_order_feature_of,
)
from phos.ontology import Domain, EvidenceRole, Narrative, Observation
from phos.reasoning import FittedPlattCalibrator

CERTAIN = FittedPlattCalibrator(coefficient=0.0, intercept=40.0)
STAMP = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


def _ticket() -> Observation:
    return Observation(
        entity_ids=["wo_fixture", "ent_plant00001"],
        feature="work_order",
        value=1.0,
        timestamp=STAMP,
        domain=Domain.ATLAS,
        context={"ticket": "WO-1"},
    )


def test_an_empty_inlet_promotes_nothing() -> None:
    assert promote_work_orders([], CERTAIN) == []


def test_a_work_order_supports_maintenance_and_contradicts_unauthorised_control() -> None:
    fact = promote_work_orders([_ticket()], CERTAIN)[0]
    assert fact.evidence.summary.startswith(WORK_ORDER_MARKER)
    assert work_order_feature_of(fact.evidence) == "work_order"
    table = {
        match.template.template_id: match.role
        for match in atlas_library().matches(fact.evidence, {})
    }
    assert table[ENGINEERING_MAINTENANCE_TEMPLATE_ID] is EvidenceRole.SUPPORTING
    assert table[UNAUTHORISED_CONTROL_TEMPLATE_ID] is EvidenceRole.CONTRADICTORY


def _rank(engine: AtlasEngine, narratives: list[Narrative]) -> list[str]:
    by_id = {hypothesis.id: hypothesis.template_id for hypothesis in engine.store.hypotheses()}
    return [by_id[item] for item in narratives[0].hypothesis_ids]


def test_omitted_and_empty_work_orders_produce_the_same_ranking() -> None:
    data = corpus(60, surge={"FT01": 40.0, "FT01Z": 20.0}, surge_rows=range(40, 46))
    omitted = vertical(fitted_on_clean_plant())
    empty = vertical(fitted_on_clean_plant())
    left = omitted.run(data)
    right = empty.run(data, work_orders=WorkOrderEvidence())
    assert left and right
    assert _rank(omitted, left) == _rank(empty, right)

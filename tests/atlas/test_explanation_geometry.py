"""Session E1: fault vs disturbance from evidence shape, not a new prior."""

from datetime import timedelta

from tests.atlas.test_grouping import EPOCH, fact, topology
from tests.atlas.test_templates import roles

from phos.atlas import (
    PROCESS_DISTURBANCE_TEMPLATE_ID,
    SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID,
    group_evidence,
)
from phos.ontology import Evidence, EvidenceRole

WINDOW = timedelta(minutes=1)


def _event(*signals: str) -> Evidence:
    members = [fact(signal, EPOCH) for signal in signals]
    evidence = [item[2] for item in members]
    deviations = {item[1].id: item[1] for item in members}
    grouped = group_evidence(evidence, topology(), WINDOW, deviations)
    assert len(grouped) == 1
    return grouped[0]


def test_one_transmitter_drift_is_shaped_like_a_fault() -> None:
    table = roles(_event("FT01"))
    assert table[SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID] is EvidenceRole.SUPPORTING
    assert table[PROCESS_DISTURBANCE_TEMPLATE_ID] is EvidenceRole.CONTRADICTORY


def test_plant_wide_demand_is_shaped_like_a_disturbance() -> None:
    table = roles(_event("FT01", "FT01Z", "PT01"))
    assert table[PROCESS_DISTURBANCE_TEMPLATE_ID] is EvidenceRole.SUPPORTING
    assert table[SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID] is EvidenceRole.CONTRADICTORY

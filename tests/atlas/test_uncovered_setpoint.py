"""An uncovered setpoint supports unauthorised control and counts against the other two."""

from datetime import UTC, datetime

from phos.atlas.templates import (
    ENGINEERING_MAINTENANCE_TEMPLATE_ID,
    SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID,
    UNAUTHORISED_CONTROL_TEMPLATE_ID,
    UNCOVERED_SETPOINT,
    atlas_templates,
)
from phos.ontology import Domain, Evidence, EvidenceKind, EvidenceRole, FacetKind


def _fact() -> Evidence:
    return Evidence(
        kind=EvidenceKind.DEVIATION,
        source_id="dev_uncovered",
        entity_ids=["ent_setpoint"],
        timestamp=datetime(2026, 10, 1, tzinfo=UTC),
        domain=Domain.ATLAS,
        weight=0.5,
        summary="setpoint left the quiet-train envelope",
        facet_kind=FacetKind.UNCOVERED_SETPOINT,
        facet=UNCOVERED_SETPOINT,
    )


def test_an_uncovered_setpoint_bears_on_the_three_declared_explanations() -> None:
    """Supports the attack, contradicts maintenance, contradicts a sensor fault."""
    fact = _fact()
    roles = {
        template.template_id: template.role_for(fact, {})
        for template in atlas_templates()
        if template.template_id
        in {
            SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID,
            ENGINEERING_MAINTENANCE_TEMPLATE_ID,
            UNAUTHORISED_CONTROL_TEMPLATE_ID,
        }
    }
    assert roles[UNAUTHORISED_CONTROL_TEMPLATE_ID] is EvidenceRole.SUPPORTING
    assert roles[ENGINEERING_MAINTENANCE_TEMPLATE_ID] is EvidenceRole.CONTRADICTORY
    assert roles[SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID] is EvidenceRole.CONTRADICTORY

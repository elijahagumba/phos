"""Session S5: HR/change-ticket inlet is a fixture. Empty is a no-op. CERT has no such field."""

from datetime import UTC, datetime

from phos.ontology import Domain, Observation
from phos.reasoning import FittedPlattCalibrator
from phos.sentiel import HR_TICKET_MARKER, promote_hr_tickets
from phos.sentiel.hr_tickets import hr_ticket_feature_of

CERTAIN = FittedPlattCalibrator(coefficient=0.0, intercept=40.0)
STAMP = datetime(2010, 1, 4, tzinfo=UTC)


def test_an_empty_hr_inlet_promotes_nothing() -> None:
    assert promote_hr_tickets([], CERTAIN) == []


def test_a_fixture_ticket_is_stamped() -> None:
    finding = Observation(
        entity_ids=["ticket_hr1", "user_ALICE"],
        feature="hr_ticket",
        value=1.0,
        timestamp=STAMP,
        domain=Domain.SENTIEL,
    )
    fact = promote_hr_tickets([finding], CERTAIN)[0]
    assert fact.evidence.summary.startswith(HR_TICKET_MARKER)
    assert hr_ticket_feature_of(fact.evidence) == "hr_ticket"

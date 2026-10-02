"""Session E2: identical evidence lists are not knowledge; the residual leads."""

from datetime import timedelta

from tests.reasoning.test_engine import T0, _saturating_rivals, engine, evidence

from phos.ontology import Domain
from phos.reasoning import INSUFFICIENT_EVIDENCE_TEMPLATE_ID, prior_only_rivals

RESIDUAL = INSUFFICIENT_EVIDENCE_TEMPLATE_ID


def test_prior_only_rivals_raise_insufficient_evidence_before_the_ceiling() -> None:
    """Three fully-trusted facts do not saturate; priors would still pick a unique winner.

    Session E2 forbids presenting that winner as knowledge when the evidence lists match.
    """
    reasoning = engine(library=_saturating_rivals())
    reasoning.ingest([evidence(weight=1.0, at=T0 + timedelta(minutes=index)) for index in range(3)])
    competing = reasoning.competing(Domain.ATLAS)
    assert prior_only_rivals(competing)
    assert competing[0].template_id == RESIDUAL
    assert competing[0].confidence < competing[1].confidence

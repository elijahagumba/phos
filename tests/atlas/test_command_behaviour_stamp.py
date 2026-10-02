"""Session D1: command-behaviour departures are stamped like graph findings."""

from tests.atlas.test_command_evidence import CERTAIN, fitted_on_normal, steady_then_spike

from phos.atlas import (
    COMMAND_BEHAVIOUR_MARKER,
    ENGINEERING_MAINTENANCE_TEMPLATE_ID,
    UNAUTHORISED_CONTROL_TEMPLATE_ID,
    command_behaviour_feature_of,
    command_behaviour_marker,
    promote_command_behaviour,
)
from phos.atlas.templates import atlas_library
from phos.ontology import EvidenceRole


def test_a_promoted_departure_declares_its_feature_on_the_summary() -> None:
    training, live = steady_then_spike()
    departure = promote_command_behaviour(live, fitted_on_normal().fit(training), CERTAIN)[0]
    assert departure.evidence.summary.startswith(COMMAND_BEHAVIOUR_MARKER)
    assert command_behaviour_feature_of(departure.evidence) == departure.observation.feature
    assert command_behaviour_marker(departure.observation.feature) in departure.evidence.summary


def test_a_stamped_departure_reaches_both_control_explanations() -> None:
    """What survives of D1's limit, restated (ADR 0071).

    D1 stamped the fact and wired no matcher, and this test asserted that nothing matched. ADR
    0070 typed the stamp and ADR 0071 gave it a consumer, so it now reaches the two explanations
    that involve somebody operating a device — and neither process explanation, which is the half
    of the old limit that genuinely survives. Known-station indistinguishability is untouched:
    both roles are SUPPORTING, so no matcher here separates an engineer from an attacker.
    """
    training, live = steady_then_spike()
    departure = promote_command_behaviour(live, fitted_on_normal().fit(training), CERTAIN)[0]

    table = {
        match.template.template_id: match.role
        for match in atlas_library().matches(departure.evidence, {})
    }

    assert table == {
        ENGINEERING_MAINTENANCE_TEMPLATE_ID: EvidenceRole.SUPPORTING,
        UNAUTHORISED_CONTROL_TEMPLATE_ID: EvidenceRole.SUPPORTING,
    }

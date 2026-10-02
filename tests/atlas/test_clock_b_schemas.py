"""Clock B schemas against the objects that actually shipped.

Does not retune Atlas templates, invent a distillation phase, un-retire CERT peer advantage,
or claim Mahalanobis lost on HAI.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from phos.atlas.command_reconstruction import (
    CommandReconstruction,
    IssuerKind,
    reconstruction_completeness,
)
from phos.atlas.transitions import (
    DISTILLATION_HAS_NO_DECLARED_PHASE,
    DeclaredPhaseTransitionModel,
    refuse_inferred_phase,
)
from phos.ontology import Evidence, Hypothesis
from phos.ontology.enums import Domain, EvidenceKind, EvidenceRole, HypothesisStatus
from phos.reasoning.counterfactual import (
    ExpectedConsequence,
    attach_forecast_outcome,
    consequences_for,
)
from phos.sentiel.identity import IdentityLayerScores, score_identity_layers
from phos.sentiel.sequences import (
    REPLACES_CERT_SIX_B,
    count_baseline_surprise,
    sequence_surprise,
)

T0 = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)


def test_command_reconstruction_records_who_what_path_when_state() -> None:
    record = CommandReconstruction(
        issuer_id="plc_engineering_01",
        issuer_kind=IssuerKind.UNKNOWN_MASTER,
        function="write_single_register",
        path=("engineering", "switch", "plc"),
        timestamp=T0,
        plant_state="HEAT",
        expected=False,
        downstream_observation_ids=("obs_tank_level",),
    )
    assert record.issuer_kind is IssuerKind.UNKNOWN_MASTER
    assert reconstruction_completeness(record) == 1.0
    assert record.lead_rate is None


def test_incomplete_reconstruction_is_not_a_lead_rate() -> None:
    record = CommandReconstruction(
        issuer_id="scada",
        issuer_kind=IssuerKind.KNOWN_STATION,
        function="write_multiple_registers",
        path=(),
        timestamp=T0,
        plant_state=None,
        expected=None,
        downstream_observation_ids=(),
    )
    assert 0.0 < reconstruction_completeness(record) < 1.0
    assert record.lead_rate is None


def test_declared_phase_model_flags_an_unlearned_transition() -> None:
    model = DeclaredPhaseTransitionModel.fit((0, 1, 2, 0, 1, 2))
    assert model.unexpected_indices((0, 1, 2, 0, 2)) == (4,)


def test_distillation_phase_inference_is_refused() -> None:
    assert refuse_inferred_phase("batch-distillation") == DISTILLATION_HAS_NO_DECLARED_PHASE
    with pytest.raises(ValueError, match="declared"):
        DeclaredPhaseTransitionModel.fit(())


def test_identity_layers_are_separate_and_peer_stays_retired_on_cert() -> None:
    scores = score_identity_layers(
        self_value=12.0,
        self_mean=4.0,
        self_std=1.0,
        role_value=12.0,
        role_mean=11.0,
        role_std=2.0,
        org_value=12.0,
        org_mean=10.0,
        org_std=3.0,
        temporal_value=12.0,
        temporal_mean=5.0,
        temporal_std=1.5,
        corpus="cert-r3.1",
    )
    assert isinstance(scores, IdentityLayerScores)
    assert scores.self_score > scores.role_score
    assert scores.peer_score is None
    assert scores.pooled_unusual is None


def test_sequence_surprise_can_exceed_count_baseline_on_a_rare_path() -> None:
    trained = (
        ("logon", "host", "file"),
        ("logon", "host", "file"),
        ("logon", "host", "file"),
        ("logon", "host", "mail"),
    )
    seq = sequence_surprise(("logon", "host", "priv", "exfil"), trained)
    counts = count_baseline_surprise(("file",) * 4, ("file",) * 4)
    assert seq > counts
    assert REPLACES_CERT_SIX_B is False


def test_counterfactual_attaches_forecast_miss_as_contradictory() -> None:
    hypothesis = Hypothesis(
        label="Planned engineering or maintenance change",
        template_id="engineering_maintenance",
        domain=Domain.ATLAS,
        prior=0.2,
        confidence=0.2,
        status=HypothesisStatus.ACTIVE,
        created_at=T0,
        updated_at=T0,
    )
    evidence = Evidence(
        kind=EvidenceKind.FORECAST_MISS,
        source_id="fc_00000000000b",
        entity_ids=["ent_engineering"],
        timestamp=T0 + timedelta(minutes=1),
        domain=Domain.ATLAS,
        summary="Expected an engineering-station issuer under maintenance; did not observe one.",
    )
    updated = attach_forecast_outcome(hypothesis, evidence, observed_as_predicted=False)
    assert evidence.id in updated.contradictory
    assert evidence.id not in updated.supporting
    assert EvidenceRole.CONTRADICTORY is EvidenceRole.CONTRADICTORY


def test_maintenance_and_unauthorised_templates_declare_distinct_consequences() -> None:
    maintenance = consequences_for("engineering_maintenance")
    attack = consequences_for("unauthorised_control_activity")
    assert maintenance
    assert attack
    assert {item.feature for item in maintenance} != {item.feature for item in attack}
    assert all(isinstance(item, ExpectedConsequence) for item in maintenance)

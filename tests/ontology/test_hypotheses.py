"""Tests for the Hypothesis model and its evidence-linking invariant."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from phos.ontology.enums import Domain, EvidenceRole, HypothesisStatus
from phos.ontology.hypotheses import Hypothesis

# Deliberately in the past so `updated_at` refresh assertions are time-independent.
T0 = datetime(2026, 1, 15, 9, 0, tzinfo=UTC)


def make_hypothesis() -> Hypothesis:
    return Hypothesis(
        id="hyp_000000000001",
        label="Unauthorised control activity",
        template_id="atlas.unauthorised_control_activity",
        domain=Domain.ATLAS,
        prior=0.2,
        confidence=0.2,
        status=HypothesisStatus.ACTIVE,
        created_at=T0,
        updated_at=T0,
    )


def test_constructs_and_defaults_to_empty_evidence() -> None:
    hypothesis = make_hypothesis()
    assert hypothesis.label == "Unauthorised control activity"
    assert hypothesis.template_id == "atlas.unauthorised_control_activity"
    assert hypothesis.supporting == []
    assert hypothesis.contradictory == []


def test_is_frozen() -> None:
    with pytest.raises(ValidationError):
        make_hypothesis().confidence = 0.9  # type: ignore[misc]


@pytest.mark.parametrize("field", ["prior", "confidence"])
@pytest.mark.parametrize("value", [-0.01, 1.01])
def test_rejects_out_of_bounds_probabilities(field: str, value: float) -> None:
    kwargs: dict[str, object] = {
        "label": "x",
        "template_id": "t",
        "domain": Domain.ATLAS,
        "prior": 0.5,
        "confidence": 0.5,
        "status": HypothesisStatus.ACTIVE,
    }
    kwargs[field] = value
    with pytest.raises(ValidationError):
        Hypothesis(**kwargs)  # type: ignore[arg-type]


class TestWithEvidence:
    def test_appends_to_the_right_list(self) -> None:
        hypothesis = make_hypothesis()
        updated = hypothesis.with_evidence("ev_1", EvidenceRole.SUPPORTING).with_evidence(
            "ev_2", EvidenceRole.CONTRADICTORY
        )
        assert updated.supporting == ["ev_1"]
        assert updated.contradictory == ["ev_2"]

    def test_returns_a_new_instance_and_leaves_the_original_untouched(self) -> None:
        hypothesis = make_hypothesis()
        updated = hypothesis.with_evidence("ev_1", EvidenceRole.SUPPORTING)
        assert updated is not hypothesis
        assert hypothesis.supporting == []

    def test_refreshes_updated_at(self) -> None:
        hypothesis = make_hypothesis()
        updated = hypothesis.with_evidence("ev_1", EvidenceRole.SUPPORTING)
        assert updated.updated_at > hypothesis.updated_at
        assert updated.created_at == hypothesis.created_at

    def test_is_idempotent_for_the_same_id_and_role(self) -> None:
        hypothesis = make_hypothesis().with_evidence("ev_1", EvidenceRole.SUPPORTING)
        assert hypothesis.with_evidence("ev_1", EvidenceRole.SUPPORTING).supporting == ["ev_1"]

    def test_reassigning_a_role_moves_the_id_and_never_duplicates_it(self) -> None:
        hypothesis = make_hypothesis().with_evidence("ev_1", EvidenceRole.SUPPORTING)
        moved = hypothesis.with_evidence("ev_1", EvidenceRole.CONTRADICTORY)
        assert moved.supporting == []
        assert moved.contradictory == ["ev_1"]

    def test_preserves_insertion_order(self) -> None:
        hypothesis = make_hypothesis()
        for evidence_id in ("ev_3", "ev_1", "ev_2"):
            hypothesis = hypothesis.with_evidence(evidence_id, EvidenceRole.SUPPORTING)
        assert hypothesis.supporting == ["ev_3", "ev_1", "ev_2"]


def test_construction_rejects_an_id_in_both_lists() -> None:
    with pytest.raises(ValidationError, match="both"):
        Hypothesis(
            label="x",
            template_id="t",
            domain=Domain.ATLAS,
            prior=0.5,
            confidence=0.5,
            status=HypothesisStatus.ACTIVE,
            supporting=["ev_1"],
            contradictory=["ev_1"],
        )


def test_construction_rejects_duplicates_within_one_list() -> None:
    with pytest.raises(ValidationError, match="duplicate"):
        Hypothesis(
            label="x",
            template_id="t",
            domain=Domain.ATLAS,
            prior=0.5,
            confidence=0.5,
            status=HypothesisStatus.ACTIVE,
            supporting=["ev_1", "ev_1"],
        )


class TestWithConfidence:
    def test_sets_the_value_and_refreshes_updated_at(self) -> None:
        hypothesis = make_hypothesis()
        updated = hypothesis.with_confidence(0.87)
        assert updated.confidence == 0.87
        assert updated.prior == hypothesis.prior
        assert updated.updated_at > hypothesis.updated_at

    @pytest.mark.parametrize("value", [-0.01, 1.01])
    def test_rejects_out_of_bounds_values(self, value: float) -> None:
        with pytest.raises(ValidationError):
            make_hypothesis().with_confidence(value)


def test_json_round_trip() -> None:
    hypothesis = make_hypothesis().with_evidence("ev_1", EvidenceRole.SUPPORTING)
    assert Hypothesis.model_validate_json(hypothesis.model_dump_json()) == hypothesis

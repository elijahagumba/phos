"""S1 of the learning engine (ADR 0118): decisions and outcomes in a ledger nobody can rewrite."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from phos.eval.learning_records import (
    GENESIS_HASH,
    AlertRow,
    DecisionRecord,
    LearningLedger,
    LearningRecord,
    LedgerError,
    OutcomeRecord,
    arena_eligibility,
    sha256_text,
    window_sha256,
)
from phos.ontology import Domain, Evidence, EvidenceKind, Hypothesis, HypothesisStatus, Narrative

T0 = datetime(2026, 10, 12, 9, 0, tzinfo=UTC)
HASH = "a" * 64


def an_evidence() -> Evidence:
    return Evidence(
        kind=EvidenceKind.DEVIATION,
        source_id="model",
        entity_ids=["ent_000000000001"],
        timestamp=T0,
        domain=Domain.ATLAS,
        summary="LIT-101 departed",
    )


def a_decision(**changes: object) -> DecisionRecord:
    evidence = an_evidence()
    hypothesis = Hypothesis(
        label="An instrument failed",
        template_id="sensor_or_device_fault",
        domain=Domain.ATLAS,
        prior=0.1,
        confidence=0.6,
        status=HypothesisStatus.ACTIVE,
        supporting=[evidence.id],
    )
    narrative = Narrative(
        title="LIT-101",
        domain=Domain.ATLAS,
        hypothesis_ids=[hypothesis.id],
        evidence_ids=[evidence.id],
    )
    fields: dict[str, object] = {
        "decided_at": T0,
        "detector": "atlas-v1-consistency",
        "commit": "c43f7d5",
        "config_sha256": HASH,
        "fit": "lib-ot train seed 80001",
        "fit_sha256": HASH,
        "source": "lib-ot-water-treatment-liar-s4242",
        "source_role": "development",
        "window_start": T0,
        "window_end": T0 + timedelta(hours=1),
        "input_sha256": HASH,
        "budget_per_shift": 8,
        "alerts": (AlertRow(rank=1, time=T0, score=2.5, entities=("ent_000000000001",)),),
        "narratives": (narrative,),
        "hypotheses": (hypothesis,),
        "evidence": (evidence,),
    }
    return DecisionRecord.model_validate(fields | changes)


def an_outcome(decision: DecisionRecord, **changes: object) -> OutcomeRecord:
    fields: dict[str, object] = {
        "decision_id": decision.id,
        "kind": "attack",
        "status": "confirmed",
        "source": "synthetic_truth",
        "source_ref": "truth.csv",
        "occurred_at": T0,
        "known_at": T0 + timedelta(hours=2),
    }
    return OutcomeRecord.model_validate(fields | changes)


class TestRecords:
    def test_a_decision_is_frozen(self) -> None:
        decision = a_decision()
        with pytest.raises(ValidationError):
            decision.detector = "another"  # type: ignore[misc]

    def test_an_inverted_window_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="inverted"):
            a_decision(window_end=T0 - timedelta(seconds=1))

    def test_alert_ranks_must_run_from_one_in_order(self) -> None:
        alert = AlertRow(rank=2, time=T0, score=1.0, entities=("e",))
        with pytest.raises(ValidationError, match="ranks"):
            a_decision(alerts=(alert,))

    def test_a_hypothesis_citing_missing_evidence_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="cites evidence"):
            a_decision(evidence=())

    def test_an_outcome_must_name_its_kind(self) -> None:
        decision = a_decision()
        fields = an_outcome(decision).model_dump()
        del fields["kind"]
        with pytest.raises(ValidationError):
            OutcomeRecord.model_validate(fields)

    def test_unknown_is_a_kind(self) -> None:
        assert an_outcome(a_decision(), kind="unknown", status="unresolved").kind == "unknown"

    def test_an_outcome_is_about_something(self) -> None:
        with pytest.raises(ValidationError, match="about a decision or a window"):
            an_outcome(a_decision(), decision_id=None)

    def test_a_miss_is_about_a_window(self) -> None:
        outcome = an_outcome(
            a_decision(), decision_id=None, window_start=T0, window_end=T0 + timedelta(hours=1)
        )
        assert outcome.decision_id is None

    def test_half_a_window_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="both a start and an end"):
            an_outcome(a_decision(), decision_id=None, window_start=T0)

    def test_known_before_it_happened_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="precedes"):
            an_outcome(a_decision(), known_at=T0 - timedelta(seconds=1))

    def test_an_operator_alone_cannot_confirm(self) -> None:
        with pytest.raises(ValidationError, match="operator"):
            an_outcome(a_decision(), source="operator")

    def test_a_corroborated_operator_can_confirm(self) -> None:
        outcome = an_outcome(a_decision(), source="operator", corroboration=("work-order:WO-1",))
        assert outcome.status == "confirmed"

    def test_an_operator_alone_may_be_provisional(self) -> None:
        assert (
            an_outcome(a_decision(), source="operator", status="provisional").source == "operator"
        )


class TestLedger:
    def test_an_empty_ledger_starts_at_genesis(self, tmp_path: Path) -> None:
        assert LearningLedger(tmp_path / "ledger.jsonl").head == GENESIS_HASH

    def test_records_survive_a_reload(self, tmp_path: Path) -> None:
        path = tmp_path / "ledger.jsonl"
        ledger = LearningLedger(path)
        decision = a_decision()
        outcome = an_outcome(decision)
        ledger.append_decision(decision)
        ledger.append_outcome(outcome)
        again = LearningLedger(path)
        assert again.decisions() == (decision,)
        assert again.outcomes() == (outcome,)
        assert again.head == ledger.head

    def test_each_line_carries_the_hash_of_the_one_before(self, tmp_path: Path) -> None:
        path = tmp_path / "ledger.jsonl"
        ledger = LearningLedger(path)
        decision = a_decision()
        ledger.append_decision(decision)
        ledger.append_outcome(an_outcome(decision))
        first, second = path.read_text(encoding="utf-8").splitlines()
        assert json.loads(first)["prev"] == GENESIS_HASH
        assert json.loads(second)["prev"] == sha256_text(first)
        assert ledger.head == sha256_text(second)

    def test_an_outcome_cannot_precede_its_decision(self, tmp_path: Path) -> None:
        ledger = LearningLedger(tmp_path / "ledger.jsonl")
        with pytest.raises(LedgerError, match="no decision"):
            ledger.append_outcome(an_outcome(a_decision()))

    def test_an_outcome_known_before_the_decision_is_refused(self, tmp_path: Path) -> None:
        ledger = LearningLedger(tmp_path / "ledger.jsonl")
        decision = a_decision(decided_at=T0 + timedelta(hours=3))
        ledger.append_decision(decision)
        with pytest.raises(LedgerError, match="known before"):
            ledger.append_outcome(an_outcome(decision))

    def test_an_id_cannot_be_appended_twice(self, tmp_path: Path) -> None:
        ledger = LearningLedger(tmp_path / "ledger.jsonl")
        decision = a_decision()
        ledger.append_decision(decision)
        with pytest.raises(LedgerError, match="already on file"):
            ledger.append_decision(decision)

    def test_the_ledger_offers_no_way_to_edit_or_delete(self) -> None:
        public = {name for name in dir(LearningLedger) if not name.startswith("_")}
        writes = {name for name in public if not name.startswith(("append_", "current_"))}
        assert writes == {"decision", "decisions", "head", "outcomes"}

    def test_a_correction_supersedes_and_history_stays(self, tmp_path: Path) -> None:
        ledger = LearningLedger(tmp_path / "ledger.jsonl")
        decision = a_decision()
        ledger.append_decision(decision)
        first = an_outcome(decision, kind="benign", status="provisional", source="operator")
        ledger.append_outcome(first)
        second = an_outcome(decision, supersedes=first.id)
        ledger.append_outcome(second)
        assert ledger.current_outcomes(decision.id) == (second,)
        assert ledger.outcomes() == (first, second)

    def test_a_superseded_outcome_cannot_be_superseded_again(self, tmp_path: Path) -> None:
        ledger = LearningLedger(tmp_path / "ledger.jsonl")
        decision = a_decision()
        ledger.append_decision(decision)
        first = an_outcome(decision, status="provisional")
        ledger.append_outcome(first)
        ledger.append_outcome(an_outcome(decision, supersedes=first.id))
        with pytest.raises(LedgerError, match="already superseded"):
            ledger.append_outcome(an_outcome(decision, supersedes=first.id))

    def test_a_correction_must_be_about_the_same_thing(self, tmp_path: Path) -> None:
        ledger = LearningLedger(tmp_path / "ledger.jsonl")
        one, two = a_decision(), a_decision()
        ledger.append_decision(one)
        ledger.append_decision(two)
        first = an_outcome(one, status="provisional")
        ledger.append_outcome(first)
        with pytest.raises(LedgerError, match="not about"):
            ledger.append_outcome(an_outcome(two, supersedes=first.id))


class TestTampering:
    def write_two(self, path: Path) -> list[str]:
        ledger = LearningLedger(path)
        decision = a_decision()
        ledger.append_decision(decision)
        ledger.append_outcome(an_outcome(decision))
        return path.read_text(encoding="utf-8").splitlines()

    def test_an_edited_line_breaks_the_chain(self, tmp_path: Path) -> None:
        path = tmp_path / "ledger.jsonl"
        first, second = self.write_two(path)
        path.write_text(first.replace("atlas-v1-consistency", "atlas-v9") + "\n" + second + "\n")
        with pytest.raises(LedgerError, match="line 2 does not follow"):
            LearningLedger(path)

    def test_a_removed_line_breaks_the_chain(self, tmp_path: Path) -> None:
        path = tmp_path / "ledger.jsonl"
        _first, second = self.write_two(path)
        path.write_text(second + "\n")
        with pytest.raises(LedgerError, match="line 1 does not follow"):
            LearningLedger(path)

    def test_reordered_lines_break_the_chain(self, tmp_path: Path) -> None:
        path = tmp_path / "ledger.jsonl"
        first, second = self.write_two(path)
        path.write_text(second + "\n" + first + "\n")
        with pytest.raises(LedgerError, match="line 1 does not follow"):
            LearningLedger(path)

    def test_a_forged_but_chained_rule_break_is_still_refused(self, tmp_path: Path) -> None:
        path = tmp_path / "ledger.jsonl"
        decision = a_decision(decided_at=T0 + timedelta(hours=3))
        early = an_outcome(decision)
        first = json.dumps(
            {"prev": GENESIS_HASH, "kind": "decision", "record": decision.model_dump(mode="json")}
        )
        second = json.dumps(
            {"prev": sha256_text(first), "kind": "outcome", "record": early.model_dump(mode="json")}
        )
        path.write_text(first + "\n" + second + "\n")
        with pytest.raises(LedgerError, match=r"line 2: .*known before"):
            LearningLedger(path)

    def test_a_line_that_is_not_json_is_refused(self, tmp_path: Path) -> None:
        path = tmp_path / "ledger.jsonl"
        path.write_text("not json\n")
        with pytest.raises(LedgerError, match="not JSON"):
            LearningLedger(path)


def test_the_window_hash_depends_on_every_value() -> None:
    stamps = [T0, T0 + timedelta(seconds=1)]
    one = window_sha256(stamps, [[1.0, 2.0], [3.0, 4.0]])
    assert one == window_sha256(stamps, [[1.0, 2.0], [3.0, 4.0]])
    assert one != window_sha256(stamps, [[1.0, 2.0], [3.0, 4.5]])
    with pytest.raises(ValueError):
        window_sha256(stamps, [[1.0]])


class TestEligibility:
    def test_a_confirmed_development_case_is_eligible(self) -> None:
        decision = a_decision()
        eligible, _reason = arena_eligibility(decision, an_outcome(decision))
        assert eligible

    @pytest.mark.parametrize("role", ["validation", "held-out", None])
    def test_a_case_from_any_other_role_is_not(self, role: str | None) -> None:
        decision = a_decision(source_role=role)
        eligible, reason = arena_eligibility(decision, an_outcome(decision))
        assert not eligible
        assert reason

    def test_a_validation_case_names_the_demotion(self) -> None:
        decision = a_decision(source_role="validation")
        _eligible, reason = arena_eligibility(decision, an_outcome(decision))
        assert "demote" in reason

    @pytest.mark.parametrize("status", ["unresolved", "provisional", "disputed", "retracted"])
    def test_an_unconfirmed_outcome_is_not(self, status: str) -> None:
        decision = a_decision()
        eligible, _reason = arena_eligibility(decision, an_outcome(decision, status=status))
        assert not eligible

    def test_no_outcome_is_not(self) -> None:
        assert arena_eligibility(a_decision(), None) == (False, "no outcome is known")

    def test_a_learning_record_is_frozen(self) -> None:
        record = LearningRecord(
            decision_id="dec_1",
            outcome_ids=("out_1",),
            channel="explanation",
            mechanism="inlet_subthreshold",
            eligible=True,
            reason="a confirmed outcome on development data",
        )
        with pytest.raises(ValidationError):
            record.eligible = False  # type: ignore[misc]

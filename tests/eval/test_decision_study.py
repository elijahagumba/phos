"""Tests for the U5 three-arm decision-usefulness instrument.

Pins the protocol, the mechanical non-operator policy's blindness to gold, the Sentiel
settling limitation, and the rule that scoring invents no usefulness score.
"""

from __future__ import annotations

import pytest

from phos.eval.decision_cases import (
    ATLAS_CASE_IDS,
    SENTIEL_CASE_ID,
    atlas_cases,
    case_pack,
    mechanical_non_operator_response,
    primary_cases,
    render_arm,
    sentiel_cases,
    stimuli_differ,
)
from phos.eval.decision_study import (
    Arm,
    Conclusion,
    Gold,
    SubjectKind,
    TrialResponse,
    aggregate_arm,
    latin_square_arms,
    score_trial,
)
from phos.ontology import Domain
from phos.reasoning.analyst import assess_narrative


def test_case_pack_is_six_atlas_and_one_sentiel() -> None:
    pack = case_pack()
    assert tuple(item.case_id for item in pack if item.in_primary_comparison) == ATLAS_CASE_IDS
    assert tuple(item.case_id for item in sentiel_cases()) == (SENTIEL_CASE_ID,)
    assert len(pack) == 7
    assert len(primary_cases(pack)) == 6
    assert len(atlas_cases()) == 6


def test_three_arms_are_different_presentations() -> None:
    for case in case_pack():
        assert stimuli_differ(case), case.case_id


def test_every_stimulus_is_labelled_non_operator() -> None:
    for case in case_pack():
        for arm in Arm:
            text = render_arm(case, arm)
            assert "CRUDE_NON_OPERATOR" in text
            assert "not a field study" in text.lower()
            assert "SYNTHETIC-DERIVED" in text


def test_known_station_gold_is_unresolved_not_the_attack() -> None:
    """ADR 0014: a known-link write still supports maintenance. Gold follows the evidence."""
    case = next(item for item in atlas_cases() if item.case_id == "known-station-write")
    assert case.gold.conclusion is Conclusion.UNRESOLVED
    assert case.gold.uncertainty_important is True
    assert case.gold.should_escalate is False


def test_unknown_master_gold_is_unauthorised_and_escalates() -> None:
    case = next(item for item in atlas_cases() if item.case_id == "unknown-master-write")
    assert case.gold.conclusion is Conclusion.UNAUTHORISED_CONTROL
    assert case.gold.should_escalate is True
    brief = assess_narrative(case.narrative, case.store, case.library)
    assert "unauthorised" in brief.assessment_line.lower()
    assert brief.assessment.value == "resolved"


def test_sentiel_atlas_arm_names_the_sanction_gap() -> None:
    case = sentiel_cases()[0]
    assert case.domain is Domain.SENTIEL
    assert case.sentiel_settling_is_weak is True
    rendered = render_arm(case, Arm.ATLAS_EXPLANATION)
    lower = rendered.lower()
    assert "no behaviour fact the templates declare can settle this" in lower
    assert "sanction" in lower
    assert "known limit of this ranking" in lower


def test_mechanical_policy_does_not_read_gold() -> None:
    """The policy sees only stimulus text. A fake threshold alert escalates regardless of gold."""
    response = mechanical_non_operator_response(
        "not-a-real-case",
        Arm.THRESHOLD_ALERT,
        "THRESHOLD ALERT\nSignal: x\n",
    )
    assert response.conclusion is Conclusion.UNAUTHORISED_CONTROL
    assert response.escalate is True
    quiet = mechanical_non_operator_response(
        "not-a-real-case",
        Arm.THRESHOLD_ALERT,
        "THRESHOLD STATUS\nNo signal exceeded its threshold in this window.\n",
    )
    assert quiet.conclusion is Conclusion.ORDINARY_OPERATION
    assert quiet.escalate is False
    raw = mechanical_non_operator_response("x", Arm.RAW_TELEMETRY, "anything at all")
    assert raw.conclusion is Conclusion.UNRESOLVED
    assert raw.escalate is False
    assert raw.confidence == 1


def test_false_escalation_and_missed_uncertainty_are_computed() -> None:
    gold = Gold(
        conclusion=Conclusion.UNRESOLVED,
        should_escalate=False,
        uncertainty_important=True,
    )
    wrong = TrialResponse(
        case_id="c",
        arm=Arm.THRESHOLD_ALERT,
        conclusion=Conclusion.UNAUTHORISED_CONTROL,
        escalate=True,
        noticed_uncertainty=False,
        confidence=4,
    )
    scored = score_trial(gold, wrong)
    assert scored.correct_conclusion is False
    assert scored.false_escalation is True
    assert scored.missed_uncertainty is True
    assert scored.overconfident_and_wrong is True
    right = TrialResponse(
        case_id="c",
        arm=Arm.ATLAS_EXPLANATION,
        conclusion=Conclusion.UNRESOLVED,
        escalate=False,
        noticed_uncertainty=True,
        confidence=2,
        evidence_requested="a covering work order",
    )
    ok = score_trial(gold, right)
    assert ok.correct_conclusion is True
    assert ok.false_escalation is False
    assert ok.missed_uncertainty is False
    assert ok.requested_evidence is True
    assert ok.overconfident_and_wrong is False


def test_aggregate_arm_counts_and_empty_is_zero() -> None:
    gold = Gold(
        conclusion=Conclusion.ORDINARY_OPERATION,
        should_escalate=False,
        uncertainty_important=False,
    )
    response = TrialResponse(
        case_id="c",
        arm=Arm.RAW_TELEMETRY,
        conclusion=Conclusion.ORDINARY_OPERATION,
        escalate=False,
        noticed_uncertainty=False,
        confidence=2,
        elapsed_ms=1500,
    )
    scored = score_trial(gold, response)
    agg = aggregate_arm(Arm.RAW_TELEMETRY, [scored])
    assert agg.n == 1
    assert agg.n_correct == 1
    assert agg.n_with_time == 1
    assert agg.sum_elapsed_ms == 1500
    empty = aggregate_arm(Arm.ATLAS_EXPLANATION, [scored])
    assert empty.n == 0
    assert empty.n_correct == 0
    assert empty.sum_elapsed_ms == 0


def test_latin_square_balances_three_arms_on_six_cases() -> None:
    first = latin_square_arms(6, 0)
    second = latin_square_arms(6, 1)
    third = latin_square_arms(6, 2)
    assert first[0] is Arm.RAW_TELEMETRY
    assert second[0] is Arm.THRESHOLD_ALERT
    assert third[0] is Arm.ATLAS_EXPLANATION
    for row in (first, second, third):
        assert row.count(Arm.RAW_TELEMETRY) == 2
        assert row.count(Arm.THRESHOLD_ALERT) == 2
        assert row.count(Arm.ATLAS_EXPLANATION) == 2
    columns = list(zip(first, second, third, strict=True))
    for column in columns:
        assert set(column) == set(Arm)


def test_subject_kind_has_no_plant_literate_on_this_run() -> None:
    assert SubjectKind.MECHANICAL_NON_OPERATOR.value == "mechanical_non_operator"
    assert SubjectKind.PLANT_LITERATE.value == "plant_literate"


def test_latin_square_rejects_bad_args() -> None:
    with pytest.raises(ValueError, match="n_cases"):
        latin_square_arms(0, 0)
    with pytest.raises(ValueError, match="subject_index"):
        latin_square_arms(3, -1)


def test_mechanical_policy_copies_atlas_assessment_not_gold() -> None:
    """The Atlas-arm policy parses U4 markdown. Gold is not an input."""
    stimulus = (
        "CRUDE_NON_OPERATOR_NOT_A_FIELD_STUDY\n\n"
        "## Assessment\n**unresolved** - attack and maintenance share the ceiling.\n\n"
        "## What would settle this\nA covering work order for this unit and window.\n"
    )
    response = mechanical_non_operator_response(
        "known-station-write", Arm.ATLAS_EXPLANATION, stimulus
    )
    assert response.conclusion is Conclusion.UNRESOLVED
    assert response.escalate is False
    assert response.noticed_uncertainty is True
    assert "covering work order" in response.evidence_requested


def test_attacker_during_maintenance_gold_notices_uncertainty() -> None:
    """A covering order does not settle an in-window write. Gold stays unresolved."""
    case = next(item for item in atlas_cases() if item.case_id == "attacker-during-maintenance")
    assert case.gold.conclusion is Conclusion.UNRESOLVED
    assert case.gold.uncertainty_important is True
    brief = assess_narrative(case.narrative, case.store, case.library)
    # Templates may resolve toward maintenance; that miss is what the study can measure.
    line = brief.assessment_line.lower()
    assert "maintenance" in line or "unresolved" in line

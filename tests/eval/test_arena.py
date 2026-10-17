"""S3 of the learning engine (ADR 0120): tasks, an enforced budget, and the candidate's fence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from phos.eval.arena import (
    ARENA_ROOT,
    MAX_RUNS_PER_HYPOTHESIS,
    Attempt,
    AttemptLog,
    BudgetExhaustedError,
    Hypothesis,
    ResearchTask,
    candidate_sha256,
    forbidden_candidate_paths,
    payloads_present,
)
from phos.eval.learning_records import LearningRecord

HASH = "b" * 64


def a_record(decision_id: str = "dec_1", **changes: object) -> LearningRecord:
    fields: dict[str, object] = {
        "decision_id": decision_id,
        "outcome_ids": ("out_1",),
        "channel": "explanation",
        "mechanism": "inlet_subthreshold",
        "eligible": True,
        "reason": "a confirmed outcome on development data",
    }
    return LearningRecord.model_validate(fields | changes)


def a_task(**changes: object) -> ResearchTask:
    fields: dict[str, object] = {
        "id": "water-liar",
        "learning_record_ids": ("dec_1",),
        "mechanism": "inlet_subthreshold",
        "capability": "see a level that stops integrating its flows",
        "hypotheses": (
            Hypothesis(id="longer-lags", statement="memory too short", change="lags"),
            Hypothesis(id="slower-detrend", statement="detrend absorbs it", change="detrend"),
        ),
        "runs_per_hypothesis": 2,
        "expected_benefit": "water passes",
        "expected_regressions": "HAI 20.07 recall",
        "regression_slices": ("liar:power", "liar:batch", "hai-20.07"),
        "evaluation_plan": "arena scorecard, then the gate",
    }
    return ResearchTask.model_validate(fields | changes)


def an_attempt(task: ResearchTask, hypothesis_id: str, number: int) -> Attempt:
    candidate: dict[str, object] = {"lags": [0, 30, 300], "n": number}
    return Attempt(
        task_id=task.id,
        hypothesis_id=hypothesis_id,
        number=number,
        candidate=candidate,
        candidate_sha256=candidate_sha256(candidate),
        scorer="liar-arena",
        scorer_sha256=HASH,
        scorecard={"passes": 4},
        compute_seconds=1.0,
    )


class TestTask:
    def test_more_than_three_hypotheses_are_refused(self) -> None:
        many = tuple(Hypothesis(id=f"h{i}", statement="s", change="c") for i in range(4))
        with pytest.raises(ValidationError):
            a_task(hypotheses=many)

    def test_a_budget_beyond_the_sandboxs_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            a_task(runs_per_hypothesis=MAX_RUNS_PER_HYPOTHESIS + 1)

    def test_duplicate_hypothesis_ids_are_refused(self) -> None:
        same = (Hypothesis(id="h", statement="s", change="c"),) * 2
        with pytest.raises(ValidationError, match="unique"):
            a_task(hypotheses=same)

    def test_a_task_needs_a_motivating_record(self) -> None:
        with pytest.raises(ValidationError):
            a_task(learning_record_ids=())

    def test_eligible_records_of_its_mechanism_motivate_it(self) -> None:
        a_task().check_motivation([a_record()])

    def test_an_ineligible_record_is_refused(self) -> None:
        with pytest.raises(ValueError, match="not eligible"):
            a_task().check_motivation([a_record(eligible=False, reason="validation source")])

    def test_a_record_of_another_mechanism_is_refused(self) -> None:
        with pytest.raises(ValueError, match="not inlet_subthreshold"):
            a_task().check_motivation([a_record(mechanism="misinterpreted")])

    def test_a_missing_record_is_refused(self) -> None:
        with pytest.raises(ValueError, match="no learning record"):
            a_task().check_motivation([])


class TestAttemptLog:
    def test_attempts_survive_a_reload(self, tmp_path: Path) -> None:
        task = a_task()
        path = tmp_path / "attempts.jsonl"
        AttemptLog(path, task).append(an_attempt(task, "longer-lags", 1))
        assert len(AttemptLog(path, task).attempts()) == 1

    def test_the_budget_is_enforced_in_code(self, tmp_path: Path) -> None:
        task = a_task()
        log = AttemptLog(tmp_path / "attempts.jsonl", task)
        log.append(an_attempt(task, "longer-lags", 1))
        log.append(an_attempt(task, "longer-lags", 2))
        assert log.remaining("longer-lags") == 0
        with pytest.raises(BudgetExhaustedError):
            log.append(an_attempt(task, "longer-lags", 3))
        log.append(an_attempt(task, "slower-detrend", 1))

    def test_an_undeclared_hypothesis_is_refused(self, tmp_path: Path) -> None:
        task = a_task()
        with pytest.raises(KeyError):
            AttemptLog(tmp_path / "a.jsonl", task).append(an_attempt(task, "invented", 1))

    def test_numbering_cannot_skip(self, tmp_path: Path) -> None:
        task = a_task()
        with pytest.raises(ValueError, match="expected 1"):
            AttemptLog(tmp_path / "a.jsonl", task).append(an_attempt(task, "longer-lags", 2))

    def test_a_mismatched_candidate_hash_is_refused(self, tmp_path: Path) -> None:
        task = a_task()
        attempt = an_attempt(task, "longer-lags", 1).model_copy(update={"candidate_sha256": HASH})
        with pytest.raises(ValueError, match="does not match"):
            AttemptLog(tmp_path / "a.jsonl", task).append(attempt)

    def test_another_tasks_attempt_is_refused(self, tmp_path: Path) -> None:
        task = a_task()
        attempt = an_attempt(task, "longer-lags", 1).model_copy(update={"task_id": "other"})
        with pytest.raises(ValueError, match="for task"):
            AttemptLog(tmp_path / "a.jsonl", task).append(attempt)

    def test_an_edited_line_breaks_the_chain(self, tmp_path: Path) -> None:
        task = a_task()
        path = tmp_path / "a.jsonl"
        log = AttemptLog(path, task)
        log.append(an_attempt(task, "longer-lags", 1))
        log.append(an_attempt(task, "longer-lags", 2))
        first, second = path.read_text(encoding="utf-8").splitlines()
        raw = json.loads(first)
        raw["attempt"]["scorecard"] = {"passes": 18}
        path.write_text(json.dumps(raw) + "\n" + second + "\n")
        with pytest.raises(ValueError, match="line 2 does not follow"):
            AttemptLog(path, task)

    def test_a_hand_added_attempt_past_the_budget_is_refused_on_load(self, tmp_path: Path) -> None:
        task = a_task(runs_per_hypothesis=1)
        path = tmp_path / "a.jsonl"
        AttemptLog(path, task).append(an_attempt(task, "longer-lags", 1))
        wider = a_task(runs_per_hypothesis=2)
        AttemptLog(path, wider).append(an_attempt(wider, "longer-lags", 2))
        with pytest.raises(BudgetExhaustedError):
            AttemptLog(path, task)


class TestFence:
    def test_a_diff_inside_the_candidate_directory_is_allowed(self) -> None:
        inside = f"{ARENA_ROOT}/water-liar/longer-lags/candidate.json"
        assert forbidden_candidate_paths([inside], "water-liar", "longer-lags") == []

    @pytest.mark.parametrize(
        "path",
        [
            "src/phos/atlas/consistency.py",
            "src/phos/eval/arena.py",
            "data/registry.json",
            "eval_runs/learning/liar-dev-s4242.ledger.jsonl",
            f"{ARENA_ROOT}/water-liar/slower-detrend/candidate.json",
            f"{ARENA_ROOT}/water-liar/longer-lags-2/candidate.json",
        ],
    )
    def test_anything_else_is_forbidden(self, path: str) -> None:
        assert forbidden_candidate_paths([path], "water-liar", "longer-lags") == [path]

    def test_validation_and_held_out_payloads_are_found(self, tmp_path: Path) -> None:
        for name in ("hai-22.04", "hai-20.07", "future"):
            (tmp_path / "data" / name).mkdir(parents=True)
            (tmp_path / "data" / name / "manifest.json").write_text("{}")
            (tmp_path / "data" / name / "test1.csv.gz").write_text("x")
        roles: dict[str, str | None] = {
            "hai-22.04": "validation",
            "hai-20.07": "development",
            "future": "held-out",
        }
        assert payloads_present(tmp_path, roles) == [
            "data/future/test1.csv.gz",
            "data/hai-22.04/test1.csv.gz",
        ]

    def test_a_fresh_worktree_has_no_payloads(self, tmp_path: Path) -> None:
        assert payloads_present(tmp_path, {"hai-22.04": "validation"}) == []

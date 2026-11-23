"""The record tree round-trips, allocates ids, and reports its own broken references."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests.genesis.conftest import EXPERIMENT, MEASUREMENT, QUESTION

from phos.genesis.records import Experiment, Question
from phos.genesis.store import RECORD_DIR, Store


class TestRoundTrip:
    def test_a_question_written_is_a_question_read(self, repo: Path) -> None:
        store = Store(repo)
        question = Question.model_validate({**QUESTION, "id": "Q-0001"})
        store.write(question)
        assert store.questions() == {"Q-0001": question}

    def test_the_file_lands_under_the_record_directory(self, repo: Path) -> None:
        store = Store(repo)
        path = store.write(Question.model_validate({**QUESTION, "id": "Q-0007"}))
        assert path == repo / RECORD_DIR / "questions" / "Q-0007.json"

    def test_an_unknown_prefix_has_no_home(self, repo: Path) -> None:
        with pytest.raises(ValueError, match="no known kind prefix"):
            Store(repo).path_for("X-0001")


class TestNextId:
    def test_the_first_id_is_one(self, repo: Path) -> None:
        assert Store(repo).next_id("questions") == "Q-0001"

    def test_the_next_id_follows_the_highest_that_exists(self, repo: Path) -> None:
        store = Store(repo)
        store.write(Question.model_validate({**QUESTION, "id": "Q-0004"}))
        assert store.next_id("questions") == "Q-0005"

    def test_a_number_taken_on_another_branch_is_not_handed_out_again(
        self, repo: Path, commit: object
    ) -> None:
        import subprocess

        store = Store(repo)
        store.write(Question.model_validate({**QUESTION, "id": "Q-0009"}))
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-qm", "q9"], cwd=repo, check=True)
        subprocess.run(["git", "branch", "other"], cwd=repo, check=True)
        subprocess.run(["git", "rm", "-q", "-r", str(RECORD_DIR)], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-qm", "drop"], cwd=repo, check=True)
        assert not (repo / RECORD_DIR / "questions" / "Q-0009.json").exists()
        assert store.next_id("questions") == "Q-0010"

    def test_a_kind_that_is_not_a_record_kind_is_refused(self, repo: Path) -> None:
        with pytest.raises(ValueError, match="is not a record kind"):
            Store(repo).next_id("hunches")


class TestAudit:
    def test_a_consistent_record_reports_nothing(self, repo: Path) -> None:
        store = Store(repo)
        store.write(Question.model_validate({**QUESTION, "id": "Q-0001"}))
        store.write(Experiment.model_validate({**EXPERIMENT, "id": "E-0001", "phase": "declared"}))
        assert store.audit() == []

    def test_an_experiment_serving_no_question_is_reported(self, repo: Path) -> None:
        store = Store(repo)
        store.write(Experiment.model_validate({**EXPERIMENT, "id": "E-0001", "phase": "declared"}))
        problems = store.audit()
        assert any("does not exist" in problem.problem for problem in problems)

    def test_a_measurement_naming_an_absent_report_is_reported(self, repo: Path) -> None:
        store = Store(repo)
        store.write(Question.model_validate({**QUESTION, "id": "Q-0001"}))
        measured = {
            **EXPERIMENT,
            "id": "E-0001",
            "phase": "measured",
            "measured": {**MEASUREMENT, "report": "eval_runs/nowhere.md"},
        }
        store.write(Experiment.model_validate(measured))
        assert any("is absent" in problem.problem for problem in store.audit())

    def test_a_verdict_that_disagrees_with_its_own_numbers_is_reported(self, repo: Path) -> None:
        store = Store(repo)
        store.write(Question.model_validate({**QUESTION, "id": "Q-0001"}))
        lying = {
            **EXPERIMENT,
            "id": "E-0001",
            "phase": "judged",
            "measured": MEASUREMENT,
            "verdict": {"outcome": "kept", "per_bar": {"b1": True}},
        }
        store.write(Experiment.model_validate(lying))
        problems = store.audit()
        assert any("but the measured values" in problem.problem for problem in problems)

    def test_a_record_that_will_not_load_is_reported_rather_than_raised(self, repo: Path) -> None:
        store = Store(repo)
        directory = repo / RECORD_DIR / "questions"
        directory.mkdir(parents=True)
        (directory / "Q-0001.json").write_text(json.dumps({"id": "nope"}), encoding="utf-8")
        assert any("will not load" in problem.problem for problem in store.audit())

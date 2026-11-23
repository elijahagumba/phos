"""The store survives two writers, an interrupted write, and a record it cannot read.

Every test here corresponds to a defect the architectural audit measured rather than suspected
(ADR 0415). The concurrency test runs real subprocesses rather than threads, because the thing
being guarded against is two editors on one checkout, and a thread pool would share the lock's
file handle and prove nothing.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from tests.genesis.conftest import EXPERIMENT, MEASUREMENT, QUESTION

from phos.genesis.records import Question
from phos.genesis.store import RECORD_DIR, Store

#: This repository, for driving the CLI as a subprocess.
REPO = Path(__file__).resolve().parents[2]

Payload = Callable[[str, dict[str, Any]], Path]


def question(record_id: str) -> Question:
    return Question.model_validate({**QUESTION, "id": record_id})


class TestConcurrentCreate:
    """The audit measured eight parallel ``ask`` calls producing one record."""

    @pytest.mark.parametrize("writers", [2, 8])
    def test_every_concurrent_writer_gets_its_own_record(
        self, repo: Path, payload: Payload, writers: int
    ) -> None:
        source = payload("q", QUESTION)
        processes = [
            subprocess.Popen(
                [
                    sys.executable,
                    str(REPO / "scripts" / "genesis.py"),
                    "--root",
                    str(repo),
                    "ask",
                    "--from",
                    str(source),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(REPO / "src")},
                text=True,
            )
            for _ in range(writers)
        ]
        errors = [process.communicate()[1] for process in processes]
        assert all(process.returncode == 0 for process in processes), errors

        written = sorted((repo / RECORD_DIR / "questions").glob("Q-*.json"))
        assert len(written) == writers, f"{writers} writers produced {len(written)} records"
        assert len({path.stem for path in written}) == writers, "ids collided"

    def test_no_temporary_file_is_left_behind(self, repo: Path, payload: Payload) -> None:
        source = payload("q", QUESTION)
        for _ in range(4):
            subprocess.run(
                [
                    sys.executable,
                    str(REPO / "scripts" / "genesis.py"),
                    "--root",
                    str(repo),
                    "ask",
                    "--from",
                    str(source),
                ],
                capture_output=True,
                env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(REPO / "src")},
                check=True,
            )
        leftovers = list((repo / RECORD_DIR / "questions").glob(".*.tmp"))
        assert leftovers == []


class TestCreateRefusesToOverwrite:
    def test_a_create_onto_an_existing_path_is_refused(self, repo: Path) -> None:
        store = Store(repo)
        store.write(question("Q-0001"))
        # An allocator that disagrees with the tree is the only way this happens, and overwriting
        # would destroy a record nobody read.
        with pytest.raises(FileExistsError, match="refusing to overwrite"):
            store.create("questions", lambda _id: question("Q-0001"))

    def test_the_existing_record_is_untouched_after_the_refusal(self, repo: Path) -> None:
        store = Store(repo)
        store.write(question("Q-0001"))
        before = (repo / RECORD_DIR / "questions" / "Q-0001.json").read_text(encoding="utf-8")
        with pytest.raises(FileExistsError):
            store.create("questions", lambda _id: question("Q-0001"))
        after = (repo / RECORD_DIR / "questions" / "Q-0001.json").read_text(encoding="utf-8")
        assert after == before

    def test_an_update_through_write_is_still_allowed(self, repo: Path) -> None:
        store = Store(repo)
        store.write(question("Q-0001"))
        store.write(Question.model_validate({**QUESTION, "id": "Q-0001", "status": "answered"}))
        assert store.questions()["Q-0001"].status == "answered"


class TestAtomicWrite:
    def test_a_reader_never_sees_a_partial_file(self, repo: Path) -> None:
        store = Store(repo)
        store.write(question("Q-0001"))
        text = (repo / RECORD_DIR / "questions" / "Q-0001.json").read_text(encoding="utf-8")
        assert json.loads(text)["id"] == "Q-0001"
        assert text.endswith("\n")

    def test_a_leftover_temporary_is_not_read_as_a_record(self, repo: Path) -> None:
        store = Store(repo)
        store.write(question("Q-0001"))
        # What a process killed mid-write leaves behind.
        (repo / RECORD_DIR / "questions" / ".Q-0002.json.999.tmp").write_text(
            '{"id": "Q-0002", "trunc', encoding="utf-8"
        )
        assert set(store.questions()) == {"Q-0001"}
        assert store.snapshot().unreadable == ()


class TestDegradedReads:
    """One unreadable record must not disable the gate, the state or the report."""

    def truncate(self, repo: Path) -> Path:
        path = repo / RECORD_DIR / "questions" / "Q-0002.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"id": "Q-0002", "frontier": "trunc', encoding="utf-8")
        return path

    def test_the_readable_records_still_load(self, repo: Path) -> None:
        store = Store(repo)
        store.write(question("Q-0001"))
        self.truncate(repo)
        assert set(store.questions()) == {"Q-0001"}

    def test_the_snapshot_names_what_it_could_not_read(self, repo: Path) -> None:
        store = Store(repo)
        store.write(question("Q-0001"))
        self.truncate(repo)
        snapshot = store.snapshot()
        assert len(snapshot.unreadable) == 1
        assert "Q-0002.json" in snapshot.unreadable[0].path
        assert "will not load" in snapshot.unreadable[0].problem

    def test_audit_reports_it(self, repo: Path) -> None:
        store = Store(repo)
        self.truncate(repo)
        assert any("will not load" in problem.problem for problem in store.audit())

    def test_a_corrupt_question_does_not_stop_the_gate_reading_experiments(
        self, repo: Path
    ) -> None:
        # The gate's safe direction: it must be able to answer, and an unreadable record it
        # cannot see means "nothing declares this", which is a refusal rather than an allow.
        store = Store(repo)
        store.write(question("Q-0001"))
        self.truncate(repo)
        from phos.genesis.records import Experiment

        store.write(Experiment.model_validate({**EXPERIMENT, "id": "E-0001", "phase": "declared"}))
        assert set(store.experiments()) == {"E-0001"}

    def test_a_corrupt_experiment_leaves_the_gate_refusing_not_allowing(self, repo: Path) -> None:
        from phos.genesis.gatehost import decide

        store = Store(repo)
        store.write(question("Q-0001"))
        path = repo / RECORD_DIR / "experiments" / "E-0001.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"id": "E-0001", "phase": "trunc', encoding="utf-8")
        decision = decide(EXPERIMENT["declared"]["command"], store)
        assert decision is not None
        assert decision.allowed is False
        assert decision.verdict == "silent"


def run_cli(repo: Path, *argv: str) -> tuple[int, str]:
    """Run the CLI as a subprocess and return its exit code and combined output."""
    done = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "genesis.py"), "--root", str(repo), *argv],
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(REPO / "src")},
        check=False,
    )
    return done.returncode, done.stdout + done.stderr


class TestCommandsDegrade:
    def truncate(self, repo: Path) -> None:
        path = repo / RECORD_DIR / "questions" / "Q-0002.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"id": "Q-0002", "frontier": "trunc', encoding="utf-8")

    def test_state_reports_the_damage_and_still_prints_the_state(self, repo: Path) -> None:
        Store(repo).write(question("Q-0001"))
        self.truncate(repo)
        code, output = run_cli(repo, "state")
        assert code == 3, "a state that could not be fully read exits non-zero"
        assert "questions:   1" in output, "the readable records are still reported"
        assert "could not be read" in output
        assert "Q-0002.json" in output
        assert "Traceback" not in output

    def test_report_says_what_is_missing_from_it(self, repo: Path) -> None:
        self.truncate(repo)
        code, output = run_cli(repo, "report")
        assert code == 3
        assert "GENESIS research report" in output
        assert "could not be read and are missing above" in output
        assert "Traceback" not in output

    def test_a_clean_store_exits_zero(self, repo: Path) -> None:
        Store(repo).write(question("Q-0001"))
        assert run_cli(repo, "state")[0] == 0
        assert run_cli(repo, "report")[0] == 0

    def test_a_corrupt_experiment_does_not_traceback_in_report(self, repo: Path) -> None:
        path = repo / RECORD_DIR / "experiments" / "E-0001.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{", encoding="utf-8")
        code, output = run_cli(repo, "report")
        assert code == 3
        assert "Traceback" not in output


class TestLock:
    def test_the_lock_is_reentrant_across_sequential_blocks(self, repo: Path) -> None:
        store = Store(repo)
        with store.locked():
            pass
        with store.locked():
            pass
        assert (repo / RECORD_DIR / ".lock").exists()

    def test_the_lock_file_is_not_a_record(self, repo: Path) -> None:
        store = Store(repo)
        with store.locked():
            store.write(question("Q-0001"))
        assert set(store.questions()) == {"Q-0001"}

    def test_measurements_still_round_trip_after_the_rewrite(self, repo: Path) -> None:
        from phos.genesis.records import Experiment

        store = Store(repo)
        store.write(question("Q-0001"))
        judged = {
            **EXPERIMENT,
            "id": "E-0001",
            "phase": "judged",
            "measured": MEASUREMENT,
            "verdict": {"outcome": "refused", "per_bar": {"b1": False}},
        }
        store.write(Experiment.model_validate(judged))
        assert store.experiments()["E-0001"].verdict is not None

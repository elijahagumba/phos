"""Tests for the evaluation report, the latency summary and the experiment log."""

import json
import math
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from phos.eval import report as report_module
from phos.eval.metrics import OperatingPoint, ReliabilityBin
from phos.eval.report import (
    EvaluationReport,
    LatencySummary,
    append_to_experiment_log,
    current_git_commit,
)
from phos.ontology import Domain

T0 = datetime(2026, 7, 28, 9, 0, tzinfo=UTC)


def make_report(**overrides: object) -> EvaluationReport:
    fields: dict[str, object] = {
        "detector_name": "threshold-detector",
        "dataset_name": "fixture",
        "domain": Domain.ATLAS,
        "seed": 7,
        "source_note": "hand-built",
        "alert_threshold": 2.0,
        "match_tolerance_seconds": 30.0,
        "calibration_bins": 10,
        "n_observations": 100,
        "n_detections": 100,
        "n_alerts": 5,
        "n_attack_intervals": 3,
        "normal_hours": 0.88,
        "window_recall": 2 / 3,
        "false_positives": 2,
        "false_positive_rate": 2.26,
        "precision": 0.6,
        "recall_sample": 0.3,
        "f1": 0.4,
        "latency": LatencySummary.from_latencies([timedelta(seconds=60)]),
        "operating_points": [OperatingPoint(threshold=0.0, recall=1.0, fp_rate=3.0, precision=0.2)],
        "expected_calibration_error": 0.05,
        "brier_score": 0.125,
        "reliability": [
            ReliabilityBin(lower=0.9, upper=1.0, count=5, mean_confidence=0.92, empirical_rate=0.8)
        ],
    }
    fields.update(overrides)
    return EvaluationReport.model_validate(fields)


# --------------------------------------------------------------------------------------------
# LatencySummary
# --------------------------------------------------------------------------------------------


def test_latency_summary_matches_hand_computed_statistics() -> None:
    # [10, 20, 60] -> min 10, median 20, mean 30, max 60
    summary = LatencySummary.from_latencies(
        [timedelta(seconds=10), timedelta(seconds=20), timedelta(seconds=60)]
    )
    assert summary.count == 3
    assert summary.min_seconds == 10.0
    assert summary.median_seconds == 20.0
    assert summary.mean_seconds == 30.0
    assert summary.max_seconds == 60.0


def test_latency_summary_median_of_an_even_count_is_the_midpoint() -> None:
    summary = LatencySummary.from_latencies([timedelta(seconds=s) for s in (10, 20, 30, 40)])
    assert summary.median_seconds == 25.0


def test_latency_summary_of_no_detections_reports_nothing_rather_than_zero() -> None:
    # Zero latency would read as "instant detection"; None reads as "never detected".
    summary = LatencySummary.from_latencies([])
    assert summary.count == 0
    assert summary.min_seconds is None
    assert summary.median_seconds is None
    assert summary.mean_seconds is None
    assert summary.max_seconds is None


def test_latency_summary_round_trips_through_json() -> None:
    summary = LatencySummary.from_latencies([timedelta(seconds=5)])
    assert LatencySummary.model_validate_json(summary.model_dump_json()) == summary


# --------------------------------------------------------------------------------------------
# EvaluationReport
# --------------------------------------------------------------------------------------------


def test_report_round_trips_through_json() -> None:
    report = make_report()
    assert EvaluationReport.model_validate_json(report.model_dump_json()) == report


def test_report_round_trips_with_an_infinite_false_positive_rate() -> None:
    # An all-attack corpus yields an undefined rate; the report must still serialise.
    report = make_report(false_positive_rate=math.inf)
    restored = EvaluationReport.model_validate_json(report.model_dump_json())
    assert restored.false_positive_rate == math.inf
    assert restored == report


def test_report_is_frozen() -> None:
    with pytest.raises(ValidationError):
        make_report().window_recall = 1.0  # type: ignore[misc]


def test_report_rejects_a_recall_outside_the_unit_interval() -> None:
    with pytest.raises(ValidationError):
        make_report(window_recall=1.2)


def test_report_stamps_created_at_automatically() -> None:
    assert make_report().created_at.tzinfo is not None


def test_report_has_no_git_commit_until_it_is_logged() -> None:
    assert make_report().git_commit is None


# --------------------------------------------------------------------------------------------
# current_git_commit
# --------------------------------------------------------------------------------------------


def test_current_git_commit_returns_the_sha(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="abc123\n", stderr="")

    monkeypatch.setattr("phos.eval.report.subprocess.run", fake_run)
    assert current_git_commit() == "abc123"


def test_current_git_commit_tolerates_not_being_in_a_repository(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=[], returncode=128, stdout="", stderr="not a git repository"
        )

    monkeypatch.setattr("phos.eval.report.subprocess.run", fake_run)
    assert current_git_commit() is None


def test_current_git_commit_tolerates_git_not_being_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("git")

    monkeypatch.setattr("phos.eval.report.subprocess.run", fake_run)
    assert current_git_commit() is None


def test_current_git_commit_tolerates_a_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(cmd="git", timeout=10)

    monkeypatch.setattr("phos.eval.report.subprocess.run", fake_run)
    assert current_git_commit() is None


def test_current_git_commit_tolerates_an_empty_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="\n", stderr="")

    monkeypatch.setattr("phos.eval.report.subprocess.run", fake_run)
    assert current_git_commit() is None


# --------------------------------------------------------------------------------------------
# append_to_experiment_log
# --------------------------------------------------------------------------------------------


@pytest.fixture
def stub_commit(monkeypatch: pytest.MonkeyPatch) -> str:
    commit = "0123456789abcdef0123456789abcdef01234567"
    monkeypatch.setattr(report_module, "current_git_commit", lambda cwd=None: commit)
    return commit


def test_append_writes_one_valid_json_line(stub_commit: str, tmp_path: Path) -> None:
    path = tmp_path / "log.jsonl"
    append_to_experiment_log(make_report(), path)

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["seed"] == 7
    assert record["detector_name"] == "threshold-detector"
    assert record["dataset_name"] == "fixture"
    assert record["git_commit"] == stub_commit


def test_append_adds_a_line_per_run(stub_commit: str, tmp_path: Path) -> None:
    path = tmp_path / "log.jsonl"
    append_to_experiment_log(make_report(seed=1), path)
    append_to_experiment_log(make_report(seed=2), path)

    lines = path.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["seed"] for line in lines] == [1, 2]


def test_append_creates_the_logs_parent_directory(stub_commit: str, tmp_path: Path) -> None:
    path = tmp_path / "nested" / "deeper" / "log.jsonl"
    append_to_experiment_log(make_report(), path)
    assert path.exists()


def test_append_keeps_a_commit_the_report_already_carries(tmp_path: Path) -> None:
    path = tmp_path / "log.jsonl"
    append_to_experiment_log(make_report(git_commit="deadbeef"), path)
    assert json.loads(path.read_text(encoding="utf-8"))["git_commit"] == "deadbeef"


def test_append_tolerates_an_undeterminable_commit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(report_module, "current_git_commit", lambda cwd=None: None)
    path = tmp_path / "log.jsonl"
    append_to_experiment_log(make_report(), path)
    assert json.loads(path.read_text(encoding="utf-8"))["git_commit"] is None


def test_append_does_not_mutate_the_report_it_was_given(stub_commit: str, tmp_path: Path) -> None:
    report = make_report()
    append_to_experiment_log(report, tmp_path / "log.jsonl")
    assert report.git_commit is None


def test_logged_lines_read_back_as_reports(stub_commit: str, tmp_path: Path) -> None:
    path = tmp_path / "log.jsonl"
    original = make_report()
    append_to_experiment_log(original, path)

    restored = EvaluationReport.model_validate(
        json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    )
    assert restored == original.model_copy(update={"git_commit": stub_commit})


def test_append_accepts_a_string_path(stub_commit: str, tmp_path: Path) -> None:
    path = tmp_path / "log.jsonl"
    append_to_experiment_log(make_report(), str(path))
    assert path.exists()

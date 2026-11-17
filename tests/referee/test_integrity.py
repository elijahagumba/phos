"""`phos.referee.integrity`: a detector cannot read labels beside its input; dirty-tree refusal."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from phos.referee._integrity_test_fixtures import CHEAT_SENTINEL_SCORE, cheating_detector
from phos.referee.integrity import (
    DirtyWorkingTreeError,
    IntegrityError,
    refuse_if_dirty_for_private_exam,
    run_detector_isolated,
)
from phos.synth.outputs import GeneratedPlant


def test_a_legitimate_detector_runs_and_returns_detections(
    small_exam_plant: GeneratedPlant, tmp_path: Path
) -> None:
    detections = run_detector_isolated(
        "phos.referee.demo:threshold_detector", small_exam_plant, tmp_path
    )
    assert isinstance(detections, list)


def test_a_cheating_detector_cannot_read_labels_beside_its_input(
    small_exam_plant: GeneratedPlant, tmp_path: Path
) -> None:
    detections = run_detector_isolated(
        "phos.referee._integrity_test_fixtures:cheating_detector", small_exam_plant, tmp_path
    )
    assert not any(detection.score == CHEAT_SENTINEL_SCORE for detection in detections)


def test_the_cheating_fixture_itself_reports_a_cheat_when_one_is_possible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unit test of the fixture's own logic, not of the isolation boundary it is used to check."""
    (tmp_path / "labels.json").write_text("{}", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    detections = cheating_detector().run(dataset=None)  # type: ignore[arg-type]

    assert any(detection.score == CHEAT_SENTINEL_SCORE for detection in detections)


def test_the_isolated_directory_holds_no_labels_or_manifest(
    small_exam_plant: GeneratedPlant, tmp_path: Path
) -> None:
    run_detector_isolated("phos.referee.demo:threshold_detector", small_exam_plant, tmp_path)
    isolated_dir = tmp_path / f"isolated-{small_exam_plant.manifest.plant_id}"
    names = {path.name for path in isolated_dir.iterdir()}
    assert "labels.json" not in names
    assert "manifest.json" not in names
    assert "registers.json" not in names


def test_an_unimportable_factory_fails_as_an_integrity_error(
    small_exam_plant: GeneratedPlant, tmp_path: Path
) -> None:
    with pytest.raises(IntegrityError):
        run_detector_isolated("phos.no_such_module:no_such_function", small_exam_plant, tmp_path)


def _run_git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _disposable_repo(tmp_path: Path) -> Path:
    """Build a throwaway git repo so the dirty-tree test never touches this checkout."""
    repo = tmp_path / "disposable-repo"
    repo.mkdir()
    _run_git(["init", "-q"], cwd=repo)
    _run_git(["config", "user.email", "test@example.invalid"], cwd=repo)
    _run_git(["config", "user.name", "test"], cwd=repo)
    tracked = repo / "detector.py"
    tracked.write_text("# committed\n", encoding="utf-8")
    _run_git(["add", "detector.py"], cwd=repo)
    _run_git(["commit", "-q", "-m", "initial"], cwd=repo)
    return repo


def test_a_clean_disposable_tree_returns_the_commit(tmp_path: Path) -> None:
    repo = _disposable_repo(tmp_path)
    record = refuse_if_dirty_for_private_exam(repo, ("detector.py",))
    assert len(record.commit) == 40
    assert record.checked_paths == ("detector.py",)


def test_a_dirty_disposable_path_refuses(tmp_path: Path) -> None:
    repo = _disposable_repo(tmp_path)
    (repo / "detector.py").write_text("# edited after commit\n", encoding="utf-8")

    with pytest.raises(DirtyWorkingTreeError):
        refuse_if_dirty_for_private_exam(repo, ("detector.py",))


def test_an_unrelated_dirty_file_does_not_block_the_named_paths(tmp_path: Path) -> None:
    repo = _disposable_repo(tmp_path)
    (repo / "unrelated.py").write_text("# untracked, not in the checked paths\n", encoding="utf-8")

    record = refuse_if_dirty_for_private_exam(repo, ("detector.py",))
    assert len(record.commit) == 40

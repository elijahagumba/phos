"""`phos.referee.cli`: make-exam, run, report and retire-seeds, end to end on one small plant."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from phos.referee.cli import main
from phos.referee.seeds import SeedPool, SeedVault

FAMILY = "level_flow"
SEED = 424242


def _set_pools(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for name in ("DEV", "PUBLIC", "PRIVATE", "RETIRED"):
        monkeypatch.setenv(f"PHOS_SEEDS_{name}", str(tmp_path / f"{name.lower()}.seedvault.json"))


def _seed_dev_pool(tmp_path: Path) -> None:
    (tmp_path / "dev.seedvault.json").write_text(
        json.dumps([{"family": FAMILY, "seed": SEED}]), encoding="utf-8"
    )


def test_make_exam_writes_an_exam_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_pools(monkeypatch, tmp_path)
    _seed_dev_pool(tmp_path)
    exam_path = tmp_path / "exam.json"

    status = main(
        [
            "make-exam",
            "--pool",
            "dev",
            "--scorer-version",
            "s6-test",
            "--size",
            "1",
            "--hours",
            "24.0",
            "--out",
            str(exam_path),
        ]
    )

    assert status == 0
    assert exam_path.exists()


def test_run_then_report_produces_a_markdown_and_json_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_pools(monkeypatch, tmp_path)
    _seed_dev_pool(tmp_path)
    exam_path = tmp_path / "exam.json"
    scores_path = tmp_path / "scores.json"
    report_dir = tmp_path / "report"

    assert (
        main(
            [
                "make-exam",
                "--pool",
                "dev",
                "--scorer-version",
                "s6-test",
                "--size",
                "1",
                "--hours",
                "24.0",
                "--out",
                str(exam_path),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "run",
                "--exam",
                str(exam_path),
                "--detector",
                "phos.referee.demo:threshold_detector",
                "--work-dir",
                str(tmp_path / "work"),
                "--out",
                str(scores_path),
            ]
        )
        == 0
    )
    assert scores_path.exists()
    assert (
        main(
            [
                "report",
                "--exam",
                str(exam_path),
                "--run",
                str(scores_path),
                "--out",
                str(report_dir),
            ]
        )
        == 0
    )

    reports = list(report_dir.glob("*.md"))
    assert reports
    assert "SIMULATED" in reports[0].read_text(encoding="utf-8")


def test_run_refuses_an_unknown_detector_factory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_pools(monkeypatch, tmp_path)
    _seed_dev_pool(tmp_path)
    exam_path = tmp_path / "exam.json"
    assert (
        main(
            [
                "make-exam",
                "--pool",
                "dev",
                "--scorer-version",
                "s6-test",
                "--size",
                "1",
                "--hours",
                "24.0",
                "--out",
                str(exam_path),
            ]
        )
        == 0
    )

    status = main(
        [
            "run",
            "--exam",
            str(exam_path),
            "--detector",
            "not_a_module:not_a_function",
            "--work-dir",
            str(tmp_path / "work"),
            "--out",
            str(tmp_path / "scores.json"),
        ]
    )
    assert status == 1


def test_retire_seeds_moves_a_seed_to_retired(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_pools(monkeypatch, tmp_path)
    (tmp_path / "private.seedvault.json").write_text(
        json.dumps([{"family": FAMILY, "seed": 1}]), encoding="utf-8"
    )

    status = main(["retire-seeds", "--family", FAMILY, "--seed", "1"])

    assert status == 0
    vault = SeedVault.from_env()
    assert vault.load(SeedPool.PRIVATE) == ()
    assert len(vault.load(SeedPool.RETIRED)) == 1


def test_make_exam_without_env_vars_fails_cleanly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in ("DEV", "PUBLIC", "PRIVATE", "RETIRED"):
        monkeypatch.delenv(f"PHOS_SEEDS_{name}", raising=False)

    status = main(
        [
            "make-exam",
            "--pool",
            "dev",
            "--scorer-version",
            "s6-test",
            "--out",
            str(tmp_path / "exam.json"),
        ]
    )
    assert status == 1

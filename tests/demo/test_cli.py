"""The ``phos`` command offers the demo and the onboarding brief."""

from pathlib import Path

import pytest

from phos.demo.cli import main


def test_no_subcommand_prints_help_and_succeeds(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    printed = capsys.readouterr().out
    assert "demo" in printed
    assert "onboard" in printed


def test_onboard_briefs_a_historian_alone(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """ADR 0341: the brief is reachable from the ``phos`` command, with no capture."""
    historian = tmp_path / "historian.csv"
    historian.write_text("time,FT_101\n0,1.0\n", encoding="utf-8")
    assert main(["onboard", "--historian", str(historian)]) == 0
    printed = capsys.readouterr().out
    assert "Suggestions are not declarations" in printed
    assert "FT_101\tsensor\tflow\t" in printed


def test_onboard_without_a_historian_is_refused() -> None:
    with pytest.raises(SystemExit):
        main(["onboard"])


def test_onboard_reports_a_missing_file_without_raising(tmp_path: Path) -> None:
    assert main(["onboard", "--historian", str(tmp_path / "missing.csv")]) == 2


def test_an_unknown_scenario_is_refused() -> None:
    with pytest.raises(SystemExit):
        main(["demo", "--scenario", "everything"])

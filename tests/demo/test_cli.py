"""The ``phos`` command offers the demo and nothing else yet."""

import pytest

from phos.demo.cli import main


def test_no_subcommand_prints_help_and_succeeds(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    assert "demo" in capsys.readouterr().out


def test_an_unknown_scenario_is_refused() -> None:
    with pytest.raises(SystemExit):
        main(["demo", "--scenario", "everything"])

"""CLI for PHOS Benchmark v1 prints the frozen table and does not search thresholds."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

import pytest

from phos.eval.benchmark import (
    BENCHMARK_PROTOCOL_ID,
    BENCHMARK_SEED,
    assemble_v1_table,
    render_v1_markdown,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "evaluate_phos_benchmark.py"


def test_cli_prints_the_frozen_table(capsys: pytest.CaptureFixture[str]) -> None:
    argv = sys.argv
    sys.argv = ["evaluate_phos_benchmark.py"]
    try:
        with pytest.raises(SystemExit) as exit_info:
            runpy.run_path(str(SCRIPT), run_name="__main__")
        assert exit_info.value.code == 0
    finally:
        sys.argv = argv
    captured = capsys.readouterr().out
    assert BENCHMARK_PROTOCOL_ID in captured
    assert "646.58" in captured
    assert "REFUSED" in captured
    assert render_v1_markdown(assemble_v1_table()) in captured


def test_cli_write_does_not_search_thresholds(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = sys.argv
    sys.argv = [
        "evaluate_phos_benchmark.py",
        "--write",
        "--output-dir",
        str(tmp_path),
    ]
    try:
        with pytest.raises(SystemExit) as exit_info:
            runpy.run_path(str(SCRIPT), run_name="__main__")
        assert exit_info.value.code == 0
    finally:
        sys.argv = argv
    markdown = (tmp_path / "phos-benchmark-v1.md").read_text(encoding="utf-8")
    payload = (tmp_path / "phos-benchmark-v1.json").read_text(encoding="utf-8")
    assert markdown == render_v1_markdown(assemble_v1_table())
    assert f'"seed": {BENCHMARK_SEED}' in payload
    assert '"threshold_search": false' in payload
    assert "REFUSED" in markdown
    _ = capsys.readouterr()


def test_cli_extra_flags_write_research_files_without_searching_thresholds(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = sys.argv
    sys.argv = [
        "evaluate_phos_benchmark.py",
        "--write",
        "--ablation",
        "--adversary",
        "--research",
        "--output-dir",
        str(tmp_path),
    ]
    try:
        with pytest.raises(SystemExit) as exit_info:
            runpy.run_path(str(SCRIPT), run_name="__main__")
        assert exit_info.value.code == 0
    finally:
        sys.argv = argv
    frozen = (tmp_path / "phos-benchmark-v1.md").read_text(encoding="utf-8")
    ablation = (tmp_path / "ablation-fixture.md").read_text(encoding="utf-8")
    adversary = (tmp_path / "adversary-catalogue.md").read_text(encoding="utf-8")
    research = (tmp_path / "clock-b-research.md").read_text(encoding="utf-8")
    assert frozen == render_v1_markdown(assemble_v1_table())
    assert "FIXTURE" in ablation.upper() or "not a public row" in ablation.lower()
    assert "646.58" in ablation
    assert "gradual-drift" in adversary
    assert "646.58" in research
    assert "threshold search" in research.lower()
    _ = capsys.readouterr()

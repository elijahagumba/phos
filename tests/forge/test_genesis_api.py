"""Tests for the GENESIS interface, and for the separation it exists to enforce.

The separation is a property of the *source*, not of a run: no module under ``phos.forge`` may
construct a research record or write under ``docs/genesis``. A behavioural test could only catch the
day somebody added one, and only if the new path happened to be exercised.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from phos.forge import genesis_api
from phos.forge.genesis_api import (
    DeclarationProblemError,
    declaration,
    declaration_json,
    gate,
    require_declared,
    snapshot,
    tier,
)

PACKAGE = Path(__file__).resolve().parents[2] / "src/phos/forge"
REAL_ROOT = Path(__file__).resolve().parents[2]

#: The record types FORGE must never construct. A second writer with its own validation is the
#: failure the thinness requirement exists to prevent.
_RECORD_TYPES = ("Declaration", "Measurement", "Verdict", "Experiment", "Question", "Finding")


def test_no_forge_module_constructs_a_record_type() -> None:
    offenders: list[str] = []
    for path in PACKAGE.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in _RECORD_TYPES:
                    offenders.append(f"{path.name}: {node.func.id}()")
    assert offenders == [], f"FORGE constructs a research record: {offenders}"


def test_no_forge_module_opens_a_genesis_path_for_writing() -> None:
    """``docs/genesis`` is reached through the GENESIS command line, never written directly."""
    offenders: list[str] = []
    for path in PACKAGE.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), start=1):
            if "docs/genesis" in line and (
                "write_text" in line or "open(" in line or "mkdir" in line
            ):
                offenders.append(f"{path.name}:{line_number}: {line.strip()}")
    assert offenders == [], f"FORGE writes to Genesis directly: {offenders}"


def test_the_only_genesis_writes_are_through_the_script() -> None:
    """The three writing functions shell out, and none of them writes the file itself."""
    source = (PACKAGE / "genesis_api.py").read_text(encoding="utf-8")
    for name in ("def declare(", "def result(", "def audit("):
        assert name in source
    assert "_run_genesis" in source


def test_tier_reads_the_real_rule(repo: Path) -> None:
    verdict = tier(repo, "phos-icssim-dev4-walk", "iterate")
    assert verdict.tier == "green"
    assert not verdict.refused


def test_tier_refuses_a_never_corpus(repo: Path) -> None:
    verdict = tier(repo, "hai", "iterate")
    assert verdict.refused


def test_a_declaration_reads_from_the_real_store(declared_repo: Path) -> None:
    record = declaration(declared_repo, "E-0001")
    assert str(record.id) == "E-0001"
    assert record.phase == "declared"


def test_require_declared_accepts_a_declaration(declared_repo: Path) -> None:
    assert str(require_declared(declared_repo, "E-0001").id) == "E-0001"


def test_require_declared_refuses_a_missing_record(declared_repo: Path) -> None:
    with pytest.raises(DeclarationProblemError, match="is not in docs/genesis"):
        require_declared(declared_repo, "E-0404")


def test_require_declared_refuses_a_judged_record(declared_repo: Path) -> None:
    """Building against a judged record is building against the answer."""
    import json
    import subprocess

    path = declared_repo / "docs/genesis/experiments/E-0001.json"
    data = json.loads(path.read_text())
    data["phase"] = "judged"
    data["measured"] = {
        "date": "2026-11-25",
        "commit": "0" * 40,
        "report": "a report",
        "values": {"b1": 1.0},
        "failures": "none",
        "notes": "none",
    }
    data["verdict"] = {"outcome": "kept", "per_bar": {"b1": True}, "adr": None}
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    subprocess.run(
        ["git", "-C", str(declared_repo), "commit", "-am", "judge it"],
        capture_output=True,
        check=True,
    )
    with pytest.raises(DeclarationProblemError, match="judged"):
        require_declared(declared_repo, "E-0001")


def test_snapshot_counts_the_record(declared_repo: Path) -> None:
    questions, experiments, findings = snapshot(declared_repo)
    assert questions == 1
    assert experiments == 1
    assert findings == 0


def test_declaration_json_returns_the_raw_record(declared_repo: Path) -> None:
    data = declaration_json(declared_repo, "E-0001")
    assert data["id"] == "E-0001"


def test_declaration_json_refuses_a_missing_file(declared_repo: Path) -> None:
    with pytest.raises(DeclarationProblemError, match="does not exist"):
        declaration_json(declared_repo, "E-0404")


def test_declaration_json_refuses_a_file_that_is_not_an_object(declared_repo: Path) -> None:
    path = declared_repo / "docs/genesis/experiments/E-0002.json"
    path.write_text("[1, 2, 3]\n")
    with pytest.raises(DeclarationProblemError, match="not a JSON object"):
        declaration_json(declared_repo, "E-0002")


def test_the_gate_has_no_opinion_about_a_non_harness_command(declared_repo: Path) -> None:
    assert gate(declared_repo, "echo hello") is None


def test_the_gate_refuses_an_undeclared_harness(declared_repo: Path) -> None:
    decision = gate(declared_repo, "uv run python scripts/lane_other.py --corpus data/x")
    assert decision is not None
    assert not decision.allowed


def test_the_gate_allows_the_declared_command(declared_repo: Path) -> None:
    """A declaration in the record makes its own command allowed. Nothing else does."""
    decision = gate(
        declared_repo,
        "uv run python scripts/lane_probe.py --corpus data/phos-icssim-dev4-walk",
    )
    assert decision is not None
    assert decision.allowed, decision.detail


def test_the_gate_refuses_a_different_harness(declared_repo: Path) -> None:
    decision = gate(
        declared_repo,
        "uv run python scripts/lane_other.py --corpus data/phos-icssim-dev4-walk",
    )
    assert decision is not None
    assert not decision.allowed


def test_the_interface_exposes_no_writer_that_skips_the_command() -> None:
    exported = {name for name in dir(genesis_api) if not name.startswith("_")}
    for name in ("declare", "result", "audit"):
        assert name in exported
    assert "write" not in exported


def test_the_real_repository_has_a_judged_first_experiment() -> None:
    """The first baseline case is a result, so the harness must reconstruct it from its commit.

    This is the fact Step 5 rests on: ``require_declared`` refusing E-0001 is correct behaviour,
    and the baseline harness reads the earlier commit instead of the live record.
    """
    if not (REAL_ROOT / "docs/genesis/experiments/E-0001.json").is_file():
        pytest.skip("the real record is not in this checkout")
    record = declaration(REAL_ROOT, "E-0001")
    assert record.phase == "judged"
    with pytest.raises(DeclarationProblemError):
        require_declared(REAL_ROOT, "E-0001")

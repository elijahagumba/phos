"""A throwaway git repository with a GENESIS record in it, for the store and CLI tests."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from tests.lab_only import RULES_ABSENT_REASON, skip_if_absent

#: One filled-in question, the shape ``ask`` accepts.
QUESTION: dict[str, Any] = {
    "title": "Can the inlet law be inferred from the register tables alone?",
    "frontier": "V.2 discovery of physical and operational constraints",
    "opened": "2026-11-03",
    "state_of_the_art": "Residual detectors assume an engineer supplied the law.",
    "gap": "Nothing establishes whether the law is recoverable from the tables.",
    "priority": {
        "significance": 5,
        "originality": 4,
        "feasibility": 3,
        "information_gain": 5,
        "tractability": 3,
        "relevance": 5,
        "operational_impact": 4,
        "evidence": 2,
        "cost": 3,
    },
}

#: The command the sample experiment declares. The tests gate on this exact string.
COMMAND = "uv run python scripts/lane_inlet.py --corpus data/phos-icssim-dev4"

EXPERIMENT: dict[str, Any] = {
    "question": "Q-0001",
    "declared": {
        "date": "2026-11-03",
        "hypothesis": "The inlet law is recoverable from the register tables with no map.",
        "why_it_might_be_wrong": "The tables may underdetermine the law, so several fit.",
        "falsifier": "Two incompatible laws fit the same tables on the development corpus.",
        "baseline": "The engineer-supplied map in declared_law.py",
        "command": COMMAND,
        "corpus": "phos-icssim-dev4",
        "tier": "iterate",
        "result_name": "law-inlet:invariants",
        "bars": [
            {
                "id": "b1",
                "metric": "laws_fitting",
                "comparator": "==",
                "threshold": 1.0,
                "text": "Exactly one law fits.",
            }
        ],
    },
}

MEASUREMENT: dict[str, Any] = {
    "date": "2026-11-03",
    "commit": "abcdef1234567",
    "report": "eval_runs/law-inlet.md",
    "values": {"b1": 2.0},
    "failures": "Both pumps underdetermine the law when the valve tag is absent.",
}


#: The repository root, so the throwaway checkout can carry the real rule and registry. A
#: declaration is resolved against those, so a fixture without them would only ever exercise the
#: unknown-corpus refusal (ADR 0416).
REPO = Path(__file__).resolve().parents[2]


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Return an initialised git repository carrying the rule and registry a declaration needs.

    The tier is resolved from ``docs/rules/data-tiers.md`` and ``data/registry.json`` rather than
    from the payload, so a checkout that lacks them refuses every declaration. The copies are the
    real files, not a cut-down stand-in: a test that ran against a fixture rule would prove
    nothing about the rule this repository ships.
    """
    for name in ("data-tiers.md", "docs-on-main.md"):
        skip_if_absent(REPO / "docs" / "rules" / name, RULES_ABSENT_REASON)
    subprocess.run(["git", "init", "-q", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.invalid"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=tmp_path, check=True)
    (tmp_path / "eval_runs").mkdir()
    (tmp_path / "eval_runs" / "law-inlet.md").write_text("report\n", encoding="utf-8")
    (tmp_path / "docs" / "rules").mkdir(parents=True)
    for name in ("data-tiers.md", "docs-on-main.md"):
        (tmp_path / "docs" / "rules" / name).write_bytes(
            (REPO / "docs" / "rules" / name).read_bytes()
        )
    (tmp_path / "data").mkdir()
    registry = (REPO / "data" / "registry.json").read_bytes()
    (tmp_path / "data" / "registry.json").write_bytes(registry)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "root"], cwd=tmp_path, check=True)
    return tmp_path


@pytest.fixture
def commit(repo: Path) -> Callable[[str], None]:
    """Return a function that commits everything in the repository."""

    def _commit(message: str) -> None:
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-qm", message], cwd=repo, check=True)

    return _commit


@pytest.fixture
def payload(tmp_path: Path) -> Callable[[str, dict[str, Any]], Path]:
    """Return a function that writes one JSON payload and gives back its path."""

    def _write(name: str, body: dict[str, Any]) -> Path:
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(body), encoding="utf-8")
        return path

    return _write

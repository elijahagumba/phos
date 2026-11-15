"""A throwaway checkout with the rule files and tracker the guards read."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

#: A cut-down data-tier rule in the real file's shape: bold lead, backticked names, seed ranges.
TIER_RULE = """# Data tiers

- **Never read, score or iterate on** `hai`, `hai-21.03`, `hai-23.05`, `batadal`.
  They are validation corpora.
- **Never touch** T1's held-out seeds 94001-94020, or the used seed sets.
- **Score once, only after a committed declaration**: `phos-icssim-heldout`.
- **Iterate freely on** `hai-20.07`, `batch-distillation`, `phos-icssim-dev4`.
- **Frozen:** Never append `eval_runs/log.jsonl`.
"""

TRACKER = {
    "schema_version": 1,
    "swarm": [
        {
            "role": "category-lock",
            "file_scope": [".phos_roadmap_state.json", ".cursor/rules/**", "docs/adr/**"],
        },
        {"role": "writer", "file_scope": ["PROGRESS.md", "encyclopedia/"]},
        {"role": "scopeless", "file_scope": []},
    ],
}


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    """Return a git checkout carrying the tier rule and the tracker."""
    (tmp_path / "docs" / "rules").mkdir(parents=True)
    (tmp_path / "docs" / "rules" / "data-tiers.md").write_text(TIER_RULE, encoding="utf-8")
    (tmp_path / "docs" / "rules" / "docs-on-main.md").write_text("# ADR 0044\n", encoding="utf-8")
    (tmp_path / ".phos_roadmap_state.json").write_text(json.dumps(TRACKER), encoding="utf-8")
    subprocess.run(["git", "init", "-q", "-b", "main", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.invalid"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "root"], cwd=tmp_path, check=True)
    return tmp_path


@pytest.fixture
def stage(checkout: Path) -> Callable[[str], None]:
    """Return a function that creates and stages one path inside the checkout."""

    def _stage(relative: str) -> None:
        path = checkout / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x\n", encoding="utf-8")
        subprocess.run(["git", "add", "--", relative], cwd=checkout, check=True)

    return _stage

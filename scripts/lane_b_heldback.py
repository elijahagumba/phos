#!/usr/bin/env python3
"""The one held-back look at lane B's maintenance-closure harness (ADR 0151, ADR 0164).

``--declare`` writes ``eval_runs/build/lane-b/heldback-declaration.json``: the command, the result
name, and the sha256 of every scored file. ``--run`` refuses unless that file is present and every
hash matches, and unless the result file does not exist yet. Nothing here appends
``eval_runs/log.jsonl``.

Usage::

    uv run python scripts/lane_b_heldback.py --declare
    uv run python scripts/lane_b_heldback.py --run
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Final

from phos.eval.maintenance_harness import (
    render_closure_markdown,
    score_held_back_closures_once,
    score_held_back_consistency_once,
    synthetic_scorecard,
)

ROOT: Final = Path(__file__).resolve().parents[1]
OUT_DIR: Final = ROOT / "eval_runs" / "build" / "lane-b"
DECLARATION: Final = OUT_DIR / "heldback-declaration.json"
RESULT: Final = OUT_DIR / "maintenance-closure-heldback.json"
SCORED_FILES: Final[tuple[str, ...]] = (
    "src/phos/atlas/maintenance_closure.py",
    "src/phos/atlas/cmms.py",
    "src/phos/atlas/consistency.py",
    "src/phos/eval/maintenance_harness.py",
    "src/phos/synth/maintenance.py",
    "scripts/lane_b_heldback.py",
)
COMMAND: Final = "uv run python scripts/lane_b_heldback.py --run"
RESULT_NAME: Final = "lane-b-maintenance-closure-heldback"


def code_sha256(root: Path = ROOT) -> dict[str, str]:
    """Return each scored file's sha256 and one combined digest, in `SCORED_FILES` order."""
    combined = hashlib.sha256()
    per_file: dict[str, str] = {}
    for relative in SCORED_FILES:
        data = (root / relative).read_bytes()
        per_file[relative] = hashlib.sha256(data).hexdigest()
        combined.update(relative.encode())
        combined.update(b"\0")
        combined.update(data)
    per_file["combined"] = combined.hexdigest()
    return per_file


def require_declaration(path: Path, digest: dict[str, str]) -> None:
    """Refuse the run unless the committed declaration matches this code.

    Raises:
        SystemExit: If the declaration is missing, or its command, result name or hash differs.
    """
    if not path.is_file():
        raise SystemExit(f"held-back run refused: no declaration at {path}")
    recorded = json.loads(path.read_text(encoding="utf-8"))
    if recorded.get("command") != COMMAND:
        raise SystemExit("held-back run refused: declaration command does not match")
    if recorded.get("result_name") != RESULT_NAME:
        raise SystemExit("held-back run refused: declaration result name does not match")
    if recorded.get("code_sha256") != digest:
        raise SystemExit("held-back run refused: declaration sha256 does not match the code")


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns a process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--declare", action="store_true")
    group.add_argument("--run", action="store_true")
    arguments = parser.parse_args(argv)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if arguments.declare:
        body = {
            "result_name": RESULT_NAME,
            "command": COMMAND,
            "code_sha256": code_sha256(),
            "seeds": "97101-97120",
            "bars": {
                "maintenance_closure_rate": ">= 0.70",
                "attack_and_mimic_closed": "0",
            },
            "note": (
                "One look at seeds 97101-97120 with the ADR 0151 harness as committed. "
                "Do not edit a scored file between this declaration and the run."
            ),
        }
        DECLARATION.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {DECLARATION}")
        return 0
    if RESULT.exists():
        raise SystemExit(f"held-back run refused: {RESULT} already exists")
    require_declaration(DECLARATION, code_sha256())
    started = time.perf_counter()
    closure = score_held_back_closures_once()
    consistency = score_held_back_consistency_once()
    elapsed = time.perf_counter() - started
    payload = {
        "result_name": RESULT_NAME,
        "closure": closure.model_dump(mode="json"),
        "consistency": consistency.model_dump(mode="json"),
        "scorecard": synthetic_scorecard(closure, consistency, elapsed),
        "runtime_seconds": elapsed,
    }
    RESULT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    body_md = render_closure_markdown(closure, consistency)
    body_md = body_md.replace("97001-97020", "97101-97120 (held back, one look)")
    (OUT_DIR / "maintenance-closure-heldback.md").write_text(body_md, encoding="utf-8")
    print(
        f"maintenance {closure.maintenance_closed}/{closure.maintenance_alerts} "
        f"({closure.maintenance_closure_rate:.4f}); attacks closed "
        f"{closure.attack_closed}/{closure.attack_alerts}; mimic closed "
        f"{closure.mimic_closed}/{closure.mimic_alerts}; consistency catches "
        f"{consistency.attacks_caught}/{consistency.attacks}; unexplained per shift "
        f"{consistency.false_alerts_per_shift:.4f}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

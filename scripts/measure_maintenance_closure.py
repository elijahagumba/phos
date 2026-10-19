"""Score lane B's maintenance-closure harness and write the lane folder.

Does not append ``eval_runs/log.jsonl``. Does not open Kelmarsh. Seeds are 97001-97020.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from phos.eval.maintenance_harness import (
    render_closure_markdown,
    score_consistency,
    score_development_closures,
    synthetic_scorecard,
)


def main() -> None:
    """Run the declared harness and write JSON and markdown under the lane folder."""
    started = time.perf_counter()
    closure = score_development_closures()
    consistency = score_consistency()
    elapsed = time.perf_counter() - started
    card = synthetic_scorecard(closure, consistency, elapsed)
    root = Path(__file__).resolve().parents[1]
    out = root / "eval_runs" / "build" / "lane-b"
    out.mkdir(parents=True, exist_ok=True)
    payload = {
        "closure": closure.model_dump(mode="json"),
        "consistency": consistency.model_dump(mode="json"),
        "scorecard": card,
        "runtime_seconds": elapsed,
    }
    (out / "maintenance-closure.json").write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )
    body = render_closure_markdown(closure, consistency)
    body += f"\nRuntime for both measurements: {elapsed:.3f} seconds.\n"
    (out / "maintenance-closure.md").write_text(body, encoding="utf-8")
    rate = closure.maintenance_closure_rate
    print(
        f"maintenance {closure.maintenance_closed}/{closure.maintenance_alerts} ({rate:.4f}); "
        f"attacks closed {closure.attack_closed}/{closure.attack_alerts}; "
        f"mimic closed {closure.mimic_closed}/{closure.mimic_alerts}; "
        f"consistency catches {consistency.attacks_caught}/{consistency.attacks} "
        f"({consistency.detector}); wrote {out}"
    )


if __name__ == "__main__":
    main()

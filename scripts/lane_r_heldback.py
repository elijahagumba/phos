#!/usr/bin/env python3
"""Score Lane R held-back seeds 97701-97720 once.

The declaration file must already say ``authorized`` is true. The result file is
written once; a second start refuses. Calibration is fit on the committed development
rows, not on these seeds. Nothing is appended to ``eval_runs/log.jsonl``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from phos.atlas.conformal_confidence import ShapedOutcome  # noqa: E402
from phos.eval.build_declaration import LANE_R_HELD_BACK_SEEDS  # noqa: E402
from phos.eval.lane_r import DevelopmentRow, score_seeds  # noqa: E402
from phos.eval.separation_confidence import (  # noqa: E402
    calibrate,
    development_counts,
    reliability,
)

OUT_DIR = REPO_ROOT / "eval_runs" / "build" / "d" / "reasoning"
DECLARATION = OUT_DIR / "held-back-declaration.json"
DEVELOPMENT = OUT_DIR / "h2b-development-rows.json"
RESULT = OUT_DIR / "held-back.json"
RESULT_NAME = "build-d:reasoning-heldback"


def main() -> int:
    """Write the one held-back summary, or refuse."""
    if RESULT.exists():
        print("held-back result already exists", file=sys.stderr)
        return 2
    if not DECLARATION.exists() or not DEVELOPMENT.exists():
        print("held-back declaration or development rows are missing", file=sys.stderr)
        return 2
    declared = json.loads(DECLARATION.read_text(encoding="utf-8"))
    if declared.get("authorized") is not True or declared.get("result_name") != RESULT_NAME:
        print("held-back Lane R is not authorized", file=sys.stderr)
        return 2
    if tuple(declared.get("seeds", [])) != LANE_R_HELD_BACK_SEEDS:
        print("declaration seeds are not 97701-97720", file=sys.stderr)
        return 2
    development = _load_rows(DEVELOPMENT)
    counts = development_counts(development)
    rows = score_seeds(LANE_R_HELD_BACK_SEEDS, "h2b", held_back_authorized=True)
    leads = calibrate(rows, counts)
    body = reliability(leads)
    fraction = body["fraction"]
    contentful_met = isinstance(fraction, float) and fraction > 33 / 54
    body["contentful_bar"] = "33/54"
    body["contentful_bar_met"] = contentful_met
    body["both_bars_met"] = bool(body["high_bar_met"]) and contentful_met
    body["result_name"] = RESULT_NAME
    body["seeds"] = list(LANE_R_HELD_BACK_SEEDS)
    RESULT.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    print(
        f"contentful={body['contentful']} right={body['right']} "
        f"fraction={fraction} contentful_bar={contentful_met} "
        f"high={body['high']} high_bar={body['high_bar_met']} both={body['both_bars_met']}"
    )
    return 0


def _load_rows(path: Path) -> tuple[DevelopmentRow, ...]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    rows: list[DevelopmentRow] = []
    for item in raw:
        correct = item["correct"]
        rows.append(
            DevelopmentRow(
                ShapedOutcome(
                    seed=int(item["seed"]),
                    plant_id=str(item["plant_id"]),
                    scenario=str(item["scenario"]),
                    lead=str(item["lead"]),
                    raw_confidence=float(item["raw_confidence"]),
                    shape=tuple(item["shape"]),
                    contentful=bool(item["contentful"]),
                    correct=None if correct is None else bool(correct),
                ),
                int(item["separation"]),
                None if item["rival"] is None else str(item["rival"]),
            )
        )
    return tuple(rows)


if __name__ == "__main__":
    raise SystemExit(main())

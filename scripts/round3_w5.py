#!/usr/bin/env python3
"""Score the W5 scenarios. Development may be repeated. Held-back runs once.

Usage::

    uv run python scripts/round3_w5.py --split development
    uv run python scripts/round3_w5.py --split held-back
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Final

REPO_ROOT: Final = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(REPO_ROOT / "src"))

from phos.atlas.conformal_confidence import (  # noqa: E402
    ShapeCalibrator,
    ShapedOutcome,
    leave_one_seed_out,
)
from phos.eval.w5_confidence import (  # noqa: E402
    K_LIAR,
    chart_bins,
    held_back_bar,
    score_split,
)

OUT_DIR: Final = REPO_ROOT / "eval_runs" / "build" / "round-3"
DECLARATION: Final = OUT_DIR / "w5-heldback-declaration.json"
DEVELOPMENT_OUTCOMES: Final = OUT_DIR / "w5-development-outcomes.json"


def main() -> int:
    """Write one split's reliability summary. Held-back refuses to start twice."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=("development", "held-back"), required=True)
    args = parser.parse_args()
    if args.split == "held-back" and not _held_back_allowed():
        return 2
    outcomes = score_split(args.split, held_back_authorized=args.split == "held-back")
    if args.split == "development":
        DEVELOPMENT_OUTCOMES.write_text(_dump_outcomes(outcomes), encoding="utf-8")
        leads = leave_one_seed_out(outcomes)
        stem = "w5-development"
    else:
        fitted = ShapeCalibrator.fit(_load_outcomes(DEVELOPMENT_OUTCOMES))
        leads = tuple(
            fitted.calibrate(item)
            for item in outcomes
            if item.contentful and item.correct is not None
        )
        stem = "w5-heldback"
    body = held_back_bar(leads)
    svg = str(body.pop("chart"))
    (OUT_DIR / f"{stem}.svg").write_text(svg, encoding="utf-8")
    body["k_liar"] = K_LIAR
    body["bins"] = [item.as_dict() for item in chart_bins(leads)]
    body["split"] = args.split
    (OUT_DIR / f"{stem}.json").write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    print(
        f"{args.split}: contentful={body['contentful']} wrong={body['wrong']} "
        f"wrong_high={body['wrong_high']} bar={body['bar_met']}"
    )
    return 0


def _held_back_allowed() -> bool:
    result = OUT_DIR / "w5-heldback.json"
    if result.exists():
        print("held-back result already exists", file=sys.stderr)
        return False
    if not DECLARATION.exists() or not DEVELOPMENT_OUTCOMES.exists():
        print("held-back declaration or development outcomes are missing", file=sys.stderr)
        return False
    body = json.loads(DECLARATION.read_text(encoding="utf-8"))
    if body.get("authorized") is not True or body.get("k_liar") != K_LIAR:
        print("held-back W5 is not authorized at this k", file=sys.stderr)
        return False
    return True


def _dump_outcomes(outcomes: tuple[ShapedOutcome, ...]) -> str:
    rows = [
        {
            "seed": item.seed,
            "plant_id": item.plant_id,
            "scenario": item.scenario,
            "lead": item.lead,
            "raw_confidence": item.raw_confidence,
            "shape": list(item.shape),
            "contentful": item.contentful,
            "correct": item.correct,
        }
        for item in outcomes
    ]
    return json.dumps(rows, indent=2) + "\n"


def _load_outcomes(path: Path) -> tuple[ShapedOutcome, ...]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    return tuple(
        ShapedOutcome(
            seed=int(row["seed"]),
            plant_id=str(row["plant_id"]),
            scenario=str(row["scenario"]),
            lead=str(row["lead"]),
            raw_confidence=float(row["raw_confidence"]),
            shape=tuple(str(part) for part in row["shape"]),
            contentful=bool(row["contentful"]),
            correct=None if row["correct"] is None else bool(row["correct"]),
        )
        for row in rows
    )


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Score lane D's command-against-physics measurement.

Development seeds may be scored repeatedly. Held-back seeds are scored only when
``eval_runs/build/lane-d/declaration.json`` names this script's code hash, the command, and the
result name, and only when that result file does not already exist.

Usage::

    uv run python scripts/lane_d_score.py --split development
    uv run python scripts/lane_d_score.py --split development --workstream naming
    uv run python scripts/lane_d_score.py --split development --workstream calibration
    uv run python scripts/lane_d_score.py --declare
    uv run python scripts/lane_d_score.py --split held-back
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Final

from phos.atlas.command_physics import diagnosis, score_split, scorecard_numbers
from phos.atlas.explanation_calibration import reliability_svg, score_calibration
from phos.atlas.explanation_calibration import (
    scorecard_numbers as calibration_scorecard,
)
from phos.atlas.sensor_explainer import (
    EXPLAINER_RESULT_NAME,
    EXPLAINER_SETTINGS,
    naming_scorecard,
    score_naming,
)
from phos.atlas.sensor_explainer import (
    bar_met as naming_bar_met,
)
from phos.eval.build_declaration import SCORECARD

ROOT: Final = Path(__file__).resolve().parents[1]
OUT_DIR: Final = ROOT / "eval_runs" / "build" / "lane-d"
DECLARATION: Final = OUT_DIR / "declaration.json"
SCORED_FILES: Final[tuple[str, ...]] = (
    "src/phos/atlas/command_response.py",
    "src/phos/atlas/command_physics.py",
    "src/phos/atlas/templates.py",
    "src/phos/atlas/consistency_evidence.py",
    "src/phos/atlas/sensor_explainer.py",
    "src/phos/atlas/explanation_calibration.py",
    "scripts/lane_d_score.py",
)
HELD_BACK_COMMAND: Final = "uv run python scripts/lane_d_score.py --split held-back"
HELD_BACK_RESULT: Final = "lane-d-heldback"
DEVELOPMENT_RESULT: Final = "lane-d-command-physics-development"
NAMING_DEVELOPMENT_RESULT: Final = "lane-d-plant-map-explainer-development"
CALIBRATION_DEVELOPMENT_RESULT: Final = "lane-d-explanation-calibration-development"


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


def declaration_body() -> dict[str, object]:
    """The declaration a held-back run requires. Writing it does not score anything."""
    return {
        "result_name": HELD_BACK_RESULT,
        "command": HELD_BACK_COMMAND,
        "code_sha256": code_sha256(),
        "seeds": "97101-97120",
        "note": (
            "One look at seeds 97101-97120. The command scores command-against-physics, "
            "the lying-sensor explainer, and the reliability chart. The chart does not fit "
            "a Platt map. Do not edit the scored files between this declaration and the run. "
            "A mismatch refuses the run."
        ),
    }


def require_declaration(path: Path, digest: dict[str, str]) -> None:
    """Refuse a held-back run whose declaration is missing or does not match the code.

    Args:
        path: The committed declaration.
        digest: The hash of the code that would run now.

    Raises:
        SystemExit: If the declaration is absent or any recorded hash, command, or result name
            differs from this process.
    """
    if not path.is_file():
        raise SystemExit(f"held-back run refused: no declaration at {path}")
    recorded = json.loads(path.read_text(encoding="utf-8"))
    if recorded.get("command") != HELD_BACK_COMMAND:
        raise SystemExit("held-back run refused: declaration command does not match")
    if recorded.get("result_name") != HELD_BACK_RESULT:
        raise SystemExit("held-back run refused: declaration result name does not match")
    if recorded.get("code_sha256") != digest:
        raise SystemExit("held-back run refused: declaration sha256 does not match the code")


def score_names(split: str) -> dict[str, object]:
    """Score the lying-sensor explainer. Held-back is refused here; it shares one later command."""
    if split != "development":
        raise SystemExit(
            "naming's held-back look is not this flag; it waits for the one declared command"
        )
    started = time.perf_counter()
    results = score_naming(split, survey=True)
    elapsed = time.perf_counter() - started
    numbers = naming_scorecard(results)
    numbers["runtime"] = elapsed
    return {
        "result_name": NAMING_DEVELOPMENT_RESULT,
        "split": split,
        "explainer_result_name": EXPLAINER_RESULT_NAME,
        "naming_rules": EXPLAINER_SETTINGS.naming_rules,
        "folds": EXPLAINER_SETTINGS.folds,
        "bar_met": naming_bar_met(results),
        "scorecard": numbers,
        "subjects": [item.as_dict() for item in results],
        "note": (
            "Synthetic diagnosis. The map names the champion's alerts and does not change them. "
            "It is not a claim that the plant map improves detection on a real plant."
        ),
    }


def score_confidence(split: str) -> dict[str, object]:
    """Score explanation confidence. Held-back waits for the one declared command."""
    if split != "development":
        raise SystemExit(
            "calibration's held-back look is not this flag; it waits for the one declared command"
        )
    started = time.perf_counter()
    report = score_calibration(split)
    elapsed = time.perf_counter() - started
    numbers = calibration_scorecard(report)
    numbers["runtime"] = elapsed
    (OUT_DIR / "reliability-development.svg").write_text(
        reliability_svg(report.bins), encoding="utf-8"
    )
    return {
        "result_name": CALIBRATION_DEVELOPMENT_RESULT,
        "split": split,
        "bar_met": False,
        "scorecard": numbers,
        "report": report.as_dict(),
    }


def score_held_back() -> dict[str, object]:
    """One look at 97101-97120: command physics, naming, and the reliability chart.

    The chart does not fit a Platt map. Naming and command numbers share one scorecard.
    ``calibration`` stays null.
    """
    started = time.perf_counter()
    command_results = score_split("held-back")
    command_numbers = scorecard_numbers(command_results)
    naming_results = score_naming("held-back", survey=True)
    naming_numbers = naming_scorecard(naming_results)
    calibration = score_calibration("held-back", fit_platt=False)
    elapsed = time.perf_counter() - started
    numbers: dict[str, float | None] = dict.fromkeys(SCORECARD)
    for source in (command_numbers, naming_numbers, calibration_scorecard(calibration)):
        for key, value in source.items():
            if value is not None:
                numbers[key] = value
    numbers["runtime"] = elapsed
    (OUT_DIR / "reliability-heldback.svg").write_text(
        reliability_svg(calibration.bins), encoding="utf-8"
    )
    return {
        "result_name": HELD_BACK_RESULT,
        "split": "held-back",
        "scorecard": numbers,
        "command": {
            "result_name": "lane-d-command-physics-heldback",
            "scorecard": command_numbers,
            "diagnosis": diagnosis(command_results),
            "seeds": [item.as_dict() for item in command_results],
        },
        "naming": {
            "result_name": "lane-d-plant-map-explainer-heldback",
            "bar_met": naming_bar_met(naming_results),
            "scorecard": naming_numbers,
            "subjects": [item.as_dict() for item in naming_results],
        },
        "calibration": {
            "result_name": "lane-d-explanation-calibration-heldback",
            "bar_met": False,
            "scorecard": calibration_scorecard(calibration),
            "report": calibration.as_dict(),
        },
    }


def score(split: str) -> dict[str, object]:
    """Score development command physics. Held-back goes through `score_held_back`."""
    if split != "development":
        raise ValueError("held-back scores are the one declared command, not this function")
    started = time.perf_counter()
    results = score_split(split)
    elapsed = time.perf_counter() - started
    numbers = scorecard_numbers(results)
    numbers["runtime"] = elapsed
    return {
        "result_name": DEVELOPMENT_RESULT,
        "split": split,
        "scorecard": numbers,
        "diagnosis": diagnosis(results),
        "seeds": [item.as_dict() for item in results],
    }


def main(argv: list[str] | None = None) -> int:
    """Write a development score, a declaration, or the one held-back score."""
    parser = argparse.ArgumentParser(description="Score lane D command-against-physics runs.")
    parser.add_argument("--split", choices=("development", "held-back"))
    parser.add_argument(
        "--workstream",
        choices=("command", "naming", "calibration"),
        default="command",
        help="command is A4; naming is the explainer; calibration is the reliability chart.",
    )
    parser.add_argument(
        "--declare",
        action="store_true",
        help="Write declaration.json from the current code and do not score.",
    )
    args = parser.parse_args(argv)
    if args.declare and args.split is not None:
        raise SystemExit("--declare does not score; omit --split")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if args.declare:
        DECLARATION.write_text(
            json.dumps(declaration_body(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return 0
    if args.split is None:
        raise SystemExit("pass --split development, --split held-back, or --declare")
    if args.workstream == "naming":
        output = OUT_DIR / "naming-development.json"
        payload = score_names(args.split)
    elif args.workstream == "calibration":
        output = OUT_DIR / "calibration-development.json"
        payload = score_confidence(args.split)
    elif args.split == "held-back":
        output = OUT_DIR / "heldback.json"
        if output.exists():
            raise SystemExit(f"held-back result already exists at {output}; not scoring again")
        require_declaration(DECLARATION, code_sha256())
        payload = score_held_back()
    else:
        output = OUT_DIR / "development.json"
        payload = score(args.split)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.split == "held-back":
        command_body = payload.get("command")
        diagnosis_body = command_body.get("diagnosis") if isinstance(command_body, dict) else None
        naming_body = payload.get("naming")
        naming_met = naming_body.get("bar_met") if isinstance(naming_body, dict) else None
        print(f"{payload['result_name']}: naming_bar_met={naming_met}")
    else:
        diagnosis_body = payload.get("diagnosis")
    if isinstance(diagnosis_body, dict):
        print(
            f"{payload['result_name']}: a4_bar_met={diagnosis_body.get('a4_bar_met')} "
            f"passed={diagnosis_body.get('a4_seeds_passed')}/"
            f"{diagnosis_body.get('a4_seeds_scored')}"
        )
    elif args.workstream == "naming":
        print(f"{payload['result_name']}: bar_met={payload.get('bar_met')}")
    elif args.workstream == "calibration":
        report = payload.get("report")
        surfaced = report.get("surfaced") if isinstance(report, dict) else None
        print(f"{payload['result_name']}: surfaced={surfaced} bar_met={payload.get('bar_met')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

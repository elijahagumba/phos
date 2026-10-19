#!/usr/bin/env python3
"""Score lane E's Atlas work on the synthetic plants (ADR 0144 seeds).

Development seeds 97001-97020 may be scored any number of times. Held-back seeds 97101-97120 are
scored only by ``--split held-back``, which refuses unless
``eval_runs/build/lane-e/heldback-declaration.json`` names this command, the result name and the
sha256 of every scored file, and unless the held-back result file does not exist yet.

Usage::

    uv run python scripts/lane_e_score.py --workstream naming
    uv run python scripts/lane_e_score.py --workstream naming-guard
    uv run python scripts/lane_e_score.py --declare
    uv run python scripts/lane_e_score.py --split held-back
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Final

from phos.atlas.conformal_confidence import (
    HIGH_BOUND,
    ShapeCalibrator,
    leave_one_seed_out,
    score_shaped,
    summarise,
)
from phos.atlas.loop_explainer import (
    ALL_NINE,
    LOOP_EXPLAINER_RESULT_NAME,
    every_sensor_subjects,
    naming_totals,
    score_subjects,
)
from phos.atlas.root_cause import ROOT_CAUSE_RESULT_NAME, score_root_causes
from phos.atlas.sensor_explainer import (
    EXPLAINER_RESULT_NAME,
    LiarSubject,
    SubjectResult,
    score_subject,
)

ROOT: Final = Path(__file__).resolve().parents[1]
OUT_DIR: Final = ROOT / "eval_runs" / "build" / "lane-e"
DECLARATION: Final = OUT_DIR / "heldback-declaration.json"
HELD_BACK_RESULT_FILE: Final = OUT_DIR / "heldback.json"
HELD_BACK_COMMAND: Final = "uv run python scripts/lane_e_score.py --split held-back"
HELD_BACK_RESULT: Final = "lane-e-heldback"
SCORED_FILES: Final[tuple[str, ...]] = (
    "src/phos/atlas/loop_explainer.py",
    "src/phos/atlas/sensor_explainer.py",
    "src/phos/atlas/plant_map_fit.py",
    "src/phos/atlas/plant_map_model.py",
    "src/phos/atlas/plant_map_naming.py",
    "src/phos/atlas/conformal_confidence.py",
    "src/phos/atlas/root_cause.py",
    "scripts/lane_e_score.py",
)

logger = logging.getLogger("lane_e_score")


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
    """Refuse a held-back run whose committed declaration is missing or does not match.

    Raises:
        SystemExit: If the declaration is absent or its command, result name or hash differs.
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


def _lane_d(subjects: Sequence[LiarSubject], split: str) -> tuple[SubjectResult, ...]:
    return tuple(score_subject(subject, split=split) for subject in subjects)


def _compare(
    subjects: Sequence[LiarSubject],
    split: str,
    current: Callable[[Sequence[LiarSubject], str], tuple[SubjectResult, ...]] = _lane_d,
) -> dict[str, object]:
    """Lane D's explainer against lane E's on the same seeds and the same alerts."""
    started = time.perf_counter()
    before = current(subjects, split)
    after = score_subjects(subjects, split)
    elapsed = time.perf_counter() - started
    return {
        "split": split,
        "current": {
            "explainer": EXPLAINER_RESULT_NAME,
            "totals": naming_totals(before).as_dict(),
            "subjects": [item.as_dict() for item in before],
        },
        "lane_e": {
            "explainer": LOOP_EXPLAINER_RESULT_NAME,
            "totals": naming_totals(after).as_dict(),
            "subjects": [item.as_dict() for item in after],
        },
        "runtime_seconds": elapsed,
        "note": (
            "Synthetic diagnosis. The champion atlas-v1-consistency decides every alert; the "
            "explainers only name. Not a claim about a real plant (ADR 0143)."
        ),
    }


def _confidence(split: str) -> dict[str, object]:
    """Raw confidence against the shape-calibrated confidence on the same leads (ADR 0171).

    Development is scored out of fold, one seed at a time. Held-back is scored by the map fitted
    on all twenty development seeds, and nothing is refitted on it.
    """
    started = time.perf_counter()
    if split == "development":
        outcomes = score_shaped("development")
        leads = leave_one_seed_out(outcomes)
        fitted = ShapeCalibrator.fit(outcomes)
    else:
        fitted = ShapeCalibrator.fit(score_shaped("development"))
        outcomes = score_shaped("held-back")
        leads = tuple(
            fitted.calibrate(item)
            for item in outcomes
            if item.contentful and item.correct is not None
        )
    contentful = [item for item in outcomes if item.contentful and item.correct is not None]
    raw_high = [item for item in contentful if item.raw_confidence >= HIGH_BOUND]
    return {
        "split": split,
        "current": {
            "confidence": "raw belief update (ADR 0162)",
            "contentful": len(contentful),
            "right": sum(1 for item in contentful if item.correct),
            "high": len(raw_high),
            "high_right_share": (
                None if not raw_high else sum(1 for i in raw_high if i.correct) / len(raw_high)
            ),
        },
        "lane_e": {
            "confidence": "evidence-shape calibration (ADR 0171)",
            **summarise(leads),
            "fitted_shapes": {"+".join(k) or "(none)": v for k, v in fitted.counts.items()},
        },
        "leads": [
            {
                "seed": lead.outcome.seed,
                "plant_id": lead.outcome.plant_id,
                "scenario": lead.outcome.scenario,
                "lead": lead.outcome.lead,
                "raw": lead.outcome.raw_confidence,
                "shape": list(lead.outcome.shape),
                "calibrated": lead.confidence,
                "lower": lead.lower,
                "n": lead.n,
                "high": lead.high,
                "correct": lead.outcome.correct,
            }
            for lead in leads
        ],
        "runtime_seconds": time.perf_counter() - started,
        "note": (
            "Synthetic diagnosis on lane D's command scenarios. The calibrated number is not "
            "surfaced to a user; a plant needs its own held-out labels first."
        ),
    }


def _root_cause(split: str) -> dict[str, object]:
    """Rank ancestors on one split. The development fit is not reused; nothing is tuned here."""
    started = time.perf_counter()
    totals, per_subject = score_root_causes(split)
    return {
        "result_name": ROOT_CAUSE_RESULT_NAME,
        "split": split,
        "totals": totals.as_dict(),
        "subjects": per_subject,
        "runtime_seconds": time.perf_counter() - started,
        "note": "Synthetic diagnosis. The ranking explains alerts; it never changes them.",
    }


def _totals_only(result: dict[str, object]) -> dict[str, object]:
    """Each comparison's current and lane-E totals, for the terminal."""
    out: dict[str, object] = {}
    for name, value in result.items():
        current = value.get("current") if isinstance(value, dict) else None
        lane = value.get("lane_e") if isinstance(value, dict) else None
        if (
            isinstance(current, dict)
            and isinstance(lane, dict)
            and "totals" in current
            and "totals" in lane
        ):
            out[name] = {
                "current": current["totals"],
                "lane_e": lane["totals"],
            }
    return out


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns a process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workstream", choices=["naming", "naming-guard", "confidence", "root-cause"]
    )
    parser.add_argument("--split", choices=["development", "held-back"], default="development")
    parser.add_argument("--declare", action="store_true")
    arguments = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if arguments.declare:
        declaration: dict[str, object] = {
            "result_name": HELD_BACK_RESULT,
            "command": HELD_BACK_COMMAND,
            "code_sha256": code_sha256(),
            "seeds": "97101-97120",
            "note": "One look. Do not edit a scored file between this declaration and the run.",
        }
        DECLARATION.write_text(json.dumps(declaration, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {DECLARATION}")
        return 0
    if arguments.split == "held-back":
        if HELD_BACK_RESULT_FILE.exists():
            raise SystemExit(f"held-back run refused: {HELD_BACK_RESULT_FILE} already exists")
        require_declaration(DECLARATION, code_sha256())
        result: dict[str, object] = {
            "result_name": HELD_BACK_RESULT,
            "naming_nine": _compare(ALL_NINE, "held-back"),
            "naming_guard": _compare(every_sensor_subjects(), "held-back"),
            "confidence": _confidence("held-back"),
            "root_cause": _root_cause("held-back"),
        }
        HELD_BACK_RESULT_FILE.write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(json.dumps(_totals_only(result), indent=2))
        return 0
    if arguments.workstream == "naming":
        body = _compare(ALL_NINE, "development")
        target = OUT_DIR / "naming-development.json"
    elif arguments.workstream == "naming-guard":
        body = _compare(every_sensor_subjects(), "development")
        target = OUT_DIR / "naming-guard-development.json"
    elif arguments.workstream == "root-cause":
        started = time.perf_counter()
        totals, per_subject = score_root_causes("development")
        body = {
            "result_name": ROOT_CAUSE_RESULT_NAME,
            "split": "development",
            "totals": totals.as_dict(),
            "subjects": per_subject,
            "runtime_seconds": time.perf_counter() - started,
            "note": "Synthetic diagnosis. The ranking explains alerts; it never changes them.",
        }
        target = OUT_DIR / "root-cause-development.json"
        target.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(body["totals"], indent=2))
        return 0
    elif arguments.workstream == "confidence":
        body = _confidence("development")
        target = OUT_DIR / "confidence-development.json"
        target.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"current": body["current"], "lane_e": body["lane_e"]}, indent=2))
        return 0
    else:
        parser.error("give --workstream, --declare or --split held-back")
    target.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(_totals_only({"development": body}), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

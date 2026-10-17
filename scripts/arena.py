#!/usr/bin/env python3
"""The arena's command line: open a task, score a candidate, check a candidate's fence.

Learning engine S3 (ADR 0120). A candidate is a consistency window set in seconds, written as
overrides on the frozen windows, e.g. ``{"lags": [0, 5, 15, 30, 60, 600]}``, or, since ADR 0127,
a detector configuration: ``{"detector": "atlas-plant-map-v1", "map": {"min_gain": 0.02}}``, the
plant-map challenger with overrides on ADR 0123's settings (its caps, stopping rule and horizons
only).
Every score is two slices: the liar slice on `ARENA_LIAR_SEEDS` and HAI 20.07 recall within the
8-per-shift budget, the arena's one real development corpus (ADR 0117). Nothing here reads a
validation or held-out corpus, and nothing writes ``eval_runs/log.jsonl``.

Usage::

    uv run python scripts/arena.py open experiments/arena/<task>/task.json
    uv run python scripts/arena.py score <task> <hypothesis> <candidate.json> --note "why"
    uv run python scripts/arena.py fence <task> <hypothesis> <base-ref>
    uv run python scripts/arena.py payloads <worktree>
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import subprocess
import sys
import tempfile
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Final

import numpy

ROOT: Final = Path(__file__).resolve().parents[1]
for entry in (ROOT, ROOT / "src"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from scripts.fetch_datasets import load_registry  # noqa: E402
from scripts.measure_baseline_table import _read_hai  # noqa: E402

from phos.atlas import consistency  # noqa: E402
from phos.atlas import plant_map_detector as challenger  # noqa: E402
from phos.atlas.consistency_windows import FROZEN_WINDOWS, Windows  # noqa: E402
from phos.atlas.plant_map_model import DEFAULT_SETTINGS, MapSettings  # noqa: E402
from phos.atlas.plant_map_naming import NAMING_RULES  # noqa: E402
from phos.atlas.signal_roles import load_roles  # noqa: E402
from phos.breaking.liar_arena import ARENA_LIAR_SEEDS, score_windows  # noqa: E402
from phos.eval.arena import (  # noqa: E402
    ARENA_ROOT,
    Attempt,
    AttemptLog,
    ResearchTask,
    candidate_sha256,
    forbidden_candidate_paths,
    payloads_present,
)
from phos.eval.baseline_table import FileScore, _score_detector, aggregate_scores  # noqa: E402
from phos.eval.learning_records import LearningRecord, sha256_text  # noqa: E402

logger = logging.getLogger("phos.arena")

RESULTS: Final = ROOT / "eval_runs" / "arena"
#: The scorer is every file whose arithmetic decides a scorecard. Its sha256 is on every attempt.
SCORER_FILES: Final = (
    "scripts/arena.py",
    "src/phos/eval/arena.py",
    "src/phos/breaking/liar_arena.py",
    "src/phos/breaking/liar_diagnosis.py",
    "src/phos/breaking/liar.py",
    "src/phos/atlas/consistency.py",
    "src/phos/atlas/consistency_windows.py",
    "src/phos/atlas/consistency_evidence.py",
    "src/phos/atlas/plant_map_select.py",
    "src/phos/atlas/plant_map_model.py",
    "src/phos/atlas/plant_map_fit.py",
    "src/phos/atlas/plant_map_naming.py",
    "src/phos/atlas/plant_map_detector.py",
    "src/phos/atlas/plant_map_evidence.py",
    "src/phos/atlas/signal_roles.py",
    "src/phos/breaking/declared_roles.py",
    "data/hai-20.07/roles.toml",
)
#: The map settings a detector candidate may override (ADR 0123 §8: caps, stopping rule, horizons).
MAP_OVERRIDES: Final = (
    "max_drivers",
    "max_lags_per_driver",
    "min_gain",
    "horizon_seconds",
    "form_horizon_seconds",
    "naming_rules",
    "calibrator",
)
HAI_20_07: Final = ("train1.csv.gz", "train2.csv.gz"), ("test1.csv.gz", "test2.csv.gz")


def scorer_sha256() -> str:
    """sha256 over the scorer's files, in order."""
    return sha256_text("".join((ROOT / name).read_text(encoding="utf-8") for name in SCORER_FILES))


def windows_from(candidate: dict[str, object]) -> Windows:
    """The frozen windows with the candidate's overrides, in seconds.

    Raises:
        ValueError: If a key is not a `Windows` field, or a value is not a whole number of
            seconds (lags may include 0; every other window is at least 1).
    """
    names = [f.name for f in dataclasses.fields(Windows)]
    unknown = set(candidate) - set(names)
    if unknown:
        raise ValueError(f"not window fields: {sorted(unknown)}")
    merged: dict[str, object] = dataclasses.asdict(FROZEN_WINDOWS) | candidate
    lags = merged["lags"]
    if not isinstance(lags, list | tuple) or not lags:
        raise ValueError("lags must be a non-empty list of whole seconds")
    if not all(isinstance(lag, int) and not isinstance(lag, bool) and lag >= 0 for lag in lags):
        raise ValueError(f"lags must be whole seconds >= 0, got {lags}")

    def seconds(name: str) -> int:
        value = merged[name]
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ValueError(f"{name} must be a whole number of seconds >= 1, got {value!r}")
        return value

    return Windows(
        lags=tuple(int(lag) for lag in lags),
        fit_step=seconds("fit_step"),
        detrend_window=seconds("detrend_window"),
        detrend_step=seconds("detrend_step"),
        feature_gap=seconds("feature_gap"),
        event_window=seconds("event_window"),
        event_span=seconds("event_span"),
        second_alert_min_separation=seconds("second_alert_min_separation"),
    )


def map_settings_from(candidate: dict[str, object]) -> MapSettings | None:
    """A detector candidate's map settings, or ``None`` for a window-set candidate.

    Raises:
        ValueError: If the detector is not the plant map, or an override is not one ADR 0123 §8
            allows, or has the wrong type.
    """
    if "detector" not in candidate:
        return None
    if candidate["detector"] != challenger.RESULT_NAME or set(candidate) - {"detector", "map"}:
        raise ValueError(f"a detector candidate is {{detector: {challenger.RESULT_NAME!r}, map}}")
    overrides = candidate.get("map", {})
    if not isinstance(overrides, dict):
        raise ValueError("map must be an object of setting overrides")
    unknown = set(overrides) - set(MAP_OVERRIDES)
    if unknown:
        raise ValueError(f"not overridable map settings: {sorted(unknown)}")
    fields: dict[str, object] = {}
    for name, value in overrides.items():
        if name == "min_gain":
            if not isinstance(value, int | float) or isinstance(value, bool) or not 0 < value < 1:
                raise ValueError(f"min_gain must be in (0, 1), got {value!r}")
            fields[name] = float(value)
        elif name == "calibrator":
            if value not in ("isotonic", "platt"):
                raise ValueError(f"calibrator must be 'isotonic' or 'platt', got {value!r}")
            fields[name] = value
        elif name == "naming_rules":
            if value not in NAMING_RULES:
                raise ValueError(f"naming_rules must be one of {NAMING_RULES}, got {value!r}")
            fields[name] = value
        elif name == "horizon_seconds":
            if (
                not isinstance(value, list)
                or not value
                or not all(isinstance(v, int) and not isinstance(v, bool) and v >= 1 for v in value)
            ):
                raise ValueError(f"horizon_seconds must be whole seconds >= 1, got {value!r}")
            fields[name] = tuple(value)
        else:
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ValueError(f"{name} must be a whole number >= 1, got {value!r}")
            fields[name] = value
    return dataclasses.replace(DEFAULT_SETTINGS, **fields)  # type: ignore[arg-type]


def score_hai_20_07(
    base: Windows | None,
    data: Path,
    plant_map: MapSettings | None = None,
    arm: challenger.Arm = challenger.Arm.EXTEND,
) -> dict[str, int]:
    """Recall within the budget on HAI 20.07, the frozen candidate's development corpus.

    ``plant_map`` scores `atlas-plant-map-v1` with those settings, roles from the committed role
    file, instead of the window set.
    """
    directory = data / "hai-20.07"
    trains, tests = HAI_20_07
    for name in (*trains, *tests):
        if not (directory / name).is_file():
            raise FileNotFoundError(f"{directory / name} is missing; HAI 20.07 is a required slice")
    windows = FROZEN_WINDOWS if base is None else base
    grids = [_read_hai(directory / name, ";") for name in trains]
    train = [
        consistency.TrainFile(
            values=grid.values, attack=numpy.asarray(grid.attack, dtype=numpy.bool_)
        )
        for grid in grids
    ]
    model = consistency.fit(train, windows) if plant_map is None else None
    detector = None
    if plant_map is not None:
        roles = load_roles(directory / "roles.toml", grids[0].features)
        detector = challenger.fit_detector(
            train, grids[0].features, roles, 1.0, windows, plant_map, arm
        )
    name_of = consistency.RESULT_NAME if detector is None else challenger.RESULT_NAME
    files = []
    for name in tests:
        grid = _read_hai(directory / name, ";")
        stamps = numpy.asarray([s.timestamp() for s in grid.timestamps], dtype=numpy.float64)
        if detector is not None:
            rows, columns, scores = challenger.detect_alerts(detector, grid.values, stamps)
        else:
            assert model is not None
            rows, columns, scores = consistency.budget_alerts(
                consistency.events(consistency.feature_scores(model, grid.values), windows=windows),
                stamps,
                windows,
            )
        cells = [
            (int(r), grid.features[int(c)], float(s))
            for r, c, s in zip(rows, columns, scores, strict=True)
        ]
        files.append(FileScore(name, (_score_detector(name_of, cells, grid),)))
    total = aggregate_scores(files)[0]
    return {"caught": total.caught, "attacks": total.attacks}


def scorecard(
    base: Windows | None, data: Path, cache: Path, plant_map: MapSettings | None = None
) -> dict[str, object]:
    """Both slices for one window set, or for the plant map with ``plant_map`` settings."""
    liar, _diagnoses = score_windows(base, ARENA_LIAR_SEEDS, cache, plant_map=plant_map)
    return {"liar": liar.as_dict(), "hai-20.07": score_hai_20_07(base, data, plant_map)}


def _task_dir(task_id: str) -> Path:
    return RESULTS / task_id


def _load_task(task_id: str) -> ResearchTask:
    return ResearchTask.model_validate_json(
        (_task_dir(task_id) / "task.json").read_text(encoding="utf-8")
    )


def _learning_records() -> list[LearningRecord]:
    records: list[LearningRecord] = []
    for path in sorted((ROOT / "eval_runs" / "learning").glob("*.learning.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            records.append(LearningRecord.model_validate_json(line))
    return records


def open_task(declaration: Path, data: Path, cache: Path) -> int:
    """Validate a task, record it, and score the champion once as its baseline."""
    task = ResearchTask.model_validate_json(declaration.read_text(encoding="utf-8"))
    task.check_motivation(_learning_records())
    target = _task_dir(task.id)
    if (target / "task.json").exists():
        print(f"task {task.id} is already open; a task is never overwritten", file=sys.stderr)
        return 2
    started = time.monotonic()
    champion = scorecard(None, data, cache)
    target.mkdir(parents=True, exist_ok=True)
    (target / "task.json").write_text(task.model_dump_json(indent=2) + "\n", encoding="utf-8")
    payload = {
        "detector": consistency.RESULT_NAME,
        "scorer_sha256": scorer_sha256(),
        "scorecard": champion,
        "compute_seconds": round(time.monotonic() - started, 1),
    }
    (target / "champion.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


def score(
    task_id: str, hypothesis_id: str, candidate_path: Path, note: str, data: Path, cache: Path
) -> int:
    """Score one candidate under one hypothesis, if its budget allows, and log the attempt."""
    task = _load_task(task_id)
    log = AttemptLog(_task_dir(task_id) / "attempts.jsonl", task)
    if log.remaining(hypothesis_id) <= 0:
        print(f"{hypothesis_id} has no runs left", file=sys.stderr)
        return 3
    candidate: dict[str, object] = json.loads(candidate_path.read_text(encoding="utf-8"))
    plant_map = map_settings_from(candidate)
    base = None if plant_map is not None else windows_from(candidate)
    number = log.next_number(hypothesis_id)
    home = ROOT / ARENA_ROOT / task_id / hypothesis_id
    home.mkdir(parents=True, exist_ok=True)
    (home / f"attempt-{number}.json").write_text(
        json.dumps(candidate, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    started = time.monotonic()
    card = scorecard(base, data, cache, plant_map)
    attempt = Attempt(
        task_id=task_id,
        hypothesis_id=hypothesis_id,
        number=number,
        candidate=candidate,
        candidate_sha256=candidate_sha256(candidate),
        scorer="liar-arena+hai-20.07",
        scorer_sha256=scorer_sha256(),
        scorecard=card,
        compute_seconds=round(time.monotonic() - started, 1),
        note=note,
    )
    log.append(attempt)
    print(json.dumps(attempt.model_dump(mode="json"), indent=2))
    return 0


def fence(task_id: str, hypothesis_id: str, base_ref: str) -> int:
    """Exit 1 if the diff since ``base_ref`` touches anything outside the candidate's directory."""
    changed = subprocess.run(
        ["git", "diff", "--name-only", f"{base_ref}...HEAD"],
        capture_output=True,
        text=True,
        check=True,
        cwd=ROOT,
    ).stdout.split()
    forbidden = forbidden_candidate_paths(changed, task_id, hypothesis_id)
    for path in forbidden:
        print(f"outside the candidate's fence: {path}")
    return 1 if forbidden else 0


def payloads(worktree: Path) -> int:
    """Exit 1 if the worktree holds any validation or held-out data file."""
    roles = {entry.name: entry.role for entry in load_registry().datasets}
    found = payloads_present(worktree, roles)
    for path in found:
        print(f"validation or held-out payload present: {path}")
    return 1 if found else 0


def main(argv: Sequence[str] | None = None) -> int:
    """Dispatch a subcommand."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", type=Path, default=ROOT / "data")
    parser.add_argument("--cache", type=Path, default=Path(tempfile.gettempdir()) / "phos-arena")
    sub = parser.add_subparsers(dest="command", required=True)
    opener = sub.add_parser("open")
    opener.add_argument("declaration", type=Path)
    scorer = sub.add_parser("score")
    scorer.add_argument("task")
    scorer.add_argument("hypothesis")
    scorer.add_argument("candidate", type=Path)
    scorer.add_argument("--note", default="")
    fencer = sub.add_parser("fence")
    fencer.add_argument("task")
    fencer.add_argument("hypothesis")
    fencer.add_argument("base")
    checker = sub.add_parser("payloads")
    checker.add_argument("worktree", type=Path)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.ERROR, format="%(levelname)s %(name)s: %(message)s")
    args.cache.mkdir(parents=True, exist_ok=True)
    if args.command == "open":
        return open_task(args.declaration, args.data, args.cache)
    if args.command == "score":
        return score(args.task, args.hypothesis, args.candidate, args.note, args.data, args.cache)
    if args.command == "fence":
        return fence(args.task, args.hypothesis, args.base)
    return payloads(args.worktree)


if __name__ == "__main__":
    raise SystemExit(main())

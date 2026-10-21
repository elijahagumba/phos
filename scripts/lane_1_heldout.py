#!/usr/bin/env python3
"""Lane 1's one held-out score, exactly as ADR 0275 declares it.

Refuses to start unless everything the declaration fixed is still true: the output does not
exist, both code hashes match, and every declared held-out run is present. A refusal opens no
file in the held-out corpus.

Train is the three `normal` runs of `phos-icssim-dev`. Test is the twenty `mixed` runs of
`phos-icssim-heldout`, scored once by `atlas-command-consistency` and by `atlas-v1-consistency`
under the identical budget.

Usage::

    uv run python scripts/lane_1_heldout.py --out eval_runs/build/lane-e/lane1-heldout.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Final

import numpy

ROOT: Final = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from phos.atlas.command_consistency import (  # noqa: E402
    COMPONENTS,
    augmented_scores,
    fit_commands,
)
from phos.atlas.consistency import (  # noqa: E402
    TrainFile,
    budget_alerts,
    events,
    feature_scores,
    fit,
)
from phos.atlas.consistency_windows import windows_for_period  # noqa: E402
from phos.atlas.icssim_adapter import read_run, read_traffic  # noqa: E402

logger = logging.getLogger("lane_1_heldout")

DATA: Final = Path("data")
DEVELOPMENT: Final = DATA / "phos-icssim-dev"
HELD_OUT: Final = DATA / "phos-icssim-heldout"

#: ADR 0275's frozen hashes, raw file bytes, path not mixed in.
PINNED: Final = {
    "src/phos/atlas/command_consistency.py": (
        "87017fcfeaae94790dd8d461d43793a1f87e15a1460e46d963d47a1ae6d0cc94"
    ),
    "src/phos/atlas/icssim_adapter.py": (
        "06de74b3c6dd52b613a0a53fd7318cabcf5818496cc33030c18605e0e9f6669c"
    ),
}

#: ADR 0275's declared seeds.
TRAIN_SEEDS: Final = (96001, 96002, 96003)
TEST_SEEDS: Final = tuple(range(96101, 96121))


def _refuse_unless_ready(out: Path) -> None:
    """Check everything ADR 0275 fixed, before any held-out file is opened."""
    if out.exists():
        raise SystemExit(f"{out} exists: ADR 0275 declared one shot, and it has been taken")
    for relative, expected in PINNED.items():
        digest = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
        if digest != expected:
            raise SystemExit(
                f"{relative} is {digest}, not the ADR 0275 hash {expected}. "
                "The detector changed after it was frozen; the shot is refused."
            )
    missing = [seed for seed in TEST_SEEDS if not (HELD_OUT / f"mixed-{seed}").is_dir()]
    if missing:
        raise SystemExit(f"held-out runs not generated yet: {missing}")
    absent = [seed for seed in TRAIN_SEEDS if not (DEVELOPMENT / f"normal-{seed}").is_dir()]
    if absent:
        raise SystemExit(f"training runs absent: {absent}")


def _caught(rows: Sequence[int], times: numpy.ndarray, start: float, end: float) -> bool:
    return any(start <= float(times[row]) <= end for row in rows)


def main(argv: Sequence[str] | None = None) -> int:
    """Take lane 1's one declared held-out score and write it once."""
    parser = argparse.ArgumentParser(description="Lane 1's one held-out score (ADR 0275).")
    parser.add_argument("--out", type=Path, required=True)
    arguments = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    started = time.monotonic()

    _refuse_unless_ready(arguments.out)

    train: list[TrainFile] = []
    command_train = []
    keys: tuple[str, ...] | None = None
    for seed in TRAIN_SEEDS:
        directory = DEVELOPMENT / f"normal-{seed}"
        run = read_run(directory)
        keys = keys or run.keys
        if run.keys != keys:
            raise SystemExit(f"normal-{seed} column order differs from normal-{TRAIN_SEEDS[0]}")
        train.append(
            TrainFile(values=run.values, attack=numpy.zeros(run.values.shape[0], dtype=numpy.bool_))
        )
        command_train.append((run.values, run.times, read_traffic(directory, writes_only=False)))
    windows = windows_for_period(1.0)
    base = fit(train, windows)
    model = fit_commands(base, tuple(command_train))
    logger.info("trained: writers=%s readers=%s", sorted(model.writers), sorted(model.readers))

    per_class: dict[str, dict[str, int]] = {}
    totals = {
        "frozen": 0,
        "lane1": 0,
        "attacks": 0,
        "benign": 0,
        "benign_frozen": 0,
        "benign_lane1": 0,
    }
    by_component: dict[str, int] = dict.fromkeys(COMPONENTS, 0)

    for seed in TEST_SEEDS:
        directory = HELD_OUT / f"mixed-{seed}"
        run = read_run(directory)
        if run.keys != keys:
            raise SystemExit(f"mixed-{seed} column order differs from the training runs")
        traffic = read_traffic(directory, writes_only=False)
        origin = float(run.times[0])

        frozen_rows, _c, _s = budget_alerts(
            events(feature_scores(base, run.values), windows=windows), run.times, windows=windows
        )
        lane_rows, lane_cols, _s2 = budget_alerts(
            events(augmented_scores(model, run.values, run.times, traffic), windows=windows),
            run.times,
            windows=windows,
        )
        n_signals = run.values.shape[1]

        for item in json.loads((directory / "events.json").read_text()):
            kind = str(item["kind"])
            start, end = origin + float(item["start"]), origin + float(item["end"])
            frozen = _caught(frozen_rows, run.times, start, end)
            lane = _caught(lane_rows, run.times, start, end)
            row = per_class.setdefault(kind, {"frozen": 0, "lane1": 0, "of": 0})
            row["of"] += 1
            row["frozen"] += int(frozen)
            row["lane1"] += int(lane)
            if str(item["label"]) == "attack":
                totals["attacks"] += 1
                totals["frozen"] += int(frozen)
                totals["lane1"] += int(lane)
            else:
                totals["benign"] += 1
                totals["benign_frozen"] += int(frozen)
                totals["benign_lane1"] += int(lane)
            if lane:
                for r, c in zip(lane_rows, lane_cols, strict=True):
                    if start <= float(run.times[r]) <= end and c >= n_signals:
                        by_component[COMPONENTS[c - n_signals]] += 1
        logger.info("mixed-%s: frozen %s alerts, lane1 %s", seed, len(frozen_rows), len(lane_rows))

    frozen_classes = {k for k, v in per_class.items() if v["frozen"] > 0}
    lane_classes = {k for k, v in per_class.items() if v["lane1"] > 0}
    strictly_more = totals["lane1"] > totals["frozen"]
    new_class = sorted(lane_classes - frozen_classes)
    payload = {
        "adr": "0275",
        "command": "uv run python scripts/lane_1_heldout.py --out " + str(arguments.out),
        "pinned": PINNED,
        "train_seeds": list(TRAIN_SEEDS),
        "test_seeds": list(TEST_SEEDS),
        "per_class": per_class,
        "totals": totals,
        "by_component": by_component,
        "strictly_more_attacks": strictly_more,
        "classes_the_frozen_engine_misses_entirely": new_class,
        "lane1_met": bool(strictly_more and new_class),
        "benign_no_worse": totals["benign_lane1"] <= totals["benign_frozen"],
        "corpus": "phos-icssim-heldout, generated by PHOS; diagnosis not proof (R4, ADR 0143)",
        "claim": "attribution on a simulated plant, not the command-against-physics claim",
        "log_jsonl_appended": False,
        "seconds": round(time.monotonic() - started, 1),
    }
    arguments.out.parent.mkdir(parents=True, exist_ok=True)
    arguments.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    logger.info(
        "attacks frozen %s lane1 %s of %s | benign %s -> %s | met=%s new classes=%s",
        totals["frozen"],
        totals["lane1"],
        totals["attacks"],
        totals["benign_frozen"],
        totals["benign_lane1"],
        payload["lane1_met"],
        new_class,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

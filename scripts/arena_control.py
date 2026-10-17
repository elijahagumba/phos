#!/usr/bin/env python3
"""Declare the untargeted control arm: the same failure, the same budget, no diagnosis.

Learning engine S5 (ADR 0121). The brief asks whether failure-driven search beats search that
ignores the diagnosis, under the same compute. This script draws the control arm's 18 candidates
(the targeted task's three hypotheses times six runs) from a declared space with a fixed seed, and
writes them, with the task, before any of them is scored. Each candidate changes one or two window
fields at random: a numeric field is multiplied by one of `FACTORS`; the lags either lose one
non-zero lag or gain one of `EXTRA_LAGS`. The arm may stumble on the targeted fix; that is fair.

Usage::

    uv run python scripts/arena_control.py experiments/arena/water-liar-control
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final

import numpy

ROOT: Final = Path(__file__).resolve().parents[1]
for entry in (ROOT, ROOT / "src"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from phos.atlas.consistency_windows import FROZEN_WINDOWS, Windows  # noqa: E402

SEED: Final = 20261012
RUNS: Final = 18
FACTORS: Final = (0.25, 0.5, 2.0, 4.0, 6.0)
EXTRA_LAGS: Final = (90, 120, 180, 300, 450, 600, 900, 1200, 1800)
FIELDS: Final = tuple(f.name for f in dataclasses.fields(Windows))


def draw(rng: numpy.random.Generator) -> dict[str, object]:
    """One untargeted candidate: one or two fields of the frozen windows, changed at random."""
    count = int(rng.integers(1, 3))
    names = sorted(rng.choice(len(FIELDS), size=count, replace=False).tolist())
    candidate: dict[str, object] = {}
    for index in names:
        name = FIELDS[index]
        if name == "lags":
            lags = list(FROZEN_WINDOWS.lags)
            if rng.random() < 0.5 and len(lags) > 2:
                lags.remove(lags[int(rng.integers(1, len(lags)))])
            else:
                extra = int(rng.choice(EXTRA_LAGS))
                lags = sorted({*lags, extra})
            candidate["lags"] = lags
        else:
            value = getattr(FROZEN_WINDOWS, name)
            factor = float(rng.choice(FACTORS))
            candidate[name] = max(1, round(value * factor))
    return candidate


def candidates() -> list[dict[str, object]]:
    """The arm's 18 candidates, in order. Deterministic."""
    rng = numpy.random.Generator(numpy.random.PCG64(SEED))
    return [draw(rng) for _ in range(RUNS)]


def main(argv: Sequence[str] | None = None) -> int:
    """Write the control task and its candidates; refuse to overwrite either."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("directory", type=Path)
    args = parser.parse_args(argv)
    targeted = json.loads(
        (ROOT / "experiments" / "arena" / "water-liar" / "task.json").read_text(encoding="utf-8")
    )
    task = {
        **targeted,
        "id": "water-liar-control",
        "hypotheses": [
            {
                "id": "untargeted",
                "statement": "No diagnosis: a random change to the window set does as well.",
                "change": "The 18 declared candidates in candidates.json, in order.",
            }
        ],
        "runs_per_hypothesis": RUNS,
        "evaluation_plan": (
            "The control arm for ADR 0121: the same failure, scorer, slices and qualifying rule as "
            "water-liar, 18 runs, candidates drawn before scoring by scripts/arena_control.py "
            f"(seed {SEED}). Compared with water-liar on qualifying candidates, best water passes, "
            "and the red-team verdict of each arm's chosen candidate."
        ),
    }
    args.directory.mkdir(parents=True, exist_ok=True)
    for name, payload in (("task.json", task), ("candidates.json", candidates())):
        path = args.directory / name
        if path.exists():
            print(f"{path} exists; a declaration is never overwritten", file=sys.stderr)
            return 2
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

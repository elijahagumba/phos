#!/usr/bin/env python3
"""Score the walk column on the development walk corpus.

ADR 0301 specified the column. ADR 0313 is the gate that allows it. This command
is not `atlas-daily:day1-walk` and does not replace that report. It appends the
calibrated column to the frozen per-signal scores and passes that matrix through
the unchanged `events` and `budget_alerts`.

Development only. A path whose name contains ``heldout`` is refused.

Usage::

    uv run python scripts/lane_daily_walk.py --corpus data/phos-icssim-dev4-walk
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Final

import numpy
from numpy.typing import NDArray

ROOT: Final = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.lane_e_icssim_baseline import (  # noqa: E402
    RunWindow,
    _events,
    _median,
    _rate,
    attack_directories,
    class_account,
)

from phos.atlas.consistency import (  # noqa: E402
    ALERTS_PER_SHIFT,
    TrainFile,
    budget_alerts,
    events,
    feature_scores,
    fit,
)
from phos.atlas.consistency_windows import Windows, windows_for_period  # noqa: E402
from phos.atlas.icssim_adapter import read_run  # noqa: E402
from phos.atlas.walk_consistency import (  # noqa: E402
    RESULT_NAME,
    augmented_scores,
    count_later,
    fit_walk,
)

logger = logging.getLogger("lane_daily_walk")

_Float64 = NDArray[numpy.float64]


def _alert_times(scores: numpy.ndarray, times: _Float64, windows: Windows) -> tuple[float, ...]:
    rows, _columns, _peaks = budget_alerts(events(scores, windows=windows), times, windows=windows)
    return tuple(float(times[row]) for row in rows)


def main(argv: list[str] | None = None) -> int:
    """Score the walk column and print the account. Held-out paths are refused."""
    parser = argparse.ArgumentParser(description="Walk-column score on the development corpus.")
    parser.add_argument("--corpus", type=Path, required=True)
    arguments = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    corpus = arguments.corpus
    if "heldout" in corpus.name:
        raise SystemExit("this script is development only; the held-out corpus is not opened here")
    normals = sorted(corpus.glob("normal-*"))
    attacks = attack_directories(corpus)
    if not normals or not attacks:
        raise SystemExit(f"{corpus} has {len(normals)} normal and {len(attacks)} attack runs")

    train: list[TrainFile] = []
    matrices: list[_Float64] = []
    keys: tuple[str, ...] | None = None
    period = 1.0
    for directory in normals:
        run = read_run(directory)
        if keys is None:
            keys = run.keys
            period = float(numpy.median(numpy.diff(run.times)))
        elif run.keys != keys:
            raise SystemExit(f"{directory.name} column order differs from {normals[0].name}")
        train.append(
            TrainFile(values=run.values, attack=numpy.zeros(run.values.shape[0], dtype=numpy.bool_))
        )
        matrices.append(run.values)
    windows = windows_for_period(period)
    model = fit(train, windows)
    walk = fit_walk(model, tuple(matrices), keys or ())
    logger.info("%s divisor %.4f budget %s", RESULT_NAME, walk.divisor, ALERTS_PER_SHIFT)

    frozen_runs: list[RunWindow] = []
    new_runs: list[RunWindow] = []
    later = 0
    for directory in attacks:
        run = read_run(directory)
        if run.keys != keys:
            raise SystemExit(f"{directory.name} column order differs from the train runs")
        frozen_at = _alert_times(feature_scores(model, run.values), run.times, model.windows)
        new_at = _alert_times(augmented_scores(walk, run.values), run.times, model.windows)
        labelled = _events(directory, float(run.times[0]))
        duration = float(run.times[-1] - run.times[0])
        frozen_runs.append(RunWindow(duration, labelled, frozen_at, ()))
        new_runs.append(RunWindow(duration, labelled, new_at, ()))
        walks = tuple((item.start, item.end) for item in labelled if item.kind == "subfloor_walk")
        later += count_later(walks, frozen_at, new_at)
        logger.info(
            "%s: frozen %s alerts, walk %s alerts", directory.name, len(frozen_at), len(new_at)
        )

    frozen = class_account(tuple(frozen_runs), "subfloor_walk")
    new = class_account(tuple(new_runs), "subfloor_walk")
    print(f"result: {RESULT_NAME}")
    print(f"budget alerts per shift: {ALERTS_PER_SHIFT}")
    print(f"walk divisor: {walk.divisor:.6f}")
    print(f"walk events: {new.events}")
    print(f"walk misses frozen: {frozen.misses_frozen}")
    print(f"walk misses new: {new.misses_frozen}")
    print(f"walk false alerts frozen: {frozen.false_frozen}")
    print(f"walk false alerts new: {new.false_frozen}")
    print(f"walk duration_s: {new.duration_s:.6f}")
    print(f"walk false alerts per hour frozen: {_rate(frozen.false_frozen, frozen.duration_s):.6f}")
    print(f"walk false alerts per hour new: {_rate(new.false_frozen, new.duration_s):.6f}")
    print(f"walk median delay s frozen: {_median(frozen.delays_frozen)}")
    print(f"walk median delay s new: {_median(new.delays_frozen)}")
    print(f"walk later than champion: {later}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

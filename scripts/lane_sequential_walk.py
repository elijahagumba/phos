#!/usr/bin/env python3
"""Score the sequential column on the development walk corpus, and the order-blind diagnostic.

Q-0001 asks whether the walk miss recorded in ADR 0313 and ADR 0315 is an artefact of thresholding a
per-sample score under a saturated calibration, or a property of the class that no per-sample
comparison can see. This command produces the numbers that separate those.

- ``walk_misses`` is what the sequential column's own alerts miss, through the frozen `events` and
  `budget_alerts` with the budget unchanged. It is the accounting ADR 0313 and ADR 0315 used, so the
  two are comparable.
- ``walk_samples_outside_range`` and ``walk_min_outside_range`` are the order-blind half: how many
  samples inside the walk windows put the walked tag outside the range attack-free training actually
  produced. This reads no order and no alert budget. It asks only whether a per-sample value
  comparison had anything to see.
- ``walk_events`` is the denominator, printed so a reader can see the corpus scored here holds the
  nine walks ADR 0313's report counted, rather than assuming it.

The champion's numbers are **not** recomputed. ADR 0313's `atlas-daily:day1-walk` is spent, and
`scripts/lane_e_icssim_baseline.py` is not run on this corpus. The champion's false-alert rate is
read from the committed record (1.187500 per hour), never re-derived here.

Development only. A path whose name contains ``heldout`` is refused, and
`phos-icssim-heldout4-walk` is not read.

Usage::

    uv run python scripts/lane_sequential_walk.py --corpus data/phos-icssim-dev4-walk
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy
from numpy.typing import NDArray

ROOT: Final = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.lane_e_icssim_baseline import (  # noqa: E402
    Event,
    RunWindow,
    _events,
    _rate,
    attack_directories,
    class_account,
)

from phos.atlas.consistency import (  # noqa: E402
    ALERTS_PER_SHIFT,
    SHIFT_SECONDS,
    budget_alerts,
    events,
)
from phos.atlas.consistency_windows import Windows, windows_for_period  # noqa: E402
from phos.atlas.icssim_adapter import read_run  # noqa: E402
from phos.atlas.sequential_consistency import (  # noqa: E402
    RESULT_NAME,
    SLID_TAG,
    fit_sequential,
    sequential_scores,
)

logger = logging.getLogger("lane_sequential_walk")

_Float64 = NDArray[numpy.float64]

#: ADR 0313's committed champion false-alert rate per hour. A record value, not recomputed.
CHAMPION_FALSE_PER_HOUR: Final = 1.187500

#: ADR 0313's committed denominator: nine `subfloor_walk` events over eight runs.
CHAMPION_WALK_EVENTS: Final = 9


@dataclass(frozen=True)
class Walk:
    """One walk window, and what each statistic made of it."""

    run: str
    start: float
    end: float
    longest_run: int
    samples_outside: int
    caught: bool


def _alert_times(
    scores: NDArray[numpy.float32], times: _Float64, windows: Windows, threshold: float
) -> tuple[float, ...]:
    """Return the budgeted alert times for one scored column, using the frozen budget.

    The threshold is the learned run length, not the frozen `THRESHOLD`. Passing the default would
    let a run of one — a single legitimate setpoint write — open an episode.
    """
    rows, _columns, _peaks = budget_alerts(
        events(scores, threshold=threshold, windows=windows), times, windows=windows
    )
    return tuple(float(times[row]) for row in rows)


def _inside(start: float, end: float, at: float) -> bool:
    """Return whether ``at`` falls inside the window, inclusive of both ends."""
    return start <= at <= end


def _window_bounds(times: _Float64, start: float, end: float) -> tuple[int, int]:
    """Return the first and last sample row whose timestamp lies inside ``[start, end]``."""
    first = int(numpy.searchsorted(times, start, side="left"))
    last = int(numpy.searchsorted(times, end, side="right")) - 1
    return first, last


def _max_alerts_per_shift(alert_times: tuple[float, ...], origin: float) -> int:
    """Return the most budgeted alerts this run placed in any one 8-hour shift."""
    if not alert_times:
        return 0
    counts: dict[int, int] = {}
    for at in alert_times:
        shift = int((at - origin) // SHIFT_SECONDS)
        counts[shift] = counts.get(shift, 0) + 1
    return max(counts.values())


def _walks(
    name: str,
    run_scores: NDArray[numpy.float32],
    times: _Float64,
    labelled: Sequence[Event],
    alerts: tuple[float, ...],
    column: _Float64,
    low: float,
    high: float,
) -> list[Walk]:
    """Return one `Walk` per labelled walk window in this run."""
    found: list[Walk] = []
    for item in labelled:
        if item.kind != "subfloor_walk":
            continue
        first, last = _window_bounds(times, item.start, item.end)
        if last < first:
            logger.warning("%s: walk window [%s, %s] holds no sample", name, item.start, item.end)
            continue
        segment = column[first : last + 1]
        found.append(
            Walk(
                run=name,
                start=item.start,
                end=item.end,
                longest_run=int(run_scores[first : last + 1, 0].max(initial=0.0)),
                samples_outside=int(numpy.count_nonzero((segment < low) | (segment > high))),
                caught=any(_inside(item.start, item.end, at) for at in alerts),
            )
        )
    return found


def main(argv: list[str] | None = None) -> int:
    """Score the sequential column and print the numbers Q-0001's fork needs."""
    parser = argparse.ArgumentParser(description="Sequential-column score on the walk corpus.")
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

    training: list[_Float64] = []
    keys: tuple[str, ...] | None = None
    period = 1.0
    for directory in normals:
        run = read_run(directory)
        if keys is None:
            keys = run.keys
            period = float(numpy.median(numpy.diff(run.times)))
        elif run.keys != keys:
            raise SystemExit(f"{directory.name} column order differs from {normals[0].name}")
        training.append(run.values)
    if keys is None:
        raise SystemExit(f"{corpus} has no readable normal run")

    windows = windows_for_period(period)
    model = fit_sequential(keys, tuple(training))
    threshold = float(model.longest_run)
    column = list(keys).index(SLID_TAG)
    attack_free = numpy.concatenate([values[:, column] for values in training])
    low, high = float(attack_free.min()), float(attack_free.max())
    logger.info("%s: longest attack-free run %s samples", SLID_TAG, model.longest_run)
    logger.info("attack-free range of %s: [%.6f, %.6f]", SLID_TAG, low, high)

    labelled_runs: list[RunWindow] = []
    walks: list[Walk] = []
    max_per_shift = 0
    for directory in attacks:
        run = read_run(directory)
        if run.keys != keys:
            raise SystemExit(f"{directory.name} column order differs from the train runs")
        scores = sequential_scores(model, run.values)
        alerts = _alert_times(scores, run.times, windows, threshold)
        labelled = _events(directory, float(run.times[0]))
        labelled_runs.append(
            RunWindow(
                duration_s=float(run.times[-1] - run.times[0]),
                events=labelled,
                frozen=alerts,
                lane1=(),
            )
        )
        walks.extend(
            _walks(
                directory.name,
                scores,
                run.times,
                labelled,
                alerts,
                run.values[:, column],
                low,
                high,
            )
        )
        max_per_shift = max(max_per_shift, _max_alerts_per_shift(alerts, float(run.times[0])))

    account = class_account(tuple(labelled_runs), "subfloor_walk")
    outside = [walk.samples_outside for walk in walks]
    print(f"result: {RESULT_NAME}")
    print(f"walk events: {account.events}")
    print(f"walk misses sequential: {account.misses_frozen}")
    print(f"walk samples outside range: {sum(outside)}")
    print(f"walk min outside range: {min(outside) if outside else 0}")
    print(f"walk duration_s: {account.duration_s:.6f}")
    print(f"walk false alerts sequential: {account.false_frozen}")
    rate = _rate(account.false_frozen, account.duration_s)
    print(f"walk false alerts per hour sequential: {rate:.6f}")
    print(f"walk false alerts per hour champion committed: {CHAMPION_FALSE_PER_HOUR:.6f}")
    print(f"walk alerts per shift max: {max_per_shift}")
    print(f"walk budget per shift: {ALERTS_PER_SHIFT}")
    print(f"walk denominator committed: {CHAMPION_WALK_EVENTS}")
    print()
    print(f"{'run':<18} {'start':>9} {'end':>9} {'longest':>8} {'outside':>8}  caught")
    for walk in walks:
        print(
            f"{walk.run:<18} {walk.start:9.1f} {walk.end:9.1f} "
            f"{walk.longest_run:8} {walk.samples_outside:8}  {'yes' if walk.caught else 'NO'}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

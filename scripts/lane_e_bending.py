#!/usr/bin/env python3
"""Lane 4 on the ICSSim development corpus: catches and false alarms, beside the frozen engine.

Lane 4's bar has two halves and this script reports both, because a catch gain bought with more
false alarms is not a pass:

* **Catches.** Strictly more attacks caught within the same eight-alerts-a-shift budget.
* **False alarms.** No more per day on attack-free data than the frozen engine.

**The false-alarm half needs care, and this script reports it two ways.** Both engines are fitted on
the corpus's `normal` runs, which are the only attack-free data it has, so counting alerts on those
same runs is **in sample** and flatters both. That number is still the fair head-to-head, because
both engines are flattered identically, and it is reported first. The honest out-of-sample number is
reported beside it: hold one `normal` run out, fit both engines on the rest, count alerts on the
held-out one, and rotate. Where the two disagree, the leave-one-out figure is the one that means
something about a plant.

**Development data only.** No held-out corpus is opened and no result file is written.

Usage::

    uv run python scripts/lane_e_bending.py
    uv run python scripts/lane_e_bending.py --corpus /path/to/phos-icssim-dev2
    uv run python scripts/lane_e_bending.py --knots 0.1,0.25,0.5,0.75,0.9
"""

from __future__ import annotations

import argparse
import collections
import json
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

from phos.atlas.bending_consistency import (  # noqa: E402
    KNOT_QUANTILES,
    bending_scores,
    fit_bending,
)
from phos.atlas.consistency import (  # noqa: E402
    TrainFile,
    budget_alerts,
    events,
    feature_scores,
    fit,
)
from phos.atlas.consistency_windows import windows_for_period  # noqa: E402
from phos.atlas.icssim_adapter import read_run  # noqa: E402

logger = logging.getLogger("lane_e_bending")

_Float64 = NDArray[numpy.float64]

DEFAULT_CORPUS: Final = Path("data/phos-icssim-dev2")
_SECONDS_PER_DAY: Final = 86_400.0


@dataclass(frozen=True)
class Outcome:
    """One labelled event, and whether each engine alerted inside its window."""

    run: str
    kind: str
    label: str
    frozen: bool
    bending: bool


@dataclass(frozen=True)
class Quiet:
    """Alerts each engine raised on one attack-free run, and how long that run was."""

    run: str
    hours: float
    frozen: int
    bending: int


def _alert_times(scores: numpy.ndarray, times: _Float64, windows: object) -> list[float]:
    rows, _c, _s = budget_alerts(
        events(scores, windows=windows),  # type: ignore[arg-type]
        times,
        windows=windows,  # type: ignore[arg-type]
    )
    return [float(times[row]) for row in rows]


def _load(directories: Sequence[Path]) -> tuple[list[TrainFile], tuple[str, ...], float]:
    """Read runs into training files, checking the column order agrees."""
    files: list[TrainFile] = []
    keys: tuple[str, ...] | None = None
    period = 1.0
    for directory in directories:
        run = read_run(directory)
        if keys is None:
            keys = run.keys
            period = float(numpy.median(numpy.diff(run.times)))
        elif run.keys != keys:
            raise SystemExit(f"{directory.name} column order differs from {directories[0].name}")
        files.append(
            TrainFile(values=run.values, attack=numpy.zeros(run.values.shape[0], dtype=numpy.bool_))
        )
    return files, keys or (), period


def _quiet_load(directory: Path, windows: object, frozen: object, bent: object) -> Quiet:
    """Count each engine's budgeted alerts on one attack-free run."""
    run = read_run(directory)
    hours = float(run.times[-1] - run.times[0]) / 3600.0
    f = _alert_times(feature_scores(frozen, run.values), run.times, windows)  # type: ignore[arg-type]
    b = _alert_times(bending_scores(bent, run.values), run.times, windows)  # type: ignore[arg-type]
    return Quiet(run=directory.name, hours=hours, frozen=len(f), bending=len(b))


def _score(
    corpus: Path, quantiles: Sequence[float]
) -> tuple[list[Outcome], list[Quiet], list[Quiet]]:
    normals = sorted(corpus.glob("normal-*"))
    mixeds = sorted(corpus.glob("mixed*"))
    if not normals or not mixeds:
        raise SystemExit(f"{corpus} has {len(normals)} normal and {len(mixeds)} mixed runs")

    train, keys, period = _load(normals)
    windows = windows_for_period(period)
    frozen = fit(train, windows)
    bent = fit_bending(train, windows, quantiles=quantiles)
    logger.info(
        "fitted on %s normal run(s), %s signals, period %.1fs | knots %s per signal",
        len(train),
        len(keys),
        period,
        bent.knots.shape[1],
    )

    outcomes: list[Outcome] = []
    for directory in mixeds:
        run = read_run(directory)
        if run.keys != keys:
            raise SystemExit(f"{directory.name} column order differs from the train runs")
        origin = float(run.times[0])
        f_times = _alert_times(feature_scores(frozen, run.values), run.times, windows)
        b_times = _alert_times(bending_scores(bent, run.values), run.times, windows)
        for item in json.loads((directory / "events.json").read_text()):
            start, end = origin + float(item["start"]), origin + float(item["end"])
            outcomes.append(
                Outcome(
                    run=directory.name,
                    kind=str(item["kind"]),
                    label=str(item["label"]),
                    frozen=any(start <= at <= end for at in f_times),
                    bending=any(start <= at <= end for at in b_times),
                )
            )
        logger.info(
            "%s: frozen %s alerts, lane4 %s alerts", directory.name, len(f_times), len(b_times)
        )

    in_sample = [_quiet_load(d, windows, frozen, bent) for d in normals]

    held_out: list[Quiet] = []
    for index, directory in enumerate(normals):
        rest = [d for i, d in enumerate(normals) if i != index]
        if not rest:
            continue
        sub, _k, sub_period = _load(rest)
        sub_windows = windows_for_period(sub_period)
        held_out.append(
            _quiet_load(
                directory,
                sub_windows,
                fit(sub, sub_windows),
                fit_bending(sub, sub_windows, quantiles=quantiles),
            )
        )
        logger.info("leave-one-out: held out %s, fitted on %s", directory.name, len(rest))

    return outcomes, in_sample, held_out


def _per_day(rows: Sequence[Quiet]) -> tuple[float, float, float]:
    """Total hours, then frozen and bending alerts per day."""
    hours = sum(r.hours for r in rows)
    if hours <= 0:
        return 0.0, 0.0, 0.0
    factor = _SECONDS_PER_DAY / (hours * 3600.0)
    return hours, sum(r.frozen for r in rows) * factor, sum(r.bending for r in rows) * factor


def _report(
    outcomes: Sequence[Outcome],
    in_sample: Sequence[Quiet],
    held_out: Sequence[Quiet],
    quantiles: Sequence[float],
) -> None:
    by_class: dict[tuple[str, str], list[Outcome]] = collections.defaultdict(list)
    for item in outcomes:
        by_class[(item.label, item.kind)].append(item)

    print()
    print(f"knot quantiles {tuple(quantiles)}")
    print()
    print(f"{'label':8} {'kind':20} {'frozen':>7} {'lane4':>6} {'of':>4}")
    for label, kind in sorted(by_class):
        rows = by_class[(label, kind)]
        print(
            f"{label:8} {kind:20} {sum(r.frozen for r in rows):7} "
            f"{sum(r.bending for r in rows):6} {len(rows):4}"
        )

    attacks = [o for o in outcomes if o.label == "attack"]
    benign = [o for o in outcomes if o.label != "attack"]
    frozen_caught = sum(o.frozen for o in attacks)
    bending_caught = sum(o.bending for o in attacks)

    print()
    print(f"attacks caught, frozen: {frozen_caught} of {len(attacks)}")
    print(f"attacks caught, lane 4: {bending_caught} of {len(attacks)}")
    print(f"benign drawing an alert, frozen: {sum(o.frozen for o in benign)} of {len(benign)}")
    print(f"benign drawing an alert, lane 4: {sum(o.bending for o in benign)} of {len(benign)}")

    hours_in, f_in, b_in = _per_day(in_sample)
    hours_out, f_out, b_out = _per_day(held_out)
    print()
    print(f"false alarms/day on attack-free data, IN SAMPLE ({hours_in:.1f}h, fitted on these):")
    print(f"    frozen {f_in:.2f}, lane 4 {b_in:.2f}")
    if held_out:
        print(f"false alarms/day on attack-free data, LEAVE-ONE-OUT ({hours_out:.1f}h, honest):")
        print(f"    frozen {f_out:.2f}, lane 4 {b_out:.2f}")

    strictly_more = bending_caught > frozen_caught
    fp_no_worse_in = b_in <= f_in
    fp_no_worse_out = (b_out <= f_out) if held_out else False
    print()
    print(f"strictly more attacks caught: {strictly_more}")
    print(f"false alarms no worse (in sample): {fp_no_worse_in}")
    print(f"false alarms no worse (leave-one-out): {fp_no_worse_out}")
    print(f"BOTH HALVES MET (on the honest leave-one-out): {strictly_more and fp_no_worse_out}")
    print()
    print("Development only. Simulated plant, so diagnosis not proof (R4, ADR 0143).")


def _quantiles(text: str) -> tuple[float, ...]:
    if not text.strip():
        return ()
    return tuple(float(part) for part in text.split(","))


def main(argv: Sequence[str] | None = None) -> int:
    """Score lane 4 beside the frozen engine on a development corpus."""
    parser = argparse.ArgumentParser(description="Lane 4 on ICSSim development.")
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument(
        "--knots",
        type=_quantiles,
        default=KNOT_QUANTILES,
        help="comma-separated quantiles; empty string reproduces the frozen engine",
    )
    arguments = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if "heldout" in arguments.corpus.name:
        raise SystemExit("this script is development only; the held-out corpus is not opened here")
    outcomes, in_sample, held_out = _score(arguments.corpus, arguments.knots)
    _report(outcomes, in_sample, held_out, arguments.knots)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

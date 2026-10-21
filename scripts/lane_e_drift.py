#!/usr/bin/env python3
"""Lane 3 on the ICSSim development corpus: catches and detection delay, beside the frozen engine.

Lane 3's bar has two halves and this script reports both, because a recall gain bought by alerting
later is not a pass:

* **Catches.** Strictly more attacks caught within the same eight-alerts-a-shift budget.
* **Delay.** Median detection delay no worse.

Delay is reported three ways, and the bar is judged on the paired one. Comparing each engine's
median over its *own* caught set compares different sets of attacks — an engine that catches six
extra hard, late-detected attacks would look worse while being strictly better. So the comparison
that decides the bar is the median over the attacks **both** engines catch, where the two numbers
describe the same events. The own-set medians are printed beside it either way.

**Development data only.** No held-out corpus is opened and no result file is written. The one
held-out score is `scripts/lane_3_heldout.py`, after its declaration is committed.

Usage::

    uv run python scripts/lane_e_drift.py
    uv run python scripts/lane_e_drift.py --corpus /path/to/phos-icssim-dev2
    uv run python scripts/lane_e_drift.py --slack-quantile 0.995
"""

from __future__ import annotations

import argparse
import collections
import json
import logging
import statistics
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

from phos.atlas.consistency import (  # noqa: E402
    TrainFile,
    budget_alerts,
    events,
    feature_scores,
    fit,
)
from phos.atlas.consistency_windows import windows_for_period  # noqa: E402
from phos.atlas.drift_consistency import (  # noqa: E402
    CONTRIBUTION_CAP,
    SLACK_QUANTILE,
    augmented_scores,
    fit_drift,
)
from phos.atlas.icssim_adapter import read_run  # noqa: E402

logger = logging.getLogger("lane_e_drift")

_Float64 = NDArray[numpy.float64]

DEFAULT_CORPUS: Final = Path("data/phos-icssim-dev2")


@dataclass(frozen=True)
class Outcome:
    """One labelled event, and what each engine did with it.

    Attributes:
        run: The run directory's name.
        kind: The event class, for example ``liar_freeze``.
        label: ``attack`` or a benign kind.
        frozen_delay: Seconds from the window's start to the frozen engine's first alert in it,
            or ``None`` if it drew none.
        drift_delay: The same for lane 3.
        by: ``signal`` or ``accumulator``, for the lane 3 alert that landed first.
    """

    run: str
    kind: str
    label: str
    frozen_delay: float | None
    drift_delay: float | None
    by: str


def _first_in_window(
    rows: Sequence[int],
    columns: Sequence[int],
    times: _Float64,
    start: float,
    end: float,
    n_signals: int,
) -> tuple[float | None, str]:
    """The earliest alert inside the window, as a delay from its start, and which half won."""
    inside = [
        (float(times[row]), column)
        for row, column in zip(rows, columns, strict=True)
        if start <= float(times[row]) <= end
    ]
    if not inside:
        return None, "-"
    at, column = min(inside)
    return at - start, "accumulator" if column >= n_signals else "signal"


def _score(corpus: Path, slack_quantile: float, cap: float) -> list[Outcome]:
    """Fit on the corpus's normal runs and score every mixed run with both engines."""
    normals = sorted(corpus.glob("normal-*"))
    mixeds = sorted(corpus.glob("mixed*"))
    if not normals or not mixeds:
        raise SystemExit(f"{corpus} has {len(normals)} normal and {len(mixeds)} mixed runs")

    train: list[TrainFile] = []
    benign: list[_Float64] = []
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
        benign.append(run.values)

    windows = windows_for_period(period)
    model = fit(train, windows)
    drift = fit_drift(model, benign, slack_quantile=slack_quantile, cap=cap)
    logger.info(
        "fitted on %s normal run(s), %s signals, period %.1fs | retention %.6f | cap %.1f",
        len(train),
        len(keys or ()),
        period,
        drift.retention,
        drift.cap,
    )
    logger.info("slack per signal %s", [round(float(v), 4) for v in drift.slack.tolist()])
    logger.info("accumulator divisors %s", [round(float(v), 3) for v in drift.divisors.tolist()])

    outcomes: list[Outcome] = []
    for directory in mixeds:
        run = read_run(directory)
        if run.keys != keys:
            raise SystemExit(f"{directory.name} column order differs from the train runs")
        n_signals = run.values.shape[1]
        origin = float(run.times[0])

        f_rows, f_cols, _fs = budget_alerts(
            events(feature_scores(model, run.values), windows=windows), run.times, windows=windows
        )
        d_rows, d_cols, _ds = budget_alerts(
            events(augmented_scores(drift, run.values), windows=windows), run.times, windows=windows
        )

        for item in json.loads((directory / "events.json").read_text()):
            start = origin + float(item["start"])
            end = origin + float(item["end"])
            frozen_delay, _f = _first_in_window(f_rows, f_cols, run.times, start, end, n_signals)
            drift_delay, by = _first_in_window(d_rows, d_cols, run.times, start, end, n_signals)
            outcomes.append(
                Outcome(
                    run=directory.name,
                    kind=str(item["kind"]),
                    label=str(item["label"]),
                    frozen_delay=frozen_delay,
                    drift_delay=drift_delay,
                    by=by,
                )
            )
        accumulator_alerts = sum(1 for c in d_cols if c >= n_signals)
        logger.info(
            "%s: frozen %s alerts, lane3 %s alerts (%s from accumulator columns)",
            directory.name,
            len(f_rows),
            len(d_rows),
            accumulator_alerts,
        )
    return outcomes


def _median(values: Sequence[float]) -> float | None:
    return statistics.median(values) if values else None


def _show(value: float | None) -> str:
    return "-" if value is None else f"{value:.0f}"


def _report(outcomes: Sequence[Outcome], slack_quantile: float, cap: float) -> None:
    """Print the per-class tally, then both halves of the bar."""
    by_class: dict[tuple[str, str], list[Outcome]] = collections.defaultdict(list)
    for item in outcomes:
        by_class[(item.label, item.kind)].append(item)

    print()
    print(f"slack quantile {slack_quantile}, contribution cap {cap}")
    print()
    print(f"{'label':8} {'kind':20} {'frozen':>7} {'lane3':>6} {'of':>4}  won by")
    for label, kind in sorted(by_class):
        rows = by_class[(label, kind)]
        won = sorted({r.by for r in rows if r.drift_delay is not None} - {"-"})
        print(
            f"{label:8} {kind:20} "
            f"{sum(r.frozen_delay is not None for r in rows):7} "
            f"{sum(r.drift_delay is not None for r in rows):6} "
            f"{len(rows):4}  {','.join(won)}"
        )

    attacks = [item for item in outcomes if item.label == "attack"]
    benign = [item for item in outcomes if item.label != "attack"]
    frozen_caught = sum(a.frozen_delay is not None for a in attacks)
    drift_caught = sum(a.drift_delay is not None for a in attacks)

    print()
    print(f"attacks caught, frozen: {frozen_caught} of {len(attacks)}")
    print(f"attacks caught, lane 3: {drift_caught} of {len(attacks)}")
    print(f"benign drawing an alert, frozen: {sum(b.frozen_delay is not None for b in benign)}")
    print(f"benign drawing an alert, lane 3: {sum(b.drift_delay is not None for b in benign)}")

    both = [a for a in attacks if a.frozen_delay is not None and a.drift_delay is not None]
    paired_frozen = _median([a.frozen_delay for a in both if a.frozen_delay is not None])
    paired_drift = _median([a.drift_delay for a in both if a.drift_delay is not None])
    own_frozen = _median([a.frozen_delay for a in attacks if a.frozen_delay is not None])
    own_drift = _median([a.drift_delay for a in attacks if a.drift_delay is not None])

    print()
    print(
        f"median delay, the {len(both)} attacks both catch:  "
        f"frozen {_show(paired_frozen)}s, lane 3 {_show(paired_drift)}s"
    )
    print(
        f"median delay, each engine's own caught set:        "
        f"frozen {_show(own_frozen)}s, lane 3 {_show(own_drift)}s"
    )

    strictly_more = drift_caught > frozen_caught
    delay_no_worse = (
        paired_frozen is not None and paired_drift is not None and paired_drift <= paired_frozen
    )
    print()
    print(f"strictly more attacks caught: {strictly_more}")
    print(f"median delay no worse (paired): {delay_no_worse}")
    print(f"BOTH HALVES MET: {strictly_more and delay_no_worse}")
    print()
    print("Development only. Simulated plant, so diagnosis not proof (R4, ADR 0143).")


def main(argv: Sequence[str] | None = None) -> int:
    """Score lane 3 beside the frozen engine on a development corpus."""
    parser = argparse.ArgumentParser(description="Lane 3 on ICSSim development.")
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--slack-quantile", type=float, default=SLACK_QUANTILE)
    parser.add_argument("--cap", type=float, default=CONTRIBUTION_CAP)
    arguments = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if "heldout" in arguments.corpus.name:
        raise SystemExit("this script is development only; the held-out corpus is not opened here")
    _report(
        _score(arguments.corpus, arguments.slack_quantile, arguments.cap),
        arguments.slack_quantile,
        arguments.cap,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

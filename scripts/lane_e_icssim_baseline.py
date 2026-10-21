#!/usr/bin/env python3
"""What the frozen engine catches on the ICSSim development corpus, by attack class.

This is the baseline every lane of ADR 0273 is measured against, and it is not a lane. It scores
`atlas-v1-consistency` exactly as it stands — nothing is retuned, nothing is added — on the
development runs only, and reports per attack class whether an alert landed inside the attack's
own window.

Train is the three `normal` runs, which carry operator activity and maintenance and no attack.
Test is the ten `mixed` runs, each carrying eight events of which six are attacks.

**Development data only.** `phos-icssim-heldout` is not read, and no result file is written.

Usage::

    uv run python scripts/lane_e_icssim_baseline.py
    uv run python scripts/lane_e_icssim_baseline.py --corpus /path/to/phos-icssim-dev
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

from phos.atlas.breadth_consistency import (  # noqa: E402
    BreadthModel,
    calibrate_breadth,
)
from phos.atlas.breadth_consistency import augmented_scores as breadth_scores  # noqa: E402
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
from phos.atlas.icssim_adapter import Command, read_run, read_traffic  # noqa: E402

logger = logging.getLogger("lane_e_baseline")

_Float64 = NDArray[numpy.float64]

DEFAULT_CORPUS: Final = Path("data/phos-icssim-dev")


@dataclass(frozen=True)
class Event:
    """One labelled event in a run."""

    kind: str
    label: str
    start: float
    end: float


@dataclass(frozen=True)
class Outcome:
    """Whether each detector's alert landed inside one event's window."""

    run: str
    kind: str
    label: str
    caught: bool
    lane1: bool
    lane2: bool
    by: str


def _events(directory: Path, origin: float) -> tuple[Event, ...]:
    """Read ``events.json``, whose times are seconds from the run's start."""
    payload = json.loads((directory / "events.json").read_text())
    return tuple(
        Event(
            kind=str(item["kind"]),
            label=str(item["label"]),
            start=origin + float(item["start"]),
            end=origin + float(item["end"]),
        )
        for item in payload
    )


def _score(corpus: Path) -> list[Outcome]:
    normals = sorted(corpus.glob("normal-*"))
    mixeds = sorted(corpus.glob("mixed*"))
    if not normals or not mixeds:
        raise SystemExit(f"{corpus} has {len(normals)} normal and {len(mixeds)} mixed runs")

    train: list[TrainFile] = []
    command_train: list[tuple[_Float64, _Float64, tuple[Command, ...]]] = []
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
        command_train.append((run.values, run.times, read_traffic(directory, writes_only=False)))
    windows = windows_for_period(period)
    model = fit(train, windows)
    logger.info(
        "fitted on %s normal run(s), %s rows, %s signals, sample period %.1fs",
        len(train),
        sum(item.values.shape[0] for item in train),
        len(keys or ()),
        period,
    )

    breadth = BreadthModel(
        base=model,
        divisor=calibrate_breadth(
            model, numpy.concatenate([f.values for f in train]), windows.feature_gap
        ),
    )
    logger.info("breadth divisor %.4f", breadth.divisor)
    commands_model = fit_commands(model, tuple(command_train))
    logger.info(
        "command path: writers=%s readers=%s divisors=%s",
        sorted(commands_model.writers),
        sorted(commands_model.readers),
        tuple(round(d, 3) for d in commands_model.divisors),
    )

    outcomes: list[Outcome] = []
    for directory in mixeds:
        run = read_run(directory)
        if run.keys != keys:
            raise SystemExit(f"{directory.name} column order differs from the train runs")
        rows, _columns, _scores = budget_alerts(
            events(feature_scores(model, run.values), windows=model.windows),
            run.times,
            windows=model.windows,
        )
        alert_times = [float(run.times[row]) for row in rows]

        traffic = read_traffic(directory, writes_only=False)
        lane1 = augmented_scores(commands_model, run.values, run.times, traffic)
        l_rows, l_cols, _ = budget_alerts(
            events(lane1, windows=model.windows), run.times, windows=model.windows
        )
        n_signals = run.values.shape[1]
        lane1_alerts = [
            (float(run.times[r]), COMPONENTS[c - n_signals] if c >= n_signals else "signal")
            for r, c in zip(l_rows, l_cols, strict=True)
        ]

        b_rows, _bc, _bs = budget_alerts(
            events(breadth_scores(breadth, run.values), windows=model.windows),
            run.times,
            windows=model.windows,
        )
        breadth_times = [float(run.times[r]) for r in b_rows]

        for event in _events(directory, float(run.times[0])):
            caught = any(event.start <= at <= event.end for at in alert_times)
            l2 = any(event.start <= at <= event.end for at in breadth_times)
            hits = [why for at, why in lane1_alerts if event.start <= at <= event.end]
            outcomes.append(
                Outcome(
                    directory.name,
                    event.kind,
                    event.label,
                    caught,
                    bool(hits),
                    l2,
                    ",".join(sorted(set(hits))) or "-",
                )
            )
        logger.info("%s: frozen %s alerts, lane1 %s alerts", directory.name, len(rows), len(l_rows))
    return outcomes


def _report(outcomes: Sequence[Outcome]) -> None:
    by_kind: dict[tuple[str, str], list[Outcome]] = collections.defaultdict(list)
    for item in outcomes:
        by_kind[(item.label, item.kind)].append(item)

    print()
    print(
        f"{'label':8} {'kind':20} {'frozen':>7} {'lane1':>6} {'lane2':>6} {'of':>4}  what caught it"
    )
    for label, kind in sorted(by_kind):
        rows = by_kind[(label, kind)]
        why = sorted({r.by for r in rows if r.lane1} - {"-"})
        print(
            f"{label:8} {kind:20} {sum(r.caught for r in rows):7} "
            f"{sum(r.lane1 for r in rows):6} {sum(r.lane2 for r in rows):6} "
            f"{len(rows):4}  {','.join(why)}"
        )

    attacks = [item for item in outcomes if item.label == "attack"]
    benign = [item for item in outcomes if item.label != "attack"]
    print()
    print(f"attacks caught, frozen: {sum(a.caught for a in attacks)} of {len(attacks)}")
    print(f"attacks caught, lane 1: {sum(a.lane1 for a in attacks)} of {len(attacks)}")
    print(f"attacks caught, lane 2: {sum(a.lane2 for a in attacks)} of {len(attacks)}")
    print(f"benign drawing an alert, frozen: {sum(b.caught for b in benign)} of {len(benign)}")
    print(f"benign drawing an alert, lane 1: {sum(b.lane1 for b in benign)} of {len(benign)}")
    print(f"benign drawing an alert, lane 2: {sum(b.lane2 for b in benign)} of {len(benign)}")
    still = sorted({a.kind for a in attacks} - {a.kind for a in attacks if a.lane1})
    if still:
        print(f"classes lane 1 still never catches: {', '.join(still)}")


def main(argv: Sequence[str] | None = None) -> int:
    """Score the frozen engine on the development corpus and print the tally."""
    parser = argparse.ArgumentParser(description="Frozen-engine baseline on ICSSim development.")
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    arguments = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if "heldout" in arguments.corpus.name:
        raise SystemExit("this script is development only; the held-out corpus is not opened here")
    _report(_score(arguments.corpus))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

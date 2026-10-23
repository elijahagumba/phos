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


@dataclass(frozen=True)
class RunWindow:
    """One test run's budgeted alerts and the labelled windows they are judged against."""

    duration_s: float
    events: tuple[Event, ...]
    frozen: tuple[float, ...]
    lane1: tuple[float, ...]


@dataclass(frozen=True)
class ClassAccount:
    """ADR 0301's denominator for one attack class, taken from the budgeted alerts."""

    kind: str
    events: int
    misses_frozen: int
    misses_lane1: int
    false_frozen: int
    false_lane1: int
    duration_s: float
    champion: str
    delays_frozen: tuple[float, ...]
    delays_lane1: tuple[float, ...]

    @property
    def misses_champion(self) -> int:
        """The smaller miss count. A tie is resolved by `champion`, not by this number."""
        return min(self.misses_frozen, self.misses_lane1)


def _inside(event: Event, at: float) -> bool:
    """Return whether ``at`` falls inside the event, inclusive of both ends."""
    return event.start <= at <= event.end


def _outside(alerts: Sequence[float], events: Sequence[Event]) -> int:
    """Budgeted alerts that fall in none of ``events``."""
    return sum(1 for at in alerts if not any(_inside(event, at) for event in events))


def _delays(events: Sequence[Event], alerts: Sequence[float]) -> tuple[float, ...]:
    """Earliest in-window alert minus the event start, for events that were caught."""
    found: list[float] = []
    for event in events:
        hits = [at for at in alerts if _inside(event, at)]
        if hits:
            found.append(min(hits) - event.start)
    return tuple(found)


def _champion(miss_frozen: int, miss_lane1: int, false_frozen: int, false_lane1: int) -> str:
    """Name the champion. Tied misses keep the lower false-alert count; a full tie keeps frozen."""
    if miss_frozen < miss_lane1 or (miss_frozen == miss_lane1 and false_frozen <= false_lane1):
        return "frozen"
    return "lane1"


def class_account(runs: Sequence[RunWindow], kind: str) -> ClassAccount:
    """Count misses, false alerts, and delays for ``kind`` across ``runs``.

    A miss is an event of ``kind`` with no budgeted alert inside its window. A false alert
    is a budgeted alert outside every window of ``kind`` on that same run. The two detectors
    share ``duration_s``, so the lower false-alert count is the lower rate.

    Args:
        runs: The test runs, and only those. Training runs are not included.
        kind: The attack class the day named.

    Returns:
        The account. ``events`` is 0 when the class is absent.
    """
    targets: list[Event] = []
    delays_frozen: list[float] = []
    delays_lane1: list[float] = []
    false_frozen = 0
    false_lane1 = 0
    duration_s = 0.0
    for run in runs:
        kind_events = tuple(event for event in run.events if event.kind == kind)
        targets.extend(kind_events)
        delays_frozen.extend(_delays(kind_events, run.frozen))
        delays_lane1.extend(_delays(kind_events, run.lane1))
        false_frozen += _outside(run.frozen, kind_events)
        false_lane1 += _outside(run.lane1, kind_events)
        duration_s += run.duration_s
    misses_frozen = len(targets) - len(delays_frozen)
    misses_lane1 = len(targets) - len(delays_lane1)
    return ClassAccount(
        kind=kind,
        events=len(targets),
        misses_frozen=misses_frozen,
        misses_lane1=misses_lane1,
        false_frozen=false_frozen,
        false_lane1=false_lane1,
        duration_s=duration_s,
        champion=_champion(misses_frozen, misses_lane1, false_frozen, false_lane1),
        delays_frozen=tuple(delays_frozen),
        delays_lane1=tuple(delays_lane1),
    )


def _rate(count: int, duration_s: float) -> float:
    """False alerts per operating hour. ``duration_s`` is the summed test-run span."""
    if duration_s <= 0.0:
        raise ValueError(f"duration_s must be positive, got {duration_s}")
    return count / (duration_s / 3600.0)


def _median(delays: Sequence[float]) -> str:
    """The median delay in seconds, or ``none`` when the detector caught nothing."""
    if not delays:
        return "none"
    return f"{statistics.median(delays):.6f}"


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


def attack_directories(corpus: Path) -> list[Path]:
    """Return the development attack runs this scorer may open.

    `mixed*` is the older scenario. ADR 0301's day-1 runs are `in_range-*`.
    The walk runs are `subfloor-*`. Training directories are not included.

    Args:
        corpus: A development corpus directory. A held-out path is refused by `main`.

    Returns:
        Matching run directories, sorted by name.
    """
    return sorted(
        [
            *corpus.glob("mixed*"),
            *corpus.glob("in_range-*"),
            *corpus.glob("subfloor-*"),
        ]
    )


def _score(corpus: Path) -> tuple[list[Outcome], tuple[RunWindow, ...]]:
    normals = sorted(corpus.glob("normal-*"))
    mixeds = attack_directories(corpus)
    if not normals or not mixeds:
        raise SystemExit(f"{corpus} has {len(normals)} normal and {len(mixeds)} attack runs")

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
    windows: list[RunWindow] = []
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

        labelled = _events(directory, float(run.times[0]))
        for event in labelled:
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
        windows.append(
            RunWindow(
                duration_s=float(run.times[-1] - run.times[0]),
                events=labelled,
                frozen=tuple(alert_times),
                lane1=tuple(at for at, _why in lane1_alerts),
            )
        )
    return outcomes, tuple(windows)


def _print_account(account: ClassAccount) -> None:
    """Print ADR 0301's denominator. The rate is false alerts divided by operating hours."""
    print(f"day1 {account.kind} events: {account.events}")
    print(f"day1 {account.kind} misses frozen: {account.misses_frozen}")
    print(f"day1 {account.kind} misses lane1: {account.misses_lane1}")
    print(f"day1 M_champion: {account.misses_champion} {account.champion}")
    print(f"day1 false alerts frozen: {account.false_frozen}")
    print(f"day1 false alerts lane1: {account.false_lane1}")
    print(f"day1 duration_s: {account.duration_s:.6f}")
    frozen_rate = _rate(account.false_frozen, account.duration_s)
    lane1_rate = _rate(account.false_lane1, account.duration_s)
    print(f"day1 false alerts per hour frozen: {frozen_rate:.6f}")
    print(f"day1 false alerts per hour lane1: {lane1_rate:.6f}")
    print(f"day1 median delay s frozen: {_median(account.delays_frozen)}")
    print(f"day1 median delay s lane1: {_median(account.delays_lane1)}")


def _report(outcomes: Sequence[Outcome], windows: Sequence[RunWindow]) -> None:
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
    for kind in ("in_range_command", "subfloor_walk"):
        if any(event.kind == kind for run in windows for event in run.events):
            print()
            _print_account(class_account(windows, kind))


def main(argv: Sequence[str] | None = None) -> int:
    """Score the frozen engine on the development corpus and print the tally."""
    parser = argparse.ArgumentParser(description="Frozen-engine baseline on ICSSim development.")
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    arguments = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if "heldout" in arguments.corpus.name:
        raise SystemExit("this script is development only; the held-out corpus is not opened here")
    _report(*_score(arguments.corpus))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Half A of ADR 0397 on the ICSSim development corpus: is the delay failure the statistic's?

ADR 0286 recorded that lane 3's accumulator catches **53 of 70** attacks against the frozen
engine's 32, loses none, and is refused anyway because its median detection delay is worse at every
setting of its own cap. It also recorded the cause as the frozen **placement rule**: a saturated
accumulator column becomes its group's ``best``, pins ``level`` at ``ONSET_LEVEL``, and disqualifies
a weak member episode from placing its own earlier alert. ADR 0398 declared the alternative rule
(``phos.atlas.placement_consistency``) and froze four bars before anything ran.

This script prints three columns from **one** fit, so the only thing that differs between the last
two is where the alert is placed:

* **frozen** — `phos.atlas.consistency.detect`'s scores and events, unchanged.
* **lane 3** — `phos.atlas.drift_consistency.augmented_scores`, through the unchanged `events`.
* **placed** — the same augmented matrix, through `earliest_crossing_events` (ADR 0398).

The four bars, as ADR 0397 and ADR 0398 froze them:

1. Attacks caught within eight alerts a shift: **strictly more than 32 of 70**.
2. **No attack the frozen engine catches is lost** — the paired set may not shrink below 32.
3. Median detection delay over the paired set **no worse than 1 s**, under **both** the paired and
   the own-set readings. Both must hold.
4. Benign events drawing an alert: **no higher than 5 of 20**.

**Development data only.** No held-out corpus is opened, no red-tier corpus is read, and no result
file is written: this prints, and the report is written from its stdout so the run cannot append
`eval_runs/log.jsonl`. Nothing here is a detection claim; the plant is simulated, so R4 and ADR 0143
make it diagnosis and not proof.

Usage::

    uv run python scripts/lane_e_placement.py --corpus data/phos-icssim-dev2
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
from phos.atlas.placement_consistency import (  # noqa: E402
    RESULT_NAME,
    earliest_crossing_events,
)

logger = logging.getLogger("lane_e_placement")

_Float64 = NDArray[numpy.float64]

DEFAULT_CORPUS: Final = Path("data/phos-icssim-dev2")


@dataclass(frozen=True)
class Bars:
    """The four halves ADR 0397 froze, repeated in ADR 0398 and not moved here.

    Attributes:
        floor_catches: The frozen engine's catch count, which bar one must strictly exceed.
        ceiling_paired_delay: The frozen engine's paired median delay, in seconds, which bar three
            must not exceed.
        ceiling_benign: The frozen engine's benign count, which bar four must not exceed.
        total_attacks: How many labelled attacks the corpus holds.
        total_benign: How many labelled benign events it holds.
    """

    floor_catches: int = 32
    ceiling_paired_delay: float = 1.0
    ceiling_benign: int = 5
    total_attacks: int = 70
    total_benign: int = 20


BARS: Final = Bars()


@dataclass(frozen=True)
class Outcome:
    """One labelled event, and what each of the three engines did with it.

    Attributes:
        run: The run directory's name.
        kind: The event class, for example ``liar_freeze``.
        label: ``attack`` or a benign kind.
        frozen_delay: Seconds from the window's start to the frozen engine's first alert inside it,
            or ``None`` if the window drew no alert.
        lane3_delay: The same for lane 3 through the unchanged `events`.
        placed_delay: The same for lane 3's matrix through the earliest-crossing rule.
    """

    run: str
    kind: str
    label: str
    frozen_delay: float | None
    lane3_delay: float | None
    placed_delay: float | None


@dataclass(frozen=True)
class Tally:
    """How many of one class each engine caught."""

    frozen: int
    lane3: int
    placed: int
    total: int


@dataclass(frozen=True)
class Reading:
    """The whole measurement, in the form the four bars are judged on.

    Attributes:
        by_class: ``(label, kind)`` to `Tally`, for the per-class table.
        frozen_caught: Attacks the frozen engine caught.
        lane3_caught: Attacks lane 3 caught through the unchanged `events`.
        placed_caught: Attacks the earliest-crossing rule caught.
        frozen_benign: Benign events the frozen engine alerted on.
        placed_benign: Benign events the earliest-crossing rule alerted on.
        paired_n: Attacks both the frozen engine and the placed rule caught.
        paired_frozen: Median delay over that paired set, frozen engine.
        paired_placed: Median delay over that paired set, placed rule.
        own_frozen: Median delay over the frozen engine's own caught set.
        own_placed: Median delay over the placed rule's own caught set.
        paired_n_lane3: Attacks both the frozen engine and lane 3 caught.
        paired_lane3: Median delay over that set for lane 3, the figure ADR 0286 recorded.
        own_lane3: Median delay over lane 3's own caught set, likewise.
        lane3_benign: Benign events lane 3 alerted on.
    """

    by_class: dict[tuple[str, str], Tally]
    frozen_caught: int
    lane3_caught: int
    placed_caught: int
    frozen_benign: int
    placed_benign: int
    lane3_benign: int
    paired_n: int
    paired_frozen: float | None
    paired_placed: float | None
    own_frozen: float | None
    own_placed: float | None
    paired_n_lane3: int
    paired_lane3: float | None
    own_lane3: float | None


@dataclass(frozen=True)
class Verdict:
    """Each of the four halves, and whether all four held.

    Attributes:
        strictly_more: Bar one. Strictly more attacks than the frozen engine catches.
        nothing_lost: Bar two. The paired set is no smaller than the frozen catch count.
        paired_delay_ok: Bar three, first definition.
        own_delay_ok: Bar three, second definition.
        benign_ok: Bar four.
        kept: All four together.
    """

    strictly_more: bool
    nothing_lost: bool
    paired_delay_ok: bool
    own_delay_ok: bool
    benign_ok: bool

    @property
    def kept(self) -> bool:
        """Whether all four halves held. A partial win is a refusal."""
        return (
            self.strictly_more
            and self.nothing_lost
            and self.paired_delay_ok
            and self.own_delay_ok
            and self.benign_ok
        )


def _median(values: Sequence[float]) -> float | None:
    """The median of the values, or ``None`` for an empty set."""
    return statistics.median(values) if values else None


def _first_in_window(
    rows: Sequence[int],
    times: _Float64,
    start: float,
    end: float,
) -> float | None:
    """The earliest alert inside the window, as a delay from its start, or ``None``.

    The alert's column is not read here: every engine's budgeted alert counts as a catch when it
    lands inside the window, which is how `scripts/lane_e_drift.py` measured it and how ADR 0286
    recorded it. Which column placed the alert is printed by the per-class table's engine column.
    """
    inside = [float(times[row]) - start for row in rows if start <= float(times[row]) <= end]
    return min(inside) if inside else None


def summarise(outcomes: Sequence[Outcome]) -> Reading:
    """Reduce the per-event outcomes to the numbers the four bars are read from.

    Every count is derived from the outcomes themselves, so there is one source of truth and no
    caller can hand in a catch count that disagrees with the per-event table.

    Args:
        outcomes: One `Outcome` per labelled event.

    Returns:
        The `Reading` the report prints and `judges` decides.
    """
    by_class: dict[tuple[str, str], list[Outcome]] = collections.defaultdict(list)
    for item in outcomes:
        by_class[(item.label, item.kind)].append(item)

    tally = {
        key: Tally(
            frozen=sum(item.frozen_delay is not None for item in rows),
            lane3=sum(item.lane3_delay is not None for item in rows),
            placed=sum(item.placed_delay is not None for item in rows),
            total=len(rows),
        )
        for key, rows in by_class.items()
    }

    attacks = [item for item in outcomes if item.label == "attack"]
    benign = [item for item in outcomes if item.label != "attack"]

    paired = [a for a in attacks if a.frozen_delay is not None and a.placed_delay is not None]
    paired_lane3 = [a for a in attacks if a.frozen_delay is not None and a.lane3_delay is not None]

    return Reading(
        by_class=dict(tally),
        frozen_caught=sum(a.frozen_delay is not None for a in attacks),
        lane3_caught=sum(a.lane3_delay is not None for a in attacks),
        placed_caught=sum(a.placed_delay is not None for a in attacks),
        frozen_benign=sum(b.frozen_delay is not None for b in benign),
        placed_benign=sum(b.placed_delay is not None for b in benign),
        lane3_benign=sum(b.lane3_delay is not None for b in benign),
        paired_n=len(paired),
        paired_frozen=_median([a.frozen_delay for a in paired if a.frozen_delay is not None]),
        paired_placed=_median([a.placed_delay for a in paired if a.placed_delay is not None]),
        own_frozen=_median([a.frozen_delay for a in attacks if a.frozen_delay is not None]),
        own_placed=_median([a.placed_delay for a in attacks if a.placed_delay is not None]),
        paired_n_lane3=len(paired_lane3),
        paired_lane3=_median([a.lane3_delay for a in paired_lane3 if a.lane3_delay is not None]),
        own_lane3=_median([a.lane3_delay for a in attacks if a.lane3_delay is not None]),
    )


def judges(reading: Reading) -> Verdict:
    """Judge the four halves as ADR 0397 and ADR 0398 froze them, and no more leniently.

    Args:
        reading: The measurement.

    Returns:
        Each half, and whether all four held.
    """
    return Verdict(
        strictly_more=reading.placed_caught > BARS.floor_catches,
        nothing_lost=reading.paired_n >= reading.frozen_caught,
        paired_delay_ok=(
            reading.paired_frozen is not None
            and reading.paired_placed is not None
            and reading.paired_placed <= reading.paired_frozen
        ),
        own_delay_ok=(
            reading.own_frozen is not None
            and reading.own_placed is not None
            and reading.own_placed <= reading.own_frozen
        ),
        benign_ok=reading.placed_benign <= BARS.ceiling_benign,
    )


def _score(corpus: Path) -> list[Outcome]:
    """Fit on the corpus's normal runs and score every mixed run with all three engines."""
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
    drift = fit_drift(model, benign, slack_quantile=SLACK_QUANTILE, cap=CONTRIBUTION_CAP)
    logger.info(
        "fitted on %d normal run(s), %d signals, period %.1fs | slack quantile %.3f | cap %.1f",
        len(train),
        len(keys or ()),
        period,
        SLACK_QUANTILE,
        drift.cap,
    )
    logger.info("result name %s", RESULT_NAME)

    outcomes: list[Outcome] = []
    for directory in mixeds:
        run = read_run(directory)
        if run.keys != keys:
            raise SystemExit(f"{directory.name} column order differs from the train runs")

        plain = feature_scores(model, run.values)
        augmented = augmented_scores(drift, run.values)

        f_rows, _f_cols, _ = budget_alerts(
            events(plain, windows=windows), run.times, windows=windows
        )
        l_rows, _l_cols, _ = budget_alerts(
            events(augmented, windows=windows), run.times, windows=windows
        )
        p_rows, _p_cols, _ = budget_alerts(
            earliest_crossing_events(augmented, windows=windows), run.times, windows=windows
        )

        for item in json.loads((directory / "events.json").read_text()):
            origin = float(run.times[0])
            start = origin + float(item["start"])
            end = origin + float(item["end"])
            outcome = Outcome(
                run=directory.name,
                kind=str(item["kind"]),
                label=str(item["label"]),
                frozen_delay=_first_in_window(f_rows, run.times, start, end),
                lane3_delay=_first_in_window(l_rows, run.times, start, end),
                placed_delay=_first_in_window(p_rows, run.times, start, end),
            )
            outcomes.append(outcome)

        logger.info(
            "%s: frozen %d alerts, lane3 %d, placed %d",
            directory.name,
            len(f_rows),
            len(l_rows),
            len(p_rows),
        )
    return outcomes


def _show(value: float | None) -> str:
    """A delay as the report prints it, with a dash for an absent set."""
    return "-" if value is None else f"{value:.0f}"


def _report(reading: Reading, verdict: Verdict) -> None:
    """Print the per-class tally, then all four halves and the verdict."""
    print()
    print("label    kind                     frozen  lane3  placed   of")
    for label, kind in sorted(reading.by_class):
        row = reading.by_class[(label, kind)]
        print(f"{label:8} {kind:24} {row.frozen:6} {row.lane3:7} {row.placed:7} {row.total:4}")

    print()
    print(f"attacks caught, frozen:  {reading.frozen_caught} of {BARS.total_attacks}")
    print(f"attacks caught, lane 3:  {reading.lane3_caught} of {BARS.total_attacks}")
    print(f"attacks caught, placed:  {reading.placed_caught} of {BARS.total_attacks}")
    print()
    print(f"benign drawing an alert, frozen: {reading.frozen_benign} of {BARS.total_benign}")
    print(f"benign drawing an alert, lane 3: {reading.lane3_benign} of {BARS.total_benign}")
    print(f"benign drawing an alert, placed: {reading.placed_benign} of {BARS.total_benign}")

    print()
    print(
        f"paired set, frozen vs placed: {reading.paired_n} attacks  "
        f"(frozen {_show(reading.paired_frozen)}s, placed {_show(reading.paired_placed)}s)"
    )
    print(
        f"own set,    frozen vs placed: frozen {_show(reading.own_frozen)}s, "
        f"placed {_show(reading.own_placed)}s"
    )
    print(
        f"paired set, frozen vs lane 3: {reading.paired_n_lane3} attacks  "
        f"(lane 3 {_show(reading.paired_lane3)}s), own set lane 3 {_show(reading.own_lane3)}s"
    )

    print()
    print(
        f"1. strictly more than {BARS.floor_catches} of {BARS.total_attacks}: "
        f"{verdict.strictly_more}"
    )
    print(f"2. no attack lost, paired set >= {reading.frozen_caught}: {verdict.nothing_lost}")
    print(f"3a. paired median delay no worse: {verdict.paired_delay_ok}")
    print(f"3b. own-set median delay no worse: {verdict.own_delay_ok}")
    print(
        f"4. benign no higher than {BARS.ceiling_benign} of {BARS.total_benign}: "
        f"{verdict.benign_ok}"
    )
    print()
    print(f"ALL FOUR HELD: {verdict.kept}")
    print()
    print("Development only. Simulated plant, so diagnosis not proof (R4, ADR 0143).")


def main(argv: Sequence[str] | None = None) -> int:
    """Score the earliest-crossing rule beside the frozen engine and lane 3 on development data."""
    parser = argparse.ArgumentParser(description="Half A of ADR 0397 on ICSSim development.")
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    arguments = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if "heldout" in arguments.corpus.name:
        raise SystemExit("this script is development only; the held-out corpus is not opened here")
    reading = summarise(_score(arguments.corpus))
    _report(reading, judges(reading))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

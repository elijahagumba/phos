#!/usr/bin/env python3
"""Lane 2 of the stronger-engine programme: does judging the signals together help?

Development seeds may be scored as often as you like. This script does not score a held-back
batch and does not touch a validation corpus. Nothing here writes a result file.

Two attack shapes are run on every seed, with one shift of plant each:

* **deep** — one signal held at a fixed value, the shape the frozen detector already catches. This
  is the regression check: the breadth column must not cost a catch here.
* **broad** — several signals held at once, each at its own mid-range value, so no single signal
  departs far. This is the shape `phos.atlas.consistency` cannot see by construction, because it
  opens an episode only where one signal alone crosses the threshold.

Both are scored by the frozen detector and by the breadth detector, through the same events and
budget machinery, and a catch is an alert whose row falls inside the attack window.

Usage::

    uv run python scripts/lane_e_breadth.py
    uv run python scripts/lane_e_breadth.py --seeds 97651 97652 --held 4
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

ROOT: Final = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from phos.atlas.breadth_consistency import (  # noqa: E402
    BreadthModel,
    augmented_scores,
    calibrate_breadth,
)
from phos.atlas.consistency import (  # noqa: E402
    ConsistencyModel,
    TrainFile,
    budget_alerts,
    events,
    feature_scores,
    fit,
)
from phos.atlas.consistency_windows import windows_for_period  # noqa: E402
from phos.eval.build_declaration import QUEUE_DEVELOPMENT_SEEDS  # noqa: E402
from phos.eval.mixed_queue import (  # noqa: E402
    QUIET_TRAIN_HOURS,
    QUIET_TRAIN_SEED,
    SHIFT_HOURS,
    attack_window,
    hold_value,
    job_for_seed,
    run_spec,
)
from phos.synth.injection import (  # noqa: E402
    CompositeInjection,
    HoldReading,
    Injection,
    TimeWindow,
)
from phos.synth.plant import PlantDescription  # noqa: E402
from phos.synth.plants.batch import BATCH_DESCRIPTION  # noqa: E402
from phos.synth.plants.power import POWER_DESCRIPTION  # noqa: E402
from phos.synth.plants.water import WATER_DESCRIPTION  # noqa: E402
from phos.synth.run import PlantRun, run_plant  # noqa: E402

_PLANTS = {
    WATER_DESCRIPTION.plant_id: WATER_DESCRIPTION,
    POWER_DESCRIPTION.plant_id: POWER_DESCRIPTION,
    BATCH_DESCRIPTION.plant_id: BATCH_DESCRIPTION,
}

logger = logging.getLogger("lane_e")

#: How many signals the broad attack holds at once, when the plant has that many.
BROAD_SIGNALS: Final = 4


@dataclass(frozen=True)
class Outcome:
    """One seed, one attack shape, both detectors."""

    seed: int
    shape: str
    champion_caught: bool
    breadth_caught: bool
    breadth_column_alerted: bool


def _matrix(run: PlantRun) -> tuple[numpy.ndarray, tuple[str, ...]]:
    keys = tuple(spec.key for spec in run.description.signals)
    rows = [[step.report.values[key] for key in keys] for step in run.steps]
    return numpy.asarray(rows, dtype=numpy.float64), keys


def _caught(
    scores: numpy.ndarray,
    model: ConsistencyModel,
    times: numpy.ndarray,
    first: float,
    last: float,
) -> tuple[bool, int | None]:
    """Return whether a budgeted alert lands in the window, and that alert's column."""
    found = events(scores, windows=model.windows)
    rows, columns, _ = budget_alerts(found, times, windows=model.windows)
    for row, column in zip(rows, columns, strict=True):
        if first <= float(times[row]) <= last:
            return True, int(column)
    return False, None


def _broad(
    description: PlantDescription, window: TimeWindow, keys: Sequence[str]
) -> CompositeInjection:
    """Hold several signals at their own mid-range value over the same window."""
    chosen = [item for item in description.signals if item.key in set(keys)][:BROAD_SIGNALS]
    return CompositeInjection(
        parts=tuple(
            HoldReading(item.key, hold_value(item.low, item.high), window) for item in chosen
        )
    )


def _score(seeds: Sequence[int]) -> list[Outcome]:
    by_plant: dict[str, list[int]] = {}
    for seed in seeds:
        by_plant.setdefault(job_for_seed(seed).plant_id, []).append(seed)

    outcomes: list[Outcome] = []
    for plant_id, plant_seeds in by_plant.items():
        job = job_for_seed(plant_seeds[0])
        description = _PLANTS[plant_id]
        windows = windows_for_period(float(job.sample_seconds))

        quiet_spec = run_spec(QUIET_TRAIN_SEED, job.sample_seconds, hours=QUIET_TRAIN_HOURS)
        quiet = run_plant(plant_id, quiet_spec)
        benign, keys = _matrix(quiet)
        model = fit(
            [TrainFile(values=benign, attack=numpy.zeros(benign.shape[0], dtype=numpy.bool_))],
            windows,
        )
        breadth = BreadthModel(
            base=model, divisor=calibrate_breadth(model, benign, windows.feature_gap)
        )
        logger.info("%s breadth divisor %.4f", plant_id, breadth.divisor)

        signal = next(item for item in description.signals if item.key == job.sensor)
        for seed in plant_seeds:
            spec = run_spec(seed, job.sample_seconds, hours=SHIFT_HOURS)
            window = attack_window(spec)
            shapes: dict[str, Injection] = {
                "deep": HoldReading(job.sensor, hold_value(signal.low, signal.high), window),
                "broad": _broad(description, window, keys),
            }
            for shape, injection in shapes.items():
                run = run_plant(plant_id, spec, injection=injection)
                values, found_keys = _matrix(run)
                if found_keys != keys:
                    raise SystemExit(f"seed {seed} columns drifted from the quiet train")
                times = numpy.array(
                    [step.timestamp.timestamp() for step in run.steps], dtype=numpy.float64
                )
                first = window.start.timestamp()
                last = window.end.timestamp()
                champion, _ = _caught(feature_scores(model, values), model, times, first, last)
                got, column = _caught(augmented_scores(breadth, values), model, times, first, last)
                outcomes.append(
                    Outcome(
                        seed=seed,
                        shape=shape,
                        champion_caught=champion,
                        breadth_caught=got,
                        breadth_column_alerted=got and column == values.shape[1],
                    )
                )
                logger.info("seed %s %-5s champion=%s breadth=%s", seed, shape, champion, got)
    return outcomes


def _report(outcomes: Sequence[Outcome]) -> None:
    print(f"{'shape':6} {'n':>3} {'champion':>9} {'breadth':>8} {'by the breadth column':>22}")
    for shape in ("deep", "broad"):
        rows = [item for item in outcomes if item.shape == shape]
        if not rows:
            continue
        print(
            f"{shape:6} {len(rows):3} "
            f"{sum(r.champion_caught for r in rows):9} "
            f"{sum(r.breadth_caught for r in rows):8} "
            f"{sum(r.breadth_column_alerted for r in rows):22}"
        )


def main(argv: Sequence[str] | None = None) -> int:
    """Score the development seeds on both attack shapes and print the tally."""
    parser = argparse.ArgumentParser(description="Lane 2 development measurement. Writes nothing.")
    parser.add_argument("--seeds", type=int, nargs="*", default=None)
    parser.add_argument("--held", type=int, default=BROAD_SIGNALS)
    arguments = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    seeds = tuple(arguments.seeds) if arguments.seeds else QUEUE_DEVELOPMENT_SEEDS
    globals()["BROAD_SIGNALS"] = int(arguments.held)
    _report(_score(seeds))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

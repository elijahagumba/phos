"""Score the six queue reorderings declared in ADR 0231.

``development`` scores HAI 20.07 and seeds 97651-97670. ``held-back`` scores
seeds 97601-97620 once, and only after ``FROZEN_VARIANT`` names one variant.
It refuses to start when the output already exists. It does not open a
validation corpus and it does not append ``eval_runs/log.jsonl``.
"""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy
from numpy.typing import NDArray

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from scripts.measure_baseline_table import (  # noqa: E402
    DECLARED_PERIOD_SECONDS,
    _read_hai,
)

from phos.atlas.consistency import (  # noqa: E402
    THRESHOLD,
    ConsistencyEvent,
    ConsistencyModel,
    TrainFile,
    events,
    feature_components,
    feature_scores,
    fit,
)
from phos.atlas.consistency_windows import windows_for_period  # noqa: E402
from phos.eval.baseline_alerts import _attack_intervals  # noqa: E402
from phos.eval.baseline_table import SeriesGrid  # noqa: E402
from phos.eval.build_declaration import (  # noqa: E402
    QUEUE_DEVELOPMENT_SEEDS,
    QUEUE_HELD_BACK_SEEDS,
)
from phos.eval.datasets import LabelledInterval  # noqa: E402
from phos.eval.mixed_queue import (  # noqa: E402
    QUIET_TRAIN_HOURS,
    QUIET_TRAIN_SEED,
    SHIFT_HOURS,
    PlantJob,
    attack_window,
    hold_value,
    job_for_seed,
    run_spec,
    work_order_for,
)
from phos.eval.queue_explain import explain_alert  # noqa: E402
from phos.eval.queue_rank import AttackSpan  # noqa: E402
from phos.eval.queue_reorder import (  # noqa: E402
    FROZEN_VARIANT,
    VARIANTS,
    QueueItem,
    Variant,
    a3_passes,
    champion_scores,
    recall_caught,
    refuse_existing,
    reject_for_recall,
    select_variant,
    variant_scores,
)
from phos.synth.injection import HoldReading  # noqa: E402
from phos.synth.maintenance import WorkOrder  # noqa: E402
from phos.synth.plant import PlantDescription  # noqa: E402
from phos.synth.plants.batch import BATCH_DESCRIPTION  # noqa: E402
from phos.synth.plants.power import POWER_DESCRIPTION  # noqa: E402
from phos.synth.plants.water import WATER_DESCRIPTION  # noqa: E402
from phos.synth.run import PlantRun, run_plant  # noqa: E402

logger = logging.getLogger("measure_d_queue")

DEVELOPMENT_OUT = ROOT / "eval_runs" / "build" / "d" / "queue" / "development.json"
HELD_BACK_OUT = ROOT / "eval_runs" / "build" / "d" / "queue" / "held-back.json"
HAI_DIR = ROOT / "data" / "hai-20.07"
_FORBIDDEN = ("hai-21", "hai-22", "hai-23", "batadal")
_PLANTS = {
    WATER_DESCRIPTION.plant_id: WATER_DESCRIPTION,
    POWER_DESCRIPTION.plant_id: POWER_DESCRIPTION,
    BATCH_DESCRIPTION.plant_id: BATCH_DESCRIPTION,
}
_Float = NDArray[numpy.float64]
_Score = NDArray[numpy.float32]


@dataclass(frozen=True)
class ScoredQueue:
    """One file or one seed: the champion's alerts and the attack windows."""

    name: str
    origin: datetime
    items: tuple[QueueItem, ...]
    spans: tuple[AttackSpan, ...]
    intervals: tuple[LabelledInterval, ...]
    benign_events: int
    alerts_in_work_order: int


def main(argv: Sequence[str]) -> None:
    """Score ``development`` or the one ``held-back`` look."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("phos.reasoning").setLevel(logging.ERROR)
    if len(argv) != 2 or argv[1] not in {"development", "held-back"}:
        raise SystemExit("usage: measure_d_queue.py development|held-back")
    if argv[1] == "held-back":
        _held_back()
        return
    _development()


def _development() -> None:
    hai = _hai_queues()
    hai_champion = _tally(hai, champion_scores)
    if hai_champion["passes"] != 19 or hai_champion["attacks"] != 38:
        raise SystemExit(
            f"HAI 20.07 champion A3 is {hai_champion['passes']}/{hai_champion['attacks']}, "
            "not 19/38; the metric is not changed and the seeds are not generated"
        )
    logger.info("HAI 20.07 champion %s/%s recall %s", 19, 38, hai_champion["recall_caught"])
    seeds = _seed_queues(QUEUE_DEVELOPMENT_SEEDS)
    payload: dict[str, object] = {
        "split": "development",
        "hai": _block(hai, hai_champion),
        "seeds": _block(seeds, _tally(seeds, champion_scores)),
    }
    payload["rejected"] = _rejected(payload)
    payload["selected"] = _selected(payload)
    _write(DEVELOPMENT_OUT, payload)
    logger.info("selected %s rejected %s", payload["selected"], payload["rejected"])


def _held_back() -> None:
    refuse_existing(HELD_BACK_OUT)
    frozen = _frozen()
    seeds = _seed_queues(QUEUE_HELD_BACK_SEEDS)
    champion = _tally(seeds, champion_scores)
    variant_tally = _tally(seeds, _scores_for(frozen))
    payload: dict[str, object] = {
        "split": "held-back",
        "result_name": f"atlas-queue-v2:{frozen.value}",
        "variant": frozen.value,
        "champion": champion,
        "variant_score": variant_tally,
        "a3_higher": variant_tally["passes"] > champion["passes"],
        "recall_not_lower": variant_tally["recall_caught"] >= champion["recall_caught"],
        "per_seed": _per_seed(seeds, (frozen,)),
    }
    _write(HELD_BACK_OUT, payload)
    logger.info(
        "%s A3 %s/%s champion %s/%s recall %s vs %s",
        payload["result_name"],
        variant_tally["passes"],
        variant_tally["attacks"],
        champion["passes"],
        champion["attacks"],
        variant_tally["recall_caught"],
        champion["recall_caught"],
    )


def _frozen() -> Variant:
    if FROZEN_VARIANT not in {variant.value for variant in VARIANTS}:
        raise SystemExit("no declared ranker is frozen; held-back does not run")
    return Variant(FROZEN_VARIANT)


def _hai_queues() -> tuple[ScoredQueue, ...]:
    _forbid(HAI_DIR)
    period = DECLARED_PERIOD_SECONDS["hai-20.07"]
    windows = windows_for_period(period)
    trains = tuple(_load_hai(name) for name in ("train1.csv.gz", "train2.csv.gz"))
    if len({grid.features for grid in trains}) != 1:
        raise SystemExit("HAI 20.07 training files do not share one column set")
    model = fit(
        [
            TrainFile(values=grid.values, attack=numpy.asarray(grid.attack, dtype=numpy.bool_))
            for grid in trains
        ],
        windows,
    )
    familiar = _familiar(model, trains)
    queues = []
    for name in ("test1.csv.gz", "test2.csv.gz"):
        grid = _load_hai(name)
        if grid.features != trains[0].features:
            raise SystemExit(f"{name} columns do not match training")
        queues.append(_queue_from_grid(name, grid, model, familiar, work_order=None))
    logger.info("HAI alerts %s", sum(len(queue.items) for queue in queues))
    return tuple(queues)


def _load_hai(name: str) -> SeriesGrid:
    path = HAI_DIR / name
    _forbid(path)
    if not path.is_file():
        raise SystemExit(f"missing {path}")
    return _read_hai(path, ";")


def _seed_queues(seeds: Sequence[int]) -> tuple[ScoredQueue, ...]:
    by_plant: dict[str, list[int]] = {}
    for seed in seeds:
        by_plant.setdefault(job_for_seed(seed).plant_id, []).append(seed)
    queues: list[ScoredQueue] = []
    for _plant_id, plant_seeds in by_plant.items():
        job = job_for_seed(plant_seeds[0])
        description = _PLANTS[job.plant_id]
        if description.units[0].unit_id != job.asset_id:
            raise SystemExit(
                f"{job.plant_id} first unit is {description.units[0].unit_id}, not {job.asset_id}"
            )
        model, familiar, keys = _fit_quiet(job, description)
        for seed in plant_seeds:
            queues.append(_score_seed(seed, job, description, model, familiar, keys))
            logger.info("scored seed %s", seed)
    return tuple(queues)


def _fit_quiet(
    job: PlantJob, description: PlantDescription
) -> tuple[ConsistencyModel, frozenset[frozenset[str]], tuple[str, ...]]:
    spec = run_spec(QUIET_TRAIN_SEED, job.sample_seconds, hours=QUIET_TRAIN_HOURS)
    run = run_plant(job.plant_id, spec)
    values, keys = _matrix(run)
    if keys != tuple(spec_item.key for spec_item in description.signals):
        raise SystemExit(f"{job.plant_id} column order drifted")
    model = fit(
        [TrainFile(values=values, attack=numpy.zeros(values.shape[0], dtype=numpy.bool_))],
        windows_for_period(float(job.sample_seconds)),
    )
    familiar = _familiar_values(model, values, keys)
    logger.info("%s quiet train sets %s", job.plant_id, len(familiar))
    return model, familiar, keys


def _score_seed(
    seed: int,
    job: PlantJob,
    description: PlantDescription,
    model: ConsistencyModel,
    familiar: frozenset[frozenset[str]],
    keys: tuple[str, ...],
) -> ScoredQueue:
    spec = run_spec(seed, job.sample_seconds, hours=SHIFT_HOURS)
    signal = next(item for item in description.signals if item.key == job.sensor)
    window = attack_window(spec)
    order = work_order_for(seed, spec, job.asset_id)
    if order.end >= window.start:
        raise SystemExit(f"seed {seed} work order overlaps the hold")
    run = run_plant(
        job.plant_id,
        spec,
        injection=HoldReading(job.sensor, hold_value(signal.low, signal.high), window),
    )
    values, found_keys = _matrix(run)
    if found_keys != keys:
        raise SystemExit(f"seed {seed} columns do not match the quiet train")
    timestamps = tuple(step.timestamp for step in run.steps)
    held = [stamp for stamp in timestamps if window.contains(stamp)]
    end = held[-1] if held else window.start
    span = AttackSpan(str(seed), window.start, end)
    interval = LabelledInterval(start=span.start, end=span.end, label="attack")
    items, in_order = _items(
        events(feature_scores(model, values), windows=model.windows),
        feature_components(model, values),
        keys,
        timestamps,
        familiar,
        f"{seed}",
        order,
    )
    return ScoredQueue(
        str(seed),
        timestamps[0],
        items,
        (span,),
        (interval,),
        len(run.events),
        in_order,
    )


def _queue_from_grid(
    name: str,
    grid: SeriesGrid,
    model: ConsistencyModel,
    familiar: frozenset[frozenset[str]],
    work_order: WorkOrder | None,
) -> ScoredQueue:
    intervals = tuple(_attack_intervals(grid))
    spans = tuple(
        AttackSpan(f"{name}#{index}", interval.start, interval.end)
        for index, interval in enumerate(intervals)
    )
    items, in_order = _items(
        events(feature_scores(model, grid.values), windows=model.windows),
        feature_components(model, grid.values),
        grid.features,
        grid.timestamps,
        familiar,
        name,
        work_order,
    )
    return ScoredQueue(name, grid.timestamps[0], items, spans, intervals, 0, in_order)


def _items(
    found: Sequence[ConsistencyEvent],
    components: tuple[_Score, _Score],
    keys: Sequence[str],
    timestamps: Sequence[datetime],
    familiar: frozenset[frozenset[str]],
    prefix: str,
    work_order: WorkOrder | None,
) -> tuple[tuple[QueueItem, ...], int]:
    loop, rng = components
    items: list[QueueItem] = []
    covered = 0
    for order, event in enumerate(found):
        columns = tuple(sorted({keys[member[4]] for member in event.members}))
        onset = keys[event.column]
        stamp = timestamps[event.onset]
        loop_score = float(loop[event.onset, event.column])
        range_score = float(rng[event.onset, event.column])
        witness = loop_score > THRESHOLD and loop_score >= range_score
        covered_now = work_order is not None and work_order.start <= stamp <= work_order.end
        if covered_now:
            covered += 1
        probe = explain_alert(columns, onset, witness=witness, work_order=covered_now)
        items.append(
            QueueItem(
                identity=f"{prefix}#{order}",
                timestamp=stamp,
                champion_score=float(event.score),
                input_order=order,
                familiar=frozenset(columns) in familiar,
                witness=witness,
                strong_innocent=probe.has_strong_innocent,
            )
        )
    return tuple(items), covered


def _familiar(model: ConsistencyModel, grids: Sequence[SeriesGrid]) -> frozenset[frozenset[str]]:
    found: set[frozenset[str]] = set()
    for grid in grids:
        for event in events(feature_scores(model, grid.values), windows=model.windows):
            if bool(grid.attack[event.onset]):
                continue
            found.add(frozenset(grid.features[member[4]] for member in event.members))
    return frozenset(found)


def _familiar_values(
    model: ConsistencyModel, values: _Float, keys: Sequence[str]
) -> frozenset[frozenset[str]]:
    found: set[frozenset[str]] = set()
    for event in events(feature_scores(model, values), windows=model.windows):
        found.add(frozenset(keys[member[4]] for member in event.members))
    return frozenset(found)


def _matrix(run: PlantRun) -> tuple[_Float, tuple[str, ...]]:
    keys = tuple(spec.key for spec in run.description.signals)
    rows = [[step.report.values[key] for key in keys] for step in run.steps]
    return numpy.asarray(rows, dtype=numpy.float64), keys


def _scores_for(
    variant: Variant,
) -> Callable[[Sequence[QueueItem]], Mapping[str, float]]:
    def scores(items: Sequence[QueueItem]) -> Mapping[str, float]:
        return variant_scores(items, variant)

    return scores


def _tally(
    queues: Sequence[ScoredQueue],
    scores_of: Callable[[Sequence[QueueItem]], Mapping[str, float]],
) -> dict[str, int]:
    passes = 0
    attacks = 0
    caught = 0
    for queue in queues:
        scores = scores_of(queue.items)
        passes += a3_passes(queue.items, queue.spans, queue.origin, scores)
        attacks += len(queue.spans)
        caught += recall_caught(queue.items, queue.intervals, queue.origin, scores)
    return {
        "passes": passes,
        "attacks": attacks,
        "recall_caught": caught,
        "recall_attacks": attacks,
    }


def _block(queues: Sequence[ScoredQueue], champion: Mapping[str, int]) -> dict[str, object]:
    variants: dict[str, object] = {}
    for variant in VARIANTS:
        tally = _tally(queues, _scores_for(variant))
        variants[variant.value] = {
            **tally,
            "rejected": reject_for_recall(tally["recall_caught"], champion["recall_caught"]),
            "flips": _flips(queues, variant),
        }
    return {
        "champion": dict(champion),
        "variants": variants,
        "per_seed": _per_seed(queues, VARIANTS),
    }


def _flips(queues: Sequence[ScoredQueue], variant: Variant) -> int:
    flips = 0
    for queue in queues:
        champion = a3_passes(queue.items, queue.spans, queue.origin, champion_scores(queue.items))
        other = a3_passes(
            queue.items, queue.spans, queue.origin, variant_scores(queue.items, variant)
        )
        if champion != other:
            flips += 1
    return flips


def _per_seed(
    queues: Sequence[ScoredQueue], variants: Sequence[Variant]
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for queue in queues:
        champion_pass = (
            a3_passes(queue.items, queue.spans, queue.origin, champion_scores(queue.items)) > 0
        )
        variant_pass = {
            variant.value: a3_passes(
                queue.items, queue.spans, queue.origin, variant_scores(queue.items, variant)
            )
            > 0
            for variant in variants
        }
        rows.append(
            {
                "name": queue.name,
                "alerts": len(queue.items),
                "attacks": len(queue.spans),
                "true_alerts": sum(
                    1
                    for item in queue.items
                    if any(interval.contains(item.timestamp) for interval in queue.intervals)
                ),
                "benign_events": queue.benign_events,
                "alerts_in_work_order": queue.alerts_in_work_order,
                "champion_pass": champion_pass,
                "variants": variant_pass,
            }
        )
    return rows


def _rejected(payload: Mapping[str, object]) -> list[str]:
    names: list[str] = []
    for block_name in ("hai", "seeds"):
        block = payload[block_name]
        if not isinstance(block, dict):
            raise TypeError("a score block must be an object")
        variants = block["variants"]
        if not isinstance(variants, dict):
            raise TypeError("variants must be an object")
        for name, row in variants.items():
            if isinstance(row, dict) and row.get("rejected") is True and name not in names:
                names.append(str(name))
    return names


def _selected(payload: Mapping[str, object]) -> str | None:
    hai = payload["hai"]
    seeds = payload["seeds"]
    if not isinstance(hai, dict) or not isinstance(seeds, dict):
        raise TypeError("score blocks must be objects")
    hai_variants = hai["variants"]
    seed_variants = seeds["variants"]
    if not isinstance(hai_variants, dict) or not isinstance(seed_variants, dict):
        raise TypeError("variants must be objects")
    rejected = {Variant(name) for name in _rejected(payload)}
    seed_passes = {variant: _passes(seed_variants[variant.value]) for variant in VARIANTS}
    hai_passes = {variant: _passes(hai_variants[variant.value]) for variant in VARIANTS}
    chosen = select_variant(seed_passes, hai_passes, rejected=tuple(rejected))
    return None if chosen is None else chosen.value


def _passes(row: object) -> int:
    if not isinstance(row, dict):
        raise TypeError("a variant row needs an integer passes count")
    passes = row.get("passes")
    if isinstance(passes, bool) or not isinstance(passes, int):
        raise TypeError("a variant row needs an integer passes count")
    return passes


def _write(path: Path, payload: dict[str, object]) -> None:
    _forbid(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _forbid(path: Path) -> None:
    text = str(path)
    if any(token in text for token in _FORBIDDEN):
        raise SystemExit(f"refusing to open {path}")


if __name__ == "__main__":
    main(sys.argv)

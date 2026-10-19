"""One A3 look: rank each attack in the champion's full shift queue.

Declared in ADR 0212. The scorer is ``atlas-v1-consistency`` with
``windows_for_period`` of the corpus's declared sample period. Nothing is tuned.
Refuses to start when the output already exists. Does not append the experiment log.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path
from typing import cast

import numpy

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.measure_baseline_table import (  # noqa: E402
    DATA,
    DECLARED_PERIOD_SECONDS,
    _read_hai,
    _read_prepared,
    _resolve,
)
from scripts.measure_clean_hai import _load  # noqa: E402

from phos.atlas import consistency  # noqa: E402
from phos.atlas.consistency_windows import windows_for_period  # noqa: E402
from phos.eval.baseline_alerts import _attack_intervals  # noqa: E402
from phos.eval.baseline_table import SeriesGrid, median_period_seconds  # noqa: E402
from phos.eval.queue_rank import AttackSpan, QueueAlert, rank_attacks  # noqa: E402

logger = logging.getLogger(__name__)

RESULT_NAME = "atlas-v1-consistency:a3-queue-rank"
OUT = ROOT / "eval_runs" / "build" / "v1" / "atlas" / "a3-queue-rank.json"
ORDER = ("hai-20.07", "hai-21.03", "hai-22.04", "hai-23.05", "batadal")
DECLARED_ATTACKS = {
    "hai-20.07": 38,
    "hai-21.03": 50,
    "hai-22.04": 58,
    "hai-23.05": 52,
    "batadal": 5,
}
HAI_FILES = {
    "hai-20.07": (
        ("train1.csv.gz", "train2.csv.gz"),
        ("test1.csv.gz", "test2.csv.gz"),
        ";",
    ),
    "hai-21.03": (
        ("train1.csv.gz", "train2.csv.gz", "train3.csv.gz"),
        ("test1.csv.gz", "test2.csv.gz", "test3.csv.gz", "test4.csv.gz", "test5.csv.gz"),
        ",",
    ),
}
EXTRA_ROOTS = ((DATA / "hai", "hai-21.03-"),)


def main() -> None:
    """Fit the frozen champion once per corpus and write the queue ranks."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if OUT.exists():
        raise SystemExit(f"{OUT.name} already exists; this run is once")
    registry = _registry_sha256()
    rows = [_one_corpus(corpus, registry) for corpus in ORDER]
    passes = sum(_as_int(row["passes"]) for row in rows)
    attacks = sum(_as_int(row["attacks"]) for row in rows)
    payload = {
        "result_name": RESULT_NAME,
        "detector": consistency.RESULT_NAME,
        "shift_hours": 8,
        "alerts_per_shift_not_applied": 8,
        "top_fraction": 0.1,
        "passes": passes,
        "attacks": attacks,
        "met": passes * 2 >= attacks,
        "corpora": rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUT.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(OUT)
    print(f"{RESULT_NAME}: {passes}/{attacks} {'met' if payload['met'] else 'not met'}")


def _one_corpus(corpus: str, registry: dict[str, dict[str, str]]) -> dict[str, object]:
    try:
        trains, tests = _load_corpus(corpus, registry)
    except FileNotFoundError as error:
        logger.error("%s not scored: %s", corpus, error)
        return _unscored(corpus, str(error))
    logger.info("fitting %s", corpus)
    return _score(corpus, trains, tests)


def _load_corpus(
    corpus: str, registry: dict[str, dict[str, str]]
) -> tuple[tuple[SeriesGrid, ...], tuple[tuple[str, SeriesGrid], ...]]:
    if corpus in HAI_FILES:
        trains, tests, separator = HAI_FILES[corpus]
        directory = DATA / corpus
        paths = tuple(_resolve(directory, name, EXTRA_ROOTS) for name in (*trains, *tests))
        _require(corpus, paths, registry)
        train_grids = tuple(_read_hai(path, separator) for path in paths[: len(trains)])
        test_grids = tuple((path.name, _read_hai(path, separator)) for path in paths[len(trains) :])
        return train_grids, test_grids
    if corpus in {"hai-22.04", "hai-23.05"}:
        _require_clean(corpus, registry)
        return _load(corpus)
    if corpus == "batadal":
        train = DATA / "batadal" / "batadal-train-prepared.csv"
        test = DATA / "batadal" / "batadal-test-prepared.csv"
        _require(corpus, (train, test), registry)
        return (_read_prepared(train, ()),), ((test.name, _read_prepared(test, ())),)
    raise FileNotFoundError(f"{corpus} has no loader")


def _require_clean(corpus: str, registry: dict[str, dict[str, str]]) -> None:
    directory = DATA / corpus
    if corpus == "hai-22.04":
        names = tuple(f"train{index}.csv" for index in range(1, 7)) + tuple(
            f"test{index}.csv" for index in range(1, 5)
        )
    else:
        names = (
            "hai-train1.csv",
            "hai-train2.csv",
            "hai-train3.csv",
            "hai-train4.csv",
            "hai-test1.csv",
            "hai-test2.csv",
            "label-test1.csv",
            "label-test2.csv",
        )
    _require(corpus, tuple(directory / name for name in names), registry)


def _require(corpus: str, paths: tuple[Path, ...], registry: dict[str, dict[str, str]]) -> None:
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError("missing files: " + ", ".join(missing))
    expected = registry.get(corpus, {})
    for path in paths:
        digest = _sha256(path)
        pinned = expected.get(path.name)
        if pinned is None:
            logger.info(
                "%s %s sha256 %s (registry has no sha256 for this name)",
                corpus,
                path.name,
                digest,
            )
            continue
        if digest != pinned:
            raise FileNotFoundError(f"{path.name} sha256 {digest} is not the registry pin {pinned}")


def _score(
    corpus: str,
    trains: tuple[SeriesGrid, ...],
    tests: tuple[tuple[str, SeriesGrid], ...],
) -> dict[str, object]:
    period = DECLARED_PERIOD_SECONDS[corpus]
    windows = windows_for_period(period)
    model = consistency.fit(
        [
            consistency.TrainFile(
                values=grid.values, attack=numpy.asarray(grid.attack, dtype=numpy.bool_)
            )
            for grid in trains
        ],
        windows,
    )
    ranks = []
    measured: list[float] = []
    for name, grid in tests:
        measured.append(median_period_seconds(grid.timestamps))
        found = consistency.events(consistency.feature_scores(model, grid.values), windows=windows)
        alerts = [
            QueueAlert(grid.timestamps[event.onset], float(event.score), order)
            for order, event in enumerate(found)
        ]
        spans = [
            AttackSpan(f"{name}#{index}", interval.start, interval.end)
            for index, interval in enumerate(_attack_intervals(grid))
        ]
        origin = grid.timestamps[0]
        for rank in rank_attacks(alerts, spans, origin=origin):
            ranks.append(
                {
                    "id": rank.attack_id,
                    "passed": rank.passed,
                    "rank": rank.rank,
                    "queue_length": rank.queue_length,
                    "top_slots": rank.top_slots,
                    "shift_index": rank.shift_index,
                }
            )
    passes = sum(1 for rank in ranks if rank["passed"])
    return {
        "corpus": corpus,
        "status": "scored",
        "declared_period_seconds": period,
        "measured_period_seconds": float(
            numpy.median(numpy.asarray(measured, dtype=numpy.float64))
        ),
        "windows": asdict(windows),
        "declared_attacks": DECLARED_ATTACKS[corpus],
        "passes": passes,
        "attacks": len(ranks),
        "ranks": ranks,
    }


def _unscored(corpus: str, reason: str) -> dict[str, object]:
    attacks = DECLARED_ATTACKS[corpus]
    return {
        "corpus": corpus,
        "status": "not_scored",
        "reason": reason,
        "declared_attacks": attacks,
        "passes": 0,
        "attacks": attacks,
        "ranks": [],
    }


def _registry_sha256() -> dict[str, dict[str, str]]:
    loaded = cast(object, json.loads((ROOT / "data" / "registry.json").read_text(encoding="utf-8")))
    if not isinstance(loaded, dict):
        raise SystemExit("registry is not an object")
    datasets = loaded.get("datasets")
    if not isinstance(datasets, list):
        raise SystemExit("registry has no datasets")
    pins: dict[str, dict[str, str]] = {}
    for entry in datasets:
        if not isinstance(entry, dict) or entry.get("name") not in ORDER:
            continue
        name = entry["name"]
        if not isinstance(name, str):
            continue
        files = entry.get("files")
        if not isinstance(files, list):
            continue
        pins[name] = {}
        for remote in files:
            if not isinstance(remote, dict):
                continue
            filename = remote.get("filename")
            digest = remote.get("sha256")
            if isinstance(filename, str) and isinstance(digest, str):
                pins[name][filename] = digest
    return pins


def _as_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SystemExit(f"expected an integer count, got {value!r}")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


if __name__ == "__main__":
    main()

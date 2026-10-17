"""Run the four checks declared in ADR 0105. Once.

Does not call the candidate look, does not edit the G1 table, and does not
append the experiment log. Refuses to start when its output already exists.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import sys
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from types import ModuleType
from typing import cast

import numpy
from numpy.typing import NDArray

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from scripts.measure_clean_hai import _load  # noqa: E402

from phos.eval.baseline_alerts import _attack_intervals, _keep_top  # noqa: E402
from phos.eval.baseline_table import (  # noqa: E402
    FileScore,
    SeriesGrid,
    _score_detector,
    aggregate_scores,
)
from phos.eval.candidate_checks import (  # noqa: E402
    CANDIDATE_CAUGHT,
    CHANCE_DRAWS,
    CHANCE_SEED,
    CHECKS_JSON_NAME,
    MINMAX_EVENTS_RELATIVE,
    MINMAX_EVENTS_SHA256,
    NO_LOOP_RELATIVE,
    NO_LOOP_SHA256,
    ChanceSummary,
    choose_driver,
    draw_rows,
    flagged_features,
    larger_component,
    same_alert_list,
    shift_ids,
    summarise_chance,
)
from phos.eval.candidate_look import (  # noqa: E402
    CANDIDATE_RELATIVE,
    CANDIDATE_SHA256,
    CLEAN_CORPORA,
    GROUPED_MINMAX,
    OWN_GROUPING,
    SHARED_WRAPPER,
    assert_candidate_bytes,
    beyond_grouped_minmax,
    cells_above,
    label_free_record,
    published_caught,
    sha256_bytes,
    train_record,
)
from phos.eval.datasets import LabelledInterval  # noqa: E402
from phos.eval.grouping import _episodes, _events, group_published_alerts  # noqa: E402

logger = logging.getLogger(__name__)

OUT = ROOT / "eval_runs" / "v1" / CHECKS_JSON_NAME
MARKDOWN = ROOT / "eval_runs" / "v1" / "g1-candidate-checks.md"
OWN_FROM = "own-grouping budget output passed to _score_detector"
SHARED_FROM = "group_published_alerts output passed to _score_detector"
CONTROLS = (
    ("sandbox-control:minmax-events", MINMAX_EVENTS_RELATIVE, MINMAX_EVENTS_SHA256),
    ("sandbox-control:no-loop", NO_LOOP_RELATIVE, NO_LOOP_SHA256),
)


def main() -> None:
    """Run chance, drivers, the two controls, and the alert-list audit once."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if OUT.exists():
        raise SystemExit(f"{OUT.name} already exists; these checks run once")
    _require_bytes(ROOT / CANDIDATE_RELATIVE, CANDIDATE_SHA256, assert_candidate_bytes)
    for _name, relative, digest in CONTROLS:
        _require_bytes(ROOT / relative, digest, None)
    candidate = _load_module(ROOT / CANDIDATE_RELATIVE, "sandbox_candidate_frozen")
    rng = numpy.random.Generator(numpy.random.PCG64(CHANCE_SEED))
    payload: dict[str, object] = {"chance": {}, "drivers": {}, "controls": {}, "independence": {}}
    chance = payload["chance"]
    drivers = payload["drivers"]
    controls = payload["controls"]
    independence = payload["independence"]
    assert isinstance(chance, dict)
    assert isinstance(drivers, dict)
    assert isinstance(controls, dict)
    assert isinstance(independence, dict)
    for corpus in CLEAN_CORPORA:
        logger.info("chance %s", corpus)
        _trains, tests = _load(corpus)
        chance[corpus] = _chance_row(tests, rng)
    for corpus in CLEAN_CORPORA:
        logger.info("candidate fit %s", corpus)
        trains, tests = _load(corpus)
        driver_row, audit_row = _candidate_fit(candidate, corpus, trains, tests)
        drivers[corpus] = driver_row
        independence[corpus] = audit_row
    for name, relative, _digest in CONTROLS:
        module = _load_module(ROOT / relative, name)
        for corpus in CLEAN_CORPORA:
            logger.info("control %s %s", name, corpus)
            trains, tests = _load(corpus)
            row = _control_row(module, name, corpus, trains, tests)
            controls.setdefault(corpus, []).append(row)
    text = _render(payload)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    MARKDOWN.write_text(text, encoding="utf-8")
    print(text)


def _require_bytes(path: Path, digest: str, candidate_check: object) -> None:
    payload = path.read_bytes()
    if sha256_bytes(payload) != digest:
        raise SystemExit(f"{path} sha256 is not {digest}")
    if candidate_check is not None:
        assert_candidate_bytes(payload)


def _load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _chance_row(
    tests: tuple[tuple[str, SeriesGrid], ...], rng: numpy.random.Generator
) -> dict[str, float | int]:
    caught = numpy.zeros(CHANCE_DRAWS, dtype=numpy.int64)
    prepared = tuple(
        (grid.timestamps, shift_ids(_unix(grid)), _attack_intervals(grid)) for _name, grid in tests
    )
    for draw in range(CHANCE_DRAWS):
        total = 0
        for timestamps, shifts, intervals in prepared:
            rows = draw_rows(numpy.arange(shifts.size, dtype=numpy.int64), shifts, rng)
            total += _hits(timestamps, rows, intervals)
        caught[draw] = total
    summary = summarise_chance(caught)
    return _chance_dict(summary)


def _hits(
    timestamps: tuple[datetime, ...],
    rows: NDArray[numpy.int64],
    intervals: Sequence[LabelledInterval],
) -> int:
    chosen = [timestamps[int(row)] for row in rows.tolist()]
    return sum(
        1
        for interval in intervals
        if any(interval.start <= stamp <= interval.end for stamp in chosen)
    )


def _chance_dict(summary: ChanceSummary) -> dict[str, float | int]:
    return {
        "draws": summary.draws,
        "mean_caught": summary.mean_caught,
        "percentile_95": summary.percentile_95,
        "max_caught": summary.max_caught,
    }


def _unix(grid: SeriesGrid) -> NDArray[numpy.float64]:
    return numpy.asarray([stamp.timestamp() for stamp in grid.timestamps], dtype=numpy.float64)


def _candidate_fit(
    module: ModuleType,
    corpus: str,
    trains: tuple[SeriesGrid, ...],
    tests: tuple[tuple[str, SeriesGrid], ...],
) -> tuple[dict[str, object], dict[str, object]]:
    train_records = [train_record(grid) for grid in trains]
    model, divisor = _fit_body(module, train_records)
    expected, attacks = CANDIDATE_CAUGHT[corpus]
    counts: dict[str, dict[str, int]] = defaultdict(
        lambda: {"attacks": 0, "range": 0, "loop": 0, "tie": 0}
    )
    own_before = own_after = own_kept = 0
    shared_before = shared_after = shared_kept = 0
    same_pairs = True
    same_timestamps = True
    files: list[FileScore] = []
    caught_attacks = 0
    for name, grid in tests:
        record = label_free_record(grid)
        values = numpy.asarray(record["values"])
        loop, rng_scores, combined = _parts(module, values, model)
        scale = numpy.asarray(divisor, dtype=numpy.float64)
        scores = (combined / scale).astype(numpy.float32)
        features = grid.features
        events = module._events(scores)
        emitted_rows, emitted_cols, emitted_scores = module._budget(events, record["time"])
        own_cells = [
            (int(row), features[int(column)], float(score))
            for row, column, score in zip(emitted_rows, emitted_cols, emitted_scores, strict=True)
        ]
        published = cells_above(
            numpy.asarray(scores, dtype=numpy.float64), features, float(module.THRESHOLD)
        )
        shared_events = _events(_episodes(grid.timestamps, published), grid.timestamps)
        shared_cells = list(group_published_alerts(grid.timestamps, published))
        own_pairs = [(row, feature) for row, feature, _score in own_cells]
        shared_pairs = [(row, feature) for row, feature, _score in shared_cells]
        same_pairs = same_pairs and same_alert_list(own_pairs, shared_pairs)
        same_timestamps = same_timestamps and {row for row, _feature in own_pairs} == {
            row for row, _feature in shared_pairs
        }
        own_before += len(events)
        own_after += len(own_cells)
        own_kept += len(_keep_top(own_cells, grid.timestamps))
        shared_before += len(shared_events)
        shared_after += len(shared_cells)
        shared_kept += len(_keep_top(shared_cells, grid.timestamps))
        files.append(FileScore(name, (_score_detector(OWN_GROUPING, own_cells, grid),)))
        _count_drivers(counts, grid, own_cells, loop, rng_scores, features)
        caught_attacks += len(_caught_rows(grid, own_cells))
    score = aggregate_scores(files)[0]
    if score.caught != expected or score.attacks != attacks or caught_attacks != expected:
        raise SystemExit(
            f"{corpus} own grouping caught {score.caught}/{score.attacks}, "
            f"ADR 0104 is {expected}/{attacks}"
        )
    return (
        {"caught": score.caught, "features": _feature_rows(counts, score.caught)},
        {
            "same_alert_list": same_pairs,
            "same_timestamps": same_timestamps,
            "rows": [
                _audit_row(OWN_GROUPING, own_before, own_after, own_kept, OWN_FROM),
                _audit_row(SHARED_WRAPPER, shared_before, shared_after, shared_kept, SHARED_FROM),
            ],
        },
    )


def _fit_body(module: ModuleType, train_records: list[dict[str, object]]) -> tuple[object, object]:
    if module.CALIBRATION == "insample":
        fitted = module._calibrate_insample(train_records)
        return cast(tuple[object, object], fitted)
    if module.CALIBRATION == "none":
        return module._fit(train_records), 1.0
    scale, divisor = module._calibrate(train_records)
    return module._fit(train_records, scale), divisor


def _parts(
    module: ModuleType, values: NDArray[numpy.float64], model: object
) -> tuple[NDArray[numpy.float32], NDArray[numpy.float32], NDArray[numpy.float32]]:
    mu, sd, live, low, high, weights, scale = cast(
        tuple[
            NDArray[numpy.float64],
            NDArray[numpy.float64],
            NDArray[numpy.intp],
            NDArray[numpy.float64],
            NDArray[numpy.float64],
            NDArray[numpy.float64],
            NDArray[numpy.float64],
        ],
        model,
    )
    loop = numpy.zeros(values.shape, dtype=numpy.float32)
    if module.USE_LOOP:
        loop[:, live] = module._loop_residual(values, mu, sd, live, weights) / scale[live]
    rng_scores = numpy.asarray(module._range_scores(values, low, high), dtype=numpy.float32)
    if module.USE_DETREND:
        loop = numpy.asarray(module._detrend(loop), dtype=numpy.float32)
        rng_scores = numpy.asarray(module._detrend(rng_scores), dtype=numpy.float32)
    combined = numpy.asarray(module._raw_scores(values, model), dtype=numpy.float32)
    if not numpy.array_equal(combined, numpy.maximum(loop, rng_scores)):
        raise SystemExit("range and loop do not reconstruct _raw_scores")
    return loop, rng_scores, combined


def _count_drivers(
    counts: dict[str, dict[str, int]],
    grid: SeriesGrid,
    cells: list[tuple[int, str, float]],
    loop: NDArray[numpy.float32],
    rng_scores: NDArray[numpy.float32],
    features: tuple[str, ...],
) -> None:
    kept = _keep_top(cells, grid.timestamps)
    row_of = {stamp: index for index, stamp in enumerate(grid.timestamps)}
    index_of = {feature: index for index, feature in enumerate(features)}
    for interval in _attack_intervals(grid):
        inside = [
            (row_of[detection.timestamp], feature, float(detection.score))
            for detection in kept
            if interval.start <= detection.timestamp <= interval.end
            and (feature := detection.feature) is not None
        ]
        if not inside:
            continue
        driver = choose_driver(inside)
        kind = larger_component(
            float(rng_scores[driver.row, index_of[driver.feature]]),
            float(loop[driver.row, index_of[driver.feature]]),
        )
        bucket = counts[driver.feature]
        bucket["attacks"] += 1
        bucket[kind] += 1


def _caught_rows(grid: SeriesGrid, cells: list[tuple[int, str, float]]) -> list[int]:
    kept = _keep_top(cells, grid.timestamps)
    return [
        index
        for index, interval in enumerate(_attack_intervals(grid))
        if any(interval.start <= detection.timestamp <= interval.end for detection in kept)
    ]


def _feature_rows(counts: dict[str, dict[str, int]], caught: int) -> list[dict[str, object]]:
    flagged = set(flagged_features({name: row["attacks"] for name, row in counts.items()}, caught))
    return [
        {
            "feature": name,
            "attacks": row["attacks"],
            "range": row["range"],
            "loop": row["loop"],
            "tie": row["tie"],
            "flagged": name in flagged,
        }
        for name, row in sorted(counts.items(), key=lambda item: (-item[1]["attacks"], item[0]))
    ]


def _audit_row(name: str, before: int, after: int, kept: int, source: str) -> dict[str, object]:
    return {
        "detector": name,
        "events_before_budget": before,
        "alerts_after_budget": after,
        "alerts_kept": kept,
        "point_adjusted_from": source,
        "point_adjusted_alerts": after,
    }


def _control_row(
    module: ModuleType,
    name: str,
    corpus: str,
    trains: tuple[SeriesGrid, ...],
    tests: tuple[tuple[str, SeriesGrid], ...],
) -> dict[str, object]:
    train_records = [train_record(grid) for grid in trains]
    test_records = [label_free_record(grid) for _file, grid in tests]
    produced = list(module.feature_scores(train_records, test_records))
    files: list[FileScore] = []
    for (file_name, grid), record, matrix in zip(tests, test_records, produced, strict=True):
        scores = numpy.asarray(matrix, dtype=numpy.float64)
        budget = module._budget(module._events(scores), record["time"])
        emitted_rows, emitted_cols, emitted_scores = budget
        cells = [
            (int(row), grid.features[int(column)], float(score))
            for row, column, score in zip(emitted_rows, emitted_cols, emitted_scores, strict=True)
        ]
        files.append(FileScore(file_name, (_score_detector(name, cells, grid),)))
    score = aggregate_scores(files)[0]
    minmax_caught, attacks = published_caught(corpus, GROUPED_MINMAX)
    if score.attacks != attacks:
        raise SystemExit(f"{corpus} {name} denominator is not {attacks}")
    return {
        "detector": name,
        "caught": score.caught,
        "attacks": score.attacks,
        "beyond_grouped_minmax": beyond_grouped_minmax(score.caught, minmax_caught),
        "point_adjusted_f1": score.point_adjusted_f1,
    }


def _render(payload: dict[str, object]) -> str:
    lines = [
        "# Four checks on the frozen candidate",
        "",
        "Recall within budget is the headline where a check catches attacks.",
        "Point-adjusted F1 is reported and is not. ADR 0104's 53/58 and 36/52 stay.",
        "Grouped MinMax stays 10/58 and 6/52.",
        "",
        "## Chance null",
        "",
        "| Edition | Draws | Mean caught | 95th percentile | Max caught |",
        "|---|---:|---:|---:|---:|",
    ]
    chance = payload["chance"]
    assert isinstance(chance, dict)
    for corpus, row in chance.items():
        assert isinstance(row, dict)
        lines.append(
            f"| {corpus} | {row['draws']} | {row['mean_caught']:.6f} | "
            f"{row['percentile_95']:.6f} | {row['max_caught']} |"
        )
    lines.extend(["", "## Drivers", ""])
    drivers = payload["drivers"]
    assert isinstance(drivers, dict)
    for corpus, row in drivers.items():
        assert isinstance(row, dict)
        lines.append(f"### {corpus}")
        lines.append("")
        lines.append("| Feature | Caught attacks | Range larger | Loop larger | Tie | Flagged |")
        lines.append("|---|---:|---:|---:|---:|---|")
        features = row["features"]
        assert isinstance(features, list)
        for feature in features:
            assert isinstance(feature, dict)
            lines.append(
                f"| {feature['feature']} | {feature['attacks']} | {feature['range']} | "
                f"{feature['loop']} | {feature['tie']} | {feature['flagged']} |"
            )
        lines.append("")
    lines.extend(
        [
            "## Controls",
            "",
            "| Edition | Control | Caught/attacks | Beyond grouped MinMax | Point-adjusted F1 |",
            "|---|---|---:|---:|---:|",
        ]
    )
    controls = payload["controls"]
    assert isinstance(controls, dict)
    for corpus, rows in controls.items():
        assert isinstance(rows, list)
        for row in rows:
            assert isinstance(row, dict)
            lines.append(
                f"| {corpus} | {row['detector']} | {row['caught']}/{row['attacks']} | "
                f"{row['beyond_grouped_minmax']} | {row['point_adjusted_f1']:.6f} |"
            )
    lines.extend(["", "## Alert lists", ""])
    lines.append(
        "| Edition | Row | Events before budget | Alerts after budget | Alerts kept | "
        "Point-adjusted F1 from |"
    )
    lines.append("|---|---|---:|---:|---:|---|")
    independence = payload["independence"]
    assert isinstance(independence, dict)
    notes: list[str] = []
    for corpus, row in independence.items():
        assert isinstance(row, dict)
        listed = row["rows"]
        assert isinstance(listed, list)
        for item in listed:
            assert isinstance(item, dict)
            lines.append(
                f"| {corpus} | {item['detector']} | {item['events_before_budget']} | "
                f"{item['alerts_after_budget']} | {item['alerts_kept']} | "
                f"{item['point_adjusted_from']} |"
            )
        notes.append(
            f"{corpus}: same alert list {row['same_alert_list']}; "
            f"same timestamps {row['same_timestamps']}."
        )
    lines.append("")
    lines.extend(notes)
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    main()

"""Score `atlas-v1-consistency` once on BATADAL, with its windows scaled by the declared rule.

Declared in ADR 0112. BATADAL is read exactly as the G1 grouped rows read it (ADR 0100): the
prepared train and test files, no unscored label. The windows are `windows_for_period` of the
declared period, 3600 s. Every other constant is the frozen candidate's. Grouped MinMax is
replayed and must reproduce its published 3/5 or nothing is written. Grouped opponents and grouped
G1 Atlas are ADR 0100's published rows, not scored again. Does not append the experiment log.
Refuses to start when the output already exists.
"""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from scripts.measure_baseline_table import (  # noqa: E402
    DATA,
    DECLARED_PERIOD_SECONDS,
    _read_prepared,
)

from phos.atlas import consistency  # noqa: E402
from phos.atlas.consistency_windows import windows_for_period  # noqa: E402
from phos.eval.baseline_alerts import _minmax_cells  # noqa: E402
from phos.eval.baseline_table import (  # noqa: E402
    FileScore,
    SeriesGrid,
    _fit_opponents,
    _score_detector,
    aggregate_scores,
    benign_matrix,
    median_period_seconds,
)
from phos.eval.grouped_rows import _caught_ids  # noqa: E402
from phos.eval.grouping import group_published_alerts  # noqa: E402

logger = logging.getLogger(__name__)

CORPUS = "batadal"
TRAIN = DATA / "batadal" / "batadal-train-prepared.csv"
TEST = DATA / "batadal" / "batadal-test-prepared.csv"
OUT = ROOT / "eval_runs" / "v1" / "consistency-batadal.json"
MARKDOWN = ROOT / "eval_runs" / "v1" / "consistency-batadal.md"
#: ADR 0100's published grouped rows on BATADAL. Not scored again.
PUBLISHED_GROUPED: dict[str, int] = {
    "g1-grouped:atlas-mahalanobis": 5,
    "g1-grouped:simple-minmax": 3,
    "g1-grouped:simple-steadytime": 2,
    "g1-grouped:simple-histogram": 2,
}
BEST_CHECKED_OPPONENT = "g1-grouped:simple-minmax"
ATTACKS = 5


def main() -> None:
    """Fit on BATADAL's training file, score its test file once, write one record."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if OUT.exists():
        raise SystemExit(f"{OUT.name} already exists; this run is once")
    missing = [str(path) for path in (TRAIN, TEST) if not path.is_file()]
    if missing:
        raise SystemExit(f"missing: {', '.join(missing)}")
    train = _read_prepared(TRAIN, ())
    test = _read_prepared(TEST, ())
    if train.features != test.features:
        raise SystemExit("train and test do not share a feature list")
    period = DECLARED_PERIOD_SECONDS[CORPUS]
    measured = median_period_seconds(test.timestamps)
    if measured != period:
        raise SystemExit(f"measured period {measured} s is not the declared {period} s")
    windows = windows_for_period(period)
    logger.info("windows %s", windows)

    minmax_ids = _replay_minmax(train, test)
    if len(minmax_ids) != PUBLISHED_GROUPED[BEST_CHECKED_OPPONENT]:
        raise SystemExit(
            f"grouped MinMax replay caught {len(minmax_ids)}, "
            f"published {PUBLISHED_GROUPED[BEST_CHECKED_OPPONENT]}; nothing written"
        )

    model = consistency.fit(
        [
            consistency.TrainFile(
                values=train.values, attack=numpy.asarray(train.attack, dtype=numpy.bool_)
            )
        ],
        windows,
    )
    time = numpy.asarray([stamp.timestamp() for stamp in test.timestamps], dtype=numpy.float64)
    found = consistency.events(consistency.feature_scores(model, test.values), windows=windows)
    rows, columns, scores = consistency.budget_alerts(found, time, windows)
    cells = [
        (int(row), test.features[int(column)], float(score))
        for row, column, score in zip(rows, columns, scores, strict=True)
    ]
    score = aggregate_scores(
        [FileScore(TEST.name, (_score_detector(consistency.RESULT_NAME, cells, test),))]
    )[0]
    if score.attacks != ATTACKS:
        raise SystemExit(f"denominator {score.attacks} is not {ATTACKS}; nothing written")
    caught_ids = tuple(_caught_ids(cells, test, TEST.name))
    best = PUBLISHED_GROUPED[BEST_CHECKED_OPPONENT]
    payload = {
        "corpus": CORPUS,
        "detector": consistency.RESULT_NAME,
        "declared_period_seconds": period,
        "windows": asdict(windows),
        "train_rows": int(train.values.shape[0]),
        "signals": len(train.features),
        "events": len(found),
        "score": asdict(score),
        "best_grouped_checked_opponent": BEST_CHECKED_OPPONENT,
        "best_grouped_checked_opponent_caught": best,
        "beyond_best_grouped_checked_opponent": score.caught - best,
        "strictly_higher_than_best_grouped_checked_opponent": score.caught > best,
        "published_grouped_rows": PUBLISHED_GROUPED,
        "caught_attacks": sorted(caught_ids),
        "attacks_only_consistency_catches_against_minmax": sorted(
            set(caught_ids) - set(minmax_ids)
        ),
        "alert_rows": [
            {"row": row, "timestamp": test.timestamps[row].isoformat(), "feature": feature}
            for row, feature, _score in cells
        ],
    }
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    MARKDOWN.write_text(_render(payload), encoding="utf-8")
    print(_render(payload))


def _replay_minmax(train: SeriesGrid, test: SeriesGrid) -> tuple[str, ...]:
    """Grouped MinMax's caught attack ids, recovered the way ADR 0103's script recovered them."""
    features, matrix, _excluded = benign_matrix((train,))
    minmax, _steady, _histogram = _fit_opponents(features, matrix)
    grouped = group_published_alerts(test.timestamps, _minmax_cells(minmax, test))
    return tuple(_caught_ids(grouped, test, TEST.name))


def _render(payload: Mapping[str, Any]) -> str:
    score = payload["score"]
    lines = [
        "# atlas-v1-consistency on BATADAL, scored once",
        "",
        "Declared in ADR 0112. Recall within budget (8 alerts per 8-hour shift) is the headline.",
        "eTaPR and point-adjusted F1 are reported and are not. The grouped rows beside it are",
        "ADR 0100's published counts, not scored again.",
        "",
        "| Detector | Caught | Attacks | Recall within budget | eTaPR F1 (reference) | "
        "eTaPR F1 (HAICon) | Point-adjusted F1 | Alerts |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
        f"| {payload['detector']} | {score['caught']} | {score['attacks']} | "
        f"{score['recall_within_budget']:.6f} | {score['etapr_reference_f1']:.6f} | "
        f"{score['etapr_haicon_f1']:.6f} | {score['point_adjusted_f1']:.6f} | {score['alerts']} |",
    ]
    for name, caught in payload["published_grouped_rows"].items():
        lines.append(f"| {name} (published) | {caught} | {ATTACKS} | | | | | |")
    caught_list = ", ".join(payload["caught_attacks"]) or "none"
    lines.extend(
        [
            "",
            f"Windows: `{payload['windows']}`.",
            f"Beyond the best grouped checked opponent "
            f"({payload['best_grouped_checked_opponent']}): "
            f"{payload['beyond_best_grouped_checked_opponent']}.",
            f"Attacks caught: {caught_list}.",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    main()

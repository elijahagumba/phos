"""Score the frozen sandbox candidate once on HAI 22.04 and 23.05.

Declared in ADR 0103. Does not refit Atlas, does not append the experiment log,
and does not edit the G1 table. Refuses to start when the output already exists.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import sys
from pathlib import Path
from types import ModuleType

import numpy

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from scripts.measure_clean_hai import _load  # noqa: E402

from phos.eval.baseline_alerts import _minmax_cells  # noqa: E402
from phos.eval.baseline_table import (  # noqa: E402
    DetectorScore,
    FileScore,
    SeriesGrid,
    _fit_opponents,
    _score_detector,
    aggregate_scores,
    benign_matrix,
)
from phos.eval.candidate_look import (  # noqa: E402
    CANDIDATE_RELATIVE,
    CLEAN_CORPORA,
    GROUPED_ATLAS,
    GROUPED_MINMAX,
    LOOK_JSON_NAME,
    OWN_GROUPING,
    SHARED_WRAPPER,
    LookRow,
    assert_candidate_bytes,
    attacks_only_candidate,
    beyond_grouped_minmax,
    cells_above,
    label_free_record,
    published_caught,
    render_look,
    train_record,
)
from phos.eval.grouped_rows import _caught_ids  # noqa: E402
from phos.eval.grouping import group_published_alerts  # noqa: E402

logger = logging.getLogger(__name__)

OUT = ROOT / "eval_runs" / "v1" / LOOK_JSON_NAME
MARKDOWN = ROOT / "eval_runs" / "v1" / "g1-candidate-look.md"


def main() -> None:
    """Fit the frozen candidate on the two clean editions and write one report."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if OUT.exists():
        raise SystemExit(f"{OUT.name} already exists; this run is once")
    path = ROOT / CANDIDATE_RELATIVE
    assert_candidate_bytes(path.read_bytes())
    module = _load_candidate(path)
    threshold = float(module.THRESHOLD)
    rows: list[LookRow] = []
    for corpus in CLEAN_CORPORA:
        logger.info("reading %s", corpus)
        trains, tests = _load(corpus)
        _same_features(trains, tests)
        minmax_ids = _replay_minmax(trains, tests)
        minmax_caught, attacks = published_caught(corpus, GROUPED_MINMAX)
        if len(minmax_ids) != minmax_caught:
            raise SystemExit(
                f"{corpus} grouped MinMax replay caught {len(minmax_ids)}, "
                f"published {minmax_caught}"
            )
        atlas_caught, atlas_attacks = published_caught(corpus, GROUPED_ATLAS)
        if atlas_attacks != attacks:
            raise SystemExit(f"{corpus} published attack counts disagree")
        logger.info("scoring candidate on %s", corpus)
        own, shared, own_ids, shared_ids = _score_candidate(module, threshold, trains, tests)
        if own.attacks != attacks or shared.attacks != attacks:
            raise SystemExit(f"{corpus} candidate denominator is not {attacks}")
        rows.extend(
            (
                LookRow(corpus, GROUPED_ATLAS, atlas_caught, attacks, None, None, ()),
                LookRow(corpus, GROUPED_MINMAX, minmax_caught, attacks, None, None, ()),
                _candidate_row(corpus, own, minmax_caught, own_ids, minmax_ids),
                _candidate_row(corpus, shared, minmax_caught, shared_ids, minmax_ids),
            )
        )
        logger.info(
            "scored %s own %s/%s shared %s/%s minmax %s",
            corpus,
            own.caught,
            attacks,
            shared.caught,
            attacks,
            minmax_caught,
        )
    text = render_look(rows)
    payload = [
        {
            "corpus": row.corpus,
            "detector": row.detector,
            "caught": row.caught,
            "attacks": row.attacks,
            "recall_within_budget": row.recall_within_budget,
            "point_adjusted_f1": row.point_adjusted_f1,
            "beyond_grouped_minmax": row.beyond_grouped_minmax,
            "attacks_only_candidate": row.attacks_only_candidate,
        }
        for row in rows
    ]
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    MARKDOWN.write_text(text, encoding="utf-8")
    print(text)


def _load_candidate(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("sandbox_candidate_frozen", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _same_features(
    trains: tuple[SeriesGrid, ...], tests: tuple[tuple[str, SeriesGrid], ...]
) -> None:
    features = trains[0].features
    grids = (*trains, *(grid for _name, grid in tests))
    if any(grid.features != features for grid in grids):
        raise SystemExit("train and test files do not share a feature list")


def _replay_minmax(
    trains: tuple[SeriesGrid, ...], tests: tuple[tuple[str, SeriesGrid], ...]
) -> tuple[str, ...]:
    """Recover grouped MinMax attack ids. Abort upstream if the count moved."""
    features, matrix, _excluded = benign_matrix(trains)
    minmax, _steady, _histogram = _fit_opponents(features, matrix)
    found: list[str] = []
    for name, grid in tests:
        grouped = group_published_alerts(grid.timestamps, _minmax_cells(minmax, grid))
        found.extend(_caught_ids(grouped, grid, name))
    return tuple(found)


def _score_candidate(
    module: ModuleType,
    threshold: float,
    trains: tuple[SeriesGrid, ...],
    tests: tuple[tuple[str, SeriesGrid], ...],
) -> tuple[DetectorScore, DetectorScore, tuple[str, ...], tuple[str, ...]]:
    """One fit. Own grouping is the body of ``run``; the wrapper sees the same scores."""
    train_records = [train_record(grid) for grid in trains]
    test_records = [label_free_record(grid) for _name, grid in tests]
    produced = list(module.feature_scores(train_records, test_records))
    if len(produced) != len(tests):
        raise SystemExit("candidate returned the wrong number of test files")
    events = module._events
    budget = module._budget
    own_files: list[FileScore] = []
    shared_files: list[FileScore] = []
    own_ids: list[str] = []
    shared_ids: list[str] = []
    for (name, grid), record, matrix in zip(tests, test_records, produced, strict=True):
        scores = numpy.asarray(matrix, dtype=numpy.float64)
        emitted_rows, emitted_cols, emitted_scores = budget(events(scores), record["time"])
        features = grid.features
        own_cells = [
            (int(row), features[int(column)], float(score))
            for row, column, score in zip(emitted_rows, emitted_cols, emitted_scores, strict=True)
        ]
        shared_cells = group_published_alerts(
            grid.timestamps, cells_above(scores, features, threshold)
        )
        own_files.append(FileScore(name, (_score_detector(OWN_GROUPING, own_cells, grid),)))
        shared_files.append(FileScore(name, (_score_detector(SHARED_WRAPPER, shared_cells, grid),)))
        own_ids.extend(_caught_ids(own_cells, grid, name))
        shared_ids.extend(_caught_ids(shared_cells, grid, name))
    return (
        aggregate_scores(own_files)[0],
        aggregate_scores(shared_files)[0],
        tuple(own_ids),
        tuple(shared_ids),
    )


def _candidate_row(
    corpus: str,
    score: DetectorScore,
    minmax_caught: int,
    candidate_ids: tuple[str, ...],
    minmax_ids: tuple[str, ...],
) -> LookRow:
    return LookRow(
        corpus=corpus,
        detector=score.detector,
        caught=score.caught,
        attacks=score.attacks,
        point_adjusted_f1=score.point_adjusted_f1,
        beyond_grouped_minmax=beyond_grouped_minmax(score.caught, minmax_caught),
        attacks_only_candidate=attacks_only_candidate(candidate_ids, minmax_ids),
    )


if __name__ == "__main__":
    main()

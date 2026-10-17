"""Grouped rows beside the published G1 table.

Does not recompute the published scores, does not append the experiment log, and does
not score HAI 22.04 or 23.05.
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

import numpy  # noqa: E402
from scripts.measure_baseline_table import (  # noqa: E402
    DATA,
    DECLARED_PERIOD_SECONDS,
    _read_hai,
    _read_prepared,
    _resolve,
)

from phos.eval.baseline_table import (  # noqa: E402
    FileScore,
    SeriesGrid,
    aggregate_scores,
    benign_matrix,
    median_period_seconds,
)
from phos.eval.grouped_rows import (  # noqa: E402
    GROUPED_ATLAS,
    GROUPED_CORPORA,
    GROUPED_HISTOGRAM,
    GROUPED_MINMAX,
    GROUPED_STEADY,
    GroupedRow,
    attacks_only_grouped_atlas,
    beyond_grouping,
    exposure_of,
    render_grouped_section,
    score_grouped_splits,
)

logger = logging.getLogger(__name__)

TABLE = ROOT / "eval_runs" / "v1" / "g1-baseline-table.md"
GROUPED_JSON = ROOT / "eval_runs" / "v1" / "g1-grouped-rows.json"
MARKER = "## Grouped rows"
PUBLISHED_ATLAS = "| hai-20.07 | yes | g1-baseline:atlas-mahalanobis | engine | 9 | 38 |"


def main() -> None:
    """Score the grouped corpora and append that section to the G1 table."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    published = TABLE.read_text(encoding="utf-8")
    if PUBLISHED_ATLAS not in published:
        raise SystemExit(
            "the published HAI 20.07 Atlas row is not 9/38; refusing to edit the table"
        )
    rows = (
        _hai(
            "hai-20.07",
            DATA / "hai-20.07",
            ("train1.csv.gz", "train2.csv.gz"),
            ("test1.csv.gz", "test2.csv.gz"),
            sep=";",
        ),
        _hai(
            "hai-21.03",
            DATA / "hai-21.03",
            ("train1.csv.gz", "train2.csv.gz", "train3.csv.gz"),
            ("test1.csv.gz", "test2.csv.gz", "test3.csv.gz", "test4.csv.gz", "test5.csv.gz"),
            sep=",",
            extra_roots=((DATA / "hai", "hai-21.03-"),),
        ),
        _prepared(
            "batadal",
            DATA / "batadal" / "batadal-train-prepared.csv",
            DATA / "batadal" / "batadal-test-prepared.csv",
            unscored=(),
        ),
        _prepared(
            "batch-distillation",
            DATA / "batch-distillation" / "batch-distillation-train-prepared.csv",
            DATA / "batch-distillation" / "batch-distillation-test-prepared.csv",
            unscored=("-1",),
        ),
        _prepared(
            "data4cyber",
            DATA / "data4cyber" / "data4cyber-s0-train-prepared.csv",
            DATA / "data4cyber" / "data4cyber-s1-test-prepared.csv",
            unscored=(),
        ),
    )
    names = tuple(row.corpus for row in rows)
    if names != GROUPED_CORPORA:
        raise SystemExit(f"grouped corpora {names} are not the declared list")
    section = render_grouped_section(rows)
    head = published.split(MARKER, maxsplit=1)[0].rstrip()
    TABLE.write_text(head + "\n\n" + section, encoding="utf-8")
    if PUBLISHED_ATLAS not in TABLE.read_text(encoding="utf-8"):
        raise SystemExit("writing the grouped section changed the published 9/38 row")
    GROUPED_JSON.write_text(
        json.dumps([_payload(row) for row in rows], indent=2) + "\n", encoding="utf-8"
    )
    print(section)


def _hai(
    corpus: str,
    directory: Path,
    trains: tuple[str, ...],
    tests: tuple[str, ...],
    *,
    sep: str,
    extra_roots: tuple[tuple[Path, str], ...] = (),
) -> GroupedRow:
    train_paths = [_resolve(directory, name, extra_roots) for name in trains]
    test_paths = [_resolve(directory, name, extra_roots) for name in tests]
    missing = [str(path) for path in (*train_paths, *test_paths) if not path.is_file()]
    if missing:
        raise SystemExit(f"{corpus} missing files: {', '.join(missing)}")
    logger.info("reading %s", corpus)
    train_grids = tuple(_read_hai(path, sep) for path in train_paths)
    test_grids = tuple((path.name, _read_hai(path, sep)) for path in test_paths)
    return _score(corpus, train_grids, test_grids)


def _prepared(
    corpus: str,
    train: Path,
    test: Path,
    *,
    unscored: tuple[str, ...],
) -> GroupedRow:
    missing = [str(path) for path in (train, test) if not path.is_file()]
    if missing:
        raise SystemExit(f"{corpus} missing files: {', '.join(missing)}")
    logger.info("reading %s", corpus)
    return _score(
        corpus,
        (_read_prepared(train, unscored),),
        ((test.name, _read_prepared(test, unscored)),),
    )


def _score(
    corpus: str,
    trains: tuple[SeriesGrid, ...],
    tests: tuple[tuple[str, SeriesGrid], ...],
) -> GroupedRow:
    features, matrix, excluded = benign_matrix(trains)
    facts, files = score_grouped_splits(
        features,
        matrix,
        (trains[0].timestamps[0], trains[-1].timestamps[-1]),
        tests,
    )
    file_scores = tuple(FileScore(name, scores) for name, scores, _caught in files)
    aggregate = {score.detector: score for score in aggregate_scores(file_scores)}
    atlas_ids: list[str] = []
    opponent_ids: dict[str, list[str]] = {
        name: [] for name in (GROUPED_MINMAX, GROUPED_STEADY, GROUPED_HISTOGRAM)
    }
    for _name, _scores, caught in files:
        atlas_ids.extend(caught[GROUPED_ATLAS])
        for name in opponent_ids:
            opponent_ids[name].extend(caught[name])
    exclusive = attacks_only_grouped_atlas(
        atlas_ids,
        (
            opponent_ids[GROUPED_MINMAX],
            opponent_ids[GROUPED_STEADY],
            opponent_ids[GROUPED_HISTOGRAM],
        ),
    )
    gap = beyond_grouping(
        aggregate[GROUPED_ATLAS].caught,
        (
            aggregate[GROUPED_MINMAX].caught,
            aggregate[GROUPED_STEADY].caught,
            aggregate[GROUPED_HISTOGRAM].caught,
        ),
    )
    periods = [median_period_seconds(grid.timestamps) for _name, grid in tests]
    measured = float(numpy.median(numpy.asarray(periods, dtype=numpy.float64)))
    exposure = exposure_of(corpus)
    seen = " Seen: the grouping constants were chosen on HAI 20.07 and held out on HAI 21.03."
    note = (
        f"Same fit as the published row: {facts.train_rows} benign rows, "
        f"{facts.atlas_signals} Atlas signals, {excluded} attack rows excluded. "
        f"Measured median step {measured:.6g} s; declared {DECLARED_PERIOD_SECONDS[corpus]:.6g} s. "
        "Each detector's published alerts pass through group_published_alerts. "
        "Beyond grouping uses the headline catch counts."
    )
    if exposure == "seen":
        note += seen
    if corpus == "batch-distillation":
        note += " Perturbation recall, not attack recall. Reported only."
    if corpus == "data4cyber":
        note += " Process-phase recall, not attack recall. Reported only."
    order = (GROUPED_ATLAS, GROUPED_MINMAX, GROUPED_STEADY, GROUPED_HISTOGRAM)
    logger.info(
        "scored %s atlas %s/%s beyond %s",
        corpus,
        aggregate[GROUPED_ATLAS].caught,
        aggregate[GROUPED_ATLAS].attacks,
        gap,
    )
    return GroupedRow(
        corpus=corpus,
        exposure=exposure,
        scores=tuple(aggregate[name] for name in order),
        beyond_grouping=gap,
        attacks_only_grouped_atlas=exclusive,
        note=note,
    )


def _payload(row: GroupedRow) -> dict[str, object]:
    return {
        "corpus": row.corpus,
        "exposure": row.exposure,
        "beyond_grouping": row.beyond_grouping,
        "attacks_only_grouped_atlas": list(row.attacks_only_grouped_atlas),
        "scores": [asdict(score) for score in row.scores],
        "note": row.note,
    }


if __name__ == "__main__":
    main()

"""Score HAI 22.04 and 23.05 once, grouped and ungrouped.

Declared in ADR 0101. Does not rescore any other corpus, does not append the
experiment log, and refuses to start when ``g1-clean-hai.json`` already exists.
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path

import numpy
import pandas

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from scripts.measure_baseline_table import (  # noqa: E402
    DECLARED_PERIOD_SECONDS,
    _frame_grid,
)
from scripts.measure_grouped_rows import _score as _grouped_score  # noqa: E402

from phos.eval.baseline_table import (  # noqa: E402
    CorpusReport,
    SeriesGrid,
    benign_matrix,
    median_period_seconds,
    score_splits,
)
from phos.eval.clean_hai import (  # noqa: E402
    CLEAN_CORPORA,
    CLEAN_JSON_NAME,
    HAI_2204_TRAIN_ATTACKS,
    HAI_2305_SUMMARY_HEADER_ATTACKS,
    HAI_2305_TRAINS,
    PUBLISHED_GUARD,
    assert_declared_counts,
    attack_runs,
    features_hai_2204,
    features_hai_2305,
    label_columns_hai_2305,
    splice_clean_json,
    splice_clean_markdown,
)
from phos.eval.grouped_rows import GroupedRow, exposure_of  # noqa: E402

logger = logging.getLogger(__name__)

DATA = ROOT / "data"
TABLE = ROOT / "eval_runs" / "v1" / "g1-baseline-table.md"
BASE_JSON = ROOT / "eval_runs" / "v1" / "g1-baseline-table.json"
CLEAN_JSON = ROOT / "eval_runs" / "v1" / CLEAN_JSON_NAME


def main() -> None:
    """Fit and score the two clean editions, then write the table once."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if CLEAN_JSON.exists():
        raise SystemExit(f"{CLEAN_JSON.name} already exists; this run is once")
    published = TABLE.read_text(encoding="utf-8")
    published_json = BASE_JSON.read_text(encoding="utf-8")
    if PUBLISHED_GUARD not in published:
        raise SystemExit("the published HAI 20.07 Atlas row is not 9/38")
    reports: list[CorpusReport] = []
    grouped: list[GroupedRow] = []
    for corpus in CLEAN_CORPORA:
        if exposure_of(corpus) is not None:
            raise SystemExit(f"{corpus} would be labelled seen")
        logger.info("reading %s", corpus)
        trains, tests = _load(corpus)
        report, row = _score(corpus, trains, tests)
        reports.append(report)
        grouped.append(row)
        logger.info(
            "scored %s atlas %s/%s grouped %s/%s beyond %s",
            corpus,
            report.scores[0].caught,
            report.scores[0].attacks,
            row.scores[0].caught,
            row.scores[0].attacks,
            row.beyond_grouping,
        )
    markdown = splice_clean_markdown(published, tuple(reports), tuple(grouped))
    rewritten = splice_clean_json(published_json, tuple(reports))
    if PUBLISHED_GUARD not in markdown:
        raise SystemExit("the splice removed the published 9/38 row")
    sidecar = {
        "corpora": CLEAN_CORPORA,
        "ungrouped": [_report_payload(report) for report in reports],
        "grouped": [asdict(row) for row in grouped],
    }
    TABLE.write_text(markdown, encoding="utf-8")
    BASE_JSON.write_text(rewritten, encoding="utf-8")
    CLEAN_JSON.write_text(json.dumps(sidecar, indent=2) + "\n", encoding="utf-8")
    print(markdown[markdown.index("## Grouped rows") :])


def _load(
    corpus: str,
) -> tuple[tuple[SeriesGrid, ...], tuple[tuple[str, SeriesGrid], ...]]:
    if corpus == "hai-22.04":
        return _load_2204()
    if corpus == "hai-23.05":
        return _load_2305()
    raise SystemExit(f"{corpus} is not in the clean run")


def _load_2204() -> tuple[tuple[SeriesGrid, ...], tuple[tuple[str, SeriesGrid], ...]]:
    directory = DATA / "hai-22.04"
    trains = tuple(_read_2204(directory / name) for name in HAI_2204_TRAIN_ATTACKS)
    for name, grid in zip(HAI_2204_TRAIN_ATTACKS, trains, strict=True):
        counted = attack_runs(grid.attack.tolist())
        if counted != HAI_2204_TRAIN_ATTACKS[name]:
            raise SystemExit(f"{name} has {counted} attack runs; the declaration says 0")
    tests = tuple(
        (name, _read_2204(directory / name))
        for name in ("test1.csv", "test2.csv", "test3.csv", "test4.csv")
    )
    return trains, tests


def _load_2305() -> tuple[tuple[SeriesGrid, ...], tuple[tuple[str, SeriesGrid], ...]]:
    directory = DATA / "hai-23.05"
    trains = tuple(_read_2305_train(directory / name) for name in HAI_2305_TRAINS)
    for name, grid in zip(HAI_2305_TRAINS, trains, strict=True):
        if attack_runs(grid.attack.tolist()) != 0:
            raise SystemExit(f"{name} was fit with an attack flag; trains have no label file")
    tests = tuple(
        (series, _read_2305_test(directory / series, directory / labels))
        for series, labels in (
            ("hai-test1.csv", "label-test1.csv"),
            ("hai-test2.csv", "label-test2.csv"),
        )
    )
    return trains, tests


def _read_2204(path: Path) -> SeriesGrid:
    frame = pandas.read_csv(path)
    columns = [str(column) for column in frame.columns]
    features = list(features_hai_2204(columns))
    return _frame_grid(frame, "timestamp", "Attack", features, ())


def _read_2305_train(path: Path) -> SeriesGrid:
    frame = pandas.read_csv(path)
    columns = [str(column) for column in frame.columns]
    features = list(features_hai_2305(columns))
    labelled = frame.copy()
    labelled["label"] = "0"
    return _frame_grid(labelled, "timestamp", "label", features, ())


def _read_2305_test(series_path: Path, label_path: Path) -> SeriesGrid:
    series = pandas.read_csv(series_path)
    labels = pandas.read_csv(label_path)
    label_columns_hai_2305([str(column) for column in labels.columns])
    features = list(features_hai_2305([str(column) for column in series.columns]))
    if len(series) != len(labels):
        raise SystemExit(f"{series_path.name} and {label_path.name} differ in length")
    labelled = series.copy()
    labelled["label"] = labels["label"].to_numpy()
    return _frame_grid(labelled, "timestamp", "label", features, ())


def _score(
    corpus: str,
    trains: tuple[SeriesGrid, ...],
    tests: tuple[tuple[str, SeriesGrid], ...],
) -> tuple[CorpusReport, GroupedRow]:
    counted = {name: attack_runs(grid.attack.tolist()) for name, grid in tests}
    assert_declared_counts(corpus, counted)
    features, matrix, excluded = benign_matrix(trains)
    facts, files = score_splits(
        features,
        matrix,
        (trains[0].timestamps[0], trains[-1].timestamps[-1]),
        tests,
    )
    report_attacks = sum(file.scores[0].attacks for file in files)
    expected = sum(counted.values())
    if report_attacks != expected:
        raise SystemExit(f"{corpus} scored {report_attacks} attacks, declared {expected}")
    periods = [median_period_seconds(grid.timestamps) for _name, grid in tests]
    measured = float(numpy.median(numpy.asarray(periods, dtype=numpy.float64)))
    note = (
        f"Clean run, scored once. Fit on {facts.train_rows} benign rows, "
        f"{facts.atlas_signals} Atlas signals, {excluded} attack rows excluded. "
        f"Declared denominator {expected}. Not labelled seen."
    )
    if corpus == "hai-23.05":
        note += (
            " Labels are joined by row, not by timestamp text. "
            f"summary_label2.txt says Attacks: {HAI_2305_SUMMARY_HEADER_ATTACKS} times; "
            "the label column has 38 runs, so the denominator is 52."
        )
    report = CorpusReport(
        corpus=corpus,
        judges=True,
        status="scored",
        note=note,
        sample_period_seconds=measured,
        declared_period_seconds=DECLARED_PERIOD_SECONDS[corpus],
        files=files,
    )
    grouped = _grouped_score(corpus, trains, tests)
    if grouped.exposure is not None:
        raise SystemExit(f"{corpus} grouped row was labelled {grouped.exposure}")
    return report, grouped


def _report_payload(report: CorpusReport) -> dict[str, object]:
    return {
        "corpus": report.corpus,
        "judges": report.judges,
        "status": report.status,
        "note": report.note,
        "sample_period_seconds": report.sample_period_seconds,
        "declared_period_seconds": report.declared_period_seconds,
        "scores": [asdict(score) for score in report.scores],
        "files": [asdict(file) for file in report.files],
    }


if __name__ == "__main__":
    main()

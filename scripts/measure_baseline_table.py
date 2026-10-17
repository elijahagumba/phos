"""Regenerate the G1 baseline table.

One Atlas configuration, the three checked opponents, and the corpora named in
``docs/v1-roadmap.md`` weeks 1-3. Writes ``eval_runs/v1/g1-baseline-table.md`` and
``.json``. Does not append the experiment log and does not reuse a frozen result name.

HAI 22.04 and 23.05 are Git LFS pointers (ADR 0087). They are rows, and they are not
scored. A judging corpus that cannot be scored counts as not won.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import asdict
from pathlib import Path

import numpy
import pandas

from phos.eval.baseline_report import recall_comparison, render_report
from phos.eval.baseline_table import (
    DETECTORS,
    ROUTING_REGISTERS,
    CorpusReport,
    FileScore,
    SeriesGrid,
    benign_matrix,
    grid_from_columns,
    median_period_seconds,
    score_splits,
)
from phos.eval.datasets import _label_key, default_attack_when

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT_DIR = ROOT / "eval_runs" / "v1"
HAI_LABELS = ("attack", "attack_P1", "attack_P2", "attack_P3")

# Declared before the run. 180 samples is this many seconds on the scored index.
# The tail is not rescaled when a file's median step disagrees.
DECLARED_PERIOD_SECONDS = {
    "hai-20.07": 1.0,
    "hai-21.03": 1.0,
    "hai-22.04": 1.0,
    "hai-23.05": 1.0,
    "batadal": 3600.0,
    "batch-distillation": 10.0,
    "data4cyber": 1.0,
}


def main() -> None:
    """Score the declared files once and write the table."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    reports = (
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
        _absent("hai-22.04", "Git LFS pointer (ADR 0087); the CSV is not on disk"),
        _absent("hai-23.05", "Git LFS pointer (ADR 0087); the CSV is not on disk"),
        _prepared(
            "batadal",
            DATA / "batadal" / "batadal-train-prepared.csv",
            DATA / "batadal" / "batadal-test-prepared.csv",
            judges=True,
            unscored=(),
        ),
        _prepared(
            "batch-distillation",
            DATA / "batch-distillation" / "batch-distillation-train-prepared.csv",
            DATA / "batch-distillation" / "batch-distillation-test-prepared.csv",
            judges=False,
            unscored=("-1",),
        ),
        _prepared(
            "data4cyber",
            DATA / "data4cyber" / "data4cyber-s0-train-prepared.csv",
            DATA / "data4cyber" / "data4cyber-s1-test-prepared.csv",
            judges=False,
            unscored=(),
        ),
    )
    text = render_report(reports)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "g1-baseline-table.md").write_text(text)
    payload = {
        "result_names": list(DETECTORS),
        "alert_threshold": 3.0,
        "alerts_per_shift": 8,
        "corpora": [_payload(report) for report in reports],
    }
    (OUT_DIR / "g1-baseline-table.json").write_text(json.dumps(payload, indent=2) + "\n")
    print(text)


def _hai(
    corpus: str,
    directory: Path,
    trains: tuple[str, ...],
    tests: tuple[str, ...],
    *,
    sep: str,
    extra_roots: tuple[tuple[Path, str], ...] = (),
) -> CorpusReport:
    """Score one HAI version. A missing file makes the whole version not scored."""
    train_paths = [_resolve(directory, name, extra_roots) for name in trains]
    test_paths = [_resolve(directory, name, extra_roots) for name in tests]
    missing = [str(path) for path in (*train_paths, *test_paths) if not path.is_file()]
    if missing:
        return _absent(corpus, "missing files: " + ", ".join(missing))
    logger.info("reading %s", corpus)
    try:
        train_grids = [_read_hai(path, sep) for path in train_paths]
        test_grids = [(path.name, _read_hai(path, sep)) for path in test_paths]
        return _score(corpus, judges=True, trains=tuple(train_grids), tests=tuple(test_grids))
    except (OSError, ValueError) as error:
        return _absent(corpus, str(error))


def _prepared(
    corpus: str,
    train: Path,
    test: Path,
    *,
    judges: bool,
    unscored: tuple[str, ...],
) -> CorpusReport:
    """Score one prepared CSV pair. Distillation and Data4Cyber do not judge."""
    missing = [str(path) for path in (train, test) if not path.is_file()]
    if missing:
        return _absent(corpus, "missing files: " + ", ".join(missing), judges=judges)
    logger.info("reading %s", corpus)
    try:
        train_grid = _read_prepared(train, unscored)
        test_grid = _read_prepared(test, unscored)
        return _score(corpus, judges=judges, trains=(train_grid,), tests=((test.name, test_grid),))
    except (OSError, ValueError) as error:
        return _absent(corpus, str(error), judges=judges)


def _score(
    corpus: str,
    *,
    judges: bool,
    trains: tuple[SeriesGrid, ...],
    tests: tuple[tuple[str, SeriesGrid], ...],
) -> CorpusReport:
    features, matrix, excluded = benign_matrix(trains)
    facts, files = score_splits(
        features,
        matrix,
        (trains[0].timestamps[0], trains[-1].timestamps[-1]),
        tests,
    )
    periods = [median_period_seconds(grid.timestamps) for _name, grid in tests]
    measured = float(numpy.median(numpy.asarray(periods, dtype=numpy.float64)))
    declared = DECLARED_PERIOD_SECONDS[corpus]
    return CorpusReport(
        corpus=corpus,
        judges=judges,
        status="scored" if judges else "reported",
        note=_note(corpus, declared, measured, facts.train_rows, facts.atlas_signals, excluded),
        sample_period_seconds=measured,
        declared_period_seconds=declared,
        files=files,
    )


def _note(
    corpus: str,
    declared: float,
    measured: float,
    train_rows: int,
    atlas_signals: int,
    excluded_attacks: int,
) -> str:
    seconds = declared * 180.0
    text = (
        f"Fit on {train_rows} benign rows, {atlas_signals} Atlas signals, "
        f"{excluded_attacks} attack rows excluded from the fit. "
        f"Delta is 180 samples on each file's scored index "
        f"({seconds:.6g} seconds at the declared period), not rescaled. "
        "Point metrics drop unscored rows and collapse a timestamp to one point. "
        "The budget counts each feature alert. "
    )
    if declared > 0.0 and abs(measured - declared) / declared > 0.01:
        text += (
            f"measured median step {measured:.6g} s, declared {declared:.6g} s. "
            "Delta stays 180 samples."
        )
    else:
        text += "Measured step matches the declared period."
    if corpus == "batch-distillation":
        text += " Perturbation recall, not attack recall. Reported only."
    if corpus == "data4cyber":
        text += (
            " Process-phase recall, not attack recall. Reported only. Not a control-room budget."
        )
    return text


def _absent(corpus: str, reason: str, *, judges: bool | None = None) -> CorpusReport:
    judges_row = corpus in {"hai-20.07", "hai-21.03", "hai-22.04", "hai-23.05", "batadal"}
    if judges is not None:
        judges_row = judges
    return CorpusReport(
        corpus=corpus,
        judges=judges_row,
        status="not_scored",
        note=reason,
        sample_period_seconds=None,
        declared_period_seconds=DECLARED_PERIOD_SECONDS.get(corpus),
        files=(),
    )


def _resolve(directory: Path, name: str, extra_roots: tuple[tuple[Path, str], ...]) -> Path:
    direct = directory / name
    if direct.is_file():
        return direct
    for root, prefix in extra_roots:
        candidate = root / f"{prefix}{name}"
        if candidate.is_file():
            return candidate
    return direct


def _read_hai(path: Path, sep: str) -> SeriesGrid:
    frame = pandas.read_csv(path, sep=sep)
    columns = [str(column) for column in frame.columns]
    if columns[0] != "time" or tuple(columns[-4:]) != HAI_LABELS:
        raise ValueError(f"{path.name} is not a HAI state file: {columns[:1]} ... {columns[-4:]}")
    features = [column for column in columns[1:-4] if column not in ROUTING_REGISTERS]
    return _frame_grid(frame, "time", "attack", features, ())


def _read_prepared(path: Path, unscored: tuple[str, ...]) -> SeriesGrid:
    frame = pandas.read_csv(path)
    skip = set(ROUTING_REGISTERS) | {"timestamp", "label", *HAI_LABELS}
    features = []
    for column in frame.columns:
        name = str(column)
        if name in skip:
            continue
        numeric = pandas.to_numeric(frame[column], errors="coerce")
        if numeric.notna().any():
            features.append(name)
    if not features:
        raise ValueError(f"{path.name} has no numeric state column")
    return _frame_grid(frame, "timestamp", "label", features, unscored)


def _frame_grid(
    frame: pandas.DataFrame,
    time_column: str,
    label_column: str,
    features: list[str],
    unscored_values: tuple[str, ...],
) -> SeriesGrid:
    stamps = pandas.to_datetime(frame[time_column], utc=True)
    timestamps = [stamp.to_pydatetime() for stamp in stamps]
    attack, unscored = _labels(frame[label_column].tolist(), unscored_values)
    values = frame[features].apply(pandas.to_numeric, errors="coerce").to_numpy(dtype=numpy.float64)
    return grid_from_columns(timestamps, features, values, attack, unscored)


def _labels(
    labels: list[object], unscored_values: tuple[str, ...]
) -> tuple[list[bool], list[bool]]:
    keys = frozenset(_label_key(value) for value in unscored_values)
    attack: list[bool] = []
    unscored: list[bool] = []
    for value in labels:
        if _missing(value):
            attack.append(False)
            unscored.append(False)
            continue
        if keys and _label_key(value) in keys:
            attack.append(False)
            unscored.append(True)
            continue
        attack.append(default_attack_when(value))
        unscored.append(False)
    return attack, unscored


def _missing(value: object) -> bool:
    if value is None or value is pandas.NA:
        return True
    if isinstance(value, float | numpy.floating):
        return math.isnan(float(value))
    return False


def _payload(report: CorpusReport) -> dict[str, object]:
    return {
        "corpus": report.corpus,
        "judges": report.judges,
        "status": report.status,
        "note": report.note,
        "sample_period_seconds": report.sample_period_seconds,
        "declared_period_seconds": report.declared_period_seconds,
        "comparison": recall_comparison(report),
        "scores": [asdict(score) for score in report.scores],
        "files": [_file_payload(file) for file in report.files],
    }


def _file_payload(file: FileScore) -> dict[str, object]:
    return {"file": file.file, "scores": [asdict(score) for score in file.scores]}


if __name__ == "__main__":
    main()

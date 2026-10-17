"""Check once whether `phos.atlas.consistency` reproduces ADR 0104's scored alert list on real HAI.

Declared in ADR 0110. ADR 0104's script grouped the frozen candidate's float32 scores into events
as float64; the port, like the frozen file's own ``run``, groups them as float32. This command
compares, on every clean HAI test file, the reference list (ADR 0104's path) with the port's list
two ways: as written (float32 grouping) and with the port's scores cast to float64 before
grouping. It also compares the float32 feature scores. It writes the record whatever the answer.
It reports the port's own-grouping catch beside ADR 0104's; that is a reproduction check, not a
new score. It does not append the experiment log. Refuses to start when the output exists.
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

from phos.atlas import consistency  # noqa: E402
from phos.eval.baseline_table import (  # noqa: E402
    DetectorScore,
    FileScore,
    SeriesGrid,
    _score_detector,
    aggregate_scores,
)
from phos.eval.candidate_look import (  # noqa: E402
    CANDIDATE_RELATIVE,
    CLEAN_CORPORA,
    assert_candidate_bytes,
    label_free_record,
    train_record,
)

logger = logging.getLogger(__name__)

OUT = ROOT / "eval_runs" / "v1" / "consistency-identity-hai.json"
MARKDOWN = ROOT / "eval_runs" / "v1" / "consistency-identity-hai.md"
#: ADR 0104's own-grouping headline. Not a new measurement.
REFERENCE_CAUGHT: dict[str, tuple[int, int]] = {"hai-22.04": (53, 58), "hai-23.05": (36, 52)}
REFERENCE = "adr-0104-path"
PORT_AS_WRITTEN = "port-float32-grouping"
PORT_FLOAT64 = "port-float64-grouping"

Alert = tuple[int, int, float]


def main() -> None:
    """Compare the port with ADR 0104's path on both clean editions and write one record."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if OUT.exists():
        raise SystemExit(f"{OUT.name} already exists; this run is once")
    path = ROOT / CANDIDATE_RELATIVE
    assert_candidate_bytes(path.read_bytes())
    frozen = _load_frozen(path)
    rows: list[dict[str, object]] = []
    for corpus in CLEAN_CORPORA:
        logger.info("reading %s", corpus)
        trains, tests = _load(corpus)
        train_records = [train_record(grid) for grid in trains]
        test_records = [label_free_record(grid) for _name, grid in tests]
        logger.info("fitting the frozen file on %s", corpus)
        theirs = list(frozen.feature_scores(train_records, test_records))
        logger.info("fitting the port on %s", corpus)
        model = consistency.fit(
            [
                consistency.TrainFile(
                    values=numpy.asarray(r["values"], dtype=numpy.float64),
                    attack=numpy.asarray(r["attack"], dtype=numpy.bool_),
                )
                for r in train_records
            ]
        )
        lists: dict[str, list[tuple[str, SeriesGrid, list[Alert]]]] = {
            REFERENCE: [],
            PORT_AS_WRITTEN: [],
            PORT_FLOAT64: [],
        }
        scores_identical = True
        for (name, grid), record, reference_scores in zip(tests, test_records, theirs, strict=True):
            time = numpy.asarray(record["time"], dtype=numpy.float64)
            ours = consistency.feature_scores(model, grid.values)
            same = ours.dtype == reference_scores.dtype and bool(
                numpy.array_equal(ours, reference_scores)
            )
            scores_identical &= same
            reference = _zip(
                frozen._budget(
                    frozen._events(numpy.asarray(reference_scores, dtype=numpy.float64)), time
                )
            )
            as_written = _zip(consistency.budget_alerts(consistency.events(ours), time))
            widened = _zip(
                consistency.budget_alerts(
                    consistency.events(numpy.asarray(ours, dtype=numpy.float64)),
                    time,
                )
            )
            lists[REFERENCE].append((name, grid, reference))
            lists[PORT_AS_WRITTEN].append((name, grid, as_written))
            lists[PORT_FLOAT64].append((name, grid, widened))
            logger.info(
                "%s %s scores %s, as written %s, float64 %s",
                corpus,
                name,
                same,
                as_written == reference,
                widened == reference,
            )
        expected = REFERENCE_CAUGHT[corpus]
        reference_score = _caught(REFERENCE, lists[REFERENCE])
        if (reference_score.caught, reference_score.attacks) != expected:
            raise SystemExit(
                f"{corpus} ADR 0104's path caught {reference_score.caught}/"
                f"{reference_score.attacks}, not {expected[0]}/{expected[1]}; nothing written"
            )
        for label in (PORT_AS_WRITTEN, PORT_FLOAT64):
            score = _caught(label, lists[label])
            rows.append(
                {
                    "corpus": corpus,
                    "port_path": label,
                    "feature_scores_identical": scores_identical,
                    "alert_lists_identical": all(
                        mine == ref
                        for (_n, _g, mine), (_m, _h, ref) in zip(
                            lists[label], lists[REFERENCE], strict=True
                        )
                    ),
                    "alerts": sum(len(alerts) for _n, _g, alerts in lists[label]),
                    "reference_alerts": sum(len(alerts) for _n, _g, alerts in lists[REFERENCE]),
                    "alerts_not_in_reference": sum(
                        len(set(mine) - set(ref))
                        for (_n, _g, mine), (_m, _h, ref) in zip(
                            lists[label], lists[REFERENCE], strict=True
                        )
                    ),
                    "own_grouping_caught": score.caught,
                    "reference_caught": expected[0],
                    "attacks": score.attacks,
                }
            )
    OUT.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    MARKDOWN.write_text(_render(rows), encoding="utf-8")
    print(_render(rows))


def _zip(budgeted: tuple[list[int], list[int], list[float]]) -> list[Alert]:
    rows, columns, scores = budgeted
    return [
        (int(row), int(column), float(score))
        for row, column, score in zip(rows, columns, scores, strict=True)
    ]


def _caught(label: str, files: list[tuple[str, SeriesGrid, list[Alert]]]) -> DetectorScore:
    scored = [
        FileScore(
            name,
            (
                _score_detector(
                    label,
                    [(row, grid.features[column], score) for row, column, score in alerts],
                    grid,
                ),
            ),
        )
        for name, grid, alerts in files
    ]
    return aggregate_scores(scored)[0]


def _render(rows: list[dict[str, object]]) -> str:
    lines = [
        "# Consistency detector against ADR 0104's scored path, on clean HAI",
        "",
        "Declared in ADR 0110. A reproduction check, not a new score. The reference is ADR 0104's",
        "path: the frozen file's float32 scores, grouped as float64.",
        "",
        "| Edition | Port path | Scores identical | Alert lists identical | Alerts | "
        "Reference alerts | Alerts not in reference | Caught | Reference caught |",
        "|---|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['corpus']} | {row['port_path']} | {row['feature_scores_identical']} | "
            f"{row['alert_lists_identical']} | {row['alerts']} | {row['reference_alerts']} | "
            f"{row['alerts_not_in_reference']} | {row['own_grouping_caught']}/{row['attacks']} | "
            f"{row['reference_caught']}/{row['attacks']} |"
        )
    lines.append("")
    return "\n".join(lines)


def _load_frozen(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("sandbox_candidate_frozen", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


if __name__ == "__main__":
    main()

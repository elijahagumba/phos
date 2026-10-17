"""A2's status for `atlas-v1-consistency` on the five judging corpora, with a chance column.

Declared in ADR 0115. Scores the detector once on HAI 20.07 and 21.03 through the lab's scorer
(the sandbox harness's figures were 37/38 and 42/50; whether the lab reproduces them is reported,
not enforced). Computes ADR 0106's chance null on HAI 20.07, 21.03 and BATADAL. Assembles one
table with the published rows for HAI 22.04, 23.05 (ADR 0104, ADR 0106) and BATADAL (ADR 0113).
Does not append the experiment log. Refuses to start when the output already exists.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import numpy

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from scripts.measure_baseline_table import (  # noqa: E402
    DATA,
    DECLARED_PERIOD_SECONDS,
    _read_hai,
    _read_prepared,
    _resolve,
)
from scripts.measure_candidate_checks import _chance_row  # noqa: E402

from phos.atlas import consistency  # noqa: E402
from phos.eval.baseline_table import (  # noqa: E402
    FileScore,
    SeriesGrid,
    _score_detector,
    aggregate_scores,
)
from phos.eval.candidate_checks import CHANCE_SEED  # noqa: E402

logger = logging.getLogger(__name__)

OUT = ROOT / "eval_runs" / "v1" / "a2-status.json"
MARKDOWN = ROOT / "eval_runs" / "v1" / "a2-status.md"

HAI_SOURCES: dict[str, tuple[Path, tuple[str, ...], tuple[str, ...], str]] = {
    "hai-20.07": (
        DATA / "hai-20.07",
        ("train1.csv.gz", "train2.csv.gz"),
        ("test1.csv.gz", "test2.csv.gz"),
        ";",
    ),
    "hai-21.03": (
        DATA / "hai-21.03",
        ("train1.csv.gz", "train2.csv.gz", "train3.csv.gz"),
        ("test1.csv.gz", "test2.csv.gz", "test3.csv.gz", "test4.csv.gz", "test5.csv.gz"),
        ",",
    ),
}
EXTRA_ROOTS = ((DATA / "hai", "hai-21.03-"),)
#: The sandbox harness's figures for the frozen candidate (experiments/2026-10-04-sandbox).
SANDBOX: dict[str, tuple[int, int]] = {"hai-20.07": (37, 38), "hai-21.03": (42, 50)}
#: Published rows, not scored again: (caught, attacks, source).
PUBLISHED_CONSISTENCY: dict[str, tuple[int, int, str]] = {
    "hai-22.04": (53, 58, "ADR 0104"),
    "hai-23.05": (36, 52, "ADR 0104"),
    "batadal": (5, 5, "ADR 0113"),
}
#: Best grouped checked opponent per corpus: (name, caught, source).
BEST_OPPONENT: dict[str, tuple[str, int, str]] = {
    "hai-20.07": ("g1-grouped:simple-minmax", 32, "ADR 0100"),
    "hai-21.03": ("g1-grouped:simple-minmax", 36, "ADR 0100"),
    "hai-22.04": ("g1-grouped:simple-minmax", 10, "ADR 0102"),
    "hai-23.05": ("g1-grouped:simple-minmax", 6, "ADR 0102"),
    "batadal": ("g1-grouped:simple-minmax", 3, "ADR 0100"),
}
#: ADR 0106's chance rows, not drawn again.
PUBLISHED_CHANCE: dict[str, dict[str, float | int]] = {
    "hai-22.04": {"draws": 500, "mean_caught": 3.808, "percentile_95": 7.0, "max_caught": 9},
    "hai-23.05": {"draws": 500, "mean_caught": 3.06, "percentile_95": 6.0, "max_caught": 8},
}
EXPOSURE: dict[str, str] = {
    "hai-20.07": "development: the candidate was tuned against it",
    "hai-21.03": "held out once by the sandbox, now seen",
    "hai-22.04": "scored once (ADR 0104), now seen",
    "hai-23.05": "scored once (ADR 0104), now seen",
    "batadal": "scored once (ADR 0113), now seen",
}
ORDER = ("hai-20.07", "hai-21.03", "hai-22.04", "hai-23.05", "batadal")


def main() -> None:
    """Score two HAI editions, draw three chance rows, and write the five-corpus table."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if OUT.exists():
        raise SystemExit(f"{OUT.name} already exists; this run is once")
    caught: dict[str, tuple[int, int, str]] = dict(PUBLISHED_CONSISTENCY)
    chance: dict[str, dict[str, float | int]] = dict(PUBLISHED_CHANCE)
    reproduced: dict[str, bool] = {}
    for corpus, (directory, trains, tests, sep) in HAI_SOURCES.items():
        if DECLARED_PERIOD_SECONDS[corpus] != 1.0:
            raise SystemExit(f"{corpus} is not declared at 1 s")
        train_grids = [_read_hai(_resolve(directory, name, EXTRA_ROOTS), sep) for name in trains]
        test_grids = [
            (name, _read_hai(_resolve(directory, name, EXTRA_ROOTS), sep)) for name in tests
        ]
        logger.info("fitting %s", corpus)
        score = _score(train_grids, test_grids)
        caught[corpus] = (score[0], score[1], "this run")
        reproduced[corpus] = score == SANDBOX[corpus]
        logger.info("%s caught %d/%d", corpus, score[0], score[1])
        chance[corpus] = _chance_row(
            tuple(test_grids), numpy.random.Generator(numpy.random.PCG64(CHANCE_SEED))
        )
    batadal = _read_prepared(DATA / "batadal" / "batadal-test-prepared.csv", ())
    chance["batadal"] = _chance_row(
        (("batadal-test-prepared.csv", batadal),),
        numpy.random.Generator(numpy.random.PCG64(CHANCE_SEED)),
    )
    rows = []
    for corpus in ORDER:
        mine, attacks, source = caught[corpus]
        opponent, theirs, opponent_source = BEST_OPPONENT[corpus]
        ceiling = int(chance[corpus]["max_caught"])
        rows.append(
            {
                "corpus": corpus,
                "exposure": EXPOSURE[corpus],
                "consistency_caught": mine,
                "attacks": attacks,
                "consistency_source": source,
                "best_grouped_checked_opponent": opponent,
                "opponent_caught": theirs,
                "opponent_source": opponent_source,
                "strictly_higher": mine > theirs,
                "chance": chance[corpus],
                "above_every_chance_draw": mine > ceiling,
            }
        )
    payload = {
        "detector": consistency.RESULT_NAME,
        "rows": rows,
        "strictly_higher": sum(1 for row in rows if row["strictly_higher"]),
        "strictly_higher_and_above_every_chance_draw": sum(
            1 for row in rows if row["strictly_higher"] and row["above_every_chance_draw"]
        ),
        "sandbox_reproduced": reproduced,
    }
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    MARKDOWN.write_text(_render(payload), encoding="utf-8")
    print(_render(payload))


def _score(trains: list[SeriesGrid], tests: list[tuple[str, SeriesGrid]]) -> tuple[int, int]:
    model = consistency.fit(
        [
            consistency.TrainFile(
                values=grid.values, attack=numpy.asarray(grid.attack, dtype=numpy.bool_)
            )
            for grid in trains
        ]
    )
    files = []
    for name, grid in tests:
        time = numpy.asarray([stamp.timestamp() for stamp in grid.timestamps], dtype=numpy.float64)
        rows, columns, scores = consistency.budget_alerts(
            consistency.events(consistency.feature_scores(model, grid.values)), time
        )
        cells = [
            (int(row), grid.features[int(column)], float(score))
            for row, column, score in zip(rows, columns, scores, strict=True)
        ]
        files.append(FileScore(name, (_score_detector(consistency.RESULT_NAME, cells, grid),)))
    total = aggregate_scores(files)[0]
    return total.caught, total.attacks


def _render(payload: dict[str, object]) -> str:
    rows = payload["rows"]
    assert isinstance(rows, list)
    lines = [
        "# A2 status: atlas-v1-consistency on the five judging corpora",
        "",
        "Declared in ADR 0115. Recall within budget, 8 alerts per 8-hour shift. The opponent is",
        "the best grouped checked opponent. Chance is ADR 0106's null: 8 random rows per shift,",
        "500 draws, seed 20261010.",
        "",
        "| Corpus | Exposure | Consistency | Best grouped checked opponent | Strictly higher | "
        "Chance mean / 95th / max | Above every chance draw |",
        "|---|---|---:|---:|---|---:|---|",
    ]
    for row in rows:
        c = row["chance"]
        lines.append(
            f"| {row['corpus']} | {row['exposure']} | "
            f"{row['consistency_caught']}/{row['attacks']} ({row['consistency_source']}) | "
            f"{row['opponent_caught']}/{row['attacks']} ({row['opponent_source']}) | "
            f"{'yes' if row['strictly_higher'] else 'no'} | "
            f"{c['mean_caught']:.3f} / {c['percentile_95']:g} / {c['max_caught']} | "
            f"{'yes' if row['above_every_chance_draw'] else 'no'} |"
        )
    lines.extend(
        [
            "",
            f"Strictly higher: {payload['strictly_higher']} of 5. "
            f"Strictly higher and above every chance draw: "
            f"{payload['strictly_higher_and_above_every_chance_draw']} of 5.",
            f"Sandbox figures reproduced by the lab scorer: {payload['sandbox_reproduced']}.",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    main()

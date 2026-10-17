#!/usr/bin/env python3
"""ADR 0117's gate for `atlas-plant-map-v1`: one look at the four validation corpora (ADR 0142).

Scores the champion (`atlas-v1-consistency`) and the challenger (attempt 6 of the `plant-map`
arena task, ADR 0137) once each on HAI 21.03, HAI 22.04, HAI 23.05 and BATADAL, at 8 alerts per
8-hour shift, with the readers, windows and scorer the champion's published rows used (ADR 0104,
ADR 0113, `scripts/measure_a2_status.py`), and draws ADR 0106's chance null on each. Then applies
ADR 0117 §3.3:

- on every corpus the challenger catches no fewer attacks than the champion;
- on at least one HAI edition it catches strictly more;
- wherever the champion is above every chance draw, so is the challenger.

Two passes, so a broken reader cannot spend the look:

1. Every corpus is read, its role file is checked against the reader's columns, and the champion
   and the chance null are scored. If any differs from its published value (`PUBLISHED`), the
   script stops here, writes nothing, and the challenger has not been fitted.
2. The challenger is fitted and scored on each corpus, and the verdict is written once.

The challenger reads each corpus's role file (`data/<corpus>/roles.toml`, ADR 0141). A corpus
without one (BATADAL) gives it every signal without a role, so there it learns no map and is the
champion exactly (ADR 0127). The record goes to ``eval_runs/gates/plant-map-gate.json``; the
script refuses to run when it exists. Nothing here appends ``eval_runs/log.jsonl``. ADR 0117
§3.4: Elijah accepts the ADR that records the result.

Usage, on a machine that holds the four corpora::

    uv run python scripts/gate.py
"""

from __future__ import annotations

import hashlib
import json
import logging
import subprocess
import sys
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final

import numpy

ROOT: Final = Path(__file__).resolve().parents[1]
for entry in (ROOT, ROOT / "src"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from scripts.arena import map_settings_from, scorer_sha256  # noqa: E402
from scripts.measure_a2_status import EXTRA_ROOTS, HAI_SOURCES  # noqa: E402
from scripts.measure_baseline_table import (  # noqa: E402
    DATA,
    DECLARED_PERIOD_SECONDS,
    _read_hai,
    _read_prepared,
    _resolve,
)
from scripts.measure_candidate_checks import _chance_row  # noqa: E402
from scripts.measure_clean_hai import _load  # noqa: E402

from phos.atlas import consistency  # noqa: E402
from phos.atlas import plant_map_detector as challenger  # noqa: E402
from phos.atlas.consistency_windows import FROZEN_WINDOWS, Windows, windows_for_period  # noqa: E402
from phos.atlas.signal_roles import RoleDeclaration, SignalRoles, load_roles  # noqa: E402
from phos.eval.baseline_table import (  # noqa: E402
    FileScore,
    SeriesGrid,
    _score_detector,
    aggregate_scores,
)
from phos.eval.candidate_checks import CHANCE_SEED  # noqa: E402
from phos.eval.clean_hai import CLEAN_CORPORA  # noqa: E402

logger = logging.getLogger("phos.gate")

OUT: Final = ROOT / "eval_runs" / "gates" / "plant-map-gate.json"
CANDIDATE: Final = (
    ROOT / "experiments" / "arena" / "plant-map" / "plant-map-v1" / "candidate-6.json"
)
CORPORA: Final = ("hai-21.03", "hai-22.04", "hai-23.05", "batadal")
HAI_EDITIONS: Final = ("hai-21.03", "hai-22.04", "hai-23.05")

#: The champion's published rows: (caught, attacks, chance max), from `eval_runs/v1/a2-status.json`.
PUBLISHED: Final[dict[str, tuple[int, int, int]]] = {
    "hai-21.03": (42, 50, 8),
    "hai-22.04": (53, 58, 9),
    "hai-23.05": (36, 52, 8),
    "batadal": (5, 5, 5),
}

#: The files that decide what the challenger alerts on, the candidate, and the role files it reads.
#: Their sha256 is declared in ADR 0142; the gate refuses to run on anything else.
DECLARED_FILES: Final = (
    "src/phos/atlas/consistency.py",
    "src/phos/atlas/consistency_windows.py",
    "src/phos/atlas/plant_map_detector.py",
    "src/phos/atlas/plant_map_fit.py",
    "src/phos/atlas/plant_map_model.py",
    "src/phos/atlas/plant_map_select.py",
    "src/phos/atlas/signal_roles.py",
    "experiments/arena/plant-map/plant-map-v1/candidate-6.json",
    "data/hai-21.03/roles.toml",
    "data/hai-22.04/roles.toml",
    "data/hai-23.05/roles.toml",
)
DECLARED_SHA256: Final = "b6d384ace4b835843a62c06a8daf7db2ddc86f40a25f47a72e64e535adf70d60"
#: Paths whose local changes would change what runs. Anything else (notes, drafts) may be dirty.
GUARDED: Final = ("src", "scripts", "experiments", "data", "pyproject.toml", "uv.lock")

Tests = tuple[tuple[str, SeriesGrid], ...]
Alerts = tuple[list[int], list[int], list[float]]


@dataclass(frozen=True)
class Corpus:
    """One validation corpus as its published rows read it."""

    name: str
    trains: tuple[SeriesGrid, ...]
    tests: Tests
    period: float

    @property
    def windows(self) -> Windows:
        """The frozen windows at 1 s, else ADR 0113's windows for the declared period."""
        return FROZEN_WINDOWS if self.period == 1.0 else windows_for_period(self.period)

    def train_files(self) -> list[consistency.TrainFile]:
        """The training files; attack rows are only left out of fits."""
        return [
            consistency.TrainFile(
                values=g.values, attack=numpy.asarray(g.attack, dtype=numpy.bool_)
            )
            for g in self.trains
        ]

    def stamps(self) -> list[numpy.ndarray]:
        """Each test file's timestamps in Unix seconds, for the shift budget."""
        return [
            numpy.asarray([s.timestamp() for s in g.timestamps], dtype=numpy.float64)
            for _n, g in self.tests
        ]


def declared_sha256() -> str:
    """sha256 over each declared file's path and bytes, in order."""
    digest = hashlib.sha256()
    for name in DECLARED_FILES:
        digest.update(name.encode("utf-8") + b"\0" + (ROOT / name).read_bytes() + b"\0")
    return digest.hexdigest()


def committed_head() -> str:
    """The commit the gate runs on. Stops if a guarded path differs from it."""
    status = subprocess.run(
        ["git", "status", "--porcelain", "--", *GUARDED],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    if status.strip():
        raise SystemExit(f"local changes to what the gate runs; commit or stash them:\n{status}")
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()


def read_corpus(name: str) -> Corpus:
    """Read one corpus with the reader its published champion row used."""
    if name == "hai-21.03":
        directory, trains, tests, sep = HAI_SOURCES[name]
        return Corpus(
            name,
            tuple(_read_hai(_resolve(directory, n, EXTRA_ROOTS), sep) for n in trains),
            tuple((n, _read_hai(_resolve(directory, n, EXTRA_ROOTS), sep)) for n in tests),
            DECLARED_PERIOD_SECONDS[name],
        )
    if name in ("hai-22.04", "hai-23.05"):
        trains_, tests_ = _load(name)
        return Corpus(name, trains_, tests_, DECLARED_PERIOD_SECONDS[name])
    if name == "batadal":
        train = _read_prepared(DATA / "batadal" / "batadal-train-prepared.csv", ())
        test = _read_prepared(DATA / "batadal" / "batadal-test-prepared.csv", ())
        return Corpus(
            name, (train,), (("batadal-test-prepared.csv", test),), DECLARED_PERIOD_SECONDS[name]
        )
    raise SystemExit(f"{name} is not a validation corpus")


def roles_for(path: Path, features: Sequence[str]) -> SignalRoles:
    """A corpus's declared roles over exactly the columns its reader returns.

    With no role file, every signal is declared without a role, so the map learns nothing.
    A role file must declare every column the reader returns; columns the reader drops (labels,
    unscored points) are dropped from the roles too, with any loop that names one.
    """
    if not path.is_file():
        return SignalRoles(
            [
                RoleDeclaration(signal=f, role=None, cited="none", reason="no role file")
                for f in features
            ],
            features,
            source=f"no role file at {path.parent.name}/{path.name} (ADR 0141)",
        )
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    declared = [str(point["signal"]) for point in raw["points"]]
    missing = sorted(set(features) - set(declared))
    if missing:
        raise SystemExit(f"{path}: the role file does not declare {missing}")
    full = load_roles(path, declared)
    keep = set(features)
    loops = [
        loop
        for loop in full.loops
        if (loop.reading is None or loop.reading in keep)
        and (loop.setpoint is None or loop.setpoint in keep)
        and set(loop.outputs) <= keep
    ]
    return SignalRoles(
        [d for d in full.declarations if d.signal in keep], features, full.source, loops
    )


def caught(name: str, tests: Tests, alerts: Sequence[Alerts]) -> tuple[int, int]:
    """Attacks caught and attacks in all, by the scorer every published row used."""
    files = []
    for (file, grid), (rows, columns, scores) in zip(tests, alerts, strict=True):
        cells = [
            (int(r), grid.features[int(c)], float(s))
            for r, c, s in zip(rows, columns, scores, strict=True)
        ]
        files.append(FileScore(file, (_score_detector(name, cells, grid),)))
    total = aggregate_scores(files)[0]
    return total.caught, total.attacks


def chance_generator(name: str, shared: numpy.random.Generator) -> numpy.random.Generator:
    """The generator the corpus's published chance row drew from.

    `scripts/measure_candidate_checks.py` drew HAI 22.04 and then 23.05 from one stream seeded
    once; `scripts/measure_a2_status.py` seeded afresh for HAI 21.03 and BATADAL. The clean
    editions must be drawn in `CLEAN_CORPORA`'s order, as they are in `CORPORA`.
    """
    if name in CLEAN_CORPORA:
        return shared
    return numpy.random.Generator(numpy.random.PCG64(CHANCE_SEED))


def champion_row(corpus: Corpus, rng: numpy.random.Generator) -> tuple[int, int, int]:
    """The champion's caught and attacks, and the chance null's maximum."""
    model = consistency.fit(corpus.train_files(), corpus.windows)
    alerts = [
        consistency.budget_alerts(
            consistency.events(
                consistency.feature_scores(model, grid.values), windows=corpus.windows
            ),
            time,
            corpus.windows,
        )
        for (_n, grid), time in zip(corpus.tests, corpus.stamps(), strict=True)
    ]
    mine, attacks = caught(consistency.RESULT_NAME, corpus.tests, alerts)
    chance = _chance_row(corpus.tests, rng)
    return mine, attacks, int(chance["max_caught"])


def challenger_row(corpus: Corpus, roles: SignalRoles) -> tuple[int, int]:
    """The challenger's caught, and how many signals its map models."""
    settings = map_settings_from(json.loads(CANDIDATE.read_text(encoding="utf-8")))
    if settings is None:
        raise SystemExit(f"{CANDIDATE} is not a detector configuration")
    detector = challenger.fit_detector(
        corpus.train_files(),
        corpus.trains[0].features,
        roles,
        corpus.period,
        corpus.windows,
        settings,
    )
    alerts = [
        challenger.detect_alerts(detector, grid.values, time)
        for (_n, grid), time in zip(corpus.tests, corpus.stamps(), strict=True)
    ]
    theirs, _ = caught(challenger.RESULT_NAME, corpus.tests, alerts)
    return theirs, len(detector.plant.targets)


def verdict(rows: dict[str, dict[str, int]]) -> tuple[bool, list[str]]:
    """ADR 0117 §3.3 on the scored rows: whether it passes, and every reason it does not."""
    reasons: list[str] = []
    for name, row in rows.items():
        mine, theirs, ceiling = row["champion"], row["challenger"], row["chance_max"]
        if theirs < mine:
            reasons.append(f"{name}: {theirs} is fewer than the champion's {mine}")
        if mine > ceiling >= theirs:
            reasons.append(f"{name}: {theirs} is not above every chance draw ({ceiling})")
    if not any(rows[c]["challenger"] > rows[c]["champion"] for c in HAI_EDITIONS if c in rows):
        reasons.append("no HAI edition where it catches strictly more than the champion")
    return not reasons, reasons


def main() -> int:
    """Run the gate once and write its record."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if OUT.exists():
        print(f"{OUT} exists; the gate is one look", file=sys.stderr)
        return 2
    if declared_sha256() != DECLARED_SHA256:
        print(
            f"the declared files hash to {declared_sha256()}, not ADR 0142's {DECLARED_SHA256}",
            file=sys.stderr,
        )
        return 2
    head = committed_head()
    rows: dict[str, dict[str, int]] = {}
    shared = numpy.random.Generator(numpy.random.PCG64(CHANCE_SEED))
    for name in CORPORA:
        corpus = read_corpus(name)
        roles_for(DATA / name / "roles.toml", corpus.trains[0].features)
        logger.info("champion on %s", name)
        mine, attacks, ceiling = champion_row(corpus, chance_generator(name, shared))
        if (mine, attacks, ceiling) != PUBLISHED[name]:
            print(
                f"{name}: champion {mine}/{attacks}, chance max {ceiling}; published "
                f"{PUBLISHED[name]}. The readers do not reproduce the champion; nothing written "
                "and the challenger was not fitted.",
                file=sys.stderr,
            )
            return 1
        rows[name] = {"attacks": attacks, "champion": mine, "chance_max": ceiling}
    logger.info("champion reproduced on every corpus; scoring the challenger once")
    for name in CORPORA:
        corpus = read_corpus(name)
        roles = roles_for(DATA / name / "roles.toml", corpus.trains[0].features)
        theirs, mapped = challenger_row(corpus, roles)
        rows[name] |= {"challenger": theirs, "mapped_signals": mapped}
        # No challenger number is shown before the record is written, so a crash here reveals
        # nothing and a rerun is not a second look.
        logger.info("challenger scored on %s", name)
    passes, reasons = verdict(rows)
    record = {
        "adr": "ADR 0117 §3, declared in ADR 0142",
        "candidate": json.loads(CANDIDATE.read_text(encoding="utf-8")),
        "commit": head,
        "declared_sha256": DECLARED_SHA256,
        "corpora": rows,
        "passes": passes,
        "reasons": reasons,
        "scorer_sha256": scorer_sha256(),
        "written": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(record, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

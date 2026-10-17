"""ADR 0123 §9.10: time one plant-map fit on HAI 20.07's training data, with the machine's specs.

Reads only HAI 20.07's two training files (development, attack-free), never its test files, and
scores nothing. The bar is a fit within 30 minutes on a laptop; the measurement is taken before
any slice is scored. Writes ``eval_runs/plant-map/fit-time-hai-20.07.json``; nothing is
appended to ``eval_runs/log.jsonl``.

Usage::

    uv run python scripts/plant_map_fit_time.py
"""

from __future__ import annotations

import json
import logging
import platform
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Final

import numpy

ROOT: Final = Path(__file__).resolve().parents[1]
for entry in (ROOT, ROOT / "src"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from scripts.measure_baseline_table import _read_hai  # noqa: E402

from phos.atlas.consistency import TrainFile  # noqa: E402
from phos.atlas.plant_map import DEFAULT_SETTINGS, PlantMap, fit_map  # noqa: E402
from phos.atlas.signal_roles import load_roles  # noqa: E402

DATA: Final = ROOT / "data" / "hai-20.07"
TRAINS: Final = ("train1.csv.gz", "train2.csv.gz")
OUT: Final = ROOT / "eval_runs" / "plant-map"
BAR_SECONDS: Final = 30 * 60
PERIOD_SECONDS: Final = 1.0


def _sysctl(name: str) -> str:
    try:
        return subprocess.run(
            ["sysctl", "-n", name], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def machine() -> dict[str, object]:
    """The machine the fit ran on."""
    memory = _sysctl("hw.memsize")
    return {
        "model": _sysctl("hw.model"),
        "cpu": _sysctl("machdep.cpu.brand_string"),
        "logical_cores": _sysctl("hw.ncpu"),
        "physical_cores": _sysctl("hw.physicalcpu"),
        "memory_gib": round(int(memory) / 2**30, 1) if memory.isdigit() else "unknown",
        "os": platform.platform(),
        "python": platform.python_version(),
        "numpy": numpy.__version__,
    }


def commit() -> dict[str, object]:
    """The commit the fit ran from, and whether the map's files differ from it."""
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "status", "--porcelain", "--", "src/phos/atlas", "scripts/plant_map_fit_time.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    return {"head": head, "map_files_clean": not dirty}


def by_section(model: PlantMap) -> dict[str, dict[str, int]]:
    """Signals, mapped signals and links per HAI process section (P1 boiler ... P4 HIL)."""
    section = [name.split("_", 1)[0] for name in model.names]
    signals = Counter(section)
    mapped = Counter(section[t] for t in model.targets)
    links = Counter(section[t] for t, m in model.targets.items() for _link in m.links)
    forms = Counter((section[t], m.form.value) for t, m in model.targets.items())
    return {
        name: {
            "signals": signals[name],
            "mapped": mapped[name],
            "links": links[name],
            "level_form": forms[(name, "level")],
            "increment_form": forms[(name, "increment")],
        }
        for name in sorted(signals)
    }


def main() -> int:
    """Fit once, time it, and write the record."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    grids = [_read_hai(DATA / name, ";") for name in TRAINS]
    features = grids[0].features
    if any(grid.features != features for grid in grids):
        raise SystemExit("the two training files disagree about their columns")
    roles = load_roles(DATA / "roles.toml", features)
    train = [
        TrainFile(values=grid.values, attack=numpy.asarray(grid.attack, dtype=numpy.bool_))
        for grid in grids
    ]
    rows = sum(grid.values.shape[0] for grid in grids)
    started_wall, started_cpu = time.perf_counter(), time.process_time()
    model = fit_map(train, features, roles, PERIOD_SECONDS, DEFAULT_SETTINGS)
    wall, cpu = time.perf_counter() - started_wall, time.process_time() - started_cpu
    record = {
        "adr": "0123 §9.10",
        "corpus": "hai-20.07 (development), train1 and train2 only",
        "rows": rows,
        "signals": len(features),
        "signals_without_role": list(roles.without_role()),
        "settings": "DEFAULT_SETTINGS (ADR 0123)",
        "fit_wall_seconds": round(wall, 1),
        "fit_cpu_seconds": round(cpu, 1),
        "bar_seconds": BAR_SECONDS,
        "passes": wall <= BAR_SECONDS,
        "mapped_signals": len(model.targets),
        "links": sum(len(m.links) for m in model.targets.values()),
        "by_section": by_section(model),
        "links_listed": list(model.describe()),
        "machine": machine(),
        "commit": commit(),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "fit-time-hai-20.07.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps({k: v for k, v in record.items() if k != "links_listed"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Score Kelmarsh 2018-2022 once for the pooled log and once for declared modes.

ADR 0165 names the files. ADR 0166 names the modes. 2016, 2017, and 2023-2024
are not opened. Nothing is appended to eval_runs/log.jsonl.

Usage::

    uv run python scripts/lane_b_kelmarsh.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Final

REPO_ROOT: Final = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(REPO_ROOT / "src"))

from phos.atlas.consistency import RESULT_NAME  # noqa: E402
from phos.eval.kelmarsh_log import (  # noqa: E402
    TURBINES,
    combine_zips,
    development_checksums,
    load_scada_zip,
    score_halves,
    verify_file,
)
from phos.eval.kelmarsh_modes import score_modes  # noqa: E402
from phos.eval.kelmarsh_round2 import (  # noqa: E402
    SCORED_SCADA_FILES,
    assert_round2_zip,
    decide_keep,
)

DEFAULT_DIR: Final = REPO_ROOT / "data" / "kelmarsh"
DEFAULT_OUT: Final = REPO_ROOT / "eval_runs" / "build" / "lane-b" / "kelmarsh-round2.json"


def main() -> int:
    """Verify the five zips, score both ways, and write the keep decision."""
    started = time.perf_counter()
    registry = json.loads((REPO_ROOT / "data" / "registry.json").read_text(encoding="utf-8"))
    checksums = {item.filename: item for item in development_checksums(registry)}
    for name in SCORED_SCADA_FILES:
        assert_round2_zip(name)
        verify_file(DEFAULT_DIR / name, checksums[name])
    loaded = [
        load_scada_zip(DEFAULT_DIR / name, allow_year_end_label=True) for name in SCORED_SCADA_FILES
    ]
    trains, tests, spans = combine_zips(loaded)
    pooled = score_halves(trains, tests, spans, turbines=TURBINES)
    modes = score_modes(trains, tests, spans, turbines=TURBINES)
    decision = decide_keep(
        pooled.false_alerts_per_shift,
        pooled.explained_share,
        modes.false_alerts_per_shift,
        modes.explained_share,
    )
    kept = modes.detector if decision == "keep" else RESULT_NAME
    body = {
        "result_name": "lane-b-kelmarsh-round2",
        "files": list(SCORED_SCADA_FILES),
        "train": "2018",
        "score": "2019-2022",
        "pooled_detector": RESULT_NAME,
        "pooled": pooled.model_dump(mode="json"),
        "modes": modes.model_dump(mode="json"),
        "decision": decision,
        "kept": kept,
        "synthetic_catch_unchanged": "consistency.py and the maintenance harness were not edited",
        "runtime_seconds": time.perf_counter() - started,
        "note": "Development only. 2023-2024 were not opened. Not a detection claim.",
    }
    DEFAULT_OUT.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    print(
        f"pooled {pooled.unexplained_alerts}/{pooled.alerts} "
        f"share={pooled.explained_share} per_shift={pooled.false_alerts_per_shift}"
    )
    print(
        f"modes {modes.unexplained_alerts}/{modes.alerts} "
        f"share={modes.explained_share} per_shift={modes.false_alerts_per_shift} {decision}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

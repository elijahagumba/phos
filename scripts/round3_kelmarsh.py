#!/usr/bin/env python3
"""Score Kelmarsh 2023-2024 once. Refuses to open the zips until ADR 0174 is authorized.

The declaration file must have ``authorized: true`` and a sha256 for every file.
If the result file already exists, this command exits without reading a zip.

Usage::

    uv run python scripts/round3_kelmarsh.py
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Final

REPO_ROOT: Final = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(REPO_ROOT / "src"))

from phos.eval.kelmarsh_heldback import (  # noqa: E402
    HELD_BACK_SCADA,
    METER_FILES,
    SCORE_RESULT,
    TRAIN_FILE,
    DeclarationError,
    registry_checksums,
    require_authorization,
    score_held_back,
)

DEFAULT_DIR: Final = REPO_ROOT / "data" / "kelmarsh"
DECLARATION: Final = REPO_ROOT / "eval_runs" / "build" / "round-3" / "kelmarsh-declaration.json"
DEFAULT_OUT: Final = REPO_ROOT / "eval_runs" / "build" / "round-3" / "kelmarsh-heldback.json"
SCORER_FILE: Final = REPO_ROOT / "src" / "phos" / "atlas" / "consistency.py"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1 << 20)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    """Verify the declaration, then score once."""
    body = json.loads(DECLARATION.read_text(encoding="utf-8"))
    if DEFAULT_OUT.exists():
        print("result already exists; the held-back score is not run again", file=sys.stderr)
        return 2
    try:
        require_authorization(body)
    except DeclarationError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    expected = body.get("scorer_sha256")
    actual = _sha256(SCORER_FILE)
    if expected != actual:
        print(f"consistency.py sha256 {actual} != declaration {expected}", file=sys.stderr)
        return 2
    started = time.perf_counter()
    registry = json.loads((REPO_ROOT / "data" / "registry.json").read_text(encoding="utf-8"))
    names = (TRAIN_FILE, *HELD_BACK_SCADA, *METER_FILES)
    checksums = registry_checksums(registry, names)
    sha256_by_name = {
        str(item["filename"]): str(item["sha256"])
        for item in body["files"]
        if isinstance(item, dict)
    }
    report, meters = score_held_back(
        DEFAULT_DIR,
        train_checksum=checksums[TRAIN_FILE],
        score_checksums=tuple(checksums[name] for name in (*HELD_BACK_SCADA, *METER_FILES)),
        sha256_by_name=sha256_by_name,
    )
    payload = {
        "result_name": SCORE_RESULT,
        "scorer": report.detector,
        "train": "2018",
        "score": "2023-2024",
        "status_log_rule": "ADR 0165 keeps ADR 0152",
        "report": report.model_dump(mode="json"),
        "meters": [item.model_dump(mode="json") for item in meters],
        "runtime_seconds": time.perf_counter() - started,
        "note": "One look. Not a detection claim. Modes were not run. No tuning.",
    }
    DEFAULT_OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        f"{report.alerts} alerts, explained {report.explained_alerts}, "
        f"share={report.explained_share}, per_shift={report.false_alerts_per_shift}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

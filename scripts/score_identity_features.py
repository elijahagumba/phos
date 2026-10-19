#!/usr/bin/env python3
"""Score the six identity features on one CERT release (ADR 0146, ADR 0204).

The register is the empty register named in ADR 0204. This script does not fill
it from a labelled day and does not put a weight on the 34. It refuses to write
over an existing result. ``insiders.csv`` is read only after the feature summary
exists, and only to count labelled insiders.

Usage: pass ``--release r3.1`` or ``r4.2`` and a required ``--out`` path.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Final

REPO_ROOT: Final = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:  # pragma: no cover - script bootstrap
    sys.path.insert(0, str(REPO_ROOT / "src"))

from phos.sentiel.identity_score import (  # noqa: E402
    EMPTY_REGISTER_SHA256,
    summarise_traces,
)
from phos.sentiel.labels import read_insiders  # noqa: E402
from phos.sentiel.traces import read_traces  # noqa: E402

logger = logging.getLogger("score_identity_features")

DEFAULT_DATA: Final = REPO_ROOT / "data" / "cert-insider-threat"


def main(argv: list[str] | None = None) -> int:
    """Score one release and write the JSON. Returns a process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", choices=("r3.1", "r4.2"), required=True)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--cache", type=Path, default=None)
    parser.add_argument("--out", type=Path, required=True)
    arguments = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", stream=sys.stdout)
    if arguments.out.exists():
        logger.error("%s already exists; this score is not run again", arguments.out)
        return 2

    started = time.monotonic()
    cache = arguments.cache or (
        arguments.data_dir / f"{arguments.release}-entity-day-traces.jsonl.gz"
    )
    summary = summarise_traces(read_traces(cache), None)
    if summary["register_sha256"] != EMPTY_REGISTER_SHA256:
        logger.error("register hash %s is not the empty register", summary["register_sha256"])
        return 1
    labels = read_insiders(arguments.data_dir / "answers", arguments.release)
    insiders = tuple(dict.fromkeys(label.user_id for label in labels))
    payload: dict[str, object] = {
        "release": arguments.release,
        "register": {"hosts": [], "destinations": [], "pcs": []},
        "register_sha256": EMPTY_REGISTER_SHA256,
        "register_note": (
            "Empty. ADR 0146 forbids filling the register from a labelled day, "
            "and no other register was committed before this score."
        ),
        "features": summary["features"],
        "all_zero": summary["all_zero"],
        "n_observations": summary["n_observations"],
        "n_labelled_insiders": len(insiders),
        "weights_on_the_34": None,
        "seconds": round(time.monotonic() - started, 1),
    }
    arguments.out.parent.mkdir(parents=True, exist_ok=True)
    temporary = arguments.out.with_suffix(arguments.out.suffix + ".partial")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(arguments.out)
    logger.info(
        "%s all_zero=%s observations=%s insiders=%d",
        arguments.release,
        summary["all_zero"],
        summary["n_observations"],
        len(insiders),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

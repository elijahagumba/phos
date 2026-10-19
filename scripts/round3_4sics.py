#!/usr/bin/env python3
"""Run Atlas's packet and command path on the two 4SICS development days.

Learns the command graph on 151020 and counts graph findings on 151021.
Does not open 151022. Does not report a catch.

Usage::

    uv run python scripts/round3_4sics.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Final

REPO_ROOT: Final = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(REPO_ROOT / "src"))

from phos.eval.four_sics import RESULT_NAME, score_days  # noqa: E402

DEFAULT_DIR: Final = REPO_ROOT / "data" / "4sics"
DEFAULT_OUT: Final = REPO_ROOT / "eval_runs" / "build" / "round-3" / "4sics-development.json"


def main() -> int:
    """Write the development-day report. Graph findings are not catches."""
    body = score_days(DEFAULT_DIR)
    body["result_name"] = RESULT_NAME
    DEFAULT_OUT.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    print(f"findings={body['findings']} per_hour={body['alerts_per_hour']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

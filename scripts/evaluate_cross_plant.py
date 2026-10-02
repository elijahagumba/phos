#!/usr/bin/env python3
"""Measure declared-role zero-shot transfer (BATADAL, optional SWaT) onto HAI.

Appends a new experiment-log row. Does not rewrite public HAI Mahalanobis
646.58, distillation 18.72, or CERT 6B 0.104. Does not fetch SWaT.

Usage::

    python scripts/evaluate_cross_plant.py
    python scripts/evaluate_cross_plant.py --no-log
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Final

REPO_ROOT: Final = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from phos.atlas.data.transfer import (  # noqa: E402
    evaluate_available_transfer,
    write_zero_shot_log,
)
from phos.eval.report import DEFAULT_LOG_PATH  # noqa: E402

logger = logging.getLogger("phos.atlas.cross_plant")


def main() -> int:
    """Run the available-plant zero-shot protocol and optionally log it."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-log",
        action="store_true",
        help="print the report and do not append eval_runs/log.jsonl",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    report = evaluate_available_transfer(REPO_ROOT / "data")
    print(
        f"{report.detector_name} on {report.dataset_name}: "
        f"FP/hour={report.false_positive_rate:.4f} "
        f"window_recall={report.window_recall:.4f} "
        f"seed={report.seed} threshold={report.alert_threshold}"
    )
    print(report.source_note)
    if not args.no_log:
        write_zero_shot_log(report, REPO_ROOT / DEFAULT_LOG_PATH)
        logger.info("appended %s", REPO_ROOT / DEFAULT_LOG_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

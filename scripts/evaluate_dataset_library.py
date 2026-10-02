#!/usr/bin/env python3
"""Run Atlas and Sentiel on the dataset library and append PART 2 reports to eval_runs/log.jsonl.

Every logged row carries SYNTHETIC_LIBRARY_CAVEATS. These numbers are not public-corpus
attack recall and not a cycle-contract claim.

Usage::

    python scripts/evaluate_dataset_library.py
    python scripts/evaluate_dataset_library.py --no-log --ot-limit 2
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parent.parent
if str(REPOSITORY / "src") not in sys.path:
    sys.path.insert(0, str(REPOSITORY / "src"))

from phos.library.evaluate import (  # noqa: E402
    evaluate_it_library,
    evaluate_ot_library,
    library_root,
    write_run_summary,
)

logger = logging.getLogger("phos.library.evaluate")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Return the parsed command line."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--no-log", action="store_true", help="print results, write nothing")
    parser.add_argument("--it-only", action="store_true")
    parser.add_argument("--ot-only", action="store_true")
    parser.add_argument("--ot-limit", type=int, default=None)
    parser.add_argument("--dwell", type=int, default=4)
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Evaluate the library and optionally append to the experiment log."""
    args = parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(message)s")
    root = library_root(REPOSITORY)
    log = not args.no_log
    reports = []
    if not args.it_only:
        reports.extend(
            evaluate_ot_library(root, dwell_samples=args.dwell, log=log, pack_limit=args.ot_limit)
        )
    if not args.ot_only:
        reports.extend(evaluate_it_library(root, log=log))
    if not reports:
        logger.error("no library corpora scored; generate first")
        return 2
    summary = REPOSITORY / "eval_runs" / "dataset-library-summary.json"
    write_run_summary(summary, reports)
    logger.info("wrote %d reports; summary %s", len(reports), summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

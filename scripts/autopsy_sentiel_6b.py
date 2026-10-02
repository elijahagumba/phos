#!/usr/bin/env python3
"""Autopsy the CERT r3.1 identity-6B top-48 queue without rewriting precision 0.104.

Streams the peer feature set once, ranks entity-windows by aggregate score, and writes
which starter-count stems led the 48-alert operating point. Always ``--no-log``: the
frozen 6B detector name is never appended to ``eval_runs/log.jsonl``.

Usage::

    PYTHONPATH=src python scripts/autopsy_sentiel_6b.py
    PYTHONPATH=src python scripts/autopsy_sentiel_6b.py --budget 48 --no-write
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final

REPO_ROOT: Final = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.evaluate_sentiel_baseline import (  # noqa: E402
    DEFAULT_DATA_DIR,
    PEER_SUBSET,
    BaselineError,
    build_corpus,
    fit_on_prefix,
    load_manifest,
    score_streaming,
)

from phos.sentiel import AggregationPolicy, FeatureSet, PeerPolicy  # noqa: E402
from phos.sentiel.autopsy import (  # noqa: E402
    AUTOPSY_DETECTOR_NAME,
    FROZEN_SIX_B_DETECTOR_NAME,
    autopsy_budget_queue,
    render_autopsy_markdown,
)

logger = logging.getLogger("phos.sentiel.autopsy")
OUTPUT_PATH: Final = REPO_ROOT / "eval_runs" / "sentiel" / "6b-autopsy.md"


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns a process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--budget", type=int, default=48)
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="print the autopsy and do not write eval_runs/sentiel/6b-autopsy.md",
    )
    arguments = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    try:
        manifest = load_manifest(arguments.data_dir)
        corpus = build_corpus(
            arguments.data_dir,
            manifest,
            FeatureSet.PEER,
            PeerPolicy(),
        )
        first_attack = min(label.start for label in corpus.labels)
        fitted, _, _ = fit_on_prefix(corpus.stream_factory, first_attack, min_samples=8)
        detections, _, _ = score_streaming(
            corpus.stream_factory,
            first_attack,
            fitted,
            AggregationPolicy(),
            {PEER_SUBSET: None},
        )
    except BaselineError as error:
        logger.error("%s", error)
        return 2

    alerts = detections[PEER_SUBSET]
    report = autopsy_budget_queue(alerts, corpus.labels, budget=arguments.budget)
    if report.detector_name == FROZEN_SIX_B_DETECTOR_NAME:
        raise RuntimeError("autopsy reused the frozen 6B detector name")
    if report.detector_name != AUTOPSY_DETECTOR_NAME:
        raise RuntimeError(f"unexpected autopsy detector name {report.detector_name}")

    markdown = render_autopsy_markdown(report)
    print(markdown)
    if not arguments.no_write:
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_PATH.write_text(markdown, encoding="utf-8")
        logger.info("wrote %s (not a 6B log row)", OUTPUT_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

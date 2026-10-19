#!/usr/bin/env python3
"""Score exclusive-host-return once on CERT r3.1 (ADR 0195).

The queue is the same person-days the frozen 6B scorer ranks. This script does
not fit that scorer, does not overwrite its row, does not append
``eval_runs/log.jsonl``, and does not read r4.2.

Usage::

    uv run python scripts/score_exclusive_host_return.py
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Final, TypedDict

REPO_ROOT: Final = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:  # pragma: no cover - script bootstrap
    sys.path.insert(0, str(REPO_ROOT / "src"))
if str(REPO_ROOT) not in sys.path:  # pragma: no cover - script bootstrap
    sys.path.insert(0, str(REPO_ROOT))

from phos.sentiel.bet001 import (  # noqa: E402
    BUDGET,
    DayScore,
    chance_malicious_days,
    rank_days,
)
from phos.sentiel.exclusive_return import (  # noqa: E402
    SCORER_NAME,
    HostDay,
    exclusive_return_scores,
)
from phos.sentiel.labels import read_insiders  # noqa: E402
from phos.sentiel.r42_holdout import r42_may_be_scored  # noqa: E402
from phos.sentiel.traces import read_traces  # noqa: E402


class _InsiderRow(TypedDict):
    """One insider's place in the 48."""

    malicious_days: int
    in_top_48: int
    best_rank: int | None
    best_score: float | None


logger = logging.getLogger("exclusive_host_return")

DEFAULT_DATA: Final = REPO_ROOT / "data" / "cert-insider-threat"
DEFAULT_OUT: Final = REPO_ROOT / "eval_runs" / "build" / "sentiel" / "exclusive-host-return.json"
R42_RESULT: Final = "exclusive-host-return:cert-r4.2@48"
SCORED_DAYS: Final = 210_814


def main(argv: list[str] | None = None) -> int:
    """Score the declared signal once and write the r3.1 result."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--release", choices=("r3.1", "r4.2"), default="r3.1")
    arguments = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", stream=sys.stdout)
    if arguments.release == "r4.2":
        logger.error(
            "CERT r4.2 is held out. Result %s is reserved at budget %d. Not fetched. Not scored.",
            R42_RESULT,
            BUDGET,
        )
        if r42_may_be_scored():
            logger.error("r42_may_be_scored() returned true; this script still has no r4.2 path")
        return 2

    started = time.monotonic()
    labels = read_insiders(arguments.data_dir / "answers", "r3.1")
    insiders = tuple(dict.fromkeys(label.user_id for label in labels))
    if insiders != ("CSF0929", "CCH0959"):
        logger.error("r3.1 insiders were %s", insiders)
        return 1
    first_attack = min(label.start for label in labels)
    cache = arguments.data_dir / "r3.1-entity-day-traces.jsonl.gz"
    host_days: list[HostDay] = []
    for trace in read_traces(cache):
        host_days.append(HostDay(trace.user_id, trace.day, trace.hosts))
    scores = exclusive_return_scores(host_days)

    ranked_input: list[DayScore] = []
    for item, score in zip(host_days, scores, strict=True):
        if item.day < first_attack:
            continue
        malicious = any(label.contains(item.user_id, item.day) for label in labels)
        ranked_input.append(
            DayScore(user_id=item.user_id, day=item.day, score=float(score), malicious=malicious)
        )
    if len(ranked_input) != SCORED_DAYS:
        logger.error("scored %d days, the 6B queue has %d", len(ranked_input), SCORED_DAYS)
        return 1

    ranked = rank_days(ranked_input)
    rank_of = {(item.user_id, item.day): index + 1 for index, item in enumerate(ranked)}
    top = ranked[:BUDGET]
    malicious_in_top = [item for item in top if item.malicious]
    insider_rows: dict[str, _InsiderRow] = {}
    for user in insiders:
        mine = [item for item in ranked_input if item.user_id == user and item.malicious]
        best = min((rank_of[(item.user_id, item.day)] for item in mine), default=None)
        insider_rows[user] = {
            "malicious_days": len(mine),
            "in_top_48": sum(1 for item in top if item.user_id == user and item.malicious),
            "best_rank": best,
            "best_score": max((item.score for item in mine), default=None),
        }
    innocent = sorted({item.user_id for item in top if item.user_id not in insiders})
    innocent_positive = sorted(
        {item.user_id for item in top if item.user_id not in insiders and item.score > 0}
    )
    payload: dict[str, object] = {
        "scorer": SCORER_NAME,
        "budget": BUDGET,
        "n_days": len(ranked_input),
        "both_in_top_48": all(row["in_top_48"] > 0 for row in insider_rows.values()),
        "malicious_days_in_top_48": len(malicious_in_top),
        "precision_at_48": len(malicious_in_top) / BUDGET,
        "chance_malicious_days_in_48": chance_malicious_days(
            len(ranked_input),
            sum(1 for item in ranked_input if item.malicious),
            BUDGET,
        ),
        "per_insider": insider_rows,
        "innocent_people_in_top_48": len(innocent),
        "innocent_people_with_positive_score": len(innocent_positive),
        "positive_days": sum(1 for item in ranked_input if item.score > 0),
        "positive_users": sorted({item.user_id for item in ranked_input if item.score > 0}),
        "top_48": [
            {
                "rank": index + 1,
                "user_id": item.user_id,
                "day": item.day.date().isoformat(),
                "score": item.score,
                "malicious": item.malicious,
            }
            for index, item in enumerate(top)
        ],
        "seconds": round(time.monotonic() - started, 1),
    }
    arguments.out.parent.mkdir(parents=True, exist_ok=True)
    arguments.out.write_text(json.dumps(payload, indent=2) + "\n")
    logger.info(
        "%s both=%s precision=%.3f innocent_people=%d positive_innocent=%d",
        SCORER_NAME,
        payload["both_in_top_48"],
        payload["precision_at_48"],
        payload["innocent_people_in_top_48"],
        payload["innocent_people_with_positive_score"],
    )
    for user in insiders:
        logger.info("%s %s", user, insider_rows[user])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

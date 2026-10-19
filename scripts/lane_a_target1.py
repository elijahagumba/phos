#!/usr/bin/env python3
"""Score lane A target 1 on CERT r3.1 development days (ADR 0149, 0190-0193).

Fits the four new streams on the attack-free prefix, ranks every later person-day
with ADR 0148's key, and applies the keep rule. Does not recompute 6B, does not
append eval_runs/log.jsonl, and does not open r4.2.

Usage::

    uv run python scripts/lane_a_target1.py
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Final

REPO_ROOT: Final = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:  # pragma: no cover - script bootstrap
    sys.path.insert(0, str(REPO_ROOT / "src"))

from phos.sentiel.day_facts import DayFacts  # noqa: E402
from phos.sentiel.dev_loop import (  # noqa: E402
    FittedStreams,
    LoopSnapshot,
    decide_keep,
    score_days,
    snapshot,
)
from phos.sentiel.entities import EntityCatalogue  # noqa: E402
from phos.sentiel.labels import read_insiders  # noqa: E402
from phos.sentiel.traces import read_traces  # noqa: E402

logger = logging.getLogger("lane_a_target1")

DEFAULT_DATA: Final = REPO_ROOT / "data" / "cert-insider-threat"
DEFAULT_CACHE: Final = DEFAULT_DATA / "r3.1-entity-day-traces.jsonl.gz"
DEFAULT_OUT: Final = REPO_ROOT / "eval_runs" / "build" / "lane-a" / "target1.json"
DEFAULT_BET: Final = REPO_ROOT / "eval_runs" / "build" / "lane-a" / "bet-001.json"
DEFAULT_DECISIONS: Final = REPO_ROOT / "eval_runs" / "build" / "lane-a" / "decisions.md"

LOOPS: Final[tuple[tuple[str, tuple[str, ...]], ...]] = (
    ("depth", ("depth",)),
    ("peer-links", ("peer_links",)),
    ("chains", ("chains",)),
    ("role-hours", ("role_hours",)),
    ("peer-links+depth", ("peer_links", "depth")),
    ("peer-links+chains", ("peer_links", "chains")),
    ("peer-links+role-hours", ("peer_links", "role_hours")),
    ("all-four", ("depth", "chains", "role_hours", "peer_links")),
    ("chains+depth", ("chains", "depth")),
    ("peer-links+chains+depth", ("peer_links", "chains", "depth")),
)


def _role_of(catalogue: EntityCatalogue, user_id: str) -> str:
    role = catalogue.entity_for(user_id).attributes.get("role")
    if isinstance(role, str) and role.strip():
        return role.strip()
    return "unknown"


def _six_b_snapshot(path: Path) -> LoopSnapshot:
    body = json.loads(path.read_text(encoding="utf-8"))
    row = next(item for item in body["candidates"] if item["candidate"] == "6b-frozen")
    per_insider = {
        user: {
            "malicious_days": int(values["malicious_days"]),
            "in_top_48": int(values["in_top_48"]),
            "best_rank": values["best_rank"],
        }
        for user, values in row["per_insider"].items()
    }
    return LoopSnapshot(
        name="6b-frozen",
        found=tuple(row["found"]),
        both_found=bool(row["both_found"]),
        precision_at_48=float(row["precision_at_48"]),
        chance_malicious_days_in_48=float(row["chance_malicious_days_in_48"]),
        per_insider=per_insider,
        n_days=int(row["n_days"]),
        n_malicious=int(body["n_malicious_days"]),
    )


def main(argv: list[str] | None = None) -> int:
    """Fit, score the declared loops, and write the development record."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--bet", type=Path, default=DEFAULT_BET)
    parser.add_argument("--decisions", type=Path, default=DEFAULT_DECISIONS)
    arguments = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", stream=sys.stdout)

    started = time.monotonic()
    catalogue = EntityCatalogue.from_ldap_directory(arguments.data_dir / "r3.1" / "LDAP")
    labels = read_insiders(arguments.data_dir / "answers", "r3.1")
    first_attack = min(label.start for label in labels)
    insider_ids = tuple(sorted({label.user_id for label in labels}))
    by_user = {label.user_id: label for label in labels}

    train: list[DayFacts] = []
    test: list[DayFacts] = []
    for trace in read_traces(arguments.cache):
        facts = DayFacts(
            user_id=trace.user_id,
            day=trace.day,
            role=_role_of(catalogue, trace.user_id),
            logons=trace.logons,
            off_hours_logons=trace.off_hours_logons,
            removable_connects=trace.removable_connects,
            file_accesses=trace.file_accesses,
            emails=trace.emails,
            external_emails=trace.external_emails,
            pcs=trace.pcs,
            hosts=trace.hosts,
            recipients=trace.recipients,
            sequence=trace.sequence,
        )
        if trace.day < first_attack:
            train.append(facts)
        else:
            test.append(facts)
    logger.info("loaded %d train days, %d test days", len(train), len(test))

    model = FittedStreams.fit(train)
    train.clear()
    logger.info("fitted four streams")

    malicious: dict[tuple[str, object], bool] = {
        (day.user_id, day.day.date()): (
            day.user_id in by_user and by_user[day.user_id].contains(day.user_id, day.day)
        )
        for day in test
    }

    current = _six_b_snapshot(arguments.bet)
    kept = current
    rows: list[dict[str, object]] = [current.model_dump()]
    no_gain = 0
    kept_name = current.name
    for slug, streams in LOOPS:
        name = f"lane-a-dev:{slug}"
        days = score_days(model, test, streams, malicious)
        row = snapshot(name, days, insider_ids)
        decision = decide_keep(current, row)
        if decision == "keep":
            current = row
            kept = row
            kept_name = name
            no_gain = 0
        else:
            no_gain += 1
        rows.append({**row.model_dump(), "decision": decision, "streams": list(streams)})
        logger.info(
            "%s found=%s precision=%.3f cch_rank=%s -> %s",
            name,
            row.found,
            row.precision_at_48,
            row.per_insider.get("CCH0959", {}).get("best_rank"),
            decision,
        )
        if no_gain >= 10:
            logger.info("ten loops with no keep; stopping")
            break

    body = {
        "result_name": "lane-a-target-1",
        "corpus": "cert-insider-threat r3.1",
        "contract": "ADR 0149, ADR 0190-0193",
        "start": "6b-frozen",
        "kept": kept_name,
        "both_found": kept.both_found,
        "loops": rows,
        "runtime_seconds": time.monotonic() - started,
        "note": (
            "Development only. The frozen 6B row was read, not recomputed. "
            "CERT r4.2 was not opened."
        ),
    }
    arguments.out.parent.mkdir(parents=True, exist_ok=True)
    arguments.out.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n")

    stamped = datetime.now().strftime("%Y-%m-%d")
    lines = []
    for entry in rows[1:]:
        insiders = entry["per_insider"]
        assert isinstance(insiders, dict)
        lines.append(
            f"{stamped} | target-1 | {entry['name']} found={entry['found']} "
            f"precision={entry['precision_at_48']:.3f} "
            f"cch_rank={insiders['CCH0959']['best_rank']} "
            f"{entry['decision']}"
        )
    if arguments.decisions.exists():
        existing = arguments.decisions.read_text(encoding="utf-8")
    else:
        existing = ""
    arguments.decisions.write_text(existing.rstrip() + "\n" + "\n".join(lines) + "\n")
    logger.info("kept %s both_found=%s", kept_name, kept.both_found)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

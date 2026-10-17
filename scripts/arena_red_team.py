#!/usr/bin/env python3
"""Score a task's chosen candidate and the champion, once, on the red-team seeds.

Learning engine S4 (ADR 0121). The candidate is chosen mechanically from the task's attempts by
`phos.breaking.liar_selection.choose`; nothing is picked by hand. Both window sets are then scored
on `RED_TEAM_SEEDS`, development seeds no attempt was scored on, and the result is written once.
It qualifies only if it again passes more water-treatment runs than the champion and loses none
the champion passes. HAI 20.07 is not re-run: it is deterministic and already in the attempt.

A detector task (ADR 0127, `plant-map`) chooses by `choose_detector` and is judged by ADR 0123
§9.3: more passes than the champion on these seeds, and no champion pass lost.

Usage::

    uv run python scripts/arena_red_team.py <task>
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Final

ROOT: Final = Path(__file__).resolve().parents[1]
for entry in (ROOT, ROOT / "src"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from scripts.arena import RESULTS, map_settings_from, scorer_sha256, windows_from  # noqa: E402

from phos.breaking.liar_arena import (  # noqa: E402
    CONFIRM_SEEDS,
    CONFIRM_SEEDS_2,
    CONFIRM_SEEDS_3,
    RED_TEAM_SEEDS,
    regressions,
    score_windows,
    within_churn,
)
from phos.breaking.liar_selection import choose, choose_detector  # noqa: E402


def main(argv: Sequence[str] | None = None) -> int:
    """Choose, score both on the red-team seeds, and write the verdict once."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("task")
    parser.add_argument(
        "--confirm",
        type=int,
        metavar="FIRST_ATTEMPT",
        help="ADR 0135: score the choice among attempts numbered from FIRST_ATTEMPT on, once, on "
        "CONFIRM_SEEDS",
    )
    parser.add_argument("--cache", type=Path, default=Path(tempfile.gettempdir()) / "phos-arena")
    parser.add_argument(
        "--confirm-set",
        type=int,
        choices=(1, 2, 3),
        default=1,
        help="CONFIRM_SEEDS, _2, or _3 (judged by ADR 0139's forward rule)",
    )
    args = parser.parse_args(argv)
    directory = RESULTS / args.task
    if args.confirm is None:
        out, seeds = directory / "red-team.json", RED_TEAM_SEEDS
    elif args.confirm_set == 1:
        out, seeds = directory / "red-team-confirm.json", CONFIRM_SEEDS
    elif args.confirm_set == 2:
        out, seeds = directory / "red-team-confirm-2.json", CONFIRM_SEEDS_2
    else:
        out, seeds = directory / "red-team-confirm-3.json", CONFIRM_SEEDS_3
    if out.exists():
        print(f"{out} exists; the red team runs once", file=sys.stderr)
        return 2
    champion = json.loads((directory / "champion.json").read_text(encoding="utf-8"))["scorecard"]
    attempts = [
        json.loads(line)["attempt"]
        for line in (directory / "attempts.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    if args.confirm is not None:
        attempts = [a for a in attempts if int(a["number"]) >= args.confirm]
    detector = any("detector" in a["candidate"] for a in attempts)
    chosen = (choose_detector if detector else choose)(champion, attempts)
    if chosen is None:
        payload: dict[str, object] = {"chosen": None, "verdict": "no attempt qualified"}
    else:
        candidate = chosen["candidate"]
        assert isinstance(candidate, dict)
        args.cache.mkdir(parents=True, exist_ok=True)
        base_card, _ = score_windows(None, seeds, args.cache)
        settings = map_settings_from(candidate)
        if settings is not None:
            cand_card, _ = score_windows(None, seeds, args.cache, plant_map=settings)
        else:
            cand_card, _ = score_windows(windows_from(candidate), seeds, args.cache)
        lost = regressions(base_card, cand_card)
        water = (
            base_card.passes_by_plant()["water-treatment"],
            cand_card.passes_by_plant()["water-treatment"],
        )
        more = (
            len(cand_card.passing) > len(base_card.passing)
            if settings is not None
            else water[1] > water[0]
        )
        payload = {
            "chosen": {
                "hypothesis_id": chosen["hypothesis_id"],
                "number": chosen["number"],
                "candidate": candidate,
            },
            "seeds": list(seeds),
            "champion": base_card.as_dict(),
            "candidate": cand_card.as_dict(),
            "lost": [list(item) for item in lost],
            "rule": "ADR 0139 (within the champion's churn)"
            if args.confirm_set == 3 and args.confirm is not None
            else "ADR 0123 §9.3 (none lost)",
            "verdict": "survives"
            if (
                within_churn(base_card, cand_card)
                if args.confirm_set == 3 and args.confirm is not None
                else more and not lost
            )
            else "fails",
        }
    payload["scorer_sha256"] = scorer_sha256()
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in payload.items() if k not in {"champion", "candidate"}}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

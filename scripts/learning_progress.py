#!/usr/bin/env python3
"""Is PHOS improving? Throughput and validated progress, kept apart, and the two arms compared.

Learning engine S5 (ADR 0121). Reads the learning records under ``eval_runs/learning/`` and every
task under ``eval_runs/arena/``, and writes ``eval_runs/learning/progress.{json,md}``. Throughput
(failures recorded, attempts, compute) is never reported as progress. Progress is only what
survived a step its search never saw: the red team, the gate, a held-out score.

Usage::

    uv run python scripts/learning_progress.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Final, cast

ROOT: Final = Path(__file__).resolve().parents[1]
for entry in (ROOT, ROOT / "src"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from phos.breaking.liar_selection import choose, qualifies  # noqa: E402
from phos.eval.learning_records import LearningLedger, LearningRecord  # noqa: E402

LEARNING: Final = ROOT / "eval_runs" / "learning"
ARENA: Final = ROOT / "eval_runs" / "arena"


def _records() -> list[LearningRecord]:
    return [
        LearningRecord.model_validate_json(line)
        for path in sorted(LEARNING.glob("*.learning.jsonl"))
        for line in path.read_text(encoding="utf-8").splitlines()
    ]


def _decided_at() -> dict[str, datetime]:
    out: dict[str, datetime] = {}
    for path in sorted(LEARNING.glob("*.ledger.jsonl")):
        for decision in LearningLedger(path).decisions():
            out[decision.id] = decision.decided_at
    return out


def _task(directory: Path, decided: Mapping[str, datetime]) -> dict[str, object]:
    task = json.loads((directory / "task.json").read_text(encoding="utf-8"))
    champion = json.loads((directory / "champion.json").read_text(encoding="utf-8"))["scorecard"]
    log = directory / "attempts.jsonl"
    attempts = (
        [json.loads(line)["attempt"] for line in log.read_text(encoding="utf-8").splitlines()]
        if log.is_file()
        else []
    )
    qualifying = [a for a in attempts if not qualifies(champion, a["scorecard"])]
    chosen = choose(champion, attempts)
    red = directory / "red-team.json"
    red_team = json.loads(red.read_text(encoding="utf-8")) if red.is_file() else None
    motivated = [decided[i] for i in task["learning_record_ids"] if i in decided]
    first = min((datetime.fromisoformat(a["at"]) for a in attempts), default=None)
    lag = None
    if first is not None and motivated:
        lag = round((first - max(motivated)).total_seconds() / 60.0, 1)
    best_water = max(
        (a["scorecard"]["liar"]["passes_by_plant"]["water-treatment"] for a in attempts), default=0
    )
    return {
        "task": task["id"],
        "hypotheses": [h["id"] for h in task["hypotheses"]],
        "budget": task["runs_per_hypothesis"] * len(task["hypotheses"]),
        "attempts": len(attempts),
        "compute_seconds": round(sum(float(a["compute_seconds"]) for a in attempts), 1),
        "champion_water": champion["liar"]["passes_by_plant"]["water-treatment"],
        "champion_passes": champion["liar"]["passes"],
        "best_water": best_water,
        "qualifying": len(qualifying),
        "chosen": None
        if chosen is None
        else {"hypothesis": chosen["hypothesis_id"], "candidate": chosen["candidate"]},
        "red_team": None if red_team is None else red_team["verdict"],
        "minutes_from_failure_to_first_attempt": lag,
        "scorer_sha256s": sorted({a["scorer_sha256"] for a in attempts}),
    }


def main() -> int:
    """Write the progress report."""
    records = _records()
    decided = _decided_at()
    failures = [r for r in records if r.channel != "success"]
    tasks = [_task(d, decided) for d in sorted(ARENA.iterdir()) if (d / "champion.json").is_file()]
    payload = {
        "throughput": {
            "learning_records": len(records),
            "failures_diagnosed": len(failures),
            "failures_by_mechanism": dict(sorted(Counter(r.mechanism for r in failures).items())),
            "eligible_failures": sum(1 for r in failures if r.eligible),
            "tasks": len(tasks),
            "attempts": sum(cast(int, t["attempts"]) for t in tasks),
            "compute_seconds": round(sum(cast(float, t["compute_seconds"]) for t in tasks), 1),
        },
        "progress": {
            "survived_red_team": [t["task"] for t in tasks if t["red_team"] == "survives"],
            "passed_the_gate": [],
            "survived_held_out": [],
            "validated_improvements": 0,
        },
        "tasks": tasks,
    }
    LEARNING.mkdir(parents=True, exist_ok=True)
    (LEARNING / "progress.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    (LEARNING / "progress.md").write_text(_render(payload), encoding="utf-8")
    print(_render(payload))
    return 0


def _render(payload: Mapping[str, object]) -> str:
    throughput = payload["throughput"]
    progress = payload["progress"]
    tasks = payload["tasks"]
    assert isinstance(throughput, dict) and isinstance(progress, dict) and isinstance(tasks, list)
    lines = [
        "# Learning engine progress",
        "",
        "Generated by `scripts/learning_progress.py` (ADR 0121). Synthetic development data only.",
        "",
        "## Throughput (not progress)",
        "",
        f"- Failures diagnosed: {throughput['failures_diagnosed']} "
        f"({throughput['eligible_failures']} eligible for the arena)",
        f"- By mechanism: {throughput['failures_by_mechanism']}",
        f"- Tasks: {throughput['tasks']}; attempts: {throughput['attempts']}; "
        f"compute: {throughput['compute_seconds']} s",
        "",
        "## Progress",
        "",
        f"- Survived the red team: {progress['survived_red_team'] or 'none'}",
        "- Passed the gate: none. Survived a held-out score: none.",
        f"- Validated improvements: {progress['validated_improvements']}",
        "",
        "## The arms",
        "",
        "| Task | Attempts | Champion water | Best water | Qualifying | Chosen | Red team |",
        "| --- | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for t in tasks:
        chosen = "none" if t["chosen"] is None else f"`{json.dumps(t['chosen']['candidate'])}`"
        lines.append(
            f"| {t['task']} | {t['attempts']}/{t['budget']} | {t['champion_water']} | "
            f"{t['best_water']} | {t['qualifying']} | {chosen} | {t['red_team'] or 'not run'} |"
        )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())

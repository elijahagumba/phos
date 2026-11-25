"""Run the four Atlas cycles under the standing approval, gated twice before they start.

Step 6 of the FORGE build. Two conditions stand in front of it and **neither can be satisfied by an
agent**:

1. Step 5's baseline report exists and shows the team helps; or it shows otherwise and Elijah has
   agreed to proceed anyway, in a recorded file that names him.
2. The standing approval in ``docs/method/approvals/standing-2026-11-24.md`` covers the cycle being
   run, is not expired, and has not been spent.

A cycle that fails either condition does not start. That is the whole design: the instruction is
"only if Step 5 shows the team helps", and an agent that can decide for itself that the condition
holds has not been gated at all.

**Runs 1 to 3 are development verdicts.** Every artefact they produce says so, in the file name and
in the text, because a development number that later reads like a sealed score is the failure
ADR 0460 exists to prevent.

**Between runs**, a learning step reads the breaker and referee notes, records every negative
finding, drops dead ideas and sets the next run's ideas. It is not optional and it is not a summary:
a negative finding that is not written down is a finding the next run repeats.

**Run 4** may add at most one sealed referee score, and only if the sealed batch exists and the
PHOSRED volume is already mounted. If either is absent, run 4 ends with its development results and
an INBOX note saying exactly what is missing. A second sealed score is never run.

Usage::

    uv run python scripts/forge_atlas.py status
    uv run python scripts/forge_atlas.py learning --cycle 1
    uv run python scripts/forge_atlas.py run --cycle 1 --runtime codex
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

ROOT = Path(__file__).resolve().parents[1]
for entry in (ROOT, ROOT / "src"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

#: The approval this build runs under.
APPROVAL: Final = Path("docs/method/approvals/standing-2026-11-24.md")

#: Step 5's report, which gates the first cycle.
BASELINE: Final = Path("docs/forge/BASELINE.md")

#: Where a cycle's own records live. Development work, not the sealed record.
CYCLES: Final = Path("docs/forge/cycles")

#: The four cycles the approval covers.
APPROVED_CYCLES: Final = 4

#: The only cycle that may carry a sealed score.
SEALED_CYCLE: Final = 4


@dataclass
class CycleRecord:
    """One cycle's record.

    Attributes:
        cycle: Which of the four.
        label: ``development`` always, except a cycle 4 that actually got a sealed score.
        started_at: When it started.
        finished_at: When it ended, or empty while running.
        ideas: What was tried, in plain language.
        negative_findings: Every finding that says an idea does not work. Never dropped.
        dead_ideas: Ideas this cycle killed, with the reason.
        next_ideas: What the learning step set for the next cycle.
        sealed_score: The one sealed score, or None.
        inbox: What was missing, when something was.
    """

    cycle: int
    label: str = "development"
    started_at: str = ""
    finished_at: str = ""
    ideas: list[str] = field(default_factory=list)
    negative_findings: list[str] = field(default_factory=list)
    dead_ideas: list[str] = field(default_factory=list)
    next_ideas: list[str] = field(default_factory=list)
    sealed_score: str | None = None
    inbox: str = ""

    @property
    def is_development(self) -> bool:
        """Return whether this cycle's verdict is a development verdict."""
        return self.label == "development"


def _stamp() -> str:
    """Return the current UTC time as a sortable ISO 8601 string."""
    return datetime.now(UTC).isoformat(timespec="seconds")


def _path(cycle: int) -> Path:
    """Return the file one cycle's record lives in."""
    return ROOT / CYCLES / f"cycle-{cycle}.json"


def _load(cycle: int) -> CycleRecord | None:
    """Return a cycle's record, or None when it has not run."""
    path = _path(cycle)
    if not path.is_file():
        return None
    return CycleRecord(**json.loads(path.read_text()))


def _save(record: CycleRecord) -> Path:
    """Write a cycle's record."""
    path = _path(record.cycle)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(record), indent=2, sort_keys=True) + "\n")
    return path


def approval_state() -> tuple[bool, str]:
    """Return whether the standing approval covers a cycle today, and why.

    Returns:
        ``(covered, detail)``. The detail names the file and, when it does not cover, what is
        wrong with it.
    """
    path = ROOT / APPROVAL
    if not path.is_file():
        return False, f"{APPROVAL.as_posix()} does not exist, so there is no approval to run under"
    text = path.read_text(encoding="utf-8")
    if "four Atlas" not in text and "Four Atlas cycles" not in text:
        return False, f"{APPROVAL.as_posix()} does not name four Atlas cycles"
    if "**The day cycle 4 ends.**" not in text.replace("\n", " "):
        return False, f"{APPROVAL.as_posix()} does not state its expiry as the day cycle 4 ends"
    return True, f"{APPROVAL.as_posix()}: four cycles, expiring the day cycle 4 ends"


def baseline_allows_start() -> tuple[bool, str]:
    """Return whether Step 5's report permits a cycle, and the sentence that decides it.

    Returns:
        ``(allowed, detail)``. A report that says the team did not win does not permit a cycle on
        its own; it needs Elijah's recorded agreement, which this function does not invent.
    """
    path = ROOT / BASELINE
    if not path.is_file():
        return False, f"{BASELINE.as_posix()} does not exist. Run the baseline before any cycle."
    text = path.read_text(encoding="utf-8")
    if "matched the recorded verdict more often than the single agent" in text:
        return True, "the baseline report says the team helped"
    if "did not win" in text:
        agreement = ROOT / "docs/method/approvals/elijah-agrees-despite-baseline.md"
        if agreement.is_file():
            return True, f"{agreement.as_posix()} records Elijah's agreement to proceed anyway"
        return (
            False,
            "the baseline report says the team did not win, and no recorded agreement from Elijah "
            "permits a cycle anyway. A fifth cycle needs his approval, not an agent's judgement.",
        )
    if "equally often" in text or "separates nothing" in text:
        # A tie is a real outcome and it is not a win. The gate has to read it, because a report
        # that says the arms tied is saying the baseline did not show the team helps. Treating it
        # as unreadable was a gap: the report was honest and the gate could not hear it.
        agreement = ROOT / "docs/method/approvals/elijah-agrees-despite-baseline.md"
        if agreement.is_file():
            return True, (
                "the baseline found no difference between the arms, and "
                f"{agreement.as_posix()} records Elijah's agreement to proceed anyway"
            )
        return (
            False,
            "the baseline found no difference between the arms, which is not a demonstration that "
            "the team helps. Elijah's recorded agreement is needed to proceed, and there is none.",
        )
    if "No trial ran" in text or "did not run" in text:
        return (
            False,
            "the baseline measurement was blocked: no trial ran, so there is nothing to show the "
            "team helps and nothing to show it does not.",
        )
    return False, "the baseline report does not say whether the team helped"


def status() -> int:
    """Print where the cycles stand and what is standing in the way.

    Returns:
        0 always: a status is a status.
    """
    covered, approval_detail = approval_state()
    allowed, baseline_detail = baseline_allows_start()

    print("Standing approval:")
    print(f"  {'covers' if covered else 'DOES NOT COVER'}: {approval_detail}")
    print()
    print("Step 5 gate:")
    print(f"  {'open' if allowed else 'CLOSED'}: {baseline_detail}")
    print()
    print("Cycles:")
    run = 0
    for cycle in range(1, APPROVED_CYCLES + 1):
        record = _load(cycle)
        if record is None:
            print(f"  {cycle}: not run")
            continue
        run += 1
        print(f"  {cycle}: {record.label}, started {record.started_at}, ended {record.finished_at}")
        if record.negative_findings:
            print(f"     {len(record.negative_findings)} negative findings recorded")
        if record.sealed_score:
            print(f"     one sealed score: {record.sealed_score}")
        if record.inbox:
            print(f"     INBOX: {record.inbox}")
    print()
    print(f"{run} of {APPROVED_CYCLES} cycles have run")
    print()
    if not covered:
        print("A cycle cannot start: the approval does not cover it.")
        return 0
    if not allowed:
        print("A cycle cannot start: Step 5 has not shown the team helps.")
        return 0
    print("A cycle may start.")
    return 0


def _sealed_batch_present() -> tuple[bool, str]:
    """Return whether a sealed batch exists and its volume is mounted.

    Returns:
        ``(present, detail)``. The volume is checked with gate (b), which never mounts it.
    """
    from phos.forge import gates

    volume = gates.require_sealed_volume()
    if not volume.passed:
        return False, volume.detail
    return True, f"{gates.SEALED_VOLUME} is mounted"


def record_learning(cycle: int, findings: list[str], dead: list[str], next_ideas: list[str]) -> int:
    """Record what a cycle learned. Every negative finding is kept.

    Args:
        cycle: Which cycle the learning step follows.
        findings: The negative findings.
        dead: Ideas this cycle killed, each with its reason.
        next_ideas: What the next cycle should try.

    Returns:
        0 recorded, 2 when the cycle has not run.
    """
    record = _load(cycle)
    if record is None:
        print(
            f"refused: cycle {cycle} has not run, so it learned nothing to record",
            file=sys.stderr,
        )
        return 2
    record.negative_findings = [*record.negative_findings, *findings]
    record.dead_ideas = [*record.dead_ideas, *dead]
    record.next_ideas = list(next_ideas)
    path = _save(record)
    print(f"recorded {len(findings)} findings for cycle {cycle} in {path.relative_to(ROOT)}")
    return 0


def run_cycle(cycle: int, runtime: str, ideas: list[str]) -> int:
    """Start one cycle, refusing when either gate is closed.

    Args:
        cycle: Which of the four.
        runtime: The runtime the roles would run on.
        ideas: What the cycle will try.

    Returns:
        0 started, 2 refused, 3 blocked.
    """
    if cycle < 1 or cycle > APPROVED_CYCLES:
        print(
            f"refused: the approval covers cycles 1 to {APPROVED_CYCLES}, not {cycle}",
            file=sys.stderr,
        )
        return 2

    covered, approval_detail = approval_state()
    if not covered:
        print(f"refused: {approval_detail}", file=sys.stderr)
        return 2

    allowed, baseline_detail = baseline_allows_start()
    if not allowed:
        print(f"refused: {baseline_detail}", file=sys.stderr)
        return 2

    if _load(cycle) is not None:
        print(f"refused: cycle {cycle} has already run. A cycle is not repeated.", file=sys.stderr)
        return 2

    if cycle > 1:
        previous = _load(cycle - 1)
        if previous is None:
            print(f"refused: cycle {cycle - 1} has not run", file=sys.stderr)
            return 2
        if not previous.next_ideas and not previous.negative_findings:
            print(
                f"refused: cycle {cycle} needs the learning step from cycle {cycle - 1}. "
                "Record its findings first.",
                file=sys.stderr,
            )
            return 2

    from phos.forge.adapters import detect

    capability = detect(runtime)
    record = CycleRecord(
        cycle=cycle,
        label="development",
        started_at=_stamp(),
        ideas=list(ideas),
    )

    if capability.state != "ready":
        record.inbox = (
            f"{runtime} is {capability.state}: {capability.detail}. No role can run, so this cycle "
            "cannot start. Authenticate a runtime and run it again."
        )
        _save(record)
        print(f"blocked: {record.inbox}", file=sys.stderr)
        return 3

    if cycle == SEALED_CYCLE:
        present, detail = _sealed_batch_present()
        if not present:
            record.inbox = (
                "cycle 4 ran on development data only. The sealed referee step did not run: "
                f"{detail}. A second sealed score is never run, so this is the only sealed "
                "opportunity the four cycles have, and it was not taken."
            )
            record.label = "development"

    path = _save(record)
    print(f"cycle {cycle} started as a {record.label} cycle, recorded in {path.relative_to(ROOT)}")
    if record.inbox:
        _write_inbox(cycle, record.inbox)
        print(f"  INBOX written: {record.inbox}")
    return 0


def _write_inbox(cycle: int, note: str) -> None:
    """Write the INBOX note a cycle leaves when something is missing.

    Args:
        cycle: Which cycle.
        note: What is missing.
    """
    path = ROOT / "docs/method/INBOX.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# INBOX",
        "",
        "Written by FORGE. A human needs to read this.",
        "",
        f"- When: {_stamp()}",
        f"- Operation: Atlas cycle {cycle}",
        f"- What is missing: {note}",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def finish_cycle(cycle: int, summary: str) -> int:
    """Mark a cycle finished.

    Args:
        cycle: Which cycle.
        summary: A sentence for the record.

    Returns:
        0 finished, 2 when the cycle has not started.
    """
    record = _load(cycle)
    if record is None:
        print(f"refused: cycle {cycle} has not started", file=sys.stderr)
        return 2
    record.finished_at = _stamp()
    if summary:
        record.ideas.append(f"outcome: {summary}")
    _save(record)
    print(f"cycle {cycle} finished as a {record.label} cycle")
    if cycle == APPROVED_CYCLES:
        print("The standing approval is now spent: it expires the day cycle 4 ends.")
    return 0


def one_page() -> int:
    """Print the one-page report Elijah gets after cycle 4.

    Returns:
        0 when there is something to report, 2 when the cycles have not run.
    """
    records = [record for cycle in range(1, APPROVED_CYCLES + 1) if (record := _load(cycle))]
    if not records:
        print("refused: no cycle has run, so there is nothing to report", file=sys.stderr)
        return 2

    print("# FORGE: the four Atlas cycles")
    print()
    print("## What ran")
    print()
    for record in records:
        kind = "development verdict" if record.is_development else "with one sealed score"
        print(f"- Cycle {record.cycle}: {kind}. {len(record.ideas)} ideas.")
    print()
    print("## What was learned")
    print()
    total_negative = sum(len(record.negative_findings) for record in records)
    dead = sum(len(record.dead_ideas) for record in records)
    print(f"- {total_negative} negative findings recorded, {dead} ideas dropped.")
    for record in records:
        for finding in record.negative_findings:
            print(f"  - cycle {record.cycle}: {finding}")
    print()
    print("## The sealed score")
    print()
    sealed = [record for record in records if record.sealed_score]
    if sealed:
        print(f"- One sealed score, in cycle {sealed[0].cycle}: {sealed[0].sealed_score}")
    else:
        print("- None. The sealed batch was not available, so every verdict here is a")
        print("  development verdict and says nothing about unseen data.")
    print()
    print("## What is missing")
    print()
    missing = [record.inbox for record in records if record.inbox]
    for note in missing:
        print(f"- {note}")
    if not missing:
        print("- Nothing.")
    return 0


def main() -> int:
    """Run one subcommand.

    Returns:
        The process exit code.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    subparsers.add_parser("status", help="where the cycles stand")

    running = subparsers.add_parser("run", help="start one cycle")
    running.add_argument("--cycle", type=int, required=True)
    running.add_argument("--runtime", default="codex", choices=["claude", "cursor", "codex"])
    running.add_argument("--idea", action="append", default=[], dest="ideas")

    learning = subparsers.add_parser("learning", help="record what a cycle learned")
    learning.add_argument("--cycle", type=int, required=True)
    learning.add_argument("--finding", action="append", default=[], dest="findings")
    learning.add_argument("--dead", action="append", default=[])
    learning.add_argument("--next", action="append", default=[], dest="next_ideas")

    finishing = subparsers.add_parser("finish", help="mark a cycle finished")
    finishing.add_argument("--cycle", type=int, required=True)
    finishing.add_argument("--summary", default="")

    subparsers.add_parser("one-page", help="the report after cycle 4")

    args = parser.parse_args()
    if args.subcommand == "status":
        return status()
    if args.subcommand == "run":
        return run_cycle(args.cycle, args.runtime, args.ideas)
    if args.subcommand == "learning":
        return record_learning(args.cycle, args.findings, args.dead, args.next_ideas)
    if args.subcommand == "finish":
        return finish_cycle(args.cycle, args.summary)
    return one_page()


if __name__ == "__main__":
    sys.exit(main())

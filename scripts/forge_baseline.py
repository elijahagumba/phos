"""Run the FORGE baseline backtest: one agent versus the team, across recorded cases and runtimes.

This is Step 5 of the FORGE build, and it runs **before any Atlas cycle**. It answers one question
with numbers rather than with confidence: does a team of mandate roles produce better work than a
single agent on the same task?

Three recorded cases, each a past result with a committed declaration and code behind it. A trial is
given the repository as it stood at the commit **before the result was recorded**, so it cannot see
the answer in its own tree, and is asked to state the verdict the bars imply. The recorded verdict
is then compared with what the trial produced.

**Why the trials judge rather than re-run.** The instruction for this harness says to use "only the
declaration and code as of the commit before the result". For the first case, ADR 0418, re-running
would have meant running `scripts/lane_sequential_walk.py` on `phos-icssim-dev4-walk` again, and the
GENESIS gate refuses that:

```
REFUSED: that score is already spent
  E-0001 is already judged. A second look is not available (docs/rules/data-tiers.md).
```

The refusal is correct and is not worked around. So every case is judged from its declaration and
its code rather than re-measured. That is also the fairer comparison of what FORGE claims to add:
whether a team reaches the right conclusion from the same information, not whether it can run a
command.

**The cases.**

* ADR 0418, refusal. Two bars are deliberately incompatible, so the verdict could only be refused.
* ADR 0315, not kept. The walk column misses the same one walk as the champion, so it does not
  halve the miss.
* ADR 0336, kept. All eight law-page bars are met at zero.

**The arms.** Three trials each, per case. ``single`` is one agent with the whole task. ``team`` is
four mandate roles in sequence in their own worktrees, each seeing what the previous one concluded.

**The runtimes.** Each trial is assigned a runtime from the ones that answer a probe, and the
assignment rotates so that every case carries both arms on every working runtime. The runtime that
ran is recorded in the result, so a difference between two trials can be traced to it. No model is
chosen or pinned here.

**Seeded defects.** ``scripts/mutate_*.py`` is run for real, once per script, and its tally
recorded. That half needs no agent, so it is measurable whatever the runtimes are doing.

Usage::

    uv run python scripts/forge_baseline.py plan
    uv run python scripts/forge_baseline.py run
    uv run python scripts/forge_baseline.py report
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

ROOT = Path(__file__).resolve().parents[1]
for entry in (ROOT, ROOT / "src"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

#: Where trials and the report live. ``eval_runs`` is gitignored data, and the report is the record.
RUNS: Final = Path("eval_runs/forge-baseline")
REPORT: Final = Path("docs/forge/BASELINE.md")

#: The two arms, and how many trials each gets per case. Fixed here so a report cannot quietly run
#: fewer than it claims.
ARMS: Final = ("single", "team")
TRIALS: Final = 3

#: The roles the team arm runs, in order. Each one in its own worktree, each seeing the notes of the
#: one before it. The last writes the verdict, which is what gets compared.
TEAM_ROLES: Final = (
    "principal_research_scientist",
    "applied_scientist",
    "adversarial_researcher",
    "verification_engineer",
)


@dataclass(frozen=True)
class Case:
    """One recorded result the baseline backtests against.

    Attributes:
        key: The directory name for this case's trials.
        adr: The record that holds the result.
        question: What the case asks, in one sentence.
        base_commit: The commit before the result was recorded.
        result_commit: The commit that recorded the result.
        corpus: The corpus the declaration names, which must be iterate tier.
        experiment: The GENESIS experiment id, when there is one.
        outcome: The verdict the record holds.
        bars: Bar id to whether it was met, as the record states.
        reads: The files a trial should read, relative to the repository root.
    """

    key: str
    adr: str
    question: str
    base_commit: str
    result_commit: str
    corpus: str
    experiment: str | None
    outcome: str
    bars: dict[str, bool]
    reads: tuple[str, ...]

    @property
    def bar_count(self) -> int:
        """Return how many bars this case declares."""
        return len(self.bars)


#: The three cases, in the order they are run.
CASES: Final[tuple[Case, ...]] = (
    Case(
        key="adr-0418-sequential-column",
        adr="0418",
        question=(
            "Does a sequential column separate the two branches of the walk question, or does the "
            "corpus refuse it because two of its bars cannot both be met?"
        ),
        base_commit="96b0553",
        result_commit="d2215a0",
        corpus="phos-icssim-dev4-walk",
        experiment="E-0001",
        outcome="refused",
        bars={"b1": True, "b2": False, "b3": True, "b4": True, "b5": True, "b6": True},
        reads=(
            "docs/genesis/experiments/E-0001.json",
            "scripts/lane_sequential_walk.py",
        ),
    ),
    Case(
        key="adr-0315-walk-column",
        adr="0315",
        question=(
            "Does the walk column halve the remaining miss over the frozen champion, on the walk "
            "corpus the declaration names?"
        ),
        base_commit="5fd281d",
        result_commit="1f3875d",
        corpus="phos-icssim-dev4-walk",
        experiment=None,
        outcome="rejected",
        bars={"b1": False, "b2": True, "b3": True, "b4": True, "b5": True},
        reads=(
            "docs/adr/0314-the-walk-column-is-declared-before-it-is-scored.md",
            "scripts/lane_daily_walk.py",
        ),
    ),
    Case(
        key="adr-0336-law-page-invariants",
        adr="0336",
        question=(
            "Do the eight law-page invariants hold at zero over the merged tree, or does ordinary "
            "operation fill the alert budget and make the queue unstaffable?"
        ),
        base_commit="1be272c",
        result_commit="c503df8",
        corpus="phos-icssim-dev",
        experiment=None,
        outcome="kept",
        bars={f"b{i}": True for i in range(1, 9)},
        reads=(
            "docs/adr/0335-the-invariant-bar-is-redeclared-over-the-fixed-score-word-refusal.md",
            "scripts/lane_law_inlet_invariants.py",
        ),
    ),
)


# -- results -----------------------------------------------------------------------------------


@dataclass
class Trial:
    """One trial's outcome.

    Attributes:
        case: Which case.
        arm: ``single`` or ``team``.
        trial: Which of the three.
        runtime: The runtime that ran it.
        status: ``ran``, ``blocked`` or ``failed``.
        outcome: The verdict the trial produced, or ``unknown``.
        bars: Bar id to whether the trial said the bar was met.
        duration_s: Wall time, including every role in the team arm.
        tokens: Tokens reported across the whole trial, or None for "not reported".
        model: The model the runtime reported, or ``unknown``.
        note: The transcript, truncated.
    """

    case: str
    arm: str
    trial: int
    runtime: str
    status: str = "blocked"
    outcome: str = "unknown"
    bars: dict[str, bool] = field(default_factory=dict)
    duration_s: float = 0.0
    tokens: int | None = None
    model: str = "unknown"
    note: str = ""

    def matches(self, case: Case) -> bool:
        """Return whether this trial reproduced the recorded verdict and every bar.

        Args:
            case: The case it was run against.

        Returns:
            True when the verdict and the full bar set agree with the record.
        """
        return self.outcome == case.outcome and self.bars == case.bars

    def bars_correct(self, case: Case) -> int:
        """Return how many of the record's bars this trial got right.

        This is separate from :meth:`matches` because the verdict word and the analysis are not the
        same thing. On ADR 0315, three trials got all five bars exactly right and one of them
        answered ``refused`` where the record says ``rejected``. Scoring only the word would have
        counted that as a total miss and hidden that the analysis was perfect. The word is a
        convention; the bars are the work.

        Args:
            case: The case it was run against.

        Returns:
            How many bars agree with the record, out of how many the case declares.
        """
        return sum(1 for bar, value in case.bars.items() if self.bars.get(bar) == value)

    def bars_total(self, case: Case) -> int:
        """Return how many bars the case declares.

        Args:
            case: The case.

        Returns:
            The bar count.
        """
        return case.bar_count


@dataclass
class MutationScore:
    """What one mutation script found when it was actually run.

    Attributes:
        script: The script's name.
        seeded: How many defects it injects.
        caught: How many the suite caught.
        ran: Whether the script completed and printed a tally.
        note: Anything a human needs to read.
    """

    script: str
    seeded: int = 0
    caught: int = 0
    ran: bool = False
    note: str = ""


def _stamp() -> str:
    """Return the current UTC time as a sortable ISO 8601 string."""
    return datetime.now(UTC).isoformat(timespec="seconds")


def _case_dir(key: str) -> Path:
    """Return the directory one case's trials live in."""
    return ROOT / RUNS / key


def case_by_key(key: str) -> Case:
    """Return one case by its key.

    Args:
        key: The case key.

    Returns:
        The case.

    Raises:
        KeyError: If there is no such case.
    """
    for case in CASES:
        if case.key == key:
            return case
    raise KeyError(key)


# -- capability and runtime spread ---------------------------------------------------------------


def ready_runtimes() -> tuple[str, ...]:
    """Return the runtimes that answered a probe turn just now, in a fixed order.

    Returns:
        The runtime names. Empty when none is ready, which makes every trial blocked.
    """
    from phos.forge.adapters import detect

    ready = []
    for name in ("claude", "cursor", "codex"):
        try:
            if detect(name).state == "ready":
                ready.append(name)
        except KeyError:
            continue
    return tuple(ready)


def assign_runtimes(ready: tuple[str, ...]) -> dict[tuple[str, str, int], str]:
    """Spread the trials across the ready runtimes.

    Every case gets every arm on every ready runtime where the trials allow it, by rotating the
    starting runtime per case and per arm. With two runtimes and three trials that gives each case
    two trials on one and one on the other, and the case that starts on the second runtime balances
    the count across the whole run.

    Args:
        ready: The runtimes that work.

    Returns:
        ``(case key, arm, trial)`` to runtime. Empty when nothing is ready.
    """
    if not ready:
        return {}
    assignment: dict[tuple[str, str, int], str] = {}
    for case_index, case in enumerate(CASES):
        for arm_index, arm in enumerate(ARMS):
            for trial in range(1, TRIALS + 1):
                offset = case_index + arm_index + (trial - 1)
                assignment[(case.key, arm, trial)] = ready[offset % len(ready)]
    return assignment


def plan() -> int:
    """Print the cases, check their commits, and show the runtime spread.

    Returns:
        0 when every case can run, 1 when a commit is missing.
    """
    print("Cases:")
    ok = True
    for case in CASES:
        print(f"  {case.key}")
        print(f"    ADR {case.adr}: {case.question}")
        print(f"    base {case.base_commit}, result {case.result_commit}, corpus {case.corpus}")
        print(f"    recorded verdict: {case.outcome}, {case.bar_count} bars")
        for label, ref in (("base", case.base_commit), ("result", case.result_commit)):
            done = subprocess.run(
                ["git", "-C", str(ROOT), "cat-file", "-e", f"{ref}^{{commit}}"],
                capture_output=True,
                text=True,
                check=False,
            )
            if done.returncode != 0:
                print(f"    {label} commit {ref}: MISSING")
                ok = False
        present = (ROOT / "data" / case.corpus).is_dir()
        print(f"    corpus on disk: {present}")

    ready = ready_runtimes()
    print()
    print(f"Ready runtimes: {', '.join(ready) if ready else 'none'}")
    if not ready:
        print("  No trial can run. That is a blocked measurement, not a result.")
        return 1

    assignment = assign_runtimes(ready)
    print()
    print(f"Trials: {len(CASES)} cases x {len(ARMS)} arms x {TRIALS} trials = {len(assignment)}")
    counts: dict[str, int] = {}
    for runtime in assignment.values():
        counts[runtime] = counts.get(runtime, 0) + 1
    for runtime, count in sorted(counts.items()):
        print(f"  {runtime}: {count} trials")
    return 0 if ok else 1


# -- the task each trial is given ----------------------------------------------------------------


def build_task(case: Case, arm: str, role: str | None = None, prior: str = "") -> str:
    """Return the task one trial, or one role in a team trial, is given.

    Args:
        case: The case.
        arm: ``single`` or ``team``.
        role: The role, for the team arm.
        prior: What the roles before this one concluded.

    Returns:
        The prompt.
    """
    reads = "\n".join(f"- {path}" for path in case.reads)
    bar_ids = ", ".join(case.bars)
    bar_lines = "".join(f"{bar} [met or missed]\n" for bar in case.bars)
    common = (
        f"You are working in the PHOS repository at commit {case.base_commit}, which is the commit "
        f"before the result of ADR {case.adr} was recorded. You cannot see that result and must "
        "not look for it.\n\n"
        f"The question: {case.question}\n\n"
        "Read these files in the repository:\n"
        f"{reads}\n\n"
        "You are asked to judge, not to re-run. Measuring again is forbidden: these scores are "
        "spent, and the GENESIS gate refuses them.\n\n"
        f"State, for each declared bar, whether that bar would be met or missed. The bars are "
        f"{bar_ids}. Then state the overall verdict the bars imply, which must be exactly one of: "
        "kept, rejected, refused.\n\n"
        "Answer in this form, one line per bar, then the verdict line. Do not copy the words in "
        "brackets, choose for yourself:\n"
        f"{bar_lines}"
        "verdict: [one of kept, rejected, refused]\n\n"
        "The three verdict words mean different things and the difference matters. Use kept when "
        "every bar is met. Use rejected when the score was judged and at least one bar was "
        "missed. Use refused when the run could not be judged at all, for example because two "
        "bars cannot both be met whatever is measured."
    )
    if arm == "single":
        return common

    slice_by_role = {
        "principal_research_scientist": (
            "Your part is the evidence: read the declaration or the bar record, and state what "
            "each bar actually requires and whether the code could satisfy it. Do not write the "
            "final verdict."
        ),
        "applied_scientist": (
            "Your part is the mechanism: read the code the declaration names and reason about what "
            "it computes, so the bars can be judged against real behaviour rather than intent. Do "
            "not write the final verdict."
        ),
        "adversarial_researcher": (
            "Your part is the attack: find the reading of the bars under which this passes when it "
            "should not, or the reason a bar cannot be met at all. Say which bars you think are "
            "genuinely met. Do not write the final verdict."
        ),
        "verification_engineer": (
            "Your part is the verdict: weigh what the other roles concluded and state the final "
            "answer in the required form."
        ),
    }
    parts = [common, slice_by_role.get(role or "", "")]
    if prior:
        parts.append("## What the roles before you concluded\n\n" + prior)
    return "\n\n".join(part for part in parts if part)


def read_verdict(transcript: str, case: Case) -> tuple[dict[str, bool], str]:
    """Read the per-bar answers and the overall verdict out of a transcript.

    The transcript contains the prompt as well as the answer, and the prompt names all three
    verdicts, so a substring search finds "kept" in the question and reports it as the answer. That
    happened on the first real run of this harness. The reader therefore takes a line that is only
    the verdict, or one labelled ``verdict:``, and the first such line wins because the answer comes
    before the echo.

    The bar answers are read the same way: a line that begins with the bar id and then says met or
    missed. The last such line wins, because a role that corrects itself later in its answer means
    the later statement.

    Args:
        transcript: The combined output.
        case: The case, which fixes the bar ids to look for.

    Returns:
        ``(bars, outcome)``. An unreadable transcript gives an empty mapping and ``unknown``, which
        is reported as a miss rather than counted as agreement.
    """
    lines = [line.strip().strip("*_` .") for line in transcript.splitlines()]
    lowered = [line.lower() for line in lines]

    bars: dict[str, bool] = {}
    for bar in case.bars:
        for line in lowered:
            if line.startswith(f"{bar} met") or line.startswith(f"{bar}: met"):
                bars[bar] = True
            elif line.startswith(f"{bar} missed") or line.startswith(f"{bar}: missed"):
                bars[bar] = False

    outcome = "unknown"
    for line, raw in zip(lowered, lines, strict=False):
        candidate = line.removeprefix("verdict:").strip()
        if candidate in {"refused", "rejected", "kept"}:
            outcome = candidate
            break
        del raw
    return bars, outcome


# -- running -------------------------------------------------------------------------------------


def _make_worktrees(case: Case, arm: str, trial: int) -> dict[str, Path]:
    """Create the worktrees one trial needs, all based on the commit before the result.

    Args:
        case: The case.
        arm: ``single`` or ``team``.
        trial: Which trial.

    Returns:
        Role to worktree path. Empty when one could not be made.
    """
    from phos.forge import worktree

    roles = ["single"] if arm == "single" else list(TEAM_ROLES)
    made: dict[str, Path] = {}
    for role in roles:
        branch = f"forge/baseline/{case.adr}-{arm}-{trial}-{role}"
        try:
            one = worktree.create(
                ROOT,
                operation=f"baseline-{case.adr}-{arm}-{trial}",
                role=role,
                branch=branch,
                base=case.base_commit,
            )
        except worktree.WorktreeError as error:
            print(f"    worktree for {role} refused: {error}", file=sys.stderr)
            _clean_worktrees(case, arm, trial)
            return {}
        made[role] = one.path
    return made


def _clean_worktrees(case: Case, arm: str, trial: int) -> None:
    """Remove the worktrees and branches one trial made.

    A trial that leaves its worktrees behind makes the next run find every path claimed. That
    happened on the first attempt here, so the cleanup is part of the harness.

    Args:
        case: The case.
        arm: ``single`` or ``team``.
        trial: Which trial.
    """
    from phos.forge import worktree

    roles = ["single"] if arm == "single" else list(TEAM_ROLES)
    for role in roles:
        path = worktree.default_path(ROOT, f"baseline-{case.adr}-{arm}-{trial}", role)
        branch = f"forge/baseline/{case.adr}-{arm}-{trial}-{role}"
        if path.exists():
            try:
                one = worktree.Worktree(
                    path=path, branch=branch, base_commit=case.base_commit, role=role
                )
                worktree.remove(one, force=True)
            except worktree.WorktreeError:
                pass
        subprocess.run(
            ["git", "-C", str(ROOT), "branch", "-D", branch],
            capture_output=True,
            text=True,
            check=False,
        )
    worktree.prune(ROOT)


def _ask(runtime: str, tree: Path, task: str, case: Case) -> tuple[str, int | None, str, bool]:
    """Ask one runtime one question in one worktree.

    Args:
        runtime: The runtime name.
        tree: The worktree.
        task: The prompt.
        case: The case, for the base commit.

    Returns:
        ``(output, tokens, model, ok)``.
    """
    from phos.forge.adapters import adapter_for
    from phos.forge.protocol import RoleRequest

    request = RoleRequest(
        operation=f"baseline-{case.adr}",
        role="applied_scientist",
        task=task,
        worktree=tree,
        base_commit=case.base_commit,
    )
    try:
        result = adapter_for(runtime).run(request)
    except Exception as error:  # a runtime's own failure is data, not a crash
        return f"the runtime refused: {error}", None, "unknown", False
    return result.stdout + "\n" + result.stderr, result.tokens, result.model, result.status == "ok"


def run_one(case: Case, arm: str, trial: int, runtime: str) -> Trial:
    """Run one trial.

    The single arm asks one agent for the answer. The team arm runs the mandate roles in sequence in
    their own worktrees, each seeing what the previous role concluded, and the last one writes the
    answer that is compared.

    A failure is recorded rather than raised, so one bad trial does not lose the rest. A trial whose
    runtime cannot answer is ``blocked``, and a trial that started and ended for a reason other than
    the task is ``failed``. Neither counts as a loss for its arm.

    Args:
        case: The case.
        arm: ``single`` or ``team``.
        trial: Which trial.
        runtime: The runtime to use.

    Returns:
        The trial.
    """
    from phos.forge.adapters import detect
    from phos.forge.redline import check_output

    capability = detect(runtime)
    if capability.state != "ready":
        return Trial(
            case=case.key,
            arm=arm,
            trial=trial,
            runtime=runtime,
            status="blocked",
            note=f"{runtime} is {capability.state}: {capability.detail}",
        )

    started = time.monotonic()
    trees = _make_worktrees(case, arm, trial)
    if not trees:
        return Trial(
            case=case.key,
            arm=arm,
            trial=trial,
            runtime=runtime,
            status="failed",
            note="a worktree could not be created",
        )

    transcript = ""
    tokens: int | None = None
    model = "unknown"
    status = "ran"
    try:
        if arm == "single":
            output, got, said, ok = _ask(runtime, trees["single"], build_task(case, arm), case)
            transcript = output
            tokens = got
            model = said
            if not ok:
                status = "failed"
        else:
            prior = ""
            for role in TEAM_ROLES:
                output, got, said, ok = _ask(
                    runtime, trees[role], build_task(case, arm, role, prior), case
                )
                transcript += f"\n\n=== {role} ===\n{output}"
                if got is not None:
                    tokens = (tokens or 0) + got
                if said != "unknown":
                    model = said
                if not ok:
                    status = "failed"
                    break
                prior += f"\n### {role}\n{output[:1500]}\n"
    finally:
        _clean_worktrees(case, arm, trial)

    red = check_output(ROOT, transcript)
    if not red.clean:
        status = "failed"
        transcript += f"\n\nFORGE: the output named a sealed path ({red.summary()})"

    bars, outcome = read_verdict(transcript, case)
    # A turn that exited zero but produced no answer is not a clean trial. Cursor's connection
    # dropped on one trial and the transcript held only "Connection lost, reconnecting", which the
    # adapter reported as success because the process exited zero. Counting that as a clean trial
    # would have put a trial that said nothing into the comparison and scored it a miss, which
    # blames the arm for the network.
    if status == "ran" and not bars:
        status = "failed"
        transcript += "\n\nFORGE: the turn produced no bar answers, so it is not a clean trial"
    if status == "ran" and outcome == "unknown":
        status = "failed"
        transcript += "\n\nFORGE: the turn produced no verdict, so it is not a clean trial"
    return Trial(
        case=case.key,
        arm=arm,
        trial=trial,
        runtime=runtime,
        status=status,
        outcome=outcome,
        bars=bars,
        duration_s=round(time.monotonic() - started, 1),
        tokens=tokens,
        model=model,
        note=transcript[:6000],
    )


def _resume_from(
    out: Path, assignment: dict[tuple[str, str, int], str]
) -> dict[tuple[str, str, int], Trial]:
    """Return the trials a previous run of this same start time already finished.

    A run is identified by the timestamp in its file name, so restarting the command resumes its
    own file rather than starting a second one. Only trials that ran cleanly are reused: a blocked
    or failed trial is worth trying again, because the reason may have gone away, and a clean one
    is not, because a repeat is not a second trial.

    Args:
        out: The runs directory.
        assignment: What this run would do.

    Returns:
        ``(case, arm, trial)`` to the finished trial.
    """
    finished: dict[tuple[str, str, int], Trial] = {}
    for path in sorted(out.glob("trials-*.json")):
        try:
            payload = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if payload.get("complete"):
            continue
        for entry in payload.get("trials", []):
            one = _normalise(Trial(**entry))
            key = (one.case, one.arm, one.trial)
            if one.status == "ran" and key in assignment:
                finished[key] = one
    return finished


def score_mutations(reuse: bool = True) -> tuple[MutationScore, ...]:
    """Run every ``scripts/mutate_*.py`` and read its tally, or reuse a measured set.

    This is a real run, not a listing. Each script copies ``src/``, injects one defect at a time and
    runs the test suite against the mutant, so it takes minutes. The tally it prints is
    ``caught/total caught``, which is what a defect-detection number has to mean.

    ``reuse`` is on by default because the scripts do not depend on an agent runtime. Once they
    have been run against a commit, running them again measures the same thing. The scores are
    stored with the commit they were measured at, and a score from a different commit is not reused.

    Args:
        reuse: Whether to use a stored score measured at the current commit.

    Returns:
        One entry per script. A script that fails to run is reported with ``ran`` False and its
        reason, never with a tidy zero.
    """
    stored = ROOT / RUNS / "mutation-scores.json"
    head = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True, check=False
    ).stdout.strip()
    if reuse and stored.is_file():
        try:
            payload = json.loads(stored.read_text())
        except (OSError, json.JSONDecodeError):
            payload = None
        if isinstance(payload, dict) and payload.get("commit") in {head, None}:
            entries = payload.get("scores")
            if isinstance(entries, list) and entries:
                print(f"  reusing {len(entries)} stored mutation scores")
                return tuple(MutationScore(**entry) for entry in entries)

    found: list[MutationScore] = []
    for script in sorted((ROOT / "scripts").glob("mutate_*.py")):
        done = subprocess.run(
            [sys.executable, str(script)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        text = done.stdout + done.stderr
        tally = re.search(r"(\d+)/(\d+)\s+caught", text)
        if tally:
            found.append(
                MutationScore(
                    script=script.name,
                    caught=int(tally.group(1)),
                    seeded=int(tally.group(2)),
                    ran=True,
                    note="the script ran and printed its tally",
                )
            )
            continue
        moved = re.search(r"mutation '([^']+)': target text appears 0 time", text)
        if moved:
            note = (
                f"aborted before any tally: mutation {moved.group(1)!r} targets text that is no "
                "longer in the source, so this script cannot score until that target is updated. "
                "Not reported as zero, because it did not measure zero."
            )
        else:
            tail = [line for line in text.strip().splitlines() if line.strip()][-1:]
            note = f"no tally printed; exit {done.returncode}: {(tail[0] if tail else '')[:160]}"
        found.append(MutationScore(script=script.name, ran=False, note=note))

    stored.parent.mkdir(parents=True, exist_ok=True)
    stored.write_text(
        json.dumps(
            {"commit": head, "measured_at": _stamp(), "scores": [asdict(s) for s in found]},
            indent=2,
        )
        + "\n"
    )
    return tuple(found)


def run(parallel: int = 1) -> int:
    """Run every case, every arm and every trial, saving after each one.

    Each trial is written to disk as soon as it finishes, under a timestamped file, so an
    interrupted run keeps what it measured. The first version wrote only at the end, and a run that
    was killed after forty minutes left nothing at all: forty minutes of real trials lost because
    the harness was tidy. A baseline is expensive and a partial result that says which trials it
    holds is worth more than no result.

    Returns:
        0 when every trial ran cleanly, 1 when any was blocked or failed.
    """
    ready = ready_runtimes()
    assignment = assign_runtimes(ready)
    started_at = _stamp()
    out = ROOT / RUNS
    out.mkdir(parents=True, exist_ok=True)
    stamp = started_at.replace(":", "").replace("-", "")
    partial = out / f"trials-{stamp}.json"

    def save(results: list[Trial], mutations: tuple[MutationScore, ...]) -> None:
        """Write what has been measured so far.

        Args:
            results: The trials finished so far.
            mutations: The mutation scores, when they have been run.
        """
        payload = {
            "generated_at": started_at,
            "complete": len(results) == len(CASES) * len(ARMS) * TRIALS,
            "ready_runtimes": list(ready),
            "cases": [asdict(case) for case in CASES],
            "trials": [asdict(trial) for trial in results],
            "mutation_scores": [asdict(score) for score in mutations],
        }
        partial.write_text(json.dumps(payload, indent=2) + "\n")

    if not assignment:
        print("no runtime answered a probe, so no trial can run", file=sys.stderr)
        blocked = [
            Trial(
                case=case.key,
                arm=arm,
                trial=trial,
                runtime="none",
                status="blocked",
                note="no runtime answered a probe turn",
            )
            for case in CASES
            for arm in ARMS
            for trial in range(1, TRIALS + 1)
        ]
        save(blocked, ())
        return 1

    print(f"ready runtimes: {', '.join(ready)}")
    results: list[Trial] = []
    save(results, ())

    # Resume from a file already in this shape: a trial that finished cleanly is not run again,
    # because a second attempt at the same case on the same runtime is a repeat, not a trial.
    already = _resume_from(out, assignment)
    if already:
        print(f"resuming: {len(already)} trials already finished in this run")
        results.extend(already.values())
        # Save immediately, so this run's own file carries the resumed trials too. Without this the
        # file says zero until the first new trial finishes, and a reader would think the resumed
        # work had been lost rather than carried.
        save(results, ())

    remaining = [
        (case, arm, trial)
        for case in CASES
        for arm in ARMS
        for trial in range(1, TRIALS + 1)
        if (case.key, arm, trial) not in already
    ]
    print(f"{len(remaining)} trials to run, {parallel} at a time", flush=True)

    def finish(case_key: str, arm: str, trial: int, one: Trial) -> None:
        """Record one finished trial and save.

        Args:
            case_key: The case key.
            arm: The arm.
            trial: Which trial.
            one: The result.
        """
        print(
            f"  {case_key} {arm} {trial}: {one.status}, {one.outcome}, "
            f"{len(one.bars)} bars, {one.duration_s}s",
            flush=True,
        )
        results.append(one)
        save(results, ())

    if parallel > 1:
        # Trials are independent by construction: each one has its own worktree on its own branch,
        # reads nothing another trial writes, and records its own result. Running them at once is
        # therefore safe, and it is the difference between two hours and one on a single runtime.
        running: dict[concurrent.futures.Future[Trial], tuple[str, str, int]] = {}
        pending = list(remaining)
        with concurrent.futures.ThreadPoolExecutor(max_workers=parallel) as pool:
            while pending or running:
                while pending and len(running) < parallel:
                    case, arm, trial = pending.pop(0)
                    key = (case.key, arm, trial)
                    future = pool.submit(run_one, case, arm, trial, assignment[key])
                    running[future] = key
                done, _ = concurrent.futures.wait(
                    running, return_when=concurrent.futures.FIRST_COMPLETED
                )
                for future in done:
                    key = running.pop(future)
                    finish(key[0], key[1], key[2], future.result())
    else:
        for case, arm, trial in remaining:
            one = run_one(case, arm, trial, assignment[(case.key, arm, trial)])
            finish(case.key, arm, trial, one)

    print("scoring seeded defects ...", flush=True)
    mutations = score_mutations()
    for score in mutations:
        state = f"{score.caught}/{score.seeded}" if score.ran else "did not run"
        print(f"    {score.script}: {state}")

    save(results, mutations)
    (out / "trials.json").write_text(partial.read_text())
    print(f"wrote {partial.relative_to(ROOT)}")

    bad = [one for one in results if one.status != "ran"]
    if bad:
        print(f"{len(bad)} of {len(results)} trials did not run cleanly")
        return 1
    return 0


# -- the report ----------------------------------------------------------------------------------


def _latest_run() -> tuple[Path, dict[str, object]] | None:
    """Return the newest run that produced at least one trial, and its path.

    Returns:
        ``(path, payload)``, or None when no run has happened.
    """
    candidates = list((ROOT / RUNS).glob("trials-*.json"))
    if not candidates:
        return None
    runs: list[tuple[str, Path, dict[str, object]]] = []
    for path in candidates:
        parsed = json.loads(path.read_text())
        runs.append((str(parsed.get("generated_at", "")), path, parsed))
    runs.sort()
    if not runs:
        return None
    _, path, payload = runs[-1]
    return path, payload


def _normalise(one: Trial) -> Trial:
    """Return a trial with its status re-derived from what it actually produced.

    A trial is only clean if it answered every bar and stated a verdict. This is applied at report
    time as well as at run time, because a run records what its own code believed: one trial here
    was written as ``ran`` by an earlier version that trusted the exit status, and its transcript
    held only "Connection lost, reconnecting". A trial that said nothing must not be scored as a
    miss, and the report cannot rely on the runner having had the rule when it wrote the file.

    Args:
        one: The trial as recorded.

    Returns:
        The trial, with ``status`` corrected and a note saying why if it changed.
    """
    if one.status != "ran":
        return one
    if not one.bars:
        return Trial(
            **{
                **asdict(one),
                "status": "failed",
                "note": one.note + "\n\nFORGE: no bar answers, so not a clean trial",
            }
        )
    if one.outcome == "unknown":
        return Trial(
            **{
                **asdict(one),
                "status": "failed",
                "note": one.note + "\n\nFORGE: no verdict, so not a clean trial",
            }
        )
    return one


def _trials_of(payload: dict[str, object]) -> list[Trial]:
    """Return the trials in a payload as objects, each normalised.

    Args:
        payload: A run's JSON.

    Returns:
        The trials.
    """
    raw = payload.get("trials", [])
    assert isinstance(raw, list)
    return [_normalise(Trial(**entry)) for entry in raw]


def _case_of(key: str) -> Case | None:
    """Return the case a trial belongs to, or None when the case is no longer declared.

    Args:
        key: The case key.

    Returns:
        The case, or None.
    """
    for case in CASES:
        if case.key == key:
            return case
    return None


def report() -> int:
    """Write the plain-language report, including every case the team lost.

    Two measures are reported side by side, because they answer different questions. The **verdict
    word** asks whether a trial named the outcome the record named. The **bar accuracy** asks
    whether it analysed the case correctly. On ADR 0315 both mattered: three trials got all five
    bars right and one of those answered ``refused`` where the record says ``rejected``. Reporting
    only the word would have scored a perfect analysis as a total miss.

    Returns:
        0 when a report was written, 1 when there is nothing to report.
    """
    latest = _latest_run()
    if latest is None:
        print(f"no trials under {RUNS.as_posix()}. Run `run` first.", file=sys.stderr)
        return 1
    source, payload = latest
    trials = _trials_of(payload)
    raw_mutations = payload.get("mutation_scores", [])
    assert isinstance(raw_mutations, list)
    mutations = [MutationScore(**entry) for entry in raw_mutations]
    raw_ready = payload.get("ready_runtimes", [])
    assert isinstance(raw_ready, list)
    ready: list[str] = [str(name) for name in raw_ready]

    blocked = [one for one in trials if one.status == "blocked"]
    failed = [one for one in trials if one.status == "failed"]
    ran = [one for one in trials if one.status == "ran"]

    lines: list[str] = [
        "# FORGE baseline backtest",
        "",
        f"Generated {payload.get('generated_at', '')}, from",
        f"`{source.relative_to(ROOT).as_posix()}`.",
        f"Runtimes that answered a probe: {', '.join(ready) if ready else 'none'}.",
        "",
        "Three recorded results were put back in front of two kinds of worker: one agent on its "
        "own, and a team of four mandate roles in sequence, each in its own copy of the",
        "repository.",
        "Every trial was given the declaration and code as they stood at the commit before the "
        "result was recorded, so it could not see the answer. Three trials each.",
        "",
        "What this run cannot measure is in `BASELINE_METHOD.md`: one runtime was available, and "
        "that runtime returns an answer without its reasoning.",
        "",
        "## The cases",
        "",
        "| case | record | recorded verdict | bars met | corpus |",
        "|---|---|---|---|---|",
    ]
    for case in CASES:
        met = sum(1 for value in case.bars.values() if value)
        lines.append(
            f"| {case.key} | ADR {case.adr} | {case.outcome} | {met} of {case.bar_count} | "
            f"{case.corpus} |"
        )
    lines.append("")

    lines += [
        "## Every trial",
        "",
        "| case | arm | trial | runtime | verdict said | verdict right | bars right | time (s) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for one in trials:
        owner = _case_of(one.case)
        if one.status != "ran":
            said = one.status
            word = "-"
            bars = f"0 of {owner.bar_count}" if owner else "-"
        else:
            said = one.outcome
            word = "yes" if owner and one.outcome == owner.outcome else "no"
            bars = f"{one.bars_correct(owner)} of {owner.bar_count}" if owner else "-"
        lines.append(
            f"| {one.case} | {one.arm} | {one.trial} | {one.runtime} | {said} | {word} | {bars} | "
            f"{one.duration_s} |"
        )
    lines.append("")

    if blocked:
        lines += [
            "## Trials that could not start",
            "",
            f"{len(blocked)} of {len(trials)} did not start. They count for neither arm and",
            "are not",
            "a result.",
            "",
        ]
        lines += [f"- {one.case}, {one.arm} {one.trial}: {one.note[:160]}" for one in blocked]
        lines.append("")

    if failed:
        lines += [
            "## Trials that failed mechanically",
            "",
            f"{len(failed)} of {len(trials)} started and ended for a reason other than the task.",
            "Each counts for neither arm. Counting one as a miss would make its arm look",
            "worse than",
            "the evidence says; counting one as a hit would make it look better.",
            "",
        ]
        for one in failed:
            owner = _case_of(one.case)
            right = one.bars_correct(owner) if owner else 0
            lines.append(
                f"- {one.case}, {one.arm} {one.trial} on {one.runtime}: {one.outcome}, "
                f"{right} bars right"
            )
        lines.append("")

    lines += ["## Case by case", ""]
    for case in CASES:
        mine = [one for one in trials if one.case == case.key and one.status == "ran"]
        section = _case_section(case, mine)
        if len(mine) < len(ARMS) * TRIALS:
            section.insert(
                0,
                f"**Incomplete: {len(mine)} of {len(ARMS) * TRIALS} trials for this case are in "
                "this report.**",
            )
            section.insert(1, "")
        lines += section

    lines += [
        "## Seeded defects",
        "",
        "Each `scripts/mutate_*.py` was run for real: it copies the package, injects one",
        "defect at a",
        "time and runs the test suite against the mutant. This half needs no agent, so it is",
        "measurable whatever the runtimes are doing.",
        "",
        "| script | defects seeded | caught by the suite |",
        "|---|---|---|",
    ]
    for score in mutations:
        seeded = str(score.seeded) if score.ran else "did not run"
        caught = str(score.caught) if score.ran else score.note[:70]
        lines.append(f"| {score.script} | {seeded} | {caught} |")
    scored = [score for score in mutations if score.ran]
    if scored:
        lines += [
            "",
            f"Across the scripts that ran, {sum(s.caught for s in scored)} of "
            f"{sum(s.seeded for s in scored)} seeded defects were caught by the test suite. A "
            "script that aborted is listed with its reason and is not counted as zero.",
        ]
    lines.append("")
    lines.append(
        "Defects found by the adversarial role itself could not be measured, because the runtime "
        "returns no reasoning trace. See `BASELINE_METHOD.md`."
    )
    lines.append("")

    lines += [
        "## Time and spend",
        "",
        "| arm | clean trials | mean time (s) | tokens |",
        "|---|---|---|---|",
    ]
    for arm in ARMS:
        arm_trials = [one for one in ran if one.arm == arm]
        if not arm_trials:
            lines.append(f"| {arm} | 0 | - | - |")
            continue
        mean = sum(one.duration_s for one in arm_trials) / len(arm_trials)
        known = [one.tokens for one in arm_trials if one.tokens is not None]
        spend = str(sum(known)) if known else "not reported"
        lines.append(f"| {arm} | {len(arm_trials)} | {mean:.1f} | {spend} |")
    lines += [
        "",
        "Token counts are what the runtime reported. Where it reported nothing this says so rather",
        "than showing zero, because zero would read as free.",
        "",
        "## The plain answer",
        "",
        _overall(ran, blocked, failed, trials),
        "",
        "## What this report gates",
        "",
        "This is the report the first Atlas cycle waits behind. Elijah agreed to begin cycle 1 on "
        "Q-0007 before this run finished. His agreement is recorded in",
        "`docs/method/approvals/elijah-agrees-despite-baseline.md`, and this report states plainly",
        "that the cycle began on a baseline still in progress rather than a completed one.",
        "",
    ]

    target = ROOT / REPORT
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {REPORT.as_posix()}")
    return 0


def _case_section(case: Case, mine: list[Trial]) -> list[str]:
    """Return the report lines for one case.

    Args:
        case: The case.
        mine: The clean trials for it.

    Returns:
        The lines.
    """
    single = [one for one in mine if one.arm == "single"]
    team = [one for one in mine if one.arm == "team"]
    single_words = sum(1 for one in single if one.outcome == case.outcome)
    team_words = sum(1 for one in team if one.outcome == case.outcome)
    single_bars = sum(one.bars_correct(case) for one in single)
    team_bars = sum(one.bars_correct(case) for one in team)
    possible = len(single) * case.bar_count
    team_possible = len(team) * case.bar_count

    lines = [
        f"### {case.key}, ADR {case.adr}",
        "",
        case.question,
        "",
        f"The record says **{case.outcome}**, with "
        f"{sum(1 for v in case.bars.values() if v)} of {case.bar_count} bars met.",
        "",
        "| arm | clean trials | verdict word right | bars right |",
        "|---|---|---|---|",
        f"| one agent | {len(single)} | {single_words} | {single_bars} of {possible} |",
        f"| the team | {len(team)} | {team_words} | {team_bars} of {team_possible} |",
        "",
        _case_sentence(single_words, len(single), team_words, len(team), case.outcome),
        "",
    ]
    return lines


def _case_sentence(
    single_hits: int, single_n: int, team_hits: int, team_n: int, recorded: str
) -> str:
    """Return the sentence for one case, in the same voice whether the team won or lost.

    Args:
        single_hits: How many single-agent trials matched.
        single_n: How many single-agent trials were clean.
        team_hits: How many team trials matched.
        team_n: How many team trials were clean.
        recorded: The verdict the record holds.

    Returns:
        One sentence.
    """
    if single_n == 0 and team_n == 0:
        return "No clean trial ran for this case, so it says nothing either way."
    if single_n == 0:
        return "Only the team produced a clean trial here, so there is nothing to compare it with."
    if team_n == 0:
        return "Only the single agent produced a clean trial here, so there is nothing to compare."
    if team_hits > single_hits:
        return f"On this case the team did better, reaching the recorded {recorded} more often."
    if single_hits > team_hits:
        return (
            f"On this case **the team lost**: the single agent reached the recorded {recorded} "
            "more often."
        )
    return (
        f"On this case the two arms matched the recorded {recorded} equally often, so the case "
        "does not separate them."
    )


def _overall(
    ran: list[Trial], blocked: list[Trial], failed: list[Trial], all_trials: list[Trial]
) -> str:
    """Return the plain-language answer for the foot of the report.

    Args:
        ran: Trials that ran cleanly.
        blocked: Trials that never started.
        failed: Trials that failed mechanically.
        all_trials: Every trial in the run.

    Returns:
        Two or three sentences that account for every trial.
    """
    if not ran:
        return (
            "No trial ran cleanly, so this report makes no claim about whether a team helps. "
            "Whatever stopped them is listed above with its reason, and the same command can be "
            "run again once that is fixed."
        )

    single = [one for one in ran if one.arm == "single"]
    team = [one for one in ran if one.arm == "team"]
    single_hits = 0
    team_hits = 0
    for one in single:
        case = _case_of(one.case)
        if case is not None and one.matches(case):
            single_hits += 1
    for one in team:
        case = _case_of(one.case)
        if case is not None and one.matches(case):
            team_hits += 1

    if not single or not team:
        core = "Only one arm finished a clean trial, so no comparison between the arms is possible."
    elif team_hits > single_hits:
        core = (
            f"The team reached the recorded verdict more often than the single agent did, "
            f"{team_hits} times against {single_hits}. That is a direction, and with three trials "
            "per case per arm it is not yet a measurement."
        )
    elif single_hits > team_hits:
        core = (
            f"The team did not win. The single agent reached the recorded verdict more often, "
            f"{single_hits} times against {team_hits}, and that is the finding. The four Atlas "
            "cycles wait on your agreement rather than on this report."
        )
    else:
        core = (
            f"The two arms reached the recorded verdict equally often, {team_hits} times each. On "
            "this many trials that difference separates nothing."
        )

    accounted = (
        f"{len(ran)} of {len(all_trials)} trials ran cleanly. "
        f"{len(failed)} failed mechanically and {len(blocked)} could not start; every one is "
        "listed above and counted for neither arm."
    )
    expected = len(CASES) * len(ARMS) * TRIALS
    if len(all_trials) < expected:
        accounted += (
            f" This run holds {len(all_trials)} of the {expected} planned trials, so it is not "
            "complete and the comparison above covers only the trials in it."
        )
    return f"{core} {accounted}"


def main() -> int:
    """Run one subcommand.

    Returns:
        The process exit code.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="subcommand", required=True)
    subparsers.add_parser("plan", help="print the cases and the runtime spread")
    running = subparsers.add_parser("run", help="run every case, arm and trial")
    running.add_argument("--parallel", type=int, default=1, help="how many trials to run at once")
    subparsers.add_parser("report", help="write the plain-language report")
    args = parser.parse_args()
    if args.subcommand == "plan":
        return plan()
    if args.subcommand == "run":
        return run(args.parallel)
    return report()


if __name__ == "__main__":
    sys.exit(main())

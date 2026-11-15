"""The subcommands behind ``scripts/genesis.py``.

The entry point is a script because both Cursor and Claude Code drive it as a command, but the
work lives here so it can be tested without a subprocess and so ``mypy --strict`` sees it as part
of the package rather than as a loose script.

Exit codes are the contract: ``0`` fine, ``2`` the arguments do not make sense, ``3`` refused.
``gate`` is the one check in this repository that stops rather than warns, because the record it
reads carries a machine-readable kind and a regex over an English title does not.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Final

from phos.genesis.gatehost import decide
from phos.genesis.levels import LEVEL_NAMES, ladder_report, promotable
from phos.genesis.records import Experiment, Finding, Measurement, Question
from phos.genesis.render import declaration_adr, finding_summary, verdict_adr
from phos.genesis.reports import session_report
from phos.genesis.store import RECORD_DIR, Store
from phos.genesis.templates import TEMPLATES
from phos.genesis.tiercheck import disagreement, resolve

#: The repository root, three parents up from ``src/phos/genesis/cli.py``.
ROOT: Final = Path(__file__).resolve().parents[3]

EXIT_USAGE: Final = 2
EXIT_REFUSED: Final = 3


def git(root: Path, *args: str) -> str:
    """Return the trimmed stdout of a git command run in ``root``, or "" if it fails.

    Args:
        root: The repository the command runs in. It is the store's root rather than this
            file's, so a store opened elsewhere is asked about its own history.
        *args: The git arguments.

    Returns:
        Trimmed stdout, or an empty string on any failure.
    """
    try:
        done = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return ""
    return done.stdout.strip()


def load_json(path: Path) -> dict[str, Any]:
    """Return the object in ``path``.

    Args:
        path: A JSON file holding one object.

    Returns:
        The decoded object.

    Raises:
        SystemExit: If the file is missing or is not a JSON object.
    """
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"{path}: {error}") from error
    if not isinstance(loaded, dict):
        raise SystemExit(f"{path}: expected a JSON object")
    return loaded


def committed_and_unmodified(path: Path, root: Path) -> tuple[bool, bool]:
    """Return whether ``path`` is in ``HEAD`` and whether the working copy still matches it.

    Args:
        path: A path inside the repository.
        root: The repository root.

    Returns:
        ``(committed, unmodified)``. A declaration that is committed but has been edited since is
        not a declaration that predates the run, which is the whole contract.
    """
    relative = _rel(path, root).as_posix()
    committed = (
        subprocess.run(
            ["git", "cat-file", "-e", f"HEAD:{relative}"],
            cwd=root,
            capture_output=True,
        ).returncode
        == 0
    )
    unmodified = (
        subprocess.run(
            ["git", "diff", "--quiet", "HEAD", "--", relative],
            cwd=root,
            capture_output=True,
        ).returncode
        == 0
    )
    return committed, unmodified


def _rel(path: Path, root: Path) -> Path:
    """Return ``path`` relative to ``root`` where possible, else unchanged.

    Args:
        path: The path to shorten for display.
        root: The repository root.

    Returns:
        The relative path, or ``path`` when it lies outside ``root``.
    """
    try:
        return path.resolve().relative_to(root.resolve())
    except ValueError:
        return path


# -- subcommands -------------------------------------------------------------------------------


def cmd_state(store: Store, _: argparse.Namespace) -> int:
    """Print the current research state: what is open, what is in flight, what is established."""
    snapshot = store.snapshot()
    questions, experiments, findings = (
        snapshot.questions,
        snapshot.experiments,
        snapshot.findings,
    )
    open_questions = [q for q in questions.values() if q.status in ("open", "investigating")]
    in_flight = [e for e in experiments.values() if e.phase == "declared"]
    judged = [e for e in experiments.values() if e.phase == "judged"]
    kept = [e for e in judged if e.verdict is not None and e.verdict.outcome == "kept"]
    broken = store.audit()

    print(f"GENESIS state — {RECORD_DIR}")
    print(f"  questions:   {len(questions)} ({len(open_questions)} open or investigating)")
    print(f"  experiments: {len(experiments)} ({len(in_flight)} declared and not yet measured)")
    print(f"  judged:      {len(judged)} ({len(kept)} kept, {len(judged) - len(kept)} refused)")
    print(
        "  ladder:      "
        + ", ".join(
            f"{name} {count}" for name, count in ladder_report(list(findings.values())).items()
        )
    )
    print(f"  integrity:   {'clean' if not broken else f'{len(broken)} problem(s)'}")
    if in_flight:
        print("\ndeclared, awaiting a run:")
        for experiment in sorted(in_flight, key=lambda e: e.id):
            print(f"  {experiment.id}  {experiment.declared.command}")
    if broken:
        print("\nintegrity problems (run `audit` for all of them):")
        for problem in broken[:5]:
            print(f"  {problem.path}: {problem.problem}")
    if snapshot.unreadable:
        # A state that silently omits a record it could not read is describing a record it has
        # not fully read. Name them and exit non-zero; the rest of the state above still stands.
        print(
            f"\n{len(snapshot.unreadable)} record(s) could not be read and are NOT counted above:"
        )
        for problem in snapshot.unreadable:
            print(f"  {problem.path}: {problem.problem}")
        return EXIT_REFUSED
    return 0


def cmd_next(store: Store, args: argparse.Namespace) -> int:
    """Print open questions, ranked by the charter's section XII criteria."""
    questions = [q for q in store.questions().values() if q.status in ("open", "investigating")]
    if not questions:
        print("no open questions. `ask --from q.json` opens one.")
        return 0
    ranked = sorted(questions, key=lambda q: (-q.priority.rank(), q.id))
    for question in ranked[: args.number]:
        print(f"{question.id}  rank {question.priority.rank():>2}  {question.title}")
        print(f"            gap: {question.gap}")
    return 0


def cmd_template(_: Store, args: argparse.Namespace) -> int:
    """Print the JSON skeleton for one record kind."""
    print(json.dumps(TEMPLATES[args.kind], indent=2))
    return 0


def cmd_ask(store: Store, args: argparse.Namespace) -> int:
    """Register a research question."""
    payload = load_json(args.source)

    def build(record_id: str) -> Question:
        return Question.model_validate({**payload, "id": record_id})

    question, path = store.create("questions", build)
    print(f"{question.id} opened: {question.title}")
    print(f"wrote {_rel(path, store.root)}  (rank {question.priority.rank()})")
    return 0


def cmd_declare(store: Store, args: argparse.Namespace) -> int:
    """Declare an experiment. Nothing has run yet, and this subcommand runs nothing."""
    payload = load_json(args.source)
    # Validate against a placeholder id first: a malformed declaration should be refused before
    # a number is spent on it, and before the lock is taken.
    experiment = Experiment.model_validate({**payload, "id": "E-0000", "phase": "declared"})

    # The tier is resolved from the rule file, not read from the payload. A declaration that
    # labels a never-read corpus `iterate` is the hole ADR 0412 claimed was closed (ADR 0416).
    verdict = resolve(store.root, experiment.declared.corpus, declared=experiment.declared.tier)
    if verdict.refused:
        print(
            f"refused: {verdict.corpus} cannot be declared.\n  " + "\n  ".join(verdict.detail),
            file=sys.stderr,
        )
        return EXIT_REFUSED

    questions = store.questions()
    if experiment.question not in questions:
        print(f"refused: {experiment.question} does not exist. `ask` it first.", file=sys.stderr)
        return EXIT_REFUSED

    for existing in store.experiments().values():
        same_run = (
            existing.declared.command == experiment.declared.command
            and existing.declared.corpus == experiment.declared.corpus
        )
        if same_run and existing.phase == "judged":
            print(
                f"refused: {existing.id} already scored that command on "
                f"{existing.declared.corpus}. A second look is not available "
                f"(docs/rules/data-tiers.md).",
                file=sys.stderr,
            )
            return EXIT_REFUSED

    def build(record_id: str) -> Experiment:
        return Experiment.model_validate({**payload, "id": record_id, "phase": "declared"})

    experiment, path = store.create("experiments", build)
    print(f"{experiment.id} declared, serving {experiment.question}")
    print(f"wrote {_rel(path, store.root)}")
    print(f"tier resolved from the rule: {verdict.tier} ({verdict.expected_tier})")
    if verdict.disagrees:
        print(
            f"  {disagreement(verdict)}; the gate will refuse this run until a new declaration "
            "names the rule's tier",
            file=sys.stderr,
        )
    print("\nCommit it before the run. The gate reads HEAD, not the working tree:")
    print(
        f"  git add {_rel(path, store.root)} && git commit -m "
        f"'docs: declare {experiment.id} before running it'"
    )
    print(f"  uv run python scripts/genesis.py gate --command '{experiment.declared.command}'")
    return 0


def cmd_gate(store: Store, args: argparse.Namespace) -> int:
    """Refuse a command that no committed declaration covers.

    This is the gate the prose rules describe and no older check enforces. The decision itself is
    in ``phos.genesis.gatehost``, so that the Claude Code hook, the Cursor hook and this
    subcommand cannot drift apart: each is a different way of asking the same function.
    """
    decision = decide(args.command, store)
    if decision is None:
        print(f"not a harness command, so the gate has no opinion: {args.command}")
        return 0
    if decision.allowed:
        print(f"{decision.headline} — {decision.detail}")
        return 0
    label = "REFUSED" if not decision.softenable else "REFUSED (softenable while lanes backfill)"
    print(
        f"{label}: {decision.headline}\n  " + decision.detail.replace("\n", "\n  "), file=sys.stderr
    )
    return EXIT_REFUSED


def cmd_result(store: Store, args: argparse.Namespace) -> int:
    """Attach the measured numbers and record the verdict the bars imply."""
    experiments = store.experiments()
    experiment = experiments.get(args.experiment)
    if experiment is None:
        print(f"refused: {args.experiment} does not exist", file=sys.stderr)
        return EXIT_REFUSED
    if experiment.phase != "declared":
        print(
            f"refused: {experiment.id} is {experiment.phase}, not declared. "
            "A result is recorded once (docs/rules/data-tiers.md).",
            file=sys.stderr,
        )
        return EXIT_REFUSED

    committed, unmodified = committed_and_unmodified(store.path_for(experiment.id), store.root)
    if not committed or not unmodified:
        state = "not committed" if not committed else "edited since it was committed"
        print(
            f"refused: the declaration for {experiment.id} is {state}, so it does not predate "
            "this result.",
            file=sys.stderr,
        )
        return EXIT_REFUSED

    measurement = Measurement.model_validate(load_json(args.source))
    staged = experiment.model_copy(update={"measured": measurement, "phase": "measured"})
    verdict = staged.compute_verdict()
    judged = staged.model_copy(
        update={
            "phase": "judged",
            "verdict": verdict,
            "declaring_commit": git(
                store.root,
                "log",
                "-1",
                "--format=%H",
                "HEAD",
                "--",
                _rel(store.path_for(experiment.id), store.root).as_posix(),
            )
            or None,
        }
    )
    path = store.write(Experiment.model_validate(judged.model_dump(mode="json")))

    print(f"{judged.id}: {verdict.outcome.upper()}")
    for bar in judged.declared.bars:
        value = measurement.values[bar.id]
        mark = "met" if verdict.per_bar[bar.id] else "MISSED"
        print(f"  {bar.id} {bar.metric} {bar.comparator} {bar.threshold:g} — {value:g} {mark}")
    print(f"wrote {_rel(path, store.root)}")
    if verdict.outcome == "refused":
        print("\nA refusal is a result. It stays in the record and is not retried by moving a bar.")
    return 0


def cmd_finding(store: Store, args: argparse.Namespace) -> int:
    """Open a claim at level 0. Promotion is a separate, gated step."""
    payload = load_json(args.source)

    def build(record_id: str) -> Finding:
        return Finding.model_validate(
            {
                **payload,
                "id": record_id,
                "level": 0,
                "history": [f"opened at level 0 on {args.today}"],
            }
        )

    finding, path = store.create("findings", build)
    print(finding_summary(finding))
    print(f"wrote {_rel(path, store.root)}")
    return 0


def cmd_promote(store: Store, args: argparse.Namespace) -> int:
    """Move a finding up the ladder, only when the evidence each level demands is present."""
    findings, experiments = store.findings(), store.experiments()
    finding = findings.get(args.finding)
    if finding is None:
        print(f"refused: {args.finding} does not exist", file=sys.stderr)
        return EXIT_REFUSED
    if args.level <= finding.level:
        print(
            f"refused: {finding.id} already holds level {finding.level} "
            f"({LEVEL_NAMES[finding.level]}). This command only moves up.",
            file=sys.stderr,
        )
        return EXIT_REFUSED

    reasons = promotable(finding, args.level, experiments)
    if reasons:
        print(
            f"REFUSED: {finding.id} may not hold level {args.level} "
            f"({LEVEL_NAMES[args.level]}):\n  " + "\n  ".join(reasons),
            file=sys.stderr,
        )
        return EXIT_REFUSED

    moved = finding.model_copy(
        update={
            "level": args.level,
            "history": (
                *finding.history,
                f"level {finding.level} -> {args.level} on {args.today}: {args.reason}",
            ),
        }
    )
    path = store.write(moved)
    print(finding_summary(moved))
    print(f"wrote {_rel(path, store.root)}")
    return 0


def cmd_adr(store: Store, args: argparse.Namespace) -> int:
    """Render the prose record for an experiment from its data record."""
    experiment = store.experiments().get(args.experiment)
    if experiment is None:
        print(f"refused: {args.experiment} does not exist", file=sys.stderr)
        return EXIT_REFUSED
    render = verdict_adr if experiment.phase == "judged" else declaration_adr
    body = render(experiment, args.number, args.title)
    if args.out is None:
        print(body, end="")
        return 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(body, encoding="utf-8")
    print(f"wrote {_rel(args.out, store.root)}")
    print("Fill the hand-written sections. The renderer does not invent a conclusion.")
    return 0


def cmd_report(store: Store, args: argparse.Namespace) -> int:
    """Print the session report the charter's section XIII asks for, filled from the record."""
    snapshot = store.snapshot()
    for line in session_report(snapshot, args.since):
        print(line)
    if snapshot.unreadable:
        print(f"\n{len(snapshot.unreadable)} record(s) could not be read and are missing above:")
        for problem in snapshot.unreadable:
            print(f"  {problem.path}: {problem.problem}")
        return EXIT_REFUSED
    return 0


def cmd_audit(store: Store, _: argparse.Namespace) -> int:
    """Check the record's own cross-references, and the verdicts against the bars."""
    broken = store.audit()
    if not broken:
        print("record is internally consistent: every reference resolves, every verdict recomputes")
        return 0
    for problem in broken:
        print(f"{problem.path}: {problem.problem}")
    print(f"\n{len(broken)} problem(s)")
    return EXIT_REFUSED


# -- wiring ------------------------------------------------------------------------------------

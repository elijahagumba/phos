"""The FORGE command line: one entry point for the operations a human or an agent drives.

Subcommands::

    uv run python scripts/forge.py capability          # what can run on this machine
    uv run python scripts/forge.py start op --idea '…'  # create a PLANNED operation
    uv run python scripts/forge.py approve op           # gate (a), then APPROVED
    uv run python scripts/forge.py status op            # where the operation stands
    uv run python scripts/forge.py resume op            # where an interrupted operation left off
    uv run python scripts/forge.py claim op ROLE GLOB   # give a role a path
    uv run python scripts/forge.py agent op ROLE --task '…' --runtime codex
    uv run python scripts/forge.py transition op STATE  # move, checked by the table

Every subcommand that can refuse does refuse, and prints why. The exit codes are the ones a script
can branch on: 0 done, 2 refused, 3 blocked.

The work is in ``phos.forge`` so that it is typed, tested and importable; this file only makes it
runnable from a shell, which is the same shape ``scripts/genesis.py`` uses.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for entry in (ROOT, ROOT / "src"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from phos.forge import adapters, conductor, gates, preflight, redline  # noqa: E402
from phos.forge.operation import (  # noqa: E402
    ConcurrentUpdateError,
    OperationError,
    OperationStore,
    OwnershipConflictError,
    resume_point,
)
from phos.forge.orchestrator import Orchestrator  # noqa: E402
from phos.forge.states import STATES, TransitionError, allowed_from  # noqa: E402

EXIT_OK = 0
EXIT_REFUSED = 2
EXIT_BLOCKED = 3


def _repo_root() -> Path:
    """Return the checkout this command is working on.

    The scripts live in a checkout and are normally run from it, but ``/forge`` may be invoked from
    a worktree, and a hard-coded root would then write an operation file into the wrong tree. The
    root is therefore the git top level of the *current directory* when there is one, and the
    script's own checkout only when there is not. That is the difference the CLI test caught: two
    operations were written into the real repository instead of the throwaway one.

    Returns:
        The repository root.
    """
    import subprocess

    try:
        done = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return ROOT
    found = done.stdout.strip()
    if done.returncode == 0 and found:
        return Path(found)
    return ROOT


def _root() -> Path:
    """Return the repository root for this invocation."""
    return _repo_root()


def cmd_capability(_: argparse.Namespace) -> int:
    """Print how available each runtime is, and what that means for a role.

    Args:
        _: The parsed arguments.

    Returns:
        0 when at least one runtime is ready, 3 when none is.
    """
    any_ready = False
    for capability in adapters.detect_all():
        print(f"{capability.runtime:8} {capability.state:10} {capability.detail}")
        any_ready = any_ready or capability.state == "ready"
    sealed = gates.require_sealed_volume()
    print()
    print(f"sealed volume: {'mounted' if sealed.passed else 'not mounted'}")
    if not sealed.passed:
        print(f"  {sealed.detail}")
    print()
    if not any_ready:
        print("No runtime is ready. A role cannot run, and an operation that needs one is blocked.")
        return EXIT_BLOCKED
    return EXIT_OK


def cmd_start(args: argparse.Namespace) -> int:
    """Create an operation.

    Args:
        args: The parsed arguments.

    Returns:
        0 created, 2 refused.
    """
    made = Orchestrator(_root())
    try:
        operation = made.start(
            args.operation, idea=args.idea, declaration=args.declaration, corpus=args.corpus
        )
    except (ValueError, FileExistsError) as error:
        print(f"refused: {error}", file=sys.stderr)
        return EXIT_REFUSED
    print(f"{operation.operation} is {operation.state} (revision {operation.revision})")
    return EXIT_OK


def cmd_approve(args: argparse.Namespace) -> int:
    """Run gate (a) and move an operation to ``APPROVED``.

    Args:
        args: The parsed arguments.

    Returns:
        0 approved, 2 refused.
    """
    made = Orchestrator(_root())
    try:
        operation = made.approve(args.operation, declaration=args.declaration)
    except (OperationError, TransitionError) as error:
        print(f"refused: {error}", file=sys.stderr)
        return EXIT_REFUSED
    print(f"{operation.operation} is {operation.state}")
    print(f"  gate a: {operation.gates[-1].detail}")
    return EXIT_OK


def cmd_status(args: argparse.Namespace) -> int:
    """Print where an operation stands.

    Args:
        args: The parsed arguments.

    Returns:
        0 printed, 2 when there is no such operation.
    """
    try:
        operation = OperationStore(_root()).load(args.operation)
    except FileNotFoundError:
        print(f"refused: no operation called {args.operation}", file=sys.stderr)
        return EXIT_REFUSED

    print(f"{operation.operation}: {operation.state} (revision {operation.revision})")
    if operation.idea:
        print(f"  idea: {operation.idea}")
    if operation.declaration:
        print(f"  declaration: {operation.declaration}")
    if operation.blocked_reason:
        print(f"  blocked: {operation.blocked_reason}")
    if operation.ownership:
        print("  claims:")
        for pattern, role in sorted(operation.ownership.items()):
            print(f"    {pattern} -> {role}")
    if operation.agents:
        print("  agents:")
        for agent in operation.agents:
            print(f"    {agent.role:26} {agent.status:10} runtime={agent.runtime}")
    if operation.gates:
        print("  gates:")
        for gate in operation.gates:
            state = "passed" if gate.passed else "REFUSED"
            print(f"    {gate.gate:8} {state:8} {gate.detail[:70]}")
    print(f"  may move to: {', '.join(sorted(allowed_from(operation.state))) or 'nothing'}")
    return EXIT_OK


def cmd_resume(args: argparse.Namespace) -> int:
    """Print where an interrupted operation left off, and optionally move it back there.

    Args:
        args: The parsed arguments.

    Returns:
        0 when a resume point exists, 2 when the operation is terminal.
    """
    store = OperationStore(_root())
    operation = store.load(args.operation)
    point = resume_point(operation)
    if point is None:
        print(
            f"refused: {operation.operation} is {operation.state}. A finished or rejected "
            "operation does not restart."
        )
        return EXIT_REFUSED
    print(f"{operation.operation} is {operation.state}; it resumes into {point}")
    if operation.blocked_reason:
        print(f"  it was blocked because: {operation.blocked_reason}")
    if args.move:
        moved = store.transition(
            operation.operation, point, reason="resumed by hand after an interruption"
        )
        print(f"  moved to {moved.state} (revision {moved.revision})")
    return EXIT_OK


def cmd_claim(args: argparse.Namespace) -> int:
    """Give a role a set of path globs.

    Args:
        args: The parsed arguments.

    Returns:
        0 claimed, 2 refused.
    """
    store = OperationStore(_root())
    try:
        operation = store.claim(args.operation, args.role, tuple(args.patterns))
    except (OwnershipConflictError, OperationError) as error:
        print(f"refused: {error}", file=sys.stderr)
        return EXIT_REFUSED
    print(f"{operation.operation}: {args.role} claims {', '.join(args.patterns)}")
    return EXIT_OK


def cmd_agent(args: argparse.Namespace) -> int:
    """Run one role turn.

    Args:
        args: The parsed arguments.

    Returns:
        0 ran clean, 2 refused, 3 blocked.
    """
    made = Orchestrator(_root())
    try:
        outcome = made.run_role(
            args.operation,
            role=args.role,
            task=args.task,
            runtime=args.runtime,
            may_write=tuple(args.write),
            sealed=args.sealed,
            allow_unready=args.allow_unready,
        )
    except (OperationError, TransitionError) as error:
        print(f"refused: {error}", file=sys.stderr)
        return EXIT_REFUSED

    if not outcome.ran:
        print(f"refused: {outcome.refusal}", file=sys.stderr)
        return EXIT_BLOCKED if outcome.state == "BLOCKED" else EXIT_REFUSED
    if outcome.result is not None:
        print(f"{outcome.role} ran on {outcome.result.runtime} in {outcome.result.duration_s}s")
        print(f"  status: {outcome.result.status}")
        if outcome.result.model != "unknown":
            print(f"  model (as the runtime reported it): {outcome.result.model}")
        tokens = outcome.result.tokens
        print(f"  tokens: {'not reported' if tokens is None else tokens}")
    if outcome.red is not None:
        print(f"  red line: {outcome.red.summary()}")
    if outcome.refusal:
        print(f"refused after the turn: {outcome.refusal}", file=sys.stderr)
        return EXIT_REFUSED
    return EXIT_OK


def cmd_transition(args: argparse.Namespace) -> int:
    """Move an operation to a named state, checked by the table.

    Args:
        args: The parsed arguments.

    Returns:
        0 moved, 2 refused.
    """
    store = OperationStore(_root())
    try:
        moved = store.transition(args.operation, args.state, reason=args.reason)
    except (TransitionError, OperationError, ConcurrentUpdateError) as error:
        print(f"refused: {error}", file=sys.stderr)
        return EXIT_REFUSED
    print(f"{moved.operation} is {moved.state} (revision {moved.revision})")
    return EXIT_OK


def cmd_states(_: argparse.Namespace) -> int:
    """Print the state table.

    Args:
        _: The parsed arguments.

    Returns:
        0.
    """
    for state in STATES:
        permitted = sorted(allowed_from(state))
        print(f"{state:14} -> {', '.join(permitted) if permitted else 'nothing'}")
    return EXIT_OK


def cmd_tokens(args: argparse.Namespace) -> int:
    """Print the tokens the red-line guard refuses, and where they came from.

    Args:
        args: The parsed arguments.

    Returns:
        0.
    """
    tokens, sources = redline.red_tokens(_root())
    print(f"{len(tokens)} tokens, from: {', '.join(sources)}")
    for token in tokens:
        print(f"  {token}")
    return EXIT_OK


def cmd_preflight(args: argparse.Namespace) -> int:
    """Run the preflight checks and print each one.

    Args:
        args: The parsed arguments.

    Returns:
        0 when every check passed, 2 when one refused.
    """
    result = preflight.run(_root(), tuple(args.wanted))
    print(result.report())
    return EXIT_OK if result.passed else EXIT_REFUSED


def cmd_forge(args: argparse.Namespace) -> int:
    """Hand a goal to the conductor: preflight, size a team, make its worktrees.

    Args:
        args: The parsed arguments.

    Returns:
        0 conducted, 2 refused, 3 blocked by something outside the repository.
    """
    outcome = conductor.conduct(
        _root(),
        args.goal,
        operation=args.operation,
        declaration=args.declaration,
        corpus=args.corpus,
        create_worktrees=not args.plan,
    )
    if outcome.preflight is not None:
        print(outcome.preflight.report())
        print()

    if outcome.blocked:
        print(f"refused: {outcome.blocked}", file=sys.stderr)
        return EXIT_REFUSED

    assert outcome.team is not None
    print(f"operation: {outcome.operation}")
    print(f"shape: {outcome.team.shape}")
    print(f"team ({len(outcome.team.roles)} roles): {', '.join(outcome.team.roles)}")
    print(f"why: {outcome.team.reason}")
    print()
    if outcome.worktrees:
        print("worktrees:")
        for role, path in outcome.worktrees.items():
            print(f"  {role:26} {path}")
        print()
    for note in outcome.notes:
        print(f"note: {note}")
    print()
    print("where the results go:")
    for label, location in conductor.where_results_are(_root(), outcome.operation).items():
        print(f"  {label:28} {location}")
    print()
    print(f"next: approve it with `forge approve {outcome.operation} --declaration E-NNNN`")
    print(f"status: `forge status {outcome.operation}`")
    if outcome.notes and any("cannot run" in note for note in outcome.notes):
        return EXIT_BLOCKED
    return EXIT_OK


def cmd_operations(_: argparse.Namespace) -> int:
    """List every operation and its state, from the state files.

    Args:
        _: The parsed arguments.

    Returns:
        0 always: an empty list is a list.
    """
    base = _root() / "docs/forge/state"
    if not base.is_dir():
        print("no operations have been created")
        return EXIT_OK
    store = OperationStore(_root())
    found = sorted(path.stem for path in base.glob("*.json"))
    if not found:
        print("no operations have been created")
        return EXIT_OK
    print(f"{'operation':32} {'state':14} {'rev':>4}  {'roles':>5}  blocked")
    for name in found:
        try:
            operation = store.load(name)
        except Exception as error:  # an unreadable record is reported, not skipped
            print(f"{name:32} {'UNREADABLE':14}    -      -  {error}")
            continue
        blocked = operation.blocked_reason or ""
        print(
            f"{operation.operation:32} {operation.state:14} {operation.revision:>4}  "
            f"{len(operation.agents):>5}  {blocked[:60]}"
        )
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    """Return the argument parser.

    Returns:
        The parser.
    """
    parser = argparse.ArgumentParser(
        prog="forge", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    subparsers.add_parser("capability", help="what can run here").set_defaults(fn=cmd_capability)
    subparsers.add_parser("states", help="the state table").set_defaults(fn=cmd_states)
    subparsers.add_parser("tokens", help="the red-line tokens").set_defaults(fn=cmd_tokens)
    subparsers.add_parser("operations", help="every operation's state").set_defaults(
        fn=cmd_operations
    )

    checking = subparsers.add_parser("preflight", help="the checks before a team is sized")
    checking.add_argument("--wanted", nargs="*", default=[], help="worktree names to check for")
    checking.set_defaults(fn=cmd_preflight)

    forging = subparsers.add_parser("forge", help="hand a goal to the conductor")
    forging.add_argument("goal")
    forging.add_argument("--operation", default=None)
    forging.add_argument("--declaration", default=None)
    forging.add_argument("--corpus", default=None)
    forging.add_argument("--plan", action="store_true", help="size the team and create nothing")
    forging.set_defaults(fn=cmd_forge)

    starting = subparsers.add_parser("start", help="create an operation")
    starting.add_argument("operation")
    starting.add_argument("--idea", required=True)
    starting.add_argument("--declaration", default=None)
    starting.add_argument("--corpus", default=None)
    starting.set_defaults(fn=cmd_start)

    approving = subparsers.add_parser("approve", help="gate (a), then APPROVED")
    approving.add_argument("operation")
    approving.add_argument("--declaration", default=None)
    approving.set_defaults(fn=cmd_approve)

    status = subparsers.add_parser("status", help="where an operation stands")
    status.add_argument("operation")
    status.set_defaults(fn=cmd_status)

    resuming = subparsers.add_parser("resume", help="where an interrupted operation left off")
    resuming.add_argument("operation")
    resuming.add_argument("--move", action="store_true", help="move it back there")
    resuming.set_defaults(fn=cmd_resume)

    claiming = subparsers.add_parser("claim", help="give a role a path")
    claiming.add_argument("operation")
    claiming.add_argument("role")
    claiming.add_argument("patterns", nargs="+")
    claiming.set_defaults(fn=cmd_claim)

    agent = subparsers.add_parser("agent", help="run one role turn")
    agent.add_argument("operation")
    agent.add_argument("role")
    agent.add_argument("--task", required=True)
    agent.add_argument("--runtime", required=True, choices=["claude", "cursor", "codex"])
    agent.add_argument("--write", nargs="*", default=[])
    agent.add_argument("--sealed", action="store_true", help="invoke gate (b) for this step")
    agent.add_argument("--allow-unready", action="store_true")
    agent.set_defaults(fn=cmd_agent)

    moving = subparsers.add_parser("transition", help="move to a named state")
    moving.add_argument("operation")
    moving.add_argument("state")
    moving.add_argument("--reason", default="")
    moving.set_defaults(fn=cmd_transition)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Run one subcommand.

    Args:
        argv: The arguments, or None to read the process's own.

    Returns:
        The process exit code.
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    fn = args.fn
    result: int = fn(args)
    return result


if __name__ == "__main__":
    sys.exit(main())

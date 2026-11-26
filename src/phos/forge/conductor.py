"""The conductor: turns a goal in plain words into a sized team and its worktrees.

This is what ``/forge`` hands a goal to. It does four things and no more:

1. **Preflight**, and refuse if any check fails.
2. **Size the team** from the goal, using a fixed rule rather than a judgement call, because dynamic
   team sizing is deferred until the baseline data exists. The rule is in :func:`size_team` and it
   is deliberately simple enough to argue with.
3. **Create the operation** and **one worktree per role**, outside the main checkout.
4. **Print where the operation stands** and where its results will be written.

It does not run a role. Starting a role is :meth:`phos.forge.orchestrator.Orchestrator.run_role`,
and the conductor stops before that so a human sees the plan first. ``/forge`` then hands each role
its brief, which is the same shape ``/phos-dispatch`` uses.

**The runtime caveat, stated where it matters.** A team can be sized and its worktrees made on any
machine. Running the roles needs a runtime in the ``ready`` state, and on the machine this was built
on only ``codex`` is. The conductor checks and says so, and it does not invent a team of agents it
cannot start.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from phos.forge import adapters, preflight, worktree
from phos.forge.operation import AgentRecord, OperationStore
from phos.forge.protocol import ROLES

#: The roles a goal of each shape needs, in the order they run. The first entry of each tuple is
#: the role that must produce something before the next can use it.
BY_SHAPE: Final[dict[str, tuple[str, ...]]] = {
    # A question about the physics or a metric: research, then a harness, then judgement.
    "research": (
        "principal_research_scientist",
        "applied_scientist",
        "experimental_scientist",
        "verification_engineer",
    ),
    # A change to how something is built: design first, then build, then attack, then verify.
    "engineering": (
        "principal_architect",
        "principal_engineer",
        "applied_scientist",
        "adversarial_researcher",
        "verification_engineer",
    ),
    # A scoping or record question: the least team that can answer it.
    "institutional": (
        "institutional_analyst",
        "principal_research_scientist",
    ),
}

#: Words that make a goal one shape or another. First match wins, and the order is the order of
#: specificity: a goal that mentions an attack is engineering even if it also says "investigate".
_SHAPE_WORDS: Final[tuple[tuple[str, tuple[str, ...]], ...]] = (
    ("engineering", ("build", "implement", "refactor", "fix", "adapter", "engineer", "code")),
    ("research", ("measure", "test", "hypothesis", "experiment", "detect", "score", "improve")),
    ("institutional", ("decide", "scope", "record", "policy", "approve", "write up")),
)

#: Roles that are always on, whatever the shape. The institutional analyst holds the category lock
#: and the executive director is the one a decision goes to, so neither is ever absent.
ALWAYS: Final[tuple[str, ...]] = ("institutional_analyst",)


@dataclass
class Team:
    """The team a goal needs.

    Attributes:
        shape: ``research``, ``engineering`` or ``institutional``.
        roles: The roles, in the order they run, with no duplicates.
        reason: Why this many, in a sentence a human can argue with.
    """

    shape: str
    roles: tuple[str, ...]
    reason: str


@dataclass
class Conducted:
    """What the conductor produced.

    Attributes:
        operation: The operation id.
        team: The team it sized.
        worktrees: Role to worktree path.
        blocked: Why it stopped, when it did.
        preflight: The preflight result.
        notes: Anything a human needs to read.
    """

    operation: str
    team: Team | None = None
    worktrees: dict[str, Path] = field(default_factory=dict)
    blocked: str = ""
    preflight: preflight.Preflight | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return whether the team was sized and its worktrees made."""
        return self.team is not None and not self.blocked


def classify(goal: str) -> str:
    """Return the shape of a goal.

    Args:
        goal: The goal in plain words.

    Returns:
        ``research``, ``engineering`` or ``institutional``. A goal that matches nothing is
        ``research``, because the safe default is the shape that must produce evidence before
        anything is built.
    """
    lowered = goal.lower()
    for shape, words in _SHAPE_WORDS:
        if any(word in lowered for word in words):
            return shape
    return "research"


def size_team(goal: str) -> Team:
    """Return the team a goal needs.

    Dynamic sizing is deferred until the baseline data exists, so this is a fixed rule keyed on the
    shape of the goal. It is deliberately legible: three shapes, each a fixed roster, so a reader
    can see why a team has the size it has and argue with the rule rather than with a judgement.

    Args:
        goal: The goal in plain words.

    Returns:
        The team.
    """
    shape = classify(goal)
    roles = list(BY_SHAPE[shape])
    for role in ALWAYS:
        if role not in roles:
            roles.append(role)
    ordered = tuple(role for role in ROLES if role in set(roles))
    reason = (
        f"'{goal.strip()[:60]}' reads as a {shape} goal, so it takes the {shape} roster of "
        f"{len(ordered)} roles. Team size is fixed by shape until the baseline data says otherwise."
    )
    return Team(shape=shape, roles=ordered, reason=reason)


def conduct(
    root: Path,
    goal: str,
    *,
    operation: str | None = None,
    declaration: str | None = None,
    corpus: str | None = None,
    create_worktrees: bool = True,
) -> Conducted:
    """Preflight, size a team, and make its worktrees.

    Args:
        root: The repository root.
        goal: The goal in plain words.
        operation: The operation id. Defaults to one derived from the goal.
        declaration: The GENESIS experiment id, when one exists.
        corpus: The corpus the goal will work on, when known.
        create_worktrees: Whether to make the worktrees. False prints the plan only.

    Returns:
        What the conductor produced. A refusal has ``blocked`` set and no team.
    """
    if not goal.strip():
        return Conducted(
            operation=operation or "",
            blocked="the goal is empty. A command with nothing to do must say so and do nothing.",
        )

    team = size_team(goal)
    operation_id = operation or _slug(goal)

    checked = preflight.run(root, wanted=(operation_id,))
    if not checked.passed:
        return Conducted(
            operation=operation_id,
            team=team,
            blocked=checked.summary(),
            preflight=checked,
        )

    store = OperationStore(root)
    try:
        if (root / "docs/forge/state" / f"{operation_id}.json").exists():
            return Conducted(
                operation=operation_id,
                team=team,
                blocked=f"{operation_id} already exists. Use /forge-resume {operation_id}.",
                preflight=checked,
            )
        if corpus is not None:
            from phos.forge.genesis_api import tier

            verdict = tier(root, corpus, "iterate")
            if verdict.refused:
                return Conducted(
                    operation=operation_id,
                    team=team,
                    blocked=f"{corpus} cannot be used: " + " ".join(verdict.detail),
                    preflight=checked,
                )
        store.create(operation_id, idea=goal.strip(), declaration=declaration)
        store.transition(operation_id, "PLANNED", reason="goal accepted by the conductor")
    except (ValueError, FileExistsError) as error:
        return Conducted(
            operation=operation_id,
            team=team,
            blocked=str(error),
            preflight=checked,
        )

    conducted = Conducted(operation=operation_id, team=team, preflight=checked)

    ready = [cap.runtime for cap in adapters.detect_all() if cap.state == "ready"]
    if not ready:
        conducted.notes.append(
            "No runtime is ready, so the roles cannot run. The worktrees are made and the "
            "operation is PLANNED; authenticate a runtime before /forge resumes it."
        )

    if not create_worktrees:
        conducted.notes.append("Plan only: no worktree was created.")
        return conducted

    for role in team.roles:
        branch = f"forge/{operation_id}/{role}"
        try:
            made = worktree.create(root, operation=operation_id, role=role, branch=branch)
        except worktree.WorktreeError as error:
            conducted.notes.append(f"worktree for {role} refused: {error}")
            continue
        conducted.worktrees[role] = made.path
        store.record_agent(
            operation_id,
            AgentRecord(
                role=role,
                branch=made.branch,
                worktree=str(made.path),
                status="running",
            ),
        )

    if len(conducted.worktrees) != len(team.roles):
        conducted.blocked = (
            f"{len(team.roles) - len(conducted.worktrees)} of {len(team.roles)} worktrees could "
            "not be made, so the team is not ready to run"
        )
    return conducted


def _slug(goal: str) -> str:
    """Return an operation id derived from a goal.

    Args:
        goal: The goal in plain words.

    Returns:
        A slug of at most six words, which is short enough to read and unique enough in practice.
    """
    import re

    words = re.findall(r"[a-z0-9]+", goal.lower())
    stop = {
        "the",
        "a",
        "an",
        "and",
        "or",
        "to",
        "of",
        "in",
        "on",
        "for",
        "with",
        "that",
        "this",
        "is",
        "are",
        "be",
        "it",
        "we",
        "i",
    }
    kept = [word for word in words if word not in stop][:6]
    return "-".join(kept) or "operation"


def where_results_are(root: Path, operation: str) -> dict[str, str]:
    """Return where an operation's results will be written.

    Args:
        root: The repository root.
        operation: The operation id.

    Returns:
        A label to path, for printing at the end of a run. Every path is relative to the root and
        none is created here.
    """
    return {
        "operation state": f"docs/forge/state/{operation}.json",
        "declarations and verdicts": "docs/genesis/experiments/",
        "cycle records": "docs/forge/cycles/",
        "baseline report": "docs/forge/BASELINE.md",
        "anything missing or aborted": "docs/method/INBOX.md",
    }

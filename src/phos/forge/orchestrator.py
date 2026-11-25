"""The orchestrator: one operation, moved through its states, with every gate in the way.

This module is where the pieces meet, and it is deliberately the only place they do. A caller does
not create a worktree, run an agent, check the red line and update the state file in whatever order
it likes; it asks this module to do one thing, and the order is fixed here.

The order for a role turn is:

1. The operation must be in a state that allows work (``IMPLEMENTING`` or ``EXPERIMENTING``).
2. Gate (c): the branch is not ``main``.
3. Gate (a), for a build: the declaration is committed and in phase ``declared``.
4. Gate (b), for a sealed step: the volume is mounted, or the step stops.
5. The role's runtime must be ``ready``.
6. A worktree is created outside the checkout, and the role runs in it.
7. Every output is scanned for a red or sealed token. A hit aborts and writes the INBOX.
8. Files changed outside the role's scope are reported.
9. The result is recorded, with the runtime that produced it.

Every step that can refuse does refuse, and records the refusal. A refusal is a result.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from phos.forge import adapters, gates, redline, worktree
from phos.forge.genesis_api import DeclarationProblemError, require_declared, tier
from phos.forge.operation import (
    AgentRecord,
    GateRecord,
    Operation,
    OperationError,
    OperationStore,
)
from phos.forge.protocol import AgentResult, RoleRequest

#: The states in which a role may be given work.
WORKING_STATES: frozenset[str] = frozenset({"IMPLEMENTING", "EXPERIMENTING", "VERIFYING"})


@dataclass(frozen=True)
class RoleOutcome:
    """What happened when one role was asked to work.

    Attributes:
        role: The role.
        ran: Whether a turn actually ran.
        result: The runtime's result, or None when the role was refused before running.
        refusal: Why it was refused, when it was.
        state: The operation's state afterwards.
        red: The red-line check, when an output existed to check.
    """

    role: str
    ran: bool
    result: AgentResult | None
    refusal: str
    state: str
    red: redline.RedCheck | None = None

    @property
    def ok(self) -> bool:
        """Return whether the role ran and its output was clean."""
        return self.ran and self.refusal == "" and (self.red is None or self.red.clean)


class Orchestrator:
    """Run one operation's roles, in order, with every gate in the way.

    Attributes:
        root: The repository root.
        store: The operation state store.
    """

    def __init__(self, root: Path) -> None:
        """Open the orchestrator for one repository.

        Args:
            root: The repository root.
        """
        self.root = root
        self.store = OperationStore(root)

    def start(
        self,
        operation: str,
        *,
        idea: str,
        declaration: str | None = None,
        corpus: str | None = None,
    ) -> Operation:
        """Create an operation, refusing a corpus the tier rule will not have.

        The tier is checked before anything else happens, so a never-tier corpus is refused before a
        directory is listed or a branch is made.

        Args:
            operation: The operation id.
            idea: What the operation is for.
            declaration: The GENESIS experiment id, when one exists.
            corpus: The corpus the operation will work on, when known.

        Returns:
            The operation, in ``PROPOSED``.

        Raises:
            ValueError: If the corpus is refused by the tier rule.
        """
        if corpus is not None:
            verdict = tier(self.root, corpus, "iterate")
            if verdict.refused:
                raise ValueError(f"{corpus} cannot be used: " + " ".join(verdict.detail))
        created = self.store.create(operation, idea=idea, declaration=declaration)
        self.store.transition(operation, "PLANNED", reason="idea recorded")
        # Return the operation as it now stands, not the one from before the move: a caller that
        # prints what ``start`` returned would otherwise report PROPOSED for a PLANNED operation.
        return self.store.load(created.operation)

    def approve(self, operation: str, *, declaration: str | None = None) -> Operation:
        """Move an operation to ``APPROVED``, but only past gate (a).

        Gate (a) is the whole point of this state: the idea and its pass bar are committed before
        any build. An operation with no declaration cannot reach ``APPROVED``, which is what stops
        a build starting from a plan in somebody's head.

        Args:
            operation: The operation id.
            declaration: The experiment id to require. Defaults to the one the operation carries.

        Returns:
            The operation, in ``APPROVED``.

        Raises:
            OperationError: If gate (a) refused, or the move is not allowed.
        """
        current = self.store.load(operation)
        experiment_id = declaration or current.declaration
        if not experiment_id:
            refused = gates.GateOutcome(
                "a",
                False,
                "the operation names no declaration, so nothing is committed for a build to be "
                "judged against. A pass bar comes before a build, not after.",
            )
            self.store.record_gate(
                operation, GateRecord(gate="a", passed=False, detail=refused.detail)
            )
            raise OperationError(refused.detail)

        outcome = gates.require_committed_declaration(self.root, experiment_id)
        self.store.record_gate(
            operation, GateRecord(gate="a", passed=outcome.passed, detail=outcome.detail)
        )
        if not outcome.passed:
            raise OperationError(outcome.detail)

        try:
            require_declared(self.root, experiment_id)
        except DeclarationProblemError as error:
            self.store.record_gate(operation, GateRecord(gate="a", passed=False, detail=str(error)))
            raise OperationError(str(error)) from error

        # PLANNED -> DESIGNING -> APPROVED keeps the table honest: a build is designed before it is
        # approved, and skipping DESIGNING would make the history a fiction.
        state = self.store.load(operation).state
        if state == "PLANNED":
            self.store.transition(operation, "DESIGNING", reason="designing the build")
        self.store.transition(operation, "APPROVED", reason=f"gate a passed for {experiment_id}")
        return self.store.load(operation)

    def run_role(
        self,
        operation: str,
        *,
        role: str,
        task: str,
        runtime: str,
        may_write: tuple[str, ...] = (),
        may_not_read: tuple[str, ...] = (),
        instruction: str = "",
        branch: str | None = None,
        sealed: bool = False,
        allow_unready: bool = False,
    ) -> RoleOutcome:
        """Run one role in its own worktree, with every gate in the way.

        Args:
            operation: The operation id.
            role: One of the nine mandate roles.
            task: The task in plain language.
            runtime: Which runtime to run it on.
            may_write: The path globs the role owns.
            may_not_read: The path globs it must not open.
            instruction: The role's own skill text.
            branch: The branch to use. Defaults to ``forge/<operation>/<role>``.
            sealed: Whether this step touches the sealed batch, which invokes gate (b).
            allow_unready: Run on a runtime that is not ready, recording it as unavailable.

        Returns:
            The outcome. A refusal has ``ran`` False and the reason in ``refusal``.

        Raises:
            OperationError: If the operation is not in a working state.
        """
        current = self.store.load(operation)
        if current.state not in WORKING_STATES:
            raise OperationError(
                f"{operation} is {current.state}. A role runs in "
                f"{', '.join(sorted(WORKING_STATES))}, and nowhere else."
            )

        chosen_branch = branch or f"forge/{operation}/{role}"
        branch_gate = gates.require_not_main(chosen_branch)
        self.store.record_gate(
            operation, GateRecord(gate="c", passed=branch_gate.passed, detail=branch_gate.detail)
        )
        if not branch_gate.passed:
            return RoleOutcome(role, False, None, branch_gate.detail, current.state)

        if sealed:
            sealed_gate = gates.require_sealed_volume()
            self.store.record_gate(
                operation,
                GateRecord(gate="b", passed=sealed_gate.passed, detail=sealed_gate.detail),
            )
            if not sealed_gate.passed:
                return RoleOutcome(role, False, None, sealed_gate.detail, current.state)

        capability = adapters.detect(runtime)
        if capability.state != "ready" and not allow_unready:
            refusal = f"{role} needs {runtime}, which is {capability.state}: {capability.detail}"
            self.store.record_gate(
                operation,
                GateRecord(gate="runtime", passed=False, detail=refusal),
            )
            self.store.transition(operation, "BLOCKED", reason=refusal, blocked_reason=refusal)
            return RoleOutcome(role, False, None, refusal, "BLOCKED")

        made = worktree.create(
            self.root,
            operation=operation,
            role=role,
            branch=chosen_branch,
        )
        request = RoleRequest(
            operation=operation,
            role=role,  # type: ignore[arg-type]
            task=task,
            idea=current.idea,
            declaration=current.declaration,
            worktree=made.path,
            base_commit=made.base_commit,
            may_write=may_write,
            may_not_read=may_not_read,
            instruction=instruction,
        )

        adapter = adapters.adapter_for(runtime)
        try:
            result = adapter.run(request, allow_unready=allow_unready)
        except adapters.RuntimeUnavailableError as error:
            self.store.transition(
                operation, "BLOCKED", reason=str(error), blocked_reason=str(error)
            )
            return RoleOutcome(role, False, None, str(error), "BLOCKED")

        check = redline.check_output(self.root, result.combined_output)
        if not check.clean:
            redline.write_inbox(
                self.root,
                operation=operation,
                role=role,
                check=check,
                runtime=result.runtime,
            )
            reason = f"aborted: {check.summary()}"
            self.store.transition(operation, "BLOCKED", reason=reason, blocked_reason=reason)
            self.store.record_agent(
                operation,
                AgentRecord(
                    role=role,
                    branch=made.branch,
                    worktree=str(made.path),
                    runtime=result.runtime,
                    runtime_state=result.runtime_state,
                    status="refused",
                    stopped_at=_now(),
                ),
            )
            return RoleOutcome(role, True, result, reason, "BLOCKED", check)

        touched = worktree.changed_files(made)
        outside = [path for path in touched if not _within(path, may_write)]
        self.store.record_agent(
            operation,
            AgentRecord(
                role=role,
                branch=made.branch,
                worktree=str(made.path),
                runtime=result.runtime,
                runtime_state=result.runtime_state,
                status=result.status,
                stopped_at=_now(),
                files_touched=touched,
            ),
        )
        refusal = ""
        if outside:
            refusal = "wrote outside its declared scope: " + ", ".join(outside[:10])
            self.store.record_gate(
                operation, GateRecord(gate="scope", passed=False, detail=refusal)
            )
        return RoleOutcome(role, True, result, refusal, self.store.load(operation).state, check)


def _within(path: str, patterns: tuple[str, ...]) -> bool:
    """Return whether a path lies inside one of the declared globs.

    An empty pattern set means the role declared no scope, and a role with no declared scope is not
    allowed to have written anything: the answer is False, so the write is reported.

    Args:
        path: The path, relative to the repository root.
        patterns: The role's declared globs.

    Returns:
        True when the path matches at least one pattern.
    """
    if not patterns:
        return False
    from fnmatch import fnmatch

    return any(fnmatch(path, pattern) for pattern in patterns)


def _now() -> str:
    """Return the current UTC time as a sortable ISO 8601 string."""
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat(timespec="seconds")

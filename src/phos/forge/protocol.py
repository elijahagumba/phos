"""The protocol tag and the small value types FORGE passes between its own parts.

The written contract is ``docs/forge/protocol/forge-protocol-v1.md``. This module is its
machine-readable half: the tag, and the shape of a request and a result. Nothing here decides
policy; the checks live in :mod:`phos.forge.gates` and :mod:`phos.forge.operation`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict

#: The only protocol version this build writes and reads. A state file under another tag is
#: refused rather than interpreted, so an upgrade cannot happen by accident.
PROTOCOL_VERSION: Final = "forge-1"

#: The nine mandate roles of ``docs/forge/SPEC.md`` section 7.
Role = Literal[
    "executive_director",
    "principal_research_scientist",
    "principal_architect",
    "applied_scientist",
    "principal_engineer",
    "experimental_scientist",
    "adversarial_researcher",
    "verification_engineer",
    "institutional_analyst",
]

#: Every role, in the order the specification lists them.
ROLES: Final[tuple[str, ...]] = (
    "executive_director",
    "principal_research_scientist",
    "principal_architect",
    "applied_scientist",
    "principal_engineer",
    "experimental_scientist",
    "adversarial_researcher",
    "verification_engineer",
    "institutional_analyst",
)

#: Which runtime will actually run a turn. ``unknown`` is a recorded outcome, not a default: it is
#: what FORGE writes when no process started at all.
Runtime = Literal["claude", "cursor", "codex", "unknown"]

#: How available a runtime is. Three states, because two cannot tell "not installed" from
#: "installed and not logged in", and on this machine both cases occur.
RuntimeState = Literal["absent", "installed", "ready"]

#: The outcome of one turn.
RunStatus = Literal["ok", "failed", "refused", "unavailable"]


class RoleRequest(BaseModel):
    """What FORGE asks one role to do.

    Attributes:
        protocol: The protocol tag this request was built under.
        operation: The operation id.
        role: Which mandate role is being asked.
        task: The task in plain language.
        idea: The idea under test, as prose.
        declaration: The GENESIS experiment id, or None when the role runs before a declaration.
        worktree: Absolute path the role owns. Never the main checkout.
        base_commit: The commit the worktree was made from.
        may_write: Path globs the role owns, relative to the repository root.
        may_not_read: Path globs the role must not open.
        instruction: The role's own skill text, verbatim.
    """

    model_config = ConfigDict(frozen=True)

    protocol: str = PROTOCOL_VERSION
    operation: str
    role: Role
    task: str
    idea: str = ""
    declaration: str | None = None
    worktree: Path
    base_commit: str
    may_write: tuple[str, ...] = ()
    may_not_read: tuple[str, ...] = ()
    instruction: str = ""


class AgentResult(BaseModel):
    """What one runtime returned for one role.

    ``model`` and ``tokens`` are what the runtime reported. FORGE never fills either in with a
    choice of its own, and a test asserts that no module in this package names a model.

    Attributes:
        protocol: The protocol tag the result was produced under.
        runtime: The runtime that actually ran.
        runtime_state: How available that runtime was when it ran.
        status: The outcome of the turn.
        exit_status: The process exit code, or None when no process started.
        stdout: Verbatim standard output.
        stderr: Verbatim standard error.
        duration_s: Wall time in seconds.
        model: What the runtime reported it used, or ``unknown``.
        tokens: The reported token count, or None for "not reported". Never zero to mean unknown.
        changed_files: Paths the role changed, relative to the repository root.
        read_check: Whether the role's ``may_not_read`` globs could be checked, and the outcome.
    """

    model_config = ConfigDict(frozen=True)

    protocol: str = PROTOCOL_VERSION
    runtime: Runtime = "unknown"
    runtime_state: RuntimeState = "absent"
    status: RunStatus = "unavailable"
    exit_status: int | None = None
    stdout: str = ""
    stderr: str = ""
    duration_s: float = 0.0
    model: str = "unknown"
    tokens: int | None = None
    changed_files: tuple[str, ...] = ()
    read_check: Literal["pass", "fail", "unchecked"] = "unchecked"

    @property
    def combined_output(self) -> str:
        """Return stdout and stderr as one string, for the red-path check."""
        return f"{self.stdout}\n{self.stderr}"


class Capability(BaseModel):
    """Whether one runtime can run a turn on this machine.

    Attributes:
        runtime: Which runtime this describes.
        state: ``absent``, ``installed`` or ``ready``.
        detail: Why it is in that state, in a sentence a human can act on.
        binary: The path to the binary, when one was found.
    """

    model_config = ConfigDict(frozen=True)

    runtime: Runtime
    state: RuntimeState
    detail: str
    binary: Path | None = None


#: Reserved for a later protocol. Declared here so a reader can see the deferral is deliberate.
DEFERRED: Final[tuple[str, ...]] = ("dynamic_team_sizing", "recursive_self_improvement")


def field_names(model: type[BaseModel]) -> tuple[str, ...]:
    """Return the field names of a model, for tests that assert a field is absent."""
    return tuple(model.model_fields)

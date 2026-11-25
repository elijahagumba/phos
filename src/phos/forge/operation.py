"""The operation state file: atomic updates, ownership, conflict detection and resume.

One file per operation, ``docs/forge/state/<operation>.json``. It records what happened to a piece
of *work*: who ran, in which worktree, in what state, which gate passed. It records no hypothesis,
no bar, no measurement and no verdict, because those belong to GENESIS and duplicating them here is
the failure this package exists to avoid. ``tests/forge/test_operation.py`` asserts the field set
has no room for one.

Two properties make it usable by more than one agent at once:

* A monotonic ``revision``. A writer that loaded revision *n* and finds the file at *n+1* is
  refused rather than overwriting, so a lost update is impossible.
* An ``flock`` around the read-modify-write, and an ``os.replace`` to publish it, so a killed
  process leaves an intact file and a stray temporary one.

The lock is the same pattern ``phos.genesis.store.Store.locked`` uses, for the same reason: it is
advisory between cooperating processes, which is what this is, and the kernel drops it if the
holder dies.
"""

from __future__ import annotations

import contextlib
import fcntl
import fnmatch
import json
import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from phos.forge.protocol import PROTOCOL_VERSION
from phos.forge.states import STATES, check_transition, is_terminal

#: Where operation files live, relative to the repository root.
STATE_DIR: Final = Path("docs/forge/state")

#: The lock file, beside the state files so that one operation at a time is enough and two
#: unrelated operations never contend.
LOCK_NAME: Final = ".forge.lock"

#: Fields the state model is allowed to have. Kept as a constant so a test can assert that no
#: research record has crept in: a field named for a hypothesis, a bar, a measurement or a verdict
#: would be the duplication FORGE must not do.
_OPERATION_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "protocol",
        "operation",
        "state",
        "revision",
        "created_at",
        "updated_at",
        "idea",
        "declaration",
        "agents",
        "ownership",
        "gates",
        "history",
        "blocked_reason",
        "note",
    }
)


class ConcurrentUpdateError(RuntimeError):
    """A writer's revision is stale: the file changed since it was read."""


class ProtocolMismatchError(ValueError):
    """The file was written under a protocol version this build does not read."""


class OwnershipConflictError(ValueError):
    """Two roles claim the same path."""


class OperationError(ValueError):
    """The operation was asked to do something its own state forbids."""


def _now() -> str:
    """Return the current UTC time as a sortable ISO 8601 string."""
    return datetime.now(UTC).isoformat(timespec="seconds")


class AgentRecord(BaseModel):
    """One role's work on one operation.

    Attributes:
        role: The mandate role.
        branch: The git branch it worked on.
        worktree: The worktree it owned, outside the main checkout.
        runtime: Which runtime actually ran it. Recorded so a difference can be traced.
        runtime_state: How available that runtime was.
        status: ``ok``, ``failed``, ``refused``, ``unavailable`` or ``running``.
        started_at: When it started.
        stopped_at: When it stopped, or None while running.
        files_touched: Paths it changed, relative to the repository root.
    """

    model_config = ConfigDict(frozen=True)

    role: str
    branch: str
    worktree: str
    runtime: str = "unknown"
    runtime_state: str = "absent"
    status: str = "running"
    started_at: str = Field(default_factory=_now)
    stopped_at: str | None = None
    files_touched: tuple[str, ...] = ()


class GateRecord(BaseModel):
    """One gate attempt, passed or refused. A refusal is recorded, not omitted.

    Attributes:
        gate: Which of the three gates, ``a``, ``b`` or ``c``, or a named check.
        passed: Whether it passed.
        detail: The reason, in the gate's own words.
        at: When it was attempted.
    """

    model_config = ConfigDict(frozen=True)

    gate: str
    passed: bool
    detail: str = ""
    at: str = Field(default_factory=_now)


class HistoryEntry(BaseModel):
    """One move between states.

    Attributes:
        from_state: The state it left, or None when the operation was created.
        to_state: The state it entered.
        at: When.
        reason: Why, in a sentence.
    """

    model_config = ConfigDict(frozen=True)

    from_state: str | None
    to_state: str
    at: str = Field(default_factory=_now)
    reason: str = ""


class Operation(BaseModel):
    """The persisted state of one FORGE operation.

    Attributes:
        protocol: The protocol tag the file was written under.
        operation: The operation id.
        state: One of the eleven execution states.
        revision: Monotonic counter, incremented on every write.
        created_at: When the operation was created.
        updated_at: When it was last written.
        idea: What the operation is for, in plain language.
        declaration: The GENESIS experiment id, or None.
        agents: One entry per role that ran.
        ownership: Path glob to role. Enforced at claim time.
        gates: One entry per gate attempt.
        history: Append-only moves between states.
        blocked_reason: Why it is blocked, when it is.
        note: A short free-text note for a human.
    """

    model_config = ConfigDict(frozen=True)

    protocol: str = PROTOCOL_VERSION
    operation: str
    state: str = "PROPOSED"
    revision: int = 0
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)
    idea: str = ""
    declaration: str | None = None
    agents: tuple[AgentRecord, ...] = ()
    ownership: dict[str, str] = Field(default_factory=dict)
    gates: tuple[GateRecord, ...] = ()
    history: tuple[HistoryEntry, ...] = ()
    blocked_reason: str | None = None
    note: str = ""


def _render(operation: Operation) -> str:
    """Return the JSON text an operation is stored as."""
    return json.dumps(operation.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"


def _write_atomic(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` so that no reader ever sees a partial file.

    The temporary file is created in the destination's own directory, because ``os.replace`` is
    only atomic within one filesystem. A killed process leaves the temporary file behind and the
    real record untouched.

    Args:
        path: The destination.
        text: The whole file's contents.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class OperationStore:
    """Read and write operation files under one repository root.

    Attributes:
        root: The repository root.
        base: ``root / docs/forge/state``.
    """

    def __init__(self, root: Path) -> None:
        """Open the store under ``root``.

        Args:
            root: The repository root. The state directory need not exist yet.
        """
        self.root = root
        self.base = root / STATE_DIR
        self._depth = 0

    @contextlib.contextmanager
    def locked(self) -> Iterator[None]:
        """Hold an exclusive lock for the duration of the block.

        The lock is re-entrant within one :class:`OperationStore` instance. ``flock`` is held per
        open file handle, not per process, so a second ``open`` and ``flock`` on the same file from
        the same process blocks for ever rather than deadlocking detectably. Methods here call each
        other constantly (``transition`` reads, then saves), so the depth is counted and the outer
        call owns the handle. That was found by a test that hung rather than failed.

        Yields:
            Nothing. The lock is held inside the block and released on the way out.
        """
        if self._depth > 0:
            self._depth += 1
            try:
                yield
            finally:
                self._depth -= 1
            return

        self.base.mkdir(parents=True, exist_ok=True)
        handle = (self.base / LOCK_NAME).open("a+")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            self._depth = 1
            yield
        finally:
            self._depth = 0
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            finally:
                handle.close()

    def path_for(self, operation: str) -> Path:
        """Return the file one operation id belongs in, whether or not it exists.

        Args:
            operation: The operation id. Letters, digits, dot, dash and underscore only, so an id
                cannot escape the state directory.

        Returns:
            The path.

        Raises:
            ValueError: If the id contains a path separator or a parent reference.
        """
        if not operation or operation in {".", ".."}:
            raise ValueError(f"{operation!r} is not a usable operation id")
        if "/" in operation or "\\" in operation or operation.startswith("."):
            raise ValueError(f"{operation!r} would escape the state directory")
        return self.base / f"{operation}.json"

    def load(self, operation: str) -> Operation:
        """Return the operation on disk.

        Args:
            operation: The operation id.

        Returns:
            The operation.

        Raises:
            FileNotFoundError: If there is no such operation.
            ProtocolMismatchError: If the file was written under another protocol version.
            ValidationError: If the file will not parse as an operation.
        """
        path = self.path_for(operation)
        text = path.read_text(encoding="utf-8")
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as error:
            raise ValidationError.from_exception_data(
                "Operation", [{"type": "json_invalid", "loc": (), "input": str(error)}]
            ) from error
        if not isinstance(parsed, dict):
            raise ValidationError.from_exception_data(
                "Operation", [{"type": "dict_type", "loc": (), "input": type(parsed).__name__}]
            )
        tag = parsed.get("protocol")
        if tag != PROTOCOL_VERSION:
            raise ProtocolMismatchError(
                f"{path.name} is written under protocol {tag!r}; this build reads "
                f"{PROTOCOL_VERSION!r} only"
            )
        return Operation.model_validate(parsed)

    def create(self, operation: str, *, idea: str, declaration: str | None = None) -> Operation:
        """Create a new operation in ``PROPOSED``.

        Args:
            operation: The operation id.
            idea: What the operation is for.
            declaration: The GENESIS experiment id, when one already exists.

        Returns:
            The operation as written.

        Raises:
            FileExistsError: If an operation of that id exists. Creating over one would discard
                its history, which is the record of what happened.
        """
        with self.locked():
            path = self.path_for(operation)
            if path.exists():
                raise FileExistsError(f"{operation} already exists at {path}")
            created = Operation(
                operation=operation,
                idea=idea,
                declaration=declaration,
                history=(HistoryEntry(from_state=None, to_state="PROPOSED", reason="created"),),
            )
            _write_atomic(path, _render(created))
            return created

    def save(self, operation: Operation, *, expected_revision: int) -> Operation:
        """Write ``operation`` at the next revision, refusing a stale writer.

        Args:
            operation: The operation to write. Its ``revision`` is replaced by ``expected + 1``.
            expected_revision: The revision the caller loaded.

        Returns:
            The operation as written.

        Raises:
            ConcurrentUpdateError: If the file on disk is not at ``expected_revision``.
        """
        with self.locked():
            path = self.path_for(operation.operation)
            on_disk = self.load(operation.operation) if path.exists() else None
            current = on_disk.revision if on_disk is not None else 0
            if current != expected_revision:
                raise ConcurrentUpdateError(
                    f"{operation.operation} is at revision {current}, not {expected_revision}: "
                    "another writer got there first, so this one's view is stale"
                )
            updated = operation.model_copy(
                update={
                    "revision": expected_revision + 1,
                    "updated_at": _now(),
                    "protocol": PROTOCOL_VERSION,
                }
            )
            _write_atomic(path, _render(updated))
            return updated

    def transition(
        self,
        operation: str,
        target: str,
        *,
        expected_revision: int | None = None,
        reason: str = "",
        blocked_reason: str | None = None,
    ) -> Operation:
        """Move an operation to ``target``, checking the transition table first.

        Args:
            operation: The operation id.
            target: The state to move to.
            expected_revision: The revision the caller loaded, or None to accept whatever is on
                disk. Passing it is what detects a concurrent writer.
            reason: Why, recorded in the history.
            blocked_reason: Set when moving to ``BLOCKED``; cleared when moving out of it.

        Returns:
            The operation as written.

        Raises:
            OperationError: If the target is unknown or the move is not allowed.
            ConcurrentUpdateError: If ``expected_revision`` is stale.
        """
        with self.locked():
            current = self.load(operation)
            if expected_revision is not None and current.revision != expected_revision:
                raise ConcurrentUpdateError(
                    f"{operation} is at revision {current.revision}, not {expected_revision}"
                )
            check_transition(current.state, target)
            entry = HistoryEntry(from_state=current.state, to_state=target, reason=reason)
            cleared = None if target != "BLOCKED" else (blocked_reason or reason or "blocked")
            moved = current.model_copy(
                update={
                    "state": target,
                    "history": (*current.history, entry),
                    "blocked_reason": cleared,
                }
            )
            return self.save(moved, expected_revision=current.revision)

    def claim(self, operation: str, role: str, patterns: tuple[str, ...]) -> Operation:
        """Give ``role`` a set of path globs, refusing an overlap with another role.

        The check is conservative and symmetric: a new pattern is refused if an existing pattern
        can match any path it can match. That is stricter than necessary for odd glob pairs and
        it is the right direction to be wrong in, because the cost of a false conflict is a
        re-plan and the cost of a missed one is two agents editing the same file.

        Args:
            operation: The operation id.
            role: The role claiming the paths.
            patterns: The globs it claims.

        Returns:
            The operation as written.

        Raises:
            OwnershipConflictError: If a pattern overlaps another role's, or a role already has a
                different claim.
            OperationError: If the operation is terminal.
        """
        with self.locked():
            current = self.load(operation)
            if is_terminal(current.state):
                raise OperationError(f"{operation} is {current.state}; nothing more is claimed")
            ownership = dict(current.ownership)
            for pattern in patterns:
                for other_pattern, other_role in ownership.items():
                    if other_role == role:
                        continue
                    if _patterns_overlap(pattern, other_pattern):
                        raise OwnershipConflictError(
                            f"{role} claims {pattern!r}, which overlaps {other_role}'s "
                            f"{other_pattern!r}"
                        )
                if _is_forbidden_scope(pattern):
                    raise OwnershipConflictError(
                        f"{role} may not claim {pattern!r}: it is outside a builder's reach"
                    )
                ownership[pattern] = role
            claimed = current.model_copy(update={"ownership": ownership})
            return self.save(claimed, expected_revision=current.revision)

    def record_agent(self, operation: str, agent: AgentRecord) -> Operation:
        """Add or replace one role's record.

        Replacing by role is deliberate: a role that runs twice in one operation (a retry after an
        interruption) leaves one entry, not two, so the file says what happened rather than how
        many attempts it took.

        Args:
            operation: The operation id.
            agent: The record to add or replace.

        Returns:
            The operation as written.
        """
        with self.locked():
            current = self.load(operation)
            kept = tuple(record for record in current.agents if record.role != agent.role)
            updated = current.model_copy(update={"agents": (*kept, agent)})
            return self.save(updated, expected_revision=current.revision)

    def record_gate(self, operation: str, gate: GateRecord) -> Operation:
        """Append one gate attempt.

        Args:
            operation: The operation id.
            gate: The attempt, passed or refused.

        Returns:
            The operation as written.
        """
        with self.locked():
            current = self.load(operation)
            updated = current.model_copy(update={"gates": (*current.gates, gate)})
            return self.save(updated, expected_revision=current.revision)


def _is_forbidden_scope(pattern: str) -> bool:
    """Return whether a claimed pattern reaches something no builder may claim.

    Two things are out of reach. Anything outside the repository, because a claim on a path FORGE
    cannot reason about is not a claim. And the operation state itself, because a role that could
    claim it could rewrite the record of what it did.

    Args:
        pattern: The glob a role wants.

    Returns:
        True when the pattern must be refused.
    """
    if pattern.startswith("/") or pattern.startswith("~") or ".." in Path(pattern).parts:
        return True
    return pattern.startswith("docs/forge/state")


def _patterns_overlap(left: str, right: str) -> bool:
    """Return whether two globs can match the same path.

    ``fnmatch`` has no intersection operator, so this compares the literal prefixes the two
    patterns share: if one pattern's fixed prefix is itself matched by the other pattern, they may
    overlap. When neither prefix is fixed, overlap is assumed, which is the conservative answer.

    Args:
        left: One glob.
        right: The other.

    Returns:
        True when they may match a common path.
    """
    left_prefix = _literal_prefix(left)
    right_prefix = _literal_prefix(right)
    if left_prefix is None or right_prefix is None:
        return True
    if fnmatch.fnmatch(left_prefix, right) or fnmatch.fnmatch(right_prefix, left):
        return True
    return (
        left_prefix == right_prefix
        or left_prefix.startswith(f"{right_prefix}/")
        or (right_prefix.startswith(f"{left_prefix}/"))
    )


def _literal_prefix(pattern: str) -> str | None:
    """Return the part of a glob before its first wildcard.

    Args:
        pattern: The glob.

    Returns:
        The literal prefix with any trailing separator removed, or None when the pattern starts
        with a wildcard and so could match anything.
    """
    for index, character in enumerate(pattern):
        if character in "*?[":
            prefix = pattern[:index]
            return prefix.rstrip("/") or None
    return pattern


def known_state(value: str) -> bool:
    """Return whether ``value`` is one of the eleven states."""
    return value in STATES


def resume_point(operation: Operation) -> str | None:
    """Return the state an interrupted operation should resume into, or None.

    An operation that was ``BLOCKED`` resumes into the last non-blocked state in its history,
    because that is where it stopped. An operation in a working state resumes into that state. A
    terminal operation does not resume, and neither does one with no history at all.

    Args:
        operation: The operation.

    Returns:
        The state to resume into, or None when it may not be resumed.
    """
    if is_terminal(operation.state):
        return None
    if operation.state != "BLOCKED":
        return operation.state
    for entry in reversed(operation.history):
        if entry.to_state != "BLOCKED" and not is_terminal(entry.to_state):
            return entry.to_state
    return "PROPOSED"


def operation_field_names() -> tuple[str, ...]:
    """Return the operation's field names, for the test that asserts no record has crept in.

    Returns:
        The field names, sorted.
    """
    return tuple(sorted(Operation.model_fields))


def unexpected_fields() -> tuple[str, ...]:
    """Return any field on the operation that is not in the allowed set.

    Returns:
        The offending names, empty when the model is exactly what the specification allows.
    """
    return tuple(sorted(set(Operation.model_fields) - _OPERATION_FIELDS))


def field_types() -> dict[str, Any]:
    """Return the annotation of each operation field, for the same test.

    Returns:
        Field name to annotation.
    """
    return {name: field.annotation for name, field in Operation.model_fields.items()}

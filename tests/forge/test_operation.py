"""Tests for the operation state file: atomicity, concurrency, ownership and resume.

The properties under test are the ones that make a file a record:

* a write never leaves a half-file behind, even when the writer is killed;
* a second writer holding a stale view is refused rather than silently overwriting;
* two roles cannot claim the same path;
* an interrupted operation can be picked up and says where it was.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from phos.forge.operation import (
    LOCK_NAME,
    STATE_DIR,
    AgentRecord,
    ConcurrentUpdateError,
    GateRecord,
    Operation,
    OperationStore,
    OwnershipConflictError,
    ProtocolMismatchError,
    operation_field_names,
    resume_point,
    unexpected_fields,
)
from phos.forge.protocol import PROTOCOL_VERSION


def test_create_writes_proposed_and_one_history_entry(tmp_path: Path) -> None:
    store = OperationStore(tmp_path)
    made = store.create("op-1", idea="test the thing")
    assert made.state == "PROPOSED"
    assert made.revision == 0
    assert len(made.history) == 1
    assert made.history[0].from_state is None
    on_disk = store.load("op-1")
    assert on_disk.revision == 0


def test_create_refuses_a_second_operation_of_the_same_id(tmp_path: Path) -> None:
    store = OperationStore(tmp_path)
    store.create("op-1", idea="first")
    with pytest.raises(FileExistsError):
        store.create("op-1", idea="second")


def test_transition_appends_history_and_bumps_revision(tmp_path: Path) -> None:
    store = OperationStore(tmp_path)
    store.create("op-1", idea="x")
    moved = store.transition("op-1", "PLANNED", reason="planned")
    assert moved.state == "PLANNED"
    assert moved.revision == 1
    assert moved.history[-1].to_state == "PLANNED"
    assert moved.history[-1].reason == "planned"


def test_illegal_transition_leaves_the_file_alone(tmp_path: Path) -> None:
    from phos.forge.states import TransitionError

    store = OperationStore(tmp_path)
    store.create("op-1", idea="x")
    before = store.load("op-1")
    with pytest.raises(TransitionError):
        store.transition("op-1", "COMPLETED")
    after = store.load("op-1")
    assert after.state == before.state
    assert after.revision == before.revision


def test_stale_writer_is_refused(tmp_path: Path) -> None:
    store = OperationStore(tmp_path)
    store.create("op-1", idea="x")

    first = store.load("op-1")
    second = store.load("op-1")

    store.save(first, expected_revision=first.revision)

    with pytest.raises(ConcurrentUpdateError, match="stale"):
        store.save(second, expected_revision=second.revision)


def test_transition_with_a_stale_revision_is_refused(tmp_path: Path) -> None:
    store = OperationStore(tmp_path)
    store.create("op-1", idea="x")
    store.transition("op-1", "PLANNED")
    with pytest.raises(ConcurrentUpdateError):
        store.transition("op-1", "DESIGNING", expected_revision=0)


def test_blocked_records_a_reason_and_clears_it_on_resume(tmp_path: Path) -> None:
    store = OperationStore(tmp_path)
    store.create("op-1", idea="x")
    store.transition("op-1", "PLANNED")
    blocked = store.transition(
        "op-1", "BLOCKED", reason="runtime missing", blocked_reason="codex not ready"
    )
    assert blocked.state == "BLOCKED"
    assert blocked.blocked_reason == "codex not ready"
    resumed = store.transition("op-1", "PLANNED", reason="resumed")
    assert resumed.blocked_reason is None


def test_an_interrupted_write_leaves_no_partial_file(tmp_path: Path) -> None:
    """A killed writer leaves the record intact and at most a temporary file behind.

    The kill is simulated by making ``os.replace`` raise, which is the step that would be
    interrupted. The record on disk must still be the one from before.
    """
    store = OperationStore(tmp_path)
    store.create("op-1", idea="x")
    before = store.load("op-1")

    loaded = store.load("op-1")
    moved = loaded.model_copy(update={"state": "PLANNED"})

    original_replace = os.replace

    def explode(src: str | Path, dst: str | Path) -> None:
        raise OSError("simulated kill between write and replace")

    os.replace = explode  # type: ignore[assignment]
    try:
        with pytest.raises(OSError):
            store.save(moved, expected_revision=loaded.revision)
    finally:
        os.replace = original_replace

    after = store.load("op-1")
    assert after.state == before.state
    assert after.revision == before.revision
    leftovers = [p.name for p in (tmp_path / STATE_DIR).iterdir() if p.name.endswith(".tmp")]
    assert leftovers == [], "the temporary file must be cleaned up even when the write failed"


def test_a_temporary_file_is_not_left_by_a_successful_write(tmp_path: Path) -> None:
    store = OperationStore(tmp_path)
    store.create("op-1", idea="x")
    store.transition("op-1", "PLANNED")
    assert not [p for p in (tmp_path / STATE_DIR).iterdir() if p.name.endswith(".tmp")]


def test_protocol_mismatch_is_refused(tmp_path: Path) -> None:
    store = OperationStore(tmp_path)
    store.create("op-1", idea="x")
    path = tmp_path / STATE_DIR / "op-1.json"
    data = json.loads(path.read_text())
    data["protocol"] = "forge-0"
    path.write_text(json.dumps(data))

    with pytest.raises(ProtocolMismatchError, match="forge-0"):
        store.load("op-1")


@pytest.mark.parametrize("name", ["../escape", "a/b", ".hidden", "", "."])
def test_an_operation_id_cannot_escape_the_state_directory(tmp_path: Path, name: str) -> None:
    store = OperationStore(tmp_path)
    with pytest.raises(ValueError):
        store.path_for(name)


def test_ownership_overlap_is_refused(tmp_path: Path) -> None:
    store = OperationStore(tmp_path)
    store.create("op-1", idea="x")
    store.claim("op-1", "builder_a", ("src/phos/atlas/**",))
    with pytest.raises(OwnershipConflictError, match="overlaps"):
        store.claim("op-1", "builder_b", ("src/phos/atlas/engine.py",))


def test_ownership_non_overlap_is_allowed(tmp_path: Path) -> None:
    store = OperationStore(tmp_path)
    store.create("op-1", idea="x")
    store.claim("op-1", "builder_a", ("src/phos/atlas/engine.py",))
    store.claim("op-1", "builder_b", ("src/phos/atlas/budget.py",))
    claims = store.load("op-1").ownership
    assert claims["src/phos/atlas/engine.py"] == "builder_a"
    assert claims["src/phos/atlas/budget.py"] == "builder_b"


def test_a_role_can_extend_its_own_claim(tmp_path: Path) -> None:
    store = OperationStore(tmp_path)
    store.create("op-1", idea="x")
    store.claim("op-1", "builder_a", ("src/phos/atlas/engine.py",))
    store.claim("op-1", "builder_a", ("src/phos/atlas/budget.py",))
    assert len(store.load("op-1").ownership) == 2


def test_the_state_file_itself_cannot_be_claimed(tmp_path: Path) -> None:
    store = OperationStore(tmp_path)
    store.create("op-1", idea="x")
    with pytest.raises(OwnershipConflictError, match="outside a builder's reach"):
        store.claim("op-1", "builder_a", ("docs/forge/state/**",))


@pytest.mark.parametrize(
    "pattern", ["/etc/passwd", "~/somewhere/**", "../outside/**", "src/../../escape"]
)
def test_a_claim_outside_the_repository_is_refused(tmp_path: Path, pattern: str) -> None:
    store = OperationStore(tmp_path)
    store.create("op-1", idea="x")
    with pytest.raises(OwnershipConflictError):
        store.claim("op-1", "builder_a", (pattern,))


def test_a_terminal_operation_takes_no_more_claims(tmp_path: Path) -> None:
    from phos.forge.operation import OperationError

    store = OperationStore(tmp_path)
    store.create("op-1", idea="x")
    store.transition("op-1", "REJECTED", reason="not worth it")
    with pytest.raises(OperationError):
        store.claim("op-1", "builder_a", ("src/phos/atlas/engine.py",))


def test_record_agent_replaces_a_role_rather_than_duplicating_it(tmp_path: Path) -> None:
    store = OperationStore(tmp_path)
    store.create("op-1", idea="x")
    first = AgentRecord(role="builder", branch="b1", worktree="/tmp/wt1", status="running")
    store.record_agent("op-1", first)
    stopped = AgentRecord(role="builder", branch="b1", worktree="/tmp/wt1", status="ok")
    store.record_agent("op-1", stopped)
    agents = store.load("op-1").agents
    assert len(agents) == 1
    assert agents[0].status == "ok"


def test_gates_accumulate_including_refusals(tmp_path: Path) -> None:
    store = OperationStore(tmp_path)
    store.create("op-1", idea="x")
    store.record_gate("op-1", GateRecord(gate="a", passed=False, detail="uncommitted"))
    store.record_gate("op-1", GateRecord(gate="a", passed=True, detail="committed"))
    gates = store.load("op-1").gates
    assert [gate.passed for gate in gates] == [False, True]


def test_resume_point_returns_the_state_a_blocked_operation_left(tmp_path: Path) -> None:
    store = OperationStore(tmp_path)
    store.create("op-1", idea="x")
    store.transition("op-1", "PLANNED")
    store.transition("op-1", "DESIGNING")
    store.transition("op-1", "BLOCKED", reason="waiting")
    assert resume_point(store.load("op-1")) == "DESIGNING"


def test_resume_point_of_a_working_operation_is_its_own_state(tmp_path: Path) -> None:
    store = OperationStore(tmp_path)
    store.create("op-1", idea="x")
    store.transition("op-1", "PLANNED")
    assert resume_point(store.load("op-1")) == "PLANNED"


@pytest.mark.parametrize("terminal", ["COMPLETED", "REJECTED"])
def test_resume_point_of_a_terminal_operation_is_none(tmp_path: Path, terminal: str) -> None:
    store = OperationStore(tmp_path)
    store.create("op-1", idea="x")
    if terminal == "COMPLETED":
        # A completion has to be reached through VERIFYING. Jumping straight to it would be an
        # illegal move, which is the point of the table.
        store.transition("op-1", "PLANNED")
        store.transition("op-1", "DESIGNING")
        store.transition("op-1", "APPROVED")
        store.transition("op-1", "IMPLEMENTING")
        store.transition("op-1", "VERIFYING")
        store.transition("op-1", "COMPLETED", reason="verified")
    else:
        store.transition("op-1", terminal, reason="done")
    assert resume_point(store.load("op-1")) is None


def test_an_operation_blocked_immediately_resumes_to_proposed(tmp_path: Path) -> None:
    store = OperationStore(tmp_path)
    store.create("op-1", idea="x")
    store.transition("op-1", "BLOCKED", reason="immediately")
    assert resume_point(store.load("op-1")) == "PROPOSED"


def test_the_operation_holds_no_research_record() -> None:
    """The separation FORGE exists for, asserted rather than described.

    A field named for a hypothesis, a bar, a measurement or a verdict would be FORGE keeping a
    second copy of the record. None may exist.
    """
    assert unexpected_fields() == ()
    forbidden = {"hypothesis", "bars", "measurement", "verdict", "result", "finding", "priority"}
    assert not forbidden & set(operation_field_names())


def test_the_model_is_frozen() -> None:
    made = Operation(operation="op-1")
    with pytest.raises(ValidationError):
        made.state = "PLANNED"  # type: ignore[misc]


def test_a_lock_file_exists_and_is_not_the_record(tmp_path: Path) -> None:
    store = OperationStore(tmp_path)
    store.create("op-1", idea="x")
    assert (tmp_path / STATE_DIR / LOCK_NAME).exists()
    assert (tmp_path / STATE_DIR / "op-1.json").exists()


def test_written_files_are_sorted_and_trailing_newline(tmp_path: Path) -> None:
    """A record written twice from the same content is byte-identical, so git sees no churn."""
    store = OperationStore(tmp_path)
    store.create("op-1", idea="x")
    path = tmp_path / STATE_DIR / "op-1.json"
    first = path.read_text()
    assert first.endswith("\n")
    assert first == json.dumps(json.loads(first), indent=2, sort_keys=True) + "\n"


def test_protocol_version_is_the_one_in_the_spec() -> None:
    assert PROTOCOL_VERSION == "forge-1"

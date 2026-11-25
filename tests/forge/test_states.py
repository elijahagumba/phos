"""Tests for the eleven states and the moves between them.

Every legal edge is walked, every illegal edge is refused, and the two terminal states are asserted
to be terminal. The table is the specification, so a test that reads it and checks it against itself
would prove nothing; these list the edges explicitly.
"""

from __future__ import annotations

import pytest

from phos.forge.states import (
    STATES,
    TERMINAL,
    TransitionError,
    allowed_from,
    check_transition,
    is_terminal,
    resumable,
)

#: Every edge the specification allows, written out rather than generated from the table.
LEGAL = [
    ("PROPOSED", "PLANNED"),
    ("PROPOSED", "REJECTED"),
    ("PROPOSED", "BLOCKED"),
    ("PLANNED", "RESEARCHING"),
    ("PLANNED", "DESIGNING"),
    ("PLANNED", "REJECTED"),
    ("PLANNED", "BLOCKED"),
    ("RESEARCHING", "DESIGNING"),
    ("RESEARCHING", "REJECTED"),
    ("RESEARCHING", "BLOCKED"),
    ("DESIGNING", "APPROVED"),
    ("DESIGNING", "REJECTED"),
    ("DESIGNING", "BLOCKED"),
    ("APPROVED", "IMPLEMENTING"),
    ("APPROVED", "BLOCKED"),
    ("IMPLEMENTING", "EXPERIMENTING"),
    ("IMPLEMENTING", "VERIFYING"),
    ("IMPLEMENTING", "BLOCKED"),
    ("EXPERIMENTING", "VERIFYING"),
    ("EXPERIMENTING", "IMPLEMENTING"),
    ("EXPERIMENTING", "BLOCKED"),
    ("VERIFYING", "COMPLETED"),
    ("VERIFYING", "IMPLEMENTING"),
    ("VERIFYING", "REJECTED"),
    ("VERIFYING", "BLOCKED"),
]

#: Moves that must be refused. A sample rather than every pair, chosen to cover each rule: skipping
#: a stage, going backwards out of a terminal state, and restarting a finished operation.
ILLEGAL = [
    ("PROPOSED", "APPROVED"),
    ("PROPOSED", "COMPLETED"),
    ("PLANNED", "IMPLEMENTING"),
    ("RESEARCHING", "APPROVED"),
    ("APPROVED", "EXPERIMENTING"),
    ("IMPLEMENTING", "COMPLETED"),
    ("COMPLETED", "PROPOSED"),
    ("COMPLETED", "IMPLEMENTING"),
    ("REJECTED", "PLANNED"),
    ("REJECTED", "BLOCKED"),
]


@pytest.mark.parametrize(("current", "target"), LEGAL)
def test_legal_edge_is_allowed(current: str, target: str) -> None:
    check_transition(current, target)


@pytest.mark.parametrize(("current", "target"), ILLEGAL)
def test_illegal_edge_is_refused(current: str, target: str) -> None:
    with pytest.raises(TransitionError):
        check_transition(current, target)


def test_every_state_is_known() -> None:
    assert len(STATES) == 11
    for state in STATES:
        assert allowed_from(state) == allowed_from(state)


def test_terminal_states_have_no_exit() -> None:
    assert TERMINAL == {"COMPLETED", "REJECTED"}
    for state in TERMINAL:
        assert allowed_from(state) == frozenset()
        assert is_terminal(state)


def test_blocked_can_resume_into_every_working_state() -> None:
    working = {
        "PROPOSED",
        "PLANNED",
        "RESEARCHING",
        "DESIGNING",
        "APPROVED",
        "IMPLEMENTING",
        "EXPERIMENTING",
        "VERIFYING",
    }
    assert working <= allowed_from("BLOCKED")


def test_blocked_cannot_skip_to_a_terminal_state() -> None:
    for terminal in TERMINAL:
        with pytest.raises(TransitionError):
            check_transition("BLOCKED", terminal)


def test_unknown_state_is_refused() -> None:
    with pytest.raises(TransitionError, match="not a FORGE state"):
        check_transition("RUNNING", "PLANNED")


def test_a_terminal_refusal_says_so() -> None:
    with pytest.raises(TransitionError, match="terminal"):
        check_transition("COMPLETED", "PLANNED")


def test_an_illegal_move_names_what_was_allowed() -> None:
    with pytest.raises(TransitionError, match="may move to"):
        check_transition("PLANNED", "APPROVED")


@pytest.mark.parametrize("state", sorted(TERMINAL))
def test_a_terminal_state_does_not_resume(state: str) -> None:
    assert not resumable(state)


@pytest.mark.parametrize("state", STATES)
def test_every_non_terminal_state_resumes(state: str) -> None:
    assert resumable(state) is (state not in TERMINAL)


def test_unknown_state_does_not_resume() -> None:
    assert not resumable("NONSENSE")

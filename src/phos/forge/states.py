"""The eleven execution states and the only legal moves between them.

``SPEC.md`` section 2 is the prose; this module is the table. Keeping it in one place is what
stops a caller inventing a transition, and what makes "resume after interruption" a question with
an answer: a resume is a move out of ``BLOCKED`` or a re-entry into the state an operation was in
when it was interrupted, and both are checked here.
"""

from __future__ import annotations

from typing import Final, Literal

State = Literal[
    "PROPOSED",
    "PLANNED",
    "RESEARCHING",
    "DESIGNING",
    "APPROVED",
    "IMPLEMENTING",
    "EXPERIMENTING",
    "VERIFYING",
    "COMPLETED",
    "BLOCKED",
    "REJECTED",
]

#: Every state, in the order the task names them.
STATES: Final[tuple[str, ...]] = (
    "PROPOSED",
    "PLANNED",
    "RESEARCHING",
    "DESIGNING",
    "APPROVED",
    "IMPLEMENTING",
    "EXPERIMENTING",
    "VERIFYING",
    "COMPLETED",
    "BLOCKED",
    "REJECTED",
)

#: The states from which nothing further happens. Resuming one is refused.
TERMINAL: Final[frozenset[str]] = frozenset({"COMPLETED", "REJECTED"})

#: The legal moves. A move not listed here is refused with the states it would have allowed.
_TRANSITIONS: Final[dict[str, frozenset[str]]] = {
    "PROPOSED": frozenset({"PLANNED", "REJECTED", "BLOCKED"}),
    "PLANNED": frozenset({"RESEARCHING", "DESIGNING", "REJECTED", "BLOCKED"}),
    "RESEARCHING": frozenset({"DESIGNING", "REJECTED", "BLOCKED"}),
    "DESIGNING": frozenset({"APPROVED", "REJECTED", "BLOCKED"}),
    "APPROVED": frozenset({"IMPLEMENTING", "BLOCKED"}),
    "IMPLEMENTING": frozenset({"EXPERIMENTING", "VERIFYING", "BLOCKED"}),
    "EXPERIMENTING": frozenset({"VERIFYING", "IMPLEMENTING", "BLOCKED"}),
    "VERIFYING": frozenset({"COMPLETED", "IMPLEMENTING", "REJECTED", "BLOCKED"}),
    "BLOCKED": frozenset(
        {
            "PROPOSED",
            "PLANNED",
            "RESEARCHING",
            "DESIGNING",
            "APPROVED",
            "IMPLEMENTING",
            "EXPERIMENTING",
            "VERIFYING",
        }
    ),
    "COMPLETED": frozenset(),
    "REJECTED": frozenset(),
}


class TransitionError(ValueError):
    """A move between states that the table does not allow."""


def allowed_from(state: str) -> frozenset[str]:
    """Return the states ``state`` may move to.

    Args:
        state: The current state.

    Returns:
        The set of states it may move to, which is empty for a terminal state.

    Raises:
        TransitionError: If ``state`` is not one of the eleven.
    """
    try:
        return _TRANSITIONS[state]
    except KeyError:
        raise TransitionError(
            f"{state!r} is not a FORGE state. Known: {', '.join(STATES)}"
        ) from None


def check_transition(current: str, target: str) -> None:
    """Refuse a move the table does not allow.

    Args:
        current: The state the operation is in.
        target: The state it is being moved to.

    Raises:
        TransitionError: If either state is unknown, or the move is not in the table.
    """
    permitted = allowed_from(current)
    if target in permitted:
        return
    if not permitted:
        raise TransitionError(
            f"{current} is terminal: an operation that finished or was rejected does not restart"
        )
    raise TransitionError(
        f"{current} may not move to {target}. It may move to: {', '.join(sorted(permitted))}"
    )


def is_terminal(state: str) -> bool:
    """Return whether ``state`` is one nothing further happens from."""
    return state in TERMINAL


def resumable(state: str) -> bool:
    """Return whether an operation in ``state`` may be picked up again.

    ``BLOCKED`` is the state a failed gate or a human interruption leaves, so it is resumable. A
    working state is resumable because an interrupted process leaves the operation where it was.
    A terminal state is not.
    """
    return state in STATES and not is_terminal(state)

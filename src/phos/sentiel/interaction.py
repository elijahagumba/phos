"""Declared interaction structure (Session S2).

Normal interaction is who this **declared role** is expected to talk to, if a directory says
so. Absence is insufficient, not a graph embedding. Do not cluster counterparties from who
emails whom (the circularity ADR 0010 refused for topology).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "UNDECLARED_INTERACTION_CAVEAT",
    "DeclaredCounterpartyDirectory",
    "interaction_is_expected",
]

UNDECLARED_INTERACTION_CAVEAT: Final = (
    "Interaction structure is declared from a directory, never inferred from who talks to whom. "
    "A missing directory is insufficient_evidence, not an alert."
)


class DeclaredCounterpartyDirectory(BaseModel):
    """Who each role is expected to communicate with.

    Attributes:
        allowed: ``role -> frozenset of counterpart roles``. A role absent from the mapping
            has no declared interaction structure.
    """

    model_config = ConfigDict(frozen=True)

    allowed: Mapping[str, frozenset[str]] = Field(default_factory=dict)

    def counterparties_of(self, role: str) -> frozenset[str] | None:
        """Return the declared counterpart roles, or ``None`` if the role is undeclared."""
        if role not in self.allowed:
            return None
        return self.allowed[role]


def interaction_is_expected(
    directory: DeclaredCounterpartyDirectory,
    role: str,
    counterparty_role: str,
) -> bool | None:
    """Return whether ``role`` is expected to talk to ``counterparty_role``.

    Returns:
        ``True`` / ``False`` when the directory names the role. ``None`` when there is no
        declared structure — the caller must treat that as insufficient, not as an anomaly.
    """
    allowed = directory.counterparties_of(role)
    if allowed is None:
        return None
    return counterparty_role in allowed

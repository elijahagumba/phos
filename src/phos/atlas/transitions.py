"""Declared-phase *transitions*: what follows what, not a clustered regime.

``PhaseConditionalModel`` already looks up a declared register. This module adds the next
question: given the current declared phase, is the *next* declared phase one that training
saw? Distillation still has no declared phase (ADR 0018 / 0031). Inferring one from
correlations is refused here, not implemented.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final, Self

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "DISTILLATION_HAS_NO_DECLARED_PHASE",
    "DeclaredPhaseTransitionModel",
    "refuse_inferred_phase",
]

DISTILLATION_HAS_NO_DECLARED_PHASE: Final = (
    "REFUSED (ADR 0018/0031): batch-distillation has no declared phase register. "
    "Phase-conditional is louder than ungated Mahalanobis on that ZIP. "
    "Do not invent a phase column from correlations. dwell_samples stays 1."
)


def refuse_inferred_phase(corpus: str) -> str:
    """Return the standing refusal for a corpus that has no declared phase register."""
    if corpus in {"batch-distillation", "distillation", "zenodo-distillation"}:
        return DISTILLATION_HAS_NO_DECLARED_PHASE
    return (
        f"REFUSED: {corpus} has no declared phase register in the files PHOS reads. "
        "Do not infer phase from co-movement (ADR 0010)."
    )


class DeclaredPhaseTransitionModel(BaseModel):
    """Allowed ``(phase_t, phase_t+1)`` pairs learned from a declared integer register."""

    model_config = ConfigDict(frozen=True)

    allowed: frozenset[tuple[int, int]] = Field(min_length=1)

    @classmethod
    def fit(cls, phases: Sequence[int]) -> Self:
        """Learn adjacent pairs from an attack-free declared-phase stream.

        Raises:
            ValueError: If ``phases`` is too short to observe a transition. Empty input is
                how distillation would look if someone "fitted" a phase nobody declared.
        """
        if len(phases) < 2:
            raise ValueError(
                "DeclaredPhaseTransitionModel needs a declared phase stream with at least "
                "one transition. Distillation has no such register; do not invent one."
            )
        allowed = frozenset((int(phases[i]), int(phases[i + 1])) for i in range(len(phases) - 1))
        return cls(allowed=allowed)

    def unexpected_indices(self, phases: Sequence[int]) -> tuple[int, ...]:
        """Return indices of *arrival* phases whose predecessor pair was never trained."""
        unexpected: list[int] = []
        for index in range(1, len(phases)):
            pair = (int(phases[index - 1]), int(phases[index]))
            if pair not in self.allowed:
                unexpected.append(index)
        return tuple(unexpected)

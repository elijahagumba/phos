"""Declared behaviour-chain shapes (ADR 0191).

A shape is present when its tokens appear in order in one day's collapsed
sequence. The score is the population surprise of those shapes on the
attack-free prefix. No host or recipient name enters the score.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field

from phos.sentiel.day_facts import DayFacts
from phos.sentiel.traces import DeclaredToken

__all__ = ["DECLARED_CHAINS", "ChainSurprise", "shape_present"]

DECLARED_CHAINS: tuple[tuple[DeclaredToken, ...], ...] = (
    (DeclaredToken.DEVICE_CONNECT, DeclaredToken.FILE_ACCESS, DeclaredToken.EMAIL_EXTERNAL),
    (DeclaredToken.DEVICE_CONNECT, DeclaredToken.FILE_ACCESS, DeclaredToken.HTTP_REQUEST),
    (DeclaredToken.HTTP_REQUEST, DeclaredToken.EMAIL_EXTERNAL, DeclaredToken.DEVICE_CONNECT),
)


def shape_present(sequence: Sequence[DeclaredToken], shape: Sequence[DeclaredToken]) -> bool:
    """Return whether ``shape`` appears in order inside ``sequence``."""
    if not shape:
        return False
    index = 0
    for token in sequence:
        if token == shape[index]:
            index += 1
            if index == len(shape):
                return True
    return False


class ChainSurprise(BaseModel):
    """Laplace-smoothed training-prefix frequency of each declared shape.

    Attributes:
        counts: How many training days contained each shape, keyed by the
            joined token values.
        n_days: Training days seen.
    """

    model_config = ConfigDict(frozen=True)

    counts: dict[str, int]
    n_days: int = Field(ge=0)

    @classmethod
    def fit(cls, train: Sequence[DayFacts]) -> ChainSurprise:
        """Count declared shapes on the attack-free prefix."""
        counts = {_key(shape): 0 for shape in DECLARED_CHAINS}
        for day in train:
            for shape in DECLARED_CHAINS:
                if shape_present(day.sequence, shape):
                    counts[_key(shape)] += 1
        return cls(counts=counts, n_days=len(train))

    def score(self, day: DayFacts) -> float:
        """Return summed surprise for shapes present on ``day``."""
        total = 0.0
        vocab = len(DECLARED_CHAINS)
        denominator = float(self.n_days + vocab)
        for shape in DECLARED_CHAINS:
            if not shape_present(day.sequence, shape):
                continue
            seen = self.counts[_key(shape)]
            total += -math.log((seen + 1) / denominator)
        return total


def _key(shape: Sequence[DeclaredToken]) -> str:
    return "".join(token.value for token in shape)

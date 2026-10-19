"""Types for an onboarding suggestion. A suggestion is not a role declaration (ADR 0220)."""

from __future__ import annotations

from enum import Enum
from typing import Final, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from phos.atlas.signal_roles import SignalRole

SUGGESTION_IS_NOT_A_DECLARATION: Final = (
    "A suggestion is not a declaration. A role the plant map trusts is declared from "
    "documentation (ADR 0123). This tool only proposes a role and a kind for an engineer "
    "to confirm or change (ADR 0220)."
)
"""The sentence that travels with every brief this module prints."""

BRIEF_HEADER: Final = (
    "# Suggestions are not declarations (ADR 0123, ADR 0220). "
    "Accept or edit each line. A blank role or kind means this tool would not guess."
)
"""First line of the printed suggestion list."""

SAMPLE_ROWS: Final = 500
"""How many data rows of a wide historian export the brief looks at."""

MIN_SAMPLE: Final = 20
"""Below this, a sample cannot separate a setpoint, a sensor, and a stuck instrument."""


class TagKind(str, Enum):
    """The five kinds an onboarding brief is willing to suggest.

    Attributes:
        FLOW: A flow measurement, or a tag whose name says flow.
        PRESSURE: A pressure measurement, or a tag whose name says pressure.
        LEVEL: A level measurement, or a tag whose name says level.
        PUMP: A pump.
        VALVE: A valve.
    """

    FLOW = "flow"
    PRESSURE = "pressure"
    LEVEL = "level"
    PUMP = "pump"
    VALVE = "valve"


class SuggestionEvidence(BaseModel):
    """One ground for a suggestion: a token, a statistic, or a capture fact.

    Attributes:
        token: The name token, when the ground is the tag's name. ``"none"`` means the name
            was searched and nothing in it matched.
        statistic: A short description of the sample statistic, when the ground is the values.
        capture: A short description of the observed references, when the ground is the capture.
        text: The same ground, as one sentence an engineer can read.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    token: str | None = None
    statistic: str | None = None
    capture: str | None = None
    text: str = Field(min_length=1)

    @model_validator(mode="after")
    def _needs_a_ground(self) -> Self:
        if not any((self.token, self.statistic, self.capture)):
            raise ValueError("evidence names a token, a statistic, or a capture fact")
        return self


class TagSample(BaseModel):
    """One tag and the sample of values taken from the historian export.

    Attributes:
        tag: Column or point name.
        values: Finite samples, in file order, already capped by the caller.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    tag: str = Field(min_length=1)
    values: tuple[float, ...] = ()


class CaptureHit(BaseModel):
    """One observed reference to a tag.

    Attributes:
        tag: The tag the capture referred to.
        access: ``read``, ``write``, or ``unknown`` when the table does not say.
        count: How many references this row stands for.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    tag: str = Field(min_length=1)
    access: Literal["read", "write", "unknown"] = "unknown"
    count: int = Field(default=1, ge=0)


class TagSuggestion(BaseModel):
    """A proposed role and kind, with the evidence an engineer checks.

    Attributes:
        tag: The tag the proposal is about.
        role: Sensor, actuator, or setpoint, or ``None`` when this tool would not guess.
        kind: One of the five kinds, or ``None`` when no name token named one.
        evidence: The tokens, statistics, and capture facts the proposal used. Never empty.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    tag: str = Field(min_length=1)
    role: SignalRole | None
    kind: TagKind | None
    evidence: tuple[SuggestionEvidence, ...] = Field(min_length=1)

    @property
    def evidence_text(self) -> str:
        """The evidence as one line, in the order it was gathered."""
        return "; ".join(item.text for item in self.evidence)

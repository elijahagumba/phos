"""The `Hypothesis` — a candidate explanation with its evidence and confidence."""

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from phos.ontology.enums import Domain, EvidenceRole, HypothesisStatus
from phos.ontology.ids import (
    HYPOTHESIS_PREFIX,
    EvidenceId,
    HypothesisId,
    UtcDatetime,
    new_id,
    utc_now,
)

__all__ = ["Hypothesis"]


class Hypothesis(BaseModel):
    """One competing explanation for observed behaviour.

    Hypotheses are generated from a curated, per-domain **template library** matched to evidence
    patterns (PART 4) — not by open-ended reasoning. ``template_id`` records which template
    produced this instance so that provenance is always inspectable.

    Immutable: the mutating-looking methods return new instances.

    Attributes:
        id: Stable opaque identifier, ``hyp_*``.
        label: Human-readable explanation, e.g. ``"Unauthorised control activity"``.
        template_id: Which hypothesis template produced this instance.
        domain: Which engine owns it.
        prior: Probability before evidence, in ``[0, 1]``.
        confidence: Current probability after evidence, in ``[0, 1]``. Uncalibrated until PART 4
            sets it — never surface this value to a user before then.
        status: Lifecycle state.
        supporting: Evidence ids that raise confidence, in the order they were attached.
        contradictory: Evidence ids that lower it, in the order they were attached.
        created_at: When the hypothesis was generated, UTC.
        updated_at: When it last changed, UTC.

    Invariants:
        An evidence id never appears twice in one list, nor in both lists at once.
    """

    model_config = ConfigDict(frozen=True)

    id: HypothesisId = Field(default_factory=lambda: new_id(HYPOTHESIS_PREFIX))
    label: str
    template_id: str
    domain: Domain
    prior: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    status: HypothesisStatus
    supporting: list[EvidenceId] = Field(default_factory=list)
    contradictory: list[EvidenceId] = Field(default_factory=list)
    created_at: UtcDatetime = Field(default_factory=utc_now)
    updated_at: UtcDatetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def _check_evidence_lists_are_disjoint(self) -> Self:
        for name, ids in (("supporting", self.supporting), ("contradictory", self.contradictory)):
            if len(set(ids)) != len(ids):
                raise ValueError(f"{name} contains duplicate evidence ids")
        overlap = set(self.supporting) & set(self.contradictory)
        if overlap:
            raise ValueError(
                f"evidence cannot be both supporting and contradictory for one hypothesis: "
                f"{sorted(overlap)}"
            )
        return self

    def with_evidence(self, evidence_id: EvidenceId, role: EvidenceRole) -> "Hypothesis":
        """Return a copy with ``evidence_id`` attached in ``role``.

        Attaching an id that is already present in the *other* list moves it rather than
        duplicating it, so the disjointness invariant holds by construction — reasoning is allowed
        to change its mind about what a fact means. Re-attaching in the same role is a no-op that
        still refreshes ``updated_at``.

        Args:
            evidence_id: The evidence to attach.
            role: Whether it supports or contradicts this hypothesis.

        Returns:
            A new `Hypothesis`; the receiver is unchanged.
        """
        supporting = [e for e in self.supporting if e != evidence_id]
        contradictory = [e for e in self.contradictory if e != evidence_id]
        if role is EvidenceRole.SUPPORTING:
            supporting.append(evidence_id)
        else:
            contradictory.append(evidence_id)
        return self.model_copy(
            update={
                "supporting": supporting,
                "contradictory": contradictory,
                "updated_at": utc_now(),
            }
        )

    def with_confidence(self, value: float) -> "Hypothesis":
        """Return a copy whose confidence is ``value``.

        Args:
            value: The new confidence, which must lie in ``[0, 1]``.

        Returns:
            A new `Hypothesis`; the receiver is unchanged.

        Raises:
            pydantic.ValidationError: If ``value`` is outside ``[0, 1]``. Out-of-range confidence
                is a bug in the caller, so it is rejected rather than silently clamped.
        """
        return Hypothesis.model_validate(
            {**self.model_dump(), "confidence": value, "updated_at": utc_now()}
        )

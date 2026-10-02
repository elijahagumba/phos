"""The `Evidence` atom that reasoning consumes."""

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from phos.ontology.enums import Domain, EvidenceKind, FacetKind
from phos.ontology.ids import EVIDENCE_PREFIX, EntityId, EvidenceId, UtcDatetime, new_id

__all__ = ["Evidence"]


class Evidence(BaseModel):
    """A behavioural fact promoted into something reasoning can weigh.

    Evidence deliberately does *not* record which hypothesis it bears on. That link, and its
    :class:`~phos.ontology.enums.EvidenceRole`, live on the `Hypothesis`, because the same
    evidence can support one explanation while contradicting another.

    **The facet is the machine-readable half of what the summary says in prose.** `kind` records
    how a fact was produced; it cannot say *which* fact, and four Atlas `EvidencePattern`
    subclasses turn on exactly that (ADR 0070). Those matchers used to recover it by parsing a
    declared prefix off `summary`, which made a reasoning outcome depend on the wording of a
    sentence written for a human. The facet carries the same declaration as a typed pair, and
    `summary` keeps the prefix so nothing a reader sees changes.

    Attributes:
        id: Stable opaque identifier, ``ev_*``.
        kind: What sort of fact produced it.
        source_id: Id of the `Deviation`, `ForecastMiss` or relationship change it came from.
            This is the traceability link: anything a user sees must lead back through here.
        entity_ids: The entities involved.
        timestamp: When the underlying fact occurred, UTC.
        domain: Which engine produced it.
        weight: How strongly this bears on a hypothesis. Non-negative and unbounded above; set by
            the reasoning engine in PART 4, defaults to 1.0 (neutral).
        summary: Short human-readable description, e.g. ``"Unexpected Modbus write to PLC-4"``.
        facet_kind: Which sub-kind of fact this is, or ``None`` when it declares none. ``None`` is
            a statement that the fact carries no sub-kind, not an admission that one is unknown.
        facet: The feature naming this fact within its facet — a graph finding, a command-behaviour
            feature, a work-order feature. Set together with `facet_kind` or not at all.

    Invariants:
        `facet_kind` and `facet` are both set or both absent. A facet kind with no feature names
        nothing, and a feature with no kind cannot be matched against a closed vocabulary; either
        half alone would be a fact that says less than it appears to.
    """

    model_config = ConfigDict(frozen=True)

    id: EvidenceId = Field(default_factory=lambda: new_id(EVIDENCE_PREFIX))
    kind: EvidenceKind
    source_id: str
    entity_ids: list[EntityId] = Field(min_length=1)
    timestamp: UtcDatetime
    domain: Domain
    weight: float = Field(default=1.0, ge=0.0)
    summary: str
    facet_kind: FacetKind | None = None
    facet: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _check_facet_pairing(self) -> Self:
        """Refuse half a facet, because half of one is not a weaker claim but an unreadable one."""
        if (self.facet_kind is None) != (self.facet is None):
            raise ValueError(
                f"facet_kind and facet must be set together or not at all; got "
                f"facet_kind={self.facet_kind!r} and facet={self.facet!r}. A kind with no feature "
                "names nothing, and a feature with no kind cannot be checked against a vocabulary"
            )
        return self

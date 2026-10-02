"""The `Narrative` — an ordered set of evidence and hypotheses forming one incident story."""

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from phos.ontology.enums import Domain
from phos.ontology.ids import (
    NARRATIVE_PREFIX,
    EvidenceId,
    HypothesisId,
    NarrativeId,
    UtcDatetime,
    new_id,
    utc_now,
)

if TYPE_CHECKING:  # pragma: no cover — import cycle broken for type checking only
    from phos.ontology.evidence import Evidence
    from phos.ontology.store import EvidenceStore

__all__ = ["Narrative"]


class Narrative(BaseModel):
    """An incident: the evidence, the competing explanations, and how they connect.

    This is what an operator ultimately reads. It references its parts by id so that the store
    stays the single source of truth and the object remains acyclic and serialisable.

    Attributes:
        id: Stable opaque identifier, ``nar_*``.
        title: Human-readable headline for the incident.
        domain: Owning engine; ``INTELLIGENCE`` when the story spans Atlas and Sentiel.
        hypothesis_ids: The competing explanations under consideration.
        evidence_ids: The evidence in the story, ordered by time.
        overall_confidence: Reserved for a **calibrated** narrative probability in ``[0, 1]``.
            Engines leave this ``None`` until hypothesis confidence is calibrated
            (Constitution §3.3). Hypothesis ``confidence`` remains on each explanation for
            ranking and reconstruction; it is not copied here.
        causal_edges: Directed ``(from_id, to_id)`` pairs from evidence ids to hypothesis ids.
            Each pair is a reconstructable bearing: the evidence id sits on that hypothesis's
            supporting or contradictory list. This is not a declared plant causal graph and not
            co-occurrence of two clocks. The UI draws these edges; it does not invent them.
        created_at: When the narrative was opened, UTC.
        updated_at: When it last changed, UTC.
    """

    model_config = ConfigDict(frozen=True)

    id: NarrativeId = Field(default_factory=lambda: new_id(NARRATIVE_PREFIX))
    title: str
    domain: Domain
    hypothesis_ids: list[HypothesisId]
    evidence_ids: list[EvidenceId]
    overall_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    causal_edges: list[tuple[str, str]] = Field(default_factory=list)
    created_at: UtcDatetime = Field(default_factory=utc_now)
    updated_at: UtcDatetime = Field(default_factory=utc_now)

    def timeline(self, store: "EvidenceStore") -> list["Evidence"]:
        """Resolve this narrative's evidence from ``store``, ordered by time.

        Args:
            store: The store holding the referenced evidence.

        Returns:
            The referenced `Evidence` sorted ascending by timestamp. The sort is stable, so
            evidence sharing a timestamp keeps the narrative's own reference order.

        Raises:
            KeyError: If the narrative references evidence the store does not hold. A narrative
                whose story cannot be reconstructed is a traceability failure, not an empty list.
        """
        resolved: list[Evidence] = []
        for evidence_id in self.evidence_ids:
            evidence = store.get_evidence(evidence_id)
            if evidence is None:
                raise KeyError(evidence_id)
            resolved.append(evidence)
        return sorted(resolved, key=lambda evidence: evidence.timestamp)

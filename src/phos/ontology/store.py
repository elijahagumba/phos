"""The evidence store: the single source of truth for ontology objects.

Because ontology objects reference each other by id rather than by nesting, something has to
guarantee those references resolve. That is this module's job: the store validates referential
integrity **at write time**, so an object that made it into the store is one whose story can
always be reconstructed. This is where the "everything displayed is traceable" invariant is
mechanically enforced.
"""

import logging
from collections.abc import Mapping
from typing import Protocol, runtime_checkable

from phos.ontology.entities import Entity
from phos.ontology.enums import Domain
from phos.ontology.evidence import Evidence
from phos.ontology.hypotheses import Hypothesis
from phos.ontology.ids import (
    DeviationId,
    EntityId,
    EvidenceId,
    HypothesisId,
    NarrativeId,
    ObservationId,
)
from phos.ontology.narratives import Narrative
from phos.ontology.observations import Deviation, Observation

__all__ = ["EvidenceStore", "InMemoryEvidenceStore"]

logger = logging.getLogger(__name__)


@runtime_checkable
class EvidenceStore(Protocol):
    """Read/write access to every ontology object type.

    Engines, reasoning and the API all talk to this interface rather than to a concrete store, so
    that a persistent implementation can replace the in-memory one without touching callers.

    All ``add_*`` methods reject duplicate ids and unresolvable references with ``ValueError``.
    All query methods return results in insertion order, so output is deterministic.
    """

    def add_entity(self, entity: Entity) -> None:
        """Store an entity. Raises ``ValueError`` if its id is already present."""
        ...

    def get_entity(self, entity_id: EntityId) -> Entity | None:
        """Return the entity with this id, or ``None``."""
        ...

    def entities(self, domain: Domain | None = None) -> list[Entity]:
        """Return stored entities, optionally filtered to one domain, in insertion order."""
        ...

    def add_observation(self, observation: Observation) -> None:
        """Store an observation. Raises ``ValueError`` if its id is already present."""
        ...

    def get_observation(self, observation_id: ObservationId) -> Observation | None:
        """Return the observation with this id, or ``None``."""
        ...

    def observations(self, domain: Domain | None = None) -> list[Observation]:
        """Return stored observations, optionally filtered to one domain, in insertion order."""
        ...

    def add_deviation(self, deviation: Deviation) -> None:
        """Store a deviation. Raises ``ValueError`` if its observation is unknown."""
        ...

    def get_deviation(self, deviation_id: DeviationId) -> Deviation | None:
        """Return the deviation with this id, or ``None``."""
        ...

    def deviations(self) -> list[Deviation]:
        """Return stored deviations in insertion order."""
        ...

    def add_evidence(self, evidence: Evidence) -> None:
        """Store a piece of evidence. Raises ``ValueError`` if its id is already present."""
        ...

    def get_evidence(self, evidence_id: EvidenceId) -> Evidence | None:
        """Return the evidence with this id, or ``None``."""
        ...

    def evidence(self, domain: Domain | None = None) -> list[Evidence]:
        """Return stored evidence, optionally filtered to one domain, in insertion order."""
        ...

    def add_hypothesis(self, hypothesis: Hypothesis) -> None:
        """Store a hypothesis. Raises ``ValueError`` if it references unknown evidence."""
        ...

    def get_hypothesis(self, hypothesis_id: HypothesisId) -> Hypothesis | None:
        """Return the hypothesis with this id, or ``None``."""
        ...

    def hypotheses(self, domain: Domain | None = None) -> list[Hypothesis]:
        """Return stored hypotheses, optionally filtered to one domain, in insertion order."""
        ...

    def add_narrative(self, narrative: Narrative) -> None:
        """Store a narrative. Raises ``ValueError`` if it references unknown ids."""
        ...

    def get_narrative(self, narrative_id: NarrativeId) -> Narrative | None:
        """Return the narrative with this id, or ``None``."""
        ...

    def narratives(self, domain: Domain | None = None) -> list[Narrative]:
        """Return stored narratives, optionally filtered to one domain, in insertion order."""
        ...

    def evidence_for(self, hypothesis_id: HypothesisId) -> tuple[list[Evidence], list[Evidence]]:
        """Resolve a hypothesis's evidence into ``(supporting, contradictory)``.

        Raises ``KeyError`` if the hypothesis is unknown.
        """
        ...


class InMemoryEvidenceStore:
    """Dict-backed :class:`EvidenceStore` for tests, evaluation runs and single-process use.

    Python dicts preserve insertion order, which is what makes every query deterministic.
    """

    def __init__(self) -> None:
        """Create an empty store."""
        self._entities: dict[EntityId, Entity] = {}
        self._observations: dict[ObservationId, Observation] = {}
        self._deviations: dict[DeviationId, Deviation] = {}
        self._evidence: dict[EvidenceId, Evidence] = {}
        self._hypotheses: dict[HypothesisId, Hypothesis] = {}
        self._narratives: dict[NarrativeId, Narrative] = {}

    @staticmethod
    def _reject_duplicate(existing: Mapping[str, object], object_id: str, kind: str) -> None:
        """Raise ``ValueError`` if ``object_id`` is already stored.

        Objects are immutable value objects, so re-adding an id would silently replace history.
        Callers that mean to revise an object should store the revision under a new id.
        """
        if object_id in existing:
            raise ValueError(f"{kind} {object_id} is already stored")

    @staticmethod
    def _require_known(
        known: Mapping[str, object],
        referenced_ids: list[str],
        kind: str,
        referrer: str,
    ) -> None:
        """Raise ``ValueError`` if any referenced id is absent from ``known``."""
        missing = [reference for reference in referenced_ids if reference not in known]
        if missing:
            raise ValueError(f"{referrer} references unknown {kind}: {', '.join(missing)}")

    def add_entity(self, entity: Entity) -> None:
        """Store an entity.

        Raises:
            ValueError: If an entity with the same id is already stored.
        """
        self._reject_duplicate(self._entities, entity.id, "entity")
        self._entities[entity.id] = entity

    def get_entity(self, entity_id: EntityId) -> Entity | None:
        """Return the entity with this id, or ``None`` if it is not stored."""
        return self._entities.get(entity_id)

    def entities(self, domain: Domain | None = None) -> list[Entity]:
        """Return stored entities, optionally filtered to ``domain``, in insertion order."""
        return [e for e in self._entities.values() if domain is None or e.domain is domain]

    def add_observation(self, observation: Observation) -> None:
        """Store an observation.

        Raises:
            ValueError: If an observation with the same id is already stored.
        """
        self._reject_duplicate(self._observations, observation.id, "observation")
        self._observations[observation.id] = observation

    def get_observation(self, observation_id: ObservationId) -> Observation | None:
        """Return the observation with this id, or ``None`` if it is not stored."""
        return self._observations.get(observation_id)

    def observations(self, domain: Domain | None = None) -> list[Observation]:
        """Return stored observations, optionally filtered to ``domain``, in insertion order."""
        return [o for o in self._observations.values() if domain is None or o.domain is domain]

    def add_deviation(self, deviation: Deviation) -> None:
        """Store a deviation, checking that the observation it explains exists.

        Raises:
            ValueError: If the id is already stored, or ``observation_id`` is unknown.
        """
        self._reject_duplicate(self._deviations, deviation.id, "deviation")
        self._require_known(
            self._observations,
            [deviation.observation_id],
            "observation",
            f"deviation {deviation.id}",
        )
        self._deviations[deviation.id] = deviation

    def get_deviation(self, deviation_id: DeviationId) -> Deviation | None:
        """Return the deviation with this id, or ``None`` if it is not stored."""
        return self._deviations.get(deviation_id)

    def deviations(self) -> list[Deviation]:
        """Return stored deviations in insertion order."""
        return list(self._deviations.values())

    def add_evidence(self, evidence: Evidence) -> None:
        """Store a piece of evidence.

        ``source_id`` is not checked here: evidence of kind ``RELATIONSHIP_CHANGE`` or
        ``SEQUENCE_ANOMALY`` derives from facts this PART does not yet model.

        Raises:
            ValueError: If evidence with the same id is already stored.
        """
        self._reject_duplicate(self._evidence, evidence.id, "evidence")
        self._evidence[evidence.id] = evidence

    def get_evidence(self, evidence_id: EvidenceId) -> Evidence | None:
        """Return the evidence with this id, or ``None`` if it is not stored."""
        return self._evidence.get(evidence_id)

    def evidence(self, domain: Domain | None = None) -> list[Evidence]:
        """Return stored evidence, optionally filtered to ``domain``, in insertion order."""
        return [e for e in self._evidence.values() if domain is None or e.domain is domain]

    def add_hypothesis(self, hypothesis: Hypothesis) -> None:
        """Store a hypothesis, checking that all the evidence it cites exists.

        Raises:
            ValueError: If the id is already stored, or any cited evidence id is unknown.
        """
        self._reject_duplicate(self._hypotheses, hypothesis.id, "hypothesis")
        self._require_known(
            self._evidence,
            [*hypothesis.supporting, *hypothesis.contradictory],
            "evidence",
            f"hypothesis {hypothesis.id}",
        )
        self._hypotheses[hypothesis.id] = hypothesis

    def get_hypothesis(self, hypothesis_id: HypothesisId) -> Hypothesis | None:
        """Return the hypothesis with this id, or ``None`` if it is not stored."""
        return self._hypotheses.get(hypothesis_id)

    def hypotheses(self, domain: Domain | None = None) -> list[Hypothesis]:
        """Return stored hypotheses, optionally filtered to ``domain``, in insertion order."""
        return [h for h in self._hypotheses.values() if domain is None or h.domain is domain]

    def add_narrative(self, narrative: Narrative) -> None:
        """Store a narrative, checking that every hypothesis and evidence it cites exists.

        Raises:
            ValueError: If the id is already stored, or any cited id is unknown. Causal edges
                must name evidence and hypotheses already listed on the narrative, so a displayed
                graph can be rebuilt from stored Evidence (Constitution §3.2). Without this,
                :meth:`Narrative.timeline` could not reconstruct the story it promises.
        """
        self._reject_duplicate(self._narratives, narrative.id, "narrative")
        referrer = f"narrative {narrative.id}"
        self._require_known(self._hypotheses, narrative.hypothesis_ids, "hypothesis", referrer)
        self._require_known(self._evidence, narrative.evidence_ids, "evidence", referrer)
        cited_evidence = set(narrative.evidence_ids)
        cited_hypotheses = set(narrative.hypothesis_ids)
        for source, target in narrative.causal_edges:
            if source not in cited_evidence:
                raise ValueError(
                    f"{referrer} causal_edges cite evidence {source} not in evidence_ids"
                )
            if target not in cited_hypotheses:
                raise ValueError(
                    f"{referrer} causal_edges cite hypothesis {target} not in hypothesis_ids"
                )
        self._narratives[narrative.id] = narrative

    def get_narrative(self, narrative_id: NarrativeId) -> Narrative | None:
        """Return the narrative with this id, or ``None`` if it is not stored."""
        return self._narratives.get(narrative_id)

    def narratives(self, domain: Domain | None = None) -> list[Narrative]:
        """Return stored narratives, optionally filtered to ``domain``, in insertion order."""
        return [n for n in self._narratives.values() if domain is None or n.domain is domain]

    def evidence_for(self, hypothesis_id: HypothesisId) -> tuple[list[Evidence], list[Evidence]]:
        """Resolve a hypothesis's evidence ids into ``(supporting, contradictory)``.

        Args:
            hypothesis_id: The hypothesis whose evidence to resolve.

        Returns:
            Two lists of `Evidence`, each in the order the hypothesis records them.

        Raises:
            KeyError: If the hypothesis is not stored.
        """
        hypothesis = self._hypotheses.get(hypothesis_id)
        if hypothesis is None:
            raise KeyError(hypothesis_id)
        # Both lists were validated on add, so every id resolves.
        supporting = [self._evidence[e] for e in hypothesis.supporting]
        contradictory = [self._evidence[e] for e in hypothesis.contradictory]
        return supporting, contradictory

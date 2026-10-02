"""The PHOS ontology: the one typed data model every engine and screen shares.

Import everything public from here — ``from phos.ontology import Evidence, Hypothesis`` — rather
than from the submodules, so that internal layout can change without breaking callers.

The shape of the model, and why:

- Objects are **frozen** Pydantic value objects. An "update" produces a new object, so evidence
  and confidence histories cannot be silently rewritten.
- Objects reference each other **by id**, never by nesting. That keeps them acyclic, trivially
  JSON-serialisable for the API, and makes the store the single source of truth.
- The **store** enforces referential integrity on write, so anything stored is traceable.

No detection, scoring, reasoning or calibration lives here; later PARTs add those on top.
"""

from phos.ontology.entities import Entity
from phos.ontology.enums import (
    Domain,
    EntityType,
    EvidenceKind,
    EvidenceRole,
    FacetKind,
    HypothesisStatus,
)
from phos.ontology.evidence import Evidence
from phos.ontology.hypotheses import Hypothesis
from phos.ontology.ids import (
    DEVIATION_PREFIX,
    ENTITY_PREFIX,
    EVIDENCE_PREFIX,
    FORECAST_PREFIX,
    HYPOTHESIS_PREFIX,
    NARRATIVE_PREFIX,
    OBSERVATION_PREFIX,
    DeviationId,
    EntityId,
    EvidenceId,
    ForecastId,
    HypothesisId,
    NarrativeId,
    ObservationId,
    UtcDatetime,
    new_id,
    utc_now,
)
from phos.ontology.narratives import Narrative
from phos.ontology.observations import (
    Deviation,
    ExpectedRange,
    Forecast,
    ForecastMiss,
    Observation,
)
from phos.ontology.store import EvidenceStore, InMemoryEvidenceStore

__all__ = [
    "DEVIATION_PREFIX",
    "ENTITY_PREFIX",
    "EVIDENCE_PREFIX",
    "FORECAST_PREFIX",
    "HYPOTHESIS_PREFIX",
    "NARRATIVE_PREFIX",
    "OBSERVATION_PREFIX",
    "Deviation",
    "DeviationId",
    "Domain",
    "Entity",
    "EntityId",
    "EntityType",
    "Evidence",
    "EvidenceId",
    "EvidenceKind",
    "EvidenceRole",
    "EvidenceStore",
    "ExpectedRange",
    "FacetKind",
    "Forecast",
    "ForecastId",
    "ForecastMiss",
    "Hypothesis",
    "HypothesisId",
    "HypothesisStatus",
    "InMemoryEvidenceStore",
    "Narrative",
    "NarrativeId",
    "Observation",
    "ObservationId",
    "UtcDatetime",
    "new_id",
    "utc_now",
]

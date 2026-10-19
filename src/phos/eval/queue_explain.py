"""Which innocent explanations one alert's shape supports (ADR 0231).

The probe weighs facts at weight 1. That asks which templates the shape
supports. It is not a calibrated confidence, and this module does not return one.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final

from phos.atlas.consistency_evidence import CROSS_SIGNAL_MISMATCH
from phos.atlas.grouping import SUBSYSTEM_EVENT_MARKER
from phos.atlas.templates import (
    ENGINEERING_MAINTENANCE_TEMPLATE_ID,
    PROCESS_DISTURBANCE_TEMPLATE_ID,
    SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID,
    atlas_library,
)
from phos.ontology import Domain, Evidence, EvidenceKind, FacetKind, InMemoryEvidenceStore
from phos.reasoning import ReasoningEngine
from phos.reasoning.templates import INSUFFICIENT_EVIDENCE_TEMPLATE_ID, TemplateLibrary

__all__ = ["INNOCENT", "Explanation", "explain_alert"]

INNOCENT: Final[frozenset[str]] = frozenset(
    {
        SENSOR_OR_DEVICE_FAULT_TEMPLATE_ID,
        ENGINEERING_MAINTENANCE_TEMPLATE_ID,
        PROCESS_DISTURBANCE_TEMPLATE_ID,
    }
)
"""The three explanations a ranker may treat as innocent. Not the attack, not the residual."""

_LIBRARY: Final[TemplateLibrary] = atlas_library()
_PROBE_TIME: Final = datetime(2026, 10, 1, tzinfo=UTC)


@dataclass(frozen=True)
class Explanation:
    """The lead template and the innocent templates the probe supports cleanly.

    Attributes:
        lead: The template at the front of the competing set. A tie raises the residual.
        strong_innocent: Innocent templates with support and no contradiction, sorted.
    """

    lead: str
    strong_innocent: tuple[str, ...]

    @property
    def has_strong_innocent(self) -> bool:
        """Whether any innocent template is supported and not contradicted."""
        return bool(self.strong_innocent)


def explain_alert(
    columns: tuple[str, ...],
    onset: str,
    *,
    witness: bool,
    work_order: bool,
) -> Explanation:
    """Return the explanation probe for one alert shape.

    Args:
        columns: Member signals, in any order. Stored sorted so the breadth fact is stable.
        onset: The signal the alert is placed on.
        witness: Whether to add a ``cross_signal_mismatch`` fact on ``onset``.
        work_order: Whether a sanctioning order covers this alert's timestamp.

    Returns:
        The lead and the strong innocent members. No confidence.

    Raises:
        ValueError: If ``columns`` is empty or ``onset`` is not one of them.
    """
    if not columns:
        raise ValueError("an alert with no member columns has no breadth to weigh")
    members = tuple(sorted(set(columns)))
    if onset not in members:
        raise ValueError(f"onset {onset!r} is not among the member columns")
    facts = [_breadth(members)]
    if witness:
        facts.append(_witness(onset))
    if work_order:
        facts.append(_work_order())
    engine = ReasoningEngine(_LIBRARY, InMemoryEvidenceStore())
    engine.ingest(facts)
    ranked = engine.competing(Domain.ATLAS)
    lead = ranked[0].template_id if ranked else INSUFFICIENT_EVIDENCE_TEMPLATE_ID
    strong = tuple(
        sorted(
            hypothesis.template_id
            for hypothesis in ranked
            if hypothesis.template_id in INNOCENT
            and hypothesis.supporting
            and not hypothesis.contradictory
        )
    )
    return Explanation(lead, strong)


def _breadth(members: tuple[str, ...]) -> Evidence:
    return Evidence(
        kind=EvidenceKind.DEVIATION,
        source_id=f"{SUBSYSTEM_EVENT_MARKER}queue-probe",
        entity_ids=list(members),
        timestamp=_PROBE_TIME,
        domain=Domain.ATLAS,
        weight=1.0,
        summary="queue probe breadth",
    )


def _witness(onset: str) -> Evidence:
    return Evidence(
        kind=EvidenceKind.DEVIATION,
        source_id="queue-probe-consistency",
        entity_ids=[onset],
        timestamp=_PROBE_TIME,
        domain=Domain.ATLAS,
        weight=1.0,
        summary="queue probe cross-signal mismatch",
        facet_kind=FacetKind.CONSISTENCY,
        facet=CROSS_SIGNAL_MISMATCH,
    )


def _work_order() -> Evidence:
    return Evidence(
        kind=EvidenceKind.RELATIONSHIP_CHANGE,
        source_id="work-order:queue-probe",
        entity_ids=["WO-probe", "unit"],
        timestamp=_PROBE_TIME,
        domain=Domain.ATLAS,
        weight=1.0,
        summary="work-order:work_order:sanctioned change for unit",
        facet_kind=FacetKind.WORK_ORDER,
        facet="work_order",
    )

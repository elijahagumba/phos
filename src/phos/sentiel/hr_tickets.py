"""Optional HR / change-ticket inlet for Sentiel (Session S5). Fixture only.

CERT has no such field. Real estate tickets arrive later. When the inlet is empty, Sentiel is
unchanged. Do not invent contradictions from logon hour. Facts go through 4A's relationship
door (ticket + person), same as Atlas work orders.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Final

from pydantic import BaseModel, ConfigDict

from phos.ontology import Evidence, Observation
from phos.reasoning import (
    FittedCalibrator,
    calibrated_probabilities,
    evidence_from_relationship_change,
)

__all__ = [
    "HR_TICKET_FEATURE",
    "HR_TICKET_MARKER",
    "HrTicketEvidence",
    "HrTicketFact",
    "hr_ticket_feature_of",
    "hr_ticket_marker",
    "promote_hr_tickets",
]

logger = logging.getLogger(__name__)

HR_TICKET_MARKER: Final = "hr-ticket:"
HR_TICKET_FEATURE: Final = "hr_ticket"


def hr_ticket_marker(feature: str = HR_TICKET_FEATURE) -> str:
    """Return the summary prefix that declares this evidence as an HR/change ticket."""
    return f"{HR_TICKET_MARKER}{feature}:"


def hr_ticket_feature_of(evidence: Evidence) -> str | None:
    """Return the stamped HR-ticket feature, or ``None``."""
    if not evidence.summary.startswith(HR_TICKET_MARKER):
        return None
    rest = evidence.summary[len(HR_TICKET_MARKER) :]
    feature, separator, _body = rest.partition(":")
    if not separator or not feature:
        return None
    return feature


class HrTicketFact(BaseModel):
    """One fixture HR / change ticket, traceable to an observation."""

    model_config = ConfigDict(frozen=True)

    observation: Observation
    evidence: Evidence


class HrTicketEvidence(BaseModel):
    """Optional inlet. Empty means Sentiel must not change."""

    model_config = ConfigDict(frozen=True)

    facts: tuple[HrTicketFact, ...] = ()

    def evidence(self) -> tuple[Evidence, ...]:
        """Return the facts in time order."""
        ordered = sorted(
            self.facts, key=lambda item: (item.evidence.timestamp, item.evidence.summary)
        )
        return tuple(item.evidence for item in ordered)


def promote_hr_tickets(
    findings: Sequence[Observation],
    calibrator: FittedCalibrator,
) -> list[HrTicketFact]:
    """Stamp HR-ticket observations as evidence. Empty input is a no-op."""
    if not findings:
        return []

    ordered = sorted(findings, key=lambda item: (item.timestamp, item.id))
    weights = calibrated_probabilities(calibrator, [finding.value for finding in ordered])
    promoted = [
        HrTicketFact(
            observation=finding,
            evidence=evidence_from_relationship_change(
                finding,
                weight,
                summary=f"{hr_ticket_marker(finding.feature)}sanctioned HR/change ticket",
            ),
        )
        for finding, weight in zip(ordered, weights, strict=True)
    ]
    logger.info("promoted %d HR-ticket fact(s) into evidence", len(promoted))
    return promoted

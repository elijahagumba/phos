"""Hypothesis-conditional forecasts: if H were true, what else should we see?

The ontology already has supporting/contradictory lists and Forecast/ForecastMiss. This
module only *names* expected consequences per template and attaches an existing evidence
atom when a forecast hits or misses. It does not invent CERT contradictions (ADR 0023).
It does not retune Atlas matchers.
"""

from __future__ import annotations

from typing import Final

from pydantic import BaseModel, ConfigDict

from phos.ontology import Evidence, Hypothesis
from phos.ontology.enums import EvidenceRole

__all__ = [
    "ExpectedConsequence",
    "attach_forecast_outcome",
    "consequences_for",
]


class ExpectedConsequence(BaseModel):
    """One observation a template predicts if it is the right explanation."""

    model_config = ConfigDict(frozen=True)

    template_id: str
    feature: str
    predicted_value: float
    summary: str


_MAINTENANCE: Final[tuple[ExpectedConsequence, ...]] = (
    ExpectedConsequence(
        template_id="engineering_maintenance",
        feature="issuer_is_engineering_station",
        predicted_value=1.0,
        summary="Maintenance predicts an engineering workstation on the path.",
    ),
    ExpectedConsequence(
        template_id="engineering_maintenance",
        feature="declared_maintenance_window",
        predicted_value=1.0,
        summary="Maintenance predicts a declared work window, when the plant publishes one.",
    ),
)

_UNAUTHORISED: Final[tuple[ExpectedConsequence, ...]] = (
    ExpectedConsequence(
        template_id="unauthorised_control_activity",
        feature="issuer_is_engineering_station",
        predicted_value=0.0,
        summary="Unauthorised control does not predict a known engineering issuer.",
    ),
    ExpectedConsequence(
        template_id="unauthorised_control_activity",
        feature="unknown_command_relationship",
        predicted_value=1.0,
        summary="Unauthorised control predicts an unexpected issuer or path.",
    ),
)

_SENSOR: Final[tuple[ExpectedConsequence, ...]] = (
    ExpectedConsequence(
        template_id="sensor_or_device_fault",
        feature="deviation_is_local",
        predicted_value=1.0,
        summary="A sensor or device fault predicts a localised deviation, not a plant-wide one.",
    ),
)

_PROCESS: Final[tuple[ExpectedConsequence, ...]] = (
    ExpectedConsequence(
        template_id="process_disturbance",
        feature="deviation_is_broad",
        predicted_value=1.0,
        summary="A process disturbance predicts a broad deviation without a new command path.",
    ),
)

_COMPROMISED: Final[tuple[ExpectedConsequence, ...]] = (
    ExpectedConsequence(
        template_id="compromised_account",
        feature="self_history_departs",
        predicted_value=1.0,
        summary="A compromised account predicts a departure from that person's own history.",
    ),
)

_BENIGN_ROLE: Final[tuple[ExpectedConsequence, ...]] = (
    ExpectedConsequence(
        template_id="benign_role_change",
        feature="declared_role_change",
        predicted_value=1.0,
        summary="A benign role change predicts a declared role attribute moving with the person.",
    ),
)

_LIBRARY: Final[dict[str, tuple[ExpectedConsequence, ...]]] = {
    "engineering_maintenance": _MAINTENANCE,
    "unauthorised_control_activity": _UNAUTHORISED,
    "sensor_or_device_fault": _SENSOR,
    "process_disturbance": _PROCESS,
    "compromised_account": _COMPROMISED,
    "benign_role_change": _BENIGN_ROLE,
}


def consequences_for(template_id: str) -> tuple[ExpectedConsequence, ...]:
    """Return the predicted observations for ``template_id``, or empty if none are authored."""
    return _LIBRARY.get(template_id, ())


def attach_forecast_outcome(
    hypothesis: Hypothesis,
    evidence: Evidence,
    *,
    observed_as_predicted: bool,
) -> Hypothesis:
    """Attach ``evidence`` as supporting (hit) or contradictory (miss). Confidence is unchanged.

    Hypothesis confidence stays uncalibrated. This function does not call ``with_confidence``.
    """
    role = EvidenceRole.SUPPORTING if observed_as_predicted else EvidenceRole.CONTRADICTORY
    return hypothesis.with_evidence(evidence.id, role)

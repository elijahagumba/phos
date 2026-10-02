"""Optional work-order / change-window inlet (Session E3).

A partner plant may later attach a sanctioned maintenance fact. Until then this module is a
fixture: when the inlet is empty, Atlas is byte-identical to commands-off. When a fact is
present, it is stamped ``work-order:`` so a template can read it without `Evidence` growing a
feature field.

Do not invent work orders from process clocks. Do not retune known-link matchers.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Final

from pydantic import BaseModel, ConfigDict

from phos.ontology import Evidence, FacetKind, Observation
from phos.reasoning import (
    FittedCalibrator,
    calibrated_probabilities,
    evidence_from_relationship_change,
)

__all__ = [
    "WORK_ORDER_FEATURE",
    "WORK_ORDER_MARKER",
    "WorkOrderEvidence",
    "WorkOrderFact",
    "promote_work_orders",
    "work_order_feature_of",
    "work_order_marker",
]

logger = logging.getLogger(__name__)

WORK_ORDER_MARKER: Final = "work-order:"
"""Declared prefix on a sanctioned-change fact. Session E3; same idiom as graph-finding stamps."""

WORK_ORDER_FEATURE: Final = "work_order"


def work_order_marker(feature: str = WORK_ORDER_FEATURE) -> str:
    """Return the summary prefix that declares this evidence as a work-order fact."""
    return f"{WORK_ORDER_MARKER}{feature}:"


def work_order_feature_of(evidence: Evidence) -> str | None:
    """Return which work-order feature this evidence declares, or ``None``.

    Typed facet first, summary marker only when no facet is set (ADR 0070). A work order is the
    one fact that contradicts unauthorised control, so which of the two a matcher sees must not
    depend on how a sentence happens to be worded.
    """
    if evidence.facet_kind is not None:
        if evidence.facet_kind is not FacetKind.WORK_ORDER:
            return None
        return evidence.facet
    return _work_order_from_summary(evidence)


def _work_order_from_summary(evidence: Evidence) -> str | None:
    """Recover a work-order feature from the declared marker. The pre-facet path."""
    if not evidence.summary.startswith(WORK_ORDER_MARKER):
        return None
    rest = evidence.summary[len(WORK_ORDER_MARKER) :]
    feature, separator, _body = rest.partition(":")
    if not separator or not feature:
        return None
    return feature


class WorkOrderFact(BaseModel):
    """One sanctioned change window, with the observation that makes it traceable."""

    model_config = ConfigDict(frozen=True)

    observation: Observation
    evidence: Evidence


class WorkOrderEvidence(BaseModel):
    """Optional inlet. Empty is the commands-off analogue: Atlas must not change."""

    model_config = ConfigDict(frozen=True)

    facts: tuple[WorkOrderFact, ...] = ()

    def evidence(self) -> tuple[Evidence, ...]:
        """Return the facts in time order."""
        ordered = sorted(
            self.facts, key=lambda item: (item.evidence.timestamp, item.evidence.summary)
        )
        return tuple(item.evidence for item in ordered)


def promote_work_orders(
    findings: Sequence[Observation],
    calibrator: FittedCalibrator,
) -> list[WorkOrderFact]:
    """Promote sanctioned-change observations into stamped `Evidence`.

    An empty ``findings`` list returns immediately so a caller who has no work orders is
    byte-identical to never calling this function.

    Args:
        findings: Observations naming at least two entities (the order/ticket and the unit).
        calibrator: Supplies each fact's calibrated weight.

    Returns:
        One `WorkOrderFact` per finding, earliest first.
    """
    if not findings:
        return []

    ordered = sorted(findings, key=lambda item: (item.timestamp, item.id))
    weights = calibrated_probabilities(calibrator, [finding.value for finding in ordered])
    promoted = [
        WorkOrderFact(
            observation=finding,
            evidence=evidence_from_relationship_change(
                finding,
                weight,
                summary=(
                    f"{work_order_marker(finding.feature)}sanctioned change for "
                    f"{finding.entity_ids[-1]}"
                ),
                facet=(FacetKind.WORK_ORDER, finding.feature),
            ),
        )
        for finding, weight in zip(ordered, weights, strict=True)
    ]
    logger.info("promoted %d work-order fact(s) into evidence", len(promoted))
    return promoted

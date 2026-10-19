"""Close a maintenance alert only when a work order is cited (A5 / W4, ADR 0150).

`phos.atlas.cmms` already reads a SAP PM or Maximo export, and `covering_order` already
answers "does any sanctioning window cover this asset at this time?". That answer is not a
closure. An attacker who is merely inside a window, including a `MIMIC` that copies the shape
of a maintenance move, would be cleared by overlap alone. ADR 0069 names that limit: a covering
order is not innocence.

This module applies a stricter rule. The plant's own job log may stamp an order id and a feature
onto an alert. That stamp is a claim, not a verdict. The alert closes only when exactly one
loaded sanctioning order matches the stamp, names the alert's feature, and covers the alert's
asset at the alert's time. The closure cites that order. It does not change a detection score,
a template prior, or a known-link matcher, and it does not carry a confidence.

`close_on_overlap` is the simple rival used by the harness. It is not the product rule.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from phos.atlas.cmms import WorkOrderRecord, covering_order
from phos.ontology.ids import UtcDatetime

__all__ = [
    "OVERLAP_IS_NOT_CLOSURE",
    "AlertClosure",
    "JobCitation",
    "OpenAlert",
    "close_maintenance_alerts",
    "close_on_overlap",
]

logger = logging.getLogger(__name__)

OVERLAP_IS_NOT_CLOSURE: Final = (
    "A sanctioning work order that covers an alert's asset and time does not close the alert. "
    "Closure requires exactly one historian citation that names that order and the alert's "
    "feature, and the loaded export must show the order sanctioning that asset at that time. "
    "An attack shaped like maintenance, including MIMIC, carries no citation and stays open. "
    "The closure cites the order. It does not change a detection score, a template prior, or a "
    "known-link matcher, and it does not carry a confidence."
)
"""The A5 rule. Overlap is the rival, not the closure."""

ClosureReason = Literal[
    "cited",
    "overlap",
    "no_citation",
    "unknown_order",
    "not_covering",
    "feature_mismatch",
    "ambiguous",
]
"""Why a closure decided what it decided. ``overlap`` is only emitted by the rival."""

_CLOSED_REASONS: Final = frozenset({"cited", "overlap"})


class JobCitation(BaseModel):
    """One historian stamp: which order the job log claims, and on which feature.

    Attributes:
        order_id: The work-order number as the maintenance system spells it.
        feature: The signal the job log says that order worked on.
    """

    model_config = ConfigDict(frozen=True)

    order_id: str = Field(min_length=1)
    feature: str = Field(min_length=1)


class OpenAlert(BaseModel):
    """One alert still open. The closer does not receive a cause label.

    Attributes:
        alert_id: Stable id, unique within a run.
        asset_id: The plant unit the alert is about. Matched exactly.
        feature: The signal the alert is about.
        timestamp: When the alert fired, UTC.
        citations: Historian stamps attached to this alert. Empty when the job log cited nothing.
    """

    model_config = ConfigDict(frozen=True)

    alert_id: str = Field(min_length=1)
    asset_id: str = Field(min_length=1)
    feature: str = Field(min_length=1)
    timestamp: UtcDatetime
    citations: tuple[JobCitation, ...] = ()


class AlertClosure(BaseModel):
    """The decision for one alert, with the order it cites when it closes.

    Attributes:
        alert_id: The alert this decision is about.
        closed: Whether the alert resolved.
        order_id: The cited order, present only when ``closed`` is true.
        citation: ``{schema}:{order_id}`` from the loaded export, present only when closed.
        reason: Which clause of the rule decided it.

    Invariants:
        A closed alert has an order id, a citation, and a closed reason. An open alert has none.
    """

    model_config = ConfigDict(frozen=True)

    alert_id: str = Field(min_length=1)
    closed: bool
    order_id: str | None
    citation: str | None
    reason: ClosureReason

    @model_validator(mode="after")
    def _citation_matches_the_decision(self) -> AlertClosure:
        if self.closed:
            if self.reason not in _CLOSED_REASONS:
                raise ValueError(
                    f"alert {self.alert_id!r} closed with reason {self.reason!r}; a closed "
                    "alert's reason is 'cited' or, for the overlap rival, 'overlap'"
                )
            if not self.order_id or not self.citation:
                raise ValueError(f"alert {self.alert_id!r} closed without an order citation")
            return self
        if self.reason in _CLOSED_REASONS or self.order_id is not None or self.citation is not None:
            raise ValueError(
                f"alert {self.alert_id!r} stayed open but still carries a citation "
                "or a closed reason"
            )
        return self


def _index(records: Sequence[WorkOrderRecord]) -> dict[str, WorkOrderRecord]:
    """Index sanctioning orders by id. A repeated id is a broken export, not a tie to break."""
    by_id: dict[str, WorkOrderRecord] = {}
    for record in records:
        if record.order_id in by_id:
            raise ValueError(
                f"work order {record.order_id!r} appears twice in the loaded export; "
                "refusing to pick one"
            )
        by_id[record.order_id] = record
    return by_id


def _cite(record: WorkOrderRecord) -> str:
    """Return the citation string stored on a closure."""
    return f"{record.schema_name}:{record.order_id}"


def _open(alert_id: str, reason: ClosureReason) -> AlertClosure:
    """An alert that stays open, with no order attached."""
    return AlertClosure(
        alert_id=alert_id,
        closed=False,
        order_id=None,
        citation=None,
        reason=reason,
    )


def _closed(alert_id: str, record: WorkOrderRecord, reason: ClosureReason) -> AlertClosure:
    """An alert that closes, citing ``record``."""
    return AlertClosure(
        alert_id=alert_id,
        closed=True,
        order_id=record.order_id,
        citation=_cite(record),
        reason=reason,
    )


def close_maintenance_alerts(
    alerts: Sequence[OpenAlert],
    records: Sequence[WorkOrderRecord],
) -> tuple[AlertClosure, ...]:
    """Close each alert that has exactly one resolving historian citation.

    A citation resolves when its feature is the alert's feature, its order id is in
    ``records``, and that order covers the alert's asset at the alert's time. ``records``
    are the sanctioning rows `load_work_order_export` kept. An order the loader dropped,
    including a draft or a cancellation, cannot resolve.

    Two resolving orders leave the alert open (``ambiguous``). No citation leaves it open,
    including when some other order covers the same asset and time.

    Args:
        alerts: Alerts in the order the caller wants the decisions back.
        records: Sanctioning work orders from a loaded export.

    Returns:
        One closure per alert, in the same order. A closure's ``citation`` is the order a
        reader would look up in the export.

    Raises:
        ValueError: If two records share an order id.
    """
    by_id = _index(records)
    decisions = tuple(_decide(alert, by_id) for alert in alerts)
    closed = sum(1 for decision in decisions if decision.closed)
    logger.info(
        "maintenance closure: %d of %d alert(s) closed with a cited work order",
        closed,
        len(decisions),
    )
    return decisions


def _decide(alert: OpenAlert, by_id: Mapping[str, WorkOrderRecord]) -> AlertClosure:
    """Apply the citation rule to one alert."""
    if not alert.citations:
        return _open(alert.alert_id, "no_citation")

    matched: list[WorkOrderRecord] = []
    seen: set[str] = set()
    saw_unknown = False
    saw_not_covering = False
    saw_feature_mismatch = False
    for citation in alert.citations:
        if citation.feature != alert.feature:
            saw_feature_mismatch = True
            continue
        record = by_id.get(citation.order_id)
        if record is None:
            saw_unknown = True
            continue
        if not record.covers(alert.timestamp, alert.asset_id):
            saw_not_covering = True
            continue
        if record.order_id not in seen:
            seen.add(record.order_id)
            matched.append(record)

    if len(matched) == 1:
        return _closed(alert.alert_id, matched[0], "cited")
    if len(matched) > 1:
        return _open(alert.alert_id, "ambiguous")
    if saw_not_covering:
        return _open(alert.alert_id, "not_covering")
    if saw_unknown:
        return _open(alert.alert_id, "unknown_order")
    if saw_feature_mismatch:
        return _open(alert.alert_id, "feature_mismatch")
    return _open(alert.alert_id, "no_citation")


def close_on_overlap(
    alerts: Sequence[OpenAlert],
    records: Sequence[WorkOrderRecord],
) -> tuple[AlertClosure, ...]:
    """Close an alert whenever any sanctioning order covers its asset and time.

    This is the simple rival the harness scores against. It ignores historian citations, so a
    `MIMIC` alert sitting inside a real maintenance window closes. That is the failure the
    product rule exists to avoid. Do not call it from the engine.

    Args:
        alerts: Alerts in the order the caller wants the decisions back.
        records: Sanctioning work orders from a loaded export.

    Returns:
        One closure per alert. A closed rival decision has reason ``overlap``.
    """
    decisions: list[AlertClosure] = []
    for alert in alerts:
        order = covering_order(records, alert.timestamp, (alert.asset_id,))
        if order is None:
            decisions.append(_open(alert.alert_id, "not_covering"))
        else:
            decisions.append(_closed(alert.alert_id, order, "overlap"))
    logger.info(
        "overlap rival: %d of %d alert(s) closed without a historian citation check",
        sum(1 for decision in decisions if decision.closed),
        len(decisions),
    )
    return tuple(decisions)

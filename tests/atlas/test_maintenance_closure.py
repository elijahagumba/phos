"""A maintenance alert closes only with a cited sanctioning work order.

Overlap in time is the rival, not the rule. A MIMIC-shaped alert inside a real window stays
open when the job log did not cite an order. A forged citation is a separate, documented limit.
"""

from datetime import UTC, datetime, timedelta

import pytest

from phos.atlas.cmms import WorkOrderRecord
from phos.atlas.maintenance_closure import (
    AlertClosure,
    JobCitation,
    OpenAlert,
    close_maintenance_alerts,
    close_on_overlap,
)

NOON = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


def _record(
    order_id: str,
    asset: str,
    start: datetime,
    end: datetime | None = None,
) -> WorkOrderRecord:
    """One sanctioning export row. The loader would have dropped anything else."""
    return WorkOrderRecord(
        order_id=order_id,
        asset_id=asset,
        start=start,
        end=NOON + timedelta(hours=4) if end is None else end,
        status="REL",
        schema_name="sap-pm",
    )


def _alert(
    alert_id: str,
    asset: str = "P-101",
    feature: str = "flow",
    when: datetime = NOON,
    citations: tuple[JobCitation, ...] = (),
) -> OpenAlert:
    """One open alert. Citations default to empty, which is what an attack carries."""
    return OpenAlert(
        alert_id=alert_id,
        asset_id=asset,
        feature=feature,
        timestamp=when,
        citations=citations,
    )


def _by_id(decisions: tuple[AlertClosure, ...]) -> dict[str, AlertClosure]:
    return {decision.alert_id: decision for decision in decisions}


def test_a_resolving_citation_closes_and_names_the_order() -> None:
    """The job log cited WO-1 for flow, and the export sanctions that window."""
    records = (_record("WO-1", "P-101", NOON),)
    alert = _alert("a", citations=(JobCitation(order_id="WO-1", feature="flow"),))
    decision = close_maintenance_alerts([alert], records)[0]
    assert decision.closed
    assert decision.reason == "cited"
    assert decision.order_id == "WO-1"
    assert decision.citation == "sap-pm:WO-1"


def test_mimic_inside_the_window_without_a_citation_stays_open() -> None:
    """Same asset, same feature, same instant as a real job. No stamp, so no closure."""
    records = (_record("WO-1", "P-101", NOON),)
    mimic = _alert("mimic")
    job = _alert("job", citations=(JobCitation(order_id="WO-1", feature="flow"),))
    decisions = _by_id(close_maintenance_alerts([mimic, job], records))
    assert decisions["mimic"].closed is False
    assert decisions["mimic"].reason == "no_citation"
    assert decisions["mimic"].order_id is None
    assert decisions["job"].closed is True


def test_overlap_rival_closes_the_uncited_mimic() -> None:
    """The rival is scored so the margin is the attacks it clears and the product rule does not."""
    records = (_record("WO-1", "P-101", NOON),)
    mimic = _alert("mimic")
    decision = close_on_overlap([mimic], records)[0]
    assert decision.closed
    assert decision.reason == "overlap"
    assert decision.order_id == "WO-1"
    product = close_maintenance_alerts([mimic], records)[0]
    assert product.closed is False


def test_a_dropped_order_id_does_not_resolve() -> None:
    """Drafts and cancellations never reach ``records``. Citing one stays open."""
    records = (_record("WO-1", "P-101", NOON),)
    alert = _alert("draft", citations=(JobCitation(order_id="WO-CANCELLED", feature="flow"),))
    decision = close_maintenance_alerts([alert], records)[0]
    assert decision.closed is False
    assert decision.reason == "unknown_order"


def test_asset_identity_is_exact() -> None:
    """P-101 does not cover P-1010, even when the citation names P-101's order."""
    records = (_record("WO-1", "P-101", NOON),)
    alert = _alert(
        "neighbour",
        asset="P-1010",
        citations=(JobCitation(order_id="WO-1", feature="flow"),),
    )
    decision = close_maintenance_alerts([alert], records)[0]
    assert decision.closed is False
    assert decision.reason == "not_covering"


def test_a_citation_outside_the_window_does_not_close() -> None:
    records = (_record("WO-1", "P-101", NOON),)
    later = NOON + timedelta(hours=5)
    alert = _alert(
        "late",
        when=later,
        citations=(JobCitation(order_id="WO-1", feature="flow"),),
    )
    decision = close_maintenance_alerts([alert], records)[0]
    assert decision.reason == "not_covering"
    assert decision.closed is False


def test_a_citation_for_a_different_feature_does_not_close() -> None:
    records = (_record("WO-1", "P-101", NOON),)
    alert = _alert(
        "speed", feature="speed", citations=(JobCitation(order_id="WO-1", feature="flow"),)
    )
    decision = close_maintenance_alerts([alert], records)[0]
    assert decision.reason == "feature_mismatch"
    assert decision.closed is False


def test_two_resolving_orders_leave_the_alert_open() -> None:
    records = (
        _record("WO-1", "P-101", NOON),
        _record("WO-2", "P-101", NOON),
    )
    alert = _alert(
        "both",
        citations=(
            JobCitation(order_id="WO-1", feature="flow"),
            JobCitation(order_id="WO-2", feature="flow"),
        ),
    )
    decision = close_maintenance_alerts([alert], records)[0]
    assert decision.closed is False
    assert decision.reason == "ambiguous"
    assert decision.citation is None


def test_citing_the_same_order_twice_is_one_closure() -> None:
    records = (_record("WO-1", "P-101", NOON),)
    alert = _alert(
        "twice",
        citations=(
            JobCitation(order_id="WO-1", feature="flow"),
            JobCitation(order_id="WO-1", feature="flow"),
        ),
    )
    decision = close_maintenance_alerts([alert], records)[0]
    assert decision.closed
    assert decision.order_id == "WO-1"


def test_a_forged_citation_on_an_attack_shaped_alert_closes() -> None:
    """The closer checks the stamp against the export. It does not know the stamp was forged.

    The harness never puts a real order id on an attack. This test records the limit ADR 0069
    already names: a forged citation is a forged citation.
    """
    records = (_record("WO-1", "P-101", NOON),)
    forged = _alert("forged", citations=(JobCitation(order_id="WO-1", feature="flow"),))
    decision = close_maintenance_alerts([forged], records)[0]
    assert decision.closed
    assert decision.citation == "sap-pm:WO-1"


def test_duplicate_order_ids_in_the_export_are_refused() -> None:
    records = (
        _record("WO-1", "P-101", NOON),
        _record("WO-1", "P-102", NOON),
    )
    with pytest.raises(ValueError, match="appears twice"):
        close_maintenance_alerts([_alert("a")], records)


def test_empty_input_returns_nothing() -> None:
    assert close_maintenance_alerts([], ()) == ()
    assert close_on_overlap([], ()) == ()


def test_decisions_keep_the_caller_order() -> None:
    records = (_record("WO-1", "P-101", NOON),)
    alerts = [
        _alert("second"),
        _alert("first", citations=(JobCitation(order_id="WO-1", feature="flow"),)),
    ]
    decisions = close_maintenance_alerts(alerts, records)
    assert [decision.alert_id for decision in decisions] == ["second", "first"]

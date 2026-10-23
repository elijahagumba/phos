"""ADR 0304: packing same-incident alerts puts more incidents inside eight slots."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from phos.atlas.consistency import ALERTS_PER_SHIFT
from phos.atlas.consistency_windows import EVENT_WINDOW
from phos.atlas.incident_pack import IncidentAlert, incidents_inside_budget, pack_incidents

WHEN = datetime(2026, 10, 22, 8, 0, tzinfo=UTC)


def _alert(incident: str, minute: int, score: float, key: str) -> IncidentAlert:
    return IncidentAlert(incident, WHEN + timedelta(minutes=minute), score, key)


def _battery() -> tuple[IncidentAlert, ...]:
    """Three loud incidents of three alerts, then two quieter single alerts."""
    rows: list[IncidentAlert] = []
    specs = (
        ("A", (30, 29, 28)),
        ("B", (20, 19, 18)),
        ("C", (10, 9, 8)),
        ("D", (7,)),
        ("E", (6,)),
    )
    minute = 0
    for incident, scores in specs:
        for offset, score in enumerate(scores):
            rows.append(_alert(incident, minute + offset, float(score), f"{incident}{offset}"))
        minute += 10
    return tuple(rows)


def test_packing_halves_the_incidents_the_budget_missed() -> None:
    alerts = _battery()
    unpacked = incidents_inside_budget(alerts, packed=False)
    packed = incidents_inside_budget(alerts, packed=True)
    missed_before = 5 - len(unpacked)
    missed_after = 5 - len(packed)
    assert len(unpacked) == 3
    assert missed_before == 2
    assert missed_after <= missed_before // 2
    assert len(packed) == 5
    assert len(packed) <= ALERTS_PER_SHIFT
    assert len(unpacked) <= ALERTS_PER_SHIFT


def test_the_representative_is_not_later_than_the_first_member() -> None:
    alerts = _battery()
    for incident in pack_incidents(alerts):
        members = [item for item in alerts if item.key in incident.member_keys]
        assert incident.at == min(item.at for item in members)
        assert incident.score == max(item.score for item in members)


def test_different_incidents_one_second_apart_stay_apart() -> None:
    alerts = (
        IncidentAlert("A", WHEN, 5.0, "a"),
        IncidentAlert("B", WHEN + timedelta(seconds=1), 4.0, "b"),
    )
    packed = pack_incidents(alerts)
    assert [item.incident_id for item in packed] == ["A", "B"]


def test_the_same_incident_outside_the_window_splits() -> None:
    late = WHEN + timedelta(seconds=EVENT_WINDOW + 1)
    alerts = (
        IncidentAlert("A", WHEN, 5.0, "early"),
        IncidentAlert("A", late, 9.0, "late"),
    )
    packed = pack_incidents(alerts)
    assert len(packed) == 2
    assert [item.key for item in packed] == ["early", "late"]


def test_an_empty_list_stays_empty() -> None:
    assert pack_incidents(()) == ()
    assert incidents_inside_budget((), packed=True) == ()


def test_pack_does_not_call_group_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    import phos.atlas.grouping as grouping
    import phos.atlas.incident_pack as incident_pack

    def trap(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("group_evidence was called")

    monkeypatch.setattr(grouping, "group_evidence", trap)
    assert not hasattr(incident_pack, "group_evidence")
    pack_incidents(_battery())

"""ADR 0312: a booking that names both tags withdraws the handoff and picks nothing."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from phos.atlas.consistency_windows import EVENT_WINDOW
from phos.atlas.handoff_booking import HANDOFF_NEXT, TagBooking, handoff_notices
from phos.atlas.joint_setpoint import SetpointStep, joint_moves
from phos.atlas.program_transfer import GO_AND_LOOK
from phos.atlas.templates import (
    ENGINEERING_MAINTENANCE_TEMPLATE_ID,
    UNAUTHORISED_CONTROL_TEMPLATE_ID,
)
from phos.reasoning import INSUFFICIENT_EVIDENCE_TEMPLATE_ID

WHEN = datetime(2026, 10, 22, 16, 0, tzinfo=UTC)


def _steps() -> tuple[SetpointStep, SetpointStep]:
    return (
        SetpointStep("tank_level_max", WHEN, 7.0),
        SetpointStep("bottle_level_max", WHEN + timedelta(seconds=EVENT_WINDOW + 1), 7.0),
    )


def _booking(
    tags: tuple[str, str] = ("bottle_level_max", "tank_level_max"),
    *,
    start: datetime | None = None,
    end: datetime | None = None,
) -> TagBooking:
    return TagBooking(tags, start or WHEN - timedelta(minutes=5), end or WHEN + timedelta(hours=1))


def test_an_unbooked_handoff_says_go_and_look_and_names_the_booking() -> None:
    found = handoff_notices(_steps())
    assert len(found) == 1
    notice = found[0]
    assert notice.alert is True
    assert notice.instruction == GO_AND_LOOK
    assert notice.next_observation == HANDOFF_NEXT
    assert notice.lead is None
    assert notice.stories == (
        ENGINEERING_MAINTENANCE_TEMPLATE_ID,
        UNAUTHORISED_CONTROL_TEMPLATE_ID,
    )
    assert set(notice.tied_lead_ids) == set(notice.stories)
    assert INSUFFICIENT_EVIDENCE_TEMPLATE_ID in {item.template_id for item in notice.hypotheses}
    assert "confidence" not in notice.__dict__


def test_a_booking_that_names_both_tags_clears_the_alert_and_keeps_the_tie() -> None:
    found = handoff_notices(_steps(), (_booking(),))
    assert len(found) == 1
    notice = found[0]
    assert notice.alert is False
    assert notice.instruction is None
    assert notice.next_observation is None
    assert notice.lead is None
    assert notice.tied_lead_ids


def test_one_tag_or_the_wrong_hour_does_not_cover() -> None:
    wrong_tag = _booking(("tank_level_max", "flow_max"))
    too_early = _booking(end=WHEN - timedelta(seconds=1))
    assert handoff_notices(_steps(), (wrong_tag,))[0].alert is True
    assert handoff_notices(_steps(), (too_early,))[0].alert is True


def test_a_joint_inside_the_window_is_not_withdrawn_by_a_handoff_booking() -> None:
    steps = (
        SetpointStep("tank_level_max", WHEN, 7.0),
        SetpointStep("bottle_level_max", WHEN + timedelta(seconds=10), 7.1),
    )
    assert handoff_notices(steps, (_booking(),)) == ()
    assert len(joint_moves(steps)) == 1


def test_an_empty_inlet_stays_empty_and_a_bad_booking_raises() -> None:
    assert handoff_notices(()) == ()
    with pytest.raises(ValueError, match="two different tags"):
        handoff_notices(_steps(), (TagBooking(("tank_level_max", "tank_level_max"), WHEN, WHEN),))
    naive = TagBooking(("a", "b"), datetime(2026, 10, 22, 16, 0), WHEN)
    with pytest.raises(ValueError, match="timezone-aware"):
        handoff_notices(_steps(), (naive,))
    backwards = TagBooking(("a", "b"), WHEN, WHEN - timedelta(seconds=1))
    with pytest.raises(ValueError, match="ends before"):
        handoff_notices(_steps(), (backwards,))

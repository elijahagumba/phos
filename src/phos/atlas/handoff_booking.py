"""A booking that names both tags withdraws a handoff, and does not pick a story.

The handoff stays an alert while no supplied booking names those two tags and covers
its hour. The instruction is ``Go and look.`` The next observation names the booking.
Both stories stay tied, and the lead stays empty. A missing booking is not a verdict
of attack. Hypothesis confidence exists only so the tie rule can see two equal
stories. It is not a field of the notice.

This is a fixture. It does not edit the frozen detector, and it does not read a
Modbus function code.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from phos.atlas.band_handoff import BandHandoff, band_handoffs
from phos.atlas.joint_setpoint import SetpointStep
from phos.atlas.program_transfer import GO_AND_LOOK
from phos.atlas.templates import (
    ENGINEERING_MAINTENANCE_TEMPLATE_ID,
    UNAUTHORISED_CONTROL_TEMPLATE_ID,
)
from phos.ontology import Domain, Hypothesis, HypothesisStatus
from phos.reasoning import INSUFFICIENT_EVIDENCE_TEMPLATE_ID, tied_lead_ids

__all__ = [
    "HANDOFF_NEXT",
    "HandoffNotice",
    "TagBooking",
    "handoff_notices",
]

logger = logging.getLogger(__name__)

HANDOFF_NEXT: Final = "A booking that names both tags and covers this hour."
"""The one fact that would withdraw the handoff. It does not pick a story."""

_STORIES: Final = (
    ENGINEERING_MAINTENANCE_TEMPLATE_ID,
    UNAUTHORISED_CONTROL_TEMPLATE_ID,
)
_TIED_CONFIDENCE: Final = 0.5
"""Equal on both stories so `tied_lead_ids` is non-empty. Not a reported confidence."""


@dataclass(frozen=True)
class TagBooking:
    """A booking the caller already holds for two setpoint tags.

    Attributes:
        tags: The two tags, in either order. They must differ.
        start: Inclusive start. Timezone-aware.
        end: Inclusive end. Timezone-aware.
    """

    tags: tuple[str, str]
    start: datetime
    end: datetime


@dataclass(frozen=True)
class HandoffNotice:
    """One handoff, and whether a supplied booking has withdrawn it.

    Attributes:
        at: The earlier write.
        tags: The two tags, sorted.
        value: The shared in-band value.
        stories: Maintenance and unauthorised control, both present.
        tied_lead_ids: The same two ids. Non-empty, so neither is a unique lead.
        hypotheses: The competing set, including insufficient evidence. Confidence on
            these objects is the tie's input. It is not a field of this notice.
        lead: Always ``None``. The tie is the refusal to pick.
        alert: True when no supplied booking covers both tags at ``at``.
        instruction: ``Go and look.`` when ``alert`` is true, otherwise ``None``.
        next_observation: The booking that would withdraw the alert, or ``None`` when
            a covering booking is already supplied. Not a confidence.
    """

    at: datetime
    tags: tuple[str, str]
    value: float
    stories: tuple[str, str]
    tied_lead_ids: tuple[str, ...]
    hypotheses: tuple[Hypothesis, ...]
    lead: None
    alert: bool
    instruction: str | None
    next_observation: str | None


def handoff_notices(
    steps: Sequence[SetpointStep],
    bookings: Sequence[TagBooking] = (),
) -> tuple[HandoffNotice, ...]:
    """Attach the caller's bookings to each handoff.

    Args:
        steps: Setpoint writes the caller supplied. Empty stays empty.
        bookings: Covering records already in hand. An empty sequence stays empty.

    Returns:
        One notice per handoff, earliest first. A covering booking clears the alert
        and leaves the tie in place.

    Raises:
        ValueError: If a booking does not name two different tags, or its interval
            is naive or runs backwards.
    """
    for booking in bookings:
        _require_booking(booking)
    notices: list[HandoffNotice] = []
    for handoff in band_handoffs(steps):
        covered = any(_covers(booking, handoff) for booking in bookings)
        hypotheses = _competing(handoff.at)
        tie = tied_lead_ids(hypotheses)
        alert = not covered
        notices.append(
            HandoffNotice(
                at=handoff.at,
                tags=handoff.tags,
                value=handoff.value,
                stories=_STORIES,
                tied_lead_ids=tie,
                hypotheses=hypotheses,
                lead=None,
                alert=alert,
                instruction=GO_AND_LOOK if alert else None,
                next_observation=HANDOFF_NEXT if alert else None,
            )
        )
    withdrawn = len(notices) - sum(item.alert for item in notices)
    logger.info("handoff notices %s withdrawn %s", len(notices), withdrawn)
    return tuple(notices)


def _covers(booking: TagBooking, handoff: BandHandoff) -> bool:
    """Return whether ``booking`` names both tags and contains the earlier write."""
    return set(booking.tags) == set(handoff.tags) and booking.start <= handoff.at <= booking.end


def _require_booking(booking: TagBooking) -> None:
    """Raise when a booking cannot be a cover for two tags."""
    _require_aware(booking.start, "booking start")
    _require_aware(booking.end, "booking end")
    if booking.end < booking.start:
        raise ValueError("booking ends before it starts")
    left, right = booking.tags
    if not left or not right or left == right:
        raise ValueError("tag booking names two different tags")


def _competing(at: datetime) -> tuple[Hypothesis, ...]:
    """Both stories at the same confidence, plus insufficient evidence.

    The confidence is equal so the tie rule keeps both. It is not returned on the notice.
    """
    return tuple(
        Hypothesis(
            label=template_id,
            template_id=template_id,
            domain=Domain.ATLAS,
            prior=_TIED_CONFIDENCE,
            confidence=_TIED_CONFIDENCE,
            status=HypothesisStatus.ACTIVE,
            created_at=at,
            updated_at=at,
        )
        for template_id in (*_STORIES, INSUFFICIENT_EVIDENCE_TEMPLATE_ID)
    )


def _require_aware(moment: datetime, name: str) -> None:
    """Raise when ``moment`` has no timezone."""
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")

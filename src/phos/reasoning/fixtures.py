"""Small labelled reasoning incidents for Clock B.

Library personas are not CERT (ADR 0029). These fixtures exist so top-1 / top-2 /
abstention-when-correct can be scored without pretending the synthetic library is a
public corpus. Hypothesis confidence stays uncalibrated.
"""

from __future__ import annotations

from typing import Final

from pydantic import BaseModel, ConfigDict

__all__ = [
    "REASONING_FIXTURES",
    "FixtureScorecard",
    "ReasoningFixture",
    "ranking_outcome",
    "score_fixtures",
]


class ReasoningFixture(BaseModel):
    """One hand-labelled incident with a known correct template id."""

    model_config = ConfigDict(frozen=True)

    incident_id: str
    correct_template_id: str
    ranked_template_ids: tuple[str, ...]
    abstain: bool = False


REASONING_FIXTURES: Final[tuple[ReasoningFixture, ...]] = (
    ReasoningFixture(
        incident_id="fixture-unknown-master-write",
        correct_template_id="unauthorised_control_activity",
        ranked_template_ids=(
            "unauthorised_control_activity",
            "engineering_maintenance",
            "insufficient_evidence",
        ),
    ),
    ReasoningFixture(
        incident_id="fixture-known-station-tie",
        correct_template_id="insufficient_evidence",
        ranked_template_ids=(
            "insufficient_evidence",
            "unauthorised_control_activity",
            "engineering_maintenance",
        ),
        abstain=True,
    ),
    ReasoningFixture(
        incident_id="fixture-local-sensor-fault",
        correct_template_id="sensor_or_device_fault",
        ranked_template_ids=(
            "sensor_or_device_fault",
            "process_disturbance",
            "insufficient_evidence",
        ),
    ),
    ReasoningFixture(
        incident_id="fixture-process-disturbance",
        correct_template_id="process_disturbance",
        ranked_template_ids=(
            "process_disturbance",
            "unauthorised_control_activity",
            "insufficient_evidence",
        ),
    ),
)


def ranking_outcome(fixture: ReasoningFixture) -> str:
    """Return ``top-1``, ``top-2``, ``abstention-when-correct``, or ``miss``.

    A fixture that marks ``abstain`` is correct only when the residual leads. That is
    not a CERT score.
    """
    if fixture.abstain:
        leads = fixture.ranked_template_ids[0] if fixture.ranked_template_ids else ""
        return "abstention-when-correct" if leads == "insufficient_evidence" else "miss"
    ranked = fixture.ranked_template_ids
    if not ranked:
        return "miss"
    if ranked[0] == fixture.correct_template_id:
        return "top-1"
    if fixture.correct_template_id in ranked[:2]:
        return "top-2"
    return "miss"


class FixtureScorecard(BaseModel):
    """Aggregate ranking outcomes on library fixtures. Not a CERT row (ADR 0029)."""

    model_config = ConfigDict(frozen=True)

    n: int
    top_1: int
    top_2: int
    abstention_when_correct: int
    miss: int
    is_cert_row: bool = False


def score_fixtures(
    fixtures: tuple[ReasoningFixture, ...] = REASONING_FIXTURES,
) -> FixtureScorecard:
    """Count top-1 / top-2 / correct abstention / miss. Library personas are not CERT."""
    counts = {"top-1": 0, "top-2": 0, "abstention-when-correct": 0, "miss": 0}
    for fixture in fixtures:
        counts[ranking_outcome(fixture)] += 1
    return FixtureScorecard(
        n=len(fixtures),
        top_1=counts["top-1"],
        top_2=counts["top-2"],
        abstention_when_correct=counts["abstention-when-correct"],
        miss=counts["miss"],
        is_cert_row=False,
    )

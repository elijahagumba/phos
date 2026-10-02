"""Detection-adversary catalogue for Clock B.

This is a **specification**, not a detection result. Hostile configs 04-07 remain
software-survival (ADR 0017 / 0041). Nothing here overwrites a breaking detection report.
"""

from __future__ import annotations

from typing import Final

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "DETECTION_ADVERSARY_SCENARIOS",
    "AdversaryScenario",
    "adversary_catalogue",
    "render_adversary_markdown",
]


class AdversaryScenario(BaseModel):
    """One named way the engines can be fooled. Spec only until a separate report exists."""

    model_config = ConfigDict(frozen=True)

    scenario_id: str
    engine: str
    summary: str
    report_kind: str = Field(default="spec")
    is_detection_claim: bool = False


DETECTION_ADVERSARY_SCENARIOS: Final[tuple[AdversaryScenario, ...]] = (
    AdversaryScenario(
        scenario_id="gradual-drift",
        engine="atlas",
        summary="Slow process drift that stays inside a joint ellipsoid learned on the old regime.",
    ),
    AdversaryScenario(
        scenario_id="maintenance-mimicry",
        engine="atlas",
        summary="Unauthorised writes on a known station that look like engineering maintenance.",
    ),
    AdversaryScenario(
        scenario_id="slow-command",
        engine="atlas",
        summary="Command-rate change stretched below the live occupancy window.",
    ),
    AdversaryScenario(
        scenario_id="sensor-dropout",
        engine="atlas",
        summary="Missing instruments that look like NO_OBSERVATION rather than a deviation.",
    ),
    AdversaryScenario(
        scenario_id="correlated-manipulation",
        engine="atlas",
        summary="Coordinated sensor writes that stay on the learned manifold.",
    ),
    AdversaryScenario(
        scenario_id="low-and-slow-identity",
        engine="sentiel",
        summary="Compromised account that stays inside the user's own history until one sequence.",
    ),
    AdversaryScenario(
        scenario_id="legitimate-role-transition",
        engine="sentiel",
        summary="Declared role change: self-history departs, role-history does not.",
    ),
    AdversaryScenario(
        scenario_id="cold-start",
        engine="sentiel",
        summary="New employee with no self baseline; identity layers must not invent a peer win.",
    ),
    AdversaryScenario(
        scenario_id="seasonal-load",
        engine="sentiel",
        summary="Calendar-normal volume that a pooled org baseline calls unusual.",
    ),
    AdversaryScenario(
        scenario_id="shared-account",
        engine="sentiel",
        summary="One directory identity used by several people; self-history is not a person.",
    ),
)


def adversary_catalogue() -> tuple[AdversaryScenario, ...]:
    """Return the frozen spec catalogue. Not a detection scoreboard."""
    return DETECTION_ADVERSARY_SCENARIOS


def render_adversary_markdown() -> str:
    """Render the spec catalogue as a report that must live beside detection logs."""
    lines = [
        "# Detection-adversary catalogue (specification)",
        "",
        "This is a **specification**, not a detection scoreboard. Hostile configs 04-07 remain",
        "software-survival (ADR 0017 / 0041). Nothing here overwrites a breaking detection report.",
        "",
        "| Id | Engine | What it tries to do | Detection claim |",
        "|---|---|---|---|",
    ]
    for item in DETECTION_ADVERSARY_SCENARIOS:
        lines.append(
            f"| `{item.scenario_id}` | {item.engine} | {item.summary} | "
            f"{str(item.is_detection_claim).lower()} |"
        )
    lines.extend(
        [
            "",
            "A later report that *scores* these scenarios must live **beside** detection logs,",
            "not inside them.",
            "",
        ]
    )
    return "\n".join(lines)

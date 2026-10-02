"""U5 protocol: three-arm stimuli, mechanical non-operator policy, case-pack access.

Fixtures live in `decision_fixtures.py`. This module is the executable protocol: render an arm,
collect a mechanical response that never sees gold, and name the primary comparison set.
"""

from __future__ import annotations

from collections.abc import Sequence

from phos.eval.decision_fixtures import (
    ATLAS_CASE_IDS,
    SENTIEL_CASE_ID,
    Case,
    atlas_cases,
    case_pack,
    sentiel_cases,
)
from phos.eval.decision_study import Arm, Conclusion, TrialResponse, stimulus_banner
from phos.reasoning.analyst import assess_narrative, render_narrative_markdown

__all__ = [
    "ATLAS_CASE_IDS",
    "SENTIEL_CASE_ID",
    "Case",
    "atlas_cases",
    "case_pack",
    "mechanical_non_operator_response",
    "primary_cases",
    "render_arm",
    "sentiel_cases",
    "stimuli_differ",
]


def render_arm(case: Case, arm: Arm) -> str:
    """Return the stimulus text for one arm. Atlas arm is the full U4 markdown."""
    if arm is Arm.RAW_TELEMETRY:
        return case.raw_stimulus
    if arm is Arm.THRESHOLD_ALERT:
        return case.threshold_stimulus
    brief = assess_narrative(case.narrative, case.store, case.library)
    return f"{stimulus_banner()}\n\n{render_narrative_markdown(brief)}"


def mechanical_non_operator_response(case_id: str, arm: Arm, stimulus: str) -> TrialResponse:
    """A declared non-operator policy that reads only the stimulus, never gold.

    Raw: cannot read process data - unresolved, do not escalate, confidence 1.
    Threshold: copy the alert line (alert -> unauthorised + escalate; quiet -> ordinary).
    Atlas explanation: copy the U4 assessment line; request the settling paragraph when present.

    Copying the Atlas brief on the Atlas arm is the policy, not a human. Quoting the resulting
    delta as usefulness is forbidden.
    """
    if arm is Arm.RAW_TELEMETRY:
        return TrialResponse(
            case_id=case_id,
            arm=arm,
            conclusion=Conclusion.UNRESOLVED,
            escalate=False,
            noticed_uncertainty=False,
            confidence=1,
        )
    if arm is Arm.THRESHOLD_ALERT:
        alerted = "THRESHOLD ALERT" in stimulus
        return TrialResponse(
            case_id=case_id,
            arm=arm,
            conclusion=(
                Conclusion.UNAUTHORISED_CONTROL if alerted else Conclusion.ORDINARY_OPERATION
            ),
            escalate=alerted,
            noticed_uncertainty=False,
            confidence=3,
        )
    return _copy_atlas_brief(case_id, arm, stimulus)


def stimuli_differ(case: Case) -> bool:
    """Return whether the three arms are actually different presentations."""
    raw = render_arm(case, Arm.RAW_TELEMETRY)
    threshold = render_arm(case, Arm.THRESHOLD_ALERT)
    atlas = render_arm(case, Arm.ATLAS_EXPLANATION)
    return raw != threshold and threshold != atlas and raw != atlas


def primary_cases(cases: Sequence[Case] | None = None) -> tuple[Case, ...]:
    """Return cases that enter the Atlas three-arm table."""
    pack = cases if cases is not None else case_pack()
    return tuple(item for item in pack if item.in_primary_comparison)


def _copy_atlas_brief(case_id: str, arm: Arm, stimulus: str) -> TrialResponse:
    """Parse U4 markdown. Unknown shapes fall through to unresolved rather than guessing."""
    settling = _section_after(stimulus, "## What would settle this")
    assessment = _section_after(stimulus, "## Assessment")
    lower = assessment.lower()
    noticed = "unresolved" in lower
    if "unresolved" in lower:
        conclusion = Conclusion.UNRESOLVED
        escalate = False
    elif "unauthorised" in lower:
        conclusion = Conclusion.UNAUTHORISED_CONTROL
        escalate = True
    elif "maintenance" in lower or "planned engineering" in lower:
        conclusion = Conclusion.ENGINEERING_MAINTENANCE
        escalate = False
    elif "ordinary" in lower:
        conclusion = Conclusion.ORDINARY_OPERATION
        escalate = False
    else:
        conclusion = Conclusion.UNRESOLVED
        escalate = False
        noticed = True
    return TrialResponse(
        case_id=case_id,
        arm=arm,
        conclusion=conclusion,
        escalate=escalate,
        noticed_uncertainty=noticed,
        confidence=3 if not noticed else 2,
        evidence_requested=settling,
    )


def _section_after(markdown: str, heading: str) -> str:
    """Return the paragraph under ``heading``, or empty if the heading is absent."""
    if heading not in markdown:
        return ""
    rest = markdown.split(heading, 1)[1]
    if "\n## " in rest:
        rest = rest.split("\n## ", 1)[0]
    return rest.strip()

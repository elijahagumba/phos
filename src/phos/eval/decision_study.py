"""U5 three-arm human-decision usefulness: scoring kernel.

This module is the measurement machinery, not the field study. Every public number in a U5
report is computed here from a gold label and a trial response. Nothing here invents a detector,
touches ``templates.py`` matchers, or appends to ``eval_runs/log.jsonl``.

**The run this phase can execute is labelled non-operator.** Plant-literate subjects are gated on
U7's partner conversation. A mechanical policy that reads only the stimulus (never the gold) is
how the instrument is exercised without recruiting. That policy is not a person, not an operator,
and not evidence of operational usefulness.

**Sentiel limitation, carried from U4 (ADR 0079 / R23).** Sentiel templates declare no
contradictory patterns, so settling-fact suggestions for Sentiel cases are weak. The study design
records that rather than assuming it away.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from phos.ontology import Domain, EvidenceStore, Narrative
from phos.reasoning.templates import TemplateLibrary

__all__ = [
    "CRUDE_RUN_LABEL",
    "NOT_A_FIELD_STUDY",
    "NOT_OPERATIONAL_USEFULNESS",
    "SENTIEL_SETTLING_LIMITATION",
    "SYNTHETIC_DERIVED_BANNER",
    "Arm",
    "ArmAggregate",
    "Case",
    "Conclusion",
    "Gold",
    "SubjectKind",
    "TrialResponse",
    "TrialScore",
    "aggregate_arm",
    "latin_square_arms",
    "raw_telemetry_stimulus",
    "score_trial",
    "stimulus_banner",
    "threshold_alert_stimulus",
    "threshold_quiet_stimulus",
]


CRUDE_RUN_LABEL: str = "CRUDE_NON_OPERATOR_NOT_A_FIELD_STUDY"
"""Banner token. Every U5 output carries this before any table."""

NOT_A_FIELD_STUDY: str = (
    "Not a field study. Subjects are not required to be plant engineers. "
    "Recruiting plant-literate people is gated on U7's partner conversation."
)
NOT_OPERATIONAL_USEFULNESS: str = (
    "Not evidence of operational usefulness. A crude first run must not be reported as a "
    "control-room result (ADR 0074 success_is_not; refusal register R4)."
)
SENTIEL_SETTLING_LIMITATION: str = (
    "Sentiel templates declare no contradictory patterns, so settling-fact suggestions for "
    "Sentiel cases are currently weak: the honest ask is a declared sanction record, and no "
    "corpus PHOS reads carries one (ADR 0079, refusal register R23). This is a study-design "
    "fact, not something the three Atlas arms can repair."
)
SYNTHETIC_DERIVED_BANNER: str = (
    "SYNTHETIC-DERIVED. Cases are ontology fixtures of U3 kinds, not a real plant. Not a "
    "detection claim. Nothing is appended to eval_runs/log.jsonl."
)


class Arm(str, Enum):
    """The three presentations of the same incident."""

    RAW_TELEMETRY = "raw_telemetry"
    THRESHOLD_ALERT = "threshold_alert"
    ATLAS_EXPLANATION = "atlas_explanation"


class Conclusion(str, Enum):
    """Closed set of conclusions a subject may record. No free-text winner."""

    ORDINARY_OPERATION = "ordinary_operation"
    ENGINEERING_MAINTENANCE = "engineering_maintenance"
    UNAUTHORISED_CONTROL = "unauthorised_control_activity"
    SENSOR_OR_DEVICE_FAULT = "sensor_or_device_fault"
    UNRESOLVED = "unresolved"


class SubjectKind(str, Enum):
    """Who produced the responses. Plant-literate is the missing input, not this run."""

    MECHANICAL_NON_OPERATOR = "mechanical_non_operator"
    HUMAN_NON_OPERATOR = "human_non_operator"
    PLANT_LITERATE = "plant_literate"


class Gold(BaseModel):
    """What a correct decision from the evidence looks like, for one incident.

    Gold is the epistemically correct call for a plant-literate reader of the *incident*, not
    a copy of whatever Atlas printed. Known-station writes without a work order are
    ``unresolved`` (ADR 0014). Quiet in-range telemetry is ordinary operation.
    """

    model_config = ConfigDict(frozen=True)

    conclusion: Conclusion
    should_escalate: bool
    uncertainty_important: bool


class Case(BaseModel):
    """One incident with gold, three stimuli, and the ontology the Atlas arm reads."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    case_id: str
    domain: Domain
    kind: str
    gold: Gold
    in_primary_comparison: bool
    raw_stimulus: str
    threshold_stimulus: str
    store: EvidenceStore
    narrative: Narrative
    library: TemplateLibrary
    sentiel_settling_is_weak: bool = False


class TrialResponse(BaseModel):
    """One subject's call on one (case, arm) stimulus.

    ``elapsed_ms`` is optional because a mechanical instrument-check has no decision time.
    Confidence is an ordinal 1-4 of the subject's own certainty, never a hypothesis probability.
    """

    model_config = ConfigDict(frozen=True)

    case_id: str
    arm: Arm
    conclusion: Conclusion
    escalate: bool
    noticed_uncertainty: bool
    confidence: int = Field(ge=1, le=4)
    evidence_requested: str = ""
    elapsed_ms: int | None = None


class TrialScore(BaseModel):
    """Computed comparison of one response against gold. No hand arithmetic."""

    model_config = ConfigDict(frozen=True)

    case_id: str
    arm: Arm
    correct_conclusion: bool
    false_escalation: bool
    missed_uncertainty: bool
    requested_evidence: bool
    overconfident_and_wrong: bool
    elapsed_ms: int | None


class ArmAggregate(BaseModel):
    """Counts for one arm. Rates are derived by the report from these counts."""

    model_config = ConfigDict(frozen=True)

    arm: Arm
    n: int
    n_correct: int
    n_incorrect: int
    n_false_escalation: int
    n_missed_uncertainty: int
    n_evidence_requested: int
    n_overconfident_wrong: int
    n_with_time: int
    sum_elapsed_ms: int


def score_trial(gold: Gold, response: TrialResponse) -> TrialScore:
    """Score one trial. False escalation is escalate-when-gold-says-no.

    Missed uncertainty is the measure the roadmap names as easiest to omit: the gold incident
    required noticing ambiguity, and the subject did not.
    """
    correct = response.conclusion is gold.conclusion
    return TrialScore(
        case_id=response.case_id,
        arm=response.arm,
        correct_conclusion=correct,
        false_escalation=response.escalate and not gold.should_escalate,
        missed_uncertainty=gold.uncertainty_important and not response.noticed_uncertainty,
        requested_evidence=bool(response.evidence_requested.strip()),
        overconfident_and_wrong=response.confidence >= 3 and not correct,
        elapsed_ms=response.elapsed_ms,
    )


def aggregate_arm(arm: Arm, scores: Sequence[TrialScore]) -> ArmAggregate:
    """Reduce trial scores for one arm to counts. Empty arm is zeros, not a hidden default."""
    matching = [item for item in scores if item.arm is arm]
    timed = [item.elapsed_ms for item in matching if item.elapsed_ms is not None]
    return ArmAggregate(
        arm=arm,
        n=len(matching),
        n_correct=sum(1 for item in matching if item.correct_conclusion),
        n_incorrect=sum(1 for item in matching if not item.correct_conclusion),
        n_false_escalation=sum(1 for item in matching if item.false_escalation),
        n_missed_uncertainty=sum(1 for item in matching if item.missed_uncertainty),
        n_evidence_requested=sum(1 for item in matching if item.requested_evidence),
        n_overconfident_wrong=sum(1 for item in matching if item.overconfident_and_wrong),
        n_with_time=len(timed),
        sum_elapsed_ms=sum(timed),
    )


def stimulus_banner() -> str:
    """Label every raw and threshold stimulus as a crude non-operator run."""
    return f"{CRUDE_RUN_LABEL} - not a field study, not operational usefulness. SYNTHETIC-DERIVED."


def raw_telemetry_stimulus(note: str) -> str:
    """A small in-range table with no alert and no explanation."""
    table = (
        "| t | intake_level | dosing_setpoint | filtration_flow |\n"
        "| --- | ---: | ---: | ---: |\n"
        "| 01:59 | 1.02 | 0.80 | 3.10 |\n"
        "| 02:00 | 1.03 | 0.80 | 3.11 |\n"
        "| 02:01 | 1.02 | 0.80 | 3.09 |"
    )
    return (
        f"{stimulus_banner()}\n\nRaw telemetry (no alert, no explanation).\n\n{table}\n\n{note}\n"
    )


def threshold_alert_stimulus(signal: str, value: str, threshold: str) -> str:
    """A conventional threshold line with no competing explanations."""
    return (
        f"{stimulus_banner()}\n\nTHRESHOLD ALERT\nSignal: {signal}\n"
        f"Value: {value} (threshold {threshold})\nTime: 2026-03-01T02:00:00Z\n"
        "No explanation is attached.\n"
    )


def threshold_quiet_stimulus() -> str:
    """A quiet window: no threshold exceeded, still no explanation."""
    return (
        f"{stimulus_banner()}\n\nTHRESHOLD STATUS\n"
        "No signal exceeded its threshold in this window.\nNo explanation is attached.\n"
    )


def latin_square_arms(n_cases: int, subject_index: int) -> tuple[Arm, ...]:
    """Return one arm per case for a within-subjects human protocol.

    Each subject sees each case once. Arms rotate so that, when ``n_cases`` is a multiple of
    three, each arm appears equally often. The crude mechanical run does not use this: it scores
    every case under every arm as an instrument check, which a human protocol must not do
    (seeing the same incident three ways contaminates the later arms).
    """
    if n_cases < 1 or subject_index < 0:
        raise ValueError("latin_square_arms needs n_cases >= 1 and subject_index >= 0")
    order = (Arm.RAW_TELEMETRY, Arm.THRESHOLD_ALERT, Arm.ATLAS_EXPLANATION)
    start = subject_index % len(order)
    return tuple(order[(start + index) % len(order)] for index in range(n_cases))

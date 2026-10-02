"""U5 report: every figure is a count already sitting on the study result.

Limitations are written first. A table before the non-operator banner is a defect.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from phos.eval.decision_study import (
    CRUDE_RUN_LABEL,
    NOT_A_FIELD_STUDY,
    NOT_OPERATIONAL_USEFULNESS,
    SENTIEL_SETTLING_LIMITATION,
    SYNTHETIC_DERIVED_BANNER,
    Arm,
    ArmAggregate,
    SubjectKind,
    TrialScore,
)

__all__ = ["StudyResult", "arm_order", "render_study_json", "render_study_markdown"]


class StudyResult:
    """Computed outcome of one U5 run. Constructed by the runner, rendered here."""

    def __init__(
        self,
        *,
        subject_kind: SubjectKind,
        n_human: int,
        n_mechanical: int,
        seed: int,
        git_commit: str,
        n_atlas_cases: int,
        n_sentiel_cases: int,
        primary: Sequence[ArmAggregate],
        sentiel: Sequence[ArmAggregate],
        scores: Sequence[TrialScore],
        sentiel_settling_is_weak: bool,
    ) -> None:
        """Store the already-computed aggregates. No arithmetic happens here."""
        self.subject_kind = subject_kind
        self.n_human = n_human
        self.n_mechanical = n_mechanical
        self.seed = seed
        self.git_commit = git_commit
        self.n_atlas_cases = n_atlas_cases
        self.n_sentiel_cases = n_sentiel_cases
        self.primary = tuple(primary)
        self.sentiel = tuple(sentiel)
        self.scores = tuple(scores)
        self.sentiel_settling_is_weak = sentiel_settling_is_weak


def render_study_markdown(result: StudyResult) -> str:
    """Render the crude-run report. Limitations occupy the first section."""
    lines = [
        "# U5 human-decision usefulness - crude non-operator run",
        "",
        f"**{CRUDE_RUN_LABEL}**",
        "",
        f"- {NOT_A_FIELD_STUDY}",
        f"- {NOT_OPERATIONAL_USEFULNESS}",
        f"- {SENTIEL_SETTLING_LIMITATION}",
        f"- {SYNTHETIC_DERIVED_BANNER}",
        "",
        "## This run",
        "",
        f"- Subject kind: `{result.subject_kind.value}`",
        f"- Human subjects: **{result.n_human}**",
        f"- Mechanical respondents: **{result.n_mechanical}**",
        f"- Atlas cases in the primary table: **{result.n_atlas_cases}**",
        f"- Sentiel limitation cases (not in the primary table): **{result.n_sentiel_cases}**",
        f"- Seed: `{result.seed}`",
        f"- Commit: `{result.git_commit}`",
        f"- Sentiel settling-fact suggestions are weak: "
        f"**{'yes' if result.sentiel_settling_is_weak else 'no'}**",
        "",
        "## Protocol (how a plant-literate human would sit this)",
        "",
        "The same six Atlas incidents are presented three ways: raw telemetry, a threshold",
        "alert with no explanation, and Atlas's U4 plain-English brief. A human protocol",
        "assigns one arm per case by Latin square so the same incident is never seen three",
        "times by one person. Measures: correct conclusion, false escalations, evidence",
        "requested, ordinal self-confidence 1-4 (not a hypothesis probability), whether",
        "important uncertainty was noticed, and elapsed milliseconds when a human sat it.",
        "The last measure is the one the roadmap names as easiest to omit.",
        "",
        "This crude run does **not** sit that protocol. It scores every case under every arm",
        "with a mechanical non-operator policy that never sees gold. Time to correct",
        "conclusion was not collected (`n_with_time` is 0). Plant-literate recruitment is",
        "the U7 partner conversation and is not started here.",
        "",
        "## Primary comparison (Atlas cases only)",
        "",
        "The mechanical policy copies the U4 assessment on the Atlas-explanation arm. A",
        "lower false-escalation count on that arm is therefore the policy, not a human",
        "result, and is not operational usefulness.",
        "",
        _arm_table(result.primary),
        "",
        "## Time to correct conclusion",
        "",
        _time_line(result.primary),
        "",
        "## Sentiel limitation case (excluded from the primary table)",
        "",
        SENTIEL_SETTLING_LIMITATION,
        "",
        _arm_table(result.sentiel),
        "",
        "## What would lift a real study",
        "",
        "Plant-literate subjects, recruited through the U7 partner conversation, sitting",
        "the Latin-square protocol on these same (or partner-site) incidents. Until then",
        "U5 has an executable instrument and no operational-usefulness measurement.",
        "",
        "Nothing in this report is a detection claim. Frozen HAI 646.58 / 53.26 and CERT",
        "6B 0.104 are untouched. Command-lead 0/16 and 1/4 stay unpooled.",
        "",
    ]
    return "\n".join(lines)


def render_study_json(result: StudyResult) -> dict[str, Any]:
    """JSON twin of the markdown. No `usefulness_score` key exists."""
    return {
        "label": CRUDE_RUN_LABEL,
        "not_a_field_study": True,
        "operational_usefulness_claim": False,
        "plant_literate": False,
        "subject_kind": result.subject_kind.value,
        "n_human": result.n_human,
        "n_mechanical": result.n_mechanical,
        "seed": result.seed,
        "git_commit": result.git_commit,
        "n_atlas_cases": result.n_atlas_cases,
        "n_sentiel_cases": result.n_sentiel_cases,
        "sentiel_settling_is_weak": result.sentiel_settling_is_weak,
        "sentiel_settling_limitation": SENTIEL_SETTLING_LIMITATION,
        "synthetic_derived": True,
        "logged_to_eval_runs_log": False,
        "primary": [_arm_dict(item) for item in result.primary],
        "sentiel": [_arm_dict(item) for item in result.sentiel],
        "n_scores": len(result.scores),
    }


def _arm_table(rows: Sequence[ArmAggregate]) -> str:
    header = (
        "| Arm | n | correct | incorrect | false escalations | missed uncertainty | "
        "evidence requested | overconfident and wrong | n with time |"
    )
    sep = "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"
    body = tuple(_arm_row(item) for item in rows)
    return "\n".join((header, sep, *body))


def _arm_row(item: ArmAggregate) -> str:
    return (
        f"| `{item.arm.value}` | {item.n} | {item.n_correct} | {item.n_incorrect} | "
        f"{item.n_false_escalation} | {item.n_missed_uncertainty} | "
        f"{item.n_evidence_requested} | {item.n_overconfident_wrong} | {item.n_with_time} |"
    )


def _arm_dict(item: ArmAggregate) -> dict[str, int | str]:
    return {
        "arm": item.arm.value,
        "n": item.n,
        "n_correct": item.n_correct,
        "n_incorrect": item.n_incorrect,
        "n_false_escalation": item.n_false_escalation,
        "n_missed_uncertainty": item.n_missed_uncertainty,
        "n_evidence_requested": item.n_evidence_requested,
        "n_overconfident_wrong": item.n_overconfident_wrong,
        "n_with_time": item.n_with_time,
        "sum_elapsed_ms": item.sum_elapsed_ms,
    }


def _time_line(rows: Sequence[ArmAggregate]) -> str:
    timed = sum(item.n_with_time for item in rows)
    if timed == 0:
        return (
            "Not collected. `n_with_time` is **0** on every primary arm. Decision time "
            "requires a human sitting the protocol."
        )
    parts: list[str] = []
    for item in rows:
        if item.n_with_time == 0:
            parts.append(f"`{item.arm.value}`: no times")
            continue
        mean = item.sum_elapsed_ms / item.n_with_time
        parts.append(f"`{item.arm.value}`: mean {mean:.1f} ms over {item.n_with_time} timed trials")
    return " ".join(parts)


def arm_order() -> tuple[Arm, ...]:
    """Stable table order: raw, threshold, Atlas explanation."""
    return (Arm.RAW_TELEMETRY, Arm.THRESHOLD_ALERT, Arm.ATLAS_EXPLANATION)

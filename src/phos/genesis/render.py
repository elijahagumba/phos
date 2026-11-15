"""Render the prose record from the data record.

The ADRs are the project's public scientific record and they stay. What changes is that they are
no longer written twice. A declaration already states the hypothesis, the command, the corpus, the
bars and why the hypothesis might be wrong; rendering turns that into the ADR body so the
researcher writes the science once and the record follows.

What is rendered is deliberately plain. The judgement, the caveats and the consequences are the
parts a human must still write, and the renderer leaves them as headed sections rather than
inventing text to fill them. A generated sentence that reads like a conclusion is exactly the
failure the charter's section VIII forbids, so this module never writes one.
"""

from __future__ import annotations

from phos.genesis.levels import LEVEL_NAMES
from phos.genesis.records import Experiment, Finding

#: The marker that says a section is for the human, not the renderer.
TODO: str = "<!-- GENESIS: written by hand. The renderer does not fill this. -->"


def _bar_lines(experiment: Experiment) -> list[str]:
    """Return one markdown list item per declared bar, with its measured value where known."""
    lines = []
    for bar in experiment.declared.bars:
        line = f"{bar.id}. {bar.text} (`{bar.metric} {bar.comparator} {bar.threshold:g}`)"
        if experiment.measured is not None:
            value = experiment.measured.values[bar.id]
            met = "met" if bar.met_by(value) else "missed"
            line += f" — measured **{value:g}**, {met}"
        lines.append(f"- {line}")
    return lines


def declaration_adr(experiment: Experiment, number: str, title: str) -> str:
    """Return the ADR body for a declaration.

    Args:
        experiment: The record, in phase ``declared``.
        number: The four-digit ADR number.
        title: The claim as a sentence, lowercase after the dash.

    Returns:
        Markdown, ending in a newline.
    """
    declared = experiment.declared
    digest = declared.challenger_sha256
    body = [
        f"# ADR {number} — {title}",
        "",
        "- **Status:** Accepted",
        f"- **Date:** {declared.date.isoformat()}",
        f"- **GENESIS:** {experiment.id}, serving {experiment.question}",
        "- **Supersedes:** nothing",
        "",
        "## Context",
        "",
        TODO,
        "",
        "## Decision",
        "",
        f"**{declared.hypothesis}**",
        "",
        f"- **Baseline:** {declared.baseline}",
        f"- **Corpus:** `{declared.corpus}` (tier `{declared.tier}`)",
        f"- **Command:** `{declared.command}`",
        f"- **Result name:** `{declared.result_name}`",
    ]
    if digest is not None:
        body.append(f"- **Challenger sha256:** `{digest}`")
    body += [
        "",
        "**Bars, as declared. Each is met or missed, and is not reworded after the run.**",
        "",
        *_bar_lines(experiment),
        "",
        "**Why this hypothesis might be wrong.**",
        "",
        declared.why_it_might_be_wrong,
        "",
        "**What would disprove it.**",
        "",
        declared.falsifier,
        "",
        "## Consequences",
        "",
        TODO,
        "",
        "---",
        "",
        f"Rendered by `scripts/genesis.py adr {experiment.id}` from "
        f"`docs/genesis/experiments/{experiment.id}.json`. The record is the source; this file is "
        "the public reading of it. Edit the record, re-render, and keep the hand-written sections.",
        "",
    ]
    return "\n".join(body)


def verdict_adr(experiment: Experiment, number: str, title: str) -> str:
    """Return the ADR body for a judgement.

    Args:
        experiment: The record, in phase ``judged``.
        number: The four-digit ADR number.
        title: The result as a sentence.

    Returns:
        Markdown, ending in a newline.

    Raises:
        ValueError: If the record carries no measurement or no verdict.
    """
    if experiment.measured is None or experiment.verdict is None:
        raise ValueError(f"{experiment.id} is not judged, so no verdict ADR can be rendered")
    measured, verdict = experiment.measured, experiment.verdict
    outcome = "kept" if verdict.outcome == "kept" else "refused"
    body = [
        f"# ADR {number} — {title}",
        "",
        "- **Status:** Accepted",
        f"- **Date:** {measured.date.isoformat()}",
        f"- **GENESIS:** {experiment.id}, serving {experiment.question}",
        f"- **Verdict:** **{outcome}**, computed from the measured values against the bars "
        f"declared on {experiment.declared.date.isoformat()}",
        "",
        "## Context",
        "",
        "The declaration was committed before the run"
        + (f" as `{experiment.declaring_commit}`" if experiment.declaring_commit else "")
        + f". The command was `{experiment.declared.command}` on `{experiment.declared.corpus}`, "
        f"measured from `{measured.commit}` and reported in `{measured.report}`.",
        "",
        "## Decision",
        "",
        f"**The result is {outcome}.**",
        "",
        *_bar_lines(experiment),
        "",
        "**Failure cases and unexpected results.**",
        "",
        measured.failures,
        "",
    ]
    if measured.notes:
        body += ["**Notes.**", "", measured.notes, ""]
    body += [
        "## Consequences",
        "",
        TODO,
        "",
        "---",
        "",
        f"Rendered by `scripts/genesis.py adr {experiment.id}`. A refusal is a result; it is "
        "recorded the same way a kept result is, and is not removed from the record later.",
        "",
    ]
    return "\n".join(body)


def finding_summary(finding: Finding) -> str:
    """Return a one-line summary of a finding, with its level named.

    Args:
        finding: The claim.

    Returns:
        A single line, no trailing newline.
    """
    level = f"L{finding.level} {LEVEL_NAMES[finding.level]}"
    evidence = ", ".join(finding.evidence) if finding.evidence else "no experiment"
    return f"{finding.id}  [{level}]  {finding.claim}  ({evidence})"

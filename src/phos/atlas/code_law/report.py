"""Render the H1 guard-form result as the report ADR 0382 names.

The report states, for each of ADR 0382's seven bars, met or not met, and quotes
the source lines the derivation read. **It states no rate, no percentage, no
coverage figure and no score**, and nothing in it may be restated as one. The
counts it carries are counts of cases and of disagreements, which are what was
checked, not a measure of how well anything did.

A refusal is written out in the same shape as a pass. The file is the record
either way.
"""

from __future__ import annotations

from collections.abc import Sequence

from phos.atlas.code_law.agreement import (
    ENUMERATION_MODES,
    ENUMERATION_SEED,
    AgreementResult,
)
from phos.atlas.code_law.certificate import Disagreement, plain
from phos.atlas.code_law.law import DerivedValveLaw, Side
from phos.atlas.code_law.source import DECLARED_SOURCES, SourceRefusal

__all__ = ["RESULT_NAME", "refusal_markdown", "report_markdown"]

#: The result name ADR 0382 declares.
RESULT_NAME = "code-law:guard-form"


def _literal_rows(law: DerivedValveLaw) -> str:
    """One table row per derived literal, quoting the source node's text."""
    lines = [
        "| Literal | Value | As the source writes it | Read from |",
        "| --- | --- | --- | --- |",
    ]
    for literal in law.literals:
        lines.append(
            f"| `{literal.name}` | {literal.value} | `{literal.literal_text}` | "
            f"`{literal.file}`:{literal.line} |"
        )
    return "\n".join(lines)


def _forced_rows(law: DerivedValveLaw) -> str:
    """One table row per forced actuator write from ``_check_manual_input``."""
    lines = [
        "| Mode | Writes | As the source writes it | Read from |",
        "| --- | --- | --- | --- |",
    ]
    for write in law.forced_writes:
        lines.append(
            f"| {write.mode} | {write.value} | `{write.literal_text}` | "
            f"`{write.file}`:{write.line} |"
        )
    return "\n".join(lines)


def _rule_rows(law: DerivedValveLaw) -> str:
    """One block per side, writing each branch out as the comparison it is."""
    blocks: list[str] = []
    for side in Side:
        rule = law.rule(side)
        lines = [
            f"**{side.value}** - writes `{rule.status_signal}`, guarded on `{rule.mode_signal}`."
        ]
        for index, branch in enumerate(rule.branches, start=1):
            parts = []
            for condition in branch.conditions:
                if condition.right_signal is not None:
                    right: float | str = condition.right_signal
                elif condition.right_literal_text is not None:
                    right = condition.right_literal_text
                else:
                    right = condition.right_literal if condition.right_literal is not None else ""
                parts.append(f"`{condition.left}` {condition.operator} `{right}`")
            lines.append(
                f"{index}. {' or '.join(parts)} → writes {branch.writes} (line {branch.line})"
            )
        if rule.otherwise is None:
            lines.append("Otherwise: nothing is required, which is silence.")
        else:
            lines.append(f"Otherwise: writes {rule.otherwise}.")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _disagreement_lines(disagreements: Sequence[Disagreement]) -> str:
    """List every disagreement. Omitting one fails bar 5."""
    if not disagreements:
        return "- none"
    lines: list[str] = []
    for item in disagreements:
        sample = item.sample
        side = item.side if item.side is not None else "both"
        lines.append(
            f"- {item.kind} on {side}: level {plain(sample.level)}, bottle "
            f"{plain(sample.bottle_level)}, belt {plain(sample.belt)}, modes "
            f"{plain(sample.input_mode)} and {plain(sample.output_mode)}, valves "
            f"{plain(sample.input_valve)} and {plain(sample.output_valve)}; "
            f"comparison: {item.certificate.comparison}"
        )
    return "\n".join(lines)


def report_markdown(law: DerivedValveLaw, result: AgreementResult) -> str:
    """Return the report for one run of the declared command.

    Args:
        law: The derived law.
        result: ADR 0382's seven bars for that law.

    Returns:
        The report, as markdown.
    """
    bars = "\n".join(
        f"| {index} | {bar.name} | {'met' if bar.met else 'not met'} | {bar.detail} |"
        for index, bar in enumerate(result.bars, start=1)
    )
    digests = "\n".join(
        f"| `{source.relative}` | `{law.digests.get(source.relative, '')}` |"
        for source in DECLARED_SOURCES
    )
    parted = _disagreement_lines(result.disagreements)
    return f"""# {RESULT_NAME}

Declared by [ADR 0382](../../../docs/adr/0382-the-derived-valve-rule-is-the-candidate-and-a-\
guard-holds-both-shapes.md), build brief H rung H1. This file reports **met or not met** against
the bars as that record
words them. Every line in it is a standing, or a count of the cases that were checked. Nothing
in it measures how well anything did, and nothing in it may be restated as if it did.

The law below was read out of the pinned ICSSim source at `{law.commit}`. The source was read
as text and parsed into a syntax tree. It was not imported, executed or simulated, and
`data/phos-icssim-dev/roles.toml` was not read.

## Files read, and their digests

| File | sha256 |
| --- | --- |
{digests}

## The bars

| # | Bar | Standing | What was found |
| --- | --- | --- | --- |
{bars}

**Overall: {"met" if result.met else "not met"}.** A bar that is not met is a refusal of this
step as ADR 0382 words it. `controller_valve` is not edited, and its literals do not move. The
derived rule stays a candidate.

## The literals the derivation read

{_literal_rows(law)}

## The forced actuator writes the derivation read

{_forced_rows(law)}

## The rules the derivation read

{_rule_rows(law)}

## The guard the derivation read

`{law.guard.file}`:{law.guard.line} is an exclusion of modes
{", ".join(str(mode) for mode in law.guard.manual_modes)}. The hand guard is an equality at the
release literal. The two forms differ. That comparison is on the form, not on a hand-picked list
of modes.

## Enumerated disagreements

The enumeration is exhaustive over the cases ADR 0382 declares (modes
{list(ENUMERATION_MODES)} on each tag), so nothing is sampled and the declared seed
{ENUMERATION_SEED} is recorded rather than used. Every disagreement is listed. Agreement in
silence is not listed as agreement on a decision.

{parted}
"""


def refusal_markdown(refusals: Sequence[SourceRefusal]) -> str:
    """Return the report for a run that could not read its declared source.

    Args:
        refusals: One entry per file that could not be used.

    Returns:
        The report, as markdown. A refusal of the run is a record, not a gap.
    """
    rows = "\n".join(
        f"| `{refusal.relative}` | {refusal.reason.value} | `{refusal.expected}` | "
        f"`{refusal.found}` |"
        for refusal in refusals
    )
    return f"""# {RESULT_NAME} - refused

Declared by [ADR 0382](../../../docs/adr/0382-the-derived-valve-rule-is-the-candidate-and-a-\
guard-holds-both-shapes.md), build brief H rung H1. **The run was refused before any law was
derived**, because the declared
source did not match what ADR 0370 pins. No bar was evaluated. Nothing here is a result
about the derivation.

| File | Refusal | Expected sha256 | Found |
| --- | --- | --- | --- |
{rows}

A digest that does not match is a refusal of the run, not a warning. The fix is a checkout at
the pinned commit, or a new declaration that pins a different one.
"""

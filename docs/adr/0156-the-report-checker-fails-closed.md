# ADR 0156 — The report checker fails closed

- **Status:** Accepted
- **Date:** 2026-10-17
- **PART:** C1 / W6, evidence-grade reports
- **Depends on:** [ADR 0155](0155-incident-types-are-template-ids.md)

## Context

Constitution §3.2 says anything a reader sees must be reconstructable from stored evidence.
Constitution §3.3 says an uncalibrated hypothesis confidence is not a probability a reader may be
shown. The roadmap's pass for this work is a check that every sentence cites an evidence id.

## Decision

`check_sentence` rejects one sentence that is not a single period-terminated sentence, or that
cites no evidence id the store holds. `check_rendered_report` applies that rule to every line of
a rendered report that is not on a fixed metadata allowlist. A blank line, a free-text header, an
unknown evidence id, and an evidence id from a different narrative all fail the check.
`build_report` runs the check before it returns.

`insufficient_evidence` must be one of the narrative's hypotheses. A narrative with no evidence
is refused: there is no id to cite. A stored summary that already contains an evidence-id token,
or a line break, is refused rather than wrapped into a citation that would mix two claims.

Hypothesis `confidence`, hypothesis `prior`, and `Narrative.overall_confidence` are not rendered.
The checker rejects a report whose text contains those stored numbers. The report fields
`confidence_surfaced` and `overall_confidence` are fixed at `false` and `withheld`.

A period between digits stays inside the quoted summary, so `1.5` is not split into two sentences.
Any other period starts a new cited sentence that carries the same evidence id.

## Consequences

The checker is `check_sentence` and `check_rendered_report`. There is no command-line script: a
script would need a store file format this lane does not own, and the functions are the check the
roadmap describes. A sentence the checker cannot bind to stored evidence is a failed report, not
a report with a gap in the margin.

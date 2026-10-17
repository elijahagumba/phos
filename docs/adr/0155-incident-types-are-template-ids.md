# ADR 0155 — An incident type is the template id already stored

- **Status:** Accepted
- **Date:** 2026-10-17
- **PART:** C1 / W6, evidence-grade reports (`docs/build-brief-2026-10.md` workstream 3)
- **Depends on:** [ADR 0144](0144-the-october-build-is-declared.md)

## Context

The v1 roadmap asks for a report for every incident type, generated from a narrative, with every
statement cited to stored evidence. The ontology names `Narrative`, `Hypothesis`, and `Evidence`.
It does not name an incident-type enum. The explanations PHOS can already give are the hypothesis
templates: Atlas, Sentiel, the two generic engine placeholders, and `insufficient_evidence` in
each library.

## Decision

`phos.reasoning.reports` reads a stored `Narrative` and writes sentences from fields the store
already holds. An incident type is the `template_id` on a hypothesis the narrative lists. No
`IncidentType` was added to the ontology.

The narrative title and the entity display name are left off the page. Neither is an evidence id,
and quoting them as a finding would be a sentence the checker would have to reject or a fact the
report would have invented.

`generic_anomalous_activity` and `generic_benign_change` render when a narrative carries them.
They stay named as the PART 4B placeholders. A rendered label is the stored label, not a claim
that the placeholder is an Atlas or Sentiel finding.

## Consequences

A new explanation becomes a reportable incident type when a template is registered and a narrative
stores its id. The tests enumerate `atlas_templates`, `sentiel_templates`, and `generic_templates`,
so a template that disappears, or one that cannot be cited, fails the suite. The public index of
ADRs is left for the merge, as the lane brief requires.

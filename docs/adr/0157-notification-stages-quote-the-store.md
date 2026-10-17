# ADR 0157 — Notification stages quote the store

- **Status:** Accepted
- **Date:** 2026-10-17
- **PART:** C1 / W6, evidence-grade reports
- **Depends on:** [ADR 0156](0156-the-report-checker-fails-closed.md)

## Context

The brief asks for a report structured for an NIS2 early warning (24 hours), an NIS2 incident
notification (72 hours), and the UK Cyber Security and Resilience law's notification stages.
Directive (EU) 2022/2555 Article 23(4)(a) asks the early warning to indicate, where applicable,
whether the incident is suspected of being caused by unlawful or malicious acts or could have a
cross-border impact. Article 23(4)(b) asks the 72-hour notification to update that and to give an
initial assessment of severity and impact and, where available, indicators of compromise.

The UK clocks used here are the two named with the Cyber Security and Resilience Bill on
12 November 2025: an initial notification within 24 hours and a fuller report within 72 hours,
to the regulator and the NCSC. This session did not read an enacted instrument.
`legislation.gov.uk` is not a host the October build may fetch. The detailed UK form, if a later
instrument fixes one, is not in the ontology.

## Decision

Every report has four stages, in this order:

| Stage | Clock |
| --- | --- |
| `nis2_early_warning_24h` | 24 hours |
| `nis2_incident_notification_72h` | 72 hours |
| `uk_csr_initial_24h` | 24 hours |
| `uk_csr_full_72h` | 72 hours |

The 24-hour sentences quote the evidence (kind, time, entities, summary) and every hypothesis,
residual included, with its supporting and contradictory ids. The 72-hour sentences are those
same sentences plus source, domain, facet, and any stored causal edge. The UK stage on a clock
carries the same sentences as the NIS2 stage on that clock. The store has one story; a second
wording would be a fact this module does not have.

Statutory prompts are fields, not sentences, and only these statuses are allowed:

- `unlawful_or_malicious_suspected` is `not_asserted` on every stage. A template id in the
  competing set is not a suspicion of an unlawful act, and hypothesis confidence is uncalibrated.
- `cross_border_impact` is `not_in_store`.
- `severity_and_impact` and `indicators_of_compromise` are `not_this_stage` at 24 hours and
  `not_in_store` at 72 hours.

The NIS2 one-month final report is outside this module. The brief names the early warning and
the incident notification. An MSP duty to notify customers is not a stage here: the ontology
holds no customer record, and this lane does not invent one.

## Consequences

A report can be handed to someone filling a 24-hour or 72-hour notice. It will not contain an
impact figure, a cross-border claim, or a probability. If the enacted UK instrument names
different stages, the stage ids are the document structure to revise. ADR 0158 and ADR 0159 were
not needed for this lane.

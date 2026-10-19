# ADR 0190 — Depth counting: one loud signal can match many quiet ones

- **Status:** Accepted
- **Date:** 2026-10-19
- **PART:** Build lane A, Sentiel capability 1
- **Depends on:** [ADR 0149](0149-lane-a-dev-loop-does-not-touch-6b.md)

## Context

6B sums `1 - exp(-magnitude / 3)` over speaking features. Each term is below 1,
so a day needs about fourteen features to reach the published 48-alert cut
(13.70). `CCH0959`'s malicious days mostly cannot: 31 of 42 are structurally
unalertable (`eval_runs/sentiel/cert-failure-classification.md`). That is a
breadth rule. Target 1 asks for the opposite: one very unusual signal may count
as much as many slightly unusual ones.

Recomputing the 34 Gaussian magnitudes on every loop is too expensive. The six
starter counts already sit on every entity-day trace.

## Decision

`phos.sentiel.depth` scores a day as `max(breadth, depth)` from the six counts
(`logons`, `off_hours_logons`, `removable_connects`, `file_accesses`, `emails`,
`external_emails`):

- Each count's magnitude is the absolute z-score against that user's own
  attack-free prefix (mean and sample standard deviation, at least eight prior
  days; otherwise the day is silent).
- Breadth is the 6B squash `sum(1 - exp(-m / 3))`.
- Depth is `max(m) / 3`, with no exponential cap.

The frozen `AggregationPolicy` is not edited. This stream is a new score, named
`lane-a-dev:depth`. Unknown is not anomalous: a user with too little history
scores 0.

## Consequences

A single count that is 14σ from the user's own past scores about 4.67 on depth
and about 1.0 on breadth. Many small departures can still win on breadth. The
stream does not read hosts, recipients, or labels. It may still miss `CCH0959`
if that insider is not loud on the six counts, which the autopsy already
suggests. That is a measurement, not a reason to change the formula after a
labelled look.

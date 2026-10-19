# ADR 0194 — The kept scorer is still 6B; r4.2 stays unscored

- **Status:** Accepted
- **Date:** 2026-10-19
- **PART:** Build lane A, Sentiel S3 restatement
- **Depends on:** [ADR 0147](0147-cert-r42-held-out-and-not-fetched.md),
  [ADR 0149](0149-lane-a-dev-loop-does-not-touch-6b.md)

## Context

Target 1 ran ten development loops on CERT r3.1 (ADR 0149, ADRs 0190–0193).
None were kept. The starting bar remains the frozen 6B row: `CSF0929` in the
top 48, `CCH0959` best rank 957, precision 0.104. S3 asked this lane to
declare the larger CERT release and not score it.

## Decision

1. The named scorer a later session may take to r4.2 is still
   `aggregate:gaussian:peer set (34 features) (6B)`. No `lane-a-dev:*` name
   is kept. The frozen row is not overwritten.

2. CERT r4.2 remains held out under ADR 0147. `r42_may_be_scored()` is still
   false. The archive was not fetched. No file of r4.2 was opened. No sha256
   was invented.

3. The closest development movement — `lane-a-dev:peer-links+chains`,
   `CCH0959` best rank 119 — lost `CSF0929` and is not the kept scorer.

## Consequences

S3's measurement bar is still unmet. A later score declares the command and
the scorer in a commit that precedes the run, then runs once. It does not
retune 6B on r4.2.

# ADR 0260 — Build D is merged, and its bars stand

- **Status:** Accepted
- **Date:** 2026-10-19
- **PART:** Build brief D (`docs/build-brief-2026-10-d.md`)
- **Depends on:** [ADR 0212](0212-a3-queue-rank-is-declared.md),
  [ADR 0234](0234-the-familiarity-queue-gate-is-not-run.md),
  [ADR 0240](0240-lane-r-held-back-confidence-is-declared.md),
  [ADR 0255](0255-trusted-station-held-back-lead-bar-is-not-met.md)

## Context

Lanes Q, R, and T were built on `7ff682c` and merged to `main` in the order
`build/d-reasoning`, `build/d-trusted`, `build/d-queue`. Each held-back batch was
scored once before the merge. Nothing here rescores one. The review is
`eval_runs/build/d/REPORT.md`.

## Decision

1. **Lane Q.** No ranker beat the champion. On HAI 20.07 the oracle ceiling is
   21 of 38, because most A3 misses are shifts with more attacks than top-10%
   slots. That ceiling is a finding for any future queue metric. v1's A3 stays
   57 of 203 and is not reworded. The five-corpus gate (ADR 0234,
   `atlas-queue-v2:familiarity-gate`) was declared and not run.
2. **Lane R.** On held-back seeds 97701–97720, 60 of 60 contentful leads were
   right, against 33 of 54 before. Those seeds are the same five scenarios the
   separators were designed around, so this shows generalisation across runs,
   not to new scenario types. W5 is not met. Its high flag is a Wilson 95%
   lower bound on the leads that share one separation count. The largest such
   group in development is 15, and 15 right out of 15 has a lower bound under
   0.8, so the flag could not come on. That is a design flaw to fix, not
   evidence about the reasoning. Seeds 97501–97520 were not opened.
3. **Lane T.** 0 of 20 hostile known-station writes led. The two kept facts
   attached on every hostile write and on no authorised run, in development and
   held-back. What stopped them leading was the fixed half weight under the
   residual prior, not the evidence. Known-link indistinguishability and the
   frozen weights were not changed. The result is a simulated diagnosis
   (ADR 0073), not the frozen 0 of 16, and it is not pooled with 1 of 4.

## Consequences

The lane code is on `main`. The bars above stand. `data-tiers.mdc` is unchanged.
The gate stays unrun. `public/` is not updated by this record.

## What would reverse this

Rewording A3 or W5, running the gate without a one-look exception, rerunning a
held-back batch, or reading the empty high band as a finding about the explanations.

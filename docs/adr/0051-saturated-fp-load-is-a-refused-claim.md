# ADR 0051 — Saturated FP load is a refused claim, not a quieter metric

- **Status:** Accepted
- **Date:** 2026-08-23
- **PART:** Category programme Session C2
- **Supersedes:** nothing. Public distillation **18.72** and Data4Cyber Track A log names
  stay `MEASURED`. This record adds a *mechanism*; it does not reclassify those rows.
- **Depends on:** [ADR 0003](0003-window-level-recall-and-false-positives-per-normal-hour.md),
  [ADR 0046](0046-data4cyber-track-a-is-process-phase-telemetry-not-a-control-room-ruler.md),
  [ADR 0048](0048-distillation-declared-phase-is-louder.md),
  [ADR 0049](0049-split-scorecard-public-files-vs-partner.md),
  [ADR 0050](0050-snapshot-joint-assumptions-are-executable.md)

## Context

The speech contract already says saturated false-positive load is a reason to stay
silent. The harness did not: `evaluate()` always returned a detection row. The
breaking report's `SATURATED_FP_PER_HOUR = 1.0` lived in markdown. Distillation 18.72
and unknown-master 1.1650 FP/hour were characterised as loud in ADRs, not as a
`claim_status` on the report object.

Quiet-pooling those rows through a new refuse to make 2–3/day look earned would be
Session C2 failing its `success_is_not`.

## Decision

1. **`ClaimStatus`** is `MEASURED` (default) or `REFUSED`. Historical `log.jsonl` lines
   have no field and load as `MEASURED`.

2. **`SaturationPolicy(max_fp_per_hour=...)`** plus **`apply_saturation_policy(report,
   policy)`** set `claim_status` when `false_positive_rate` **exceeds** the declared
   line. Metrics are never rewritten. Equal-to-the-line stays `MEASURED`.

3. **`evaluate()` never applies a policy.** Public distillation and Data4Cyber callers
   omit the call, so those log names stay comparable. `DEFAULT_SYNTH_SATURATION` is
   1.0 FP/hour — the breaking-harness line — and is opt-in. New breaking-harness
   appends apply it; the log is append-only, so historical lines are not rewritten.

4. **`SATURATED_FP_LOAD_CAVEAT`** joins `ATLAS_VERTICAL_CAVEATS`. It names the public
   18.72 and Data4Cyber rows as staying `MEASURED` unless a caller applies a policy.

## Consequences

- A future experiment can complete as `REFUSED` with the same status field as a
  positive row. That is the mechanism Clock A asked for.
- Distillation 2–3/day remains refused on the public ZIP (ADR 0048). This session did
  not quieter-pool 18.72 through `REFUSED` to earn the budget.
- Live session after this record is **C3** (scale relationships, stated).

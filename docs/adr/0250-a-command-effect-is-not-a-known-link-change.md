# ADR 0250 — A command effect is not a known-link change

- **Status:** Accepted
- **Date:** 2026-10-19
- **PART:** Build brief D, lane T
- **Supersedes:** nothing
- **Depends on:** [ADR 0034](0034-command-lead-rate-zero-on-known-link-writes.md),
  [ADR 0036](0036-a-lead-tie-is-a-refusal-not-an-alphabetical-winner.md),
  [ADR 0039](0039-ranking-contract-lock-undoing-0036-0038-must-turn-existing-tests-red.md),
  [ADR 0073](0073-a-synthetic-command-and-maintenance-harness-that-measures-nothing.md)

## Context

Known-station unique lead is **0 of 16**. Unknown-master unique lead is **1 of 4**. They are not
pooled. A function change or a silence on a known link still supports both
`engineering_maintenance` and `unauthorised_control_activity`. Lane T asks whether a fact about
what the write does to the plant can support unauthorised control without moving those matchers.

The issuer in this lane is the plant's declared operator, the station that already commands in
normal operation. It is not a silent engineering workstation. Development seeds are
97801–97820. Held-back seeds are 97901–97920 and are not scored in this record.

## Decision

**Add `FacetKind.COMMAND_EFFECT`.** The first feature is `toward_limit_against_state`: the
setpoint left the plant's declared operating band toward a safety limit (the signal's own low
or high), against the direction the reported state called for. The call is the sign of setpoint
minus the controlled measurement. An error inside three of that measurement's own noise
standard deviations is a hold. A covering work order withholds the fact.

The pattern supports `unauthorised_control_activity` only. It does not support or contradict
maintenance, a process upset, or a sensor fault. It does not match `unexpected_command_function`
or `silent_command_relationship`. Those facts still support both explanations.

The evidence weight is `FittedPlattCalibrator(coefficient=0.0, intercept=0.0)`, a constant one
half. It is not tuned. One such fact does not lift unauthorised above the residual prior, so a
unique lead is not expected. A tie is not a lead. `insufficient_evidence` listed first is not a
lead.

Seeds 97801–97820 and 97901–97920 are registered in `build_seed_blocks`. They do not overlap
97601–97670 or 97701–97720. Held-back is not generated here.

## Consequences

**Gained.** The known-link both-support tests stay the test of indistinguishability. A later
hypothesis can add another command-effect feature without retuning those matchers.

**Cost.** H1's development numbers are not in this record. They are written after the run.
Nothing here is a field rate (ADR 0073), and nothing here moves the frozen 0 of 16 or 1 of 4.

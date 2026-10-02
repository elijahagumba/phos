# ADR 0054 — A VAR residual is a named experiment beside snapshot Mahalanobis

- **Status:** Accepted
- **Date:** 2026-08-23
- **PART:** Category programme Sessions C5–C6
- **Supersedes:** nothing
- **Depends on:** [ADR 0050](0050-snapshot-joint-assumptions-are-executable.md),
  [ADR 0052](0052-scale-invariant-shrinkage-is-a-named-option.md)

## Context

The snapshot joint model scores a moment without \(x_{t-1}\). Session C5 asked for a
declared-order linear dynamical residual. Session C6 asked for a bake-off against that
snapshot, without overwriting ungated distillation **18.72**.

## Decision

1. `LinearDynamicsModel` (`atlas-var1`, default `lag=1`) fits OLS VAR on attack-free
   train and scores \(r_t = x_t - \hat{x}_t\) with a per-signal `ExpectedRange`.
2. Named assumptions: linear within a mode, declared lag, attack-free train.
   Named breaks: setpoint not in train; unmodelled switching.
3. Bake-off is fixture-only. Dummy-batch pooled snapshot stays blind (ADR 0018).
   Declared phase-conditional snapshot still recovers that fixture. A mixed-mode VAR
   is not the public distillation row. `dwell_samples` / `joint_k` were not retuned.

## Consequences

- Snapshot Mahalanobis remains the public comparison name.
- Live session after C6 is C7 (starve-mode fallback).

# ADR 0055 — Starved declared modes fall back; forged matching physics is unhandled

- **Status:** Accepted
- **Date:** 2026-08-23
- **PART:** Category programme Sessions C7–C8
- **Supersedes:** nothing
- **Depends on:** [ADR 0018](0018-phase-conditional-modelling-for-a-batch-process.md),
  [ADR 0048](0048-distillation-declared-phase-is-louder.md),
  [ADR 0054](0054-var-residual-is-a-named-experiment.md)

## Context

`PhaseConditionalModel` is a lookup, not a switching system. Sparse modes explode FP
(ADR 0048). An attacker who writes a valid other phase is an unmeasured risk named
in `phased.py`.

## Decision

1. Phases seen in train but too rare to fit a tight inner model are listed on
   `starved_phases` and scored by the pooled fallback. That is not "the mode was
   learned."
2. The inner model may be snapshot Mahalanobis or `LinearDynamicsModel`. Public
   distillation settling stays 0.
3. Forged valid phase with mismatched physics is flagged by the wrong \(f_m\).
   Forged valid phase whose physics match that phase is **unhandled**. Switching
   is not a security claim against a lying PLC.

## Consequences

- 2–3/day is still refused. Clustering a phase from correlations is still forbidden
  as a public row.

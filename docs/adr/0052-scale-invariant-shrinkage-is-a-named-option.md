# ADR 0052 — Scale-invariant shrinkage is a named option, not the public default

- **Status:** Accepted
- **Date:** 2026-08-23
- **PART:** Category programme Session C3
- **Supersedes:** nothing. [ADR 0018](0018-phase-conditional-modelling-for-a-batch-process.md)
  still rejects Option A as the *default* `_shrink`. This record ships that path as an
  opt-in.
- **Depends on:** [ADR 0018](0018-phase-conditional-modelling-for-a-batch-process.md),
  [ADR 0050](0050-snapshot-joint-assumptions-are-executable.md)

## Context

`_shrink` pulls covariance toward `(trace / width) * I` in the **raw units** of the
signals. A batch pool with one huge-variance tag then floors every band (ADR 0018).
Standardising before shrink (Option A) revived the dummy batch plant and **inflated**
water-treatment's attack-free holdout. ADR 0018 therefore kept `_shrink` unchanged and
chose per-declared-phase models instead.

Session C3 asked for that scale-invariant path as a **named option**, with a bake-off,
without overwriting ungated distillation **18.72**.

## Decision

1. **`ShrinkageTarget`** on `MahalanobisModel`:
   - `AVERAGE_VARIANCE` — public default; identical to the previous `_shrink`.
   - `CORRELATION` — standardise, shrink toward `I`, rescale (ADR 0018 Option A).

2. **Within declared mode** is `PhaseConditionalModel(inner=MahalanobisModel(
   shrinkage_target=CORRELATION))`. The router already subsets before `fit`.

3. **Bake-off (fixtures, not a public log overwrite):** pooled `CORRELATION` sees the
   miniature phase-violation that pooled `AVERAGE_VARIANCE` misses. On a continuous
   mixed-scale analogue of water/power, `CORRELATION` inflates the attack-free holdout
   relative to the default. Do not quote that quietness or loudness as distillation.

## Consequences

- Public Mahalanobis comparison rows stay on `AVERAGE_VARIANCE`. 18.72 is not rewritten.
- One shrinkage is not used for every plant. `CORRELATION` is available where a caller
  names it. Live session after this record is **C4**.

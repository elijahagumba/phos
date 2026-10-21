# ADR 0050 — Snapshot joint-model assumptions are executable

- **Status:** Accepted
- **Date:** 2026-08-23
- **PART:** Category programme Session C1
- **Supersedes:** nothing. [ADR 0009](0009-joint-modelling-per-signal-attribution-and-the-model-that-lost.md)
  still records that PCA lost on HAI. This record does not retune PCA.
- **Depends on:** [ADR 0009](0009-joint-modelling-per-signal-attribution-and-the-model-that-lost.md),
  [ADR 0018](0018-phase-conditional-modelling-for-a-batch-process.md),
  [ADR 0048](0048-distillation-declared-phase-is-louder.md),
  [ADR 0049](0049-split-scorecard-public-files-vs-partner.md),
  category-defining roadmap (lab record, not published)

## Context

Atlas already *says* the plant is a manifold. What it *implements* in
`src/phos/atlas/multivariate.py` is a **static linear snapshot**: shrunk covariance or a PCA
subspace at one timestamp. Session C1 of Clock A asked that those assumptions be named in
code so a test can falsify them, and that the known break conditions be named rather than
left in docstrings.

The public ungated Mahalanobis log name (distillation **18.72** FP/hour) is not this
session. `_shrink` is not rewritten. PCA is not "fixed" by fitting on the test set.

## Decision

1. **`SNAPSHOT_ASSUMPTIONS`** names what the current joint models actually do:
   `temporal_independence` (a complete moment is scored without using \(x_{t-1}\)),
   `linear_feasible_set` (PCA subspace or Mahalanobis ellipsoid), `constants_dropped`
   (a tag that never moved in train is not in the space).

2. **`MANIFOLD_BREAK_CONDITIONS`** names when that snapshot is not a valid plant model:
   `nonstationarity_capture_drift` (ADR 0009 PCA out-of-sample inflation),
   `mixed_modes` (ADR 0018 / 0048), `constant_in_train`, `shrinkage_floor_mixed_scale`
   (Ledoit–Wolf target in raw units).

3. **Tests pin the geometry, not a retune.** Scoring a complete moment with a wild
   previous timestamp does not change the tip reconstruction. PCA components span a
   proper subspace (`1 <= k < n`). Mahalanobis precision is SPD after shrink. PCA's
   residual-band inflation under a larger noise floor exceeds the Gaussian's, without
   fitting on the drifted set.

## Consequences

- The snapshot model is honest about being a snapshot. Session C5 may add a dynamical
  residual beside it; it must not overwrite public Mahalanobis log names.
- `_shrink` on public rows is unchanged. Scale-aware covariance is Session C3, as a
  named option, not a silent default.
- Live session after this record is **C2** (saturated FP load as a refuse).

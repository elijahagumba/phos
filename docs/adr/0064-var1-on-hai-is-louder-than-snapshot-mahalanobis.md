# ADR 0064 — VAR(1) on HAI is louder than snapshot Mahalanobis

- **Status:** Accepted
- **Date:** 2026-08-24
- **PART:** Engine week (public Atlas bakeoff)
- **Supersedes:** nothing
- **Depends on:** [ADR 0054](0054-var-residual-is-a-named-experiment.md),
  [ADR 0009](0009-joint-models-explainability-and-the-pca-out-of-sample-failure.md)

## Context

ADR 0054 named `LinearDynamicsModel` (`atlas-var1`) as a fixture experiment beside snapshot
Mahalanobis. It had never been asked of a public plant. Engine week scored it on the frozen HAI
three-way protocol (seed **11**, threshold **3.0**, `dwell_samples=1`) under a **new** log name.

The question is one sentence: does a VAR(1) residual beat a snapshot Mahalanobis ellipsoid on
HAI at the locked threshold?

## Decision

1. `scripts/evaluate_atlas.py --var` scores `LinearDynamicsModel` only. It does not re-log
   `model:atlas-mahalanobis`.
2. Measured on `hai-test-test`: `model:atlas-var1`, seed 11, threshold 3.0, commit `5b62230`.
   Window recall **1.00**. **14071.07** FP/normal hour (110966 FPs / 7.886 normal hours).
   Native HAI Mahalanobis **646.58** is not overwritten. VAR is **louder**.
3. `atlas-var1` is **refused** as the HAI detector. Do not retune lag, threshold, or `_shrink`
   to chase a win. Do not stack further dynamics on HAI this week.
4. `model:atlas-var1+isotonic` logged on the same split; alerting still uses the model score,
   so the FP/hour matches the uncalibrated row. It is not a quieter detector.
5. **Provenance.** The first pair of rows written for this measurement — log rows **180-181**,
   stamped `git_commit: 5c652c3` — are **superseded pre-commit rows**. That commit does not
   contain the `--var` code path that produced them; it existed only in the working tree, so
   the rows could not be reproduced from the commit they named. The measurement was re-run
   from `5b62230`, the commit that actually carries `--var`, and returned **bit-identical**
   values across all 29 non-volatile report fields (`false_positive_rate`
   14071.067277210286, recall, ECE, Brier, every operating point and reliability bin). The
   corrected rows are **182-183**. Rows 180-181 are retained rather than deleted: the
   experiment log is append-only evidence. Cite rows 182-183.

## Consequences

**Gained.** The unused math was asked of the plant. Snapshot Mahalanobis remains the public
HAI ruler because the dynamical residual flooded normal hours.

**Cost.** A linear one-step predictor fitted on 173 attack-free timestamps × 52 signals does
not describe HAI's test half. That is a measurement, not a licence to add lag-2 or torch.

## Alternatives considered

- **Add VAR to default `contenders()`.** Rejected. That would re-append Gaussian / PCA /
  Mahalanobis rows.
- **Search a threshold on HAI test.** Rejected. The public operating point stays 3.0.
- **Quote 14071 as a 10× claim versus Gaussian.** Rejected. Gaussian is already 8389; VAR is
  louder than both the baseline and Mahalanobis.

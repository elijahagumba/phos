# ADR 0066 — Correlation-target Mahalanobis cannot invert on HAI three-way

- **Status:** Accepted
- **Date:** 2026-08-24
- **PART:** Engine week (days 8–30 Atlas follow-up)
- **Supersedes:** nothing
- **Depends on:** [ADR 0052](0052-scale-invariant-shrinkage-is-a-named-option.md),
  [ADR 0064](0064-var1-on-hai-is-louder-than-snapshot-mahalanobis.md)

## Context

VAR(1) on HAI was louder than snapshot Mahalanobis (ADR 0064). The next Atlas question on
the same locked protocol was `ShrinkageTarget.CORRELATION` as a **named option**, not a
rewrite of `_shrink`. ADR 0052 already warned that path can inflate a continuous
attack-free holdout.

## Decision

1. `scripts/evaluate_atlas.py --correlation` scores `atlas-mahalanobis-correlation` only.
2. On HAI three-way (seed 11, threshold 3.0) the fit **refused**: 52-signal training
   covariance is singular at shrinkage **0.05** (condition number **3.85e+25**). No
   experiment-log row. See `eval_runs/atlas/hai-correlation-refuse.md`.
3. Do not raise shrinkage, drop redundant signals, or change the public default
   `AVERAGE_VARIANCE` to chase an invertible matrix. 646.58 stays the HAI Mahalanobis cell.
4. Do not stack BATADAL VAR. Dynamics already lost on this plant.

## Consequences

The snapshot ellipsoid with average-variance shrinkage remains the only HAI joint model
that actually scored. Correlation-target is a named option that this public split cannot
use at the frozen knob.

## Alternatives considered

- **Raise shrinkage until `_invert` succeeds.** Rejected. That is retuning `_shrink` on
  the public holdout.
- **Log a dummy FP/hour of zero.** Rejected. There was no detector.

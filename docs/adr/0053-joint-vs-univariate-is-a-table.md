# ADR 0053 — Joint vs univariate is a table, not a 10× stamp

- **Status:** Accepted
- **Date:** 2026-08-23
- **PART:** Category programme Session C4
- **Supersedes:** nothing. ADR 0049 already forbade the stamp. This record publishes
  the table the scorecard asked for, from measurements already on disk.
- **Depends on:** [ADR 0009](0009-joint-modelling-per-signal-attribution-and-the-model-that-lost.md),
  [ADR 0025](0025-joining-batch-distillation-without-poisoning-the-false-positive-ruler.md),
  [ADR 0046](0046-data4cyber-track-a-is-process-phase-telemetry-not-a-control-room-ruler.md),
  [ADR 0049](0049-split-scorecard-public-files-vs-partner.md)

## Context

The cycle asked for ≥10× joint vs univariate on every dataset. Public files gave
**13.0×** (HAI three-way), **8.6×** (distillation), **6.6×** (Data4Cyber Track A),
and on BATADAL the per-signal Gaussian was already quiet (~0.06 FP/hour) while
Mahalanobis sits at ~0.11 — a **loss** on the false-positive axis, with the win
on recall instead.

Session C4 asked for one table, process types already in hand, label semantics
named. Not a pooled "Atlas is 10×." Not fetching SWaT. Not collapsing 3W to attacks.

## Decision

Publish `PUBLIC_JOINT_VS_UNIVARIATE` in `src/phos/eval/joint_table.py`. Each row
names corpus, process type, Gaussian FP/hour, joint FP/hour, ratio, recall kind,
and whether FP/hour may be quoted as a control-room ruler. Tests pin the frozen
numbers. Encyclopedia volume 11 carries the same table.

Ratios may miss 10×. Data4Cyber stays 6.6× with the ruler **refused**. Distillation
recall is **perturbation**. HAI recall is **attack**. Data4Cyber recall is
**process-phase**. BATADAL is included as the water-distribution row already scored.

## Consequences

- There is no `pooled_ten_x`. Completing C4 does not earn the old stamp.
- 3W remains Session C9. Live session after this record is **C5** (dynamical residual).

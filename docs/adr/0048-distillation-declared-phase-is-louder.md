# ADR 0048 — Distillation's declared recipe step exists; phase-conditional modelling is louder, not quieter

- **Status:** Accepted
- **Date:** 2026-08-23
- **PART:** Cycle evaluation campaign (Atlas)
- **Supersedes:** [ADR 0031](0031-distillation-budget-refused-without-declared-phase.md)
  on the clause "until a declared phase exists". The ungated pooled Mahalanobis **18.72**
  FP/normal-hour row is unchanged.
- **Depends on:** [ADR 0018](0018-phase-conditional-modelling-for-a-batch-process.md),
  [ADR 0025](0025-joining-batch-distillation-without-poisoning-the-false-positive-ruler.md),
  [ADR 0031](0031-distillation-budget-refused-without-declared-phase.md)

## Context

ADR 0031 refused the ≤2–3 actionable alerts/day contract on batch-distillation because the
prepared CSV had no `phase_feature` for `PhaseConditionalModel` to route on. It left an
explicit next measurement: *if the operation logs declare a phase, measure that model — do
not quieter-pool `joint_k` or `dwell`*.

The operation logs were on disk the whole time (`07_…_Tabular_Operation_Logs`, 106 CSVs).
They declare **`Executing step`** events with plant-published names (`Druck`, `Heat1`–`Heat10`,
`Distillation`, `End`, `Heat`, `ANOMALIE`). Jump conditions, warnings, and operator-UI
tokens (`H701 new step`, `Selected recipe steps`) are not that register. Preparation never
joined them. That was the code defect ADR 0031 was waiting on, not a missing model.

A second declared grouping key sits in the path: `operating_point_NNN`. ADR 0025 refused to
write it as a numeric column because the CSV adapter would treat it as a process signal.
`Dataset.without_features` now drops routing registers from pooled comparison models so that
column can exist without silently rewriting the 18.72 row.

## Decision

1. **Join `Executing step` as `recipe_step`.** Last-observation-carried-forward onto the 1 Hz
   clock. Named steps are 1-based ordinals over a sorted vocabulary. **Ordinal 0 means "the
   log did not name a step"** — a real register value, not a hole. Encoding those rows as
   NaN made `vectorise` drop 92% of training timestamps from the phase-conditional fallback
   (the fallback spans the register; a sparse NaN is a missing signal). That interaction is
   a defect; the 0-sentinel is the fix. UI-only logs still contribute no named step.

2. **Join `operating_point` from the directory name.** Always present. Pooled Gaussian / PCA /
   Mahalanobis drop both registers via `without_features`.

3. **Measure `PhaseConditionalModel` with `settling_window=0`.** The first number is
   per-phase covariance, not the batch-reactor settling allowance imported from ADR 0019.
   Detector names are new (`atlas-phase-conditional`,
   `atlas-phase-conditional-operating-point`). The ungated pooled row is not overwritten.

4. **The 2–3/day contract stays refused.** The reason is no longer "missing column". Both
   declared routing keys **raise perturbation recall and explode false positives**.

Designed protocol, seed 11, threshold 3.0, dual-clean train / labelled test, perturbation
recall (never attack recall). Pooled Mahalanobis reconfirmed at **18.72** FP/hour, recall
**0.603**.

| Detector | Perturbation recall | FP/normal-hr | vs pooled |
| --- | ---: | ---: | ---: |
| `model:atlas-mahalanobis` (pooled, registers dropped) | 0.603 | **18.72** | — |
| `model:atlas-phase-conditional` (`recipe_step`) | 0.748 | **235.64** | 12.6× louder |
| `model:atlas-phase-conditional-operating-point` | 0.741 | **140.40** | 7.5× louder |

Named executing-step coverage after stride: **842 / 10,918** train rows, **15,154 / 39,664**
test rows. Fifteen declared names. Most dual-clean train experiments have no `Executing step`
token at all; Heat1–Heat9 in the OP001 log sit **before** that experiment's sensor clock
starts. `operating_point` covers every row; 23 of 63 test experiments share an operating
point with dual-clean train, 40 fall back to an unlearned point.

On the dummy batch reactor, pooling mixed CHARGE with idle and the shrinkage floor swallowed
every band (ADR 0018). Distillation's pooled model already detects. Conditioning on a
sparsely trained recipe step, or on one training run per operating point, tightens bands
until ordinary test traffic looks out of band. Recall is not free.

## Consequences

**Gained.** The logs were read. The authorized model was scored. ADR 0031's "until" is
closed. The 18.72 row still compares.

**Cost.** Cross-plant 2–3/day still has no batch-column exemplar. Tuning `dwell_samples` or
`joint_k` on this louder detector to chase the budget remains forbidden. Do not invent a
phase from correlations. Do not pool this recall with attack recall.

**Unchanged.** CERT 6B @ 48, known-station command lead 0/16, unknown-master unique lead 1/4,
Data4Cyber 6.6×, S7 unlabelled Track A. Hypothesis confidence still uncalibrated.

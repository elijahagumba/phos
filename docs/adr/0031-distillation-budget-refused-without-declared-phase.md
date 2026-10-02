# ADR 0031 — The 2–3/day budget is refused on batch-distillation until a declared phase exists

- **Status:** Accepted
- **Date:** 2026-08-22
- **PART:** Cycle evaluation campaign (Atlas)
- **Supersedes:** nothing
- **Depends on:** [ADR 0018](0018-phase-conditional-modelling-for-a-batch-process.md),
  [ADR 0025](0025-joining-batch-distillation-without-poisoning-the-false-positive-ruler.md),
  [ADR 0026](0026-joint-distance-gating-and-the-actionable-alert-unit.md)

## Context

The cycle contract asks for ≤2–3 actionable Atlas alerts/day-equivalent on public process types.
Batch distillation is the first non-water public plant. Ungated Mahalanobis posted ~449/day
(perturbation recall 0.60). Joint-moment gating posted ~49/day (perturbation recall 0.29).
Neither is the budget. ADR 0018's per-phase models exist in code and are unused here because
the prepared CSV has **no phase feature Atlas may route on**.

Raising the training quantile, or turning on dwell, to chase 2–3/day on a pooled envelope
would spend more perturbation recall for a number that still would not be phase-conditional
modelling. Inventing a phase from correlations would violate declared-topology discipline
(ADR 0010's spirit: do not infer the recipe from the wiggles).

## Decision

**The 2–3/day contract is refused on this corpus until the operation logs declare a phase
register Atlas can route on.** The gated ~49/day row remains the honest operating point.
`dwell_samples` stays 1 on public distillation logs. ADR 0018 is not "the next threshold";
it is blocked on a missing column.

If a later read of the operation logs produces a declared phase, this record is superseded
by a measurement of `PhaseConditionalModel` on that column — not by a quieter pooled gate.

## Consequences

**Gained.** The sprint cannot claim the budget on distillation by configuration.

**Cost.** Cross-plant "usable FP rates" still has no batch-column exemplar at 2–3/day.
That gap is named rather than tuned away.

**Unchanged.** Perturbation recall is still not attack recall. The ungated 18.72/hour row
stays comparable.

**Later measurement (ADR 0048).** The operation logs do declare `Executing step`. Joining
that register and scoring `PhaseConditionalModel` **raised** perturbation recall (0.60 →
0.75) and **raised** false positives (18.72 → 235.64 /hour). The 2–3/day refuse stands;
the missing-column clause of this record is superseded.

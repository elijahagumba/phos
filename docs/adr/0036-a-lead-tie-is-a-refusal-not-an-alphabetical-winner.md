# ADR 0036 — A lead tie is a refusal, not an alphabetical winner

- **Status:** Accepted
- **Date:** 2026-08-22
- **PART:** Command-lead mechanical honesty, session 1 (tie-break resolution)
- **Supersedes:** nothing
- **Depends on:** [ADR 0008](0008-template-based-hypotheses-log-odds-belief-and-the-residual.md),
  [ADR 0034](0034-command-lead-rate-zero-on-known-link-writes.md),
  [ADR 0035](0035-unknown-master-writes-still-do-not-lead.md)

## Context

ADR 0034 measured known-station command lead **0 of 16**. ADR 0035 measured unknown-master
command lead **0 of 4**, scored apart. Both reports named `engineering_maintenance` as the
unique leader when attack and maintenance saturated at the log-odds ceiling.

That unique leader was not an evidential win. `rank_explanations` and
`ReasoningEngine._ranked` both sorted `(-confidence, template_id)`. Saturated confidences
are equal, so alphabetical order made `engineering_maintenance` first and
`unauthorised_control_activity` second. Constitution §3.7 requires a reproducible order.
It does not license a fake winner. The product sells the right to remain silent.

Known-link unexpected function still supports both explanations (ADR 0014). Unknown-master
writes still contradict maintenance (ADR 0027) and still did not uniquely lead (ADR 0035).
This record does not retune those matchers or priors.

## Decision

**When two or more contentful hypotheses share the lead, do not emit a unique leader.**

Share means: within a declared `LEAD_TIE_EPSILON` (`1e-9`) of `CONFIDENCE_CEILING`, or —
away from the ceiling — within that same epsilon of the current top confidence. The epsilon
is numerical, not fitted on D2. Do not widen it to manufacture leads or blanket refusal.

`tied_lead_ids` in `phos.reasoning.belief` is the shared rule.

- **Breaking harness.** `rank_explanations` still lists `(-confidence, template_id)` so two
  runs agree. It records `tied_leaders`. `leads` / `newly_leads` are false when the set is
  non-empty. Residual is **not** inserted into that listing: inserting it would shift the
  attack's ordinal and erase "moved up" comparisons. Silence is the `tied_leaders` field
  and the false `leads` bit.
- **Reasoning engine.** `competing()` and narratives raise `insufficient_evidence` to the
  front when the lead is tied. The residual is the reported leader. The tied explanations
  stay in the set, listed in the same deterministic order underneath. `overall_confidence`
  is the residual's confidence — reconstructable, and not a pick between the rivals.

**Do not invert `template_id` so the attack wins ties. Do not lower the maintenance prior.**
Those would be the other fake winner.

Known-station **0/16** and unknown-master **0/4** remain the last harness rows (ADR 0034,
ADR 0035). This session did not remeasure them. Completing it does not earn ≥70%. A
breaking-harness ordinal is not a field detection rate.

## Consequences

**Gained.** Saturated attack vs maintenance is a refusal, not an alphabetical maintenance
win. The operator-facing competing set names "insufficient evidence". The measurement
`leads` stays false when they share the ceiling. Determinism is preserved: the tied ids
are a sorted set, and the listing under the residual is still `(-confidence, template_id)`.

**Cost.** A unique strong leader is unchanged. Mid-range equals (gap ≤ `1e-9`) also refuse;
a gap of `1e-6` is still a unique lead. Session 2's silence flood and session 3's causal
drowning are unaddressed. The cycle contract remains unearned.

## Alternatives considered

- **Invert alphabetical order so `unauthorised_control_activity` wins.** Forbidden. That is
  the same fake winner with a preferred name.
- **Lower the `engineering_maintenance` prior.** Template cheat. ADR 0014's remaining limit
  would be quietly lost.
- **Put known-link `unexpected_command_function` on maintenance-contradict.** Weakens
  indistinguishability to chase 70% on D2 (ADR 0034).
- **Insert `insufficient_evidence` into the breaking `templates` tuple.** Would shift the
  attack's rank and make "moved toward attack" lie about the command path.
- **Fit epsilon on the unknown-master battery.** Would be a D2 knob, not a numerical
  declaration.

## When to revisit

When a licence-confirmed public command capture is scored with issuer kinds apart, or when
labelled explanation data exists to calibrate hypothesis confidence (ADR 0008). Not when D2
`newly_leads` flips.

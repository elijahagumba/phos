# ADR 0059 — Explanation geometry is fixture-first; prior-only is silence; work orders are an inlet

- **Status:** Accepted
- **Date:** 2026-08-23
- **PART:** Category programme Sessions E1–E3
- **Supersedes:** nothing
- **Depends on:** [ADR 0036](0036-a-lead-tie-is-a-refusal-not-an-alphabetical-winner.md),
  [ADR 0057](0057-command-behaviour-is-a-stamp.md)

## Context

Templates cannot become reliable by rewriting priors. Public ICS does not label
"this window was maintenance." Partner work orders do not exist in this repository.

## Decision

1. **E1.** One-transmitter vs plant-wide demand: fault vs disturbance is ordered
   from grouped evidence shape (`SubsystemBreadthPattern`), not a new prior. HAI
   remains attack/normal, not explanation-labelled.
2. **E2.** `prior_only_rivals`: if two operational hypotheses carry the same
   evidence lists, `rank_hypotheses` raises `insufficient_evidence` even when
   priors would pick a unique winner. The breaking harness is unchanged (D2
   ordinals stay 0/16 and 1/4). Residual-first is not unauthorised-control lead.
3. **E3.** `promote_work_orders`: empty inlet is a no-op. A stamped work-order
   fact supports `engineering_maintenance` and contradicts
   `unauthorised_control_activity`. Command-graph structure patterns exclude
   that stamp so the two facts do not overlap. Work orders are not invented from
   process clocks.

## Consequences

- High-reliability explanation split on public files remains unearned.
- Partner-shaped sanction is a fixture until real tickets arrive.

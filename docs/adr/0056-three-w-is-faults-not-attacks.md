# ADR 0056 — 3W is a fault process type, not an attack row

- **Status:** Accepted
- **Date:** 2026-08-23
- **PART:** Category programme Session C9
- **Supersedes:** nothing. Restates [ADR 0033](0033-three-campaign-licences-confirmed-and-what-they-still-cannot-be.md)
  in executable form.
- **Depends on:** ADR 0033, [ADR 0040](0040-no-labelled-public-command-corpus.md),
  [ADR 0053](0053-joint-vs-univariate-is-a-table.md)

## Context

3W Petrobras is licence-confirmed CC-BY-4.0. Payloads are `files: []`. Classes 1–9
are faults. `default_attack_when(1)` is True; collapsing those classes to attack
would be a false statement.

## Decision

1. `phos.eval.three_w`: class 0 is normal; 1–9 are faults; `is_attack_class` is
   always false; `prepare_attack_track()` raises.
2. The joint-vs-univariate table grows by process type **offshore-wells** as
   `THREE_W_OFFSHORE_WELLS`: files absent, no invented FP/hour, not a cyber claim,
   not a command corpus.
3. Registry `attack_values` stays empty.

## Consequences

- Fault recall must never be quoted as attack recall. Completing C9 does not earn
  command 70% or 2–3/day.

# ADR 0297 — Build brief E is closed, without a stronger engine

- **Status:** Accepted
- **Date:** 2026-10-21
- **PART:** Build brief E, the close
- **Supersedes:** nothing
- **Depends on:** [ADR 0273](0273-the-stronger-engine-programme-is-declared.md),
  [ADR 0276](0276-lane-1-met-its-bar-on-held-out-runs.md),
  [ADR 0286](0286-an-appended-column-cannot-win-a-slot-without-taking-the-alert.md),
  [ADR 0288](0288-the-linear-predictors-misfit-is-load-bearing.md),
  [ADR 0293](0293-step-0284-would-reproduce-the-frozen-alerts-on-a-process-table.md),
  [ADR 0294](0294-three-rescues-are-refused-and-lane-2-stays-a-question.md),
  [ADR 0296](0296-legal-flow-does-not-give-breadth-the-catches.md)

## Context

ADR 0273 set the goal as an Atlas significantly stronger than the frozen v1 detector, pursued
in four lanes, then assembled and looked at once on the corpora where the old numbers live.
v1 stays 8 of 12. `atlas-v1-consistency` was not edited.

## Decision

**Build brief E is closed. The stronger engine was not reached. This record is not a new
roadmap.**

Lane 1 was kept. On a simulated plant, held out, attacks caught went from 49 of 120 to 87 of
120, and reconnaissance from 0 of 20 to 20 of 20. The gain is attribution, and an attacker at
the operator's console defeats it (ADR 0276). It keeps the name it already has.

Lane 2 stayed undeclared. A coordinated small bias was caught by the frozen engine on its
ordinary columns (ADR 0285). The attack this plant can actually host, a level bias with legal
flow, was scored on development runs: breadth caught 15 of 32 attacks and the frozen engine
16 of 32 (ADR 0296). The 3–8% band was not changed. Held-out3 was not opened.

Lane 3 was refused. A running tally caught 53 of 70 against 32 and arrived later (ADR 0286).
Lane 4 was refused. A bending prediction got quieter and caught fewer (ADR 0288).

The combined candidate was not assembled. The one look at the seen corpora was not taken,
because on a process table the kept lane would reproduce the frozen alerts (ADR 0293). The
three ways of keeping a loss were refused (ADR 0294). Reserved numbers 0277–0284 stay
unwritten. They are not a queue.

P1 stays blocked on a human conversation. This close does not start Intelligence, an API, or a
UI, and it does not authorise a successor brief.

## Consequences

A session that opens `docs/build-brief-2026-10-e.md` is reading a finished programme. The
sentence that says to start there is historical. The next scientific step, if there is one, is
one question declared before it is measured. It is not a new four-lane plan, and it is not a
filled-in 0277.

v1 stays 8 of 12. No corpus on the never-read list was opened. `eval_runs/log.jsonl` was not
appended. Simulated results in this programme remain diagnosis, not proof.

## What would reverse this

A new brief, with its own ADR, its bars written before any measurement, and its own numbers.
Filling 0277–0284 does not reverse this. Those numbers belong to the programme that just closed.

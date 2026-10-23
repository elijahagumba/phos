# ADR 0298 — Five questions succeed the closed stronger-engine programme

- **Status:** Accepted
- **Date:** 2026-10-21
- **PART:** Atlas roadmap F
- **Supersedes:** nothing
- **Depends on:** [ADR 0297](0297-build-brief-e-is-closed-without-a-stronger-engine.md)

## Context

ADR 0297 closed build brief E. The stronger engine was not reached, and that record said a
new brief could exist only with its own ADR and with bars written before measurement. This
is that brief. It does not reopen 0277–0284.

The five capabilities were proposed as the technical roadmap. Each names a weakness in the
evidence we have. None of them is a result.

## Decision

**The live programme is `docs/atlas-roadmap-2026-10-f.md`. It is five questions and one
evaluation. It assumes none of them will work.**

The order is fixed. Capability 1 is first, and its first task is an evaluation set plus one
score of the frozen detector, declared before that score. No new detector is built in that
step. Capabilities 2, 3 and 4 wait. Capability 5 waits on feedback we do not have. The
flagship evaluation waits on a candidate worth freezing.

The primary bar of that evaluation, written before any run, is both of: more labelled
attacks caught than frozen Atlas inside the same alert budget, and false alerts per
operating hour no higher. The budget is 8 alerts a shift unless a later declaration changes
it before the run. A gain on one half is not a pass.

Fences that travel with the questions:

- Lane 3's 53 of 70 does not transfer to a new incident linker (ADR 0286, ADR 0294).
- Phase-conditional distillation was louder (ADR 0048). A regime model does not assume the
  opposite.
- Uncalibrated confidence is not surfaced. The Kelmarsh confidence test did not meet its bar.
- Seen HAI editions, BATADAL, and spent ICSSim held-outs stay spent. `phos-icssim-heldout2`
  and `phos-icssim-heldout3` stay unopened until named.
- `mimic_maintenance` is not rewritten. `atlas-v1-consistency` is not edited.
- P1 is not unblocked. Intelligence, an API, and a UI do not start.
- Simulated results stay diagnosis. v1 stays 8 of 12.

## Consequences

A session reads the roadmap, then writes the capability 1 declaration, then stops until that
declaration is committed. The empty numbers of brief E are still not a queue.

## What would reverse this

A measurement run before its declaration. A pass declared on one half of the primary bar.
A successor that fills 0277–0284. Promoting capability 5 on simulated operator clicks and
calling it a deployed improvement.

## Correction, 22 October 2026

ADR 0300 opens the daily leap contract. The Consequences section, which says to stop after
the capability 1 declaration, is amended there. The decision text is left as written.
Roadmap F is not edited. Day 1's evaluation set is ADR 0301, committed before any generation
or score.

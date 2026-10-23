# ADR 0300 — A kept day halves the remaining misses

- **Status:** Accepted
- **Date:** 2026-10-22
- **PART:** Atlas daily leaps
- **Supersedes:** nothing
- **Amends:** the "then a stop" consequence of [ADR 0298](0298-five-questions-succeed-the-closed-stronger-engine-programme.md)
- **Depends on:** [ADR 0297](0297-build-brief-e-is-closed-without-a-stronger-engine.md),
  [ADR 0298](0298-five-questions-succeed-the-closed-stronger-engine-programme.md)

## Context

Build brief E closed without a stronger engine (ADR 0297). The one kept gain was a new
observation: control traffic, scored apart from the frozen detector, took held-out attacks from
49 of 120 to 87 of 120 and reconnaissance from 0 of 20 to 20 of 20 (ADR 0276). The lanes that
retuned the same residual were refused. A tally caught more and arrived later (ADR 0286). A
bending predictor got quieter and caught fewer (ADR 0288). Breadth on the attack this plant can
host caught 15 of 32 against the frozen engine's 16 (ADR 0296).

ADR 0298 opened five questions and stopped the next session after a declaration for the first.
The goal now is a kept leap every day. Five kept days cut the remaining misses of the classes
they covered by 32 times, because each kept day halves what is left. That arithmetic is the bar.
It is not a result. Nothing in this record was measured.

## Decision

**The live programme is `docs/atlas-daily-leaps.md`. A kept day halves the remaining misses of
one declared class, inside 8 alerts a shift, with false alerts per operating hour no higher
than the champion that day.**

The champion for a class is whichever of `atlas-v1-consistency` and `atlas-command-consistency`
catches more of that class on the development battery named in that day's declaration. Misses
are counted against it. A tie on misses keeps the lower false-alert rate, and a tie on both
keeps the frozen detector.

A day is kept only when all of these hold. A tie on misses is a miss.

1. `M_new <= floor(M_champion / 2)` on the class that day named.
2. False alerts per operating hour are no higher than that champion's, on the same runs.
3. The alert budget stays 8 per shift.
4. On attacks both catch, the new alert is not later than the champion's. The time used is the
   earliest budgeted alert inside the event window.

Only a kept detector becomes the next champion. A refused day stays in the record and stays out
of the product. The mechanism that missed is not retried the next day.

`mimic_maintenance` is reported when a scenario contains it and is not a miss the leap has to
halve. Telemetry and commands already failed to separate it from genuine maintenance (ADR 0276).
`recon` is already 20 of 20 on the kept command detector, so it is not a day's class. `mixed`,
`mixed2`, and `mixed3` stay reproducible and are not extended.

Development seeds may be iterated. A held-out look happens after two kept leaps, on a freshly
generated held-out named in its own declaration. `phos-icssim-heldout`,
`phos-icssim-heldout2`, and `phos-icssim-heldout3` stay spent or unopened as ADR 0298 left
them. Seen HAI editions and BATADAL stay unread. Simulated results stay diagnosis until that
held-out look.

`atlas-v1-consistency` is never edited. Each leap is a new module and a new result name.
`eval_runs/log.jsonl` is not appended. v1 stays 8 of 12. P1 stays blocked. Intelligence, an
API, and a UI do not start. Reserved numbers 0277–0284 stay unwritten.
[`docs/atlas-roadmap-2026-10-f.md`](../atlas-roadmap-2026-10-f.md) is not edited. Its first
question is day 1 of this programme, declared separately.

The order of classes is fixed in the programme document: an in-range command, then a sub-floor
setpoint walk, then a joint command vector, then incident packing, then a checkable report on
a kept detector. A regime model waits until a kept leap needs one. Phase-conditional
distillation was louder (ADR 0048). Quietness alone does not promote a regime candidate.

One declaration each morning names the class, the seeds, both champion scores, the detector
mechanism, the bar, and the fallback, and is committed before any generation or score. The
score decides whether the predeclared build runs. It does not redesign the build.

## Consequences

Day 1 is the next record. It declares the evaluation set and the champion command. It does not
contain a measurement, and it does not add a detector.

The five questions in ADR 0298 stay questions. The sentence that told a session to stop after
the capability 1 declaration is the sentence this record amends.

## What would reverse this

A leap claimed on one half of the bar. A mechanism retried the day after it missed. A held-out
corpus opened on a day that has not kept two leaps, or a spent look opened again. An edit of
`atlas-v1-consistency`. Filling 0277–0284. Surfacing uncalibrated confidence. Starting
Intelligence, an API, or a UI.

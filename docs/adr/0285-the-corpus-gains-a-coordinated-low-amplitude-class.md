# ADR 0285 — The ICSSim corpus gains a coordinated low-amplitude class, on new seeds

- **Status:** Accepted
- **Date:** 2026-10-21
- **PART:** Atlas, stronger-engine programme, the corpus
- **Amends:** [ADR 0122](0122-a-phos-generated-icssim-corpus.md)
- **Depends on:** [ADR 0273](0273-the-stronger-engine-programme-is-declared.md),
  [ADR 0276](0276-lane-1-met-its-bar-on-held-out-runs.md)

## Context

Every attack class in the corpus moves one thing: a frozen reading, an offset reading, a valve
mode, a burst of polling. Lane 2 therefore could not be judged — it exists for an attack spread
across many signals, none individually large, and tied the frozen engine at 24 of 60 with no such
attack to find (`eval_runs/build/lane-e/lane2-development.md`). Lanes 3 and 4 target shapes a
single-signal corpus cannot contain either: a slow accumulation, and a non-linear response.

This record adds one class. It does **not** change `mimic_maintenance`: that class is correct as
built, separable only by the missing work order, and a test of criterion A5's CMMS inlet rather
than of the command path (`docs/build-brief-2026-10-e.md`).

## Decision

**1. The class: `creep_many`.** Several instruments report a small steady bias at the same time,
while the plant underneath carries on normally. It is a calibration or sensor-bias attack, the
kind that moves a process off target without any single reading looking wrong.

**Defined on physical grounds, never on a detector's threshold.** Each affected instrument
reports `value x (1 + f)` for the event, with `f` drawn per signal from **3% to 8%**. A
multiplicative bias is what a miscalibrated or tampered transmitter actually does, it scales with
the reading so no range table is needed, and it is stated about instruments rather than about any
alerting level. The signals are the four continuous readings — `tank_level_value`,
`tank_output_flow_value`, `bottle_level_value`, `bottle_distance_to_filler_value` — and the number
affected is drawn from 3 to 4. Duration is drawn from 300 to 900 simulated seconds.

The percentages are a statement about instruments, not about Atlas. **No magnitude in this record
was chosen by running a detector against it**, and none may be adjusted after one is. If the
class turns out to be trivially caught, or never caught, that is the result.

**2. It is an attack**, added to `ATTACK_KINDS` and to a **new** scenario, `mixed2`: nine events
over 9000 simulated seconds. The frozen `mixed` scenario is unchanged at eight events over 7200,
because a ninth event does not fit two hours — the schedule refuses, which is how this was found
— and because lane 1's held-out score rests on runs that must stay reproducible.

**3. New seeds, because the generator changes.** The same seed produces different runs under a
changed generator, so the existing corpus cannot be extended in place:

| Role | Directory | Seeds |
| --- | --- | --- |
| Development | `phos-icssim-dev2` | 3 `normal` 96201–96203, 10 `mixed` 96211–96220 |
| Held out | `phos-icssim-heldout2` | 20 `mixed` 96301–96320 |

**4. The existing corpus is frozen as a record, not deleted.** `phos-icssim-dev` and
`phos-icssim-heldout` stay exactly as they are. Lane 1's held-out score (ADR 0276) rests on them
and must remain reproducible. Nothing is regenerated over them.

**5. `phos-icssim-heldout2` is generated and not opened** until a lane's own declaration names
it, as `data-tiers.md` requires. Generating is not opening. It is added to the score-once tier in
that rule by this commit.

**6. Lane 1 is not rescored on it.** ADR 0276 stands as taken. A later lane may use the new corpus
for its own declared shot, and would report beside it that the two corpora differ.

## Consequences

Lanes 2, 3 and 4 become judgeable. The programme keeps one corpus whose results are already
recorded and one whose held-out half nothing has seen.

## What would reverse this

Adjusting any magnitude in this record after a detector has been run against the class, changing
`mimic_maintenance`, regenerating over the existing corpus, or opening `phos-icssim-heldout2`
without a declaration naming it.

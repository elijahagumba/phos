# ADR 0126 — Declared control loops narrow the level-form bar, and three testimony rules

- **Status:** Accepted
- **Date:** 2026-10-15
- **PART:** ADR 0123, before step 3
- **Amends:** [ADR 0123](0123-the-plant-map-proposed.md) §3 (the first rule) and §5.2 (its first
  two checks); [ADR 0125](0125-a-drop-one-check-is-decisive-or-inconclusive.md) §2
- **Depends on:** [ADR 0124](0124-the-plant-map-is-built-and-fits-in-seconds.md),
  [ADR 0125](0125-a-drop-one-check-is-decisive-or-inconclusive.md)

## Context

ADR 0125 found that its drop-one rule could not pass the controlled tank, because the map had
learned the wrong tank. ADR 0123 §3 bars every preliminary descendant of *y* from *y*'s level
form, so that a controller driven by a false reading cannot vouch for it. On the tank, the valve
and the inflow each predicted the other, so each was barred from the other's level form: the
inflow lost its only real driver, the valve, and the quality signal lost the level it follows.
Then a lying level had no downstream witness, a lying inflow meter was invisible, and the level
was wrongly blamed for the inflow's lie at 5 of 20 rows.

The bar is right where a loop is. It is wrong everywhere else: two signals that merely echo each
other are not a controller and its reading. Elijah chose on 15 October to narrow it to declared
loops rather than remove it.

## Decision

**1. Control loops are declared, like roles.** A role file may list `[[loops]]`: a name, where it
is stated, the statement, the reading it holds, the actuators it moves, and its setpoint, each
only where the statement names it. The loader refuses a loop that names neither a reading nor an
output, a signal outside the corpus, or a signal in the wrong role (a reading must be a sensor,
an output an actuator, a setpoint a setpoint). Loops are documentation, never inferred.

- **HAI 20.07:** the six loop statements of the manual (pp. 7–11), transcribed from the `loop`
  lines the role file already carried. P1-PC, P1-LC, P1-FC and P1-TC name their reading and
  valves. P2-SC names a reading and no output; P3-LC names outputs and no reading. Neither is
  completed from tag names.
- **The test tank:** its one loop, as its docstring states it.
- **The synthetic plants and ICSSim declare none yet.** The synthetic plants' `CONTROL`
  couplings are declared, but ADR 0123 §3 keeps couplings for checking the map, never as input,
  so they are not read as loops here. Using them is a separate decision, before the liar
  measurement uses the map.

**2. The level-form bar.** A corpus with no declared loop keeps ADR 0123's rule unchanged. One
with loops bars, from the level form of the reading a loop holds, the loop's outputs and every
signal they reach in the preliminary graph, whether or not a path from the reading exists. Where
a loop names no reading, the same set is barred from the level form of every signal with a path
into its outputs. Where a loop names a reading but no output, that reading keeps ADR 0123's rule.
Every other signal is barred from nothing. The increment form is unchanged: what a controller
does still enters as a cause of the reading's change.

**3. Three testimony rules**, each found on the tank and each argued on its own:

- **A drop-one model with no driver left is inconclusive.** It can only say the candidate is
  within its normal range, which says nothing about the link it dropped.
- **A candidate's driver is judged without the candidate.** If the driver's own model uses the
  candidate, the candidate's lie would leave the driver out of band, and "its drivers are in
  band" would fail because of the lie it is testing. The driver is judged by its model without
  the candidate.
- **A drop-one model explains a candidate away only as a single liar can.** ADR 0125 let any
  decisive drop-one in band block naming. It now blocks only when it is the **only** decisive
  drop-one in band and its driver is **not itself in band** (judged without the candidate). Two
  decisive drop-ones in band contradict each other as single-liar explanations: if *k* lied, the
  model without *j* still holds *k* and should disagree. A driver that agrees with its own
  drivers is no liar to blame. Without this, a held reading was "explained away" by whichever
  flow its drop-one models happened to ignore.

Nothing else in §5 changes.

## Results (the fixture only; no slice scored)

The two ADR 0125 tests pass, with all 22 plant-map tests. The same checks on fixture seeds the
tests do not use (11–15), with two training seeds (1 and 2):

| Training seed | Lying level named, within the calibrated free run | Another instrument named | Inflow meter lies: level wrongly blamed | Inflow named |
| --- | ---: | ---: | ---: | ---: |
| 1 | 54 of 55 rows | 0 | 0 of 100 | 98 of 100 |
| 2 | 55 of 55 | 0 | 0 of 100 | 98 of 100 |

Before this record, on seed 3: 3 of 19 and 5 of 20 wrongly blamed (ADR 0125). Beyond the
fixture's calibrated free-run time (1,200 s), the reconstruction's band is unknown, the
downstream witness is not judged to agree, and the level is left unnamed: by design, never a
wrong name.

**HAI 20.07, training files only, refitted** on this record's build container (4 cores, Linux;
not the §9.10 machine): 14.8 s. 31 signals mapped and 73 links, against ADR 0124's 32 and 85.
Two changes matter for step 3:

- `P1_FT03` (the reading of loop P1-FC) is no longer mapped. Its old model came from its own
  loop's valve, `P1_FCV03D` and `P1_FCV03Z`, which is the echo the bar exists to stop. A falsified
  `FT03` now gets no reconstruction rather than one that repeats the lie.
- The loop readings stay barred from 35 to 37 of 59 signals each in level form, because their
  valves reach most of HAI's preliminary graph. On HAI the bar narrows little for the loops it
  protects; it frees the signals outside them.

ADR 0124's §9.10 record (6.7 s, from `3f05cbb`) stands as measured. The 30-minute bar is not in
question.

## Consequences

- Step 3 starts from this rule. §9.7 (a wrong name in more than 10% of caught runs) is the
  measure of whether the testimony rules are right beyond one tank.
- **The risk is a rule fitted to its fixture.** Each refinement was found on the tank. The guard
  is that each has its own argument above, that unseen seeds agree, and that HAI development
  slices judge it next. If §9.7 fails, these rules are the first suspects.

## What would reverse this

Inferring a loop from data or a tag name; reading the synthetic couplings as loops without a
record; letting a loop bar anything from an increment form; or changing any of the three
testimony rules after a development score has been seen.

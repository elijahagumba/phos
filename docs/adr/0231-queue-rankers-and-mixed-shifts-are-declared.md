# ADR 0231 — The queue rankers and the mixed shifts are declared before they run

- **Status:** Accepted
- **Date:** 2026-10-19
- **PART:** Build brief D, lane Q
- **Depends on:** [ADR 0212](0212-a3-queue-rank-is-declared.md)

## Context

The HAI 20.07 diagnosis is already committed. The champion's own order is 19 of 38.
A shuffle from `numpy.random.default_rng(97651)` is 7 of 38. An oracle that puts every
true alert before every benign alert, inside each shift, is 21 of 38, and that 21 is the
ceiling: one attack has no alert, and every other miss is a shift with more attacks than
top-10% slots. Recall within 8 alerts a shift is 37 of 38 for the champion and for the
oracle. The two attacks the oracle saves, and only those two, sit in `test1.csv.gz` shift 0.
The benigns in their slots are unfamiliar column-sets whose shape is "everything moved
together" and whose explanation probe supports `process_disturbance` without contradicting
it. One of the two true alerts is a witness disagreement with no strong innocent member.
The other has the same shape as the benigns in front of it.

Nothing in this record is a score of a ranker, and no mixed-queue seed has been generated.

## Decision

**What a ranker is.** It reorders the frozen champion's alerts. It does not add one and it
does not remove one. The champion, its thresholds, its windows and its fit stay as they are.

**Six variants.** Each keeps the champion tiebreak: higher champion score, then earlier
timestamp, then earlier input order. The extra keys are 0/1 priorities, written here, not
coefficients fitted to a result. An alert is familiar when its member-column set equals a
column set of a champion event on the training rows whose onset is not an attack. It is a
witness when the onset cell's calibrated loop score is above the frozen threshold and at
least the range score. It has a strong innocent member when `sensor_or_device_fault`,
`engineering_maintenance` or `process_disturbance` is supported by the probe below and not
contradicted. The probe weighs a subsystem event of the member signals, a
`cross_signal_mismatch` fact on the onset signal when the alert is a witness, and a
work-order fact when a sanctioning order covers the alert's timestamp. Each fact has weight
1. That weight is a structural probe. It is not a calibrated confidence, and no confidence
is reported.

| Variant | Earlier in the queue |
| --- | --- |
| `familiarity` | unfamiliar, then familiar |
| `innocent` | no strong innocent member, then one |
| `cross-path` | witness, then everything else |
| `familiarity-cross` | unfamiliar, then witness, then the champion score |
| `cross-innocent` | witness, then no strong innocent member, then the champion score |
| `all-three` | unfamiliar, then witness, then no strong innocent member, then the champion score |

**What they are predicted to do, before the run.** On HAI 20.07, `familiarity` does not
move the two recoverable attacks, because those benigns are not familiar; recall within 8
should stay 37 of 38, because the only familiar true alert is already outside the top 8.
`cross-path` and `innocent` can move the witness true alert at position 5 into a slot, and
they cannot, on these features, prefer the together-shaped true alert at position 6 over
the together-shaped benigns. Either may also push a together-shaped true alert out of the
top 8. A variant whose recall within 8 falls on HAI 20.07 or on seeds 97651–97670 is
rejected. Among the rest, the one frozen for the held-back look is the greatest A3 pass
count on seeds 97651–97670, then the greater HAI A3, then the earlier row in the table.

**Seeds.** `QUEUE_DEVELOPMENT_SEEDS` is 97651–97670. `QUEUE_HELD_BACK_SEEDS` is 97601–97620.
They are disjoint from each other and from the blocks already in `build_seed_blocks`.
97651–97670 may be generated and scored more than once. 97601–97620 are not generated until
a later record names the frozen ranker, the command, the result name and the bar.

**Generator.** In memory, not under `data/`. Plants cycle with the seed: 97651 and 97601
are `water-treatment`, the next seed `power-generation`, the next `batch-reactor`, and so
on. Sample periods are the ones already used for these plants: 30 s, 10 s and 60 s.
Windows are `windows_for_period` of that period and are not retuned. The champion is
`atlas-v1-consistency`, fit on a quiet run of seed 97001 for that plant: 24 hours, no
injection, no work order, attack flags clear. Each scored seed is one 8-hour shift starting
at 2026-10-01 00:00 UTC. The plant's own scheduler supplies the benign process events. One
sanctioning routine work order, `WO-{seed}`, covers hour 1 through hour 5 on the plant's
first declared unit (`intake`, `turbine`, `reactor`). The attack is `HoldReading` on the
frozen sensor for that plant (`filtered_turbidity_ntu`, `transformer_oil_temp_c`,
`reactor_temp_c`), held at the low end plus 0.9 of the span, from hour 6 through hour 8.
The attack window is that hold. The work order does not overlap it.

## Consequences

The next step is to implement these six reorderings and score them on HAI 20.07 and on
97651–97670. Seeds 97601–97620 stay ungenerated. The real-data gate is not this record.

## What would reverse this

Generating a held-back seed before its declaration, changing a priority after a development
score, or editing the champion to make a variant pass.

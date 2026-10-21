# Lane 2 on the ICSSim development corpus — no gain, no cost, and untested rather than refuted

**Date:** 2026-10-21 · **Development data only.** `phos-icssim-heldout` was not read.
**Not declared, not frozen.** Simulated, so diagnosis and not proof (R4, ADR 0143).
`eval_runs/log.jsonl` was not appended and no v1 number moved.

Command: `uv run python scripts/lane_e_icssim_baseline.py`
Detector: `phos.atlas.breadth_consistency` — one extra column, the sum over signals of each
signal's score capped at `THRESHOLD`, so breadth across instruments can drive it and depth in one
cannot. Calibrated by the engine's own third-largest-training-peak rule and run through the
unchanged `events` and `budget_alerts`.

## Result

| Class | Frozen | Lane 2 | Of |
| --- | ---: | ---: | ---: |
| `liar_offset` | 10 | 10 | 10 |
| `rogue_command` | 7 | 7 | 10 |
| `replay` | 4 | 4 | 10 |
| `liar_freeze` | 3 | 3 | 10 |
| `mimic_maintenance` | 0 | 0 | 10 |
| `recon` | 0 | 0 | 10 |

**24 of 60, identical to the frozen engine in every class. Benign events drawing an alert: 4 of
20, also unchanged.**

## Why, and what it does and does not mean

Lane 2 exists for an attack spread thinly across many signals, none of them individually over the
threshold — the shape `phos.atlas.consistency` cannot see because it opens an episode only where
one signal alone crosses. **This corpus contains no such attack.** Every class in it moves one
thing: a frozen reading, an offset reading, a valve mode, a burst of polling. There is no
coordinated low-amplitude manipulation for a breadth column to find, so it never wins a budget
slot that a signal column had not already won.

So the lane is **untested, not refuted**. Nothing here says breadth is a bad idea; it says this
corpus cannot ask the question, exactly as the synthetic plants could not ask lane 1's.

It is also **free**: the column costs no false alarm and displaces no catch. An idea that neither
helps nor hurts on the only corpus available is not a reason to keep carrying it, and not a
reason to throw it away either.

## What would test it

A declared attack class that moves several signals, each by less than the alerting threshold.
That is a change to ADR 0122's generator and belongs with the `mimic_maintenance` change the lane
1 work already found necessary (`eval_runs/build/lane-e/lane1-development.md`): two separate
reasons the corpus needs extending before it can judge this programme's harder claims.

Until then lane 2 is **not declared**, ADRs 0277 and 0278 stay unwritten, and 24 of 60 is
recorded as a tie rather than quoted as a result either way.

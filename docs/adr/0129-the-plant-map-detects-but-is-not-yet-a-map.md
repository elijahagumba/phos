# ADR 0129 — Step 3's report: the plant map detects the liar, but by its own falsifiers it is not yet a map

- **Status:** Accepted (a report; it decides nothing beyond what ADR 0123 §9 already decided)
- **Date:** 2026-10-15
- **PART:** ADR 0123 step 3, before the red team
- **Depends on:** [ADR 0123](0123-the-plant-map-proposed.md),
  [ADR 0127](0127-the-arena-scores-the-plant-map-challenger.md),
  [ADR 0128](0128-icssim-roles-loops-and-the-development-slice.md)

## Context

ADR 0127 declared the arena task and ADR 0128 the ICSSim slice before any score. This record
reports attempt 1 (ADR 0123's settings unchanged) on every development slice, and every §9
falsifier that can be judged before the red team. All figures are development diagnosis on
synthetic or emulated data (R4); nothing is a result, and nothing was appended to
`eval_runs/log.jsonl`. Raw records: `eval_runs/arena/plant-map/` and `eval_runs/plant-map/dev/`.

## What was measured

**The arena (attempt 1).** `atlas-plant-map-v1` passes **55 of 90** liar runs (water 22 of 30,
power 14, batch 19), against the champion's 24 (water 0, power 12, batch 12), reproduced in the
same run. **No champion pass is lost.** HAI 20.07: **37 of 38**, the champion's figure. Under
ADR 0127's rule the configuration qualifies.

**Chance** (added after attempt 1, as diagnosis, ADR 0109's zero-magnitude control on the same
layout): the predicate passes 9 of 90 for the champion (water 0) and 15 of 90 for the challenger
(water 3). The challenger promotes more facts outside attack windows (water: 8 to 9 per corpus
against the champion's 3), and a liar window is three hours long, so some of its passes are
chance. Its margin over chance (40) is still well above the champion's (15).

**The replace arm** (map and range only, diagnosis): 45 of 90, HAI 20.07 37 of 38. The map alone
detects.

**ICSSim** (development, 10 mixed runs, 20 liar events): the challenger raises a budgeted alert in
all 20 liar windows, the champion in 11. On the 50 events where the readings are true, the
challenger alerts in 22 (champion 15); of the benign ones, maintenance raised an alert in 5 of 10
(champion 3) and a setpoint change in none.

## The falsifiers

| § | Falsifier | Measured | Verdict |
| --- | --- | --- | --- |
| 9.1 | Water level reconstructed in increment form from its flows or pump, and closer to the truth than `loop_expectation` | Increment form, raw inflow its driver; within 10% of normal range on 65% of falsified samples against 28%, median error 0.091 against 0.273 | **Passes** |
| 9.2 | At least 24 of 90, water above 0 | 55 of 90, water 22 | **Passes** |
| 9.3 | Red team | Not run | — |
| 9.4 | HAI 20.07 at least 37 of 38 | 37 of 38 | **Passes** |
| 9.5 | Half the declared pairs recovered, and half the learned links on a declared path, on each synthetic plant | Recovered 47% (water), 64%, 59%; on a path 42% (water), 50%, 41% (batch) | **Fails** (water both; batch on paths) |
| 9.6 | 70% of links in both halves' maps; at most 30% of shared links differing in lag by over a grid step | 41 shared of 71 and 80: 37% of the union, 58% of the smaller; 15% differ in lag | **Fails** on sharing |
| 9.7 | Right instrument in 70% of caught development liar runs, a wrong one in at most 10% | Arena 41 of 85 (water 22 of 26, batch 19 of 29, power 0 of 30); ICSSim 4 of 20; together 45 of 105, 43%. Wrong: 2 of 105 | **Fails** on the right name; passes on wrong names |
| 9.8 | A lying instrument named in at most 1 event in 10 where the readings are true (ICSSim) | 1 of 50 | **Passes** |
| 9.9 | The true value inside the band 90% of the time, at nominal 99% | Water 100%, batch 94%, power 0.4%; ICSSim freeze 95%, offset 74% | **Fails** (power; ICSSim offset) |
| 9.10 | A fit within 30 minutes on a laptop | 6.7 s (ADR 0124) | **Passes** |

## What ADR 0123 §9 says these mean

ADR 0123 fixed the consequences before anything was built, and they are applied here unchanged:

- **9.2 and 9.4 pass, 9.3 is unrun:** the challenger may still become a candidate, through the
  red team and then ADR 0117's gate.
- **9.5 and 9.6 fail: "the method is wrong; PCMCI+ is then the next method."** The links are
  not a property of the plant: half of HAI's links change between its two training files, and on
  the synthetic plants fewer than half of the learned links follow the declared plumbing. It
  predicts well enough to detect, but **Atlas must not say which signals drive which.**
- **9.7 and 9.9 fail: "the map may detect, but must not name instruments or emit
  reconstructions."** Where it names, it is rarely wrong (2 of 105, and 1 of 50 on true readings),
  but it names the right instrument in under half of caught runs, and its band does not hold on
  the power plant or on ICSSim's offset liar.

## Where it works, and where it does not

- **The water liar, the case ADR 0123 was written for, works.** The champion catches none of its
  30 runs. The challenger passes 22, names the clearwell level in 22 of 26 caught runs, rebuilds
  its true value more than twice as accurately as the loop, and its band covers the truth on
  every falsified sample.
- **The power plant fails differently.** Its liar target, `feeder_voltage_kv`, is a reading its
  tap changer follows, so §5.3's rule reads the event as "reading true, plant changed" in every
  run, the reconstruction misses by a median 239 units, and the map never names it. Its passes
  (14) come from the loop.
- **ICSSim's offset liar** is the limit ADR 0124 named: "true value minus a constant" keeps every
  change, so an increment model sees only its onset and its anchored reconstruction drifts.

## Decision

Nothing is promoted, emitted or changed by this record. The red team is **not** run: ADR 0127
holds it until Elijah has read this report. The five remaining configurations are unspent.

Three paths are open, for Elijah to choose:

1. **Red-team attempt 1 as a detector only.** Its facts would then carry the champion's
   `loop_expectation` band, not the map's reconstruction, and name no link or instrument, which
   is what §9.5–9.9 allow. A separate short record would say so before the red team runs.
2. **Spend the remaining configurations** on the map's stopping rule and caps (fewer, stronger
   links), the ones most likely to move §9.5 and §9.6, before any red team. Its §9 thresholds do
   not move.
3. **Take ADR 0123's own exit:** PCMCI+ under its own record, after its licence is verified.

## What would reverse this

A §9 threshold moved after these figures; the red team run before Elijah's choice; or a naming or
reconstruction emitted to an operator while §9.5–9.9 stand failed.

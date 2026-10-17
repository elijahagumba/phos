# ADR 0134 — The red team, and the trusted map's first naming: both fail, for reasons now known

- **Status:** Accepted (a report)
- **Date:** 2026-10-15
- **PART:** ADR 0123 §9.3; ADR 0130 falsifiers 3 to 5
- **Depends on:** [ADR 0127](0127-the-arena-scores-the-plant-map-challenger.md),
  [ADR 0131](0131-stricter-links-do-not-stabilise-the-map.md),
  [ADR 0133](0133-grades-a-and-d-and-naming-on-trusted-links.md)

## The red team (ADR 0123 §9.3)

Attempt 1, the only qualifying configuration, was scored once on `RED_TEAM_SEEDS` (95101–95110,
180 runs) beside the champion, on Elijah's instruction to keep working towards ADR 0130's goal.
Record: `eval_runs/arena/plant-map/red-team.json`.

| | Passes | Water | Power | Batch |
| --- | ---: | ---: | ---: | ---: |
| Champion | 53 | 0 | 28 | 25 |
| `atlas-plant-map-v1` | **116** | **47** | 34 | 35 |

**Verdict: fails.** It loses 2 runs the champion passes (power, seeds 95107 and 95110, subtlety
0.4), and §9.3 allows none. The rule stands as written. On those two runs the challenger's map
reads the feeder current's event as "reading true, plant changed" and promotes the loop's facts on
the feeder voltage as the champion does; the exact difference in the competing hypotheses was not
isolated.

**A reproducibility finding.** The champion's power passes differ from ADR 0121's red team on the
same seeds (53 against 52: four runs gained, three lost, all power), and from the water-liar
task's arena champion by one power run each way. Scored twice in this container, every pass
repeats exactly; the difference is in the corpora, regenerated here rather than on the machine
ADR 0121 used. Within one run both detectors see identical corpora, so this comparison is fair.
Comparisons across machines on the power plant are not, until the generator is shown to be
platform-independent.

## The trusted map (ADR 0130 falsifiers 3 to 5, ADR 0133)

Record: `eval_runs/plant-map/dev/graded-model.json`.

| Falsifier | Measured | Verdict |
| --- | --- | --- |
| 3. D keeps at least a quarter of HAI's links, and passes §9.5 on each synthetic plant | HAI 23 of 73 (32%). Stable links on a declared path: water 78%, power 58%, batch 53%; declared pairs among them: water **21%**, power 64%, batch 59% | **Fails** (water recovers too few) |
| 4. The trusted map names right in 70%, wrong in at most 10% | **0 of 105 right, 21 wrong (20%)** | **Fails** |
| 5. The water liar's target has an A-to-C driver | Yes: raw inflow and distribution flow | Passes |

D does what ADR 0130 hoped on precision: stable links lie on the declared plumbing far more often
than the full map's (water 78% against 42%). It keeps too few of them on water to pass.

## Why the trusted map names nothing right (diagnosis, development data)

- **Water: a witness too vague to testify.** The clearwell's only downstream signal in the
  trusted map is chlorine residual, linked weakly (share 0.051). It sits inside its band whether
  the level reading is true or false, so §5.3 counts it as agreeing with the reading and decides
  "reading true, plant changed" at every caught run. The full map gave the clearwell no such
  witness and named it in 22 of 26.
- **Batch: consequences named instead of the cause.** The controller follows the lying reactor
  temperature, so the jacket temperature, jacket flow and reactor pressure really change. The
  trusted map names them, the plant's response, rather than the reading upstream that caused it.
- **ICSSim:** the tank level has no A-to-C driver (ICSSim declares its loops, not its physics),
  so it cannot be placed, as designed.

## Decision

ADR 0129's restriction stands for both maps: detection only, no naming or reconstruction shown to
an operator. Both failures have specific causes, and each matches a principle already in the
design: ADR 0125's decisive-or-inconclusive test, and ADR 0123 §5.2's "a controller downstream of
a reading follows it". The next record proposes those rules and fresh red-team seeds before
anything is scored again.

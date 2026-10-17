# ADR 0131 — Stricter links do not stabilise the map; attempt 1 stays the chosen configuration

- **Status:** Accepted (a report)
- **Date:** 2026-10-15
- **PART:** ADR 0123 step 3, before the red team
- **Depends on:** [ADR 0127](0127-the-arena-scores-the-plant-map-challenger.md),
  [ADR 0129](0129-the-plant-map-detects-but-is-not-yet-a-map.md),
  [ADR 0130](0130-the-graded-plant-model.md)

## Context

ADR 0129 found the map's links unstable (§9.5, §9.6). The cheapest explanation was a stopping
rule too permissive: weak terms admitted by chance in one training file and not the other.
Elijah chose on 15 October to test it with the arena's unspent budget. Three stricter
configurations were declared in `cd40f40` before any was scored, and each was given every §9
measure (`scripts/plant_map_dev.py --candidate`).

## What was measured

| Attempt | Overrides | Liar passes (water) | Champion passes lost | HAI 20.07 | HAI links shared, of union / of smaller | Arena names right / wrong (caught) | ICSSim liar caught |
| --- | --- | ---: | ---: | ---: | --- | --- | ---: |
| 1 | none | 55 (22) | 0 | 37 / 38 | 37% / 58% | 41 / 2 (85) | 20 of 20 |
| 2 | `min_gain` 0.03 | 29 (0) | 1 | 36 / 38 | 38% / 57% | 12 / 17 (73) | 18 of 20 |
| 3 | `min_gain` 0.05, 4 drivers | 28 (0) | 1 | 37 / 38 | 37% / 56% | 17 / 14 (72) | 17 of 20 |
| 4 | `min_gain` 0.05, 3 drivers, 1 lag | 21 (0) | 3 | 36 / 38 | 37% / 59% | 0 / 11 (68) | 10 of 20 |

Learned links on a declared path (§9.5), water / power / batch: attempt 2 40% / 54% / 48%, attempt 3 46% / 59% / 50%,
attempt 4 45% / 60% / 59%; declared pairs recovered 42% / 50% / 55%, 37% / 50% / 41% and 32% / 50% / 55%.

## Findings

- **Stricter selection does not make the links stable.** The share of HAI 20.07's links that
  appear in both training files' maps stays at 37–38% of the union whatever the stopping rule.
  The instability is not weak terms crossing a threshold by chance; it is what co-movement alone
  can and cannot identify, as ADR 0130 argues.
- **It costs the one thing that worked.** Every water pass rested on the clearwell's inflow link,
  which removes only 2.2% of the level's error. Any stopping rule above 0.022 drops it, and water
  falls back to 0 of 30. That the decisive link is also a weak one is itself a reason the map
  must say how it knows each link.
- **Fewer links make naming worse, not better.** Wrong names rise from 2 to 17, 14 and 11, past
  §9.7's 10% bar: with fewer drivers, the drop-one checks have less to stand on.

## Decision

Under ADR 0127's unchanged rule, **attempt 1 is the only qualifying configuration, and it stays
the chosen one.** The two remaining runs are left unspent: the stopping rule is shown not to be
the lever, and spending them on the other overrides would be searching, not testing. §9.5–9.9
stand failed for every configuration, so the map may detect but not name or reconstruct (ADR
0129). The next step for structure is ADR 0130's graded model, whose first step (grade C on
ICSSim) is built. The red team for attempt 1 as a detector is still Elijah's call.

## What would reverse this

Choosing a configuration other than attempt 1 under ADR 0127's rule, or spending the remaining
runs without a stated hypothesis.

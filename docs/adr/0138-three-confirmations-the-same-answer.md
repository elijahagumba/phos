# ADR 0138 — Three confirmations, the same answer: double the catches, two losses, water solved

- **Status:** Accepted (a report)
- **Date:** 2026-10-15
- **PART:** ADR 0137's confirmation; the arena task `plant-map` closes
- **Depends on:** [ADR 0134](0134-red-team-and-the-trusted-map-first-results.md),
  [ADR 0136](0136-the-confirmation-water-works-the-bars-are-not-met.md),
  [ADR 0137](0137-smooth-weights-and-a-third-confirmation.md)

## The third confirmation (attempt 6, `CONFIRM_SEEDS_2`, once)

Records: `eval_runs/arena/plant-map/red-team-confirm-2.json`,
`eval_runs/plant-map/dev/*-candidate-6-confirm-2.json`. One corpus
(`t1-liar-water-treatment-s95310`) was unmeasurable for both detectors (ADR 0137's amendment),
so 174 runs were scored.

| | Champion | Attempt 6 | Verdict |
| --- | ---: | ---: | --- |
| Liar passes | 43 | **103** (water 41, champion 0) | — |
| Champion passes lost | — | 2 (batch 95308 at 0.4, power 95306 at 0.4) | **Fails** §9.3 |
| Full map names right / wrong, caught | — | 82 / 10 of 173 (47% / 6%) | **Fails** §9.7 on right |
| Trusted map names right / wrong | — | 82 / 24 of 193 (42% / 12%) | **Fails** both |
| Water named right / wrong | — | **44 / 0 of 53** | — |
| Band coverage: water / batch / power | — | 99.9% / 89.5% / 0.4% | **Fails** |

Platt weights removed the three power losses they were diagnosed on (ADR 0137), but on fresh
seeds the challenger again loses one power run and one batch run.

## Across all three held-back sets

| Set | Champion | Challenger | Water (champion → challenger) | Champion passes lost |
| --- | ---: | ---: | --- | ---: |
| `RED_TEAM_SEEDS` (attempt 1) | 53 | 116 | 0 → 47 | 2 |
| `CONFIRM_SEEDS` (attempt 5) | 50 | 113 | 0 → 49 | 2 |
| `CONFIRM_SEEDS_2` (attempt 6) | 43 | 103 | 0 → 41 | 2 |
| **Together, 534 measurable runs** | **146** | **332** | **0 → 137** | **6** |

On the water liar, across the three sets, the challenger passes 137 of 174 measurable runs where the champion
passes none. On the two sets where naming was measured, the right instrument is named in 91 of 107
caught runs (85%) with **none** wrong, and the true value lies inside the band on 99.9% of
falsified samples.

## Findings

- **The result is stable.** Three sets of seeds that no rule saw give the same answer: more
  than twice the champion's passes, and two of its passes lost each time, six of 146 in all.
- **The losses are not one cause.** Calibrator ties explained the first power losses, and
  removing them did not remove losses on new seeds. Batch losses are undiagnosed. At least two
  champion passes examined (ADR 0137) cite facts on a setpoint or a neighbouring signal rather than
  the liar's target, so part of what the zero-loss rule protects is the champion passing for the
  wrong reason. That is recorded as an observation, not used to excuse a loss.
- **Water is solved, power and batch are not.** The pattern of ADR 0136 repeats exactly.

## Decision

The arena task `plant-map` closes with its six runs spent. Under the rules as written, nothing is
promoted: §9.3 fails on every set, §9.7 and §9.9 fail pooled. ADR 0129's restriction stands.

Two questions are now Elijah's, because they are policy, not measurement, and each needs its own
record before any further score:

1. **The zero-loss rule.** Whether a detector that catches 332 where the champion catches 146,
   losing 6, should be judged by a rule that allows a declared, small loss beside a large gain.
2. **Scope.** Whether a capability proven on one class of plant (a level integrating its flows,
   held by a controller that follows the reading) may be offered for that class alone, with the
   others stated as not yet covered.

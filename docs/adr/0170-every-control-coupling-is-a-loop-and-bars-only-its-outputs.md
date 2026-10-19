# ADR 0170 — The lane E explainer reads every control coupling as a loop, and a loop bars only its outputs

- **Status:** Accepted (development result; held-back look later, after its own declaration)
- **Date:** 2026-10-18
- **PART:** Build lane E, target 2 (naming the sensors the explainer skipped)
- **Depends on:** [ADR 0123](0123-the-plant-map-proposed.md),
  [ADR 0126](0126-declared-loops-narrow-the-level-form-bar.md),
  [ADR 0135](0135-decisive-witnesses-and-upstream-first.md),
  [ADR 0161](0161-the-plant-map-names-the-champions-alerts.md)

## Context

Lane D's explainer (`lane-d-plant-map-explainer`, ADR 0161) names the lying sensor on
`atlas-v1-consistency`'s alerts. On development seeds 97001–97020 it named 96 of 156 caught runs
across nine sensor types, and named one wrongly. Three sensors failed for two reasons, found by
reading the failing cells:

- **Chlorine residual and distribution pressure had no model at all** (`no_model` on 20 of 20).
  Each is the reading a water loop holds. ADR 0126 bars the loop's outputs *and every signal they
  reach in the preliminary graph* from that reading's level form. Water's preliminary graph is
  connected, so the dose and the booster reach all eleven other signals. Both readings were barred
  from everything, and their increment forms chose no term.
- **Reactor pressure was unnamed on 14 of 20 and wrongly reconstructed on 4.** Batch declares no
  loop. Its three `CONTROL` couplings each name several sensors, or no setpoint, so lane D's rule
  (exactly one sensor and one setpoint) built none. With no loop, ADR 0123's first rule bars every
  preliminary descendant, and pressure was left with an increment model only. Held at 10.8 bar
  (training never exceeded 2.5), the increment model is out of band at the onset row (score 26)
  and back in band at later alert rows (score 0.06 to 1.0), because a flat reading has flat
  increments.

## Decision

A new explainer, `lane-e-loop-explainer` (`phos.atlas.loop_explainer`), changes two things.

1. **Every `CONTROL` coupling whose driven signal is an actuator is a loop.** Lane D's loops are
   kept exactly. Any other control coupling becomes a loop that names its output and no reading.
   It names a setpoint only when the coupling names exactly one. Nothing is inferred from a key's
   spelling. ADR 0126 left using the couplings as loops to "a separate decision"; this is that
   decision, for this explainer only.
2. **A loop bars only its declared outputs** from the level form (`MapSettings.loop_bar =
   "outputs"`). The output is the echo ADR 0123 guards against: a controller moved by a false
   reading vouching for it. A signal further down the process follows the real plant, which the
   false reading contradicts. `MapSettings()` keeps `loop_bar = "reach"`, so the frozen map,
   ADR 0126's rule, lane D's explainer and every earlier record are unchanged.

The champion still decides every alert. The explainer does not add, drop or reorder one.

## Development result (seeds 97001–97020)

Measured by `uv run python scripts/lane_e_score.py --workstream naming` and `--workstream
naming-guard`, against lane D's explainer on the same alerts:

| Set | Lane D: named right | Lane D: named wrong | Lane E: named right | Lane E: named wrong |
| --- | ---: | ---: | ---: | ---: |
| The nine sensor types (target 2) | 96 of 156 (61.5%) | 1 | 153 of 156 (98.1%) | 0 |
| Every declared sensor (guard, not the target) | 310 of 460 (67.4%) | 8 | 398 of 460 (86.5%) | 7 |

Chlorine residual 0 → 19 of 20, distribution pressure 0 → 19 of 20, reactor pressure 1 → 20 of 20.
The other six are unchanged.

Two loops came first. Loop 1 changed only the bar (134 of 156, wrong 1). Loop 2 barred the outputs
and one more hop (129 of 156), and was reverted.

## Consequences

The bar of at least 70% named right across all nine, with no rise in wrong names, is met on
development. It is a synthetic diagnosis. These rules were found on development scores, so the
held-back seeds 97101–97120 judge them once, after a committed declaration. A pass would still not
show that the plant map names a liar on a real plant (ADR 0143).

## What would reverse this

A held-back result below 70%, or with more wrong names than lane D's explainer on the same seeds.
Inferring a loop's reading from a key's name. Changing `MapSettings()`'s default bar.

## Note at merge (19 October)

The reconstruction half of `docs/phos-2027.md` W2 was checked from `eval_runs/build/lane-e/`: on
the nine sensors the worst reconstruction was 0.045 of span on development and 0.042 on the
held-back seeds, inside the 10% bar on every one. With 146 of 150 held-back caught runs named right
and none wrong, **W2 is met on the synthetic plants.** It is a diagnosis on plants this repository
builds (ADR 0143), not a real-plant result.

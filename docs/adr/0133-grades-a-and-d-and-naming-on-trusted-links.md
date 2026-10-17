# ADR 0133 — Grades A and D, and naming on the trusted map, declared before they are scored

- **Status:** Accepted
- **Date:** 2026-10-15
- **PART:** ADR 0130 build order, steps three to five, before they are scored
- **Depends on:** [ADR 0130](0130-the-graded-plant-model.md),
  [ADR 0131](0131-stricter-links-do-not-stabilise-the-map.md),
  [ADR 0132](0132-grade-b-links-from-logged-changes.md)

## Context

Grades C and B pass their falsifiers on ICSSim (ADR 0130, ADR 0132). What remains of ADR 0130's
build order is grade A, grade D, and naming on the A-to-C links only, judged by its falsifiers
3, 4 and 5. This record fixes how, before anything is scored.

## Decision

**1. The code** is `phos.atlas.plant_model`. `fit_map` gains `allowed`, the only drivers each
target may use; nothing else in the map changes, and every existing test passes unchanged.

- **A, declared:** each declared loop's reading and setpoint to its outputs, and, where a corpus
  has them, its declared couplings. A declared pair that the full map learned only the other way
  round is contradicted and dropped.
- **D, stable:** a link learned by maps fitted on two disjoint halves of the same training data
  (alternate files when there are several; one file split at its middle otherwise), at lags within
  one grid step.
- **The trusted map:** `fit_map` refitted with each target allowed only its A-to-C drivers. A
  target with none has no model, and Atlas says it cannot place that reading.

**2. What each corpus can earn.**

| Corpus | A | B | C |
| --- | --- | --- | --- |
| Synthetic plants | Their declared couplings and loops (the plant's drawing) | None: no logged writes | None: no traffic in the liar corpora |
| ICSSim | Its declared loops | ADR 0132's links | ADR 0130's claims |
| HAI 20.07 | Its manual's loops | None | None |

Reading a synthetic plant's couplings as its drawing is the honest analogue of a design partner's
P&ID, and it ends their independence as a check on the trusted map. They remain an independent
check on D, which never reads them.

**3. Naming** runs at the events the full challenger (attempt 1) carries on the map, exactly as
ADR 0129 measured it, but on the trusted map: the first instrument it names inside a liar
window. Detection is unchanged.

**4. The verdicts**, ADR 0130's, unmoved. `scripts/plant_map_dev.py graded` measures all three
in one run, with attempt 1's settings.

- **Falsifier 3:** D keeps fewer than a quarter of the full map's links on HAI 20.07, or, on any
  synthetic plant, fewer than half of the declared pairs are among the stable links or fewer than
  half of the stable links lie on a declared path.
- **Falsifier 4:** pooled over the caught arena and ICSSim liar runs, the trusted map names the
  right instrument in under 70%, or a wrong one in over 10%.
- **Falsifier 5:** the water plant's liar target has no A-to-C driver, so the trusted map cannot
  place it.

## Consequences

- Run once after this record is committed. Whatever it finds is reported beside ADR 0129's
  figures for the full map.

## What would reverse this

Changing a grade's definition or a verdict's threshold after the score; letting D decide a
naming; or using ICSSim's truth (`phos.breaking.icssim_truth`) as a declaration.

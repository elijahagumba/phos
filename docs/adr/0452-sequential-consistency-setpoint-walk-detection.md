# Sequential consistency fix for setpoint_walk detection (ADR 0452)

**Status:** Declared  
**Date:** 2026-11-16  
**Part:** S6-S11  
**Phase:** Declare (five-phase cycle, phase 1 of 5)

## Hypothesis

The sequential consistency detector (`phos.atlas.sequential_consistency`) is wired into `phos.referee.detectors._build_sequential_detections` but only detects 30% of setpoint_walk attacks (70% missed). The detector fits a `SequentialModel` on the first half of each test plant's data and scores the second half, comparing run lengths against `model.longest_run` (the longest consecutive-change run in training). Two problems:

1. **Training on test data**: `fit_sequential` is called on the first half of the same plant being scored, not on a separate training plant. If the first half has any setpoint variation (even normal operator adjustments), `longest_run` is inflated, causing real walks in the second half to be missed.

2. **No margin on threshold**: Detection uses `scores[i, 0] > model.longest_run` with no margin. If training and test data have similar variation characteristics, walks that are only slightly longer than training runs are missed.

3. **No margin on threshold**: Detection uses `scores[i, 0] > float(model.longest_run)` with no margin. If training and test data have similar variation characteristics, walks that are only slightly longer than training runs are missed.

## Command

Fix `_build_sequential_detections` in `src/phos/referee/detectors.py` to:

1. **Fit the sequential model on a separate training plant** (not on the test data itself). Reuse the same training plant that `atlas_detector` uses in `demo.py` (seed 20261116, family level_flow), fitting the `SequentialModel` once at factory time and reusing it for all exam plants.

2. **Add a margin on the threshold**: Instead of `scores[i, 0] > longest_run`, use `scores[i, 0] > longest_run + margin` where margin is at least 1 sample (a legitimate write has run length 1, so any run of 2+ samples is already suspicious; requiring run length > training_max + 1 reduces false positives while catching walks).

3. **Use a fixed threshold from training data** rather than computing it per-plant from the test data itself, ensuring consistent detection across all exam plants.

## Result name

`sequential-consistency-fixed`

## Bar

Measured on development seeds (level_flow family, PHOS_SEEDS_DEV):

- **Kept**: The breaker run on dev seeds detects at least 50% of setpoint_walk attacks (up from 30%), with false alarm rate on benign dev plants unchanged from baseline.
- **Rejected**: The breaker run detects fewer setpoint_walk attacks than before, or false alarms increase significantly.
- **Refused**: The sequential module cannot be imported, the data lacks `tank_level_max`, or the bar cannot be measured on dev data.

A "previously-missed attack" is one that Round 1's breaker found (`physical_effect=True`, `detected=False`). Detection is defined as `detected=True` on replay.

## Constraints (all still in force)

- No changes to `src/phos/atlas/sentinent/` or other non-atlas modules — only changes to `src/phos/referee/detectors.py` and `src/phos/referee/demo.py`
  <!-- evidence-ack: src/phos/atlas/sentinent/ — never a path in any branch of this repository; the engine this constraint protects is `src/phos/sentiel/`, which is not under `atlas`, and the constraint held as written -->
- No changes to frozen numbers, frozen rows, or `eval_runs/log.jsonl`
- No red-tier corpus reads
- Everything simulated and offline (PART S0 rule 5)
- No ≥70%, 10×, or 2–3/day claims (execution master)

## Related

- ADR 0451: Wire Atlas consistency inlet into engine path (kept)
- ADR 00315: Walk column missed the same one (1 of 9 slow walks missed by frozen detector)
- `src/phos/atlas/sequential_consistency.py`: Existing sequential consistency module with `fit_sequential` and `sequential_scores`

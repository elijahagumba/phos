# ADR 0127 — The arena scores a detector configuration: the plant map's development budget

- **Status:** Accepted
- **Date:** 2026-10-15
- **PART:** ADR 0123 step 3, before any slice is scored
- **Depends on:** [ADR 0120](0120-the-arena-tasks-an-enforced-budget-and-a-fence.md),
  [ADR 0123](0123-the-plant-map-proposed.md),
  [ADR 0126](0126-declared-loops-narrow-the-level-form-bar.md)

## Context

ADR 0123 §8 asks, before any score, for a short record that extends the arena's candidate type
from a window set to a detector configuration, keeps its fence, budget and scorer pinning, and
declares the budget: at most six scored configurations of the map's parameters, then the red
team once. The challenger, its evidence and its place in the liar assembly are now built:
`phos.atlas.plant_map_detector` (ADR 0123 §7), `phos.atlas.plant_map_evidence` (§5, "The fact"),
and an optional plant map on the liar inlet. This record fixes how they are scored.

## Decision

**1. A candidate may be a detector configuration.**
`{"detector": "atlas-plant-map-v1", "map": {...}}` scores the challenger with overrides on ADR
0123's settings. Only its caps (`max_drivers`, `max_lags_per_driver`), stopping rule (`min_gain`)
and horizons (`horizon_seconds`, `form_horizon_seconds`) may be overridden; lags, bands, folds,
the ridge penalty and the free-run settings may not. Window-set candidates are unchanged. The
fence, the payload check and the hash-chained `AttemptLog` are the same code.

**2. The task and its budget.** Task `plant-map` (`experiments/arena/plant-map/task.json`), one
hypothesis, `plant-map-v1`, **six runs**. It cites the same learning records as `water-liar`
(mechanism `inlet_subthreshold`). Attempt 1 is ADR 0123's settings unchanged. The selection rule
is in the task's evaluation plan, fixed now: a configuration qualifies with at least 24 of 90
liar passes, water above 0 of 30, no champion pass lost, and HAI 20.07 at least 37 of 38; the
chosen one has the most passes, then the most water passes, then the fewest overrides. The red
team (`RED_TEAM_SEEDS`, once) runs only after Elijah has read the §9 report.

**3. How the liar slice assembles the challenger.** `fit_inlet` fits the champion exactly as
before and, given map settings, fits `atlas-plant-map-v1` beside it on the same attack-free corpus,
with windows by the corpus's sample period (ADR 0112). Its facts then replace the champion's in
both the calibrator's fit (development seeds 71001–71003, ADR 0114) and the scored runs. With no
map settings, every path is the champion's, byte for byte.

**4. The synthetic plants declare loops.** Elijah chose on 15 October to read each synthetic
plant's `CONTROL` couplings as ADR 0126's loops: one loop per sensor that drives a `CONTROL`
coupling, its driven actuator the output. A controller driven only by a setpoint or a phase holds
no reading and declares none. **The cost:** §9.5 compares learned links with the declared
couplings, and the `CONTROL` couplings now also shape which links the map may learn (they bar,
never add). §9.5 is reported with that noted.

**5. The development measures beyond the scorecard** are `scripts/plant_map_dev.py`, written to
`eval_runs/plant-map/dev/`:

| Measure | Falsifier | What it reads |
| --- | --- | --- |
| `liar` | §9.1, §9.7, §9.9 | Every arena liar run: caught, map-carried, the first instrument named inside the window against the recipe's target, whether a broken link involves the target, and, from `truth.csv`, the reconstruction's share of falsified samples within 10% of normal range and its band coverage, beside `loop_expectation` on the same samples |
| `map` | §9.5 | Each synthetic plant's learned links against its declared couplings |
| `halves` | §9.6 | HAI 20.07: one map per training file, the links both share and their lags |
| `replace` | §7 | The replace arm (map and range only), once on both slices, as diagnosis |

**6. ICSSim** (§9.7's second half, §9.8) needs an adapter from `process.csv` to the map, with
ICSSim's roles and loops declared from its own tag list and PLC logic. That is the next record;
the development corpus is being generated now.

**7. The scorer pin grows.** `SCORER_FILES` now includes the map's modules, the role loader, the
synthetic role adapter and HAI 20.07's role file. Every attempt from now on carries the new
sha256; attempts already logged keep theirs.

## Consequences

- Nothing is scored by this record. No frozen row, prior, detector constant or log line changes.
  The champion's paths are unchanged, and the full suite passes.
- After attempt 1 and the four measures, the §9 report goes to Elijah before any further
  configuration or the red team.

## What would reverse this

Overriding a setting outside §1's list; scoring more than six configurations; scoring the red
team before the report; reading a `validation` or `held-out` corpus; or changing the selection
rule after attempt 1 has been seen.

# ADR 0124 — The plant map is built, and fits HAI 20.07 in seconds

- **Status:** Accepted
- **Date:** 2026-10-13
- **PART:** ADR 0123, steps 1 and 2
- **Depends on:** [ADR 0123](0123-the-plant-map-proposed.md),
  [ADR 0010](0010-declared-topology-and-the-granularity-hai-supports.md),
  [ADR 0112](0112-consistency-windows-by-sample-period-and-one-batadal-score.md)

## Context

ADR 0123 was accepted on 13 October with its build order: declared roles, then the map, then
§9.10's fit time measured before any slice is scored. Elijah approved step 1's role file the same
day, with its seven unroled points as they are and load demands kept as setpoints.

## Decision

### 1. Declared roles (step 1, commit `78c07f2`)

`data/hai-20.07/roles.toml` declares a role for each of HAI 20.07's 59 columns from the
official point list (`hai_dataset_technical_details.pdf` at `2a814ceb`, sha256 `0668345c…`),
every row citing its table row and printed page. 24 sensors, 15 actuators, 13 setpoints, 7 with
no role. `phos.atlas.signal_roles` loads and validates a total role map.
`phos.breaking.declared_roles` reads the synthetic plants' roles (`SignalKind`) and couplings
from their own definitions; it sits outside `phos.synth` because the generator may not import
Atlas (`tests/synth/test_anti_bias.py`).

### 2. The map (step 2, commit `3f05cbb`)

`phos.atlas.plant_map` (with `_model`, `_fit`, `_select`, `_naming`) builds ADR 0123 §2–§6 as
written: lags 5–3600 s by ADR 0112's rule (a test checks it equals the frozen helper), two forms,
forward selection on five time-blocked folds from per-fold Gram matrices, caps of 6 drivers and 2
lags, a 1% gain stop, the frozen ridge, out-of-block bands per horizon, a drop-one band per link,
pass two without descendants, free-run bands, naming and reconstruction. Result name
`atlas-plant-map-v1`. `phos.atlas.consistency` is untouched; a test checks its scores are
identical before and after a map is fitted. No scorer file of ADR 0120 changed.

**One implementation decision ADR 0123 did not state: setpoints get no model of their own.**
The plant follows a setpoint. Predicting one from plant signals reverses that, and on the test
tank it created sensor → setpoint edges that made almost every signal a "descendant" of every
other, which stripped true drivers from level forms. Setpoints remain admissible drivers of
actuators, as §3 says. Drivers and targets also exclude signals with no role.

### 3. §9.10, measured before any slice

`scripts/plant_map_fit_time.py`, run once from commit `3f05cbb` with the map's files clean, on
HAI 20.07's `train1` and `train2` only (550,800 rows on disk; no test file read):

| | |
| --- | --- |
| Fit wall time | **6.7 s** (CPU 6.7 s) |
| Bar | 1,800 s. **Passes** |
| Machine | Mac16,13 (Apple M4, 10 cores, 16 GiB), macOS 26.3, Python 3.12.11, NumPy 2.5.1 |
| Mapped | 32 of 59 signals, 85 links |

| Section | Signals | Mapped | Links | Level form | Increment form |
| --- | ---: | ---: | ---: | ---: | ---: |
| P1 boiler | 31 | 21 | 61 | 15 | 6 |
| P2 turbine | 12 | 5 | 5 | 5 | 0 |
| P3 water treatment | 5 | 3 | 12 | 3 | 0 |
| P4 HIL | 11 | 3 | 7 | 1 | 2 |

Not mapped: the 7 unroled points, the 13 setpoints (§2), and 7 sensors or actuators for which
no term cleared the 1% gain: `P1_PCV02D`, `P1_TIT01`, `P1_TIT02`, `P2_VYT02`, `P4_HT_FD`,
`P4_ST_FD`, `P4_ST_TT01`. Every link is listed in `eval_runs/plant-map/fit-time-hai-20.07.json`.
Whether these links are the plant is §9.5 and §9.6's question, not this record's.

## Known limits, stated before step 3

1. **Seven HAI 20.07 points have no role,** so no model and no reconstruction: four operator
   buttons (`P2_Auto`, `P2_Emgy`, `P2_On`, `P2_TripEx`) and three columns the manual names no
   20.07 point for (`P2_VT01e`, `P3_LH`, `P3_LL`). A similar name is not taken as the same point.
2. **Load demands stay setpoints** (`P4_LD`, `P4_HT_LD`, `P4_ST_LD`), by ADR 0123 §3's reason:
   power follows demand, so demand would vouch for a falsified power reading. Revisited only with
   evidence, in its own record.
3. **§5.2's naming rule fails the controlled case.** On the test tank (a level integrating
   inflow minus outflow, a PI loop on the reported level, a liar held under the setpoint), the
   level's score rises to about 50 and reconstruction is within a tenth of the reported error and
   inside its band throughout. But both drop-one models are poor, because an integrating relation
   needs both flows, so their bands are wide; under the liar both fall back in band, both links
   count as broken, and the level never "disagrees with all its drivers". It was named at 1 of 20
   rows tried. `test_the_lying_level_is_named` pins this as a strict expected failure. Naming
   evidence in step 3 would inherit it; changing the rule needs its own record.
4. **A pure-offset liar is visible to an increment form only at its onset.** Reporting the true
   value less a constant preserves every change. ICSSim's `liar_offset` is of this kind; the
   synthetic library's liar (held under the setpoint) and `liar_freeze` are not.
5. **Two-way echoes block true relations.** When two signals predict each other (a level and
   a quality that follows it), pass one puts them in a cycle and each is excluded from the other's
   level form. This is ADR 0123's stated identifiability limit, met in practice.

## Consequences

- Nothing is scored. No slice, validation or held-out corpus was read. HAI 20.07's test files
  were not opened. Nothing was appended to `eval_runs/log.jsonl`.
- Step 3 (evidence promotion, the arena record, the development slices) waits for Elijah.

## What would reverse this

A slice scored before this record; a role inferred from a tag name; the naming test's expected
failure removed without a record that changes the rule; or a change to `phos.atlas.consistency`.

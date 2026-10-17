# ADR 0128 — ICSSim's roles and loops, and the plant map's ICSSim development slice

- **Status:** Accepted
- **Date:** 2026-10-15
- **PART:** ADR 0123 step 3, before the ICSSim slice is scored
- **Depends on:** [ADR 0122](0122-a-phos-generated-icssim-corpus.md),
  [ADR 0126](0126-declared-loops-narrow-the-level-form-bar.md),
  [ADR 0127](0127-the-arena-scores-the-plant-map-challenger.md)

## Context

ADR 0123 §8 names an ICSSim slice: liar events caught within 8 per shift, the instrument named,
the reconstruction against `truth.csv`, and, on the events where the plant really moves and the
readings are true, how often a lying instrument is named. It needs the development corpus
(ADR 0122, generated on 15 October) and declared roles. ADR 0127 left both to this record.

## Decision

**1. The roles and loops come from ICSSim's own source**, at the pinned commit, recorded in
`data/phos-icssim-dev/roles.toml`: the tag table in `src/Configs.py` (each tag's PLC and whether
it is a PLC input or output), the control programs `src/PLC1.py` and `src/PLC2.py`, and
`_check_manual_input` in `src/ics_sim/Device.py`. Each row quotes its source line, and every quote
was checked to occur in the file. Inputs are sensors; outputs a program sets are actuators;
outputs a program only compares a sensor with are setpoints. **A mode tag is a setpoint**: mode 1
forces its actuator off and mode 2 on, so it is a demand the actuator is asked to follow, and
maintenance (the output valve forced closed) is then explained by its own mode tag. Six loops,
one per sensor a program reads before it sets an actuator. Nothing is inferred from a tag's name.

**2. The reader** is `phos.breaking.icssim_runs`: one run's `process.csv`, `truth.csv` and
`events.json` as arrays, and a refusal to open anything under `phos-icssim-heldout`.

**3. The slice** is `scripts/plant_map_dev.py icssim`, on development runs only:

- **Training:** the three `normal` runs (96001–96003, 12 h), attack-free by construction. The
  champion and `atlas-plant-map-v1` (ADR 0123's settings, ADR 0127 attempt 1) are fitted on them
  with HAI's 1-second windows, because ICSSim samples once a second.
- **Scored:** the ten `mixed` runs (96011–96020), every event.
- **Measured:** liar events (`liar_freeze`, `liar_offset`) with a budgeted alert inside the
  window, for the challenger and the champion; on caught liar events, `tank_level_value` named
  (§9.7's right name) or another instrument named (its wrong name); the reconstruction's share of
  falsified samples within 10% of normal range of `truth.csv`, and its band's coverage (§9.9);
  and on `setpoint`, `maintenance`, `rogue_command`, `replay` and `mimic_maintenance`, the events
  naming a lying instrument (§9.8, at most 1 in 10) and those labelled reading true, plant
  changed (§5.3, recorded, not emitted).

An event's naming is the first map-carried event inside its window that names an instrument.

## Consequences

- The held-out ICSSim corpus stays ungenerated and unopened. The development runs may be scored
  any number of times (ADR 0122 §4), but this slice is run once for attempt 1's configuration,
  beside the other measures, before the §9 report.
- ICSSim's valves are on or off and its PLCs sample on a 200 ms cycle (ADR 0122 §5): reported and
  true values differ slightly outside any attack, and a linear map fits a switching plant poorly.
  Every figure is emulated diagnosis (R4).

## What would reverse this

A role or loop read from a tag's name or the data; opening the held-out runs; or changing the
slice's definition after its first result has been seen.

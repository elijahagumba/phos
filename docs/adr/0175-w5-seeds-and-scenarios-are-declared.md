# ADR 0175 — W5 seeds and scenarios are declared before any plant is built

- **Status:** Accepted (a declaration; nothing here is a score)
- **Date:** 2026-10-19
- **PART:** Round 3, Job 2
- **Depends on:** [ADR 0144](0144-the-october-build-is-declared.md),
  [ADR 0171](0171-explanation-confidence-is-calibrated-by-evidence-shape.md)

## Context

ADR 0171's held-back look had no wrong contentful lead, so it could not show
that a wrong explanation scores low. W5 needs a held-back set that contains
wrong answers. The calibration rule does not change: evidence shape, Laplace
`(right + 1) / (n + 2)`, high only when the Wilson 95% lower bound is at least
0.8. Priors, templates, `EVIDENCE_STRENGTH`, and `(-confidence, template_id)`
stay as they are. The calibrated number is not surfaced.

No plant for these seeds has been generated.

## Decision

### 1. Seeds

`W5_DEVELOPMENT_SEEDS` is 97401–97420. `W5_HELD_BACK_SEEDS` is 97501–97520.
Both sit in `build_seed_blocks`. A test checks each is disjoint from the other
and from every used set: T1's 94001–94020, `DEVELOPMENT_SEEDS`, the library
seeds, `ARENA_LIAR_SEEDS`, `RED_TEAM_SEEDS`, `CONFIRM_SEEDS`,
`CONFIRM_SEEDS_2`, `CONFIRM_SEEDS_3`, the ICSSim seeds, 97001–97020,
97101–97120, and the GRFICS seeds 97201–97210 and 97301–97310.

Development may be scored any number of times. Held-back is scored once, after
a later declaration names the command and the result. The quiet train the
detector fits is seed 97001, the champion's existing train seed. It is not a
W5 case.

### 2. Scenarios

Every seed runs all five kinds on `water-treatment`. Ground truth is not an
engine input.

| Kind | What is true | A contentful lead is right when |
| --- | --- | --- |
| `plain_sensor_fault` | Chlorine residual is held at 0 for the second half of the run. | The lead is `sensor_or_device_fault`. |
| `fault_and_maintenance` | The same chlorine hold, and a work order on filtration covering that window. The order does not replace the chlorine sensor. | The lead is `sensor_or_device_fault`. `engineering_maintenance` is wrong. |
| `subtle_liar` | Chlorine residual is reported at the quiet-train mean plus `k` declared noise standard deviations, `k` starting at 3. The instrument is lying; the plant is not. | The lead is `sensor_or_device_fault`. `process_disturbance` is wrong. |
| `two_sensors` | Chlorine residual and distribution pressure are both held at 0 for the second half. | The lead is `sensor_or_device_fault` and the supporting facts name both signals. Naming one is wrong. |
| `mimic_with_work_order` | A MIMIC moves the clearwell level setpoint with no legitimate write, inside a work order for filtration. | The lead is `unauthorised_control_activity`. `engineering_maintenance` is wrong. |

Silence (`insufficient_evidence`) is not a wrong lead and is not counted.
`k` for the liar may move on development seeds only. The kind list and the
right/wrong rule do not. Both are frozen in the held-back declaration before
that one score.

### 3. The bar

On the held-back block, after the map is fit on all twenty development seeds:

- High-confidence contentful leads are right at least 80% of the time. Zero
  high leads means the bar is not met.
- Wrong contentful leads are mostly low: at least 80% have calibrated
  confidence strictly below 0.5. The report also counts how many wrong leads
  fell in the high band.

Development is scored out of fold, one seed against the other nineteen, the
same way ADR 0171 scores.

## Consequences

These numbers are synthetic diagnosis. They are not a plant probability and
they are not shown to a user.

## What would reverse this

Generating a 975xx seed before its score declaration. Changing the shape
definition. Refitting the map on held-back leads.

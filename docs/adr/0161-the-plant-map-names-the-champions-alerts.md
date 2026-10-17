# ADR 0161 — The plant map names the champion's alerts

- **Status:** Accepted
- **Date:** 2026-10-17
- **PART:** October 2026 build, lane D, item 5 (W2)
- **Depends on:** [ADR 0125](0125-a-drop-one-check-is-decisive-or-inconclusive.md),
  [ADR 0135](0135-decisive-witnesses-and-upstream-first.md),
  [ADR 0143](0143-the-plant-map-fails-the-gate.md),
  [ADR 0144](0144-the-october-build-is-declared.md),
  [ADR 0160](0160-a-command-the-actuator-ignored.md)

## Context

W2 asks the plant map to name the lying sensor on the champion's alerts, and to reconstruct the
value the drivers imply. The alerts stay the champion's. ADR 0143 already recorded that
`atlas-plant-map-v1` does not improve detection on HAI or BATADAL. This measurement does not
reopen that gate, and it does not claim a detection gain on a real plant.

The champion stays `atlas-v1-consistency`. The map is a separate object, result name
`lane-d-plant-map-explainer`. `DEFAULT_SETTINGS` still names instruments with ADR 0125's rules.
Those rules, on a development probe, named water's filtered turbidity on 0 of 20 seeds. ADR 0135's
rules named it on 20 of 20. The explainer selects ADR 0135. The default object is not modified.

## Decision

### 1. What is explained

Roles come from the plant's signal table. The role is the declared `SignalKind`. The quote is the
signal's label. A control loop is a `CONTROL` coupling with one sensor, one setpoint, and an
actuator. A coupling with several sensors, or with no setpoint, is not turned into a loop.

The falsified reading is held at 90% of the way from the signal's low to its high, over the middle
third of the run. The true state keeps moving. Reconstruction error is the absolute gap between
the map's centre and that true value, divided by the signal's span.

A run is caught when the champion has at least one budgeted alert on the falsified column inside
that window. It is named right when every such cell is named as that column and each
reconstruction error is finite and at most 0.10. It is named wrong when any such cell is named as
a different instrument. The explainer does not add or drop an alert. `alerts_unchanged` re-reads
`budget_alerts` and requires the same rows and columns. The map is not an input to the champion.

The three subjects on the bar, one per plant, are filtered turbidity (water, 30 s, 900 samples),
transformer oil temperature (power, 10 s, 1200 samples), and reactor temperature (batch, 60 s,
700 samples). Six other sensors are surveyed and are not on the bar. The map's fold count is the
`MapSettings` default of 5. A probe at 3 folds named chlorine residual, and this run does not.
Folds were not changed to recover it.

The champion and the map are fit on quiet seed 97001 only.

### 2. The bar

Each of the three frozen plants must name at least 70% of its caught runs, with reconstruction
error at most 10% of span, and with the champion's alerts unchanged. The scorecard's
`naming_right` is the lowest of the three rates. `naming_wrong` is the highest.
`reconstruction_error` is the worst gap. `falsified_sensor_passes` is the fraction of the three
that meet the bar. A plant with no caught run leaves the rates unset.

### 3. Development result

`uv run python scripts/lane_d_score.py --split development --workstream naming`. Result name
`lane-d-plant-map-explainer-development`. File
`eval_runs/build/lane-d/naming-development.json`.

| Plant | Signal | Caught | Named right | Named wrong | Worst reconstruction |
| --- | --- | ---: | ---: | ---: | ---: |
| water-treatment | filtered_turbidity_ntu | 20/20 | 20/20 | 0 | 0.0082 of span |
| power-generation | transformer_oil_temp_c | 20/20 | 19/20 | 0 | 0.0450 of span |
| batch-reactor | reactor_temp_c | 20/20 | 20/20 | 0 | 0.0017 of span |

The bar is met. `naming_right` is 0.95, `naming_wrong` is 0.0, `reconstruction_error` is 0.0450,
and `falsified_sensor_passes` is 1.0. Power seed 97005 was caught and not named as the oil
temperature. It was not named as a different instrument, and it contributed no reconstruction.

The survey is not the bar. Chlorine residual and distribution pressure were caught on 20 of 20
runs and named on none. Feeder voltage was caught on 13 of 20 and named on all 13, within 0.034
of span. Exhaust temperature was caught on 3 of 20 and named on all 3. Jacket temperature was
named on 20 of 20. Reactor pressure was named right on 1 of 20, named wrong on 1 of 20, and its
worst reconstruction was 0.76 of span.

These are synthetic plants. The result is a diagnosis (ADR 0143).

## Correction at merge (17 October)

The three sensors on the bar were chosen in the same commit that recorded their development
results, so the bar is a development choice, not a declaration made before scoring. The held-back
check was declared first (`declaration.json`) and confirmed the same three sensors, 20 of 20 each.
The fair statement is therefore: **three sensor types, one per plant, chosen on development seeds
and confirmed on held-back seeds.**

Across every sensor this record scored on development seeds, the bar's three and the six surveyed,
the explainer named 96 of 156 caught runs right (62%) and 1 wrong. `docs/phos-2027.md` W2 asks for
at least 70% of caught runs named right, with reconstruction within 10% of span. **W2 is not met.**
What this record shows is that the explainer rarely names the wrong sensor, names some sensors
almost always, and mostly declines on chlorine residual, distribution pressure and reactor
pressure.

This lane also added the TU Wien entry to `data/registry.json`, which the build brief reserved for
Step 0. The entry is kept as written.

## Consequences

Held-back seeds 97101-97120 are not scored here. They wait for one declared command that also
scores the command-against-physics check and the calibration check. Editing the scored files
after that declaration refuses the run.

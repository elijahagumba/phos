# ADR 0152 — The Kelmarsh log rule is declared before it is scored

- **Status:** Accepted (a declaration; this record has no alert count)
- **Date:** 2026-10-17
- **PART:** October 2026 build, lane B, A5 / W4
- **Depends on:** [ADR 0112](0112-consistency-windows-scale-with-the-sample-period.md),
  [ADR 0143](0143-the-plant-map-does-not-improve-detection.md),
  [ADR 0144](0144-the-october-build-is-declared.md)

## Context

Kelmarsh development SCADA has no work-order export. `discover_work_order_exports` stays
empty, and a maintenance window is not invented from the power trace. What the turbine does
ship is its own status log, beside the ten-minute signals. A5 on this corpus is the share of
`atlas-v1-consistency` alerts that log explains, and the unexplained alerts per shift.

The column names and the status vocabulary below were read from the 2016 development zip
after its registry md5 matched. No score was computed from those values. Held-back names
were not opened. 2017–2022 were not required for this declaration.

## Decision

`phos.eval.kelmarsh_log` is the configuration.

1. **Files.** `KELMARSH_DEVELOPMENT_FILES` only. A held-back name raises `HeldBackFileError`
   before the path is read. A member whose name is held back, or contains `PMU`, `Grid_Meter`,
   `2023`, or `2024`, raises the same way before that member is read. Each zip's size and md5
   are checked against `data/registry.json` before use.

2. **Signals.** Five columns from the turbine CSV header, not from the signal map's unit cell:
   `Wind speed (m/s)`, `Power (kW)`, `Rotor speed (RPM)`, `Generator RPM (RPM)`,
   `Blade angle (pitch position) A`. The header says power is in kW. The signal map's `Power`
   row says kWh, and that cell is not used. Min, max, and standard-deviation columns stay out.
   A row with any of the five missing is dropped. It is not filled with zero.

3. **Split.** Train is `[2016-01-01, 2019-01-01)`. Score is `[2019-01-01, 2023-01-01)`.
   A timestamp on or after 2023-01-01 is outside the score. All six turbines are scored.
   The year zips mix the turbines, so there is no turbine holdout. A missing turbine, or a
   missing year zip, is not a partial farm and is not scored as one.

4. **Windows.** The sample period is 600 seconds. `windows_for_period(600)` is ADR 0112's
   rule and is not retuned. It collapses: lags `(0, 1)`, fit step 1, detrend window 6
   samples, detrend step 1, feature gap 1, event window 1, event span 1, second-alert
   separation 1. Lag 1 is the previous kept row. When a row was dropped, that neighbour can
   be more than ten minutes away. `clock_gaps` counts kept pairs that are not 600 seconds
   apart. A file whose raw steps are mostly not 600 seconds is refused.

5. **What the log explains.** A status row explains an alert on that turbine when the alert
   time is inside `[Timestamp start, Timestamp end]`, endpoints included, and `Service
   contract category` is not `System OK (32)`. That string is the file's own running code.
   Every other category, including an empty one, is the log naming something other than
   system OK. `Status` and `IEC category` are required to be present so the schema is the
   one that was read, and they do not decide. Low wind (`External stop (low wind speed)`)
   explains, because it is not system OK. A manual service stop explains. Overlapping system
   OK does not cancel another explaining row.

6. **The detector.** `atlas-v1-consistency`, one fit per turbine, attack flags all false.
   Kelmarsh has no attack labels. Budgeted alerts only. Explained share is explained alerts
   over all budgeted alerts, and is undefined when there are none. False alerts per shift
   are the unexplained ones divided by scored seconds over an 8-hour shift. Scored seconds
   are the clock from the first kept score row to the last, summed across turbines.

7. **What this record does not do.** It does not quote an alert count. It does not append
   `eval_runs/log.jsonl`. It does not edit templates, priors, `EVIDENCE_STRENGTH`, or the
   consistency arithmetic. It does not surface a hypothesis confidence. A false-alarm count,
   when a later record quotes one, is not a detection claim and is not evidence the plant
   map detects attacks.

## Consequences

A later record can quote the explained share and the false alerts per shift from this
configuration. Changing the OK category, the five signals, or the year cut to move that
share would be a different configuration.

What would reverse this: opening `KELMARSH_HELD_BACK_FILES`, scoring a subset of the year
files as if it were the development half, or calling the false-alarm count a detection result.

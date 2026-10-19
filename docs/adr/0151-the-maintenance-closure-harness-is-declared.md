# ADR 0151 — The maintenance-closure harness is declared before it is scored

- **Status:** Accepted (a declaration; this record has no measured rate)
- **Date:** 2026-10-17
- **PART:** October 2026 build, lane B, A5 / W4
- **Depends on:** [ADR 0150](0150-maintenance-alerts-close-only-with-a-citation.md),
  [ADR 0144](0144-the-october-build-is-declared.md)

## Context

A5's bar is a synthetic harness: at least 70% of maintenance-caused alerts close with a cited
work order, and no attack-caused alert closes, `MIMIC` included. The seeds for that harness were
named in ADR 0144. This record names the configuration that will be scored. It does not contain
the score.

## Decision

`phos.eval.maintenance_harness` is the configuration.

1. **Seeds.** `BUILD_DEVELOPMENT_SEEDS`, 97001–97020, and no others. Any other seed raises
   `UndeclaredSeedError` before a calendar is drawn. 97101–97120 are not run.

2. **Calendar.** Three assets, `P-101`, `P-102`, `V-201`, with features `flow`, `speed`, and
   `position`. The run is six hours from 2026-01-01 00:00 UTC. `plan_maintenance` draws it from
   `HARNESS_PRACTICE`: routine every two hours for twenty minutes, reactive rate 12 per asset per
   year for fifteen minutes, no shutdown, `idle_share` 0.15. The two-hour interval is so a
   six-hour run contains several jobs. `idle_share` is the shipped `MaintenancePractice` default.
   It was not fitted to the 70% bar. The calendar does not see the attacks.

3. **Export.** The calendar is written with `write_sap_pm_export` and read back with
   `load_work_order_export` and `SAP_PM_SCHEMA`, assets declared. Non-sanctioning rows are
   dropped by that loader. Each order, sanctioning or not, produces one maintenance alert at the
   order's start, citing that order and the asset's feature.

4. **Attacks.** Three attacks are placed from a separate random stream, without reading the
   calendar: `MIMIC`, `BLATANT`, `STEALTH_DRIFT`, each a point alert with an empty citation.
   After both schedules exist, one further `MIMIC` is placed on the earliest sanctioning order's
   start (same asset, same feature, empty citation). The calendar is not redrawn around it. If a
   seed has no sanctioning order, that `MIMIC` is placed without reading a window. Every attack
   alert, including both `MIMIC`s, must stay open.

5. **What "closed" means.** `close_maintenance_alerts` (ADR 0150). A maintenance alert whose
   order did not sanction stays open, because its citation does not resolve. That is the gap
   under 100%. The rival is `close_on_overlap` on the same alerts. The chance null is one
   permutation per seed of the citation lists, then the same closer.

6. **The same events, scored with the champion.** A quiet hour trains
   `atlas-v1-consistency`. The six-hour run is scored at one sample per second, so
   `windows_for_period(1)` is the frozen window set. Each job and each attack is a thirty-second
   step of +20 on its own signal. The two steps are the same size, so the detector is not told
   which is `MIMIC`. Catches within budget and unexplained alerts per 8-hour shift are reported
   under the result name `atlas-v1-consistency`. They are a diagnosis, not a detection claim.

7. **What this record does not do.** It does not open Kelmarsh. It does not append
   `eval_runs/log.jsonl`. It does not edit templates, priors, or `EVIDENCE_STRENGTH`. It does
   not surface a hypothesis confidence. The pass mark 0.70 is the bar the score will be compared
   to. The rate itself is written later, under `eval_runs/build/lane-b/`, from this configuration
   and not from a retune.

## Consequences

A later record can quote the rate. Changing `idle_share`, the citation rule, or the attack
placement to move that rate would be a different configuration, and would need its own record
before a new score.

What would reverse this: scoring 97101–97120, or treating the consistency catch rate on this
trace as evidence about a real plant.

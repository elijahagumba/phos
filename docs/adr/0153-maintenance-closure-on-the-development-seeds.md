# ADR 0153 — Maintenance closure on seeds 97001–97020

- **Status:** Accepted
- **Date:** 2026-10-17
- **PART:** October 2026 build, lane B, A5 / W4
- **Depends on:** [ADR 0151](0151-the-maintenance-closure-harness-is-declared.md)

## Context

ADR 0151 declared the harness and left the rate out. This record quotes the run of that
configuration. The code that draws the calendar, the citation rule, `idle_share`, and the
attack placement were not changed to move the rate. The only wording change since the run is
the singular of "1 attack alert" in the markdown renderer. The counts are the JSON file.

## Decision

`eval_runs/build/lane-b/maintenance-closure.json` is the measurement.
`scripts/measure_maintenance_closure.py` produced it from `score_development_closures` and
`score_consistency` on seeds 97001–97020. Runtime 0.409 seconds. Nothing was appended to
`eval_runs/log.jsonl`.

1. **Maintenance closure.** 158 of 180 maintenance alerts closed with a cited sanctioning work
   order. The rate is 0.8778. The bar is 0.70, and it is met. Per seed,
   `maintenance_closed` equals `sanctioning_orders` and `maintenance_alerts` equals `orders`.
   The 22 alerts that stay open are the orders the SAP loader dropped. `idle_share` 0.15 is
   the shipped default. The rate is that sanctioning fraction, not a learned detector.

2. **Attacks stay open.** 0 of 80 attack alerts closed. 0 of 40 `MIMIC` alerts closed. That
   includes the `MIMIC` placed on a real job's instant with an empty citation. The no-attack
   bar is met.

3. **Rival.** `close_on_overlap` closed 27 of 80 attack alerts (0.3375), including each
   in-window `MIMIC` on a seed that had a sanctioning order. Margin over that rival, rival
   attack-closure rate minus the citation rule's, is 0.3375.

4. **Chance.** One citation permutation per seed closed 1 of 80 attack alerts (0.0125).
   Margin over that chance is 0.0125. A random citation rarely matches an attack's asset,
   feature, and time. The permutation was not retuned.

5. **The same events, `atlas-v1-consistency`.** 57 of 80 attack steps contained a budgeted
   alert (0.7125). 51 of those alerts were on the attacked signal. Unexplained budgeted
   alerts: 0 over 15.0000 shifts, 0.0000 per shift. The job step and the attack step are the
   same thirty-second step of +20. This catch rate is a diagnosis on that trace. It is not a
   detection claim about a plant.

Hypothesis confidence is not in the file. Templates, known-link matchers, priors,
`EVIDENCE_STRENGTH`, and the consistency arithmetic were not edited.

## Consequences

A5's two synthetic bars are met on the declared seeds: at least 70% of maintenance alerts
close with a cited work order, and no attack alert closes. Kelmarsh is a separate
measurement and is not this rate.

What would reverse this: quoting 0.8778 as proof on a real plant, or retuning `idle_share`
or the citation rule and still citing this file.

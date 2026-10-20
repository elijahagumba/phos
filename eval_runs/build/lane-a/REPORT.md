# Lane A — Sentiel S1, S2, S3, and target 1

19 October 2026. Branch `build/lane-a-sentiel`. Work is ADRs 0145–0149 and
0190–0194. Nothing was merged. `eval_runs/log.jsonl` was not appended. The
frozen 6B row stays precision 0.104 at 48 alerts.

## S1 — Bet 001

Ran once on CERT r3.1 (ADR 0148). Gate reproduced 6B. All three declared
formulas lost: no formula put a day of `CCH0959` in the top 48.
`linear-excess` added a sixth `CSF0929` day and still missed the second
insider. Details in `bet-001.md`.

## S2 — which, not just how many

`named_counterparties` still ships an empty register (ADR 0146). The register
was not filled from a labelled insider. The 34 features were not weighted.

## Target 1 — both insiders in the top 48

Ten development loops on r3.1 (ADR 0149). None kept. Closest movement:
`lane-a-dev:peer-links+chains` ranked `CCH0959` at 119 and lost `CSF0929`.
Depth alone kept `CSF0929` and made `CCH0959` worse (1,094). The kept scorer
is still 6B. Details in `target1.md`.

## Phase 2b — four Sentiel capabilities

Each was declared, built with tests, and scored against 6B on the same r3.1
days. Each was reverted.

| Capability | ADR | Start (6B) | Best on development | Held-back | Kept? | Loops |
| --- | --- | --- | --- | --- | --- | ---: |
| Depth counting | 0190 | CSF in 48, CCH 957 | CSF in 48 (6 days), prec 0.125, CCH 1,094 | not scored | reverted | 1 |
| Behaviour chains | 0191 | CSF in 48, CCH 957 | both lost; CCH 2,049 | not scored | reverted | 1 |
| Role and time peers | 0192 | CSF in 48, CCH 957 | both lost; CCH 8,296 | not scored | reverted | 1 |
| Rare peer links | 0193 | CSF in 48, CCH 957 | both lost; CCH 1,203 | not scored | reverted | 1 |
| Target 1 (combinations) | 0149 | 1 of 2 | still 1 of 2; best CCH rank 119, CSF lost | not scored | reverted | 10 |

## S3 — the larger CERT release

r4.2 stays held out (ADR 0147, restated ADR 0194). Not fetched. Not scored.
The scorer a later session would take there is still 6B, because nothing was
kept.

## Scorecard

| Field | S1 | Target 1 | S3 |
| --- | --- | --- | --- |
| catches_within_budget | 1 of 2 | 1 of 2 | not measured |
| margin_over_best_simple_rival | none of the three formulas won | none of the ten loops kept | not measured |
| margin_over_chance | 5 vs 0.012 | 5 vs 0.012 (6B, unchanged) | not measured |
| falsified_sensor_passes | not applicable | not applicable | not applicable |
| naming_right | not applicable | not applicable | not applicable |
| naming_wrong | not applicable | not applicable | not applicable |
| reconstruction_error | not applicable | not applicable | not applicable |
| maintenance_closures | not applicable | not applicable | not applicable |
| calibration | not measured | not measured | not measured |
| false_alerts_per_shift | not measured | not measured | not measured |
| runtime | 552 s (Bet 001) | 65 s (ten loops) | not measured |

## What this lane did not do

It did not overwrite 0.104. It did not append `eval_runs/log.jsonl`. It did
not fetch r4.2. It did not copy a labelled insider's hosts into a register.
It did not start Intelligence, API, or UI.

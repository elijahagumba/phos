# ADR 0111 — The port reproduces ADR 0104's scored alert list on every clean HAI file

- **Status:** Accepted
- **Date:** 2026-10-12
- **PART:** v1 rebuild, the check declared in ADR 0110
- **Depends on:** [ADR 0110](0110-the-ports-identity-on-real-hai-declared.md)

## Context

ADR 0110 declared one command, `scripts/measure_consistency_identity.py`, committed and pushed in
`a0cc4b9` before it ran. It then ran once. The frozen file's sha256 matched, and ADR 0104's path
caught 53/58 and 36/52 as required. No constant, detector, or published row changed. The
experiment log was not appended.

## Decision

| Edition | Port path | Scores identical | Alert lists identical | Alerts | Reference alerts | Alerts not in reference | Caught | Reference caught |
|---|---|---|---|---:|---:|---:|---:|---:|
| hai-22.04 | as written (float32 grouping) | yes | yes | 101 | 101 | 0 | 53/58 | 53/58 |
| hai-22.04 | float64 grouping | yes | yes | 101 | 101 | 0 | 53/58 | 53/58 |
| hai-23.05 | as written (float32 grouping) | yes | yes | 73 | 73 | 0 | 36/52 | 36/52 |
| hai-23.05 | float64 grouping | yes | yes | 73 | 73 | 0 | 36/52 | 36/52 |

On every test file, four on HAI 22.04 and two on HAI 23.05, the port's float32 feature scores
equal the frozen file's, and the port's alert list as written equals ADR 0104's scored list,
`(row, column, score)` for `(row, column, score)`. The float32-against-float64 grouping difference
ADR 0110 described is possible in principle and does not occur on this data.

## Consequences

ADR 0107's identity holds on the data the headline came from, not only on the synthetic plant.
`events` stays as written. The 53/58 and 36/52 remain ADR 0104's numbers, on editions this
detector has seen, with ADR 0106's flag on `P1_PCV01D` beside them. Nothing here judges roadmap §2.

## What would reverse this

A port whose alert list differs from ADR 0104's on any clean HAI file, or this command run again.

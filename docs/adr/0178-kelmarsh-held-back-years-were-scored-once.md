# ADR 0178 — Kelmarsh 2023–2024 was scored once

- **Status:** Accepted
- **Date:** 2026-10-19
- **PART:** Round 3, Job 1
- **Depends on:** [ADR 0174](0174-kelmarsh-held-back-score-is-declared.md)

## Context

The command named in ADR 0174 ran once after the sha256 values were committed.
`atlas-v1-consistency` was not edited. Modes were not run. Nothing was tuned
on the result.

## Decision

Train stayed 2018. Score was SCADA 2023 and 2024, six turbines, the ADR 0165
status-log rule.

| Half | Alerts | Explained | Share | Unexplained per shift |
| --- | ---: | ---: | ---: | ---: |
| Development 2019–2022 (ADR 0166, kept scorer) | 74 | 57 | 0.770 | 0.000646 |
| Held back 2023–2024 | 29 | 23 | 0.793 | 0.000456 |

Six of the 29 alerts were not explained, across 13,158 shifts. The PMU and
grid-meter archives were checksummed. Their columns are not the five turbine
signals, so `detect` was not called.

## Consequences

This is a false-alarm count on a real wind farm. It is not a detection claim
(ADR 0143). The result is `eval_runs/build/round-3/kelmarsh-heldback.json`.
It is not in `eval_runs/log.jsonl`.

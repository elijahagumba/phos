# ADR 0309 — The champions missed none of the in-range commands

- **Status:** Accepted
- **Date:** 2026-10-22
- **PART:** Atlas daily leaps, day 1 score
- **Supersedes:** nothing
- **Depends on:** [ADR 0301](0301-the-in-range-command-is-declared-before-either-champion-is-scored.md),
  [ADR 0073](0073-a-synthetic-command-and-maintenance-harness-that-measures-nothing.md)

## Context

The score declared in ADR 0301 was run after commit `0f27b1f`. The generation log is
`eval_runs/build/lane-daily/day1-generate.log`. `python` was not on PATH, so the declared
generation command was run as `python3 -u scripts/icssim/generate_corpus.py development4`.
The score command was `uv run python scripts/lane_e_icssim_baseline.py --corpus data/phos-icssim-dev4`.

The first score invocation exited 1. The script opened only `mixed*` directories, and these
attack runs are `in_range-*`. No alerts were computed. The glob was extended to `in_range-*`
and the same command was run again. The champion files were not edited. Their sha256 values
still match the declaration: `consistency.py`
`71aeebfea7ee491117316f9a7db32c9ae2c4aced4f17baf4575a078a48ff5911`,
`command_consistency.py`
`87017fcfeaae94790dd8d461d43793a1f87e15a1460e46d963d47a1ae6d0cc94`.

Result name `atlas-daily:day1-champions`. Report:
`eval_runs/build/lane-daily/day1-champions.md`. A second look was not taken. This is a
simulated diagnosis (ADR 0073).

## Decision

**`M_champion` is 0. `atlas-inrange-consistency` is not built. Do not rerun this score.**

| Bar | Result |
| --- | --- |
| If `M_champion` is 0, the detector below is not built, and the fallback command is the next legal command. | `M_champion` is 0, kept by the tie on misses and on the false-alert rate, so the frozen detector. `atlas-inrange-consistency` is not built. The walk corpus was not generated. **Met.** |

From the report, and not recomputed here. `in_range_command` events: 13. Misses frozen: 0.
Misses lane 1: 0. Caught 13 of 13 on each champion, and what caught them is `signal`.
False alerts: 11 and 11. `duration_s`: 115200.000000. False alerts per hour: 0.343750 each.
Median delay: 0.500000 s each. Maintenance drew an alert on 4 of 17. Setpoint drew an alert
on 0 of 18. Benign events drawing an alert: 4 of 35 on each champion.

This is not a kept day. A kept day is a new detector that halves remaining misses. The
remaining misses of this class were already 0. Breadth is printed in the report and is not
a champion.

## Consequences

The denominator for `in_range_command` on `phos-icssim-dev4` is 0. The walk corpus stays
ungenerated until this record and `day1-champions.md` are committed. Held-out stays
unopened. v1 stays 8 of 12. Nothing here is a field rate, and nothing here is a result
about a real plant.

## What would reverse this

Building `atlas-inrange-consistency` after a zero-miss champion score. Rerunning this
score. Generating `phos-icssim-dev4-walk` before this report is committed. Quoting 13 of 13
as a result about a real plant.

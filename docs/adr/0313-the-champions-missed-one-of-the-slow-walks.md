# ADR 0313 — The champions missed one of the slow walks

- **Status:** Accepted
- **Date:** 2026-10-23
- **PART:** Atlas daily leaps, the walk score
- **Supersedes:** nothing
- **Depends on:** [ADR 0301](0301-the-in-range-command-is-declared-before-either-champion-is-scored.md),
  [ADR 0309](0309-the-champions-missed-none-of-the-in-range-commands.md),
  [ADR 0073](0073-a-synthetic-command-and-maintenance-harness-that-measures-nothing.md)

## Context

The walk command declared in ADR 0301 was run after commit `61d03ec`. ADR 0309 is in that
commit, and so is `eval_runs/build/lane-daily/day1-champions.md`. `M_champion` on
`phos-icssim-dev4` is 0, which is the gate that allows this corpus.

`python` is not on PATH, so generation was
`python3 -u scripts/icssim/generate_corpus.py development4-walk`. The shell then failed
assigning `status`, which zsh keeps read-only, after that process had returned. All 11
manifests exist under `data/phos-icssim-dev4-walk`. Held-out was not generated. The
generation log is `eval_runs/build/lane-daily/day1-walk-generate.log`.

The scorer at the generation's start opened `mixed*` and `in_range-*` only. These attack
runs are `subfloor-*`. Commit `61d03ec` extended that selection. No alerts were computed
before it. The champion files were not edited. Their sha256 values still match the
declaration: `consistency.py`
`71aeebfea7ee491117316f9a7db32c9ae2c4aced4f17baf4575a078a48ff5911`,
`command_consistency.py`
`87017fcfeaae94790dd8d461d43793a1f87e15a1460e46d963d47a1ae6d0cc94`.

The score command was then run once:

```
uv run python scripts/lane_e_icssim_baseline.py --corpus data/phos-icssim-dev4-walk
```

It exited 0. Result name `atlas-daily:day1-walk`. Report:
`eval_runs/build/lane-daily/day1-walk.md`. A second look was not taken. This is a
simulated diagnosis (ADR 0073). `eval_runs/log.jsonl` was not appended.

## Decision

**`M_champion` is 1. The walk detector specified in ADR 0301 may be built. It is not
built in this record. Do not rerun this score.**

| Bar | Result |
| --- | --- |
| If that champion miss count is greater than 0, the walk detector may be built as specified here, and not otherwise. | The report states `M_champion` 1. **Met.** |

From the report, and not recomputed here. `subfloor_walk` events: 9. Misses frozen: 1.
Misses lane 1: 1. Caught 8 of 9 on each champion, and what caught them is `signal`.
`M_champion` is 1, kept by the tie on misses and on the false-alert rate, so the frozen
detector. False alerts: 19 and 19. `duration_s`: 57600.000000. False alerts per hour:
1.187500 each. Median delay: 0.950000 s each. Maintenance drew an alert on 3 of 14.
Setpoint drew an alert on 3 of 9. Benign events drawing an alert: 6 of 23 on each
champion. Breadth is printed in the report and is not a champion.

The scenario draws four events from three kinds, so one run can hold more than one walk.
The report's count is 9. This record does not name which walk was missed. The report
does not say.

This is not a kept day. A kept day is a new detector that halves the remaining misses.
The reported miss count is 1, so the bar already written for that detector is
`M_new <= floor(M_champion / 2)` with this count on the right-hand side. The other three
bars in ADR 0301 stay as written. No weight was changed.

## Consequences

The walk corpus exists and has been scored once. `atlas-inrange-consistency` stays
unbuilt. The walk detector may be the next module, beside the frozen files, and only as
ADR 0301 specified it. Held-out stays unopened. v1 stays 8 of 12. Nothing here is a
field rate, and nothing here is a result about a real plant. Nothing here is ≥70%.

## What would reverse this

Rerunning this score. Building the walk detector on a report whose miss count is 0.
Editing either champion file and scoring it under the digests above. Opening
`phos-icssim-heldout4` or `phos-icssim-heldout4-walk`. Quoting 8 of 9 as a result about
a real plant.

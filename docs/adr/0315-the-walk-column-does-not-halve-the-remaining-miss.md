# ADR 0315 — The walk column does not halve the remaining miss

- **Status:** Accepted
- **Date:** 2026-10-23
- **PART:** Atlas daily leaps, the walk detector
- **Supersedes:** nothing
- **Depends on:** [ADR 0314](0314-the-walk-column-is-declared-before-it-is-scored.md),
  [ADR 0073](0073-a-synthetic-command-and-maintenance-harness-that-measures-nothing.md)

## Context

The score declared in ADR 0314 was run after commit `5fd281d`:

```
uv run python scripts/lane_daily_walk.py --corpus data/phos-icssim-dev4-walk
```

Result name `atlas-walk-consistency`. Challenger sha256
`396b1fa08414ef5bd279dd0ec60e9d1e6b22637cec62ba91003f020edba9f991` for
`src/phos/atlas/walk_consistency.py` and
`5cbd7d50bd5791aa472296db15e96e06f9405b8ddbb147b518fa60c91470b595` for
`scripts/lane_daily_walk.py`. The path is not mixed in. Seeds `normal`
96801–96803 and `subfloor` 96811–96818. Report:
`eval_runs/build/lane-daily/day1-walk-detector.md`. A second run was refused.
This is a simulated diagnosis (ADR 0073). `eval_runs/log.jsonl` was not appended.
The champion files were not edited.

## Decision

**Not kept. The first bar is not met. Do not rerun this score, and do not retune
the column.**

| Bar | Result |
| --- | --- |
| Misses of `subfloor_walk` satisfy `M_new <= floor(M_champion / 2)`. | The report prints misses new 1. `M_champion` in ADR 0313 is 1, so the bound is `floor(1 / 2)`, which is 0. **Not met.** |
| The false-alert rate, defined above, is no higher than the champion's. | The report prints 1.187500. The champion rate in ADR 0313 is 1.187500. **Met.** |
| The alert budget stays 8 per shift. | The report prints 8. **Met.** |
| On events both catch, the new alert time is not later than the champion's. | The report prints `walk later than champion: 0`. **Met.** |
| The frozen miss count this command prints is 1. | The report prints misses frozen 1. **Met.** |

Bar 5 is met, so bars 1–4 are judged. The column misses the same one walk the
frozen detector misses. The report prints the divisor as 2.000000. The command's
log line was `walk column divisor 2.0000 from 3 peaks`. A full valve error is
`ONSET_LEVEL` before that division, and an episode opens only on a score strictly
above 1, so a full error sits on the threshold and does not open. The weight was
not raised. The divisor was not changed. This is a limit of the specified column
on training that already contains three such peaks, not a licence to pick a
different rank.

## Consequences

`atlas-walk-consistency` is not a champion. ADR 0300 retires a mechanism that
misses its bar, and this column is not the next day's work. The champion walk
score stays the one in ADR 0313. Held-out stays unopened. v1 stays 8 of 12.
Nothing here is a field rate, and nothing here is ≥70%. The next class named in
`docs/atlas-daily-leaps.md` is the joint command vector. It has no morning record.
It is not generated here.

## What would reverse this

Rerunning this score. Lowering the divisor, or any other constant, after this
report. Calling a tie on misses a kept day. Quoting 8 of 9 as a result about a
real plant.

# ADR 0314 — The walk column is declared before it is scored

- **Status:** Accepted
- **Date:** 2026-10-23
- **PART:** Atlas daily leaps, the walk detector
- **Supersedes:** nothing
- **Depends on:** [ADR 0301](0301-the-in-range-command-is-declared-before-either-champion-is-scored.md),
  [ADR 0313](0313-the-champions-missed-one-of-the-slow-walks.md),
  [ADR 0073](0073-a-synthetic-command-and-maintenance-harness-that-measures-nothing.md)

## Context

ADR 0313 records `M_champion` 1 on `subfloor_walk`. That is the gate that allows the
walk column ADR 0301 specified. The column is in
`src/phos/atlas/walk_consistency.py`. It is per sample. It is not a running sum.
Above `tank_level_max` the predicted `tank_input_valve_status` is 0. Below
`tank_level_min` it is 1, the constant PLC1 writes at ICSSim `bcfd1844d3f063850c69f2643f6a052bac03d8ec`, which is not in this repository. Samples
inside the band, including either end, are 0. The raw value is the absolute error
times `ONSET_LEVEL`. The divisor is the third-largest training peak, or 1.0. The
calibrated column is appended after the frozen per-signal scores and passed through
the unchanged `events` and `budget_alerts`.

No score of this column exists. The report path below does not exist.
`phos-icssim-dev4-walk` is not regenerated. Held-out is not opened. The champion
files are not the challenger. Their sha256 values are still
`consistency.py`
`71aeebfea7ee491117316f9a7db32c9ae2c4aced4f17baf4575a078a48ff5911` and
`command_consistency.py`
`87017fcfeaae94790dd8d461d43793a1f87e15a1460e46d963d47a1ae6d0cc94`.
The path is not mixed in.

## Decision

**`atlas-walk-consistency` is scored once, after this record is committed, on the
walk corpus that already exists. The bars are the four ADR 0301 named, applied to
`subfloor_walk` as that record says, plus one check that the frozen miss count
printed here is the committed 1.**

- **Challenger:** the walk column on, appended to the frozen scores. No other
  component. `consistency.py` and `command_consistency.py` off the challenger set.
- **sha256:** `src/phos/atlas/walk_consistency.py`
  `396b1fa08414ef5bd279dd0ec60e9d1e6b22637cec62ba91003f020edba9f991`;
  `scripts/lane_daily_walk.py`
  `5cbd7d50bd5791aa472296db15e96e06f9405b8ddbb147b518fa60c91470b595`.
  The path is not mixed in. A change to either file before the score is a
  different challenger, and the score stops.
- **Command:**

```
uv run python scripts/lane_daily_walk.py --corpus data/phos-icssim-dev4-walk
```

- **Result name:** `atlas-walk-consistency`
- **Report:** `eval_runs/build/lane-daily/day1-walk-detector.md`
- **Seeds:** the corpus ADR 0313 generated. Train `normal` 96801–96803. Test
  `subfloor` 96811–96818. Nothing is regenerated.

ADR 0301 says the half-miss bars apply to `subfloor_walk`, in place of
`in_range_command`. The champion rate they are held to is the one ADR 0313's
report printed, 1.187500 false alerts per hour. `M_champion` in the first bar is
that record's 1.

**Bars:**

1. Misses of `subfloor_walk` satisfy `M_new <= floor(M_champion / 2)`.
2. The false-alert rate, defined above, is no higher than the champion's.
3. The alert budget stays 8 per shift.
4. On events both catch, the new alert time is not later than the champion's.
5. The frozen miss count this command prints is 1.

The false-alert rate is a budgeted alert on the eight test runs whose time falls
outside every `subfloor_walk` window, divided by the summed duration of those runs
in hours. If bar 5 is not met, bars 1–4 are not judged. `eval_runs/log.jsonl` is
not appended. This command does not replace `eval_runs/build/lane-daily/day1-walk.md`.

A simulated score, when one exists, is diagnosis (ADR 0073), not a field rate, and
not a change to any frozen count. Not ≥70%.

## Consequences

**Gained.** The column and the command are fixed before any number from them exists.

**Cost.** This record contains no score. Held-out stays unopened. v1 stays 8 of 12.
The champion files stay as hashed in ADR 0301.

## What would reverse this

Scoring before this record is committed. Editing either hashed file and scoring it
under the digests above. Regenerating `phos-icssim-dev4-walk`. Opening either
held-out directory. Rewriting a bar after the number exists.

# ADR 0316 — The joint command is declared before either champion is scored

- **Status:** Accepted
- **Date:** 2026-10-23
- **PART:** Atlas daily leaps, the joint command
- **Supersedes:** nothing
- **Depends on:** [ADR 0300](0300-a-kept-day-halves-the-remaining-misses.md),
  [ADR 0301](0301-the-in-range-command-is-declared-before-either-champion-is-scored.md),
  [ADR 0315](0315-the-walk-column-does-not-halve-the-remaining-miss.md),
  [ADR 0122](0122-a-phos-generated-icssim-corpus.md),
  [ADR 0128](0128-icssim-roles-loops-and-the-development-slice.md),
  [ADR 0073](0073-a-synthetic-command-and-maintenance-harness-that-measures-nothing.md)

## Context

ADR 0315 retired the walk column. The next class in `docs/atlas-daily-leaps.md` is the joint
command vector. This is its morning record. It is committed before any generation or score.

The plant facts used below are already fixed. At ICSSim `bcfd184`, `tank_level_max` defaults
to 7 and a benign `setpoint` already writes it into 6.5–7.5. `bottle_level_max` defaults to
1.8. `PHYSICS.BOTTLE_MAX_LEVEL` is 2. PLC1 closes the input valve when the level is above
`tank_level_max` and opens it when the level is below `tank_level_min`. It closes the output
valve when the bottle level is above `bottle_level_max` or the belt position is above 1.0,
and opens it otherwise. Those lines are quoted in `data/phos-icssim-dev/roles.toml`. The
operator writes from the known console. `MIN_COMMAND_SHARE` is 0.05. `HORIZON_STEPS` is 20.
`EVENT_WINDOW` is 300 and `EVENT_SPAN` is 600. An episode opens only when a score is strictly
above `THRESHOLD` (1.0). `ONSET_LEVEL` is 2.0. `CALIBRATION_RANK` is 3. `VALVE_RELEASE` is 3.
None of these numbers is adjusted here.

This class is not `creep_many` and not `legal_flow`. It does not bias a sensor. It is not
`in_range_command`: no valve is held. It is not `subfloor_walk`: neither setpoint is walked.
`mimic_maintenance` is not in the scenario. It is not a command-lead measurement. The frozen
rates stay where they are.

No corpus for this record has been generated. No champion has been scored on it. The report
path named below does not exist. `phos-icssim-dev4` and `phos-icssim-dev4-walk` are not
regenerated. The walk score is not rerun. The walk divisor is not retuned.

## Decision

**`joint_command` is an attack: the operator writes `tank_level_max` and `bottle_level_max`
once each, inside the bands below, and tampers nothing. Both champions are scored on it once
this record is committed. The new detector is not built in this record.**

### The class

From the operator station, which is the known console and not an unknown master:

1. Write `tank_level_max` once, to a value drawn from 6.5–7.5. The band is not widened.
   Its centre is the pinned default 7.
2. Write `bottle_level_max` once, to a value drawn from 1.3–2.0. The half-width is half of
   6.5–7.5, which is 0.5, applied to the pinned default 1.8, and the high end stops at
   `BOTTLE_MAX_LEVEL` 2 so the output valve's level comparison can still become true.
3. Both writes happen at the start of the event. The registers are not restored. No mode
   tag is written. No sensor is tampered. The reported values are the physics.

Duration is drawn from 60 to 180 simulated seconds. The short end is three times
`HORIZON_STEPS` at one sample per second, so the event window can contain the check. It is
not a search.

The scenario `joint` draws `setpoint`, `maintenance`, and `joint_command`, six events, over
14400 simulated seconds. `normal` is unchanged and is the training scenario. `mixed`,
`mixed2`, `mixed3`, `in_range`, and `subfloor` are unchanged.

### Seeds

New seeds, because the generator changes. Nothing is regenerated over an existing corpus.

| Role | Directory | Seeds | When it may be generated |
| --- | --- | --- | --- |
| Development | `phos-icssim-dev5` | 3 `normal` 98001–98003, 8 `joint` 98011–98018 | After this commit, by the command below |
| Held out | `phos-icssim-heldout5` | 20 `joint` 98101–98120 | Not by this record. Score once, after a later declaration |

`phos-icssim-heldout5` is on the score-once tier from this commit.

### Champion score

Both files below are the champions. The digests are the plain sha256 of the file bytes. The
path is not mixed in. A change to either file before the score is a different champion, and
the score stops.

- `src/phos/atlas/consistency.py` — `71aeebfea7ee491117316f9a7db32c9ae2c4aced4f17baf4575a078a48ff5911`
- `src/phos/atlas/command_consistency.py` — `87017fcfeaae94790dd8d461d43793a1f87e15a1460e46d963d47a1ae6d0cc94`

**Command, after this record is committed:**

```
python scripts/icssim/generate_corpus.py development5
uv run python scripts/lane_e_icssim_baseline.py --corpus data/phos-icssim-dev5
```

Train is the three `normal` runs. Test is the eight `joint` runs. The script opens `joint-*`
and prints the account for `joint_command`. Its frozen column is `atlas-v1-consistency`. Its
lane-1 column is `atlas-command-consistency`. Its breadth column is printed and is not a
champion.

**Result name:** `atlas-daily:joint-champions`

**Report:** `eval_runs/build/lane-daily/joint-champions.md`, written from that command's
stdout. `eval_runs/log.jsonl` is not appended.

For `joint_command` only, `M_v1` is the number of those events with no frozen alert inside
the event window, and `M_cmd` is the same count for the command detector. `M_champion` is the
smaller of the two. Tied misses keep the detector with the lower false-alert rate defined
below, and a tie on both keeps the frozen detector.

A false alert is a budgeted alert on the eight test runs whose time falls outside every
`joint_command` window. The rate is that count divided by the summed duration of those runs,
in hours. Delay, for an event a detector catches, is the earliest budgeted alert inside the
window minus the event start. The report states `M_v1`, `M_cmd`, `M_champion`, both rates,
and both median delays. It does not drop an alert that fell outside the window.

This score has no pass bar. It is the denominator. If `M_champion` is 0, the detector below
is not built. If `M_champion` is greater than 0, that detector may be built as specified
here, and not otherwise.

### The detector, specified and not built

Built only after `joint-champions.md` is committed in a verdict record, and only when
`M_champion` is greater than 0. New module `src/phos/atlas/joint_consistency.py`, result name
`atlas-joint-consistency`. It does not edit `consistency.py` or `command_consistency.py`. It
does not read `mimic_maintenance`. It does not restore `response_departure`. The page
predicate in `joint_setpoint.py` is not this column.

A step on `tank_level_max` or on `bottle_level_max` is a sample-to-sample absolute change of
at least `MIN_COMMAND_SHARE` of that signal's training span. The span is the maximum minus
the minimum on the three `normal` runs of the same corpus. A span of zero ignores the signal.
Two steps join when the later step is at most `EVENT_WINDOW` after the previous step and at
most `EVENT_SPAN` after the earliest. A chain of one setpoint leaves the column at 0. A chain
of two writes, at the earliest step only, `(2 - 1) * ONSET_LEVEL`. Later samples, where the
registers still hold the new values, stay 0. A full joint therefore sits strictly above
`THRESHOLD`. No new height is introduced.

The column stays 0 unless, `HORIZON_STEPS` after that earliest step, both of these hold. If
that later sample does not exist, the column stays 0.

1. `tank_input_valve_mode` and `tank_output_valve_mode` are both `VALVE_RELEASE`. A held
   valve is not this column.
2. Each actuator equals the value the pinned PLC1 line writes, using the setpoints at that
   later sample. The input valve is 0 when `tank_level_value` is strictly above
   `tank_level_max`, and 1 when it is strictly below `tank_level_min`. Inside that band the
   quoted logic does not move the valve, so the input valve does not constrain the column.
   The output valve is 0 when `bottle_level_value` is strictly above `bottle_level_max` or
   `bottle_distance_to_filler_value` is strictly above 1.0, and 1 otherwise. The 1.0 is the
   literal in that PLC1 line.

The divisor is the third-largest episode peak of that column on the normal runs, or 1.0 when
there are fewer than `CALIBRATION_RANK` peaks. The calibrated column is appended after the
frozen per-signal scores and passed through the unchanged `events` and `budget_alerts`.

**Bars, from ADR 0300, on `phos-icssim-dev5` only:**

1. Misses of `joint_command` satisfy `M_new <= floor(M_champion / 2)`.
2. The false-alert rate, defined above, is no higher than the champion's.
3. The alert budget stays 8 per shift.
4. On events both catch, the new alert time is not later than the champion's.

The score command for that detector is written with the module, after the champion report
exists, and it names these four bars unchanged. This record does not contain that score.

### Fallback

If the committed champion report shows `M_champion` = 0, `atlas-joint-consistency` is not
built. The next class in the programme document is incident packing: a linker beside
`src/phos/atlas/grouping.py`. It does not inherit the refused 53 of 70. It gets its own
morning record. This record does not write that record, and it does not build the linker.

### What this record does not do

It does not generate a corpus, score a champion, or add a detector. It does not open a
held-out directory. It does not move v1, which stays 8 of 12. A simulated score, when one
exists, is diagnosis (ADR 0073), not a field rate, and not a change to any frozen count.
Not ≥70%.

## Consequences

**Gained.** The class, the seeds, the champion command, the detector, the bar, and the
fallback are fixed before any number from them exists.

**Cost.** This record contains no score. Held-out stays unopened. v1 stays 8 of 12. The
champion files stay as hashed in ADR 0301. The walk column stays retired.

## What would reverse this

Generating `phos-icssim-dev5` or `phos-icssim-heldout5` before this record is committed.
Widening 6.5–7.5 or 1.3–2.0, or changing 60, 180, 1.8, 2, or 7, after a detector has run.
Building `atlas-joint-consistency` before `joint-champions.md` is committed, or building it
when `M_champion` is 0. Editing either champion file and scoring it under the digests above.
Opening `phos-icssim-dev`, `phos-icssim-dev2`, `phos-icssim-dev3`, `phos-icssim-dev4`,
`phos-icssim-dev4-walk`, or any spent or unopened held-out named before this record.
Rerunning the walk score or retuning its divisor.

# ADR 0301 — The in-range command is declared before either champion is scored

- **Status:** Accepted
- **Date:** 2026-10-22
- **PART:** Atlas daily leaps, day 1
- **Supersedes:** nothing
- **Depends on:** [ADR 0300](0300-a-kept-day-halves-the-remaining-misses.md),
  [ADR 0122](0122-a-phos-generated-icssim-corpus.md),
  [ADR 0128](0128-icssim-roles-loops-and-the-development-slice.md),
  [ADR 0276](0276-lane-1-met-its-bar-on-held-out-runs.md),
  [ADR 0073](0073-a-synthetic-command-and-maintenance-harness-that-measures-nothing.md)

## Context

ADR 0300 requires one morning record, committed before any generation or score. This is that
record for day 1. The class is roadmap F's first question: a command the plant should answer,
posed so a range threshold can miss it, scored on the detectors we already have before any new
one is built.

The plant facts used below are already on record. `tank_level_max` is the setpoint of the PLC1
input-valve loop, and that loop's actuator is `tank_input_valve_status` (`roles.toml`, ADR 0128).
A benign `setpoint` event already writes `tank_level_max` into 6.5–7.5 from the operator
station. Maintenance already holds a valve by writing mode 1 and releases it by writing mode 3.
`command_response` already judges an unanswered command with `HORIZON_STEPS` 20,
`MIN_COMMAND_SHARE` 0.05, and `MIN_RESPONSE_SHARE` 0.05. An episode opens only when a score is
strictly above `THRESHOLD` (1.0). None of these numbers is adjusted here.

No corpus for this record has been generated. No champion has been scored on it. The report
paths named below do not exist.

## Decision

**`in_range_command` is an attack: the operator writes `tank_level_max` inside the existing
6.5–7.5 band and holds the input valve off, and no sensor is falsified. Both champions are
scored on it once this record is committed. The new detector is not built in this record.**

### The class

From the operator station, which is the known console and not an unknown master:

1. Write `tank_input_valve_mode` to 1, the force-off value maintenance already uses.
2. Write `tank_level_max` once, to a value drawn from 6.5–7.5, the band a benign `setpoint`
   already uses. The band is not widened.
3. Hold the mode until the event ends, then write 3, the release value maintenance already uses.
4. Tamper no sensor. The reported values are the physics.

Duration is drawn from 60 to 180 simulated seconds. The short end is three times
`HORIZON_STEPS` at one sample per second, so the event window can contain the check. It is not
a search. The class is not `mimic_maintenance`: the valve is the input valve, and the event
also writes a setpoint. It is not a command-lead measurement. The frozen rates stay where they
are.

The scenario `in_range` draws `setpoint`, `maintenance`, and `in_range_command`, six events,
over 14400 simulated seconds. `normal` is unchanged and is the training scenario. `mixed`,
`mixed2`, and `mixed3` are unchanged.

### Seeds

New seeds, because the generator changes. Nothing is regenerated over an existing corpus.

| Role | Directory | Seeds | When it may be generated |
| --- | --- | --- | --- |
| Development | `phos-icssim-dev4` | 3 `normal` 96601–96603, 8 `in_range` 96611–96618 | After this commit, by the command below |
| Held out | `phos-icssim-heldout4` | 20 `in_range` 96701–96720 | Not by this record. Score once, after a later declaration |
| Walk development | `phos-icssim-dev4-walk` | 3 `normal` 96801–96803, 8 `subfloor` 96811–96818 | Only if the committed champion score has `M_champion` = 0 |
| Walk held out | `phos-icssim-heldout4-walk` | 20 `subfloor` 96901–96920 | Not by this record. Score once, after a later declaration |

`phos-icssim-heldout4` and `phos-icssim-heldout4-walk` are on the score-once tier from this
commit. Generating either walk directory before that gate is a reversal of this record.

### Champion score

Both files below are the champions. The digests are the plain sha256 of the file bytes. The
path is not mixed in. A change to either file before the score is a different champion, and
the score stops.

- `src/phos/atlas/consistency.py` — `71aeebfea7ee491117316f9a7db32c9ae2c4aced4f17baf4575a078a48ff5911`
- `src/phos/atlas/command_consistency.py` — `87017fcfeaae94790dd8d461d43793a1f87e15a1460e46d963d47a1ae6d0cc94`

**Command, after this record is committed:**

```
python scripts/icssim/generate_corpus.py development4
uv run python scripts/lane_e_icssim_baseline.py --corpus data/phos-icssim-dev4
```

Train is the three `normal` runs. Test is the eight `in_range` runs. The script's frozen
column is `atlas-v1-consistency`. Its lane-1 column is `atlas-command-consistency`. Its
breadth column is printed and is not a champion.

**Result name:** `atlas-daily:day1-champions`

**Report:** `eval_runs/build/lane-daily/day1-champions.md`, written from that command's
stdout. `eval_runs/log.jsonl` is not appended.

For `in_range_command` only, `M_v1` is the number of those events with no frozen alert inside
the event window, and `M_cmd` is the same count for the command detector. `M_champion` is the
smaller of the two. Tied misses keep the detector with the lower false-alert rate defined
below, and a tie on both keeps the frozen detector.

A false alert is a budgeted alert on the eight test runs whose time falls outside every
`in_range_command` window. The rate is that count divided by the summed duration of those
runs, in hours. Delay, for an event a detector catches, is the earliest budgeted alert inside
the window minus the event start. The report states `M_v1`, `M_cmd`, `M_champion`, both
rates, and both median delays. It does not drop an alert that fell outside the window.

This score has no pass bar. It is the denominator. If `M_champion` is 0, the detector below
is not built, and the fallback command is the next legal command. If `M_champion` is greater
than 0, the walk corpus stays ungenerated.

### The detector, specified and not built

Built only after `day1-champions.md` is committed in a verdict record, and only when
`M_champion` is greater than 0. New module `src/phos/atlas/inrange_consistency.py`, result
name `atlas-inrange-consistency`. It does not edit `consistency.py` or
`command_consistency.py`. It does not restore `response_departure`. It does not read
`mimic_maintenance`.
<!-- evidence-ack: src/phos/atlas/inrange_consistency.py — specified and not built; the recorded miss count was zero, so this module stays unwritten -->

A write to `tank_level_max` is counted when the step is at least `MIN_COMMAND_SHARE` of that
signal's training span. The span is the maximum minus the minimum on the three `normal` runs
of the same corpus. A span of zero ignores the signal. The actuator is
`tank_input_valve_status`. Travel is the absolute change from the write's sample to
`HORIZON_STEPS` later. Travel at or above `MIN_RESPONSE_SHARE` of the actuator's training
span is an answer, and the column stays 0. Otherwise the shortfall is
`(min_travel - travel) / min_travel`, and the raw value at the horizon sample is
`shortfall * ONSET_LEVEL`. `ONSET_LEVEL` is the existing onset score. A full shortfall
therefore sits strictly above `THRESHOLD`, which a raw shortfall of 1 would not, because an
episode opens only on a strict greater-than. No new height is introduced.

The divisor is the third-largest episode peak of that column on the normal runs, or 1.0 when
there are fewer than `CALIBRATION_RANK` peaks. That is the rule `fit_commands` already uses.
The calibrated column is appended after the frozen per-signal scores and passed through the
unchanged `events` and `budget_alerts`.

**Bars, from ADR 0300, on `phos-icssim-dev4` only:**

1. Misses of `in_range_command` satisfy `M_new <= floor(M_champion / 2)`.
2. The false-alert rate, defined above, is no higher than the champion's.
3. The alert budget stays 8 per shift.
4. On events both catch, the new alert time is not later than the champion's.

The score command for that detector is written with the module, after the champion report
exists, and it names these four bars unchanged. This record does not contain that score.

### Fallback

`subfloor_walk` is an attack the fallback command may pose, and only after the committed
champion report shows `M_champion` = 0. The operator writes `tank_level_max` from 6.5 toward
7.5 in 720 equal steps, one per simulated second. The step is `(7.5 - 6.5) / 720`. There is
no final jump to 7.5. The actuator is not held. No sensor is tampered. The scenario
`subfloor` draws `setpoint`, `maintenance`, and `subfloor_walk`, four events, over 7200
simulated seconds.

**Command, only after that gate:**

```
python scripts/icssim/generate_corpus.py development4-walk
uv run python scripts/lane_e_icssim_baseline.py --corpus data/phos-icssim-dev4-walk
```

**Result name:** `atlas-daily:day1-walk`

**Report:** `eval_runs/build/lane-daily/day1-walk.md`

The same miss and rate definitions apply, with `subfloor_walk` in place of `in_range_command`.
If that champion miss count is greater than 0, the walk detector may be built as specified
here, and not otherwise.

The walk column is per sample, not a running sum. A running sum is the shape ADR 0286 refused.
Where `tank_level_value` is above `tank_level_max`, the predicted `tank_input_valve_status` is
0, the value the pinned PLC1 line writes. Where the level is below `tank_level_min`, the
predicted status is the constant that same function writes in the min branch, copied from the
pinned source into the module. Samples inside the band are not scored, because the quoted
logic does not move the valve there. The raw value is the absolute error times `ONSET_LEVEL`,
calibrated by the same third-largest-peak rule. If the min branch does not write a constant,
the walk detector is refused and that refusal is the result. An alert counts only inside the
event window. One that lands later is a miss. The half-miss bars above apply to
`subfloor_walk`.

### What this record does not do

It does not generate a corpus, score a champion, or add a detector. It does not open a
held-out directory. It does not move v1, which stays 8 of 12. A simulated score, when one
exists, is diagnosis (ADR 0073), not a field rate, and not a change to any frozen count.

## Consequences

The evaluation set is in the generator, so the command above can run. Running it is the next
session's work. The denominator is whatever that score reports.

## What would reverse this

Generating `phos-icssim-dev4-walk` or either held-out directory before the gate in this
record. Widening 6.5–7.5, or changing 60, 180, 720, 1, or 3, after a detector has run.
Building `atlas-inrange-consistency` before `day1-champions.md` is committed, or building it
when `M_champion` is 0. Editing either champion file and scoring it under the digests above.
Opening `phos-icssim-dev`, `phos-icssim-dev2`, `phos-icssim-dev3`, or any spent or unopened
held-out named before this record.

# ADR 0398 — A weak episode keeps its right to place the alert

- **Status:** Accepted
- **Date:** 2026-11-01
- **PART:** Exploratory. Half A of ADR 0397, the declaration
- **Supersedes:** nothing
- **Depends on:** [ADR 0397](0397-an-exploratory-measurement-session-is-declared.md),
  [ADR 0286](0286-an-appended-column-cannot-win-a-slot-without-taking-the-alert.md),
  [ADR 0273](0273-the-stronger-engine-programme-is-declared.md),
  [ADR 0112](0112-a-window-is-a-span-of-seconds.md)

## Context

ADR 0397 asks one question of lane 3 and freezes four bars before anything runs: is the delay
failure ADR 0286 recorded a property of the **accumulator statistic** or of the **alert-placement
rule it was fed through**? This record is the declaration that question requires. It states the
alternative placement rule in prose, names the command and the result, and repeats the four bars
unchanged. **It was committed before any measurement ran.** Nothing below is a result.

### What ADR 0286 established, and what it left open

`phos.atlas.consistency.events` groups episodes, takes the highest-peak member as `best`, sets
`level = min(best[2], max(ONSET_LEVEL, ONSET_FRACTION * best[2]))`, starts the alert at `best`'s
peak row, and then moves it earlier **only** for a member whose own peak reaches `level`. A member
whose peak is below `level` is skipped by `if peak < level: continue` and cannot place the alert at
all. Alone an episode always qualifies against itself, because `level` is clamped by
`min(best[2], …)`. So a weak episode — peak between `THRESHOLD` (1.0) and `ONSET_LEVEL` (2.0) —
places its own early alert until a stronger column joins its group, and loses that right the moment
it does. That is the three-fact constraint ADR 0286 recorded, and it was measured, not inferred:
lane 3's cap sweep took the paired median from 1 s to 2, 3, 4 and 5 s as catches rose, and shrinking
the cap bought delay back only by losing catches the frozen engine keeps.

ADR 0286 was explicit that this is **not** a refutation of accumulation, and that a delay-aware
placement rule is "a **new function beside** the frozen one, under a new name, declared and measured
on its own". ADR 0397 authorises exactly that and nothing wider. This record is that declaration.

### What is not under test

The statistic is fixed at lane 3's module defaults — `SLACK_QUANTILE = 0.99`,
`CONTRIBUTION_CAP = 20.0` — and `phos.atlas.drift_consistency` is not edited. Its augmented matrix
keeps the frozen per-signal columns first, in place, then one capped accumulator column per signal.
The cap stays where lane 3 put it, for the reason recorded there: `ONSET_LEVEL / ONSET_FRACTION` is
the largest value for which `level` is still at its floor. **If the rule below fails, the cap is not
the knob that gets turned**; that sweep is on the record and repeating it is not a discovery.

## Decision

**Declare one new placement rule, as a pure function beside `events`, and measure it once against
the four bars. The frozen engine is not edited.**

### The rule, in prose

`phos.atlas.consistency.events` answers "where does this event's alert go?" with *the earliest
member that reaches the group's own level*. The alternative answers the same question with *the
earliest member that clears the threshold at all* — the bar an episode already had to clear to
exist. Concretely, for each group of chained member episodes, in the same grouping order and with
the same event boundaries:

1. **The score is still the group's strongest peak.** Event strength is `max(peak)` over members.
   The budget ranks events by this number, unchanged, so the same events win the same slots.
2. **The placement is the earliest qualifying sample in the group.** Every member qualifies, because
   `THRESHOLD` is the bar that made it an episode. The candidate row is the first sample at or after
   the member's start where that member's own column is `>= THRESHOLD`; the earliest such row over
   the group wins. Ties keep the member that started earlier, then the lower column index, so the
   rule is deterministic.
3. **No level is computed from the group's peak.** The rule does not read `best[2]` when placing, so
   a saturated accumulator joining a group can no longer move a weak member's alert later. That is
   the whole of the change.
4. **A signal is still named.** The placed cell is one column of one signal, so the alert still
   names an instrument and `phos.atlas.consistency_evidence` can still attribute it to an
   `ExpectedRange`. The accumulator columns occupy their own indices beside the per-signal ones, so
   which half placed the alert remains recoverable downstream.
5. **The budget is untouched.** The rule returns `ConsistencyEvent` objects of the same shape and in
   the same onset order, and `budget_alerts` is called on them exactly as it is today, unchanged.
   `ALERTS_PER_SHIFT`, `SHIFT_SECONDS` and the spare-second-alert rule are not read or written here.

**The honest name is `earliest_threshold_crossing`**, not "delay-aware" or "priority": it makes one
choice — the first sample the group can point at — and its cost is stated with it. It can move an
alert *earlier* than the frozen rule only by pointing at a weaker sample; where the frozen rule
would have found an earlier sample at or above `level`, both rules agree. It has no constant of its
own and nothing to tune.

### What is built, and where

- **New module** `src/phos/atlas/placement_consistency.py`, result name
  `atlas-placement-consistency`. Two public functions: `earliest_crossing_events` (the rule above,
  a pure function of the score matrix and a threshold) and `detect_with_placement` (one fit, then
  the rule and the unchanged `budget_alerts` per file).
- It **imports** from `phos.atlas.consistency`. It never writes it. `events`, `budget_alerts`,
  `THRESHOLD`, `ONSET_LEVEL`, `ONSET_FRACTION`, `ALERTS_PER_SHIFT`, `SHIFT_SECONDS`,
  `FROZEN_WINDOWS` and the detrend window stay exactly as they are, and the frozen row must still
  reproduce unchanged.
- It **does not import** `phos.atlas.drift_consistency` at module scope; the harness passes lane 3's
  `augmented_scores` matrix in. That keeps the placement rule a function of a matrix, so it can be
  driven by a hand-built matrix in a unit test.
- **New harness** `scripts/lane_e_placement.py`, modelled on `scripts/lane_e_drift.py` and reporting
  all four halves. **It writes no file**: like its sibling, it prints, and the report is written
  from its stdout, so the run cannot append `eval_runs/log.jsonl`.
- **New tests** `tests/atlas/test_placement_consistency.py` and
  `tests/scripts/test_lane_e_placement.py`, written first. No existing test is edited to accommodate
  the new rule.

### The command, after this record is committed

```
uv run python scripts/lane_e_placement.py --corpus data/phos-icssim-dev2
```

**Result name:** `atlas-placement:dev2`

**Report:** `eval_runs/build/lane-e/lane-placement-development.md`, written from that command's
stdout. `eval_runs/log.jsonl` is not appended. The frozen row is not overwritten.

Train is the three `normal` runs of `phos-icssim-dev2`. Test is the ten `mixed2` runs. Lane 3 is
fitted at its module defaults on the same three runs, so the only difference between lane 3's column
in this report and the column in `lane3-development.md` is the placement rule. **That comparison is
the measurement**: the frozen engine, lane 3 through the unchanged `events`, and lane 3 through the
new rule, all three printed side by side from one fit.

### The four bars, frozen here as in ADR 0397

Judged against the frozen engine on `phos-icssim-dev2`, with lane 3's statistic at its module
default. All four, or the lane is refused again.

1. **Attacks caught within eight alerts a shift: strictly more than 32 of 70.** A tie is not a pass.
2. **No attack the frozen engine catches is lost.** The paired set may not shrink below 32.
3. **Median detection delay over the paired set: no worse than 1 s, under both the paired and the
   own-set readings.** Both must hold. An attack counts as caught when a budgeted alert lands
   inside its window; delay is that alert's time minus the window's start.
4. **Benign events drawing an alert: no higher than 5 of 20.**

A partial win is a refusal, written up in the same voice as a win.

### The outcome that closes the question

If the delay cannot be improved without losing catches or raising benign alerts, that is the
result, and it is written as a refusal. It would then be evidence that the failure is the
statistic's, not the placement rule's — which is the distinction ADR 0397 opened this half to
settle. **No corpus is opened to reach that answer**: development data only, no held-out directory,
no HAI edition, no BATADAL, no T1 seed set.

## Consequences

The rule is a candidate and not a keeper. On a pass it is kept as a result about the engine's own
machinery on a simulated plant and **nothing more**: R4 and ADR 0143 make a synthetic score
diagnosis, not proof, and no sentence here says Atlas is any particular strength or speed on a real
plant. A later held-out score would need its own declaration; none is authorised by this record.

The frozen engine, every frozen row, every prior and `EVIDENCE_STRENGTH` are untouched by
construction, because the rule reads them and cannot write them. A test pins that the frozen
detector's alert list is unmoved by the new module's existence.

## What would reverse this

Editing `phos.atlas.consistency`, `phos.atlas.drift_consistency`, `atlas/templates.py`, any prior or
`EVIDENCE_STRENGTH` to make a result land. Retuning `CONTRIBUTION_CAP` or `SLACK_QUANTILE` after
seeing the result, or reproducing ADR 0286's cap sweep and reporting it as a discovery. Inverting
the rule so the *latest* member places the alert, or letting the rule read the group's peak. Calling
a rule that fires on `THRESHOLD` a delay-aware or priority rule. Reporting a win on one delay
definition while failing the other. Buying recall with benign alerts, or delay with lost catches.
Opening a held-out corpus, reading a red-tier corpus, appending `eval_runs/log.jsonl`, or overwriting
a frozen row. Claiming this session is a detection claim, a field result, or a promise that the
measurements can be pushed.

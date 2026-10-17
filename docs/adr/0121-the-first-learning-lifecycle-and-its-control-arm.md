# ADR 0121 — The first learning lifecycle, and its control arm

- **Status:** Accepted
- **Date:** 2026-10-12
- **PART:** learning engine S4 and S5
- **Depends on:** [ADR 0114](0114-the-liar-measurement-is-assembled-and-held.md),
  [ADR 0117](0117-two-loops-a-seen-ledger-and-the-held-out-bank.md),
  [ADR 0119](0119-why-a-liar-run-fails-by-a-declared-precedence.md),
  [ADR 0120](0120-the-arena-tasks-an-enforced-budget-and-a-fence.md)

## Context

`docs/learning-engine.md` asked for one full lifecycle on a controlled example before anything
wider: a recorded failure, a diagnosis, competing hypotheses, bounded search, a check on runs the
search never saw, and only then a gate. It also asked whether diagnosis-led search beats search
that ignores the diagnosis, under the same budget. The example is the water-treatment liar
(ADR 0119: 10 of 14 development failures are the inlet below threshold).

## Decision

1. **The task was declared and pushed before any arena run**
   (`experiments/arena/water-liar/task.json`, commit `2b9bbd2`). Three hypotheses (longer lags,
   slower detrending, both), six runs each, the regression slices, and the qualifying and choice
   rules. `phos.breaking.liar_selection` writes those rules as code, kept outside the scorer's
   pinned files, so the choice is mechanical.
2. **The control arm was declared and pushed before any of it was scored**
   (`experiments/arena/water-liar-control/`, commit `ff158d4`). Same failure, scorer, slices and
   rule; 18 candidates drawn by `scripts/arena_control.py` (seed 20261012) from random one- or
   two-field window changes.
3. **The red team runs once per task** (`scripts/arena_red_team.py`): the chosen candidate and the
   champion on `RED_TEAM_SEEDS` (95101–95110), seeds no attempt was scored on. It survives only if
   it passes more water runs and loses no run the champion passes.
4. **`scripts/learning_progress.py`** writes `eval_runs/learning/progress.{json,md}`, keeping
   throughput apart from progress.

Every attempt in both arms carries the same scorer sha256 (`4843c9e3…`).

## Results (synthetic development data; diagnosis, not proof)

| | Targeted (`water-liar`) | Control (`water-liar-control`) |
| --- | --- | --- |
| Runs used | 12 of 18 | 18 of 18 |
| Compute | about 25 min | about 33 min |
| Qualifying candidates | 7 | 2 |
| Best water passes, arena (champion 0 of 30) | 23 | 13 (did not qualify: HAI 36/38) |
| Chosen | lags 0, 5, 15, 30, 60, 300, 900 s; detrend 12 h | fit_step 2 s; detrend_step 240 s |
| Chosen on the arena: water, total (champion 0, 24 of 90) | 23, 66 | 12, 40 |
| Red team: water, total (champion 0, 52 of 180) | **51, 125** | 18, 74 |
| Red team: champion passes lost | 2 (power 95107 at 0.4 and 0.8) | 2 (power 95105 and 95107 at 0.4) |
| Verdict | **fails** | **fails** |

HAI 20.07 stayed 37/38 for every targeted attempt.

**What it shows.**
- **The red team did its job.** Both chosen candidates were better on the arena seeds and lost
  champion passes on unseen seeds. Neither goes to the gate. Validated improvements: **0**. T1's
  360 held-out runs stay held (ADR 0114), and no validation corpus was read.
- **Diagnosis-led search found more, and better.** On one task, with two-thirds of the runs: 7
  qualifying candidates against 2, and a chosen candidate with 51 of 60 unseen water runs against
  18. This is one task, one control draw and synthetic plants. It is a first observation, not
  evidence that failure-driven search is better in general (`docs/learning-engine.md` §8.1).
- **Longer memory is the lever.** Every targeted attempt that added minutes-long lags raised
  water passes. Detrending alone did less. That matches ADR 0114's prose diagnosis.
- **A success that is fragile.** Three of the four lost runs are power generation at subtlety 0.4,
  and both arms lose seed 95107 there. The champion's pass there may rest on a narrow margin. That
  is a channel-E question (`docs/learning-engine.md` §2): diagnose the champion's power-0.4 passes
  before blaming the candidate.

## Consequences

The next task should be opened on what the red team found, not by tuning the failed candidate:
a diagnosis of the power-generation 0.4 runs, then a task whose regression slice includes them.
The six unused targeted runs stay unused; a new task gets a new budget.

Tests: `tests/breaking/test_liar_selection.py`, `tests/scripts/test_arena_control.py`,
`tests/scripts/test_learning_progress.py`. No detector default, frozen row or log line changes.
Nothing is promoted.

## What would reverse this

Promoting either candidate; re-running a red team after seeing its result; scoring a held-out
seed; or quoting the arena figures as a T1 result.

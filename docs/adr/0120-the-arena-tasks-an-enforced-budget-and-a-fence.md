# ADR 0120 — The arena: tasks, an enforced budget, and a fence

- **Status:** Accepted
- **Date:** 2026-10-12
- **PART:** learning engine S3
- **Depends on:** [ADR 0084](0084-non-saturating-aggregation-for-sentiel.md),
  [ADR 0096](0096-sandbox-event-grouping-explains-the-budget-gap.md),
  [ADR 0112](0112-consistency-windows-by-sample-period-and-one-batadal-score.md),
  [ADR 0117](0117-two-loops-a-seen-ledger-and-the-held-out-bank.md),
  [ADR 0119](0119-why-a-liar-run-fails-by-a-declared-precedence.md)

## Context

ADR 0117 promised an arena for the fast loop. `docs/learning-engine.md` found that the 4 October
sandbox's 25-run budget was stated in the agent's prompt and never enforced, and that the harness
paths were hard-coded to one machine. The first task the arena must serve is the water-treatment
liar (ADR 0119): 10 of 14 development failures are the consistency inlet staying below its
threshold.

## Decision

1. **`phos.eval.arena`.**
   - `ResearchTask`: motivated only by eligible learning records sharing its mechanism
     (`check_motivation`); one to three hypotheses (ADR 0084's cap); a run budget of at most 25 per
     hypothesis; regression slices; an evaluation plan. Declared before any arena run.
   - `AttemptLog`: append-only and hash-chained, like the ADR 0118 ledger. It refuses an attempt
     past its hypothesis's budget, a misnumbered attempt, an undeclared hypothesis, or a candidate
     whose hash does not match. A hand-added line past the budget is refused on load.
   - `forbidden_candidate_paths`: a candidate's diff may touch only
     `experiments/arena/<task>/<hypothesis>/`. The scorer, the gate, the registry, the records
     and the frozen detector are outside it.
   - `payloads_present`: lists any `validation` or `held-out` data file in a worktree.
2. **A candidate is a consistency window set in seconds**, converted by ADR 0112's rule.
   `scale_windows` applies that rule to any set; a test checks
   `scale_windows(FROZEN_WINDOWS, p) == windows_for_period(p)` at eight periods.
   `windows_for_period` is untouched. `phos.breaking.liar.fit_inlet` gains an optional `base`; the
   default is exactly T1's.
3. **The liar slice** (`phos.breaking.liar_arena`) scores a window set on development seeds
   declared here: **`ARENA_LIAR_SEEDS` = 4242, 95001–95004**. **`RED_TEAM_SEEDS` = 95101–95110**
   are kept back and scored only after a candidate is chosen. Both are disjoint from T1's held-out
   seeds and the calibration seeds (a test checks). Every run is diagnosed by ADR 0119's precedence.
4. **The HAI 20.07 slice**: recall within the 8-per-shift budget on the frozen candidate's
   development corpus, the arena's only real corpus (ADR 0117). Before anything else it was checked
   to reproduce ADR 0116's **37/38** for the champion.
5. **`scripts/arena.py`**: `open` validates a task and scores the champion once as its baseline;
   `score` checks the budget before scoring, writes the candidate into its fenced directory, scores
   both slices, and appends the attempt with the scorer's sha256 (`SCORER_FILES`); `fence` and
   `payloads` are the two checks. Results go under `eval_runs/arena/<task>/`.

## The champion on the arena (synthetic, development only)

Liar slice, 90 runs on five seeds: **24 pass**. Of the 66 failures: 45 `inlet_subthreshold`, 9
`inlet_not_promoted`, 8 `insufficient_observations`, 4 `inlet_unavailable`. HAI 20.07: 37/38.
One liar scoring takes about 100 s; HAI 20.07 about 20 s.

## Consequences

Tests: `tests/eval/test_arena.py`, `tests/breaking/test_liar_arena.py`,
`tests/scripts/test_arena_cli.py`, and the new cases in `tests/atlas/test_consistency_windows.py`.
No validation or held-out corpus is read. No detector default, frozen row or log line changes.

Two limits stated, not solved:
- The fence and the payload check are functions and a script. CI does not yet run `fence` on
  candidate branches.
- An agent with shell access could still read `data/` in another checkout by absolute path
  (`docs/learning-engine.md` §8).

## What would reverse this

Scoring a candidate on a red-team seed before one is chosen; an attempt past its budget; editing a
scorer file without the pinned sha256 changing; or reading a validation corpus in the arena.

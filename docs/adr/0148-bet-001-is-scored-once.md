# ADR 0148 — Bet 001 is scored once, with the ranking fixed first

- **Status:** Accepted
- **Date:** 2026-10-17
- **PART:** Build lane A, Sentiel S1
- **Depends on:** [ADR 0084](0084-non-saturating-aggregation-for-sentiel.md),
  [ADR 0093](0093-bet-001-three-candidates-declared.md),
  [ADR 0145](0145-bet-001-not-run.md)

## Context

ADR 0145 recorded that Bet 001 could not run in round 1, because CERT r3.1 was
not on disk. It is now: `r3.1/`, `answers/` and the entity-day trace cache
resolve from the lane folder.

ADR 0093 named three formulas and did not score them. The success test was
fixed earlier: at 48 alerts, a day of the insider 6B misses must be in the
budget, and the insider 6B already finds must still be there. This record
fixes how "the top 48" is read, and then the run is allowed. It does not
contain a score.

## Decision

1. The formulas stay `linear-excess`, `gaussian-tail`, and `family-max`, with
   the parameters ADR 0093 pinned. No fourth formula. No weight. `emit_k`
   stays 1.0. `AggregationPolicy()` is not edited. The frozen 6B detector
   name is not reused.

2. The one run is `uv run python scripts/lane_a_bet001.py`. It reproduces the
   frozen 6B point first, through `check_frozen_row`, and stops if that gate
   fails. It does not append `eval_runs/log.jsonl`.

3. Each candidate ranks every person-day by `(-score, user_id, timestamp)`
   and keeps 48. The malicious flag is not in the key. A tie does not widen
   the 48. A user counts as found only when one of their labelled malicious
   days is inside those 48.

4. The result file is `eval_runs/build/lane-a/bet-001.json`. All three
   candidates are in it. Chance is the expected number of malicious days in a
   random 48. The bet page on this branch records the same numbers after the
   run, whichever way it goes.

## Consequences

A later change to Sentiel's features is a different experiment. It may not
edit these three formulas or this ranking to chase the result.

## What would reverse this

Scoring a fourth formula in this file. Putting the label into the sort.
Overwriting the published 0.104.

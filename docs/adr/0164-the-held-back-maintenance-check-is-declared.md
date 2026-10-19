# ADR 0164 — The held-back maintenance check is declared before it runs

- **Status:** Accepted (a declaration; the score is recorded after the one run)
- **Date:** 2026-10-18
- **PART:** Build lane B, A5 / W4, round 2
- **Depends on:** [ADR 0144](0144-the-october-build-is-declared.md),
  [ADR 0150](0150-maintenance-alerts-close-only-with-a-citation.md),
  [ADR 0151](0151-the-maintenance-closure-harness-is-declared.md),
  [ADR 0153](0153-maintenance-closure-on-the-development-seeds.md)

## Context

ADR 0151 declared the synthetic maintenance-closure harness. ADR 0153 recorded
its development result on seeds 97001–97020: 158 of 180 maintenance alerts
closed with a cited order (0.8778), 0 of 80 attack alerts closed, 0 of 40 MIMIC
alerts closed. ADR 0144 holds seeds 97101–97120 back for one score.

The harness refused every seed outside 97001–97020, so it had no held-back path.

## Decision

1. `build_held_back_seed` draws a seed from 97101–97120 with the same code as
   `build_seed`; only the seed gate differs. `score_held_back_closures_once` and
   `score_held_back_consistency_once` call it. The development functions still
   refuse a held-back seed. After the refactor, the development run gave the
   same counts as ADR 0153; only the runtime changed.

2. The one command is `uv run python scripts/lane_b_heldback.py --run`, result
   name `lane-b-maintenance-closure-heldback`. The declaration file
   `eval_runs/build/lane-b/heldback-declaration.json` holds the sha256 of six
   scored files. The script refuses to run if any hash differs, or if the result
   file already exists.

3. The bars are the ones ADR 0151 named: at least 70% of maintenance alerts close
   with a cited order, and no attack alert closes, MIMIC included.

## A look that came first, disclosed

Before this lane's round-1 branch was pulled, this session found an uncommitted
draft harness in the lane folder (`alert_closure.py`, `innocence_harness.py`).
It declared that draft by commit (`ffceffb`) and scored seeds 97101–97120 with
it once (`7b321f3`): 57 of 57 maintenance alerts closed, 0 of 60 attack alerts
closed, 0 of 20 MIMIC alerts closed. Both commits are kept on
`backup/lane-b-draft-harness`. Nothing in this ADR's harness was changed after
that look. The report states both numbers.

## Consequences

The held-back number is recorded whichever way it goes, and nothing is tuned on
it. A pass is synthetic diagnosis. It does not show that a real plant's work
orders close real alerts.

## What would reverse this

A second run of this command. An edit to a scored file between the declaration
and the run. Quoting a closure count as a detection rate.

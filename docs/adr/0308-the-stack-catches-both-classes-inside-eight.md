# ADR 0308 — The stack catches both classes inside eight

- **Status:** Accepted
- **Date:** 2026-10-22
- **PART:** Atlas daily leaps, the stack
- **Supersedes:** nothing
- **Depends on:** [ADR 0305](0305-two-setpoints-inside-the-band-are-one-move.md),
  [ADR 0307](0307-a-720-step-walk-is-invisible-to-the-joint-check.md)

## Context

The joint check misses every one-tag walk. The walk check misses every two-tag move.
Each, on a fixture of four moves and four walks, catches 4 and misses 4. The better of
them still misses 4. The page holds 8.

## Decision

**`stack_page` returns both classes, at most 8, earliest first. On that fixture the
misses go from 4 to 0, which is at most half. A lone in-band write adds nothing.**

`src/phos/atlas/leap_stack.py` calls `joint_moves` and `subfloor_walks`. It does not
call `budget_alerts`. It does not edit either checker.

No corpus was generated. v1 stays 8 of 12. This is a fixture. It is not a detection claim.

## Consequences

The two classes share one page. A later session still cannot open the walk corpus from
this record.

## What would reverse this

Dropping a walk to keep a joint, or the reverse, when both fit in 8. Editing either
checker so that one class starts to see the other by retuning a window.

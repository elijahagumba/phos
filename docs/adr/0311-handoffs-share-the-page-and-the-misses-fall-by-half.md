# ADR 0311 — Handoffs share the page and the misses fall by half

- **Status:** Accepted
- **Date:** 2026-10-22
- **PART:** Atlas daily leaps, the handoff page
- **Supersedes:** nothing
- **Depends on:** [ADR 0308](0308-the-stack-catches-both-classes-inside-eight.md),
  [ADR 0310](0310-the-same-value-after-the-window-is-one-handoff.md)

## Context

The stack catches joint moves and walks. It misses every handoff. On a fixture of
two joint moves, two walks, and eight handoffs, the stack catches 4 and misses all
8 handoffs. The page holds 8. The three checks are not retuned, and the stack
function is not edited.

## Decision

**`handoff_page` returns all three classes, at most 8, earliest first. On that
fixture the handoff misses go from 8 to 4, which is at most half. A lone in-band
write adds nothing.**

`src/phos/atlas/handoff_page.py` calls `joint_moves`, `subfloor_walks`, and
`band_handoffs`. It does not call `budget_alerts`. It does not edit those checkers
or `leap_stack.py`.

The two joint moves and two walks are the earlier hits, so they stay. Four of the
eight handoffs fit in the remaining slots. Four handoffs are missed.
`4 <= floor(8 / 2)`.

No corpus was generated. v1 stays 8 of 12. This is a fixture. It is not a detection
claim, and it does not open the walk corpus.

## Consequences

The three classes share one page. A later session still cannot open the walk corpus
from this record.

## What would reverse this

Dropping an earlier joint or walk to keep a later handoff when the earlier one fits.
Editing a checker so that one class starts to see another by retuning a window.

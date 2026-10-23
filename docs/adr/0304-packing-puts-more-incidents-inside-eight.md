# ADR 0304 — Packing puts more incidents inside eight

- **Status:** Accepted
- **Date:** 2026-10-22
- **PART:** Atlas daily leaps, the counting day
- **Supersedes:** nothing
- **Depends on:** [ADR 0300](0300-a-kept-day-halves-the-remaining-misses.md),
  [ADR 0303](0303-the-shift-page-holds-eight.md)

## Context

The shift page holds 8 alerts (ADR 0303). Repeated alerts of one incident spend those
slots, and a quieter incident never appears. `group_evidence` already collapses signals
that share a declared subsystem. It is not edited, and this day does not inherit the
refused 53 of 70. The chain window is the frozen `EVENT_WINDOW` of 300 seconds and the
span is the frozen `EVENT_SPAN` of 600. Neither number is retuned.

## Decision

**On the declared fixture, packing cuts the incidents the budget misses from 2 to 0,
which is at most half, and the page still holds at most 8.**

`src/phos/atlas/incident_pack.py` takes alerts the caller has already labelled with an
incident id.

- The same id joins when the gap is at most 300 seconds and the chain spans at most 600.
- Two ids never join, however close they are.
- The representative time is the earliest member. The score that competes is the
  strongest member.
- The page keeps at most `ALERTS_PER_SHIFT` representatives.
- `group_evidence` is not called. `grouping.py` and `consistency.py` are not edited.

The fixture is five incidents: three of them have three alerts each, scored above the
two single alerts. Unpacked, the top 8 alerts are three incidents and miss two. Packed,
all five fit. Misses go from 2 to 0. `0 <= floor(2 / 2)`. The packed page uses 5 slots,
which is not more than 8.

No corpus was generated. `eval_runs/log.jsonl` was not appended. v1 stays 8 of 12. This
is a fixture. It is not a detection claim.

## Consequences

A later session can pass labelled alerts and get one slot per chain. It cannot invent an
incident by time alone, and it cannot edit the frozen grouper to do it.

## What would reverse this

Merging two incident ids because they are close. Retuning 300 or 600. Editing
`group_evidence`. Quoting this fixture as a plant result.

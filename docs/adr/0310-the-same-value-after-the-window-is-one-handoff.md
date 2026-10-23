# ADR 0310 — The same value after the window is one handoff

- **Status:** Accepted
- **Date:** 2026-10-22
- **PART:** Atlas daily leaps, the handoff
- **Supersedes:** nothing
- **Depends on:** [ADR 0300](0300-a-kept-day-halves-the-remaining-misses.md),
  [ADR 0305](0305-two-setpoints-inside-the-band-are-one-move.md),
  [ADR 0308](0308-the-stack-catches-both-classes-inside-eight.md)

## Context

The joint check joins two tags only inside the frozen 300-second window. The walk check
wants 720 steps of one tag. The stack is those two checks. A second tag that takes the
same in-band value after that window, and before a shift is over, is invisible to all
three. The window and the shift length are the constants already in the engine. Neither
is retuned. A pair inside the window stays the joint check's.

## Decision

**On the declared fixture, twelve handoffs the stack misses become a page of 8 that
misses 4, which is at most half. A pair inside the joint window adds no handoff.**

`src/phos/atlas/band_handoff.py` takes setpoint steps the caller supplies.

- Two different tags, the same value inside 6.5-7.5, with a gap longer than 300 seconds
  and shorter than one shift, are one handoff. The time is the earlier write. The score
  is 2, the count of tags. It is not a confidence.
- The same tag twice returns nothing. A different value returns nothing. A value outside
  the band returns nothing. A gap of one full shift returns nothing.
- A gap of 300 seconds returns nothing, and the joint check returns that pair.
- The joint check, the walk check, and the stack return nothing on one handoff pair.
- Twelve such pairs: those three still return nothing, and the handoff check returns 12.
  Placed on the incident page, 8 are shown and 4 are missed. `4 <= floor(12 / 2)`.

No corpus was generated. `eval_runs/log.jsonl` was not appended. v1 stays 8 of 12.
`consistency.py` was not edited. This is a fixture. It is not a detection claim, and it
does not open the walk corpus.

## Consequences

A later session can pass named setpoint writes and see the pair the joint window drops.
It cannot turn a function code into a step, and it cannot treat a pair the joint check
already owns as this alert.

## What would reverse this

Widening 6.5-7.5. Retuning 300 or the shift length. Counting a same-tag repeat as a
handoff. Counting a pair inside the joint window as a handoff. Quoting the fixture as a
plant result.

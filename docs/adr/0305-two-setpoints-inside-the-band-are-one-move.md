# ADR 0305 — Two setpoints inside the band are one move

- **Status:** Accepted
- **Date:** 2026-10-22
- **PART:** Atlas daily leaps, the joint day
- **Supersedes:** nothing
- **Depends on:** [ADR 0300](0300-a-kept-day-halves-the-remaining-misses.md),
  [ADR 0304](0304-packing-puts-more-incidents-inside-eight.md)

## Context

A single setpoint inside 6.5-7.5 is the ordinary operator write. One tag in that band
raises nothing. The class a single-tag check misses is two or more tags moving inside
that same band, close enough to be one chain. The chain uses the frozen event window
of 300 seconds and the frozen span of 600. Neither is retuned. A value outside the band
is not this class. A Modbus function code is not a step.

## Decision

**On the declared fixtures, the joint move cuts the misses at least in half, and a
single in-band write adds no alert.**

`src/phos/atlas/joint_setpoint.py` takes setpoint steps the caller supplies.

- One tag inside the band returns no move.
- Two or more tags inside the band, within the frozen window, return one move. The time
  is the earliest step. The score is the count of tags. It is not a confidence.
- Two tags separated by more than 300 seconds do not join.
- Four such pairs are all returned. The single extra write returns nothing.
- Twelve pairs, placed on the incident page, show 8 and miss 4. The single-tag check
  misses all 12. `4 <= floor(12 / 2)`. The page does not exceed 8.

No corpus was generated. `eval_runs/log.jsonl` was not appended. v1 stays 8 of 12.
`consistency.py` was not edited. This is a fixture. It is not a detection claim.

## Consequences

A later session can pass named setpoint writes and see the joint ones. It cannot turn a
function code into a step, and it cannot treat one ordinary write as this alert.

## What would reverse this

Widening 6.5-7.5. Retuning 300 or 600. Counting a one-tag chain as a move. Quoting the
fixture as a plant result.

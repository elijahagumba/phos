# ADR 0307 — A 720-step walk is invisible to the joint check

- **Status:** Accepted
- **Date:** 2026-10-22
- **PART:** Atlas daily leaps, the walk
- **Supersedes:** nothing
- **Depends on:** [ADR 0300](0300-a-kept-day-halves-the-remaining-misses.md),
  [ADR 0305](0305-two-setpoints-inside-the-band-are-one-move.md)

## Context

`joint_moves` returns nothing for one tag. A setpoint walked from 6.5 toward 7.5 in 720
steps, one second apart, is one tag inside the band for the whole walk, so the joint
check misses it. The frozen event span is 600 seconds. This walk is longer than that.
The span is not retuned. 720 is the harness floor already written down. The ICSSim
sub-floor corpus stays ungenerated. ADR 0301 has not been scored.

## Decision

**A one-tag chain of 720 in-band steps, gaps of at most one second, is one walk at the
first step. The joint check stays silent. 719 steps are not a walk.**

`src/phos/atlas/subfloor_walk.py` takes the same setpoint steps as the joint check.

- One step returns nothing. A value outside 6.5-7.5 does not count.
- A two-second gap splits the chain. Neither side reaches 720, so nothing is returned.
- The alert time is the first step.
- Twelve such walks, one tag each, placed on the incident page of 8, miss 4. The joint
  check misses all 12. `4 <= floor(12 / 2)`.

No corpus was generated. `consistency.py` was not edited. v1 stays 8 of 12. This is a
fixture. It is not a detection claim.

## Consequences

A later session can pass a walked tag and see it. It cannot treat 719 steps as the
class, and it cannot open the sealed walk corpus from this record.

## What would reverse this

Lowering 720 after a run. Retuning the frozen 600-second span so the walk fits it.
Generating `phos-icssim-dev4-walk` before ADR 0301's gate.

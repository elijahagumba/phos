# ADR 0109 — Subtlety 0.0 in the liar declaration is the obvious end, not "no attack"

- **Status:** Accepted
- **Date:** 2026-10-11
- **PART:** v1 T1, an open question settled without a run
- **Depends on:** [ADR 0094](0094-liar-measurement-seeds-and-pass-share.md)

## Context

After ADR 0094 was committed, the question was raised (in a working prompt, not in a record) whether
the value `0.0` among its six values meant no manipulation at all. If it did, 60 of the 360 runs
would have no liar in them, yet the pass predicate would ask Atlas to name the instrument as at
fault in each, and a new named declaration would be needed.

## Decision

**The question is settled by reading the library, and no new declaration is needed.** The six
values are `phos.library.ot.SUBTLETIES`, a *subtlety* dial, not a magnitude. In
`phos.synth.attacks.spec`, `DifficultyLevel.for_subtlety` maps subtlety below 0.25 to `OBVIOUS`
("a naive detector should catch this"), below 0.6 to `MODERATE`, below 0.9 to `SUBTLE`, and 0.9 and
above to `NEAR_INVISIBLE`, "up to the zero-magnitude control at 1.0". So `0.0` is the most obvious
liar, at full magnitude. The zero-magnitude control is `1.0`, which is not among ADR 0094's values.
Every one of the 360 declared runs contains a liar.

ADR 0094 is unchanged. Its own text already calls the values "the graded dial already in
`SUBTLETIES`". Where later notes or prompts call them "magnitudes", they mean this dial.

## Consequences

The liar measurement waits only on what ADR 0108 supplied (a facet Atlas emits) and on a run
declared before it is scored. Nothing is scored here.

## What would reverse this

A change to `SUBTLETIES` or to the difficulty bands, which would be its own record.

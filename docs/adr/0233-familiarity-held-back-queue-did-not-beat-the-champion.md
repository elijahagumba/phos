# ADR 0233 — Familiarity's held-back queue did not beat the champion

- **Status:** Accepted
- **Date:** 2026-10-19
- **PART:** Build brief D, lane Q
- **Depends on:** [ADR 0232](0232-familiarity-is-frozen-before-the-held-back-queue.md)

## Context

ADR 0232 froze `familiarity` and named the one command. This record is the result of
that command, run once. The output file now exists, so a second run is refused.

## Decision

**Result name.** `atlas-queue-v2:familiarity`

**Seeds.** 97601–97620, the generator in ADR 0231.

| Ordering | A3 | Recall within 8 |
| --- | ---: | ---: |
| Champion | 20/20 | 20/20 |
| `familiarity` | 20/20 | 20/20 |

A3 is not strictly higher. Recall within 8 is not lower. The bar is not met. The run is
not repeated and the bar is not reworded.

The development margin was already zero (ADR 0232). Held-back agrees: every seed passed
under both orderings.

## Consequences

Lane Q stops on this ranker. The real-data gate is a separate record and is not run here.
v1's A3, 57 of 203, is unchanged.

## What would reverse this

A second run, or treating 20 of 20 against 20 of 20 as a pass.

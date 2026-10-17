# ADR 0132 — Grade B: links seen to propagate from logged changes, and how ICSSim judges them

- **Status:** Accepted
- **Date:** 2026-10-15
- **PART:** ADR 0130 build order, second step, before it is scored
- **Depends on:** [ADR 0128](0128-icssim-roles-loops-and-the-development-slice.md),
  [ADR 0130](0130-the-graded-plant-model.md)

## Context

ADR 0130's grade B is a link earned by intervention: a logged change to one point, followed by
another point's response, again and again, the responder never moving first. Its falsifier 2
needs ICSSim's true cause-and-effect graph declared before B is scored. Both are fixed here.

## Decision

**1. The method** is `phos.atlas.interventions`, with these constants, set now:

| Constant | Value | Meaning |
| --- | --- | --- |
| `HORIZON_SECONDS` | 120 | A response may take this long; means are taken over this window |
| `NULL_QUANTILE` | 0.99 | A shift counts beyond this quantile of the signal's ordinary shifts |
| `NULL_STRIDE_SECONDS` | 30 | Ordinary shifts are sampled this often, two horizons from any change |
| `MIN_CHANGES` | 3 | A link needs at least this many changes on its driver |
| `AGREEMENT` | 2/3 | And a response to at least this share of them |

A **response** is a shift in a signal's mean, after the change against before it. **Moving
first** is the same test one horizon earlier; one such change disqualifies the pair.

**2. The changes** are every logged write in the three normal development runs that changed its
point's value (`phos.breaking.icssim_runs.load_interventions`): the operator's maintenance mode
writes and level-limit changes. The attack runs are not used.

**3. The truth** is `phos.breaking.icssim_truth.ICSSIM_EDGES`: 20 direct edges, each a line of
ICSSim's physics, its two PLC programs, or its mode handling, at the pinned commit. A link is
**true** when a directed path of true edges runs from its driver to its responder. A test checks
that nothing under `phos.atlas` imports it.

**4. The verdict.** Falsifier 2 fails if fewer than 8 in 10 links are true. Because ICSSim is a
small, tightly coupled plant, most pairs are reachable from a written point: the record reports
the chance precision (the share of all pairs from the written points that are on a true path)
beside the measured one, so a pass that only matches chance is visible.

## Consequences

- Scored once, by `scripts/plant_map_dev.py intervened`, after this record is committed.
- HAI logs no writes, so grade B is not available on it. A design partner's historian or work
  orders would supply the changes there.

## What would reverse this

Changing a constant or the truth after the first score; using the attack runs; or letting
anything that learns import the truth.

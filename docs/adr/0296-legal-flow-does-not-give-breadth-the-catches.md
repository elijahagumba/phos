# ADR 0296 — On the development runs, breadth caught fewer attacks than the frozen engine

- **Status:** Accepted
- **Date:** 2026-10-21
- **PART:** Build brief E, lane 2, development only
- **Supersedes:** nothing
- **Depends on:** [ADR 0295](0295-legal-flow-biases-the-level-and-keeps-the-plants-own-flow.md)

## Context

ADR 0295 fixed `legal_flow` and named the command before this run. The seven development
runs were generated after that commit. `phos-icssim-heldout3` was not generated and was not
opened. The fraction band was not changed.

The command was `uv run python scripts/lane_e_icssim_baseline.py --corpus data/phos-icssim-dev3`.
It prints catch counts. It does not print which signal accounts for the breadth detector's
catches, so the second bar is not answered here.

## Decision

**The first bar fails.** On 4 `mixed3` runs, 32 attacks and 8 benign events:

| | frozen | lane 1 | breadth |
| --- | --- | --- | --- |
| attacks caught | 16 of 32 | 20 of 32 | 15 of 32 |
| benign events drawing an alert | 2 of 8 | 1 of 8 | 2 of 8 |

Breadth's 15 is not strictly more than the frozen engine's 16. Lane 2 stays undeclared.
0277 and 0278 stay unwritten. `f` stays 0.03 to 0.08.

`legal_flow` itself was 2 of 4 for the frozen engine, 2 of 4 for lane 1, and 2 of 4 for
breadth. Where lane 1 caught it, the catching column was a signal column. The class is not
invisible to the frozen engine, and breadth did not catch the two the frozen engine missed.

Lane 1's 20 of 32 is this development corpus only. It does not replace the held-out 87 of 120
(ADR 0276). Simulated, so diagnosis, not proof. v1 stays 8 of 12. `eval_runs/log.jsonl` was
not appended.

## Consequences

A level bias that keeps flow legal does not give the joint score the catches on these four
runs. The next change to the class would be a new declaration, not an edit of this band.

## What would reverse this

A different development command, or a change to 0.03 or 0.08 after this table. Opening
`phos-icssim-heldout3` to try again. That half stays unopened.

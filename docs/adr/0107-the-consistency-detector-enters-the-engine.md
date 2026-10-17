# ADR 0107 — The consistency detector enters the engine, unchanged

- **Status:** Accepted
- **Date:** 2026-10-11
- **PART:** v1, rebuilding the detector after G1
- **Depends on:** [ADR 0103](0103-the-frozen-candidate-is-declared-on-clean-hai.md),
  [ADR 0104](0104-the-frozen-candidate-on-clean-hai.md),
  [ADR 0106](0106-four-checks-on-the-frozen-candidate.md)

## Context

The sandbox candidate (`experiments/2026-10-04-sandbox/candidate.py`, sha256
`7d485b72…20433d4`) was frozen on 4 October 2026 and scored once on the clean HAI editions:
53/58 on HAI 22.04 and 36/52 on HAI 23.05 within 8 alerts per 8-hour shift, against grouped
MinMax's 10/58 and 6/52 (ADR 0104). The four checks in ADR 0106 found the result well above a
random-alert null (max 9 and 8 in 500 draws), driven mostly by its loop score, with independent
alert lists for its two rows. The controls put grouping at 21/58 and 15/52, so the loop model
carries the remaining 32 and 21 attacks. G1's rule applies: Atlas trailed badly, so the detector
is replaced before anything is built on it.

## Decision

**1. `phos.atlas.consistency` is that candidate, ported without changing a number.** The scored
configuration only: loop and range scores, detrending, in-sample calibration by the third-largest
training episode peak, events, and one alert per event per shift with spare second alerts. The
frozen file's ablation switches and its unused calibration modes are not carried over, because
nothing was scored with them. Every constant is the frozen file's, and the operations keep their
order and dtypes.

**2. Identity is a test, not a claim.** `tests/atlas/test_consistency.py` loads the frozen file
(checking its sha256), runs it and the port on one fixed synthetic plant with a frozen instrument
and an out-of-range reading, and requires the same rows, columns and scores, element for element.
A second test requires every ported constant to equal the frozen file's. Both are `lab_only`,
because the frozen file is not published.

**3. The loop score is exposed on its own.** `feature_components` returns the calibrated loop and
range scores separately; their maximum is `feature_scores`. The loop score is what the reasoning
layer will cite as consistency evidence. That wiring is the next record, not this one.

**4. Result name `atlas-v1-consistency`.** Anything this detector scores carries that name. No
result is scored in this record.

**5. Windows are in samples.** On HAI a sample is one second. Scoring a corpus with another sample
period (BATADAL is hourly) needs a declared scaling rule first (roadmap §2.0, A6).

## Consequences

- Atlas now has a detector that has beaten grouped published methods on data it was not developed
  on. Its numbers on HAI 20.07 and 21.03 are seen (the candidate was developed on 20.07 and scored
  on 21.03), and HAI 22.04 and 23.05 are now seen by this detector too. Any future clean claim
  needs a corpus it has not met.
- The G1 Mahalanobis configuration and its published rows stay as they are, including the frozen
  rows. Nothing is appended to `eval_runs/log.jsonl`.
- Priors and `EVIDENCE_STRENGTH` are untouched.

## What would reverse this

The identity test failing, or a constant in `phos.atlas.consistency` differing from the frozen
file without its own record and a new result name.

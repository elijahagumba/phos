# ADR 0119 — Why a liar run fails, by a declared precedence

- **Status:** Accepted
- **Date:** 2026-10-12
- **PART:** learning engine S2
- **Depends on:** [ADR 0074](0074-the-usefulness-phase-is-defined-and-diagnosis-precedes-optimisation.md),
  [ADR 0094](0094-liar-measurement-seeds-and-pass-share.md),
  [ADR 0114](0114-the-liar-measurement-is-assembled-and-held.md),
  [ADR 0117](0117-two-loops-a-seen-ledger-and-the-held-out-bank.md),
  [ADR 0118](0118-decisions-and-outcomes-in-a-chained-ledger.md)

## Context

ADR 0114 explained in prose why the T1 assembly fails on development seed 4242: water treatment's
falsified level never crosses the consistency inlet's threshold. `docs/learning-engine.md` chose
this failure as the controlled example for the whole learning lifecycle. A lifecycle needs the
failure stated as a checkable verdict per run, recorded against the decision that produced it.
Sentiel already has that shape (`VisibilityVerdict` and `CEILING_PRECEDENCE`, ADR 0074); Atlas
did not.

## Decision

1. **`phos.breaking.liar_diagnosis.LIAR_PRECEDENCE`.** Eight clauses, read in order; the first that
   fits decides: `unscored`, `passed`, `inlet_subthreshold` (the falsified signal's peak loop score
   inside the window is at most `THRESHOLD`), `inlet_unavailable` (no calibrator), `inlet_not_promoted`
   (crossed, but no promoted fact in the window), `insufficient_observations` (tie or nothing
   contentful), `misinterpreted` (another template leads), `not_separable`. Subthreshold comes
   before calibrator availability because it is upstream: with no crossing on development corpora
   there are no positives to calibrate on.
2. **It re-runs, it does not re-score.** The pass verdict is `run_liar_corpus`'s, unchanged. The
   with-inlet stores are rebuilt from the same fitted parts, and the recomputed leader must equal
   the runner's or the diagnosis raises.
3. **Every scored run is recorded** in an ADR 0118 ledger: one `DecisionRecord` (the competing
   hypotheses and the evidence they cite, the fold's input hash, the fit hash, the commit) and one
   `confirmed` `synthetic_truth` outcome. `LearningRecord` and `arena_eligibility` join them: only
   a confirmed outcome on a `development` source is eligible; a `validation` case would demote its
   corpus.
4. **Held-out seeds are refused** by `refuse_held_out` before anything is generated.
5. **`scripts/diagnose_liar_runs.py`** runs seed 4242 for the three liar plants, refuses to write
   unless the runner reproduces ADR 0114's passes, never overwrites a ledger, and writes
   `eval_runs/learning/liar-dev-s4242.{ledger.jsonl,diagnosis.json,learning.jsonl}`.

## Result on development seed 4242 (synthetic, diagnosis only)

ADR 0114's passes reproduce: water none; power 0.0 and 0.2; batch 0.0 and 0.4.

| Plant | Subtlety | Verdict | Peak loop on the falsified signal |
| --- | --- | --- | ---: |
| water-treatment | 0.0, 0.2, 0.4, 0.8, 0.9 | inlet_subthreshold | 0.700, 0.367, 0.476, 0.199, 0.718 |
| water-treatment | 0.6 | inlet_unavailable | 1.344 |
| power-generation | 0.0, 0.2 | passed | 11.805, 7.397 |
| power-generation | 0.4, 0.6 | inlet_not_promoted | 4.433, 2.532 |
| power-generation | 0.8, 0.9 | inlet_subthreshold | 0.989, 0.984 |
| batch-reactor | 0.0, 0.4 | passed | 3.506, 0.869 |
| batch-reactor | 0.2 | insufficient_observations | 1.769 |
| batch-reactor | 0.6, 0.8, 0.9 | inlet_subthreshold | 0.891, 0.812, 0.810 |

Of 14 failures: **10 subthreshold**, 2 not promoted, 1 unavailable, 1 tie. Batch 0.4 passes with
its target below the threshold; the cited consistency fact is on another signal. Water 0.6 does
cross (1.344), but water has no calibrator, so nothing could be cited.

What it points at: most failures are the relation, not the reasoning. Power 0.4 and 0.6 cross by a
wide margin and are still not promoted, which points at the range score or the event's onset
rather than the loop model. Those are different repairs, and S4 is about the first.

## Consequences

`tests/breaking/test_liar_diagnosis.py` covers each clause, the held-out refusal, the report, one
plant end to end (`slow`) and the recorded files. Nothing is scored on a held-out seed. No
detector, constant, frozen row or log line changes. All figures are synthetic and from one
development seed (R4).

## What would reverse this

Diagnosing a held-out seed; editing a verdict without changing the precedence and its tests; or
quoting these figures as a T1 result.

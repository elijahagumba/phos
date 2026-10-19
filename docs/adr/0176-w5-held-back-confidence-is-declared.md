# ADR 0176 — The W5 held-back confidence score is declared

- **Status:** Accepted (the development numbers below are already measured; the held-back
  score is not in this record)
- **Date:** 2026-10-19
- **PART:** Round 3, Job 2
- **Depends on:** [ADR 0171](0171-explanation-confidence-is-calibrated-by-evidence-shape.md),
  [ADR 0175](0175-w5-seeds-and-scenarios-are-declared.md)

## Context

Development seeds 97401-97420 were scored out of fold. `k` stayed 3. Each run is
160 samples at 30 seconds, and the fault occupies the second half. A shorter run
left the detector silent, so the length is part of this configuration and it is
frozen here. Raising `k` was not kept: a louder liar still rests on
`cross_signal_mismatch`, the same shape as a right lead, so it cannot move the
Wilson bound.

On development, 46 contentful leads: 28 right, 18 wrong. Calibrated scores for
right and wrong leads overlap (about 0.59 to 0.63). Nothing is high-confidence.
Zero wrong leads are below 0.5. The bar is not met. The map is not refit to
chase it.

## Decision

1. The one held-back command is `uv run python scripts/round3_w5.py --split held-back`.
   Result name `round-3:w5-heldback`. It fits `ShapeCalibrator` on
   `eval_runs/build/round-3/w5-development-outcomes.json` and scores seeds
   97501-97520 once. It refuses to run if that result file already exists.

2. Frozen inputs, sha256:

   - `src/phos/atlas/conformal_confidence.py`
     `98f0080481a4e44bb482b220ac7ddaf66081b51e32bbdb7f09da7c518ea32dbf`
   - `src/phos/eval/w5_confidence.py`
     `e4eabb1a592899e140075f5c6748c9bf5e301833e17ef68284887712736312c0`
   - `scripts/round3_w5.py`
     `f545da67fe1dc66772858cc4078c2905523e21e46dffa45308a7a840b7f169df`
   - `eval_runs/build/round-3/w5-development-outcomes.json`
     `d3a61bc967f7e981a5c79acf534e7d191a0a994bc8228a56af73da6c86ab4c43`

3. The bar stays the one ADR 0175 named. The calibrated number is not surfaced.
   Nothing is appended to `eval_runs/log.jsonl`.

## Consequences

If the held-back wrong leads wear the same shape as the right ones, they will
not score low, and the bar will not be met. That is a result.

## What would reverse this

Editing the outcomes file or `k` after this record and still calling the run
the one look.

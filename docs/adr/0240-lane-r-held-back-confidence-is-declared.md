# ADR 0240 — The Lane R held-back score is declared

- **Status:** Accepted (a declaration; the held-back score is not in this record)
- **Date:** 2026-10-19
- **PART:** Build brief D, Lane R
- **Depends on:** [ADR 0172](0172-root-cause-ranking-points-an-alert-upstream.md),
  [ADR 0175](0175-w5-seeds-and-scenarios-are-declared.md),
  [ADR 0176](0176-w5-held-back-confidence-is-declared.md)

## Context

Development seeds 97401-97420 were re-run and then used to test declared hypotheses.
The frozen W5 scorer stays. Its development result was 28 of 46 contentful leads right.
The challenger kept after those hypotheses is H2b with H3's separation calibration.

On development, H2b's engine leads are right on 80 of 80 contentful rows.
`mimic_with_work_order` leads with `insufficient_evidence` on all 20 seeds.
H3 then reports a contentful lead as silence when no fact supports it and contradicts
the runner-up. That removes all 20 `fault_and_maintenance` leads, because their
runner-up is `engineering_maintenance` and the work order does not separate them.
The remaining development leads are 60 of 60 right. Leave-one-seed-out confidence
has an empty high band: no separation count has a Wilson 95% lower bound of at least
0.8. There is no wrong contentful lead left, so right and wrong confidences do not
form two sets to compare.

Seeds 97701-97720 have not been generated.

## Decision

1. The one held-back command, from this worktree, is
   `PYTHONPATH=src .venv/bin/python scripts/lane_r_heldback.py`.
   Result name `build-d:reasoning-heldback`. It scores seeds 97701-97720 once, the five
   ADR 0175 scenarios, `water-treatment`, 160 samples at 30 seconds, subtle-liar `k` = 3,
   quiet train 97001. It fits the separation map on
   `eval_runs/build/d/reasoning/h2b-development-rows.json` and refuses to start if
   `eval_runs/build/d/reasoning/held-back.json` already exists.

2. Both bars are required, and neither is reworded:

   - Contentful leads right, as a fraction, strictly greater than 33/54.
   - High-confidence leads right at least 80% of the time, with a reliability table.
     Zero high leads means this bar is not met.

   A lead is high when the Wilson 95% lower bound of its separation count, fit on the
   development rows, is at least 0.8. The calibrated number is not surfaced.

3. Frozen inputs, sha256:

   - `src/phos/eval/lane_r.py`
     `0388fe85d1223abe36c95a4dd38a767413d7f5a8748cc97466512e7eaf81e526`
   - `src/phos/eval/separation_confidence.py`
     `15321fa7ee8829cade45274c060131ac6ebc686d39eb6a6edd8ff1a9972d1cdc`
   - `src/phos/reasoning/separation.py`
     `bf4dd14b833e9863ecea7e76bcaba06be131bfa79d1532e2360ccbfabe8d98e3`
   - `src/phos/atlas/origin_evidence.py`
     `372b6b97c97e5066d278b095b5cfb9aa41e16dd7643ba425b952b96da162d570`
   - `src/phos/atlas/uncovered_setpoint.py`
     `93b68deb52fa85357dea8150fe0d0f9c377a4647e5a68a35a739d67946375d8b`
   - `src/phos/atlas/templates.py`
     `e035eafe8ce907a605c0283ea5baa0c643c6a73ff1a999a5799810767c183010`
   - `src/phos/ontology/enums.py`
     `6fa8ad59231f738dc40ad893946ecc00982cb6d05db10a1f34d60221d76d469a`
   - `scripts/lane_r_heldback.py`
     `09f2cb0d8fd73dc28566fb83a70615e9cca791dfb72ba459f8184ecc26e52ae9`
   - `eval_runs/build/d/reasoning/h2b-development-rows.json`
     `493e274524157c5aa8a882a37b66f37b1920e182511e62e989c706184e396fe8`

4. Nothing is appended to `eval_runs/log.jsonl`. Seeds 97501-97520 are not opened.
   `EVIDENCE_STRENGTH`, the priors, and the champion detector are not edited.

## Consequences

If the held-back high band is empty, the high-confidence bar is not met. That is a result.
The contentful fraction is judged on the leads that remain after a separation of zero is
reported as silence.

## What would reverse this

Editing a hashed file or the development rows after this record and still calling the run
the one look.

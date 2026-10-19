# ADR 0171 — Explanation confidence is calibrated by the shape of its evidence

- **Status:** Accepted (written before the capability was built or scored)
- **Date:** 2026-10-18
- **PART:** Build lane E, target 3 and the conformal-confidence capability
- **Depends on:** [ADR 0160](0160-a-command-the-actuator-ignored.md),
  [ADR 0162](0162-explanation-confidence-is-not-a-probability.md)

## Context

ADR 0162 charted the confidence on the leading explanation in lane D's command scenarios (a stuck
actuator, an actuator that followed its command, a quiet run). On development seeds 97001–97020
there were 36 contentful leads: 33 right, 3 wrong. The three wrong ones sat at raw confidence
0.355, the same number as 30 of the right ones. Nothing reached 0.8.

Reading the 36 cases shows why. Every right lead rests on one `command_to_response_mismatch` (the
actuator did not move after its setpoint changed), plus one or two `cross_signal_mismatch` facts.
Every wrong lead rests on two `cross_signal_mismatch` facts and no command fact: the champion's
ordinary false alerts on a run where nothing was falsified. The belief update counts facts, so one
command fact and one cross-signal fact score the same as two cross-signal facts.

## Decision

1. **A calibrated confidence beside the raw one.** `phos.atlas.conformal_confidence` maps a lead to
   its *evidence shape*: the sorted set of consistency facets among the facts that support it.
   Fitted on development runs, the confidence for a shape is `(right + 1) / (n + 2)` over the
   contentful leads with that shape. A shape never seen in fitting gets 0.5 with `n = 0`.
2. **High confidence is a bound, not a point.** A lead is high-confidence only when the Wilson
   95% lower bound of its shape's right share is at least 0.8. A shape seen a handful of times
   cannot be high, however often it was right.
3. **The development number is scored out of fold.** Each seed's leads are scored by a map fitted
   on the other nineteen seeds. The held-back seeds 97101–97120 are scored once, after a committed
   declaration, by the map fitted on all twenty development seeds. Nothing is refitted on them.
4. **Nothing else moves.** The raw confidence, the ranking `(-confidence, template_id)`, the
   priors, `EVIDENCE_STRENGTH` and the templates are untouched. The calibrated number is not
   surfaced to a user. Constitution §3.3 asks for held-out data first, and this record gives it
   held-back synthetic seeds only, not a plant.

## Bar

On development, out of fold: high-confidence leads right at least 80% of the time, and no right
and wrong lead sharing one calibrated score.

## Consequences

The confidence now separates a lead that rests on a command the actuator ignored from one that
rests on cross-signal noise. It is fitted on lane D's scenario mix, which this measurement chose,
so its numbers belong to that mix. A shape this mix never produced has no calibration and is
never high.

## What would reverse this

Refitting the map on held-back leads. Surfacing the calibrated number as a probability on a real
plant without held-out plant labels. Choosing the shape definition after the held-back look.

## Note at merge (19 October)

The held-back look had no wrong contentful lead, so it could not test that wrong explanations
score low. `docs/phos-2027.md` W5 asks that confidence mean what it says; that needs a held-back
set with errors in it. **W5 is not yet shown**, and the figure stays off the page.

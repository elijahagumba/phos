# A calibrated weight that is constant cannot rank, and a tie is not an alphabetical winner.

*Atlas carries numbers that look like severity, and on the one operator queue actually ranked by them, none pointed at the attacks. This paper is about why a calibrated weight that is constant cannot order a queue, and why a tie is not broken alphabetically.*

[The record](../README.md) · [Front page](../../README.md)

Atlas carries numbers that look like severity. On the one operator queue that was actually ranked, none of them pointed at the attacks. The repair for a different failure, two explanations saturating together, was to stop electing a winner. Both results are in committed code. Neither is a threshold that someone forgot to tune.

## Two objects that get called "confidence"

`evidence_from_deviation` promotes an out-of-band candidate and attaches a weight. That weight is a calibrated probability that the deviation is the kind of excursion the calibrator was fit on. It is allowed to exist as a number on `Evidence`.

A hypothesis confidence is a different object. It is built from template priors and from `EVIDENCE_STRENGTH`, then updated as if successive subsystem events were independent. They are not. One disturbance that persists across windows arrives as many near-identical events, so a confidence built from them counts one cause many times. The priors are an ordering derived from the pruning floor and from one piece of fully trusted evidence (`prior_at_rank` in `src/phos/atlas/templates.py`). They are not measured base rates of "which explanation was true". No corpus this repository uses carries that label. HAI labels attack and normal.

`UNCALIBRATED_HYPOTHESIS_CONFIDENCE_CAVEAT` in `src/phos/atlas/engine.py` is attached to reports by `annotate_with_caveats`. The sentence is an instruction: Atlas may rank and reason over hypotheses. It may not present their confidences as calibrated. Mixing the evidence weight into a sentence that says "80% this is an attack" is how a dashboard lies. The constitution's rule is the same one, §3.3.

The grouped weight makes the confusion easier. `group_evidence` sets `weight` to the max of the members. `GROUPED_WEIGHT_CAVEAT`: a maximum of calibrated probabilities is biased upward by how many signals the unit has. It is not itself calibrated.

## The sort that elected a string

When two contentful hypotheses sat at the ceiling, the old order was `(-confidence, template_id)`. `engineering_maintenance` sorts before `unauthorised_control_activity`. The maintenance story won because `strcmp` said so. ADR 0036 retired that as a unique lead.

`tied_lead_ids` in `src/phos/reasoning/belief.py` is the replacement. `CONFIDENCE_CEILING` is 1.0. `LEAD_TIE_EPSILON` is `1e-9`. `insufficient_evidence` is removed from the contest and kept in the set. If two or more contentful hypotheses sit within epsilon of the ceiling, or within epsilon of the top confidence away from the ceiling, the function returns their template ids in sorted order. A unique leader returns an empty tuple. The sort remains the listing order. It is not a winner.

`transfer_report` and `handoff_notices` construct both stories at `_TIED_CONFIDENCE = 0.5` so this function is non-empty, set `lead` to `None`, and do not put `0.5` on the report. The tests assert the tie equals the two story ids and that the notice has no confidence field. Alphabetical order of the two ids is how the tuple is stored. It is not a verdict that maintenance happened.

## The queue that was ranked, and what the ranks were

`src/phos/atlas/queue.py` is a stage after grouping. `grouping.py` does not import it. The promise that grouping re-scores nothing stays intact. A queue is built from finished subsystem events by a caller that already walked their traceability links. The module never sees a model, a store, or a corpus.

Three keys, declared, never chosen because they scored well:

- `magnitude` — largest raw joint distance among members. Continuous. Uncalibrated.
- `weight` — strongest member's calibrated probability.
- `breadth` — how many of the unit's signals departed. An integer. On a coarse map, a small one, so it ties by construction.

`rank_queue` orders by the key, then by timestamp, then by evidence id. `outcome_at_budget` cuts at a budget. Precision uses the budget as the denominator, not the number of alerts that happened to exist. A queue shorter than the budget does not get credit for the alerts it did not raise. Truth is overlap: an event whose span touches a labelled window counts, even if its stamp is before the window. Counting only the stamp would report a miss that did not happen. `windows_overlapped` is that rule. The vertical's own copy is left untouched so the frozen `hai[after]` row still reproduces.

When the last alert taken and the first alert dropped share a score, `BudgetOutcome.cut_is_arbitrary` is true and the validator requires `tie_span_at_cut >= 2`. `QueueCurve.honest_points` drops those points. The precision of an arbitrary cut is a property of the tiebreak. It is not a property of Atlas. ADR 0051's refusal, applied to a budget instead of to a false-positive load.

ADR 0068 measured the frozen row `atlas-vertical:atlas-mahalanobis+isotonic/subsystem-events` on HAI, seed 11, threshold search forbidden. 424 subsystem events, 7.89 normal hours, 6 overlaps with a labelled attack. Report: `eval_runs/atlas/hai-operator-queue.md`.

| Key | Distinct scores | Ranks of the 6 true alerts, of 424 | True positives in the first 48 |
| --- | ---: | --- | ---: |
| `magnitude` | 424 | 187, 204, 255, 320, 348, 359 | 0 |
| `weight` | 1 | every cut is the same tie | refused |
| `breadth` | 4 | 285, 286, 340, 341, 350, 351 | 0 |

A random draw of 48 expects 0.68 true positives. Magnitude finds 0. The loudest 96 alerts contain no attack. The true alerts sit between the 44th and 85th percentile. The severity signal points away from the incidents. No threshold on it repairs the order.

Weight is the constant `0.03375934410417169` on all 424 events. The isotonic calibrator tops out there. Only 140 of 4,249 calibration candidates fall in attack windows, across four knots spanning roughly `[0.000, 0.034]`. On this queue the weight carries zero ranking information. A 424-way tie is timestamp order. HAI's attacks fall early in the test slice, which would print precision 0.1250 at budget 48, window recall 1.00. `cut_is_arbitrary` struck that point, and every other tied cut. The figure is refused. It must not be quoted as `atlas-queue:weight`, and it must not be compared to CERT 6B's 0.104. One of those is an operating point of a different engine. The other is a sort.

Detector names minted here are prefixed `atlas-queue:` so they cannot be mistaken for the vertical's frozen names, 646.58 ungated and 53.26 grouped. `tests/atlas/test_queue_report_freeze.py` pins those rows. No threshold was searched. HAI's map could not be partitioned below process level, so the events being ranked are coarse. A finer map would change the queue without changing the detector.

## The bounds that do not pretend to be probabilities

The parts of Atlas that currently decide what a person sees are integers and closed intervals, not densities.

- `ALERTS_PER_SHIFT = 8` and `SHIFT_SECONDS = 28800`. A page longer than eight raises, or it truncates. It does not soften.
- `THRESHOLD = 1.0` opens an episode. `ONSET_LEVEL = 2.0` and `ONSET_FRACTION = 0.1` decide who may place it. A second alert inside `budget_alerts` is stored at `score * 1e-3` so it cannot outrank a first alert.
- `SETPOINT_BAND = (6.5, 7.5)` is the band a benign write already uses. A joint move, a 720-step walk, and a handoff are predicates on that interval and on `EVENT_WINDOW = 300` and `EVENT_SPAN = 600`. They return an object or they return nothing. They do not return a probability.
- `refuse_function_code` raises for every integer. It does not return a likelihood that the byte was a download.
- `lead: None` on `TransferReport` and `BriefSlot` is a type. The tie is the result.

`M_champion = 0` on the in-range command class (ADR 0309) is the same discipline one level up. Both champions caught 13 of 13 on a simulated plant. The predeclared new detector was not built, because a miss count of zero has no half left to cut. Building it would have been a model in search of a failure it did not have. The walk column that was allowed to exist missed the same 1 of 9 and was not kept (ADR 0315). A score that does not move the miss count is not promoted because the code ran.

## What would reverse this paper

Quoting 0.1250. Inverting `(-confidence, template_id)` so `unauthorised_control_activity` wins ties. Fitting a per-feature command calibrator on the graded battery. Retuning `_shrink`, `joint_k`, or `dwell_samples` so magnitude points the other way. Surfacing hypothesis confidence, or surfacing `0.5` and `0.03375934410417169` as if a person should act on them. Treating the HAI queue measurement as something a threshold will fix. It will not. The order is the result.

---

[The record](../README.md) · [Front page](../../README.md)

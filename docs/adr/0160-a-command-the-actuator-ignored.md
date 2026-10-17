# ADR 0160 — A command the actuator ignored is consistency evidence

- **Status:** Accepted
- **Date:** 2026-10-17
- **PART:** October 2026 build, lane D, item 4 (A3 / A4, gate G2)
- **Depends on:** [ADR 0014](0014-command-evidence-the-second-boundary-door-and-the-unrun-measurement.md),
  [ADR 0071](0071-command-behaviour-evidence-reaches-a-template.md),
  [ADR 0108](0108-consistency-evidence-routes-to-the-explanations.md),
  [ADR 0143](0143-the-plant-map-fails-the-gate.md),
  [ADR 0144](0144-the-october-build-is-declared.md)

## Context

A4 asks whether consistency evidence can separate a pair of explanations that neither the command
path nor the physics path separates alone. A3's frozen judging corpora are HAI and BATADAL. Those
are validation corpora, and gate look 1 is spent (ADR 0143). They are not opened, and A3 is not
re-scored.

The measurement that can be run is the synthetic one ADR 0144 declared: develop on seeds
97001-97020, and look once at 97101-97120 only after a committed declaration. This record is the
development measurement. The held-back look is not in it.

## Decision

### 1. What is emitted

`COMMAND_TO_RESPONSE_MISMATCH` is promoted by `phos.atlas.command_response` from a plant's declared
`CONTROL` couplings. A coupling qualifies when it names exactly one setpoint. The actuator is the
driven signal. The response is the only other driver when there is exactly one; otherwise it is
the actuator. Nothing is inferred from signals that happen to move together.

After a wire `WRITE`, decoded through the declared register map, the setpoint must have moved by
at least 5% of its span. Travel is the actuator's reported change from the write sample to the
sample 20 steps later. Travel under 5% of the actuator's span is the mismatch. The observation is
that travel. The expected range is from the minimum travel up to the actuator span, so staying put
is out of band. The fact goes through `phos.reasoning.boundary`.

The weight is a constant one half, from a Platt map with coefficient 0 and intercept 0. Separation
reads evidence lists, not this weight. It is not a user-facing probability.

On these plants the write lands before the controller reads the previous report, so the actuator
answers on the scans inside the horizon, not on the write sample itself.

### 2. Where it routes

`CommandResponsePattern` supports `sensor_or_device_fault` and contradicts
`engineering_maintenance`. `ConsistencyPattern` still matches any consistency feature, so the same
fact also contradicts `process_disturbance` (ADR 0108). It is silent on
`unauthorised_control_activity`.

Known-link matchers are not retuned. A known station's write still supports both maintenance and
an attack. Priors, `EVIDENCE_STRENGTH`, and the rank `(-confidence, template_id)` are unchanged.
Known-station lead 0/16 and unknown-master lead 1/4 stay apart.

A command-to-response fact is not a grouped subsystem event. `SubsystemBreadthPattern.overlaps`
says so in both directions, the same way it already does for `ConsistencyPattern`. Without that,
a broad departure would be treated as this fact, and the ask that settles maintenance against an
attack would stop being the unknown-master write.

### 3. What a seed has to do

Three bundles on the stuck run:

- Command: empty. The issuer is the plant's declared operator. An empty baseline is not an
  unknown master. Silence separates nothing.
- Physics: `CROSS_SIGNAL_MISMATCH` from `atlas-v1-consistency`, windows scaled by ADR 0112, fit
  on quiet seed 97001 only.
- Joint: the physics facts plus the command-to-response facts.

A pair of contentful templates is separated when one evidence id is in one hypothesis's supporting
list and the other's contradictory list. `insufficient_evidence` is not in a pair. A gained pair
is separated by the joint bundle and by neither of the other two.

A networked plant passes when the stuck run gains at least one pair and the follow run emits no
mismatch. Batch declares no control network, so it is recorded and not scored. A seed passes when
water and power both pass. The bar is a majority of the twenty seeds, which is at least eleven.

The scored loops are the ones the plants' own couplings and a development probe support. Water:
clearwell level setpoint 4.8, intake pump, 30-second samples. Power: feeder voltage setpoint 12.5,
tap changer, 10-second samples. The fuel-valve pair is declared and not scored: a dispatch step
does not move that valve by 5% of its span inside the horizon, and a slow governor is not a failed
actuator. Runs are 40 samples. The write is at sample 8. The actuator on the stuck run is held at
the pre-write reported value.

### 4. Development result

Seeds 97001-97020, scored by `uv run python scripts/lane_d_score.py --split development`. Result
name `lane-d-command-physics-development`. 20 of 20 seeds passed. Every networked stuck run gained
`(engineering_maintenance, sensor_or_device_fault)`. Follow-run mismatches were 0, so
`false_alerts_per_shift` is 0.0. That rate is the command-to-response fact, not the champion.

`atlas-v1-consistency` placed a budgeted alert inside the command window on every stuck networked
run and on every follow run. Both rates are 1.0. The window hit is the command. It does not
distinguish an actuator that followed from one that was held. `catches_within_budget` 1.0 is that
window count. It is not a detection claim, and it is not the A4 bar.

On some water seeds the cross-signal path separated no pair, so the joint bundle also gained
`(process_disturbance, sensor_or_device_fault)`. On the others the cross-signal path already
separated that pair, and it was not counted as gained. The maintenance pair was gained on every
networked run either way.

These are synthetic plants. The result is a diagnosis. It is not evidence about a real factory
(ADR 0143).

## Consequences

Held-back seeds 97101-97120 are not scored in this record. One later declaration will hash the
code and name one command that scores this check together with the lane's other held-back checks.
Editing the scored files after that declaration refuses the run.

A3 stays unmeasured on HAI and BATADAL.

# ADR 0162 — Explanation confidence is not shown as a probability

- **Status:** Accepted
- **Date:** 2026-10-17
- **PART:** October 2026 build, lane D, item 6 (W5)
- **Depends on:** [ADR 0036](0036-a-lead-tie-is-a-refusal-not-an-alphabetical-winner.md),
  [ADR 0144](0144-the-october-build-is-declared.md),
  [ADR 0160](0160-a-command-the-actuator-ignored.md)

## Context

W5 asks that a high-confidence explanation be right at least 80% of the time on held-out runs,
with a reliability chart. Constitution §3.3 already forbids showing an uncalibrated confidence
as a probability. The priors and `EVIDENCE_STRENGTH` are frozen. This record does not change
them, and it does not invert `(-confidence, template_id)`.

The labelled runs are the command-against-physics scenarios. A stuck actuator should lead with
`sensor_or_device_fault`. A follow run and a quiet run have nothing falsified, so a contentful
lead there is wrong. `insufficient_evidence` is silence. It is not in the chart.

## Decision

### 1. What is counted

The lead is the front of `competing`, which is the engine's own rank. A lead is contentful when
it is not the residual. High confidence, were a probability being shown, would mean at least 0.8.
Raw hypothesis confidence is not that probability.

A Platt map is fit on the development pairs only as a diagnostic. If the probabilities it returns
on those pairs span less than 0.05, the map is a base rate of a mix this measurement chose. It is
not shown. Held-back data does not get a second map, and it does not unlock surfacing.

### 2. Development result

`uv run python scripts/lane_d_score.py --split development --workstream calibration`. Result name
`lane-d-explanation-calibration-development`. Chart
`eval_runs/build/lane-d/reliability-development.svg`. Numbers
`eval_runs/build/lane-d/calibration-development.json`.

Forty runs on each of water and power (20 seeds, stuck, follow, and quiet):

| Lead | Count |
| --- | ---: |
| Stuck, sensor fault, right | 33 |
| Stuck, silence | 7 |
| Follow, silence | 38 |
| Follow, sensor fault, wrong | 2 |
| Quiet, silence | 39 |
| Quiet, sensor fault, wrong | 1 |

The chart has two occupied bins. Raw confidence 0.355 (33 leads) was right 0.909 of the time.
Raw confidence 0.488 (3 leads) was right 1.000 of the time. The three wrong leads sit in the
0.355 bin, with the same confidence as thirty right ones. Nothing reached 0.8. The expected
gap between the raw confidence and the observed frequency is 0.550.

Platt's coefficient is 0.033. Its outputs sit between 0.9167 and 0.9170. That is the 33/36 base
rate of the contentful leads in this mix. The map is rejected. `surfaced` is false.
`user_facing_probability` is null. The scorecard's `calibration` is null. The bar is not met.

These are synthetic plants. The chart is a diagnosis.

## Consequences

No explanation confidence from this lane is a user-facing probability. Narrative
`overall_confidence` stays unset, as the engine already leaves it.

Held-back seeds 97101-97120 are not scored here. One later declaration hashes the code and names
one command. That command may draw the same chart on the held-back seeds. It does not fit a new
map, and a raw confidence at or above 0.8 on that chart would still not be shown.

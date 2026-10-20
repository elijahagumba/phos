# Lane Q — decisions

Diagnosis only. No ranker is implemented in this record. HAI 20.07 is the only corpus opened. The metric is ADR 0212, unchanged: `rank_attacks` on the frozen champion's events, before the budget cut, top `ceil(10%)` of the shift that contains the attack's start. A true alert is an event whose onset timestamp lies inside an attack window, inclusive, using the same windows as the G1 scorer.

The champion's own scores reproduce **19 of 38**. The metric was not changed.

## Three orderings

| Ordering | A3 | Recall within 8 |
| --- | ---: | ---: |
| Champion score | 19/38 | 37/38 |
| Random, `numpy.random.default_rng(97651)` | 7/38 | 20/38 |
| Oracle: true alerts before benign alerts | 21/38 | 37/38 |

Recall within 8 is `recall_within_budget` at 8 alerts a shift, scored per file on that file's first timestamp and summed. On the champion scores the hand count matches the harness function.

The random order is one draw. The seed is 97651 and was not searched. Files are `test1.csv.gz` then `test2.csv.gz`. Inside a file, shifts run in index order. Inside a shift, the detector's emission order is shuffled by that one generator. Rank scores along the shuffled list are strictly decreasing, so a timestamp cannot undo the shuffle.

The oracle stable-partitions the champion order inside each shift: alerts inside any attack window of that file, then the rest, each half keeping the champion order.

## Why the oracle only reaches 21

251 alerts: 183 on `test1.csv.gz` (28 attacks) and 68 on `test2.csv.gz` (10 attacks). One attack, `test1.csv.gz#24`, has no alert in its shift, so every ordering fails it. In every other miss, the shift contains more attacks than top-10% slots. Putting every true alert first cannot create a slot. The per-shift ceiling is 21, and the oracle meets it. The champion is 2 below that ceiling.

Those 2 are both in `test1.csv.gz` shift 0 (queue 39, 4 slots):

| Attack | Champion rank | Oracle rank |
| --- | ---: | ---: |
| `test1.csv.gz#2` | 5 | 3, passes |
| `test1.csv.gz#3` | 6 | 4, passes |

No other attack changes its pass under the oracle. A ranker that reorders this alert list cannot score above 21/38 here. Recall within 8 is already 37/38 for the champion and the oracle. The missing attack is the one with no alert. Reordering cannot catch it, and a ranker that pushes a caught attack out of the 8 is rejected.

Shift 0, champion order, first eight places:

| Pos | Label | Onset | Members | Shape | Exact column-set in training normal | Strong innocent member | Lead |
| ---: | --- | --- | ---: | --- | --- | --- | --- |
| 1 | true | `P1_LIT01` | 17 | witness | no | none | `insufficient_evidence` |
| 2 | benign | `P1_B3005` | 9 | together | no | `process_disturbance` | `insufficient_evidence` |
| 3 | benign | `P1_PCV02Z` | 16 | together | no | `process_disturbance` | `insufficient_evidence` |
| 4 | true | `P1_LIT01` | 18 | witness | no | none | `insufficient_evidence` |
| 5 | true | `P1_LIT01` | 15 | witness | no | none | `insufficient_evidence` |
| 6 | true | `P1_FCV03D` | 10 | together | no | `process_disturbance` | `insufficient_evidence` |
| 7 | benign | `P1_TIT01` | 2 | local range | no | `sensor_or_device_fault` | `sensor_or_device_fault` |
| 8 | benign | `P1_LIT01` | 2 | witness | yes | `sensor_or_device_fault` | `sensor_or_device_fault` |

The two benigns that occupy pass slots (positions 2 and 3) are unfamiliar as a column set. The true alert at position 5, which the oracle promotes into a slot, is a witness disagreement with no strong innocent member. The true alert at position 6, which the oracle also promotes, has the same shape as the two benigns: together, unfamiliar, strong `process_disturbance`, residual lead. On these features that alert is not distinct from the benigns in front of it.

## Benign alerts that outrank a true alert

Thirty benign alerts sit ahead of at least one true alert in their shift. Counts below. An onset unit is the HAI tag prefix, the text before the first underscore.

| | Blocking benign | True alerts they outrank | All true alerts | All benign alerts |
| --- | ---: | ---: | ---: | ---: |
| Alerts | 30 | 6 | 41 | 210 |
| Exact column-set seen on a training-normal event | 20 | 1 | 1 | 99 |
| Onset tag seen inside some training-normal event | 30 | 4 | 35 | 209 |
| Strong innocent member | 29 | 4 | 25 | 186 |
| Witness disagreement | 8 | 5 | 19 | 93 |
| Together (3 or more members, not a witness) | 4 | 1 | 20 | 40 |
| Local range | 18 | 0 | 2 | 77 |

Onset unit of the 30: **P1 29, P4 1**. Onset signal: `P1_PCV02Z` 19, `P1_FCV02Z` 3, `P1_FT03Z` 2, and one each of `P1_B3005`, `P1_FT01`, `P1_B4002`, `P1_FT02`, `P1_FT02Z`, `P4_ST_FD`. The exact member set `{P1_PCV02Z}` accounts for 17 of the 30.

Training normal is an event on `train1.csv.gz` or `train2.csv.gz` whose onset row is not labelled attack. There are **38** distinct member-column sets. "Familiar" means the test alert's member-column set equals one of those. An onset tag appearing somewhere in those sets does not separate anything: 30 of 30 blocking benigns and 35 of 41 true alerts have that.

Shape, from the champion's own loop and range scores at the onset cell. Witness means the calibrated loop score is above the frozen threshold and at least the range score: the reading disagrees with the rest of the plant. Together means three or more member columns and not a witness. Local range is everything else.

The explanation probe weighs two facts at weight 1, which asks which explanations the shape supports. It is not a calibrated confidence, and no confidence is reported. The first fact is a subsystem event whose entities are the member signals. The second fact is added only for a witness: `cross_signal_mismatch` on the onset signal. Innocent templates are `sensor_or_device_fault`, `engineering_maintenance`, and `process_disturbance`. A strong innocent member is one that the evidence supports and does not contradict.

Of the 30, 25 have a strong `sensor_or_device_fault` and 4 have a strong `process_disturbance`. None have a strong `engineering_maintenance`: these rows carry no work order. Twenty-five lead with `sensor_or_device_fault`. The other five lead with `insufficient_evidence`. Four of those five are the together-shaped alerts: a broad subsystem event supports `process_disturbance` and `unauthorised_control_activity` with the same evidence, so the residual leads. The process explanation is still supported and not contradicted.

Cell counts for the 30 blocking benigns:

| Shape | Exact set familiar | Strong innocent | Count |
| --- | --- | --- | ---: |
| local range | yes | yes | 17 |
| together | no | yes | 4 |
| witness | no | yes | 4 |
| witness | yes | yes | 3 |
| witness | no | no | 1 |
| local range | no | yes | 1 |

The same cells on all 41 true alerts:

| Shape | Exact set familiar | Strong innocent | Count |
| --- | --- | --- | ---: |
| together | no | yes | 20 |
| witness | no | no | 16 |
| witness | no | yes | 2 |
| local range | no | yes | 2 |
| witness | yes | yes | 1 |

Exact column-set familiarity separates the bulk of the blocking benigns (20 of 30) from true alerts (1 of 41). It does not touch the two benigns in the only two recoverable slots. Witness-versus-together separates the true alert at position 5 from those two benigns, and does not separate the true alert at position 6 from them.

Passes by shift, champion order:

| File | Shift | Attacks | Pass | Queue | Top slots | Ranks |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| test1.csv.gz | 0 | 4 | 2 | 39 | 4 | 4, 1, 5, 6 |
| test1.csv.gz | 2 | 3 | 3 | 26 | 3 | 2, 3, 1 |
| test1.csv.gz | 3 | 5 | 2 | 13 | 2 | 7, 6, 1, 2, 3 |
| test1.csv.gz | 5 | 2 | 1 | 5 | 1 | 2, 1 |
| test1.csv.gz | 6 | 5 | 3 | 24 | 3 | 2, 5, 4, 3, 1 |
| test1.csv.gz | 8 | 2 | 1 | 5 | 1 | 2, 1 |
| test1.csv.gz | 9 | 7 | 2 | 13 | 2 | 6, 3, 2, none, 4, 1, 7 |
| test2.csv.gz | 0 | 2 | 1 | 9 | 1 | 2, 1 |
| test2.csv.gz | 2 | 5 | 1 | 9 | 1 | 5, 4, 3, 1, 2 |
| test2.csv.gz | 3 | 2 | 2 | 30 | 3 | 1, 2 |
| test2.csv.gz | 5 | 1 | 1 | 3 | 1 | 1 |

## Declared before they are run

ADR 0231. Not scored yet. A ranker reorders the champion's alerts and does not add or remove
one. Familiar means the exact member-column set appeared on a training-normal event. Witness
means the onset loop score is above the frozen threshold and at least the range score. A
strong innocent member is `sensor_or_device_fault`, `engineering_maintenance` or
`process_disturbance` supported by the structural probe and not contradicted. The probe is
the subsystem event, a `cross_signal_mismatch` fact when the alert is a witness, and a
work-order fact when a sanctioning order covers the timestamp. Weight 1 is the probe. No
confidence is reported.

| Variant | Order, then the champion tiebreak |
| --- | --- |
| `familiarity` | unfamiliar before familiar |
| `innocent` | no strong innocent member before one |
| `cross-path` | witness before the rest |
| `familiarity-cross` | unfamiliar, then witness |
| `cross-innocent` | witness, then no strong innocent member |
| `all-three` | unfamiliar, then witness, then no strong innocent member |

Prediction, from the counts above. `familiarity` does not move the two recoverable HAI
attacks. `cross-path` and `innocent` can move the witness true alert in shift 0 and cannot
separate the together-shaped true alert from the together-shaped benigns. A variant that
lowers recall within 8 on HAI 20.07 or on seeds 97651–97670 is rejected. The frozen variant
is the greatest A3 on 97651–97670 among the ones not rejected, then the greater HAI A3, then
the earlier row.

Seeds 97651–97670 are development. Seeds 97601–97620 are held back and are not generated in
this record. The generator is ADR 0231: water, power, then batch, cycling; quiet train is
seed 97001 for 24 hours; each scored seed is one 8-hour shift with the plant's own benign
events, a work order on hours 1–5, and a held reading on hours 6–8.

## Development scores

Scored after the declaration above. Every seed had at least one benign process event and
at least one alert inside the hold. The champion's HAI order remained 19 of 38, recall
within 8 remained 37 of 38.

| Variant | HAI A3 | HAI recall within 8 | Seeds 97651–97670 A3 | Seed recall within 8 |
| --- | ---: | ---: | ---: | ---: |
| Champion order | 19/38 | 37/38 | 19/20 | 20/20 |
| `familiarity` | 19/38 | 37/38 | 19/20 | 20/20 |
| `innocent` | 17/38 | 34/38 | 15/20 | 20/20 |
| `cross-path` | 13/38 | 28/38 | 10/20 | 20/20 |
| `familiarity-cross` | 16/38 | 32/38 | 10/20 | 20/20 |
| `cross-innocent` | 13/38 | 28/38 | 10/20 | 20/20 |
| `all-three` | 16/38 | 32/38 | 10/20 | 20/20 |

`innocent`, `cross-path`, `familiarity-cross`, `cross-innocent` and `all-three` lowered
recall within 8 on HAI and are rejected. They do pass seed 97660, the one development seed
the champion misses (water, 13 alerts, 6 inside the hold). Saving that seed cost other
seeds and cost HAI. `familiarity` changed no seed's pass. The margin is zero, smaller than
that one-seed miss. ADR 0232 freezes `familiarity` anyway, because it is the only variant
the rejection rule leaves standing.

## Held-back, once

`atlas-queue-v2:familiarity` on seeds 97601–97620. Champion 20 of 20, recall within 8
20 of 20. Familiarity 20 of 20, recall within 8 20 of 20. A3 is not strictly higher.
Recall is not lower. The bar is not met (ADR 0233). Not run again.

The gate is ADR 0234, command `PYTHONPATH=src:. .venv/bin/python scripts/measure_d_queue_gate.py`,
result name `atlas-queue-v2:familiarity-gate`. It was not run.

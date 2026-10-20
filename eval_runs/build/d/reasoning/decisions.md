# Lane R decisions

## Confusion table (development re-run)

2026-10-19 — Development seeds 97401–97420 were re-run on `water-treatment`, 160 samples at 30 seconds, subtle-liar `k` = 3, quiet train seed 97001. The scorer is the frozen W5 path: loop-carried `cross_signal_mismatch` facts, the filtration work order on `fault_and_maintenance` and `mimic_with_work_order`, and `atlas_library()` unchanged. The re-run matches `eval_runs/build/round-3/w5-development-outcomes.json` on lead, contentful flag, right/wrong, and raw confidence for all 100 rows. That file was not edited. The capture is `development-evidence.json` in this directory.

100 rows = 20 seeds × 5 kinds. Contentful 46: 28 right, 18 wrong. All 46 contentful leads are `sensor_or_device_fault`, and every one of them rests only on `cross_signal_mismatch`. `tied_lead_ids` is empty on all 100 rows, and no pair of contentful explanations shares an evidence list, so none of these leads is an ADR 0036 tie. The 54 silences are `insufficient_evidence` leading because its prior (0.3) sits above a hypothesis that has no physics fact or only one. One `cross_signal_mismatch` moves `sensor_or_device_fault` to about 0.241. Two or more move it to about 0.355 or higher, and then it leads. The numbers in this file are the engine's uncalibrated confidence, written down so the attachment can be checked. They are not a reported probability.

| Kind | Contentful | Right | Wrong | Silent |
| --- | --- | --- | --- | --- |
| `plain_sensor_fault` | 9 | 9 | 0 | 11 |
| `fault_and_maintenance` | 9 | 9 | 0 | 11 |
| `subtle_liar` | 10 | 10 | 0 | 10 |
| `two_sensors` | 9 | 0 | 9 | 11 |
| `mimic_with_work_order` | 9 | 0 | 9 | 11 |

The 18 wrong leads are two pairs.

1. **Two held sensors, scored as a sensor fault that names neither of them.** Truth, by the rule in `w5_confidence._is_right`, is `sensor_or_device_fault` whose supporting facts name both `chlorine_residual_mgpl` and `distribution_pressure_bar`. The lead is that same template. The supporting facts name other signals. 0 of 9 name either required signal, so 0 of 9 name both. On every one of these 9 rows both signals are members of a consistency event. `distribution_pressure_bar` is the alert column of an event on all 9, and `chlorine_residual_mgpl` is the alert column on 97402 and 97405. Promotion keeps the loop-carried cell, and those two alert cells are not among the promoted facts. The facts that do arrive support `sensor_or_device_fault` and contradict `process_disturbance`. They are not subsystem events, so they do not bear on `unauthorised_control_activity`. The true explanation and the lead are the same hypothesis: it has those supporting facts and no contradictory ones. What fails is the both-names rule.

2. **A setpoint move inside a filtration work order, scored as a sensor fault.** Truth is `unauthorised_control_activity`. The lead is `sensor_or_device_fault`, resting on `cross_signal_mismatch` facts. 0 of 9 of those facts name `clearwell_level_setpoint_m`. The setpoint is a member of a consistency event on all 9, and the alert column on 7 (97401, 97404, 97410, 97416, 97418, 97419, 97420). It is never promoted. `unauthorised_control_activity` has no supporting fact. The filtration work order (`work_order` on `wo_w5_filtration` and `filter_headloss_m`) contradicts it, and the same fact supports `engineering_maintenance`. Maintenance's uncalibrated confidence stays about 0.155, under the sensor-fault lead. No row promotes a graph finding. The features in the whole re-run are `cross_signal_mismatch` (164) and `work_order` (40).

### The 18 wrong leads

Feature, entities, and role of every fact the lead rested on, and of every fact the true explanation rested on. For `two_sensors` those are the same hypothesis.

**97401 `two_sensors`.** Truth and lead: `sensor_or_device_fault`. Supporting: `cross_signal_mismatch` on `raw_turbidity_ntu`; `cross_signal_mismatch` on `distribution_flow_m3ph`; `cross_signal_mismatch` on `coagulant_dose_mgpl`. Contradictory: none.

**97401 `mimic_with_work_order`.** Truth: `unauthorised_control_activity`. Lead: `sensor_or_device_fault`. Lead supporting: `cross_signal_mismatch` on `clearwell_level_m`; `cross_signal_mismatch` on `intake_pump_speed_pct`. Truth supporting: none. Truth contradictory: `work_order` on `wo_w5_filtration`, `filter_headloss_m`.

**97402 `two_sensors`.** Truth and lead: `sensor_or_device_fault`. Supporting: `cross_signal_mismatch` on `raw_turbidity_ntu` (twice); `cross_signal_mismatch` on `clearwell_level_setpoint_m`. Contradictory: none.

**97402 `mimic_with_work_order`.** Truth: `unauthorised_control_activity`. Lead: `sensor_or_device_fault`. Lead supporting: `cross_signal_mismatch` on `clearwell_level_m`; `cross_signal_mismatch` on `raw_inflow_m3ph`. Truth supporting: none. Truth contradictory: `work_order` on `wo_w5_filtration`, `filter_headloss_m`.

**97403 `two_sensors`.** Truth and lead: `sensor_or_device_fault`. Supporting: `cross_signal_mismatch` on `intake_pump_speed_pct`; `cross_signal_mismatch` on `raw_turbidity_ntu`. Contradictory: none.

**97404 `two_sensors`.** Truth and lead: `sensor_or_device_fault`. Supporting: `cross_signal_mismatch` on `clearwell_level_m`; `cross_signal_mismatch` on `chlorine_dose_mgpl`; `cross_signal_mismatch` on `filtered_turbidity_ntu`. Contradictory: none.

**97404 `mimic_with_work_order`.** Truth: `unauthorised_control_activity`. Lead: `sensor_or_device_fault`. Lead supporting: `cross_signal_mismatch` on `clearwell_level_m`; `cross_signal_mismatch` on `chlorine_dose_mgpl`; `cross_signal_mismatch` on `intake_pump_speed_pct`; `cross_signal_mismatch` on `chlorine_residual_mgpl`. Truth supporting: none. Truth contradictory: `work_order` on `wo_w5_filtration`, `filter_headloss_m`.

**97405 `two_sensors`.** Truth and lead: `sensor_or_device_fault`. Supporting: `cross_signal_mismatch` on `raw_turbidity_ntu` (twice). Contradictory: none.

**97410 `two_sensors`.** Truth and lead: `sensor_or_device_fault`. Supporting: `cross_signal_mismatch` on `chlorine_dose_mgpl`; `cross_signal_mismatch` on `raw_turbidity_ntu`; `cross_signal_mismatch` on `filtered_turbidity_ntu`. Contradictory: none.

**97410 `mimic_with_work_order`.** Truth: `unauthorised_control_activity`. Lead: `sensor_or_device_fault`. Lead supporting: `cross_signal_mismatch` on `chlorine_dose_mgpl` (twice); `cross_signal_mismatch` on `distribution_pressure_bar`. Truth supporting: none. Truth contradictory: `work_order` on `wo_w5_filtration`, `filter_headloss_m`.

**97411 `two_sensors`.** Truth and lead: `sensor_or_device_fault`. Supporting: `cross_signal_mismatch` on `filter_headloss_m`; `cross_signal_mismatch` on `filtered_turbidity_ntu`. Contradictory: none.

**97411 `mimic_with_work_order`.** Truth: `unauthorised_control_activity`. Lead: `sensor_or_device_fault`. Lead supporting: `cross_signal_mismatch` on `filter_headloss_m`; `cross_signal_mismatch` on `chlorine_residual_mgpl` (three times). Truth supporting: none. Truth contradictory: `work_order` on `wo_w5_filtration`, `filter_headloss_m`.

**97416 `two_sensors`.** Truth and lead: `sensor_or_device_fault`. Supporting: `cross_signal_mismatch` on `chlorine_dose_mgpl`; `cross_signal_mismatch` on `clearwell_level_m`; `cross_signal_mismatch` on `filtered_turbidity_ntu` (twice). Contradictory: none.

**97416 `mimic_with_work_order`.** Truth: `unauthorised_control_activity`. Lead: `sensor_or_device_fault`. Lead supporting: `cross_signal_mismatch` on `chlorine_dose_mgpl` (three times). Truth supporting: none. Truth contradictory: `work_order` on `wo_w5_filtration`, `filter_headloss_m`.

**97418 `mimic_with_work_order`.** Truth: `unauthorised_control_activity`. Lead: `sensor_or_device_fault`. Lead supporting: `cross_signal_mismatch` on `chlorine_dose_mgpl`; `cross_signal_mismatch` on `raw_inflow_m3ph`. Truth supporting: none. Truth contradictory: `work_order` on `wo_w5_filtration`, `filter_headloss_m`.

**97419 `mimic_with_work_order`.** Truth: `unauthorised_control_activity`. Lead: `sensor_or_device_fault`. Lead supporting: `cross_signal_mismatch` on `chlorine_residual_mgpl`; `cross_signal_mismatch` on `distribution_pressure_bar`; `cross_signal_mismatch` on `chlorine_residual_mgpl`. Truth supporting: none. Truth contradictory: `work_order` on `wo_w5_filtration`, `filter_headloss_m`.

**97420 `two_sensors`.** Truth and lead: `sensor_or_device_fault`. Supporting: `cross_signal_mismatch` on `coagulant_dose_mgpl`; `cross_signal_mismatch` on `filtered_turbidity_ntu`; `cross_signal_mismatch` on `raw_turbidity_ntu`; `cross_signal_mismatch` on `distribution_flow_m3ph`. Contradictory: none.

**97420 `mimic_with_work_order`.** Truth: `unauthorised_control_activity`. Lead: `sensor_or_device_fault`. Lead supporting: `cross_signal_mismatch` on `coagulant_dose_mgpl`; `cross_signal_mismatch` on `clearwell_level_m` (twice); `cross_signal_mismatch` on `chlorine_residual_mgpl`. Truth supporting: none. Truth contradictory: `work_order` on `wo_w5_filtration`, `filter_headloss_m`.

## Example pairs tested against this table

The brief's four examples were checked against the rows above.

**A lying sensor versus a real process change** does not appear as a wrong lead. `process_disturbance` leads on 0 of 100 rows. On every contentful row the `cross_signal_mismatch` facts support `sensor_or_device_fault` and contradict `process_disturbance`. `plain_sensor_fault` is right on 9 of 9 contentful rows, `fault_and_maintenance` on 9 of 9, and `subtle_liar` on 10 of 10. No separator will be built for this pair.

**An instrument failure versus a plausible lie** does not appear as a wrong lead. A chlorine hold at 0 and a chlorine hold at the quiet-train mean plus 3 noise standard deviations are both right when the lead is `sensor_or_device_fault`, which is what the frozen right-rule says. No contentful row of either kind is wrong. No separator will be built for this pair.

**Maintenance versus attack** is not the pair that leads. `engineering_maintenance` leads on 0 of 100 rows. On every wrong mimic row it is supported by the filtration work order and stays under `sensor_or_device_fault`. The wrong lead is the sensor-fault explanation. The attack explanation is the one with no supporting fact and with the work order against it. A fixer that only prefers attack over maintenance would be aimed at a lead this table does not produce.

**Two sensors failing together versus one liar** is the first wrong pair, and it is one template. `subtle_liar` is right whenever it is contentful, on `sensor_or_device_fault`. `two_sensors` leads that same template and is wrong because the supporting facts do not name both held sensors. The two errors are visible as members of the consistency events. The promoted facts name other signals, so the sensor-fault explanation cannot show two origins.

No hypothesis has been run. No new evidence is in the tree yet.

## Hypotheses declared before they are run

Each one is run on development seeds 97401–97420 only, with the same plant, length, sample period, `k`, and quiet train as the re-run above. New facts use `FittedPlattCalibrator(coefficient=0.0, intercept=0.0)`, weight 0.5. `EVIDENCE_STRENGTH` stays `log(3)`. Priors stay. The champion detector stays. Known-link matchers stay. A non-empty `tied_lead_ids` is a refusal: the lead is `insufficient_evidence`.

**H1.** One `cross_signal_mismatch` fact per independent root-cause origin. The plant map is fitted on quiet train 97001 with `roles_with_every_control_coupling` and `LOOP_EXPLAINER_SETTINGS` (ADR 0170, ADR 0172). For each loop-carried consistency event, `rank_root_causes` ranks the alert column and its ancestors. Every candidate whose tier is `ORIGIN` contributes one fact, one per signal. The fact is `FacetKind.CONSISTENCY` / `cross_signal_mismatch`, so it supports `sensor_or_device_fault` and contradicts `process_disturbance`, the same way today's facts do. Facts already promoted stay.

Predicts: on `two_sensors`, the sensor-fault explanation's supporting entities include both `chlorine_residual_mgpl` and `distribution_pressure_bar`, so a contentful lead of that template is right under the frozen rule. Predicts: `plain_sensor_fault`, `fault_and_maintenance`, and `subtle_liar` stay `sensor_or_device_fault` whenever they are contentful. Predicts: `mimic_with_work_order` stays `sensor_or_device_fault` when contentful, because an origin fact of this kind still supports a sensor fault.

**H2.** A declared setpoint (`SignalKind.SETPOINT`) whose report leaves the quiet-train envelope, while a work order is in the evidence and that work order's entities do not include the setpoint, is one fact. The fact is not a graph finding. `unexpected_command_function` and the silent-link matcher are not edited. The fact supports `unauthorised_control_activity`, contradicts `engineering_maintenance`, and contradicts `sensor_or_device_fault`.

Predicts: `mimic_with_work_order` takes a unique lead of `unauthorised_control_activity`, or `tied_lead_ids` is non-empty and the scorer refuses. Predicts: the three sensor kinds stay `sensor_or_device_fault` whenever they are contentful.

**H3.** The confidence used for the bar is how well the evidence separates the lead from the runner-up: the number of facts that support one of those two and contradict the other. Evidence shape is not the key. When that number is zero, the lead's confidence is the low bin and `insufficient_evidence` may lead, raised the way a tie is raised. The map is leave-one-seed-out on development: a separation count's confidence is `(right + 1) / (n + 2)` fitted on the other seeds. High means the Wilson 95% lower bound of that count is at least 0.8 (`HIGH_BOUND`). Zero high leads means the high-confidence bar is not met. H3 is scored on the evidence H1 and H2 produce, and also reported for the frozen evidence so the before and after are both in the record.

Predicts: a development reliability table, out of fold, and a statement of whether right and wrong contentful leads occupy different calibrated confidences.

## H1 result

2026-10-19 — H1 was run on seeds 97401-97420. The plant map is the lane E map (`LOOP_EXPLAINER_SETTINGS`). Origins were read only at loop-carried alert cells, which is what the declaration said. Result file `h1-development.json`.

| Kind | Contentful | Right | Wrong | Silent |
| --- | --- | --- | --- | --- |
| `plain_sensor_fault` | 9 | 9 | 0 | 11 |
| `fault_and_maintenance` | 9 | 9 | 0 | 11 |
| `subtle_liar` | 10 | 10 | 0 | 10 |
| `two_sensors` | 9 | 1 | 8 | 11 |
| `mimic_with_work_order` | 11 | 0 | 11 | 9 |

48 contentful, 29 right, 19 wrong. Fraction 29/48. The frozen re-run was 28/46. The three sensor kinds stayed `sensor_or_device_fault` whenever contentful. Mimic's contentful lead stayed `sensor_or_device_fault`, and two rows that had been silent became wrong contentful leads.

The both-names prediction failed. Chlorine residual's map is driven by distribution pressure, intake speed, inflow, booster speed, filtered turbidity, and raw turbidity. On every two_sensors seed, at rows in the second half, chlorine's own score is out of band and at least one driver is too, so its tier is `INHERITED`, never `ORIGIN`. Pressure is an origin at its own column on 7 of 20 seeds and on none of the other 13. Across the whole second half, both signals are origins together on 0 of 20 seeds. The one right two_sensors row is seed 97404, where the promoted alert's ancestor list happened to include both names. H1 stays as a failed hypothesis.

**H1b, declared before it is run.** One `cross_signal_mismatch` fact per consistency-event member whose own plant-map score is above 1, inherited members included. A signal already named by a promoted fact is not given a second fact. Weight stays 0.5. Predicts: two_sensors contentful leads name both `chlorine_residual_mgpl` and `distribution_pressure_bar` and are therefore right. Predicts: the three sensor kinds stay `sensor_or_device_fault` when contentful. Predicts: mimic's contentful lead stays `sensor_or_device_fault`.

## H1b result

2026-10-19 — H1b was run after the declaration above. Result file `h1b-development.json`.

| Kind | Contentful | Right | Wrong | Silent |
| --- | --- | --- | --- | --- |
| `plain_sensor_fault` | 20 | 20 | 0 | 0 |
| `fault_and_maintenance` | 20 | 20 | 0 | 0 |
| `subtle_liar` | 20 | 20 | 0 | 0 |
| `two_sensors` | 20 | 20 | 0 | 0 |
| `mimic_with_work_order` | 20 | 0 | 20 | 0 |

100 contentful, 80 right, 20 wrong. Fraction 80/100, which is above 33/54. Every two_sensors lead is right, so the supporting facts name both held sensors. The three sensor kinds are `sensor_or_device_fault` on every seed, including the rows that were silent before. Mimic is `sensor_or_device_fault` on every seed, which is what H1b predicted, and all 20 are wrong. The mimic pair is untouched. H2 is the hypothesis declared for that pair.

## H2 result

2026-10-19 — H2 was run on the frozen W5 evidence, with one uncovered-setpoint fact. The envelope is the quiet-train minimum and maximum of each setpoint. Weight 0.5. Result file `h2-development.json`.

| Kind | Contentful | Right | Wrong | Silent |
| --- | --- | --- | --- | --- |
| `plain_sensor_fault` | 9 | 9 | 0 | 11 |
| `fault_and_maintenance` | 6 | 6 | 0 | 14 |
| `subtle_liar` | 10 | 10 | 0 | 10 |
| `two_sensors` | 9 | 0 | 9 | 11 |
| `mimic_with_work_order` | 6 | 0 | 6 | 14 |

40 contentful, 25 right, 15 wrong. Fraction 25/40. No mimic row leads with `unauthorised_control_activity`. The six contentful mimic rows still lead with `sensor_or_device_fault`. The other fourteen are `insufficient_evidence` because the residual prior 0.3 sits above the updated hypotheses, not because `tied_lead_ids` is non-empty. One fact of weight 0.5 cannot lift unauthorised control (prior about 0.02, and the work order still contradicts it at weight about 1) over that residual, and it cannot outvote two or more cross-signal facts on the sensor-fault explanation. The prediction failed.

The quiet-train min/max is also crossed by the plant's own setpoint steps. On `fault_and_maintenance`, 3 rows that were right contentful leads became silence. The train's level setpoint runs from 3.0 to 3.75. Benign steps reach about 2.74 and 3.77. The mimic reports 4.8.

**H2b, declared before it is run.** A setpoint counts as uncovered only when it falls outside the quiet-train range by at least the width of that range. On the level setpoint that is outside [2.25, 4.50]. The development benign steps measured above sit inside that band. 4.8 does not. When such a fact is present, the cross-signal facts are not ingested: they are the plant following a setpoint the work order does not cover, so they are not offered as a sensor fault. The uncovered-setpoint fact is still weight 0.5, and the work order is still ingested. Member facts from H1b are ingested only when no such setpoint fact is present. Predicts: `plain_sensor_fault`, `fault_and_maintenance`, `subtle_liar`, and `two_sensors` match H1b (contentful leads right, template `sensor_or_device_fault`). Predicts: `mimic_with_work_order` leads with `insufficient_evidence`, because one half-weight fact cannot raise unauthorised control over the residual. That silence is not counted as a wrong contentful lead.

## H2b result

2026-10-19 — H2b was run after that declaration. Engine leads, before H3's refusal:

| Kind | Contentful | Right | Wrong | Silent |
| --- | --- | --- | --- | --- |
| `plain_sensor_fault` | 20 | 20 | 0 | 0 |
| `fault_and_maintenance` | 20 | 20 | 0 | 0 |
| `subtle_liar` | 20 | 20 | 0 | 0 |
| `two_sensors` | 20 | 20 | 0 | 0 |
| `mimic_with_work_order` | 0 | 0 | 0 | 20 |

80 contentful, 80 right. Fraction 80/80. The prediction held.

## H3 result, on H2b's evidence

Leave-one-seed-out on `h2b-development-rows.json`. A contentful lead with separation 0 is reported as `insufficient_evidence`. All 20 of those leads are `fault_and_maintenance`: the runner-up is `engineering_maintenance`, the work order supports maintenance, and the cross-signal facts do not contradict it, so nothing separates the two. After that refusal the contentful leads are 60, all right. Fraction 60/60, above 33/54.

The separation counts that remain are spread across 5, 6, 7, 8, 9, 10, 11, 12, 13 and 14. None of those counts, fit on the other seeds, has a Wilson 95% lower bound of at least 0.8. High leads: 0. The high-confidence bar is not met on development. There is no wrong contentful lead, so right and wrong confidences are not two sets. The reliability table is in `h2b-separation.json`: 4 leads sit in [0.4, 0.6) and 56 sit in [0.8, 1), and the high flag is the Wilson bound, not the bin.

ADR 0240 declares the one held-back look on seeds 97701-97720 before those plants are built.

## Held-back result

2026-10-19 — One look, seeds 97701-97720, result `build-d:reasoning-heldback`, file `held-back.json`. Contentful leads after the separation refusal: 60, all right. Fraction 60/60, strictly greater than 33/54. That bar is met. High leads: 0. The high-confidence bar is not met. Both bars together are not met. The reliability table has 5 leads in [0.6, 0.8) and 55 in [0.8, 1), all right. Those bin counts are not the high band. High is the Wilson lower bound, and it was reached for none of the separation counts. There is no wrong contentful lead, so right and wrong confidences are not two sets. The look was not repeated.

# Lane R — explanations that separate

Branch `build/d-reasoning`. Declaration ADR 0240. Result name `build-d:reasoning-heldback`.

The calibrated number in this report is the separation confidence used for the bar. It is not shown on a public page.

## Diagnosis

Development seeds 97401-97420 were re-run on `water-treatment`, 160 samples at 30 seconds, subtle-liar `k` = 3, quiet train 97001. The re-run matches the frozen file `eval_runs/build/round-3/w5-development-outcomes.json` on all 100 rows. That file was not edited.

100 rows, 46 contentful, 28 right, 18 wrong. Every contentful lead is `sensor_or_device_fault` and rests only on `cross_signal_mismatch`. `tied_lead_ids` is empty on every row.

The 18 wrong leads are two pairs.

- `two_sensors`, 9 contentful, all wrong. The lead template is the right one. The supporting facts name neither `chlorine_residual_mgpl` nor `distribution_pressure_bar`. Both signals are members of the consistency events.
- `mimic_with_work_order`, 9 contentful, all wrong. The lead is `sensor_or_device_fault`. The truth is `unauthorised_control_activity`, which has no supporting fact and is contradicted by the filtration work order. The setpoint is inside the consistency events and is not a promoted fact.

`plain_sensor_fault`, `fault_and_maintenance`, and `subtle_liar` are right whenever they are contentful. `process_disturbance` and `engineering_maintenance` lead on 0 rows. A lying sensor versus a real process change, and an instrument hold versus a plausible lie, are not wrong-lead pairs. No separator was built for them.

## Variants on development

| Variant | Contentful | Right | Fraction | What happened |
| --- | ---: | ---: | ---: | --- |
| Frozen re-run | 46 | 28 | 28/46 | The confusion table. |
| H1, one fact per ADR 0172 origin | 48 | 29 | 29/48 | Failed. Chlorine is inherited from distribution pressure on every seed, so both names appear together on 0 of 20. |
| H1b, one fact per out-of-band event member | 100 | 80 | 80/100 | `two_sensors` right on 20 of 20. The three sensor kinds stay `sensor_or_device_fault`. Mimic is a sensor fault on 20 of 20. |
| H2, setpoint outside the quiet-train min/max, weight 0.5 | 40 | 25 | 25/40 | Failed. No mimic lead is `unauthorised_control_activity`. One half-weight fact cannot lift that prior over the residual or over two cross-signal facts. Benign setpoint steps also leave the min/max. |
| H2b, setpoint outside the train range by at least the range's own width; cross-signal facts dropped when that fact is present; otherwise H1b | 80 | 80 | 80/80 | Mimic is `insufficient_evidence` on 20 of 20. The other four kinds are right. |
| H3 on H2b, leave-one-seed-out | 60 | 60 | 60/60 | Separation 0, which is every `fault_and_maintenance` lead, is reported as silence. High leads: 0. No wrong contentful lead remains, so the confidences do not form a right set and a wrong set. |

H1 and H2 stay in `decisions.md` as failures. The challenger that was frozen is H2b with H3.

## Held-back, one look

Seeds 97701-97720. Command `PYTHONPATH=src .venv/bin/python scripts/lane_r_heldback.py`. Result `eval_runs/build/d/reasoning/held-back.json`.

- Contentful fraction 60/60. Strictly greater than 33/54. **Met.**
- High-confidence leads: 0. Right-at-least-80% is not met, because zero high leads means the bar is not met. **Not met.**
- Both bars together: **not met.**

Reliability table, calibrated separation confidence against fraction right:

| Bin | Leads | Right | Fraction right |
| --- | ---: | ---: | ---: |
| [0.0, 0.2) | 0 | 0 |  |
| [0.2, 0.4) | 0 | 0 |  |
| [0.4, 0.6) | 0 | 0 |  |
| [0.6, 0.8) | 5 | 5 | 1 |
| [0.8, 1) | 55 | 55 | 1 |

The [0.8, 1) bin is the Laplace value `(right + 1) / (n + 2)`. The high flag is the Wilson 95% lower bound of the separation count, and that bound stayed under 0.8 for every count. On development, out of fold, the same pattern held: 60 of 60 right, 0 high, and no wrong lead whose confidence could be compared with a right one.

## What the reasoning does now

A consistency event contributes one `cross_signal_mismatch` fact for each member whose plant-map score is above 1, so two held sensors are both named on the sensor-fault explanation. A setpoint that leaves the quiet-train range by at least that range's width, while a work order does not name it, is one fact of weight 0.5. It supports `unauthorised_control_activity` and counts against `engineering_maintenance` and `sensor_or_device_fault`. It is not a graph finding, and the known-link matchers are unchanged. When that fact is present, the cross-signal facts are not ingested. When no fact supports the lead and contradicts the runner-up, the reported lead is `insufficient_evidence`. The confidence used for the bar is the out-of-fold rate of that separation count, not the shape of the evidence.

## Rule note

`uv run` was used once at the start and retargeted the shared virtualenv at this worktree. It was pointed back at `~/dev/phos` with `uv pip install -e` before any score. No `uv sync`. No write under `data/`. `eval_runs/log.jsonl` was not appended. Seeds 97501-97520 and the validation corpora were not opened. `EVIDENCE_STRENGTH` and the template priors were not edited. The held-back command was not run a second time.

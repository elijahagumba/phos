# ADR 0083 — normal-score calibrator measurement

New experiment names only. Frozen 646.58 / 53.26 / 18.72 untouched.
Seed 11, threshold 3.0, calib_fraction=0.1.

| Dataset | Detector | Alerts | Recall | FPs | FP/normal-hr | Precision | ECE |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `hai[designed-normal-score][5A context]` | `model:atlas-mahalanobis` | 99 | 1.000 | 87 | 11.03 | 0.1212 | 0.5890 |
| `hai[designed-normal-score][before]` | `atlas-vertical:atlas-mahalanobis+normal-score-cdf/per-signal-evidence` | 99 | 1.000 | 87 | 11.03 | 0.1212 | 0.8597 |
| `hai[designed-normal-score][after]` | `atlas-vertical:atlas-mahalanobis+normal-score-cdf/subsystem-events` | 31 | 1.000 | 28 | 3.55 | 0.0968 | 0.8832 |
| `batch-distillation[designed][adr0083-baseline]` | `model:atlas-mahalanobis` | 5,637 | 0.548 | 1,476 | 20.19 | 0.7041 | 0.1130 |
| `batch-distillation[designed-normal-score]` | `model:atlas-mahalanobis+normal-score-cdf` | 5,637 | 0.548 | 1,476 | 20.19 | 0.7041 | 0.2491 |

## Verdict (ADR 0083)

- HAI gate: frozen ungated 646.58 / grouped 53.26 reproduced.
- HAI new path (`hai[designed-normal-score][after]`): 31 alerts, recall 1.000, FP/hr 3.55. Compare to frozen grouped 53.26 (short isotonic fit) and diagnostic 97 alerts at 60 h.
- Batch-distillation baseline (full designed train): recall 0.548, FP/hr 20.19, precision 0.7041 (sandbox noboom-atlas-v1 was 0.532/18.61/0.709).
- Batch-distillation normal-score (full designed fit + normal-CDF from held-out suffix): recall 0.548, FP/hr 20.19, precision 0.7041. Alert set must match baseline when the behavioural fit is identical; divergence means the calibrator leaked into scoring (a defect).
- Weights caveat: Normal-score CDF weights are not attack probabilities: the map is the empirical CDF of held-out attack-free magnitudes (ADR 0083). A weight of 0.9 means the score sits at or above about 90% of ordinary scores the model saw on normal data — not that an attack is 90% likely. Do not quote ECE against attack labels as evidence that these weights are calibrated probabilities under Constitution §3.3.

**Incomplete dual win:** HAI improved (longer attack-free fit unlocked by the normal-score calibrator) at unchanged recall. Batch-distillation detection metrics are **unchanged** versus designed — expected, because designed already fits the full attack-free train; the calibrator only adds evidence weights. ADR 0083 asked for improvement on both corpora; detection parity on distillation is not that improvement. Recipe-step coverage mismatch remains the residual FP driver.

Read with:
- Coarse-map inflation: HAI's declared topology could not be partitioned below process level for P1 and P2, so unrelated departures anywhere on one process collapse into a single subsystem event. A large reduction here is evidence that grouping is correctly IMPLEMENTED, not that it is correctly RESOLVED. A finer map would lower the headline number and raise its meaning.
- Uncalibrated hypothesis confidence: the confidences on these hypotheses are NOT calibrated probabilities and must not be surfaced to a user under Constitution §3.3. Three reasons, and the third is measured rather than asserted. (1) The template priors are reasoned placeholders, not measured base rates. (2) EVIDENCE_STRENGTH is a placeholder too, and measuring either needs data labelling WHICH EXPLANATION IS TRUE, which no corpus PHOS uses carries — HAI labels attack and normal. (3) The belief update treats each subsystem event as independent, and on a plant they are plainly not: one disturbance persisting across consecutive windows arrives as many near-identical events, so a confidence built from them counts one cause many times. Atlas may rank and reason over these hypotheses; it may not present their confidences as calibrated. Evidence weights, separately, are calibrated.
- Co-occurring-fault masking: a coarse group can hide a second, unrelated event inside one subsystem event. Two independent faults on one process are indistinguishable from one, and an attack co-occurring with a fault is reported as a single thing to investigate. That is a recall risk carried by the grouping, not a win.
- Grouped weight is a maximum: a subsystem event carries the strongest member's calibrated weight, and a maximum over a set of calibrated probabilities is not itself a calibrated probability — it is biased upward by how many signals the unit carries. The calibration error reported for subsystem events may therefore come out better or worse than the per-signal one for reasons that have nothing to do with the calibrator, and is not a reading of it.
- Saturated false-positive load: when a declared SaturationPolicy fires, the row is REFUSED as a detection claim even if recall looks excellent. Metrics stay on the report; they must not be quoted as detection. Public distillation 18.72 and Data4Cyber Track A keep their log names and stay MEASURED unless a caller applies a policy. Do not raise dwell_samples to chase a quieter public ZIP.

# phos-benchmark-v1

Frozen **before** Clock B model work (ADR 0062). Cited cells are copies of already-
published public rows. REFUSED cells are measurements: the files cannot support the
claim. Do not retune Atlas templates. Do not overwrite ungated HAI Mahalanobis
**646.58**, distillation **18.72**, or CERT 6B **0.104**. Do not pool command issuers.
Must not pool known-station **0/16** with unknown-master **1/4**. Cycle ≥70% remains
unearned.

- Protocol: `phos-benchmark-v1`
- Seed (HAI public split): `11`
- Threshold search on this split: **forbidden**

| Family | Dataset | Detector | Status | Window recall | FP/normal hour | FP/normal day | Precision | Precision@budget | Unique lead | n | Caveat / refusal |
|---|---|---|---|---|---|---|---|---|---|---|---|
| atlas-process-cyber | hai | model:gaussian | CITED | 1 | 8389.81 | 201355.44 | 0.0043 | — | — | — | encyclopedia/11 HAI three-way seed 11; atlas-report |
| atlas-process-cyber | hai | model:atlas-pca | CITED | 1 | 17529.93 | 420718.32 | 0.0048 | — | — | — | encyclopedia/11: PCA residual lost; kept, not tuned away (ADR 0009) |
| atlas-process-cyber | hai | atlas-mahalanobis | CITED | 1 | 646.58 | 15517.92 | 0.0047 | — | — | — | encyclopedia/11 HAI Mahalanobis 646.58 FP/hour at recall 1.00 |
| atlas-process-cyber | hai | atlas-mahalanobis-grouped | CITED | 1 | 53.26 | 1278.24 | 0.0094 | — | — | — | COUNTING_CHANGE_NOT_A_CONTROL_ROOM ADR 0011: grouping shrinks the queue; 53.26/hour is not 2-3/day |
| atlas-process-perturbation | batch-distillation | atlas-mahalanobis | CITED | 0.6 | 18.72 | 449.28 | — | — | — | — | PERTURBATION_RECALL_IS_NOT_ATTACK_RECALL ADR 0025/0031 ungated Mahalanobis 18.72; 8.6x vs Gaussian is not 10x |
| atlas-process-perturbation | batch-distillation | 2-3-per-day | REFUSED | — | — | — | — | — | — | — | REFUSED (ADR 0031): 2-3 actionable alerts/day on public distillation is uneearned. Phase-conditional is louder than ungated Mahalanobis. dwell_samples stays 1. Do not invent a phase column. |
| atlas-command-public | none | command-lead | REFUSED | — | — | — | — | — | — | — | REFUSED (ADR 0040): discover_labelled_command_corpora is empty. Data4Cyber labels are 1 Hz process phases, not command-action windows. This cell is not a lead rate. |
| atlas-command-d2 | synth-water-power-graded | known-station | DIAGNOSTIC | — | — | — | — | — | 0/16 | 16 | ATTRIBUTION_RANK_IS_NOT_A_RATE_CAVEAT ADR 0038: unique lead 0/16; moved 6/16; must not pool |
| atlas-command-d2 | synth-water-unknown-master | unknown-master | DIAGNOSTIC | — | — | — | — | — | 1/4 | 4 | ATTRIBUTION_RANK_IS_NOT_A_RATE_CAVEAT ADR 0038: unique lead 1/4; D2 diagnostic; 1.1650 FP/hour saturated |
| sentiel | cert-r3.1 | aggregate:gaussian:peer-set-6B | CITED | 0.5 | — | — | — | 0.104 | — | 48 | ADR 0032: 6B at 48 alerts, precision 0.104 (5 TP / 43 FP), recall 0.5 |
| sentiel | cert-r3.1 | :precision | CITED | 0.5 | — | — | — | 0.083 | — | 48 | MEASURED_LOSS_VS_6B ADR 0032: :precision 0.083 is a measured loss vs 6B; do not headline |
| sentiel | cert-r3.1 | peer-advantage | REFUSED | — | — | — | — | — | — | — | REFUSED (ADR 0023): CERT r3.1 has zero peer-relative positives. Peer-group advantage stays retired. r4.2 is not a peer corpus. |
| transfer | hai→batadal | shared-schema | REFUSED | — | — | — | — | — | — | — | REFUSED: HAI→BATADAL transfer is not a measurement until a declared shared plant-state schema exists. Different signal names are not a leave-one-plant protocol. |

D2 known-station unique lead **0/16**. D2 unknown-master unique lead **1/4** (diagnostic, not a field rate). Public command row: REFUSED.

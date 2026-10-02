# PHOS Benchmark v2 — cite table for engine-week log names

**Not a rewrite of Benchmark v1.** ADR 0062 freeze stands. HAI Mahalanobis **646.58**,
distillation **18.72**, and CERT 6B **0.104** remain the public rulers. This table only
**cites new names** measured after that freeze.

- Protocol: `phos-benchmark-v2-cite`
- Seed (HAI public split): `11`
- Threshold search: **forbidden**
- Intelligence / API / UI: still absent. P1 still a human conversation.

| Family | Dataset | Detector | Status | Window recall | FP/normal hour | Precision | n | Caveat |
|---|---|---|---|---|---|---|---|---|
| atlas-process-cyber | hai | model:atlas-var1 | CITED | 1.00 | 14071.07 | 0.0049 | — | ADR 0064. Louder than 646.58. Refused as the HAI detector. New log name only. |
| atlas-process-cyber | hai | atlas-mahalanobis-correlation | REFUSED | — | — | — | — | ADR 0066. Singular at shrinkage 0.05 (cond. 3.85e+25). Cannot invert. Do not retune `_shrink`. No log row. |
| transfer | batadal→hai | model:atlas-mahalanobis-physical-roles | CITED | 1.00 | 1078.99 | — | — | ADR 0063. Louder than in-plant HAI. HAI→BATADAL cell stays REFUSED on v1. |
| sentiel | cert-r3.1 | autopsy:6b-top-budget | DIAGNOSTIC | — | — | — | 48 | ADR 0065. 5 TP / 43 FP. No exclusive stem. Do not invent a subset. Does not replace 0.104. |
| atlas-process-cyber | swat | in-plant | REFUSED | — | — | — | — | iTrust form-gated. Files not on disk. Engineering does not scrape the form. |
| sentiel | cert-r4.2 | compromised-vs-insider | REFUSED | — | — | — | — | ADR 0067. Events archive not on disk. Probe labels only. Not a 6B rewrite. |
| atlas-process-cyber | icssim-bottle-filling | fault-vs-attack | REFUSED | — | — | — | — | ADR 0067. Licence read once; identity unestablished. Not acquired. |

v1 cells are not copied here so this file cannot be mistaken for a replacement freeze.
Read `eval_runs/benchmark/phos-benchmark-v1.md` for the locked public rows.

# Clock B research scoreboard

Behind PHOS Benchmark v1 (ADR 0062). Cited public rows are not retuned.
Fixture results are not public rows. P1 remains a blocked human conversation.

## Public ruler (cited, not overwritten)

- HAI Gaussian: **8389.81** FP/normal hour
- HAI Mahalanobis: **646.58** FP/normal hour (still quieter than Gaussian on the public row)
- Distillation ungated Mahalanobis: **18.72** FP/hour = **449.28** FP/day. 2-3/day stays refused.
- CERT 6B at 48: precision **0.104** (5/48 = 0.104 on the frozen TP/FP counts)
- Known-station unique lead **0/16**; unknown-master unique lead **1/4**; unpooled.

## Fixture ablation (not a public row)

- Toy Mahalanobis true positives exceed Gaussian: **True**.
- That does not overwrite HAI 646.58. If Mahalanobis still wins on HAI, it wins.

## Declared-phase transitions

- Distillation inferred phase: REFUSED (ADR 0018/0031): batch-distillation has no declared phase register. Phase-conditional is louder than ungated Mahalanobis on that ZIP. Do not invent a phase column from correlations. dwell_samples stays 1.
- Declared-phase fixture flags illegal arrival at index (4,).

## Sequences versus counts

- Rare ordered path more surprising than the common trained path: **True**.
- Replaces CERT 6B: **False**.

## Reasoning fixtures (library, not CERT)

- n=4 top-1=3 top-2=0 abstention-when-correct=1 miss=0
- is_cert_row: **False**
- Maintenance consequences authored: 2
- Unauthorised consequences authored: 2

## D2 reconstruction completeness (not a lead rate)

- Known-station command records: 16
- Unknown-master command records: 4
- Mean completeness: 0.571 (path/state/aftermath usually empty)
- Every record has lead_rate None. 0/16 and 1/4 stay the ranking freeze.

## Identity layers (not a CERT row)

- Self/role/org/time scored separately on a fixture. Peer slot: **None**. Pooled unusual: **None**. Peer advantage stays retired.
- This is not a CERT 6B replacement and not a public log name.

## Hunt tickets

- TEP: read-once per dump (faults, not attacks). Dumps do not confirm each other. Not acquired.
- Electra ICS: host timed out; dataset licence unverified; name collisions. Not acquired.
- HVAC/BACnet: campus traces have no SPDX and truncated payloads; Kaggle unread. Not acquired.
- Further Modbus pcaps: unlabelled or attack-type, not command-action windows. Not acquired. None fills ADR 0040.

## Still forbidden

- Intelligence, API, UI, TAP in src/phos.
- Threshold search on seed 11.
- Pooling command issuers. Claiming >=70%, 10x, or 2-3/day on public ZIPs.

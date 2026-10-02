# SYNTHETIC-DERIVED DIAGNOSTIC — NOT A MEASUREMENT, NOT A DETECTION CLAIM

Not a measurement. Not a detection claim. Not a row in `eval_runs/log.jsonl`.
Not evidence about a real plant. Frozen command-lead 0/16 and 1/4 are untouched.

- seed: `11`
- commit: `8190d196315ec10ed0f9810a92376dadc5639d78`
- reproduce: `uv run python scripts/diagnose_u3_environment.py --seed 11`
- plant: `water-treatment`
- fit history: `120 h` (instrument calibration-drift period (range upper bound))

## 1. Does command attribution function when command evidence genuinely exists?

- control (ordinary operation): unauthorised writes = `0` (can come out zero: `True`)
- treatment (unauthorised scada write): unauthorised writes = `1`
- command-path findings on unauthorised capture: `1`
- command-path findings on ordinary capture: `0`
- issuer `scada` classified as: `known_station` (known-station vs unknown-master, unpooled)
- answer: `yes, the path sees the writes`
- not a lead rate. not 0/16. not 1/4.

## 2. Does maintenance evidence move the competing hypotheses, and in which direction?

- control (export withheld): promoted facts = `0` (can come out zero: `True`)
- treatment (SAP PM export): orders raised = `4`, sanctioning = `2`, promoted facts = `2`
- competing set with the export: `['engineering_maintenance', 'insufficient_evidence', 'unauthorised_control_activity'] (3 hypotheses)`
- unique leader with the export: `engineering_maintenance`
- unique leader with the export withheld: `insufficient_evidence`
- answer: `yes, the inlet promotes facts`
- direction: work-order facts support engineering_maintenance and contradict unauthorised_control_activity (ADR 0069). This script does not retune templates.
- wiring result, not a queue improvement.

## 3. What happens when an attacker uses legitimate credentials inside a sanctioned window?

- construction: the adversary is given an independently planned calendar and chooses a window. The calendar is not moved to cover the attack. Natural overlap is a seed search, reported as method, not a calendar that was walked onto the attack.
- seeds searched: `[7, 11, 13, 17, 19, 23]`
- overlap by seed: `{7: True, 11: False, 13: True, 17: False, 19: True, 23: True}`
- control (seed 11 has no overlap): `True`
- first overlapping seed: `7`
- attacker writes issued on that seed: `1`
- falling inside a sanctioned clearwell window: `1`
- Atlas then has, when the write is covered: an unauthorised write in the ground truth, a graph finding, AND a covering work order. ADR 0014 still holds: the bytes are the same.
- answer: `adversary wrote inside a sanctioned window; the case is inspectable`

## 4. Does Atlas become MORE uncertain when evidence is removed?

Paired runs, same seed, unauthorised-commands scenario. Capture present vs capture withheld (the incomplete-observations lever: no live pcap, so no command facts are ingested; the residual remains). Structural terms only. No confidence numbers.

- with live capture: unique leader `insufficient_evidence`, tied leaders `none`, competing `['insufficient_evidence', 'engineering_maintenance', 'unauthorised_control_activity', 'process_disturbance'] (4 hypotheses)`, graph findings `1`, command evidence `3`
- capture withheld: unique leader `insufficient_evidence`, tied leaders `none`, competing `['insufficient_evidence'] (1 hypotheses)`, command evidence `0`
- ordinary-operation control: unique leader `insufficient_evidence`, graph findings `0`, command evidence `1` (graph findings can come out zero: a yes that cannot fail is meaningless)
- more uncertain when evidence is removed: `True`
- more confident with less evidence (a break): `False`

A unique contentful command story that appears only after the capture is removed would be a break. Changing engine behaviour to chase a prettier answer is outside U3.

## What this is not

- A detection claim.
- A row in `eval_runs/log.jsonl`.
- A reason to quote 0/16 or 1/4.
- Evidence about a real plant (ADR 0029, ADR 0073, register R4).


# Sentiel lane — S2 and S3

Roadmap pass sentences, from `docs/v1-roadmap.md` §2.2:

- S2: "Implemented, tested and scored on CERT r3.1 and at least one larger release with more insiders."
- S3: "More distinct labelled insiders surfaced than the frozen 6B scorer, beside a label-free chance null."

| Criterion | Verdict | Number | Record |
| --- | --- | --- | --- |
| S2 | not met (ADR 0230) | Every one of the six features has sum 0 and max 0. r3.1: 2 labelled insiders, 340171 windows. r4.2: 70 labelled insiders, 330452 windows. The register is empty (`2c284a6e2f41061c514104f6eb6e885b55664d0a7eb18b9b0278a1c3f74f168b`). No weight was put on the 34. | `eval_runs/build/v1/sentiel/s2-r31.json`, `eval_runs/build/v1/sentiel/s2-r42.json` |
| S3 | not met | Challenger `exclusive-host-return:cert-r4.2@48-per-day` surfaced **1** distinct labelled insider. Frozen 6B `6b:cert-r4.2@48-per-day` surfaced **59**. Chance null expected **35.2855319099821**. Realism check: **0** of **930** innocent users have a web host no other user requested (share **0**). 1 is not more than 59. | `eval_runs/build/v1/sentiel/s3-r42.json` |

S3 was scored once, at 48 tickets a day, after ADR 0202. The frozen r3.1 row (precision 0.104 at 48 alerts) was not written. The run was not repeated.

The realism reading fixed in ADR 0196 applies to the share of 0: near zero innocent users with such a host means the signal most likely reads how the CERT generator plants scenario activity. That reading does not change the S3 verdict. The challenger did not surface more distinct labelled insiders than frozen 6B.

**At merge (ADR 0230):** S2 is counted not met. The register was empty, so every feature is zero by
construction and no host, destination or machine was named. The zeros stay recorded.

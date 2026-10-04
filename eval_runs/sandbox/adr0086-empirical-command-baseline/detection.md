# Empirical command baseline — unauthorised-write detection (ADR 0086)

Figure name: `empirical-command-baseline:unauthorised-concerns-write`.
SYNTHETIC-DERIVED. Not a row on `eval_runs/log.jsonl`. Not command-lead 0/16 or 1/4.
Run: `phos demo --scenario unauthorised`, 120-hour fit, SCADA writes the HMI setpoint.
A hit is a shown brief that concerns that write. Silence is a miss.
Seeds, fixed before the runs: 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30.

| Seed | Gaussian hit | Empirical hit | Gaussian silent | Empirical silent |
| --- | --- | --- | --- | --- |
| 11 | True | True | False | False |
| 12 | True | True | False | False |
| 13 | True | True | False | False |
| 14 | True | True | False | False |
| 15 | True | True | False | False |
| 16 | True | True | False | False |
| 17 | True | True | False | False |
| 18 | True | True | False | False |
| 19 | True | True | False | False |
| 20 | True | True | False | False |
| 21 | True | True | False | False |
| 22 | False | True | False | False |
| 23 | True | True | False | False |
| 24 | True | True | False | False |
| 25 | True | True | False | False |
| 26 | True | True | False | False |
| 27 | True | True | False | False |
| 28 | True | True | False | False |
| 29 | True | True | False | False |
| 30 | True | True | False | False |

Gaussian briefs that concern the write: 19 of 20.
Empirical briefs that concern the write: 20 of 20.

The empirical model sees the write more often: 20 against 19.

## What the shown incident said

- Seed 11, Gaussian: The SCADA server: 17% of its commands in one minute were writes. In 120 hours it had sent none.
- Seed 11, empirical: The SCADA server: 17% of its commands in one minute were writes. In 120 hours it had sent none.
- Seed 12, Gaussian: The SCADA server: 12% of its commands in one minute were writes. In 120 hours it had sent none.
- Seed 12, empirical: The SCADA server: 12% of its commands in one minute were writes. In 120 hours it had sent none.
- Seed 13, Gaussian: The SCADA server: 12% of its commands in one minute were writes. In 120 hours it had sent none.
- Seed 13, empirical: The SCADA server: 12% of its commands in one minute were writes. In 120 hours it had sent none.
- Seed 14, Gaussian: The SCADA server: 12% of its commands in one minute were writes. In 120 hours it had sent none.
- Seed 14, empirical: The SCADA server: 12% of its commands in one minute were writes. In 120 hours it had sent none.
- Seed 15, Gaussian: The SCADA server: 20% of its commands in one minute were writes. In 120 hours it had sent none.
- Seed 15, empirical: The SCADA server: 20% of its commands in one minute were writes. In 120 hours it had sent none.
- Seed 16, Gaussian: The SCADA server: 8 commands in one minute. Normally 4 to 8.
- Seed 16, empirical: The SCADA server: 12% of its commands in one minute were writes. In 120 hours it had sent none.
- Seed 17, Gaussian: The SCADA server: 20% of its commands in one minute were writes. In 120 hours it had sent none.
- Seed 17, empirical: The SCADA server: 20% of its commands in one minute were writes. In 120 hours it had sent none.
- Seed 18, Gaussian: The SCADA server: 14% of its commands in one minute were writes. In 120 hours it had sent none.
- Seed 18, empirical: The SCADA server: command interval cv was 2.23347. Normally 0.998647 to 1.99914.
- Seed 19, Gaussian: The SCADA server: 14% of its commands in one minute were writes. In 120 hours it had sent none.
- Seed 19, empirical: The SCADA server: 14% of its commands in one minute were writes. In 120 hours it had sent none.
- Seed 20, Gaussian: The SCADA server: 8 commands in one minute. Normally 4 to 8.
- Seed 20, empirical: The SCADA server: command interval cv was 2.23408. Normally 0.999474 to 1.99919.
- Seed 21, Gaussian: The SCADA server: 12% of its commands in one minute were writes. In 120 hours it had sent none.
- Seed 21, empirical: The SCADA server: 12% of its commands in one minute were writes. In 120 hours it had sent none.
- Seed 22, Gaussian: The SCADA server: 8 commands in one minute. Normally 4 to 8.
- Seed 22, empirical: The SCADA server: command interval cv was 2.2283. Normally 1.22236 to 1.99921.
- Seed 23, Gaussian: The SCADA server: 14% of its commands in one minute were writes. In 120 hours it had sent none.
- Seed 23, empirical: The SCADA server: command interval cv was 2.23416. Normally 0.999027 to 1.99922.
- Seed 24, Gaussian: The SCADA server: 17% of its commands in one minute were writes. In 120 hours it had sent none.
- Seed 24, empirical: The SCADA server: 17% of its commands in one minute were writes. In 120 hours it had sent none.
- Seed 25, Gaussian: The SCADA server: 14% of its commands in one minute were writes. In 120 hours it had sent none.
- Seed 25, empirical: The SCADA server: command interval cv was 2.2321. Normally 0.998901 to 1.99923.
- Seed 26, Gaussian: The SCADA server: command interval cv was 1.22333. Normally 1.24387 to 2.52801.
- Seed 26, empirical: The SCADA server: command interval cv was 2.23163. Normally 1.22275 to 1.9993.
- Seed 27, Gaussian: The SCADA server: 8 commands in one minute. Normally 4 to 8.
- Seed 27, empirical: The SCADA server: one command every 15.0 s on average. Normally every 6.0 s to 15.0 s.
- Seed 28, Gaussian: The SCADA server: 12% of its commands in one minute were writes. In 120 hours it had sent none.
- Seed 28, empirical: The SCADA server: 12% of its commands in one minute were writes. In 120 hours it had sent none.
- Seed 29, Gaussian: The SCADA server: 14% of its commands in one minute were writes. In 120 hours it had sent none.
- Seed 29, empirical: The SCADA server: command interval cv was 2.23335. Normally 1.22293 to 1.99924.
- Seed 30, Gaussian: The SCADA server: 8 commands in one minute. Normally 4 to 8.
- Seed 30, empirical: The SCADA server: command interval cv was 2.23114. Normally 1.22244 to 1.99921.

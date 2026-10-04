# Empirical command baseline — ordinary-run false alarms (ADR 0086)

Figure name: `empirical-command-baseline:operator-false-alarms`.
SYNTHETIC-DERIVED. Not a row on `eval_runs/log.jsonl`. Not command-lead 0/16 or 1/4.
Ordinary run: `phos demo --scenario operator`, 120-hour fit, authorised write.
A false alarm is a narrative that does not concern that write. Silence is 0.
Seeds, fixed before the runs: 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30.

| Seed | Gaussian | Empirical | Gaussian concerns write | Empirical concerns write |
| --- | --- | --- | --- | --- |
| 11 | 1 | 1 | False | False |
| 12 | 2 | 0 | False | False |
| 13 | 0 | 0 | False | False |
| 14 | 0 | 0 | False | False |
| 15 | 0 | 0 | False | False |
| 16 | 0 | 0 | False | False |
| 17 | 0 | 0 | False | False |
| 18 | 0 | 1 | False | False |
| 19 | 1 | 0 | False | False |
| 20 | 1 | 0 | False | False |
| 21 | 0 | 0 | False | False |
| 22 | 1 | 0 | False | False |
| 23 | 1 | 0 | False | False |
| 24 | 0 | 0 | False | False |
| 25 | 0 | 0 | False | False |
| 26 | 2 | 1 | False | False |
| 27 | 1 | 1 | False | False |
| 28 | 0 | 0 | False | False |
| 29 | 2 | 0 | False | False |
| 30 | 3 | 0 | False | False |

## What the shown incident said

- Seed 11, Gaussian: The SCADA server: one command every 15.0 s on average. Normally every 1.6 s to 13.2 s.
- Seed 11, empirical: The SCADA server: command interval cv was 0.998692. Normally 0.999031 to 1.99922.
- Seed 12, Gaussian: The SCADA server: one command every 15.0 s on average. Normally every 1.5 s to 14.5 s.
- Seed 12, empirical: silence
- Seed 13, Gaussian: silence
- Seed 13, empirical: silence
- Seed 14, Gaussian: silence
- Seed 14, empirical: silence
- Seed 15, Gaussian: silence
- Seed 15, empirical: silence
- Seed 16, Gaussian: silence
- Seed 16, empirical: silence
- Seed 17, Gaussian: silence
- Seed 17, empirical: silence
- Seed 18, Gaussian: silence
- Seed 18, empirical: The SCADA server: command interval cv was 0.998594. Normally 0.998647 to 1.99914.
- Seed 19, Gaussian: The SCADA server: 9 commands in one minute. Normally 3 to 9.
- Seed 19, empirical: silence
- Seed 20, Gaussian: The SCADA server: 8 commands in one minute. Normally 4 to 8.
- Seed 20, empirical: silence
- Seed 21, Gaussian: silence
- Seed 21, empirical: silence
- Seed 22, Gaussian: The SCADA server: 8 commands in one minute. Normally 4 to 8.
- Seed 22, empirical: silence
- Seed 23, Gaussian: The SCADA server: one command every 15.0 s on average. Normally every 1.6 s to 13.2 s.
- Seed 23, empirical: silence
- Seed 24, Gaussian: silence
- Seed 24, empirical: silence
- Seed 25, Gaussian: silence
- Seed 25, empirical: silence
- Seed 26, Gaussian: The SCADA server: command interval cv was 1.22333. Normally 1.24387 to 2.52801.
- Seed 26, empirical: The SCADA server: command interval cv was 1.22246. Normally 1.22275 to 1.9993.
- Seed 27, Gaussian: The SCADA server: 8 commands in one minute. Normally 4 to 8.
- Seed 27, empirical: The SCADA server: one command every 15.0 s on average. Normally every 6.0 s to 15.0 s.
- Seed 28, Gaussian: silence
- Seed 28, empirical: silence
- Seed 29, Gaussian: The SCADA server: 8 commands in one minute. Normally 5 to 7.
- Seed 29, empirical: silence
- Seed 30, Gaussian: The SCADA server: 8 commands in one minute. Normally 4 to 8.
- Seed 30, empirical: silence

Gaussian mean false alarms per ordinary run: 0.75 over 20 seeds.
Empirical mean false alarms per ordinary run: 0.20 over 20 seeds.

The tail is `one_sided_gaussian_tail(3)`, about 0.00135, inherited from the Gaussian
three-sigma claim. It was not searched. Template priors and evidence strength are the
placeholder values from ADR 0008.

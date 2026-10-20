# Lane B — self-closing maintenance alerts

This lane built one closer and one harness, measured them on the declared synthetic seeds, and declared how a Kelmarsh status log would explain an alert. The Kelmarsh development score ran on 2018–2022. Held-back years did not.

## What was built

An alert closes only when the job log cites exactly one work order, and that order is a sanctioning row covering the same asset and the same feature at the alert's time. The closure stores the schema and the order id. Window overlap does not close an alert. An attack that sits inside a real job, including a MIMIC with an empty citation, stays open. If someone stamps a real order id onto an attack, the closer accepts it. The harness does not do that.

The rival ignores the citation and closes on overlap. It is not what the product calls.

The same synthetic events are also scored with atlas-v1-consistency, at the frozen one-second windows. That catch rate is a diagnosis. The maintenance step and the attack step are the same size.

On Kelmarsh the rule is different, because that corpus has no work-order export. A budgeted atlas-v1-consistency alert is explained when the turbine's own status log covers that time and the service category is not "System OK (32)". Samples are ten minutes apart, so the frozen window rule collapses: lags become (0, 1) and the detrend window becomes 6 samples. Those windows were not retuned. This round trains on 2018 and scores 2019–2022 (ADR 0165).

Hypothesis confidence is not reported. Templates, known-link matchers, priors, and the consistency arithmetic were not changed.

## Synthetic seeds 97001–97020

Maintenance alerts closed with a cited work order: 158 of 180 (0.8778). The bar is 70%. It was met.

Attack alerts closed: 0 of 80. MIMIC alerts closed: 0 of 40. The bar that no attack closes was met.

The 158 of 180 is the share of orders the SAP loader kept. Each order produces one maintenance alert, and an order that does not sanction does not resolve. The idle share is the shipped 0.15. It was not fitted to the bar.

The overlap rival closed 27 of 80 attack alerts (0.3375). The margin, rival minus the citation rule, is 0.3375.

A citation permutation closed 1 of 80 attack alerts (0.0125). The margin over that chance is 0.0125. A random citation rarely matches an attack's asset, feature, and time.

atlas-v1-consistency, on the same events: 57 of 80 attack steps contained a budgeted alert (0.7125). 51 of those were on the attacked signal. Unexplained budgeted alerts: 0 over 15 shifts, 0 per shift. This is not a detection claim about a plant. The two steps are identical on purpose.

Runtime for both measurements: 0.409 seconds. The file is `eval_runs/build/lane-b/maintenance-closure.json`.

## Kelmarsh 2018–2022

Measured. ADR 0165. Train is 2018 because 2017 is absent and 2016 is not the registry file. Score is 2019–2022, six turbines, five signals, ten-minute windows.

Budgeted `atlas-v1-consistency` alerts: 74. The turbine's own log explains 57 (0.770). Unexplained: 17, which is 0.0006 per 8-hour shift over 26,298 shifts. This is not a detection claim and is not evidence the plant map detects attacks.

| Scorer | Alerts | Explained share | Unexplained per shift | Loops | Kept |
| --- | ---: | ---: | ---: | ---: | --- |
| Pooled log (start) | 74 | 0.770 | 0.0006 | 0 | yes |
| Operating modes | 616 | 0.424 | 0.0135 | 1 | no |

2023–2024 were not fetched and not scored.

## What blocked the held-back years

4.5 GB was free and the 2023 and 2024 zips are 1.42 GB together, on a volume already 98% full. They were not downloaded and not opened.

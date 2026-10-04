# ADR 0089 — Three published HAI detectors, checked against their own table

- **Status:** Accepted
- **Date:** 2026-10-04
- **PART:** v1 roadmap week 1, step 3
- **Depends on:** [ADR 0087](0087-every-hai-version-is-registered.md),
  [ADR 0088](0088-etapr-and-shift-budget-recall.md)

## Context

Week 1 asks for two or three published methods that have public code and a reported HAI
result, reproduced as named detectors and checked against the paper's own numbers. The v1
pass criteria are still a draft. This ADR does not compare the reproductions with Atlas, and
it does not score them against that draft.

The methods are MinMax, Steadytime and Histogram from Wolsing, Thiemt, van Sloun, Wagner,
Wehrle and Henze, "Can Industrial Intrusion Detection Be SIMPLE?", ESORICS 2022. The public
code is `ipal-ids/ipal_ids_framework` `ids/simple/{minmax,steadytime,histogram}.py`, read
2026-10-04 (blobs `2591ce26`, `cafe86ac`, `8b3e3fcb`). The paper also reports Gradient.
That tree has `preprocessors/gradient.py` and no Gradient IDS, so Gradient is not a fourth
reproduction.

The paper cites HAI 1.0. The registered release of that dataset is `hai-20.07`. The check
used the four files named in the registry, at the registered sizes, semicolon-separated.
`train2.csv.gz` is not entirely benign: 776 of its 241,200 rows have `attack` 1. Those rows
were left out of the fit. `train1` has no attack rows. The two test files were scored
separately, so an attack window cannot bridge them, and the counts were then added.
38 attack windows, 17,527 attack rows, 444,600 test rows.

## Decision

**1. Three detectors, new names.** `simple-minmax`, `simple-steadytime` and
`simple-histogram` live in `phos.eval.simple_iids`. Fit and score are separate: the caller
passes the benign corpus. A feature with more than ten distinct training values gets the
doubled range in MinMax and is ignored by the other two. Histogram's window is 100.
Steadytime's default back-dates a bad run the way the public `adjust` flag describes.
`Detection.confidence` is 0. The score is the code's likelihood, which is not a calibrated
probability.

**2. The paper's HAI row was not reproduced.** No column was dropped and no threshold was
moved to get closer. The hand-worked tests lock the public rules. The HAI figures below are
what those rules do on `hai-20.07`.

| | attack windows | point precision | point recall | point F1 |
|---|---|---|---|---|
| Paper, MinMax | 86% | 0.87 | 0.38 | 0.53 |
| This code, MinMax | 33/38 = 86.84% | 0.0682 | 0.6664 | 0.1238 |
| Paper, Steadytime | 28% | 0.86 | 0.11 | 0.19 |
| This code, Steadytime | 7/38 = 18.42% | 0.0179 | 0.0375 | 0.0243 |
| Paper, Histogram | 28% | 0.86 | 0.11 | 0.19 |
| This code, Histogram | 7/38 = 18.42% | 0.0179 | 0.0375 | 0.0243 |

MinMax also counted 255 alert-runs that overlap an attack and 811 that do not. The paper's
row is 73 and 7. Of the MinMax row-alerts, 147,135 come from `P1_PCV02Z`, whose benign
range is about 11.98 to 12.24. Steadytime and Histogram alerted on the same 36,656 rows.
The paper prints those two methods as the same row as well; the rate is still not 28%.

The paper's evaluation runs inside IPAL, which parses HAI, may extend alarms, and was not
re-executed here. Matching that stack was not attempted by changing the rules.

**3. Nothing is a frozen measurement.** No row was appended to `eval_runs/log.jsonl`. The
names are not `hai`, `atlas-mahalanobis`, or any other frozen log name. Roadmap §2 was not
applied.

## Consequences

A later comparison can call these detectors. It cannot treat the paper's HAI table as
confirmed by this run, and it cannot treat 86.84% as the paper's 86%. The one number that
sits next to the paper's headline is the MinMax window rate. The point scores do not.

# A6 — parameters behind the v1 numbers

A6 is met. Every public v1 number comes from one configuration. The values that
differ between corpora are the corpus's sample period, and the file layout
required to read it. Both were declared before the measurement that used them.
Nothing here was rescored. No threshold, window, or prior was changed.

Roadmap sentence: every v1 number comes from a single configuration; no
parameter differs between corpora. A per-corpus value derived by a rule declared
before measurement, for example from the sample rate, is one configuration.

## Numbers this audit covers

- The G1 headline and the columns beside it, in
  `eval_runs/v1/g1-baseline-table.md`: recall within budget, reference eTaPR,
  HAICon eTaPR, and point-adjusted F1, for `g1-baseline:atlas-mahalanobis`,
  `g1-baseline:simple-minmax`, `g1-baseline:simple-steadytime` and
  `g1-baseline:simple-histogram`, on hai-20.07, hai-21.03, hai-22.04, hai-23.05,
  batadal, batch-distillation and data4cyber.
- The grouped rows in that same file (`g1-grouped:`).
- A2's recall within budget for `atlas-v1-consistency` on the five judging
  corpora, in `eval_runs/v1/a2-status.md`. HAI 22.04 and 23.05 quote ADR 0104.
  BATADAL quotes ADR 0113. HAI 20.07 and 21.03 are the lab scorer in ADR 0115.

## One configuration, same on every corpus

| Parameter | Value | Where |
| --- | --- | --- |
| Atlas model in the G1 table | `MahalanobisModel()`: shrinkage 0.05, average-variance target, `joint_k` 0, adaptive joint quantile unset, `emit_k` 1.0, `band_k` 3.0 | ADR 0095, `phos.atlas.multivariate` |
| G1 alert threshold | 3.0 on the conditional departure | `G1_ATLAS_THRESHOLD` |
| Alerts per shift | 8 | `G1_ALERTS_PER_SHIFT` and `ALERTS_PER_SHIFT` |
| Shift | 8 hours | `phos.eval.budget.OPERATOR_SHIFT` and `SHIFT_SECONDS` |
| Rank tie break | higher score, then earlier timestamp, then earlier input order | `recall_within_budget` |
| Opponents | minmax, steadytime (`adjust` true), histogram | ADR 0090 |
| Discrete cutoff | 10 | `DISCRETE_THRESHOLD` |
| Histogram window | 100 samples | `HISTOGRAM_WINDOW` |
| Opponent confidence | 0 | ADR 0095 |
| Columns left out of the fit when present | `recipe_step`, `operating_point` | `ROUTING_REGISTERS` |
| Fit | every attack-free scored training row; the recorded time span does not change the threshold | `score_splits` |
| Reference eTaPR | theta_p 0.5, theta_r 0.1, delta 0.0 | `REFERENCE_ETAPR` |
| HAICon eTaPR | pi 0.7, rho 0.1, delta 180 samples; alpha 0.5 is recorded and is not passed | `HAICON_2020`, ADR 0091, ADR 0095 |
| Point-adjusted F1 | reported, not the headline, on the unbudgeted points | ADR 0088 |
| Grouping | gap 60 s, event window 300 s, span 600 s, onset fraction 0.1, onset level 2.0, 8 alerts per 8-hour shift | `phos.eval.grouping`, ADR 0099 |
| Consistency champion | `atlas-v1-consistency` | `RESULT_NAME` |
| Consistency constants | ridge 1.0, residual quantile 0.9999, range weight 10, episode threshold 1.0, onset fraction 0.1, onset level 2.0, calibration rank 3 | `phos.atlas.consistency` |
| Consistency windows at 1 s | lags (0, 5, 15, 30, 60), fit step 5, detrend 3600 step 60, feature gap 60, event window 300, span 600, second-alert separation 30 | `FROZEN_WINDOWS` |

The histogram window is 100 samples on every corpus. An hourly corpus therefore
spans more wall-clock time inside that window. The constant was not given a
per-corpus value. The same is true of the HAICon tail: it is 180 samples on
every file's scored index. ADR 0095 says that count is not rescaled when the
median step disagrees. The wall-clock length is 180 times the declared sample
period: 180 s on the 1 s corpora, 1800 s on batch distillation, 648000 s on
BATADAL.

The fit is the attack-free training rows of that corpus. There is no second fit
window, in samples or in hours, chosen per corpus.

## Sample period, per corpus

Declared in `DECLARED_PERIOD_SECONDS` before the G1 run, and confirmed by the
measured median in the published notes.

| Corpus | Declared period | Measured median in the G1 note |
| --- | ---: | --- |
| hai-20.07 | 1 s | 1 s |
| hai-21.03 | 1 s | 1 s |
| hai-22.04 | 1 s | 1 s |
| hai-23.05 | 1 s | 1 s |
| batadal | 3600 s | 3600 s |
| batch-distillation | 10 s | 10 s |
| data4cyber | 1 s | 1 s |

## BATADAL's windows

BATADAL's consistency windows are `windows_for_period` applied to its declared
sample period of 3600 s. That is one declared rule, ADR 0112, written before any
consistency score of BATADAL. It is the same function on every corpus. Each
frozen window is that many seconds, because that is what it was on 1-second HAI,
and it becomes `max(1, floor(seconds / period + 0.5))` samples. Lag 0 stays 0.
Lags that land on the same sample are kept once.

At 1 s the function returns `FROZEN_WINDOWS`, so hai-20.07, hai-21.03, hai-22.04
and hai-23.05 are the frozen configuration. At 3600 s it returns lags (0, 1) and
1 sample for every other window: fit step, detrend window, detrend step, feature
gap, event window, event span, and second-alert separation. Those counts are the
rule at an hourly sample. They are not a BATADAL-only window set entered after
looking at a score.

`atlas-v1-consistency` is not a v1 number on batch distillation or Data4Cyber.
The rule at distillation's 10 s period would be lags (0, 1, 2, 3, 6), fit step 1,
detrend 360 step 6, feature gap 6, event window 30, span 60, second-alert
separation 3. That figure is the rule, and it was not used for a published v1
number.

Grouping stays in seconds (ADR 0099) on every corpus, including BATADAL. It does
not call `windows_for_period`.

## Readers, per corpus

These are how each published file is turned into columns. They were declared
before the score that used them. They are not detector thresholds.

| Corpus | Reader | Declaration |
| --- | --- | --- |
| hai-20.07 | semicolon; `time`; labels `attack`, `attack_P1`, `attack_P2`, `attack_P3` | ADR 0095 |
| hai-21.03 | comma; the same labels; `train1` and `test1` also resolved under `data/hai` | ADR 0095 |
| hai-22.04 | comma; `timestamp`; `Attack` last; 86 features; train attack runs 0; test runs 7, 17, 10, 24; denominator 58 | ADR 0101, before the score |
| hai-23.05 | series has no Attack column; `label-test1.csv` and `label-test2.csv` joined by row, because the label timestamps are minute-truncated and do not match the series as text; denominator 52, not the summary's 40 | ADR 0101, before the score |
| batadal | prepared train and test; attack is the prepared label 1; unlabelled `-999` is not an attack | registry prepare, ADR 0095, ADR 0112 |
| batch-distillation | prepared pair; label `-1` is unscored | ADR 0082, before G1 |
| data4cyber | prepared pair; no unscored label | ADR 0095 |

## Verdict

No threshold, alert budget, shift length, opponent default, Mahalanobis
argument, consistency constant, eTaPR sample count, or grouping constant differs
between corpora. The sample period differs because the recordings differ, and
`windows_for_period` of that period is the one rule ADR 0112 declared before
measurement. A6 is met.

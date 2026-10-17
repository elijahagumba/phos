# atlas-v1-consistency on BATADAL, scored once

Declared in ADR 0112. Recall within budget (8 alerts per 8-hour shift) is the headline.
eTaPR and point-adjusted F1 are reported and are not. The grouped rows beside it are
ADR 0100's published counts, not scored again.

| Detector | Caught | Attacks | Recall within budget | eTaPR F1 (reference) | eTaPR F1 (HAICon) | Point-adjusted F1 | Alerts |
|---|---:|---:|---:|---:|---:|---:|---:|
| atlas-v1-consistency | 5 | 5 | 1.000000 | 0.112084 | 0.259780 | 0.264653 | 1335 |
| g1-grouped:atlas-mahalanobis (published) | 5 | 5 | | | | | |
| g1-grouped:simple-minmax (published) | 3 | 5 | | | | | |
| g1-grouped:simple-steadytime (published) | 2 | 5 | | | | | |
| g1-grouped:simple-histogram (published) | 2 | 5 | | | | | |

Windows: `{'lags': (0, 1), 'fit_step': 1, 'detrend_window': 1, 'detrend_step': 1, 'feature_gap': 1, 'event_window': 1, 'event_span': 1, 'second_alert_min_separation': 1}`.
Beyond the best grouped checked opponent (g1-grouped:simple-minmax): 2.
Attacks caught: batadal-test-prepared.csv#0, batadal-test-prepared.csv#1, batadal-test-prepared.csv#2, batadal-test-prepared.csv#3, batadal-test-prepared.csv#4.

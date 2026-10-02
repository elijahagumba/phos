# CERT r3.1 identity-6B queue autopsy

Budget **48**. Detector name `autopsy:6b-top-budget` (not `aggregate:gaussian:peer set (34 features) (6B)`).

True positives **5**. False positives **43**.

The frozen 6B row stays precision **0.104** (5 TP / 43 FP) at 48 alerts. This table is a diagnosis, not a replacement.

| Stem | TP | FP |
| --- | --- | --- |
| `distinct_files` | 3 | 7 |
| `off_hours_logon_count` | 1 | 9 |
| `logon_count` | 1 | 7 |
| `removable_device_connects` | 0 | 13 |
| `distinct_http_hosts` | 0 | 3 |
| `distinct_pcs` | 0 | 2 |
| `new_counterparties` | 0 | 1 |
| `new_pcs` | 0 | 1 |

Named-subset bakeoff: no stem led every TP with zero FP; do not invent a subset.

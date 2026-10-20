# S3 — CERT r4.2 declared held out

Lane A, 2026-10-17. ADR 0147.

## What was declared

CERT release r4.2, dataset `cert-insider-threat`, role `held-out`. The declaration
is `phos.sentiel.r42_holdout`. A call to score it returns false. The declaring
session does not score it even if the files are later found on disk.

## Why it was not fetched

The deposit page recorded for this dataset is on `kilthub.cmu.edu`. The file URLs
recorded for the same deposit are on `ndownloader.figshare.com`. r4.2's own file id
is not in the registry, so no file URL and no sha256 were invented. Neither host is
on the allow-list (`zenodo.org`, `www.netresec.com`, `github.com`,
`raw.githubusercontent.com`, `media.githubusercontent.com`, `pypi.org`,
`files.pythonhosted.org`, `researchdata.tuwien.ac.at`). The archive is not on disk.
It was not downloaded.

## What was not scored

No insider count, no precision, no recall, no chance null, no comparison with the
frozen 6B scorer. Peer-group advantage stays retired.

## Scorecard

| Field | This run |
| --- | --- |
| catches_within_budget | not measured |
| margin_over_best_simple_rival | not measured |
| margin_over_chance | not measured |
| falsified_sensor_passes | not applicable |
| naming_right | not applicable |
| naming_wrong | not applicable |
| reconstruction_error | not applicable |
| maintenance_closures | not applicable |
| calibration | not measured |
| false_alerts_per_shift | not measured |
| runtime | not measured |

## Bar

The holdout declaration is in place. S3's measurement bar is not met, because the
release was not scored.

Round 2 (2026-10-19, ADR 0194): still held out, still not fetched, still not scored. The kept development scorer is 6B; no lane-a-dev name survived the target-1 loops.

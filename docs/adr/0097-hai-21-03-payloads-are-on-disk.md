# ADR 0097 — HAI 21.03's eight files are on disk, with a checksum each

- **Status:** Accepted
- **Date:** 2026-10-05
- **PART:** v1, registry housekeeping after G1
- **Depends on:** [ADR 0087](0087-every-hai-version-is-registered.md)

## Context

ADR 0087 registered `hai-21.03` as `registered-not-fetched`. The integrated `hai` entry
already held train1 and test1. The other six files are now on disk as well. This record
is the checksum of each payload. It does not score a detector, and it does not fetch
HAI 22.04 or 23.05.

## Decision

`hai-21.03` is `on-disk`. That status is outside `FETCHABLE_STATUSES`, so
`scripts/fetch_datasets.py --all` does not download these URLs and does not rewrite
`data/hai/manifest.json`. Each file has a sha256 of the gzip payload:

| File | sha256 |
|---|---|
| train1.csv.gz | `fdd0162315b32817ba665e2cc8990eb09c47c4edc29683a86b11dc9df062b3a9` |
| train2.csv.gz | `c330af06a24f5fe3df864dddc0e9cbbbfd27db2e005bd32dc8ab3eb2ab356337` |
| train3.csv.gz | `de09120c617bad5f4f3cab86705137fe7ced4b1123fb67ffdf67fd645f3d1b8f` |
| test1.csv.gz | `532de41bed372206941609d05b763958f59abecfd63c8c123649f823452e445e` |
| test2.csv.gz | `c5572e0ed19906107ceb56c4b4f40e165153fc7ba87b3506230d53d2478c29bb` |
| test3.csv.gz | `bff835894baff0c73871bc01ece4f5cf759d455a049e808b012128767420caaf` |
| test4.csv.gz | `51380fd28fd985b94a10cae3d8b80926becb3af9f233f2d3a38ab8be9482a482` |
| test5.csv.gz | `f0d59308b167ed95d0e81fb3e27c906682c9b21d3dba0ab4c4d696565df35179` |

train1 and test1 are the copies the integrated entry already uses, at
`data/hai/hai-21.03-train1.csv.gz` and `data/hai/hai-21.03-test1.csv.gz`. The other six
are `data/hai-21.03/<filename>`. The payloads are not in git. `hai-20.07`, `hai-22.04`,
`hai-23.05` and `haiend-23.05` stay `registered-not-fetched`.

## Consequences

A later fetch of the raw GitHub URL is not how these files are obtained. The integrated
`hai` preparer and its manifest stay as they were. No detection number moves.

## What would reverse this

A payload on those paths whose sha256 is not the value in this record.

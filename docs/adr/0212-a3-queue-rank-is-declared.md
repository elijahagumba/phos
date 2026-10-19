# ADR 0212 — A3's queue rank is declared before the one look

- **Status:** Accepted
- **Date:** 2026-10-19
- **PART:** v1 sprint, lane A, criterion A3
- **Depends on:** [ADR 0112](0112-consistency-windows-by-sample-period-and-one-batadal-score.md),
  [ADR 0211](0211-a6-is-one-configuration.md)

## Context

A3 is one measurement of the frozen champion on the five judging corpora. Those
corpora are validation data. This record is committed and pushed before any
validation file is opened. Nothing in it is a score.

## Decision

**Scorer.** The frozen champion `atlas-v1-consistency`, parameters unchanged.
Windows are `windows_for_period` of the corpus's declared sample period. At 1 s
that is the frozen HAI windows. At BATADAL's 3600 s it is ADR 0112's rule. The
detector is not edited.

**Corpora.** HAI 20.07, HAI 21.03, HAI 22.04, HAI 23.05, BATADAL. A corpus that
cannot be scored counts as not won; the denominator does not shrink. "At least
half of all those attacks."

**Metric.** Roadmap wording: for each attack, the rank of its first true alert
in its shift's full queue, before the budget cut. A shift is the frozen 8-hour
shift (`phos.eval.budget.OPERATOR_SHIFT`). The full queue is every alert in that
shift, ranked by the champion's own score, ties broken as `recall_within_budget`
breaks them (higher score, then earlier timestamp, then earlier input order).
Pass for an attack if it has a true alert in the top 10% of its shift's queue
(ceil, so a queue of 1 is the top slot). An attack with no alert in its shift
fails. Pass for A3 if at least half of all attacks across the five corpora pass.

The attack's shift is the shift that contains the attack's start. The first true
alert is the earliest alert in that shift's ordered queue whose timestamp lies
inside the attack, inclusive, using the same attack windows as the G1 scorer.
Alerts the budget would drop stay in the queue. The champion's alerts are its
events, before `budget_alerts`.

**Command.** `uv run python scripts/measure_a3_queue_rank.py`

**Result name.** `atlas-v1-consistency:a3-queue-rank`

**Output.** `eval_runs/build/v1/atlas/a3-queue-rank.json`

The script refuses to run if that JSON already exists. Nothing is tuned on the
result.

**Registry sha256.** HAI 20.07 is already on disk and is included. Its four
registry files have no sha256. BATADAL's two registry files have no sha256:

| File | Bytes | URL |
| --- | ---: | --- |
| BATADAL_dataset03.csv | 2940389 | https://www.batadal.net/data/BATADAL_dataset03.csv |
| BATADAL_dataset04.csv | 1225392 | https://www.batadal.net/data/BATADAL_dataset04.csv |

The champion's existing BATADAL path reads `batadal-train-prepared.csv` and
`batadal-test-prepared.csv`, produced by `prepare_csv` in
`scripts/fetch_datasets.py` from those two files. No sha256 is invented for them.

HAI 21.03, from `data/registry.json`:

| File | sha256 |
| --- | --- |
| train1.csv.gz | fdd0162315b32817ba665e2cc8990eb09c47c4edc29683a86b11dc9df062b3a9 |
| train2.csv.gz | c330af06a24f5fe3df864dddc0e9cbbbfd27db2e005bd32dc8ab3eb2ab356337 |
| train3.csv.gz | de09120c617bad5f4f3cab86705137fe7ced4b1123fb67ffdf67fd645f3d1b8f |
| test1.csv.gz | 532de41bed372206941609d05b763958f59abecfd63c8c123649f823452e445e |
| test2.csv.gz | c5572e0ed19906107ceb56c4b4f40e165153fc7ba87b3506230d53d2478c29bb |
| test3.csv.gz | bff835894baff0c73871bc01ece4f5cf759d455a049e808b012128767420caaf |
| test4.csv.gz | 51380fd28fd985b94a10cae3d8b80926becb3af9f233f2d3a38ab8be9482a482 |
| test5.csv.gz | f0d59308b167ed95d0e81fb3e27c906682c9b21d3dba0ab4c4d696565df35179 |

HAI 22.04:

| File | sha256 |
| --- | --- |
| train1.csv | 63383690ffc5344ba68a019c7000854a4d341a22d743ac035f5207072a197b33 |
| train2.csv | f496991bbef4a6ef5881505aa242fe05cc500b4d5c4cea0d2cf1cf79e4e99285 |
| train3.csv | 4910c49dc07cce238e05c449972a30b7588139ef92d36067f32aadd820e63de7 |
| train4.csv | 81a1c3a8e1726c92c9253602b8628b72d0508a9c260ff21109433ad2b82687bf |
| train5.csv | 298468467991e73689b61f3cd3975ca21685ef8ba5b5ced4d6a7874f304d9cf7 |
| train6.csv | 717b37b7b88b40885cb6994c9fe00d08a941ec0c3c73801e378f84e846ae35d4 |
| test1.csv | 19627f5dac40c3a5039e7468cfd6c6e4ccd37a85055671e8c349b6bce5f50ed1 |
| test2.csv | b2ba5d6665deee1c86870a3970417b51a3e640a2cc18b9f8de2d6d8a21979923 |
| test3.csv | f253f1c78a4a4654d843f8f670a24caa7a72ac91e4418b4505009822b3c55940 |
| test4.csv | 2d2e99ed3364d75d27ab84f0a6523496f7295decf363c90b8a1b9b84e1070376 |

HAI 23.05:

| File | sha256 |
| --- | --- |
| hai-train1.csv | 53007b0ba604fbf338e7ac2e08cd81d874b5d1388f3aecb213ddcba5bf2bec4a |
| hai-train2.csv | 0e520e82bf78a661ab19ce4967f3c766bd809820f457a9c90c365102d4534c56 |
| hai-train3.csv | bfcec2dc05adea103e7491546b0e28268faaa26d3cc717d10f4595c94b81e85d |
| hai-train4.csv | 56658c83657d42a65db982b864362e0d0ffeb96d1f7b357d5e76e3a5c522d940 |
| hai-test1.csv | 78c7f1d4de1f2ab9ccc2f8c719f80f831033543adb0c81d0d78f84f40838d4be |
| hai-test2.csv | b2b8dd295aefd87e39260fe43cb4c73ee86d6264b0ac4b0761e7efb0c2b545c3 |
| label-test1.csv | eaf69edb9c5834bc393afd7bf658b5e408d34fd7bfc3261f80516765fb818fbc |
| label-test2.csv | 8090c44981176e39b0f01a7126a80248ac0b93355c00f9db4d4e2f2106452b92 |

The summary texts already on disk are not inputs to this score. Their registry
sha256 values stay in `data/registry.json` and are not repeated here.

## Consequences

The next step is to re-fetch the deleted validation payloads from the registry
URLs, check sha256 where the registry has one, prepare BATADAL with the existing
preparer, and run the command once. Whatever that run writes is the result.
A second run is refused by the output file.

## What would reverse this

Opening a validation file before this record is pushed, changing the champion
or a window because of the result, or running the command twice.

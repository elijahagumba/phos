# ADR 0025 — Joining batch-distillation without poisoning the false-positive ruler

- **Status:** Accepted
- **Date:** 2026-08-21
- **PART:** C2 (first mixture baseline)
- **Supersedes:** nothing
- **Depends on:** [ADR 0024](0024-corpus-intake-a-confirmed-licence-a-version-pin-and-two-label-sources-that-disagree.md),
  [ADR 0006](0006-dataset-registry-and-never-committing-data.md),
  [ADR 0003](0003-window-level-recall-and-false-positives-per-normal-hour.md),
  [ADR 0009](0009-joint-modelling-per-signal-attribution-and-the-model-that-lost.md)

## Context

ADR 0024 acquired the laboratory batch-distillation corpus, confirmed its licence, pinned
version 1.1.2, and recorded three decisions the first measurement has to honour: fit only on
experiments both label sources call clean; restrict to one mixture family; never quote a recall
figure as attack recall. It left the preparation path outstanding, because the registry's
one-source-file-per-split schema cannot join 119 experiments across three modality archives.

This record is that path, and the first number it produced. The number is a baseline, not a
claim that the operational false-alarm target has been met.

## Decision 1 — Join at acquisition time; do not grow `LabelledCsvAdapter`

The corpus is turned into two prepared CSVs (dual-clean train, labelled test) plus a third
held-out file of YAML-contaminated train experiments. `LabelledCsvAdapter` reads them
unmodified. That is ADR 0006 decision 4 applied to a corpus that happens to arrive as a tree
rather than a table: every trap is resolved once, on disk, from a committed spec, and the
adapter's contract stays "a clean labelled CSV" permanently.

Rejected: a second `DatasetAdapter` that reads the zips at evaluation time. It would teach the
harness a corpus, which is the thing the adapter protocol exists to prevent, and it would
re-discover the ragged-file tail and the YAML disagreement on every run.

The join spec lives in `data/registry.json` under `join` and is executed by
`phos.eval.batch_distillation.prepare_corpus`. YAML is inspected by a string match on
`class: Anomaly` and `class: ConfirmedAnomaly`, not parsed. `pyyaml` is not a PHOS dependency
and this path does not make it one. A missing YAML on a training file is treated as
contaminated: absence of evidence is not evidence of absence.

## Decision 2 — Pack experiments onto a continuous clock, with a seam row between them

ADR 0024 decision 6 gave each experiment its own synthetic date so that a grouping window
could never span two timelines. That is the right *grouping* key. It is the wrong *ruler*
key. `Dataset.normal_duration` is the wall-clock span from the first observation to the last,
minus labelled intervals. Day-scale gaps between 63 test experiments would add about 62 days
of empty time to the false-positive denominator and make every rate look ~20× better than the
traffic supports. The model would not notice — `MahalanobisModel` scores rows independently —
which is exactly why the error would be invisible in the detection numbers and visible only
in the hours.

The prepared CSV therefore packs experiments onto a continuous synthetic clock starting at
`1970-01-01T00:00:00+0000`. Each experiment keeps its 1 Hz (or strided) internal spacing. A
seam row one second after the last sample carries label 0 and **no signal values**, so
`LabelledCsvAdapter`'s consecutive-row collapse cannot merge a perturbation at the end of one
experiment with a perturbation at the start of the next, and no fabricated measurement enters
the ontology. The next experiment starts one second after the seam. Across 63 test experiments
the seams add 124 seconds to a 109.92-hour span, which is 0.03% of the denominator.

Grouping, if it is ever run on this corpus, must group by experiment identity, not by
wall-clock proximity of the packed clock. That identity is not written as a numeric column:
the adapter's auto-detection would feed it in as a signal.

## Decision 3 — Stride 10, and refuse a stride that erases a window

Full 1 Hz is 395,712 test rows × 31 signals ≈ 12 million `Observation` objects, which is the
same intractability HAI forced at 17 million. Preparation keeps every 10th row, as HAI did,
and records the stride in the source note so a number is never quietly computed on a thinned
corpus. The shortest labelled run in this mixture is 11 seconds; every one of the 131
perturbation windows survives the stride, and preparation would refuse the write if one did
not.

The dual-clean fit set is 15 experiments, 108,981 rows at 1 Hz, 10,904 timestamps after
stride, 30.27 original hours. The test set is 63 experiments, 131 windows, 73.13 hours of
labelled-normal operation under ADR 0003.

## Decision 4 — The designed protocol is the only honest headline on this corpus

`train_test_split`'s prefix protocol carves an attack-free prefix out of one chronological
capture. Concatenated experiments are not one capture; a "prefix" of the packed file is "the
first experiments in sort order". The three-way calibration split has the same problem. Both
remain available behind `--protocol` for corpora where they mean something. The number logged
for this corpus is **designed**: fit on the dual-clean train file, score the labelled test
file. Nothing scores data it was fitted on.

## What was measured

Fitted on the 15 dual-clean experiments of `ternary_butan-1-ol+propan-2-ol+water`. Scored on
its 63 test experiments. Alert threshold 3.0, seed 11, the same ruler as BATADAL and HAI.
Recall is **perturbation recall**.

| Detector | Recall | FPs | FP/normal-hr | Precision | ECE | Brier |
| --- | --- | --- | --- | --- | --- | --- |
| `model:gaussian` | 0.92 | 11,741 | 160.55 | 0.549 | 0.220 | 0.297 |
| `model:atlas-pca` | 0.86 | 47,933 | 655.43 | 0.515 | 0.271 | 0.301 |
| `model:atlas-mahalanobis` | 0.60 | 1,369 | 18.72 | 0.740 | 0.105 | 0.205 |

`MahalanobisModel` cuts false positives 8.6× relative to the per-signal Gaussian, at a
recall cost of 0.92 → 0.60. `PcaResidualModel` loses again, as it did on HAI and BATADAL
(ADR 0009). Four signals were constant across the dual-clean fit set and sit outside the
joint model: `AV709`, `AV716`, `LS702`, `P301`.

## What these numbers do not license

**They are not attack recall.** The 131 windows are engineered process perturbations. The
source note on every report says so.

**They are not a cross-recipe claim.** Two other mixtures remain on disk, unread.

**They do not meet the operational false-alarm budget.** 18.72 false positives per hour of
normal operation is about 449 alerts/day equivalent. The sprint target is 2–3 actionable
alerts/day under normal traffic, roughly 0.1 per hour. The joint model is 8.6× quieter than
the per-signal baseline and about 150× too loud for that budget. A 10× joint-model reduction
was the internal comparison target; 8.6× is the measurement, not a rounding of 10.

**They are not a calibrated confidence.** ECE 0.10 on Mahalanobis is a measurement of
miscalibration, not a licence to surface 90% to an operator (Constitution §3.3).

**They are not phase-conditional.** ADR 0018 exists because a pooled covariance on a batch
process can set a noise floor that swallows every band. This baseline is the pooled model.
Whether this column declares a phase register is still the open question ADR 0024 left on
the operation logs.

## Consequences

`scripts/fetch_datasets.py batch-distillation` is fetchable, verifies the published MD5 of
every file, joins the one mixture, and writes `data/batch-distillation/manifest.json`. The
designed baseline is in `eval_runs/log.jsonl`. The YAML-contaminated train experiments are
prepared as their own CSV and have not been scored: they are the probe ADR 0024 reserved for
"does Atlas see what the annotators saw", not part of this baseline.

The next measurement that would change what can be claimed is whether phase-conditional
modelling (ADR 0018) reduces the 18.72/hour without giving back the 0.60 perturbation
recall — and that measurement is only licensed if the operation logs actually declare a
phase.

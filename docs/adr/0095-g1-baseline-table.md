# ADR 0095 — The G1 baseline table, one Atlas configuration, and where it loses

- **Status:** Accepted
- **Date:** 2026-10-04
- **PART:** v1 roadmap weeks 1–3, gate G1
- **Depends on:** [ADR 0088](0088-etapr-and-shift-budget-recall.md),
  [ADR 0090](0090-authors-hai-pipeline-matches-our-detectors-not-the-paper.md),
  [ADR 0091](0091-haicon-2020-etapr-parameters.md)

## Context

Roadmap §2 is frozen at `93156a51d4cd2e2be5684ca817306d2db07c0be7`. A1 asks for one table:
Atlas and every reproduced published method, on the integrated public ICS corpora whose
licence permits commercial use, with recall within budget as the headline, eTaPR beside
it, and point-adjusted F1 reported and never headlined. The budget is 8 alerts per
8-hour shift. The five corpora that judge are HAI 20.07, 21.03, 22.04, 23.05 and
BATADAL. A corpus that cannot be scored counts as not won. Distillation and Data4Cyber
are reported and judge nothing. The three opponents in ADR 0090 are checked. This
record does not edit §2.

## Decision

**1. One Atlas configuration.** `MahalanobisModel()` with no argument changed: shrinkage
0.05, `ShrinkageTarget.AVERAGE_VARIANCE`, `joint_k` 0, `adaptive_joint_quantile` unset,
`emit_k` 1.0, `band_k` 3.0. An alert is a conditional departure of at least 3.0, the
threshold in `scripts/evaluate_atlas.py`. Each alerting feature spends its own slot.
This is not `JointMomentDetector`, not an adaptive joint quantile, and not a raised
dwell. The column path calls the same fit and the same departure as that model. A test
checks it against `ModelDetector` on a complete grid.

**2. The opponents are not retuned.** `simple-minmax`, `simple-steadytime` and
`simple-histogram` keep the published defaults (discrete cutoff 10, histogram window
100, Steadytime `adjust` true). Confidence stays 0. Fit uses attack-free rows only.
`recipe_step` and `operating_point` are not signals. HAI is scored from the native
files, not the stride-10 prepared series.

**3. The headline is an argument, not a new default.** `recall_within_budget` is called
with 8. Its signature still requires the count. Beside it, on the unbudgeted alert
points: `etapr_at(REFERENCE_ETAPR)`, and `etapr_sample_tail` at HAICon pi 0.7, rho 0.1
and 180 samples. Alpha 0.5 is printed and is not passed. `etapr` still rejects
`delta=180`. Delta is a sample count on each file's scored index. It is 180 seconds
where the declared period is 1 second, 1800 seconds on distillation's 10-second rows,
and 180 hours on BATADAL's hourly rows. It is not rescaled after the run.

**4. Files do not share a tail.** Each test file is scored on its own clock. Recall is
the micro-average. eTaPR F1 and point-adjusted F1 are the attack-count-weighted mean of
the per-file scores. Unscored rows leave the point index and still spend a budget slot
if an alert lands there. A timestamp with any feature alert is one point.

**5. New names only.** The command is `uv run python scripts/measure_baseline_table.py`.
It writes `eval_runs/v1/g1-baseline-table.md` and `.json`. It does not append
`eval_runs/log.jsonl`. The result names are `g1-baseline:atlas-mahalanobis`,
`g1-baseline:simple-minmax`, `g1-baseline:simple-steadytime` and
`g1-baseline:simple-histogram`.

**6. Two versions are rows and are not scores.** HAI 22.04 and 23.05 are Git LFS
pointers (ADR 0087). They stay in the table. They count as not won.

## Measurement

Nothing below was used to change a threshold, a feature list, a dwell, or an opponent
rule. Regenerating the note's wording left these fractions the same.

Headline, caught attacks / attacks, 8 alerts per shift:

| Corpus | Atlas | Best checked opponent |
|---|---|---|
| HAI 20.07 | 9/38 | simple-minmax 15/38 |
| HAI 21.03 | 7/50 | simple-minmax 14/50 |
| HAI 22.04 | not scored | not scored |
| HAI 23.05 | not scored | not scored |
| BATADAL | 5/5 | simple-minmax 3/5 |

Atlas is strictly above the best checked opponent on one of the five judging corpora.
It is below on both HAI versions that could be scored. The two that could not be scored
count as not won.

On HAI 20.07, point-adjusted F1 is 0.758717 for Atlas and 0.163805 for MinMax. That
number is in the table and is not the headline. Reference eTaPR F1 there is 0.281654
for Atlas and 0.347471 for MinMax. On BATADAL, HAICon-parameter eTaPR F1 is 0.652324
for Atlas and 0.690050 for Steadytime, while the headline still has Atlas at 5/5.

Distillation, reported only, perturbation recall: Atlas 21/126, MinMax 16/126.
Data4Cyber, reported only, process-phase recall: Atlas 0/2, MinMax 1/2. The HAI 20.07
fit excluded 776 attack rows and kept 51 of the state signals. The HAI 21.03 fit
excluded 0 attack rows and kept 57 signals.

## Consequences

The table exists and one command regenerates it. A2's "strictly higher on at least
three of the five" is not met by this table. Roadmap §2 is unchanged. Frozen log rows
are unchanged. A later configuration gets a new name.

## What would reverse this

A fetched payload for HAI 22.04 or 23.05 is a new row in this table, not a rewrite of
these fractions. A different Atlas configuration is a different result name.

# ADR 0100 — Grouped G1 rows, and Atlas still loses where the constants were chosen

- **Status:** Accepted
- **Date:** 2026-10-06
- **PART:** v1, the grouped rows beside the published G1 table
- **Depends on:** [ADR 0095](0095-g1-baseline-table.md),
  [ADR 0096](0096-sandbox-event-grouping-explains-the-budget-gap.md),
  [ADR 0099](0099-event-grouping-is-a-shared-wrapper.md)

## Context

ADR 0099 declared `group_published_alerts` and its constants before any grouped score.
ADR 0096 forbids comparing a grouped Atlas with an ungrouped opponent. The constants
were chosen on HAI 20.07 and held out on HAI 21.03, so those two grouped rows are
labelled seen. HAI 22.04 and 23.05 are the clean test and are not in this run.

## Decision

`scripts/measure_grouped_rows.py` fits the same G1 configuration as the published
table, builds each detector's published alert cells, and passes those cells through
`group_published_alerts`. Result names are `g1-grouped:atlas-mahalanobis`,
`g1-grouped:simple-minmax`, `g1-grouped:simple-steadytime`, and
`g1-grouped:simple-histogram`. The section is appended to
`eval_runs/v1/g1-baseline-table.md`. The numbers also sit in
`eval_runs/v1/g1-grouped-rows.json`. The published JSON is not rewritten. The
experiment log is not appended. The script refuses to write if the published line
`| hai-20.07 | yes | g1-baseline:atlas-mahalanobis | engine | 9 | 38 |` is missing.

Headline, recall within budget. Beyond grouping is grouped Atlas caught minus the
best grouped checked opponent caught.

| Corpus | Exposure | Grouped Atlas | Grouped MinMax | Grouped Steadytime | Grouped Histogram | Beyond grouping |
|---|---|---:|---:|---:|---:|---:|
| hai-20.07 | seen | 23/38 | 32/38 | 7/38 | 7/38 | −9 |
| hai-21.03 | seen | 15/50 | 36/50 | 14/50 | 14/50 | −21 |
| batadal | | 5/5 | 3/5 | 2/5 | 2/5 | 2 |
| batch-distillation | reported | 26/126 | 33/126 | 22/126 | 17/126 | −7 |
| data4cyber | reported | 1/2 | 1/2 | 0/2 | 0/2 | 0 |

Attacks only grouped Atlas catches:

- hai-20.07: `test1.csv.gz#11`, `test1.csv.gz#27`, `test1.csv.gz#5`
- hai-21.03: `test3.csv.gz#7`
- batadal: `batadal-test-prepared.csv#3`
- batch-distillation: `batch-distillation-test-prepared.csv` indexes 0, 109, 115, 120, 15, 47, 67
- data4cyber: none

Fit sizes match the published notes: HAI 20.07 550024 benign rows, HAI 21.03 921603,
BATADAL 8761, distillation 10904, Data4Cyber 1798.

Grouped MinMax on HAI 21.03 is 36/50. ADR 0096's control caught 41/50 by regrouping
MinMax's own range rule inside the sandbox. This row uses the published G1 cells.
Those are different alerts. This record does not change either rule to close that gap.

On hai-20.07 and hai-21.03 every grouped detector's reference eTaPR F1 and HAICon
eTaPR F1 is 0.0. The wrapper emits one sample per event, and eTaPR drops a prediction
whose overlap with the anomaly is below its threshold. Point-adjusted F1 on those
same rows is not zero: grouped Atlas is 0.790837 on HAI 20.07 and 0.355150 on
HAI 21.03. The headline of this row stays recall within budget.

On BATADAL the grouped headline counts match the published ungrouped counts. Grouped
Atlas HAICon eTaPR F1 is 0.6523243304962558 and grouped Steadytime is
0.6900501444182673, the same figures as the published rows, while the cell counts
fell (Atlas 543 to 182, Steadytime 206 to 144). A timestamp is one point, so fewer
feature-cells can leave the same ranges. On an hourly series the 60-second gap does
not merge neighbouring hours.

Distillation remains perturbation recall. Data4Cyber remains process-phase recall.
Neither judges. The published ungrouped fractions stay where ADR 0095 put them.
HAI 22.04 and 23.05 stay `not_scored`. No constant moved. Nothing was retuned.

## Consequences

A grouped Atlas is only compared with grouped opponents. Beyond grouping is negative
on both seen HAI editions and on distillation, zero on Data4Cyber, and 2 on BATADAL.
The clean HAI test is still one future run, declared before it is scored.

## What would reverse this

Replacing a published `g1-baseline:` fraction, scoring HAI 22.04 or 23.05 inside this
command, or changing a grouping constant after these numbers.

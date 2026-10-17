# ADR 0101 — The clean HAI run is declared, and it has not been scored

- **Status:** Accepted
- **Date:** 2026-10-06
- **PART:** v1, the one score of HAI 22.04 and 23.05
- **Depends on:** [ADR 0098](0098-hai-22-and-23-are-on-disk-and-not-scored.md),
  [ADR 0099](0099-event-grouping-is-a-shared-wrapper.md),
  [ADR 0100](0100-grouped-g1-rows-and-where-atlas-loses.md)

## Context

HAI 22.04 and 23.05 are on disk and have not been scored. ADR 0096 makes them the
clean test for any grouped configuration. ADR 0100 scored the wrapper on the corpora
the constants had already seen, and left these two out. The published table still
says the CSV is not on disk. That sentence is now false. It is corrected when this
run is scored, not before.

## Decision

One command, after this record is committed, and not before:

`uv run python scripts/measure_clean_hai.py`

It scores each of these detectors once, ungrouped and through
`group_published_alerts`, on hai-22.04 and hai-23.05 only:

- `g1-baseline:atlas-mahalanobis` and `g1-grouped:atlas-mahalanobis`
- `g1-baseline:simple-minmax` and `g1-grouped:simple-minmax`
- `g1-baseline:simple-steadytime` and `g1-grouped:simple-steadytime`
- `g1-baseline:simple-histogram` and `g1-grouped:simple-histogram`

The Atlas configuration is the published G1 configuration. The wrapper constants are
the ones in ADR 0099. Neither is changed. These two editions are not labelled seen.

HAI 22.04 is comma-separated. The first column is `timestamp`, the last is `Attack`,
and there are 86 feature columns. Train files train1 through train6 have zero attack
runs. Test runs are 7, 17, 10 and 24. The denominator is 58.

HAI 23.05 series files have no Attack column: `timestamp` and 86 features. Train
files hai-train1 through hai-train4 have no label file, so every train row is fit as
benign. Labels are `label-test1.csv` and `label-test2.csv`, columns `timestamp,label`,
joined to the series by row. Label-test2's timestamps are minute-truncated
(`2022-08-17 0:00` beside the series `2022-08-17 00:00:01`) and are not matched as
text. The label columns have 14 and 38 attack runs. The denominator is 52.
`summary_label2.txt` says "Attacks: 40 times"; the file lists 38 windows. 40 is not
the denominator.

The command refuses to start if `eval_runs/v1/g1-clean-hai.json` already exists. It
refuses to write if a file's attack runs are not the counts above, or if the
published line `| hai-20.07 | yes | g1-baseline:atlas-mahalanobis | engine | 9 | 38 |`
is missing. It fills the two `not_scored` placeholders in the markdown and replaces
those two objects in `g1-baseline-table.json` without reformatting the rest of that
file. Grouped rows are appended in the grouped section. It does not rescore any
other corpus. It does not append the experiment log.

This record does not contain a score. The command has not been run.

## Consequences

The next commit that contains fractions for these two editions is the one run. A
second run is a different command. A different denominator, a timestamp join, or a
changed constant is a different declaration.

## What would reverse this

Running the command before this record is committed, or treating the summary's 40
as the HAI 23.05 denominator.

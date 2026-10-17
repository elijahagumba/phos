# ADR 0103 — The frozen sandbox candidate is declared on the clean HAI editions

- **Status:** Accepted
- **Date:** 2026-10-08
- **PART:** v1, one more look at HAI 22.04 and 23.05
- **Depends on:** [ADR 0096](0096-sandbox-event-grouping-explains-the-budget-gap.md),
  [ADR 0099](0099-event-grouping-is-a-shared-wrapper.md),
  [ADR 0102](0102-the-clean-hai-run-and-where-atlas-loses.md)

## Context

ADR 0102 scored grouped Atlas and grouped MinMax once on HAI 22.04 and 23.05.
Grouped Atlas is behind grouped MinMax on both: 5/58 against 10/58, and 5/52
against 6/52. A second score of these editions needs a new command and a reason
written first.

The reason: `experiments/2026-10-04-sandbox/candidate.py` is the detector the
sandbox README names as worktree commit `6e7c665`, frozen on 4 October 2026.
That commit is not in this repository. The file arrived here in `77ab04e` and
its sha256 is `7d485b7298282b6b369d55675804d3017e9f952d1353b5e673c84734720433d4`.
None of its constants was chosen on HAI 22.04 or 23.05. Those editions were
fetched later. The question is whether this candidate's scoring — each signal
predicted from the rest of the plant at lags 0, 5, 15, 30 and 60, own-noise
calibration, detrending — beats grouped MinMax on that clean data.

## Decision

One command, after this record is committed, and not before:

`uv run python scripts/measure_candidate_look.py`

It refuses to start if `eval_runs/v1/g1-candidate-look.json` already exists, or
if the sha256 above does not match the file. It does not edit the G1 table. It
does not append the experiment log. It does not change a constant. It does not
refit Atlas.

The candidate is loaded from that file and called as frozen. `feature_scores`
runs once per edition. Own grouping is `_budget(_events(scores), time)`, which
is the body of `run`, including the spare second alert and the sample-index
gaps. The shared-wrapper row takes the same scores, keeps a cell where
`score > THRESHOLD` (the file's 1.0), and passes those cells through
`group_published_alerts`. Test labels are not passed into the candidate. Train
attack flags are passed, and on these editions every train row is benign.

Result names:

- `sandbox-candidate:own-grouping`
- `sandbox-candidate:shared-wrapper`

Comparison rows, quoted from ADR 0102 and not scored again:

| Corpus | Grouped Atlas | Grouped MinMax |
|---|---:|---:|
| hai-22.04 | 5/58 | 10/58 |
| hai-23.05 | 5/52 | 6/52 |

The command replays grouped MinMax's published cells through the shared wrapper
only to recover attack ids. If that replay's catch count is not 10 and 6, it
writes nothing. Headline recall uses the published counts.

Beyond grouped MinMax is the candidate's catches minus grouped MinMax's catches,
one number for each candidate row. Attacks only the candidate catches are the
attack ids in that row and not in the replayed grouped MinMax ids. Recall within
budget is the headline. Point-adjusted F1 is reported and is not the headline.
These editions are not labelled seen. Denominators stay 58 and 52.

This record does not contain a score. The command has not been run.

## Consequences

A candidate number for these editions appears only in the report that command
writes. Beating grouped MinMax, or failing to, is that report. It is not a
reason to edit Atlas.

## What would reverse this

Running the command before this record is committed, changing the candidate
file, or treating a grouped-Atlas comparison with an ungrouped opponent as this
result.

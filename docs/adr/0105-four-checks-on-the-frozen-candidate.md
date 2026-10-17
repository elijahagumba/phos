# ADR 0105 — Four checks on the frozen candidate, declared before they run

- **Status:** Accepted
- **Date:** 2026-10-10
- **PART:** v1, checks on the score in ADR 0104
- **Depends on:** [ADR 0103](0103-the-frozen-candidate-is-declared-on-clean-hai.md),
  [ADR 0104](0104-the-frozen-candidate-on-clean-hai.md)

## Context

ADR 0104 recorded one score of the frozen sandbox candidate: 53/58 on HAI 22.04
and 36/52 on HAI 23.05, own grouping and the shared wrapper the same, against
grouped MinMax at 10/58 and 6/52. These four checks ask what that score is. They
change no constant, no detector, and no published row. They do not append the
experiment log. They do not call `scripts/measure_candidate_look.py`.

## Decision

One command, after this record is committed, and not before:

`uv run python scripts/measure_candidate_checks.py`

It refuses to start if `eval_runs/v1/g1-candidate-checks.json` already exists.
It checks the sha256 of `experiments/2026-10-04-sandbox/candidate.py`, which
stays `7d485b7298282b6b369d55675804d3017e9f952d1353b5e673c84734720433d4`. It
aborts without writing if the candidate's own-grouping catch is not 53/58 and
36/52. Those two fractions stay the ADR 0104 headline. This command does not
replace them.

### 1. Chance null

On each edition, 500 draws. Seed `20261010`, `numpy.random.Generator` with
`PCG64`. Draw 0 through 499, and within a draw the test files in load order.
Each file's shifts are counted from its first timestamp in units of 8 hours,
the same cut as the candidate's `SHIFT_SECONDS`. Shifts are drawn in ascending
index order. Each shift contributes 8
distinct rows, drawn uniformly without replacement. A shorter shift contributes
every row. An attack is caught when a drawn row's timestamp falls inside its
interval, the same inclusive test as the headline. The draw's catch is the sum
across that edition's files. The report is the arithmetic mean, the 95th
percentile (`numpy.quantile`, method `linear`), and the maximum.

### 2. Drivers

Check 2 and check 4 share one fit per edition. The fit is the body of
`feature_scores`: `_calibrate_insample` when calibration is insample, `_fit`
when it is none, otherwise `_calibrate` and then `_fit`. Scores are
`_raw_scores` divided by that divisor. For each attack the own-grouping row
caught, the driver is the kept
alert inside that attack with the greatest event score. A tie takes the
earliest row, then the feature name. "Kept" is the alert `_keep_top` retains,
which is the alert the headline counts. At that row and feature, the range
score and the loop score are the two inputs of the frozen `_raw_scores` after
detrend when detrending is on, before the per-feature divisor. The larger one
is the component. Equal values are a tie. The combined score must equal
`maximum(loop, range)` divided by the divisor; a mismatch aborts the command.
The report is a count of caught attacks per feature. A feature is flagged when
its count divided by the attacks caught is strictly greater than 0.20. Its
meaning is quoted from `hai_dataset_technical_details.pdf` at pin `2a814ceb`,
and only from a sentence that PDF states. A column the PDF does not define is
reported as undefined there.

### 3. The two controls

Loaded from their files, not rewritten:

- `experiments/2026-10-04-sandbox/controls/minmax_events/candidate.py`, sha256
  `c9ff81dead9ff0154b83c276772d93149fad4e0b5f6b815fdd824c35321b5a0d`
- `experiments/2026-10-04-sandbox/controls/no_loop/candidate.py`, sha256
  `91d462d78d210fea8aac6f432f1019ffee6b4ce948e6895dc4cab6f5d516bd91`

Each is called once per edition through its own `_budget(_events(scores), time)`,
the body of its `run`. Those cells pass through the same `_score_detector` the
candidate's own-grouping row used. The headline is caught/attacks. Beyond
grouped MinMax uses the published 10/58 and 6/52. Point-adjusted F1 is reported
and is not the headline.

### 4. Whether the two ADR 0104 rows were independent

From the same fit as check 2, for each row and each file:

- events before the 8-per-shift cut
- alerts after that row's own cut
- alerts `_keep_top` then keeps
- the alert list point-adjusted F1 was computed from, which is the list passed
  to `_score_detector` (`_point_flags` reads that list, not the `_keep_top`
  subset)

Own grouping's cut is `_budget`. The shared wrapper's cut is
`group_published_alerts`. The two lists are the same when their `(row, feature)`
pairs match on every file. The command also records whether the timestamp sets
match, because point-adjusted F1 marks a row and ignores the feature. This
command does not start a corrected
shared-wrapper run. If the lists match, the result record says so. A corrected
run needs its own declaration, committed before it runs.

## Consequences

This record does not contain a score. The command has not been run.

## What would reverse this

Changing a constant, a detector, or a published row on the way to these counts,
or running the command twice.

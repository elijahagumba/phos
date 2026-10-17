# ADR 0106 — Four checks on the frozen candidate

- **Status:** Accepted
- **Date:** 2026-10-10
- **PART:** v1, the checks declared in ADR 0105
- **Depends on:** [ADR 0105](0105-four-checks-on-the-frozen-candidate.md)

## Context

ADR 0105 named the four checks and was committed before this run.
`scripts/measure_candidate_checks.py` then ran once. The candidate's own-grouping
catch stayed 53/58 and 36/52. No constant, detector, or published row changed.
The experiment log was not appended.

## Decision

### Chance null

500 draws, seed 20261010, 8 rows per 8-hour shift.

| Edition | Draws | Mean caught | 95th percentile | Max caught |
|---|---:|---:|---:|---:|
| hai-22.04 | 500 | 3.808 | 7 | 9 |
| hai-23.05 | 500 | 3.06 | 6 | 8 |

The candidate's 53 and 36 sit above every draw.

### Drivers

Caught attacks per feature. The component is the larger of the range score and
the loop score at the kept alert. One feature is flagged: `P1_PCV01D` on HAI
22.04, 11 of 53. In `hai_dataset_technical_details.pdf` at pin `2a814ceb`, point
list row 24, that tag is "Position command for the PCV01 valve." All 11 of those
alerts were loop, not range. No feature on HAI 23.05 is above one fifth of 36.

| Feature | Caught attacks | Range larger | Loop larger | Tie | Flagged |
|---|---:|---:|---:|---:|---|
| P1_PCV01D | 11 | 0 | 11 | 0 | yes |
| P1_FT03Z | 8 | 0 | 8 | 0 | |
| P3_LCV01D | 6 | 0 | 6 | 0 | |
| P1_LIT01 | 5 | 0 | 5 | 0 | |
| P1_LCV01D | 4 | 0 | 4 | 0 | |
| P2_AutoSD | 4 | 3 | 1 | 0 | |
| P1_B3005 | 3 | 0 | 3 | 0 | |
| P2_SCO | 3 | 3 | 0 | 0 | |
| P1_PP04 | 2 | 2 | 0 | 0 | |
| P1_B4005 | 1 | 0 | 1 | 0 | |
| P1_FCV01D | 1 | 0 | 1 | 0 | |
| P1_TIT02 | 1 | 0 | 1 | 0 | |
| P2_ManualSD | 1 | 1 | 0 | 0 | |
| P2_SIT01 | 1 | 0 | 1 | 0 | |
| P2_VT01 | 1 | 1 | 0 | 0 | |
| P3_LH01 | 1 | 0 | 1 | 0 | |

HAI 22.04, 53 attacks. HAI 23.05:

| Feature | Caught attacks | Range larger | Loop larger | Tie | Flagged |
|---|---:|---:|---:|---:|---|
| P1_FT03Z | 6 | 0 | 6 | 0 | |
| P1_PCV01D | 6 | 0 | 6 | 0 | |
| x1002_07_SETPOINT_OUT | 5 | 0 | 5 | 0 | |
| P1_PIT01 | 4 | 0 | 4 | 0 | |
| P1_FCV01D | 3 | 0 | 3 | 0 | |
| x1002_08_SETPOINT_OUT | 3 | 0 | 3 | 0 | |
| P2_SCO | 2 | 2 | 0 | 0 | |
| P2_VT01 | 2 | 2 | 0 | 0 | |
| P1_FCV02Z | 1 | 0 | 1 | 0 | |
| P1_LCV01Z | 1 | 0 | 1 | 0 | |
| P1_LIT01 | 1 | 0 | 1 | 0 | |
| P1_PCV01Z | 1 | 0 | 1 | 0 | |
| P1_PCV02D | 1 | 0 | 1 | 0 | |

### Controls

Each control file, byte for byte, once. Caught/attacks is the headline.

| Edition | Control | Caught/attacks | Beyond grouped MinMax | Point-adjusted F1 |
|---|---|---:|---:|---:|
| hai-22.04 | sandbox-control:minmax-events | 21/58 | 11 | 0.4618154585396108 |
| hai-22.04 | sandbox-control:no-loop | 21/58 | 11 | 0.4618154585396108 |
| hai-23.05 | sandbox-control:minmax-events | 15/52 | 9 | 0.5435215434667239 |
| hai-23.05 | sandbox-control:no-loop | 15/52 | 9 | 0.5435215434667239 |

On both editions the two controls return the same headline and the same
point-adjusted F1. Both sit above grouped MinMax and below the frozen candidate.

### Alert lists

The two ADR 0104 rows were separate computations. Point-adjusted F1 for each
row was computed from that row's own post-budget list. The second `_keep_top`
cut dropped nothing. The `(row, feature)` lists are not the same on either
edition, so this record does not declare a corrected shared-wrapper run.

| Edition | Row | Events before budget | Alerts after budget | Alerts kept | Point-adjusted F1 from |
|---|---|---:|---:|---:|---|
| hai-22.04 | sandbox-candidate:own-grouping | 83 | 101 | 101 | own-grouping budget output passed to _score_detector |
| hai-22.04 | sandbox-candidate:shared-wrapper | 83 | 83 | 83 | group_published_alerts output passed to _score_detector |
| hai-23.05 | sandbox-candidate:own-grouping | 85 | 73 | 73 | own-grouping budget output passed to _score_detector |
| hai-23.05 | sandbox-candidate:shared-wrapper | 85 | 73 | 73 | group_published_alerts output passed to _score_detector |

On HAI 22.04 the timestamp sets differ as well. On HAI 23.05 the timestamp sets
match and the features do not. Own grouping's extra alerts on HAI 22.04 are the
spare second alerts: 101 after the budget, against 83 events.

## Consequences

The four checks are recorded. Nothing was retuned.

## What would reverse this

Replacing one of these counts, or changing a detector or a constant because of
them.

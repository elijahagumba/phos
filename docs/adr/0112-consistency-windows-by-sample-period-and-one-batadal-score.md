# ADR 0112 — One rule for the consistency detector's windows by sample period, and one BATADAL score, declared before it runs

- **Status:** Accepted
- **Date:** 2026-10-12
- **PART:** v1, handover step 1 (BATADAL); roadmap §2.0 and A6
- **Depends on:** [ADR 0095](0095-g1-baseline-table.md),
  [ADR 0100](0100-grouped-g1-rows-and-where-atlas-loses.md),
  [ADR 0107](0107-the-consistency-detector-enters-the-engine.md),
  [ADR 0111](0111-the-port-reproduces-the-scored-list-on-real-hai.md)

## Context

`atlas-v1-consistency` counts its windows in samples: lags of 5, 15, 30 and 60, a fit stride of
5, an hour's detrending (3600, sampled every 60), episode gaps of 60, events chaining within 300
and spanning 600, and a second alert at least 30 from its onset. It was developed and scored on
HAI, where a sample is one second. BATADAL's samples are one hour apart (declared 3600 s in
`scripts/measure_baseline_table.py`, measured the same in ADR 0100). Its test file is 4,177 hourly
rows, about 174 days, with five labelled attacks.

Read literally on BATADAL, the frozen windows mean other things: lags of up to 60 hours, events
chaining across 12.5 days and spanning 25, and a 150-day detrend. Roadmap §2.0 allows a per-corpus
value only when it comes from a rule declared before measurement, for example from the sample
rate. The handover asked for that rule before any BATADAL score.

The rule below was chosen from the windows' meaning on HAI and from BATADAL's declared period,
its row count and its column header. No BATADAL score by this detector exists. None was computed
on the way to this record.

## Decision

### The rule, for every corpus

Each frozen window is read as that many **seconds**, because that is what it was on the corpus
it was developed on. For a corpus whose samples are `p` seconds apart, a window of `s` seconds
becomes `max(1, floor(s / p + 0.5))` samples: rounded half up, and never below one sample,
because a zero-sample window switches its mechanism off (a zero detrend step divides by zero; a
zero second-alert separation puts a second alert on the onset row). Lag 0 stays 0. Lags that land
on the same sample are kept once, in order. Nothing else changes: thresholds, the ridge penalty,
the residual quantile, the range weight, the onset rule, the calibration rank, the 8-hour shift
and the 8 alerts in it are the frozen values on every corpus.

`phos.atlas.consistency_windows.windows_for_period` is the rule. At `p = 1` it returns the frozen
windows exactly, so nothing scored on HAI can move (`tests/atlas/test_consistency_windows.py`). A
fitted model keeps its windows, so a file is always scored with the windows it was fit with.

At BATADAL's 3600 s:

| Window | Frozen (HAI, samples = seconds) | BATADAL (hourly samples) |
| --- | --- | ---: |
| Lags | 0, 5, 15, 30, 60 | 0, 1 |
| Fit stride | 5 | 1 |
| Detrend window, step | 3600, 60 | 1, 1 |
| Episode gap | 60 | 1 |
| Event window, span | 300, 600 | 1, 1 |
| Second-alert separation | 30 | 1 |

So on BATADAL each signal is predicted from the others now and one hour earlier; each score is
detrended against the previous hour's; and an event is the departures that begin within the same
hour or the next. Each of those is the frozen detector's meaning at the coarsest resolution
BATADAL has.

### One score

One command, after this record is committed, and not before:

`uv run python scripts/measure_consistency_batadal.py`

It refuses to start if `eval_runs/v1/consistency-batadal.json` exists. It reads
`data/batadal/batadal-train-prepared.csv` and `batadal-test-prepared.csv` with the G1 reader
(`_read_prepared`, no unscored label), exactly as ADR 0100 did. It aborts and writes nothing if the
measured period is not 3600 s, if grouped MinMax replayed on the same split does not catch its
published 3/5, or if the denominator is not 5. It fits once on the training file with
`windows_for_period(3600)`, scores the test file once, and keeps alerts with the detector's own
events and budget. `_score_detector` scores the kept alerts.

**Headline.** Recall within budget, 8 alerts per 8-hour shift, against the best grouped checked
opponent: grouped MinMax, 3/5 (ADR 0100). A2 asks for strictly higher, so 4/5 or 5/5 wins
BATADAL. Grouped Steadytime and Histogram (2/5 each) and grouped G1 Atlas (Mahalanobis, 5/5) are
reported beside it, all ADR 0100's published counts, not scored again. eTaPR at the reference
defaults and at HAICon's parameters, and point-adjusted F1, are reported and are not the headline.
HAICon's 180-sample tail is 180 hours here, as in the published rows; it is not rescaled (ADR 0095).

**Two things to keep beside the number.** With five attacks, one attack is twenty points of
recall. And on hourly rows the budget is one alert per sample, so it constrains little; that is
true of every row on this corpus, including the opponents'.

## Consequences

BATADAL becomes seen by this detector. A later record reports A2's status across the five
judging corpora with every seen corpus marked. This record does not edit the G1 table, the frozen
rows, priors or `EVIDENCE_STRENGTH`, and appends no log row. Any later change to the rule is a
new rule with a new name, scored beside this one.

## What would reverse this

Running the command twice; changing the rule, a constant, or the reader after seeing the score; or
reporting a corpus-specific window that the rule does not produce.

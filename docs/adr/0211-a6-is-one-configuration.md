# ADR 0211 — A6 holds: the per-corpus differences are the declared sample-period rule

- **Status:** Accepted
- **Date:** 2026-10-19
- **PART:** v1 sprint, lane A, criterion A6
- **Depends on:** [ADR 0095](0095-g1-baseline-table.md),
  [ADR 0112](0112-consistency-windows-by-sample-period-and-one-batadal-score.md),
  [ADR 0210](0210-the-g1-table-reprints-its-validation-rows.md)

## Context

A6 asks that every v1 number come from a single configuration, with no parameter
differing between corpora. A value derived by a rule declared before measurement,
for example from the sample rate, is one configuration. A value chosen by looking
is not. This is an audit of the parameters already on disk. It does not rescore
a validation corpus and it does not change a detector.

## Decision

A6 is met. The audit is `eval_runs/build/v1/atlas/a6-parameters.md`.

The G1 Mahalanobis threshold is 3.0, the shift is 8 hours, the budget is 8
alerts, the HAICon tail is 180 samples, and the three opponents keep their
published defaults, on every corpus. The consistency constants (ridge, residual
quantile, range weight, threshold, onset, calibration rank, 8 alerts, 8-hour
shift) are the frozen champion's, on every corpus where that champion is a v1
number.

BATADAL's windows are `windows_for_period` applied to its declared sample period
of 3600 s. That is one rule, declared in ADR 0112 before the BATADAL consistency
score, not a per-corpus setting. At 1 s the same function returns the frozen HAI
windows, which is what hai-20.07, hai-21.03, hai-22.04 and hai-23.05 use.

The file readers differ because the published layouts differ. Each reader was
declared before the score that used it (ADR 0095, ADR 0082, ADR 0101). HAI
23.05's labels are joined by row because the label timestamps do not match the
series. That join was written in ADR 0101 before the clean run.

## Consequences

No knob moves. A later score that introduces a per-corpus threshold, fit window,
or eTaPR delta would be a different configuration, and A6 would no longer hold.

## What would reverse this

Finding a parameter that differs between corpora and was chosen by looking,
rather than by the sample-period rule or by a reader declared before measurement.

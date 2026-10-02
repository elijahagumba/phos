# ADR 0003 — Recall is window-level; false positives are per hour of normal operation

- **Status:** Accepted
- **Date:** 2026-07-28
- **PART:** 2 — Evaluation Harness & Dataset Adapters

## Context

Constitution §3.5 says nothing in PHOS is trusted until it has been measured, and every engine —
Atlas, Sentiel, Intelligence — is scored by this one harness so their numbers stay comparable.
That makes the metric definitions load-bearing in a way the metric *code* is not: the code can be
optimised freely, but changing what "recall" means retroactively invalidates every line already
written to `eval_runs/log.jsonl`. So the definitions are fixed here, before any real detector
exists to be flattered by them.

Two further invariants constrain the choice. §3.3 requires confidence to be calibrated before it
is surfaced, which is only enforceable if calibration is measurable. §3.7 requires reproducibility,
which means every number must carry the settings that produced it.

The naive definitions — per-sample recall, false positives as a fraction of alerts — are the ones
most anomaly-detection papers report, and both mislead in exactly the setting PHOS targets.

## Decision

**1. Recall is window-level. An attack is caught if *any* alert lands in its labelled window.**
`window_recall(detections, intervals, tolerance)` returns detected windows over total windows.

A detector that fires once on a thirty-minute intrusion has caught that intrusion; an analyst
investigates and the incident is over. Per-sample recall scores that same detector in the low
single digits and would lead us to discard a working detector in favour of a chattier one.
`recall_sample` is still computed and reported, because the *gap* between the two numbers is
itself informative — it says how continuously a detector fires inside an incident — but window
recall is the headline and the one the sweep is indexed on.

**2. False positives are normalised per hour of normal operation.**
`false_positive_rate` = alerts falling in no attack window ÷ `Dataset.normal_duration()` in hours.

Not per sample, and not as a fraction of alerts. An analyst lives in wall-clock time, and "three
false alarms a shift" is the number that decides whether a system stays switched on. Per-sample
rates are unreadable (a 1 Hz corpus and a 1/60 Hz corpus produce incomparable numbers for
identical behaviour), and precision hides the sampling rate entirely.

The denominator excludes labelled attack time, computed by clamping each attack interval to the
corpus span, merging overlaps, and subtracting. Merging matters: overlapping labels would
otherwise be subtracted twice, shrinking the denominator and *inflating* the reported FP rate.
Excluding attack time matters because a corpus that is mostly attack — which testbed corpora often
are — would otherwise hand a noisy detector a flattering denominator it did not earn.

**3. `tolerance` is applied consistently, through one shared predicate.**
Labelled window boundaries are imprecise, so alerts near an edge are forgiven by widening the
window. Every metric that classifies an alert routes through the same `_is_true_positive` helper,
so an alert forgiven *into* a window as a true positive can never also be charged as a false
positive. Two independent tolerance implementations would drift, and the resulting recall and FP
rate would silently describe different alert sets.

**4. Detection latency counts only alerts strictly inside a window.**
An alert that matched only because of `tolerance` preceded the attack, and "time to detect" is not
a meaningful quantity for it. Excluding it keeps every latency non-negative. The returned list has
one entry per *detected* window, so it is shorter than `intervals` whenever recall is below 1 —
latency is deliberately not averaged over windows that were never caught.

**5. Calibration is measured here and fitted nowhere.**
`reliability_table`, `expected_calibration_error` and `brier_score` make §3.3 testable: a detector
claiming 90% should be right about 90% of the time in the `[0.9, 1.0]` bin. ECE is weighted by bin
population so one wild claim made once cannot dominate. Brier is reported alongside because ECE
alone rewards hedging — answering 0.5 to everything is perfectly calibrated on a balanced corpus
and tells an analyst nothing. Fitting calibrators is PART 4; until then `Detection.confidence` is a
normalised score and must not reach a user.

**6. The number that decides adoption is the sweep, not any single operating point.**
`threshold_sweep` returns recall, FP rate and precision at each threshold, which answers *how many
false alarms per hour does it cost to catch 90% of incidents?* A single threshold cannot. Recall
and FP rate are non-increasing as the threshold rises — raising it can only shrink the alert set —
and this is asserted across the sweep rather than assumed. Precision is not monotone and is not
expected to be.

**7. Degenerate cases resolve pessimistically.**
Every ratio here has a denominator that can be zero, and in each case the harness reports the
answer that cannot be mistaken for success. See the table below.

## Consequences

- Numbers from this harness are comparable across corpora with different sampling rates, and
  across engines, which is the entire point of having one ruler.
- A detector cannot win by firing continuously: window recall saturates at 1.0 while the FP rate
  keeps climbing, so the sweep exposes the trade rather than hiding it.
- The metric definitions are now part of the public contract. Changing one is a new ADR *and*
  invalidates prior log lines; the log records the commit precisely so that stale lines can be
  identified rather than silently re-interpreted.
- `metrics.py` is pure — values in, numbers out, no disk, no state, no knowledge of what a detector
  is. That is what lets every expected value in `tests/eval/test_metrics.py` be hand-computed in a
  comment next to its assertion, which is the only real defence against a plausible-looking metric
  bug.

## Ambiguities resolved in this PART

| Question | Decision | Why |
| --- | --- | --- |
| `window_recall` on a corpus with **no** attack windows | Return `0.0`. | A vacuous `1.0` would let a detector claim perfect recall on a corpus that never tested it — and that corpus is exactly the one used for FP measurement. |
| `false_positive_rate` when there is **no normal time** | `0.0` if there were no false positives, `inf` if there were. | There is no normal time to amortise them over. Reporting `inf` is honest; inventing a denominator is not. `EvaluationReport` sets `ser_json_inf_nan="constants"` so this still round-trips through JSON. |
| `precision` on an **empty** alert set | Return `0.0`. | Firing nothing is not perfect precision. |
| `recall_sample` with no attack-labelled observations | Return `0.0`. | Same reasoning as window recall. |
| `f1` when precision and recall are both zero | Return `0.0`, not a `ZeroDivisionError`. | The harness must be able to score a detector that found nothing without raising. |
| Which alerts count for latency | Only those strictly inside the window, ignoring `tolerance`. | Keeps latency non-negative and meaningful; see decision 4. |
| Confidence of exactly `1.0` in the reliability table | Falls in the **last** bin, not a phantom `n_bins + 1`th. | `min(int(c * n_bins), n_bins - 1)`. The table always has exactly `n_bins` rows and can be plotted directly. |
| Unpopulated reliability bins | Emitted with `count=0` and zero statistics; excluded from ECE. | The table is a plottable curve, so gaps must be visible rather than dropped. Weighting by count excludes them from ECE automatically. |
| `threshold_sweep`'s parameters | Takes `dataset` only; the spec's separate `intervals` parameter was dropped. | Two sources of ground truth that can disagree is a bug waiting to happen. Intervals come from `dataset.attack_intervals`. |
| Sweep threshold selection | Quantiles of the observed score distribution, de-duplicated. | An even split of the score range is mostly empty when scores are skewed, and anomaly scores always are. De-duplication means a detector emitting one distinct score yields one operating point, not eleven identical ones. |
| Spec's `Bin` type name | Renamed `ReliabilityBin`. | `Bin` is too generic for a name re-exported at package level. |
| Where the git commit is captured | At the I/O edge, in `append_to_experiment_log`, not in `evaluate`. | Keeps `evaluate` pure and deterministic; shelling out to `git` inside the scoring function would make it neither. |

## Alternatives considered

- **Per-sample recall as the headline.** Rejected: penalises a detector for the sin of not being
  redundant, and is the single most common way a usable OT detector is discarded on paper.
- **Precision/recall/F1 alone.** Rejected: precision is a function of the alert base rate, so it
  moves when the corpus's attack proportion changes even though detector behaviour has not. It is
  still reported, because it is what the literature reports and comparisons need it, but it is not
  the adoption number.
- **ROC / AUC.** Rejected as the headline: AUC integrates over operating points nobody would ever
  run, and on the extreme class imbalance of real OT telemetry it looks excellent while the
  detector is unusable. The sweep gives the same information restricted to the region that matters.
- **A fixed global threshold across detectors.** Rejected: anomaly scores are detector-specific and
  unbounded, which is exactly why the harness sweeps rather than comparing raw scores.

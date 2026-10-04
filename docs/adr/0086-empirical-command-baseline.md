# ADR 0086 — An empirical quantile band for command behaviour

- **Status:** Accepted
- **Date:** 2026-10-02
- **PART:** public pre-release
- **Supersedes:** the disposition of the recurring command-interval false alarm recorded in
  [ADR 0085](0085-phos-demo-runs-one-incident-end-to-end-and-names-its-misses.md). The demo, the
  choice of incident, and the never-seen-device prior finding in that record stand.
- **Depends on:** [ADR 0005](0005-fit-score-separation-per-key-baselines-and-attack-free-splits.md),
  [ADR 0085](0085-phos-demo-runs-one-incident-end-to-end-and-names-its-misses.md)

## Context

`phos demo` fits a command-behaviour baseline on a 120-hour water-plant capture and then watches a
short live run. ADR 0085 found that the Gaussian baseline raises a false alarm on ordinary
operation: features such as `command_interval_mean_ms` pile up on a few exact values, and a band of
mean ± 3 standard deviations can exclude a pile that occurs often enough to be ordinary. On the
seed-11 fit, the SCADA server's mean command interval is exactly 15 s in 36 of 7,197 one-minute
windows, and the fitted band (mean + 3 standard deviations = 13.15 s) excludes it.
`command_interval_cv` can do the same. `IqrBaseline` is the wrong repair: when a count is nearly
always one integer, the quartiles coincide and Tukey's fence collapses onto that integer.

The Gaussian model still produces the frozen public rows. This record adds a separately named
model. It does not retune `templates.py` priors or `EVIDENCE_STRENGTH`.

## Decision

**1. `EmpiricalBaseline` learns a per-key quantile band at the tail a Gaussian `band_k` band
claims.** The tail is `one_sided_gaussian_tail(band_k) = 0.5 * erfc(band_k / sqrt(2))`. At the
default `band_k` of 3 that is approximately **0.00135** on each side — the standard-normal
probability of exceeding three standard deviations. The number is inherited from the Gaussian
claim already in the tree. It was not searched against a false-alarm count.

The quantiles use `numpy.quantile(..., method="inverted_cdf")`, the empirical quantile function,
with no interpolation between order statistics. A pile thicker than the tail therefore lands on
the pile. `mean` and population `stddev` (`ddof=0`) are stored on the same `ExpectedRange`.
Inside the band the magnitude is 0. Outside it, the magnitude is the absolute z-score. A fit with
no spread (`stddev == 0`) makes any departure `MAX_MAGNITUDE`.

**2. The demo fits this model on command features.** `demo_command_baseline()` returns
`EmpiricalBaseline`. The `phos demo` command does not expose a switch. `GaussianBaseline` remains
the model the frozen-row scripts fit.

**3. Two figures, each with its own name.** Neither is appended to `eval_runs/log.jsonl`.
Command-lead **0/16** and **1/4** stay frozen and unpooled.

`empirical-command-baseline:operator-false-alarms` counts narratives on the demo's `operator`
scenario (an authorised write) that do not concern that write. Silence is 0.

`empirical-command-baseline:unauthorised-concerns-write` counts runs of the `unauthorised`
scenario whose shown brief concerns the real write: a cited fact about the writing device, or
the link, in the minute of the write.

## Consequences

**What the band does to the discrete pile.** On a hand-built sample of 1,000 values at 10 and 10
values at 15, the empirical high is 15 and the Gaussian high is about 11.5, so 15 is inside one
band and outside the other. On a sample that is 10 fives and 1,000 sixes, the IQR fence is the
point 6 and a five scores `MAX_MAGNITUDE`; the empirical band is [5, 6] and the five scores 0.
Those two comparisons are unit tests. They are why this model exists and why IQR is not used here.

**Ordinary runs, twenty seeds, fixed before the measurement.** Seeds 11 through 30. Seed 11 is
the one ADR 0085 already named; 12 through 30 are the next integers. Reproduction:
`uv run python scripts/measure_empirical_command_baseline.py`. Report:
`eval_runs/sandbox/adr0086-empirical-command-baseline/measurement.md`.

| | Narratives | Per run | Runs with at least one |
| --- | ---: | ---: | ---: |
| Gaussian | 15 | 0.75 | 10 of 20 |
| Empirical | 4 | 0.20 | 4 of 20 |

No shown narrative concerned the authorised write. The drop is the discrete-interval and
integer-count alarms leaving. It is a plant we simulated.

**Unauthorised writes, the same twenty seeds.** The SCADA server writes a setpoint only the HMI
may write. A hit is a shown brief that concerns that write. Reproduction:
`uv run python scripts/measure_empirical_command_baseline.py --figure detection`. Report:
`eval_runs/sandbox/adr0086-empirical-command-baseline/detection.md`.

| | Briefs that concern the write | Silent |
| --- | ---: | ---: |
| Gaussian | 19 of 20 | 0 |
| Empirical | 20 of 20 | 0 |

The empirical model does not see the write less often. It sees it on every seed. The Gaussian
model misses seed 22: that run raises a brief, and the brief does not concern the write. No run
under either model stayed silent.

**Seed 11 did not go to silence.** The Gaussian incident is the 15.0 s mean interval against a
band printed as 1.6 s to 13.2 s. The empirical incident is `command_interval_cv` 0.998692 against
a band of 0.999031 to 1.99922. On that fit the coefficient of variation has 7,197 windows and
5,150 distinct values; three training windows sit below the live value (fraction 0.00042), which
is inside the inherited 0.00135 tail, and the value sits inside the Gaussian three-sigma band.
The full narrative path therefore still raises one false alarm on seed 11, about a different
fact. The tail was not widened to remove it.

The other three empirical incidents are seed 18 (a coefficient of variation the Gaussian run left
silent), seed 26 (a coefficient of variation both models raised), and seed 27 (a mean interval
whose printed sentence rounds both the value and the band edge to 15.0 s; the demo prints one
decimal, and the stored value is outside the inclusive quantile).

**Unchanged.** Template priors, `EVIDENCE_STRENGTH`, known-station **0/16**, unknown-master
**1/4**, and every frozen log name. `src/phos/models/gaussian.py` is byte-identical to the
PART 6B tree. The Sentiel reuse pin names the two files this record opens —
`empirical.py` and `models/__init__.py` — and leaves the rest of the package frozen. This session did not recompute the never-seen-device
posterior ADR 0085 recorded; the priors that posterior was built from were not edited. Hypothesis
confidence stays uncalibrated and is not printed.

## What would reopen this

A labelled public command corpus, or a partner capture, on which the inherited tail is the wrong
description of ordinary command intervals. Searching the tail against these twenty seeds would
reopen it for the wrong reason.

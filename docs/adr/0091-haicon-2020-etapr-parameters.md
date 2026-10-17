# ADR 0091 — HAICon 2020's eTaPR parameters, beside the reference defaults

- **Status:** Accepted
- **Date:** 2026-10-04
- **PART:** v1 roadmap week 1, scoring settings
- **Depends on:** [ADR 0088](0088-etapr-and-shift-budget-recall.md)

## Context

Roadmap §2 is frozen at `93156a51d4cd2e2be5684ca817306d2db07c0be7`. This record does not
edit §2. §2.0 says eTaPR is reported with the parameters HAICon used, recorded in their own
ADR before any Atlas-versus-opponent number exists, beside the reference defaults (ADR
0088). No such number exists yet. ADR 0088's sentence that eight alerts per shift is still
a draft is the state before that freeze. The freeze came after.

Shin, Lee, Yun and Min, "Two ICS Security Datasets and an Anomaly Detection Contest on HAI
Datasets", CSET 2021, §4.1.2:

> In the eTaPR Python package, we set the parameter values to α = 0.5, ρ = 0.1, π = 0.7,
> and δ = 180 in consideration of the characteristics of the competition dataset. These
> values are not allowed to change.

HAICon 2020 scored the raw version of HAI 21.03. The wheel this project checked, eTaPR
22.6.1, is later than that contest. It still contains two scorers.

`evaluate_w_ranges(theta_p, theta_r, delta)` asserts each argument is in `[0, 1]`. Its
command-line default is `theta_p=0.5`, `theta_r=0.1`, `delta=0.0`. That is ADR 0088's
reference. `evaluate_w_streams` defaults `theta_p` to 0.7 and `theta_r` to 0.1, which are
π and ρ, and still defaults `delta` to 0.0. The mix of detection and portion is hardcoded
`(detection + detection * portion) / 2`. There is no `alpha` argument.

The older `tapr.compute(anomalies, predictions, alpha, theta, delta: int)` in the same
wheel takes α, one shared θ, and an integer sample count. Its command-line default is
`alpha=0.8`, `theta=0.5`, `delta=600`, which is not the contest. Passing 180 to
`evaluate_w_ranges` raises `AssertionError`. Passing it to `etapr` raises `ValueError`.

The contest wheel's `evaluate_haicon` (the name in the HAICon 2021 rules, package
`eTaPR-21.8.2`) is not in the 22.6.1 tree and was not retrieved. The four numbers below
are the CSET paragraph, not a guess at that function's body.

## Decision

Two named records live in `phos.eval.etapr` and are re-exported from `phos.eval.metrics`.

**`REFERENCE_ETAPR`**, name `reference-22.6.1`: `theta_p=0.5`, `theta_r=0.1`, `delta=0.0`.
`etapr_at` scores with an `EtaprSetting`. The ADR 0088 hand case is unchanged: eTaR 0.425,
eTaP 0.35860968734610654, F1 0.38899242718212823.

**`HAICON_2020`**, name `haicon-2020`: `theta_p=0.7` (π), `theta_r=0.1` (ρ), `alpha=0.5`
(α), `ambiguous_samples=180` (δ). It is not an `EtaprSetting`. `alpha` is not an argument
of `etapr`. `ambiguous_samples` is not a fractional `delta`, and `etapr(..., delta=180)`
is rejected.

A call that uses π and ρ with fractional `delta=0` is a legal `etapr` call and is not the
HAICon score, because δ is missing. The hand case from ADR 0088 does not even separate
`theta_p` 0.5 from 0.7. A case that does, anomaly `(0, 19)`, predictions `(0, 9)` and
`(14, 23)`, `theta_r=0.1`, `delta=0`, checked against 22.6.1 `evaluate_w_ranges`:

| `theta_p` | eTaR | eTaP | F1 |
|---|---|---|---|
| 0.5 (reference) | 0.9 | 0.9000000000000001 | 0.9 |
| 0.7 (HAICon π) | 0.75 | 0.5 | 0.6 |

At 0.7 the parts are eTaRd 1.0, eTaRp 0.5, eTaPd 0.5, eTaPp 0.5. The second prediction's
overlap ratio is 0.6, so 0.5 keeps it and 0.7 prunes it.

No Atlas-versus-opponent number is computed here. No frozen row moves. Nothing is appended
to `eval_runs/log.jsonl`. The wheel is still not a dependency.

## Consequences

A later comparison that says "eTaPR" has to name the setting. `reference-22.6.1` is the
ADR 0088 default. `haicon-2020` is the four contest numbers. Reporting HAICon eTaPR by
calling `etapr` at `delta=0` drops δ and must not be labelled as the contest score. Integer
δ is the older TaPR tail, a fixed sample count added after the anomaly, not
`int(delta * (end - start))`. Implementing that tail would be a new function. It is not
this record, and it is not required to stop an Atlas number: this record is what §2.0
asked to land first, and no Atlas number is in it.

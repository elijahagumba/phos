# ADR 0088 — eTaPR and shift-budget recall are metrics, not a pass mark

- **Status:** Accepted
- **Date:** 2026-10-04
- **PART:** v1 roadmap week 1, step 2
- **Depends on:** [ADR 0003](0003-eval-harness-and-metric-definitions.md)

## Context

Week 1 of `docs/v1-roadmap.md` asks for two scores the existing harness does not compute:
enhanced time-series aware precision and recall (eTaPR; Hwang, Yun, Kim and Min, SAC 2022,
DOI 10.1145/3477314.3507024), and recall when an operator may read only a fixed number of
alerts in an eight-hour shift. Roadmap §2's eight alerts per shift is still a draft. It is
not a default and not a gate.

The reference implementation is the wheel `eTaPR-22.6.1-py3-none-any.whl` on
`wshw4ng/eTaPR` `main` (the `saurf4ng/eTaPR` raw URL returns 404). It is not a project
dependency. The check was a separate interpreter with a stub in place of `cv2`, which that
wheel imports at import time and which the scoring path does not use.

## Decision

**1. eTaPR lives in `phos.eval.etapr` and is re-exported from `phos.eval.metrics`.** Ranges
are inclusive integer indexes. `theta_p` and `theta_r` are required. `delta` defaults to 0,
the reference default. `delta` is a fraction of `end - start`, in `[0, 1]`. It is not the
integer delta of the earlier TaPR package, and it is not HAICon's 180.

The arithmetic follows `evaluate_w_ranges` in 22.6.1, including the sharp edges:

- Anomalies are sorted by `(start, end)` before the ambiguous tail is attached.
- The tail starts at `end + 1` and has length `int(delta * (end - start))`, clipped before
  the next anomaly. A tail whose start is not strictly before its end is ignored, so a
  one-point tail scores nothing.
- Overlap inside the anomaly is its length. Overlap in the tail is the logistic decay the
  reference uses (the index mapped onto `[-6, 6]`).
- Pruning zeros an anomaly whose overlap ratio is strictly between 0 and `theta_r`, and a
  prediction whose ratio is strictly between 0 and `theta_p`. An exact zero is left alone.
  The pass repeats until nothing moves.
- Prediction weight is the square root of the prediction's length. The prediction portion
  is not capped at 1. The anomaly portion is.
- An empty anomaly list or an empty prediction list returns zeros. The reference returns
  NaN or raises. A trial with nothing to score is a zero here.

**2. `recall_within_budget` keeps the top `alerts_per_shift` alerts in each half-open shift
and then calls `window_recall`.** The shift defaults to `OPERATOR_SHIFT`, eight hours. The
origin is the first observation, or the earliest alert when there are no observations. An
alert on a boundary belongs to the later shift. Ties break on timestamp, then on the
original index. Every alert spends a slot, including time that is not an attack. The alert
count has no default. Eight is not wired in.

**3. Neither function writes `eval_runs/log.jsonl`, and neither is applied to a frozen
row.** No detector, prior, or `EVIDENCE_STRENGTH` changes in this step. Roadmap §2 is not
applied.

## Check

Against eTaPR 22.6.1, anomalies `(0, 9)` and `(30, 34)`, predictions `(2, 8)`, `(32, 40)`
and `(50, 52)`, `theta_p=0.5`, `theta_r=0.1`, `delta=0`:

| | reference | this code |
|---|---|---|
| eTaR | 0.425 | 0.425 |
| eTaP | 0.35860968734610654 | same |
| F1 | 0.38899242718212823 | same |

A second case, anomaly `(0, 9)` and predictions `(10, 12)`, `(0, 4)`, same thresholds:
`delta=0` gives eTaR 0.75 and eTaP 0.5635083268962916; `delta=0.5` gives eTaR
0.8725050751832899 and eTaP 0.9599956475496451. Perfect cover scores 1. A total miss scores
0. The shift-budget tests use the existing one-hour fixture: budget 1 keeps a miss (recall
0), budget 2 keeps the first window (recall 1/3), budget 5 keeps the unbudgeted 2/3.

## Consequences

A later comparison can call these functions. It cannot treat a particular `alerts_per_shift`
as the v1 pass until §2 is frozen by commit. Adding the wheel to `pyproject.toml` would pull
`opencv` in through an import the score does not need; the pin is the hand-built case, not
the wheel.

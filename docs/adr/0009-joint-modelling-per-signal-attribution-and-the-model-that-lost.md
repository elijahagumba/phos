# ADR 0009 — Modelling the plant as one machine, attributing what breaks, and the model that lost

- **Status:** Accepted
- **Date:** 2026-08-03
- **PART:** 5A

## Context

PART 3 gave PHOS three behavioural baselines, each learning one `ExpectedRange` per
`(entity, feature)` and judging every reading alone. Measured on real industrial telemetry that
approach failed, and failed in a way no threshold could fix: on HAI's seventy-nine-signal corpus the
Gaussian baseline posts **8,390 false positives per normal hour**. An operator would see one alarm
every four-tenths of a second.

The cause is structural. Modelling seventy-nine signals as seventy-nine strangers means that when
demand rises — an entirely ordinary event — every demand-driven signal rises with it, and a
per-signal baseline raises one alarm per signal for one non-event. The alarms compound with the
width of the plant, which is why BATADAL's forty-three signals at 0.06 FP/normal-hour looked
tolerable and HAI's seventy-nine did not.

But industrial signals were never independent. A pump's flow follows a valve's position; a tank's
level follows its inflow and outflow. Normal operation occupies a thin, low-dimensional manifold
inside the space of possible readings. Atlas's central modelling claim is that the right question
about a moment is not "is this signal high?" but "does this combination still lie on the manifold?".
5A builds that and measures it.

## Decision

**1. Correlation-aware modelling is Atlas's stance, and the interface was widened to admit it.**

`BehaviouralModel` was PART 3's contract *and* its per-key implementation in one class: `fit` was
concrete, grouped observations by `(entity, feature)`, and delegated statistics to an abstract
`_learn`. A joint model cannot be expressed that way at all — PCA needs the whole matrix, not one
group at a time — so the contract was extracted from the strategy. `BehaviouralModel` is now `fit`
and nothing else; `PerKeyBehaviouralModel` carries the grouping the three baselines share and is
their new base class. Nothing else changed: no caller referenced the removed behaviour, and
`ModelDetector`, `CalibratedModelDetector` and the PART 2 harness score a joint model with no
modification whatsoever.

That was the alternative to giving Atlas its own model interface, which would have meant its own
detector, its own harness adapter and, before long, its own alert format — the thing Constitution
§3.1 exists to prevent.

**2. Vectorising is isolated, and its missing-data policy is stated rather than assumed.**

`phos.atlas.vectorise` is the only place ontology observations become a matrix. It exists as its own
module because the reshape forces one judgement call — what to do about a signal with no reading at
some timestamp — and the tempting answer, a zero, fabricates a measurement. Everything the joint
model learned afterwards would be partly learned from fiction.

The policy: carry the last reading forward for at most `forward_fill_rows` rows, otherwise drop the
whole timestamp, and never substitute a value that was neither measured nor carried. Counted in rows
rather than seconds so it means the same thing on BATADAL's hourly readings and HAI's ten-second
ones.

A carried cell is marked `NO_OBSERVATION` in `source_index`, and **a carried cell can never raise a
`Deviation`**. It may inform the reconstruction of the rest of the plant — that is why it is carried
— but there is no measurement at that instant for a deviation to point back to, and inventing one
would break §3.2 silently.

**3. Attribution is a conditional expectation, which is what keeps a joint model explainable.**

A joint anomaly score is naturally a scalar: this moment is unusual. Emitting that would be a black
box. Instead both models answer two questions per signal per moment — what did the rest of the plant
imply this should read, and how far does a reading normally sit from that — and everything after
those two answers is shared code. The result is an ordinary `Deviation` whose `ExpectedRange` is
**dynamic**: centred on the implied value, half-width `band_k` times the learned departure spread.

"Given everything else, the outlet flow should have read 140.2 ± 0.6; it read 100.0" is a sentence
with a defensible number in it, and it survives every existing mechanism unchanged — 4A's
`is_out_of_band` compares value against bounds exactly as before, and `evidence_from_deviation`
accepts an Atlas deviation with no special case written for it.

The stored `expected_ranges` hold the per-signal band on *departure from the joint structure*,
centred on zero. That is genuinely the baseline each reading is judged against, so `resolve_range`
keeps its documented meaning. `feature_ranges` is always empty: the cross-entity fallback has no
analogue here, because there is nothing in a learned subspace to reconstruct a signal the subspace
does not contain.

**4. A fitted model is stored parameters, not a live estimator.**

Both fitted types are frozen Pydantic models holding plain floats — means, scales, the principal
basis, the precision matrix — so a score reproduces from the record rather than by re-running a fit,
and a model can reach the API in PART 8 without pickling anything. scikit-learn fits the PCA basis
and nothing else; no estimator object outlives `_principal_components`. This is the arrangement PART
4A adopted for the calibrators, followed deliberately.

**5. Two signals the models decline to learn, and one of them is a real gap.**

A signal absent from training is outside the `SignalSpace` and is ignored at score time — unknown is
not anomalous. A signal that never *varied* in training is also excluded, and that one is a
concession rather than a principle: a constant has no correlation, so it can neither inform a
reconstruction nor be reconstructed from one. A signal constant for a week that moves today is
interesting, and a joint model structurally cannot notice.

Measured, the concession is small: 21 of HAI's 79 signals are constant in training, and exactly one
of them ever moves in test, on 5 rows of 4,321. The false-positive reduction below is therefore
attributable to correlation modelling and not to quietly discarding signals. 5B and 5C should decide
whether a per-signal guard belongs beside the joint model; 5A does not close it.

**6. Near-singular covariance is refused by condition number, not by waiting for LAPACK.**

Wide industrial plants routinely contain exact linear combinations — a total that sums its branches,
a level reported in two units. `numpy.linalg.inv` raises only for a matrix singular in *exact*
arithmetic; a covariance assembled from real readings of a redundant signal is merely astronomically
ill-conditioned, so it inverts without protest and returns numbers with no surviving precision.
`_invert` therefore tests the condition number against the reciprocal of machine epsilon and raises
a `ValueError` naming the remedy. Relying on the exception would have let exactly the realistic case
through in silence.

## The measured result

Same corpus, same split, same alert threshold (3.0), same seed (11), same harness. The only thing
that differs is the model. Written to `eval_runs/log.jsonl` by `scripts/evaluate_atlas.py`.

On HAI's three-way split — the protocol the 8,390 figure comes from:

| Detector | Recall | FP/normal-hr | Precision | ECE (isotonic) |
| --- | --- | --- | --- | --- |
| `model:gaussian` (PART 3) | 1.00 | 8,389.81 | 0.0043 | 0.0424 |
| `model:atlas-pca` | 1.00 | 17,529.93 | 0.0048 | 0.0343 |
| `model:atlas-mahalanobis` | 1.00 | **646.58** | 0.0047 | 0.0291 |

**Mahalanobis delivers the claim: a 13.0× reduction in false positives per normal hour at
identical recall.** It holds under the other two protocols as well, though there it is a trade
rather than a free win — prefix, 7,092 → 624 (11.4×) at recall 1.00 → 0.80; designed, 435 → 8.78
(49.6×) at recall 1.00 → 0.40. The three-way result is the one that satisfies "materially lower
false positives at comparable-or-better recall" outright, and it is the one the headline test
asserts.

## The result 5A did not expect

**`PcaResidualModel`, which the PART nominated as the primary model, loses on HAI.** It roughly
doubles the false-positive rate. This is recorded rather than tuned away (Constitution §3.5), and
the mechanism is understood:

| | in-sample (train) | out-of-sample (test) | inflation |
| --- | --- | --- | --- |
| `atlas-pca` | 0.64% out-of-band | 4.92% | 7.7× |
| `model:gaussian` | 0.48% | 1.59% | 3.3× |

In-sample the PCA fit is exactly right — 0.64% of readings outside a three-sigma band is what a
correct fit on real, non-Gaussian residuals looks like. The problem is what happens when the capture
changes underneath it. A PCA residual band is built from the variance the retained components
*failed* to explain, five per cent of it at the default, so it is a far tighter band than a marginal
standard deviation. HAI's training and test data are different capture periods, and the drift
between them is small in absolute terms and enormous relative to a band sized by the noise floor.

Lowering `variance_retained` confirms the mechanism monotonically — 0.95 → 4.92%, 0.80 → 3.36%,
0.50 → 1.77% — reaching parity with the per-signal baseline but never beating it. Mahalanobis does
not inflate at all (0.04% → 0.03%) because shrinkage widens its conditional bands, which is exactly
the tolerance PCA lacks.

Both models ship, because the PART asked for both and because BATADAL tells a different story
(there PCA lifts recall from 0.50 to 1.00 while Mahalanobis does the same at a fifth of the alarms).
What changes is which one Atlas should reach for first, and the measurement says Mahalanobis. The
finding is pinned by `test_the_pca_residual_band_is_the_one_that_does_not_survive_capture_drift`,
which fails loudly and names this ADR if it ever reverses.

## Consequences

- Atlas has a measured, reproducible answer to the false-positive problem that motivated it, and it
  cost nothing in recall on the protocol the problem was stated in.
- The joint models are ordinary `BehaviouralModel`s. 5B, 5C and the harness need no special path.
- Explainability survives joint modelling. Every Atlas deviation names its signal, carries the value
  the rest of the plant implied, and traces to a real measurement.
- A hypothesis confidence is still not a calibrated probability, because 4B's priors and
  `EVIDENCE_STRENGTH` remain unmeasured placeholders. Nothing in 5A changes that, and §3.3 still
  forbids surfacing one. 5C owns it for the OT domain.
- **HAI's absolute numbers remain poor for everyone.** 646 false positives per normal hour is a 13×
  improvement and still not deployable, and precision stays near 0.005 for every model tried. Some
  of that ceiling is the corpus: training and test are different captures, and the three-way split
  leaves HAI only 4% of its timeline to learn from — 173 complete timestamps for 52 signals. The
  claim this PART makes is a real reduction attributable to joint modelling, not a solved problem.

## Alternatives considered

- **A per-signal fallback for constant signals.** Would close the gap in decision 5, and would have
  been a third model in all but name. The PART says two exactly.
- **Selecting components by a fixed count rather than retained variance.** Rejected: a count means
  something different on every plant, whereas retained variance is the same statement everywhere.
  `variance_retained` is bounded strictly below 1.0, since retaining everything reconstructs any
  input perfectly and turns the model into an elaborate identity function.
- **Tuning `variance_retained` per corpus until PCA won.** Rejected outright. It would have turned a
  measurement into an advertisement, and the diagnostic above shows it does not even reach parity.
- **Reporting only the winning model.** Rejected for the same reason `scripts/calibrate_corpora.py`
  reports Platt losing on BATADAL.

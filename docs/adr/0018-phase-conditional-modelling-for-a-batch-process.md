# ADR 0018 — Seeing a phased process: why Atlas was blind on the batch reactor, and the one fix that does not cost another plant

- **Status:** Accepted
- **Date:** 2026-08-17
- **PART:** A-FIX-1
- **Supersedes:** nothing
- **Depends on:** [ADR 0017](0017-the-breaking-harness-fingerprint-classification-and-judging-from-true-state.md),
  [ADR 0015](0015-simulated-plants-the-injection-hook-and-the-true-state-record.md),
  [ADR 0009](0009-joint-modelling-per-signal-attribution-and-the-model-that-lost.md),
  [ADR 0007](0007-the-evidence-boundary-and-a-calibrated-confidence.md)

## Context

D3 measured Atlas against D2's graded battery and found it **wholly blind** on the batch reactor:
zero subsystem events across all 20 attacks, at every subtlety including the most blatant, and zero
across 34 hours of normal operation. D3 named the thing to investigate — a batch process has no
single stationary correlation structure for `MahalanobisModel` to learn — and left it.

This PART was commissioned on that diagnosis. The diagnosis is **confirmed in its conclusion and
corrected in its mechanism**, and the correction matters because it is what rules out the fix that
looks most obvious.

---

## What was actually measured

### 1. The blindness is a scale-dependent noise floor, not a blurred average

`_shrink` (`src/phos/atlas/multivariate.py:697`) pulls the empirical covariance toward the standard
Ledoit–Wolf target:

```
shrunk = cov * (1 - shrinkage) + I * (shrinkage * trace(cov) / width)
```

That target is expressed **in the units of the signals**, and a plant's signals are incommensurable.
`MahalanobisModel` reports a conditional standard deviation of `1 / sqrt(diag(precision))`, so adding
`shrinkage × average_variance` to every diagonal entry imposes a **uniform absolute floor** on every
signal's conditional σ, whatever that signal's own scale.

Pooled across phases, the batch reactor's `reagent_feed_kgph` swings 0 → 5,420 kg/h (variance
4.63 × 10⁶) while `reactor_pressure_barg` has variance 0.913 — a spread of 5.07 × 10⁶. The mean
diagonal is 356,850, so 17,842 is added to every diagonal entry, and no signal's conditional σ can
fall below `sqrt(17,842) = 133.58` units. The floor predicts the observed minimum to four
significant figures on all three plants:

| Plant | predicted `sqrt(0.05 · avg var)` | observed min conditional σ |
| --- | --- | --- |
| `batch-reactor` | 133.576 | 133.578 |
| `water-treatment` | 4.682 | 4.683 |
| `power-generation` | 21.367 | 21.367 |

With `band_k = 3.0`, every batch band is ~801 units wide. Observed signal ranges run from 4
(`batch_phase`) to 5,420 (`reagent_feed_kgph`), so **13 of 13 signals carry a band wider than their
entire observed range**. The largest departure anywhere in the attacked corpus is **1.99** against a
threshold of 3.0. Nothing can ever be out of band. That is the blindness, exactly and completely.

This is not a subtle statistical shortcoming. It is a scale bug with a closed-form magnitude.

### 2. It is nevertheless a *phase* problem, which is why the PART's instinct was right

`reagent_feed_kgph` only has a variance of 4.63 × 10⁶ because the pool mixes CHARGE — feed running at
~5,400 kg/h — with the four phases in which it is exactly zero. Conditioning on phase collapses the
trace and the floor with it, using the shipped `_shrink` completely unchanged:

| Phase | IDLE | CHARGE | HEAT | REACT | DISCHARGE |
| --- | --- | --- | --- | --- | --- |
| conditional σ floor | 1.65 | 53.3 | 40.5 | 1.30 | 2.47 |

So the mechanism and the phase structure are one story: **pooling across phases inflates one
signal's variance enough that the scale-dependent shrinkage target sets a noise floor which swallows
every band.** Phase conditioning removes the cause rather than compensating for the symptom.

---

## Options considered

### Option A — make the shrinkage target scale-invariant (shrink the correlation matrix)

Standardise before shrinking, then rescale. It addresses the mechanism directly, is a ~4-line change
to one function, and needs no new concepts. It also revives the batch plant on its own.

**Measured, and rejected.** It is scored per-plant below as out-of-band *rows* on the untouched
holdout (the false-positive proxy) against out-of-band rows on the attacked corpus, with their ratio
as a separation figure:

| Plant | variant | holdout rows OOB | attacked rows OOB | separation |
| --- | --- | --- | --- | --- |
| `batch-reactor` | shipped | 0/4,320 (0.0%) | 0/11,520 (0.0%) | — |
| `batch-reactor` | scale-invariant | 123/4,320 (2.8%) | 1,271/11,520 (11.0%) | 3.88 |
| `water-treatment` | shipped | 70/5,760 (1.2%) | 1,016/14,400 (7.1%) | **5.81** |
| `water-treatment` | scale-invariant | 2,538/5,760 (44.1%) | 3,415/14,400 (23.7%) | **0.54** |
| `power-generation` | shipped | 1/8,640 (0.0%) | 13,582/14,400 (94.3%) | — |
| `power-generation` | scale-invariant | 2,382/8,640 (27.6%) | 14,400/14,400 (100.0%) | 3.63 |

On water treatment — the one plant D3 found to be a plausible detector — a scale-invariant target
flags the **attack-free holdout at nearly twice the rate of the attacked corpus** (44.1% against
23.7%): separation collapses from 5.81 to 0.54. Standardising makes every small-scale signal live,
and those signals' conditional structure does not generalise from the training corpus to a fresh one.
On power generation, whose false-positive load D3 already called unusable, holdout rows go from 1 to
2,382.

It fixes the blind plant by destroying the working one. The PART is explicit: *"A batch-process fix
that degrades water-treatment detection is not a fix."* Rejected on the measurement, not on taste.

### Option B — one joint model per phase, routed by the published phase register — **CHOSEN**

The batch plant publishes `batch_phase` as ordinary telemetry (`src/phos/synth/plants/batch.py`), so
the operating mode is an **observed signal**, not something that has to be inferred. Fit the existing
joint model separately within each phase and route each moment to its phase's model at score time.

Measured on the production code path, with `_shrink` untouched:

| `batch-reactor` | candidates | out-of-band deviations |
| --- | --- | --- |
| Single shipped model — holdout | 841 | **0** |
| Single shipped model — attacked | 2,521 | **0** |
| Per-phase — holdout | 3,508 | 131 |
| Per-phase — attacked | 25,047 | **13,593** |

Why this one:

* **It cannot touch another plant.** It is a new `BehaviouralModel` selected for a plant that
  declares a phase register. Water treatment and power generation declare none, keep
  `MahalanobisModel`, and are byte-for-byte unaffected. Option A could not offer that guarantee
  because it changed a function every plant shares.
* **It changes no interface.** `AtlasEngine` only ever asks a model to `score`, so the emitted
  objects, 4A's out-of-band boundary, calibration, grouping and reasoning are all unchanged.
* **It stays explainable** (Constitution §3.2). Each `Deviation` still carries a real
  `ExpectedRange` — now "what the rest of the plant implies during *this phase*", which is a
  stronger claim than the pooled one, not a vaguer one.
* **It is honest about its own machinery** (Constitution §3.6). Routing on a declared, observed
  register is a mechanical lookup. It is not mode inference and the code does not imply otherwise.

### Option C — condition on an *inferred* operating mode (clustering, or a switching/HMM regime model)

The general answer, and the only one available for a phased plant that publishes no phase register.
Rejected for this PART:

* It introduces an inference step whose errors are invisible — a misassigned mode produces a
  confident judgement against the wrong baseline, with nothing in the evidence to show it happened.
  Option B's routing key is a stored number that can be read back.
* It adds a fitted component (cluster count, transition matrix) that would itself need evaluating
  before anything downstream could be trusted (Constitution §3.5), which is a PART of its own.
* On *this* plant it would be strictly worse than reading the register that is already there.

It remains the right next step for the general case, and is recorded as deferred rather than
dismissed.

---

## Decisions

1. **`PhaseConditionalModel` / `PhaseConditionalFittedModel`** in `src/phos/atlas/phased.py`. A
   `BehaviouralModel` that partitions training observations by the value of a declared phase feature,
   fits an inner `MultivariateModel` per phase, and routes each moment at score time.
2. **The phase feature is declared, never guessed.** `phase_feature` is a required field. Sniffing
   for "a signal with few distinct integer values" would silently pick up a tap position or a pump
   stage count and partition a plant on nonsense.
3. **The wrapper's knobs are authoritative.** `min_samples`, `band_k` and `emit_k` are copied onto
   each per-phase inner fit, so one setting cannot mean two things. `inner` chooses only the
   *representation* (Mahalanobis or PCA residual).
4. **A pooled fallback model is fitted alongside the per-phase ones** and used for any moment whose
   reported phase was never seen in training, or which carries no phase reading at all. The
   alternative — emitting nothing — would make an out-of-range phase value a guaranteed blind spot,
   which is the one thing an attacker who can write to the register would want. The fallback spans
   the phase register itself, so a wild value is out of band on its own terms.
5. **The routing key is excluded from each per-phase model by the existing machinery, not by new
   code.** Within a phase `batch_phase` is constant, so `MultivariateModel.fit`'s existing
   zero-variance filter drops it: each per-phase model spans 12 signals rather than 13. This is
   correct — a constant cannot be judged against its own correlation structure — and it is why
   decision 4 matters.
6. **`_shrink` is left exactly as it is.** The scale-dependence documented above is real and is not
   confined to the batch reactor: 13/15 water-treatment and 13/16 power-generation signals also carry
   a band wider than their observed range. But every attempt to fix it globally that was measured
   here made the working plants worse, and this PART's scope is the batch process. Recorded as a
   known defect with its magnitude, for a PART that can measure it properly.

---

## Measured outcome

Re-run of `scripts/evaluate_breaking_points.py`, seed 7, against the same battery D3 measured.

**Batch reactor — every attack type moved off the floor, and the danger column nearly emptied:**

| Section | Type | Before (caught/missed, danger) | After (caught/missed, danger) |
| --- | --- | --- | --- |
| clean | `BLATANT` | blind 0/4, danger 3 | caught to 0.99 — 4/0, danger 0 |
| clean | `MIMIC` | blind 0/4, danger 2 | ragged 0.40–0.99 — 3/1, danger 1 |
| clean | `STEALTH_DRIFT` | blind 0/4, danger 0 | caught to 0.99 — 4/0, danger 0 |
| caveated | `CORRELATION_BREAK` | blind 0/4, danger 1 | caught to 0.99 — 4/0, danger 0 |
| caveated | `LIAR` | blind 0/4, danger 3 | caught to 0.99 — 4/0, danger 0 |

Attacks that drove the true state into danger while Atlas reported all-clear fell from **9 to 1** on
this plant, and from 10 to 2 across the whole report.

**And the harness refuses to call that detection.** The false-positive load went from 0.00 to
**3.59 per normal hour** (123 over 34.25 hours, 3,887 subsystem events, 66 narratives), against
`SATURATED_FP_PER_HOUR = 1.0`. D3's own saturation rule therefore marks the batch corpus saturated
and strikes any detection claim from it, exactly as it does for power generation. The honest reading
of this PART is **silent → saturated**: Atlas now produces evidence on a batch process where it
produced none, and 19-of-20 is not a recall that may be quoted.

**No harm elsewhere, proven rather than argued.** Every `water-treatment` and `power-generation` row
in the breaking-point map is byte-identical to D3's, as are both plants' false-positive rates
(0.3894 and 134.4943 per hour), event counts (598 and 15,903) and narrative counts (12 and 2). The
guarantee is structural — `_model_for` selects on `plant_id`, and neither plant is declared — and
`test_every_other_plant_keeps_the_pooled_joint_model` asserts it.

**The anti-fingerprint check still passes.** No zero-magnitude control produced an alert, so the
gain is not Atlas learning the injection artefact. `LIAR` and `CORRELATION_BREAK` remain in the
caveated section and are never pooled with the clean map.

**Where the false positives actually are.** On the untouched holdout, **92.4% of out-of-band
deviations fall within ten samples (five minutes) of a phase change**, from 25.2% of the moments.
The first moment of a new phase carries 0.657 out-of-band deviations against 0.003 once settled — a
factor of 219. The cause is mechanical: the register flips the instant the recipe's condition is
met, while the plant's physical state takes minutes to arrive in the new regime, so the opening
moments of every phase are judged against a baseline the plant has not reached yet. That is the
whole of the saturation, and it is a transition-handling problem rather than a modelling one.

Not fixed here, deliberately. The obvious remedy — a settling allowance after each transition — is a
*blind window*, and an attacker able to trigger phase changes would buy cover with it. That trade
needs its own measurement of what it costs in recall, which is a PART rather than a postscript.

## Consequences

**Gained.** A batch process is no longer invisible. The per-phase claim is also a sharper one: an
`ExpectedRange` now says what a reading should be *during this phase*, which is the question the
plant's docstring says actually matters.

**Cost.** More fitted parameters — one covariance per phase instead of one per plant — so each phase
needs enough samples, and `min_samples` is now counted per phase. A phase that is rare in training
gets no model and falls through to the pooled fallback.

**Unmeasured, and stated as such.** Routing depends on a *reported* signal. An attacker who can
falsify `batch_phase` to another valid phase routes the moment to the wrong baseline, and no per-phase
model spans the register to catch it. D2 never targets `batch_phase` — all 20 batch attacks move it
only as a physical *consequence* of shifted phase timing — so **this risk cannot be measured with the
shipped battery and is not claimed to be handled.** Measuring it needs an attack type that writes to a
phase register, which is a change to D2 and out of scope here.

**Deferred, in the order the evidence ranks them.**

1. **Transition handling on a phased plant.** 92.4% of the residual false-positive load sits in the
   five minutes after a phase change. Closing it is what would convert this result from *saturated*
   into a detection claim, and it needs the blind-window trade measured rather than assumed.
2. **The scale-dependence of `_shrink`**, which is not confined to the batch reactor: 13/15
   water-treatment and 13/16 power-generation signals also carry a band wider than their entire
   observed range, so both plants are detecting on a handful of wide-ranging signals and are deaf
   on the rest. The global fix measured here made things worse; a correct one is its own PART.
3. **Option C (inferred operating mode)** for a phased plant that publishes no register.
4. **An attack that writes to a phase register**, without which decision 4's exposure cannot be
   measured at all. That is a change to D2.

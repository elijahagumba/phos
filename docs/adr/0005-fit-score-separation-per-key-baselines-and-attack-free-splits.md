# ADR 0005 — Fit/score separation, per-key baselines with a feature-level fallback, and attack-free splits

- **Status:** Accepted
- **Date:** 2026-07-28
- **PART:** 3 — Behavioural Model Interface & Baseline Models

## Context

PART 3 builds the first thing in PHOS that actually detects. Everything above it in the build order
— the two engines, the reasoning layer, the correlation layer — will inherit whatever shape is
chosen here, so the interface matters more than the three baseline models that first implement it.

Three Constitution invariants bind the design directly. §3.1 says every engine reads and writes the
one ontology and invents no private alert format. §3.2 says anything a user could see must be
reconstructable from stored evidence. §3.5 says nothing is trusted until the harness has measured
it. A fourth constraint is implicit in §3.4's rejection of signatures: a behavioural model that
cannot say *what it expected* is not explainable, and an unexplainable detector is not the product.

The specific traps this PART had to avoid are the ones that make published anomaly-detection results
irreproducible: scoring a model on data it was fitted to, counting training hours in a
false-positive denominator, and treating "I have never seen this before" as "this is an attack".

## Decision

**1. Fitting and scoring are different types.**
`BehaviouralModel.fit(observations) -> FittedModel`, and only a `FittedModel` has `score`. The
unfitted model has no `score` method at all — `hasattr(GaussianBaseline(), "score")` is `False`, and
a test asserts it.

This is a structural guarantee rather than a runtime check. "Scored before fit" is not a bug that
can be written and then caught by an assertion; it is a program that does not type-check. The cost
is one extra class per model, which is cheap against a category of error that would silently produce
excellent-looking numbers.

**2. A baseline is learned per `(entity_id, feature)` key, with a feature-level aggregate beneath
it.** `model_key(observation)` pairs the observation's first entity id with its feature.

Per-entity is the granularity that makes a deviation meaningful: pump 4 running at 60 °C may be
normal while pump 7 running at 60 °C is not, and one shared baseline across both learns neither.
The feature-level aggregate — one range per feature across every entity — exists solely as the
fallback for a key training never saw, which is the common case in any environment where devices
appear after the training window closed.

An observation naming several entities is attributed to the first. That is a simplification, stated
as one: relationship and peer-group keying is PART 6's problem.

**3. Unknown is not anomalous.**
Resolution runs exact key → feature-level → *nothing*. An observation whose feature was never
trained on produces **no** `Deviation` at all.

This is the rule most likely to be quietly broken by a future engine, so it is worth stating why.
A model that flags everything it does not recognise appears to have excellent recall on any corpus
containing something new, and it is precisely useless in production, where "something new" is the
normal state of an enterprise network. Emitting a deviation here would also violate §3.2: there is
no stored `ExpectedRange` to reconstruct the conclusion from, because none was ever learned. A key
with fewer than `min_samples` points forms no baseline either, for the same reason — eight readings
are not evidence of what normal looks like.

**4. The training set is the longest attack-free prefix, and the harness only ever sees the test
half.** `train_test_split(dataset, policy)` returns two full `Dataset` objects. The training half is
the time-ordered prefix that stays within `policy.train_fraction` of the timeline *and* ends
strictly before the earliest labelled attack; the test half is the remainder, carrying every
interval that intersects it.

A prefix rather than a random sample because behavioural models are temporal: sampling randomly
leaks the future into the past, and for the EWMA model it is not even well-defined. `train_fraction`
is a ceiling, not a target — the prefix is cut shorter whenever that is what it takes to keep an
attack out of training, and if the corpus opens under attack the training half is empty and says so.

Returning `Dataset` objects rather than raw observation lists is what keeps the false-positive rate
honest. `false_positive_rate` divides by `Dataset.normal_duration()`; had training and test shared
one `Dataset`, the hours the model learned from would sit in that denominator and flatter every
detector PHOS ever builds by the ratio of the split.

`ModelDetector` deliberately does *not* split or fit internally. The caller splits, fits on the
training half, and passes the fitted model in — so a run in which the model saw its own test data is
something you have to write on purpose.

**5. A model's fitted state is stored as ontology objects, not as a private struct.**
`FittedModel.expected_ranges` is a mapping of `ExpectedRange`, and that is the whole of what a
fitted Gaussian or IQR model knows. The EWMA model is the interesting case: its fitted state is an
exponentially weighted mean and variance, which are exactly `ExpectedRange.mean` and the square of
`ExpectedRange.stddev`. Nothing extra was needed, so §3.1 applies to a model's internals and not
merely to its outputs.

**6. Every anomaly score is finite.**
`clamp_magnitude` bounds scores to `MAX_MAGNITUDE` (1e6). `ExpectedRange.zscore` returns infinity
for any departure from a perfectly constant feature — PART 1 says explicitly that callers wanting a
finite magnitude must clamp it themselves — and an infinite `Deviation.magnitude` serialises to JSON
`null` and fails to round-trip, which would break traceability for exactly the deviations that
matter most.

**7. The reported confidence is an uncalibrated squash, and is labelled as one everywhere.**
`ModelDetector` sets `Detection.confidence = 1 - exp(-magnitude / score_scale)`. The function is
named `uncalibrated_confidence`, its docstring carries a warning, and a test asserts the exact
formula so that PART 4 replacing it is a visible change rather than a silent one. Per §3.3 it must
not reach a user until PART 4 fits a calibrator; it exists now only so the harness can *measure*
calibration, which is the honest order — measure first, claim later.

## Consequences

- Any `FittedModel` can be scored by the PART 2 harness through `ModelDetector` with no change to
  the harness, which is the first evidence that the `Detector` protocol was drawn at the right
  altitude. The Atlas and Sentiel engines inherit this for free.
- The three baselines fail differently on purpose — Gaussian is sensitive but assumes clean training
  data, EWMA tracks drift at the cost of absorbing sustained attacks, IQR shrugs off contaminated
  training data at the cost of sensitivity. `tests/models/test_iqr.py` demonstrates the
  Gaussian/IQR difference directly rather than asserting it in prose.
- Anomaly magnitudes are **not** comparable across models. A Gaussian magnitude is a z-score, an IQR
  magnitude is an overshoot in interquartile ranges; the same alert threshold means different things
  to each. This is why the harness sweeps each detector's own score distribution (ADR 0003) instead
  of comparing raw scores, and why the end-to-end tests use a different `alert_threshold` per model.
- `min_samples` and `emit_k` are now part of what a reported number depends on. Neither is recorded
  on `EvaluationReport`, which records the *harness* config only. If model hyperparameters start
  varying between logged runs this will need revisiting.

## Ambiguities resolved in this PART

| Question | Decision | Why |
| --- | --- | --- |
| The PART 3 spec says a `Deviation` is emitted "only when the observation lies outside the expected band", but also that `emit_k` defaults to 1.0 while `band_k` defaults to 3.0 — so the two disagree | `emit_k` governs emission; `band_k` shapes the reported `ExpectedRange`. With the defaults, some emitted deviations lie *inside* their reported range. | The spec states the intent plainly: a low `emit_k` "gives the harness a dense set of candidate detections to threshold-sweep over". A sweep over a sparse set is not a sweep. A PART 3 deviation is therefore a **candidate**, its `magnitude` is the authority, and the harness's `alert_threshold` picks the operating point. **This is the one place PART 3 stretches PART 1's wording**, so it is flagged rather than buried: set `emit_k >= band_k` for the strict reading, in which every emitted deviation also falls outside its reported range. PART 4 should decide whether to tighten this before deviations become evidence. |
| What `ExpectedRange` attaches to a `Deviation` from the feature-level fallback | The feature-level range itself, carrying `FEATURE_LEVEL_ENTITY_ID` (`"ent_featurelevel"`) as its entity. | §3.2: the stored evidence must say which baseline judged the observation. A sentinel that reads as obviously-not-a-device is better than silently attributing a cross-entity aggregate to one machine. |
| Which `ExpectedRange` an EWMA deviation carries | The **dynamic** band as it stood at that timestep, captured *before* the observation was folded in. | The evidence has to record what the model actually expected at the moment it was surprised, not what it expects afterwards. |
| Which entity an EWMA dynamic range names when the state was seeded from the feature-level fallback | The observed entity, not the sentinel. | Unlike the static models, the EWMA state stops being a shared aggregate the moment it is seeded — from then on it tracks this key's values and nothing else's. |
| `learned_from_window` on a dynamic EWMA range | `(training window start, latest timestamp folded in)`, where the latter is monotonic. | It is then literally true: this is the span of data the state reflects. Monotonicity means out-of-order scoring can never invert the window and trip PART 1's validator. |
| The IQR spec names its fence multiplier `k`, the others name theirs `band_k` | One field, `band_k`, on the shared base; `IqrBaseline` overrides the default to 1.5. | One name for one concept. The docstring is explicit that for IQR it multiplies the interquartile range rather than a standard deviation. |
| How an IQR model recovers the interquartile range at scoring time | Derived from the stored bounds: `IQR = (high - low) / (1 + 2·band_k)`. | Exact, and avoids adding a field to `ExpectedRange` that only one model would use. |
| Anomaly score for a value *inside* the IQR fence | Exactly `0.0`, not a small positive number. | Tukey's fence makes no claim about where within normal a value sits. The consequence — a sparser candidate set than the other two models — is a property of the model, and is documented rather than papered over. |
| Which standard deviation the Gaussian model learns | Population (`numpy.std`, `ddof=0`). | Matches PART 2's `ThresholdDetector` so a z-score means the same thing everywhere in PHOS. |
| Whether `fit` should sort its input | Yes, per group, by timestamp. | Makes fitting deterministic and order-independent even for EWMA. `score` deliberately does **not** sort: an EWMA's answer depends on the sequence it is given, and silently re-ordering the caller's data would hide that. A test asserts scoring is order-dependent. |
| Whether the EWMA state should freeze while an anomaly is in progress | No. Anomalous values are folded in like any other. | Freezing is a real technique but it belongs to the OT engine (PART 5), not to a shared baseline. A test asserts the resulting decay so the behaviour is documented rather than discovered later. |
| A `Deviation` for an observation the dataset does not contain | `ModelDetector.run` raises `ValueError`. | §3.2. A deviation that cannot be traced back to a measurement is unexplainable by definition, so it is refused rather than dropped. |
| `Deviation.timestamp` — detection time or observation time? | The observation's timestamp. | This is an offline scorer. Stamping wall-clock time would make every run irreproducible, violating §3.7. |
| Non-finite `Observation.value` (NaN) | Out of scope; not handled. | Neither shipped adapter can produce one (`LabelledCsvAdapter` skips NaN cells). Adding an untested path for an unreachable input is scope creep. Recorded in `PROGRESS.md` as deferred. |
| `scikit-learn`, pinned in PART 2 and still unused | Left pinned, still unused, still flagged. | The PART 3 spec permits either. Nothing here needs it — three baselines that are a mean, a recursion and two quantiles do not justify the dependency. If PART 4's calibrator does not use it, drop it. |

## Alternatives considered

- **One `Model` class with a `fitted: bool` flag.** Rejected: it turns a compile-time guarantee into
  a runtime check that every call site must remember to make, which is the failure mode the
  separation exists to prevent.
- **Random train/test sampling instead of a prefix.** Rejected: leaks future into past for temporal
  models, and is meaningless for EWMA.
- **Falling back to a global all-features baseline beneath the feature level.** Rejected: pressure
  and packet rate share no units and no scale, so a range aggregated across features describes
  nothing. The ladder stops at the feature and then stops emitting.
- **Treating an unseen feature as maximally anomalous.** Rejected — see decision 3. It inflates
  recall on any corpus containing novelty and is useless in production.
- **Normalising the IQR score by a robust sigma estimate (`IQR / 1.349`) to make it comparable to a
  z-score.** Tempting, because it would let one `alert_threshold` serve all three models. Rejected:
  the spec defines the score as distance beyond the band, and manufacturing cross-model
  comparability would undercut ADR 0003's reason for sweeping each detector's own distribution.

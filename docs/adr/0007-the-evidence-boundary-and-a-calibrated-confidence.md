# ADR 0007 — The evidence boundary, and a confidence that means what it says

- **Status:** Accepted
- **Date:** 2026-07-30
- **PART:** 4A

## Context

Two debts blocked PART 4B, and both were about a number or a type meaning something other than what
its name claimed.

**A `Deviation` was not a deviation.** `BehaviouralModel.emit_k` defaults to 1.0 while `band_k`
defaults to 3.0, so a model emits a `Deviation` for any observation reaching one unit of its
magnitude scale — including observations sitting comfortably inside their own `ExpectedRange`. That
is deliberate and useful: a dense candidate set is what makes the harness's threshold sweep
meaningful. But it means "deviation" named two different things, and PART 4B intends to build
competing hypotheses out of them. Hypotheses resting on observations that never left normal would
look perfectly well-supported and be about nothing.

**A confidence was not a probability.** `phos.models.uncalibrated_confidence` maps a magnitude
through `1 - exp(-m/scale)`. It is monotone and bounded, and it never consulted a label, so it has
no grounds to claim that 0.63 means "right about 63% of the time". Measured, it is not close:
expected calibration error of 0.33 on BATADAL and 0.65 on HAI (0.94 under the prefix protocol).
Constitution §3.3 forbids surfacing it, which left PHOS with no user-facing confidence at all.

## Decision

**1. Three terms, defined once, and `Evidence` can only be built from one of them.**

- A **scored candidate** is any `Deviation` a model emits. It exists to give the harness a dense
  threshold sweep and never becomes `Evidence`.
- An **out-of-band deviation** is a scored candidate whose observation value fell outside its
  `ExpectedRange` `[low, high]`. This is a genuine departure from learned normal.
- **`Evidence`** is constructed only from an out-of-band deviation, only by
  `evidence_from_deviation`, which raises `ValueError` otherwise.

The refusal is the load-bearing part. PART 4B does not have to remember this rule, and cannot
forget it, because the only route from a model's output to `Evidence` enforces it.

**2. The boundary is the value against the range, never a magnitude threshold.**

`is_out_of_band` reduces to `not deviation.expected.contains(observation.value)`. A magnitude
threshold was rejected because **magnitude means something different in each baseline**: Gaussian
reports an absolute z-score, EWMA a z-score against a moving level, IQR an overshoot beyond a fence
expressed in interquartile ranges — and IQR reports exactly `0.0` for everything inside its band,
so a magnitude test would classify its in-band candidates correctly by accident and Gaussian's
incorrectly. The bounds are the one thing all three state in the same units: those of the
measurement. The check is therefore exact rather than tuned, and it needs no per-model constant.

Both `is_out_of_band` and `evidence_from_deviation` additionally refuse a deviation/observation pair
whose ids do not match. This is beyond the letter of the PART, and it is here because the
alternative is silent: answering a question about a mismatched pair would produce `Evidence` whose
`source_id` leads back to a measurement other than the one it describes, which is a §3.2
traceability hole that nothing downstream could detect.

**3. Three slices, not two, and degenerate slices raise.**

A calibrator is itself fitted on labels, so `train_calib_test_split` yields train (attack-free
prefix, delegated to PART 3's `train_test_split` so the invariant means exactly what it meant
there), calib (labelled middle slice, fits the calibrator), and test (labelled remainder, the only
source of any reported metric). Both fractions are of the whole timeline; test takes the remainder.
When an early attack cuts the training prefix short, the space given up goes to calib rather than
being dropped.

`DegenerateSplitError` is raised — not returned, not logged — when any slice is empty, when there is
no attack-free prefix, or when calib **or test** lacks either class. Requiring it of *test* is
broader than the PART asked for, and it is the most important of the checks. On an attack-free test
slice every alert is a false positive, so a calibrator answering `0.0` to everything scores a
*perfect* calibration error, and the before/after comparison this PART exists to make would report a
spectacular improvement that means nothing. HAI is a live example: its attacks all end by 51% of its
test file's timeline, so the 0.4/0.3 fractions that suit BATADAL leave HAI with nothing to be right
about. It is refused, and the operator narrows the fractions (0.04/0.30) until every slice is
viable.

**4. A fitted calibrator is stored parameters, not a live estimator.**

`FittedPlattCalibrator` holds a coefficient and an intercept; `FittedIsotonicCalibrator` holds the
fitted interpolation knots. Both are frozen Pydantic models of plain floats, so a calibrated
confidence can be reproduced from the record instead of by re-running a fit (§3.7), and a calibrator
can cross the API boundary in PARTs 8–10 without pickling anything. sklearn is used to fit and is
confined to two private functions that convert what it returns to floats immediately; a test pins
the isotonic interpolation to sklearn's own `predict`, including the `out_of_bounds="clip"`
behaviour outside the fitted range, so the reimplementation cannot drift.

Fitting refuses single-class calibration data. A logistic regression refuses it anyway, but isotonic
regression returns a **constant** calibrator — perfectly calibrated, entirely uninformative — which
would post an excellent ECE while carrying no signal.

**5. Isotonic is the calibrator PHOS uses; both are measured and both are reported.**

Measured on the test slice, with the calibrator fitted only on calib:

| Corpus | uncalibrated ECE | isotonic | Platt |
| --- | --- | --- | --- |
| BATADAL | 0.3485 | **0.1569** | 0.5283 |
| HAI | 0.9536 | 0.0424 | **0.0358** |

Isotonic beats the baseline on both. **Platt is worse than doing nothing on BATADAL**, and the
reason is specific rather than bad luck: nine of BATADAL's forty-three features are perfectly
constant across the training window, so their z-scores are infinite and `clamp_magnitude` pins them
at `MAX_MAGNITUDE` (1e6). The resulting score distribution has a median of 1.38, a 99th percentile
of 3.06, and a maximum of 1e6 — six orders of magnitude concentrated in 0.45% of the points. Platt's
logit is *linear in the raw score*, so those sixty points fix its coefficient at 3.4e-06, which
makes its logit effectively constant at the base rate for the other 99.5% of the data. Isotonic
depends only on the rank ordering of scores, so the clamp costs it nothing. The empirical attack
rate is not even monotone in score — flat near 0.10 for the bottom seven deciles, then rising to
0.22 — which no sigmoid in the raw score can express.

The general lesson, recorded because it will recur: **PHOS's magnitude scale is not linearly
meaningful.** `MAX_MAGNITUDE` exists to keep infinities serialisable, and that alone makes any
calibrator parametric in the raw score mis-specified. Rank-based calibration is the safer default
here.

Both are still reported by `scripts/calibrate_corpora.py`, including when one loses. Reporting only
the winner would turn a measurement into an advertisement.

**6. `CalibratedModelDetector` changes the confidence and nothing else.**

`score` remains the raw magnitude. So every `alert_threshold` in the experiment log keeps its
meaning, and the before/after comparison is two readings of *the same alert set* rather than a
comparison between two different ones — asserted directly in
`test_the_comparison_is_between_two_readings_of_the_same_alert_set`. The detector validates that
what the calibrator returns is in `[0, 1]` and has one entry per score, because `FittedCalibrator`
is a `Protocol` and a structural contract cannot express either.

## Consequences

- **§3.3 is satisfied on the `CalibratedModelDetector` path, and only there.**
  `ModelDetector`'s confidence remains uncalibrated and remains unfit to surface. It is kept because
  the harness needs something to *measure* calibration against, which is the honest order.
- **PART 4B has a floor it cannot fall through.** `Evidence` exists only for real departures from
  normal, and its `weight` is a calibrated probability.
- **`scikit-learn`'s pin is finally justified.** It had been pinned and unused since PART 1.
- **The calibrator is fitted on all candidates, but ECE is measured on the alert subset.** This is
  the sharpest known limitation. `scores_and_labels_from` labels every candidate (base rate 11.85%
  on BATADAL's calib slice), while the harness computes ECE over alerts at `alert_threshold=3.0`,
  where the true attack rate is roughly double that. Isotonic absorbs the mismatch; Platt is
  destroyed by it. Fitting conditional on the operating point would be the principled fix and is
  deliberately not done here — it changes what a calibrator *is* and belongs with whatever PART
  chooses PHOS's operating points.
- **Calibration fixes the claim, not the detection.** Recall, false positives and latency are
  unchanged by construction. HAI still emits 66,450 alerts at 8,390 false positives per normal
  hour; it now says "about 4%" about each of them instead of "about 63%", which is honest and still
  unusable. Making the detector *good* is PARTs 5–6.
- **HAI needs non-default split fractions, recorded in `SPLIT_POLICIES`.** A corpus-specific
  constant in a script is a small maintenance surface, accepted because the alternative — moving
  split policy into the committed manifests — would put an evaluation decision in a data file.
- **A fitted calibrator's `calibrate` takes an array, not a scalar.** Convenient for the detector,
  which batches one call per corpus; a papercut for a caller holding one deviation. PART 4B will
  build `Evidence` one deviation at a time and should decide whether a scalar overload earns its
  keep.

## Alternatives considered

- **Raise `emit_k` to `band_k` so every emitted `Deviation` is out of band.** Rejected: it would
  make the boundary free but collapse the threshold sweep to the handful of points above the band,
  destroying the operating-point curve that PART 2 exists to produce. The two uses genuinely want
  different densities, so the right fix is to name the difference, not to erase it.
- **A magnitude threshold for the boundary.** Rejected in decision 2 — the three baselines do not
  share a magnitude scale, so any constant would be right for one and wrong for the others.
- **Store the fitted sklearn estimator (pickle) on the calibrator.** Rejected: unserialisable to
  JSON, unversioned across sklearn releases, and unable to cross the API boundary — it would make a
  user-facing confidence unreproducible from the record, which is §3.7 exactly.
- **Let `Evidence.weight` keep accepting any non-negative float.** Rejected for this path.
  `evidence_from_deviation` requires `[0, 1]`, because the only thing it ever writes there is a
  calibrated probability and silently accepting 2.0 would put a non-probability on the path §3.3
  governs. The ontology's own field stays permissive, since PART 4B may want unbounded weights for
  other evidence kinds.
- **Calibrate on the test slice and report cross-validated ECE.** Rejected: it is the §3.7 violation
  this ADR is largely about, and a three-way split costs only data, which both corpora have.
- **Pick isotonic on reputation and skip Platt.** Rejected: "isotonic usually wins with enough
  data" is a plausible claim that happens to be true here, and Constitution §3.5 does not accept
  plausible. Fitting both is what produced the BATADAL finding in decision 5, which is the most
  useful thing learned in this PART.

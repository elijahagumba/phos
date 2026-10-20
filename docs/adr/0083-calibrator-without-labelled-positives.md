# ADR 0083 — Calibrator without labelled positives (session opened; not yet implemented)

- **Status:** Accepted — implemented 2026-09-24; **incomplete dual win**; HAI
  `hai[designed-normal-score][after]` **logged** 2026-09-25 (3.55 FP/hr, recall 1.00, 31 alerts)
  beside frozen isotonic 53.26. Frozen rows untouched.
- **Date:** 2026-09-24
- **PART:** Usefulness Phase follow-on (tracked at Gate 1 / ADR 0075; opened here)
- **Supersedes:** nothing. Does not rewrite ADR 0007, ADR 0075, or any frozen log row.
- **Depends on:** [ADR 0007](0007-the-evidence-boundary-and-a-calibrated-confidence.md),
  [ADR 0044](0044-public-surfaces-on-main-must-move-with-every-advancement.md),
  [ADR 0074](0074-the-usefulness-phase-is-defined-and-diagnosis-precedes-optimisation.md),
  [ADR 0075](0075-the-hai-false-alert-load-is-modelling-error-not-missing-evidence.md),
  [ADR 0082](0082-batch-distillation-label-classes-are-phases-and-only-the-anomalous-phase-is-scored.md)

## Context

U1 (ADR 0075) answered what kind of uncertainty produces Atlas's HAI false-alert load: **modelling
error, 418 of 418**, not missing plant context. The dominant lever it measured was fit length. The
same model class, threshold 3.0, seed 11, scored slice and signal space, varying only how much
attack-free history the model saw:

| Fit length | Alerts on the scored slice | Share of moments | Window recall |
| --- | --- | --- | --- |
| 0.48 h (the public vertical's fit) | 5,123 | 55.96% | 2 of 2 |
| 60.00 h (HAI's declared-normal file) | 97 | 2.49% | 2 of 2 |

The transition is a **step** between 3.89 h and 4.86 h — the first fit past `P1_B400B`'s 3.15 h duty
cycle. That sweep lived under its own diagnostic name; **nothing was logged to
`eval_runs/log.jsonl`**, and ADR 0075 deliberately refused to publish the quiet end as an operating
point.

**Why the public fit is 0.48 h.** The Atlas vertical needs labelled positives to fit its isotonic
calibrator (ADR 0007). The declared-normal file carries none. So the vertical splits the *labelled*
file three ways. HAI's attacks fall early enough there that `train_fraction` must be 0.04 to leave
any attack in the scored slice. The short fit is a consequence of where the only labels live, not an
oversight.

Gate 1 of the usefulness phase tracked this as
`future_sessions.calibrator_without_labelled_positives`: the actual lever on Atlas's alert load, and
**optimisation**, deferred until Sentiel was also diagnosed. Sentiel diagnosis is complete (ADR
0076). The noBOOM / batch-distillation sandbox (`eval_runs/sandbox/noboom-atlas/`) has since shown
<!-- evidence-ack: eval_runs/sandbox/noboom-atlas/ — that sandbox was never committed to this repository, as this paragraph states -->
that regime coverage and calibrator starvation are related but not identical problems: designed
protocol already fits on ~30 h of dual-clean train, yet recipe-step coverage in that train is only
7.7% of what the test split sees. **That sandbox directory was never committed to this
repository**, so the two figures in this paragraph cannot be re-checked from this history; the
`noboom-atlas-v1` baseline it is quoted against survives in
`eval_runs/sandbox/adr0083-normal-score/measurement.md`. This ADR opens the calibrator session. It
does **not** pretend the calibrator alone dissolves every recipe-regime FP on distillation.

**This record authorises the session and freezes its success contract. It does not implement the
fix, retune a threshold, or append a public log row.**

## Decision

**1. The session is opened.** Work that produces a calibrator (or an honest substitute for the
vertical's evidence-weight path) which does **not** require labelled positives is now in scope under
this ADR. The usefulness tracker's `calibrator_without_labelled_positives` entry points here. Sibling
`non_saturating_aggregation` (Sentiel) stays separately tracked and is not opened by this record.

**2. The proposed fix, stated as a requirement rather than an algorithm.** Evidence weights on the
Atlas vertical must become producible when the only attack-free history available is an unlabelled
declared-normal corpus. Concretely: the behavioural model may be fitted on the full attack-free
training file (HAI's ~60 h file; batch-distillation's dual-clean designed train), and the vertical
must still emit evidence whose weights satisfy Constitution §3.3's calibration requirement — or the
vertical must **refuse to claim** those weights are calibrated and say so in the report, rather than
starving the fit to feed isotonic.

The specific mechanism (identity weights with an explicit caveat, a one-class / conformal map, a
prior-only weight schedule, Platt/isotonic on a synthetic-free proxy, or something else that survives
review) is **left to the implementing session**. This ADR binds the *outcome and the measurement*,
not the recipe. Inventing labelled positives, tuning on the test set, or rewriting `_shrink` to make
the longer fit look good is forbidden.

**3. Frozen public rows are gates, not candidates for overwrite.**

| Row | Value | Rule |
| --- | --- | --- |
| HAI ungated Mahalanobis | 646.58 FP/normal-hour | Reproduce before any new number; never overwrite |
| HAI grouped vertical | 53.26 FP/normal-hour | Reproduce before any new number; never overwrite |
| Distillation ungated Mahalanobis | 18.72 FP/normal-hour (pre-0082 scoring) | Do not overwrite; ADR 0082 numbers use a new name |
| CERT 6B @ 48 | precision 0.104, recall 0.5 | Untouched |

Any quieter or differently calibrated result lands under a **new experiment name**. The sandbox
5,123→97 sweep remains a diagnostic citation, not a published operating point, until success below
is met under the new calibrator path.

**4. Success is measured on both HAI and batch-distillation.** A fix that helps only one corpus is
incomplete. Both measurements use seed 11, threshold 3.0, and report window recall, false positives
per normal hour, precision, and (for the vertical) whether evidence weights are claimed calibrated.

### HAI success

1. Reproduce 646.58 and 53.26 as a gate (abort on drift past the existing tolerance).
2. Fit the behavioural model on the **full** attack-free training file (~60 h), not on a
   `train_fraction=0.04` carve of the labelled file.
3. Produce a vertical (or explicitly scoped substitute) whose evidence-weight path does not require
   labelled positives to fit.
4. On the same scored slice the frozen vertical uses: report alert count, FP/normal-hour, and window
   recall under a **new** log name only when authorised to log. Window recall must remain **1.00**
   on the two labelled windows, or the report must state the loss.
5. Compare against the diagnostic anchors without selecting a best point from a sweep: the 0.48 h /
   5,123 and 60 h / 97 figures from ADR 0075 stay cited as diagnosis. A published quieter row is
   allowed only if it is produced by the new calibrator path, not by replaying the uncalibrated
   diagnostic.

### Batch-distillation success (ADR 0082 scoring)

1. Fit on the dual-clean **designed** train (attack-free; no unscored intervals in train — ADR 0082).
2. Score the prepared test under ADR 0082 rules: only class 2 is positive; classes 1 and 3 unscored;
   126 windows; ~73.12 normal hours. Recall is **perturbation recall**, never attack recall.
3. Produce calibrated (or honestly refused-as-uncalibrated) evidence weights **without** a three-way
   split that starves the fit. The labelled test file starts inside an anomalous window, so
   `train_calib_test_split` on it is not a viable vertical path today; the new calibrator must not
   depend on that split existing.
4. Report under a new sandbox or authorised log name: window recall, FP/normal-hour, precision,
   beside the sandbox `noboom-atlas-v1` baseline (**0.532** recall / **18.61** FP/hr / **0.709**
   precision). Improving **both** recall and FP/hr relative to that baseline is success; improving
   one by breaking the other is a measured negative and must be recorded as such.
5. Honest residual: if recipe-step coverage mismatch (train named-recipe share 7.7% vs test 38%)
   still dominates FPs after the calibrator change, say so. The calibrator session is not licence to
   invent a phase register or retune `atlas/templates.py`.

**5. Hypothesis confidence stays uncalibrated and unsurfaced.** This session is about **evidence
weights** on the vertical (ADR 0007), not about promoting hypothesis confidence to a user-facing
probability (Constitution §3.3). Conflating the two is a defect.

**6. Implementation is not done in this record.** No code lands with this ADR beyond the public-record
update ADR 0044 requires for opening the decision. The implementing session writes its own
`PROGRESS.md` entry, tests first, and appends to `log.jsonl` only when explicitly authorised.

## Consequences

**Gained.** The lever ADR 0075 named is no longer a tracker footnote. It has a number, a success
contract on two corpora, and a hard ban on publishing the diagnostic 97 as if the calibrator problem
were already solved.

**Cost.** Until the implementing session lands, the public HAI vertical remains the short-fit path
(53.26 grouped). Batch-distillation designed Mahalanobis remains the sandbox/ADR-0082 measurement
without a calibrated vertical. Operators still do not get the quieter queue the diagnostic showed is
geometrically available.

**Risks the implementing session must confront.**

- A weight schedule that ignores labels may be *worse* than isotonic on corpora that do have calib
  positives; HAI three-way with isotonic stays the comparison, not a straw man.
- Dropping calibration silently (shipping uncalibrated weights as if they were probabilities) is a
  Constitution §3.3 violation. Refusal or an explicit "uncalibrated weight" facet is allowed;
  lying is not.
- Fitting on 60 h may change which signals depart and may move ranking pathologies ADR 0068/0075
  documented; those must be remeasured, not assumed cured.
- On batch-distillation, a longer honest fit does not create recipe-step coverage the dual-clean
  train never had. Expecting the calibrator alone to clear the P702 flood is a likely failure mode
  and must be reported if it happens.
- Threshold search, `_shrink` retunes, and template matcher edits remain forbidden as ways to "make
  success look true."

## Alternatives considered

- **Publish the 60 h / 97 diagnostic as the new Atlas operating point now.** Rejected. That is the
  "Atlas V47, 97.3%" outcome ADR 0074/0075 exist to prevent. The calibrator question was unresolved;
  this ADR opens it rather than skipping it.
- **Keep isotonic; synthesise fake attack labels for calib.** Rejected. Invented positives are not
  ground truth; they would calibrate toward a fiction and still couple the fit to a labelled carve.
- **Drop the calibrator and surface `uncalibrated_confidence`.** Rejected. ADR 0007 measured that
  curve as not a probability (ECE 0.33–0.65). Constitution §3.3 forbids surfacing it.
- **Use Platt instead of isotonic.** Rejected as the fix. Platt also needs labelled positives; it
  does not unlock the declared-normal file.
- **Fit on designed train, calibrate on a three-way carve of the labelled file (status quo where
  possible).** Already available for some protocols; it is exactly what forces HAI's 0.48 h fit, and
  it is impossible on batch-distillation's test file (first observation is inside an anomalous
  window). Not a solution to the problem this ADR names.
- **Open Sentiel's non-saturating aggregation in the same session.** Rejected. Sibling lever, separate
  corpus, separate failure mode (ADR 0076). Pooling them would again optimise one engine while the
  other's contract is unsettled.
- **Retune `atlas/templates.py` or invent a distillation phase to absorb P702 FPs.** Rejected. Out of
  scope. Category lock and ADR 0082 stand.

## What the next session assumes exists

- This ADR's success contract.
- ADR 0075's diagnostic figures and report path (`eval_runs/atlas/hai-error-taxonomy.md`).
- Sandbox `noboom-atlas-v1` baseline under ADR 0082 scoring
  (`eval_runs/sandbox/noboom-atlas/`, never committed here — see the note in Context).
  <!-- evidence-ack: eval_runs/sandbox/noboom-atlas/ — never committed here; the note in Context says so and the figures cannot be re-checked -->
- Frozen log names listed above, unreproduced only as gates.
- No implementation yet.

## Implementation outcome (2026-09-24)

`NormalScoreCalibrator` (`normal-score-cdf`) landed in `phos.reasoning.calibration`. Measurement:
`scripts/evaluate_normal_score_calibrator.py` → `eval_runs/sandbox/adr0083-normal-score/`.

| Corpus | Result |
| --- | --- |
| HAI gate | 646.58 / 53.26 / 424 / recall 1.00 reproduced |
| HAI `hai[designed-normal-score][after]` | **31** grouped alerts, FP/hr **3.55**, recall **1.00** (vs frozen grouped 53.26; diagnostic 97 per-signal at 60 h → this path 99 per-signal) |
| Batch-distillation | Designed baseline and `designed-normal-score` both **0.548** recall / **20.19** FP/hr — detection **parity**, not improvement |

Weights carry `NORMAL_SCORE_WEIGHT_CAVEAT` (not attack probabilities). Dual-corpus success per §4 is
**not** met. On 2026-09-25 the HAI quieter row was **appended** to `eval_runs/log.jsonl` under
`hai[designed-normal-score][after]` (seed 11, commit of the implementing code) beside frozen
isotonic `hai[after]` 53.26 — not an overwrite. Distillation stays unlogged from this path.

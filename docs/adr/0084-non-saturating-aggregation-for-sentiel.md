# ADR 0084 — Non-saturating aggregation for Sentiel (session opened; not yet implemented)

- **Status:** Accepted — session opened 2026-09-27; **not implemented**. No code change, no
  measurement, nothing appended to `eval_runs/log.jsonl`.
- **Date:** 2026-09-27
- **PART:** Usefulness Phase follow-on (tracked at Gate 2 / ADR 0076; opened here)
- **Supersedes:** nothing. Does not rewrite ADR 0022, ADR 0076, or any frozen log row.
- **Depends on:** [ADR 0021](0021-sentiel-feature-enrichment-a-causal-trailing-history-and-the-budget-that-bounded-it.md),
  [ADR 0022](0022-peer-group-baselining-and-the-scoring-shape-that-survives-a-wide-feature-set.md),
  [ADR 0032](0032-precision-policy-lost-on-cert-at-48.md),
  [ADR 0044](0044-public-surfaces-on-main-must-move-with-every-advancement.md),
  [ADR 0065](0065-cert-6b-queue-autopsy-no-exclusive-stem.md),
  [ADR 0074](0074-the-usefulness-phase-is-defined-and-diagnosis-precedes-optimisation.md),
  [ADR 0076](0076-sentiel-fails-on-an-aggregation-ceiling-not-a-missing-corpus.md),
  [ADR 0083](0083-calibrator-without-labelled-positives.md)

## Context

U2 (ADR 0076) asked why Sentiel's frozen CERT r3.1 ruler —
`aggregate:gaussian:peer set (34 features)`, precision **0.104** at 48 alerts (5 TP / 43 FP),
window recall **0.5** — finds one labelled insider and not the other. The answer was an
**aggregation ceiling**, reached by arithmetic rather than search.

`AggregationPolicy` (`src/phos/sentiel/scoring.py`) scores an entity-day as a sum of one bounded
term per speaking feature, `1 - exp(-magnitude / 3.0)`. Every term is at most 1.0, so a day on
which *k* features spoke scores at most *k*. The 48-alert threshold is **13.700640148454447**, so
**at least 14 of the 34 features must speak at once for any entity-day to alert, whatever the
magnitudes** (`phos.sentiel.failure.features_required`). The squash also flattens depth: a feature
at magnitude 6.333 contributes 0.879, one at the out-of-band cut of 3.0 contributes 0.632.

On the committed report (`eval_runs/sentiel/cert-failure-classification.md`, seed 7, the 48-alert
point reproduced as a gate first):

| | `CSF0929` (scenario 1) | `CCH0959` (scenario 2) |
| --- | ---: | ---: |
| Labelled malicious entity-days | 11 | 42 |
| Alerted | 5 | **0** |
| Reachable, magnitudes too small | 1 | 11 |
| **Structurally unalertable** | 5 | **31** |
| Evidence absent | 0 | 0 |
| Best rank of any malicious day | 1 of 210,814 | 957 of 210,814 |
| Median score, malicious days | 10.995 | 4.500 |
| Median score, own ordinary days | 2.764 | 4.586 |

31 of `CCH0959`'s 42 malicious entity-days could not have alerted at any magnitude. The evidence
was not absent — every one of the 42 days had features speaking, the strongest at magnitude 6.33 on
`new_counterparties` — and the day was never outranked, because it was never a candidate.
`CSF0929` is found because a change from a near-zero baseline moves many correlated features at
once, which is the breadth the aggregation demands. ADR 0076 also recorded that the unit of
analysis is **not** the binding constraint: the episode ranks on `peak` and inherits the cap entire.

Gate 2 (2026-09-12) recorded the fix as `future_sessions.non_saturating_aggregation`,
**`tracked_not_authorised`**: the actual lever on Sentiel, and optimisation, which the phase
deferred until diagnosis was finished. Diagnosis is finished on both engines (ADR 0075, ADR 0076),
the Atlas sibling has been opened and implemented under ADR 0083, and Elijah has authorised this
session to open.

ADR 0076 was explicit about what it did **not** show, and this record inherits that limit rather
than softening it: *the ceiling proves the current aggregation cannot surface `CCH0959`; it does not
prove an alternative can.*

**This record opens the session and freezes its success contract. It does not choose the
aggregation, implement it, run it, or append a public log row.**

## Decision

**1. The session is opened.** Work that replaces the bounded per-feature sum with an aggregation
whose per-feature contribution is not capped at 1.0 — as an **opt-in, separately named** policy
beside the frozen one — is now in scope under this ADR. The usefulness tracker's
`non_saturating_aggregation` entry points here and moves to `adr_opened_not_implemented`.

**2. What "non-saturating" means, stated as a requirement rather than an algorithm.** An
aggregation qualifies only if:

- **Depth can reach the cut.** There is no *k* below 34 such that a day with *k* speaking features
  is guaranteed never to alert, for any finite quantified magnitude. Equivalently, the score is not
  bounded above by the count of speaking features.
- **It is a change of functional form, declared before any labelled measurement.** Raising the
  numerical value of the cap (1.0 → *c*), raising `score_scale`, or lowering the threshold does not
  qualify. Raising `score_scale` makes each term smaller and leaves the ceiling at *k*; raising the
  cap to *c* moves it to *c·k*, a tuned number on two insiders. Gate 2's `must_not` "raise a cap"
  stands against those moves.
- **It keeps the properties the bounded sum was built for** (`scoring.py` module docstring), or
  names which one it gives up and why: monotone in every magnitude and in the count of speaking
  features; order-independent; reconstructable, so the contributions sum to the score (Constitution
  §3.2); no calibrated-probability claim (Constitution §3.3).
- **It does not reopen PART 6A's floor.** The cap exists because a feature with no spread clamps to
  `MAX_MAGNITUDE` (1e6), and under PART 6A that produced an irreducible **1,668-alert floor with no
  true positive** (ADR 0022). An unbounded form must bound or exclude **unquantified**
  contributions explicitly, and keep counting them in `ScoringSummary.unquantified`. One unmeasured
  departure must not be able to lead the queue by itself.
- **It treats all 34 features symmetrically.** `feature_weights` and `stem_weights` stay empty in
  every candidate. ADR 0076 already told this project which features moved for `CCH0959`
  (`new_counterparties`, `removable_device_connects`); a weight on either one is fitting to the
  answer and is forbidden.

**3. The shape of the design space, named so the implementing session starts from the
constraints rather than from a blank page.** The mechanism is left to that session; these are the
families it is expected to weigh, each with the cost this record can already see:

| Family | Form (per entity-day) | What it buys | What it risks |
| --- | --- | --- | --- |
| Linear excess | `Σ max(0, m_i − emit_k)` over quantified features | Depth counts in proportion; simplest reconstructable form | One extreme benign feature leads; scale differs across feature kinds |
| Tail-probability sum | `Σ −log p_i`, with `p_i` each magnitude's tail probability under its own fitted reference | Grows like `m²/2`; the principled combination for independent evidence | Features are **not** independent: count, `_dev`, `_peer`, `_diff`, `_trend` of one stem move together, so it multiplies ADR 0021's redundancy |
| Family-first | Max (or mean) **within** a behaviour family, then an uncapped sum **across** families | Removes the redundancy that makes breadth cheap for scenario 1 and expensive for scenario 2 | May cost `CSF0929`, who is found *because* of that redundancy (ADR 0076 item 8) |
| L*p* norm | `(Σ m_i^p)^(1/p)`, `p` declared, not searched | One knob between breadth (`p = 1`) and depth (`p → ∞`) | A knob is a search target; `p` must be fixed before labelled measurement |

At most **three** candidates may be declared. All are measured and all are reported; none is
selected by its labelled result.

**4. Frozen public rows are gates, not candidates for overwrite.**

| Row | Value | Rule |
| --- | --- | --- |
| CERT 6B @ 48 (`aggregate:gaussian:peer set (34 features)`) | precision 0.104, window recall 0.5, 5 TP / 43 FP | Reproduce via `measure_sentiel_episodes.check_frozen_row` before any new number (threshold `13.700640148454447`, 210,814 entity-days, abort past 1e-12); never overwrite |
| ADR 0076 classification | 14 required; `CCH0959` 31 structurally unalertable / 11 reachable / 0 alerted | Reproduce under the **frozen** policy as the second gate |
| `:precision` @ 48 | 0.083 (a loss, ADR 0032) | Untouched |
| `sentiel-episode:peak` | 9 malicious entity-days at 48 (ratio withdrawn, R18) | Untouched; episode coverage is **not** re-measured in this session |

`AggregationPolicy()` must remain byte-identical to the PART 6B scorer. A new aggregation lands
under a **new detector name** through `AggregationPolicy.log_tag`, and the code must refuse a
non-saturating policy with an empty tag, so it cannot write under the frozen name.

**5. Overfitting to two known insiders is the central risk, and the contract is built around it.**
CERT r3.1 has two labelled insiders and 53 malicious entity-days in 210,814. Every labelled number
this session produces is a test-set number, and the project already knows the answer key in
detail. So:

1. **Pre-registration by commit.** The candidate forms and every parameter are fixed and pinned by
   a test in a commit that **precedes** the first commit containing any labelled CERT measurement
   of them. The implementing session records both SHAs in this ADR's outcome section. A candidate
   added after labelled results exist is a new session.
2. **Label-blind development only.** Before that commit, the session may use unit tests, the
   `dataset library/IT/` fixture (which is not CERT, ADR 0029), and **unlabelled** CERT statistics
   — the score distribution, how often the top of the queue is led by a single feature, the
   unquantified share. It may not look at either insider's days, ranks or scores under a
   candidate.
3. **No threshold, budget or parameter search.** The decision point is the frozen 48-alert
   budget. The full alert curve is reported, and no point on it is selected after the fact.
4. **Symmetric features** (Decision 2) and **no named subset** (ADR 0065).

**6. Inflating precision artificially is the second risk, and precision alone cannot carry a
claim.** At 48 alerts, precision moves in steps of 1/48 and can be raised without finding anyone
new: pulling more of `CSF0929`'s eleven malicious days into the queue lifts it while window recall
stays 0.5. That is "the same insider, more days", and it is reported under that name. Every
precision figure is broken down by insider, beside the count of distinct entities in the top 48.
A precision gain with unchanged window recall is **not** success.

**7. Success is measured on CERT r3.1, under the same evaluation standards as the frozen row.**
Same corpus, same train/test split, seed 7, same 34 features, same fitted model, same
`evaluate_entity_aware` metric math, FP denominator in normal user-hours, 210,814 test entity-days.
Only the aggregation changes.

1. **Gates.** Reproduce the 48-alert row and the ADR 0076 classification under the frozen policy,
   exactly, before any candidate is scored.
2. **The decision criterion, fixed now.** A candidate **surfaces `CCH0959`** if and only if at
   least one of their 42 malicious entity-days is in its top 48 **and** `CSF0929` is still in its
   top 48 — window recall **1.0** at 48. Anything else is a measured negative, including finding
   `CCH0959` by losing `CSF0929`.
3. **Reported for every candidate, win or lose:** window recall; precision with TP by insider;
   false positives; sample recall; distinct entities in the top 48; `CCH0959`'s best rank (against
   **957**); and a re-run of ADR 0076's visibility classification under the candidate — how many of
   `CCH0959`'s days remain structurally unalertable and how many are reachable but sub-threshold.
   That last split is what says whether the ceiling or the magnitudes were binding.
4. **Chance, computed by the runner.** Any insider-level result is reported beside the probability
   of the same outcome under a label-free null computed by the committed runner — at minimum a
   uniform ranking and ADR 0076's within-entity reshuffle. This record does not assert those
   figures; ADR 0076's process lesson is that a figure in a PHOS record comes from the runner or
   does not appear.
5. **Floor and flood.** The full alert curve is reported, and the session states whether a floor
   of alerts with no true positive reappears, as it did under PART 6A.
6. **Log discipline.** Results land first under a sandbox report
   (`eval_runs/sentiel/non-saturating-aggregation.md` and `.json`; BET-001 was declared in
   <!-- evidence-ack: eval_runs/sentiel/non-saturating-aggregation.md — BET-001 was declared in ADR 0093 and never run (ADR 0145), so the file was never written -->
   ADR 0093 and not run, ADR 0145, so neither file was ever written). A row reaches
   `eval_runs/log.jsonl` only when separately authorised, under the new name, beside 0.104.

**8. The expected outcome is recorded before the measurement, so a negative cannot be a surprise.**
ADR 0076's own figures give four reasons to expect this fix to be **necessary and not sufficient**.
Eleven of `CCH0959`'s days already had the breadth and still fell short. Their malicious days score
**below** their own ordinary days at the median (4.500 against 4.586). Against their own pre-attack
history, no feature shifts by more than z = 1.27 (`distinct_pcs_peer`, the largest in the committed
report, as ADR 0081 corrected R15 to say); `removable_device_connects` shifts by 1.07 and
`new_counterparties` by 0.41. And the strongest magnitude on any of their days, 6.33, sits well
below the 18.768 reached elsewhere in the run, so an aggregation that rewards depth rewards the
population's most extreme single-feature days first, and those are not `CCH0959`'s. If `CCH0959`
stays outside the top 48, that is a **permitted and valuable** outcome (ADR 0074): it moves the
binding constraint from the aggregation to the feature space, by measurement rather than by
argument. That is register R16: the 34 features count *how many* hosts and recipients, never
*which*.

**9. Implementation is not done in this record.** No code lands with this ADR beyond the public
record ADR 0044 requires for opening it. The implementing session writes its own `PROGRESS.md`
entry, writes tests first, and appends to `log.jsonl` only when explicitly authorised.

## What would need to change in the code

Named so the implementing session's scope is visible now. **None of it is changed here.**

- **`src/phos/sentiel/scoring.py`.** An opt-in aggregation selector on `AggregationPolicy`, whose
  default is the current bounded sum so `AggregationPolicy()` stays the PART 6B scorer.
  `FeatureContribution.contribution` is validated `le=1.0`: that holds for the bounded form and has
  to become form-aware rather than being deleted. `_weights_are_strictly_positive_and_at_most_one`
  justifies its upper bound by "the per-feature ceiling", and needs restating for a form without
  one. `WindowScorer._contribution` is where unquantified magnitudes (`MAX_MAGNITUDE`) are handled
  and where the new form must bound or exclude them. `_rescaled`, used by the peer-match, family-gate
  and chronic-volume factors, multiplies contributions and needs a test on unbounded terms;
  combining the new form with `precision_policy()` is **out of scope**. `ScoredWindow.as_detection`
  squashes the total score through `uncalibrated_confidence`; it stays uncalibrated and unsurfaced.
  The module docstring's "No single feature can dominate" is a claim about the bounded form, and a
  new form must state what replaces it.
- **`src/phos/sentiel/failure.py`.** `score_ceiling`, `features_required` and `day_ceiling` are
  arithmetic about the bounded sum. `depth_blind_ceiling_notice()` hard-codes PART 6B's threshold,
  and U4 prints it with every Sentiel render (Gate 2's binding condition, register R24). The notice
  must stay true for the frozen policy, must not be printed for a policy where it is false, and
  must not be dropped silently. It becomes policy-aware or explicitly scoped to the bounded form.
- **Runner.** Either an extension of `scripts/classify_sentiel_failures.py` or a new
  `scripts/measure_sentiel_aggregation.py` — neither was written, because BET-001 was not run (ADR
  <!-- evidence-ack: scripts/measure_sentiel_aggregation.py — never written, because BET-001 was not run (ADR 0145) -->
  0145) — that runs both gates, scores each declared candidate from the same trace cache
  (`traces.py`), re-runs the visibility classification per candidate, computes the nulls, and
  writes the sandbox report. `scripts/evaluate_sentiel_baseline.py` gains a CLI flag in
  `_aggregation_policy` only if a log row is later authorised.
- **Unchanged by construction.** `engine.py`, `autopsy.py` and `phos/library/evaluate.py` construct
  `AggregationPolicy()` with defaults and do not move. `episodes.py` reads a quantile floor and
  `peak`, and is not re-run for claims here. `featurise.py`, `peers.py`, `templates.py` and every
  threshold are untouched. New symbols are imported from their submodules and not re-exported
  through `phos/sentiel/__init__.py`, following ADR 0075 and ADR 0076.
- **Tests.** `tests/sentiel/test_scoring.py`: the default stays byte-identical; the new form is
  monotone, order-independent and reconstructable; an unquantified feature cannot lead the queue
  alone; an empty `log_tag` is refused. `tests/sentiel/test_failure.py`: the ceiling functions and
  the notice behave correctly per form. `tests/sentiel/test_public_row_freeze.py` stays green and
  unedited. A test pins the declared candidates and their parameters, and that test is part of the
  pre-registration commit.

## Consequences

**Gained.** The lever ADR 0076 diagnosed is no longer a tracker footnote. It has a definition that
excludes the cheap moves, a success criterion fixed before any candidate exists, a named failure
mode for each way the result could flatter itself, and a prediction on record.

**Cost.** Until the implementing session lands, 0.104 at 48 remains Sentiel's number, `CCH0959`
remains invisible, and every Sentiel render keeps printing the 14-of-34 notice. Opening a session
is not a result.

**Risks the implementing session must confront.**

- **Two insiders cannot carry a ratio** (R18). Window recall moves in steps of 0.5, and a success
  here is one person found by one declared aggregation on one corpus. It does not generalise, and
  no second labelled enterprise corpus is available to check it (ADR 0067 keeps r4.2 events
  closed).
- **Trading one insider for the other.** A depth-favouring form may drop `CSF0929`, who is found by
  breadth. The criterion counts that as failure, and the report must show it.
- **A flood from depth.** Removing the cap rewards the single most extreme feature on any day. If
  the top 48 fills with one-feature benign days, precision falls and the report says so.
- **Correlated families.** A form that treats features as independent evidence compounds the
  multiplicity ADR 0021 bounded as a false-alarm cost.
- **Contamination by what is already known.** ADR 0076 published which features spoke for which
  insider. The symmetric-feature rule and the pre-registration commit are the defences, and the
  session states in its outcome that it held to both.
- **The ceiling notice drifting.** If the notice is edited for the new form and stops being true
  for the frozen one, U4 renders become dishonest in exactly the way Gate 2 forbade.

## Alternatives considered

- **Raise the cap, raise `score_scale`, or lower the threshold.** Rejected (Decision 2). None
  removes the ceiling, and each is a number tuned against two insiders.
- **Up-weight `new_counterparties` and `removable_device_connects`.** Rejected. That is the answer
  key written into the detector.
- **Score the subset of features `CCH0959` moved.** Rejected. ADR 0065 already refused the
  named-subset move on this corpus.
- **Train a supervised combiner on the labels.** Rejected. Two positive entities are not a training
  set, and the result would be a detector fitted to its own test.
- **Add a counterparty-identity feature (R16) in the same session.** Rejected. It is the other
  lever ADR 0076 named, and if both moved together no one could say which one found `CCH0959`. If
  this session's result is negative, R16 is the natural next session, under its own ADR.
- **Change the episode unit instead.** Rejected. ADR 0076 showed the episode inherits the ceiling
  through `peak`, and the episode statistics sit inside a reshuffle null.
- **Open this session together with the Atlas calibrator.** Not applicable now. ADR 0083 kept the
  two apart and has since landed. This session does not touch Atlas.
- **Leave it tracked indefinitely.** Rejected by authorisation. Diagnosis is complete on both
  engines, and ADR 0076 itself names this as the next thing to measure.

## What the next session assumes exists

- This ADR's definition, success criterion and pre-registration rule.
- ADR 0076's report and JSON (`eval_runs/sentiel/cert-failure-classification.md` / `.json`) and
  its runner (`scripts/classify_sentiel_failures.py`).
- The frozen 6B row and `check_frozen_row` as gates.
- The trace cache (`traces.py`, `fast_intake.py`) for re-scoring without re-reading CERT.
- No implementation yet.

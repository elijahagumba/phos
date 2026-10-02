# ADR 0075 — The HAI false-alert load is modelling error, not missing evidence

- **Status:** Accepted
- **Date:** 2026-09-11
- **PART:** Usefulness Phase, item U1 (Atlas error taxonomy)
- **Supersedes:** nothing
- **Depends on:** [ADR 0018](0018-phase-conditional-modelling-for-a-batch-process.md),
  [ADR 0051](0051-saturated-fp-load-is-a-refused-claim.md),
  [ADR 0065](0065-cert-6b-queue-autopsy-no-exclusive-stem.md),
  [ADR 0068](0068-the-atlas-operator-queue-cannot-be-ranked.md),
  [ADR 0074](0074-the-usefulness-phase-is-defined-and-diagnosis-precedes-optimisation.md)

## Context

`atlas-vertical:atlas-mahalanobis+isotonic/subsystem-events` is a frozen public row: **53.26** false
positives per normal hour on HAI, window recall 1.00, **424** subsystem events over 7.89 normal
hours, of which 6 overlap a labelled attack (ADR 0068). It has only ever been treated as a quantity
to reduce. ADR 0074 forbids reducing it and requires understanding it first, and names the question
that decides the rest of the phase: **what kind of uncertainty is generating these alerts?**

The answer matters because the two candidate answers point in opposite directions. If *modelling
error* dominates, the answer is a better model and the work is ours. If *insufficient context*
dominates, the answer is evidence PHOS does not have — a work order, a mode register — and no amount
of algorithm work will help. PHOS could not previously tell which it was in.

ADR 0068 left one observation explicitly undiagnosed: "more than a quarter of the queue is pinned in
a band 0.03 wide near magnitude 10.10, and the whole of that block falls in a contiguous stretch from
22:54 to 02:05 — hours after the 20:21–21:04 attacks."

## Decision

**1. The taxonomy is a new analysis stage in `phos.eval`, and it decides nothing by assumption.**

`src/phos/eval/taxonomy.py` classifies alerts; `taxonomy_evidence.py` holds the measurements its
verdicts rest on, so no figure in a report is transcribed; `taxonomy_report.py` renders it.
`scripts/classify_atlas_alerts.py` runs it. `templates.py`, `grouping.py`, `multivariate.py` and
every threshold are untouched. Nothing appends to `eval_runs/log.jsonl`; the report lands in
`eval_runs/atlas/hai-error-taxonomy.md`, following ADR 0065 and ADR 0068.

**These three modules are deliberately NOT re-exported through `phos/eval/__init__.py`**, against the
package's own "import everything public from here" convention. Two Sentiel contract tests assert that
`git diff HEAD -- src/phos/eval` is empty — the strongest available statement that the PART 2 harness
was reused exactly as Sentiel found it (`tests/sentiel/test_evaluation.py`,
`tests/sentiel/test_featurise.py`). Adding modules to the package does not breach that; editing its
`__init__` would, because that is the surface those tests pin. A first draft of this session did edit
it and turned both tests red. Callers import from the submodules, and a later session that wants the
re-export needs its own ADR acknowledging which contract it is spending.

**2. The frozen rows are reproduced as a gate, by the code that has always measured them, before any
new number exists.** 646.58 ungated, 53.26 grouped, 424 events, recall 1.00 — compared to four
decimal places, and the run aborts on drift. A taxonomy of a different alert set is a taxonomy of
nothing.

**3. The ten candidate categories are not a partition, and the record says so.** Eight answer *what
was the plant doing*; two answer *why did the model speak*. An alert can be truly described on both
axes at once and usually is. Every alert therefore carries a `primary_category` **and** the full set
of `co_firing` categories.

**4. Each category is first screened for whether the corpus carries its evidence at all.** Three
verdicts, and only `assigned` lets a category compete. A `not_separable` screen must state **what
would lift it**, so the screen is a specification rather than a shrug. A screen marking a category
`assigned` when no per-event discriminator exists for it is a hard error — otherwise its zero would
read as a measurement.

**5. The deciding instrument is the same fitted model applied to declared-normal data it never saw.**
HAI's own 60-hour attack-free training file, which the script refuses if it declares any attack
interval. No label on the judged side is consulted and no threshold is chosen: the band is the one
the model already reports.

**6. Attribution between the axes is a counterfactual settled by measurement.** Replace the plant's
behaviour with declared-normal behaviour and the alert still occurs; so the plant's behaviour is not
the condition without which it would not exist. `MODEL_FAULT_PRECEDENCE` states this in one place.
It is deliberately **not** keyed on the band-versus-spread comparison, because that puts a
conditional band beside a marginal standard deviation and a correct conditional band is legitimately
narrower. Where no model-side category fires, the plant-side reading takes the slot — so the
procedure cannot only ever answer "modelling error".

## Measured on HAI, seed 11, threshold search forbidden

`eval_runs/atlas/hai-error-taxonomy.md`.

**7. The queue is 424 alerts and 15 phenomena.** 15 distinct (subsystem, departing-signal-set)
signatures in 132 contiguous runs. One signature — `P1_B400B`, `P1_FT02`, `P1_FT02Z` on `p1-boiler` —
is **221 events, 52% of the whole queue, in two runs** spanning 22:11–02:47. Only **9 of 79** signals
ever depart.

**8. Four categories are refuted by measurement, not by assumption.**

| Category | Basis |
| --- | --- |
| `communication_artefacts` | All 2,851 inter-sample intervals exactly 10.0 s; 0 duplicate timestamps; 0 duplicate rows |
| `startup_shutdown_transition` | All 15 declared run-state signals constant across all 7.92 h; 0 moved |
| `grade_or_recipe_change` | No declared mode or setpoint change anywhere in the slice |
| `sensor_noise` | Lag-1 jitter within 1.5× of declared normal on all 9 departing signals (medians 0.76–1.05, p99 0.86–1.02) |

**9. Two are not separable, and both append to the refusal register.** `maintenance` — HAI carries no
work-order, operator-identity or mode-register column, 0 of 79. `equipment_ageing` — three signals
drift (ρ to −0.54 against −0.14 on the reference) inside envelopes unmoved to within 0.1%, while the
one signal whose envelope moved materially shows no trend.

**10. Modelling error accounts for 418 of 418 false alerts. The residual in `not_separable` is 0.**

The model exceeds its own reported band on **55.74%** of moments across the 60-hour declared-normal
file, against **55.81%** of the scored slice's normal moments. The same 8 signals exceed, at the same
rates, to the same maxima. Every one of the 418 false alerts has a departure no larger than one the
model produces on data the corpus declares attack-free; **none exceeds it**. The alert load is the
model's out-of-sample behaviour on ordinary operation.

**11. The mechanism has three measured parts.**

- `shrinkage_floor_mixed_scale` (ADR 0018). 44 of 52 fitted signals share a conditional spread of
  **277.9568140855581**, which is exactly `sqrt(0.05 × 1,545,199.81)` — the Ledoit-Wolf floor, set in
  raw units by the plant's largest-scale tag (`P1_PP01AD` ≈ 540,833). Agreement to nine significant
  figures; this is measured, not inferred.
- **Bands narrower than the signals' own normal variation.** For `P1_FT02`, `P1_FT02Z`, `P1_B400B`,
  `P3_LCV01D` and `P3_LCP01D` the band is narrower than the signal's declared-normal standard
  deviation. Those signals are the strongest member of **360 of 424** events. Such a signal must
  alert in normal operation; that is arithmetic.
- `mixed_modes`, as a fit shorter than one duty cycle. `P1_B400B` has a first autocorrelation peak at
  **3.15 h**; the fit window is **0.48 h — 15% of one cycle**. Other departing signals cycle out to
  17.04 h.

**12. The contribution is quantified by a fit-length sweep, and it costs no recall.** Same model
class, same threshold 3.0, same seed, same scored slice, same 52-signal space; only the fit set's
length varies. 0.48 h → 5,123 alerts, 55.96% of moments. 60.00 h → 97 alerts, 2.49%. **The transition
is a step, not a slope**: it falls between 3.89 h (4,111 alerts) and 4.86 h (186 alerts) — the first
fit length past `P1_B400B`'s 3.15 h period — and the curve then flattens near 2.4% rather than going
to zero, which is what a fit still shorter than the slowest signal's 17.04 h cycle should look like.
**Window recall is 2 of 2 at every fit length tested.**

**13. The 0.48 h fit is a consequence of where the labels live, not an oversight.** The vertical needs
labelled positives to fit its isotonic calibrator; the declared-normal file carries none; so it splits
the labelled file three ways; and HAI's attacks fall early enough in that file that `train_fraction`
must be 0.04 to leave any attack in the scored slice. The already-logged `hai[designed]` row — which
does fit on the 60-hour file — reads 116 alerts at 8.78 FP/normal-hour, uncalibrated.

**14. ADR 0068's undiagnosed band is resolved.** 10.10 / 10.11 is the **ceiling of the
`P1_B400B`/`P1_FT02Z` departure geometry under this model**, reproduced identically on 60 hours of
declared-normal data containing no attack. It is not an operating-point shift peculiar to the test
slice, and not a saturating distance in the sense ADR 0068 offered as a possibility.

**15. ADR 0068's ranking refusal now has a mechanism.** Four of the six true alerts sit on signals
this model flags on 14.21%, 10.56% and 4.43% of declared-normal moments, with magnitudes (7.885,
7.223, 6.082, 4.439) all **below those signals' declared-normal maxima** (9.460, 6.140, 10.129).
Nothing about those four distinguishes them from the 418 false ones. No severity can rank a queue in
which the true items are inside the model's own normal-operation noise.

**16. `P2_CO_rpm`'s separation is recorded and REFUSED as a detector (register R13).** It is the one
signal whose departure is unprecedented against ~71 h of declared-normal data (max 0.308 there;
3.648 and 3.772 inside attack window 2). **n = 1 signal, 2 events, 1 of 2 windows, 1 corpus.**
Promoting it would fit a sign to two attack windows on the only corpus with a declared topology —
the move ADR 0068 already rejected. It must not be quoted as a detection result.

**17. Frozen rows are untouched.** 646.58, 53.26, 424, recall 1.00, distillation 18.72 (8.6×), CERT
6B 0.104 at 48, command-lead 0/16 and 1/4 unpooled all stand. The taxonomy's own figures are a
diagnostic instrument under its own name and are **not** re-derivations of any of them.

## Consequences

**Gained, and it redirects the phase.** The HAI false-alert load is explained, and the explanation is
ours rather than the world's: the evidence needed to remove those alerts is already inside the corpus.
The phase's working assumption that more evidence is the bottleneck is **wrong for this number**. It
remains right for maintenance and mode attribution, which is where U3's synthetic environment is
aimed and which this finding leaves exactly as blocked as it was.

**Gained, second.** 53.26 FP/normal-hour was never one phenomenon. It is 15 signatures, 132 runs, and
a single persistent condition that is over half the queue. An operator's experience of the queue was
being described by a rate that could not express it.

**Cost, and it must not be papered over.** This ADR does **not** make Atlas quieter. No threshold
moved, no model was refitted for a public row, and 53.26 is still the number. Knowing that a 60-hour
fit would read 97 alerts instead of 5,123 is not permission to publish that; doing so needs its own
session, its own ADR, and an honest account of what the calibrator does without labelled positives —
which is the thing that forced the short fit in the first place.

**Cost, second.** The `not_separable` residual is 0 for a structural reason rather than a reassuring
one. Only 4 of 10 categories reach a per-event test at all; the other 6 are settled by the screen. A
reader who takes 0 as "nothing was ambiguous" has misread it, which is why the report says so in the
residual's own paragraph and why register entry R12 exists.

**Unexplained, and named rather than papered.** Why the curve flattens at ~2.4% of moments rather than
approaching zero is attributed here to signals whose cycles (to 17.04 h) exceed even the 60-hour fit's
ability to characterise them from 21,601 samples, but that attribution was **not** tested by extending
the reference, because no longer HAI capture exists. It is a hypothesis with a mechanism, not a
measurement.

**What this points at.** Three things, none started. A calibrator that does not need labelled
positives, since that requirement is what produced the 0.48 h fit. `ShrinkageTarget.CORRELATION`
(ADR 0018 Option A, already shipped as a named option, not the default) measured against the floor
this session quantified. And a declared mode register, which is the single piece of context that would
move `grade_or_recipe_change`, `mixed_modes` and `maintenance` at once.

## Alternatives considered

- **Report the 60-hour fit as a new Atlas operating point.** Rejected, and this is the tempting one.
  ADR 0074 forbids reducing the number in this item, the calibrator question is unresolved, and a
  53× quieter row published the same session that diagnosed the cause would be exactly the
  "Atlas V47, 97.3%" outcome the phase was written to avoid.
- **Assign the 418 to `normal_process_variation`, since every reading is in range.** Rejected. 5,117
  of 5,123 member departures do sit inside the declared-normal envelope, and that is recorded as
  co-firing on all 418 — but a marginal envelope test is too weak to carry the primary slot. An
  individually-in-range reading whose joint departure is unprecedented is what a subtle attack looks
  like, and calling it normal variation would be the joint model arguing against itself.
- **Split `modelling_error` into its three mechanisms as three categories.** Rejected. The three
  co-occur on the same events — a floored band on a signal whose cycle the fit never saw — and
  splitting them would require a tie-break rule the data does not supply. They are reported as
  mechanism beside one category instead.
- **Use the 3.5-hour same-day calib slice as the reference instead of the 60-hour file.** Rejected as
  the primary, kept as the sensitivity that bounds the finding: against it, 185 of 418 alerts look
  unprecedented, against the 60-hour file none do. The verdict depends on how much declared-normal
  data is held, and `SignalReference.reference_hours` travels with every verdict so a reader cannot
  miss it.
- **Conclude `insufficient_context` because the fit window's shortness is itself a corpus-shape
  problem.** Rejected as the primary reading, and it is a real argument. HAI's attacks falling early
  is a fact about the corpus, not about Atlas. But the evidence that removes the alerts — 60 hours of
  declared normal — is *in the corpus and on disk*, so the limit is in the protocol that does not
  reach it. That is modelling error under any useful definition.
- **Drop `equipment_ageing` for being undecidable.** Rejected, following ADR 0068's treatment of
  `breadth`. Measuring that 2.5 days of data cannot separate a duty-cycle phase from a degradation is
  the result, not a nuisance, and it is what register entry R9 is for.

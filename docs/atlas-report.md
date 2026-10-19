# Atlas — status report

**Engine:** Atlas (industrial / OT) · **PARTs covered:** 5A, 5B, 5C · **As of:** 2026-08-11 ·
**Commit:** `eb561da` · **Status:** complete as specified; not deployable

---

> **Superseded as Atlas's current status.** This report records Atlas as it stood in August 2026,
> and its numbers and verdict describe that design. Since 7 October Atlas's detector is
> `atlas-v1-consistency` ([ADR 0107](adr/0107-the-consistency-detector-enters-the-engine.md)),
> measured by attacks caught within the 8 alerts an operator can read in a shift: on HAI 21.03,
> 22.04 and 23.05 it caught 42 of 50, 53 of 58 and 36 of 52, against 36, 10 and 6 for the best
> baseline checked, above every random draw of the same budget
> ([ADR 0116](adr/0116-a2-status-four-of-five-beyond-chance.md)). Current results are on the
> [record page](README.md). The report below is kept as written.

> **Scope and currency.** This is a point-in-time record of Atlas at PARTs 5A to 5C, kept as written
> rather than revised. Work has landed since, and two statements below have been overtaken by it.
> The packet adapter this report lists as missing was built in PARTs P1 to P3, which retired the two
> stability stubs
> ([ADR 0014](adr/0014-command-evidence-the-second-boundary-door-and-the-unrun-measurement.md)).
> A synthetic plant simulator and an adversarial breaking harness followed in PARTs D1 to D3
> ([ADR 0017](adr/0017-the-breaking-harness-fingerprint-classification-and-judging-from-true-state.md)),
> and phase-conditional modelling in A-FIX-1
> ([ADR 0018](adr/0018-phase-conditional-modelling-for-a-batch-process.md)), then a settling
> allowance for phase changes in A-FIX-2
> ([ADR 0019](adr/0019-the-settling-allowance-and-the-blind-window-it-is-bounded-by.md)), which also
> established that three of A-FIX-1's twenty "caught" batch-reactor attacks had been credited to a
> false positive that fires at every CHARGE→HEAT transition, attacked or not.
>
> The HAI figures in this report are unaffected by that work: phase-conditional modelling is
> selected per plant and HAI declares no phase register. Results against the simulated plants are
> reported in ADR 0017 and ADR 0018, not here.
>
> **Later HAI work, none of which overturns the numbers below.** §6 item 5 asked for predictive
> behaviour; it was measured and it **lost**: `model:atlas-var1` posts **14071.07** FP/normal hour
> against this report's 646.58, and is refused as the HAI detector
> ([ADR 0064](adr/0064-var1-on-hai-is-louder-than-snapshot-mahalanobis.md)). Correlation-target
> shrinkage could not be fitted at all on the same split
> ([ADR 0066](adr/0066-correlation-target-cannot-invert-on-hai.md)). A declared three-role transfer
> from BATADAL is louder still at 1078.99
> ([ADR 0063](adr/0063-declared-physical-roles-unblock-cross-plant-measurement.md)). §5's 0.034
> weight ceiling turned out to be worse than a ceiling: on the 424-event operator queue the
> calibrated weight is a **single value**, and no severity Atlas carries ranks that queue towards
> the incidents ([ADR 0068](adr/0068-the-atlas-operator-queue-cannot-be-ranked.md)). §6 item 3's
> packet adapter exists; §6 items 1, 2 and 4 are still open.

## 1. What Atlas is

Atlas is the industrial half of PHOS. It answers one question about a running plant — *is this
still the machine we learned?* — and, when the answer is no, produces a set of competing
explanations with the evidence for and against each, rather than an alert.

Its thesis is a modelling claim, not an engineering preference:

> An industrial environment is not a collection of independent signals. It is one machine. A pump's
> flow moves with a valve's position; a tank's level with its inflow and outflow. Normal operation
> therefore lives on a low-dimensional manifold of correlated behaviour, and the right question
> about a reading is not "is this signal high?" but "does this reading still fit the plant?"

That claim was worth testing because the alternative had already been measured and had failed.
PART 3's per-signal Gaussian — one independent baseline per signal — posts **8,389.81 false
positives per normal hour** on HAI's 79-signal corpus. Not a tuning failure: modelling 79 signals
as 79 strangers means ordinary correlated movement looks anomalous in isolation, and across dozens
of signals the false alarms compound.

Atlas is now a complete vertical: raw industrial telemetry in, explainable competing-hypothesis
narrative out, every number traceable back to a measurement.

---

## 2. What was built

| PART | Modules | What it added |
|---|---|---|
| **5A** | `vectorise.py`, `multivariate.py`, `stability.py` | The joint models — the plant as one machine |
| **5B** | `topology.py`, `data/hai/topology.toml` | The declared map of which signals share a physical unit |
| **5C** | `grouping.py`, `templates.py`, `engine.py` | The collapse, the OT explanations, and the vertical |

**2,875 lines** of engine across eight modules, **3,602 lines** of test across nine, **229 Atlas
tests**, `src/phos/atlas/` at **100% line and branch coverage**. `mypy --strict` and `ruff` clean.
Four evaluation scripts produce every number quoted here and append it to `eval_runs/log.jsonl`
stamped with commit and seed.

### 5A — the models

Two joint models, chosen because they fail differently:

- **`MahalanobisModel`** keeps the whole correlation structure in the inverse covariance. The
  expected value it reports for a signal is the *conditional mean* given every other reading at
  that instant. "Given the rest of the plant, this should have read 140.2 ± 0.6; it read 100.0" is
  not an analogy — it is what the number is.
- **`PcaResidualModel`** keeps a rank-limited summary and scores by reconstruction error.

Both stay explainable. A joint anomaly score is naturally a scalar — "this moment is unusual" —
which would be a black box and a §3.2 violation. Instead both answer two questions per signal per
moment (what did the rest of the plant imply this should read, and how far does a reading normally
sit from that), and emit an ordinary `Deviation` carrying a **dynamic** `ExpectedRange` centred on
the implied value. Everything downstream consumes it with no special case.

`vectorise.py` exists as a separate module because reshaping observations into a `(time × signal)`
matrix forces exactly one judgement call — a signal with no reading at some timestamp — and the
tempting answer, a zero, fabricates a measurement. The policy is carry-forward for a bounded number
of rows, else drop the timestamp, never substitute. **A carried cell can never raise a deviation:**
it informs the reconstruction, but there is no measurement at that instant to point back to.

### 5B — the map

Which signals sit on the same piece of plant. Not a statistic — a claim about plumbing, written
down, sourced to documentation, and never derived from the data.

The rejected shortcut is to cluster signals by co-movement and call the clusters subsystems. It is
circular: grouping exists to answer "did these deviations share a cause?", so deriving membership
from co-movement answers that question with the same statistics that raised the deviations. The
reduction would be real in the log and meaningless in the plant — and the failure would be
invisible, because a tighter cluster yields a better number.

Enforcement rather than aspiration: every `Subsystem` carries a mandatory `source` naming its
documentation, `render_topology` prints the whole map for a domain expert to falsify by eye, and a
test asserts no authored source cites co-movement. Membership is validated as a **total partition**
at construction — five failure modes, each naming the offending signals, none recoverable.

### 5C — the vertical

`AtlasEngine.run(dataset) -> list[Narrative]`, in five steps: score jointly → promote only genuine
departures with a calibrated weight → collapse by physical unit and time window → reason with OT
templates → narrate.

**Grouping runs before reasoning, and the order is the point.** Reasoning after grouping counts a
pump event once. Reasoning before it counts the same event once per instrument, and every
confidence downstream is inflated by the size of the instrumentation rather than by anything that
happened in the plant.

Five OT explanations, and no mechanism for inventing a sixth: `sensor_or_device_fault`,
`engineering_maintenance`, `process_disturbance`, `unauthorised_control_activity`, and the
always-present `insufficient_evidence` residual.

---

## 3. What was measured

### 3.1 Joint modelling beats per-signal modelling (5A)

HAI, three-way split, same corpus, same threshold (3.0), same seed (11), same harness. **Only the
model differs.**

| Detector | Recall | FPs | FP/normal-hr | Precision |
|---|---|---|---|---|
| `model:gaussian` (PART 3 baseline) | 1.00 | 66,163 | 8,389.81 | 0.0043 |
| `model:atlas-pca` | 1.00 | 138,243 | 17,529.93 | 0.0048 |
| `model:atlas-mahalanobis` | 1.00 | 5,099 | **646.58** | 0.0047 |

**A 13.0× reduction in false positives per normal hour at identical recall.** Under the other two
protocols it is a trade rather than a free win: prefix 7,092 → 624 (11.4×) at recall 1.00 → 0.80;
designed 435 → 8.78 (49.6×) at recall 1.00 → 0.40.

On BATADAL, where 43 signals never produced a false-positive problem (0.06 FP/normal-hr), the win
is recall instead: both joint models take it from 0.50 to 1.00, Mahalanobis at 0.11 FP/normal-hr
against PCA's 0.48.

### 3.2 The result 5A did not expect

**`PcaResidualModel` — the model 5A nominated as primary — loses on HAI.** It roughly doubles the
false-positive rate. Recorded rather than tuned away, and the mechanism measured:

| Model | in-sample out-of-band | out-of-sample | inflation |
|---|---|---|---|
| `atlas-pca` | 0.64% | 4.92% | 7.7× |
| `model:gaussian` | 0.48% | 1.59% | 3.3× |
| `atlas-mahalanobis` | 0.04% | 0.03% | 0.8× |

The fit is correct — 0.64% outside a three-sigma band in-sample is right. A PCA residual band is
built from the variance the components *failed* to explain (5% at the default), so it is far
tighter than a marginal band, and HAI's train and test are different capture periods. The drift
between them is small in absolute terms and enormous relative to a band sized by the noise floor.
Lowering `variance_retained` confirms it monotonically, reaching parity with the per-signal
baseline but never beating it.

Both models ship as specified. What the measurement changed is which one Atlas reaches for first.

### 3.3 Grouping collapses the operator's queue (5C)

One run over HAI's test slice, one alert set, counted two ways:

| Counted as | Alerts | Recall | FP/normal-hr | Precision |
|---|---|---|---|---|
| per-signal evidence | 5,123 | 1.00 | 646.58 | 0.0047 |
| **subsystem events** | **424** | **1.00** | **53.26** | 0.0094 |

**12.1× fewer things to investigate, at unchanged recall.** Both attack windows were covered before
grouping and both after, measured by overlap rather than assumed.

The "before" row *is* 5A's logged number, not a near neighbour of it: a magnitude is a departure
measured in band widths, so the evidence boundary and a harness threshold of 3.0 select the same
alerts whenever the threshold equals `band_k`, which at 3.0 it does.

**The detector did not change.** This is a counting change and is reported as one.

### 3.4 Calibration works; the evidence it calibrates is weak

The isotonic calibrator collapses expected calibration error from 0.8769 to **0.0291** on the Atlas
detector. But it fits **4 knots spanning [0.000, 0.034]** — because only 140 of 4,249 calibration
candidates fall in attack windows. So evidence weights top out at 0.034, each piece of evidence
moves a hypothesis's log-odds by about 0.033, and confidences sit near their priors.

The calibrator is not wrong. A 3% probability *is* the correct calibrated answer for these
candidates. The consequence is that Atlas's competing set is currently ordered almost entirely by
prior, and that is a fact about the evidence, not about the reasoning.

---

## 4. What is honest about these numbers

Four caveats travel with every report Atlas logs, written into `source_note` rather than kept in a
document, because a document is not what a reader of `eval_runs/log.jsonl` has in front of them.

**1 · The grouping reduction is inflated by a coarse map.** HAI's topology could not be partitioned
below process level for P1 (38 signals) and P2 (22), so unrelated departures anywhere on one
process collapse into a single event. A P1-wide disturbance has a theoretical ceiling of 38-to-1,
which flatters the mechanism. **12.1× is evidence that grouping is correctly *implemented*, not
that it is correctly *resolved*.** A finer map would lower the headline number and raise its
meaning.

The coarseness was not laziness. The manual decomposes the boiler into five control loops, but that
is a covering rather than a partition — `P1_FCV03D` belongs to two loops — and it names only 26 of
38 P1 points. The physical-vessel route fails too: Figure 1 names six vessels and assigns no data
point to any. `P1_FT01` and `P1_FT03` carry *identical* descriptions, so the manual cannot
distinguish two of its own flow transmitters. A coarse honest map is a usable input; a fabricated
fine one is not.

**2 · Hypothesis confidences are not calibrated probabilities and may not be surfaced** under
Constitution §3.3. The template priors and `EVIDENCE_STRENGTH` are reasoned placeholders, not
values measured against explanation-labelled data — and no such data exists. HAI labels *attack*
and *normal*, not *which explanation is true*. Atlas may rank and reason over hypotheses; it may
not present their confidences as calibrated. Evidence weights, separately, are calibrated.

**3 · Coarse grouping can mask a co-occurring event.** Two independent faults on one process are
indistinguishable from one, and an attack co-occurring with a fault is reported as a single thing
to investigate. That is a recall risk carried by the grouping, not a win — and HAI's attack table
contains many such combinations.

**4 · A subsystem event's weight is a maximum** over its members' calibrated weights, and a maximum
over calibrated probabilities is not itself calibrated. The calibration error reported for
subsystem events may come out better or worse than the per-signal one for reasons that have nothing
to do with the calibrator.

### The priors, and why they are not round numbers

PART 5C required priors authored from base rates. They are **computed, not typed**, from two
anchors:

- **The floor** is the reasoning engine's own pruning threshold (0.02). Below it a hypothesis is
  born marked implausible, which is a judgement made before looking — so the rarest explanation
  starts exactly there and no lower.
- **The step** is one piece of fully-trusted evidence. Each rank multiplies the odds by
  `exp(EVIDENCE_STRENGTH)`, so a rank gap reads as a number of observations rather than a
  preference.

| Explanation | Rank | Prior |
|---|---|---|
| `insufficient_evidence` (residual) | — | 0.30 |
| `sensor_or_device_fault` | 2 | 0.1552 |
| `engineering_maintenance` | 1 | 0.0577 |
| `process_disturbance` | 1 | 0.0577 |
| `unauthorised_control_activity` | 0 | 0.0200 |

The ordering comes from base rates: equipment faults are the modal cause of unexpected behaviour in
a running plant; human intervention and genuine upsets are common but episodic; a cyber attack with
a visible process effect is rarer than all of them by orders of magnitude. Every domain explanation
starts **below** the residual, so before any evidence the only thing on the table is that nobody
knows yet. All of this is pinned by test — if either anchor moves elsewhere in PHOS, a test fails
rather than the priors quietly drifting away from the argument that justified them.

The unconditional attack base rate is far below the floor, and using it directly would produce an
explanation no evidence could ever raise. The priors are therefore **conditional** — the population
is "a unit on which a calibrated, out-of-band departure has already been raised" — and the
compression that conditioning implies is not something the available data measures. That is caveat
2 restated at its source.

---

## 5. Known limits

**On the corpus.**

- **646 FP/normal-hour is a 13× improvement and still not deployable.** Precision stays near 0.005
  for every model tried. Part of the ceiling is HAI itself: different captures for train and test,
  and the three-way split leaves 4% of the timeline — 173 complete timestamps for 52 signals. The
  claim is a real reduction attributable to joint modelling, not a solved problem.
- **A constant training signal is dropped from the `SignalSpace`** and Atlas says nothing about it.
  Forced by PCA — a constant has no correlation to learn or be learned from. 5A measured the cost
  under its protocol: 21 of 79 signals constant, exactly one ever moves in test, on 5 rows of 4,321.
  So the FP reduction is not this in disguise. **The number is protocol-dependent and worth
  watching:** the 5C vertical run, on the narrower 4% training prefix, drops 27 of 79 and models
  52. A shorter training window makes more signals look constant, and every one of them is a signal
  Atlas is silent about.
- **Only HAI has a topology.** BATADAL has none, so anything requiring a `SubsystemMap` is HAI-only.
  BATADAL's 43 signals never had a false-positive problem, so the pressure is low.

**On the reasoning.**

- **One narrative for the whole slice.** The reasoning engine unions all evidence cited by one
  hypothesis, and with near-continuous departures inside a 30-minute correlation window everything
  joins. Pre-existing 4B behaviour, left rather than tuned to produce a prettier answer.
- **The joint model weakens the localised/broad discrimination.** When one instrument goes bad it
  breaks the structure for its correlated neighbours too, so most real events read as "broad". The
  breadth split is sharper in principle than in practice on HAI.
- **`engineering_maintenance` has no working matcher on HAI.** The corpus carries no maintenance
  window, work order or engineering-workstation context. The only thing that would genuinely argue
  for a planned change is a change in the environment's structure, which Atlas does not yet
  produce. Stated in a test rather than left to be discovered.
- **`unauthorised_control_activity` weighs evidence identically to `process_disturbance`.** Process
  telemetry carries no control-command context, so nothing in HAI separates an operator's legitimate
  action from an attacker's. The two are told apart only by their priors. Also asserted by test — if
  a later PART finds evidence that *can* separate them, that test is what fails.

**On coverage.**

- **Communication-timing and protocol-state stability are stubs that raise**, naming the missing
  packet adapter. Approximating them from process telemetry would put a number on a dashboard that
  no measurement stands behind.
- **No predictive behaviour.** `Forecast` and `ForecastMiss` are PART 1 types that nothing in Atlas
  produces.
- **No behaviour-graph relationship edges.**

**Carried from earlier PARTs, untouched.** Narrative assembly is quadratic; the
`SplitPolicy(seed=...)` defect at `scripts/evaluate_corpora.py:131` is open from PART 3;
`scikit-learn` has been pinned since PART 2 and is used only to fit the PCA basis and the
calibrator.

---

## 6. What would move Atlas forward

Ranked by what the measurements actually say, not by what is easiest.

1. **A finer topology.** The single highest-leverage change. Splitting P1 and P2 below process level
   would lower the 12.1× headline and make it mean something, and would let a co-occurring second
   fault survive grouping. It needs plant documentation HAI does not publish — or a different
   corpus that does.
2. **A corpus whose attacks are dense enough to calibrate against.** The 0.034 weight ceiling is the
   binding constraint on the reasoning layer. Everything downstream of it is ordered by prior
   because the evidence is honestly weak.
3. **A packet adapter.** It unlocks the two stubbed stability metrics, and — more importantly —
   control-command context, which is the only thing that could separate `unauthorised_control_activity`
   from `process_disturbance`. That separation is currently impossible in principle, not just
   unimplemented.
4. **Explanation-labelled data.** The only route to lifting the §3.3 prohibition on surfacing a
   hypothesis confidence. Nothing else will do it; the constraint is data, not code.
5. **Predictive behaviour**, to produce `ForecastMiss` evidence and widen what the templates can
   match on.

---

## 7. Verdict

Atlas does what PARTs 5A–5C specified, and the two claims it makes are measured rather than
asserted: joint modelling cuts HAI's false-positive rate 13× at unchanged recall, and grouping by
declared physical unit cuts the operator's queue a further 12.1× without dropping a single piece of
evidence or an attack window.

Neither number makes it deployable. 53 alerts per normal hour is still far past what a control room
would tolerate, precision is near 0.009, and the grouping factor is inflated by a map that HAI's own
documentation could not make finer. The reasoning layer works and is currently starved — its
confidences are ordered by prior because the evidence carries a maximum weight of 0.034.

What Atlas has that matters more than any of these numbers is that **every one of them is
reconstructable**. A narrative resolves to subsystem events, an event to its member evidence, each
member to the deviation that raised it, and that deviation to the measurement it describes — and a
test walks that path end to end. Nothing on that chain is a number without a reason behind it, and
the four things that could be misread are attached to the numbers themselves rather than left in a
document.

---

### Sources

Every figure above comes from `eval_runs/log.jsonl` (40 reports, each stamped with commit and seed)
or from the test suite. Reproduce with:

```bash
uv run python scripts/evaluate_atlas.py && uv run python scripts/evaluate_atlas_vertical.py
```

Design decisions: [ADR 0009](adr/0009-joint-modelling-per-signal-attribution-and-the-model-that-lost.md),
[ADR 0010](adr/0010-declared-topology-and-the-granularity-hai-supports.md),
[ADR 0011](adr/0011-group-before-reason-ot-template-priors-and-two-honesty-guards.md).
Per-PART detail: `PROGRESS.md` §5A, §5B, §5C.

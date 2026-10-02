# ADR 0019 — Settling after a phase change: forgiving only what the phase being left explains, and the blind window that buys

- **Status:** Accepted
- **Date:** 2026-08-19
- **PART:** A-FIX-2
- **Supersedes:** nothing
- **Depends on:** [ADR 0018](0018-phase-conditional-modelling-for-a-batch-process.md),
  [ADR 0017](0017-the-breaking-harness-fingerprint-classification-and-judging-from-true-state.md),
  [ADR 0009](0009-joint-modelling-per-signal-attribution-and-the-model-that-lost.md),
  [ADR 0007](0007-the-evidence-boundary-and-a-calibrated-confidence.md)

## Context

A-FIX-1 gave Atlas per-phase detection on the batch reactor and left it **saturated**: 3.59 false
positives per normal hour against `SATURATED_FP_PER_HOUR = 1.0`, so D3's own rule strikes any
detection claim from the corpus. That PART localised the load — 92.4% of holdout out-of-band
deviations within five minutes of a phase change — and deliberately did not fix it, because the
obvious remedy is a *blind window* an attacker could time an attack into.

This record is the measurement of that transient and the fix chosen for it, with the blind-window
cost of every option stated rather than assumed.

---

## What was measured, before anything was changed

Fitted on `synth-batch-reactor-train`, scored on the untouched `synth-batch-reactor-holdout`:
3,508 candidate deviations, **131 out of band** — A-FIX-1's number, reproduced.

### 1. The decay profile

Out-of-band deviations per moment, by position within the current phase run (60 s per sample):

| position | 0 | 1 | 2 | 3 | 4 | 5 | 6–9 | 10–19 | 20–29 | 30–59 | 60+ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| rate | **0.657** | 0.091 | 0.071 | 0.061 | 0.091 | 0.071 | 0.043 | 0.0045 | 0.0027 | 0.0038 | 0.000 |

**49.6% of the entire holdout false-positive load sits at position 0 alone** (65 of 131), and 91.6%
within positions 0–9. The rate reaches its settled value at position 10 and never rises again.

### 2. It is concentrated, not uniform

| transition | HEAT→REACT | REACT→DISCHARGE | IDLE→CHARGE | CHARGE→HEAT | *start*→IDLE | DISCHARGE→IDLE |
| --- | --- | --- | --- | --- | --- | --- |
| transient (pos 0–9) | 41 | 20 | 20 | 20 | 15 | 4 |

Three signals carry 87 of the 120 transient deviations: `reagent_feed_kgph` (48),
`conversion_pct` (20), `jacket_valve_pct` (19).

At position 0 the firing is **deterministic**: `IDLE→CHARGE` puts `reagent_feed_kgph` out of band in
**20 of 20 batches**, and so does `CHARGE→HEAT`. This is not an anomaly distribution with a tail. It
is normal plant behaviour, mislabelled, every single time.

### 3. The mechanism, sharper than "the baseline is wrong"

`reagent_feed_kgph` through the CHARGE phase, across 41 training batches:

| position | 0 | 1 | 2 | 3 | 5 | 10 | 20 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| mean (kg/h) | **3.0** | 5401.3 | 5400.8 | 5400.2 | 5401.5 | 5400.1 | 5400.0 |
| sd | 4.10 | 5.03 | 5.69 | 6.49 | 6.46 | 5.94 | 6.36 |

The register flips to CHARGE **one sample before the feed moves**. The pooled CHARGE model learns a
mean near 5,400, so position 0's reading of 3.0 is an enormous departure — and the position-0 state
is *more* reproducible across batches (sd 4.10) than the settled state it is judged against
(sd 5.96).

The PART asked whether this is "the baseline is wrong for a few minutes" or "a genuinely distinct
short transitional regime". **It is both, and the split is what the fix is built on:**

* For the dominant contributor it is a **register/physics lead**. The plant is still, physically, in
  the phase it has just left.
* For `conversion_pct` it is a **real transitional regime** with genuinely higher cross-batch spread
  early (sd 14.9 at positions 0–4 against 1.93 settled), because early conversion carries the
  previous batch's residue.

Both are the same sentence: **during settling the plant still resembles the phase it is leaving.**

### 4. The transient deviations are large, so this is not a threshold problem

Transient (pos 0–9) magnitudes: min 3.04, median 5.97, p90 8.06, max 35.03. Settled: median 3.61.
Raising a threshold far enough to quiet the transient would quiet most real attacks with it.

---

## Options considered, each with the blind window it grants

### Option 1 — model the settling transient as part of each phase's normal (sub-phase conditioning)

Fit a separate model per (phase, position-in-phase bucket), so early-phase moments are judged
against an early-phase baseline rather than forgiven. In principle this grants **no blind window at
all**: it is a *finer* baseline, not a relaxation.

**Measured, and rejected on the numbers.** Holdout out-of-band, against 131 shipped:

| bucket edges | [1] | [1,5] | [1,3,10] | [1,2,5,10] | [1,5,15] |
| --- | --- | --- | --- | --- | --- |
| models fitted | 10 | 15 | 20 | 25 | 19 |
| holdout out-of-band | 135 | **111** | 123 | 122 | 127 |

It does exactly what it should at position 0 (65 → 6) and then re-creates the problem further in:
with edges `[1,5]` the positions 5–9 load *rises* from 24 to 45, because the tail bucket lumps
still-settling moments with settled ones and the phases have wildly different durations (IDLE 14–15
samples, HEAT 62–91, REACT 8–101). A 15% reduction gets nowhere near the saturation threshold, and
it costs 15–25 covariances each fitted on 41 samples.

Its real blind window, where it has one, is measurable and was measured: wherever the early-phase
band is genuinely wider than the settled one (`conversion_pct`, 7.7×), sensitivity in that window
falls by that factor.

### Option 2 — treat the transition as its own short phase

Structurally Option 1 with edges `[1]`: **measured at 135 against 131 shipped — no improvement at
all.** One extra bucket per phase cannot represent a settling curve whose length differs per phase.
Rejected on the measurement.

### Option 3 — accumulate evidence over time (persistence of k consecutive samples)

Require a departure to persist before it can raise an alert. Run lengths of consecutive out-of-band
samples per signal:

| surviving runs | k=2 | k=3 | k=4 | k=5 |
| --- | --- | --- | --- | --- |
| holdout (of 89) | 15 | 8 | 4 | 4 |
| attacked (of 358) | 188 | 168 | 158 | 150 |

Genuinely attractive, and it has the **best security property of any option here**: the requirement
is uniform in time and *not keyed to phase changes at all*, so an attacker gains nothing by timing an
attack to a transition. Its blind window is any attack shorter than k samples, everywhere, uniformly.

**Rejected for this PART, and recorded as a strong candidate for its own.** Persistence lives in
shared machinery — the evidence boundary or grouping — which water treatment and power generation
also run through, so adopting it here would forfeit the byte-identical no-harm guarantee A-FIX-1
established and would fold two results into one unreadable number. It also trades a bounded,
phase-local exposure for an unbounded, everywhere-and-always one, which is a bigger claim than this
PART is scoped to measure.

### Option 4 — forgive a settling departure only if the phase being left explains it — **CHOSEN**

Within a bounded window after a phase change, a departure from the entering phase's baseline is
forgiven **only when the reading sits inside the outgoing phase's own learned band at that moment**.
Outside the window, and for any reading outside both bands, nothing changes.

**Measured**, window 10 samples, against 131 holdout / 13,593 attacked out-of-band shipped:

| rule | holdout | attacked | separation |
| --- | --- | --- | --- |
| shipped (A-FIX-1) | 131 | 13,593 | 38.9 |
| convex hull of the two bands | **28** (−78.6%) | 12,560 (−7.6%) | 168.2 |
| **union of the two bands** | **28** (−78.6%) | 12,714 (−6.5%) | **170.3** |

**The union is chosen over the convex hull on the measurement.** Both remove exactly the same false
positives, but the hull additionally forgives everything *between* the two bands — for
`reagent_feed_kgph` that is the whole range 0 → 5,400 — while buying nothing. Real settling readings
sit in one band or the other, never in the gap, so the gap must not be forgiven. This is the
"minimum the physics demand" the PART asked for, and it is a measured minimum rather than an
asserted one.

---

## Decisions

1. **A settling allowance in `PhaseConditionalFittedModel.score`.** A moment within the settling
   window of a phase change is scored by the entering phase's model as before, and any departure it
   produces is re-judged against the phase being left. If the outgoing phase explains the reading,
   the moment is reported **as the outgoing model judged it**; otherwise the entering model's
   judgement stands unchanged.

2. **A forgiven moment is reported, not deleted.** It keeps its `Deviation`, carrying the outgoing
   phase's real learned `ExpectedRange` — so `phos.reasoning.boundary.is_out_of_band` returns
   `False` by construction and no boundary code changes. The evidence chain still shows what the
   reading was judged against and why, which is what Constitution §3.2 requires. Nothing is
   silently dropped and no synthetic widened band is invented.

3. **The window is a duration, not a sample count.** Settling is physics and physics runs in time;
   a sample count would mean different things on corpora of different sample intervals. Default
   **10 minutes**, which on this corpus is the 10 samples the decay profile identifies.

4. **The window is set where the benefit saturates, not where the number looks best.** Holdout
   out-of-band is 28 at window 10 and **28 at window 20** — extending it buys *nothing* — while the
   attack cost climbs monotonically: 7.6% at 10, 14.6% at 20, and **66.4% unbounded**. The window
   stops exactly where the transient stops.

   *Qualified after measurement, honestly.* On the **attacked** corpus a longer window does keep
   reducing false positives (198 out-of-band at 10 minutes, 109 at 20, 86 at 30). It does so by
   forgiving a different defect — the within-phase trajectory measured below — and on a DISCHARGE
   phase lasting 19–34 minutes a 30-minute window would place most of the phase inside a settling
   allowance. That is the blanket quieting this PART forbids, so the window stays where the
   transient ends rather than where the false-positive curve flattens.

5. **The allowance is not self-limiting, and that was measured rather than assumed.** Left
   unbounded it suppresses 66.4% of the attacked corpus's out-of-band deviations. The bound is
   load-bearing, and decision 4 is why it is where it is.

6. **It is opt-in per plant, keyed to the same declaration A-FIX-1 introduced.** A plant that
   declares no phase register is not phase-conditional and cannot reach this code. Water treatment
   and power generation remain byte-identical, structurally rather than by argument.

7. **A moment with no outgoing phase is untouched** — the first phase run of a corpus has nothing
   to be settling from, and an unlearned outgoing phase yields no band to be forgiven by.

---

## The blind window this grants, stated precisely

**Within 10 minutes of a phase change, a falsified reading that is plausible for the phase just left
is not flagged on that signal.**

That is a real exposure and it is keyed to phase changes, which is exactly the shape of trade the
PART warned about. What bounds it:

* It is **not a suppression window**. Nothing is quieted for being near a transition. The reading
  must fall inside a *specific, learned, per-moment* envelope — the one the outgoing phase's joint
  structure implies for that signal at that instant. A reading outside both bands is flagged exactly
  as it was before.
* It is **bounded in time** by decision 4, at the measured end of the transient.
* Its cost is **6.5% of the attacked corpus's out-of-band deviations**, and 11.8% of that corpus's
  moments lie inside a settling window at all.

**Measured, not argued** — `scripts/probe_settling_window.py`, twenty IDLE→CHARGE transitions on the
untouched holdout, each probe run with the allowance off and on:

| probe | what it injects | allowance off | allowance on |
| --- | --- | --- | --- |
| `hides` | feed held at 0 through the window — a blocked charge, and exactly what IDLE expects | 191 / 191 caught | **0 / 191** |
| `outlives` | the same attack held for three times the window | 591 / 591 caught | 400 / 591 |
| `exceeds` | a feed rate outside *both* phases' envelopes | 200 / 200 caught | 200 / 200 |

The exposure is real and complete while it lasts: a blocked charge is **entirely invisible** for ten
minutes. It is also exactly bounded — `outlives` hides 591 − 400 = **191** readings, the same 191
`hides` conceals, so nothing beyond the window is forgiven — and it is conditional, not a period of
quiet: `exceeds` is caught throughout.

**What it is not proof of.** D2's battery cannot test this exposure on its own: every one of its 20
batch attacks runs 180–720 moments and overlaps a settling window for at most 17.8% of its length,
and **not one lies wholly inside one**. An attack long enough to be caught in settled operation says
nothing about an attack sized to hide in the transient. That is why this PART builds a purpose-made
probe and reports it separately, and why no claim here rests on the shipped map alone.

## Measured outcome

Re-run of `scripts/evaluate_breaking_points.py`, seed 7, same battery.

**The false-positive load fell by a third, and that is not enough.**

| `batch-reactor` | A-FIX-1 | A-FIX-2 |
| --- | --- | --- |
| false positives per normal hour | 3.5912 | **2.4526** (−31.7%) |
| subsystem events | 3,887 | 3,480 |
| narratives | 66 | 32 |

`SATURATED_FP_PER_HOUR` is 1.0. **The batch corpus is still saturated, so it still supports no
detection claim**, and nothing below may be read as a recall.

**No harm elsewhere, proven rather than argued.** Every `water-treatment` and `power-generation` row
is byte-identical: false-positive rates 0.3894 and 134.4943 per hour, event counts 598 and 15,903,
narrative counts 12 and 2, and unchanged verdict tallies. The guarantee is structural — a plant that
declares no phase register cannot reach this code — and `test_every_other_plant_keeps_the_pooled_joint_model`
asserts it.

### Three attacks moved from CAUGHT to MISSED, and that is a correction rather than a regression

| `batch-reactor` verdicts | A-FIX-1 | A-FIX-2 |
| --- | --- | --- |
| CAUGHT | 19 | 16 |
| MISSED | 0 | 1 |
| MISSED_DANGEROUS | 1 | **3** |

That looks like the exact trade this PART forbids, so it was run down rather than reported. All
three — `br-blatant-obvious`, `br-blatant-subtle`, `br-mimic-obvious` — were caught by **exactly one
alert** in A-FIX-1, and in every case that alert was a single out-of-band deviation on
`reagent_feed_kgph` at the instant the CHARGE→HEAT flip fired.

That cell fires at **28 of 28** CHARGE→HEAT flips in the attacked corpus: **18 of 18** inside attack
windows and **10 of 10** outside them. Its firing rate is identical with and without an attack
present, because it is the register/physics lead measured at the top of this record — the same
deviation that fires in 20 of 20 batches of clean holdout. It is a property of the transition, not
of any attack.

So those three attacks were never detected. They were credited to a false positive that happened to
land inside their windows, which is precisely the failure mode D3's saturation rule exists to
describe, here demonstrated for three named attacks. **A-FIX-1's 19-of-20 on this plant was inflated
by three, and the true count of attacks that reached danger unseen was always 3 rather than 1.**
Removing the artefact reveals that; it does not cause it.

The remaining 16 keep substantial evidence — 1 to 978 alerts each, and every one of the five now
carried by a single alert is carried by `jacket_temp_c` in DISCHARGE, which fires **only** inside
attack windows (0 of 7 clean transitions) and is therefore genuine.

### The window costs nothing beyond the flip instant

| settling window | 0 (A-FIX-1) | 1 min | 2 min | 3 min | 5 min | 10 min |
| --- | --- | --- | --- | --- | --- | --- |
| false positives / hour | 3.5912 | 2.9197 | 2.8613 | 2.8321 | 2.7737 | **2.4526** |
| CAUGHT / MISSED / DANGEROUS | 19/0/1 | 16/1/3 | 16/1/3 | 16/1/3 | 16/1/3 | 16/1/3 |

The entire verdict change happens at one minute — that is, at the flip instant alone — and nothing
further is lost out to ten. The transient moments and the artefact are the same moments.

### Where the residual actually is, which corrects this record's own premise

A-FIX-1 measured "92.4% of false positives within five minutes of a phase change" **on the holdout**.
On the attacked corpus, which is what the harness's false-positive rate is computed from, that
concentration does not hold. Out-of-band deviations outside attack windows, by time into the phase:

| | flip instant | < 10 min | 10–30 min | ≥ 30 min |
| --- | --- | --- | --- | --- |
| A-FIX-1 | 28 | 75 | 131 | 15 |
| A-FIX-2 | **4** | 48 | 131 | 15 |

The allowance removes 86% of the flip-instant load and 36% of the rest of the window, and touches
nothing beyond it by design. But **the majority of the residual — 131 of 198 — sits 10 to 30 minutes
into a phase**, and it is not settling at all. It is a *within-phase trajectory* that a stationary
per-phase model cannot track. Measured as how far a signal's training mean travels across its own
phase, in the spreads that phase judges it with:

| phase | signal | mean travel, in learned spreads |
| --- | --- | --- |
| DISCHARGE | `reactor_temp_c` | **7.5** |
| DISCHARGE | `reactor_level_pct` | 4.0 |
| DISCHARGE | `jacket_temp_c` | 4.0 |
| DISCHARGE | `jacket_flow_m3ph` | 3.9 |
| REACT | `conversion_pct` | 1.9 |

Against `band_k = 3.0`, four signals are carried out of band by the phase's own mean, with no attack
and no transition involved. That is a distinct defect from the one this PART was commissioned on,
and it is deliberately not touched here.

### One thing the corpora disagree about, which the design already anticipated

The attacked corpus samples every **30 seconds**; the training and holdout corpora sample every
**60**. A window expressed in samples and calibrated on the holdout would therefore have covered half
the physical time on the corpus every number in the map is measured from. Decision 3 — a duration
rather than a sample count — is load-bearing, and this is the measurement that shows it.

## Consequences

**Gained.** The flip-instant transient is removed at its measured cause rather than covered over,
and the claim made about a forgiven moment — "the phase it is leaving explains this" — is checkable
from the stored evidence. The false-positive load falls by 31.7%.

**Gained, and worth more than the number.** Removing the artefact exposed three attacks that were
being credited to it. A-FIX-1's batch recall was overstated by three and its danger count understated
by two, and neither could have been seen without this change. A saturated corpus does not merely
report an unreliable recall — it can report a *specific, nameable* recall that is wrong, and now
there is a worked example of it.

**Not gained: the thing this PART was aiming at.** 2.4526 per hour is still well above
`SATURATED_FP_PER_HOUR = 1.0`. **Batch detection is not a claim that may be made after this PART any
more than before it.** The honest reading is *saturated → less saturated*.

**Cost.** One extra scoring pass over the settling moments per phase change, and the blind window
above — measured at a blocked charge being wholly invisible for ten minutes.

**Cost, unquantified.** The allowance changes the candidate set the calibrator is fitted on, since a
forgiven moment keeps a `Deviation` carrying a different magnitude. Promotion is decided by
`is_out_of_band` rather than by calibrated weight (ADR 0017), so the map does not move on this
account, but evidence *weights* on this plant are not the same numbers they were and no separate
calibration measurement was run.

**Deferred, in the order the evidence now ranks them.**

1. **The within-phase trajectory**, which is where the majority of the residual false-positive load
   actually sits — four DISCHARGE signals whose phase mean alone travels 3.9 to 7.5 spreads. This is
   what stands between the batch reactor and a corpus that could support a detection claim, and it
   is a modelling problem rather than a transition one.
2. **Option 3 (persistence)**, the better answer to transient false positives if it is ever measured
   across all three plants at once, which is what makes it its own PART rather than a postscript
   here.
3. **The scale-dependence of `_shrink`**, carried unchanged from ADR 0018.
4. **An attack that writes to a phase register**, still unmeasurable with the shipped battery, and
   now with a second reason to want it: the settling allowance reads the same register, so falsifying
   it moves the allowance as well as the routing.

**A caveat on the probe.** `scripts/probe_settling_window.py` is an instrument, not a battery entry.
It measures one exposure on one signal at one transition, chosen because it is the clearest case. It
is not a search for the worst case, and no claim here rests on it being one.

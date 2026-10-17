# ADR 0123 — The plant map: which signals drive which, with a delay and a normal band per link

- **Status:** Accepted. Proposed and amended on 13 October 2026; building waits for Elijah's go.
- **Date:** 2026-10-13
- **PART:** after v1 A2; for T1, W2 and the learning engine's next task
- **Depends on:** [ADR 0010](0010-declared-topology-and-the-granularity-hai-supports.md),
  [ADR 0094](0094-liar-measurement-seeds-and-pass-share.md),
  [ADR 0106](0106-four-checks-on-the-frozen-candidate.md),
  [ADR 0108](0108-consistency-evidence-routes-to-the-explanations.md),
  [ADR 0112](0112-consistency-windows-by-sample-period-and-one-batadal-score.md),
  [ADR 0114](0114-the-liar-measurement-is-assembled-and-held.md),
  [ADR 0117](0117-two-loops-a-seen-ledger-and-the-held-out-bank.md),
  [ADR 0119](0119-why-a-liar-run-fails-by-a-declared-precedence.md),
  [ADR 0120](0120-the-arena-tasks-an-enforced-budget-and-a-fence.md),
  [ADR 0121](0121-the-first-learning-lifecycle-and-its-control-arm.md),
  [ADR 0122](0122-a-phos-generated-icssim-corpus.md)

## Context

1. **What the frozen detector knows.** `phos.atlas.consistency` predicts each signal from every
   other signal now and 5, 15, 30 and 60 samples ago, in one dense ridge regression per signal,
   with the signal's own history left out. ADR 0106 puts most of the clean-HAI margin on that loop
   score. It says *that* a reading disagrees with everything else. It does not say which relation
   broke, and `loop_expectation`, today's reconstruction of the true value, is built from every
   other signal, including the controllers that acted on the false reading.
2. **Where it fails.** On development liar runs, 10 of 14 failures on seed 4242 (ADR 0119) and 45
   of 66 on the arena seeds (ADR 0120) are the inlet staying below its threshold, almost all on
   water treatment. ADR 0121's targeted search found that minute-long lags (300 and 900 s) and a
   12-hour detrend raise water passes from 0 to 23 of 30, and that the chosen candidate then lost
   two champion passes on the red team. Longer memory is the lever; adding it to a dense model also
   moves margins elsewhere.
3. **Why, mechanically (a hypothesis, untested).** The water plant declares the clearwell level as
   *integrating* raw inflow minus distribution flow, and a PI loop that holds the level at its
   setpoint by moving the intake pump (`WATER_COUPLINGS`). The liar reports the setpoint less a
   fixed deficit, and the PI loop acts on that report. In normal closed-loop data the best predictor
   of a controlled level is its controller and its setpoint, and under the liar both agree with the
   lie, because the controller is responding to the lie. A model that predicts the level from its
   controller learns the lie back. Only the integrating relation through the flows disagrees with
   it. ICSSim's tank is the same case (ADR 0122): PLC-1 reads the tampered level and runs its
   valves on it.
4. **What W2 asks for** (`docs/phos-2027.md`): the true value reconstructed to within 10% of the
   signal's normal range for most falsified samples, and the lying instrument named in at least 70%
   of caught runs. Today's fact names the event's column, not the link, and does not argue which of
   two disagreeing signals is the one lying.

Elijah asked on 13 October for this design, and for no code or scoring until it is accepted.

## Proposal

### 1. What the map is

For each live signal *y*, learned from attack-free training only:

- a short list of **drivers**, and for each driver the **lag or lags** at which it predicts *y*;
- a **form**: *level* (the value of *y*) or *increment* (the change in *y*);
- a **normal-error band** for *y*'s model, and one for each **drop-one model** (*y* without one
  driver). The drop-one band is the link's band (§4).

A link "*x* → *y* at 300 s" means: on this plant's normal data, *x* 300 s ago predicts *y* beyond
what *y*'s other drivers already predict. That is a predictive (Granger) statement, not a claim
about what an intervention would do. Operator text says *y* "normally follows" *x*; it never says
the link is physical.

### 2. The method: lagged regression, per-link lag selection, two forms

- **Inputs.** Signals standardised exactly as the frozen detector does. Every map term has a lag of
  **at least one sample**: direction cannot be read from a lag-0 relation by this method. The
  frozen loop keeps lag 0.
- **The lag grid**, in seconds, converted by ADR 0112's rule (`scale_windows`'s conversion,
  duplicates kept once): 5, 15, 30, 60, 120, 300, 600, 900, 1800, 3600. It contains the frozen
  lags and the 300 and 900 s that ADR 0121's targeted search found on development data, said
  openly. At 30 s samples it is 1, 2, 4, 10, 20, 30, 60, 120 samples.
- **Two forms per target.** Level: *y*ₜ = *c* + Σ β *x*ₖ,ₜ₋ℓ. Increment: *y*ₜ − *y*ₜ₋₁ =
  *c* + Σ β *x*ₖ,ₜ₋ℓ, which is how an integrating relation (a level over net flow) is written.
  Up to two lags per driver lets either form carry a rate (*x*ₜ₋ℓ₁ − *x*ₜ₋ℓ₂), so an algebraic
  relation can still be written in increments. The target's own history is never a driver in
  either form: a liar agrees with itself (the frozen detector's rule).
- **Selection.** Forward stepwise over (driver, lag) terms. Each step adds the term that most lowers
  time-blocked cross-validated error (five contiguous blocks of attack-free training; error measured
  outside the block that was fitted). Stop when the reduction is under 1% of the current error, or
  at the caps: **at most 6 drivers per target and 2 lags per driver**. Coefficients are then solved
  with the frozen ridge penalty (`RIDGE` 1.0). Ties go to signal order, then lag, so a fit is
  deterministic.
- **Two passes, so the controller cannot cover for the lie (§3).** Pass one selects both forms
  for every target from every admissible lag-≥1 term and gives a preliminary graph. Pass two
  re-selects each target's level form without its descendants in that graph.
- **The form a target uses** is the one whose reconstruction (§6), from its admissible drivers
  alone, stays closer to *y* on out-of-block training rows at a 900 s horizon.

**Why this method first.** It is the frozen detector's own machinery made sparse and directed: the
same standardisation and ridge, cheap from one Gram matrix per form, deterministic, and every link
legible to an operator. The documented alternative for autocorrelated series with lagged and
contemporaneous links is PCMCI+ (Runge, 2020), built on conditional-independence tests. It is not
first because it gives a graph and still needs a predictor with bands beside it, its tests over
HAI's several dozen signals and a 3600 s grid are costly at 1 s, and its reference implementation
(tigramite) is GPL-licensed as far as is known. It is the named next method if §9.5 or §9.6 fails.
**tigramite will not be a dependency** unless its licence is verified compatible with PHOS's, on
two surfaces as ADR 0024 requires, in a record of its own. If PCMCI+ is needed before that, it is
implemented from the paper, with the paper cited and no tigramite code read into the lab.

### 3. Direction, feedback, and which drivers may reconstruct a reading

- **Descendants may not predict a level.** If the preliminary graph has a directed path from *y* to
  *x*, then *x* carries *y*'s past (a controller output is computed from the reading it was given).
  *x* is then excluded from *y*'s level form, and allowed in its increment form, where it enters as
  a cause of *y*'s change. Under the water liar this is the difference that matters: the intake
  pump, run by the false level, says "the level is where it was reported" in level form, and "the
  level is rising" in increment form, which is true.
- **Setpoints may not reconstruct a sensor.** A setpoint says where a controller wants a reading,
  which is exactly the assumption a falsified reading breaks. Setpoints are admissible drivers of
  actuators, never of sensors.
- **Signal roles are declared, never inferred.** Sensor, actuator and setpoint come from the
  corpus's documentation, like topology (ADR 0010): `SignalKind` on the synthetic plants, and
  ICSSim's tag list as its adapter declares it. **HAI's roles come from the official point list
  in `hai_dataset_technical_details.pdf` at the registry's pin
  `2a814cebc9a66b06c9e5cd545e2d72e65d383737`**, recorded as a committed data file, one row per
  point, each citing that document, its pin and the page or table it was read from. They are **never inferred from tag names**: a name such as
  `P1_FCV01D` suggests a role, and a suggestion is not a declaration. A point the list does not
  describe has no role, and gets no reconstruction. A corpus without declared roles gets no
  reconstruction, rather than a guessed one.
- **The map never groups.** ADR 0010 refuses subsystem membership learned from co-movement, because
  grouping would then be computed from the statistics that raised the deviations. The map is
  learned from co-movement, so it is used only to predict, as the frozen loop already does. It never
  decides grouping or subsystem membership. Declared couplings on the synthetic plants are used only
  to check the map (§8), never as input.

### 4. The bands

- **A target's band.** Level form: the 99.99th percentile (`RESID_QUANTILE`, as frozen) of
  |*y* − *ŷ*| on out-of-block attack-free training rows. Increment form: one band per horizon
  *h* ∈ {60, 300, 900, 3600} s, on |(*y*ₜ − *y*ₜ₋ₕ) − Σ Δ*ŷ*| over the same rows, so a slow
  divergence that no single step shows still accumulates against a band.
- **A link's band.** For each driver *k* of *y*, the drop-one model *y*∖*k*: the same form and the
  remaining terms, refitted without reselection, with its band computed the same way. It is how well
  *y* is explained without that link. The link record also carries its lags, the sign of its
  coefficient, and the share of *y*'s cross-validated error it removes.
- **The map score** of *y* at a row is its largest |residual| / band over its horizons.

### 5. How a broken link becomes evidence

**Detection is unchanged downstream of the score.** The map score passes through the frozen
detrend, per-signal divisor, episodes, events and 8-per-shift budget, with ADR 0112's windows. An
event is **map-carried** when, at its alert cell, the calibrated map score is above `THRESHOLD`
and at least the frozen loop and range scores there.

At a map-carried event on signal *y*:

1. **The broken link.** Link *k* → *y* is broken when *y*'s full model is out of band and its
   drop-one model *y*∖*k* is back in band: every other driver still explains *y*, and only *k*
   disagrees.
2. **The lying instrument.** The candidates are *y* and the driver of each broken link. A candidate
   *c* is named only if all three hold:
   - *c* is out of band in its own model and in every one of its drop-one models: it disagrees with
     all its drivers, and no single driver explains that away;
   - *c*'s drivers are in band in their own models;
   - of *c*'s **downstream** children (signals with *c* among their drivers that are not also
     ancestors of *c*), at least half are out of band with *c*'s reported value and back in band
     with its reconstruction (§6). A controller downstream of a reading follows the reading whether
     it is true or false, so it cannot testify about it. With no downstream children the fact says
     no downstream check was possible.

   If one candidate passes, it is named. If two pass, neither is: the fact lists both as not
   separable.
3. **A reading that the plant itself follows is not a liar.** If *y* is out of band but its
   downstream children follow its reported value, the reading is probably true and the relation
   into *y* changed: a forced valve, a leak, maintenance. That is not promoted as
   `cross_signal_mismatch`, because ADR 0108 routes that facet to an instrument fault and against a
   real upset. It is kept in the diagnosis output, labelled **reading true, plant changed**. It is
   the future route to an **unexplained-actuation** finding for W3: the plant really moved, and
   the question becomes which command, work order or device explains it. It is **not emitted now**;
   that finding, its facet and its routing are a later record.

**The fact.** Built and promoted exactly as ADR 0108's, through `phos.reasoning.boundary`, with
the facet unchanged, (`CONSISTENCY`, `CROSS_SIGNAL_MISMATCH`), so the template routing does not
move. One fact per event: where the map and the frozen loop both carry an event, the map's fact
replaces the loop's. Events carried only by the frozen loop are promoted as today, naming no link.

| Part | Content |
| --- | --- |
| `Observation` | The named instrument's reading at the alert row (the event's column if none is named) |
| `context` | `expected_from_rest_of_plant` (kept; now the map's reconstruction), `broken_link` ("raw_inflow_m3ph → clearwell_level_m, increment form, 30 and 60 s"), `instrument` (a signal, or "not separable: a, b"), `instrument_checks` (the three checks in words), `reconstruction_anchor` |
| `ExpectedRange` | Centre: the reconstruction. Half-width: its band at that horizon (§6) |
| `Deviation.magnitude` | The calibrated map score |
| Weight | From the inlet calibrator fitted on development liar seeds 71001–71003, as ADR 0114 |

The sentence an operator reads, for example: "clearwell_level_m read 3.21 m. Its drivers, raw
inflow and distribution flow, integrated since 10:42, imply about 4.90 m (consistent between 4.52
and 5.28). The link from raw_inflow_m3ph broke. clearwell_level_m disagrees with all its drivers,
and chlorine_residual_mgpl, downstream of it, agrees with the reconstruction and not the reading."

### 6. The reconstructed true value

The value the instrument's own admissible drivers imply (§3: lag ≥ 1, no setpoints for a sensor,
no descendants in level form). The instrument's own reading is never used during the event.

- **Level form.** The model's prediction, with the target's band.
- **Increment form.** Anchored at the last row before the event's first member onset where the
  instrument was in band at every horizon (looking back at most 6 hours; with no such row, no
  reconstruction). From there, *ĉ*ₜ = *y*ₜ₀ + Σ Δ*ŷ*. Its band is the **free-run band**: on
  attack-free training, the same reconstruction started every 10 minutes, and the 99th percentile
  of its error at each elapsed time up to 6 hours. An integrated reconstruction drifts, and its band
  widens to say so.
- If a driver of the instrument is itself out of band during the window, the reconstruction is
  marked degraded, naming that driver. Centre and band are always reported. Where the band is wider
  than 10% of the signal's normal range, the sentence says the rest of the plant cannot place the
  value closer than that, rather than implying precision.

### 7. Replacing or extending the frozen 0–60 s lags

**It extends.** `atlas-v1-consistency` is untouched: its constants, its lag-0-to-60 loop and its
identity tests (ADR 0107, ADR 0111). It stays the champion and the engine's detector.

The proposed challenger, result name **`atlas-plant-map-v1`**, takes the element-wise maximum of
the frozen range score, the frozen loop score and the map score, computes the per-signal divisor
from that maximum as the frozen detector does from its two, and then uses the frozen detrend,
events and budget. The map adds directed, lagged relations up to an hour, the link, the instrument
and a reconstruction that cannot learn the lie back from the controller. It removes nothing ADR
0106's HAI result rests on.

Why not replace: the HAI margin is on the dense loop, a sparse map alone is unmeasured, and a
regression on HAI 20.07 would then have no single cause. A **replace arm** (map and range only) is
scored once on the development slices as diagnosis, to learn whether the map alone can detect. It
is not a candidate. The challenger reaches the validation corpora only through ADR 0117 §3's gate,
and the engine only through a separate record after that, as ADR 0107 was.

### 8. Evaluation, on development data only

**Before any score:** the map is built with tests, which include that the frozen detector's outputs
are unchanged. A short record extends the arena's candidate type (ADR 0120) from a window set to a
detector configuration, keeping its fence, budget and scorer pinning. The budget is declared then:
at most 6 scored configurations of the map's parameters (caps, stopping rule, horizons) on the
arena seeds, in an `AttemptLog`, then the red team once.

| Slice | Data (all `development`) | Training | Measured |
| --- | --- | --- | --- |
| Liar arena | `ARENA_LIAR_SEEDS` 4242, 95001–95004: 90 runs, three plants × six subtleties | Library attack-free seeds 80001–80003, as T1 | ADR 0094's pass share (champion 24/90, water 0/30), each failure diagnosed by ADR 0119. From `truth`: the share of falsified samples whose reconstruction is within 10% of normal range of the true value, against `loop_expectation` on the same samples; the true value's coverage by the band; instrument named = the recipe's target in caught runs; the broken link involves the target. Learned links against the declared couplings |
| Liar red team | `RED_TEAM_SEEDS` 95101–95110: 180 runs, once, after the configuration is chosen | Same | ADR 0121's rule: survives only with more passes than the champion (52/180) and no champion pass lost. The same reconstruction and naming measures |
| ICSSim | `phos-icssim-dev`: mixed seeds 96011–96020 (20 h, at least 10 `liar_freeze` and 10 `liar_offset`) | Normal seeds 96001–96003 (12 h) | Liar events caught within 8 per shift; instrument named = `tank_level_value`; reconstruction against `truth.csv`; on `setpoint`, `maintenance`, `rogue_command`, `replay` and `mimic_maintenance` (the plant really moves and the readings are true), the share of events naming a lying instrument, and the share the diagnosis labels reading true, plant changed (§5.3; recorded, not emitted) |
| HAI 20.07 | The frozen candidate's development corpus | Its attack-free training | Recall at 8 per shift against the champion's 37/38. Link stability: the map fitted on each half of training separately. Where its published attack list names a target point, whether a lying instrument is named, and which |

The ICSSim slice needs the development corpus generated and the adapter to Atlas's inlets
(handover step 5); neither exists yet. HAI has no true values for a falsified reading, so every
reconstruction measure is synthetic or emulated (R4).

**Never read:** HAI 21.03, 22.04 and 23.05, BATADAL (`validation`); T1's seeds 94001–94020 and
`phos-icssim-heldout` (`held-out`). Nothing is appended to `eval_runs/log.jsonl`. Every figure is
diagnosis, never a result.

### 9. What would prove it wrong

Set now, before anything is built. Any of 2–4 means no challenger. Any of 1, 5 or 6 means the
method is wrong; PCMCI+ is then the next method, under its own record. Any of 7–9 means the map
may detect, but must not name instruments or emit reconstructions. 10 means the design has failed
on practicality, and nothing else is scored until it passes.

1. **The mechanism.** On the arena seeds, clearwell_level_m's reconstruction does not use the
   increment form with raw inflow, distribution flow or the intake pump among its drivers, or its
   error on falsified samples is not lower than `loop_expectation`'s. Then §Context 3 is wrong, or
   the method cannot act on it.
2. **Liar arena.** Fewer than 24 of 90 passes, or water still 0 of 30.
3. **Red team.** Any champion pass lost, or not more than 52 of 180.
4. **HAI 20.07.** Below 37 of 38 at 8 alerts per shift.
5. **Not a map.** On the three synthetic plants, under half of the declared (driver, driven) pairs
   are recovered as links, or under half of the learned links lie on a declared path of at most two
   couplings. Then it is a predictor, and Atlas must not say which signals drive which.
6. **Not a property of the plant.** On HAI 20.07, under 70% of (driver, target) links appear in the
   maps fitted on both halves of training, or more than 30% of shared links differ in lag by more
   than one grid step.
7. **Naming.** On caught development liar runs (arena and ICSSim), the right instrument named in
   under 70%, or a wrong one named in over 10%. A wrong name is worse than none.
8. **Innocence.** On ICSSim's benign events and its attacks with true readings, a lying instrument
   named in more than 1 event in 10.
9. **Bands.** On falsified development samples, the true value inside the reconstruction band less
   than 90% of the time at the band's nominal 99%. The band would claim confidence it has not
   earned. The **measured coverage is reported beside the 90% floor and the nominal 99%** on every
   slice, per plant and per form, whether it passes or not, so a band that clears the floor while
   sitting well under its nominal rate is visible.
10. **Practicality.** A map fit on HAI 20.07's attack-free training data, both passes and every
    drop-one model included, does not finish within **30 minutes on a laptop**. Then the design has
    failed on practicality, whatever it scores: Atlas is meant to learn a plant the same afternoon
    (`docs/phos-2027.md` §3). The wall time is reported with the machine's model, core count and
    memory, and is measured before any slice is scored.

## Consequences

- If accepted, the order is: HAI 20.07's role file from the official point list (§3);
  `phos.atlas.plant_map` (fit, score, naming, reconstruction), tests first; the §9.10 fit time;
  its evidence promotion beside `consistency_evidence`; the arena record of §8; the declared
  budget and the development slices; the red team once. A gate is a later decision.
- Nothing is built, scored or read by this record. No detector, constant, prior, frozen row,
  registry entry or log line changes.
- **Limits, stated now.** Links are predictive, not causal: an unmeasured common driver (weather,
  upstream demand) makes links that are not plumbing. Closed loops limit what normal data can
  identify, which §3 works around by declared roles and the descendant rule, not by proof. The map
  is not conditioned on operating mode, so batch phases and setpoint changes absent from training
  will raise departures, as they do for the frozen detector. ICSSim's valves are on or off, and its
  PLCs sample on a 200 ms cycle, so reported and true values differ slightly outside any attack.
  The synthetic plants' couplings were written by PHOS and are close to linear, so recovering them
  is easier than recovering a real plant's. An attacker present during training is learned as
  normal, as with any learned baseline.

## What would reverse this

Building or scoring any of it before acceptance; reading a `validation` or `held-out` corpus for
it; using the map to group deviations or define subsystems; inferring a signal's role from its
name; taking tigramite as a dependency before its licence is verified; or moving a §9 threshold
after a development score has been seen.

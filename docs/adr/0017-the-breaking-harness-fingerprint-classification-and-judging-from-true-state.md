# ADR 0017 — The breaking harness: where it sits, how it fits a baseline, which results are clean, and what judges a miss

- **Status:** Accepted
- **Date:** 2026-08-17
- **PART:** D3
- **Supersedes:** nothing
- **Depends on:** [ADR 0016](0016-the-graded-attack-library-flavour-separation-and-the-anti-fingerprint-discipline.md),
  [ADR 0015](0015-simulated-plants-the-injection-hook-and-the-true-state-record.md),
  [ADR 0014](0014-command-evidence-the-second-boundary-door-and-the-unrun-measurement.md),
  [ADR 0011](0011-group-before-reason-ot-template-priors-and-two-honesty-guards.md),
  [ADR 0007](0007-the-evidence-boundary-and-a-calibrated-confidence.md)

## Context

D1 built plants. D2 built a graded, honestly-labelled adversary and deliberately refused to judge
anything with it. D3 is the measurement both were for: run Atlas against the battery and report where
it goes blind.

Five decisions were load-bearing, and one of them contradicts the PART that commissioned the work.

---

## Decisions

### 1. A sibling top-level package, `phos.breaking`, not a corner of `synth` or `atlas`

The PART allowed either "the synth subpackage or a sibling eval path". Neither of the obvious homes is
safe:

* Putting it in `phos.synth` would make the **generator** import the **detector**. D2's whole
  anti-fingerprint discipline rests on the generator being unable to see what it will be graded
  against; a dependency edge in that direction is the first step toward a library tuned to the
  engine, and the import graph is where that becomes checkable.
* Putting it in `phos.eval` would make the engine-agnostic measurement spine depend on Atlas, and
  PART 2's value is that the same `evaluate` scores every engine without knowing which.

So D3 is a top-level application package that depends on `phos.eval`, `phos.synth` *and* `phos.atlas`,
and on which nothing depends. Neither the generator nor the detector gained an edge.

### 2. The baseline is fitted on a separate normal corpus, and the calibrator is cross-fitted

The model needs attack-free training data; the calibrator needs both classes; and neither may see the
data it is scored on. Three facts about the shipped battery decide the arrangement:

* D2 opens its first attack **four hours** into a five-day run, so the attacked corpus's attack-free
  prefix is four hours long against a plant with a daily demand cycle. `train_calib_test_split` would
  cut the training prefix to exactly that, and a model fitted on four hours of a twenty-four-hour
  rhythm flags every evening. The breaking-point map would then describe a starved baseline, not
  Atlas.
* The battery is **62% attacked** by sample, so there is little normal time to spare inside it.
* D2 lays the battery out **band by band in time**, so the difficulty dial *is* the time axis. A
  train/calib/test split by time is a split by difficulty: every obvious attack on one side, every
  near-invisible one on the other, and no sweep left to find a boundary in.

Therefore: the model is fitted on the plant's separate D1 **normal** corpus, which is attack-free over
its whole length because D1 generates no attacks. The calibrator is **cross-fitted over two time
folds** — the corpus is run twice with the halves swapping calibration and test roles, and every
attack is scored in the fold whose calibration slice excluded it. The false-positive load pools across
the two folds and covers the corpus exactly once.

The fold boundary is walked out of any attack window it would have split, and an attack that still
straddles it is reported in `CorpusBreakdown.unscored` rather than dropped, because a silently
unscored attack is a missing row that reads as a clean sweep.

**One property makes this cheaper than it looks.** Promotion through 4A's boundary is decided by
`is_out_of_band` — the fitted model's own expected range — not by the calibrated weight (ADR 0007).
The calibrator supplies evidence *weight*, which reaches reasoning and what may be surfaced, and not
whether a departure becomes evidence. So the **breaking-point map does not move with the fold
assignment**; only the weights and the hypothesis ordering do.

### 3. Fingerprint status is classified by mechanism, and the PART's expectation was wrong

The PART said: *"D2 documented that some attacks, the stealth-drift in particular, carry an
unavoidable statistical fingerprint."* D2 documented no such thing about stealth drift. What D2
documented (`phos.synth.attacks.manipulations`, ADR 0016 §5) is a residual in **falsified readings**:
pseudo-noise reproduces an instrument's measurement noise but not its slow calibration drift, whose
phase is drawn from the plant's setup generator and cannot be reconstructed from outside, so at full
strength a falsified signal is drift-free.

That is a property of *overriding what a signal reports*, not of *being hard to see*. Read against
D2's library and D1's plant declarations:

| Type | Manipulation | Target kind | Residual? |
| --- | --- | --- | --- |
| `BLATANT` | `ActuatorOffset` | actuator | No — the plant senses the consequence through its own path, drift included |
| `STEALTH_DRIFT` | `ActuatorRamp` | actuator | **No** — same reason |
| `CORRELATION_BREAK` | `ReadingBlend` | sensor (`drift_amplitude > 0`) | **Yes** |
| `LIAR` | `ReadingTrack` | sensor (`drift_amplitude > 0`) | **Yes** |
| `MIMIC`, `ROGUE_COMMAND`, `MIMIC_COMMAND` | `ReadingBlend` | setpoint (`noise = drift = 0`) | No — a held setpoint is exactly constant, which is what a real setpoint is |

So `phos.breaking.fingerprint` applies a **mechanical rule** rather than a list of type names: *an
attack is caveated exactly when it falsifies the reading of a signal that carries calibration drift.*
Both halves are read off declarations that already exist — the manipulation D2 builds for the type,
and `SignalSpec.drift_amplitude` from D1's plant — which is why the classifier takes a
`PlantDescription`: the same type is caveated on a drifting sensor and clean on a driftless setpoint,
and only the plant knows which.

**Why not caveat stealth drift anyway, to be safe?** Because a caveat is a claim, and an unjustified
one is not conservative — it is noise. Marking five of seven types suspect would bury the two rows
that genuinely are, and those two are where a reader's scepticism needs to go. The discrepancy is
recorded here, in the module docstring, and in a test named for it, so nobody has to rediscover it.

**A nuance that changes how the caveated rows read.** `artefact_strength` is `1 - subtlety`: the
blend keeps that share of the synthetic value and the rest of the genuine signal, drift included. The
residual is therefore *strongest at the blatant end* and nearly gone at the near-invisible end. A
caught result at low subtlety is the one most likely to be the artefact; the breaking point itself,
which lives at high subtlety, is the least contaminated part of the sweep. That is a reason not to
discard the row, not a reason to trust it.

### 4. Danger is judged from D1's true-state record, on consequence signals only, against a
non-parametric envelope

For a liar attack the readings Atlas saw were fabricated, so being fooled cannot be judged from them.
`phos.breaking.truth` reads `truth.csv` and asks one question: did the true state go somewhere the
plant never went when nobody was attacking it?

Three choices inside that:

* **The envelope is the observed range of attack-free samples**, not a mean and standard deviation.
  These plants have a daily demand cycle, so a mean sits between the night trough and the afternoon
  peak — a value the plant is never actually at. The observed range covers ordinary operation, cycle
  included, and leaving it means reaching a value five days of unattacked operation never produced.
  Samples inside *any* attack window are excluded, so one attack cannot widen the envelope another is
  judged against.
* **Only consequence signals count.** An actuator driven by the attack, or a setpoint written by it,
  leaves its envelope because the attacker put it there; counting that would make every attack
  "dangerous" and the word would stop meaning anything. The test is the declared `SignalKind`: a
  targeted actuator or setpoint was moved directly, whereas a targeted **sensor** had only its
  *reading* falsified, leaving its true value a consequence like any other. This is why the liar is
  judged correctly without being special-cased — and the discount is per-signal, so what a driven
  actuator did to the *rest* of the plant still counts.
* **The margin is three measurement noises past the envelope.** The envelope is already the extreme of
  every unattacked sample, so a value just past it is the tail of ordinary operation rather than a new
  regime. Raising the margin makes the harness harder to convince the plant was harmed, which is the
  direction an honest default errs in.

`MISSED_DANGEROUS` is a distinct verdict rather than a flag on `MISSED`, so it cannot be aggregated
away; `is_miss` is the only thing that pools them.

### 5. The two flavours are separated by type, and `INERT` is neither a catch nor a miss

D2 made the flavour confusion unrepresentable per case (`HostileGroundTruth` has no `interval()`) and
per corpus. D3 keeps it so on the results side, where the temptation is stronger: `AttackOutcome` and
`RobustnessOutcome` are unrelated types, the robustness type has no `detected`, no latency, no
fingerprint status and no route into a breaking-point map, and nothing in the package combines them.
The report prints them in separate sections with the boundary stated in the output itself.

`INERT` exists because an attack at subtlety 1.0 has *exactly* zero magnitude — `strength_of(1.0)` is
`0.0` by arithmetic, not nearly zero. It was never there to be caught, so calling it a miss would
slander Atlas with D2's own control case. It stays on the map because a **detection** on one is a
leaked fingerprint caught red-handed, and the report escalates that above every other finding.

---

## Ambiguities in the PART, and how they were resolved

**"the stealth-drift in particular"** — contradicted by D2's record. Classified by mechanism instead;
see decision 3. Recorded in the report itself so a reader of the numbers meets the discrepancy too.

**"at what latency"** — latency is `phos.eval.metrics.detection_latency`, which counts only alerts
*strictly inside* a window, so an alert forgiven into a window by tolerance contributes none. That is
PART 2's definition and D3 does not vary it.

**What counts as an alert** — the **subsystem event**, which is what 5C established Atlas hands an
operator. The match tolerance is set to the grouping window, because an event is stamped at its
earliest member and grouping can therefore pull a stamp slightly ahead of the window it plainly
covers. The tolerance is applied consistently to true and false positives, so no alert is forgiven
and charged at once.

**"whether Atlas survives hostile input"** — split three ways rather than two. A crash is a defect; a
**refusal** is correct behaviour for a security product handed something it cannot trust; and
`COMPLETED` is only safe if the answer is still right, which `baseline_shift` measures as the change
in out-of-band rate on an untouched holdout between a poisoned fit and a clean one. `EXPECTED_REFUSALS`
names the documented exception types explicitly, so a widening of it is a visible change rather than a
drifting standard.

**"whether the competing-explanation ordering moved toward the correct cause"** — measured as a
change in **rank**, not confidence. The hypothesis confidences are uncalibrated and Constitution §3.3
forbids surfacing them; a rank is ordinal and says what the PART asked without quoting a number the
project has said is not a probability. The target explanation is named
(`unauthorised_control_activity`) rather than inferred, so the measurement cannot be satisfied by
whichever hypothesis happened to win.

---

## Consequences

* Atlas now has measured blind spots rather than assumed capability, and every one of them is a
  reproducible thing to fix. The map's value is in its misses.
* P3's open question has its first real answer. It is not the flattering one: on process telemetry
  alone `unauthorised_control_activity` is not raised **at all** over a command attack, and with the
  capture beside the corpus it rises but does not lead. The design's direction is confirmed; its
  sufficiency is not.
* Nothing about Atlas changed. D3 measures, and no threshold, prior or model was touched to improve a
  number.
* The command-path result carries a limitation this ADR should not hide: the graph comparison is made
  against a capture from a *different run*, so it reports a large number of structural findings, and
  the volume of command evidence reaching reasoning is correspondingly high. A within-run baseline
  would be a fairer comparison and does not exist. Read the ordering movement as directional, not as
  a magnitude.
* The map is only as hard as D2's dial. Two types were not broken by the shipped battery, which means
  "not broken below the hardest subtlety tested" and not "always caught". Finding those limits needs
  a dial that goes further, which is a change to D2 and out of scope here.

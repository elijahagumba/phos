# ADR 0016 — The graded attack library: flavour separation, measured ground truth, and the anti-fingerprint discipline

- **Status:** Accepted
- **Date:** 2026-08-17
- **PART:** D2
- **Supersedes:** nothing
- **Depends on:** [ADR 0015](0015-simulated-plants-the-injection-hook-and-the-true-state-record.md)

## Context

D1 built three simulated plants, an injection hook designed so that a manipulated run is separable
from a normal one *by the manipulation and by nothing else*, and a true-state record kept
independently of what the instruments report. It built no attacks.

D2 builds the attacks. The purpose is not to produce attacks Atlas can catch — that would be
trivial and worthless. It is to produce attacks across a full difficulty range, including ones
aimed at Atlas's central modelling claim specifically, so that D3 can find exactly where Atlas
goes blind. An attack library that only produced easy attacks would be a failure of this PART.

Two things had to be got right or the whole effort is void:

1. The two kinds of adversary — one that acts on the plant, one that acts on the data pipeline —
   support claims that are **not interchangeable**, and must never be reported as the same thing.
2. An attack must not leave an incidental tell. If a manipulated run differs from a normal one by
   anything other than the manipulation, Atlas can learn the artefact instead of the attack, and
   every detection number measured afterwards is worthless in the flattering direction.

---

## Decisions

### 1. The flavour separation is structural, in four places, not conventional in any

A detection attack supports *"Atlas detects plant attacks down to this level of subtlety"*. An
input-hostile attack supports *"Atlas handles hostile input safely"* — which is **not** a claim
that PHOS is secure against a real attacker, and would need a live deployment this project does
not have.

Rather than write that down and hope, the confusion is made unrepresentable:

| Where | How |
|---|---|
| **The type** | `AttackType.flavour` is a *derived property*. `LIAR` is `DETECTION` because of what it is. There is no field to set wrongly. |
| **The ground truth** | `AttackGroundTruth.flavour` is a Pydantic `computed_field`. A caller who passes a flavour is overruled rather than believed, and the serialised manifest still carries it for a reader. |
| **The plan** | `AttackPlan` refuses an input-hostile type at construction; `HostilePlan` refuses a detection one. A config file cannot express the confusion. |
| **The corpus** | `AttackDatasetConfig` refuses to hold both lists. A malformed record inside a labelled attack window would make it impossible to say whether a detector missed the attack or choked on the rubbish. |

And the load-bearing one: **`HostileGroundTruth` has no `interval()` method.** A detection attack
yields the `LabelledInterval` that labels its window; an input-hostile case has no counterpart, so
there is no route by which it can reach a corpus's `attack_intervals` and be scored as a missed
detection. The boundary is the absence of a road, not a rule about which road to take. This is
asserted directly in `tests/synth/attacks/test_spec.py` and again in `test_hostile.py`.

### 2. Ground truth is *measured*, not intended — and an inert attack is refused

Every corpus is **two simulations of one seed**: a clean run, then the same run under attack.
What each attack did is the difference between them.

This is worth the doubled cost for a reason that is not convenience. An attack whose parameters
looked dangerous but which the plant absorbed is an attack that did nothing, and a corpus that
labelled its window anyway would teach D3 that Atlas missed something that never happened. So
`inject` compares the runs sample by sample and **refuses to produce a corpus containing an attack
that moved neither the true state nor a single reading**, unless `allow_inert=True` is passed —
which only the anti-fingerprint tests do, because the zero-magnitude control is their subject.
This is the enforcement of D1's own warning that a manipulation quietly doing nothing would be
labelled as an attack that quietly did nothing, "the worst possible ground truth".

The clean run does a second job: it is what every attack is *parameterised against*. A
manipulation blended toward a value that run actually took cannot leave the range that run
actually occupied — so "every signal stays inside its own normal range" is true by construction
rather than by luck.

### 3. Two measurement spans, because two different questions are being asked

- `report_departure` is measured **over the attack's window**: what could a detector have seen
  while this was happening? For the liar this is small on purpose, and it is the number that
  matters.
- `truth_departure` is measured **from the window's start to the next attack's window** (or the
  end of the run): how much real danger did this cause? The danger outlives the manipulation — a
  clearwell filled by a lie is still full after the lie stops — and cutting at the window's edge
  would understate it. Windows never overlap, so every sample is attributed to exactly one attack.

The corpus is **labelled over the window only**, which is the convention every published ICS
corpus uses. The recovery tail is recorded and not labelled, so a detector that fires only during
the manipulation is not penalised for the plant's inertia.

### 4. The dial is a *relative* departure, so zero magnitude is a no-op by arithmetic

D1's `HoldActuator` and `HoldReading` put a signal at an **absolute** value, and an absolute hold
has no path to zero magnitude: "hold this valve at 90%" is either applied or not. D2 therefore
adds four relative manipulations — `ActuatorOffset`, `ActuatorRamp`, `ReadingBlend`,
`ReadingTrack` — each defined as a *departure from what the plant was going to do anyway*.

`strength_of(subtlety)` returns `1 - subtlety`, which is **exactly** `0.0` at full subtlety. The
arithmetic is then applied unconditionally: there is no branch that skips it, because a branch is
a difference in code path and the whole discipline is that there is only one. The consequence is
tested for all seven detection types: a subtlety of 1.0 produces a run whose every reported value
and every true value equals the clean run's, bit for bit.

**Where the dial does not reach zero, and why that is honest.** A packet either exists or it does
not, so a command attack has no continuous path to "no command at all". What the dial reaches for
`ROGUE_COMMAND` and `MIMIC_COMMAND` is *one* write, carrying the value the setpoint already had,
from a device with no business sending it. The irreducible tell of a command attack is who sent
it, and that is the correct floor.

### 5. A falsified reading carries pseudo-noise, drawn from outside the plant

Pull a reading all the way onto a chosen value and the signal goes perfectly smooth. A transmitter
that suddenly stops being noisy announces itself to the crudest variance check there is — and
that would let Atlas find the *injection* rather than the attack.

So `ReadingBlend` and `ReadingTrack` carry a `jitter`, and the library sets it to the signal's
**own declared `noise_stddev`**. That rule is right in every case including the case where the
right answer is zero: a setpoint declares no noise, so a held setpoint stays exactly constant,
which is what a real setpoint does.

The noise comes from `pseudo_noise`, a pure function of the clock and the signal's name — three
uniform draws from a splitmix64 finaliser, summed, which gives a standard deviation of exactly one
and a passable bell. It cannot come from the plant: D1's hook forbids an injection touching the
plant's random stream, because that is what keeps the per-step randomness rate constant and the
bit-identity property provable.

**Residual, stated rather than hidden:** pseudo-noise reproduces the instrument's noise and *not*
its slow calibration drift, whose phase is drawn from the plant's setup generator and cannot be
reconstructed from outside. At full strength a falsified signal is therefore drift-free. This is a
known, unclosed gap and the second thing to check if Atlas scores suspiciously well.

### 6. Every attack is built from the plant's own declaration, and refused otherwise

The library is declaration-driven, not a per-plant recipe book. Refusing is the feature:

| Attack | What the plant must declare, or it is not built |
|---|---|
| `BLATANT`, `STEALTH_DRIFT` | The target is a declared **actuator**. Pushing a measurement would be falsifying telemetry, a different attack with a different label. |
| `CORRELATION_BREAK` | A `Coupling` from the named driver to the named driven signal. A break has to break a relation the plant *claims* exists, or the label asserts a violation of nothing. |
| `LIAR` | A `CouplingKind.CONTROL` relation joining the falsified measurement and its setpoint. False data injection is only that where something believes the data; falsifying a reading nothing acts on moves no plant. |
| `MIMIC`, `MIMIC_COMMAND` | A benign event of the named kind that genuinely occurred in this run *and* changes the target signal. A disguise has to be of something the plant does. |
| `ROGUE_COMMAND` | An issuer with **no** legitimate write history. `MIMIC_COMMAND` requires the opposite. |
| Any command attack | A declared control network. The reactor has none, so no command attack can be staged against it. |

A related resolution: **`event_touches` counts both routes.** A works run over Modbus records a
setpoint change as a *write*; the reactor, which has no control network, records the same kind of
change as an event *parameter* and puts nothing on any wire. Taking only the writes would say the
reactor performs no setpoint changes at all, and a mimic of one would be refused on a plant that
genuinely does them.

### 7. Wire and telemetry must agree, so a command attack is a setpoint hold *plus* its traffic

A rogue write that appeared on the wire while the setpoint it wrote never moved would be findable
by comparing the two outputs of one run — a tell of how D2 assembled the corpus, not of what an
attacker did. So a command attack pins the setpoint to *exactly* the value the write carries, at
blend strength 1.0, with the dial carried entirely by how far that value sits from the anchor the
setpoint legitimately held. The write carries `register_count(spec, value)` of the same number.

This forced a constraint worth having anyway: an attack holding a setpoint is **refused if a
genuine operator write to the same setpoint falls inside its window**, because two hands on one
setpoint leaves "who moved this" with two answers. The three setpoint-holding kinds in each
shipped battery therefore take three different setpoints.

It also produced three attacks on one setpoint that differ only in what reaches the wire —
`MIMIC` (no write at all: an attacker at the PLC), `MIMIC_COMMAND` (a plausible write from the
device that legitimately writes: an attacker at the HMI), `ROGUE_COMMAND` (a write from a device
that never writes). Same telemetry shape, three different evidence pictures. That is exactly what
D3 needs to find out whether command visibility is worth anything.

### 8. Commands are spliced into the step stream, not simulated

D1's plant emits the traffic its own process implies, and D2 modifies no D1 module. An attacker's
writes are added afterwards as `CommandIntent`s on the steps they land on, appended after whatever
the process generated at that sample — which is D1's own ordering for an operator's write
following a cyclic poll, so the ordering carries no tell. The `reason` field records provenance
for ground truth; the traffic renderer never puts it in a byte.

### 9. The dial is monotone *at a fixed window*, and the shipped battery is not

Measured across the shipped battery, peak departures are **not** monotone in subtlety. This is not
a defect and it is worth stating plainly: each difficulty band sits at a different hour of the
plant's day, and the plant's own rhythm — demand cycle, filter fouling, which loop is saturated —
dominates the comparison. Monotonicity is a property of the dial, not of the corpus, and
`test_antifingerprint.py` measures it the only way that means anything: the same attack, the same
window, subtlety swept. All seven types are monotone there and reach exactly zero.

The measurement that drove a change: at subtlety 0.95 a blatant attack still moved the works'
inflow by ~11 standard deviations. The top band of every shipped battery is therefore **0.99**,
where the departure is around one standard deviation — genuinely near-invisible — while still
being non-zero, which the inert check independently confirms for all 76 shipped attacks.

### 10. One corruption per input-hostile corpus

The four corruptions were first shipped in one file. Generating it showed why that is wrong: the
malformed records made the whole file unloadable, so nothing whatever was learned about what the
out-of-range values or the poisoned baseline would have done. Separated, each corpus answers
exactly one question. Four hostile corpora, one corruption each.

### 11. The CSV writer is duplicated rather than D1's being changed

`phos.synth.telemetry.write_csv` hard-codes a label of zero, which is right for a corpus with no
attacks and wrong here. D2 modifies no D1 module, so the row is rebuilt in
`phos.synth.attacks.generate.telemetry_lines` — to the same five decimal places, with the same
`\r\n` terminators. The formatting is identical **on purpose**: a corpus whose numbers were
formatted differently from a normal one would be separable by its formatting rather than by its
contents, which is precisely the failure this PART exists to avoid. `test_antifingerprint.py`
asserts the decimal places, the field count, the timestamp spacing and the capture size directly.

---

## Ambiguities in the PART, and how they were resolved

| Ambiguity | Resolution |
|---|---|
| "A rogue command from a device with no legitimate history of issuing it" — a device outside the declared network, or a declared one that never writes? | A **declared node with no write history** (the SCADA poller, which only reads). A device absent from the register map could not be rendered without changing D1's traffic module, and a compromised existing engineering station is the more common ICS pattern anyway. |
| What does "difficulty" mean numerically? | A single `subtlety` in `[0, 1]`, with `DifficultyLevel` as four derived bands for reports. One dial, so "turning subtlety up" has one meaning across all seven types. |
| Should input-hostile cases appear in `attack_intervals` under a different label? | **No.** The harness's `is_attack` ignores the label string, so any interval would be scored as a detection target. They appear only under the manifest's `hostile` field. |
| Should the true state be published? | In a **separate `truth.csv`**, never in the corpus. A detector that could read it would be detecting nothing. |
| May attack windows overlap? | **No.** Overlapping attacks make "which attack was this sample" have two answers, and the whole value of synthetic ground truth is that it has one. Abutting windows are allowed. |
| Where should the mimic's value come from? | The range the target setpoint **legitimately occupied in the clean run**, anchored to what it read when the window opened. A convex combination of two values the plant genuinely used cannot leave the range it genuinely used. |
| Which way should the liar lie? | **Below** setpoint, uniformly. On all three plants a direct-acting loop then drives the true value *up* — overfill, overheat, overvoltage. No direction is assumed in ground truth: the departure is measured, so a reverse-acting loop would be recorded honestly. |

---

## Consequences

**Good.** Ground truth is measured rather than asserted, and a degenerate attack is refused rather
than labelled. The two flavours cannot be confused by any input. Zero-magnitude bit-identity holds
for all seven types, and a KS test at 5% cannot separate a minimal attack from normal — while the
same test *can* separate an obvious one, which is the control that keeps the first claim honest.
Every attack is constructed from the plant's declaration, so the library works on a plant it was
not written against.

**Costs.** Every corpus costs two simulations. The setpoint-holding attacks make the shipped
configs seed-sensitive: change a seed and the genuine event schedule moves, and a window may have
to move with it. The refusal is loud and names the colliding event, which is the intended
workflow, but it is a real maintenance cost.

**What this does not establish.** Nothing about Atlas. D2 runs no model and scores nothing. And
the standing caveat, which no test in this PART can discharge: **these are attacks we designed.**
The library was written by someone who could read the detector, and an attack nobody here thought
of is not in it. A detection rate measured on this data is an upper bound on this library, never a
lower bound on reality. If Atlas scores suspiciously well in D3, the first hypothesis is a leaked
fingerprint — the drift-free falsified signal in §5 being the known candidate — and not
brilliance.

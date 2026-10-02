# The synthetic command-and-maintenance harness: method, construction, and what it gets wrong

**Status:** built, exercised, and measuring nothing.
**Related:** ADR 0073, ADR 0015, ADR 0016, ADR 0029, ADR 0040, ADR 0014, ADR 0069, ADR 0027.

---

## What this is, and what it is not

This is a **test harness**. It exists because two Atlas capabilities are built, wired, tested, and
completely unmeasurable, and no data PHOS can obtain carries what they need.

| Capability | Built | Measured on real data | Why not |
| --- | --- | --- | --- |
| Unauthorised-command attribution | yes | **no** — known-station unique lead stands at 0 of 16 | No public corpus carries command-action ground truth (ADR 0040) |
| The CMMS / work-order join | yes | **no** — nothing has ever been measured through it | No public corpus ships a maintenance calendar (ADR 0069) |

The existing synthetic library could not exercise either. Its plants had a control network whose
writes were **cosmetic** — a benign event moved a setpoint, and the write emitted afterwards
carried the value the setpoint had already taken, so deleting the capture changed nothing — and no
maintenance register at all.

This harness closes both gaps so the machinery can be exercised, debugged and improved while the
search for real data continues.

**It is not a corpus.** It produces no detection claim, ever. Specifically:

- Nothing measured on it enters `eval_runs/log.jsonl` as a public row.
- Nothing measured on it is quoted in `README.md`, `encyclopedia/`, the easy-to-reads, or any
  outward-facing surface as a detection result.
- Nothing measured on it is compared against a frozen public row.
- Every improvement to Atlas or Sentiel derived from it is labelled **SYNTHETIC-DERIVED** wherever
  it is recorded, and states that it is unvalidated until real data arrives.

ADR 0029 already establishes that the synthetic library is not a public corpus. That stands, and
this work reinforces rather than weakens it: a harness that can now exercise *more* machinery is a
harness whose results are *more* tempting to quote, which is why the refusals below are mechanised
rather than written down.

---

## The anti-bias construction

The central risk is circularity. If the same mind specifies both what an attack looks like and what
the detector looks for, then a good score measures the agreement of two beliefs, not detection.

PHOS already refuses this one level down: **topology is declared and never clustered**, and **peer
groups come from the directory and never from behaviour**. The five mechanisms below are the same
refusal one level up. Each is enforced by a test in `tests/synth/test_anti_bias.py` that fails a
build — none is an intention.

### 1. The generator may not reference the detector

No module under `src/phos/synth/` may import from, or name, any Atlas or Sentiel feature, score,
threshold, model, or detection concept. `test_no_generator_module_imports_a_detector_beyond_the_declared_exception`
parses every generator module's AST and fails on any such import.

**The one exception, declared by name.** `phos.synth.topology` imports `SCHEMA_VERSION`,
`Subsystem` and `SubsystemMap` from `phos.atlas.topology`, so a generated corpus ships its declared
subsystem map in exactly the format a real corpus does. That is a *declaration format* — it carries
no feature, no score, no threshold and no finding. The allowlist names the module **and the three
symbols**; any other name from that same module fails. A further test asserts the exception is
actually used, so a dead entry cannot sit there widening the hole.

The four modules this work added — `command.py`, `maintenance.py`, `scenarios.py`, `realism.py` —
carry **no** exception, and a separate test holds them to zero.

### 2. Attacks are specified by physical or operational intent, never by signature

A scenario states a **goal in the plant's own terms** and the constraints the adversary works
under. What that does to the readings and the traffic is derived by simulating it.

> "Drive the clearwell above the level the works is operated to, in one move, so the treated water
> overflows to waste."

It is forbidden to specify an attack as "make signal X deviate by Y", or in terms of any quantity
the detector computes. This is enforced two ways:

- `test_no_scenario_names_anything_atlas_exports` scans every scenario's prose against **Atlas's
  own `__all__`**, so the forbidden lexicon widens automatically as Atlas grows.
- `test_difficulty_is_carried_by_patience_not_by_a_magnitude` asserts the `Scenario` model has no
  field named `magnitude`, `deviation`, `strength`, `subtlety`, `sigma` or `z_score`. There is
  nowhere to put one.

Difficulty is carried by **`patience_steps`** — how long the adversary is willing to take. That is
an operational choice a real attacker makes, and the band of undetectable cases falls out of it
rather than being placed there.

### 3. Every scenario carries real-world provenance

Each scenario cites a documented incident, a published ICS attack taxonomy, a process-engineering
failure mode, or a vendor advisory. The `Provenance` model has **nowhere to record** "this would be
interesting for Atlas", and its validator rejects a citation containing `atlas`, `sentiel`,
`interesting`, `tbd`, `todo` or `n/a`.

The ten scenarios draw on: the ESET and Dragos Industroyer/CRASHOVERRIDE analyses; the Symantec
W32.Stuxnet dossier on falsified process reporting; the CISA/FBI/EPA advisory AA21-042A on the
Oldsmar water-treatment setpoint alteration; MITRE ATT&CK for ICS T0836 and T0831; conventional
surface-water treatment practice on clearwell overflow and chlorine contact time; and the CISA
advisory class covering unauthenticated Modbus writes to governor parameters.

### 4. A mandatory band of cases the detector should miss

A generator that only produces catchable attacks is a mirror. Two tests fail a build that has
become one:

- `test_the_catalogue_contains_attacks_below_any_plausible_floor` requires scenarios whose
  adversary walks a setpoint over 720+ samples — a per-step change far under the plant's own
  ordinary variation.
- `test_a_realism_run_produces_benign_cases_that_would_tempt_a_detector` requires a generated run
  to produce benign phenomena deliberately shaped like attacks, and fails if it produces none.

### 5. The method is publishable, including its failures

This document, and the section below, which is a **required deliverable** — `tests/synth/test_anti_bias.py`
fails if it is shorter than 400 words.

---

## How the harness is built

### The command layer

`phos.synth.command` adds three things the plants lacked.

**Writes are causal.** A `CommandSource` is consulted once per sample, *before* the controllers
run. A write is applied to the plant's own state, so the setpoint it moves is the setpoint the loop
closes on at its next scan, and the loop moves the true state. The counterfactual test is the one
that matters: the same run with the write removed reaches a different true state. A cosmetic write
would leave the two identical.

**Authorisation is declared, not asserted.** `WriteAuthority` is part of a `PlantDescription`: which
device the plant permits to write which signal. The authorisation recorded against an observed write
is *derived* from that declaration. `PlannedWrite` deliberately has no authorisation field, so a
scenario cannot label its own commands.

Granting exactly one station produces three cases worth building:

| Issuer | Authorisation | On the learned graph |
| --- | --- | --- |
| `hmi` | authorised | known station |
| `scada` | **unauthorised** | known station — the compromised legitimate host, the hard case |
| `engineering` | unauthorised | unknown master (the ADR 0027 shape) |

**Ground truth is kept apart from the observable.** `IssuedCommand` records what was really
commanded and whether it was really authorised; `CommandIntent` is what a capture shows. An
authorised write and an unauthorised one are **the same bytes**, because in a real plant they are.
A test builds two plants differing only in declared policy, confirms the ground truth differs, and
asserts the rendered frames are byte-identical.

The protocol is Modbus/TCP, which Atlas already dissects, so the existing packet path consumes it
with no new dissector.

### The maintenance calendar

`phos.synth.maintenance` generates a register from routine intervals, reactive callouts and planned
shutdowns, and writes it as an SAP PM or IBM Maximo CSV export using those systems' own field names
(`AUFNR`/`EQUNR`/`GSTRP`/`GLTRP`, `WONUM`/`ASSETNUM`/`SCHEDSTART`/`SCHEDFINISH`).

`plan_maintenance` takes `(rng, spec, assets, practice)`. It takes **no attack schedule**, and the
module imports nothing that could supply one — both are asserted by tests. A calendar laid out
around where the attacks are would make every covered attack a covered attack *by construction*.
Here, coverage is a **collision between two independent schedules**, which is what it is in a real
plant — including the hard case ADR 0014 and ADR 0069 both name: an attacker operating inside a
sanctioned window.

A share of orders carry non-sanctioning statuses (SAP `CRTD`/`DLFL`, Maximo `WAPPR`/`CAN`), so ADR
0069's refusal that a cancelled order authorised nothing is exercised by data rather than by a
fixture. Nothing in `maintenance.py` imports `phos.atlas.cmms`; the columns are literals, and the
test loads what it writes through the **real** adapter.

### Operational realism

`phos.synth.realism` adds grade changes, ambient and seasonal drift, equipment ageing and fouling,
benign operator interventions, sensor faults and calibration drift that are **not** attacks, comms
dropouts and retransmissions, and startup/shutdown transitions.

All of it is benign, several kinds are deliberately shaped to resemble attacks, and a
`RealismProfile` left at its defaults produces nothing — so every corpus generated before this
existed is reproduced byte for byte.

---

## What the synthetic data probably gets wrong

This section is the point of the document. Everything below is a way this harness is likely to
mislead, written down while it is still uncomfortable to write.

**The physics is a model of a process, not a process.** Every plant was written from public
descriptions of how such processes behave — coagulation and rapid gravity filtration, chlorine
contact time with first-order decay, square-root valve characteristics, quadratic pump curves,
`P=√3·V·I·cosφ`. None of it was fitted to, or validated against, any particular works or station.
The dynamics are almost certainly too clean: real plants have unmodelled interactions between
units, hysteresis in valves and dampers, stiction, dead bands, and operators who do things the
model has no representation for. A detector that learns our plant is learning something smoother
than reality, and its false-positive rate on a real plant will be **worse** than anything measured
here — probably much worse.

**The noise model is too kind.** Instrument error here is Gaussian noise plus a bounded sinusoidal
calibration drift. Real instrument error is heavy-tailed, correlated across instruments sharing a
transmitter or a power supply, and punctuated by spikes, freezes and rail-outs with no distribution
behind them. A Mahalanobis-style model tuned against Gaussian residuals will look far better here
than it deserves to.

**The control network is impoverished.** One protocol, one unit id, a fixed poll cycle, and a
handful of devices. Real plants carry several protocols simultaneously, redundant masters, serial
gateways, engineering tools that poll erratically, historians, asset-management traffic, vendor
remote-access sessions, and long stretches where the network looks quite different because someone
is commissioning something. Anything Atlas learns about "normal command behaviour" here is learned
against a network far more regular than a real one, and command-behaviour features will be more
stable — and therefore more discriminating — than they will be in the field.

**The write authority is a fiction of convenience.** Granting exactly one station is a clean
three-case structure that makes the harness expressive. Real plants have messy, partially
documented, frequently violated access policies; engineers write from whatever station is nearest;
shared accounts are common; and the difference between "authorised" and "unauthorised" is often
genuinely ambiguous rather than a lookup. Treating authorisation as a clean declared fact is the
single largest idealisation in the command layer.

**The maintenance practice is invented.** The intervals, the callout rate, the outage cadence and
the share of non-sanctioning orders are plausible numbers, not measured ones. Real registers are
far dirtier: orders raised retrospectively, windows that bear little relation to when work actually
happened, assets named inconsistently, orders left open for months, and work done with no order at
all. The **coverage rate** — how often an anomaly falls inside a sanctioned window — is the number
most likely to be badly wrong, and it is precisely the number the CMMS join's value depends on.
Nothing here should be read as evidence about how often real maintenance explains a real anomaly.

**The adversary is more consistent than a real one.** `GoalSeekingSource` walks a straight line to
its goal at a fixed patience. Real intruders hesitate, retry, make mistakes, act on stale
information, abandon attempts, and interleave their actions with reconnaissance the harness does not
model at all. There is no lateral movement here, no credential theft, no dwell time, no attempt to
cover tracks, and no attacker who reads the maintenance calendar and *chooses* a window — which,
given that the covered-window case is a headline capability, is a real gap.

**The benign class is still too easy, even after this work.** Real plants produce most false
positives from things nobody thought to simulate. The seven phenomena added here are the ones we
could think of; the ones that matter are, almost by definition, the ones we could not.

**Coverage collisions are rare and the sample is small.** Because the two schedules are genuinely
independent, the number of attacks landing inside sanctioned windows in any one run is small and
seed-dependent. Any statement about what Atlas does in the covered-window case rests on a handful
of instances, and is an anecdote about machinery rather than a rate.

**The whole thing shares an author with the detector.** The five mechanisms above reduce
circularity; they do not eliminate it. The same person chose which processes to model, which
failure modes to consider interesting, and which real-world citations to draw on. A scenario
catalogue assembled by someone who had never seen Atlas would be different, and the difference is
unmeasurable from inside.

---

## What no result here may be used for

- Not a detection rate, a recall figure, or a false-positive rate for any real environment.
- Not a comparison against, or a replacement for, any frozen public row — HAI Mahalanobis 646.58,
  grouped 53.26, distillation 18.72, CERT 6B 0.104 are untouched by anything here.
- Not a row in `eval_runs/log.jsonl`.
- Not evidence that command-lead has moved off 0 of 16, which is a public-corpus fact and stays
  frozen (ADR 0034, 0038–0040).
- Not evidence that the CMMS join improves any queue, ranking, or explanation split.
- Not a claim of ≥70%, 10×, or 2–3 alerts/day.
- Not a substitute for a public ICS corpus or a CERT corpus, and not a reason to stop looking for
  one. The design-partner conversation (P1) remains the next real step.
- Not grounds to pool known-station and unknown-master issuer kinds, here or anywhere.

What it **may** be used for: exercising machinery that has never run, finding defects in it,
and knowing what to ask a design partner for.

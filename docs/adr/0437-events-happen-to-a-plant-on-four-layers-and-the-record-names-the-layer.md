# ADR 0437 — Events happen to a plant on four layers, and the record names the layer

- **Status:** Accepted
- **Date:** 2026-11-13
- **PART:** R4
- **Supersedes:** nothing
- **Depends on:** [0436](0436-a-drawn-plant-is-refused-before-it-is-written.md), [0435](0435-a-family-draws-a-plant-and-one-family-is-sealed.md), [0027](0027-unknown-master-writes-are-not-maintenance.md), [0017](0017-the-breaking-harness-fingerprint-classification-and-judging-from-true-state.md)

## Context

PART R3 writes a generated plant to disk, and every sample of it is normal. PART R4 fills the
other side: the attacks, faults, maintenance and operator behaviour that make the data worth
scoring against. R4's first instruction is an audit — mark each item of a target catalogue as
exists, partial or missing, and **do not rewrite what exists**. The audit is `docs/sim/coverage.md`
and it is the decision this record rests on.

## Decision 1 — Audit first, and most of R4 is labelling rather than physics

The audit found that most of the *effects* the catalogue asks for already exist, in
`phos.synth.injection` (two manipulation layers) and `phos.synth.realism` (benign phenomena). A
stuck transmitter, a drift, a dropout, a loop taken to manual — all were already modelled. What was
missing was the **label**: a record saying what kind of thing happened, which layer it acted on,
and whether it had a physical consequence. Re-implementing the effects would have been the mistake
the audit exists to prevent, so R4 mostly schedules and labels what the package could already do,
and builds genuinely new physics only where the audit found none.

That shaped the whole part. `phos.synth.events.EventRecord` carries the seven facts R4 asks for,
including the one the existing `AttackGroundTruth` does not: the **layer**. Two of those facts —
whether the process moved and whether the event stayed inside the normal range — are *measured* by
`assess_events`, by running the same plant twice on the same seed and comparing, not declared.
Declaring them would make a stealth result unearned. And both are measured over *every* signal, not
only the tag the event names: a valve stroked through its travel disturbs the signals above it, and
measuring only the valve would call that stealthy because a valve's own reading is of course inside
a valve's own range.

## Decision 2 — A plant has four manipulation layers, and the new two are opt-in

`Injection` reached a plant at two layers: what the instruments report and what the actuators do.
R4 found two catalogue items that fit neither, and added a layer for each — as **opt-in protocols
the base `Plant` checks by `isinstance`**, so every existing injection and `NoInjection` are
untouched and a normal run stays byte-identical. The six golden corpora prove it rather than the
claim resting on inspection.

- **The process layer** (`injection.ProcessLoss`), for the **leak**. A leak removes inventory by a
  route nothing meters — not a sensor manipulation, not an actuator one. It is applied to the true
  state after the physics advances and before the instruments read, so its consequences propagate
  through the loops: the level falls, the sensor sees it, the loop pumps harder. It is the one
  fault a conservation check is built to catch, and the test for it is that the residual *moves* —
  a balance that kept closing during a leak would be the tell that nothing really leaked. This is
  ADR 0017's principle (judge from true state) applied to a fault: the loss is in the state, not
  painted on the telemetry.

- **The network layer** (`phos.synth.wire`), for the three attacks that act on the wire rather than
  the plant: a value changed in transit, a polling flood, a traffic replay. These are transforms on
  the *already-built* capture — `modbus_frames` is untouched — so the plant's physics and its
  telemetry are left alone, and the wire can now say something the historian did not. That
  asymmetry is the whole point of the layer: a detector comparing the two has the one piece of
  evidence that separates them. A replay and a flood reuse TCP sequence numbers on purpose, because
  `docs/sim/recon.md` §5 records that the Modbus dissector does no reassembly — renumbering them
  would be a capture of an event that never happened.

## Decision 3 — Events are scripted from seeds, and nothing here searches

R4 says it explicitly and this record holds it: no attack search, no optimisation, no scoring.
There is nowhere in `events.py` or `wire.py` to put a detector's response, and that is deliberate.
PART S7's breaker is where a search belongs, in a separate package, for the reason ADR 0435 gives
for sealing a family — a generator that could aim at a detector's weak spot is no longer generating
data, it is tuning against a target. The schedule is drawn from one stream, kept apart from the
plant's own seed so that adding events cannot move a physical parameter, and `plan_events` refuses
a catalogue that would leave less than three-quarters of the run normal rather than cramming it.

## Decision 4 — One catalogue item is deferred, with its reason, not quietly dropped

**Control-logic parameter tampering is not built.** A controller's gain, integral time and output
limits are *internal* plant state. None of the four layers reaches them: the sensor and actuator
layers perturb a plant "through its own mechanisms", the process layer removes inventory, and the
network layer acts on the wire — but a loop's own tuning is none of those. Building it means every
one of the six templates routing its controller construction through a time-varying parameter
source, a cross-cutting change to all of them and the base `Plant` for a single attack. That is a
design decision with its own cost and belongs in its own declaration, not smuggled into R4 where it
would be the one effect built unlike all the others.

**The operator self-corrected error is deferred with it.** Both want a cleaner operator-write path
than R4 provides — a setpoint written wrong and corrected is an operator *write*, which lives in
`command.py` and the families' `DisturbanceSpec`, not in the injection path R4 built. Pairing the
two keeps that path a single later piece of work rather than two.

Both are listed in `docs/sim/coverage.md` as deferred rather than done, so the gaps are visible
rather than buried. Everything else in the catalogue is built: the sensor replay, three faults
(stuck valve, pump trip, leak), three maintenance effects (sensor offline, valve exercised,
controller in manual), and the three network attacks.

## Decision 5 — A hardening of the no-network rule, which the audit's own work triggered

PART S0's fifth rule is that attack code touches only simulated signals and files this package
writes — no sockets, no scanning, no real devices. `tests/synth/test_no_network.py` now asserts it
by walking every module's AST, and bans the packet libraries (`scapy`, `pymodbus`) as well as the
network clients, because `traffic.py` writes Modbus frames with `struct` on purpose and importing a
library that could also transmit them would leave nothing but convention in the way.

It caught a real regression on its first run: PART R3 had added `import subprocess` to
`phos.synth.outputs` to ask `git rev-parse` for the commit hash. Shelling out is not reaching a
device and the rule was not aimed at it, but the rule is drawn around exactly that shape. The commit
is now read out of `.git` as two small text files, handling the worktree case this branch is checked
out in, and it returns the same hash `git` does.

## Consequences

**What a generated corpus now contains.** `generate_plant` takes an `EventCatalogue` and writes the
scripted events into `labels.json` beside the benign ones. The attack and fault intervals are the
detection targets; the maintenance intervals are cover, labelled so a detection on one is not
scored as a catch. A corpus with all four layers of events verifies against its manifest, ingests
through `LabelledCsvAdapter` unchanged, and its capture — injected and replayed frames and all —
dissects through the real Modbus dissector with zero malformed frames. The same seed regenerates it
byte-identical.

**What PART S6's referee inherits.** The label shape it will score against exists and is written.
It has the layer on every event, which bounds what a detector could have noticed; the measured
physical-effect flag, which is what "a physical-effect attack was missed" is counted from; and the
measured within-range flag, which is what "stealthy" means. None of it is declared, so a stealth or
a physical-effect result is a fact about the run rather than the generator's intention.

**What is still owed, and is R4's debt rather than a surprise.** Control-logic parameter tampering
and the operator self-corrected error are deferred, both named above with reasons. The
cross-parameter consistency check ADR 0436 left open is still open — `validity.py` catches a
governor holding to the wrong frequency through its consequences, but not two parameters that
disagree about what the frequency is.

**The caveat is unchanged.** A generated plant with an attack on it is still a model, not a plant,
and an attack on it is a model of an attack. Every manifest carries `MODEL_NOT_REALITY_CAVEAT`, and
no result measured on one may be quoted as a result on a real plant (ADR 0143).

**No measurement.** This record builds events, labels and a no-network test, and scores nothing. It
opens no committed corpus, runs no harness, moves no frozen number, and does not touch P1.
Everything it writes is to a git-ignored directory.

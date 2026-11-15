# ADR 0434 — A plant is a document, and its physics is a named template

- **Status:** Accepted
- **Date:** 2026-11-12
- **PART:** R1
- **Supersedes:** nothing
- **Depends on:** [0433](0433-physics-constrained-plant-randomisation-for-training-data.md), [0015](0015-simulated-plants-the-injection-hook-and-the-true-state-record.md), [0010](0010-declared-topology-and-the-granularity-hai-supports.md)

## Context

ADR 0433 recorded the gap and built nothing: three plants whose structure lives in their source
code, a seed that varies their noise and their event schedule but never the plant, and three empty
modules — `families.py`, `randomise.py`, `validity.py` — with a docstring each saying what would go
in them.

PART R1 is the step before any of those can be filled. Before a generator can *draw* a plant, a
plant has to be something that can be drawn: a document with the free numbers named, rather than a
class with constants in it. So R1 asks for a `PlantSpec` that fully describes a plant, a builder
that turns one back into a running `Plant`, the three existing plants re-expressed through it, and
— the safeguard the whole thing rests on — byte-identical output for the corpora that existed
before.

That last requirement is what makes the design question sharp rather than a matter of taste. The
three plants do not share a physics. The water works carries contact-time chlorine decay; the
generating set carries an electrical solution and a tap changer that steps on a timer; the batch
reactor carries Arrhenius kinetics, a vessel-mixing term and a phase state machine. Between them
they hold about a hundred and sixty hand-tuned constants and three bodies of arithmetic that were
written, tuned and tested one at a time.

## Decision 1 — The spec holds the plant; a named template holds the physics

`phos.synth.plant_spec.PlantSpec` is frozen, round-trips through JSON, and declares: the
components and the connections between them, the control loops and their tunings, the instruments
with their tag names and error models, the scan period, the disturbance model, the couplings, the
register map, the write authority, and a flat mapping of every free number the physics reads.

What it does not hold is the arithmetic. The body stays a named *process template* —
`"water-treatment-v1"` and its two siblings — and the spec supplies the numbers it reads. A
template reads `self._p.max_intake_m3ph` where it read `_MAX_INTAKE_M3PH`.

The alternative was an executable dataflow graph: nodes, edges, and a builder that evaluates them
in topological order. It is what PART R1's text literally asks for, and it was declined for two
reasons, neither of them schedule.

The first is that it would not be declarative. Reproducing these three plants needs a node type for
Arrhenius kinetics, one for vessel mixing, one for a tap changer's wait-then-step, one for a pump
curve, one for a phase state machine. Each exists for exactly one plant. That is the bespoke code
with a `Node(...)` wrapper around it, and the generality is in the wrapper rather than in the
model.

The second is arithmetic. Byte-identity over a 14,400-sample run is identity in the last bit of
every double. Evaluating `a + b*c` as a graph of two nodes rather than one expression reassociates
the operation, and reassociated floating point is not the same number. A graph transcription would
have had to be checked term by term against three bodies of arithmetic, and the failure mode — a
corpus that drifts in the fifth decimal place — is one nobody would notice without the golden
record and nobody could explain with it.

So the component graph is a **declaration its template must honour**, not the thing that executes.
That is the stance ADR 0010 already takes on topology, for the same reason: a structure derived
from the statistics it exists to explain explains nothing.

The honest limitation, stated here rather than left to be discovered: a template could disagree
with its own spec's component graph, and nothing at run time would catch it. What is enforced is
the part that can be — the graph has to agree with the *instruments* — and what is not enforced is
named in Decision 3.

## Decision 2 — The graph has to agree with the instruments, or the spec is refused

`PlantSpec` refuses a component on an undeclared unit, a signal owned by two components, a signal
no component owns, a connection to a component that does not exist, a loop driving a measurement,
a loop holding to a setpoint that is not a setpoint, a loop holding to nothing, and a loop holding
to two things. A component's signals must sit on the component's own physical unit.

That last rule is what makes `topology.subsystems_from_components` sound. The subsystem map can be
read off the component graph — off *what the plant is made of* — and comes out as the same
partition `SignalSpec.physical_unit` gives. The two are computed by different functions and the
agreement is asserted in `tests/synth/test_plant_spec.py` rather than assumed, so a generated plant
in PART R2 can be grouped from its structure before a single sample has been taken.

Two things control engineering needed that bookkeeping would not have:

- A PI loop may hold to a **fixed value** rather than a setpoint signal. The governor holds nominal
  frequency and the AVR holds nominal bus voltage. Neither is a tag anyone writes, and declaring
  them as setpoint signals would have invented two instruments the plant does not have.
- A PI loop may **cascade** into another: a controller's `output` may name another controller, and
  a loop with a master needs no target of its own. The reactor's temperature loop does not touch a
  valve; it decides what the jacket should be at. Whether a loop has a target is therefore checked
  across the whole plant rather than on the loop, because being a slave is a fact about the plant.

The tap changer is neither a PI loop nor a hysteresis element — it is a timer and a single step —
so it stays in its template rather than being described as one of the two control elements
`phos.synth.process` implements. A document whose purpose is to be read must not contain that kind
of lie.

## Decision 3 — The golden record is captured before the refactor, and a moved digest is a result

`scripts/synth_golden.py` records what every corpus in `configs/synth/` hashes to: each file's
SHA-256, size and record count, and the manifest's own SHA-256, which covers the plant's full
declaration, its couplings, its benign events and the run spec. It was captured and committed on
unmodified code, before the first line of the refactor, and `tests/synth/test_golden_corpora.py`
regenerates and compares in the default suite.

The manifest digest is the part that earns its place. A refactor that changed a signal's noise
model, dropped a coupling's driver or renamed a physical unit would leave every published number
untouched and still be wrong, and only the manifest hash catches it.

The test is deliberately not marked `slow`. Six corpora take seven seconds between them, and a
golden check the default suite deselects is a safeguard nobody runs.

**A mismatch is a result, not a thing to fix by recapturing.** Rerunning with `--write` to clear a
red check destroys the only evidence that the refactor preserved behaviour. PART R1 says the same
in its own words: if byte-identical is impossible for a justified reason, stop and report.

It was not impossible. All six corpora match.

## Consequences

**What this buys.** PART R2 draws a plant from a family by drawing a `PlantSpec`: the parameters,
the tag names, the sensor layout, the controller tunings, the scan period, the disturbance
schedule, and whatever structure a template is written to vary. Nothing downstream — the
integrator, the sensor model, the Modbus writer, the injection hook, the topology renderer, the
manifest — needs to know whether the spec it was handed was typed by a person or drawn from a seed.
`PlantSpec` is also what PART V1's `plant.json` and `structure.json` are, which is why the
components carry a plain-language `description` and a closed list of kinds: V4 draws a symbol per
kind, and a free-text kind would be a symbol nobody drew.

**What it costs.** Structural variety in R2 is per-template rather than generic. A family that
wants a different number of stages needs a template written to loop over them; it does not fall out
of a generic graph evaluator. That is a real limit and it is the price of the three existing plants
keeping their numbers.

**What is still owed, and belongs to R2 rather than here.** Two parameters can now disagree with
each other and nothing notices: the governor's declared setpoint and `nominal_hz` both say what
frequency the island runs at. A hand-written spec keeps them consistent because a person wrote
both. A drawn one will not, and `validity.py` is where that check belongs, with the other relations
ADR 0433 listed. No parameter bounds are declared yet either — `PlantSpec.parameters` is a flat
mapping of floats with no ranges on it, because a range is a property of a *family* and families do
not exist until R2.

**The caveat is unchanged and is not weakened by any of this.** A spec describes a model of an
industrial process, not a plant. Unlimited draws from a family are unlimited models. Nothing here
may be described as real plant data, and no result measured on a generated plant may be quoted as a
result on a real one (ADR 0143).

**No measurement.** This record refactors a generator and scores nothing. It opens no corpus, runs
no harness, moves no frozen number, and does not touch P1.

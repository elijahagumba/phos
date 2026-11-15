# ADR 0433 — Physics-constrained plant randomisation for training data

- **Status:** Accepted
- **Date:** 2026-11-12
- **PART:** S0
- **Supersedes:** nothing
- **Depends on:** [0015](0015-simulated-plants-the-injection-hook-and-the-true-state-record.md), [0010](0010-declared-topology-and-the-granularity-hai-supports.md), [0073](0073-a-synthetic-command-and-maintenance-harness-that-measures-nothing.md)

## Context

Atlas's reasoning layer has been starved of varied data since it was built. ADR 0015 answered the
scarcity of *labelled* industrial data by building plants we control: `phos.synth.plants` holds
three — water treatment, power generation, batch chemistry — each with real physics, real control
loops, a true-state record kept independently of the instruments, and an injection hook for D2's
attacks. That was the right answer to the question it was asked.

It leaves a different question unanswered. Those three plants are hand-written and fixed. A seed
varies their sensor noise, their per-instrument calibration drift and their benign-event schedule;
it does not vary the plant. Six tanks are six tanks on every seed. A controller's gain is the number
somebody typed. The topology is the same partition every run, and the signal set is the same list.

So a model fitted on all the data this package can produce has, structurally, seen three plants. It
can do well on them by learning those three — their particular capacities, their particular
tunings, the particular shape their level traces make — rather than by learning how a plant
behaves. Nothing in the harness can tell the two apart, because every corpus it scores comes from
the same three structures. Held-out seeds hold out noise, not a plant.

The failure this matters for is the one PHOS exists to avoid. A detector that has memorised a plant
will look excellent in evaluation and will have nothing to say on a plant it has not met, which is
every real plant. The data is not what is wrong with it; the *variety* of the data is.

The obvious fix is wrong in an instructive way. Perturbing signal values — adding noise, scaling
columns, scrambling — produces data that is different and that is no longer a plant: a tank level
that moves without a flow that moved it, a controller output uncorrelated with the error it was
supposed to be acting on. A model trained on that learns something untrue about industry, and a
detector evaluated on it is being asked to detect departures from a normality that has no
mechanism. Variety has to come from somewhere other than the values.

## Decision 1 — Variety comes from the plant's description, not from its signals

A **family** is a process structure held fixed with its parameters left free: what is connected to
what, which signals exist, and what kind of quantity each one measures, with capacities, gains,
integral times, dominant time constants, flow coefficients, setpoints, instrument spans and
instrument error characteristics drawn per seed, together with the structural choices the family
deliberately leaves open, such as how many units of a repeated kind the plant has.

A seed draws one plant from a family. Two plants from one family are the same process at different
sizes and tunings — which is what two real plants of the same kind are. The draw acts on the
`PlantDescription` and is finished before the first step is integrated, so everything downstream is
unchanged: the same integrator, the same controllers acting on reported readings rather than on
truth, the same sensor model, the same Modbus writer, the same injection hook, the same topology
renderer. A generated plant is a plant to every consumer of one.

## Decision 2 — Every draw is checked against physics, and a bad draw is refused, not clipped

Sampling parameters independently produces combinations no engineer would build: a pump that cannot
fill its tank against the outlet it is paired with, a gain and a time constant that put the closed
loop into sustained oscillation, a nominal level outside its own alarm limits, an instrument span
that does not contain the values the process lives at.

So a drawn parameter set is checked before it is used, against relations between parameters rather
than bounds on single ones — capacity against throughput, control stability at the step the
simulation actually runs at, the nesting of setpoint inside normal range inside alarm limits inside
instrument span, and dimensional sanity. Some of these can only be settled by stepping the plant
through a warm-up and looking, so the check may run the integrator; that is why it lives in the
package and not in the test suite, since it has to refuse a corpus before it is written rather than
fail a suite after.

**A failing draw is refused with the relation it broke named.** It is not clipped into range, not
nudged, not warned about. A clipped parameter set is one the family said was impossible and the
generator produced anyway, and it would reach a corpus wearing the family's claim of validity. A
refusal is a result in the ordinary sense this repository means: a family whose refusal rate is high
has declared ranges wider than its own physics, which is a finding about the family.

## Decision 3 — This lands in `phos.synth`, not in a new `phos.sim`

<!-- evidence-ack: src/phos/sim/ — the layout the brief proposed and ADR 0433 Decision 3 declined; the tree is deliberately not built -->
The brief that produced this record proposed a new package, `src/phos/sim/`, with subpackages for
core physics, plant spec, controllers and sensors, generation, operator schedules, protocol writers
and injection. `docs/sim/recon.md` §1 sets out, module by module, that `phos.synth` already holds
every one of those but the randomisation — `process.py` for the physics primitives, `plant.py` and
`plants/` for the spec and the three plants, `maintenance.py` and `scenarios.py` for operator
action, `traffic.py` for the Modbus/TCP pcap, `injection.py` and `attacks/` for the injection layer,
and `scripts/generate_synth.py` for the command line.

Taking the proposed layout would put a second plant simulator in the tree, and S1–S5 would spend
themselves rebuilding physics that is written, tested and in use. The brief's own clause — "or the
layout the repo prefers, recorded in recon.md" — is the licence not to. So S0 adds three modules to
`phos.synth`, which are the parts that do not exist:

- `families.py` — the structure held fixed and the parameters left free, with the relations between
  them that make this a constrained randomisation rather than a scrambler.
- `randomise.py` — seed to parameter set, drawn through `numpy.random.SeedSequence` spawned into
  named child streams by index, as `phos.synth.plant` already does, so adding a stream for a new
  component cannot shift the numbers an existing one gets.
- `validity.py` — the checks of Decision 2.

Three smaller deviations are recorded in `docs/sim/recon.md` §6 and taken the same way: the command
line stays in `scripts/` where this repository keeps command lines and where pytest can reach it,
the tests go to `tests/synth/` because the test tree mirrors the source tree package by package, and
a dependency's licence is justified in the record rather than in `pyproject.toml`, which carries
exact version pins and no licence column. S0 adds no dependency.

## Alternatives rejected

**Scramble or perturb the signal values.** Cheap, and it destroys the mechanism that makes the data
a plant. Rejected in Context: the resulting corpus has no physics to depart from, so a detector
scored on it is not being measured at anything.

**Leave the three fixed plants and generate more seeds.** This is the status quo, and it is what
makes the gap invisible: more seeds give more noise and more event schedules on the same three
structures, so every number goes up and nothing about generalisation has been tested. Rejected
because the quantity it adds is the quantity that was never scarce.

**Hand-write more plants.** Honest, and it does produce structural variety, at a few hundred lines
of careful process engineering each. It does not scale, and more importantly a held-out
hand-written plant is one sample — a detector that fails on it has failed on *that* plant, and one
that passes has passed one. A family gives a held-out *draw*, which is a population. Not rejected
permanently: a new family is still hand-written, and this decision changes what hand-writing buys.

**Use a third-party process simulator.** Rejected on licence and on the hard rule against adding a
dataset or a dependency without a permissive licence, and on the deeper point that the true-state
record ADR 0015 depends on — truth recorded independently of the instruments from the first sample
— is a property of a simulator we wrote.

## Consequences

**More code, and a new class of bug.** A generator that draws a plant can draw a plant that is
subtly wrong in a way no test for a fixed plant would catch. `validity.py` is the answer and is also
the cost: it has to be at least as carefully reasoned as the physics, and a missing check is a
silent corruption of every corpus drawn after it.

**Determinism is harder to hold and more important.** A fixed plant consumes randomness at a
constant rate, which is what makes `tests/synth/test_plant.py` able to prove bit-identity rather
than observe it. A draw that branched on what it had already drawn could consume a different amount,
so the same discipline — spawned child streams by index, no global state, no wall clock, no
iteration over a set or an unsorted dict where a drawn value depends on the order — applies to
`randomise.py` from its first line, and its tests owe the same bit-identity assertion.

**The regeneration record grows.** `phos.synth.manifest` states how a corpus regenerates itself. A
generated plant's drawn parameter set belongs there beside the seed, so a reviewer can see what was
drawn without rerunning the draw.

**The standing caveat is unchanged, and volume does not soften it.** A family generates models of an
industrial process. Unlimited draws are unlimited models. `MODEL_NOT_REALITY_CAVEAT` is carried on
every dataset, manifest and topology this package writes and is carried on these too; good Atlas
results on generated plants mean Atlas handles our models of a plant, which is a step toward and not
evidence of handling a real one (ADR 0143). Nothing produced here may be described as real plant
data.

**Nothing is measured by this record.** S0 creates three modules holding a docstring each and an
empty `__all__`, plus a smoke test asserting exactly that. No physics, no draw, no corpus, no score.
The frozen numbers are untouched, v1 stays where the record left it, and P1 remains the blocked
human conversation.

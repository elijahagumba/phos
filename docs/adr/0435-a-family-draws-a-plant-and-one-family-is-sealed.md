# ADR 0435 — A family draws a plant, by name-addressed streams, and one family is sealed

- **Status:** Accepted
- **Date:** 2026-11-12
- **PART:** R2
- **Supersedes:** nothing
- **Depends on:** [0434](0434-a-plant-is-a-document-and-its-physics-is-a-named-template.md), [0433](0433-physics-constrained-plant-randomisation-for-training-data.md), [0010](0010-declared-topology-and-the-granularity-hai-supports.md), [0027](0027-unknown-master-writes-are-not-maintenance.md)

## Context

ADR 0433 named the gap: three hand-written plants, and a seed that varies their noise but never
the plant, so a model that scores well on them may have learned those three rather than how a
plant behaves. ADR 0434 made a plant into a document that can be drawn. This record is the
drawing.

## Decision 1 — A family is a process with its numbers left open, and its bounds are data

`phos.synth.families.PlantFamily` owes four things: what it is, which process template its plants
run on, what it varies and between what bounds, and how to turn a master seed into a `PlantSpec`.
Five open families are registered — `level_flow`, `thermal`, `power`, `batch_mix` and `hybrid` —
and each is a *process* rather than a plant: building one without a spec is refused rather than
defaulted, because a process has no canonical instance.

`ParameterBound` is a record, not prose: a range, a sampling scale, a unit, and a sentence a
process engineer could disagree with. That last field is what makes the bound reviewable rather
than merely declared, and it is why the table in `docs/sim/README.md` is *generated* from the
registry by `scripts/document_families.py` with a test that fails when the two disagree. A table
maintained by hand would be wrong within a month and nobody would know.

`bounded()` is the only way a family takes a number, and it refuses a parameter no bound declares.
So "every drawn parameter came through a declared bound" holds by construction and needs no test;
the test that exists checks the other direction, that no declared bound is dead.

`BoundScale` carries `LINEAR`, `LOG`, `INTEGER` and `CHOICE`. The log scale is load-bearing rather
than decorative: a time constant that may be thirty seconds or an hour, drawn evenly, puts nine
plants in ten at the slow end. `CHOICE` exists because an island runs at 50 Hz or at 60 Hz and 55
is not a cautious middle — it is a plant that does not exist.

## Decision 2 — Random streams are addressed by name, not by spawn index

`numpy.random.SeedSequence.spawn` is deterministic by child *index*. Used directly, adding a
stream for a new component shifts every stream after it, and every plant drawn before that day
silently becomes a different plant. For a generator whose whole claim is reproducibility that is
not a risk to manage, it is a defect to design out.

So a stream is derived from the master seed and a `blake2b` hash of its name:
`SeedSequence(entropy=master, spawn_key=(hash_of(name),))`. `blake2b` rather than Python's `hash`
because the interpreter salts string hashing per process, so a generator built on it would draw a
different plant every time it ran. `tests/synth/test_randomise.py` asserts that asking for five
new streams leaves an existing one bit-identical.

Every draw is recorded under the name it was asked for, and drawing one name twice is refused —
two values claiming one name in a manifest means the record says whichever came last.

## Decision 3 — Tag names are drawn, and the role map is the ground truth

A family draws its own naming convention per plant, so the same level transmitter is `LT_201.PV`
on one seed and `level-13-m` on the next. The purpose is not variety for its own sake: a detector
that learned anything from a tag *name* has learned the convention of the one site it was trained
on, which is the single thing guaranteed not to transfer.

What a tag means survives in `PlantSpec.roles` — `SignalRole`, carrying the role, the train and
the stage. A process template finds its instruments through `PlantSpec.tag(role, train, stage)`
and never sees a name. The role map travels with the plant as ground truth, so a reviewer can
always read the telemetry, and `PlantSpec` refuses two signals claiming one role position because
that would make the lookup arbitrary.

This is also why `ComponentKind` is a closed list and every component carries a plain-language
description: PART V4 draws a symbol per kind, and a free-text kind would be a symbol nobody drew.

## Decision 4 — Prime movers are sized for their duty, because drawing them directly did not work

This is the one decision here that came from a measurement rather than from a principle, and it is
recorded because the first version shipped in a commit and was wrong.

Drawing a pump's flow and a heater's rating independently of the demand they serve produced plants
that could not work: **7 of 40** `level_flow` draws had a pump that could not meet mean demand,
and **3 of 5** `thermal` draws ran with the heater pinned at full duty for the entire run. A
saturated actuator is a plant with no control behaviour left in it, which is the opposite of what
this programme generates data for.

The bound therefore moved onto the *ratio* — `pump_margin`, `heater_margin` — and the absolute
figure is derived from the duty at the design point. That is how a pump or a heater is actually
chosen: work out the duty, buy something with headroom over it. After the change, **0 of 20** and
**2 of 20**. The remaining two are a badly lagged vessel fighting a swinging ambient, which is a
real plant and exactly what PART R3's gate exists to refuse.

The same reasoning applies to several others and for the same reason — the absolute number means
nothing without the thing it serves: a feed rate from a charge *time*, an island's load as a
*fraction* of rated output, an Arrhenius prefactor from a *half-life* an operator would recognise.
A usable reaction rate needs a prefactor spanning many orders of magnitude, so drawn directly it
almost never lands in one.

Derived parameters appear in `PlantSpec.parameters`, which is what the physics reads, but their
bound is on the ratio. That is stated in each family's docstring and in the public document.

## Decision 5 — The electrical identity is solved exactly, not stepped around

Also recorded because the first version was wrong. In `power`, bus voltage depends on total
current and total current depends on bus voltage. Computing each feeder's current from the
previous sample's voltage — one sample of lag, which the module docstring claimed was "far below
the transmitters' own noise" — violated `P = sqrt(3)·V·I·pf` by up to **21%** on honest data,
because a machine whose excitation is moving quickly moves its voltage a long way in one sample.

An identity that holds to a fifth is not an identity, and the entire value of that process is that
a detector can trust it. No approximation was needed: `V = A - drop·I` and `I = K/V` combine into
a quadratic whose positive root is the answer. The lag now lives where the physics puts it, on the
field's response to excitation, and the load-dependent sag is algebraic. Worst relative error over
fifteen seeds, every feeder, every sample: **4.3e-16**.

Voltage collapse — a negative discriminant — returns the maximum-power-transfer voltage and
carries on, because a collapsing plant is one R3 should refuse on the evidence of a whole run
rather than one that should crash mid-sample.

## Decision 6 — Sealing is a loading switch, and nothing in the generator knows what it is for

One sealed family ships: `gas_pressure`, in `phos.synth.families_sealed`, which is imported only
when `PHOS_SYNTH_ALLOW_SEALED=1`. The seal holds three ways, and the third is the one that
matters: because the package is not imported, its *process template* is unregistered too, so a
spec naming a sealed process cannot be built at all. That survives a sealed spec leaking on to a
disk somebody else can read, which hiding it from a listing would not.

`get_family` reports it exactly as it reports a family that does not exist, and the message does
not hint otherwise. A refusal that said "there is one more, but you may not have it" would leak
the thing sealing is for.

Nothing in `families.py` or in the sealed package knows *why* a family is sealed. PART S6's
referee decides to examine a detector on an unseen process; a generator that knew which of its
plants were the exam could favour them — by widening a bound, by making one easier, or simply by a
developer reading the code and remembering. `tests/synth/test_sealed_families.py` enforces the
separation on what the code does rather than on what its prose says: the sealed modules may
explain why a held-back process is worth holding back, and that explanation mentions detectors;
what they may not do is import anything that measures one or define anything that scores.

The process type is deliberately unlike the five open ones. A sealed tank chain would test whether
a detector had memorised some parameters. A gas network tests whether it learned how a plant
behaves, because nothing open has compressible inventory, transport that is square-law in pressure
rather than linear in anything, or a controlled variable the compressor only reaches after the
whole line has repacked.

## Consequences

**What the five families buy.** Each carries a relationship a single-signal model cannot hold: an
integral of two flows (`level_flow`), three competing heat terms whose balance shifts with
throughput and weather (`thermal`), an arithmetic identity on every feeder (`power`), a *sequence*
in which the same reading is ordinary at one step and impossible at another (`batch_mix`), and —
only in the hybrid — a thermal mass that *is* a controlled level, so moving a level setpoint
changes how the temperature loop behaves. The hybrid earns its place on that coupling, which
neither parent can produce: in `level_flow` nothing is hot, and in `thermal` the holdup is a
constant.

**Every family declares a device that is granted nothing.** `spec_build.operator_authority` grants
the operator's HMI its setpoints and nobody else anything, and every drawn network carries an
engineering workstation that emits no baseline traffic. That is what makes the unknown-master
shape ADR 0027 measures available on a generated plant at all; a family that declared no such
device would make one of the two issuer kinds unmeasurable, and ADR 0034 requires them scored
apart.

**What is owed to R3, and is not a gap here.** `validity.py` is still empty: nothing checks whether
a drawn plant *could exist*. The bounds are chosen to make a bad draw uncommon rather than
impossible, and about one draw in ten still produces a plant at the edge of what it can do. The
gate that refuses those — with the broken relation named rather than a parameter quietly nudged
into range — is R3, as is the per-plant output on disk and the command line. A drawn plant today
exists only in memory.

Two parameters can still disagree with each other and nothing notices: the governor's declared
setpoint and `nominal_hz` both say what frequency an island runs at. ADR 0434 recorded that debt
and it is still open; `validity.py` is where it belongs.

**The caveat is unchanged and volume does not weaken it.** A family generates models of an
industrial process, not plants. Unlimited draws are unlimited models. Nothing here may be
described as real plant data, and no result measured on a generated plant may be quoted as a
result on a real one (ADR 0143).

**No measurement.** This record builds a generator and scores nothing. It opens no corpus, runs no
harness, writes no file to disk, moves no frozen number, and does not touch P1.

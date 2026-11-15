# ADR 0436 — A drawn plant is refused before it is written, and a template must state its own physics

- **Status:** Accepted
- **Date:** 2026-11-13
- **PART:** R3
- **Supersedes:** nothing
- **Depends on:** [0435](0435-a-family-draws-a-plant-and-one-family-is-sealed.md), [0434](0434-a-plant-is-a-document-and-its-physics-is-a-named-template.md), [0010](0010-declared-topology-and-the-granularity-hai-supports.md), [0082](0082-batch-distillation-label-classes-are-phases-and-only-the-anomalous-phase-is-scored.md)

## Context

PART R2 draws a plant from a family's declared bounds. Sampling inside a range still produces
combinations no engineer would build: a pump that cannot fill its tank against the outlet it is
paired with, a loop whose gain and the loop's time constant put it into sustained oscillation, a
vessel whose operating point sits outside its own instrument span, a signal that never moves.
ADR 0433 said so when it created the module and built nothing; this record is the gate, and the
outputs a plant that passes it writes.

## Decision 1 — A process that states no balance cannot be validated, and that is a failure

`phos.synth.validity.check` runs a candidate and judges six things: every value finite, every
declared balance closing, the process inside its instruments' spans, signals not constant,
modulating actuators not pinned, tracking loops reaching and holding their setpoints.

Conservation is the one it cannot write generically. A `Coupling` says a level depends on two
flows; it does not say which is an inflow. So a process template declares its own balances through
`SelfAuditing.conservation_residuals`, and **a template that declares none fails the gate**.

That is a strong rule and it is deliberate. The alternative — pass a plant whose physics nothing
checked — approves exactly the candidates most likely to be wrong, and does so silently. Making it
a failure means every template R4 and R5 add must state its balance too, which is the behaviour
worth locking in. All six existing templates now do: volume balances on the two tank chains, an
energy balance per vessel on `thermal`, mass per train on `batch_mix`, and on `power` both the
three-phase identity and the shaft.

The residuals are computed on the **true** state, not the reported readings. A balance is a
statement about the process; checking it against the instruments would check the sensor model,
which has its own noise and drift and would refuse an honest plant.

On `thermal` the balance is stated in its *physical* form rather than in the discretised form
`advance` implements. Checking the latter would close to the last bit by construction and verify
nothing. Stating it physically means the residual also carries the integration error — which is
the honest thing for it to carry, because a vessel whose residence time is short against the
sample interval really is modelled coarsely, and a reviewer should see that rather than be
reassured.

## Decision 2 — Reachability and holding are different failures, so they are different checks

PART R3 asks for "setpoints reachable, loops settle". One bar conflated them and refused both: a
loop that never once comes near its target and a loop that gets there and then rides a daily
demand swing a tenth of its span away failed the same way.

So reachability is tight — a loop must come within 8% of span at some point — and holding is
looser, at 20%, and judged at the 90th percentile of the offset rather than at the worst instant.
The percentile is not laxity: an operator moving a setpoint is a benign event every one of these
plants is built to contain, and for a minute afterwards the loop is legitimately a long way off.
Judging the maximum refused every plant whose setpoint happened to move late in the run, which is
a fact about the event schedule and not about the loop.

## Decision 3 — A candidate is judged at its own scan period

In this engine `RunSpec.sample_interval` is both the sampling rate and the interval the controllers
run at. The gate first used a fixed 30 seconds for every family, which asked whether a plant's
loops would be stable on somebody else's SCADA system — not a question about the plant. A candidate
is now judged at the scan period its own spec declares.

This is also why `power`'s scan period was narrowed to 1–10 s. An islanded machine's frequency is
an integral, so a governor updated every half minute cannot hold it; a real turbine governor is a
local controller running far faster than anything this engine represents, and the honest thing was
to say so in the bound's own words rather than let the family draw a plant that cannot work.

## Decision 4 — What the gate found, which is the whole reason for building it

Running the gate exposed five defects in PART R2's families and two in the gate itself. Every one
of the family defects is the same mistake, and it is the mistake ADR 0435 already recorded twice:
a number drawn independently of the thing it describes.

| What was drawn | Why it could not work | What it is now |
|---|---|---|
| `power`'s regulator gains, in %/Hz and %/kV | Frequency is an integral, so a gain suiting a 6 MW set makes a 170 MW one hunt — 25 of 30 refused | Governor sized from its droop and the largest step it must reject, floored at twice the fuel lag and twice the scan period |
| `power`'s bus impedance, in kV/A | A rounding error on a small machine at high voltage, a 26% collapse on a large one at low voltage | A per-unit sag, which is how reactance is actually quoted |
| `power`'s load step, as a fraction of rating | A quarter-rating step on a machine at 85% drove demand past what the set can make | A fraction of the headroom above mean load |
| `power`'s fuel lag, up to 40 s | No governor can hold frequency through a 40-second fuel system | 1–10 s, which is what a gas turbine's fuel system is |
| `thermal`'s throughput, in kg/h | Residence times from one minute to two days; a vessel turning over faster than the plant is sampled is unresolved, not hard | Derived from a drawn residence time |

And in the gate: the saturation check applied to every actuator, which refused every batch plant —
a feed valve open while the vessel charges and shut the rest of the time is not a loop with no
authority, it is not a loop at all, and `PlantSpec.controllers` already says so. It now applies
only to actuators a declared PI loop modulates. The range check read the *reported* value, which
`phos.synth.plant` clamps into the instrument's span, so it could never fail however wrong the
plant was; it now reads the true state, which is what "the process sits where its instruments can
see it" actually means.

**After all of it, 52 of 150 candidates are refused** across the five families — 35%, so 1.40 draws
per plant. `hybrid` is the worst at 50%, where the temperature loop's effective gain moves with the
level its other loop is controlling. That is left as a measured fact rather than tuned away, and
the count goes into every manifest: a rejection rate is a finding about a family's declared ranges,
and hiding it would make the family look better than it is.

## Decision 5 — A plant that passes is written as eight files, and two of them are Atlas's doors

One directory per plant: `telemetry.csv`, `labels.json`, `topology.toml`, `plant.json`,
`control.json`, `registers.json`, `capture.pcap`, `manifest.json`. Nothing is committed — a corpus
reproduced exactly from a family and a seed does not need storing — and `.gitignore` already covers
the directory.

Two of them are checked against Atlas's own public entry points, unchanged and read-only:

- the telemetry loads through `phos.eval.LabelledCsvAdapter`, the adapter a prepared HAI CSV goes
  through, with no special case for synthetic data;
- the capture parses through `phos.atlas.packet.dissect_capture` with the real Modbus dissector,
  without one malformed frame, and **every polled register carries the value the telemetry
  published for that signal** — 10,329 registers on a six-hour plant, zero outside the
  quantisation an industrial device imposes, and that count equals the number of observations
  Atlas ingested, so every reading is polled exactly once.

The second is the one that earns its place. Both outputs are projections of one simulated run; if
they disagreed about what the plant said, a detector watching the wire and the historian would be
right to distrust both, and nothing else in the suite would catch it. Writing the test also found
a trap worth recording: pairing a read response to its request by the MBAP transaction identifier
alone reported 945 mismatches out of 8344, because a capture with a PLC per train has several
conversations in flight and the identifier is unique only within one of them.

The register map is **per plant**, because R2 draws tag names and sensor layouts per seed and there
is no longer a fixed map to document once. It is rendered from the same `ControlNetwork` the
traffic writer builds its frames from, so the document and the wire cannot drift, and it carries
each signal's span because without it a reader of the capture cannot turn a count back into an
engineering value.

The control export is deliberately **not** a PLC program. These plants have no ladder logic and
inventing some would be fake realism. What they have is a set of declared loops with their
tunings, a set of actuators the recipe drives directly, and the role map saying what every
randomised tag name means — which is the content a reviewer needs to judge plausibility and the
content PART V4 renders as "the control logic in plain language".

`labels.json` carries an empty `attack_intervals` list and the benign events in full. The list is
present and empty for the reason the telemetry's label column is: a corpus that omitted its labels
would be indistinguishable from one whose labels were lost, and PART R4 writes into exactly this
shape. The benign events are ground truth in their own right — a detection landing on one landed
on a Tuesday morning, and the scorer can only know that because this file says so.

## Consequences

**What R4 inherits.** The event catalogue and the attack, fault and maintenance injection go into
`attack_intervals` and alongside the benign events, in a file shape that already exists. R4 does
not have to invent a label format, and the gate it must keep passing is already written.

**What is still owed.** Two parameters can disagree with each other and nothing notices: the
governor's declared setpoint and `nominal_hz` both say what frequency an island runs at. ADR 0434
recorded that debt, ADR 0435 left it open, and it is still open — the gate catches the
*consequence* (a governor holding to the wrong frequency would fail controllability) but not the
contradiction itself. A cross-parameter consistency check belongs in `validity.py` and is not
there.

`hybrid`'s 50% rejection rate is a known weakness of that family rather than of the gate, and
tuning its temperature loop against the thermal mass at its level setpoint is the obvious next
move. It is recorded rather than done.

**The caveat is unchanged.** A generated plant is a model of an industrial process, not a plant.
Every manifest carries `MODEL_NOT_REALITY_CAVEAT` and `SYNTHETIC_TOPOLOGY_CAVEAT`, and no result
measured on one may be quoted as a result on a real plant (ADR 0143).

**No measurement.** This record builds a gate and a writer and scores nothing. It opens no
committed corpus, runs no harness, moves no frozen number, and does not touch P1. Everything it
writes is to a git-ignored directory.

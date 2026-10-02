# ADR 0015 — Simulated plants, the injection hook, and the true-state record

- **Status:** Accepted
- **Date:** 2026-08-15
- **PART:** D1 — Synthetic industrial data engine: plants and normal operation
- **Supersedes / amends:** nothing. `phos.synth` is a new subpackage and no existing module was
  changed. Two files outside it were touched and both are configuration: `.gitignore` gained a rule
  for generated corpora, and `pyproject.toml`'s pytest `pythonpath` gained the repository root so
  that `scripts/` is importable and therefore testable (Decision 12).

## Context

Atlas's deepest constraint has never been modelling. It is that clean, richly labelled,
attack-dense industrial data barely exists in public. HAI and BATADAL between them offer two
testbeds and a handful of labelled windows; neither says *which explanation was true*, which is
precisely what a reasoning engine most needs to be measured against. PART P3 ended by stating the
consequence plainly: the claim that command visibility separates an operator from an attacker is
**unproven** and stays unproven until a labelled attack capture exists.

D1 is the first of three PARTs that answer that by building the environment ourselves. D1 builds
the plants and normal operation. D2 will build a graded attack library that injects labelled
attacks into them. D3 will run Atlas against the result and map where it goes blind.

The whole value of D1 is realism and honesty of construction. If the plants are too simple then
everything built on them proves nothing, because an attack that fools a toy world is not evidence.
So most of what follows is about what makes a simulated plant *hard* rather than about what makes
it convenient.

---

## Decision 1 — Three plants, chosen for rhythm rather than for count

**Decided:** three plants — `water-treatment`, `power-generation`, `batch-reactor` — and no more.

The PART asks for "a small number of genuinely different plant types … for behavioural variety
rather than a catalogue". The selection principle used was: **each plant must present a different
shape of "normal", not merely different column names.** Three continuous processes with different
units would have been three copies of one test.

| Plant | Rhythm | The coupling that makes it hard |
|---|---|---|
| Surface water treatment works | Continuous, paced by a city's diurnal demand; slow accumulating state (a filter fouling between backwashes) | Chlorine residual depends on dose, clearwell level **and** distribution flow together, through the contact time the last two imply. A long transport delay separates a cause from its effect. |
| Islanded gas turbine generating set | Continuous and an order of magnitude faster; a smooth daily curve **plus** a stepped three-shift industrial load | `P = sqrt(3).V.I.cos(phi)` holds exactly, every instant. Four signals, one equation. Shaft speed *is* frequency for a two-pole machine. |
| Jacketed batch reactor | Not continuous at all: idle → charge → heat → react → discharge, repeating | Normal is a *sequence*. The same reading is ordinary in one phase and impossible in another. Jacket utility flow is **non-monotone** in the valve that sets it (split range). |

The power plant's identity is the sharpest instrument in the set: an attacker who moves any one of
those four numbers without moving the others has broken arithmetic, not merely stepped outside a
band. Nothing in a water works is that tight, which is the point of having both.

**Coupling structure, stated as the PART requires** — each is declared as data on the plant
(`Coupling`), embedded in every manifest, and checked by tests:

- *Water:* level integrates (raw inflow − distribution flow); inflow follows √(pump speed);
  filtered turbidity lags a residual fraction of raw turbidity falling exponentially with coagulant
  dose per unit turbidity; headloss integrates inflow × turbidity since the last backwash; residual
  lags dose decayed over contact time (= clearwell volume ÷ demand); pressure lags a pump curve in
  booster speed² less friction in flow².
- *Power:* current is fixed by output, bus voltage and power factor through the three-phase
  identity; shaft speed integrates mechanical minus electrical power; frequency is speed ÷ 60;
  bus voltage follows excitation less an IR drop; feeder voltage is bus voltage through the tap
  ratio less a line drop; top-oil temperature lags ambient plus a rise in current², τ = 1 h.
- *Batch:* conversion integrates an Arrhenius rate in temperature against unconverted reagent;
  temperature integrates the exotherm plus wall transfer from the jacket over the charge's thermal
  mass; level integrates feed less discharge; pressure is exponential in temperature scaled by
  liquid depth; agitator power is cube-law in speed × viscosity(conversion) × depth.

---

## Decision 2 — Two injection points, and the contract that makes a manipulated run fight fair

**Decided:** `Injection` exposes exactly two methods — `actuator_overrides`, consulted *before* the
physics with what the controllers commanded, and `reading_overrides`, consulted *after* it with
what the instruments measured.

Two rather than one because they are the two things a real attacker does, and they have different
physical consequences: moving a final control element changes the plant; falsifying telemetry does
not, until somebody acts on it.

**The rules that keep the machinery invisible**, all three enforced by tests in
`tests/synth/test_plant.py`:

1. **An injection is consulted on every step, unconditionally.** `NoInjection` is a real object
   returning empty mappings, not a `None` that skips a branch. Applying an empty override mapping
   copies the same values through the same code, so it is a no-op *by construction* rather than by
   a conditional that could be got wrong.
2. **An injection never touches the plant's random stream.** It receives values and a clock and
   nothing else. The plant draws **one fixed-size block of normal deviates per step, before
   anything else in the step can happen**, so no path through the rest of the method can shift the
   stream by a single draw. The benign-event schedule is drawn once at construction, from a
   *separate* seed stream, for the same reason: sampling events per step would make the
   randomness rate depend on what happened.
3. **The plant refuses an override it does not recognise.** An unknown signal, or an actuator
   override naming something that is not a declared actuator, raises. A manipulation that silently
   did nothing would be labelled by D2 as an attack that silently did nothing — the worst possible
   ground truth.

**The property that follows, and is tested:** a run through an injection whose window has not
opened yet is **bit-identical** to a run with no injection at all. After the window opens the runs
diverge, and they diverge because the plant genuinely moved.

**Consequence for the command capture:** frame *count and structure* cannot change with an
injection (polls come from the sample index and the declared register map), but frame *contents*
can, because a falsified reading is what the PLC answers with. That is the manipulation reaching
the capture, not a tell.

---

## Decision 3 — Controllers act on reported readings, never on the true state

**Decided:** every control loop is handed the **previous sample's reported readings**.

This is how a real loop works — a controller has no oracle — and it is load-bearing for D2. It is
the reason a fabricated reading has physical consequences rather than being a cosmetic edit to a
column of numbers: told the clearwell is nearly empty, the level loop opens the intake and the real
level climbs. `test_a_falsified_reading_reaches_the_plant_because_the_loop_believes_it` is that
sentence as an assertion.

The cost is a one-sample control delay everywhere. That is realistic (a scan-based controller acts
on the last scan) and was accepted without qualification.

---

## Decision 4 — The true-state record is separate from the first sample, not retrofitted

**Decided:** every step records `TrueState` (what the plant is actually doing, plus internal state
no instrument is on) and `SensorReport` (what the instruments say) as two objects, from sample
zero, even though in D1 they only ever differ by the declared error model.

Retrofitting this later would have meant reconstructing truth from the reports it is supposed to be
independent of, which is not a reconstruction — it is an assumption. `TrueState.internal` carries
quantities no instrument reads (filter solids load, chlorine contact time, reagent and converted
mass, phase timers) because D2 may need to say a manipulation drove an *unmeasured* quantity
somewhere dangerous, which is the case telemetry alone can never establish.

**"They agree in normal operation" is a bounded claim, not an identity.** Report = truth + gaussian
measurement noise + a bounded calibration drift, then clamped to the instrument's span. Both terms
are declared per signal, so the agreement bound is provable and is asserted for every signal at
every sample: `|report − truth| ≤ drift_amplitude + 6σ`.

---

## Decision 5 — Sensor drift and process drift are different things and live in different places

**Decided:** *calibration* drift belongs to the instrument and moves the report only; *process*
drift belongs to the plant and moves the true state.

So a transmitter's slow wander (a sinusoid whose period — 2 to 5 days — and phase are drawn once
per run, bounded by a declared amplitude) never touches the process, while river water quality
wandering over three days, a filter fouling, and a transformer's thermal memory are all in the true
state where they physically are. Merging the two would have made the truth/report agreement bound
above unprovable, and would have made a fouling filter indistinguishable from a drifting sensor —
which is a real diagnostic question and should stay one.

---

## Decision 6 — Physics integrates at the sample interval

**Decided:** one integration step per sample. No sub-stepping.

**Limit accepted and stated:** dynamics faster than one sample are not represented, and final
control elements are modelled as reaching their commanded position within one sample. At the
sampling rates the standard datasets use (10 s for the machine, 30 s for the works, 60 s for the
reactor) this is defensible for the processes modelled; it would not be for, say, a protection
relay or a compressor surge.

**Numerical consequence that had to be handled rather than accepted.** An explicit Euler step for
the reactor's wall heat transfer has gain `UA·dt/(m·cp)`, which exceeds 2 — and therefore
diverges — whenever the vessel is nearly empty. The first version of the reactor ran to 200 °C and
0 °C against its instrument stops for exactly this reason. The wall term is now an exact
exponential approach (`process.first_order`), unconditionally stable at any step size, with the
exotherm and agitator work added as increments. This is a modelling correctness issue, not a
tuning one: a plant that diverges numerically is not a plant.

---

## Decision 7 — The batch reactor emits no Modbus, and that is an answer

**Decided:** water treatment and power generation declare a `ControlNetwork` and produce a capture.
The batch reactor declares `control_network = None` and produces telemetry only.

A jacketed reactor of this kind is normally run from a DCS over a fieldbus Atlas cannot dissect.
Emitting Modbus for it would be fake realism — inventing the one thing that would make Atlas look
better. The asymmetry is also useful: it gives D3 a plant where Atlas is **deaf to commands by
construction**, so "no capture exists for this process" is one of the honest answers D3 can find
when mapping where Atlas goes blind.

The generator says so out loud (`"no control network, so no capture"`) rather than writing a
zero-frame file, and the manifest simply does not list a capture.

---

## Decision 8 — The capture is real bytes, read back by the real dissector

**Decided:** `phos.synth.traffic` assembles Modbus/TCP ADUs inside TCP inside IPv4 inside Ethernet
inside a libpcap file with `struct`, importing nothing from `phos.atlas.packet`. The test then runs
the file through `dissect_capture` and asserts every payload-carrying frame comes back a decoded
`ModbusMessage` and not one `MalformedFrame`.

A generator that used the parser's own types would be testing the parser against itself and would
prove nothing about whether the bytes are right. This is the same argument
`tests/atlas/packet/conftest.py` makes for hand-built fixtures, applied in the other direction.

**What makes it a capture rather than a stream of ADUs**, each of which is a way a synthetic file
announces itself if omitted:

- a real three-way handshake opens each conversation (counted by `CaptureStats` as
  `frames_without_payload`, which is exactly the bucket that field documents);
- sequence numbers advance by the bytes actually sent;
- **IP and TCP checksums are computed**, and the tests verify them the way a receiver does — a
  correct header sums to zero over its own checksum field;
- **polls carry timing jitter**, because a scan landing on the same millisecond forever would give
  `COMMAND_INTERVAL_CV` a coefficient of variation of exactly zero, which no real SCADA produces;
- **requests are serialised per connection** — the next request waits for the previous answer.
  Without that, two block reads scheduled at one instant could overtake each other under
  independent jitter and the sequence numbers on one connection would go backwards, which no TCP
  endpoint does and any analyst would notice.

**The jitter has its own seed**, drawn from a generator seeded by `TrafficPolicy`, never from the
plant's. Regenerating a capture with different jitter therefore cannot move a single telemetry
reading; the two outputs of one run are independently reproducible. `traffic_seed` is a separate
field in every dataset config for the same reason.

**Register values are raw 16-bit counts** scaled across each instrument's calibrated span — the
digital form of the 4–20 mA loop — not engineering floats, because that is what a real device puts
on the wire and it handles negative engineering values without a sign convention.

**Scope limit:** the encoder writes function 3 (read holding registers) and function 6 (write
single register), and **refuses** anything else with a named error rather than emitting an
approximation. A multi-register write, or a read of an address no declared block starts at, raises.

---

## Decision 9 — Telemetry is written at five decimal places

**Decided:** `write_csv` formats every value as `{:.5f}`.

Two reasons, and the second is the one that forced it. A seventeen-digit `repr` is long enough that
pandas' fast float parser can land one unit in the last place away from the value written — so
writing more digits buys a precision the round trip does not preserve, and the test asserting an
exact round trip fails. Five decimals is also what HAI's own prepared CSV carries and roughly what
a historian storing single-precision floats can hold.

The run itself remains exactly regenerable, from the seed. Precision on disk and reproducibility of
the corpus are separate properties, and only the second one is a claim D1 makes.

---

## Decision 10 — The synthetic topology is exact, and saying so is the point

**Decided:** the topology file is rendered from `SignalSpec.physical_unit` — the same declaration
the physics reads — and every subsystem's `source` carries `SYNTHETIC_TOPOLOGY_CAVEAT`.

`phos.atlas.topology` (ADR 0010) refuses to infer membership from co-movement because grouping
would then be computed from the statistics that raised the deviations. That argument holds here.
What is different is the *quality* of the source: a real corpus's topology is a **reading** of a
P&ID and can be wrong; this one is exact by construction.

That makes it better ground truth than any real corpus offers, and therefore a trap. **A grouping
reduction measured against this map is an upper bound on what the same grouping would achieve on a
real plant**, and the caveat travels in the file itself so a reviewer sees it without reading this
document.

---

## Decision 11 — Nothing generated is committed, manifest included

**Decided:** `.gitignore` excludes `data/synth/` entirely.

This differs deliberately from the rule for downloaded corpora, where `manifest.json` and
`topology.toml` *are* committed. There, the manifest is the only account of where the bytes came
from and the topology is hand-authored from documentation — neither can be regenerated. Here both
are generated artefacts, and the committed authority is the config plus the generator.

What the manifest carries is set by what someone holding only it would need: the regeneration
recipe (plant, seed, start, duration, interval), the plant's whole declaration **including its
couplings** so a reviewer can check the plant's claim about itself without reading the physics, the
benign events that occurred, a SHA-256 digest and size for every file written, and both standing
caveats.

**Generated corpora live at `data/synth/<name>/`, one level deeper than downloaded ones.** This is
not tidiness: `tests/eval/test_real_dataset.py` discovers real corpora by globbing
`data/*/manifest.json` and reading every hit as a `LabelledCsvAdapter` config. Writing a synthetic
manifest at `data/<name>/manifest.json` crashed that test's collection with a `KeyError` on the
missing `path` field. Moving one level down removes the collision without touching a test that
belongs to another PART.

---

## Decision 12 — Generation logic lives in the package; the script is a command line

**Decided:** `phos.synth.generate.generate_dataset` decides what a corpus is;
`scripts/generate_synth.py` parses arguments and knows where the repository keeps its configs.

The PART requires full line and branch coverage on the new subpackage, and coverage is measured
over `src/phos/`. Logic in a script would have been logic outside that measurement — and, as the
repository stood, logic no test could even import. `pyproject.toml`'s pytest `pythonpath` gained
`"."` so `scripts/` is importable, which is how the command line itself is now tested. Scripts were
previously the one part of PHOS pytest could not reach.

---

## Decision 13 — Benign events are scheduled, parameterised and labelled

**Decided:** each plant declares `EventPlan`s; one shared `lay_out_events` places them round-robin
through the run with random gaps, drawing each occurrence's parameters from declared ranges.

Benign events are what make the data honestly difficult. A plant whose only sharp change is an
attack is a plant detection is trivial in, and which does not exist. Water has seven placements
across five kinds (setpoint moves on three loops, filter backwash — twice per cycle, because
filters are washed more often than setpoints are moved — a maintenance stop and a rainfall
turbidity excursion); power has four (dispatch change, customer load step, feeder switching,
voltage setpoint change); the reactor has four (recipe change, charge size, extended hold, agitator
speed).

Parameters are **drawn per occurrence** rather than fixed, so two occurrences of one kind are not
identical — otherwise a mimic attack would only have to match one exemplar. The events are recorded
on the run and in the manifest as ground truth in their own right: D3 needs to know whether a
detection landed on an attack or on a Tuesday morning backwash.

Where a plant has a control network, an event's `writes` become **real writes on the wire**, which
is what ties the benign event in the telemetry to the benign event in the capture — the thing D2's
mimic attack must imitate in both places at once.

---

## Ambiguities in the PART, and how they were resolved

1. **"Several concrete plant models"** — resolved as three, one per named profile (water, power,
   chemical/batch), on the reasoning in Decision 1.
2. **"Command traffic in the packet adapter's message shape"** — resolved as *a real pcap of real
   bytes*, not hand-constructed `ModbusMessage` objects. The acceptance criterion says the packet
   adapter must *parse* it without malformed frames, and only bytes can be parsed (Decision 8).
3. **"Every data point labelled normal"** — resolved as both a label column of zeros in the CSV
   (which `phos.eval.default_attack_when` reads as normal) and an empty `attack_intervals` on the
   `Dataset`. The column exists even though it is constant, because it is the column D2 writes into
   and a corpus without it would be indistinguishable from one whose labels were lost.
4. **"Do not aim at a data-size target"** — the standard set is sized by *process* time: enough
   backwash cycles, enough daily cycles, enough batches for the sequence to be learnable. Six
   datasets, a fitting corpus and a held-out one per plant, because every measurement elsewhere in
   PHOS requires that separation and inventing it later would be worse.
5. **Where actuator dynamics belong** — resolved as "within one sample" (Decision 6), stated as a
   limit rather than modelled.

---

## Consequences

**What is now possible.** D2 has a door to come through that leaves no marks, ground truth that
records what the plant was really doing while its instruments were lying, benign events to hide
among, and three plants whose couplings are declared explicitly enough to be attacked
deliberately. D3 has corpora that load through every Atlas path unmodified, an exact topology, and
one plant where Atlas is deaf by construction.

**What has NOT been established, and must not be claimed.**

- **A plant here is a model, not a plant.** `MODEL_NOT_REALITY_CAVEAT` is carried in every dataset's
  `source_note`, every manifest and this ADR. A detection result measured on this data says Atlas
  handles *our model of a plant*. That is a necessary step toward handling a real one and is not
  evidence of it.
- **No detection result of any kind exists here.** D1 runs no model, scores nothing and touches no
  engine. The claim P3 left open — that command visibility separates an operator from an attacker —
  is still unproven, and stays unproven until D2 produces labelled attacks and D3 measures them.
- **Realism is a claim, defended per plant in `PlantDescription.model_source`, not a property that
  has been validated.** No plant here has been compared against telemetry from a real works,
  machine or reactor. The couplings are textbook relations and public process descriptions applied
  honestly; that is the standard of evidence, and it is lower than measurement.
- **The plants are small.** Fifteen, sixteen and thirteen signals against HAI's seventy-nine. The
  interactions a hundred-signal plant has, and the correlations a large joint model must sort out,
  are not represented.
- **One process each.** No plant models redundant trains, standby equipment swapping in, or a unit
  being taken off line for days — all ordinary industrial behaviour that a detector meets in the
  field.

# Generated plants, in plain English

## The problem

PHOS has a simulator already. `src/phos/synth/` builds three industrial plants — a water treatment
works, a power generator, a batch chemistry reactor — and runs them properly: tanks that fill
because something flowed into them, temperatures that lag behind the heat applied to them,
controllers that act on what the instruments report rather than on what is actually happening, and
a record of what the plant was really doing kept separately from what it said it was doing. It
writes the telemetry as a CSV, the plumbing as a topology file, and the control traffic as a real
Modbus capture, all in the shapes Atlas already reads.

Three plants is the problem. You can run them a million times with a million different seeds, and
each run gives you different noise, a different pattern of drift on the instruments, a different
schedule of ordinary events like backwashes and setpoint changes. What you never get is a different
plant. Six tanks are six tanks every time. The controller's gain is the number a person typed when
the file was written. The list of signals is the same list.

That matters because of what a detector can do with it. If every corpus Atlas is measured on comes
from the same three structures, a detector can score beautifully by memorising those three — the
particular size of that tank, the particular shape that level trace makes — rather than by learning
anything about how a plant behaves. Nothing in the evaluation can tell the difference, because
there is nothing else to score it on. And a detector that memorised a plant has nothing to say
about a plant it has never met, which is every real plant.

## What this work adds

A **family**: a kind of plant, with its shape fixed and its numbers left free.

The shape is what is connected to what — this tank feeds that pump, this instrument measures that
temperature. The numbers are everything a real engineer would have chosen differently on a
different site: how big the tank is, how fast the pump moves, how the controller is tuned, where the
setpoints sit, how good the instruments are.

Give the family a seed and it draws one plant. Give it a different seed and you get a different
plant of the same kind — the same process at a different size and a different tuning, which is
exactly what two real plants of the same kind are. The drawing happens to the plant's *description*,
before anything is simulated, so from that point on it is just a plant: the same physics engine, the
same controllers, the same instruments, the same attack hooks, the same files out.

## The part that is easy to get wrong

If you draw each number independently you will draw plants that could not exist. A pump too weak to
fill the tank it is plumbed to. A controller tuned so aggressively that the loop never settles. A
normal operating level that sits outside the plant's own alarm limits. A pressure gauge whose range
does not include the pressure the process runs at.

Data from a plant like that is not difficult training data. It is wrong, and anything learned from
it is a false belief about industry.

So every draw is checked before it is used, and the checks are about *relationships* rather than
individual numbers — can this pump actually fill this tank against this outlet, does this gain and
this time constant leave a loop that settles, do the setpoint and the alarm limits and the
instrument range nest in the order their names imply. Some of those can only be answered by running
the plant for a while and watching, so the check is allowed to do that.

**A draw that fails is thrown away, with the rule it broke written down. It is never quietly
adjusted to fit.** A number nudged into range is a plant the family said was impossible and the
generator built anyway, and it would arrive in a corpus carrying the family's word that it was
fine. If a family keeps producing draws that fail, that is worth knowing: it means the ranges it
declares are wider than its own physics.

## What this is not

**It is not real plant data, and more of it does not make it closer to real.** Everything here is a
model of an industrial process, written from public descriptions of how such processes behave. A
million generated plants are a million models. If Atlas does well on them, what has been shown is
that Atlas handles our models of a plant — a necessary step toward handling a real one, and not
evidence of handling one. Every file this package writes carries that caveat, and these will too.

**The physics is deliberately modest.** A tank is a volume with flows in and out. A temperature is a
first-order lag. A valve is a flow coefficient and a square-law relation. There is no computational
fluid dynamics, no detailed chemistry, no mechanical wear model, no electrical transient below the
sampling interval, no multi-phase flow. What is modelled is modelled because a detector has to see
it; what is not modelled is left out honestly rather than faked.

**It does not touch anything real.** Nothing here opens a socket, reaches a network, or knows that
devices exist outside this computer. The attack code moves numbers around inside a simulation and
writes files. That is the whole of its reach, by construction.

## Where things are

| | |
|---|---|
| The simulator | `src/phos/synth/` |
| The three hand-written plants | `src/phos/synth/plants/` |
| Physics primitives | `src/phos/synth/process.py` |
| A plant written down (new in R1) | `src/phos/synth/plant_spec.py` |
| Plant families (still empty) | `src/phos/synth/families.py` |
| Drawing a plant from a seed (still empty) | `src/phos/synth/randomise.py` |
| Checking a drawn plant could exist (still empty) | `src/phos/synth/validity.py` |
| Tests | `tests/synth/` |
| Command line | `scripts/generate_synth.py` |
| What the existing corpora hash to | `scripts/synth_golden.py`, `tests/synth/golden/` |
| The survey this plan was built on | `recon.md` (lab record, not published) |
| The decision records | [`ADR 0433`](../adr/0433-physics-constrained-plant-randomisation-for-training-data.md), [`ADR 0434`](../adr/0434-a-plant-is-a-document-and-its-physics-is-a-named-template.md) |

## What R1 added: a plant you can read

Until now a plant was a *class*. The water works was six hundred lines of Python, and the fact that
its clearwell has a plan area of 250 square metres was a line of code in the middle of it. You
could run that plant, but you could not hand it to anything — you could not draw a different one,
you could not write one down, and you could not ask it what it was made of without reading the
physics.

After R1 a plant is a **document**. `PlantSpec` says, in a form that saves to a JSON file and loads
back again:

- **what the plant is made of** — thirteen components for the water works: a river, an intake pump,
  a rising main, two dosing skids, a filter, a clearwell, a booster set, a distribution main, the
  city drinking at the end of it, and the three control loops;
- **what is connected to what**, and which way the water goes;
- **the loops and how they are tuned** — which reading each one watches, which valve or pump it
  moves, how hard and how fast it pushes;
- **the instruments** — their tag names, their units, their calibrated range, how noisy they are
  and how much they drift;
- **how often the control network is read**;
- **what normally happens** — the backwashes, the setpoint changes, the rainfall that muddies the
  river, and how far apart they fall;
- **every free number the physics reads** — about sixty of them across the three plants, each one
  named, so a generator can later pick a different value for it.

### The physics itself is not in the document

One thing is deliberately left out, and it is the thing most likely to be misread, so it is worth
being plain. The spec does not contain the *equations*. Those stay in a named recipe — a "process
template" — and the spec supplies the numbers that recipe reads.

Why: these three plants do not share a physics. The reactor has reaction kinetics and a batch
sequence it steps through; the generating set has an electrical solution and a tap changer that
jumps a whole step at a time; the water works has chlorine dying away in a tank at a rate that
depends on how long the water sits there. Writing all of that as a generic diagram of boxes and
arrows would have needed a special box for each one — which is the same code in a different shape —
and would have risked changing the answers in the last decimal place, because a computer adding
three numbers in a different order does not get quite the same result.

So the drawing in the document is a **statement about the plant that the recipe has to honour**,
not the thing that does the work. The repository already treats its subsystem map this way, for the
same reason (ADR 0010). What the spec *does* enforce is that the drawing agrees with the
instruments: every reading belongs to exactly one piece of plant, and a reading cannot be claimed
by a pump if it is declared on a tank.

### How we know the refactor changed nothing

The whole value of this step rests on one claim: that it changed how a plant is *described* and not
one number any plant *produces*. So before anything was touched, every standard corpus was
generated and its files were fingerprinted — the telemetry, the subsystem map, the packet capture,
and the manifest, which carries the plant's full declaration. Those fingerprints were committed.

After the refactor, all six corpora still fingerprint to exactly the same values, down to the byte.
`tests/synth/test_golden_corpora.py` checks it on every test run, and takes seven seconds to do it.

If one of those fingerprints ever moves, that is a finding to explain, not a file to overwrite.

## What R2 added: a seed draws a plant

R1 made a plant into a document. R2 is what *writes* one.

A **family** is a kind of process with its numbers left open — what is connected to what is fixed,
and the sizes, the tunings, the instruments, the tag names and the normal disturbances are drawn
from a seed. Two plants from one family are the same process at different scales, which is what
two real plants of the same kind are. There are five:

| Family | What it is | Why it is worth generating |
|---|---|---|
| `level_flow` | Liquid pumped through a chain of tanks to a demand nobody controls | A level is the running total of two flows, so a reading that disagrees with the flows around it is not unusual — it is impossible |
| `thermal` | Fluid through a chain of heated vessels | A temperature is three competing terms, so what is plausible on a cold morning at low throughput is impossible on a warm afternoon at high throughput |
| `power` | A generating set supplying an island with no grid behind it | Power, voltage and current have to multiply out on every feeder. That is arithmetic, not a trend |
| `batch_mix` | Reactor trains stepping through a recipe | Normal is a *sequence*. The same temperature is ordinary at one step and impossible at another |
| `hybrid` | A tank chain that is also heated | A tank's thermal mass **is** its level, so the two loops are not independent |

### Why the tag names are scrambled

Every plant draws its own naming convention. The same level transmitter is `LT_201.PV` on one
seed, `level-13-m` on the next and `WTW.LEVEL.01.M` on a third, because real sites do not agree
and a detector that learned anything from a tag *name* has learned the convention of the one site
it was trained on — the one thing guaranteed not to transfer.

What a tag means is not lost. Every drawn plant carries a **role map**: this column is the level of
the second tank in the first train, that one is its pump's speed. The physics finds its own
instruments by role and never sees a name, and the role map travels with the output as ground
truth, so a reviewer can always read the telemetry.

### Sizes are drawn as ratios, not as numbers

The first version of this drew a pump size and a heater rating directly, and produced plants that
could not work: seven draws in forty had a pump that could not meet mean demand, and three in five
had a heater pinned at full duty for the whole run. A saturated actuator is a plant with no control
behaviour left to learn.

So the drawn quantity is the **margin** — how much more a pump can deliver than the duty it has to
do — and the absolute figure is worked out from the duty, which is how a pump or a heater is
actually chosen. The same trick fixes several others: a feed rate comes from a charge *time*, an
island's load from a *fraction* of rated output, a reaction's prefactor from a *half-life* an
operator would recognise.

### One family is held back

A sixth family, a gas pressure network, is **sealed**: it is absent from every listing and from the
builder, and loads only when `PHOS_SYNTH_ALLOW_SEALED=1` is set. That is all the seal is — a
loading switch. Nothing in the generator knows what a sealed family is *for*; the referee decides
that later, and a generator that knew which of its plants were the exam could favour them.

Its process type is deliberately unlike the five above. A sealed tank chain would test whether a
detector had memorised some parameters. A gas network tests whether it learned how a plant behaves,
because nothing in the open set has compressible inventory or transport that is square-law in
pressure.

### Every randomised parameter, and its range

Generated from the code by `scripts/document_families.py`, and
`tests/synth/test_family_docs.py` fails if the two disagree — so a bound that changes here has
changed in the plant. The sealed family's bounds are not published: this table is read by whoever
is being examined on it.

<!-- BEGIN GENERATED: family bounds -->

#### `batch_mix` — Parallel batch reactor trains

One or more reactor trains, each stepping through the same recipe: fill, heat, react, empty, wait, and start again. Nothing here holds an operating point, so the same temperature is ordinary at one step and impossible at another, and the trains are deliberately not in step with one another.

| Parameter | Range | Unit | What it is |
|---|---|---|---|
| `trains` | 1 to 3 | — | How many reactor trains run side by side. Each runs the recipe independently and they are started staggered, so the site is never in one state. |
| `full_charge_kg` | 400 to 12000 (log) | kg | Mass in a vessel at a full charge. |
| `charge_minutes` | 6 to 45 | min | How long a vessel takes to fill. The feed rate is derived from this and the charge, because a recipe specifies a time and an operator would never quote a kg/h. |
| `discharge_minutes` | 4 to 30 | min | How long a vessel takes to empty. The discharge rate is derived from it. |
| `heat_capacity_kj_per_kg_k` | 1.6 to 4.2 | kJ/kg/K | Specific heat of the batch. |
| `vessel_thermal_fraction` | 0.02 to 0.2 | — | Thermal mass of the steel itself, as a fraction of a full charge. Why an empty vessel does not change temperature instantly. |
| `wall_ua_kw_per_k` | 2 to 60 (log) | kW/K | How fast heat crosses from the jacket into the batch. With the charge this sets how long the heat step takes. |
| `reaction_enthalpy_kj_per_kg` | 40 to 400 (log) | kJ/kg | Heat released per kilogram converted. The reaction warms itself, which is why the loop has to back the jacket off once it starts. |
| `arrhenius_temperature_k` | 5000 to 10000 | K | Activation temperature of the reaction. With the prefactor this is why a batch held ten degrees cooler takes markedly longer, so a temperature attack shows up in the timing of everything downstream. |
| `reaction_half_life_minutes` | 4 to 40 (log) | min | How long the reaction takes to convert half of what is left, at the reaction temperature. The Arrhenius prefactor is derived from this and the activation temperature, because a prefactor drawn directly produces batches that finish during heating or never finish at all. |
| `jacket_tau_s` | 30 to 400 (log) | s | How long the jacket's own temperature takes to follow its valve. |
| `jacket_cold_c` | 5 to 40 | degC | Jacket temperature with the service valve shut — the cold utility. |
| `jacket_approach_c` | 15 to 60 | degC | How much hotter than the reaction temperature the hot utility is. The jacket has to be above the batch for heat to flow into it, and this is the margin a designer picks. |
| `feed_temp_c` | 4 to 30 | degC | Temperature the reagent arrives at. Cold feed cools the batch when it charges. |
| `reaction_temp_c` | 55 to 140 | degC | Temperature the recipe calls for while the batch reacts. |
| `temperature_headroom` | 1.3 to 2 | — | How far above the reaction temperature the transmitters are calibrated, as a multiple. |
| `idle_minutes` | 3 to 40 | min | How long a vessel waits empty between batches — turnaround, cleaning, waiting for a tanker. |
| `hold_minutes` | 20 to 180 | min | How long the react step holds if conversion has not reached its target first. |
| `conversion_target_pct` | 88 to 98 | % | Conversion the recipe calls for before the batch may be discharged. |
| `arrival_margin_c` | 0.5 to 4 | degC | How close to setpoint counts as up to temperature, so the hold may start. |
| `agitator_rated_kw` | 2 to 60 (log) | kW | Agitator power at rated speed in a full vessel. |
| `agitator_base_fraction` | 0.01 to 0.1 | — | Power the drive takes with the vessel empty, as a fraction of its rating — its own losses. |
| `agitator_rated_rpm` | 40 to 220 | rpm | Speed the agitator's rating is quoted at, and what it runs at while heating and reacting. |
| `agitator_idle_fraction` | 0 to 0.35 | — | Speed the agitator turns at outside the heat and react steps, as a fraction of rated. Some sites keep it ticking over and some stop it. |
| `viscosity_per_conversion` | 0.4 to 3 | — | How much harder the agitator works at full conversion than at none. This is what makes the drive's power a second witness to conversion. |
| `stagger_fraction` | 0 to 1 | — | How far apart the trains start their recipes, as a fraction of the idle time. At zero they run in lockstep, which is the case a detector could learn once and know all of. |
| `temperature_noise_c` | 0.02 to 0.8 (log) | degC | Measurement noise on the batch and jacket temperature transmitters. |
| `temperature_drift_c` | 0.005 to 0.4 (log) | degC | Bound on each temperature transmitter's slow calibration drift. |
| `level_noise_pct` | 0.02 to 0.9 (log) | % | Measurement noise on the vessel's level. |
| `power_noise_fraction` | 0.002 to 0.04 (log) | — | Measurement noise on the agitator's power meter, as a fraction of its rating. |
| `conversion_noise_pct` | 0.05 to 1.5 (log) | % | Measurement noise on the conversion analyser. Analysers are noisier than thermocouples, which is part of why the agitator's power is worth having. |
| `temperature_gain` | 0.5 to 6 (log) | K/K | Proportional gain of the outer temperature loop, which asks the jacket for degrees rather than percent. |
| `temperature_integral_s` | 300 to 2400 (log) | s | Integral time of the outer loop. Long, because a vessel full of liquid is slow. |
| `jacket_gain` | 1 to 12 (log) | %/K | Proportional gain of the inner jacket loop. |
| `jacket_integral_s` | 30 to 400 (log) | s | Integral time of the inner loop. Much shorter than the outer one, which is what makes the cascade stable rather than two loops fighting. |
| `jacket_bias_pct` | 20 to 70 | % | Service valve position the inner loop starts from before its own terms. |
| `scan_period_s` | 5 to 60 | s | How often the SCADA system polls every register block. |
| `event_gap_low_steps` | 40 to 400 | samples | Shortest quiet stretch between two benign events. |
| `event_gap_span_steps` | 200 to 2000 | samples | How much longer the longest quiet stretch may be than the shortest. |
| `hold_extension` | 0.1 to 0.8 | — | How much longer an extended hold runs than the recipe's default. |

#### `hybrid` — Heated tank chain

A chain of tanks that are pumped full and heated at the same time, each with a level loop and a temperature loop. The two halves are not independent: how full a tank is decides how fast it warms, so moving a level setpoint changes how the temperature loop behaves.

| Parameter | Range | Unit | What it is |
|---|---|---|---|
| `trains` | 1 to 2 | — | How many heated chains run in parallel. |
| `stages` | 2 to 3 | — | How many heated tanks each chain is made of. Smaller than the unheated family's range because every stage here carries two loops and two transmitters. |
| `tank_area_m2` | 10 to 150 (log) | m2 | Plan area of every tank. With the level it is the volume, and with the density and the specific heat it is the thermal mass — which is why this one parameter sets both how fast the level moves and how fast the temperature does. |
| `level_span_m` | 2 to 7 | m | Height of every tank, and the calibrated span of its level transmitter. |
| `level_setpoint_fraction` | 0.35 to 0.7 | — | Where in the tank the level loops hold, as a fraction of its height. It also decides the holdup the heaters are sized against. |
| `pump_margin` | 1.3 to 3 | — | How much more flow each pump can deliver than its train's share of mean demand. |
| `flow_tau_s` | 10 to 180 (log) | s | How long a pump takes to reach a new flow after its speed changes. |
| `demand_base_m3ph` | 10 to 150 (log) | m3/h | Mean draw at the end of the chain. |
| `demand_daily_m3ph` | 2 to 40 (log) | m3/h | Amplitude of the once-a-day swing in that draw. |
| `demand_floor_fraction` | 0.1 to 0.5 | — | Fraction of mean draw the demand never falls below. |
| `density_kg_per_m3` | 700 to 1050 | kg/m3 | Density of the liquid. Neither parent family needs it — one works in volume and the other in mass — and a plant that is both has to convert between them. |
| `heat_capacity_kj_per_kg_k` | 1.8 to 4.2 | kJ/kg/K | Specific heat of the liquid. |
| `heater_margin` | 1.3 to 2.8 | — | How much more heat each heater can put in than the duty its tank needs at the level setpoint. Sized at the setpoint rather than at a fixed holdup, because the holdup is something the other loop is moving. |
| `ua_ambient_kw_per_k` | 0.02 to 1.5 (log) | kW/K | How fast each tank loses heat to the room, per degree above it. |
| `feed_temp_c` | 4 to 30 | degC | Temperature of what arrives at the front of the chain. |
| `ambient_base_c` | 2 to 28 | degC | Mean temperature of the room or yard the tanks stand in. |
| `ambient_daily_c` | 1 to 12 | degC | How far the room's temperature swings over a day. |
| `temperature_setpoint_c` | 35 to 95 | degC | Temperature every tank in the chain is held at. |
| `temperature_headroom` | 1.3 to 2 | — | How far above the setpoint the temperature transmitters are calibrated. |
| `level_gain` | 4 to 40 (log) | %/m | Proportional gain of every level loop. |
| `level_integral_s` | 240 to 2400 (log) | s | Integral time of every level loop. |
| `pump_bias_pct` | 15 to 60 | % | Pump speed the level loop starts from before its own terms. |
| `temperature_gain` | 0.8 to 15 (log) | %/K | Proportional gain of every temperature loop. Harder to choose here than in the unheated family: the loop's effective gain changes with the level, so a tuning that is right at the setpoint is brisk when the tank is low. |
| `temperature_integral_s` | 120 to 1800 (log) | s | Integral time of every temperature loop. |
| `duty_bias_pct` | 10 to 55 | % | Heater duty the temperature loop starts from before its own terms. |
| `flow_meter_chance` | 0.4 to 1 | — | How likely each stage is to have a flow meter on its inlet. |
| `level_noise_m` | 0.002 to 0.05 (log) | m | Measurement noise on every level transmitter. |
| `level_drift_m` | 0.001 to 0.04 (log) | m | Bound on each level transmitter's slow drift. Worth watching in this family in particular: a drifting level transmitter moves the thermal mass the temperature loop is working against, so it shows up twice. |
| `temperature_noise_c` | 0.01 to 0.7 (log) | degC | Measurement noise on every temperature transmitter. |
| `temperature_drift_c` | 0.005 to 0.4 (log) | degC | Bound on each temperature transmitter's slow drift. |
| `flow_noise_fraction` | 0.001 to 0.02 (log) | — | Measurement noise on every flow meter, as a fraction of a pump's full flow. |
| `actuator_noise_pct` | 0.01 to 0.5 (log) | % | Measurement noise on reported pump speed and heater duty. |
| `scan_period_s` | 5 to 90 | s | How often the SCADA system polls every register block. |
| `event_gap_low_steps` | 40 to 400 | samples | Shortest quiet stretch between two benign events. |
| `event_gap_span_steps` | 200 to 2000 | samples | How much longer the longest quiet stretch may be than the shortest. |
| `surge_fraction` | 0.08 to 0.4 | — | How much a demand surge raises the draw while it lasts. |
| `surge_steps` | 30 to 400 | samples | How long a demand surge lasts. |
| `feed_drop_c` | 2 to 15 | degC | How much colder the feed turns during a cold-feed excursion. |
| `feed_drop_steps` | 40 to 400 | samples | How long a cold-feed excursion lasts. |

#### `level_flow` — Pumped tank chain

Liquid is pumped through a chain of tanks and drawn off at the end by a demand nobody at the site controls. Each tank has a level transmitter and a pump filling it, held at a target level by its own control loop. Chains may run side by side into a common header.

| Parameter | Range | Unit | What it is |
|---|---|---|---|
| `trains` | 1 to 3 | — | How many chains run side by side into the common header. Real sites run more than one so a stream can be taken out for maintenance without stopping supply. |
| `stages` | 2 to 4 | — | How many tanks each chain is made of, counting in the direction of flow. |
| `tank_area_m2` | 20 to 400 (log) | m2 | Plan area of every tank. With the level span this is its volume, and it is what turns a flow imbalance into a rate of level change. Drawn in the log because a small balance tank and a large reservoir are two orders of magnitude apart. |
| `level_span_m` | 2.5 to 9 | m | Height of every tank, and the calibrated span of its level transmitter. |
| `pump_margin` | 1.3 to 3.2 | — | How much more flow each pump can deliver than its train's share of mean demand. This is how a pump is actually chosen: you work out the duty and buy something with headroom over it. Drawing the pump size independently of the demand produced chains that could never keep up — seven draws in forty — and a plant whose pumps are flat out all run has no control behaviour left to learn. |
| `flow_tau_s` | 10 to 240 (log) | s | How long a pump takes to reach a new flow after its speed changes — the liquid in the main has to accelerate. This lag is what makes a level loop a control problem. |
| `demand_base_m3ph` | 20 to 260 (log) | m3/h | Mean draw on the header. Nobody at the site controls it; everything upstream is arranged to keep up with it. |
| `demand_daily_m3ph` | 4 to 70 (log) | m3/h | Amplitude of the once-a-day swing in that draw — the morning and evening peaks. |
| `demand_floor_fraction` | 0.1 to 0.5 | — | Fraction of the mean draw the header never falls below, even at four in the morning. |
| `level_setpoint_fraction` | 0.35 to 0.7 | — | Where in the tank the loops hold the level, as a fraction of its height. Sites keep headroom above for a surge and a working volume below. |
| `level_gain` | 4 to 45 (log) | %/m | Proportional gain of every level loop: how hard the pump responds to being off target. |
| `level_integral_s` | 240 to 2400 (log) | s | Integral time of every level loop: how long it takes to repeat the proportional term, so how patiently it removes a standing offset. |
| `pump_bias_pct` | 15 to 65 | % | Pump speed the loop starts from before its own terms. A real loop carries a feedforward, and it keeps the integral from having to supply the whole operating point. |
| `flow_meter_chance` | 0.35 to 1 | — | How likely each stage is to have a flow meter on its inlet at all. Below one, some tanks are instrumented on level alone — which is how a great many real sites are, and means a detector cannot assume every flow it needs is measured. |
| `level_noise_m` | 0.002 to 0.06 (log) | m | Measurement noise on every level transmitter. |
| `level_drift_m` | 0.001 to 0.05 (log) | m | Bound on each level transmitter's slow calibration drift. |
| `flow_noise_fraction` | 0.001 to 0.02 (log) | — | Measurement noise on every flow meter, as a fraction of a pump's full flow. |
| `pump_noise_pct` | 0.01 to 0.5 (log) | % | Measurement noise on the reported pump speed. |
| `scan_period_s` | 5 to 120 | s | How often the SCADA system polls every register block. A plant polled every two minutes is a plant where a detector watching the wire sees far less than one polled every five seconds, and both exist. |
| `event_gap_low_steps` | 40 to 400 | samples | Shortest quiet stretch between two benign events. |
| `event_gap_span_steps` | 200 to 2000 | samples | How much longer the longest quiet stretch may be than the shortest. Most of any run is normal, and this is what makes that true. |
| `surge_fraction` | 0.08 to 0.45 | — | How much a demand surge raises the draw on the header while it lasts. |
| `surge_steps` | 30 to 400 | samples | How long a demand surge lasts. |

#### `power` — Islanded generating set

A generating set supplying an island with no grid behind it. A governor holds the frequency by varying fuel and an automatic voltage regulator holds the bus voltage by varying excitation. Because there is no grid, taking load slows the whole island down, and on every outgoing circuit the power, the voltage and the current have to multiply out.

| Parameter | Range | Unit | What it is |
|---|---|---|---|
| `feeders` | 1 to 4 | — | How many outgoing circuits leave the site. Each one is metered separately, and each one has to satisfy the power identity on its own. |
| `rated_mw` | 3 to 200 (log) | MW | What the machine is rated at. A small standby set and a mid-size industrial station are nearly two orders of magnitude apart, which is why this is drawn in the log. |
| `nominal_hz` | 50 or 60 | Hz | The frequency the island runs at. Discrete, because 55 Hz is not a cautious middle — it is a plant that does not exist. |
| `load_factor` | 0.3 to 0.85 | — | Mean island load as a fraction of rated output. Below this the machine is barely loaded and above it there is no headroom for a customer to pick up. |
| `demand_daily_fraction` | 0.04 to 0.35 | — | How far the island's draw swings over a day, as a fraction of its mean. |
| `inertia_hz_per_mw_s` | 0.004 to 0.06 (log) | Hz/MW/s | How far the frequency falls per megawatt of unmatched load per second. This is the machine's rotating inertia, and it is the whole reason frequency moves at all: a heavy machine rides through a load step that a light one notices immediately. |
| `fuel_tau_s` | 1 to 10 (log) | s | How long the machine takes to turn a fuel change into output. Seconds, not tens of seconds: a gas turbine's fuel system is fast, and it has to be, because frequency on an islanded machine is an integral and there is nothing else holding it up. |
| `nominal_kv` | 3.3 to 33 (log) | kV | Bus voltage the machine is designed around, and what the AVR holds it at. |
| `voltage_tau_s` | 1 to 20 (log) | s | How long bus voltage takes to follow a change in excitation. |
| `bus_drop_fraction` | 0.01 to 0.1 | — | How far the bus sags at full load, as a fraction of nominal voltage — the machine's own impedance in per-unit, which is how a machine's reactance is actually quoted. The kV-per-amp figure the physics reads is derived from it. Drawn in kV/A directly, the same number was a rounding error on a small machine at high voltage and a 26% collapse on a large one at low voltage, because an amp means nothing without knowing the machine. This is what couples the feeders to each other: load on one pulls the voltage every other feeder is measured against. |
| `power_factor` | 0.78 to 0.99 | — | Mean power factor of the load. It appears directly in the power identity, so a detector that ignores it will find the identity broken on every honest sample. |
| `governor_droop_fraction` | 0.01 to 0.05 | — | How far the frequency is allowed to fall, as a fraction of nominal, while the governor picks up the largest load step a customer makes. This is a governor's droop, which is what a real one is actually specified by, and the gain in percent per hertz is derived from it together with the machine's rating, its inertia and the step it has to reject. Drawn as a gain directly, the governor was unstable on seventeen draws in twenty — frequency is an *integral* of unmatched power, so a gain that suits a 6 MW set makes a 170 MW one hunt, and no gain at all works if the loop is tuned to a timescale over which the frequency has already left the building. |
| `governor_integral_multiple` | 2 to 8 | — | How much slower the governor's integral action is than its proportional action. Above one because an integral faster than the loop it is correcting winds up and oscillates, which is the second half of what made the independently drawn tuning unstable. |
| `avr_loop_gain` | 1 to 8 (log) | — | Dimensionless loop gain of the automatic voltage regulator — how hard it pushes, relative to how much the bus voltage actually moves per percent of excitation. The gain in percent per kilovolt is derived from it and the machine's nominal voltage. |
| `avr_integral_multiple` | 1 to 5 | — | How much slower the AVR's integral action is than the field's own time constant. |
| `avr_bias_pct` | 30 to 70 | % | Excitation the AVR starts from before its own terms. |
| `frequency_noise_hz` | 0.002 to 0.08 (log) | Hz | Measurement noise on the frequency transducer. |
| `voltage_noise_fraction` | 0.0005 to 0.01 (log) | — | Measurement noise on bus and feeder voltage, as a fraction of nominal. |
| `power_noise_fraction` | 0.001 to 0.02 (log) | — | Measurement noise on the power and current meters, as a fraction of rated output. |
| `power_factor_noise` | 0.001 to 0.02 (log) | — | Measurement noise on the power-factor meters. |
| `scan_period_s` | 1 to 10 | s | How often the station is polled, which in this engine is also how often its regulators run. Much faster than the other families, and it has to be: an islanded machine's frequency is an integral, so a governor updated every half minute has no chance of holding it. A real turbine governor is a local controller running far faster than this and faster than anything this engine represents. |
| `event_gap_low_steps` | 60 to 600 | samples | Shortest quiet stretch between two benign events. |
| `event_gap_span_steps` | 300 to 3000 | samples | How much longer the longest quiet stretch may be than the shortest. |
| `load_step_headroom` | 0.2 to 0.9 | — | How much of the machine's spare capacity the largest customer load step takes up. The step as a fraction of rated output is derived from it and the load factor. Drawn as a fraction of rating directly, a quarter-rating step on a machine already at 85% drove the demand past what the set can make, and the fuel valve sat at its stop for most of the run — a plant with no governor behaviour in it at all. |
| `load_step_steps` | 30 to 600 | samples | How long a customer's load step lasts. |
| `power_factor_shift` | 0.02 to 0.12 | — | How far switching moves the power factor while it lasts. |
| `switching_steps` | 30 to 600 | samples | How long a feeder-switching event lasts. |

#### `thermal` — Heated vessel chain

Fluid passes through a chain of heated vessels. Each has a heater held at a target temperature by its own loop, and each is fighting two things at once: the stream running through it carrying heat away, and the room around it taking heat out through the walls.

| Parameter | Range | Unit | What it is |
|---|---|---|---|
| `trains` | 1 to 3 | — | How many chains of vessels run side by side. |
| `stages` | 2 to 4 | — | How many heated vessels each chain is made of, counting in the direction of flow. |
| `holdup_kg` | 200 to 20000 (log) | kg | How much fluid is in each vessel. With its heat capacity this is the thermal inertia — why a large vessel's temperature barely moves in a minute and a small one's does. |
| `heat_capacity_kj_per_kg_k` | 1.8 to 4.2 | kJ/kg/K | Specific heat of whatever is being heated. Water sits at the top of this range and most organic liquids near the bottom. |
| `heater_margin` | 1.2 to 2.6 | — | How much more heat each heater can put in than the duty its vessel actually needs at the design point. This is how a heater is chosen: you work out the duty from the throughput, the temperature rise and the heat loss, and buy something with headroom over it. Drawing the rating independently produced chains whose heaters were pinned at full duty for the whole run — three draws in five — and a saturated loop has no control behaviour to learn. |
| `ua_ambient_kw_per_k` | 0.02 to 2.5 (log) | kW/K | How fast each vessel loses heat to the room, per degree it is above it. A well-lagged vessel sits at the bottom of this range and a bare one at the top. |
| `feed_temp_c` | 4 to 40 | degC | Temperature of what arrives at the front of the chain. |
| `ambient_base_c` | 2 to 28 | degC | Mean temperature of the room or the yard the vessels stand in. |
| `ambient_daily_c` | 1 to 14 | degC | How far the room's temperature swings over a day. A vessel outdoors swings more than one in a heated building, and the loops have to absorb it. |
| `residence_minutes` | 12 to 240 (log) | min | How long fluid spends in each vessel at mean throughput — the holdup divided by the flow. The throughput in kilograms per hour is derived from it and the holdup, because the residence time is the quantity that actually matters and the one an engineer would quote. Drawn as a throughput directly, the residence time ranged from a minute to two days: a vessel whose contents turn over faster than the plant is sampled is not a hard plant, it is an unresolved one, and the energy balance said so on three draws in five. |
| `flow_daily_fraction` | 0.02 to 0.3 | — | How far the throughput swings over a day, as a fraction of its mean. |
| `temperature_setpoint_c` | 40 to 150 | degC | What every vessel in the chain is held at. |
| `temperature_headroom` | 1.25 to 2 | — | How far above the setpoint the transmitters are calibrated, as a multiple of it. Real spans carry headroom, and a signal that sits at the top of its own span all run is a signal whose range tells a detector nothing. |
| `temperature_gain` | 0.8 to 18 (log) | %/K | Proportional gain of every temperature loop: how much duty it adds per degree of error. |
| `temperature_integral_s` | 120 to 2400 (log) | s | Integral time of every temperature loop. A vessel with a long residence time needs a patient loop; a brisk one on a slow vessel hunts. |
| `duty_bias_pct` | 5 to 55 | % | Heater duty the loop starts from before its own terms, so the integral does not have to supply the whole operating point. |
| `temperature_noise_c` | 0.01 to 0.9 (log) | degC | Measurement noise on every temperature transmitter. |
| `temperature_drift_c` | 0.005 to 0.5 (log) | degC | Bound on each temperature transmitter's slow calibration drift. This is the one that matters: a thermocouple drifting half a degree over a week is ordinary, and it is also exactly what a slow sensor-spoofing attack looks like. |
| `duty_noise_pct` | 0.01 to 0.6 (log) | % | Measurement noise on the reported heater duty. |
| `flow_noise_fraction` | 0.001 to 0.025 (log) | — | Measurement noise on the throughput meter, as a fraction of mean throughput. |
| `scan_period_s` | 5 to 120 | s | How often the SCADA system polls every register block. |
| `event_gap_low_steps` | 40 to 400 | samples | Shortest quiet stretch between two benign events. |
| `event_gap_span_steps` | 200 to 2000 | samples | How much longer the longest quiet stretch may be than the shortest. |
| `feed_drop_c` | 2 to 18 | degC | How much colder the feed turns during a cold-feed excursion — a tanker of cold material, or a change of source. |
| `feed_drop_steps` | 40 to 500 | samples | How long a cold-feed excursion lasts. |
| `throughput_fraction` | 0.08 to 0.45 | — | How far a throughput change moves the stream while it lasts. |
| `throughput_steps` | 40 to 500 | samples | How long a throughput change lasts. |

<!-- END GENERATED: family bounds -->

## What R3 added: a plant is refused before it is written, and then written

### Quick start

```bash
# what can be drawn
python scripts/generate_plants.py list-families

# draw one plant and write a day of it
python scripts/generate_plants.py generate level_flow 2026001

# draw twenty, from consecutive seeds
python scripts/generate_plants.py generate-batch thermal 2026001 --count 20

# check what was written against its own manifest
python scripts/generate_plants.py verify data/plants/level-flow-2026001
```

Nothing it writes is committed. A plant drawn from a family and a seed is reproduced exactly by
drawing it again, so storing it would put a large binary in a repository whose whole claim is
reproducibility.

### The gate

Drawing inside a declared range is not enough. A pump can be too small for the outlet it is
paired with; a loop's gain and its time constant can put it into permanent oscillation; a tank's
working level can sit above the top of its own gauge; a signal can simply never move. Data from
such a plant is not hard training data — it is wrong, and a model that learns it learns something
untrue about industry.

So every candidate is **run for a few hours and then judged**, on six questions:

| Check | What it asks |
|---|---|
| Finite | Did any value become infinite or not-a-number? |
| Conservation | Does every balance the process declares actually close? |
| Range | Does the plant sit where its own instruments can see it? |
| Variability | Does anything actually move, or is most of it standing still? |
| Saturation | Is a valve or a heater jammed at its stop for the whole run? |
| Controllability | Does each loop reach its target, and then hold it? |

A candidate that fails is **refused, with the relation it broke named** — never clipped, never
nudged into range. Then another is drawn from a fresh child seed, and the number refused goes into
the plant's manifest. A high count is not noise to hide; it says the family's declared ranges are
wider than its physics, which is a finding about the family.

As it stands, 52 of 150 candidates are refused across the five families — about 1.4 draws per
plant. The hybrid family is the worst at one in two, because its temperature loop is working
against a thermal mass that its *other* loop is moving. That is written down rather than tuned
away.

#### A process has to state its own physics, or it cannot be checked

One of those six is different from the others. The gate can tell that a value went infinite
without knowing anything about the plant, but it cannot check conservation that way: the plant
says a level depends on two flows, and nothing tells the gate which of them is the way in.

So each process states its own balances, and **a process that states none fails the gate rather
than passing it**. That is deliberate. The alternative waves through exactly the plants whose
physics nobody checked, and does it silently.

### What the gate found

Building the gate was worth it before it had refused a single plant for a good reason, because
running it on the existing families exposed five things that were wrong — and every one of them
was the same mistake: *a number drawn without reference to the thing it describes.*

- The generating set's governor gains were drawn in percent per hertz. Frequency on an island is
  a running total, so a gain that suits a 6 MW machine makes a 170 MW one swing. Twenty-five draws
  in thirty were refused. It is now sized from the droop it has to hold and the largest load step
  it has to catch.
- The same machine's impedance was drawn in kilovolts per amp — a rounding error on a small
  machine and a 26% voltage collapse on a large one.
- Its load step was a fraction of its rating, so a quarter-rating step on a machine already at 85%
  asked it for more power than it can make.
- Its fuel system was allowed to take up to 40 seconds. No governor can hold frequency through
  that.
- The heated-vessel family drew a throughput, which gave residence times from one minute to two
  days. A vessel whose contents turn over faster than the plant is sampled is not a hard plant, it
  is an unresolved one.

And two of the checks were themselves broken. Saturation flagged every batch plant, because a feed
valve that is open while the vessel fills and shut the rest of the time sits at a limit the whole
run — and is completely correct; it is not a loop with no authority, it is not a loop at all. And
the range check looked at the *reported* reading, which a transmitter clamps into its own span, so
it could never fail however wrong the plant was. It now looks at what the plant is truly doing.

### What a plant looks like on disk

| File | What it holds |
|---|---|
| `telemetry.csv` | The readings, one row per sample, with a timestamp and a label column |
| `labels.json` | What legitimately happened and when — ground truth |
| `topology.toml` | Which readings belong to which piece of plant |
| `plant.json` | The plant's own description, which is enough to rebuild it |
| `control.json` | What the control logic is, in plain language |
| `registers.json` | Where each reading sits on the network, and its calibrated span |
| `capture.pcap` | The control traffic, as a packet capture |
| `manifest.json` | Family, seeds, rejections, every parameter, and a digest of every file |

Two of those are checked by going in through Atlas's own front doors, unchanged: the telemetry
loads through exactly the reader a downloaded corpus goes through, and the capture parses through
the real protocol dissector without a single malformed frame — with **every value read off the
network matching the value the telemetry published for it**. The capture and the telemetry are two
views of one simulated run, so if they disagreed about what the plant said, anything watching both
would be right to distrust both.

## What R4 added: things happen, on four layers

R3's plants were all normal. R4 is what makes something happen to them — an attack, a fault, a
piece of maintenance — and labels it so a scorer knows what it was.

It started with an audit (`coverage.md`), because the rule was *do not rebuild what exists*. Most of
the effects already existed; what was missing was the **label**. A stuck transmitter was already
modelled — it just was not recorded as a fault, with the layer it acted on and whether it moved the
plant. So R4 is mostly labelling and scheduling, with new physics only where there was none.

### The four layers something can happen on

| Layer | What it means | Example |
|---|---|---|
| Sensor | The reading is false; the plant is fine | a meter replays its own earlier values |
| Actuator | A final control element does the wrong thing | a valve sticks, a pump trips |
| Process | Material leaves by a route nothing meters | a leak |
| Network | The wire carries something the plant never sent | a value changed in transit, a flood, a replay |

Every event's record says which layer it was on, because the layer bounds what could possibly have
noticed. A false *reading* leaves the process untouched, so only a model of how signals relate can
catch it; a manipulated *actuator* moves the plant, so a physical model can.

### The leak, and why it is the interesting fault

Most faults are easy to fake badly: change a number in the output file and move on. A leak cannot be
faked that way, and that is what makes it worth having. A real leak removes material the plant was
holding — so the level falls, the control loop sees it and pumps harder, and the amount that left is
in none of the meters. A detector that checks whether what came in equals what went out plus what is
stored will find the sums no longer add up. If you *painted* a leak onto the telemetry, the sums
would still add up — and that closing balance would be the giveaway that nothing really leaked. So
the leak removes real inventory, and it is checked that the balance actually stops closing.

### The wire can now disagree with the control room

The network attacks change the captured traffic and nothing else. The plant carries on; the
historian records what the plant did; but the wire said something different. An operator watching
the screen sees the tampered value, the process does nothing unusual, and the one thing that can
tell them apart is a detector comparing the two. That disagreement is the whole point — and the
manipulated capture still parses cleanly through the real protocol reader, replayed and injected
frames and all.

### What is on purpose *not* here

No attack search, no tuning against a detector, no scoring. The events are drawn from a seed and
that is all. A generator that could aim at a detector's weak spot would no longer be making data, it
would be training against a target — that is a separate tool (the breaker, much later) and a
separate package for exactly that reason. And **most of any run is normal**: a schedule that would
fill more than a quarter of the run is refused, because a corpus busier than a real plant would give
a detector a false-alarm rate three times kinder than the one it meets in service.

### One attack left for later, said plainly

Changing a control loop's own tuning mid-run — its gain, how hard it reacts — is in the catalogue
and is **not built**. It does not fit: the four layers above all reach the plant from outside, and a
loop's tuning is inside it, part of the machine rather than something done to the machine. Building
it would mean changing how every one of the six process types wires up its controllers, for one
attack. That is a decision worth its own write-up, not something to slip into this part, so it is
left on the list with the reason beside it.

## What R5 added: the audits, and how to drive the whole thing

R5 is the finish: the checks that the generator does what this document says, and the two tools for
looking at what it produced.

### Everything you can run

```bash
# what can be drawn
python scripts/generate_plants.py list-families

# one plant, a day of it, with one of every kind of event
python scripts/generate_plants.py generate level_flow 2026001 --events 1

# twenty plants from consecutive seeds
python scripts/generate_plants.py generate-batch thermal 2026001 --count 20 --events 1

# check what was written against its own manifest
python scripts/generate_plants.py verify data/plants/level-flow-2026001

# describe a whole batch: what is in it, and nothing about how good it is
python scripts/summarise_plants.py data/plants

# prove the same seed gives the same bytes, in fresh processes
python scripts/audit_reproducibility.py --all-families

# prove the three hand-written plants still produce what they always did
python scripts/synth_golden.py
```

### The reproducibility audit, and why it uses separate processes

The claim this whole package rests on is that a corpus defined by a family and a seed does not need
to be *stored*, because it can be made again exactly. That is why the payload is git-ignored and
the manifest carries digests instead of data.

`audit_reproducibility.py` checks it the only way worth checking: it generates the same plant twice
in **two separate `python` runs** and compares every file byte for byte. Two generations inside one
program share too much — a cache, a module-level dictionary, a random stream somebody forgot to
reset — and would agree for reasons that have nothing to do with determinism.

It also checks the opposite, which matters just as much: a generator that returned the same bytes
for *every* seed would sail through the first half. So the second half changes only the seed and
insists the plant is structurally different. Determinism without variety is a fixture, not a
generator. All five families pass both halves.

### The summary describes; it does not grade

`summarise_plants.py` reads a folder of generated plants and prints what is in it: how many per
family, the range of each structural parameter, how often the validity gate refused a candidate,
and how much of each run has something happening in it.

There is deliberately nowhere in that script to put a detection, a recall or a false-alarm rate. A
summary that could also grade something would be read as a grade, and the referee — much later in
the programme — is the only thing entitled to produce one. This answers the question that comes
first: *what did we actually generate?*

### How long it takes

A 24-hour run, on an Apple M4 (10 cores), Python 3.12. "Normal" is a plain corpus; "with events"
places one of every kind, including the network-layer ones:

| Family | Samples in 24h | Scan period drawn | Normal | With events |
|---|---|---|---|---|
| `thermal` | 815 | 106 s | 0.1 s | 0.2 s |
| `level_flow` | 1,200 | 72 s | 0.2 s | 0.4 s |
| `batch_mix` | 1,489 | 58 s | 0.2 s | 0.3 s |
| `power` | 14,400 | 6 s | 1.8 s | 2.6 s |
| `hybrid` | 12,342 | 7 s | 3.3 s | 5.5 s |

The spread is not one family being slow. It is that **how often a plant is polled is itself drawn**,
and the sample count follows: a generating set polled every six seconds has eighteen times the
samples of a heated chain polled every hundred and six. A thousand plants is minutes, not hours.
Add roughly a third again for each candidate the validity gate refuses — about 1.4 draws per plant
on average, and about 3 for `thermal`, which has the widest bounds relative to its physics.

## What is NOT modelled

Worth being blunt about, because every item here is a way a real plant is harder than these ones.

- **No real device, ever.** Nothing in this package opens a socket or runs another program; it is
  checked by a test over every module. The packet captures are bytes assembled with `struct` and
  written to a file.
- **One protocol.** Modbus/TCP, because it is the one Atlas can read. A real site runs several, and
  a plant whose control is on something else appears here as a plant with no capture at all —
  which is honest, and one of the five families is deliberately like that.
- **No multi-site, no historian quirks, no clock problems.** One plant, one clock, evenly spaced
  samples. Real historians backfill, drop, interpolate and re-stamp.
- **Dynamics faster than the sample interval do not exist.** The sample interval *is* the
  integration step, so anything happening between two samples is not represented. A real
  transient, a real water hammer, a real electrical fault are all faster than this.
- **The control is PI loops and recipes, and nothing else.** No cascaded override logic, no
  interlocks firing, no safety system tripping, no operator fighting the plant.
- **A controller's own tuning never changes.** The one catalogue attack left unbuilt (see the R4
  section) — and in reality, parameters do drift, get retuned, and get tampered with.
- **The physics is lumped and small.** Tanks are perfectly mixed, pipes have no length, gas is
  isothermal, reactions are single-step. Every balance closes to within a few parts per thousand
  *because the model is simple*, not because a real plant would.
- **Above all: these are models, not plants.** Every manifest says so. A number measured here is a
  number about this simulation, and nothing measured on a generated plant may be quoted as a result
  on a real one.

## Where the simulator stands

R1 made a plant a document. R2 made a seed draw one. R3 refused the ones that could not exist and
wrote the rest to disk. R4 made things happen to them, on four layers, each labelled. R5 proved it
reproduces and gave it the tools to be looked at.

The decisions are ADR 0434 (R1), 0435 (R2), 0436 (R3), 0437 (R4) and 0438 (R5). ADR 0438 also
carries what R1–R5 changed about the original declaration, ADR 0433, which is left as written
because a record is immutable once accepted.

Two things are known-open rather than forgotten:

1. **Two of a plant's own numbers can contradict each other** and nothing notices — a governor's
   target and the island's nominal frequency both say what it runs at. The validity gate catches
   the *consequence* (a loop holding the wrong number does not settle) but not the contradiction.
2. **Control-logic parameter tampering is not built**, with its reason recorded in
   `coverage.md` and ADR 0437: it reaches inside the machine rather than acting on it, and it
   deserves its own decision rather than being slipped in.

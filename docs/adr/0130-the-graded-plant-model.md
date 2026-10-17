# ADR 0130 — The graded plant model: every link says how Atlas knows it

- **Status:** Proposed. Its first step, grade C on ICSSim, was built and measured on 15 October at Elijah's instruction (see the end)
- **Date:** 2026-10-15
- **PART:** after ADR 0123 step 3; `docs/phos-2027.md` W2–W4
- **Depends on:** [ADR 0123](0123-the-plant-map-proposed.md),
  [ADR 0126](0126-declared-loops-narrow-the-level-form-bar.md),
  [ADR 0129](0129-the-plant-map-detects-but-is-not-yet-a-map.md)

## Context

ADR 0129 found that `atlas-plant-map-v1` detects the liar the champion cannot, but by its own
falsifiers is not a map. Half of HAI 20.07's links change between its two training files
(§9.6), fewer than half of the synthetic plants' learned links follow their declared plumbing
(§9.5), and so it may not name an instrument or emit a reconstruction (§9.7, §9.9).

That is a limit of the evidence, not of the tuning. A map learned only from normal co-movement
cannot tell, inside a closed loop, the valve that moves the level from the level that moves the
valve, and a shared daily schedule makes unrelated parts of a plant move together. Engineers do
not learn a plant that way. They read its drawings and control narratives, they know which
controller reads which instrument and drives which valve, they watch what responds when someone
changes something, and they check that the balances add up.

Elijah's goal, set on 15 October, is a category-defining understanding of the plant. This record
proposes it: **a plant model in which every link carries the evidence for it**, so that Atlas
can say not only what drives what, but how it knows, and where it does not know.

## Decision (proposed)

**1. Every link has a grade**, the strongest kind of evidence for it.

| Grade | Name | Earned when |
| --- | --- | --- |
| **A** | Declared | The plant's documentation states it (a role file's loop, a declared coupling, a drawing), **and** the data does not contradict it: a statistical link agrees in direction, or none disagrees |
| **B** | Intervened | A logged change to *T* (an operator write, a setpoint change, a work order) is followed, within a declared horizon, by *S* leaving its normal band, in at least 3 logged changes and in at least two thirds of them, and *S* never moves first. Direction *T* → *S* |
| **C** | Network-observed | A controller reads *X* over the network, and the actuators it hosts are the only ones that could be driven by it: *X* drives one of that set. Narrowed to one actuator only when a statistical link agrees |
| **D** | Statistical, stable | A map link that appears in maps fitted on disjoint halves of training, with lags within one grid step |
| — | Rejected | A statistical link that fails D's test. It is kept for detection, never shown as structure |

A link may hold several grades; it is shown with its strongest, and every piece of evidence is
kept beside it.

**2. What each grade may do.**

- **Detection** uses every learned link, as `atlas-plant-map-v1` does now. Grading takes nothing
  away from what ADR 0129 measured.
- **Naming and reconstruction** run on the subgraph of grades A–C. A–C is evidence an engineer
  would accept from a colleague: the drawing, the controller's own traffic, a change seen to
  propagate. D can corroborate, never decide.
- **"I don't know" is an output.** A signal with no A–C link into it is reported as "the plant
  model cannot place this reading", rather than reconstructed from statistics.

**3. Each grade's evidence is declared or observed, never inferred from a name.** Documentation
for A, under ADR 0123 §3's rules. Logged writes and work orders for B, which ICSSim records
(`modbus.csv`, `work_orders.csv`), HAI does not, and a design partner's historian would. Network
traffic for C (`modbus.csv`; packet captures such as Netresec's 4SICS set). A grade with no
evidence source in a corpus is simply absent there.

**4. The build order.** C on ICSSim, where traffic and truth exist together; then B on ICSSim;
then D's stability test on HAI 20.07 and the synthetic plants; then A from HAI's role file and
the synthetic declarations; then naming on the A–C subgraph; then §9.7 and §9.9 again.

## What would prove it wrong

Set now, before any part is built. On development data only.

1. **C is wrong.** On ICSSim, fewer than 9 in 10 network-observed claims contain a true control
   relation, judged against the loops declared from ICSSim's PLC programs
   (`data/phos-icssim-dev/roles.toml`).
2. **B is wrong.** On ICSSim's development runs, fewer than 8 in 10 intervened links lie on a
   true path of the plant, judged against ICSSim's declared control programs and its physics
   (`src/FactorySimulation.py`, declared in its own record before B is scored).
3. **D adds nothing.** D keeps fewer than a quarter of the map's links on HAI 20.07, or what it
   keeps still fails §9.5 on the synthetic plants.
4. **Naming does not improve.** On the A–C subgraph, the right instrument is named in under 70%
   of caught development liar runs, or a wrong one in over 10%: §9.7's own bars, unmoved.
5. **It does not know enough to matter.** On the water plant, the liar's target has no A–C link
   into it, so the model can only say "cannot place it" where ADR 0129 named it correctly.

## Consequences

- If accepted, `docs/phos-2027.md`'s W2–W4 gain their mechanism: Atlas's account of a plant is a
  set of claims an engineer can check, each with its source.
- HAI cannot earn B (no logged interventions) and has no network capture; its model can reach A
  and D only. A design partner's drawings, historian and traffic are what A, B and C need on a
  real plant, which is one more reason the outreach matters.
- The limits are stated now. The network shows only what crosses it: a controller's own local
  inputs never appear on the wire, so C sees cross-controller and supervisory relations, not
  every loop. A logged change is not a randomised experiment: an operator changes things for
  reasons, and B can mistake a coincident disturbance for a response; its two-thirds rule and
  "S never moves first" are the guard, not a proof.

## What would reverse this

Inferring a grade from a tag's name; letting a D link decide a naming; moving a threshold in
"What would prove it wrong" after a score has been seen; or reading a `validation` or `held-out`
corpus for any part of it.

## First step, built and measured (15 October 2026)

Grade C is `phos.atlas.network_links`, measured by `scripts/plant_map_dev.py network` on
`phos-icssim-dev`'s three normal runs. **Falsifier 1 passes:** 4 claims, 4 true against the loops
declared from ICSSim's PLC programs (PLC-1 reads the bottle level, the bottle's distance and its
limit from PLC-2 to drive its output valve; PLC-2 reads the tank's outflow from PLC-1 to drive
its conveyor). Two claims were narrowed by a statistical link, both to the right valve. All 3
loops that cross controllers were found; the other 3 close inside one PLC and never appear on
the wire. All 13 development runs, the attack runs included, give the same claims: the
attacker's reads and writes make none, because the attacker serves no points.
ICSSim is a small plant with named tags; on a real network the points are register addresses,
and grade C there needs the register map a design partner holds.


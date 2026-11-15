# ADR 0372 — Three physics laws are declared by hand, the inlet balance is refused, and deriving them is refused because the physics is ground truth

- **Status:** Accepted
- **Date:** 2026-11-07
- **PART:** Atlas, build brief H, rung H2. Declaration. No code exists, no corpus is opened
- **Supersedes:** nothing
- **Depends on:** [ADR 0423](0423-h2-opens-for-declarations-only-and-the-scoring-still-waits-for-the-bid.md),
  ADR 0369 (lab record, not published),
  [ADR 0370](0370-code-laws-are-derived-from-the-controller-program.md),
  [ADR 0322](0322-a-slot-enters-only-as-a-law-break.md),
  [ADR 0323](0323-every-sentence-names-the-law-it-came-from.md),
  [ADR 0295](0295-legal-flow-biases-the-level-and-keeps-the-plants-own-flow.md),
  [ADR 0132](0132-grade-b-links-from-logged-changes.md),
  [ADR 0122](0122-a-phos-generated-icssim-corpus.md),
  [ADR 0108](0108-consistency-evidence-routes-to-the-explanations.md)

## Context

Rung H2 asks for "balances on the simulated process, such as level change against flow in and flow
out, each as its own declared law," and rules that "if the simulator does not model a quantity, the
law that needs it is refused rather than approximated."

Two things were found by reading the record before writing any law, and both change what the rung
can be. The first narrows it. The second is the finding.

### The inlet is not measured

`data/phos-icssim-dev/roles.toml` is the committed tag evidence: thirteen tags, each role read from
ICSSim's own source at pin `bcfd1844d3f063850c69f2643f6a052bac03d8ec` and from nothing else.
Exactly one of the thirteen is a flow: `tank_output_flow_value`, the **outlet**.

The simulator does compute an inflow — `ICSSIM_EDGES` carries
`("tank_input_valve_status", "tank_level_value")` for a tank that "fills through the input valve" —
but it never publishes it. There is no inlet flow tag of any name. The inlet reaches the data only
as `tank_input_valve_status`, which says open or shut and never how much. A balance of level against
flow in and flow out therefore has no inflow term that can be *checked against data*, and the rule
above says what happens next: refused, not approximated from the valve state. Register entry **R29**.

### Every statement of this plant's physics is ground truth, and Atlas may not read it

This is the one that matters, and it was not anticipated when the rung was named.

The repository does state this plant's physics. `src/phos/breaking/icssim_truth.py` carries
twenty-one `driver -> driven` edges read from `src/FactorySimulation.py` at the pin, including the
pipework a physics law would need: the bottle "fills from the outflow only while it is under the
filler". ADR 0295 quotes the constants from the same file — outflow is `TANK_OUTPUT_FLOW_RATE`
(0.0001 litre per millisecond) while the output valve is open and the tank holds water and zero
otherwise, and level is the water divided by `TANK_LEVEL_CAPACITY` (3 litres), clamped at
`TANK_MAX_LEVEL` (10).
<!-- evidence-ack: src/FactorySimulation.py — AlirezaDehlaghi/ICSSIM's own path in the pinned checkout under data/, not a path in this repository -->

And that file's own docstring forbids its use here:

> **This is ground truth, so nothing that learns may read it.** Like `truth.csv` (ADR 0017), it
> judges the plant model's claims and is never an input to them: no module under `phos.atlas`
> imports this one, which a test checks.

The test is `tests/atlas/test_interventions.py:57`. So the physics is written down, and the engine is
correctly forbidden from reading it.

The one source Atlas *may* read declares something else. `roles.toml` gives each tag's role and six
control loops — "the belt runs when the bottle is away from the filler, or no flow and the bottle
full" — and states **no physical connection and no physics constant** at all. Its own header closes
the remaining gap: roles were "Never inferred from the data, and never from a tag's name." So Atlas
may not conclude that `tank_output_flow_value` is the flow through `tank_output_valve_status` because
the two names look related.

The consequence is exact. Every physics law worth writing relates two tags. Every relation between
two tags in this repository is either in the ground-truth file or in an ADR quoting it. Therefore
H2's laws **cannot be derived** the way H1 derives a code law from a controller program. They can
only be **hand-declared** — which is the precise standing of `controller_valve`, the hand copy that
H1 exists to distrust. Register entry **R30**.

That is not a defect in the rung. It is the product's own shape arriving earlier than expected:
`DeclaredLaw` is documented as "a law the plant or the operator **already declared**." A plant
declares its physics and Atlas checks the plant against it. Atlas does not discover physics from
traffic, and this record does not let it start.

### Two constraints from the page itself

`DeclaredLaw.statement` is documented "No numeric threshold," and `_SCORE_WORDS` refuses a sentence
carrying *confidence*, *probability*, *weight*, *magnitude* or *score*. `controller_valve` shows the
only permitted route: literals live in code with their provenance quoted in a comment, the statement
stays in words. And ADR 0108 with `src/phos/atlas/templates.py:93` already record that an unmodelled
event such as a leak breaks a mass balance too and is read as equipment failing. Nothing here
changes that routing.

## Decision

**Three physics laws are declared, by hand, each citing a document rather than importing one. The
inlet balance is refused. Deriving any of the three is refused on this corpus.**

### The three laws

**`closed_outlet_no_flow`** — when `tank_output_valve_mode` is release and
`tank_output_valve_status` is closed, `tank_output_flow_value` is zero. A non-zero reading through a
shut valve is not a plant state; one of the two tags is wrong. Manual mode means the law was not
stated. **No constant:** zero is zero, and the break depends on no threshold anybody chose.

**`no_inflow_no_rise`** — when `tank_input_valve_mode` is release and `tank_input_valve_status` is
closed, `tank_level_value` does not rise from one sample to the next. The tank has exactly one
modelled way in and it is shut. Manual mode means the law was not stated. **No constant:** the break
is a strict rise, the later sample strictly greater than the earlier.

**`outlet_rate_is_the_quoted_rate`** — when both modes are release, the input valve is closed, the
output valve is open and the tank holds water, the fall in `tank_level_value` between two samples is
the quoted rate over that interval: `TANK_OUTPUT_FLOW_RATE` divided by `TANK_LEVEL_CAPACITY`, times
the elapsed milliseconds. This is the only *quantitative* balance the corpus supports, and it is the
outlet half of the balance the brief asked for. Its two constants enter code the way
`controller_valve`'s four literals do, with ADR 0295 and `src/FactorySimulation.py` at the pin named
in the comment above them. The statement carries no number.
<!-- evidence-ack: src/FactorySimulation.py — AlirezaDehlaghi/ICSSIM's own path in the pinned checkout under data/, not a path in this repository -->

Two open questions are written down here rather than left for the build to trip over:

- **Quantisation.** If the level reading jitters upward while the inlet is shut,
  `no_inflow_no_rise` breaks on noise. The fix would be a tolerance, and no tolerance is quoted
  anywhere. **The law is then refused, not given one.** A tolerance chosen so a law passes is a
  knob, and this register has no knobs.
- **Sampling.** `outlet_rate_is_the_quoted_rate` compares a measured fall with a computed one, so it
  needs a comparison that is exact up to floating point and the sample interval, and nothing more
  generous. If the corpus's sample timing cannot support that, this law is refused too. The rate is
  not fitted to the data; ADR 0295 already established that this plant has no continuous
  level-to-flow ratio, so there is nothing to fit.

### What is refused

**`inlet_balance`**, the brief's own worked example — no inflow is measured. **R29.**

**Derivation of any physics law on this corpus** — the physics exists only as ground truth Atlas may
not read, and `roles.toml` states no physical relation. So H1's method does not transfer, the three
laws above stand as hand declarations, and a derived-versus-hand comparison is impossible here
rather than merely unperformed. **R30.**

### The bar, for when these are built

The build is a later change under ADR 0423. These bars are frozen now, before it:

- **b1** — all three laws appear in `LAWS` in `src/phos/atlas/declared_law.py`, each with a statement
  containing no word from `_SCORE_WORDS` and no numeral.
- **b2** — `CONTROLLER_VALVE`'s statement and the four literals `_VALVE_CLOSED`, `_VALVE_OPEN`,
  `_MODE_RELEASE` and `_BELT_PAST_FILLER` are byte-identical to this repository at the commit
  carrying this record. A hand copy is never edited to make a new law fit.
- **b3** — no module under `phos.atlas` imports `phos.breaking.icssim_truth`, and
  `tests/atlas/test_interventions.py:57` still passes. The two constants are typed into
  `declared_law.py` with their provenance quoted, exactly as `controller_valve`'s literals are, and
  are read from no import.
- **b4** — `inlet_balance` appears as no code path under any name, and no inflow term is introduced
  from `tank_input_valve_status`.
- **b5** — a break of any of the three produces a `LawBreak` whose statement names the law and the
  broken fact in a sentence a person can check, and routes per ADR 0108 with equipment failing among
  the explanations. A break is never reported as an attack on its own.

A build that cannot meet b1 through b5 is refused and recorded. ADR 0373 says which.

### Two prerequisites the build will hit

`ControllerSample` carries ten measurements and none is `tank_output_flow_value`, so two of the three
laws have nothing to read through the existing inlet. And every law in the register today is decided
on one sample or on supplied setpoint steps; two of these three need **two consecutive samples** of
one tag, which is a shape the register has never had. Neither is a reason to weaken a law.

Found in passing and left alone, because ADR 0423 Decision 3 writes no code: `ControllerSample`'s
docstring says "The nine measurements" above ten fields, and `icssim_truth.py` records
`src/FactorySimulation.py`'s sha256 only as the ellipsis `03c4a3ac…ad5e`, so the full digest of the
file this record's constants come from is nowhere in the repository.
<!-- evidence-ack: src/FactorySimulation.py — AlirezaDehlaghi/ICSSIM's own path in the pinned checkout under data/, not a path in this repository -->

## What this record does not do

- It opens **no corpus** and runs **no command**. There is no measurement here and no result name.
- It makes **no detection claim**. Three declared laws are not a detector. v1 stays **8 of 12**.
- It does not put a score, confidence, probability, weight or magnitude on the law page.
- It does not call a break an attack, and does not call an empty page a safe plant.
- It does not let Atlas read ground truth, infer a relation from a tag's name, or fit a constant.
- It does not edit `controller_valve`, retune a frozen constant, or touch a data tier.
- It does not start Intelligence, an API or a UI, and does not unblock **P1**.
- It does not open H3 or H4, and does not fill reserved numbers 0277–0284.

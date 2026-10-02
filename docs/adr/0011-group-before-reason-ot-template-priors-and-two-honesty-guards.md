# ADR 0011 — Group before reason, the OT template priors, and two honesty guards

- **Status:** Accepted
- **Date:** 2026-08-10
- **PART:** 5C — Atlas: grouping, templates and the engine
- **Supersedes / amends:** nothing. Builds on [ADR 0007](0007-the-evidence-boundary-and-a-calibrated-confidence.md),
  [ADR 0008](0008-template-based-hypotheses-log-odds-belief-and-the-residual.md),
  [ADR 0009](0009-joint-modelling-per-signal-attribution-and-the-model-that-lost.md) and
  [ADR 0010](0010-declared-topology-and-the-granularity-hai-supports.md).

## Context

Every piece of Atlas existed and none of them were joined up. 5A gave the engine a joint model that
attributes an anomaly to the signal that broke the plant's learned structure. 4A gave it an evidence
boundary and a calibrator. 5B gave it a declared map of which signals share a physical unit. 4B gave
it a reasoning engine that holds competing explanations. PART 5C is the join, and joining them
forced five decisions worth recording.

## Decision 1 — Grouping happens before reasoning, not after

**Decided:** the vertical runs score → promote → **group** → reason → narrate. The reasoning engine
only ever weighs subsystem events; it never sees the per-signal evidence underneath them.

**Why.** A hypothesis's confidence is built by accumulating evidence, so what counts as *one piece*
of evidence decides what the confidence means. Reasoning before grouping would count a single pump
event once per instrument on that pump, and every confidence downstream would be inflated by the
size of the instrumentation rather than by anything that happened in the plant. On HAI the
inflation factor would have been 12.1×.

Grouping afterwards was never coherent: by then the belief update has already run, and collapsing
hypotheses is not a thing the log-odds arithmetic supports.

`tests/atlas/test_engine.py::test_the_reasoning_engine_only_ever_weighs_subsystem_events` asserts
the ordering directly, by checking that every evidence id any hypothesis cites is a subsystem event.

## Decision 2 — A subsystem event carries its members in `source_id`, behind a marker

**The problem.** PART 5C §5 requires the collapsed evidence to "retain links to every member
`Evidence`/deviation" *and* to be an `Evidence`. `Evidence` has one `source_id: str` and no
free-form metadata, so there is nowhere obvious to put a set of ids.

**Options considered.**

1. Add a `component_ids` field to `phos.ontology.Evidence`. The most natural home, and rejected:
   PART 5C's file manifest is explicit and does not include the ontology, and §3.1's "one ontology"
   rule makes an additive change there a decision for a PART that owns the ontology.
2. Return the member index alongside the events, changing the specified `-> list[Evidence]`
   signature. Rejected: it puts traceability in a second object a caller can drop.
3. **Chosen:** `source_id` carries every member `Evidence` id, joined by commas behind the marker
   `subsystem-event:`. `member_evidence_ids` parses it and refuses anything that is not a subsystem
   event.

**Why the members are `Evidence` ids rather than `Deviation` ids.** The requirement names both. One
list suffices because the ontology already links them: a member evidence's own `source_id` is its
deviation, and that deviation's `observation_id` is the measurement. So event → member → deviation →
observation is one chain through existing references rather than two parallel lists.

**Why a marker rather than sniffing the id prefix.** `ev_` and `dev_` would in fact distinguish the
two cases, but that makes "is this a collapsed event?" a question about how identifiers happen to be
spelled. The marker makes it a declared fact, and lets `member_evidence_ids` raise a useful message
instead of silently handing back a deviation id.

`tests/atlas/test_grouping.py::test_the_drill_down_path_walks_event_to_signal_to_observation` and
`tests/atlas/test_engine.py::test_a_narrative_drills_all_the_way_back_down_to_the_measurements`
walk the full path.

## Decision 3 — `group_evidence` takes a deviation lookup, and the window grid is absolute

**The deviation lookup.** PART 5C §5 specifies `group_evidence(evidence, subsystem_map, window)`,
and that signature cannot work: membership must come from `SubsystemMap.subsystem_for(signal)`, and
an `Evidence` does not carry its signal. It carries `entity_ids`, and in a CSV-sourced corpus
`LabelledCsvAdapter` attributes every one of HAI's 79 signals to the same entity, so the entity
cannot say which signal departed. The signal lives on the `Deviation`'s `ExpectedRange`.

A fourth parameter, `deviations: Mapping[DeviationId, Deviation]`, was added. It keeps the function
pure — no store, no I/O — and recovering the signal by walking the evidence's own traceability link
is exactly the route an operator takes.

**Tumbling windows anchored to the Unix epoch**, not to the earliest evidence in the batch. Two runs
over overlapping slices of one corpus must agree about which window a measurement fell in;
anchoring to the batch would make an event's membership depend on what else happened to be passed
in. The cost is the ordinary tumbling-window one, recorded rather than hidden: two departures a
second apart land in different events if they straddle a boundary.

**Domain is part of the key** — `(domain, subsystem_id, window)` — rather than checked and rejected.
A `SubsystemMap` describes one corpus, so mixing engines cannot happen by accident; putting domain
in the key means it also cannot happen by omission, and correlating across engines stays PART 7's.

**A grouped event's `entity_ids` are the signals that departed**, per §5, not the entities behind
them. That is what makes breadth a property of one fact rather than of a set, which is what
Decision 4d depends on. One consequence, recorded rather than left to be discovered: 4B's
`ReasoningEngine` tests co-occurrence by intersecting `entity_ids`, and since membership is a
partition no two subsystem events ever share a signal — so events are never joined into one story
by co-occurrence, only by a hypothesis resting on both. That is the mechanism behind HAI's single
narrative.

**A grouped event is stamped at its earliest member** and carries the strongest member's calibrated
weight. The stamp makes the alert instant the moment the unit first departed; the weight follows
§5's rule that a unit is at least as suspicious as its most suspicious signal. Both have
consequences recorded under Decision 5.

## Decision 4 — The OT template priors, derived from two anchors rather than chosen

PART 5C §6 requires priors authored from base rates and defended here, not round numbers picked by
feel. The derivation has three parts.

### 4a. The ordering comes from base rates

- **Instrument and equipment faults are the modal cause** of unexpected behaviour in a running
  plant. A plant carries hundreds of transmitters, valve positioners and pumps, each with a service
  life measured in years, so faults arrive continuously. This is why alarm-management practice
  (IEC 62682 / ISA-18.2) treats nuisance alarms from failing instrumentation as its dominant load
  problem rather than as an edge case.
- **Human intervention and genuine process upsets are common but episodic.** Maintenance touches a
  given unit on a schedule; a controlled plant is continuously rejecting disturbances but only large
  ones break its learned correlation structure.
- **A cyber attack with a visible process effect is rarer by orders of magnitude.** The publicly
  confirmed set numbers in the tens across two decades against a population of industrial plants in
  the hundreds of thousands — an unconditional rate on the order of 10⁻⁵ per plant-year or below,
  against roughly 10¹ instrument faults per plant-year. That is a spread of five to six orders of
  magnitude.

So: `fault > {maintenance, disturbance} > unauthorised control`.

### 4b. The unconditional rate cannot be used as the prior, and why

A prior of 10⁻⁶ is not usable: with `EVIDENCE_STRENGTH = log 3` it would take thirteen fully-trusted
observations merely to reach even odds, and the reasoning engine would mark the hypothesis `PRUNED`
before anything arrived. More importantly it would be the *wrong* number. A template prior is
applied to a unit on which a calibrated, out-of-band departure has **already** been raised, so the
population is not "a plant-hour" but "an anomaly worth explaining". Conditioning on that compresses
the spread enormously, and **by how much is precisely what no available data measures** — which is
the second honesty guard, stated at its source.

### 4c. The magnitudes come from two engine-level anchors

Rather than pick numbers, `phos.atlas.templates.prior_at_rank` computes them from two facts that
already exist elsewhere in PHOS:

- **Floor.** `LOWEST_BASE_RATE_PRIOR = ReasoningConfig().pruning_threshold = 0.02`. Below it a
  hypothesis is born marked implausible, which is a verdict reached before looking. The rarest
  explanation therefore starts exactly there and no lower.
- **Step.** `RANK_ODDS_FACTOR = exp(EVIDENCE_STRENGTH) = 3`. One rank of base rate is one piece of
  fully-trusted evidence, so a gap between two explanations reads as a number of observations
  rather than as a preference.

| Template | Rank | Prior | Reading |
| --- | --- | --- | --- |
| `sensor_or_device_fault` | 2 | 0.1552 | the modal cause |
| `engineering_maintenance` | 1 | 0.0577 | common but episodic |
| `process_disturbance` | 1 | 0.0577 | common but episodic |
| `unauthorised_control_activity` | 0 | 0.0200 | rarest; the floor |
| `insufficient_evidence` | — | 0.3000 | 4B's residual, unchanged |

A third constraint falls out and is asserted: **no explanation starts above the residual**, so
before any evidence the only thing on the table is that nobody knows yet. `atlas_templates()` calls
`prior_at_rank`, so no prior in the codebase was typed in, and
`tests/atlas/test_templates.py::test_the_registered_priors_are_the_ones_the_ladder_produces` fails
if one ever is.

### 4d. What the matchers can honestly see, and what they cannot

**Breadth is expressible; `SubsystemBreadthPattern` reads it.** 4B's pattern language deliberately
describes one fact and leaves properties of a *set* to the engine. Grouping changes what "one fact"
means: a subsystem event lists the signals that departed together, so breadth is now a property of
the evidence itself. `SubsystemBreadthPattern` subclasses `EvidencePattern` inside the Atlas package
— 4B is untouched — adding a closed `[min_signals, max_signals]` band and keeping `overlaps` exact
so `HypothesisTemplate` can still refuse an ambiguous template at construction. Against a plain
`EvidencePattern` the band is read as unbounded, and the reverse call runs the base implementation
and answers conservatively, which can only make a template be refused that need not have been.

**The localised/broad boundary is a corpus fact, not a tuned threshold.** HAI 21.03 instruments a
device as at most a command channel and its feedback — `P1_FCV01D`/`P1_FCV01Z`,
`P1_PP01AD`/`P1_PP01AR` — so up to two signals is consistent with one device failing and three or
more is not. `ONE_DEVICE_MAX_SIGNALS = 2`, sourced to `data/hai/topology.toml`.

**Persistence is not a pattern, and does not need to be.** A unit that keeps departing produces a
subsystem event in each successive window, and each is another piece of evidence on the same
hypothesis. The engine's accumulation *is* the persistence measure. (That the accumulation treats
those events as independent is a real problem — see Decision 5c.)

**Two limits HAI imposes, each asserted by a test rather than only written down:**

- `engineering_maintenance` has no matcher worth the name. The corpus carries no maintenance window,
  work order or engineering-workstation context. The only thing that would genuinely argue for a
  planned change is a change in the environment's structure — `RELATIONSHIP_CHANGE` evidence —
  which Atlas does not produce yet, so on HAI this explanation never moves off its prior. A
  deviation is deliberately **not** listed as contradicting it: maintenance genuinely produces
  deviations of any breadth, so calling one evidence against it would be wrong rather than weak.
- `unauthorised_control_activity` weighs evidence **identically** to `process_disturbance` and is
  separated from it only by its prior. Process telemetry carries no control-command context, so
  nothing in this corpus distinguishes an operator's legitimate action from an attacker's. Stating
  that plainly is better than inventing a discriminator; a test asserts the two matchers are equal,
  so if a later PART finds evidence that *can* separate them, the test is what fails.

**Cross-subsystem breadth is not expressible per evidence.** §6 phrases breadth as "one subsystem vs
several", and a grouped event is one subsystem by construction. Several subsystems departing at once
is a property of a set, so it is expressed the same way persistence is: each unit's event is another
piece of evidence on the same hypothesis. Recorded here because it is a narrower reading of §6 than
the words invite.

## Decision 5 — The honesty guards, and three findings that made them sharper

PART 5C §2 makes two caveats non-negotiable and requires them to be encoded, not merely written. All
four live in `phos.atlas.ATLAS_VERTICAL_CAVEATS`, and `annotate_with_caveats` writes them into every
report's `source_note` before it reaches `eval_runs/log.jsonl` — because a document is not what a
reader of the experiment log has in front of them.

### 5a. Coarse-map inflation (required by §2)

HAI's topology could not be partitioned below process level for P1 and P2 (ADR 0010), so unrelated
departures anywhere on one process collapse into one event. The measured 12.1× reduction is evidence
that grouping is correctly **implemented**, not that it is correctly **resolved**. A finer map would
lower the headline and raise its meaning.

### 5b. Co-occurring-fault masking (required by §8)

The same coarseness can hide a second, unrelated event inside one group. Two independent faults on
one process are indistinguishable from one, and an attack co-occurring with a fault is reported as a
single thing to investigate. That is a recall risk carried by the grouping, not a win.

### 5c. Uncalibrated hypothesis confidence (required by §2) — with a third reason the run revealed

The caveat originally carried 4B's two reasons: the priors are placeholders, and `EVIDENCE_STRENGTH`
is a placeholder, and measuring either needs explanation-labelled data that does not exist. Running
the vertical on HAI surfaced a third, and it is measured rather than argued:

**The belief update treats each subsystem event as independent, and on a plant they plainly are
not.** One disturbance persisting across consecutive windows arrives as many near-identical events.
On HAI's test slice, `process_disturbance` reached 0.89 and `unauthorised_control_activity` reached
0.73 on a net 132 supporting events — not because any observation was discriminating, but because
there were a lot of them and the log-odds simply add. The caveat now says so.

A related measurement makes the point sharper: **every one of the 5,123 evidence weights on HAI is
exactly 0.0338.** The isotonic calibrator, fitted on the held-out calibration slice, maps the whole
out-of-band magnitude range onto a single probability, so on this corpus the calibrated weight
carries no discrimination at all and the confidence is driven purely by event *counts*. Fixing that
is not 5C's — it belongs to whichever PART measures `EVIDENCE_STRENGTH` and the priors — but it is
the strongest available reason not to surface a hypothesis confidence today.

### 5d. Grouped weight is a maximum

A subsystem event carries the strongest member's calibrated weight (§5's rule), and a maximum over
calibrated probabilities is not itself calibrated — it is biased upward by how many signals a unit
carries. The reported calibration error for subsystem events may therefore land better or worse than
the per-signal one for reasons that have nothing to do with the calibrator. On HAI it landed
slightly *better* (0.0243 against 0.0291), which is why the caveat states the mechanism and
deliberately predicts no direction.

## Consequences

- Atlas is a complete engine: real industrial telemetry in, explainable competing-hypothesis
  narratives out, every conclusion traceable to a measurement.
- On HAI: **5,123 per-signal alerts → 424 subsystem events, 12.1× fewer things to investigate, at
  identical recall** (both attack windows covered before and after, checked by overlap). FP per
  normal hour 646.58 → 53.26. This is a counting change and the script says so in those words.
- The before row is not an approximation of PART 5A's number, it *is* it: for a joint model a
  magnitude is a departure in band widths, so "outside the reported band" and `magnitude >= 3.0`
  select the same alert set when `band_k = 3.0`.
- Four caveats now travel with every logged Atlas number.
- `pyproject.toml` gained `--import-mode=importlib` / `consider_namespace_packages` for pytest and
  `explicit_package_bases` / `mypy_path = "src:."` for mypy. Constitution §5 says `tests/` mirrors
  `src/phos/` package by package, so `tests/atlas/test_engine.py` and
  `tests/reasoning/test_engine.py` both legitimately exist; the default import modes identify a test
  module by basename alone and refuse the pair. This is the minimal configuration that makes the
  mirroring rule expressible.

## Alternatives rejected

- **Deriving subsystem membership from co-movement** — barred by ADR 0010 as circular, and nothing
  here relaxes it. A corpus without a declared `topology.toml` is skipped by the evaluation script
  rather than grouped by some other rule.
- **Tuning the grouping window to improve the headline.** The default is one minute — six samples of
  HAI's ten-second cadence — chosen before any number was measured and left alone afterwards.
- **Shrinking the reasoning correlation window so HAI yields more than one narrative.** It yields
  exactly one, because 4B unions any evidence a single hypothesis rests on and one hypothesis per
  template accumulates continuously across a dense stream. That is 4B behaviour, it is reported as a
  limit, and tuning it here would be changing a result rather than measuring one.
- **Inventing a fifth or sixth OT explanation** to look thorough. §11 forbids it and the set is
  pinned by a test.

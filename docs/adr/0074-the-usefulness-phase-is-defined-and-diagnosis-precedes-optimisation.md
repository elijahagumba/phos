# ADR 0074 — The Usefulness Phase is defined: diagnosis precedes optimisation, and "this does not work" is a permitted result

- **Status:** Accepted
- **Date:** 2026-09-05
- **PART:** Phase definition (no implementation)
- **Supersedes:** nothing
- **Amends:** nothing. `docs/category-defining-roadmap.md` stands unchanged and `P1` remains the
  live category session.
- **Depends on:** [ADR 0029](0029-synthetic-dataset-library-is-not-a-public-corpus.md),
  [ADR 0040](0040-no-labelled-public-command-corpus.md),
  [ADR 0049](0049-split-scorecard-public-files-vs-partner.md),
  [ADR 0061](0061-clock-a-published-partner-unearned.md),
  [ADR 0068](0068-the-atlas-operator-queue-cannot-be-ranked.md),
  [ADR 0069](0069-cmms-exports-reach-the-work-order-inlet.md),
  [ADR 0072](0072-episodes-the-declared-entity-graph-and-what-cert-r31-can-and-cannot-answer.md),
  [ADR 0073](0073-a-synthetic-command-and-maintenance-harness-that-measures-nothing.md)

## Context

Clock A is complete (ADR 0049–0061). Clock B is frozen (ADR 0062). Both engines are complete
verticals. Each has exactly one measured win — Atlas on HAI, Sentiel on CERT r3.1 — and a large,
undescribed gap to being useful to anybody.

The last four measured results were refusals: VAR(1) is louder (0064), the CERT 6B queue has no
exclusive stem (0065), the correlation target cannot invert (0066), the operator queue cannot be
ranked (0068). Read together they say something the repository has not yet acted on: **further
algorithm invention is not the bottleneck.** Four attempts to make the engines better produced four
honest negatives, and none of them told us *why* the engines fail or whether their output helps a
person decide.

Two facts sharpen this.

**Atlas's false-alert load is one undifferentiated number.** 53.26 per normal hour on HAI is 424
subsystem events over 7.89 hours, 6 of which overlap an attack. It has always been treated as a
quantity to reduce. It has never been decomposed. Nobody in this repository can currently say
whether those 424 alerts are dominated by modelling error — in which case a better model is the
answer — or by insufficient context, in which case **no amount of algorithm work will help** and
the answer is more evidence. Those two conclusions point in opposite directions, and the project
has been proceeding without knowing which it is in.

**Sentiel's 0.104 has been treated as a number to optimise.** ADR 0072 measured the episode unit
honestly and reported coverage rather than recall, but the underlying failures were not
investigated: the second insider is invisible to both queues, entirely false episodes run 49, 41,
71 and 75 days, and it is not established whether the unit of analysis is even right — or whether
r3.1 contains the evidence the question needs at all.

ADR 0073 changed what is possible here. Two capabilities that could be built but never exercised
now can be. That makes a diagnostic phase feasible in a way it was not a week ago.

## Decision

**A phase is defined, not begun.** `docs/usefulness-phase-roadmap.md` and
`.phos_usefulness_state.json` are the tracked artefacts. Roughly sixty days of implementation
effort, executed as fast as is computationally possible per session and **not paced by a calendar**.

### Decision 1 — The pivot is from "does it work" to "is it useful"

From *can we make the engines technically work* to *can we prove what they produce is actually
useful to a human operator*.

This is a real reordering, not a slogan. It puts diagnosis before optimisation, makes the first
deliverable an explanation of failure rather than a reduction in it, and makes a human's decision
quality the terminal measure rather than a detection rate.

### Decision 2 — The first two items are hard decision gates that no agent may pass

U1 (Atlas error taxonomy) and U2 (Sentiel failure classification) each end by setting a gate to
`awaiting_decision` and stopping. Only Elijah may set a gate to `passed`.

The gates exist because both items may change the rest of the plan. Answering "the false alerts are
mostly insufficient context" and then proceeding to build a better model would waste the answer.
Answering "the unit of analysis is wrong" and then building an interface on the old unit would
waste that one.

**Rejected: soft gates that an agent may pass when `success_is` is met.** The failure this prevents
is the one the phase is most exposed to — an agent that has done good diagnostic work, is confident
about what it means, and carries straight on into implementation without the one human who can
judge whether the diagnosis changes the plan. The gate is worth more than the days it costs.

### Decision 3 — "This does not work" is a permitted and valuable outcome, written into the plan

Any item may conclude that the capability it examines does not work, cannot be measured on the
available data, or is not worth continuing. That conclusion is recorded in the refusal register, an
ADR, and the state file, and the phase counts it as a **success**.

This is not a new principle — ADR 0040 completed a session *by refusal*, and 0064/0066/0068 are all
negatives — but it has never been written into a plan *in advance*. Doing so matters, because the
pressure to find something is highest precisely when a phase is ending.

**If the phase concludes that PHOS produces output which does not help a human decide, that is a
finding worth sixty days**, and it must be stated plainly rather than buried under a version
number.

### Decision 4 — The nightmare outcome is named in the plan so the structure can be built against it

> "Atlas V47. 97.3% accuracy. Revolutionary." — with no real-world evidence.

Named explicitly in the roadmap. Three structural properties make it hard to reach: no item's
`success_is` is a number going up; the first two items are diagnostic and gated; and the refusal
register (U6) is a deliverable that grows as the phase proceeds, so the list of things PHOS cannot
do gets *longer* as the work continues rather than quietly shorter.

`accuracy` and `usefulness_score` are added to `keys_that_must_not_exist` in the phase state file,
alongside the existing `pooled_lead_rate` and `session_success`.

### Decision 5 — A separate state file, because the category tracker is pinned

`.phos_roadmap_state.json` has `current_session == "P1"` pinned by
`tests/eval/test_roadmap_freeze.py`. This phase therefore gets its own
`.phos_usefulness_state.json` and does not touch the category tracker.

The two run alongside each other. P1 — the design-partner conversation — remains blocked and
remains the dominant external bottleneck. U7 exists to make P1 easier to say yes to, by replacing
"share your data" with a bounded two-week question. **It does not bypass P1**, and no agent may
conduct outreach.

**Rejected: extending the existing tracker with a new session letter.** It would have required
moving `current_session` off `P1`, which is pinned, and would have implied the category programme
had advanced when it has not.

### Decision 6 — The standing procedure is in the artefacts, not in a person's head

Section 0 of the roadmap and `how_to_resume` in the state file tell a future session with **no
other context**: read the state file, take the next incomplete item by order, check the gate, do as
much as is computationally possible, update the state honestly including partial progress and
failures, and stop. Never skip a gate. Never mark an item done that was not finished.

### Decision 7 — Nothing is implemented by this record

No engine source is modified. No item is begun. U1 is `not_started` and Gate 1 is `not_reached`.
Frozen rows are untouched, no row is appended to `eval_runs/log.jsonl`, and
`.phos_roadmap_state.json` is unchanged.

## Consequences

**Gained.** The project has, for the first time, a plan whose terminal measure is a human's decision
quality rather than a detection metric — and one that can end in "no" without that being a failure
of the plan.

**Gained, second.** The refusal register (U6) turns the repository's accumulated negatives from
scattered ADRs into a single map of the boundary between what PHOS knows and what it wishes it
knew. Because each entry must state **what would lift it**, that register doubles as the
specification for what PHOS needs from the world — which is exactly what a design-partner
conversation needs to be able to hand over.

**Cost.** Sixty days that produce no new detection capability, by design. If the phase goes well,
PHOS will be able to describe its own limits far better and will detect nothing it does not detect
today.

**Cost, second.** Two hard gates mean the phase can stall on a human decision. That is deliberate,
and it is the same shape as P1: the binding constraints on this project are human, not
computational, and a plan that pretends otherwise would be lying about where the work is.

**Risk accepted.** U4 (the analyst interface) sits close to the Ω3 line. It is explicitly *not*
FastAPI, React, `src/phos/api/` or `src/phos/ui/` — neither of those trees is built, and this
<!-- evidence-ack: src/phos/api/ — not built; the programme lock forbids the surface and this record is why -->
<!-- evidence-ack: src/phos/ui/ — not built; the programme lock forbids the surface and this record is why -->
record is why — it is the smallest renderer of an existing narrative, and the roadmap instructs a
session to **stop and raise it** if the work starts to need a server. If that instruction is
ignored, this phase becomes the route by which Intelligence/API/UI arrive early, which the
programme lock forbids.

## Alternatives considered

- **Keep optimising: reduce 53.26 and raise 0.104.** Rejected. Four consecutive refusals say the
  bottleneck is not algorithmic, and optimising a number nobody has decomposed is how a project
  arrives at V47 with no evidence.
- **Go straight to the analyst interface.** Rejected. An interface built before the failure
  taxonomy would render explanations whose failure modes are not understood, and would be very
  hard to unbuild once it existed.
- **Run the full human study now.** Rejected. Plant-literate subjects are not available, and a study
  run with unqualified subjects would produce a number more misleading than no number.
- **Fold this into the category roadmap as Clock A sessions.** Rejected. Clock A is complete and its
  completion is a fact worth keeping intact; this is a different question with a different terminal
  measure.
- **Make the gates advisory.** Rejected — see Decision 2.
- **Begin U1 in this session.** Rejected: the instruction was to author the phase, and beginning the
  highest-value diagnostic item in the same session that defines it would mean designing the
  taxonomy and applying it under one set of assumptions, with nobody having reviewed the design.

## When to revisit

When Gate 1 and Gate 2 have both been decided. If either diagnosis says the plan is wrong, this
record is amended by a successor ADR rather than quietly reinterpreted. If the phase concludes that
PHOS's output does not help a human decide, that conclusion gets its own ADR and the refusal
register carries it permanently.

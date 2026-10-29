# ADR 0368: triangulation and a self-search are named as the next Atlas programme, after brief G

- **Status:** Accepted
- **Date:** 2026-10-29
- **PART:** Atlas, build brief H. Named here, not written here
- **Supersedes:** nothing. Two sentences of the operating plan stand down for brief H only, and stay in the plan
- **Depends on:** [ADR 0344](0344-industrial-protocol-coverage-is-declared.md),
  [ADR 0324](0324-the-operating-plan-loads-in-both-tools.md),
  [ADR 0321](0321-the-controller-comparison-is-true-or-false.md),
  [ADR 0322](0322-a-slot-enters-only-as-a-law-break.md),
  [ADR 0298](0298-five-questions-succeed-the-closed-stronger-engine-programme.md),
  [ADR 0073](0073-a-synthetic-command-and-maintenance-harness-that-measures-nothing.md)

## Context

The law page checks six laws on one simulated plant. Every law was written by hand. One of them,
`controller_valve`, is a comparison copied by hand out of the ICSSim PLC1 program, with that
program's literals quoted in `data/phos-icssim-dev/roles.toml`. ADR 0336 found the page empty on
every corpus run: the simulated plant never broke a declared law. The page is shown to behave.
It is not shown to catch anything.

On 29 October 2026 Elijah decided that Atlas's next programme should push what the engine can
establish, framed as a research question rather than as a product feature. Brief G, the protocol
programme, was declared the same day and is in progress. This record names what follows it.

Nothing here is a measurement. No corpus was opened. No code was written.

## Decision

1. **The question.** Given a plant's controller program, the physics of its process, and the laws
   its engineers sign, which departures can be shown to break at least one of the three, and
   which can be shown to break none of them? The programme assumes any rung may fail. A refusal is
   a result.

2. **Three independent sources of law.** Code laws are derived from the controller program.
   Physics laws are balances the process must obey, with constants quoted from a named source.
   Engineer laws are the existing register. A departure that breaks none of the three has to be
   consistent with all of them at once. That is the sense in which the three triangulate.

3. **The rungs, in a fixed order. Each waits on the one before. Each has its own declaration,
   committed before any code that scores it.**

   - **H1, code laws.** Laws are derived automatically from the ICSSim PLC program at the pinned
     commit. The first bar is agreement: the law derived for PLC1's valve comparison equals
     `controller_valve`, literal for literal (close `0.0`, open `1.0`, release mode `3.0`, belt
     `1.0`). A derived law that disagrees is refused. `controller_valve` is not edited to match
     it. Each break carries a certificate: the law, the rows it was evaluated on, and the
     comparison that came out false. Anyone holding the rows can recheck it without PHOS.
   - **H2, physics laws.** Balances on the simulated process, such as level change against flow
     in and flow out, each as its own declared law. If the simulator does not model a quantity,
     the law that needs it is refused rather than approximated. A corpus in which controller
     behaviour is altered while sensor values are replayed is declared, with its development half
     committed, before any of it is generated.
   - **H3, detectability prediction.** Before an attack corpus is generated, Atlas writes down
     which classes of departure the register can break and which it cannot. The corpus is then
     generated and scored once. The bar is agreement between prediction and outcome, in both
     directions. A departure predicted silent that stays silent meets the prediction. It is
     recorded as a blind spot, not as a success.
   - **H4, the self-search.** A search for departures that are consistent with the code and the
     physics and break no signed law, each reported with the smallest added law or sensor that
     would break it. It waits on H3 meeting its bar.

4. **Named and not opened.** Passive program attestation (whether a controller still runs the
   program that was signed, judged from its inputs and outputs), a should-have timeline replayed
   from code and physics, and confirmation of a law's meaning by example are later questions.
   They get no declaration from this record. A formally verified decider is a proof-assistant
   programme, which the operating plan section 4 does not open, and this record does not open it
   either.

5. **Brief H is written only after brief G closes (ADR 0363).** No numbers are reserved here.
   The brief reserves its own block when it is written, after
   `scripts/check_number_allocation.py` has seen every fetched branch.

6. **What stands down, for brief H only.** The operating plan says the freeze quarter adds no new
   law, and that `controller_valve`'s literals move only when a different plant's logic is quoted.
   H1 and H2 add laws before a partner exists. The literals do not move. Every new law still
   enters by its own ADR, written before it is scored. Both sentences stay in the plan for every
   other programme.

7. **Fences that travel with the programme.**
   - The page contract is unchanged: admission is `type(item) is LawBreak`, at most 8, ordered by
     time then law name, every sentence names its law, a score-word is refused. A certificate is
     subject to the same refusal and has no field that can hold a confidence, probability,
     weight, magnitude or score.
   - A detectability statement is a list of classes. It is not a rate, a coverage percentage or a
     recall, and is not restated as one.
   - The law module does not import the residual files.
   - Held-out corpora stay unopened until a declaration names them.
   - Simulated results are a simulated diagnosis, not a field rate (ADR 0073). Nothing here says
     Atlas would have caught a named real-world attack.
   - No Intelligence, API, UI, socket or TAP starts. v1 stays 8 of 12. P1 stays blocked.

8. **Attack recipes are controlled from the first one.** A departure found by H3 or H4 is a
   working recipe against the plant it was found on. Recipes against the simulated plant stay in
   this lab and do not export. `public/manifest.toml` gains their path as forbidden in the same
   commit that first writes one. Records carry the class of a blind spot, not its recipe. A
   recipe against a real plant never leaves that plant.

## Consequences

**Gained.** Atlas gets a question it can be wrong about in public. The `controller_valve` law,
copied once by hand, becomes the first check on the derivation that would replace the copying.
The blind spots stop being a sentence in a refusal register and become a prediction that is
tested.

**Cost.** Work on brief H is work not spent preparing for a plant. The first rung reads an
open-source simulator's program. Real controller programs come in several languages and vendor
formats, and nothing in H1 says the derivation transfers to them. A tool that finds working
attacks is itself sensitive, and Decision 8 is a cost carried from the start.

## What would reverse this

Starting brief H before ADR 0363 is written. Editing `controller_valve` to match a derived law.
Printing a detectability statement as a rate or a percentage. Exporting a recipe. Placing a
sentence or a certificate that carries a score-word. Claiming that Atlas would have caught a named
real-world attack on the strength of a simulated corpus.

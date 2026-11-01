# ADR 0396 — The DTU department is named, so the credit line is writable

- **Status:** Accepted
- **Date:** 2026-11-01
- **PART:** v1 C2, tools lane. Corpus provenance
- **Supersedes:** nothing. [ADR 0394](0394-the-dtu-pilot-plant-export-is-registered-for-onboarding-only.md)
  Decision 3 is not edited; this record closes the first of its four named gaps and leaves the other
  three standing
- **Depends on:** [ADR 0394](0394-the-dtu-pilot-plant-export-is-registered-for-onboarding-only.md),
  [ADR 0006](0006-dataset-registry-and-never-committing-data.md)

## Context

ADR 0394 Decision 3 recorded the sender's grant verbatim — *"You are welcome to publish and use the
obtained results commercially as long as appropriate credit is given to our department"* — and then
named four things the message does not settle. The first was:

> **Which department.** "Our department" is unnamed in the message. The credit line cannot be
> written until the department is confirmed, so no publication may precede that confirmation.

That gap blocked the corpus from being used in anything publishable. It was a gap in *knowledge*,
not in permission, and it is now closed from a public source.

## Decision

1. **The department is the Department of Chemical and Biochemical Engineering, Technical University
   of Denmark (DTU), and within it the PILOT PLANT section.** Confirmed on 2026-11-01 from the
   sender's own DTU staff page and cross-checked against the DTU Research Database entry for the
   PILOT PLANT organisation
   ([orbit.dtu.dk/en/organisations/pilot-plant/persons](https://orbit.dtu.dk/en/organisations/pilot-plant/persons/)).
   Both name the Department of Chemical and Biochemical Engineering; both list the sender there as
   an Associate Professor affiliated with PILOT PLANT. **The sender's name and staff-page address
   are deliberately not reproduced here.** He asked for credit to his department, not to himself,
   and ADR 0394 Decision 3 already keeps his address out of exported files; publishing the name
   would undo that care for no gain to the record's correctness. The confirmation can be rechecked
   from the organisation page above, which lists the department's staff itself.

2. **The credit line the citation field now carries is that department.** The line is:
   *Bubble column aeration 1F and continuous distillation 5A pilot-plant runs, Department of
   Chemical and Biochemical Engineering, Technical University of Denmark (DTU), July and September
   2026.* It is already the `citation` field of `dtu-lab` in `data/registry.json` and it is
   unchanged by this record — what changes is that it may now be used, because the department it
   names has been confirmed rather than inferred.

3. **`data/registry.json` `license.evidence` is corrected in one place.** Gap (1) read *"the
   department is unnamed, so the credit line cannot be written yet"*. It now records the
   confirmation, its date, and that the confirmation is an institutional page rather than a
   document about rights. The other three gaps are untouched and still travel with the corpus:
   whether DTU's own IP policy agrees, that the grant covers results and not redistribution of the
   payloads, and that it says nothing about what the columns mean.

4. **How the name was obtained is recorded, and what was not obtained is named.** It came from a
   public staff page the sender publishes himself. **No contact attempt was made to obtain it and
   none is recorded here.** The sender's email address stays out of every exported file, for the
   reason ADR 0394 Decision 3 gives: `data/*` exports publicly and the export's academic-address
   gate matches `.ac`/`.edu` suffixes, so a `.dk` address would pass the gate and publish a private
   individual's contact details.

5. **Naming the department does not make this a licence, and does not make it a partner.** The
   status stays `operator-stated`. A staff member's welcome is still not a statement that the
   institution holds or waives rights in student-generated laboratory data, so the second gap
   stands and is what an institutional answer would close.

## Consequences

- **The blocker on publishing results from this corpus is lifted to the extent a department name
  lifts it.** The corpus may be described and credited. Gaps (2), (3) and (4) still constrain what
  may be claimed and what may be redistributed.
- **C2 is still not met.** It is a human time trial; `eval_runs/build/v1/tools/c2-trial.md` is
  unfilled and an agent's run is a smoke test. v1 stays **8 of 12**.
- **Nothing was measured.** No corpus was opened, no detector was scored, `eval_runs/log.jsonl` was
  not appended, and no frozen row was read or rewritten.
- The one-line registry change is deliberate: rewriting the file through a JSON serialiser
  reformatted 62 unrelated lines, so the edit was made in place instead.

## What would reverse this

Publishing a result that names the department before crediting it in the form the citation field
gives; treating this record as the institution's permission rather than the sender's; recording the
sender's email address in any exported file; or reporting the corpus as usable for a detection
claim, a rate, or a held-out score.

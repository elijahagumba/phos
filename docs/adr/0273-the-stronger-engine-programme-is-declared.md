# ADR 0273 — The stronger-engine programme is declared, with its ADR numbers reserved

- **Status:** Accepted
- **Date:** 2026-10-20
- **PART:** Atlas, the engine after v1
- **Supersedes:** nothing
- **Depends on:** [ADR 0106](0106-four-checks-on-the-frozen-candidate.md),
  [ADR 0108](0108-consistency-evidence-routes-to-the-explanations.md),
  [ADR 0122](0122-a-phos-generated-icssim-corpus.md),
  [ADR 0269](0269-the-a7-regeneration-matched.md)

## Context

v1 reached 8 of 12 and freezes on 24 January 2027. Its detector,
`atlas-v1-consistency`, catches 37 of 38, 42 of 50, 53 of 58, 36 of 52 and 5 of 5
attacks within 8 alerts a shift, beating the best checked opponent on all five
judging corpora. Elijah's decision of 20 October 2026: the goal is an Atlas
**significantly stronger than that**, not merely better evidenced, and public
release should rest on the stronger engine.

Two facts shape how that can be pursued, and both were established before this
record rather than assumed.

**The engine's weaknesses are measured, not guessed.** Grouping alone accounts for
21 of 58 and 15 of 52, with the loop score supplying the rest and `P1_PCV01D` alone
driving 11 of the 53 catches (ADR 0106). The loop score predicts signals from other
signals only, so the command path never reaches detection — it reaches the
explanation layer and stops there (ADR 0108). Each signal is scored alone and only
at its peak.

**There is no real data left to improve against.** Every registered corpus was
checked against `data/registry.json` on 20 October. The five judging corpora are
seen and `data-tiers.md` forbids iterating on them. hai-20.07 is free to iterate on
and already yields 37 of 38, so it has no headroom. Morris and WUSTL are
`skipped-licence-unclear`, FORGE is `skipped-subscription-gated`,
s7-data-modification has its attack labels verified absent (ADR 0047),
tu-wien-pilot-factory's attacks never move the plant, 3W and Data4Cyber are faults
and phases (ADR 0046, ADR 0056), and SWaT, WADI, ICS-Flow and AIT-LDS are
licence-barred.

## Decision

1. **The programme is `docs/build-brief-2026-10-e.md`**, committed with this record.
   It holds the four lanes, each lane's bar, the data plan and the hard rules. A
   session on Claude or Cursor starts there.

2. **Progress is read from the record, not from a status line.** Each step reserves
   an ADR number, 0273 to 0284. The reserved numbers that exist are the steps done;
   the lowest missing one is where work resumes. `ls docs/adr/ | grep -E
   '^02(7[3-9]|8[0-4])'` is the whole status check. This is deliberate: the
   programme tracker stood two months stale because a counter nobody wrote was the
   source of truth (ADR 0266), and on 20 October two sessions each took the next
   free ADR number and collided twice, costing a renumber. Work outside this
   programme takes **0285** onward.

3. **The corpus comes first (0274).** No lane may be developed against a validation
   corpus, and the one freely iterable real corpus is saturated, so the ICSSim
   generation in ADR 0122 is a precondition rather than optional setup. It is also
   the only source that carries control traffic and process telemetry for the same
   plant, which lane 1 requires. `phos-icssim-heldout` is generated and not opened;
   generating is not opening. GRFICSv3 is the second source, registered and split
   before use.

4. **Four lanes, each frozen and declared before its one score.** Lane 1 gives the
   engine the commanded value as a predictor, so a reading that does not follow its
   order becomes a residual it can detect rather than only explain. Lane 2 scores
   the whole vector of prediction errors jointly. Lane 3 accumulates small
   deviations over time instead of waiting for a peak. Lane 4 replaces the linear
   predictor with one that can bend. Each bar is in the brief, each is strictly
   more attacks caught within the same budget plus a second condition that stops a
   gain being bought elsewhere, and a tie is not a pass.

5. **This programme does not touch v1.** `atlas-v1-consistency` is never edited;
   every attempt is a new name measured beside it. No v1 number is overwritten,
   rescored or reworded, and v1 stays 8 of 12 unless its own criteria move.

6. **Step 0284 is Elijah's alone.** Saying "significantly stronger than the engine
   we shipped" means scoring the finished candidate once on the corpora where the
   old numbers live, which spends a fourth one-look exception in `data-tiers.md`.
   That authorisation is not given by this record and no session may assume it.

## Consequences

Atlas has a written route from "well evidenced" to "stronger", the first step is
hours of compute rather than a decision, and any session can tell in one command
where the programme stands. Until step 0284, no claim from this programme is a
claim about real plant data.

## What would reverse this

Editing the frozen detector, developing a lane against a seen corpus, opening
`phos-icssim-heldout` without its declaration, taking a reserved ADR number for
unrelated work, or reporting a simulated gain as a result about real plants.

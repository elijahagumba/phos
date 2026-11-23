# ADR 0420 — One Atlas engineering roadmap, and the rest are closed or parked

- **Status:** Accepted
- **Date:** 2026-11-03
- **PART:** Programme. The engineering sequence for Atlas
- **Supersedes:** nothing. It **absorbs** roadmap F and the daily-leaps contract, **adopts** brief H as
  the roadmap's Acts II–IV, and **parks** brief G. No record is edited; ADR 0369 is left exactly as
  written, including H2–H4 staying closed until after 6 January 2027
- **Depends on:** [ADR 0049](0049-split-scorecard-public-files-vs-partner.md),
  [ADR 0290](0290-bet-003-the-first-shift.md),
  [ADR 0300](0300-a-kept-day-halves-the-remaining-misses.md),
  [ADR 0324](0324-the-operating-plan-loads-in-both-tools.md),
  [ADR 0412](0412-research-and-engineering-run-through-a-record-a-machine-can-read.md),
  [ADR 0336](0336-the-law-page-invariants-hold-and-the-corpus-was-silent.md),
  [ADR 0368](0368-triangulation-and-a-self-search-are-named-after-brief-g.md),
  [ADR 0369](0369-h1-runs-now-and-the-later-rungs-wait-for-the-bid.md)

## Context

Seven programmes were open at once: the daily-leaps contract (ADR 0300), roadmap F, build brief G,
build brief H rung H1, the zero-to-one operating plan (ADR 0324), GENESIS (ADR 0412), and P1. Each
was justified when it was opened. The effect of all seven together was that any morning offered seven
defensible pieces of work and none of them named a criterion it moved.

The human stated the problem directly on 3 November 2026: too complex to found a company around, and
one roadmap is wanted — explicitly an engineering one.

This is worth recording as a cause rather than a complaint. Six of the seven were opened while **P1
was blocked**, and P1 is the one thing that would have ordered the work. Programmes accumulated
because the ordering input was missing, not because anyone lost discipline.

## What the record says, once gathered in one place

Atlas's criteria are A1–A7, frozen with their definitions in `docs/v1-roadmap.md` before any of them
was measured. Gathered from the records rather than restated:

| | Status | Record |
|---|---|---|
| A1 | met | ADR 0264; grouped block not recomputed |
| A2 | met | Strictly higher than grouped MinMax 5 of 5, beyond chance on 4; every corpus **seen** |
| A3 | **not met** | Instrument retired (ADR 0290); ranking attempted and refused (ADR 0068) |
| A4 | met | — |
| A5 | met | — |
| A6 | met | — |
| A7 | **not met** | Three frozen constants and the outside run; both looks spent (ADRs 0268–0272) |

**Five of seven.** With C1 met, C2 not, S1 and S2 met and S3 not, that reconstructs the **8 of 12**
the tracker already carries. Nothing here is a new measurement and nothing moves v1.

The consequence is sharper than the question that prompted it. "As good as Atlas can be with what
exists" is not open-ended: on the corpora that exist, Atlas already meets five of its seven
criteria, and the remaining two are **A3** and **A7**.

## Decision

**1. One roadmap: `docs/atlas-engineering-roadmap.md`, in four acts.** Act I settles the debts —
the ADR 0316 score, A7, then A3 against Bet 003's four bars. Acts II, III and IV are brief H's
rungs: triangulation across three independent sources of law, blind spots declared before the
corpus exists, and the self-search that reports the smallest added law or sensor which would break
each invisible departure.

A1–A7 remain the destination, because they were frozen before any result came in, and Act I is
where the two open ones are settled. But the criteria are a scorecard, not a thesis, and a roadmap
organised only around them describes a system that is correct rather than one that is
unprecedented. Acts II–IV are what the product is *for*; Act I is what makes anything it says
defensible.

**2. A3 and A7 are named as questions, not tasks.** A3's instrument has already been retired once
(ADR 0290) and a ranking stage has already been built and refused once (ADR 0068). A7's two looks are
spent. A roadmap that listed them as work to be completed would be promising a result, which is the
failure mode this project's rules exist to prevent. Each needs its own declaration, including a
statement of what would show the criterion cannot be met — and a record saying it cannot is an
ending, not a gap.

**3. A7 is ranked above A3.** A6 is met: one configuration. A6 is worth nothing without A7, because a
single configuration nobody outside can execute is a claim about a private machine. A7 is also the
only criterion whose failure is partly infrastructural rather than scientific, so it is the one where
effort reliably converts into progress.

**4. The declared-law page is the engine spine, and its problem is not invariants.**
`declared_law.py` and `law_inlet.py` (ADR 0325) are what make the constitution's speech contract
code rather than intention. `law-inlet:invariants` was declared by ADR 0335 and measured by
ADR 0336 with **all eight bars met** — earlier rule text saying it waits on a declaration is stale
and is corrected here.

What ADR 0336 also found is the point: the plant never broke a declared law, and all thirty-nine
corpus-derived pages were empty. The page is shown to behave and is **not** shown to speak when it
should. More invariant work cannot fix that. A corpus that breaks a law can, which is precisely
what Acts II and III build — and is the substantive reason brief H is adopted rather than parked.

**5. Dispositions, named so a future session cannot quietly reopen one.** Roadmap F and the
daily-leaps contract are **absorbed** — a kept day remains a good shape for a measurement and stops
being a destination. Brief G is **parked**: its further protocols move neither A3 nor A7, and without
a partner capture a second dissector is specification without evidence. **Brief H is adopted** as
Acts II–IV; ADR 0369's timing is untouched, so H1 is open and H2–H4 stay closed until after
6 January 2027 for the Ofwat Catalyst bid. Adopting a programme whose later rungs are closed is
deliberate: it fixes where the work is going without starting it early. Build brief E stays closed
(ADR 0297) with 0277–0284 unwritten.
`docs/ipo-roadmap-2026-2034.md` is untouched, being not an engineering document. **Parked** means not
deleted, not forbidden, and not restarted without a record naming the criterion it moves.

**6. GENESIS is the method and is not in the sequence.** It is how each step runs, not a step.

**7. The ADR 0316 debt is the first item.** That record declared the joint command vector and it has
never been scored. A declared-and-unrun experiment is the one state the record exists to make
visible, and finishing something already declared is the cheapest honest work available.

**8. The dual-use fence travels with Acts III and IV.** A departure found by H3 or H4 is a working
recipe against the plant it was found on. ADR 0368 Decision 8 governs them unchanged: recipes stay
with that plant, are not published, not generalised, and not carried into another programme. H4
waits on H3 meeting its bar, and H1 generates no recipe, so no recipe can exist before H2 reopens.
The deliverable of Act IV is a sensor recommendation, never an exploit.

## What this record does not do

It lifts nothing. P1 remains a blocked human conversation, and this roadmap neither unblocks it nor
proceeds as though it had happened — Intelligence, the API and the UI stay closed behind it. Every
frozen number stays frozen, and no bar in the roadmap may be met by moving one. The data tiers stand.
The v1 criteria are not reopened or reworded, and v1's freeze date stays 24 January 2027.

No measurement was run to produce this record. No corpus was opened. `genesis state` still reads one
question and one judged experiment. v1 stays 8 of 12.

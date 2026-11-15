# ADR 0423 — H2 opens for its declarations only, and the scoring still waits for the bid

- **Status:** Accepted
- **Date:** 2026-11-07
- **PART:** Atlas, build brief H, rung H2. Opening record. No code, no corpus, no measurement
- **Supersedes:** nothing
- **Depends on:** ADR 0369 (lab record, not published),
  [ADR 0368](0368-triangulation-and-a-self-search-are-named-after-brief-g.md),
  [ADR 0420](0420-one-atlas-engineering-roadmap-and-the-rest-are-closed-or-parked.md),
  [ADR 0422](0422-build-brief-g-is-unparked-against-the-refusal-register.md),
  [ADR 0383](0383-the-guard-form-result-is-a-refusal-and-the-products-still-part.md)

## Context

ADR 0369 closed rungs H2, H3 and H4 "until after 6 January 2027, **or until a later record opens
them. Whichever comes first.**" This is that record, for H2 and for one half of it.

The reason ADR 0369 recorded was not engineering readiness. It was one person's time:

> Engine work that is not needed for that bid competes with it for the only person who can make it.

H1 was let through because it was cheap and independent. H2 was held because it needs "corpus
generation, prediction and a search, and that is the time the bid needs." That reasoning is sound
and this record keeps it — for the expensive half. It does not hold for the cheap half, because
**declaring a law is a document and scoring it is a programme.** The two halves of H2 were closed
together because nothing had separated them. This record separates them.

Two things should be written down rather than left implicit.

The first is that the window ADR 0369 protected was not spent on the bid. Between 29 October and
today, brief G's packet foundation was judged (ADR 0346), the programme was unparked (ADR 0422), a
whole S7comm lane was declared, built, judged and landed (ADR 0347, ADR 0348), a roadmap was
consolidated (ADR 0420), and H1 ran and had its guard form **refused** (ADR 0383). Meanwhile the
bid's own blocking step — `docs/ipo-roadmap-2026-2034.md` §7.2, a licensed water company to lead
the entry, which §7.1 calls "the single most time-critical item in the repository" — still reads
**Not started**, and the three outreach emails drafted on 4 October still read **Not sent**. The
closure did not protect the bid window. It changed which engine work filled it.

That is not an argument for opening the expensive half. It is an argument for being honest that
closing a rung is not the same as advancing a bid, and for keeping the expensive half closed on its
own merits rather than on a premise that the record no longer supports.

The second is that H2 is the rung most likely to matter to that bid if it ever gets written. Its
worked example in `docs/build-brief-2026-10-h.md` is a balance on a tank — level against flow in
and flow out. A water plant is that balance. The declarations are also the one artefact a water
company could be shown before anything is measured: here are the laws we would check on your
plant, and here is what we would refuse to claim.

## Decision

**H2 opens for its declarations and for nothing else. The corpus, the generation, the scoring and
the verdict stay closed until after 6 January 2027, or until a later record opens them.**

1. **The laws may be declared.** [ADR 0372](0372-the-physics-laws-are-declared-from-the-thirteen-tags-and-the-inlet-balance-is-refused.md)
   is that declaration: which balances become declared laws, which are refused, and the bar each
   must meet when it is built.
2. **No corpus is declared, generated or scored.** The brief's corpus sentence — "a corpus in which
   controller behaviour is altered while sensor values are replayed is declared, with its
   development half committed, before any of it is generated" — is untouched. That declaration
   takes its own number, not 0372, and not before the date in point 4.
3. **No code is written under `src/phos/atlas/` by this change.** The register additions ADR 0372
   specifies are built later, against the bars ADR 0372 freezes now. ADR 0373 stays reserved and
   unwritten: there is nothing yet to judge.
4. **H3 and H4 stay closed**, until after 6 January 2027 or until their own later record. ADR 0369
   Decision 2 is amended as to H2's declaration half alone. **ADR 0369 is not edited.**
5. **Reaching 6 January 2027 is still not permission.** ADR 0369's sentence stands: the rung needs
   its own declaration committed before any code that scores it. Point 1 supplies the declaration
   for the laws; the corpus will need its own.

## What this record does not do

- It is **not permission to score anything**, on any corpus, at any tier.
- It makes **no detection claim**. A declared physics law is not a detector, and a law page is not
  evidence that Atlas finds attacks. v1 stays **8 of 12**; A3 and A7 stay open.
- It does not open H3 or H4, does not unpark anything ADR 0420 parked beyond what ADR 0422 already
  unparked, and does not fill reserved numbers 0277–0284.
- It does not lift a data tier, retune a frozen constant, or touch `.phos_roadmap_state.json`.
- It does not unblock **P1**, which remains the blocked human conversation, with Intelligence, the
  API and the UI closed behind it.
- It does not advance the Ofwat bid. Only an email to a licensed water company does that, and no
  record can send one.

## What would reverse this

If the declarations cannot be written truthfully without reading the pinned simulator source that
this repository does not carry, or without generating a corpus, then the cheap half was not cheap
and H2 returns to closed until the date in Decision 4. ADR 0372 reports exactly where it ran into
that boundary rather than approximating past it.

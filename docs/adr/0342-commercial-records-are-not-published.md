# ADR 0342 — Commercial records are not published, and the export enforces it

- **Status:** Accepted
- **Date:** 2026-10-28
- **Supersedes:** [ADR 0334](0334-the-destination-is-a-listing-and-the-date-moves.md) in its
  publication only. Every decision ADR 0334 took stands, unchanged, in the private lab. Nothing in
  this record reverses, softens or restates one.
- **Related:** [ADR 0044](0044-public-surfaces-on-main-must-move-with-every-advancement.md),
  [ADR 0201](0201-the-front-page-leads-with-real-data-and-a-contact.md)

## Context

This repository publishes a measurement record: what was built, what was measured, what was
refused, and the decision behind each. `public/manifest.toml` decides what leaves the private lab,
and it already withholds the files that describe how PHOS gets a partner or raises money —
`docs/investor-*`, `docs/design-partner-*`, `docs/partner-routes.md`, `outreach/*`.

`docs/adr/*` is a **wholesale include**. Every decision record exports, which is right for a
project whose argument is that its decisions are inspectable. But it means a record that reasons
about commercial or personal financial matters publishes by default, with no gate between writing it
and serving it, and the manifest's named exclusions do not catch it because the record lives under
`docs/adr/` like every other.

ADR 0334 is such a record. It was exported and served publicly, which was not intended and was not
noticed at the time of the export. The decisions it contains are sound and remain in force. Its
audience was never the public.

The structural fault is the absence of a gate, not the existence of the record. A named exclusion
for one file fixes one file; the next commercial record would publish the same way.

## Decision

1. **ADR 0334 is withdrawn from the public export.** `public/manifest.toml` `[forbidden].paths`
   gains `docs/adr/0334-*`. The record is not edited, not deleted and not superseded in substance:
   it stays in the private lab as an accepted record, and its decisions continue to govern.
2. **The export gains a commercial-content gate.** `[forbidden].content` gains patterns for the
   vocabulary of a funding or ownership discussion — a sum of money in millions or billions, a
   compound annual growth rate, a dilution or round term, a projected earnings schedule. One hit stops the
   export, which fails loudly rather than publishing quietly. Each pattern was tested against the
   whole current export before being added, and each matched nothing but the record being withdrawn.
3. **The public decision index keeps the number and declines the record.**
   `docs/adr/README.md`'s row for 0334 says it is a commercial record held back, rather than
   vanishing. A gap in a numbered sequence is a question a careful reader asks, and the honest
   answer is cheap. No figure, target, probability or valuation is restated anywhere in the public
   tree.
4. **This record is published.** A reader is entitled to know that the repository withholds
   commercial material, because that is a limit on what the record shows. Stating the policy costs
   nothing; the material it withholds is what must not be stated.

## Consequences

A false block is now possible: a legitimate measurement that happens to use one of the patterns
will stop an export. That is the intended direction of failure — a stopped export is a human
reading a diff, and `[forbidden].allowed` takes an exact string with its reason when a match is
genuinely fine.

Removing the file stops it being served. **It does not remove it from the public repository's
history**, where it was committed, and a blob can stay reachable by its hash until the host
collects it. That is stated here rather than implied, and whether to rewrite that history is not a
decision this record takes.

Three records held on another branch reason about market size and projected earnings. They are not
published today, and when that branch lands the content gate in Decision 2 will stop their export
rather than let it happen silently. That is the gate working as intended, not a defect to route
around.

## What would reverse this

Publishing a commercial or personal financial figure anywhere in the exported tree; weakening a
content pattern to let an export through instead of holding the record back; editing or deleting
ADR 0334 in the lab, which would destroy an accepted record to tidy a mistake made in publishing
it; or treating a withdrawn publication as a withdrawn decision.

## A note on this record's own wording

This record names the *categories* the content gate catches rather than quoting its patterns, and
the patterns live in `public/manifest.toml` where they are read. A record that had to be added to
`[forbidden].allowed` in order to publish itself would have weakened the gate everywhere to describe
it once.

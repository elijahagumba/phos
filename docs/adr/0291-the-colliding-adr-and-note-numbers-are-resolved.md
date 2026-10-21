# ADR 0291 — Two ADR numbers and two note numbers were taken twice, and the earlier pair keeps them

- **Status:** Accepted
- **Date:** 2026-10-21
- **PART:** Process, the public record
- **Supersedes:** nothing
- **Depends on:** [ADR 0044](0044-public-surfaces-on-main-must-move-with-every-advancement.md),
  [ADR 0268](0268-the-a7-regeneration-is-declared.md),
  [ADR 0269](0269-the-a7-regeneration-matched.md),
  [ADR 0287](0287-the-live-brief-is-discoverable-from-the-rules.md),
  [ADR 0289](0289-the-build-record-reaches-the-public-tree.md),
  [ADR 0290](0290-bet-003-the-first-shift.md)

## Context

On 20 October 2026 two sessions worked on separate branches and each took ADR numbers 0268 and
0269 for different decisions, three minutes apart. This is the second instance of that failure on
that date; `docs/build-brief-2026-10-e.md` records the first.

| Number | Committed first, on `main` | Committed second, on `claude/phos-public-release-status-76feb0` |
| --- | --- | --- |
| 0268 | the A7 regeneration is declared, 14:21:14 | the build record reaches the public tree, 14:24:38 |
| 0269 | the A7 regeneration matched | Bet 003, the first shift, 14:47:34 |

The collision had a consequence beyond tidiness. The public repository `phos` is generated from
this lab by `scripts/export_public.py` and is never edited by hand, and it had last been exported
from the unmerged branch. So the public tree held the *second* pair under 0268/0269, while `main`
held the first pair under the same numbers. Exporting from the engine branch before merging would
have deleted `docs/adr/0268-...`, `docs/adr/0269-...` and `docs/bets/003-the-first-shift.md` from
`phos` — Bet 003, a published prediction, erased rather than renumbered.
<!-- evidence-ack: docs/adr/0268-... — the path as it stood in the public tree before this renumber; in this repository that record is docs/adr/0289-the-build-record-reaches-the-public-tree.md -->
<!-- evidence-ack: docs/adr/0269-... — the path as it stood in the public tree before this renumber; in this repository that record is docs/adr/0290-bet-003-the-first-shift.md -->
<!-- evidence-ack: docs/bets/003-the-first-shift.md — the exported path in phos; the source here is public/overlay/docs/bets/003-the-first-shift.md, which the overlay rebases to the repository root on export -->


Merging also surfaced a **second collision that had gone unnoticed**, because its two sides had
different filenames and so git merged them silently rather than reporting a conflict: both
branches had written plain-English notes **78** and **79**, for different subjects. The tree
briefly held two of each.

| Number | On `main` | On the unmerged branch |
| --- | --- | --- |
| 78 | the second way to ask who is new (S3) | the record the front page could not show |
| 79 | the numbers come back from the files (A7) | the bar that was measuring the wrong thing |

## Decision

**The pair committed first keeps 0268 and 0269.** Three independent grounds, any one of which
would be sufficient:

1. **It was committed first** — 14:21:14 against 14:24:38, verifiable from `git log`.
2. **It is on `main`.** The other pair's branch was not merged when the collision was found.
3. **It is already cited** by `README.md`, `docs/adr/README.md`, ADR 0269 itself, and ADR 0273,
   the stronger-engine programme's own declaration. Renumbering it would break a citation in a
   live programme's declaration.

**The second pair renumbers to 0289 and 0290**, preserving their order: the build record (14:24)
becomes 0289, Bet 003 (14:47) becomes 0290. Each file keeps a note at the top recording the number
it was written under, so a reader who follows an old reference is not left guessing.

**The note collision is resolved on the same grounds, to 85 and 86.** The notes on `main` keep 78
and 79; the branch's two become note **85** (the record the front page could not show, ADR 0289)
and note **86** (the bar that was measuring the wrong thing, ADR 0290). This was not in the plan
the previous session handed over — it had not spotted this collision — but re-deciding the grounds
for the same conflict between the same two branches would be inventing a second rule for one
problem.

**Nothing public breaks**, and that is why the renumber is cheap rather than a cost: `phos` is
still private, nothing outside the project cites 0268, 0269, 78 or 79, and the export regenerates
the tree wholesale.

## Consequences

The renumbered records sit out of date order in `encyclopedia/12-adr-catalogue.md`, under their
20 October topic headings with 0289 and 0290 as their numbers. That is the honest arrangement: the
decisions were taken on 20 October and the numbers were assigned on 21 October, and the catalogue
already handles one such case (ADR 0274, written after the work it names).

The next export of `phos` will show these as renames — two ADR files and two note files deleted
under their old names and added under new ones. That diff must be read as a rename and not as the
deletion trap this record exists to describe. Nothing else should disappear.

**The cause is unfixed and will recur.** Two sessions on two branches both take "the next free
number" from their own tree, and neither can see the other's. Nothing in the repository allocates
numbers across branches, and `ls docs/adr/` on a branch is not evidence about `main`. ADR 0273's
reserved-number block (0273–0284) is the only mitigation in place and it covers one programme's
steps, not unrelated work. A third instance should be treated as a tooling problem rather than
another renumber.

## What would reverse this

A citation to 0268 or 0269 from outside this repository, which would make renumbering the second
pair the wrong way round — but that cannot now arise, because the first pair keeps those numbers
and the second pair's old numbers were never public. Or a decision to allocate ADR numbers from a
single committed register, after which collisions stop happening and this record becomes history
rather than precedent.

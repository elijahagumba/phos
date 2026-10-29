# ADR 0381: the front door is corrected, and the freeze opens for explanatory figures

- **Status:** Accepted (Elijah's decision, 29 October 2026)
- **Date:** 2026-10-29
- **PART:** the public front page; `docs/v1-roadmap.md`'s branding freeze
- **Supersedes:** nothing
- **Depends on:** [ADR 0200](0200-the-public-repository-takes-the-house-style.md),
  [ADR 0327](0327-the-front-door-shows-the-path-and-labels-the-older-engine.md),
  [ADR 0342](0342-commercial-records-are-not-published.md),
  [ADR 0044](0044-public-surfaces-on-main-must-move-with-every-advancement.md),
  [ADR 0368](0368-triangulation-and-a-self-search-are-named-after-brief-g.md)

## Context

`docs/v1-roadmap.md` freezes branding for sixteen weeks from 5 October 2026: no README, card, film
or design work until week 13, **except to correct something untrue**. Today is week 4.

Two separate things brought the front page back open, and they are not the same kind of thing.

**The first is a false statement.** `public/overlay/README.md` opens with "PHOS is a behavioural
cybersecurity company." On 29 October 2026 Elijah confirmed that no company exists. The footer of
the same page already says the true thing, that PHOS is built by one researcher with AI coding
agents, so the page contradicts itself and the stronger claim is the one a reader meets first. A
reader who checks, and the four audiences `docs/voice.md` names all check, finds no company. That
is the overclaim the whole project argues against, printed in its own first sentence. ADR 0200's
correction of 21 October 2026 already removed a company entity's name from the documentation; the
word "company" survived it in the public overlay.

**The second is a request.** On 29 October 2026 Elijah asked for the front page to carry diagrams,
mathematics and charts, so that a reader can see the path a line takes to the page, read the page
contract as the code enforces it, and see what the refused lanes measured rather than only read
the sentence that reports them. None of that corrects an untruth, so the freeze's own exception
does not cover it. It needs a decision, and the decision is Elijah's to make.

ADR 0200 is the precedent for how that is done: Elijah asked, the work was done to the settled
house style, and the crossing was recorded rather than assumed. Nothing there was a new identity.

## Decision

1. **The first sentence is corrected under the freeze's own exception, not under a new
   permission.** The public front page describes PHOS near the top as an independent research
   project built by one researcher with AI coding agents. The word "company" does not appear as a
   description of what PHOS is. This part of the work needs no crossing: correcting something
   untrue is what the freeze already allows.

2. **The freeze is crossed for explanatory figures, diagrams and mathematics only**, by Elijah's
   decision of 29 October 2026, recorded here. What that admits, and nothing else:
   - **Diagrams** as Mermaid blocks in the README, so GitHub renders them from text a reader can
     read in the diff.
   - **Mathematics** as GitHub LaTeX, stating only what `src/phos/atlas/declared_law.py` already
     enforces, with a plain-English sentence under each line.
   - **Charts** as SVG plates generated beside `public/figures/build_figures.py`, in that file's
     palette, type and margin checks, with every plotted value read from a committed record.

3. **No identity work is admitted.** No logo, no colour, no second accent, no new typeface, no new
   spacing scale, no film, no card, no demo video. The existing plates are moved, not edited and
   not redrawn. `brand/` is untouched. ADR 0200's achromatic decision stands, and the one blue in
   `public/figures/build_figures.py` stays what that record made it: data ink, not a heading
   colour and not a severity.

4. **A figure the record does not hold is not drawn.** Every plotted value is read from a committed
   file at build time, and a test fails when a plotted value stops matching its source. Three
   charts are drawn this way: the lane 3 dial from `eval_runs/build/lane-e/lane3-development.md`
   (ADR 0286), the lane 4 knot settings from `eval_runs/build/lane-e/lane4-development.md`
   (ADR 0288), and the older engine against the best grouped checked opponent from
   `eval_runs/v1/a2-status.json` (ADR 0116).

   A fourth was asked for and is **refused**: alert loudness against whether an alert was an
   attack, from ADR 0068. `eval_runs/atlas/hai-operator-queue.md` holds the ranks of the six true
   alerts and the magnitude at seven budget cuts. It does not hold a loudness value paired with an
   attack flag for each of the 424 alerts, and the corpus that would regenerate them is a tier
   `docs/rules/data-tiers.md` forbids reading. So the chart is not drawn, the README says the
   record does not hold it, and the sentence ADR 0068 already supports stays as prose.

5. **Planned work is labelled planned.** The triangulation diagram carries ADR 0368's name and
   says it is not built beyond H1. A diagram is not a claim that the thing in it runs.

6. **Every existing number, caveat and "cannot do" item stays exactly as true as it was.** No new
   number is introduced anywhere by this change. The measurements on the page keep their scope
   sentences: seen data is called seen, simulated is called simulated, and the four unmet v1
   criteria stay listed. The older engine's measurements move under a heading that names them as
   the older engine, which is ADR 0327's decision applied to the page rather than a new one.

7. **The plain-English notes publish.** `public/manifest.toml` `include` gains `easy to reads/*`
   and `[forbidden].paths` gives that prefix up, because a tree cannot be both included and
   forbidden. One note is held back by name: the plain-English companion to the commercial record
   ADR 0342 withdrew. It is excluded with its reason and listed under `[forbidden].paths` as well,
   exactly as ADR 0342 did for the record itself, so a later widening of `include` refuses the
   export instead of publishing it quietly. `easy to reads/README.md` keeps that note's number and
   declines it, in place of the paragraph that restated the withheld plan, which ADR 0342
   Decision 3 requires and which that paragraph broke. No content pattern is weakened and no
   pattern is added.

8. **The missing record numbers are explained.** `docs/adr/README.md` gains one paragraph naming
   the three reasons a number in the exported sequence has no file: reserved and never written,
   held on a branch that has not merged, and withheld under ADR 0342. It names the categories and
   the ranges. It does not name what a withheld record says.

### Options

1. Leave "company" in the first sentence until week 13. Refused. The freeze exists so the engine
   comes first, not so a false sentence keeps its place for nine weeks.
2. Correct the sentence and refuse the figures until week 13. Available, and it was not chosen.
   Elijah asked for the figures now, and the cost is counted in the Consequences below.
3. Rebuild the whole front page, including the plates and the identity, now. Refused. That is
   week 13's work from v1 numbers, and ADR 0200 did not open it either.
4. Draw the fourth chart from the ranks the record does hold, labelled as ranks. Refused. The
   question asked was loudness against attack, the record does not answer it, and a chart that
   answers a different question under the same heading is the kind of substitution this repository
   exists to refuse.

## Consequences

**Gained.** The front page no longer opens on a claim a reader can falsify in one search. A reader
can follow a line from the plant's own rules to the page without reading code, read the page
contract as mathematics beside the function that enforces it, and see the shape of two refused
lanes rather than only their one-sentence summaries. The charts cannot drift from the record,
because the build reads the record and a test fails when a plotted value stops matching it. The
plain-English notes, written for a reader who should not start at decision records, become
reachable from the public repository.

**Cost.** This is design work in week 4, which the freeze was written to prevent, and it is the
second crossing after ADR 0200. Two crossings make a habit, and the next request should be weighed
against that rather than against this record alone. The front page is still rebuilt from v1
numbers in week 13, and this work does not count towards it. Nothing here moves a measurement, so
v1 stays 8 of 12 and P1 stays a blocked human conversation. The chart script needs `fonttools`,
which is not a project dependency, so the half of its test that rebuilds the plates is skipped
where that library is absent; the half that checks every plotted value against its source record
runs everywhere.

**A gap left open.** The twelve live assets on the public front page were brought into the overlay
from the public repository, recorded in `docs/voice.md` section 8, and the script that drew them is
not in this lab. `public/figures/build_figures.py` still draws the eight plates that the overlay no
longer uses. So two generations of plate builder exist and only one of them matches what the page
shows. This change adds its charts beside the committed builder rather than guessing at the lost
one, and that mismatch is named here rather than tidied over.

## What would reverse this

A logo, a colour, a typeface or a second spacing scale changing before week 13. A figure on the
front page whose value is typed in rather than read from a record. A planned programme drawn
without its label. A new number appearing on the page without a record behind it. Describing PHOS
as a company anywhere in the public tree. Publishing the withheld note, or restating what it says.
Weakening an export content pattern to let a note through.

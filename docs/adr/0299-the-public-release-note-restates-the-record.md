# ADR 0299 — The public release note restates the record

- **Status:** Accepted
- **Date:** 2026-10-22
- **PART:** the public research pre-release
- **Supersedes:** nothing
- **Depends on:** [ADR 0044](0044-public-surfaces-on-main-must-move-with-every-advancement.md),
  [ADR 0116](0116-a2-status-four-of-five-beyond-chance.md),
  [ADR 0200](0200-the-public-repository-takes-the-house-style.md),
  [ADR 0201](0201-the-front-page-leads-with-real-data-and-a-contact.md),
  [ADR 0276](0276-lane-1-met-its-bar-on-held-out-runs.md),
  [ADR 0286](0286-an-appended-column-cannot-win-a-slot-without-taking-the-alert.md),
  [ADR 0288](0288-the-linear-predictors-misfit-is-load-bearing.md),
  [ADR 0297](0297-build-brief-e-is-closed-without-a-stronger-engine.md)

## Context

The public front page is the house-style cards (ADR 0200, ADR 0201). The licence is PolyForm
Noncommercial 1.0.0. Launch drafts in `outreach/launch-posts.md` had not been posted. Three of
them compressed a recorded band into its flattering end: three refused gains, where the record
is one kept result, two refusals, and a fourth attempt that could not be posed; a quarter fewer
false alarms and nine fewer catches, where ADR 0288 measured 28.00 a day down to between 20.00
and 24.00, and 32 catches down to between 23 and 25; and a 66 percent rise, where ADR 0286
measured 21 more attacks, 32 to 53 of 70. The PHOS thread's last post said every number
rebuilds by one command. Four of the five pinned records do. The three headline constants
stay frozen under their own names, and nobody outside has run the command, so A7 is not met
(ADR 0268, ADR 0269).

## Decision

**The public research pre-release is a one-page note that restates the record. The cards stay.
The licence stays. No measurement is added.**

The note is `docs/release.md` in the public tree. In this lab it is
`public/overlay/docs/release.md`, and the export copies it onto that public path. It leads with
the PolyForm Noncommercial licence, the demo command, 131 of 160 against 52 for the best
baseline checked (ADR 0116), v1 at 8 of 12 with A3, A7, S3 and C2 still open, the queue and the
maintenance tie, and the simulated results labelled as simulated. A7 stays unmet.

The unsent drafts are corrected to those bands, and the claim that every number rebuilds is
corrected to four of five, with A7 unmet. A Show HN draft sits in the same lab file. The
export forbids `outreach/`, so the drafts do not enter the public tree. Pushing and posting
remain Elijah's actions.

## Consequences

A visitor can quote the note without opening an image. A figure on it still has to name its
ADR. The corrected drafts are what can be posted.

## What would reverse this

A figure on the note with no record behind it. A rewrite of the cards' claims. A licence change
made inside this packaging. Posting the compressed drafts.
